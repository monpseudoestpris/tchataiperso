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
from .page_generator import generate_page_html, slugify
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
    page_type: str = "educational",
    target_audience: str | None = None,
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
) -> dict[str, Any]:
    """Génère et enregistre une nouvelle page Web cLAIr strictement en brouillon."""
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

    resolved_title, html_content = await generate_page_html(
        settings=settings,
        prompt=prompt,
        chat_transcript=chat_transcript,
        title=fallback_title,
        model=selected_model,
        page_type=page_type,
        target_audience=target_audience,
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
    )

    clean_slug = slugify(resolved_title)

    with sessions() as db:
        page = WebPage(
            user_id=user_id,
            title=resolved_title,
            slug=clean_slug,
            is_published=False,
        )
        db.add(page)
        db.flush()

        version = WebPageVersion(
            page_id=page.id,
            version_number=1,
            prompt_used=prompt or "Création initiale",
            html_content=html_content,
        )
        db.add(version)
        page.updated_at = now()
        db.commit()
        db.refresh(page)
        return web_page_json(page, include_versions=True, include_latest_html=True)
