import asyncio
from collections.abc import AsyncIterator
import logging
import re
import unicodedata
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..base_prompt import BASE_USER_PROMPT
from ..config import Settings
from ..context import build_context
from ..deep_search import execute_deep_search
from ..evidence_ledger import extract_deterministic_evidence_from_sources
from ..fact_verifier import format_verification_markdown, remedy_unverified_claims, run_repair_loop, verify_report_figures
from ..chat_export_html import generate_chat_export_html
from ..deep_search_html import generate_report_html
from ..learn_mode import execute_learn_mode
from ..learn_html import generate_learn_course_html
from ..multi_agent import execute_multi_agent_contradictory_debate, execute_multi_agent_debate, execute_multi_agent_synthesis
from ..deps import check_model, claim, current_user, get_conversation, get_sessions, get_settings, get_upload_dir
from ..documents import extraction_text
from ..finance import process_message_finance_inquiries
from ..memory_agent import process_memory_turn
from ..models import Attachment, Conversation, DeepSearchReport, LearnReport, Message, Memory, Skill, User, now
from ..schemas import DeepSearchPlanResponse, LearnModePlanResponse, PlanDeepSearch, PlanLearnMode, SendMessage
from ..serializers import conversation_json, deep_search_report_json, extract_mentioned_skills, learn_report_json, message_json, sse
from ..web import fetch_and_parse_web_url


_DEFAULT_STREAM_CHAT = providers.stream_chat
_DEFAULT_PLAN_REPORT_OUTLINE = providers.plan_report_outline
_DEFAULT_CLASSIFY_CONVERSATION = providers.classify_conversation
_DEFAULT_REWRITE_SEARCH_QUERY = providers.rewrite_search_query
_DEFAULT_SEARCH_WEB = providers.search_web
_DEFAULT_SEARCH_WEB_IMAGES = providers.search_web_images
_logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["messages"])


