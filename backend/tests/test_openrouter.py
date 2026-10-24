from unittest.mock import MagicMock, patch

from app.config import Settings
from app.openrouter import (
    _CACHE,
    fetch_openrouter_models,
    format_openrouter_model,
    is_chat_model,
)


def test_is_chat_model_filtering():
    # Regular chat models
    assert is_chat_model({
        "id": "openai/gpt-6-astra",
        "architecture": {
            "modality": "text+image+file->text",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
    })
    assert is_chat_model({
        "id": "deepseek/deepseek-v4.1-flash",
        "architecture": {
            "modality": "text->text",
            "output_modalities": ["text"],
        },
    })

    # Batch queues should be rejected
    assert not is_chat_model({"id": "openai/gpt-6-astra:batch"})
    assert not is_chat_model({"id": "google/gemini-3.8-flash:batch"})

    # Audio / Sound generation should be rejected
    assert not is_chat_model({
        "id": "google/lyria-3-pro-preview",
        "architecture": {
            "modality": "text+image->text+audio",
            "output_modalities": ["text", "audio"],
        },
    })
    assert not is_chat_model({
        "id": "openai/gpt-audio",
        "architecture": {
            "modality": "text+audio->text+audio",
            "output_modalities": ["text", "audio"],
        },
    })
    assert not is_chat_model({"id": "elevenlabs/speech-v2"})
    assert not is_chat_model({"id": "openai/whisper-large-v3"})

    # Embedding / rerank should be rejected
    assert not is_chat_model({"id": "baai/bge-m3-embedding"})
    assert not is_chat_model({"id": "cohere/rerank-v3"})


def test_format_openrouter_model():
    raw = {
        "id": "openai/gpt-6-astra",
        "name": "OpenAI: GPT-6 Astra",
        "description": "Next-gen flagship model",
        "context_length": 200000,
        "architecture": {
            "modality": "text+image->text",
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        "pricing": {
            "prompt": "0.00001",
            "completion": "0.00005",
            "input_cache_read": "0.000001",
        },
        "reasoning": {
            "mandatory": False,
            "supported_efforts": ["high", "low"],
        },
    }
    formatted = format_openrouter_model(raw)
    assert formatted["id"] == "openai/gpt-6-astra"
    assert formatted["name"] == "OpenAI: GPT-6 Astra"
    assert formatted["vision"] is True
    assert formatted["context_length"] == 200000
    assert formatted["prompt_price_1m"] == 10.0
    assert formatted["completion_price_1m"] == 50.0
    assert formatted["input_cache_read_price_1m"] == 1.0
    assert formatted["provider"] == "openai"
    assert formatted["reasoning"] is True


def test_fetch_openrouter_models_caching():
    _CACHE["timestamp"] = 0.0
    _CACHE["models"] = []

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "id": "openai/gpt-6-astra",
                "name": "GPT-6 Astra",
                "architecture": {"modality": "text+image->text", "output_modalities": ["text"]},
                "pricing": {"prompt": "0.000002", "completion": "0.00001"},
            },
            {
                "id": "google/lyria-3-pro",
                "architecture": {"modality": "text->audio", "output_modalities": ["audio"]},
            },
        ]
    }

    with patch("httpx.Client.get", return_value=mock_resp):
        models = fetch_openrouter_models(force_refresh=True)
        assert len(models) == 1
        assert models[0]["id"] == "openai/gpt-6-astra"

        # Second call should use cache without calling httpx.Client.get again
        with patch("httpx.Client.get") as second_get:
            cached = fetch_openrouter_models(force_refresh=False)
            assert cached == models
            second_get.assert_not_called()


def test_models_api_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=True,
        llm_models='[{"id":"demo-chat","name":"Demo Chat","vision":true}]',
        default_model="demo-chat",
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/models")
    assert response.status_code == 200
    payload = response.json()
    assert "models" in payload
    assert "default_model" in payload
    assert isinstance(payload["models"], list)
    assert any(m["id"] == "demo-chat" for m in payload["models"])
