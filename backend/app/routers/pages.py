from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..models import Conversation, User, WebPage, WebPageVersion, now
from ..page_generator import generate_page_html, refine_page_html, slugify
from ..schemas import CreateWebPage, RefineWebPage, UpdateWebPage
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


@router.post("/api/pages", status_code=201)
async def create_page(
    body: CreateWebPage,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        count = db.scalar(select(func.count(WebPage.id)).where(WebPage.user_id == user.id))
        if count and count >= 100:
            raise HTTPException(422, "Nombre maximal de pages web atteint (100)")

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

    resolved_title, html_content = await generate_page_html(
        settings=settings,
        prompt=body.prompt,
        chat_transcript=chat_transcript,
        title=fallback_title,
        model=selected_model,
        page_type=body.page_type,
        target_audience=body.target_audience,
        creative_freedom=body.creative_freedom,
        orientation=body.orientation,
        layout_style=body.layout_style,
        text_density=body.text_density,
        interactivity=body.interactivity,
        include_quiz=body.include_quiz,
        include_svg=body.include_svg,
        theme_palette=body.theme_palette,
        visual_style=body.visual_style,
    )

    clean_slug = slugify(resolved_title)

    with sessions() as db:
        page = WebPage(
            user_id=user.id,
            title=resolved_title,
            slug=clean_slug,
            is_published=False,
        )
        db.add(page)
        db.flush()

        version = WebPageVersion(
            page_id=page.id,
            version_number=1,
            prompt_used=body.prompt or "Création initiale",
            html_content=html_content,
        )
        db.add(version)
        page.updated_at = now()
        db.commit()
        db.refresh(page)
        return web_page_json(page, include_versions=True, include_latest_html=True)


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
        next_version_num = max(v.version_number for v in versions) + 1

    updated_html = await refine_page_html(
        settings=settings,
        current_html=current_html,
        instruction=body.instruction,
        model=body.model,
    )

    with sessions() as db:
        page = db.scalar(select(WebPage).where(WebPage.id == page_id, WebPage.user_id == user.id))
        if not page:
            raise HTTPException(404, "Page introuvable")
        new_version = WebPageVersion(
            page_id=page.id,
            version_number=next_version_num,
            prompt_used=body.instruction,
            html_content=updated_html,
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

        restored_version = WebPageVersion(
            page_id=page.id,
            version_number=next_version_num,
            prompt_used=f"Restauration de la version {target_version.version_number}",
            html_content=target_version.html_content,
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
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: blob:;",
            "X-Content-Type-Options": "nosniff",
        },
    )

