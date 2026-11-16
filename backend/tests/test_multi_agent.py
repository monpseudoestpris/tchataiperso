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


def test_multi_agent_uses_selected_model(tmp_path):
    from app.multi_agent import resolve_model

    database_url = f"sqlite:///{tmp_path / 'multi_selected_model.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]
    selected_model = next(
        (m["id"] for m in settings.models if m["id"] != settings.default_model),
        settings.default_model,
    )

    # resolve_model falls back to fallback_model (selected_model) when target_model is unknown
    assert resolve_model(settings, "nonexistent/model-xyz", fallback_model=selected_model) == selected_model

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="seluser",
            password_hash=hash_password("correct horse battery"),
            is_admin=True,
            active=True,
        )
        db.add(user)
        db.commit()
        conv = Conversation(title="Test Selected Model", user_id=user.id, model=settings.default_model)
        db.add(conv)
        db.commit()
        conv_id = conv.id

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "seluser", "password": "correct horse battery"})
        assert login_res.status_code == 200

        payload = {
            "content": "Faut-il migrer vers PostgreSQL ?",
            "model": selected_model,
            "multi_agent": True,
            "multi_agent_config": {
                "mode": "synthesis",
                "use_selected_model": True,
                "agents": [
                    {
                        "name": "Expert A",
                        "role": "DBA",
                        "model": "anthropic/claude-3.5-sonnet",
                        "prompt": "Analyse BDD",
                        "avatar": "🗄️",
                        "color": "#0284c7",
                    },
                    {
                        "name": "Expert B",
                        "role": "Ops",
                        "model": "openai/gpt-4o",
                        "prompt": "Analyse Ops",
                        "avatar": "⚙️",
                        "color": "#059669",
                    },
                ],
            },
        }

        with client.stream("POST", f"/api/conversations/{conv_id}/messages", json=payload) as response:
            assert response.status_code == 200
            response.read()
            events = response.text
            assert selected_model in events
            assert "anthropic/claude-3.5-sonnet" not in events
            assert "openai/gpt-4o" not in events


def test_multi_agent_receives_mid_chat_history(tmp_path, monkeypatch):
    from app.multi_agent import _format_conversation_context

    # 1. Unit test for _format_conversation_context with summary + prior turns + attachments
    ctx = _format_conversation_context(
        recent_history=[
            {
                "role": "user",
                "content": "Voici le cahier des charges initial.",
                "attachments": [{"filename": "cdc.pdf", "extracted_text": "Budget max 50k EUR"}],
            },
            {"role": "assistant", "content": "Bien noté, budget de 50k EUR."},
        ],
        conversation_summary="L'utilisateur souhaite lancer une app mobile B2B.",
    )
    assert "Résumé des échanges antérieurs" in ctx
    assert "app mobile B2B" in ctx
    assert "cdc.pdf" in ctx
    assert "Budget max 50k EUR" in ctx
    assert "Bien noté, budget de 50k EUR." in ctx

    # 2. Integration test: switching from normal mode to Conseil IA mid-conversation passes full prior history & summary
    database_url = f"sqlite:///{tmp_path / 'multi_history.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="histuser",
            password_hash=hash_password("correct horse battery"),
            is_admin=True,
            active=True,
        )
        db.add(user)
        db.commit()
        conv = Conversation(
            title="Mid-chat Conseil",
            user_id=user.id,
            model=settings.default_model,
            summary="Résumé initial : projet de refonte ERP.",
        )
        db.add(conv)
        db.commit()
        for idx in range(6):
            db.add(Message(conversation_id=conv.id, role="user", content=f"Tour utilisateur #{idx + 1}"))
            db.add(Message(conversation_id=conv.id, role="assistant", content=f"Réponse assistant #{idx + 1}"))
        db.commit()
        conv_id = conv.id

    captured: dict[str, object] = {}

    async def fake_synthesis(**kwargs):
        captured["recent_history"] = kwargs.get("recent_history")
        captured["conversation_summary"] = kwargs.get("conversation_summary")
        yield {"type": "delta", "text": "OK"}
        yield {"type": "done", "content": "OK"}

    monkeypatch.setattr("app.routers.messages.execute_multi_agent_synthesis", fake_synthesis)

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "histuser", "password": "correct horse battery"})
        assert login_res.status_code == 200

        payload = {
            "content": "Que recommande le conseil suite à nos échanges ?",
            "multi_agent": True,
            "multi_agent_config": {
                "mode": "synthesis",
                "use_selected_model": True,
                "agents": [
                    {"name": "Expert A", "role": "Tech", "model": settings.default_model, "prompt": "Tech"},
                    {"name": "Expert B", "role": "Biz", "model": settings.default_model, "prompt": "Biz"},
                ],
            },
        }
        with client.stream("POST", f"/api/conversations/{conv_id}/messages", json=payload) as response:
            assert response.status_code == 200
            response.read()

    assert captured["conversation_summary"] == "Résumé initial : projet de refonte ERP."
    prior = captured["recent_history"]
    assert isinstance(prior, list)
    assert len(prior) == 12
    assert prior[0]["content"] == "Tour utilisateur #1"
    assert prior[-1]["content"] == "Réponse assistant #6"


def test_agent_personas_panel_and_categories(tmp_path):
    # 1. Verify built-in categories include scientists, politicians, and creatives
    categories = {t.get("category") for t in DEFAULT_AGENT_TEMPLATES}
    assert {"science", "politique", "créatif"}.issubset(categories)
    names = [t["name"] for t in DEFAULT_AGENT_TEMPLATES]
    assert any("Marie Curie" in n for n in names)
    assert any("Richard Feynman" in n for n in names)
    assert any("Simone Veil" in n for n in names)
    assert any("Nelson Mandela" in n for n in names)
    assert any("Salvador Dalí" in n for n in names)
    assert any("Hayao Miyazaki" in n for n in names)

    # 2. CRUD API for saving/listing/deleting individual personas
    database_url = f"sqlite:///{tmp_path / 'personas_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="personauser",
            password_hash=hash_password("correct horse battery"),
            is_admin=True,
            active=True,
        )
        db.add(user)
        db.commit()

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "personauser", "password": "correct horse battery"})
        assert login_res.status_code == 200

        create_res = client.post(
            "/api/agent-teams/personas",
            json={
                "name": "Isaac Newton",
                "role": "Physicien & Mathématicien",
                "category": "science",
                "avatar": "🍎",
                "color": "#2563eb",
                "prompt": "Tu analyses par les lois du mouvement et du calcul infinitésimal.",
                "model": settings.default_model,
            },
        )
        assert create_res.status_code == 201
        created = create_res.json()
        assert created["name"] == "Isaac Newton"
        assert created["category"] == "science"

        list_res = client.get("/api/agent-teams")
        assert list_res.status_code == 200
        personas = list_res.json()["personas"]
        assert len(personas) == 1
        assert personas[0]["id"] == created["id"]

        del_res = client.delete(f"/api/agent-teams/personas/{created['id']}")
        assert del_res.status_code == 204

        list_after = client.get("/api/agent-teams").json()["personas"]
        assert list_after == []
