"""Endpoints API pour la bibliothèque de documents illustrés (Mistral OCR + WebP)."""

from __future__ import annotations

import asyncio
import logging
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
from ..schemas import AddVisualDocLinksRequest, UpdateVisualDocumentRequest
from ..serializers import conversation_json, visual_doc_json
from ..visual_doc_links import (
    MAX_LINKS_PER_VISUAL_DOC,
    extract_and_summarize_supplementary_file,
    extract_and_summarize_visual_doc_link,
    parse_raw_urls_input,
    remove_supplementary_file,
    resolve_supplementary_file_path,
)
from ..visual_doc_profiles import (
    VISUAL_DOC_CATEGORIES,
    infer_visual_doc_category,
    normalize_visual_doc_category,
)
from ..visual_documents import (
    ASSET_NAME_RE,
    MAX_VISUAL_DOC_IMAGES,
    SLUG_RE,
    ingest_visual_document,
    make_visual_doc_slug,
    remove_visual_doc_cover_image,
    remove_visual_doc_dir,
    remove_visual_doc_prefixed_assets,
    resolve_visual_doc_asset,
    save_visual_doc_cover_image,
)

router = APIRouter(tags=["visual-docs"])
_logger = logging.getLogger("uvicorn.error")


@router.get("/api/visual-docs/categories")
def list_visual_doc_categories(
    user: User = Depends(current_user),
):
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "short_label": item["short_label"],
            "description": item["description"],
            "forum_label": item["forum_label"],
            "forum_domains": item["forum_domains"],
            "auto_forum_search": item["auto_forum_search"],
        }
        for item in VISUAL_DOC_CATEGORIES
    ]


