from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings, get_upload_dir
from ..documents import extract_document
from ..models import Attachment, User
from ..schemas import FetchUrlRequest
from ..serializers import attachment_json
from ..web import fetch_and_parse_web_url


router = APIRouter(tags=["attachments"])


@router.post("/api/attachments", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("auto"),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    try:
        content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    finally:
        await file.close()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Fichier limité à {settings.max_upload_mb} Mo")
    if not content:
        raise HTTPException(422, "Fichier vide")
    filename = Path((file.filename or "document").replace("\\", "/")).name[:255]
    try:
        mime, extracted, extraction = await extract_document(settings, content, filename, mode=mode)
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    if mime.startswith("image/") and len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Les images sont limitées à 8 Mo pour la vision")
    storage_name = str(uuid4())
    path = upload_dir / storage_name
    path.write_bytes(content)
    try:
        with sessions() as db:
            item = Attachment(
                user_id=user.id,
                filename=filename,
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
                extracted_text=extracted,
                extraction=extraction,
            )
            db.add(item)
            db.commit()
            return attachment_json(item)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.post("/api/attachments/url", status_code=201)
async def upload_url(
    body: FetchUrlRequest,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    filename, content, mime, extracted, extraction = await fetch_and_parse_web_url(
        settings, body.url.strip()
    )
    storage_name = str(uuid4())
    path = upload_dir / storage_name
    path.write_bytes(content)
    try:
        with sessions() as db:
            item = Attachment(
                user_id=user.id,
                filename=filename,
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
                extracted_text=extracted,
                extraction=extraction,
            )
            db.add(item)
            db.commit()
            return attachment_json(item)
    except Exception:
        path.unlink(missing_ok=True)
        raise


@router.get("/api/attachments/{attachment_id}/extraction")
def attachment_extraction(
    attachment_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.user_id == user.id))
        if not item:
            raise HTTPException(404, "Pièce jointe introuvable")
        return JSONResponse({"extraction": item.extraction}, headers={"Cache-Control": "no-store"})


@router.get("/api/attachments/{attachment_id}/file")
def attachment_file(
    attachment_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(select(Attachment).where(Attachment.id == attachment_id, Attachment.user_id == user.id))
        if not item or not (upload_dir / item.storage_name).is_file():
            raise HTTPException(404, "Pièce jointe introuvable")
        return FileResponse(
            upload_dir / item.storage_name,
            media_type=item.mime_type,
            filename=item.filename,
            content_disposition_type="inline" if item.mime_type.startswith("image/") else "attachment",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )


@router.delete("/api/attachments/{attachment_id}", status_code=204)
def delete_unattached_file(
    attachment_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(Attachment)
            .where(Attachment.id == attachment_id, Attachment.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Pièce jointe introuvable")
        if item.message_id:
            raise HTTPException(409, "Cette pièce jointe appartient à un message ; supprimez sa conversation pour la retirer")
        storage_name = item.storage_name
        db.delete(item)
        db.commit()
    (upload_dir / storage_name).unlink(missing_ok=True)
    return Response(status_code=204)

