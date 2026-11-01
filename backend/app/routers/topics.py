from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..deps import current_user, get_sessions
from ..models import Conversation, TopicEvent, TopicMemory, TopicResource, TopicSpace, User, now
from ..schemas import (
    CreateTopicEvent,
    CreateTopicMemory,
    CreateTopicResource,
    CreateTopicSpace,
    UpdateTopicMemory,
    UpdateTopicResource,
    UpdateTopicSpace,
)
from ..serializers import (
    topic_event_json,
    topic_memory_json,
    topic_resource_json,
    topic_space_json,
)

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("")
def list_topics(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topics = list(
            db.scalars(
                select(TopicSpace)
                .where(TopicSpace.user_id == user.id)
                .order_by(TopicSpace.updated_at.desc())
            )
        )
        return [topic_space_json(t) for t in topics]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_topic(
    body: CreateTopicSpace,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = TopicSpace(
            user_id=user.id,
            title=body.title.strip(),
            icon=body.icon.strip() or "📌",
            topic_type=body.topic_type,
            objective=body.objective.strip(),
            current_resume_context=f"Espace « {body.title.strip()} » initialisé.",
            suggested_next_step="Démarrer une première discussion pour définir les bases et explorer ce sujet.",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return topic_space_json(item, detail=True)


@router.get("/{topic_id}")
def get_topic(
    topic_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")
        return topic_space_json(topic, detail=True)


@router.patch("/{topic_id}")
def update_topic(
    topic_id: str,
    body: UpdateTopicSpace,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        if body.title is not None:
            topic.title = body.title.strip()
        if body.icon is not None:
            topic.icon = body.icon.strip() or "📌"
        if body.topic_type is not None:
            topic.topic_type = body.topic_type
        if body.objective is not None:
            topic.objective = body.objective.strip()
        if body.current_resume_context is not None:
            topic.current_resume_context = body.current_resume_context.strip()
        if body.suggested_next_step is not None:
            topic.suggested_next_step = body.suggested_next_step.strip()

        topic.updated_at = now()
        db.commit()
        db.refresh(topic)
        return topic_space_json(topic, detail=True)


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(
    topic_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")
        db.delete(topic)
        db.commit()


@router.post("/{topic_id}/conversations/{conversation_id}")
def link_conversation(
    topic_id: str,
    conversation_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        conv = db.scalar(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation introuvable")

        conv.topic_space_id = topic.id
        conv.updated_at = now()
        topic.updated_at = now()
        db.commit()
        db.refresh(topic)
        return topic_space_json(topic, detail=True)


@router.delete("/{topic_id}/conversations/{conversation_id}")
def unlink_conversation(
    topic_id: str,
    conversation_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        conv = db.scalar(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
        )
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation introuvable")

        if conv.topic_space_id == topic.id:
            conv.topic_space_id = None
            conv.updated_at = now()
            topic.updated_at = now()
            db.commit()
        db.refresh(topic)
        return topic_space_json(topic, detail=True)


@router.get("/{topic_id}/memories")
def list_topic_memories(
    topic_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        memories = list(
            db.scalars(
                select(TopicMemory)
                .where(TopicMemory.topic_space_id == topic.id)
                .order_by(TopicMemory.created_at.desc())
            )
        )
        return [topic_memory_json(m) for m in memories]


@router.post("/{topic_id}/memories", status_code=status.HTTP_201_CREATED)
def create_topic_memory(
    topic_id: str,
    body: CreateTopicMemory,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        memory = TopicMemory(
            topic_space_id=topic.id,
            fact=body.fact.strip(),
            category=body.category.strip() or "general",
            status=body.status,
            confidence=body.confidence,
            source_message_id=body.source_message_id,
            user_verified=True,  # created by user
        )
        db.add(memory)
        topic.updated_at = now()
        db.commit()
        db.refresh(memory)
        return topic_memory_json(memory)


@router.patch("/{topic_id}/memories/{memory_id}")
def update_topic_memory(
    topic_id: str,
    memory_id: str,
    body: UpdateTopicMemory,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        memory = db.scalar(
            select(TopicMemory).where(TopicMemory.id == memory_id, TopicMemory.topic_space_id == topic.id)
        )
        if not memory:
            raise HTTPException(status_code=404, detail="Souvenir introuvable dans cet espace")

        if body.fact is not None:
            memory.fact = body.fact.strip()
        if body.category is not None:
            memory.category = body.category.strip()
        if body.status is not None:
            memory.status = body.status
        if body.confidence is not None:
            memory.confidence = body.confidence
        if body.user_verified is not None:
            memory.user_verified = body.user_verified
        if body.is_archived is not None:
            memory.is_archived = body.is_archived

        memory.updated_at = now()
        topic.updated_at = now()
        db.commit()
        db.refresh(memory)
        return topic_memory_json(memory)


@router.delete("/{topic_id}/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic_memory(
    topic_id: str,
    memory_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        memory = db.scalar(
            select(TopicMemory).where(TopicMemory.id == memory_id, TopicMemory.topic_space_id == topic.id)
        )
        if not memory:
            raise HTTPException(status_code=404, detail="Souvenir introuvable dans cet espace")

        db.delete(memory)
        topic.updated_at = now()
        db.commit()


@router.post("/{topic_id}/events", status_code=status.HTTP_201_CREATED)
def create_topic_event(
    topic_id: str,
    body: CreateTopicEvent,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        event = TopicEvent(
            topic_space_id=topic.id,
            event_type=body.event_type,
            title=body.title.strip(),
            details=body.details or {},
        )
        db.add(event)
        topic.updated_at = now()
        db.commit()
        db.refresh(event)
        return topic_event_json(event)


@router.get("/{topic_id}/resources")
def list_topic_resources(
    topic_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        resources = list(
            db.scalars(
                select(TopicResource)
                .where(TopicResource.topic_space_id == topic.id)
                .order_by(TopicResource.created_at.desc())
            )
        )
        return [topic_resource_json(r) for r in resources]


@router.post("/{topic_id}/resources", status_code=status.HTTP_201_CREATED)
def create_topic_resource(
    topic_id: str,
    body: CreateTopicResource,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        res = TopicResource(
            topic_space_id=topic.id,
            title=body.title.strip(),
            resource_type=body.resource_type,
            url=body.url.strip() if body.url else None,
            content=body.content.strip() if body.content else "",
        )
        db.add(res)
        topic.updated_at = now()
        db.commit()
        db.refresh(res)
        return topic_resource_json(res)


@router.patch("/{topic_id}/resources/{resource_id}")
def update_topic_resource(
    topic_id: str,
    resource_id: str,
    body: UpdateTopicResource,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        res = db.scalar(
            select(TopicResource).where(TopicResource.id == resource_id, TopicResource.topic_space_id == topic.id)
        )
        if not res:
            raise HTTPException(status_code=404, detail="Ressource introuvable")

        if body.title is not None:
            res.title = body.title.strip()
        if body.resource_type is not None:
            res.resource_type = body.resource_type
        if body.url is not None:
            res.url = body.url.strip() if body.url else None
        if body.content is not None:
            res.content = body.content.strip() if body.content else ""

        res.updated_at = now()
        topic.updated_at = now()
        db.commit()
        db.refresh(res)
        return topic_resource_json(res)


@router.delete("/{topic_id}/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic_resource(
    topic_id: str,
    resource_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_id, TopicSpace.user_id == user.id)
        )
        if not topic:
            raise HTTPException(status_code=404, detail="Espace thématique introuvable")

        res = db.scalar(
            select(TopicResource).where(TopicResource.id == resource_id, TopicResource.topic_space_id == topic.id)
        )
        if not res:
            raise HTTPException(status_code=404, detail="Ressource introuvable")

        db.delete(res)
        topic.updated_at = now()
        db.commit()