@router.get("/api/visual-docs")
def list_visual_docs(
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        docs = db.scalars(
            select(VisualDocument)
            .where(VisualDocument.user_id == user.id)
            .order_by(VisualDocument.updated_at.desc(), VisualDocument.created_at.desc())
        )
        return [visual_doc_json(doc, detail=False, app_data_dir=settings.app_data_dir) for doc in docs]


@router.post("/api/visual-docs", status_code=201)
async def create_visual_doc(
    files: list[UploadFile] = File(...),
    supplementary_files: list[UploadFile] | None = File(default=None),
    cover_image: UploadFile | None = File(default=None),
    title: str = Form(""),
    doc_category: str = Form(""),
    links: str = Form(""),
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

    prepared_supp_files: list[tuple[str, bytes]] = []
    if supplementary_files:
        for supp_up in supplementary_files[:MAX_LINKS_PER_VISUAL_DOC]:
            try:
                s_raw = await supp_up.read(max_total_bytes - total_bytes + 1)
            finally:
                await supp_up.close()
            if not s_raw:
                continue
            total_bytes += len(s_raw)
            if total_bytes > max_total_bytes:
                raise HTTPException(413, f"La taille totale des fichiers dépasse {max(settings.max_upload_mb, 40)} Mo.")
            s_name = Path((supp_up.filename or "complement.pdf").replace("\\", "/")).name[:200] or "complement.pdf"
            prepared_supp_files.append((s_name, s_raw))

    cover_raw_data: tuple[str, bytes] | None = None
    if cover_image is not None:
        try:
            c_raw = await cover_image.read(15 * 1024 * 1024 + 1)
        finally:
            await cover_image.close()
        if c_raw:
            c_name = Path((cover_image.filename or "cover.png").replace("\\", "/")).name[:200] or "cover.png"
            cover_raw_data = (c_name, c_raw)

    first_name = prepared_files[0][0]
    default_title = Path(first_name).stem.replace("_", " ").replace("-", " ").strip()[:180] or "Document illustré"
    resolved_title = (title or "").strip()[:200] or default_title
    raw_cat = (doc_category or "").strip().lower()
    if raw_cat and raw_cat != "auto":
        valid_ids = {c["id"] for c in VISUAL_DOC_CATEGORIES}
        if raw_cat not in valid_ids:
            raise HTTPException(422, f"Type de document inconnu : {raw_cat}")
        resolved_category = normalize_visual_doc_category(raw_cat)
    else:
        resolved_category = infer_visual_doc_category(title=resolved_title, filename=first_name)
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

    initial_urls = parse_raw_urls_input(links)
    extracted_links: list[dict] = []
    warnings_combined = list(result.get("warnings") or [])
    sem = asyncio.Semaphore(3)

    if prepared_supp_files:
        async def _ingest_one_supp(fname: str, raw_b: bytes):
            async with sem:
                return await extract_and_summarize_supplementary_file(
                    settings,
                    settings.app_data_dir,
                    doc_id,
                    filename=fname,
                    raw_bytes=raw_b,
                    doc_title=resolved_title,
                    doc_slug=slug,
                    doc_category=resolved_category,
                )

        supp_outcomes = await asyncio.gather(
            *(_ingest_one_supp(fn, rb) for fn, rb in prepared_supp_files),
            return_exceptions=True,
        )
        for (fn, _), outcome in zip(prepared_supp_files, supp_outcomes):
            if isinstance(outcome, dict):
                extracted_links.append(outcome)
            else:
                detail_msg = getattr(outcome, "detail", str(outcome))
                warnings_combined.append(f"Document complémentaire ignoré ({fn}) : {detail_msg}")

    if initial_urls:
        async def _ingest_one_url(u: str):
            async with sem:
                return await extract_and_summarize_visual_doc_link(
                    settings,
                    u,
                    doc_title=resolved_title,
                    doc_category=resolved_category,
                )

        link_outcomes = await asyncio.gather(*(_ingest_one_url(u) for u in initial_urls), return_exceptions=True)
        for u, outcome in zip(initial_urls, link_outcomes):
            if isinstance(outcome, dict):
                extracted_links.append(outcome)
            else:
                detail_msg = getattr(outcome, "detail", str(outcome))
                warnings_combined.append(f"Lien ignoré ({u}) : {detail_msg}")

    if cover_raw_data is not None:
        try:
            await asyncio.to_thread(
                save_visual_doc_cover_image,
                settings.app_data_dir,
                doc_id,
                cover_raw_data[1],
                cover_raw_data[0],
            )
        except Exception as cover_exc:
            warnings_combined.append(f"Image de couverture ignorée : {getattr(cover_exc, 'detail', str(cover_exc))}")

    try:
        with sessions() as db:
            item = VisualDocument(
                id=doc_id,
                user_id=user.id,
                slug=slug,
                title=resolved_title,
                filename=first_name if len(prepared_files) == 1 else f"{len(prepared_files)} images ({first_name}…)"[:255],
                source_type=result["source_type"],
                doc_category=resolved_category,
                ocr_model=result["ocr_model"],
                vision_enriched=result["vision_enriched"],
                page_count=result["page_count"],
                figure_count=result["figure_count"],
                compiled_markdown=result["compiled_markdown"],
                pages_meta=result["pages_meta"],
                external_links=extracted_links,
                warnings=warnings_combined,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)
    except Exception:
        remove_visual_doc_dir(settings.app_data_dir, doc_id)
        raise


@router.get("/api/visual-docs/{doc_id}")
def read_visual_doc(
    doc_id: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


@router.patch("/api/visual-docs/{doc_id}")
def update_visual_doc(
    doc_id: str,
    body: UpdateVisualDocumentRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
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
        if body.doc_category is not None:
            item.doc_category = body.doc_category
        if body.compiled_markdown is not None:
            item.compiled_markdown = body.compiled_markdown
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


@router.post("/api/visual-docs/{doc_id}/cover")
async def upload_visual_doc_cover(
    doc_id: str,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    try:
        raw = await file.read(15 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if not raw:
        raise HTTPException(422, "L'image de couverture est vide.")
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(413, "L'image de couverture ne doit pas dépasser 15 Mo.")
    clean_name = Path((file.filename or "cover.png").replace("\\", "/")).name[:200] or "cover.png"

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")

    await asyncio.to_thread(save_visual_doc_cover_image, settings.app_data_dir, doc_id, raw, clean_name)

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument)
            .where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


@router.delete("/api/visual-docs/{doc_id}/cover")
def reset_visual_doc_cover(
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
        remove_visual_doc_cover_image(settings.app_data_dir, doc_id)
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


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


@router.post("/api/visual-docs/{doc_id}/links")
async def add_links_to_visual_doc(
    doc_id: str,
    body: AddVisualDocLinksRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    raw_inputs = list(body.urls or [])
    if body.url and body.url.strip():
        raw_inputs.append(body.url.strip())
    urls = parse_raw_urls_input(raw_inputs)
    if not urls:
        raise HTTPException(422, "Fournissez au moins une adresse URL valide (forum, site ou vidéo YouTube).")

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        doc_title = item.title
        doc_slug = item.slug
        doc_category = item.doc_category or "general"
        existing_links = list(item.external_links if isinstance(item.external_links, list) else [])

    existing_by_url = {str(l.get("url") or "").strip(): l for l in existing_links}
    new_count = sum(1 for u in urls if u not in existing_by_url)
    if len(existing_links) + new_count > MAX_LINKS_PER_VISUAL_DOC:
        raise HTTPException(422, f"Maximum {MAX_LINKS_PER_VISUAL_DOC} liens externes par document illustré.")

    sem = asyncio.Semaphore(3)
    custom_title = (body.title or "").strip() if len(urls) == 1 else ""

    async def _process_one(u: str):
        async with sem:
            prev = existing_by_url.get(u)
            return await extract_and_summarize_visual_doc_link(
                settings,
                u,
                doc_title=doc_title,
                doc_category=doc_category,
                custom_title=custom_title,
                existing_id=str(prev["id"]) if prev and prev.get("id") else None,
            )

    results = await asyncio.gather(*(_process_one(u) for u in urls), return_exceptions=True)
    added_entries: list[dict] = []
    first_error: Exception | None = None
    for res in results:
        if isinstance(res, dict):
            added_entries.append(res)
        elif isinstance(res, Exception) and first_error is None:
            first_error = res

    if not added_entries and first_error is not None:
        if isinstance(first_error, HTTPException):
            raise first_error
        raise HTTPException(422, str(first_error))

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument)
            .where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        merged = list(item.external_links if isinstance(item.external_links, list) else [])
        idx_by_url = {str(entry.get("url") or ""): i for i, entry in enumerate(merged)}
        for new_entry in added_entries:
            u_key = str(new_entry.get("url") or "")
            if u_key in idx_by_url:
                merged[idx_by_url[u_key]] = new_entry
            else:
                idx_by_url[u_key] = len(merged)
                merged.append(new_entry)
        item.external_links = merged[:MAX_LINKS_PER_VISUAL_DOC]
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


@router.post("/api/visual-docs/{doc_id}/supplementary-files")
async def add_supplementary_files_to_visual_doc(
    doc_id: str,
    files: list[UploadFile] = File(...),
    doc_role: str = Form(""),
    title: str = Form(""),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if not files:
        raise HTTPException(422, "Sélectionnez au moins un document complémentaire (PDF, Word, MD, TXT, Image).")

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        doc_title = item.title
        doc_slug = item.slug
        doc_category = item.doc_category or "general"
        existing_links = list(item.external_links if isinstance(item.external_links, list) else [])

    if len(existing_links) + len(files) > MAX_LINKS_PER_VISUAL_DOC:
        raise HTTPException(422, f"Maximum {MAX_LINKS_PER_VISUAL_DOC} ressources complémentaires par document.")

    max_total_bytes = max(settings.max_upload_mb, 40) * 1024 * 1024
    prepared: list[tuple[str, bytes]] = []
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
        clean_name = Path((upload.filename or "complement.pdf").replace("\\", "/")).name[:200] or "complement.pdf"
        prepared.append((clean_name, raw))

    sem = asyncio.Semaphore(3)
    custom_title = (title or "").strip() if len(prepared) == 1 else ""

    async def _process_file(fname: str, raw_b: bytes):
        async with sem:
            return await extract_and_summarize_supplementary_file(
                settings,
                settings.app_data_dir,
                doc_id,
                filename=fname,
                raw_bytes=raw_b,
                doc_title=doc_title,
                doc_slug=doc_slug,
                doc_category=doc_category,
                doc_role=doc_role,
                custom_title=custom_title,
            )

    outcomes = await asyncio.gather(*(_process_file(fn, rb) for fn, rb in prepared), return_exceptions=True)
    added_entries: list[dict] = []
    first_err: Exception | None = None
    for res in outcomes:
        if isinstance(res, dict):
            added_entries.append(res)
        elif isinstance(res, Exception) and first_err is None:
            first_err = res

    if not added_entries and first_err is not None:
        _logger.warning(
            "Échec d'ajout de document complémentaire sur %s : %s (%s)",
            doc_id,
            type(first_err).__name__,
            getattr(first_err, "detail", str(first_err)),
        )
        if isinstance(first_err, HTTPException):
            raise first_err
        raise HTTPException(422, str(first_err))

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument)
            .where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
            .with_for_update()
        )
        if not item:
            for e in added_entries:
                remove_supplementary_file(settings.app_data_dir, doc_id, e.get("storage_name"))
            raise HTTPException(404, "Document illustré introuvable")
        merged = list(item.external_links if isinstance(item.external_links, list) else [])
        merged.extend(added_entries)
        item.external_links = merged[:MAX_LINKS_PER_VISUAL_DOC]
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


@router.get("/api/visual-docs/{doc_id}/supplementary-files/{link_id}")
def serve_visual_doc_supplementary_file(
    doc_id: str,
    link_id: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        links_list = item.external_links if isinstance(item.external_links, list) else []
        target = next((l for l in links_list if str(l.get("id")) == link_id and l.get("link_type") == "document"), None)
        if not target or not target.get("storage_name"):
            raise HTTPException(404, "Fichier complémentaire introuvable")
        storage_name = str(target["storage_name"])
        orig_filename = str(target.get("filename") or storage_name)
        mime_type = str(target.get("mime_type") or "application/octet-stream")

    file_path = resolve_supplementary_file_path(settings.app_data_dir, doc_id, storage_name)
    if file_path is None:
        raise HTTPException(404, "Fichier introuvable sur le disque")

    disposition = "inline" if mime_type in {"application/pdf", "text/plain", "image/png", "image/jpeg", "image/webp"} else "attachment"
    return FileResponse(
        file_path,
        media_type=mime_type,
        filename=orig_filename,
        content_disposition_type=disposition,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/api/visual-docs/{doc_id}/links/{link_id}/refresh")
async def refresh_visual_doc_link(
    doc_id: str,
    link_id: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument).where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        links_list = list(item.external_links if isinstance(item.external_links, list) else [])
        target = next((l for l in links_list if str(l.get("id")) == link_id), None)
        if not target or not target.get("url"):
            raise HTTPException(404, "Ressource introuvable sur ce document")
        doc_title = item.title
        doc_slug = item.slug
        doc_category = item.doc_category or "general"
        target_snapshot = dict(target)

    if target_snapshot.get("link_type") == "document":
        file_path = resolve_supplementary_file_path(
            settings.app_data_dir, doc_id, str(target_snapshot.get("storage_name") or "")
        )
        if file_path is None:
            raise HTTPException(404, "Le fichier source n'est plus disponible pour ré-analyse.")
        raw_bytes = await asyncio.to_thread(file_path.read_bytes)
        refreshed = await extract_and_summarize_supplementary_file(
            settings,
            settings.app_data_dir,
            doc_id,
            filename=str(target_snapshot.get("filename") or file_path.name),
            raw_bytes=raw_bytes,
            doc_title=doc_title,
            doc_slug=doc_slug,
            doc_category=doc_category,
            doc_role=str(target_snapshot.get("doc_role") or ""),
            custom_title=str(target_snapshot.get("title") or ""),
            existing_id=link_id,
            existing_storage_name=str(target_snapshot.get("storage_name") or ""),
            existing_asset_prefix=str(target_snapshot.get("asset_prefix") or "") or None,
        )
    else:
        refreshed = await extract_and_summarize_visual_doc_link(
            settings,
            str(target_snapshot["url"]),
            doc_title=doc_title,
            doc_category=doc_category,
            existing_id=link_id,
        )

    with sessions() as db:
        item = db.scalar(
            select(VisualDocument)
            .where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        updated_links = [
            refreshed if str(entry.get("id")) == link_id else entry
            for entry in (item.external_links if isinstance(item.external_links, list) else [])
        ]
        item.external_links = updated_links
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        return visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)


@router.delete("/api/visual-docs/{doc_id}/links/{link_id}")
def delete_visual_doc_link(
    doc_id: str,
    link_id: str,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    removed_storage: str | None = None
    removed_prefix: str | None = None
    with sessions() as db:
        item = db.scalar(
            select(VisualDocument)
            .where(VisualDocument.id == doc_id, VisualDocument.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Document illustré introuvable")
        current = list(item.external_links if isinstance(item.external_links, list) else [])
        target = next((entry for entry in current if str(entry.get("id")) == link_id), None)
        if target is None:
            raise HTTPException(404, "Ressource introuvable sur ce document")
        removed_storage = target.get("storage_name")
        removed_prefix = target.get("asset_prefix")
        item.external_links = [entry for entry in current if str(entry.get("id")) != link_id]
        item.updated_at = now()
        db.commit()
        db.refresh(item)
        payload = visual_doc_json(item, detail=True, app_data_dir=settings.app_data_dir)
    if removed_storage:
        remove_supplementary_file(settings.app_data_dir, doc_id, str(removed_storage))
    if removed_prefix:
        remove_visual_doc_prefixed_assets(settings.app_data_dir, doc_id, str(removed_prefix))
    return payload


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
