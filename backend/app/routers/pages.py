from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..models import Conversation, User, WebPage, WebPageVersion, now
from ..page_bricks import (
    build_bricks_prompt_context,
    execute_page_brick,
    inject_bricks_runtime_html,
    interview_app_diagram,
    normalize_bricks,
    propose_app_diagram,
)
from ..page_generator import propose_page_topics, refine_page_html, slugify
from ..page_runtime import sanitize_and_enhance_html
from ..page_service import create_draft_web_page
from ..page_wizard import interview_page_wizard
from ..providers import ProviderError
from ..schemas import (
    CreateWebPage,
    ExecutePageBrickRequest,
    InterviewAppDiagramRequest,
    PageTopicItem,
    PageWizardInterviewRequest,
    PageWizardInterviewResponse,
    ProposeAppDiagramRequest,
    ProposePageTopicsRequest,
    ProposePageTopicsResponse,
    RefineWebPage,
    UpdateWebPage,
)
from ..serializers import web_page_json, web_page_version_json

router = APIRouter(tags=["pages"])


@router.get("/api/pages")
def list_pages(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        items = list(
            db.scalars(
                select(WebPage)
                .where(WebPage.user_id == user.id)
                .order_by(WebPage.updated_at.desc())
            )
        )
        return [web_page_json(item, include_versions=False, include_latest_html=True) for item in items]


@router.post("/api/pages/propose-topics", response_model=ProposePageTopicsResponse)
async def propose_topics_endpoint(
    body: ProposePageTopicsRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    chat_transcript = None
    fallback_title = body.title
    selected_model = body.model

    if body.conversation_id:
        with sessions() as db:
            conv = db.scalar(
                select(Conversation).where(
                    Conversation.id == body.conversation_id,
                    Conversation.user_id == user.id,
                )
            )
            if conv:
                if not fallback_title:
                    fallback_title = conv.title
                if not selected_model and conv.model:
                    selected_model = conv.model
                lines = []
                for msg in conv.messages:
                    role_label = "Utilisateur" if msg.role == "user" else "Assistant"
                    lines.append(f"{role_label} : {msg.content}")
                chat_transcript = "\n\n".join(lines)

    try:
        s_title, summary, topics_data = await propose_page_topics(
            settings=settings,
            prompt=body.prompt,
            chat_transcript=chat_transcript,
            title=fallback_title,
            page_type=body.page_type,
            target_audience=body.target_audience,
            editorial_tone=body.editorial_tone,
            format_priorities=body.format_priorities,
            mandatory_sections=body.mandatory_sections,
            author_persona=body.author_persona,
            visual_description=body.visual_description,
            layout_style=body.layout_style,
            model=selected_model,
            web_search=body.web_search,
            raise_on_failure=not getattr(settings, "demo_mode", False),
        )
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc

    return ProposePageTopicsResponse(
        suggested_title=s_title,
        summary=summary,
        topics=[PageTopicItem(**t) for t in topics_data],
    )


@router.post("/api/pages/wizard/interview", response_model=PageWizardInterviewResponse)
async def wizard_interview_endpoint(
    body: PageWizardInterviewRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    chat_transcript = None
    fallback_title = body.title
    selected_model = body.model

    if body.conversation_id:
        with sessions() as db:
            conv = db.scalar(
                select(Conversation).where(
                    Conversation.id == body.conversation_id,
                    Conversation.user_id == user.id,
                )
            )
            if conv:
                if not fallback_title:
                    fallback_title = conv.title
                if not selected_model and conv.model:
                    selected_model = conv.model
                lines = []
                for msg in conv.messages:
                    role_label = "Utilisateur" if msg.role == "user" else "Assistant"
                    lines.append(f"{role_label} : {msg.content}")
                chat_transcript = "\n\n".join(lines)

    return await interview_page_wizard(
        settings=settings,
        prompt=body.prompt,
        title=fallback_title,
        chat_transcript=chat_transcript,
        messages=[m.model_dump() for m in body.messages],
        model=selected_model,
        force_finalize=body.force_finalize,
    )



@router.post("/api/pages", status_code=201)
async def create_page(
    body: CreateWebPage,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    try:
        return await create_draft_web_page(
            settings=settings,
            sessions=sessions,
            user_id=user.id,
            prompt=body.prompt,
            title=body.title,
            model=body.model,
            conversation_id=body.conversation_id,
            kind=body.kind,
            page_type=body.page_type,
            target_audience=body.target_audience,
            editorial_tone=body.editorial_tone,
            format_priorities=body.format_priorities,
            mandatory_sections=body.mandatory_sections,
            author_persona=body.author_persona,
            visual_description=body.visual_description,
            creative_freedom=body.creative_freedom,
            orientation=body.orientation,
            layout_style=body.layout_style,
            text_density=body.text_density,
            interactivity=body.interactivity,
            include_quiz=body.include_quiz,
            include_svg=body.include_svg,
            theme_palette=body.theme_palette,
            visual_style=body.visual_style,
            animation_engine=body.animation_engine,
            font_family=body.font_family,
            text_effects=body.text_effects,
            selected_topics=[t.model_dump() for t in body.selected_topics] if body.selected_topics else None,
            html_content=body.html_content,
            canvas_files=[f.model_dump() for f in body.canvas_files] if body.canvas_files else None,
            bricks=[b.model_dump() for b in body.bricks] if body.bricks else None,
            web_search=body.web_search,
            multipass_exhaustive=body.multipass_exhaustive,
        )
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/api/pages/bricks/execute")
async def execute_brick_endpoint(
    body: ExecutePageBrickRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    target_brick: dict | None = body.brick.model_dump() if body.brick else None

    if target_brick is None and body.page_id:
        with sessions() as db:
            page = db.scalar(select(WebPage).where(WebPage.id == body.page_id, WebPage.user_id == user.id))
            if not page:
                raise HTTPException(404, "Page ou application introuvable")
            page_bricks = getattr(page, "bricks", None) or []
            needle = (body.brick_id or "").strip().lower()
            for candidate in page_bricks:
                if not isinstance(candidate, dict):
                    continue
                cid = str(candidate.get("id") or "").lower()
                cname = str(candidate.get("name") or "").lower()
                if not needle or needle == "default" or cid == needle or cname == needle:
                    target_brick = candidate
                    break

    if not target_brick:
        raise HTTPException(404, "Brique IA introuvable pour cette application")

    return await execute_page_brick(
        settings=settings,
        brick=target_brick,
        inputs=body.inputs,
        fallback_model=body.model,
    )


@router.post("/api/pages/diagram/propose")
async def propose_diagram_endpoint(
    body: ProposeAppDiagramRequest,
    _user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    return await propose_app_diagram(
        settings=settings,
        prompt=body.prompt,
        title=body.title,
        model=body.model,
    )


@router.post("/api/pages/diagram/interview")
async def interview_diagram_endpoint(
    body: InterviewAppDiagramRequest,
    _user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    return await interview_app_diagram(
        settings=settings,
        messages=[m.model_dump() for m in body.messages],
        available_templates=body.available_templates,
        model=body.model,
        force_finalize=body.force_finalize,
    )


@router.get("/api/pages/{page_id}")
def get_page(
    page_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        return web_page_json(page, include_versions=True, include_latest_html=True)


@router.patch("/api/pages/{page_id}")
def update_page(
    page_id: str,
    body: UpdateWebPage,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        if body.title is not None:
            page.title = body.title
            page.slug = slugify(body.title)
        if body.is_published is not None:
            page.is_published = body.is_published
        if body.kind is not None:
            page.kind = body.kind
        if body.bricks is not None:
            page.bricks = normalize_bricks([b.model_dump() for b in body.bricks])

        versions = page.versions or []
        effective_bricks = getattr(page, "bricks", None) or []

        if body.html_content is not None and body.html_content.strip():
            next_version_num = (max(v.version_number for v in versions) if versions else 0) + 1
            enhanced_html = sanitize_and_enhance_html(
                body.html_content.strip(),
                title=page.title,
                bricks=effective_bricks if (effective_bricks or page.kind == "app") else None,
            )
            norm_files = (
                [
                    {
                        "path": str(f.path).strip(),
                        "language": str(f.language).strip(),
                        "content": str(f.content),
                    }
                    for f in body.canvas_files
                    if str(f.path).strip()
                ]
                if body.canvas_files is not None
                else ((versions[0].canvas_files or []) if versions else [])
            )
            new_version = WebPageVersion(
                page_id=page.id,
                version_number=next_version_num,
                prompt_used=body.prompt_used or "Mise à jour depuis Code Canvas",
                html_content=enhanced_html,
                canvas_files=norm_files,
            )
            db.add(new_version)
        elif body.bricks is not None and versions:
            latest = versions[0]
            latest.html_content = inject_bricks_runtime_html(latest.html_content, effective_bricks)
            if body.canvas_files is not None:
                latest.canvas_files = [
                    {
                        "path": str(f.path).strip(),
                        "language": str(f.language).strip(),
                        "content": str(f.content),
                    }
                    for f in body.canvas_files
                    if str(f.path).strip()
                ]
        elif body.canvas_files is not None and versions:
            versions[0].canvas_files = [
                {
                    "path": str(f.path).strip(),
                    "language": str(f.language).strip(),
                    "content": str(f.content),
                }
                for f in body.canvas_files
                if str(f.path).strip()
            ]

        page.updated_at = now()
        db.commit()
        db.refresh(page)
        return web_page_json(page, include_versions=True, include_latest_html=True)


@router.delete("/api/pages/{page_id}", status_code=204)
def delete_page(
    page_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        db.delete(page)
        db.commit()
    return Response(status_code=204)


@router.post("/api/pages/{page_id}/refine")
async def refine_page(
    page_id: str,
    body: RefineWebPage,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        versions = page.versions or []
        if not versions:
            raise HTTPException(400, "Aucune version existante à modifier")
        current_version = versions[0]
        current_html = current_version.html_content
        current_canvas_files = getattr(current_version, "canvas_files", None) or []
        page_bricks = getattr(page, "bricks", None) or []
        next_version_num = max(v.version_number for v in versions) + 1

    effective_instruction = body.instruction
    bricks_ctx = build_bricks_prompt_context(page_bricks)
    if bricks_ctx:
        effective_instruction = f"{effective_instruction}\n\n{bricks_ctx}"

    try:
        updated_html = await refine_page_html(
            settings=settings,
            current_html=current_html,
            instruction=effective_instruction,
            model=body.model,
            web_search=body.web_search,
            raise_on_failure=not getattr(settings, "demo_mode", False),
        )
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    if page_bricks or getattr(page, "kind", "page") == "app":
        updated_html = inject_bricks_runtime_html(updated_html, page_bricks)

    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        new_version = WebPageVersion(
            page_id=page.id,
            version_number=next_version_num,
            prompt_used=body.instruction,
            html_content=updated_html,
            canvas_files=current_canvas_files,
        )
        db.add(new_version)
        page.updated_at = now()
        db.commit()
        db.refresh(page)
        return web_page_json(page, include_versions=True, include_latest_html=True)


@router.post("/api/pages/{page_id}/versions/{version_id}/restore")
def restore_version(
    page_id: str,
    version_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        target_version = db.scalar(
            select(WebPageVersion).where(
                WebPageVersion.id == version_id,
                WebPageVersion.page_id == page.id,
            )
        )
        if not target_version:
            raise HTTPException(404, "Version introuvable")

        versions = page.versions or []
        next_version_num = (max(v.version_number for v in versions) if versions else 0) + 1
        page_bricks = getattr(page, "bricks", None) or []
        restored_html = target_version.html_content
        if page_bricks or getattr(page, "kind", "page") == "app":
            restored_html = inject_bricks_runtime_html(restored_html, page_bricks)

        restored_version = WebPageVersion(
            page_id=page.id,
            version_number=next_version_num,
            prompt_used=f"Restauration de la version {target_version.version_number}",
            html_content=restored_html,
            canvas_files=getattr(target_version, "canvas_files", None) or [],
        )
        db.add(restored_version)
        page.updated_at = now()
        db.commit()
        db.refresh(page)
        return web_page_json(page, include_versions=True, include_latest_html=True)


@router.get("/p/{token}")
@router.get("/api/pages/public/{token}")
def serve_public_page(
    token: str,
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.public_token == token))
        if not page or not page.is_published:
            raise HTTPException(404, "Page introuvable ou non publiée")
        versions = page.versions or []
        if not versions:
            raise HTTPException(404, "Contenu de page vide")
        latest = versions[0]
        html_content = latest.html_content

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; script-src 'unsafe-inline'; img-src data: blob:;",
            "X-Content-Type-Options": "nosniff",
        },
    )

