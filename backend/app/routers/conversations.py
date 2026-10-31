import re
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..chat_export_html import generate_chat_export_html
from ..presentation_html import generate_chat_presentation_html
from ..config import Settings
from ..deps import check_model, current_user, get_conversation, get_sessions, get_settings, get_upload_dir
from ..models import Conversation, User, now
from ..schemas import (
    ClassifyConversationRequest,
    CreateConversation,
    GenerateStudyMaterialRequest,
    StudyMaterialResponse,
    UpdateConversation,
)
from ..serializers import conversation_json


router = APIRouter(tags=["conversations"])


@router.get("/api/conversations")
def list_conversations(
    q: str = "",
    theme: str = "",
    keyword: str = "",
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    query_norm = q.strip().lstrip("#").casefold()
    theme_norm = theme.strip().casefold()
    keyword_norm = keyword.strip().lstrip("#").casefold()
    with sessions() as db:
        items = list(
            db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
            )
        )
        results = []
        for item in items:
            data = conversation_json(item)
            if theme_norm and (data["theme"] or "général").casefold() != theme_norm:
                continue
            if keyword_norm and not any(keyword_norm in kw.casefold() for kw in data["keywords"]):
                continue
            if query_norm:
                haystack = " ".join([
                    data["title"],
                    data["theme"],
                    data["summary"] or "",
                    " ".join(data["keywords"]),
                ]).casefold()
                if query_norm not in haystack:
                    continue
            results.append(data)
        return results


@router.post("/api/conversations", status_code=201)
def new_conversation(
    body: CreateConversation,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    model = body.model or settings.default_model
    check_model(settings, model)
    with sessions() as db:
        item = Conversation(
            user_id=user.id,
            title=body.title.strip() or "Nouvelle conversation",
            model=model,
            theme=(body.theme or "").strip(),
            keywords=[k.strip().lstrip("#") for k in (body.keywords or []) if k.strip()][:5],
        )
        db.add(item)
        db.commit()
        return conversation_json(item, True)


@router.post("/api/conversations/classify-all")
async def classify_all_conversations(
    force: bool = False,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        conversations = list(
            db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
            )
        )
        targets = []
        for item in conversations:
            if not item.messages:
                continue
            if force or not item.theme or not item.keywords or item.title == "Nouvelle conversation":
                user_msgs = "\n".join(m.content for m in item.messages if m.role == "user" and m.content.strip())[:1500]
                asst_msgs = "\n".join(m.content for m in item.messages if m.role == "assistant" and m.content.strip())[:1500]
                targets.append((item.id, item.title, user_msgs, asst_msgs))

    use_real = not settings.demo_mode and settings.enabled(settings.llm_api_key)
    updates: dict[str, dict] = {}
    for conv_id, curr_title, user_msgs, asst_msgs in targets:
        if use_real:
            try:
                meta = await providers.classify_conversation(settings, user_msgs, asst_msgs, current_title=curr_title)
            except providers.ProviderError:
                meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)
        else:
            meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)
        updates[conv_id] = meta

    with sessions() as db:
        for conv_id, meta in updates.items():
            item = db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user.id))
            if not item:
                continue
            if (force or item.title == "Nouvelle conversation") and meta.get("title"):
                item.title = meta["title"][:200]
            if meta.get("theme"):
                item.theme = meta["theme"][:80]
            if meta.get("keywords"):
                item.keywords = meta["keywords"][:5]
        db.commit()
        return [
            conversation_json(item)
            for item in db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc())
            )
        ]


