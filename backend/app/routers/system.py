import asyncio
from contextlib import suppress
import os
from pathlib import Path
import signal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from ..config import Settings
from ..deps import get_sessions, get_settings, require_admin
from ..finance_funds import is_sync_task_running, stop_active_sync_task
from ..finance_warehouse import checkpoint_warehouse, warehouse_db_path
from ..google_cloud import has_llm_access
from ..models import User
from ..sampling import PARAMETER_CATALOG
from ..schemas import CONVERSATION_THEMES
from ..voice import GOOGLE_TTS_TONES, GOOGLE_TTS_VOICES, has_stt_access, has_tts_access, resolve_stt_provider, resolve_voice_name


router = APIRouter(tags=["system"])


class PrepareShutdownRequest(BaseModel):
    stop_process: bool = False


def _is_running_in_docker() -> bool:
    return Path("/.dockerenv").exists()


def _count_active_chat_streams(request: Request) -> int:
    locks = getattr(request.app.state, "locks", None) or {}
    return sum(1 for lock in locks.values() if lock.locked())


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
        "skill_prompt_model": settings.skill_prompt_model,
        "image_models": settings.available_image_models,
        "default_image_model": settings.effective_default_image_model,
        "google_cloud_mode": settings.active_google_cloud_mode or "disabled",
        "features": {
            "chat": settings.demo_mode or has_llm_access(settings),
            "google_cloud": settings.google_cloud_enabled,
            "web_search": settings.web_search_enabled,
            "ocr": settings.enabled(settings.mistral_api_key),
            "image_generation": bool(settings.available_image_models),
            "sound_effects": settings.enabled(settings.eleven_labs_key),
            "music_generation": settings.enabled(settings.eleven_labs_key),
            "tts": has_tts_access(settings),
            "stt": has_stt_access(settings),
        },
        "voice": {
            "voices": GOOGLE_TTS_VOICES,
            "tones": [{"id": t["id"], "label": t["label"]} for t in GOOGLE_TTS_TONES],
            "default_voice": resolve_voice_name(settings),
            "default_tone": "natural",
            "stt_provider": resolve_stt_provider(settings),
        },
    }


@router.get("/api/models")
def models_directory(refresh: bool = False, settings: Settings = Depends(get_settings)):
    return {
        "models": settings.get_models(force_refresh=refresh),
        "default_model": settings.default_model,
    }


@router.get("/api/models/{model_id:path}/parameters")
def model_parameters(
    model_id: str,
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
):
    supported = settings.get_model_supported_parameters(model_id, force_refresh=refresh)
    supported_set = set(supported)
    return {
        "model": model_id,
        "supported_parameters": supported,
        "parameters": [
            {
                **param,
                "available": param["name"] in supported_set,
            }
            for param in PARAMETER_CATALOG
        ],
    }


@router.get("/api/system/shutdown-status")
def shutdown_status(
    request: Request,
    _admin: User = Depends(require_admin),
):
    engine = getattr(request.app.state, "engine", None)
    return {
        "shutting_down": bool(getattr(request.app.state, "shutting_down", False)),
        "active_chat_streams": _count_active_chat_streams(request),
        "finance_sync_running": is_sync_task_running(),
        "running_in_docker": _is_running_in_docker(),
        "main_db_dialect": engine.dialect.name if engine is not None else "unknown",
    }


@router.post("/api/system/prepare-shutdown")
async def prepare_shutdown(
    body: PrepareShutdownRequest,
    request: Request,
    _admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """Gèle les nouvelles écritures, arrête proprement les tâches de fond, attend les streams actifs et flushe les BDDs."""
    request.app.state.shutting_down = True

    # 1. Arrêt coopératif de la boucle de synchro quotidienne + synchro Finance en cours
    sync_loop = getattr(request.app.state, "sync_task", None)
    if sync_loop is not None and not sync_loop.done():
        sync_loop.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(asyncio.shield(sync_loop), timeout=3.0)
        request.app.state.sync_task = None

    finance_sync_stopped = await stop_active_sync_task(timeout_seconds=12.0)

    # 2. Attendre la fin des streams de tchat actifs (borné à 12 s)
    deadline = asyncio.get_running_loop().time() + 12.0
    while _count_active_chat_streams(request) > 0 and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.25)
    remaining_streams = _count_active_chat_streams(request)

    # 3. Checkpoint complet SQLite WAL sur finance_warehouse.db
    warehouse_ckpt = await asyncio.to_thread(checkpoint_warehouse, warehouse_db_path(settings))

    # 4. Flush / checkpoint de la base principale
    main_db_flushed = False
    engine = getattr(request.app.state, "engine", None)
    if engine is not None:
        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
                conn.commit()
            main_db_flushed = True
        else:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                conn.commit()
            main_db_flushed = True

    in_docker = _is_running_in_docker()
    process_stopping = bool(body.stop_process and not in_docker)
    if process_stopping:
        loop = asyncio.get_running_loop()
        loop.call_later(0.4, lambda: os.kill(os.getpid(), signal.SIGTERM))

    return {
        "status": "ready_to_quit",
        "shutting_down": True,
        "running_in_docker": in_docker,
        "finance_sync_stopped": finance_sync_stopped,
        "active_chat_streams_remaining": remaining_streams,
        "warehouse_checkpoint": warehouse_ckpt,
        "main_db_flushed": main_db_flushed,
        "process_stopping": process_stopping,
    }


@router.post("/api/system/resume")
def resume_after_shutdown(
    request: Request,
    _admin: User = Depends(require_admin),
):
    """Lève le gel des écritures si l'administrateur décide finalement de continuer la session."""
    request.app.state.shutting_down = False
    return {"status": "running", "shutting_down": False}

