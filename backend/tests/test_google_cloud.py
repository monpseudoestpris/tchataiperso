import asyncio
import base64
import datetime
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import (
    finance_dossier,
    finance_experts,
    google_cloud,
    hermes_agent,
    providers,
    topic_agent,
)
from app.config import Settings
from app.models import Base, TopicSpace, User
from tests.test_api import authenticated_client

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _DummyCredentials:
    def __init__(self, token: str = "ya29.test-token", expiry_delta_seconds: int = 3600):
        self.token = token
        self.valid = bool(token)
        self.expiry = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=expiry_delta_seconds)
        )
        self.refresh_calls = 0

    def refresh(self, request):
        self.refresh_calls += 1
        self.token = f"ya29.refreshed-{self.refresh_calls}"
        self.valid = True
        self.expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=3600)


def _mock_async_client_factory(handler, *, stream_handler=None):
    """Build an httpx.AsyncClient drop-in that captures kwargs and dispatches to handlers."""
    calls: list[dict] = []

    class _MockResponseStream:
        def __init__(self, resp: httpx.Response, lines: list[str]):
            self._resp = resp
            self._lines = lines

        async def __aenter__(self):
            return self._resp

        async def __aexit__(self, *args):
            return False

    class _MockAsyncClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            calls.append({"method": "POST", "url": str(url), "headers": dict(headers or {}), "json": json})
            return handler(str(url), dict(headers or {}), json)

        async def get(self, url, headers=None, params=None, **kwargs):
            calls.append({"method": "GET", "url": str(url), "headers": dict(headers or {}), "params": params})
            return handler(str(url), dict(headers or {}), params)

        def stream(self, method, url, headers=None, json=None, **kwargs):
            calls.append({"method": f"STREAM_{method}", "url": str(url), "headers": dict(headers or {}), "json": json})
            if stream_handler is not None:
                resp = stream_handler(str(url), dict(headers or {}), json)
            else:
                resp = handler(str(url), dict(headers or {}), json)
            return _MockResponseStream(resp, [])

    return _MockAsyncClient, calls


def _sse_response(status_code: int, events: list[str], url: str = "https://example.test") -> httpx.Response:
    body = "".join(f"data: {item}\n\n" for item in events).encode("utf-8")
    return httpx.Response(status_code, content=body, request=httpx.Request("POST", url))


# 1. Detection & Normalization


def test_is_google_model_and_normalize_model_id():
    assert google_cloud.is_google_model("google/gemini-2.5-flash") is True
    assert google_cloud.is_google_model("gemini-2.5-pro") is True
    assert google_cloud.is_google_model("imagen-3.0-generate-002") is True
    assert google_cloud.is_google_model("gemma-3-27b-it") is True
    assert google_cloud.is_google_model("publishers/google/models/gemini-2.5-flash") is True
    assert google_cloud.is_google_model("models/gemini-2.5-flash") is True

    assert google_cloud.is_google_model("openai/gpt-4o-mini") is False
    assert google_cloud.is_google_model("anthropic/claude-3.5-sonnet") is False
    assert google_cloud.is_google_model("ideogram-4-5") is False
    assert google_cloud.is_google_model("") is False
    assert google_cloud.is_google_model(None) is False

    settings = Settings(
        _env_file=None,
        google_cloud_model_map='{"google/gemini-4-hydrogen": "gemini-2.5-pro", "custom-alias": "gemini-2.5-flash"}',
    )
    assert google_cloud.normalize_google_model_id("google/gemini-2.5-flash:free", for_vertex_openapi=True) == "google/gemini-2.5-flash"
    assert google_cloud.normalize_google_model_id("google/gemini-2.5-flash:thinking", for_vertex_openapi=False) == "gemini-2.5-flash"
    assert google_cloud.normalize_google_model_id("google/gemini-4-hydrogen", settings=settings, for_vertex_openapi=True) == "google/gemini-2.5-pro"
    assert google_cloud.normalize_google_model_id("CUSTOM-ALIAS", settings=settings, for_vertex_openapi=False) == "gemini-2.5-flash"

    for bad in ("", "../etc/passwd", "google/../../secret", "gemini/sub/model", "bad model!"):
        with pytest.raises(google_cloud.ProviderError):
            google_cloud.normalize_google_model_id(bad)


# 2. Settings Validation, Catalogs & Live Reload


