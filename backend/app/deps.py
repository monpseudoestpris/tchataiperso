import asyncio
from pathlib import Path
from typing import Generator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .auth import token_digest
from .config import Settings
from .models import AuthSession, Conversation, User, now


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    settings.refresh_from_env_file()
    return settings


def get_sessions(request: Request) -> sessionmaker:
    return request.app.state.sessions


def get_db(request: Request) -> Generator[Session, None, None]:
    sessions: sessionmaker = request.app.state.sessions
    with sessions() as db:
        yield db


def get_upload_dir(request: Request) -> Path:
    if hasattr(request.app.state, "upload_dir"):
        return request.app.state.upload_dir
    settings: Settings = request.app.state.settings
    upload_dir = settings.app_data_dir.resolve() / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def current_user(request: Request) -> User:
    settings: Settings = request.app.state.settings
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(401, "Connexion requise")
    sessions: sessionmaker = request.app.state.sessions
    with sessions() as db:
        auth_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == token_digest(token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now(),
            )
        )
        user = db.get(User, auth_session.user_id) if auth_session else None
        if not user or not user.active:
            raise HTTPException(401, "Session invalide ou expirée")
        return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "Accès réservé à l’administration")
    return user


def get_conversation(db: Session, conversation_id: str, user_id: str) -> Conversation:
    item = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    if not item:
        raise HTTPException(404, "Conversation introuvable")
    return item


def check_model(settings: Settings, model: str) -> dict:
    found = next((item for item in settings.models if item["id"] == model), None)
    if not found:
        try:
            found = next((item for item in settings.configured_models if item["id"] == model), None)
        except Exception:
            pass
    if not found:
        raise HTTPException(422, "Modèle absent de LLM_MODELS")
    return found


def claim(request: Request, user_id: str, conversation_id: str) -> asyncio.Lock:
    if not hasattr(request.app.state, "locks"):
        request.app.state.locks = {}
    lock = request.app.state.locks.setdefault(f"{user_id}:{conversation_id}", asyncio.Lock())
    if lock.locked():
        raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
    return lock


def get_lock(request: Request, user_id: str, conversation_id: str) -> asyncio.Lock | None:
    locks: dict[str, asyncio.Lock] = getattr(request.app.state, "locks", {})
    return locks.get(f"{user_id}:{conversation_id}")

