from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..deps import current_user, get_sessions
from ..models import Memory, User
from ..schemas import CreateMemory
from ..serializers import stamp


router = APIRouter(tags=["memories"])


@router.get("/api/memories")
def list_memories(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        return [
            {"id": item.id, "content": item.content, "created_at": stamp(item.created_at)}
            for item in db.scalars(select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at))
        ]


@router.post("/api/memories", status_code=201)
def add_memory(
    body: CreateMemory,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    if not body.content.strip():
        raise HTTPException(422, "Le souvenir ne peut pas être vide")
    with sessions() as db:
        if len(db.scalars(select(Memory).where(Memory.user_id == user.id)).all()) >= 100:
            raise HTTPException(422, "Limite de 100 souvenirs atteinte")
        item = Memory(user_id=user.id, content=body.content.strip())
        db.add(item)
        db.commit()
        return {"id": item.id, "content": item.content, "created_at": stamp(item.created_at)}


@router.delete("/api/memories/{memory_id}", status_code=204)
def delete_memory(
    memory_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
        if not item:
            raise HTTPException(404, "Souvenir introuvable")
        db.delete(item)
        db.commit()
    return Response(status_code=204)