def test_settings_validation_catalogs_and_live_reload(tmp_path, monkeypatch):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, google_cloud_mode="invalid_mode")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, google_cloud_project="BAD_PROJECT!")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, google_cloud_location="invalid/region")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, google_cloud_model_map="{not-json")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, google_application_credentials="/tmp/sa.json\nBAD")

    s = Settings(
        _env_file=None,
        demo_mode=False,
        llm_api_key=SecretStr(""),
        google_cloud_mode="auto",
        google_cloud_project="my-gcp-project",
    )
    assert s.active_google_cloud_mode == "vertex_oauth"
    assert s.google_cloud_enabled is True
    assert s.has_llm_for_model("google/gemini-2.5-flash") is True
    assert s.has_llm_for_model("openai/gpt-4o-mini") is False

    models = s.get_models()
    model_ids = {m["id"] for m in models}
    assert "google/gemini-2.5-flash" in model_ids
    assert "google/gemini-4-hydrogen" in model_ids

    img_models = s.get_image_models()
    google_imgs = [m for m in img_models if m["id"].startswith("google/")]
    assert len(google_imgs) >= 1
    assert all(m.get("routed_via") == "google_cloud" for m in google_imgs)

    params = s.get_model_supported_parameters("google/gemini-2.5-pro")
    assert "reasoning_effort" in params

    # Live reload using temporary .env file in tmp_path (never real .env)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VERTEX_PROJECT_ID=live-gcp-proj\n"
        "VERTEX_LOCATION=europe-west1\n"
        "GOOGLE_CLOUD_API_KEY=vertex-live-secret\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    watched = Settings()
    assert watched.google_cloud_project == "live-gcp-proj"
    assert watched.google_cloud_location == "europe-west1"
    assert watched.vertex_api_key.get_secret_value() == "vertex-live-secret"

    # Temporarily invalid edit in .env is safely ignored during live reload
    env_file.write_text(
        "GOOGLE_CLOUD_PROJECT=BAD_INVALID\n"
        "GOOGLE_CLOUD_LOCATION=us-central1\n",
        encoding="utf-8",
    )
    watched.refresh_from_env_file(force=True)
    assert watched.google_cloud_project == "live-gcp-proj"
    assert watched.google_cloud_location == "us-central1"


# 3. Vertex OAuth2 (Global & Regional), Caching, Sanitization & SSE Thoughts


