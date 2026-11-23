"""Routeur API de l'espace « Mes Vidéos » (/api/videos/*)."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import current_user, get_sessions, get_settings, get_upload_dir
from ..models import Attachment, SavedVideo, User, now
from ..saved_videos import (
    build_video_action_prompt,
    generate_video_analysis,
    record_video_analysis,
    saved_video_json,
    upsert_saved_video_from_youtube,
)
from ..schemas import DocumentAnnotation, DocumentExtraction, ExtractedPage
from ..serializers import attachment_json
from ..youtube import extract_youtube_video_id, fetch_and_parse_youtube_video

router = APIRouter(tags=["videos"])

VideoActionLiteral = Literal["none", "summarize", "analyze", "key_points", "study", "translate_fr", "custom"]


class ImportSavedVideoRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    action: VideoActionLiteral = "summarize"
    custom_prompt: str = Field(default="", max_length=2000)
    model: str | None = Field(default=None, max_length=150)


class GenerateSavedVideoAnalysisRequest(BaseModel):
    action: Literal["summarize", "analyze", "key_points", "study", "translate_fr", "custom"] = "summarize"
    custom_prompt: str = Field(default="", max_length=2000)
    model: str | None = Field(default=None, max_length=150)


class UpdateSavedVideoRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary_markdown: str | None = Field(default=None, max_length=120000)
    summary_action: str | None = Field(default=None, max_length=40)
    summary_model: str | None = Field(default=None, max_length=120)
    summary_prompt: str | None = Field(default=None, max_length=500)


@router.get("/api/videos")
def list_saved_videos(
    q: str = Query(default="", max_length=200),
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        stmt = select(SavedVideo).where(SavedVideo.user_id == user.id)
        cleaned_q = q.strip()
        if cleaned_q:
            like = f"%{cleaned_q}%"
            stmt = stmt.where(
                or_(
                    SavedVideo.title.ilike(like),
                    SavedVideo.author.ilike(like),
                    SavedVideo.url.ilike(like),
                )
            )
        items = list(db.scalars(stmt.order_by(SavedVideo.updated_at.desc())))
        return [saved_video_json(item, detail=False) for item in items]


@router.get("/api/videos/{saved_video_id}")
def get_saved_video(
    saved_video_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(SavedVideo).where(SavedVideo.id == saved_video_id, SavedVideo.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Vidéo introuvable")
        return saved_video_json(item, detail=True)


@router.post("/api/videos", status_code=201)
async def import_saved_video(
    body: ImportSavedVideoRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    clean_url = body.url.strip()
    video_id = extract_youtube_video_id(clean_url)
    if not video_id:
        raise HTTPException(422, "Veuillez fournir une adresse de vidéo YouTube valide.")

    _filename, _content_bytes, _mime, full_markdown, extraction = await fetch_and_parse_youtube_video(
        settings, clean_url, video_id
    )
    annotations = extraction.get("annotations") if isinstance(extraction.get("annotations"), list) else []
    first_ann = annotations[0] if annotations and isinstance(annotations[0], dict) else {}
    resolved_title = str(first_ann.get("title") or f"Vidéo YouTube ({video_id})").strip()

    generated_md = ""
    used_model = ""
    if body.action != "none":
        generated_md, used_model = await generate_video_analysis(
            settings,
            title=resolved_title,
            url=str(extraction.get("url") or clean_url),
            transcript_markdown=full_markdown,
            action=body.action,
            custom_prompt=body.custom_prompt,
            model=body.model,
        )

    with sessions() as db:
        saved = upsert_saved_video_from_youtube(
            db,
            user.id,
            video_id=video_id,
            url=str(extraction.get("url") or clean_url),
            title=resolved_title,
            author=str(extraction.get("author") or ""),
            duration=str(extraction.get("duration") or ""),
            lang_label=str(extraction.get("lang_label") or ""),
            has_transcript=bool(extraction.get("has_transcript")),
            transcript_segments=int(extraction.get("transcript_segments") or 0),
            transcript_markdown=full_markdown,
        )
        if generated_md:
            record_video_analysis(
                saved,
                action=body.action,
                markdown=generated_md,
                model=used_model,
                prompt=build_video_action_prompt(body.action, saved.title, body.custom_prompt),
            )
        db.commit()
        db.refresh(saved)
        return saved_video_json(saved, detail=True)


@router.post("/api/videos/{saved_video_id}/generate")
async def generate_saved_video_summary(
    saved_video_id: str,
    body: GenerateSavedVideoAnalysisRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(SavedVideo).where(SavedVideo.id == saved_video_id, SavedVideo.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Vidéo introuvable")
        title = item.title
        url = item.url
        transcript_md = item.transcript_markdown or ""

    generated_md, used_model = await generate_video_analysis(
        settings,
        title=title,
        url=url,
        transcript_markdown=transcript_md,
        action=body.action,
        custom_prompt=body.custom_prompt,
        model=body.model,
    )

    with sessions() as db:
        item = db.scalar(
            select(SavedVideo).where(SavedVideo.id == saved_video_id, SavedVideo.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Vidéo introuvable")
        record_video_analysis(
            item,
            action=body.action,
            markdown=generated_md,
            model=used_model,
            prompt=build_video_action_prompt(body.action, item.title, body.custom_prompt),
        )
        db.commit()
        db.refresh(item)
        return saved_video_json(item, detail=True)


@router.patch("/api/videos/{saved_video_id}")
def update_saved_video(
    saved_video_id: str,
    body: UpdateSavedVideoRequest,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(SavedVideo).where(SavedVideo.id == saved_video_id, SavedVideo.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Vidéo introuvable")
        if body.title is not None:
            cleaned_title = body.title.strip()
            if not cleaned_title:
                raise HTTPException(422, "Le titre de la vidéo ne peut pas être vide.")
            item.title = cleaned_title[:255]
            item.updated_at = now()
        if body.summary_markdown is not None and body.summary_markdown.strip():
            record_video_analysis(
                item,
                action=body.summary_action or "summarize",
                markdown=body.summary_markdown,
                model=body.summary_model or "",
                prompt=body.summary_prompt or "",
            )
        db.commit()
        db.refresh(item)
        return saved_video_json(item, detail=True)


@router.post("/api/videos/{saved_video_id}/attach", status_code=201)
def attach_saved_video_to_chat(
    saved_video_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Crée instantanément une pièce jointe de tchat depuis une vidéo déjà sauvegardée (sans re-requêter YouTube)."""
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        video = db.scalar(
            select(SavedVideo).where(SavedVideo.id == saved_video_id, SavedVideo.user_id == user.id)
        )
        if not video:
            raise HTTPException(404, "Vidéo introuvable")

        full_markdown = video.transcript_markdown or f"# 🎬 {video.title}\n\n{video.url}"
        content = full_markdown.encode("utf-8")
        short_title = video.title[:65].strip()
        author = video.author or "YouTube"
        filename = f"🎬 {short_title} ({author})"[:255]
        extraction = DocumentExtraction(
            model="youtube-transcript",
            pages=[ExtractedPage(index=0, markdown=full_markdown, method="local", images=[])],
            annotations=[
                DocumentAnnotation(
                    title=video.title,
                    summary=f"Vidéo YouTube : {video.title} par {author} ({video.duration or 'Inconnue'}).",
                )
            ],
            warnings=[],
        ).model_dump()
        extraction["url"] = video.url
        extraction["video_id"] = video.video_id
        extraction["author"] = author
        extraction["duration"] = video.duration or "Inconnue"
        extraction["lang_label"] = video.lang_label or ""
        extraction["has_transcript"] = bool(video.has_transcript)
        extraction["transcript_segments"] = int(video.transcript_segments or 0)
        extraction["transcript_chars"] = len(full_markdown)
        extraction["saved_video_id"] = video.id

        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        try:
            att = Attachment(
                user_id=user.id,
                filename=filename,
                mime_type="text/html; video=youtube",
                size=len(content),
                storage_name=storage_name,
                extracted_text=full_markdown,
                extraction=extraction,
            )
            db.add(att)
            db.commit()
            return attachment_json(att)
        except Exception:
            path.unlink(missing_ok=True)
            raise


@router.delete("/api/videos/{saved_video_id}", status_code=204)
def delete_saved_video(
    saved_video_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(SavedVideo).where(SavedVideo.id == saved_video_id, SavedVideo.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Vidéo introuvable")
        db.delete(item)
        db.commit()
    return Response(status_code=204)
