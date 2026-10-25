import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import claim, current_user, get_sessions, get_settings, get_upload_dir
from ..models import GeneratedSound, User
from ..schemas import CreateSound, ImproveSoundPrompt
from ..serializers import (MAX_GENERATED_SOUNDS, MUSIC_MODELS, SOUND_OUTPUT_FORMATS,
                          generated_sound_json)


router = APIRouter(tags=["sounds"])


@router.get("/api/sounds")
def list_generated_sounds(
    type: str | None = None,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        stmt = select(GeneratedSound).where(GeneratedSound.user_id == user.id)
        if type in ("sound_effect", "music"):
            stmt = stmt.where(GeneratedSound.sound_type == type)
        stmt = stmt.order_by(GeneratedSound.created_at.desc(), GeneratedSound.id.desc())
        return [
            generated_sound_json(item)
            for item in db.scalars(stmt)
        ]


@router.get("/api/sounds/formats")
def list_sound_formats():
    return SOUND_OUTPUT_FORMATS


@router.get("/api/sounds/music-models")
def list_music_models():
    return MUSIC_MODELS


@router.post("/api/sounds/improve")
async def improve_sound(
    body: ImproveSoundPrompt,
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
        if body.sound_type == "music":
            prompt = await providers.improve_music_prompt(
                settings,
                model,
                body.prompt,
                style_keywords=body.style_keywords,
                duration_hint=body.duration_hint,
                instrumental=body.instrumental,
            )
        else:
            prompt = await providers.improve_sound_prompt(
                settings,
                model,
                body.prompt,
                style_keywords=body.style_keywords,
                duration_hint=body.duration_hint,
                loop=body.loop,
            )
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"prompt": prompt}


@router.post("/api/sounds/translate")
async def translate_sound(
    body: ImproveSoundPrompt,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    if settings.demo_mode or not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "La traduction nécessite une clé LLM_API_KEY et le mode IA réel")
    try:
        if body.sound_type == "music":
            prompt = await providers.translate_music_prompt_to_english(settings, body.prompt)
        else:
            prompt = await providers.translate_sound_prompt_to_english(settings, body.prompt)
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"prompt": prompt}


@router.post("/api/sounds", status_code=201)
async def create_sound_effect(
    body: CreateSound,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if settings.demo_mode or not settings.enabled(settings.eleven_labs_key):
        raise HTTPException(
            503,
            "La génération audio nécessite une clé ELEVEN_LABS_KEY valide dans le fichier .env",
        )
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        count = db.scalar(
            select(func.count()).select_from(GeneratedSound).where(GeneratedSound.user_id == user.id)
        )
        if count >= MAX_GENERATED_SOUNDS:
            raise HTTPException(
                422,
                f"Limite de {MAX_GENERATED_SOUNDS} sons sauvegardés atteinte ; supprimez d'anciens effets sonores",
            )
    lock = claim(request, user.id, "sound-studio")
    await lock.acquire()
    path = None
    try:
        is_music = body.sound_type == "music"
        if is_music:
            english_prompt = await providers.translate_music_prompt_to_english(settings, body.prompt)
            content, mime = await providers.generate_music(
                settings,
                english_prompt,
                duration_seconds=body.duration_seconds,
                force_instrumental=True if body.instrumental is None else bool(body.instrumental),
                model_id=body.model_id or "music_v1",
                output_format=body.output_format,
            )
        else:
            english_prompt = await providers.translate_sound_prompt_to_english(settings, body.prompt)
            content, mime = await providers.generate_sound_effect(
                settings,
                english_prompt,
                duration_seconds=body.duration_seconds,
                prompt_influence=body.prompt_influence,
                output_format=body.output_format,
                loop=body.loop,
            )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        extension = "wav" if "wav" in mime or "pcm" in body.output_format else "mp3"
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", body.prompt[:16]).strip("-") or ("music" if is_music else "sound")
        with sessions() as db:
            sound_id = str(uuid4())
            item = GeneratedSound(
                id=sound_id,
                user_id=user.id,
                sound_type="music" if is_music else "sound_effect",
                prompt=body.prompt,
                duration_seconds=body.duration_seconds,
                prompt_influence=body.prompt_influence if not is_music else None,
                output_format=body.output_format,
                loop=body.loop if not is_music else False,
                instrumental=body.instrumental if is_music else None,
                model_id=body.model_id if is_music else None,
                filename=f"{safe_prefix}-{sound_id[:8]}.{extension}",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            res = generated_sound_json(item)
            res["english_prompt"] = english_prompt
            return res
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


@router.get("/api/sounds/{sound_id}/file")
def generated_sound_file(
    sound_id: str,
    download: bool = False,
    request: Request = None,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(GeneratedSound).where(GeneratedSound.id == sound_id, GeneratedSound.user_id == user.id)
        )
        if not item or not (upload_dir / item.storage_name).is_file():
            raise HTTPException(404, "Effet sonore introuvable")
        return FileResponse(
            upload_dir / item.storage_name,
            media_type=item.mime_type,
            filename=item.filename,
            content_disposition_type="attachment" if download else "inline",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
                "Accept-Ranges": "bytes",
            },
        )


@router.delete("/api/sounds/{sound_id}", status_code=204)
def delete_generated_sound(
    sound_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(GeneratedSound).where(GeneratedSound.id == sound_id, GeneratedSound.user_id == user.id)
        )
        if not item:
            raise HTTPException(404, "Effet sonore introuvable")
        storage_path = upload_dir / item.storage_name
        db.delete(item)
        db.commit()
        storage_path.unlink(missing_ok=True)
    return None