def test_vertex_oauth_endpoints_cache_sanitization_and_streaming(tmp_path, monkeypatch):
    # Test ADC / near-expiry refresh + cache reuse
    creds_adc = _DummyCredentials(token="ya29.initial", expiry_delta_seconds=3600)
    default_calls = 0

    def fake_default(scopes=None):
        nonlocal default_calls
        default_calls += 1
        assert scopes == [google_cloud._CLOUD_SCOPE]
        return creds_adc, "adc-detected-project"

    monkeypatch.setattr(google_cloud.google.auth, "default", fake_default)
    s_adc = Settings(_env_file=None, google_cloud_mode="vertex_oauth")
    tok1, proj1 = asyncio.run(google_cloud.get_google_cloud_access_token(s_adc))
    tok2, proj2 = asyncio.run(google_cloud.get_google_cloud_access_token(s_adc))
    assert tok1 == "ya29.initial" and tok2 == "ya29.initial"
    assert proj1 == "adc-detected-project" and proj2 == "adc-detected-project"
    assert default_calls == 1 and creds_adc.refresh_calls == 0

    # Near-expiry triggers refresh cleanly
    creds_adc.expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=120)
    tok3, _ = asyncio.run(google_cloud.get_google_cloud_access_token(s_adc))
    assert tok3 == "ya29.refreshed-1"
    assert creds_adc.refresh_calls == 1

    # Service account file path
    sa_file = tmp_path / "sa.json"
    sa_file.write_text('{"type": "service_account"}', encoding="utf-8")
    creds_sa = _DummyCredentials(token="ya29.sa-token", expiry_delta_seconds=3600)
    monkeypatch.setattr(
        google_cloud.google.auth,
        "load_credentials_from_file",
        lambda path, scopes=None: (creds_sa, "sa-project-123"),
    )
    s_sa = Settings(
        _env_file=None,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="explicit-proj-1",
        google_cloud_location="europe-west1",
        google_application_credentials=str(sa_file),
    )

    def handler(url, headers, body):
        assert url == (
            "https://europe-west1-aiplatform.googleapis.com/v1/projects/"
            "explicit-proj-1/locations/europe-west1/endpoints/openapi/chat/completions"
        )
        assert headers["Authorization"] == "Bearer ya29.sa-token"
        assert "HTTP-Referer" not in headers
        assert "X-Title" not in headers
        assert body["model"] == "google/gemini-2.5-flash"
        assert body["reasoning_effort"] == "medium"
        for field in google_cloud._OPENROUTER_ONLY_FIELDS:
            assert field not in body
        sys_content = body["messages"][0]["content"]
        assert isinstance(sys_content, list) and "cache_control" not in sys_content[0]
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-vertex",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK Vertex"}, "finish_reason": "stop"}],
            },
            request=httpx.Request("POST", url),
        )

    mock_cls, recorded = _mock_async_client_factory(handler)
    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": "Sys", "cache_control": {"type": "ephemeral"}}]},
            {"role": "user", "content": "Bonjour"},
        ],
        "reasoning": {"effort": "medium"},
        "provider": {"sort": "price"},
        "transforms": ["middle-out"],
        "route": "fallback",
        "models": ["a", "b"],
        "include_reasoning": True,
        "min_p": 0.1,
        "top_a": 0.5,
        "top_k": 40,
        "repetition_penalty": 1.1,
        "logit_bias": {"1": 2},
        "verbosity": "low",
    }
    resp = asyncio.run(
        google_cloud.post_chat_completion(
            s_sa,
            payload,
            client=mock_cls(),
            extra_headers={"HTTP-Referer": "https://clair.local", "X-Title": "cLAIr"},
        )
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "OK Vertex"
    assert len(recorded) == 1

    # Global endpoint + SSE streaming with extra_content.google.thought via providers.stream_chat_events
    s_global = Settings(
        _env_file=None,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="global-proj-1",
        google_cloud_location="global",
        google_application_credentials=str(sa_file),
    )

    def stream_handler(url, headers, body):
        assert url == "https://aiplatform.googleapis.com/v1/projects/global-proj-1/locations/global/endpoints/openapi/chat/completions"
        assert body["model"] == "google/gemini-2.5-pro"
        # gemini-2.5-pro ignores reasoning_effort="none"
        assert "reasoning_effort" not in body
        return _sse_response(
            200,
            [
                json.dumps({"choices": [{"delta": {"extra_content": {"google": {"thought": "Réflexion Vertex..."}}, "content": ""}}]}),
                json.dumps({"choices": [{"delta": {"content": "Réponse finale"}, "finish_reason": "stop"}]}),
                "[DONE]",
            ],
            url=url,
        )

    stream_mock_cls, _ = _mock_async_client_factory(handler, stream_handler=stream_handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", stream_mock_cls)

    async def collect_events():
        out = []
        async for ev in providers.stream_chat_events(
            s_global,
            [{"role": "user", "content": "Analyse"}],
            "google/gemini-2.5-pro",
            sampling_params={"reasoning_effort": "none"},
        ):
            out.append(ev)
        return out

    ev_list = asyncio.run(collect_events())
    thoughts = "".join(e["text"] for e in ev_list if e["type"] == "thought")
    deltas = "".join(e["text"] for e in ev_list if e["type"] == "delta")
    assert "Réflexion Vertex..." in thoughts
    assert deltas == "Réponse finale"


# 4. Vertex API Key Mode (Native Translation + SSE)


def test_vertex_api_key_native_translation_and_streaming(monkeypatch):
    s = Settings(
        _env_file=None,
        google_cloud_mode="vertex_api_key",
        vertex_api_key=SecretStr("AIzaVertexTestKey123"),
    )

    def handler(url, headers, body):
        assert url == "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash:generateContent"
        assert headers["x-goog-api-key"] == "AIzaVertexTestKey123"
        assert "Authorization" not in headers
        assert body["systemInstruction"] == {"parts": [{"text": "Sois concis."}]}
        assert body["generationConfig"]["topK"] == 32
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "$schema" not in body["generationConfig"]["responseSchema"]
        assert "additionalProperties" not in body["generationConfig"]["responseSchema"]
        assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 8192}
        # Vision inlineData + tool call history translated cleanly
        user_parts = body["contents"][0]["parts"]
        assert user_parts[0] == {"text": "Décris"}
        assert user_parts[1]["inlineData"]["mimeType"] == "image/png"
        assert body["tools"][0]["functionDeclarations"][0]["name"] == "lookup_stock"
        return httpx.Response(
            200,
            json={
                "responseId": "resp-native-1",
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Réflexion interne", "thought": True},
                                {"functionCall": {"name": "lookup_stock", "args": {"ticker": "AAPL"}}},
                                {"text": '{"ok": true}'},
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8, "totalTokenCount": 20},
            },
            request=httpx.Request("POST", url),
        )

    img_b64 = base64.b64encode(_TINY_PNG).decode("ascii")
    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": "Sois concis."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Décris"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            },
        ],
        "top_k": 32,
        "reasoning_effort": "medium",
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "res",
                "schema": {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object", "additionalProperties": False},
            },
        },
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup_stock",
                    "description": "Lookup",
                    "parameters": {"type": "object", "additionalProperties": False},
                },
            }
        ],
        "tool_choice": "auto",
    }
    mock_cls, _ = _mock_async_client_factory(handler)
    resp = asyncio.run(google_cloud.post_chat_completion(s, payload, client=mock_cls()))
    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["finish_reason"] == "tool_calls"
    assert data["choices"][0]["message"]["content"] == '{"ok": true}'
    assert data["choices"][0]["message"]["reasoning_content"] == "Réflexion interne"
    assert data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "lookup_stock"
    assert data["usage"] == {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}

    # Streaming SSE via :streamGenerateContent?alt=sse
    def stream_handler(url, headers, body):
        assert url == "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
        assert headers["x-goog-api-key"] == "AIzaVertexTestKey123"
        return _sse_response(
            200,
            [
                json.dumps({"candidates": [{"content": {"parts": [{"text": "Étape 1...", "thought": True}]}}]}),
                json.dumps({"candidates": [{"content": {"parts": [{"text": "Bonjour Vertex Key"}]}, "finishReason": "STOP"}]}),
            ],
            url=url,
        )

    stream_cls, _ = _mock_async_client_factory(handler, stream_handler=stream_handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", stream_cls)

    async def collect():
        return [
            ev
            async for ev in providers.stream_chat_events(
                s,
                [{"role": "user", "content": "Salut"}],
                "google/gemini-2.5-flash",
            )
        ]

    events = asyncio.run(collect())
    assert "".join(e["text"] for e in events if e["type"] == "thought") == "Étape 1..."
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Bonjour Vertex Key"


# 5. Gemini Developer API Mode


def test_gemini_api_mode_routing():
    s = Settings(
        _env_file=None,
        google_cloud_mode="gemini_api",
        google_api_key=SecretStr("AIzaGeminiDevKey999"),
    )

    def handler(url, headers, body):
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert headers["Authorization"] == "Bearer AIzaGeminiDevKey999"
        assert body["model"] == "gemini-2.5-flash"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK Gemini Dev"}, "finish_reason": "stop"}]},
            request=httpx.Request("POST", url),
        )

    mock_cls, _ = _mock_async_client_factory(handler)
    resp = asyncio.run(
        google_cloud.post_chat_completion(
            s,
            {"model": "google/gemini-2.5-flash", "messages": [{"role": "user", "content": "Hi"}]},
            client=mock_cls(),
        )
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "OK Gemini Dev"


# 6. Strict No-Fallback Default & Opt-In OpenRouter Fallback


def test_no_fallback_default_and_opt_in_openrouter_fallback(monkeypatch):
    creds = _DummyCredentials(token="ya29.ok", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "strict-proj"))

    # Default: google_cloud_fallback_openrouter=False (even if llm_api_key is set)
    s_strict = Settings(
        _env_file=None,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="strict-proj",
        llm_api_key=SecretStr("sk-or-should-not-be-called"),
    )
    assert s_strict.google_cloud_fallback_openrouter is False
    assert google_cloud.can_fallback_to_model(s_strict, "google/gemini-2.5-pro", "openai/gpt-4o-mini") is False
    assert google_cloud.can_fallback_to_model(s_strict, "google/gemini-2.5-pro", "google/gemini-2.5-flash") is True

    for status in (401, 404, 429):
        called_urls: list[str] = []

        def strict_handler(url, headers, body, _status=status):
            called_urls.append(url)
            return httpx.Response(_status, json={"error": {"message": "fail"}}, request=httpx.Request("POST", url))

        mock_cls, _ = _mock_async_client_factory(strict_handler, stream_handler=strict_handler)
        resp = asyncio.run(
            google_cloud.post_chat_completion(
                s_strict,
                {"model": "google/gemini-2.5-flash", "messages": [{"role": "user", "content": "Hi"}]},
                client=mock_cls(),
            )
        )
        assert resp.status_code == status
        assert len(called_urls) == 1
        assert all("openrouter.ai" not in u for u in called_urls)

        monkeypatch.setattr(providers.httpx, "AsyncClient", mock_cls)

        async def run_stream():
            async for _ in providers.stream_chat_events(
                s_strict,
                [{"role": "user", "content": "Hi"}],
                "google/gemini-2.5-flash",
            ):
                pass

        with pytest.raises(providers.ProviderError):
            asyncio.run(run_stream())
        assert all("openrouter.ai" not in u for u in called_urls)

    # Opt-in: google_cloud_fallback_openrouter=True
    s_optin = Settings(
        _env_file=None,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="strict-proj",
        google_cloud_fallback_openrouter=True,
        llm_api_key=SecretStr("sk-or-fallback-key"),
    )
    assert google_cloud.can_fallback_to_model(s_optin, "google/gemini-2.5-pro", "openai/gpt-4o-mini") is True

    fallback_urls: list[str] = []

    def optin_handler(url, headers, body):
        fallback_urls.append(url)
        if "aiplatform.googleapis.com" in url:
            return httpx.Response(429, text="quota", request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OpenRouter backup"}, "finish_reason": "stop"}]},
            request=httpx.Request("POST", url),
        )

    def optin_stream_handler(url, headers, body):
        fallback_urls.append(url)
        if "aiplatform.googleapis.com" in url:
            return httpx.Response(429, content=b"quota", request=httpx.Request("POST", url))
        return _sse_response(
            200,
            [json.dumps({"choices": [{"delta": {"content": "Stream fallback"}, "finish_reason": "stop"}]}), "[DONE]"],
            url=url,
        )

    opt_cls, _ = _mock_async_client_factory(optin_handler, stream_handler=optin_stream_handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", opt_cls)

    res_post = asyncio.run(
        google_cloud.post_chat_completion(
            s_optin,
            {"model": "google/gemini-2.5-flash", "messages": [{"role": "user", "content": "Hi"}]},
            client=opt_cls(),
        )
    )
    assert res_post.status_code == 200
    assert res_post.json()["choices"][0]["message"]["content"] == "OpenRouter backup"
    assert len(fallback_urls) == 2
    assert "aiplatform.googleapis.com" in fallback_urls[0]
    assert "openrouter.ai/api/v1/chat/completions" in fallback_urls[1]

    fallback_urls.clear()

    async def collect_fallback_stream():
        return [
            e
            async for e in providers.stream_chat_events(
                s_optin,
                [{"role": "user", "content": "Hi"}],
                "google/gemini-2.5-flash",
            )
        ]

    ev_fb = asyncio.run(collect_fallback_stream())
    assert "".join(e["text"] for e in ev_fb if e["type"] == "delta") == "Stream fallback"
    assert len(fallback_urls) == 2
    assert "aiplatform.googleapis.com" in fallback_urls[0]
    assert "openrouter.ai" in fallback_urls[1]


# 7. Google Image Generation (Gemini + Imagen, Validations & Non-Google Untouched)


def test_google_cloud_image_generation_and_validation(monkeypatch):
    creds = _DummyCredentials(token="ya29.img-tok", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "img-proj"))

    tiny_b64 = base64.b64encode(_TINY_PNG).decode("ascii")
    s_oauth = Settings(_env_file=None, google_cloud_mode="vertex_oauth", google_cloud_project="img-proj", google_cloud_location="europe-west1")

    # Gemini image via vertex_oauth
    def gemini_img_handler(url, headers, body):
        assert url == "https://europe-west1-aiplatform.googleapis.com/v1/projects/img-proj/locations/europe-west1/publishers/google/models/gemini-2.5-flash-image:generateContent"
        assert headers["Authorization"] == "Bearer ya29.img-tok"
        assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
        assert body["generationConfig"]["imageConfig"]["aspectRatio"] == "16:9"
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": tiny_b64}}]}}]},
            request=httpx.Request("POST", url),
        )

    mock_cls, _ = _mock_async_client_factory(gemini_img_handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", mock_cls)
    img_bytes, mime = asyncio.run(providers.generate_image(s_oauth, "Un phare", "16:9", None, model="google/gemini-2.5-flash-image"))
    assert img_bytes == _TINY_PNG
    assert mime == "image/png"

    # Imagen :predict via vertex_api_key
    s_vkey = Settings(_env_file=None, google_cloud_mode="vertex_api_key", vertex_api_key=SecretStr("vkey-img"))

    def imagen_handler(url, headers, body):
        assert url == "https://aiplatform.googleapis.com/v1/publishers/google/models/imagen-3.0-generate-002:predict"
        assert headers["x-goog-api-key"] == "vkey-img"
        assert body["instances"] == [{"prompt": "Un volcan"}]
        assert body["parameters"]["aspectRatio"] == "1:1"
        assert body["parameters"]["negativePrompt"] == "flou"
        return httpx.Response(
            200,
            json={"predictions": [{"bytesBase64Encoded": tiny_b64, "mimeType": "image/png"}]},
            request=httpx.Request("POST", url),
        )

    imagen_cls, _ = _mock_async_client_factory(imagen_handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", imagen_cls)
    img_bytes2, mime2 = asyncio.run(providers.generate_image(s_vkey, "Un volcan", "1:1", "flou", model="google/imagen-3.0-generate-002"))
    assert img_bytes2 == _TINY_PNG and mime2 == "image/png"

    # Reject invalid image bytes
    bad_b64 = base64.b64encode(b"NOT_AN_IMAGE_BYTES").decode("ascii")

    def bad_img_handler(url, headers, body):
        return httpx.Response(
            200,
            json={"predictions": [{"bytesBase64Encoded": bad_b64, "mimeType": "image/png"}]},
            request=httpx.Request("POST", url),
        )

    bad_cls, _ = _mock_async_client_factory(bad_img_handler)
    with pytest.raises(google_cloud.ProviderError, match="image reconnue"):
        asyncio.run(
            google_cloud.generate_google_cloud_image(
                s_vkey, "google/imagen-3.0-generate-002", "Test", client=bad_cls()
            )
        )

    # Reject oversized image (> 10 MiB)
    huge_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (10 * 1024 * 1024 + 32)).decode("ascii")

    def huge_img_handler(url, headers, body):
        return httpx.Response(
            200,
            json={"predictions": [{"bytesBase64Encoded": huge_b64, "mimeType": "image/png"}]},
            request=httpx.Request("POST", url),
        )

    huge_cls, _ = _mock_async_client_factory(huge_img_handler)
    with pytest.raises(google_cloud.ProviderError, match="10 Mio"):
        asyncio.run(
            google_cloud.generate_google_cloud_image(
                s_vkey, "google/imagen-3.0-generate-002", "Test", client=huge_cls()
            )
        )

    # Ideogram & OpenRouter non-Google images stay untouched
    s_both = Settings(
        _env_file=None,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="img-proj",
        llm_api_key=SecretStr("sk-or-img"),
        ideogram_api_key=SecretStr("ideo-secret"),
    )
    called_targets: list[str] = []

    def non_gc_img_handler(url, headers, body):
        called_targets.append(url)
        if url == "https://ideogram.ai/assets/img.png":
            return httpx.Response(
                200,
                content=_TINY_PNG,
                headers={"content-type": "image/png"},
                request=httpx.Request("GET", url),
            )
        if "ideogram.ai" in url:
            return httpx.Response(200, json={"data": [{"url": "https://ideogram.ai/assets/img.png"}]}, request=httpx.Request("POST", url))
        return httpx.Response(
            200,
            json={"data": [{"b64_json": tiny_b64, "media_type": "image/png"}]},
            request=httpx.Request("POST", url),
        )

    non_gc_cls, _ = _mock_async_client_factory(non_gc_img_handler)
    monkeypatch.setattr(providers.httpx, "AsyncClient", non_gc_cls)
    b1, _ = asyncio.run(providers.generate_image(s_both, "Logo", "1:1", None, model="ideogram-4-5"))
    b2, _ = asyncio.run(providers.generate_image(s_both, "Paysage", "1:1", None, model="black-forest-labs/flux-3-image"))
    assert b1 == _TINY_PNG and b2 == _TINY_PNG
    assert any("ideogram.ai" in u for u in called_targets)
    assert any("openrouter.ai/api/v1/images" in u for u in called_targets)


# 8. Non-Google Chat Models Stay on OpenRouter


def test_non_google_models_remain_on_openrouter(monkeypatch):
    creds = _DummyCredentials(token="ya29.gc", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "gc-proj"))

    s = Settings(
        _env_file=None,
        google_cloud_mode="vertex_oauth",
        google_cloud_project="gc-proj",
        llm_api_key=SecretStr("sk-or-primary"),
    )
    seen_urls: list[tuple[str, str]] = []

    def handler(url, headers, body):
        seen_urls.append((url, body["model"]))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OpenRouter OK"}, "finish_reason": "stop"}]},
            request=httpx.Request("POST", url),
        )

    mock_cls, _ = _mock_async_client_factory(handler)
    for model_id in ("openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"):
        resp = asyncio.run(
            google_cloud.post_chat_completion(
                s,
                {"model": model_id, "messages": [{"role": "user", "content": "Hello"}]},
                client=mock_cls(),
            )
        )
        assert resp.status_code == 200
    assert seen_urls == [
        ("https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4o-mini"),
        ("https://openrouter.ai/api/v1/chat/completions", "anthropic/claude-3.5-sonnet"),
    ]


