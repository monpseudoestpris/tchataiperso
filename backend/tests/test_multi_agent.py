import pytest
from starlette.testclient import TestClient

from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import AgentTeam, Base, Conversation, Message, User
from app.multi_agent import (
    DEFAULT_AGENT_TEAMS,
    DEFAULT_AGENT_TEMPLATES,
    fallback_agent_turn,
    fallback_multi_agent_synthesis,
)


def test_multi_agent_defaults_and_fallbacks():
    assert len(DEFAULT_AGENT_TEMPLATES) >= 17
    assert len(DEFAULT_AGENT_TEAMS) >= 6

    template_names = [t["name"] for t in DEFAULT_AGENT_TEMPLATES]
    assert any("Tony Stark" in name for name in template_names)
    assert any("Général de Gaulle" in name for name in template_names)
    assert any("Kennedy" in name for name in template_names)
    assert any("Einstein" in name for name in template_names)
    assert any("Léonard de Vinci" in name for name in template_names)
    assert any("Spielberg" in name for name in template_names)
    assert any("Jordan" in name for name in template_names)
    assert any("Camus" in name for name in template_names)

    lawyer = DEFAULT_AGENT_TEMPLATES[0]
    lawyer_turn = fallback_agent_turn(lawyer, "Puis-je rompre ce contrat unilatéralement ?")
    assert "juridique" in lawyer_turn.lower() or "contrat" in lawyer_turn.lower()

    math_expert = DEFAULT_AGENT_TEMPLATES[1]
    math_turn = fallback_agent_turn(math_expert, "Combien font 2^10 et pourquoi ?")
    assert "logique" in math_turn.lower() or "calcul" in math_turn.lower()

    synth = fallback_multi_agent_synthesis(
        "Comment lancer notre projet ?",
        [
            {"name": "Maître Legrand", "role": "Avocat", "avatar": "⚖️", "model": "gpt-4", "text": "Avis légal"},
            {"name": "Professeur Gauss", "role": "Mathématicien", "avatar": "📐", "model": "r1", "text": "Avis logique"},
        ],
    )
    assert "## 🎯 Synthèse du Conseil d'Experts" in synth
    assert "Points de Consensus" in synth
    assert "Divergences" in synth
    assert "<details>" in synth
    assert "Maître Legrand" in synth


