import pytest
from app.config import Settings
from app.models import Conversation, TopicMemory, TopicSpace, User, now
from app.topic_agent import build_topic_prompt_context, fallback_topic_analysis
try:
    from test_api import authenticated_client
except ImportError:
    from .test_api import authenticated_client


@pytest.fixture
def client(tmp_path):
    st = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    with authenticated_client(st) as value:
        yield value


def test_topic_crud(client):
    # 1. Create a Topic Space
    res = client.post(
        "/api/topics",
        json={
            "title": "Apprendre l'espagnol",
            "icon": "🇪🇸",
            "topic_type": "learning",
            "objective": "Niveau B1 d'ici juin",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["title"] == "Apprendre l'espagnol"
    assert data["icon"] == "🇪🇸"
    assert data["topic_type"] == "learning"
    assert data["objective"] == "Niveau B1 d'ici juin"
    topic_id = data["id"]

    # 2. List Topic Spaces
    res = client.get("/api/topics")
    assert res.status_code == 200
    topics = res.json()
    assert any(t["id"] == topic_id for t in topics)

    # 3. Get Topic Space details
    res = client.get(f"/api/topics/{topic_id}")
    assert res.status_code == 200
    details = res.json()
    assert details["id"] == topic_id
    assert "memories" in details
    assert "conversations" in details
    assert "events" in details

    # 4. Update Topic Space
    res = client.patch(
        f"/api/topics/{topic_id}",
        json={
            "objective": "Niveau B2 d'ici fin d'année",
            "current_resume_context": "Bases acquises, passé composé en cours.",
            "suggested_next_step": "Exercice sur l'imparfait.",
        },
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["objective"] == "Niveau B2 d'ici fin d'année"
    assert updated["current_resume_context"] == "Bases acquises, passé composé en cours."
    assert updated["suggested_next_step"] == "Exercice sur l'imparfait."


def test_topic_memories_and_events(client):
    # Create topic
    res = client.post(
        "/api/topics",
        json={"title": "Projet Bot Discord", "icon": "🤖", "topic_type": "project"},
    )
    assert res.status_code == 201
    topic_id = res.json()["id"]

    # Add memory
    res = client.post(
        f"/api/topics/{topic_id}/memories",
        json={
            "fact": "Architecture basée sur discord.py v2.0",
            "category": "decision",
            "status": "validated",
        },
    )
    assert res.status_code == 201
    mem = res.json()
    assert mem["fact"] == "Architecture basée sur discord.py v2.0"
    assert mem["status"] == "validated"
    mem_id = mem["id"]

    # Update memory
    res = client.patch(
        f"/api/topics/{topic_id}/memories/{mem_id}",
        json={"status": "needs_review", "fact": "Migration envisagée vers hikari"},
    )
    assert res.status_code == 200
    updated_mem = res.json()
    assert updated_mem["status"] == "needs_review"
    assert updated_mem["fact"] == "Migration envisagée vers hikari"

    # Add event
    res = client.post(
        f"/api/topics/{topic_id}/events",
        json={
            "event_type": "milestone",
            "title": "Setup du repository et CI/CD",
            "details": {"branch": "main"},
        },
    )
    assert res.status_code == 201
    event = res.json()
    assert event["title"] == "Setup du repository et CI/CD"

    # Add resource
    res = client.post(
        f"/api/topics/{topic_id}/resources",
        json={
            "title": "Documentation discord.py",
            "resource_type": "link",
            "url": "https://discordpy.readthedocs.io",
            "content": "Doc officielle pour les events et cogs",
        },
    )
    assert res.status_code == 201
    resource = res.json()
    assert resource["title"] == "Documentation discord.py"
    assert resource["resource_type"] == "link"
    res_id = resource["id"]

    # List resources
    res = client.get(f"/api/topics/{topic_id}/resources")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # Verify in topic details
    res = client.get(f"/api/topics/{topic_id}")
    assert res.status_code == 200
    details = res.json()
    assert len(details["memories"]) == 1
    assert len(details["events"]) == 1
    assert len(details["resources"]) == 1

    # Update resource
    res = client.patch(
        f"/api/topics/{topic_id}/resources/{res_id}",
        json={"title": "Doc discord.py v2"},
    )
    assert res.status_code == 200
    assert res.json()["title"] == "Doc discord.py v2"

    # Delete resource
    res = client.delete(f"/api/topics/{topic_id}/resources/{res_id}")
    assert res.status_code == 204

    # Delete memory
    res = client.delete(f"/api/topics/{topic_id}/memories/{mem_id}")
    assert res.status_code == 204


def test_topic_conversation_linking(client):
    # Create topic
    res = client.post(
        "/api/topics",
        json={"title": "Intelligence Artificielle", "icon": "🧠", "topic_type": "interest"},
    )
    assert res.status_code == 201
    topic_id = res.json()["id"]

    # Create conversation
    res = client.post(
        "/api/conversations",
        json={"title": "Discussion LLM reasoning", "topic_space_id": topic_id},
    )
    assert res.status_code == 201
    conv = res.json()
    assert conv["topic_space_id"] == topic_id
    conv_id = conv["id"]

    # Unlink conversation
    res = client.delete(f"/api/topics/{topic_id}/conversations/{conv_id}")
    assert res.status_code == 200
    details = res.json()
    assert details["conversations_count"] == 0

    # Link conversation back
    res = client.post(f"/api/topics/{topic_id}/conversations/{conv_id}")
    assert res.status_code == 200
    details = res.json()
    assert details["conversations_count"] == 1


def test_topic_agent_helpers():
    topic = TopicSpace(
        title="Espagnol débutant",
        icon="🇪🇸",
        topic_type="learning",
        objective="Apprendre les temps du passé",
        current_resume_context="SER vs ESTAR abordé.",
        suggested_next_step="Passer aux verbes irréguliers.",
    )
    memories = [
        TopicMemory(fact="Distingue ser et estar pour l'état civil", status="validated", is_archived=False),
        TopicMemory(fact="Confond encore estar pour les sentiments", status="needs_review", is_archived=False),
    ]

    prompt_ctx = build_topic_prompt_context(topic, memories)
    assert "ESPACE THÉMATIQUE ACTIF : 🇪🇸 Espagnol débutant" in prompt_ctx
    assert "SER vs ESTAR abordé." in prompt_ctx
    assert "[Validé] Distingue ser et estar" in prompt_ctx
    assert "[À renforcer / corriger] Confond encore" in prompt_ctx

    # Fallback analysis
    fallback = fallback_topic_analysis(topic, "J'ai eu 7/8 sur le test", "Bravo pour ton score !")
    assert "new_resume_context" in fallback
    assert len(fallback["events"]) == 1
    assert fallback["events"][0]["details"]["score"] == "7/8"
