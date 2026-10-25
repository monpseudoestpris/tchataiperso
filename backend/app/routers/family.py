from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..auth import hash_password, new_token, token_digest, verify_password
from ..config import Settings
from ..deps import current_user, get_sessions, get_settings
from ..models import AuthSession, FamilyGroup, User, now
from ..schemas import (
    CreateFamilyGroup,
    CreateFamilyMember,
    FamilyGroupResponse,
    FamilyMemberItem,
    LinkFamilyMember,
    UpdateFamilyGroup,
)
from ..serializers import user_json

router = APIRouter(tags=["family"])


def _build_family_response(family: FamilyGroup | None, current_user_id: str, db: Session) -> dict:
    if not family:
        return {"id": None, "name": None, "members": []}
    members = db.scalars(
        select(User).where(User.family_group_id == family.id, User.active.is_(True)).order_by(User.username)
    ).all()
    return {
        "id": family.id,
        "name": family.name,
        "members": [
            {
                "id": member.id,
                "username": member.username,
                "is_admin": member.is_admin,
                "active": member.active,
                "is_current": member.id == current_user_id,
            }
            for member in members
        ],
    }


@router.get("/api/family", response_model=FamilyGroupResponse)
def get_family(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        family = db.get(FamilyGroup, user.family_group_id) if user.family_group_id else None
        return _build_family_response(family, user.id, db)


@router.post("/api/family", response_model=FamilyGroupResponse)
def create_or_update_family(
    body: CreateFamilyGroup,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Le nom du groupe familial ne peut pas être vide.")
    with sessions() as db:
        db_user = db.get(User, user.id)
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable.")

        if db_user.family_group_id:
            family = db.get(FamilyGroup, db_user.family_group_id)
            if family:
                family.name = name
                db.commit()
                return _build_family_response(family, user.id, db)

        family = FamilyGroup(name=name, created_by_user_id=db_user.id)
        db.add(family)
        db.flush()
        db_user.family_group_id = family.id
        db.commit()
        return _build_family_response(family, user.id, db)


@router.patch("/api/family", response_model=FamilyGroupResponse)
def update_family(
    body: UpdateFamilyGroup,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Le nom du groupe familial ne peut pas être vide.")
    with sessions() as db:
        db_user = db.get(User, user.id)
        if not db_user or not db_user.family_group_id:
            raise HTTPException(404, "Vous n'appartenez à aucun groupe familial.")
        family = db.get(FamilyGroup, db_user.family_group_id)
        if not family:
            raise HTTPException(404, "Groupe familial introuvable.")
        family.name = name
        db.commit()
        return _build_family_response(family, user.id, db)


@router.post("/api/family/members", response_model=FamilyGroupResponse, status_code=201)
def create_family_member(
    body: CreateFamilyMember,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        db_user = db.get(User, user.id)
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable.")

        # Vérifier si l'identifiant est déjà pris
        existing = db.scalar(select(User).where(User.username == body.username))
        if existing:
            raise HTTPException(409, f"L'identifiant « {body.username} » est déjà utilisé.")

        # S'assurer que l'utilisateur courant a un groupe familial
        if not db_user.family_group_id:
            family = FamilyGroup(name=f"Famille {db_user.username}", created_by_user_id=db_user.id)
            db.add(family)
            db.flush()
            db_user.family_group_id = family.id
        else:
            family = db.get(FamilyGroup, db_user.family_group_id)
            if not family:
                family = FamilyGroup(name=f"Famille {db_user.username}", created_by_user_id=db_user.id)
                db.add(family)
                db.flush()
                db_user.family_group_id = family.id

        new_member = User(
            username=body.username,
            password_hash=hash_password(body.password),
            is_admin=False,
            active=True,
            family_group_id=family.id,
        )
        db.add(new_member)
        db.commit()
        return _build_family_response(family, user.id, db)


@router.post("/api/family/link", response_model=FamilyGroupResponse)
def link_existing_member(
    body: LinkFamilyMember,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        db_user = db.get(User, user.id)
        if not db_user:
            raise HTTPException(404, "Utilisateur introuvable.")

        target = db.scalar(select(User).where(User.username == body.username, User.active.is_(True)))
        if not target or not verify_password(body.password, target.password_hash):
            raise HTTPException(401, "Identifiant ou mot de passe incorrect.")

        if target.id == db_user.id:
            raise HTTPException(400, "Vous ne pouvez pas rattacher votre propre compte à lui-même.")

        # S'assurer que l'utilisateur courant a un groupe familial
        if not db_user.family_group_id:
            family = FamilyGroup(name=f"Famille {db_user.username}", created_by_user_id=db_user.id)
            db.add(family)
            db.flush()
            db_user.family_group_id = family.id
        else:
            family = db.get(FamilyGroup, db_user.family_group_id)
            if not family:
                family = FamilyGroup(name=f"Famille {db_user.username}", created_by_user_id=db_user.id)
                db.add(family)
                db.flush()
                db_user.family_group_id = family.id

        if target.family_group_id == family.id:
            raise HTTPException(400, f"« {target.username} » fait déjà partie de ce groupe familial.")

        target.family_group_id = family.id
        db.commit()
        return _build_family_response(family, user.id, db)


@router.delete("/api/family/members/{member_id}", response_model=FamilyGroupResponse)
def remove_family_member(
    member_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        db_user = db.get(User, user.id)
        if not db_user or not db_user.family_group_id:
            raise HTTPException(404, "Vous n'appartenez à aucun groupe familial.")

        family = db.get(FamilyGroup, db_user.family_group_id)
        target = db.get(User, member_id)
        if not target or target.family_group_id != db_user.family_group_id:
            raise HTTPException(404, "Membre introuvable dans ce groupe familial.")

        target.family_group_id = None
        db.commit()
        return _build_family_response(family, user.id, db)


@router.post("/api/family/switch/{target_user_id}")
def switch_account(
    target_user_id: str,
    response: Response,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        db_user = db.get(User, user.id)
        if not db_user or not db_user.family_group_id:
            raise HTTPException(403, "Vous ne faites partie d'aucun groupe familial.")

        target = db.get(User, target_user_id)
        if not target or not target.active or target.family_group_id != db_user.family_group_id:
            raise HTTPException(403, "Basculement non autorisé : cet utilisateur n'appartient pas à votre groupe familial.")

        token = new_token()
        expires_at = now() + timedelta(days=settings.session_days)
        db.add(AuthSession(user_id=target.id, token_hash=token_digest(token), expires_at=expires_at))
        db.commit()
        result = user_json(target)

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

