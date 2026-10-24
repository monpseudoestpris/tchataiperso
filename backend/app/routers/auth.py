from datetime import timedelta
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..auth import hash_password, new_token, token_digest, verify_password
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..models import AuthSession, Invitation, User, now
from ..schemas import AcceptInvitation, LoginRequest
from ..serializers import user_json


router = APIRouter(tags=["auth"])


@router.post("/api/auth/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if not hasattr(request.app.state, "login_failures"):
        request.app.state.login_failures = {}
    login_failures: dict[str, tuple[int, float]] = request.app.state.login_failures

    current_time = monotonic()
    if len(login_failures) > 1024:
        for address, (_, started_at) in list(login_failures.items()):
            if current_time - started_at >= 60:
                login_failures.pop(address, None)

    address = request.client.host if request.client else "unknown"
    attempts, window_start = login_failures.get(address, (0, current_time))
    if current_time - window_start >= 60:
        attempts, window_start = 0, current_time
    if attempts >= 10:
        raise HTTPException(429, "Trop de tentatives. Réessayez dans une minute.")

    with sessions() as db:
        user = db.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
        if not user or not verify_password(body.password, user.password_hash):
            login_failures[address] = (attempts + 1, window_start)
            raise HTTPException(401, "Identifiant ou mot de passe incorrect")
        login_failures.pop(address, None)
        token = new_token()
        expires_at = now() + timedelta(days=settings.session_days)
        db.add(AuthSession(user_id=user.id, token_hash=token_digest(token), expires_at=expires_at))
        db.commit()
        result = user_json(user)

    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return result


@router.get("/api/auth/session")
def session_info(user: User = Depends(current_user)):
    return user_json(user)


@router.post("/api/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    token = request.cookies.get(settings.session_cookie_name)
    with sessions() as db:
        auth_session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_digest(token)))
        if auth_session and not auth_session.revoked_at:
            auth_session.revoked_at = now()
            db.commit()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    response.status_code = 204
    return response


@router.post("/api/auth/register", status_code=201)
def accept_invitation(body: AcceptInvitation, sessions: sessionmaker = Depends(get_sessions)):
    with sessions() as db:
        invitation = db.scalar(
            select(Invitation).where(
                Invitation.token_hash == token_digest(body.token),
                Invitation.used_at.is_(None),
                Invitation.expires_at > now(),
            ).with_for_update()
        )
        if not invitation:
            raise HTTPException(400, "Invitation invalide, expirée ou déjà utilisée")
        user = User(username=body.username, password_hash=hash_password(body.password), is_admin=False)
        invitation.used_at = now()
        db.add(user)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Cet identifiant est déjà utilisé") from exc
        return user_json(user)

