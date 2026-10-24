from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ..auth import new_token, token_digest
from ..config import Settings
from ..deps import get_sessions, get_settings, require_admin
from ..models import Invitation, User, now
from ..schemas import AdminUpdateUser
from ..serializers import stamp


router = APIRouter(tags=["admin"])


@router.get("/api/admin/users")
def list_users(
    _admin: User = Depends(require_admin),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        return [
            {
                "id": item.id,
                "username": item.username,
                "is_admin": item.is_admin,
                "active": item.active,
                "created_at": stamp(item.created_at),
            }
            for item in db.scalars(select(User).order_by(User.created_at))
        ]


@router.post("/api/admin/invitations", status_code=201)
def create_invitation(
    admin: User = Depends(require_admin),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    token = new_token()
    expires_at = now() + timedelta(days=settings.invitation_days)
    with sessions() as db:
        db.add(Invitation(created_by_user_id=admin.id, token_hash=token_digest(token), expires_at=expires_at))
        db.commit()
    return {"token": token, "expires_at": stamp(expires_at)}


@router.patch("/api/admin/users/{user_id}")
def update_user(
    user_id: str,
    body: AdminUpdateUser,
    admin: User = Depends(require_admin),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, "Utilisateur introuvable")
        if target.id == admin.id and not body.active:
            raise HTTPException(409, "Vous ne pouvez pas désactiver votre propre compte")
        if target.is_admin and target.active and not body.active:
            active_admins = db.scalar(
                select(func.count()).select_from(User).where(User.is_admin.is_(True), User.active.is_(True))
            )
            if active_admins <= 1:
                raise HTTPException(409, "Le dernier administrateur actif ne peut pas être désactivé")
        target.active = body.active
        db.commit()
        return {
            "id": target.id,
            "username": target.username,
            "is_admin": target.is_admin,
            "active": target.active,
            "created_at": stamp(target.created_at),
        }

