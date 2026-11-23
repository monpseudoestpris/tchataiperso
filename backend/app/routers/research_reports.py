"""Routes HTTP pour la planification, les rapports DeepSearch / Mode Apprendre et les exports HTML/Slides."""

from __future__ import annotations

import logging
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..chat_export_html import generate_chat_export_html
from ..chat_site_store import get_or_create_chat_site
from ..config import Settings
from ..deep_search_html import generate_report_html
from ..deps import current_user, get_conversation, get_sessions, get_settings
from ..google_cloud import has_llm_access
from ..google_deep_research import plan_google_deep_research
from ..learn_html import generate_learn_course_html
from ..models import Conversation, DeepSearchReport, LearnReport, Message, User
from ..presentation_html import (
    generate_chat_presentation_html,
    generate_report_presentation_html,
)
from ..schemas import DeepSearchPlanResponse, LearnModePlanResponse, PlanDeepSearch, PlanLearnMode
from ..serializers import deep_search_report_json, learn_report_json

_logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["research-reports"])


@router.post("/api/conversations/{conversation_id}/deep-search/plan", response_model=DeepSearchPlanResponse)
async def plan_conversation_deep_search(
    conversation_id: str,
    body: PlanDeepSearch,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    has_google_dr_key = bool(
        body.model
        and "google" in body.model.lower()
        and "deep-research" in body.model.lower()
        and settings.enabled(settings.google_api_key)
    )
    if not settings.demo_mode and not (has_llm_access(settings, (body.model or "").strip() or None) or has_google_dr_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou Google Cloud, ou activez explicitement DEMO_MODE pour une simulation")
    if not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")

    with sessions() as db:
        conversation = get_conversation(db, conversation_id, user.id)
        search_summary = conversation.summary
        search_context = [
            {"role": item.role, "content": item.content}
            for item in conversation.messages[-4:]
        ]

    raw_query = body.content.strip()[:1500]
    if body.model and "google" in body.model.lower() and "deep-research" in body.model.lower():
        try:
            g_plan = await plan_google_deep_research(
                settings=settings,
                query=raw_query,
                model=body.model,
                summary=search_summary or "",
                recent_turns=search_context,
                learn_mode=False,
                previous_interaction_id=body.interaction_id,
            )
            return DeepSearchPlanResponse(
                queries=g_plan.get("queries", []),
                plan_text=g_plan.get("plan_text"),
                interaction_id=g_plan.get("interaction_id"),
            )
        except Exception as exc:
            _logger.warning("Collaborative planning Google Deep Research indisponible: %s", exc)

    st_plan_model = body.stage_models.plan_model if body.stage_models and body.stage_models.plan_model else None
    try:
        try:
            queries = await providers.plan_deep_search_queries(
                settings, raw_query, search_summary, search_context, model=st_plan_model,
            )
        except TypeError:
            queries = await providers.plan_deep_search_queries(
                settings, raw_query, search_summary, search_context,
            )
    except providers.ProviderError as exc:
        _logger.warning("Planification DeepSearch indisponible: %s", exc)
        queries = providers.default_deep_search_themes(raw_query)

    return DeepSearchPlanResponse(queries=queries)


@router.post("/api/deep-search/plan", response_model=DeepSearchPlanResponse)
async def plan_direct_deep_search(
    body: PlanDeepSearch,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    has_google_dr_key = bool(
        body.model
        and "google" in body.model.lower()
        and "deep-research" in body.model.lower()
        and settings.enabled(settings.google_api_key)
    )
    if not settings.demo_mode and not (has_llm_access(settings, (body.model or "").strip() or None) or has_google_dr_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou Google Cloud, ou activez explicitement DEMO_MODE pour une simulation")
    if not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")

    raw_query = body.content.strip()[:1500]
    if body.model and "google" in body.model.lower() and "deep-research" in body.model.lower():
        try:
            g_plan = await plan_google_deep_research(
                settings=settings,
                query=raw_query,
                model=body.model,
                summary="",
                recent_turns=[],
                learn_mode=False,
                previous_interaction_id=body.interaction_id,
            )
            return DeepSearchPlanResponse(
                queries=g_plan.get("queries", []),
                plan_text=g_plan.get("plan_text"),
                interaction_id=g_plan.get("interaction_id"),
            )
        except Exception as exc:
            _logger.warning("Collaborative planning Google Deep Research indisponible: %s", exc)

    st_plan_model = body.stage_models.plan_model if body.stage_models and body.stage_models.plan_model else None
    try:
        try:
            queries = await providers.plan_deep_search_queries(
                settings, raw_query, "", [], model=st_plan_model,
            )
        except TypeError:
            queries = await providers.plan_deep_search_queries(
                settings, raw_query, "", [],
            )
    except providers.ProviderError as exc:
        _logger.warning("Planification DeepSearch indisponible: %s", exc)
        queries = providers.default_deep_search_themes(raw_query)

    return DeepSearchPlanResponse(queries=queries)


@router.get("/api/deep-search/reports")
def list_deep_search_reports(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        items = list(
            db.scalars(
                select(DeepSearchReport)
                .where(DeepSearchReport.user_id == user.id)
                .order_by(DeepSearchReport.created_at.desc())
            )
        )
        return [deep_search_report_json(item) for item in items]


@router.get("/api/deep-search/reports/{report_id}")
def get_deep_search_report(
    report_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(DeepSearchReport).where(
                DeepSearchReport.id == report_id, DeepSearchReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Rapport DeepSearch introuvable")
        return deep_search_report_json(report, include_html=True)


@router.get("/api/deep-search/reports/{report_id}/html")
def get_deep_search_report_html(
    report_id: str,
    download: bool = False,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(DeepSearchReport).where(
                DeepSearchReport.id == report_id, DeepSearchReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Rapport DeepSearch introuvable")

        headers = {}
        if download:
            clean_ascii = unicodedata.normalize("NFKD", report.title).encode("ascii", "ignore").decode("ascii")
            clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "rapport-deepsearch"
            headers["Content-Disposition"] = f'attachment; filename="{clean_filename}.html"'

        html_doc = generate_report_html(
            title=report.title,
            topic=report.topic,
            markdown_content=report.markdown_content,
            sources=report.sources or [],
            created_at_str=report.created_at.strftime("%d/%m/%Y") if report.created_at else None,
        )
        return Response(
            content=html_doc,
            media_type="text/html; charset=utf-8",
            headers=headers,
        )


@router.get("/api/deep-search/reports/{report_id}/slides")
async def get_deep_search_report_slides(
    report_id: str,
    download: bool = False,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(DeepSearchReport).where(
                DeepSearchReport.id == report_id, DeepSearchReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Rapport DeepSearch introuvable")

        title = report.title
        markdown_content = report.markdown_content
        topic = report.topic
        created_at_str = report.created_at.strftime("%d/%m/%Y") if report.created_at else None
        sources = list(report.sources or [])

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if download:
        clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
        clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "presentation-deepsearch"
        headers["Content-Disposition"] = f'attachment; filename="{clean_filename}-slides.html"'

    html_doc = await generate_report_presentation_html(
        settings=settings,
        title=title,
        markdown_content=markdown_content,
        topic=topic,
        model="DeepSearch",
        created_at_str=created_at_str,
        sources=sources,
    )
    return Response(
        content=html_doc,
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@router.delete("/api/deep-search/reports/{report_id}")
def delete_deep_search_report(
    report_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(DeepSearchReport).where(
                DeepSearchReport.id == report_id, DeepSearchReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Rapport DeepSearch introuvable")
        db.delete(report)
        db.commit()
        return {"ok": True}


@router.post("/api/deep-search/reports/from-message/{message_id}")
def create_or_get_report_from_message(
    message_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        existing = db.scalar(
            select(DeepSearchReport).where(
                DeepSearchReport.message_id == message_id, DeepSearchReport.user_id == user.id
            )
        )
        if existing:
            return deep_search_report_json(existing, include_html=True)

        message = db.scalar(
            select(Message)
            .join(Conversation)
            .where(
                Message.id == message_id,
                Message.role == "assistant",
                Conversation.user_id == user.id,
            )
        )
        if not message:
            raise HTTPException(404, "Message introuvable")

        conv = message.conversation
        report_title = conv.title if conv and conv.title != "Nouvelle conversation" else "Rapport d'analyse DeepSearch"
        topic = report_title
        if conv and conv.messages:
            prev_users = [m.content for m in conv.messages if m.role == "user" and m.created_at <= message.created_at]
            if prev_users:
                topic = prev_users[-1]

        created_at_dt = message.created_at
        html_doc = generate_report_html(
            title=report_title,
            topic=topic,
            markdown_content=message.content,
            sources=message.sources or [],
            created_at_str=created_at_dt.strftime("%d/%m/%Y à %H:%M"),
        )
        new_report = DeepSearchReport(
            user_id=user.id,
            conversation_id=conv.id if conv else None,
            message_id=message.id,
            title=report_title,
            topic=topic,
            markdown_content=message.content,
            html_content=html_doc,
            sources=message.sources or [],
            created_at=created_at_dt,
        )
        db.add(new_report)
        db.commit()
        db.refresh(new_report)
        return deep_search_report_json(new_report, include_html=True)


@router.post("/api/conversations/{conversation_id}/learn/plan", response_model=LearnModePlanResponse)
async def plan_conversation_learn_mode(
    conversation_id: str,
    body: PlanLearnMode,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    has_google_dr_key = bool(
        body.model
        and "google" in body.model.lower()
        and "deep-research" in body.model.lower()
        and settings.enabled(settings.google_api_key)
    )
    if not settings.demo_mode and not (has_llm_access(settings, (body.model or "").strip() or None) or has_google_dr_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou Google Cloud, ou activez explicitement DEMO_MODE pour une simulation")
    if not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")

    with sessions() as db:
        conversation = get_conversation(db, conversation_id, user.id)
        search_summary = conversation.summary
        search_context = [
            {"role": item.role, "content": item.content}
            for item in conversation.messages[-4:]
        ]

    raw_query = body.content.strip()[:1500]
    if body.model and "google" in body.model.lower() and "deep-research" in body.model.lower():
        try:
            g_plan = await plan_google_deep_research(
                settings=settings,
                query=raw_query,
                model=body.model,
                summary=search_summary or "",
                recent_turns=search_context,
                learn_mode=True,
                previous_interaction_id=body.interaction_id,
            )
            return LearnModePlanResponse(
                queries=g_plan.get("queries", []),
                plan_text=g_plan.get("plan_text"),
                interaction_id=g_plan.get("interaction_id"),
            )
        except Exception as exc:
            _logger.warning("Collaborative planning Google Deep Research indisponible: %s", exc)

    st_plan_model = body.stage_models.plan_model if body.stage_models and body.stage_models.plan_model else None
    try:
        try:
            queries = await providers.plan_learn_queries(
                settings, raw_query, search_summary, search_context, model=st_plan_model,
            )
        except TypeError:
            queries = await providers.plan_learn_queries(
                settings, raw_query, search_summary, search_context,
            )
    except providers.ProviderError as exc:
        _logger.warning("Planification Mode Apprendre indisponible: %s", exc)
        queries = providers.default_learn_themes(raw_query)

    return LearnModePlanResponse(queries=queries)


@router.post("/api/learn/plan", response_model=LearnModePlanResponse)
async def plan_direct_learn_mode(
    body: PlanLearnMode,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    has_google_dr_key = bool(
        body.model
        and "google" in body.model.lower()
        and "deep-research" in body.model.lower()
        and settings.enabled(settings.google_api_key)
    )
    if not settings.demo_mode and not (has_llm_access(settings, (body.model or "").strip() or None) or has_google_dr_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou Google Cloud, ou activez explicitement DEMO_MODE pour une simulation")
    if not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")

    raw_query = body.content.strip()[:1500]
    if body.model and "google" in body.model.lower() and "deep-research" in body.model.lower():
        try:
            g_plan = await plan_google_deep_research(
                settings=settings,
                query=raw_query,
                model=body.model,
                summary="",
                recent_turns=[],
                learn_mode=True,
                previous_interaction_id=body.interaction_id,
            )
            return LearnModePlanResponse(
                queries=g_plan.get("queries", []),
                plan_text=g_plan.get("plan_text"),
                interaction_id=g_plan.get("interaction_id"),
            )
        except Exception as exc:
            _logger.warning("Collaborative planning Google Deep Research indisponible: %s", exc)

    st_plan_model = body.stage_models.plan_model if body.stage_models and body.stage_models.plan_model else None
    try:
        try:
            queries = await providers.plan_learn_queries(
                settings, raw_query, "", [], model=st_plan_model,
            )
        except TypeError:
            queries = await providers.plan_learn_queries(
                settings, raw_query, "", [],
            )
    except providers.ProviderError as exc:
        _logger.warning("Planification Mode Apprendre indisponible: %s", exc)
        queries = providers.default_learn_themes(raw_query)

    return LearnModePlanResponse(queries=queries)


@router.get("/api/learn/reports")
def list_learn_reports(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        items = list(
            db.scalars(
                select(LearnReport)
                .where(LearnReport.user_id == user.id)
                .order_by(LearnReport.created_at.desc())
            )
        )
        return [learn_report_json(item) for item in items]


@router.get("/api/learn/reports/{report_id}")
def get_learn_report(
    report_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(LearnReport).where(
                LearnReport.id == report_id, LearnReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Cours introuvable")
        return learn_report_json(report, include_html=True)


@router.get("/api/learn/reports/{report_id}/html")
def get_learn_report_html(
    report_id: str,
    download: bool = False,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(LearnReport).where(
                LearnReport.id == report_id, LearnReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Cours introuvable")

        headers = {}
        if download:
            raw_title = report.title or "cours-complet"
            ascii_title = unicodedata.normalize("NFKD", raw_title).encode("ascii", "ignore").decode("ascii")
            safe_title = re.sub(r"[^\w\s-]", "", ascii_title).strip()
            safe_title = re.sub(r"[\s_]+", "-", safe_title).lower() or "cours"
            filename = f"{safe_title[:60]}.html"
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'

        html_doc = generate_learn_course_html(
            title=report.title,
            topic=report.topic,
            markdown_content=report.markdown_content,
            sources=report.sources or [],
            created_at_str=report.created_at.strftime("%d/%m/%Y") if report.created_at else None,
        )
        return Response(
            content=html_doc,
            media_type="text/html; charset=utf-8",
            headers=headers,
        )


@router.get("/api/learn/reports/{report_id}/slides")
async def get_learn_report_slides(
    report_id: str,
    download: bool = False,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(LearnReport).where(
                LearnReport.id == report_id, LearnReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Cours introuvable")

        title = report.title or "Cours cLAIr"
        markdown_content = report.markdown_content
        topic = report.topic
        created_at_str = report.created_at.strftime("%d/%m/%Y") if report.created_at else None
        sources = list(report.sources or [])

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if download:
        clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
        clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "presentation-cours"
        headers["Content-Disposition"] = f'attachment; filename="{clean_filename}-slides.html"'

    html_doc = await generate_report_presentation_html(
        settings=settings,
        title=title,
        markdown_content=markdown_content,
        topic=topic,
        model="cLAIr Apprendre",
        created_at_str=created_at_str,
        sources=sources,
    )
    return Response(
        content=html_doc,
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@router.delete("/api/learn/reports/{report_id}")
def delete_learn_report(
    report_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        report = db.scalar(
            select(LearnReport).where(
                LearnReport.id == report_id, LearnReport.user_id == user.id
            )
        )
        if not report:
            raise HTTPException(404, "Cours introuvable")
        db.delete(report)
        db.commit()
        return {"ok": True}


@router.post("/api/learn/reports/from-message/{message_id}")
def create_or_get_learn_report_from_message(
    message_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        existing = db.scalar(
            select(LearnReport).where(
                LearnReport.message_id == message_id, LearnReport.user_id == user.id
            )
        )
        if existing:
            return learn_report_json(existing, include_html=True)

        message = db.scalar(
            select(Message)
            .join(Conversation)
            .where(
                Message.id == message_id,
                Message.role == "assistant",
                Conversation.user_id == user.id,
            )
        )
        if not message:
            raise HTTPException(404, "Message introuvable")

        conv = message.conversation
        course_title = conv.title if conv and conv.title != "Nouvelle conversation" else "Cours complet"
        topic = course_title
        if conv and conv.messages:
            prev_users = [m.content for m in conv.messages if m.role == "user" and m.created_at <= message.created_at]
            if prev_users:
                topic = prev_users[-1]

        created_at_dt = message.created_at
        html_doc = generate_learn_course_html(
            title=course_title,
            topic=topic,
            markdown_content=message.content,
            sources=message.sources or [],
            created_at_str=created_at_dt.strftime("%d/%m/%Y à %H:%M"),
        )
        new_report = LearnReport(
            user_id=user.id,
            conversation_id=conv.id if conv else None,
            message_id=message.id,
            title=course_title,
            topic=topic,
            markdown_content=message.content,
            html_content=html_doc,
            sources=message.sources or [],
            created_at=created_at_dt,
        )
        db.add(new_report)
        db.commit()
        db.refresh(new_report)
        return learn_report_json(new_report, include_html=True)


@router.get("/api/messages/{message_id}/html")
async def get_message_html(
    message_id: str,
    scope: str = "turn",
    download: bool = False,
    pdf: bool = False,
    print_mode: bool = Query(False, alias="print"),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        message = db.scalar(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.id == message_id,
                Conversation.user_id == user.id,
            )
        )
        if not message:
            raise HTTPException(404, "Message introuvable")

        conv = message.conversation
        preceding_user = next((
            m for m in reversed(conv.messages)
            if m.role == "user" and m.created_at <= message.created_at
        ), None)
        turn_messages_for_site = [
            {"role": m.role, "content": m.content, "sources": m.sources or []}
            for m in (preceding_user, message) if m is not None
        ]

        # Si l'utilisateur demande la synthèse complète de la conversation
        if scope in ("conversation", "all"):
            title = conv.title or "Synthèse de la discussion cLAIr"
            messages_data = [
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at_str": m.created_at.strftime("%d/%m/%Y %H:%M") if m.created_at else "",
                    "sources": m.sources or [],
                }
                for m in conv.messages
            ]
            html_doc = generate_chat_export_html(
                title=title,
                messages=messages_data,
                scope="conversation",
                topic=conv.title,
                model=conv.model,
                created_at_str=conv.created_at.strftime("%d/%m/%Y") if conv.created_at else None,
                summary=conv.summary or "",
            )
        else:
            # 1. Vérifier si ce message possède un rapport Learn
            learn_rep = db.scalar(
                select(LearnReport).where(
                    LearnReport.message_id == message.id,
                    LearnReport.user_id == user.id,
                )
            )
            if learn_rep:
                title = learn_rep.title or "Cours cLAIr"
                html_doc = generate_learn_course_html(
                    title=learn_rep.title,
                    topic=learn_rep.topic,
                    markdown_content=learn_rep.markdown_content,
                    sources=learn_rep.sources or [],
                    created_at_str=learn_rep.created_at.strftime("%d/%m/%Y") if learn_rep.created_at else None,
                )
            else:
                # 2. Vérifier si ce message possède un rapport DeepSearch
                ds_rep = db.scalar(
                    select(DeepSearchReport).where(
                        DeepSearchReport.message_id == message.id,
                        DeepSearchReport.user_id == user.id,
                    )
                )
                if ds_rep:
                    title = ds_rep.title or "Rapport DeepSearch"
                    html_doc = generate_report_html(
                        title=ds_rep.title,
                        topic=ds_rep.topic,
                        markdown_content=ds_rep.markdown_content,
                        sources=ds_rep.sources or [],
                        created_at_str=ds_rep.created_at.strftime("%d/%m/%Y") if ds_rep.created_at else None,
                    )
                else:
                    # 3. Message classique : Question & Réponse
                    prev_user_msg = db.scalar(
                        select(Message)
                        .where(
                            Message.conversation_id == message.conversation_id,
                            Message.role == "user",
                            Message.created_at <= message.created_at,
                        )
                        .order_by(Message.created_at.desc())
                    )
                    topic = prev_user_msg.content.strip() if prev_user_msg else (conv.title or "Échange cLAIr")
                    title = conv.title or topic[:60] or "Échange cLAIr"

                    turn_messages = []
                    if prev_user_msg:
                        turn_messages.append({
                            "role": "user",
                            "content": prev_user_msg.content,
                            "created_at_str": prev_user_msg.created_at.strftime("%d/%m/%Y %H:%M") if prev_user_msg.created_at else "",
                            "sources": [],
                        })
                    turn_messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "created_at_str": message.created_at.strftime("%d/%m/%Y %H:%M") if message.created_at else "",
                        "sources": message.sources or [],
                    })

                    html_doc = generate_chat_export_html(
                        title=title,
                        messages=turn_messages,
                        scope="turn",
                        topic=topic,
                        model=conv.model,
                        created_at_str=message.created_at.strftime("%d/%m/%Y %H:%M") if message.created_at else None,
                    )

        has_dedicated_report = scope not in ("conversation", "all") and bool(learn_rep or ds_rep)
        if not (pdf or print_mode or has_dedicated_report):
            site_messages = [
                {"role": m.role, "content": m.content, "sources": m.sources or []}
                for m in conv.messages
            ] if scope in ("conversation", "all") else turn_messages_for_site
            html_doc = await get_or_create_chat_site(
                db, settings, conv.id, title, site_messages,
                "conversation" if scope in ("conversation", "all") else "turn",
                "" if scope in ("conversation", "all") else message.id,
            )
        headers = {}
        if download:
            clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
            clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "document"
            headers["Content-Disposition"] = f'attachment; filename="{clean_filename}.html"'

        return Response(
            content=html_doc,
            media_type="text/html; charset=utf-8",
            headers=headers,
        )


@router.get("/api/messages/{message_id}/slides")
async def get_message_slides(
    message_id: str,
    scope: str = "turn",
    download: bool = False,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        message = db.scalar(
            select(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Message.id == message_id,
                Conversation.user_id == user.id,
            )
        )
        if not message:
            raise HTTPException(404, "Message introuvable")

        conv = message.conversation

        if scope in ("conversation", "all"):
            title = conv.title or "Synthèse de la discussion cLAIr"
            messages_data = [
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at_str": m.created_at.strftime("%d/%m/%Y %H:%M") if m.created_at else "",
                    "sources": m.sources or [],
                }
                for m in conv.messages
            ]
            html_doc = await generate_chat_presentation_html(
                settings=settings,
                title=title,
                messages=messages_data,
                scope="conversation",
                topic=conv.title,
                model=conv.model,
                created_at_str=conv.created_at.strftime("%d/%m/%Y") if conv.created_at else None,
                summary=conv.summary or "",
            )
        else:
            # 1. Vérifier si ce message possède un rapport Learn
            learn_rep = db.scalar(
                select(LearnReport).where(
                    LearnReport.message_id == message.id,
                    LearnReport.user_id == user.id,
                )
            )
            if learn_rep:
                title = learn_rep.title or "Cours cLAIr"
                html_doc = await generate_report_presentation_html(
                    settings=settings,
                    title=learn_rep.title,
                    markdown_content=learn_rep.markdown_content,
                    topic=learn_rep.topic,
                    model=conv.model or "cLAIr Apprendre",
                    created_at_str=learn_rep.created_at.strftime("%d/%m/%Y") if learn_rep.created_at else None,
                    sources=learn_rep.sources or [],
                )
            else:
                # 2. Vérifier si ce message possède un rapport DeepSearch
                ds_rep = db.scalar(
                    select(DeepSearchReport).where(
                        DeepSearchReport.message_id == message.id,
                        DeepSearchReport.user_id == user.id,
                    )
                )
                if ds_rep:
                    title = ds_rep.title or "Rapport DeepSearch"
                    html_doc = await generate_report_presentation_html(
                        settings=settings,
                        title=ds_rep.title,
                        markdown_content=ds_rep.markdown_content,
                        topic=ds_rep.topic,
                        model=conv.model or "DeepSearch",
                        created_at_str=ds_rep.created_at.strftime("%d/%m/%Y") if ds_rep.created_at else None,
                        sources=ds_rep.sources or [],
                    )
                else:
                    # 3. Message classique : Question & Réponse
                    prev_user_msg = db.scalar(
                        select(Message)
                        .where(
                            Message.conversation_id == message.conversation_id,
                            Message.role == "user",
                            Message.created_at <= message.created_at,
                        )
                        .order_by(Message.created_at.desc())
                    )
                    topic = prev_user_msg.content.strip() if prev_user_msg else (conv.title or "Échange cLAIr")
                    title = conv.title or topic[:60] or "Présentation cLAIr"

                    turn_messages = []
                    if prev_user_msg:
                        turn_messages.append({
                            "role": "user",
                            "content": prev_user_msg.content,
                            "created_at_str": prev_user_msg.created_at.strftime("%d/%m/%Y %H:%M") if prev_user_msg.created_at else "",
                            "sources": [],
                        })
                    turn_messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "created_at_str": message.created_at.strftime("%d/%m/%Y %H:%M") if message.created_at else "",
                        "sources": message.sources or [],
                    })

                    html_doc = await generate_chat_presentation_html(
                        settings=settings,
                        title=title,
                        messages=turn_messages,
                        scope="turn",
                        topic=topic,
                        model=conv.model,
                        created_at_str=message.created_at.strftime("%d/%m/%Y %H:%M") if message.created_at else None,
                    )

        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        if download:
            clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
            clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "presentation"
            headers["Content-Disposition"] = f'attachment; filename="{clean_filename}-slides.html"'

        return Response(
            content=html_doc,
            media_type="text/html; charset=utf-8",
            headers=headers,
        )
