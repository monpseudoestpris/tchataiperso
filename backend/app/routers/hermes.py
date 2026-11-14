import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..hermes_agent import (
    DEFAULT_HERMES_SOUL,
    HERMES_MISSION_PRESETS,
    HERMES_TOOLS_CATALOG,
    probe_hermes_gateway,
    stream_hermes_mission,
)
from ..models import Memory, Skill, User
from ..schemas import HermesRunRequest
from ..serializers import sse

_logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/hermes", tags=["hermes"])


@router.get("/status")
async def hermes_status(
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Retourne l'état du connecteur Hermes Agent, ses outils et les statistiques utilisateur."""
    probe = await probe_hermes_gateway(settings)
    with sessions() as db:
        memories_count = db.scalar(
            select(func.count(Memory.id)).where(Memory.user_id == user.id)
        ) or 0
        skills_count = db.scalar(
            select(func.count(Skill.id)).where(Skill.user_id == user.id)
        ) or 0
    return {
        "enabled": probe["enabled"],
        "mode": probe["mode"],
        "provider": probe.get("provider", "openrouter"),
        "gateway_reachable": probe["reachable"],
        "gateway_url": probe["gateway_url"],
        "gateway_models": probe["gateway_models"],
        "default_model": getattr(settings, "hermes_default_model", "nousresearch/hermes-3-llama-3.1-405b"),
        "tools": HERMES_TOOLS_CATALOG,
        "presets": HERMES_MISSION_PRESETS,
        "default_soul": DEFAULT_HERMES_SOUL,
        "user_memories_count": int(memories_count),
        "user_skills_count": int(skills_count),
    }


@router.post("/run")
async def run_hermes_mission(
    body: HermesRunRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Lance une mission Hermes Agent en streaming SSE (Gateway, Autonome Local ou Démo)."""
    if not getattr(settings, "hermes_enabled", True):
        raise HTTPException(503, "L'intégration Hermes Agent est désactivée par configuration")

    with sessions() as db:
        user_memories = [
            item.content
            for item in db.scalars(
                select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at)
            )
        ]
        user_skills = [
            {"name": item.name, "prompt": item.prompt}
            for item in db.scalars(
                select(Skill).where(Skill.user_id == user.id).order_by(Skill.created_at)
            )
        ]

    async def event_stream():
        try:
            async for ev in stream_hermes_mission(
                settings=settings,
                prompt=body.prompt,
                model=body.model,
                session_id=body.session_id,
                soul_prompt=body.soul_prompt,
                enabled_tools=list(body.enabled_tools),
                user_memories=user_memories,
                user_skills=user_skills,
                auto_learn_skill=body.auto_learn_skill,
                execution_mode=body.execution_mode,
                sessions=sessions,
                user_id=user.id,
            ):
                event_type = ev.get("type", "message")
                yield sse(event_type, ev)
        except providers.ProviderError as exc:
            yield sse("error", {"message": str(exc)})
        except Exception as exc:
            _logger.exception("Erreur lors de l'exécution d'une mission Hermes: %s", exc)
            yield sse("error", {"message": "Impossible de terminer la mission Hermes Agent."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
