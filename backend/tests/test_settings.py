import pytest
from starlette.testclient import TestClient

from app.config import Settings
from app.base_prompt import BASE_USER_PROMPT
from app.context import SYSTEM_PROMPT, build_context
from app.main import create_app
from app.models import User
from app.providers import prepare_messages_for_caching
from app.serializers import user_json


def test_prepare_messages_for_caching_injects_ephemeral_cache_control():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
    ]

    # OpenRouter endpoint
    cached_or = prepare_messages_for_caching(
        messages,
        model="openai/gpt-4o",
        base_url="https://openrouter.ai/api/v1",
        enable_cache=True,
    )
    assert cached_or[0]["role"] == "system"
    assert isinstance(cached_or[0]["content"], list)
    assert cached_or[0]["content"][0]["type"] == "text"
    assert cached_or[0]["content"][0]["text"] == "You are a helpful assistant."
    assert cached_or[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert cached_or[1]["content"] == "Hello!"

    # Claude direct model
    cached_claude = prepare_messages_for_caching(
        messages,
        model="anthropic/claude-3.5-sonnet",
        base_url="https://api.anthropic.com/v1",
        enable_cache=True,
    )
    assert cached_claude[0]["content"][0]["cache_control"] == {"type": "ephemeral"}

    # Disabled cache
    uncached = prepare_messages_for_caching(
        messages,
        model="anthropic/claude-3.5-sonnet",
        base_url="https://openrouter.ai/api/v1",
        enable_cache=False,
    )
    assert isinstance(uncached[0]["content"], str)
    assert "cache_control" not in uncached[0]


def test_prepare_messages_for_caching_handles_multi_turn_history():
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Question 1"},
        {"role": "assistant", "content": "Answer 1"},
        {"role": "user", "content": "Question 2"},
    ]

    cached = prepare_messages_for_caching(
        messages,
        model="anthropic/claude-3.5-sonnet",
        base_url="https://openrouter.ai/api/v1",
        enable_cache=True,
    )
    # Breakpoint 1 on system prompt
    assert cached[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # Breakpoint 2 on penultimate turn (Answer 1)
    assert cached[2]["role"] == "assistant"
    assert isinstance(cached[2]["content"], list)
    assert cached[2]["content"][0]["text"] == "Answer 1"
    assert cached[2]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # Latest turn remains uncached
    assert cached[3]["role"] == "user"
    assert cached[3]["content"] == "Question 2"


def test_build_context_with_user_system_prompt():
    settings = Settings(_env_file=None, max_context_chars=20000)
    custom_prompt = "Sois toujours direct, réponds en minuscules."
    context = build_context(
        settings,
        summary="",
        memories=[],
        messages=[{"role": "user", "content": "Bonjour"}],
        sources=[],
        vision=False,
        user_system_prompt=custom_prompt,
    )
    assert context[0]["role"] == "system"
    assert custom_prompt in context[0]["content"]
    assert SYSTEM_PROMPT in context[0]["content"]

    # When passing BASE_USER_PROMPT as resolved by messages router / serializers
    base_context = build_context(
        settings,
        summary="",
        memories=[],
        messages=[{"role": "user", "content": "Bonjour"}],
        sources=[],
        vision=False,
        user_system_prompt=BASE_USER_PROMPT,
    )
    assert BASE_USER_PROMPT in base_context[0]["content"]
    assert "chaleureux, curieux et naturel" in base_context[0]["content"]


def test_user_json_serialization_includes_settings():
    user = User(
        username="alice",
        password_hash="hash",
        system_prompt="Mon prompt custom",
        prompt_cache_enabled=True,
    )
    serialized = user_json(user)
    assert serialized["username"] == "alice"
    assert serialized["system_prompt"] == "Mon prompt custom"
    assert serialized["prompt_cache_enabled"] is True


def test_settings_api_get_and_patch(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'settings_test.db'}"
    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=database_url, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]

    from app.auth import hash_password
    from app.models import Base

    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        user = User(
            username="testadmin",
            password_hash=hash_password("adminpassword123"),
            is_admin=True,
            active=True,
            system_prompt="Initial prompt",
            prompt_cache_enabled=True,
        )
        db.add(user)
        db.commit()

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "testadmin", "password": "adminpassword123"})
        assert login_res.status_code == 200

        # GET /api/settings
        res = client.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["system_prompt"] == "Initial prompt"
        assert data["prompt_cache_enabled"] is True
        assert len(data["prompt_presets"]) >= 4

        # PATCH /api/settings
        patch_res = client.patch(
            "/api/settings",
            json={
                "system_prompt": "Nouveau prompt général : réponds en français et concis.",
                "prompt_cache_enabled": False,
            },
        )
        assert patch_res.status_code == 200
        updated = patch_res.json()
        assert updated["system_prompt"] == "Nouveau prompt général : réponds en français et concis."
        assert updated["prompt_cache_enabled"] is False

        # Verify GET reflects update
        verify_res = client.get("/api/settings")
        assert verify_res.json()["system_prompt"] == "Nouveau prompt général : réponds en français et concis."
        assert verify_res.json()["prompt_cache_enabled"] is False