# 9. End-to-End Auxiliary Modules, Hermes Bypass & FastAPI Endpoints Without LLM_API_KEY


def test_topic_agent_routes_google_cloud_without_llm_api_key(tmp_path, monkeypatch):
    creds = _DummyCredentials(token="ya29.topic", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "topic-proj"))

    engine = create_engine(f"sqlite:///{tmp_path / 'topic.db'}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as db:
        u = User(id="u1", username="topic-tester", password_hash="x", is_admin=False)
        t = TopicSpace(id="t1", user_id="u1", title="Rust", topic_type="learning", objective="Maîtriser Rust")
        db.add_all([u, t])
        db.commit()

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key=SecretStr(""),
        default_model="google/gemini-2.5-flash",
        google_cloud_mode="vertex_oauth",
        google_cloud_project="topic-proj",
    )
    called_urls: list[str] = []

    def handler(url, headers, body):
        called_urls.append(url)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "new_resume_context": "Point borrow checker acquis.",
                                "suggested_next_step": "Tester les lifetimes",
                                "add_memories": [],
                                "update_memories": [],
                                "events": [],
                            })
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    mock_cls, _ = _mock_async_client_factory(handler)
    monkeypatch.setattr(topic_agent.httpx, "AsyncClient", mock_cls)

    res = asyncio.run(
        topic_agent.process_topic_turn(
            SessionLocal,
            "t1",
            "Explique le borrow checker",
            "Voici comment fonctionne le borrow checker...",
            settings,
        )
    )
    assert res["new_resume_context"] == "Point borrow checker acquis."
    assert len(called_urls) == 1
    assert "aiplatform.googleapis.com" in called_urls[0]


