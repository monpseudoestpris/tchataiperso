"""Endpoints API pour la bibliothèque de documents illustrés (Mistral OCR + WebP)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import current_user, get_conversation, get_sessions, get_settings
from ..models import ConversationVisualDoc, User, VisualDocument, now
from ..schemas import UpdateVisualDocumentRequest
from ..serializers import conversation_json, visual_doc_json
from ..visual_documents import (
    ASSET_NAME_RE,
    MAX_VISUAL_DOC_IMAGES,
    SLUG_RE,
    ingest_visual_document,
    make_visual_doc_slug,
    remove_visual_doc_dir,
    resolve_visual_doc_asset,
)

router = APIRouter(tags=["visual-docs"])


@router.get("/api/visual-docs")
def list_visual_docs(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        docs = db.scalars(
            select(VisualDocument)
            .where(VisualDocument.user_id == user.id)
            .order_by(VisualDocument.updated_at.desc(), VisualDocument.created_at.desc())
        )
        return [visual_doc_json(doc, detail=False) for doc in docs]


@router.post("/api/visual-docs", status_code=201)
async def create_visual_doc(
    files: list[UploadFile] = File(...),
    title: str = Form(""),
    enrich_vision: bool = Form(True),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if not files:
        raise HTTPException(422, "Sélectionnez un fichier PDF ou une liste d'images.")
    if len(files) > MAX_VISUAL_DOC_IMAGES:
        raise HTTPException(422, f"Maximum {MAX_VISUAL_DOC_IMAGES} images par document.")

    max_total_bytes = max(settings.max_upload_mb, 40) * 1024 * 1024
    prepared_files: list[tuple[str, bytes]] = []
    total_bytes = 0
    for upload in files:
        try:
            raw = await upload.read(max_total_bytes - total_bytes + 1)
        finally:
            await upload.close()
        total_bytes += len(raw)
        if total_bytes > max_total_bytes:
            raise HTTPException(413, f"La taille totale des fichiers dépasse {max(settings.max_upload_mb, 40)} Mo.")
        if not raw:
            raise HTTPException(422, f"Le fichier « {upload.filename or 'sans nom'} » est vide.")
        clean_name = Path((upload.filename or "document").replace("\\", "/")).name[:255] or "document"
        prepared_files.append((clean_name, raw))

    first_name = prepared_files[0][0]
    default_title = Path(first_name).stem.replace("_", " ").replace("-", " ").strip()[:180] or "Document illustré"
    resolved_title = (title or "").strip()[:200] or default_title
    doc_id = str(uuid4())
    slug = make_visual_doc_slug(resolved_title or first_name)

    try:
        result = await ingest_visual_document(
            settings=settings,
            app_data_dir=settings.app_data_dir,
            doc_id=doc_id,
            slug=slug,
            title=resolved_title,
            files=prepared_files,
            enrich_vision=bool(enrich_vision),
        )
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc

    try:
        with sessions() as db:
            item = VisualDocument(
                id=doc_id,
                user_id=user.id,
                slug=slug,
                title=resolved_title,
                filename=first_name if len(prepared_files) == 1 else f"{len(prepared_files)} images ({first_name}…)"[:255],
                source_type=result["source_type"],
                ocr_model=result["ocr_model"],
                vision_enriched=result["vision_enriched"],
                page_count=result["page_count"],
                figure_count=result["figure_count"],
                compiled_markdown=result["compiled_markdown"],
                pages_meta=result["pages_meta"],
                warnings=result["warnings"],
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return visual_doc_json(item, detail=True)
    except Exception:
        remove_visual_doc_dir(settings.app_data_dir, doc_id)
        raise


@router.get("/api/visual-docs/{doc_id}")
def read_visual_doc(
    doc_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        return visual_doc_json(item, detail=True)


@router.patch("/api/visual-docs/{doc_id}")
def update_visual_doc(
    doc_id: str,
    body: UpdateVisualDocumentRequest,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        if body.title is not None:
            item.title = body.title
        if body.compiled_markdown is not None:
            item.compiled_markdown = body.compiled_markdown
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True)


@router.delete("/api/visual-docs/{doc_id}", status_code=204)
def delete_visual_doc(
    doc_id: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument)
            .where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        db.delete(item)
        db.commit()
    remove_visual_doc_dir(settings.app_data_dir, doc_id)
    return Response(status_code=204)


@router.post("/api/conversations/{conversation_id}/visual-docs/{doc_id}")
def attach_visual_doc_to_conversation(
    conversation_id: str,
    doc_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        conv = get_conversation(db, conversation_id, user.id)
        doc = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not doc:
            raise HTTPException(404, "Document illustré introuvable")
        existing = [link for link in conv.visual_doc_links if link.visual_doc_id == doc.id]
        if not existing:
            if len(conv.visual_doc_links) >= 5:
                raise HTTPException(422, "Vous pouvez associer au maximum 5 documents illustrés par conversation.")
            next_pos = max((link.position for link in conv.visual_doc_links), default=-1) + 1
            db.add(ConversationVisualDoc(conversation_id=conv.id, visual_doc_id=doc.id, position=next_pos))
            conv.updated_at = now()
            db.commit()
            db.refresh(conv)
        return conversation_json(conv, detail=True)


@router.delete("/api/conversations/{conversation_id}/visual-docs/{doc_id}")
def detach_visual_doc_from_conversation(
    conversation_id: str,
    doc_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        conv = get_conversation(db, conversation_id, user.id)
        link = db.scalar(
            select(ConversationVisualDoc).where(
                ConversationVisualDoc.conversation_id == conv.id,
                ConversationVisualDoc.visual_doc_id == doc_id,
            )
        )
        if link:
            db.delete(link)
            conv.updated_at = now()
            db.commit()
            db.refresh(conv)
        return conversation_json(conv, detail=True)


@router.get("/api/docs/{slug}/{asset_name}")
def serve_visual_doc_asset(
    slug: str,
    asset_name: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if not SLUG_RE.fullmatch(slug or "") or not ASSET_NAME_RE.fullmatch(asset_name or ""):
        raise HTTPException(404, "Ressource introuvable")
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.slug == slug, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document introuvable")
        doc_id = item.id
    asset_path = resolve_visual_doc_asset(settings.app_data_dir, doc_id, asset_name)
    if asset_path is None:
        raise HTTPException(404, "Image introuvable")
    return FileResponse(
        asset_path,
        media_type="image/webp",
        content_disposition_type="inline",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=86400",
        },
    )
