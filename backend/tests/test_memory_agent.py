import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.memory_agent import (
    fallback_memory_analysis,
    process_memory_turn,
)
from app.models import Memory, User


def test_fallback_explicit_memory_add():
    existing = []
    # Explicit "note en mémoire que..."
    res1 = fallback_memory_analysis("Note en mémoire que j'adore le café noir", existing)
    assert len(res1["add"]) == 1
    assert "café noir" in res1["add"][0].lower()

    # Explicit "retiens dans ma mémoire : ..."
    res2 = fallback_memory_analysis("Retiens dans ma mémoire : je vis à Bordeaux", existing)
    assert len(res2["add"]) == 1
    assert "bordeaux" in res2["add"][0].lower()

    # Explicit "souviens-toi que..."
    res3 = fallback_memory_analysis("Souviens-toi que je développe en Rust", existing)
    assert len(res3["add"]) == 1
    assert "rust" in res3["add"][0].lower()


def test_fallback_explicit_memory_forget():
    existing = [
        {"id": "mem-1", "content": "Vit à Lyon"},
        {"id": "mem-2", "content": "Aime le ski alpin"},
    ]
    res = fallback_memory_analysis("Oublie que j'aime le ski alpin", existing)
    assert "mem-2" in res["delete_ids"]
    assert len(res["add"]) == 0


def test_fallback_deduplication():
    existing = [
        {"id": "mem-1", "content": "Vit à Bordeaux"},
    ]
    # Adding the exact same fact should be ignored
    res = fallback_memory_analysis("Note en mémoire que je vis à Bordeaux", existing)
    assert len(res["add"]) == 0


def test_fallback_autonomous_memory_toggle():
    existing = []
    # With auto_memory_enabled=True: captures identity/profile facts
    res_enabled = fallback_memory_analysis("Je m'appelle Thomas et je suis végétarien", existing, auto_memory_enabled=True)
    assert any("thomas" in item.lower() for item in res_enabled["add"])
    assert any("végétarien" in item.lower() for item in res_enabled["add"])

    # With auto_memory_enabled=False: does not capture implicit facts
    res_disabled = fallback_memory_analysis("Je m'appelle Thomas et je suis végétarien", existing, auto_memory_enabled=False)
    assert len(res_disabled["add"]) == 0


@pytest.mark.asyncio
async def test_process_memory_turn_db_persistence(tmp_path):
    from app.config import Settings
    from app.auth import hash_password
    from app.main import create_app
    from app.models import Base

    database_url = f"sqlite:///{tmp_path / 'memory_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    sessions: sessionmaker = app.state.sessions

    Base.metadata.create_all(app.state.engine)
    with sessions() as db:
        user = User(
            username="memuser",
            password_hash=hash_password("adminpassword123"),
            is_admin=True,
            active=True,
            auto_memory_enabled=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    # 1. Process explicit addition
    result = await process_memory_turn(
        settings=settings,
        sessions=sessions,
        user_id=user_id,
        user_text="Note en mémoire que mon chien s'appelle Milo",
        assistant_text="C'est bien noté dans votre mémoire !",
        auto_memory_enabled=True,
    )

    assert len(result["new_memories"]) == 1
    assert "Milo" in result["new_memories"][0]
    assert any("Milo" in m["content"] for m in result["all_memories"])

    # Verify in DB directly
    with sessions() as db:
        saved = list(db.scalars(select(Memory).where(Memory.user_id == user_id)))
        assert any("Milo" in s.content for s in saved)

    # 2. Process explicit deletion
    result_del = await process_memory_turn(
        settings=settings,
        sessions=sessions,
        user_id=user_id,
        user_text="Oublie que mon chien s'appelle Milo",
        assistant_text="J'ai oublié cette information.",
        auto_memory_enabled=True,
    )
    assert len(result_del["deleted_memories"]) >= 1

    # Verify deleted in DB
    with sessions() as db:
        saved_after = list(db.scalars(select(Memory).where(Memory.user_id == user_id)))
        assert not any("Milo" in s.content for s in saved_after)


def test_settings_auto_memory_toggle(tmp_path):
    from starlette.testclient import TestClient
    from app.config import Settings
    from app.auth import hash_password
    from app.main import create_app
    from app.models import Base

    database_url = f"sqlite:///{tmp_path / 'settings_memory_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="toggleuser",
            password_hash=hash_password("adminpassword123"),
            is_admin=True,
            active=True,
            auto_memory_enabled=True,
        )
        db.add(user)
        db.commit()

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "toggleuser", "password": "adminpassword123"})
        assert login_res.status_code == 200

        # GET settings should include auto_memory_enabled: True
        res = client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert "auto_memory_enabled" in data
        assert data["auto_memory_enabled"] is True

        # PATCH settings to disable auto_memory
        patch_res = client.patch("/api/settings", json={"auto_memory_enabled": False})
        assert patch_res.status_code == 200
        assert patch_res.json()["auto_memory_enabled"] is False

        # Verify persistence
        res_after = client.get("/api/settings")
        assert res_after.json()["auto_memory_enabled"] is False

        # Restore
        client.patch("/api/settings", json={"auto_memory_enabled": True})
        assert client.get("/api/settings").json()["auto_memory_enabled"] is True


def test_stream_message_triggers_memory_retention(tmp_path):
    import json
    from starlette.testclient import TestClient
    from app.config import Settings
    from app.auth import hash_password
    from app.main import create_app
    from app.models import Base

    database_url = f"sqlite:///{tmp_path / 'stream_memory_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="chatuser",
            password_hash=hash_password("adminpassword123"),
            is_admin=True,
            active=True,
            auto_memory_enabled=True,
        )
        db.add(user)
        db.commit()

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "chatuser", "password": "adminpassword123"})
        assert login_res.status_code == 200

        # Create conversation
        conv_res = client.post("/api/conversations", json={})
        assert conv_res.status_code == 201
        conv_id = conv_res.json()["id"]

        # Send a message with explicit memory instruction
        msg_res = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={"content": "Note en mémoire que j'habite à Strasbourg"},
        )
        assert msg_res.status_code == 200

        # Parse SSE events
        raw_events = []
        for block in msg_res.text.strip().split("\n\n"):
            lines = [l for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            name = next((line[7:].strip() for line in lines if line.startswith("event: ")), None)
            data_line = next((line[6:].strip() for line in lines if line.startswith("data: ")), None)
            if name and data_line:
                raw_events.append((name, json.loads(data_line)))

        done_event = next((data for name, data in raw_events if name == "done"), None)
        assert done_event is not None
        assert "new_memories" in done_event
        assert len(done_event["new_memories"]) >= 1
        assert any("Strasbourg" in m for m in done_event["new_memories"])

        # Check memories endpoint directly
        mem_res = client.get("/api/memories")
        assert mem_res.status_code == 200
        memories = mem_res.json()
        assert len(memories) >= 1
        assert any("Strasbourg" in m["content"] for m in memories)
