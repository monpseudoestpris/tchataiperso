"""Service partagé de création de brouillons cLAIr Pages.

Réutilisé par le routeur `/api/pages` et par l'outil agentique `clair_create_page`
pour garantir une logique unique, la création stricte en brouillon (`is_published=False`),
le respect du quota de pages et l'absence d'écrasement de pages existantes.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import Conversation, WebPage, WebPageVersion, now
from .page_bricks import build_bricks_prompt_context, normalize_bricks
from .page_generator import extract_title_from_html, generate_page_html, slugify
from .page_multipass import generate_multipass_page_html
from .page_runtime import sanitize_and_enhance_html
from .serializers import web_page_json


async def create_draft_web_page(
    *,
    settings: Settings,
    sessions: sessionmaker,
    user_id: str,
    prompt: str | None = None,
    title: str | None = None,
    model: str | None = None,
    conversation_id: str | None = None,
    kind: str = "page",
    page_type: str = "educational",
    target_audience: str | None = None,
    editorial_tone: str = "auto",
    format_priorities: list[str] | None = None,
    mandatory_sections: list[str] | None = None,
    author_persona: str | None = None,
    visual_description: str | None = None,
    creative_freedom: str = "balanced",
    orientation: str = "portrait",
    layout_style: str = "editorial",
    text_density: int | str = 5,
    interactivity: str = "standard",
    include_quiz: bool = False,
    include_svg: bool = True,
    theme_palette: str = "editorial_warm",
    visual_style: str = "minimal",
    animation_engine: str = "none",
    font_family: str = "sans",
    text_effects: list[str] | str | None = None,
    selected_topics: list[dict[str, Any]] | None = None,
    html_content: str | None = None,
    canvas_files: list[dict[str, Any]] | None = None,
    bricks: list[dict[str, Any]] | None = None,
    web_search: bool = True,
    multipass_exhaustive: bool = False,
) -> dict[str, Any]:
    """Génère et enregistre une nouvelle page Web ou App cLAIr strictement en brouillon."""
    resolved_kind = "app" if kind == "app" else "page"
    normalized_bricks = normalize_bricks(bricks)
    normalized_canvas_files = [
        {
            "path": str(f.get("path") or "").strip(),
            "language": str(f.get("language") or "text").strip(),
            "content": str(f.get("content") or ""),
        }
        for f in (canvas_files or [])
        if isinstance(f, dict) and str(f.get("path") or "").strip()
    ]

    with sessions() as db:
        count = db.scalar(select(func.count(WebPage.id)).where(WebPage.user_id == user_id))
        if count and count >= 100:
            raise HTTPException(422, "Nombre maximal de pages web atteint (100)")

    chat_transcript = None
    fallback_title = title
    selected_model = model
    if conversation_id:
        with sessions() as db:
            conv = db.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
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

    resolved_density = 5
    if isinstance(text_density, int):
        resolved_density = max(1, min(10, text_density))
    elif isinstance(text_density, str):
        cleaned_density = text_density.strip().lower()
        if cleaned_density.isdigit():
            resolved_density = max(1, min(10, int(cleaned_density)))
        elif cleaned_density in {"compact", "synth", "short", "low"}:
            resolved_density = 3
        elif cleaned_density in {"dense", "deep", "high"}:
            resolved_density = 8

    resolved_effects = [text_effects] if isinstance(text_effects, str) and text_effects != "none" else (text_effects or [])

    if html_content and html_content.strip():
        resolved_title = (
            fallback_title or extract_title_from_html(html_content, fallback="Application Canvas" if resolved_kind == "app" else "Brouillon cLAIr Page")
        ).strip()
        final_html = sanitize_and_enhance_html(
            html_content.strip(),
            title=resolved_title,
            layout_style=layout_style,
            orientation=orientation,
            bricks=normalized_bricks if (normalized_bricks or resolved_kind == "app") else None,
        )
    else:
        effective_prompt = prompt or ""
        bricks_ctx = build_bricks_prompt_context(normalized_bricks)
        if bricks_ctx:
            effective_prompt = f"{effective_prompt}\n\n{bricks_ctx}".strip()
        is_strict_a4 = layout_style in ("print_sheet", "a4_1p", "a4_2p", "cheat_sheet") or page_type in (
            "a4_revision_1p",
            "revision_a4",
            "a4_revision_2p",
            "cheat_sheet",
        )
        if multipass_exhaustive and not is_strict_a4:
            resolved_title, final_html = await generate_multipass_page_html(
                settings=settings,
                prompt=effective_prompt,
                chat_transcript=chat_transcript,
                title=fallback_title,
                model=selected_model,
                target_audience=target_audience or "general",
                editorial_tone=editorial_tone,
                format_priorities=format_priorities,
                mandatory_sections=mandatory_sections,
                author_persona=author_persona,
                visual_description=visual_description,
                orientation=orientation,
                theme_palette=theme_palette,
                font_family=font_family,
                selected_topics=selected_topics,
                web_search=web_search,
                raise_on_failure=not getattr(settings, "demo_mode", False),
            )
        else:
            resolved_title, final_html = await generate_page_html(
                settings=settings,
                prompt=effective_prompt,
                chat_transcript=chat_transcript,
                title=fallback_title,
                model=selected_model,
                page_type=page_type,
                target_audience=target_audience,
                editorial_tone=editorial_tone,
                format_priorities=format_priorities,
                mandatory_sections=mandatory_sections,
                author_persona=author_persona,
                visual_description=visual_description,
                creative_freedom=creative_freedom,
                orientation=orientation,
                layout_style=layout_style,
                text_density=resolved_density,
                interactivity=interactivity,
                include_quiz=include_quiz,
                include_svg=include_svg,
                theme_palette=theme_palette,
                visual_style=visual_style,
                animation_engine=animation_engine,
                font_family=font_family,
                text_effects=resolved_effects,
                selected_topics=selected_topics,
                web_search=web_search,
                raise_on_failure=not getattr(settings, "demo_mode", False),
            )
        if normalized_bricks:
            final_html = sanitize_and_enhance_html(
                final_html,
                title=resolved_title,
                layout_style=layout_style,
                orientation=orientation,
                bricks=normalized_bricks,
            )

    clean_slug = slugify(resolved_title)

    with sessions() as db:
        page = WebPage(
            user_id=user_id,
            title=resolved_title,
            slug=clean_slug,
            kind=resolved_kind,
            bricks=normalized_bricks,
            is_published=False,
        )
        db.add(page)
        db.flush()

        version = WebPageVersion(
            page_id=page.id,
            version_number=1,
            prompt_used=prompt or ("Import Code Canvas" if resolved_kind == "app" else "Création initiale"),
            html_content=final_html,
            canvas_files=normalized_canvas_files,
        )
        db.add(version)
        page.updated_at = now()
        db.commit()
        db.refresh(page)
        return web_page_json(page, include_versions=True, include_latest_html=True)