def test_agent_teams_crud_api(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'teams_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="teamuser",
            password_hash=hash_password("correct horse battery"),
            is_admin=True,
            active=True,
        )
        db.add(user)
        db.commit()

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "teamuser", "password": "correct horse battery"})
        assert login_res.status_code == 200

        # 1. GET /api/agent-teams (initially empty saved teams, templates and preset teams present)
        res = client.get("/api/agent-teams")
        assert res.status_code == 200
        data = res.json()
        assert data["teams"] == []
        assert len(data["templates"]) >= 8
        assert len(data["preset_teams"]) >= 3

        # 2. POST /api/agent-teams (create team)
        create_payload = {
            "name": "Mon Conseil Privé",
            "description": "Avocat et Mathématicien",
            "mode": "synthesis",
            "agents": [
                {
                    "name": "Maître Legrand",
                    "role": "Avocat",
                    "model": "anthropic/claude-3.5-sonnet",
                    "prompt": "Analyse juridique stricte",
                    "avatar": "⚖️",
                    "color": "#d97706",
                },
                {
                    "name": "Professeur Gauss",
                    "role": "Mathématicien",
                    "model": "deepseek/deepseek-r1",
                    "prompt": "Raisonnement logique",
                    "avatar": "📐",
                    "color": "#2563eb",
                },
            ],
        }
        create_res = client.post("/api/agent-teams", json=create_payload)
        assert create_res.status_code == 201
        created = create_res.json()
        team_id = created["id"]
        assert created["name"] == "Mon Conseil Privé"
        assert len(created["agents"]) == 2

        # 3. PATCH /api/agent-teams/{id}
        patch_res = client.patch(
            f"/api/agent-teams/{team_id}",
            json={"name": "Mon Conseil Privé (Modifié)", "mode": "debate"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["name"] == "Mon Conseil Privé (Modifié)"
        assert patch_res.json()["mode"] == "debate"

        # 4. GET /api/agent-teams shows updated team
        list_res = client.get("/api/agent-teams")
        assert len(list_res.json()["teams"]) == 1
        assert list_res.json()["teams"][0]["id"] == team_id

        # 5. DELETE /api/agent-teams/{id}
        del_res = client.delete(f"/api/agent-teams/{team_id}")
        assert del_res.status_code == 204

        # Confirm deleted
        empty_res = client.get("/api/agent-teams")
        assert len(empty_res.json()["teams"]) == 0

        # 6. POST /api/agent-teams/generate-persona (AI Persona generation)
        gen_res = client.post(
            "/api/agent-teams/generate-persona",
            json={"name_or_concept": "Poutine"},
        )
        assert gen_res.status_code == 200
        persona = gen_res.json()
        assert "Poutine" in persona["name"]
        assert persona["avatar"] == "🐻"
        assert len(persona["prompt"]) > 50
        assert persona["role"] != ""


def test_send_message_with_multi_agent(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'multi_msg_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="msguser",
            password_hash=hash_password("correct horse battery"),
            is_admin=True,
            active=True,
        )
        db.add(user)
        db.commit()
        conv = Conversation(title="Test Multi-Agent", user_id=user.id, model=settings.default_model)
        db.add(conv)
        db.commit()
        conv_id = conv.id

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "msguser", "password": "correct horse battery"})
        assert login_res.status_code == 200

        # Send multi-agent message (Synthesis mode)
        payload = {
            "content": "Devons-nous signer ce partenariat complexe ?",
            "multi_agent": True,
            "multi_agent_config": {
                "mode": "synthesis",
                "agents": [
                    {
                        "name": "Maître Legrand",
                        "role": "Avocat",
                        "model": "anthropic/claude-3.5-sonnet",
                        "prompt": "Analyse juridique stricte",
                        "avatar": "⚖️",
                        "color": "#d97706",
                    },
                    {
                        "name": "Alexandre",
                        "role": "Architecte Logiciel",
                        "model": "openai/gpt-4o",
                        "prompt": "Architecture logicielle",
                        "avatar": "💻",
                        "color": "#0284c7",
                    },
                ],
            },
        }

        with client.stream("POST", f"/api/conversations/{conv_id}/messages", json=payload) as response:
            assert response.status_code == 200
            response.read()
            events = response.text
            assert "Conseil Multi-Agents" in events
            assert "Synthèse du Conseil d'Experts" in events

        # Verify message persisted in DB
        with app.state.sessions() as db:
            from sqlalchemy import select
            messages = list(db.scalars(select(Message).where(Message.conversation_id == conv_id)))
            # 1 user message + 1 assistant message
            assert len(messages) == 2
            assistant_msg = next(m for m in messages if m.role == "assistant")
            assert "Synthèse du Conseil d'Experts" in assistant_msg.content
            assert "Maître Legrand" in assistant_msg.content

        # Send multi-agent message (Debate mode)
        debate_payload = {
            "content": "Débattons de l'opportunité de réécrire tout le backend en Rust",
            "multi_agent": True,
            "multi_agent_config": {
                "mode": "debate",
                "rounds": 1,
                "agents": [
                    {
                        "name": "Alexandre",
                        "role": "Architecte Logiciel",
                        "model": "openai/gpt-4o",
                        "prompt": "Architecture logicielle",
                        "avatar": "💻",
                        "color": "#0284c7",
                    },
                    {
                        "name": "Socrate",
                        "role": "Avocat du Diable",
                        "model": "anthropic/claude-3.5-sonnet",
                        "prompt": "Esprit critique",
                        "avatar": "🧠",
                        "color": "#7c3aed",
                    },
                ],
            },
        }

        with client.stream("POST", f"/api/conversations/{conv_id}/messages", json=debate_payload) as response:
            assert response.status_code == 200
            response.read()
            events = response.text
            assert "Table Ronde" in events

        # Send multi-agent message (Contradictory / Dialectic mode)
        dialectic_payload = {
            "content": "Faut-il interdire l'IA générative dans les universités ?",
            "multi_agent": True,
            "multi_agent_config": {
                "mode": "dialectic",
                "agents": [
                    {
                        "name": "Pr. Défenseur",
                        "role": "Le Défenseur (Thèse)",
                        "model": "anthropic/claude-3.5-sonnet",
                        "prompt": "Tu défends vigoureusement la thèse.",
                        "avatar": "🥊",
                        "color": "#16a34a",
                    },
                    {
                        "name": "Me. Opposant",
                        "role": "L'Opposant (Antithèse)",
                        "model": "openai/gpt-4o",
                        "prompt": "Tu attaques frontalement la thèse.",
                        "avatar": "⚔️",
                        "color": "#dc2626",
                    },
                    {
                        "name": "Dr. Arbitre",
                        "role": "L'Arbitre & 3e Voie",
                        "model": "google/gemini-2.0-flash-001",
                        "prompt": "Tu réfutes les deux biais et proposes une voie contradictoire.",
                        "avatar": "⚖️",
                        "color": "#7c3aed",
                    },
                ],
            },
        }

        with client.stream("POST", f"/api/conversations/{conv_id}/messages", json=dialectic_payload) as response:
            assert response.status_code == 200
            response.read()
            events = response.text
            assert "Débat Contradictoire" in events
            assert "Acte 1 · La Thèse" in events
            assert "Acte 2 · L'Antithèse" in events
            assert "Acte 3 · La Contradiction & 3e Voie" in events
