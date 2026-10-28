from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..deps import current_user, get_sessions, get_settings
from ..config import Settings
from ..models import AgentTeam, User, now
from ..multi_agent import DEFAULT_AGENT_TEAMS, DEFAULT_AGENT_TEMPLATES, generate_ai_persona
from ..schemas import CreateAgentTeam, GeneratePersonaRequest, UpdateAgentTeam
from ..serializers import agent_team_json

router = APIRouter(prefix="/api/agent-teams", tags=["agent-teams"])


@router.post("/generate-persona")
async def generate_persona(
    body: GeneratePersonaRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    """Génère un profil de personnalité riche (nom, rôle, avatar, prompt, couleur) assisté par l'IA."""
    persona = await generate_ai_persona(settings, body.name_or_concept, body.model)
    return persona


@router.get("")
def list_agent_teams(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Retourne les équipes enregistrées de l'utilisateur ainsi que les modèles et équipes types."""
    with sessions() as db:
        teams = db.scalars(
            select(AgentTeam)
            .where(AgentTeam.user_id == user.id)
            .order_by(AgentTeam.updated_at.desc(), AgentTeam.created_at.desc())
        ).all()
        return {
            "teams": [agent_team_json(t) for t in teams],
            "templates": DEFAULT_AGENT_TEMPLATES,
            "preset_teams": DEFAULT_AGENT_TEAMS,
        }


@router.post("", status_code=201)
def create_agent_team(
    body: CreateAgentTeam,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Enregistre une nouvelle équipe d'agents pour l'utilisateur."""
    with sessions() as db:
        team = AgentTeam(
            id=str(uuid4()),
            user_id=user.id,
            name=body.name.strip(),
            description=body.description.strip(),
            mode=body.mode,
            agents=[agent.model_dump() for agent in body.agents],
            created_at=now(),
            updated_at=now(),
        )
        db.add(team)
        db.commit()
        db.refresh(team)
        return agent_team_json(team)


@router.patch("/{team_id}")
def update_agent_team(
    team_id: str,
    body: UpdateAgentTeam,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Met à jour une équipe existante."""
    with sessions() as db:
        team = db.scalar(select(AgentTeam).where(AgentTeam.id == team_id, AgentTeam.user_id == user.id))
        if not team:
            raise HTTPException(404, "Équipe d'agents introuvable")

        if body.name is not None:
            team.name = body.name.strip()
        if body.description is not None:
            team.description = body.description.strip()
        if body.mode is not None:
            team.mode = body.mode
        if body.agents is not None:
            team.agents = [agent.model_dump() for agent in body.agents]
        team.updated_at = now()
        db.commit()
        db.refresh(team)
        return agent_team_json(team)


@router.delete("/{team_id}", status_code=204)
def delete_agent_team(
    team_id: str,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    """Supprime une équipe enregistrée."""
    with sessions() as db:
        team = db.scalar(select(AgentTeam).where(AgentTeam.id == team_id, AgentTeam.user_id == user.id))
        if not team:
            raise HTTPException(404, "Équipe d'agents introuvable")
        db.delete(team)
        db.commit()
    return Response(status_code=204)

