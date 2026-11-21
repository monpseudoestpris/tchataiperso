from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..base_prompt import BASE_USER_PROMPT
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..models import User
from ..schemas import DEFAULT_PROMPT_PRESETS, UpdateUserSettingsRequest, UserSettingsResponse
from ..voice import is_valid_voice_id, resolve_voice_name

router = APIRouter(tags=["settings"])


@router.get("/api/settings", response_model=UserSettingsResponse)
def get_user_settings(
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    """Retrieve the current user's general prompt, caching preference, voice and presets."""
    effective_prompt = (getattr(user, "system_prompt", "") or "").strip() or BASE_USER_PROMPT
    effective_voice = resolve_voice_name(settings, getattr(user, "default_voice", None))
    return UserSettingsResponse(
        system_prompt=effective_prompt,
        prompt_cache_enabled=getattr(user, "prompt_cache_enabled", True),
        auto_memory_enabled=getattr(user, "auto_memory_enabled", True),
        default_voice=effective_voice,
        default_system_prompt=BASE_USER_PROMPT,
        prompt_presets=DEFAULT_PROMPT_PRESETS,
    )


@router.patch("/api/settings", response_model=UserSettingsResponse)
def update_user_settings(
    body: UpdateUserSettingsRequest,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
    settings: Settings = Depends(get_settings),
):
    """Update general system prompt, prompt caching, auto memory and default voice preferences."""
    with sessions() as db:
        db_user = db.scalar(select(User).where(User.id == user.id))
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable")

        if body.system_prompt is not None:
            db_user.system_prompt = body.system_prompt.strip()
        if body.prompt_cache_enabled is not None:
            db_user.prompt_cache_enabled = bool(body.prompt_cache_enabled)
        if body.auto_memory_enabled is not None:
            db_user.auto_memory_enabled = bool(body.auto_memory_enabled)
        if body.default_voice is not None:
            cleaned_voice = body.default_voice.strip()
            if not cleaned_voice:
                db_user.default_voice = None
            elif is_valid_voice_id(cleaned_voice):
                db_user.default_voice = cleaned_voice
            else:
                raise HTTPException(400, f"Voix par défaut inconnue : {cleaned_voice}")

        db.commit()
        db.refresh(db_user)

        user.system_prompt = db_user.system_prompt
        user.prompt_cache_enabled = db_user.prompt_cache_enabled
        user.auto_memory_enabled = db_user.auto_memory_enabled
        user.default_voice = db_user.default_voice

        effective_prompt = (db_user.system_prompt or "").strip() or BASE_USER_PROMPT
        effective_voice = resolve_voice_name(settings, db_user.default_voice)
        return UserSettingsResponse(
            system_prompt=effective_prompt,
            prompt_cache_enabled=db_user.prompt_cache_enabled,
            auto_memory_enabled=db_user.auto_memory_enabled,
            default_voice=effective_voice,
            default_system_prompt=BASE_USER_PROMPT,
            prompt_presets=DEFAULT_PROMPT_PRESETS,
        )