def test_finance_dossier_and_experts_route_google_no_openrouter_fallback(tmp_path, monkeypatch):
    creds = _DummyCredentials(token="ya29.fin", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "fin-proj"))

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-should-not-run"),
        default_model="openai/gpt-4o-mini",
        google_cloud_mode="vertex_oauth",
        google_cloud_project="fin-proj",
        google_cloud_fallback_openrouter=False,
    )

    fake_dossier = {
        "symbol": "ACME",
        "currency": "USD",
        "header": {"name": "ACME Corp", "sector": "Tech", "industry": "Cloud", "cap_category": "Large", "ih_score": 8, "ih_trend": "stable"},
        "capital_valuation": {"pe_ttm": 20.0, "ev_ebitda": 12.0, "op_margin_ttm": 25.0},
        "annual_tables": {"piotroski": {"latest_score": 7}, "altman": {"latest_score": 3.5}},
    }

    async def fake_get_dossier(*args, **kwargs):
        return fake_dossier

    async def fake_collect_news(*args, **kwargs):
        return {"articles": [], "sources_used": []}

    monkeypatch.setattr(finance_dossier, "get_financial_dossier", fake_get_dossier)
    monkeypatch.setattr(finance_dossier, "build_dossier_facts_context", lambda d: ({"source_principale": "test", "date_generation_analyse": "2026-11-19", "date_reference_cours": "2026-11-18"}, "TTM"))
    monkeypatch.setattr(finance_dossier, "_finalize_and_save_dossier_analysis", lambda *args, **kwargs: {"markdown": kwargs["markdown"], "model": kwargs["model"]})
    monkeypatch.setattr(finance_experts, "get_financial_dossier", fake_get_dossier)
    monkeypatch.setattr(finance_experts, "collect_latest_stock_news", fake_collect_news)
    monkeypatch.setattr(finance_experts, "build_dossier_facts_context", lambda d: ({"source_principale": "test"}, "TTM"))
    monkeypatch.setattr(finance_experts, "_finalize_and_save_expert_opinion", lambda *args, **kwargs: {"markdown": kwargs["markdown"], "model": kwargs["model"]})

    # 1. Success on Vertex AI for dossier + expert
    called_models: list[tuple[str, str]] = []

    def ok_handler(url, headers, body):
        called_models.append((url, body["model"]))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "### Analyse Vertex Finance\nVerdict positif."}, "finish_reason": "stop"}]},
            request=httpx.Request("POST", url),
        )

    ok_cls, _ = _mock_async_client_factory(ok_handler)
    monkeypatch.setattr(finance_dossier.httpx, "AsyncClient", ok_cls)
    monkeypatch.setattr(finance_experts.httpx, "AsyncClient", ok_cls)

    res_dossier = asyncio.run(finance_dossier.generate_dossier_ai_analysis(settings, "ACME", model_id="google/gemini-4-hydrogen"))
    res_expert = asyncio.run(finance_experts.generate_finance_expert_opinion(settings, "ACME", "warren_buffett", model_id="google/gemini-4-hydrogen"))
    assert res_dossier["model"] == "google/gemini-4-hydrogen"
    assert res_expert["model"] == "google/gemini-4-hydrogen"
    assert len(called_models) == 2
    assert all("aiplatform.googleapis.com" in u for u, _ in called_models)

    # 2. Failure on Vertex AI must NOT fallback to non-Google settings.default_model
    err_urls: list[str] = []

    def err_handler(url, headers, body):
        err_urls.append(url)
        return httpx.Response(503, text="vertex unavailable", request=httpx.Request("POST", url))

    err_cls, _ = _mock_async_client_factory(err_handler)
    monkeypatch.setattr(finance_dossier.httpx, "AsyncClient", err_cls)
    monkeypatch.setattr(finance_experts.httpx, "AsyncClient", err_cls)

    with pytest.raises(providers.ProviderError):
        asyncio.run(finance_dossier.generate_dossier_ai_analysis(settings, "ACME", model_id="google/gemini-4-hydrogen"))
    with pytest.raises(providers.ProviderError):
        asyncio.run(finance_experts.generate_finance_expert_opinion(settings, "ACME", "warren_buffett", model_id="google/gemini-4-hydrogen"))
    assert len(err_urls) == 2
    assert all("aiplatform.googleapis.com" in u for u in err_urls)


