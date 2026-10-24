from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import get_sessions, get_settings
from ..schemas import CONVERSATION_THEMES


router = APIRouter(tags=["system"])


@router.get("/api/health")
def health(sessions: sessionmaker = Depends(get_sessions)):
    with sessions() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/api/config")
def config(settings: Settings = Depends(get_settings)):
    search_providers = []
    if not settings.demo_mode:
        if settings.searxng_url.strip():
            search_providers.append("searxng")
        if settings.enabled(settings.brave_api_key):
            search_providers.append("brave")
        if settings.duckduckgo_enabled:
            search_providers.append("duckduckgo_instant_answers")
    return {
        "models": settings.models,
        "default_model": settings.default_model,
        "demo_mode": settings.demo_mode,
        "themes": list(CONVERSATION_THEMES),
        "search_providers": search_providers,
        "image_prompt_model": settings.image_prompt_model,
        "image_models": settings.available_image_models,
        "default_image_model": settings.effective_default_image_model,
        "features": {
            "chat": settings.demo_mode or settings.enabled(settings.llm_api_key),
            "web_search": settings.web_search_enabled,
            "ocr": settings.enabled(settings.mistral_api_key),
            "image_generation": bool(settings.available_image_models),
        },
    }


@router.get("/api/models")
def models_directory(refresh: bool = False, settings: Settings = Depends(get_settings)):
    return {
        "models": settings.get_models(force_refresh=refresh),
        "default_model": settings.default_model,
    }

