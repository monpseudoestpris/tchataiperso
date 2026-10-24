from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import current_user, get_conversation, get_sessions, get_settings
from ..models import ConversationSkill, Skill, User, now
from ..schemas import CreateSkill, ImproveSkillPrompt, SetConversationSkills, UpdateSkill
from ..serializers import MAX_SKILL_COUNT, MAX_SKILL_CONTEXT_CHARS, skill_json


router = APIRouter(tags=["skills"])


@router.get("/api/skills")
def list_skills(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        return [
            skill_json(item)
            for item in db.scalars(select(Skill).where(Skill.user_id == user.id).order_by(Skill.created_at, Skill.id))
        ]


@router.post("/api/skills", status_code=201)
def create_skill(
    body: CreateSkill,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        count = db.scalar(select(func.count()).select_from(Skill).where(Skill.user_id == user.id))
        if count >= MAX_SKILL_COUNT:
            raise HTTPException(422, f"Limite de {MAX_SKILL_COUNT} compétences atteinte")
        item = Skill(user_id=user.id, name=body.name, prompt=body.prompt)
        db.add(item)
        db.commit()
        return skill_json(item)


@router.post("/api/skills/improve")
async def improve_skill(
    body: ImproveSkillPrompt,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    if settings.demo_mode or not settings.enabled(settings.llm_api_key):
        raise HTTPException(503, "L'amélioration des compétences nécessite une clé LLM_API_KEY et le mode IA réel")
    try:
        prompt = await providers.improve_skill_prompt(settings, settings.default_model, body.prompt)
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"prompt": prompt}


@router.patch("/api/skills/{skill_id}")
def update_skill(
    skill_id: str,
    body: UpdateSkill,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id))
        if not item:
            raise HTTPException(404, "Compétence introuvable")
        new_prompt = body.prompt if body.prompt is not None else item.prompt
        for link in item.conversation_links:
            other_prompt_chars = sum(
                len(active_link.skill.prompt)
                for active_link in link.conversation.skill_links
                if active_link.skill_id != item.id
            )
            skill_limit = min(MAX_SKILL_CONTEXT_CHARS, settings.max_context_chars - 5000)
            if other_prompt_chars + len(new_prompt) > skill_limit:
                raise HTTPException(422, "Les prompts actifs de cette conversation dépasseraient la limite de contexte")
        if body.name is not None:
            item.name = body.name
        if body.prompt is not None:
            item.prompt = body.prompt
        item.updated_at = now()
        db.commit()
        return skill_json(item)


@router.delete("/api/skills/{skill_id}", status_code=204)
def delete_skill(
    skill_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        item = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id))
        if not item:
            raise HTTPException(404, "Compétence introuvable")
        db.delete(item)
        db.commit()
    return Response(status_code=204)


@router.get("/api/conversations/{conversation_id}/skills")
def list_conversation_skills(
    conversation_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        conversation = get_conversation(db, conversation_id, user.id)
        return [skill_json(link.skill) for link in conversation.skill_links]


@router.patch("/api/conversations/{conversation_id}/skills")
def set_conversation_skills(
    conversation_id: str,
    body: SetConversationSkills,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    locks = getattr(request.app.state, "locks", {})
    lock_key = f"{user.id}:{conversation_id}"
    if locks.get(lock_key) and locks[lock_key].locked():
        raise HTTPException(409, "Attendez la fin de la réponse")
    with sessions() as db:
        conversation = get_conversation(db, conversation_id, user.id)
        found = (
            list(db.scalars(select(Skill).where(Skill.id.in_(body.skill_ids), Skill.user_id == user.id)))
            if body.skill_ids
            else []
        )
        if len(found) != len(body.skill_ids):
            raise HTTPException(404, "Une ou plusieurs compétences sont introuvables")
        by_id = {item.id: item for item in found}
        selected = [by_id[item_id] for item_id in body.skill_ids]
        skill_limit = min(MAX_SKILL_CONTEXT_CHARS, settings.max_context_chars - 5000)
        if sum(len(item.prompt) for item in selected) > skill_limit:
            raise HTTPException(422, "Les prompts actifs dépassent la limite de contexte")
        conversation.skill_links.clear()
        db.flush()
        conversation.skill_links = [ConversationSkill(skill=item, position=index) for index, item in enumerate(selected)]
        conversation.updated_at = now()
        db.commit()
        return [skill_json(item) for item in selected]