@router.get("/api/conversations/{conversation_id}")
def read_conversation(
    conversation_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        return conversation_json(get_conversation(db, conversation_id, user.id), True)


@router.post("/api/conversations/{conversation_id}/classify")
async def classify_single_conversation(
    conversation_id: str,
    request: Request,
    body: ClassifyConversationRequest | None = None,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    locks = getattr(request.app.state, "locks", {})
    lock_key = f"{user.id}:{conversation_id}"
    if locks.get(lock_key) and locks[lock_key].locked():
        raise HTTPException(409, "Attendez la fin de la réponse")
    update_title = True if body is None else body.update_title
    with sessions() as db:
        item = get_conversation(db, conversation_id, user.id)
        if not item.messages:
            raise HTTPException(422, "Ajoutez au moins un message avant de générer les mots-clés")
        user_msgs = "\n".join(m.content for m in item.messages if m.role == "user" and m.content.strip())[:1500]
        asst_msgs = "\n".join(m.content for m in item.messages if m.role == "assistant" and m.content.strip())[:1500]
        curr_title = item.title

    if not settings.demo_mode and settings.enabled(settings.llm_api_key):
        try:
            meta = await providers.classify_conversation(settings, user_msgs, asst_msgs, current_title=curr_title)
        except providers.ProviderError:
            meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)
    else:
        meta = providers.fallback_conversation_metadata(user_msgs, asst_msgs, current_title=curr_title)

    with sessions() as db:
        item = get_conversation(db, conversation_id, user.id)
        if update_title and meta.get("title"):
            item.title = meta["title"][:200]
        if meta.get("theme"):
            item.theme = meta["theme"][:80]
        if meta.get("keywords"):
            item.keywords = meta["keywords"][:5]
        item.updated_at = now()
        db.commit()
        return conversation_json(item, True)


@router.patch("/api/conversations/{conversation_id}")
def edit_conversation(
    conversation_id: str,
    body: UpdateConversation,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    locks = getattr(request.app.state, "locks", {})
    lock_key = f"{user.id}:{conversation_id}"
    if locks.get(lock_key) and locks[lock_key].locked():
        raise HTTPException(409, "Attendez la fin de la réponse")
    with sessions() as db:
        item = get_conversation(db, conversation_id, user.id)
        if body.title is not None:
            item.title = body.title.strip() or "Nouvelle conversation"
        if body.model is not None:
            check_model(settings, body.model)
            item.model = body.model
        if body.theme is not None:
            item.theme = body.theme.strip()[:80]
        if body.keywords is not None:
            item.keywords = body.keywords[:5]
        item.updated_at = now()
        db.commit()
        return conversation_json(item, True)


@router.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    locks = getattr(request.app.state, "locks", {})
    lock_key = f"{user.id}:{conversation_id}"
    if locks.get(lock_key) and locks[lock_key].locked():
        raise HTTPException(409, "Attendez la fin de la réponse")
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = get_conversation(db, conversation_id, user.id)
        files = [attachment for message in item.messages for attachment in message.attachments]
        names = [attachment.storage_name for attachment in files]
        for attachment in files:
            db.delete(attachment)
        db.delete(item)
        db.commit()
    for name in names:
        (upload_dir / name).unlink(missing_ok=True)
    locks.pop(lock_key, None)
    return Response(status_code=204)


@router.get("/api/conversations/{conversation_id}/html")
def get_conversation_html(
    conversation_id: str,
    download: bool = False,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        conv = get_conversation(db, conversation_id, user.id)
        messages_data = [
            {
                "role": m.role,
                "content": m.content,
                "created_at_str": m.created_at.strftime("%d/%m/%Y %H:%M") if m.created_at else "",
                "sources": m.sources or [],
            }
            for m in conv.messages
        ]
        title = conv.title or "Synthèse de la discussion cLAIr"
        html_doc = generate_chat_export_html(
            title=title,
            messages=messages_data,
            scope="conversation",
            topic=conv.title,
            model=conv.model,
            created_at_str=conv.created_at.strftime("%d/%m/%Y") if conv.created_at else None,
            summary=conv.summary or "",
        )
        headers = {}
        if download:
            clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
            clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "discussion"
            headers["Content-Disposition"] = f'attachment; filename="{clean_filename}.html"'

        return Response(
            content=html_doc,
            media_type="text/html; charset=utf-8",
            headers=headers,
        )


@router.get("/api/conversations/{conversation_id}/slides")
async def get_conversation_slides(
    conversation_id: str,
    download: bool = False,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        conv = get_conversation(db, conversation_id, user.id)
        messages_data = [
            {
                "role": m.role,
                "content": m.content,
                "created_at_str": m.created_at.strftime("%d/%m/%Y %H:%M") if m.created_at else "",
                "sources": m.sources or [],
            }
            for m in conv.messages
        ]
        title = conv.title or "Présentation de la discussion cLAIr"
        topic = conv.title
        model = conv.model
        created_at_str = conv.created_at.strftime("%d/%m/%Y") if conv.created_at else None
        summary = conv.summary or ""

    html_doc = await generate_chat_presentation_html(
        settings=settings,
        title=title,
        messages=messages_data,
        scope="conversation",
        topic=topic,
        model=model,
        created_at_str=created_at_str,
        summary=summary,
    )
    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    if download:
        clean_ascii = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
        clean_filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean_ascii).strip("_")[:40] or "discussion-slides"
        headers["Content-Disposition"] = f'attachment; filename="{clean_filename}.html"'

    return Response(
        content=html_doc,
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@router.post("/api/conversations/{conversation_id}/study", response_model=StudyMaterialResponse)
async def generate_conversation_study_material(
    conversation_id: str,
    body: GenerateStudyMaterialRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    course_text = (body.course_text or "").strip()
    transcript = ""
    with sessions() as db:
        conv = get_conversation(db, conversation_id, user.id)
        if not conv.messages and not course_text:
            raise HTTPException(422, "La conversation doit comporter au moins un message ou un texte de cours pour générer des révisions.")

        parts: list[str] = []
        if conv.summary:
            parts.append(f"Résumé contextuel : {conv.summary}")
        for m in conv.messages:
            if m.content and m.content.strip():
                role_label = "Utilisateur" if m.role == "user" else "Assistant"
                parts.append(f"{role_label} : {m.content.strip()}")
        transcript = "\n\n".join(parts)
        topic = (body.topic or "").strip() or conv.title or conv.theme or "Sujet abordé"
        model = conv.model

    result = await providers.generate_study_material(
        settings=settings,
        transcript=transcript,
        kind=body.kind,
        count=body.count,
        difficulty=body.difficulty,
        topic=topic,
        model=model,
        course_text=course_text,
    )
    return StudyMaterialResponse(**result)


@router.post("/api/study/generate", response_model=StudyMaterialResponse)
async def generate_study_material_direct(
    body: GenerateStudyMaterialRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    transcript = ""
    topic = (body.topic or "").strip()
    model = getattr(settings, "default_model", "")

    if body.conversation_id:
        with sessions() as db:
            conv = get_conversation(db, body.conversation_id, user.id)
            if conv.messages:
                parts: list[str] = []
                if conv.summary:
                    parts.append(f"Résumé contextuel : {conv.summary}")
                for m in conv.messages:
                    if m.content and m.content.strip():
                        role_label = "Utilisateur" if m.role == "user" else "Assistant"
                        parts.append(f"{role_label} : {m.content.strip()}")
                transcript = "\n\n".join(parts)
            if not topic:
                topic = conv.title or conv.theme or ""
            model = conv.model or model

    course_text = (body.course_text or "").strip()
    if not course_text and not transcript:
        raise HTTPException(422, "Veuillez fournir un texte de cours ou sélectionner une conversation avec des échanges.")

    result = await providers.generate_study_material(
        settings=settings,
        transcript=transcript,
        kind=body.kind,
        count=body.count,
        difficulty=body.difficulty,
        topic=topic or "",
        model=model,
        course_text=course_text,
    )
    return StudyMaterialResponse(**result)