def test_hermes_bypasses_docker_gateway_for_google_models(monkeypatch):
    creds = _DummyCredentials(token="ya29.hermes", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "hermes-proj"))

    settings = Settings(
        _env_file=None,
        demo_mode=False,
        llm_api_key=SecretStr(""),
        hermes_enabled=True,
        hermes_api_url="http://clair-hermes:8642",
        google_cloud_mode="vertex_oauth",
        google_cloud_project="hermes-proj",
    )
    hit_urls: list[str] = []

    def handler(url, headers, body):
        hit_urls.append(url)
        if url.endswith("/health"):
            return httpx.Response(200, json={"status": "ok"}, request=httpx.Request("GET", url))
        if url.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "nousresearch/hermes-agent"}]}, request=httpx.Request("GET", url))
        raise AssertionError(f"Unexpected gateway call: {url}")

    def stream_handler(url, headers, body):
        hit_urls.append(url)
        return _sse_response(
            200,
            [
                json.dumps({"choices": [{"delta": {"extra_content": {"google": {"thought": "Plan Hermes"}}}, "finish_reason": None}]}),
                json.dumps({"choices": [{"delta": {"content": "Réponse Hermes Vertex"}, "finish_reason": "stop"}]}),
                "[DONE]",
            ],
            url=url,
        )

    mock_cls, _ = _mock_async_client_factory(handler, stream_handler=stream_handler)
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", mock_cls)

    async def run_mission():
        events = []
        async for ev in hermes_agent.stream_hermes_mission(
            settings=settings,
            prompt="Analyse rapide",
            model="google/gemini-2.5-flash",
            enabled_tools=[],
            auto_learn_skill=False,
            execution_mode="auto",
        ):
            events.append(ev)
        return events

    events = asyncio.run(run_mission())
    meta = next(e for e in events if e["type"] == "meta")
    assert meta["mode"] == "local_autonomous"
    assert meta["model"] == "google/gemini-2.5-flash"
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Réponse Hermes Vertex"
    assert not any("/v1/chat/completions" in u for u in hit_urls)
    assert any("aiplatform.googleapis.com" in u for u in hit_urls)


