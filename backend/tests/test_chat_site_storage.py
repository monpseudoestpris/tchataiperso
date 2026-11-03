"""Saved chat sites remain private, reusable and tied to a conversation snapshot."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text

from app.config import Settings
from app.models import ChatSite, Conversation, Message, User
from app.providers import ProviderError
from test_api import authenticated_client


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    with authenticated_client(settings) as value:
        yield value


def seed_chat(client):
    with client.app.state.sessions() as db:
        owner = db.scalar(select(User).where(User.username == "tester"))
        conv = Conversation(user_id=owner.id, title="Sujet", model="demo")
        db.add(conv)
        db.flush()
        message = Message(conversation_id=conv.id, role="assistant", content="Information initiale")
        db.add(message)
        db.commit()
        return conv.id, message.id


def test_snapshot_persists_and_is_reused_across_export_entry_points(client, monkeypatch):
    calls = []

    async def generate(settings, title, messages, **kwargs):
        assert kwargs["raise_on_failure"]
        calls.append(messages)
        return f"<html><body>Synthèse {len(calls)}</body></html>"

    monkeypatch.setattr("app.chat_site_store.generate_chat_site", generate)
    conv_id, msg_id = seed_chat(client)
    base = f"/api/conversations/{conv_id}"
    first = client.get(base + "/html")
    assert first.status_code == 200 and "Synthèse 1" in first.text
    assert client.get(base + "/html").text == first.text
    assert client.get(f"/api/messages/{msg_id}/html?scope=conversation").text == first.text
    assert len(calls) == 1
    sites = client.get(base + "/sites").json()
    assert len(sites) == 1 and "html_content" not in sites[0]
    saved_url = sites[0]["url"]
    assert client.get(saved_url).text == first.text
    assert len(calls) == 1
    downloaded = client.get(base + "/html?download=1")
    assert downloaded.text == first.text and "attachment" in downloaded.headers["content-disposition"]
    assert len(calls) == 1
    with client.app.state.sessions() as db:
        db.get(Message, msg_id).content = "Information mise à jour"
        db.commit()
    assert "Synthèse 2" in client.get(base + "/html").text
    assert len(calls) == 2 and len(client.get(base + "/sites").json()) == 2
    assert client.get(saved_url).text == first.text
    # The turn scope is distinct from the whole discussion snapshot.
    client.get(f"/api/messages/{msg_id}/html?scope=turn")
    assert len(calls) == 3
    assert client.get(base + "/sites").json()[0]["scope"] == "turn"


def test_failed_generation_is_not_saved_or_reused(client, monkeypatch):
    calls = []

    async def generate(settings, title, messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            raise ProviderError("La page générée est incomplète.")
        return "<html><body>Synthèse réussie</body></html>"

    monkeypatch.setattr("app.chat_site_store.generate_chat_site", generate)
    conv_id, _ = seed_chat(client)
    base = f"/api/conversations/{conv_id}"
    assert "incomplète" in client.get(base + "/html").text
    assert client.get(base + "/sites").json() == []
    assert "Synthèse réussie" in client.get(base + "/html").text
    assert len(calls) == 2 and len(client.get(base + "/sites").json()) == 1


def test_saved_sites_enforce_ownership_conversation_binding_and_cascade(client):
    conv_id, _ = seed_chat(client)
    with client.app.state.sessions() as db:
        other = User(username="other", password_hash="unused")
        db.add(other)
        db.flush()
        private = Conversation(user_id=other.id, title="Privé", model="demo")
        db.add(private)
        db.flush()
        site = ChatSite(conversation_id=private.id, input_hash="a" * 64, scope="conversation",
                        title="Privé", html_content="NE PAS EXPOSER")
        own = ChatSite(conversation_id=conv_id, input_hash="b" * 64, scope="conversation",
                       title="Sujet", html_content="Page privée")
        db.add_all([site, own])
        db.commit()
        private_id, site_id, own_id = private.id, site.id, own.id
    assert client.get(f"/api/conversations/{private_id}/sites").status_code == 404
    assert client.get(f"/api/conversations/{private_id}/sites/{site_id}").status_code == 404
    assert client.get(f"/api/conversations/{conv_id}/sites/{site_id}").status_code == 404
    assert client.delete(f"/api/conversations/{conv_id}").status_code == 204
    with client.app.state.sessions() as db:
        assert db.get(ChatSite, own_id) is None
    client.cookies.clear()
    assert client.get(f"/api/conversations/{private_id}/sites").status_code == 401


def test_additive_migration_is_idempotent_and_preserves_existing_chat():
    migration_path = Path(__file__).parents[1] / "migrations/versions/0018_add_chat_sites.py"
    spec = importlib.util.spec_from_file_location("chat_sites_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE conversations (id VARCHAR(36) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO conversations VALUES ('existing')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        assert "chat_sites" in inspect(connection).get_table_names()
        assert connection.execute(text("SELECT id FROM conversations")).scalar_one() == "existing"
        assert any(c["name"] == "uq_chat_sites_input" for c in inspect(connection).get_unique_constraints("chat_sites"))
    engine.dispose()