@router.post("/api/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessage,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
    if not body.content.strip() and not body.attachment_ids:
        raise HTTPException(422, "Écrivez un message ou joignez un document")
    if (body.web_search or body.deep_search or body.learn_mode) and not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")
    lock = claim(request, user.id, conversation_id)
    await lock.acquire()
    try:
        with sessions() as db:
            conversation = get_conversation(db, conversation_id, user.id)
            user_selected_model = body.model or conversation.model
            if body.model and body.model in {m["id"] for m in settings.models}:
                conversation.model = body.model
            model = user_selected_model

            # Configuration modulaire des modèles par étape pour DeepSearch et Mode Apprendre
            st_cfg = body.stage_models
            stage_plan_model = (
                (st_cfg.plan_model if st_cfg and st_cfg.plan_model else None)
                or getattr(settings, "deep_search_plan_model", None)
                or "google/gemini-4-argon"
            )
            stage_search_model = (
                (st_cfg.search_model if st_cfg and st_cfg.search_model else None)
                or getattr(settings, "deep_search_synthesis_model", None)
                or "google/gemini-3.8-flash"
            )
            stage_expert_model = (
                (st_cfg.expert_model if st_cfg and st_cfg.expert_model else None)
                or (body.model if body.model else None)
                or getattr(settings, "deep_search_synthesis_model", None)
                or "google/gemini-3.8-flash"
            )
            stage_synthesis_model = (
                (st_cfg.synthesis_model if st_cfg and st_cfg.synthesis_model else None)
                or (body.model if body.model else None)
                or getattr(settings, "deep_search_synthesis_model", None)
                or "google/gemini-3.8-flash"
            )
            stage_audit_model = (
                (st_cfg.audit_model if st_cfg and st_cfg.audit_model else None)
                or getattr(settings, "deep_search_audit_model", None)
                or "openai/gpt-6-astra"
            )

            if body.deep_search or body.learn_mode:
                model = stage_synthesis_model
            try:
                model_info = check_model(settings, model)
            except HTTPException:
                if body.deep_search or body.learn_mode:
                    model_info = {
                        "id": model,
                        "name": model,
                        "vision": True,
                        "provider": model.split("/")[0] if "/" in model else "openrouter",
                    }
                else:
                    raise
            attachments = []
            for attachment_id in body.attachment_ids:
                item = db.scalar(
                    select(Attachment)
                    .where(Attachment.id == attachment_id, Attachment.user_id == user.id)
                    .with_for_update()
                )
                if not item or item.message_id:
                    raise HTTPException(422, "Pièce jointe introuvable ou déjà utilisée")
                attachments.append(item)
            if sum(item.mime_type.startswith("image/") for item in attachments) > 4:
                raise HTTPException(422, "Joignez au maximum 4 images par message pour qu'elles soient toutes analysées")
            for item in attachments:
                if (
                    item.mime_type.startswith("image/")
                    and not item.extracted_text
                    and not model_info["vision"]
                    and not settings.demo_mode
                ):
                    raise HTTPException(422, "Joignez à nouveau cette image pour l'analyser, ou choisissez un modèle vision.")
            message = Message(conversation_id=conversation_id, role="user", content=body.content.strip())
            db.add(message)
            db.flush()
            for item in attachments:
                item.message_id = message.id

            # Auto-parse any web URLs contained directly in the message text
            raw_urls = re.findall(r'https?://[^\s<>"]+', body.content)
            existing_urls = {
                att.extraction.get("url")
                for att in attachments
                if isinstance(att.extraction, dict) and att.extraction.get("url")
            }
            urls_to_fetch = []
            for u in raw_urls:
                clean_u = u.rstrip(".,;:!?)'\"")
                if clean_u and clean_u not in existing_urls and clean_u not in urls_to_fetch:
                    urls_to_fetch.append(clean_u)

            for target_url in urls_to_fetch[:3]:
                try:
                    u_fn, u_cnt, u_mime, u_txt, u_extr = await fetch_and_parse_web_url(settings, target_url)
                    u_storage = str(uuid4())
                    u_path = upload_dir / u_storage
                    u_path.write_bytes(u_cnt)
                    web_att = Attachment(
                        user_id=user.id,
                        filename=u_fn,
                        mime_type=u_mime,
                        size=len(u_cnt),
                        storage_name=u_storage,
                        extracted_text=u_txt,
                        extraction=u_extr,
                        message_id=message.id,
                    )
                    db.add(web_att)
                    attachments.append(web_att)
                except Exception as exc:
                    _logger.warning("Échec d'analyse automatique de l'URL %s: %s", target_url, exc)

            # Auto-fetch real-time financial & stock data (EOD Historical Data, Yahoo Finance)
            u_skills_pre = list(db.scalars(select(Skill).where(Skill.user_id == user.id)))
            active_skill_prompts = [
                s.prompt.lower()
                for s in (extract_mentioned_skills(body.content, u_skills_pre) + [s for s in u_skills_pre if s.id in body.skill_ids])
            ]
            has_finance_skill = any("financ" in p or "bours" in p for p in active_skill_prompts)
            is_finance_active = body.finance_mode or (has_finance_skill and not body.deep_search and not body.learn_mode)
            previous_finance_targets: list[str] = []
            recent_turns: list[dict[str, str]] = []
            for past in conversation.messages:
                if past.id == message.id:
                    continue
                recent_turns.append({"role": past.role, "content": past.content})
                for past_att in past.attachments:
                    ext = past_att.extraction if isinstance(past_att.extraction, dict) else {}
                    if ext.get("model") in ("yahoo-finance", "eod-historical-data") and ext.get("symbol"):
                        sym = str(ext["symbol"])
                        if sym in previous_finance_targets:
                            previous_finance_targets.remove(sym)
                        previous_finance_targets.insert(0, sym)
            entity_resolver = None
            if not settings.demo_mode and settings.enabled(settings.llm_api_key) and not body.deep_search and not body.learn_mode:
                async def entity_resolver(text: str, previous: list[str]) -> list[str]:
                    return await providers.extract_finance_targets(settings, text, previous, recent_turns[-4:])
            finance_failures: list[str] = []
            try:
                if (not body.deep_search and not body.learn_mode) or body.finance_mode:
                    finance_atts = await process_message_finance_inquiries(
                        settings,
                        body.content,
                        attachments,
                        user.id,
                        message.id,
                        upload_dir,
                        finance_mode=is_finance_active,
                        previous_targets=previous_finance_targets,
                        entity_resolver=entity_resolver,
                        failures=finance_failures,
                    )
                    for f_att in finance_atts:
                        db.add(f_att)
                        attachments.append(f_att)
            except Exception as exc:
                _logger.warning("Échec lors de la recherche financière: %s", exc)

            if not (body.deep_search or body.learn_mode):
                conversation.model = model
            conversation.updated_at = now()
            auto_title_eligible = False
            if not conversation.messages or len(conversation.messages) <= 1:
                if conversation.title == "Nouvelle conversation":
                    auto_title_eligible = True
                    conversation.title = (body.content.strip() or attachments[0].filename)[:70]
            needs_classification = auto_title_eligible or not conversation.theme or not conversation.keywords
            initial_title = conversation.title
            prompt_for_meta = body.content.strip() or (attachments[0].filename if attachments else "")
            db.commit()
            db.refresh(message)
            user_message = message_json(message)
            assistant_id = str(uuid4())
    except providers.ProviderError as exc:
        lock.release()
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        lock.release()
        raise

    async def _search_with_limit(query_text: str, limit: int) -> list[dict[str, str]]:
        try:
            return await providers.search_web(settings, query_text, limit=limit)
        except TypeError:
            return await providers.search_web(settings, query_text)

    user_prompt_cache = getattr(user, "prompt_cache_enabled", True)
    user_general_prompt = (getattr(user, "system_prompt", "") or "").strip() or BASE_USER_PROMPT

    async def _stream_chat_with_keepalive(
        chat_context: list[dict],
        target_model: str,
        ping_interval: float = 2.0,
        enable_cache: bool = True,
    ) -> AsyncIterator[tuple[str, bool]]:
        try:
            gen = providers.stream_chat(settings, chat_context, target_model, enable_cache=enable_cache)
        except TypeError:
            gen = providers.stream_chat(settings, chat_context, target_model)
        aiterator = gen.__aiter__()
        pending: asyncio.Task | None = None
        while True:
            if pending is None:
                pending = asyncio.create_task(aiterator.__anext__())
            done, _ = await asyncio.wait([pending], timeout=ping_interval)
            if done:
                try:
                    chunk = pending.result()
                    pending = None
                    yield (chunk, False)
                except StopAsyncIteration:
                    pending = None
                    break
            else:
                yield (": keepalive\n\n", True)

    async def _collect_chat(chat_context: list[dict], target_model: str, enable_cache: bool = True) -> str:
        """Appel LLM indépendant dont la réponse complète est collectée (analyse d'un expert)."""
        try:
            gen = providers.stream_chat(settings, chat_context, target_model, enable_cache=enable_cache)
        except TypeError:
            gen = providers.stream_chat(settings, chat_context, target_model)
        text = ""
        async for chunk in gen:
            text += chunk
            if len(text) > 60000:
                break
        return text

    async def stream():
        accumulated = ""
        sources = []
        try:
            yield ": keepalive\n\n"
            yield sse("meta", {"user_message": user_message, "assistant_message_id": assistant_id})
            with sessions() as db:
                u_skills = list(db.scalars(select(Skill).where(Skill.user_id == user.id)))
                init_active_skills = [
                    s.name
                    for s in (extract_mentioned_skills(body.content, u_skills) + [s for s in u_skills if s.id in body.skill_ids])
                ]
            if init_active_skills:
                yield sse("status", {"message": f"Compétence active · {' · '.join(init_active_skills)}…"})
            finance_items = [
                item
                for item in attachments
                if item.filename.startswith("📈")
                or (isinstance(item.extraction, dict) and item.extraction.get("model") in ("yahoo-finance", "eod-historical-data"))
            ]
            for f_item in finance_items:
                ext = f_item.extraction if isinstance(f_item.extraction, dict) else {}
                symbol = ext.get("symbol") or "Actif"
                short_name = ext.get("short_name") or f_item.filename
                price = ext.get("price")
                curr = ext.get("currency") or "USD"
                chg = ext.get("change_percent")
                chg_str = f" ({chg:+.2f}%)" if chg is not None else ""
                price_str = f"{price} {curr}{chg_str}" if price is not None else ""
                is_eod = ext.get("model") == "eod-historical-data" or ext.get("provider") == "eodhd"
                provider_name = "EOD Historical Data" if is_eod else "Yahoo Finance"
                sources.append({
                    "title": f"{provider_name} · {short_name} ({symbol})",
                    "url": ext.get("url") or (f"https://eodhd.com/financial-summary/{symbol}" if is_eod else f"https://finance.yahoo.com/quote/{symbol}"),
                    "snippet": f"Cours : {price_str} · Données financières téléchargées en direct via l'API {ext.get('source_label') or provider_name}.",
                    "provider": "eodhd" if is_eod else "yahoo_finance",
                })
            if finance_failures:
                yield sse("status", {"message": f"⚠️ Données financières introuvables pour : {', '.join(finance_failures)}"})
            elif finance_items:
                providers_used = sorted({s["title"].split(" · ")[0] for s in sources if s.get("provider") in ("eodhd", "yahoo_finance")})
                yield sse("status", {"message": f"📈 Données live téléchargées · {' + '.join(providers_used)}"})

            has_web_attachment = any(
                item.mime_type.startswith("text/html") or (isinstance(item.extraction, dict) and item.extraction.get("url"))
                for item in attachments
            )
            if has_web_attachment and not body.deep_search and not body.web_search:
                has_youtube = any(
                    item.filename.startswith("🎬")
                    or (isinstance(item.extraction, dict) and item.extraction.get("model") == "youtube-transcript")
                    for item in attachments
                )
                has_finance = bool(finance_items)
                if has_youtube:
                    status_text = "Analyse de la vidéo YouTube et de sa transcription…"
                elif has_finance:
                    symbols_label = ", ".join(
                        f_item.extraction.get("symbol", "Actif")
                        for f_item in finance_items
                        if isinstance(f_item.extraction, dict) and f_item.extraction.get("symbol")
                    ) or "marché"
                    status_text = f"Données financières en direct ({symbols_label}) · Synthèse des cours en cours…"
                else:
                    status_text = "Analyse et synthèse des pages web jointes…"
                yield sse("status", {"message": status_text})
            findings: list[str] = []
            aspect_checklist: list[dict[str, str]] = []
            inter_questions: list[str] = []
            should_fetch_images = (
                not body.code_mode
                and bool(getattr(settings, "searxng_url", "").strip())
                and (
                    providers.search_web is _DEFAULT_SEARCH_WEB
                    or providers.search_web_images is not _DEFAULT_SEARCH_WEB_IMAGES
                )
            )
            image_attachment_hints = [
                att.extracted_text.strip()[:500]
                for att in attachments
                if att.mime_type.startswith("image/") and (att.extracted_text or "").strip()
            ]
            effective_detail_level = body.detail_level if body.detail_level is not None else 8
            detail_spec = providers.get_detail_level_spec(effective_detail_level, learn_mode=body.learn_mode)
            if body.deep_search:
                raw_query = body.content.strip()[:1500]
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id, user.id)
                    search_summary = conversation.summary
                    search_context = [
                        {"role": item.role, "content": item.content}
                        for item in conversation.messages[:-1][-4:]
                    ]
                async for event in execute_deep_search(
                    settings=settings,
                    query=raw_query,
                    summary=search_summary,
                    recent_turns=search_context,
                    search_fn=_search_with_limit,
                    initial_queries=body.deep_search_queries,
                    max_iterations=detail_spec["max_iterations"],
                    max_sources=None,
                    plan_model=stage_plan_model,
                    search_model=stage_search_model,
                ):
                    if event["type"] == "status":
                        yield sse("status", {"message": event["message"]})
                    elif event["type"] == "ping":
                        yield ": keepalive\n\n"
                    elif event["type"] == "done":
                        sources = event["sources"]
                        findings = event.get("findings", [])
                        aspect_checklist = event.get("aspect_checklist", [])
                        inter_questions = event.get("intermediate_questions", [])
                if should_fetch_images and raw_query:
                    web_imgs = await providers.search_web_images(settings, raw_query[:400], limit=6)
                    if web_imgs:
                        sources = list(sources) + web_imgs
            elif body.learn_mode:
                raw_query = body.content.strip()[:1500]
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id, user.id)
                    search_summary = conversation.summary
                    search_context = [
                        {"role": item.role, "content": item.content}
                        for item in conversation.messages[:-1][-4:]
                    ]
                async for event in execute_learn_mode(
                    settings=settings,
                    query=raw_query,
                    summary=search_summary,
                    recent_turns=search_context,
                    search_fn=_search_with_limit,
                    initial_queries=body.learn_mode_queries,
                    max_iterations=detail_spec["max_iterations"],
                    max_sources=None,
                    plan_model=stage_plan_model,
                    search_model=stage_search_model,
                ):
                    if event["type"] == "status":
                        yield sse("status", {"message": event["message"]})
                    elif event["type"] == "ping":
                        yield ": keepalive\n\n"
                    elif event["type"] == "done":
                        sources = event["sources"]
                        findings = event.get("findings", [])
                        aspect_checklist = event.get("aspect_checklist", [])
                        inter_questions = event.get("intermediate_questions", [])
                if should_fetch_images and raw_query:
                    web_imgs = await providers.search_web_images(settings, raw_query[:400], limit=6)
                    if web_imgs:
                        sources = list(sources) + web_imgs
            else:
                perform_search = body.web_search
                auto_search_allowed = (
                    settings.web_search_enabled
                    and not perform_search
                    and not body.deep_search
                    and not body.learn_mode
                    and body.web_search_mode != "off"
                    and body.auto_web_search is not False
                    and (body.auto_web_search is True or body.web_search_mode == "auto" or getattr(settings, "auto_web_search", True))
                )
                auto_search_reason = ""
                effective_user_query = body.content.strip()
                if image_attachment_hints and providers.stream_chat is _DEFAULT_STREAM_CHAT:
                    effective_user_query = (
                        f"{effective_user_query}\n[Contenu visuel de l'image jointe : {' | '.join(image_attachment_hints)}]"
                        if effective_user_query
                        else " | ".join(image_attachment_hints)
                    )
                if auto_search_allowed:
                    with sessions() as db:
                        conversation = get_conversation(db, conversation_id, user.id)
                        search_summary = conversation.summary
                        search_context = [
                            {"role": item.role, "content": item.content}
                            for item in conversation.messages[:-1][-4:]
                        ]
                    yield sse("status", {"message": "Agent Web : analyse de l’intention et des critères de recherche…"})
                    try:
                        should_search, reason = await providers.decide_web_search(
                            settings,
                            query=effective_user_query,
                            summary=search_summary,
                            recent_turns=search_context,
                        )
                        if should_search:
                            perform_search = True
                            auto_search_reason = reason
                            yield sse("status", {"message": f"Agent Web : recherche requise ({reason}) · Collecte des données…"})
                    except Exception as exc:
                        _logger.warning("Arbitrage web automatique indisponible: %s", exc)

                if perform_search:
                    query = effective_user_query[:1000]
                    with sessions() as db:
                        conversation = get_conversation(db, conversation_id, user.id)
                        search_summary = conversation.summary
                        search_context = [
                            {"role": item.role, "content": item.content}
                            for item in conversation.messages[:-1][-4:]
                        ]
                    if (
                        providers.stream_chat is _DEFAULT_STREAM_CHAT
                        or providers.rewrite_search_query is not _DEFAULT_REWRITE_SEARCH_QUERY
                    ):
                        yield sse("status", {"message": "Reformulation de la recherche…"})
                        try:
                            query = await providers.rewrite_search_query(
                                settings, query, search_summary, search_context,
                            )
                        except providers.ProviderError as exc:
                            _logger.warning("Reformulation de recherche indisponible; question originale conservée: %s", exc)
                            query = (body.content.strip() or effective_user_query)[:1000]
                            yield sse("status", {"message": "Reformulation indisponible; recherche avec la question originale…"})
                    yield sse("status", {"message": "Recherche web & images SearXNG en cours…" if should_fetch_images else "Recherche web en cours…"})
                    if should_fetch_images:
                        text_res, img_res = await asyncio.gather(
                            providers.search_web(settings, query),
                            providers.search_web_images(settings, query, limit=6),
                            return_exceptions=True,
                        )
                        if isinstance(text_res, BaseException):
                            raise text_res
                        sources = list(text_res)
                        web_imgs = list(img_res) if isinstance(img_res, list) else []
                    else:
                        sources = await providers.search_web(settings, query)
                        web_imgs = []
                    if auto_search_reason and sources:
                        for s in sources:
                            s["auto_search_reason"] = auto_search_reason
                    if web_imgs and (sources or not body.web_search):
                        if auto_search_reason and not sources:
                            web_imgs[0]["auto_search_reason"] = auto_search_reason
                        sources = sources + web_imgs
                    if not sources and body.web_search:
                        if web_imgs:
                            sources = web_imgs
                        else:
                            raise providers.ProviderError(
                                "Aucune source web exploitable n’a été trouvée. "
                                "Reformulez ou désactivez Web pour continuer sans recherche."
                            )
                    elif not sources:
                        yield sse("status", {"message": "Aucune source externe trouvée ; réponse basée sur les connaissances internes…"})
                    elif notice := sources[0].get("search_notice"):
                        yield sse("status", {"message": notice})
            # Summarize old turns, retaining the complete persisted history.
            with sessions() as db:
                conversation = get_conversation(db, conversation_id, user.id)
                history = conversation.messages
                cutoff = max(0, len(history) - 6)
                should_summarize = (
                    len(history) - conversation.summary_through >= settings.summary_every_messages
                    and cutoff > conversation.summary_through
                )
                previous_summary = conversation.summary
                transcript_parts = []
                transcript_size = 0
                summary_cutoff = conversation.summary_through
                for item in history[conversation.summary_through:cutoff]:
                    item_text = f"{item.role}: {item.content[:4000]}"
                    for attachment in item.attachments:
                        attachment_text = (
                            extraction_text(attachment.extraction, 4000)
                            if attachment.extraction
                            else attachment.extracted_text[:4000]
                        )
                        item_text += f"\n[Pièce jointe : {attachment.filename}]\n{attachment_text}"
                    item_text = item_text[:12000]
                    if transcript_parts and transcript_size + len(item_text) > 24000:
                        break
                    transcript_parts.append(item_text)
                    transcript_size += len(item_text)
                    summary_cutoff += 1
                transcript = "\n".join(transcript_parts)
            if should_summarize:
                yield sse("status", {"message": "Mise à jour du résumé de la conversation…"})
                try:
                    if settings.demo_mode:
                        summary = (
                            "[Résumé de démonstration, extraits du dialogue]\n"
                            + (previous_summary + "\n" + transcript)[-settings.max_summary_chars:]
                        )
                    else:
                        summary = await providers.summarize(
                            settings, settings.summary_model, previous_summary, transcript
                        )
                    with sessions() as db:
                        conversation = get_conversation(db, conversation_id, user.id)
                        conversation.summary = summary[:settings.max_summary_chars]
                        conversation.summary_through = summary_cutoff
                        db.commit()
                except providers.ProviderError:
                    yield sse("status", {"message": "Résumé temporairement indisponible ; utilisation des messages récents dans la limite du contexte."})
            with sessions() as db:
                conversation = get_conversation(db, conversation_id, user.id)
                memories = [
                    item.content
                    for item in db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at))
                ]
                u_skills = list(db.scalars(select(Skill).where(Skill.user_id == user.id)))
                explicit_skills = [s for s in u_skills if s.id in body.skill_ids]
                mentioned_skills = extract_mentioned_skills(body.content, u_skills)
                conv_skills = [link.skill for link in conversation.skill_links]
                merged_skills = []
                seen_skill_ids = set()
                for s in (mentioned_skills + explicit_skills + conv_skills):
                    if s.id not in seen_skill_ids:
                        seen_skill_ids.add(s.id)
                        merged_skills.append(s)
                skills = [{"name": s.name, "prompt": s.prompt} for s in merged_skills]
                history = [
                    {
                        "role": item.role,
                        "content": item.content,
                        "attachments": [
                            {
                                "filename": attachment.filename,
                                "mime_type": attachment.mime_type,
                                "extracted_text": attachment.extracted_text,
                                "extraction": attachment.extraction,
                                "path": str(upload_dir / attachment.storage_name),
                            }
                            for attachment in item.attachments
                        ],
                    }
                    for item in conversation.messages[conversation.summary_through:]
                ]
                summary = conversation.summary
            if body.multi_agent and body.multi_agent_config and body.multi_agent_config.agents:
                agents_list = [a.model_dump() for a in body.multi_agent_config.agents]
                mode_choice = body.multi_agent_config.mode
                raw_query = body.content.strip() or "Question soumise au conseil d'experts"
                with sessions() as db:
                    conversation = get_conversation(db, conversation_id, user.id)
                    recent_turns = [
                        {"role": item.role, "content": item.content}
                        for item in conversation.messages[:-1][-4:]
                    ]
                if mode_choice in ("dialectic", "contradictory"):
                    async for event in execute_multi_agent_contradictory_debate(
                        settings=settings,
                        query=raw_query,
                        agents=agents_list,
                        recent_history=recent_turns,
                    ):
                        if event["type"] == "status":
                            yield sse("status", {"message": event["message"]})
                        elif event["type"] == "delta":
                            accumulated += event["text"]
                            yield sse("delta", {"text": event["text"]})
                        elif event["type"] == "ping":
                            yield ": keepalive\n\n"
                elif mode_choice == "debate":
                    async for event in execute_multi_agent_debate(
                        settings=settings,
                        query=raw_query,
                        agents=agents_list,
                        rounds=body.multi_agent_config.rounds,
                        recent_history=recent_turns,
                    ):
                        if event["type"] == "status":
                            yield sse("status", {"message": event["message"]})
                        elif event["type"] == "delta":
                            accumulated += event["text"]
                            yield sse("delta", {"text": event["text"]})
                        elif event["type"] == "ping":
                            yield ": keepalive\n\n"
                else:
                    async for event in execute_multi_agent_synthesis(
                        settings=settings,
                        query=raw_query,
                        agents=agents_list,
                        synthesizer_model=model,
                        recent_history=recent_turns,
                    ):
                        if event["type"] == "status":
                            yield sse("status", {"message": event["message"]})
                        elif event["type"] == "delta":
                            accumulated += event["text"]
                            yield sse("delta", {"text": event["text"]})
                        elif event["type"] == "ping":
                            yield ": keepalive\n\n"
            elif settings.demo_mode:
                if body.code_mode:
                    prompt_summary = (body.content.strip() or "Application de démonstration")[:80]
                    response = (
                        f"Voici un projet multi-fichiers généré en **Mode Code Canvas** pour : « {prompt_summary} ».\n\n"
                        "```html path=\"index.html\"\n"
                        "<!DOCTYPE html>\n<html lang=\"fr\">\n<head>\n  <meta charset=\"UTF-8\" />\n"
                        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                        "  <title>Application Canvas</title>\n  <link rel=\"stylesheet\" href=\"styles.css\" />\n"
                        "</head>\n<body>\n  <main class=\"app-card\">\n    <h1>Application Canvas</h1>\n"
                        f"    <p id=\"subtitle\">{prompt_summary}</p>\n"
                        "    <button id=\"action-btn\" type=\"button\">Tester l'interaction</button>\n"
                        "    <output id=\"output\"></output>\n  </main>\n  <script src=\"app.js\"></script>\n</body>\n</html>\n"
                        "```\n\n"
                        "```css path=\"styles.css\"\n"
                        "body { margin: 0; font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; display: grid; place-items: center; min-height: 100vh; }\n"
                        ".app-card { background: #1e293b; border: 1px solid #334155; border-radius: 16px; padding: 28px; max-width: 420px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.35); }\n"
                        "button { margin-top: 12px; padding: 10px 18px; border-radius: 10px; border: 0; background: #6366f1; color: white; font-weight: 600; cursor: pointer; }\n"
                        "output { display: block; margin-top: 14px; color: #38bdf8; font-weight: 600; }\n"
                        "```\n\n"
                        "```javascript path=\"app.js\"\n"
                        "const btn = document.getElementById('action-btn');\n"
                        "const out = document.getElementById('output');\n"
                        "let count = 0;\n"
                        "btn?.addEventListener('click', () => {\n"
                        "  count += 1;\n"
                        "  if (out) out.textContent = `Interaction #${count} exécutée avec succès !`;\n"
                        "});\n"
                        "```\n\n"
                        "```markdown path=\"README.md\"\n"
                        f"# Projet Canvas\n\nDemande : {prompt_summary}\n\n## Fichiers\n- `index.html`\n- `styles.css`\n- `app.js`\n```\n"
                    )
                else:
                    response = (
                        "**Mode démonstration — aucune IA externe n'est appelée.**\n\n"
                        f"Votre message a été enregistré : « {body.content.strip() or 'Document joint'} ».\n\n"
                        "L'historique, les pièces jointes et les souvenirs fonctionnent localement. "
                        "Configurez une clé LLM et désactivez DEMO_MODE pour obtenir de vraies réponses."
                    )
                for offset in range(0, len(response), 32):
                    chunk = response[offset:offset + 32]
                    accumulated += chunk
                    yield sse("delta", {"text": chunk})
                    await asyncio.sleep(0.005)
            else:
                context = build_context(
                    settings,
                    summary,
                    memories,
                    history,
                    sources,
                    model_info["vision"],
                    skills,
                    deep_search=body.deep_search,
                    code_mode=body.code_mode,
                    findings=findings if (body.deep_search or body.learn_mode) else None,
                    learn_mode=body.learn_mode,
                    user_system_prompt=user_general_prompt,
                    prompt_cache_enabled=user_prompt_cache,
                )
                use_two_step_section_writer = (
                    (body.deep_search or body.learn_mode)
                    and (
                        providers.stream_chat is _DEFAULT_STREAM_CHAT
                        or providers.plan_report_outline is not _DEFAULT_PLAN_REPORT_OUTLINE
                    )
                )
                if use_two_step_section_writer:
                    mode_prefix = "Mode Apprendre" if body.learn_mode else "DeepSearch"
                    plan_display_name = stage_plan_model.split("/")[-1] if "/" in stage_plan_model else stage_plan_model
                    yield sse(
                        "status",
                        {
                            "message": (
                                f"{mode_prefix} · Étape 1/2 — Agent Planificateur [{plan_display_name}] (Niveau {detail_spec['level']}/10 : {detail_spec['label']}) : "
                                f"sélection des 3 experts et plan détaillé ({len(sources)} source{'s' if len(sources) != 1 else ''})…"
                            )
                        },
                    )
                    raw_query_for_outline = body.content.strip()[:1500]
                    structured_findings = [
                        {"sub_query": "", "summary": f} if isinstance(f, str) else f
                        for f in (findings or [])
                    ]
                    try:
                        outline = await providers.plan_report_outline(
                            settings=settings,
                            query=raw_query_for_outline,
                            sources=sources,
                            findings=structured_findings,
                            aspect_checklist=aspect_checklist,
                            intermediate_questions=inter_questions,
                            learn_mode=body.learn_mode,
                            detail_level=effective_detail_level,
                            model=stage_plan_model,
                        )
                    except TypeError:
                        try:
                            outline = await providers.plan_report_outline(
                                settings=settings,
                                query=raw_query_for_outline,
                                sources=sources,
                                findings=structured_findings,
                                aspect_checklist=aspect_checklist,
                                intermediate_questions=inter_questions,
                                learn_mode=body.learn_mode,
                                detail_level=effective_detail_level,
                            )
                        except TypeError:
                            outline = await providers.plan_report_outline(
                                settings=settings,
                                query=raw_query_for_outline,
                                sources=sources,
                                findings=structured_findings,
                                aspect_checklist=aspect_checklist,
                                intermediate_questions=inter_questions,
                                learn_mode=body.learn_mode,
                            )
                    outline_md = providers.format_report_outline_markdown(
                        outline,
                        learn_mode=body.learn_mode,
                        detail_level=effective_detail_level,
                    )
                    accumulated += outline_md
                    yield sse("delta", {"text": outline_md})

                    parts = outline.get("parts") or []
                    total_parts = len(parts)
                    written_headings: list[str] = []

                    # Evidence Ledger (V2 Evidence-First) extrait des sources collectées
                    evidence_ledger_text = ""
                    if sources:
                        ledger = extract_deterministic_evidence_from_sources(sources)
                        evidence_ledger_text = ledger.format_for_analysts(max_items=50)

                    for part_idx, part_item in enumerate(parts):
                        part_heading = str(part_item.get("heading") or f"## Partie {part_idx + 1}")
                        clean_heading_label = part_heading.lstrip("#").strip()[:75]
                        yield sse(
                            "status",
                            {
                                "message": (
                                    f"{mode_prefix} · Étape 2/2 — Agent Écrivain (3 experts · Niveau {detail_spec['level']}/10) : "
                                    f"rédaction de la partie {part_idx + 1}/{total_parts} ({clean_heading_label})…"
                                )
                            },
                        )
                        part_subparts = part_item.get("subparts") or []
                        is_flashcard_module = (
                            body.learn_mode
                            and part_idx == total_parts - 1
                            and "flashcard" in (part_heading + " " + " ".join(part_subparts)).lower()
                        )
                        expert_drafts: list[str] | None = None
                        if not is_flashcard_module:
                            expert_display_name = stage_expert_model.split("/")[-1] if "/" in stage_expert_model else stage_expert_model
                            yield sse(
                                "status",
                                {
                                    "message": (
                                        f"{mode_prefix} · Partie {part_idx + 1}/{total_parts} — Analyse experte du domaine [{expert_display_name}] "
                                        "appuyée sur l'Evidence Ledger…"
                                    )
                                },
                            )
                            expert_task = asyncio.create_task(_collect_chat(
                                providers.build_expert_analysis_messages(
                                    base_context=context,
                                    query=raw_query_for_outline,
                                    outline=outline,
                                    part_index=part_idx,
                                    expert_index=0,
                                    learn_mode=body.learn_mode,
                                    detail_level=effective_detail_level,
                                    evidence_ledger=evidence_ledger_text,
                                ),
                                stage_expert_model,
                                user_prompt_cache,
                            ))
                            try:
                                while True:
                                    done, pending_expert = await asyncio.wait([expert_task], timeout=2.0)
                                    if not pending_expert:
                                        break
                                    yield ": keepalive\n\n"
                            except BaseException:
                                expert_task.cancel()
                                raise
                            expert_analysis = expert_task.result() if not expert_task.cancelled() and expert_task.exception() is None else ""
                            if expert_analysis.strip():
                                expert_drafts = [expert_analysis]
                            else:
                                _logger.warning("Aucune analyse d'expert exploitable pour la partie %s", part_idx + 1)
                            synth_display_name = stage_synthesis_model.split("/")[-1] if "/" in stage_synthesis_model else stage_synthesis_model
                            yield sse(
                                "status",
                                {
                                    "message": (
                                        f"{mode_prefix} · Étape 2/2 — Agent Écrivain [{synth_display_name}] (synthèse unifiée · Niveau {detail_spec['level']}/10) : "
                                        f"rédaction de la partie {part_idx + 1}/{total_parts} ({clean_heading_label})…"
                                    )
                                },
                            )
                        part_messages = providers.build_section_writer_messages(
                            base_context=context,
                            query=raw_query_for_outline,
                            outline=outline,
                            part_index=part_idx,
                            written_headings=written_headings,
                            previous_tail=accumulated[-800:],
                            learn_mode=body.learn_mode,
                            detail_level=effective_detail_level,
                            expert_drafts=expert_drafts,
                            evidence_ledger=evidence_ledger_text,
                        )
                        part_text = ""
                        async for chunk, is_ping in _stream_chat_with_keepalive(
                            part_messages, stage_synthesis_model, enable_cache=user_prompt_cache
                        ):
                            if is_ping:
                                yield chunk
                            else:
                                part_text += chunk
                                accumulated += chunk
                                if len(accumulated) > 320000:
                                    raise providers.ProviderError("La réponse dépasse la limite autorisée")
                                yield sse("delta", {"text": chunk})
                        if part_text.strip() and not part_text.endswith("\n\n"):
                            sep = "\n\n" if not part_text.endswith("\n") else "\n"
                            accumulated += sep
                            yield sse("delta", {"text": sep})
                        written_headings.append(part_heading)
                    if body.deep_search or body.learn_mode:
                        # 1. Déduplication des images identiques insérées à travers plusieurs parties
                        accumulated = providers.deduplicate_markdown_images(accumulated)

                        # 2. Étape 5/5 — Relecture critique approfondie et arbitrage par GPT-6 Astra
                        audit_display_name = stage_audit_model.split("/")[-1] if "/" in stage_audit_model else stage_audit_model
                        yield sse(
                            "status",
                            {
                                "message": (
                                    f"{mode_prefix} · Étape 5/5 — Relecture critique & validation des sources et du texte par {audit_display_name}…"
                                )
                            },
                        )

                        # Pré-contrôle déterministe pour guider l'auditeur
                        body_content = accumulated[len(outline_md):]
                        pre_check = verify_report_figures(body_content, sources)

                        # Appel à l'auditeur critique (GPT-6 Astra)
                        audit_result = await providers.review_report_with_auditor(
                            settings=settings,
                            query=raw_query_for_outline,
                            report_markdown=body_content,
                            sources=sources,
                            pre_check=pre_check,
                            learn_mode=body.learn_mode,
                            model=stage_audit_model,
                        )

                        # 3. Application des corrections de l'auditeur et boucle de réparation multi-cycles V2
                        remedied_body = audit_result.get("remedied_markdown") or body_content
                        # Boucle de réparation multi-cycles déterministe (Claim Validator + Repair Loop V2)
                        remedied_body, final_check = run_repair_loop(remedied_body, sources, max_cycles=2)
                        if remedied_body != body_content:
                            accumulated = accumulated[:len(outline_md)] + remedied_body

                        # 4. Registre de vérification factuelle final consolidé avec avis d'audit GPT-6 Astra
                        registry_md = format_verification_markdown(final_check, audit_review=audit_result)
                        if registry_md:
                            decision_label = str(audit_result.get("decision") or "validé").replace("_", " ")
                            yield sse(
                                "status",
                                {
                                    "message": f"{mode_prefix} · Relecture {audit_display_name} terminée : statut {decision_label}."
                                },
                            )
                            accumulated += "\n" + registry_md
                            yield sse("delta", {"text": "\n" + registry_md})
                else:
                    if body.deep_search:
                        status_label = f"DeepSearch · Synthèse globale et rapport approfondi ({len(sources)} source{'s' if len(sources) != 1 else ''})…"
                    elif body.learn_mode:
                        status_label = f"Mode Apprendre · Rédaction du cours complet et structuré ({len(sources)} support{'s' if len(sources) != 1 else ''})…"
                    elif body.code_mode:
                        status_label = "Canvas Code · Conception et génération des fichiers…"
                    else:
                        status_label = "Rédaction de la réponse…"
                    yield sse("status", {"message": status_label})
                    async for chunk, is_ping in _stream_chat_with_keepalive(context, model, enable_cache=user_prompt_cache):
                        if is_ping:
                            yield chunk
                        else:
                            accumulated += chunk
                            if len(accumulated) > 240000:
                                raise providers.ProviderError("La réponse dépasse la limite autorisée")
                            yield sse("delta", {"text": chunk})
                if not accumulated.strip():
                    _logger.warning("Réponse vide du modèle %s ; nouvelle tentative", model)
                    yield sse("status", {"message": "Réponse vide du modèle · nouvelle tentative…"})
                    retry_context = context + [{
                        "role": "system",
                        "content": (
                            "Ta tentative précédente n'a produit aucun texte visible. Réponds maintenant directement "
                            "à l'utilisateur en t'appuyant sur les données disponibles ; si une donnée manque, dis-le "
                            "explicitement plutôt que de ne rien répondre."
                        ),
                    }]
                    async for chunk, is_ping in _stream_chat_with_keepalive(retry_context, model, enable_cache=user_prompt_cache):
                        if is_ping:
                            yield chunk
                        else:
                            accumulated += chunk
                            if len(accumulated) > 240000:
                                raise providers.ProviderError("La réponse dépasse la limite autorisée")
                            yield sse("delta", {"text": chunk})
                if not use_two_step_section_writer and (body.deep_search or body.learn_mode):
                    mode_prefix = "Mode Apprendre" if body.learn_mode else "DeepSearch"
                    accumulated = providers.deduplicate_markdown_images(accumulated)
                    audit_display_name = stage_audit_model.split("/")[-1] if "/" in stage_audit_model else stage_audit_model
                    yield sse(
                        "status",
                        {
                            "message": f"{mode_prefix} · Étape 5/5 — Relecture critique & validation par {audit_display_name}…"
                        },
                    )
                    pre_check = verify_report_figures(accumulated, sources)
                    audit_result = await providers.review_report_with_auditor(
                        settings=settings,
                        query=body.content.strip()[:1500],
                        report_markdown=accumulated,
                        sources=sources,
                        pre_check=pre_check,
                        learn_mode=body.learn_mode,
                        model=stage_audit_model,
                    )
                    remedied_body = audit_result.get("remedied_markdown") or accumulated
                    remedied_body, final_check = run_repair_loop(remedied_body, sources, max_cycles=2)
                    accumulated = remedied_body
                    registry_md = format_verification_markdown(final_check, audit_review=audit_result)
                    if registry_md:
                        accumulated += "\n" + registry_md
                        yield sse("delta", {"text": "\n" + registry_md})
            if not accumulated.strip():
                raise providers.ProviderError("Le fournisseur a retourné une réponse vide (deux tentatives). Réessayez ou changez de modèle.")
            generated_meta: dict | None = None
            if needs_classification:
                use_real_classifier = (
                    not settings.demo_mode
                    and settings.enabled(settings.llm_api_key)
                    and (
                        providers.stream_chat is _DEFAULT_STREAM_CHAT
                        or providers.classify_conversation is not _DEFAULT_CLASSIFY_CONVERSATION
                    )
                )
                if use_real_classifier:
                    yield sse("status", {"message": "Organisation · Titre, thème et mots-clés…"})
                    try:
                        generated_meta = await providers.classify_conversation(
                            settings, prompt_for_meta, accumulated, current_title=initial_title,
                        )
                    except providers.ProviderError as exc:
                        _logger.warning("Classification automatique indisponible; repli local: %s", exc)
                        generated_meta = providers.fallback_conversation_metadata(
                            prompt_for_meta, accumulated, current_title=initial_title,
                        )
                        generated_meta["keep_initial_title"] = True
                else:
                    generated_meta = providers.fallback_conversation_metadata(
                        prompt_for_meta, accumulated, current_title=initial_title,
                    )
                    generated_meta["keep_initial_title"] = True
            with sessions() as db:
                conversation = get_conversation(db, conversation_id, user.id)
                answer = Message(id=assistant_id, conversation_id=conversation_id, role="assistant", content=accumulated, sources=sources)
                db.add(answer)
                if generated_meta:
                    if auto_title_eligible and not generated_meta.get("keep_initial_title") and generated_meta.get("title"):
                        conversation.title = generated_meta["title"][:200]
                    if not conversation.theme and generated_meta.get("theme"):
                        conversation.theme = generated_meta["theme"][:80]
                    if not conversation.keywords and generated_meta.get("keywords"):
                        conversation.keywords = generated_meta["keywords"][:5]
                conversation.updated_at = now()

                deep_search_report_id: str | None = None
                learn_report_id: str | None = None
                if body.deep_search:
                    report_title = (
                        conversation.title
                        if conversation.title != "Nouvelle conversation"
                        else (body.content.strip()[:120] or "Rapport d'analyse DeepSearch")
                    )
                    created_at_dt = now()
                    html_content = generate_report_html(
                        title=report_title,
                        topic=body.content.strip(),
                        markdown_content=accumulated,
                        sources=sources,
                        created_at_str=created_at_dt.strftime("%d/%m/%Y à %H:%M"),
                    )
                    report = DeepSearchReport(
                        user_id=user.id,
                        conversation_id=conversation_id,
                        message_id=assistant_id,
                        title=report_title,
                        topic=body.content.strip(),
                        markdown_content=accumulated,
                        html_content=html_content,
                        sources=sources,
                        created_at=created_at_dt,
                    )
                    db.add(report)
                    db.flush()
                    deep_search_report_id = report.id
                elif body.learn_mode:
                    course_title = (
                        conversation.title
                        if conversation.title != "Nouvelle conversation"
                        else (body.content.strip()[:120] or "Cours complet")
                    )
                    created_at_dt = now()
                    html_content = generate_learn_course_html(
                        title=course_title,
                        topic=body.content.strip(),
                        markdown_content=accumulated,
                        sources=sources,
                        created_at_str=created_at_dt.strftime("%d/%m/%Y à %H:%M"),
                    )
                    learn_rep = LearnReport(
                        user_id=user.id,
                        conversation_id=conversation_id,
                        message_id=assistant_id,
                        title=course_title,
                        topic=body.content.strip(),
                        markdown_content=accumulated,
                        html_content=html_content,
                        sources=sources,
                        created_at=created_at_dt,
                    )
                    db.add(learn_rep)
                    db.flush()
                    learn_report_id = learn_rep.id

                db.commit()
                db.refresh(conversation)
                db.refresh(answer)
                final_msg_json = message_json(answer)
                final_conv_json = conversation_json(conversation)

            memory_result: dict = {}
            try:
                memory_result = await process_memory_turn(
                    settings=settings,
                    sessions=sessions,
                    user_id=user.id,
                    user_text=body.content.strip(),
                    assistant_text=accumulated,
                    auto_memory_enabled=getattr(user, "auto_memory_enabled", True),
                )
            except Exception as m_exc:
                _logger.warning("Échec traitement mémoire agent: %s", m_exc)

            yield sse("done", {
                "message": final_msg_json,
                "conversation": final_conv_json,
                "deep_search_report_id": deep_search_report_id,
                "learn_report_id": learn_report_id,
                "memories": memory_result.get("all_memories"),
                "new_memories": memory_result.get("new_memories", []),
                "deleted_memories": memory_result.get("deleted_memories", []),
            })
        except asyncio.CancelledError:
            raise
        except providers.ProviderError as exc:
            yield sse("error", {"message": str(exc)})
        except Exception as exc:
            _logger.exception("Erreur dans stream message: %s", exc)
            yield sse("error", {"message": "Impossible de terminer la réponse. Votre message reste enregistré ; réessayez."})
        finally:
            lock.release()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/conversations/{conversation_id}/deep-search/plan", response_model=DeepSearchPlanResponse)
async def plan_conversation_deep_search(
    conversation_id: str,
    body: PlanDeepSearch,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
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
    if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
    if not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")

    raw_query = body.content.strip()[:1500]
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
    if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
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
    if not settings.demo_mode and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "Configurez LLM_API_KEY ou activez explicitement DEMO_MODE pour une simulation")
    if not settings.web_search_enabled:
        raise HTTPException(503, "La recherche web nécessite SearXNG, BRAVE_API_KEY ou DUCKDUCKGO_ENABLED en mode IA réel")

    raw_query = body.content.strip()[:1500]
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
def get_message_html(
    message_id: str,
    scope: str = "turn",
    download: bool = False,
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