def test_fastapi_config_and_images_work_with_google_cloud_only(tmp_path, monkeypatch):
    creds = _DummyCredentials(token="ya29.api", expiry_delta_seconds=3600)
    monkeypatch.setattr(google_cloud.google.auth, "default", lambda scopes=None: (creds, "api-proj-1"))

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key=SecretStr(""),
        google_cloud_mode="vertex_oauth",
        google_cloud_project="api-proj-1",
    )

    tiny_b64 = base64.b64encode(_TINY_PNG).decode("ascii")

    def img_handler(url, headers, body):
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": tiny_b64}}]}}]},
            request=httpx.Request("POST", url),
        )

    mock_cls, _ = _mock_async_client_factory(img_handler)
    monkeypatch.setattr(google_cloud.httpx, "AsyncClient", mock_cls)

    with authenticated_client(s) as client:
        cfg_res = client.get("/api/config")
        assert cfg_res.status_code == 200
        cfg = cfg_res.json()
        assert cfg["demo_mode"] is False
        assert cfg["google_cloud_mode"] == "vertex_oauth"
        assert cfg["features"]["chat"] is True
        assert cfg["features"]["google_cloud"] is True
        assert cfg["features"]["image_generation"] is True
        assert any(m["id"] == "google/gemini-2.5-flash" for m in cfg["models"])

        img_res = client.post(
            "/api/images",
            json={"prompt": "Un lever de soleil", "aspect_ratio": "1:1", "model": "google/gemini-2.5-flash-image"},
        )
        assert img_res.status_code == 201, img_res.text
        body = img_res.json()
        assert body["mime_type"] == "image/png"
