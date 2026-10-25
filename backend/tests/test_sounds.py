import asyncio
from pathlib import Path

import httpx
import pytest
from app.config import Settings
from app.main import create_app
from app.models import GeneratedSound
from app import providers
from fastapi.testclient import TestClient
from sqlalchemy import select


def test_sound_effects_endpoints_and_lifecycle(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        eleven_labs_key="fake-elevenlabs-key",
        llm_api_key="fake-llm-key",
        demo_mode=False,
    )

    async def fake_improve(_settings, model, prompt, style_keywords=None, duration_hint=None, loop=False):
        assert prompt == "bruit de pas dans la forêt"
        if style_keywords:
            return f"Crisp footsteps on dry leaves, {style_keywords} mood"
        return "Soft footsteps sinking into autumn leaves with discreet wooden snaps"

    async def fake_translate(_settings, prompt):
        if "pas" in prompt:
            return "Crisp footsteps on dry leaves in the night"
        return "Crisp footsteps on dry leaves, mysterious, nocturnal mood"

    async def fake_generate(_settings, text, duration_seconds=None, prompt_influence=None, output_format="mp3_44100_128", loop=False):
        assert "footsteps" in text.lower() or "leaves" in text.lower()
        assert duration_seconds == 3.5
        assert prompt_influence == 0.4
        assert loop is True
        return b"\xff\xfb\x90\x00fake-mp3-audio-data", "audio/mpeg"

    monkeypatch.setattr(providers, "improve_sound_prompt", fake_improve)
    monkeypatch.setattr(providers, "translate_sound_prompt_to_english", fake_translate)
    monkeypatch.setattr(providers, "generate_sound_effect", fake_generate)

    # Use test client with authenticated admin
    from test_api import authenticated_client

    with authenticated_client(settings) as client:
        # Check system config exposure
        cfg = client.get("/api/config").json()
        assert cfg["features"]["sound_effects"] is True

        # Check formats endpoint
        formats_res = client.get("/api/sounds/formats")
        assert formats_res.status_code == 200
        formats = formats_res.json()
        assert any(f["id"] == "mp3_44100_128" for f in formats)

        # Initial list is empty
        list_res = client.get("/api/sounds")
        assert list_res.status_code == 200
        assert list_res.json() == []

        # Test translation endpoint
        trans_res = client.post(
            "/api/sounds/translate",
            json={"prompt": "bruit de pas dans la forêt"},
        )
        assert trans_res.status_code == 200
        assert trans_res.json()["prompt"] == "Crisp footsteps on dry leaves in the night"

        # Test prompt improvement
        improve_res = client.post(
            "/api/sounds/improve",
            json={
                "prompt": "bruit de pas dans la forêt",
                "style_keywords": "mystérieux, nocturne",
                "duration_hint": 3.5,
                "loop": True,
            },
        )
        assert improve_res.status_code == 200
        improved_text = improve_res.json()["prompt"]
        assert "footsteps" in improved_text.lower()

        # Test sound creation
        create_res = client.post(
            "/api/sounds",
            json={
                "prompt": improved_text,
                "duration_seconds": 3.5,
                "prompt_influence": 0.4,
                "output_format": "mp3_44100_128",
                "loop": True,
            },
        )
        assert create_res.status_code == 201
        sound = create_res.json()
        assert sound["id"]
        assert sound["duration_seconds"] == 3.5
        assert sound["prompt_influence"] == 0.4
        assert sound["loop"] is True
        assert sound["output_format"] == "mp3_44100_128"
        assert sound["mime_type"] == "audio/mpeg"
        assert sound["url"] == f"/api/sounds/{sound['id']}/file"

        # Verify listed
        list_res2 = client.get("/api/sounds")
        assert len(list_res2.json()) == 1
        assert list_res2.json()[0]["id"] == sound["id"]

        # Stream / download audio file
        file_res = client.get(sound["url"])
        assert file_res.status_code == 200
        assert file_res.content == b"\xff\xfb\x90\x00fake-mp3-audio-data"
        assert file_res.headers["content-type"] == "audio/mpeg"
        assert "attachment" not in file_res.headers.get("content-disposition", "")

        dl_res = client.get(sound["download_url"])
        assert dl_res.status_code == 200
        assert "attachment" in dl_res.headers.get("content-disposition", "")

        # Delete sound
        del_res = client.delete(f"/api/sounds/{sound['id']}")
        assert del_res.status_code == 204

        # Verify deleted
        assert client.get("/api/sounds").json() == []
        assert client.get(sound["url"]).status_code == 404


def test_sound_creation_requires_eleven_labs_key(tmp_path):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        eleven_labs_key="",
        demo_mode=False,
    )
    from test_api import authenticated_client

    with authenticated_client(settings) as client:
        cfg = client.get("/api/config").json()
        assert cfg["features"]["sound_effects"] is False

        res = client.post(
            "/api/sounds",
            json={"prompt": "Explosion de météore", "duration_seconds": 2.0},
        )
        assert res.status_code == 503
        assert "ELEVEN_LABS_KEY" in res.json()["detail"]


@pytest.mark.asyncio
async def test_providers_generate_sound_effect_success(monkeypatch):
    settings = Settings(
        _env_file=None,
        eleven_labs_key="test-key",
        demo_mode=False,
    )

    class MockTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/sound-generation"
            assert request.url.params["output_format"] == "mp3_44100_128"
            assert request.headers["xi-api-key"] == "test-key"
            return httpx.Response(200, content=b"audio-bytes-ok", headers={"content-type": "audio/mpeg"})

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_async_client(transport=MockTransport()))

    content, mime = await providers.generate_sound_effect(
        settings,
        "laser zap",
        duration_seconds=2.0,
        prompt_influence=0.5,
        output_format="mp3_44100_128",
        loop=False,
    )
    assert content == b"audio-bytes-ok"
    assert mime == "audio/mpeg"
