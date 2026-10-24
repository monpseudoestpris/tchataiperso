import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import claim, current_user, get_conversation, get_sessions, get_settings, get_upload_dir
from ..models import Attachment, GeneratedImage, Message, User, now
from ..schemas import CreateImage, ImproveImagePrompt
from ..serializers import (IMAGE_ASPECT_RATIOS, MAX_GENERATED_IMAGES,
                          generated_image_json, message_json)


router = APIRouter(tags=["images"])


@router.get("/api/images")
def list_generated_images(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        return [
            generated_image_json(item)
            for item in db.scalars(
                select(GeneratedImage)
                .where(GeneratedImage.user_id == user.id)
                .order_by(GeneratedImage.created_at.desc(), GeneratedImage.id.desc())
            )
        ]


@router.post("/api/images/improve")
async def improve_image(
    body: ImproveImagePrompt,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    if settings.demo_mode or not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "L'amélioration du prompt nécessite une clé LLM_API_KEY et le mode IA réel")
    model = (
        (body.model.strip() if body.model and body.model.strip() else None)
        or settings.image_prompt_model
        or settings.default_model
    )
    try:
        prompt = await providers.improve_image_prompt(
            settings, model, body.prompt, body.style_keywords, body.negative_prompt
        )
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"prompt": prompt}


@router.post("/api/images", status_code=201)
async def create_studio_image(
    body: CreateImage,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    is_ideogram = body.model == "ideogram"
    if is_ideogram and not settings.enabled(settings.ideogram_api_key):
        raise HTTPException(503, "La génération d'image avec Ideogram nécessite IDEOGRAM_API_KEY et un mode IA réel")
    if not is_ideogram and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "La génération d'image avec ce modèle nécessite LLM_API_KEY et un mode IA réel")
    if body.aspect_ratio not in IMAGE_ASPECT_RATIOS:
        raise HTTPException(422, "Ratio d'image non pris en charge")
    with sessions() as db:
        count = db.scalar(select(func.count()).select_from(GeneratedImage).where(GeneratedImage.user_id == user.id))
        if count >= MAX_GENERATED_IMAGES:
            raise HTTPException(422, f"Limite de {MAX_GENERATED_IMAGES} images sauvegardées atteinte ; supprimez d'anciennes images")
    lock = claim(request, user.id, "image-studio")
    await lock.acquire()
    path = None
    try:
        content, mime = await providers.generate_image(
            settings, body.prompt, body.aspect_ratio, body.negative_prompt, model=body.model
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
        model_prefix = "ideogram" if is_ideogram else re.sub(r"[^a-zA-Z0-9_-]", "-", body.model.split("/")[-1])[:24]
        with sessions() as db:
            image_id = str(uuid4())
            item = GeneratedImage(
                id=image_id,
                user_id=user.id,
                prompt=body.prompt,
                aspect_ratio=body.aspect_ratio,
                filename=f"{model_prefix}-{image_id[:8]}.{extension}",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            return generated_image_json(item)
    except providers.ProviderError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.release()


@router.get("/api/images/{image_id}/file")
def generated_image_file(
    image_id: str,
    download: bool = False,
    request: Request = None,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.user_id == user.id))
        if not item or not (upload_dir / item.storage_name).is_file():
            raise HTTPException(404, "Image introuvable")
        return FileResponse(
            upload_dir / item.storage_name,
            media_type=item.mime_type,
            filename=item.filename,
            content_disposition_type="attachment" if download else "inline",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )


@router.delete("/api/images/{image_id}", status_code=204)
def delete_generated_image(
    image_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(GeneratedImage)
            .where(GeneratedImage.id == image_id, GeneratedImage.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Image introuvable")
        storage_name = item.storage_name
        db.delete(item)
        db.commit()
    (upload_dir / storage_name).unlink(missing_ok=True)
    return Response(status_code=204)


@router.post("/api/conversations/{conversation_id}/images", status_code=201)
async def create_image(
    conversation_id: str,
    body: CreateImage,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    is_ideogram = body.model == "ideogram"
    if is_ideogram and not settings.enabled(settings.ideogram_api_key):
        raise HTTPException(503, "La génération d'image avec Ideogram nécessite IDEOGRAM_API_KEY et un mode IA réel")
    if not is_ideogram and not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "La génération d'image avec ce modèle nécessite LLM_API_KEY et un mode IA réel")
    if body.aspect_ratio not in IMAGE_ASPECT_RATIOS:
        raise HTTPException(422, "Ratio d'image non pris en charge")
    lock = claim(request, user.id, conversation_id)
    await lock.acquire()
    path = None
    try:
        with sessions() as db:
            get_conversation(db, conversation_id, user.id)
        content, mime = await providers.generate_image(
            settings, body.prompt, body.aspect_ratio, body.negative_prompt, model=body.model
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        model_label = "Ideogram" if is_ideogram else body.model
        model_prefix = "ideogram" if is_ideogram else re.sub(r"[^a-zA-Z0-9_-]", "-", body.model.split("/")[-1])[:24]
        with sessions() as db:
            conversation = get_conversation(db, conversation_id, user.id)
            prompt = Message(conversation_id=conversation_id, role="user", content=f"Génère une image : {body.prompt}")
            answer = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=f"Image générée avec {model_label} : {body.prompt}",
            )
            db.add_all([prompt, answer])
            db.flush()
            extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
            attachment = Attachment(
                user_id=user.id,
                filename=f"{model_prefix}.{extension}",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
                message_id=answer.id,
            )
            db.add(attachment)
            conversation.updated_at = now()
            db.commit()
            db.refresh(answer)
            return message_json(answer)
    except providers.ProviderError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.release()

