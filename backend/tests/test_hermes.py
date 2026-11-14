import json
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app import hermes_agent
from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Base, User


@pytest.fixture
def demo_settings(tmp_path):
    return Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)


@contextmanager
def authenticated_client(settings: Settings):
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        existing = db.scalar(select(User).where(User.username == "hermes-tester"))
        if not existing:
            db.add(
                User(
                    username="hermes-tester",
                    password_hash=hash_password("correct horse battery"),
                    is_admin=True,
                )
            )
            db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        resp = client.post(
            "/api/auth/login",
            json={"username": "hermes-tester", "password": "correct horse battery"},
        )
        assert resp.status_code == 200
        yield client


def parse_sse_events(text: str) -> list[tuple[str, dict]]:
    result: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event_lines = [line[7:] for line in lines if line.startswith("event: ")]
        data_lines = [line[6:] for line in lines if line.startswith("data: ")]
        if not event_lines or not data_lines:
            continue
        result.append((event_lines[0], json.loads("\n".join(data_lines))))
    return result


def test_hermes_status_demo_and_fallback(tmp_path):
    s_demo = Settings(_env_file=None, app_data_dir=tmp_path / "demo", demo_mode=True)
    with authenticated_client(s_demo) as client:
        res = client.get("/api/hermes/status")
        assert res.status_code == 200
        body = res.json()
        assert body["enabled"] is True
        assert body["mode"] == "demo"
        assert body["gateway_reachable"] is False
        assert len(body["tools"]) == 5
        assert len(body["presets"]) >= 3

    s_local = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "local",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test-key"),
        hermes_api_url="",
    )
    with authenticated_client(s_local) as client:
        res = client.get("/api/hermes/status")
        assert res.status_code == 200
        body = res.json()
        assert body["mode"] == "local_autonomous"
        assert body["provider"] == "openrouter"
        assert body["gateway_reachable"] is False


def test_hermes_status_gateway_connected(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "hermes-agent"}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", mock_async_client)

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        hermes_api_url="http://hermes-mock.local:8642",
        hermes_api_key=SecretStr("gw-secret-token"),
    )
    with authenticated_client(settings) as client:
        res = client.get("/api/hermes/status")
        assert res.status_code == 200
        body = res.json()
        assert body["mode"] == "gateway"
        assert body["gateway_reachable"] is True
        assert body["gateway_models"] == ["hermes-agent"]


def test_hermes_run_sse_stream_demo(demo_settings):
    with authenticated_client(demo_settings) as client:
        res = client.post(
            "/api/hermes/run",
            json={
                "prompt": "Prépare un plan d'audit API sécurisé",
                "enabled_tools": ["web_search", "memory", "skills", "code_execution"],
                "auto_learn_skill": True,
            },
        )
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        ev_types = [name for name, _ in ev_list]
        assert "meta" in ev_types
        assert "step" in ev_types
        assert "delta" in ev_types
        assert "artifacts" in ev_types
        assert ev_types[-1] == "done"

        artifacts = next(data for name, data in ev_list if name == "artifacts")
        assert artifacts["suggested_skill"] is not None
        assert artifacts["suggested_skill"]["name"]
        assert artifacts["suggested_memory"]


def test_hermes_run_gateway_forwarding(tmp_path, monkeypatch):
    captured_requests: list[tuple[str, dict[str, str]]] = []

    sse_payload = (
        'event: hermes.tool.progress\n'
        'data: {"tool_call_id": "tc1", "tool": "web_search", "message": "Recherche en cours", "done": true}\n\n'
        'data: {"choices": [{"delta": {"content": "Résultat "}}]}\n\n'
        'data: {"choices": [{"delta": {"content": "Gateway OK"}}]}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append((request.url.path, dict(request.headers)))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "hermes-agent"}]})
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                content=sse_payload,
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", mock_async_client)

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        hermes_api_url="http://hermes-mock.local:8642",
        hermes_api_key=SecretStr("gw-secret-token"),
    )
    with authenticated_client(settings) as client:
        res = client.post(
            "/api/hermes/run",
            json={
                "prompt": "Analyse le répertoire courant",
                "session_id": "sess-xyz-42",
                "auto_learn_skill": False,
            },
        )
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        deltas = "".join(data["text"] for name, data in ev_list if name == "delta")
        assert deltas == "Résultat Gateway OK"
        step_tools = [data["tool"] for name, data in ev_list if name == "step"]
        assert "web_search" in step_tools

        chat_reqs = [hdrs for path, hdrs in captured_requests if path == "/v1/chat/completions"]
        assert len(chat_reqs) == 1
        assert chat_reqs[0].get("authorization") == "Bearer gw-secret-token"
        assert chat_reqs[0].get("x-hermes-session-id") == "sess-xyz-42"


def test_hermes_react_limits_and_clean_stops(tmp_path, monkeypatch):
    def make_sse(delta_payload: dict, usage: dict | None = None) -> bytes:
        lines = [f"data: {json.dumps({'choices': [{'delta': delta_payload}]})}\n\n"]
        if usage:
            lines.append(f"data: {json.dumps({'usage': usage})}\n\n")
        lines.append("data: [DONE]\n\n")
        return "".join(lines).encode("utf-8")

    # 1. Plafond 10 appels d'outils + restitution partielle + suivi tokens/coût
    def handler_max_tools(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openrouter.ai":
            calls = [
                {
                    "index": idx,
                    "id": f"tc_{idx}",
                    "type": "function",
                    "function": {"name": "github_inspect", "arguments": json.dumps({"repo": f"org/repo-{idx}"})},
                }
                for idx in range(12)
            ]
            return httpx.Response(
                200,
                content=make_sse({"tool_calls": calls}, {"prompt_tokens": 40, "completion_tokens": 10, "total_tokens": 50, "cost": 0.002}),
                headers={"content-type": "text/event-stream"},
            )
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"full_name": "org/repo", "html_url": "https://github.com/org/repo", "default_branch": "main"})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_max_tools), **kw))

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "max_tools",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="",
        hermes_max_cost_usd=1.0,
    )
    with authenticated_client(s) as client:
        res = client.post("/api/hermes/run", json={"prompt": "Inspecte 12 dépôts", "enabled_tools": ["web_search"], "auto_learn_skill": False})
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        done = next(d for name, d in ev_list if name == "done")
        assert done["metrics"]["tool_calls"] == 10
        assert done["metrics"]["stop_reason"] == "max_tool_calls"
        assert done["metrics"]["cost_usd"] == 0.002
        assert "Restitution partielle" in done["content"]

    # 2. Plafond budget financier configurable
    def handler_budget(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openrouter.ai":
            calls = [{"index": 0, "id": "tc_b", "type": "function", "function": {"name": "github_inspect", "arguments": '{"repo":"letta-ai/letta"}'}}]
            return httpx.Response(
                200,
                content=make_sse({"tool_calls": calls}, {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "cost": 0.02}),
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(404)

    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_budget), **kw))
    s_budget = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "budget",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="",
        hermes_max_cost_usd=0.01,
    )
    with authenticated_client(s_budget) as client:
        res = client.post("/api/hermes/run", json={"prompt": "Test budget", "enabled_tools": ["web_search"], "auto_learn_skill": False})
        assert res.status_code == 200
        done = next(d for name, d in parse_sse_events(res.text) if name == "done")
        assert done["metrics"]["stop_reason"] == "budget_exceeded"
        assert done["metrics"]["cost_usd"] >= 0.01

    # 3. Détection appels identiques répétés & absence de progression + plafond 15 LLM
    turn_counter = {"n": 0}

    def handler_repeat(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openrouter.ai":
            turn_counter["n"] += 1
            calls = [{"index": 0, "id": f"tc_r_{turn_counter['n']}", "type": "function", "function": {"name": "github_inspect", "arguments": '{"repo":"letta-ai/letta"}'}}]
            return httpx.Response(
                200,
                content=make_sse({"tool_calls": calls}, {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001}),
                headers={"content-type": "text/event-stream"},
            )
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"full_name": "letta-ai/letta", "html_url": "https://github.com/letta-ai/letta", "default_branch": "main"})
        return httpx.Response(404)

    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_repeat), **kw))
    with authenticated_client(s) as client:
        res = client.post("/api/hermes/run", json={"prompt": "Test répétition", "enabled_tools": ["web_search"], "auto_learn_skill": False})
        assert res.status_code == 200
        done = next(d for name, d in parse_sse_events(res.text) if name == "done")
        assert done["metrics"]["tool_calls"] == 1
        assert done["metrics"]["stop_reason"] in {"repeated_call", "no_progress"}
        assert "Restitution partielle" in done["content"]


def test_hermes_multitool_chain_after_two_web_searches(tmp_path, monkeypatch):
    """Reproduit 2 web_search -> raisonnement intermédiaire -> 2 github_inspect -> synthèse finale."""
    captured_payloads: list[dict] = []
    turn_idx = {"n": 0}

    async def fake_search_web(_settings, query: str, limit: int = 5):
        return [{"title": f"Result for {query}", "url": f"https://example.org/{limit}", "snippet": "LangGraph info"}]

    monkeypatch.setattr(hermes_agent.providers, "search_web", fake_search_web)

    def make_chunk_sse(chunks: list[dict]) -> bytes:
        return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openrouter.ai":
            payload = json.loads(request.content.decode("utf-8"))
            captured_payloads.append(payload)
            turn_idx["n"] += 1
            n = turn_idx["n"]
            if n == 1:
                return httpx.Response(
                    200,
                    content=make_chunk_sse(
                        [
                            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "ws_1", "type": "function", "function": {"name": "web_search", "arguments": '{"query":"langgraph"}'}}]}, "finish_reason": "tool_calls"}]}
                        ]
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            if n == 2:
                return httpx.Response(
                    200,
                    content=make_chunk_sse(
                        [
                            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "ws_2", "type": "function", "function": {"name": "web_search", "arguments": '{"query":"crewai"}'}}]}, "finish_reason": "tool_calls"}]}
                        ]
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            if n == 3:
                # Raisonnement intermédiaire seul (ancien déclencheur du faux no_progress)
                return httpx.Response(
                    200,
                    content=make_chunk_sse(
                        [{"choices": [{"delta": {"reasoning": "Je dois maintenant inspecter les dépôts GitHub."}, "finish_reason": "stop"}]}]
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            if n == 4:
                return httpx.Response(
                    200,
                    content=make_chunk_sse(
                        [
                            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "gh_1", "type": "function", "function": {"name": "github_inspect", "arguments": '{"repo":"langchain-ai/langgraph"}'}}]}, "finish_reason": "tool_calls"}]}
                        ]
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            if n == 5:
                return httpx.Response(
                    200,
                    content=make_chunk_sse(
                        [
                            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "gh_2", "type": "function", "function": {"name": "github_inspect", "arguments": '{"repo":"crewAIInc/crewAI"}'}}]}, "finish_reason": "tool_calls"}]}
                        ]
                    ),
                    headers={"content-type": "text/event-stream"},
                )
            return httpx.Response(
                200,
                content=make_chunk_sse(
                    [
                        {"choices": [{"delta": {"content": "Synthèse finale LangGraph + CrewAI vérifiée."}, "finish_reason": "stop"}]},
                        {"usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160, "cost": 0.004}},
                    ]
                ),
                headers={"content-type": "text/event-stream"},
            )
        if request.url.host == "api.github.com":
            return httpx.Response(200, json={"full_name": request.url.path.split("/repos/")[1].split("/")[0] + "/repo", "html_url": "https://github.com/org/repo", "default_branch": "main"})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler), **kw))

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "chain",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="",
        web_search_enabled=True,
        brave_api_key=SecretStr("brave-test"),
    )
    with authenticated_client(s) as client:
        res = client.post("/api/hermes/run", json={"prompt": "Compare LangGraph et CrewAI", "enabled_tools": ["web_search"], "auto_learn_skill": False})
        assert res.status_code == 200
        done = next(d for name, d in parse_sse_events(res.text) if name == "done")
        assert done["metrics"]["stop_reason"] == "completed"
        assert done["metrics"]["tool_calls"] == 4
        assert done["metrics"]["llm_calls"] == 6
        assert "Synthèse finale LangGraph + CrewAI vérifiée." in done["content"]

    # Vérifier la conformité stricte de assistant.tool_calls et tool.tool_call_id sur le dernier tour
    final_msgs = captured_payloads[-1]["messages"]
    tool_call_ids_in_assistant = [
        tc["id"]
        for m in final_msgs
        if m.get("role") == "assistant" and isinstance(m.get("tool_calls"), list)
        for tc in m["tool_calls"]
    ]
    tool_ids_in_responses = [m["tool_call_id"] for m in final_msgs if m.get("role") == "tool"]
    assert tool_call_ids_in_assistant == ["ws_1", "ws_2", "gh_1", "gh_2"]
    assert tool_ids_in_responses == ["ws_1", "ws_2", "gh_1", "gh_2"]
    assert all(isinstance(m.get("content"), str) for m in final_msgs if m.get("role") == "assistant")


def test_hermes_loop_resistance_identical_web_search_and_no_new_info(tmp_path, monkeypatch):
    """Résistance aux boucles : (1) web_search identique infini, (2) appels différents sans info nouvelle."""
    search_queries: list[str] = []

    async def fake_search_web(_settings, query: str, limit: int = 5):
        search_queries.append(query)
        if query == "langgraph":
            return [{"title": "LangGraph", "url": "https://langchain-ai.github.io/langgraph/", "snippet": "Docs"}]
        return []

    monkeypatch.setattr(hermes_agent.providers, "search_web", fake_search_web)

    def make_sse(delta_payload: dict, usage: dict | None = None) -> bytes:
        chunks = [{"choices": [{"delta": delta_payload, "finish_reason": "tool_calls"}]}]
        if usage:
            chunks.append({"usage": usage})
        return ("".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n").encode("utf-8")

    # Scénario 1 : le faux OpenRouter demande indéfiniment le même web_search("langgraph")
    call_idx = {"n": 0}

    def handler_identical(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"
        call_idx["n"] += 1
        return httpx.Response(
            200,
            content=make_sse(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"ws_loop_{call_idx['n']}",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": '{"query": "langgraph"}'},
                        }
                    ]
                },
                {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "cost": 0.0005},
            ),
            headers={"content-type": "text/event-stream"},
        )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_identical), **kw),
    )

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "loop_res",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="",
        web_search_enabled=True,
        brave_api_key=SecretStr("brave-test"),
    )
    with authenticated_client(s) as client:
        res = client.post(
            "/api/hermes/run",
            json={"prompt": "Boucle infinie web_search", "enabled_tools": ["web_search"], "auto_learn_skill": False},
        )
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        ev_types = [name for name, _ in ev_list]
        assert "artifacts" in ev_types
        assert ev_types[-1] == "done"

        done = next(d for name, d in ev_list if name == "done")
        assert done["metrics"]["stop_reason"] == "repeated_call"
        assert done["metrics"]["tool_calls"] == 1
        assert done["metrics"]["llm_calls"] == 3
        assert done["metrics"]["tool_calls"] <= 10
        assert done["metrics"]["llm_calls"] <= 15
        assert "Restitution partielle" in done["content"]
        assert search_queries == ["langgraph"]

        step_titles = [d["title"] for name, d in ev_list if name == "step"]
        assert any("Appel identique bloqué" in title for title in step_titles)

    # Scénario 2 : appels différents mais aucune nouvelle information retournée
    search_queries.clear()
    diff_idx = {"n": 0}

    def handler_diff_no_info(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"
        diff_idx["n"] += 1
        return httpx.Response(
            200,
            content=make_sse(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": f"ws_empty_{diff_idx['n']}",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": json.dumps({"query": f"requete_vide_{diff_idx['n']}"})},
                        }
                    ]
                }
            ),
            headers={"content-type": "text/event-stream"},
        )

    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_diff_no_info), **kw),
    )
    with authenticated_client(s) as client:
        res = client.post(
            "/api/hermes/run",
            json={"prompt": "Recherches sans résultat", "enabled_tools": ["web_search"], "auto_learn_skill": False},
        )
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        assert [name for name, _ in ev_list][-1] == "done"
        done = next(d for name, d in ev_list if name == "done")
        assert done["metrics"]["stop_reason"] == "no_progress"
        assert done["metrics"]["tool_calls"] == 2
        assert done["metrics"]["llm_calls"] == 2
        assert "Restitution partielle" in done["content"]
        assert search_queries == ["requete_vide_1", "requete_vide_2"]


def test_hermes_execution_mode_override_local_when_gateway_reachable(tmp_path, monkeypatch):
    """Permet de choisir `local_autonomous` même lorsque le Gateway Hermes est actif."""
    called_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(f"{request.url.host}{request.url.path}")
        if request.url.host == "hermes-mock.local" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.host == "hermes-mock.local" and request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "hermes-agent"}]})
        if request.url.host == "openrouter.ai" and request.url.path.endswith("/chat/completions"):
            sse = (
                'data: {"choices":[{"delta":{"content":"Réponse locale rapide."},"finish_reason":"stop"}]}\n\n'
                'data: [DONE]\n\n'
            ).encode("utf-8")
            return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler), **kw),
    )

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "override",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="http://hermes-mock.local:8642",
        hermes_api_key=SecretStr("gw-secret"),
    )
    with authenticated_client(s) as client:
        res = client.post(
            "/api/hermes/run",
            json={
                "prompt": "Tâche rapide",
                "execution_mode": "local_autonomous",
                "enabled_tools": ["code_execution"],
                "auto_learn_skill": False,
            },
        )
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        meta = next(d for name, d in ev_list if name == "meta")
        done = next(d for name, d in ev_list if name == "done")
        assert meta["mode"] == "local_autonomous"
        assert done["content"] == "Réponse locale rapide."
        assert "hermes-mock.local/v1/chat/completions" not in called_hosts


def test_hermes_gateway_telemetry_openrouter_cost_and_no_double_counting(tmp_path, monkeypatch):
    """Vérifie la télémétrie Gateway : coût réel OpenRouter (/generation), anti-double-comptage et repli None."""
    sse_with_gens = (
        'event: hermes.tool.progress\n'
        'data: {"tool_call_id": "tc1", "tool": "terminal", "message": "curl api.github.com", "done": true}\n\n'
        'data: {"id": "gen-abc1", "choices": [{"delta": {"content": ""}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100}}\n\n'
        'data: {"id": "gen-abc1", "choices": [{"delta": {"content": ""}}], "usage": {"prompt_tokens": 1000, "completion_tokens": 100, "total_tokens": 1100}}\n\n'
        'event: hermes.tool.progress\n'
        'data: {"tool_call_id": "tc2", "tool": "web_search", "message": "docs", "done": true}\n\n'
        'data: {"id": "gen-abc2", "choices": [{"delta": {"content": "Audit terminé."}}], "usage": {"prompt_tokens": 2000, "completion_tokens": 200, "total_tokens": 2200}}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler_with_cost(request: httpx.Request) -> httpx.Response:
        if request.url.host == "hermes-mock.local":
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "hermes-agent"}]})
            if request.url.path == "/v1/chat/completions":
                return httpx.Response(200, content=sse_with_gens, headers={"content-type": "text/event-stream"})
        if request.url.host == "openrouter.ai" and request.url.path.endswith("/generation"):
            gid = request.url.params.get("id")
            if gid == "gen-abc1":
                return httpx.Response(200, json={"data": {"total_cost": 0.0025}})
            if gid == "gen-abc2":
                return httpx.Response(200, json={"data": {"total_cost": 0.0045}})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_with_cost), **kw),
    )

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "gw_cost",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="http://hermes-mock.local:8642",
        hermes_api_key=SecretStr("gw-secret"),
    )
    with authenticated_client(s) as client:
        res = client.post(
            "/api/hermes/run",
            json={"prompt": "Audit Gateway", "execution_mode": "gateway", "auto_learn_skill": False},
        )
        assert res.status_code == 200
        done = next(d for name, d in parse_sse_events(res.text) if name == "done")
        assert done["metrics"]["llm_calls"] == 2
        assert done["metrics"]["tool_calls"] == 2
        assert done["metrics"]["prompt_tokens"] == 3000
        assert done["metrics"]["completion_tokens"] == 300
        assert done["metrics"]["total_tokens"] == 3300
        assert done["metrics"]["cost_usd"] == 0.007

    # Sans coût ni ID gen-* : cost_usd doit être None (« Coût indisponible » côté UI)
    sse_no_cost = (
        'data: {"id": "local-gw-1", "choices": [{"delta": {"content": "OK"}}], "usage": {"prompt_tokens": 500, "completion_tokens": 50, "total_tokens": 550}}\n\n'
        'data: [DONE]\n\n'
    ).encode("utf-8")

    def handler_no_cost(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "hermes-agent"}]})
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, content=sse_no_cost, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(handler_no_cost), **kw),
    )
    with authenticated_client(s) as client:
        res = client.post(
            "/api/hermes/run",
            json={"prompt": "Sans coût", "execution_mode": "gateway", "auto_learn_skill": False},
        )
        assert res.status_code == 200
        done = next(d for name, d in parse_sse_events(res.text) if name == "done")
        assert done["metrics"]["total_tokens"] == 550
        assert done["metrics"]["cost_usd"] is None


def test_tool_registry_adapters_validation_and_permissions(tmp_path):
    """Vérifie la compatibilité OpenAI/MCP du ToolRegistry, la validation et le refus de permission."""
    import asyncio
    from app import page_service
    from app.tool_registry import (
        CLAIR_TOOL_REGISTRY,
        PERMISSION_CREATE_PAGE_DRAFT,
        ToolExecutionContext,
        permissions_from_enabled_tools,
    )

    assert permissions_from_enabled_tools(["web_search", "memory"]) == set()
    assert PERMISSION_CREATE_PAGE_DRAFT in permissions_from_enabled_tools(["web_search", "create_page"])

    # Sans permission : aucun outil exposé
    assert CLAIR_TOOL_REGISTRY.to_openai_tools(set()) == []
    assert CLAIR_TOOL_REGISTRY.to_mcp_tools(set()) == []

    # Avec permission : schémas OpenAI et MCP alignés
    perms = {PERMISSION_CREATE_PAGE_DRAFT}
    oa_tools = CLAIR_TOOL_REGISTRY.to_openai_tools(perms)
    mcp_tools = CLAIR_TOOL_REGISTRY.to_mcp_tools(perms)
    assert len(oa_tools) == 1 and len(mcp_tools) == 1
    assert oa_tools[0]["function"]["name"] == mcp_tools[0]["name"] == "clair_create_page"
    assert oa_tools[0]["function"]["parameters"] == mcp_tools[0]["inputSchema"]

    s = Settings(_env_file=None, app_data_dir=tmp_path / "reg", demo_mode=True)

    # Refus de permission explicite
    ctx_denied = ToolExecutionContext(settings=s, sessions=None, user_id="u1", allowed_permissions=set())
    res_denied = asyncio.run(
        CLAIR_TOOL_REGISTRY.execute(
            "clair_create_page",
            {"title": "Rapport test", "content": "Contenu suffisamment long pour passer la validation."},
            ctx_denied,
        )
    )
    assert res_denied.success is False
    assert "Permission refusée" in (res_denied.error or "")

    # Validation des arguments (titre trop court + contenu manquant)
    ctx_allowed = ToolExecutionContext(settings=s, sessions=None, user_id="u1", allowed_permissions=perms)
    res_invalid = asyncio.run(
        CLAIR_TOOL_REGISTRY.execute("clair_create_page", {"title": "A", "content": "court"}, ctx_allowed)
    )
    assert res_invalid.success is False
    assert "Arguments invalides" in (res_invalid.error or "")


def test_clair_create_page_local_autonomous_and_engine_failure(tmp_path, monkeypatch):
    """Vérifie clair_create_page via local_autonomous (brouillon uniquement) et gestion d'échec Pages."""
    from app import page_service, providers
    from app.models import WebPage

    async def fake_generate_page_html(*args, title="Brouillon", prompt="", **kwargs):
        return (title or "Brouillon"), f"<!doctype html><html><body><h1>{title}</h1><p>{prompt}</p></body></html>"

    monkeypatch.setattr(page_service, "generate_page_html", fake_generate_page_html)

    captured_tool_names: list[str] = []
    turn_counter = {"n": 0}

    def openrouter_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content.decode("utf-8"))
            if not captured_tool_names:
                captured_tool_names.extend(t["function"]["name"] for t in (body.get("tools") or []))
            turn_counter["n"] += 1
            if turn_counter["n"] == 1:
                chunks = [
                    'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_cp_1", "type": "function", "function": {"name": "clair_create_page", "arguments": ""}}]}}]}\n\n',
                    'data: {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\\"title\\": \\"Brouillon Architecture\\", \\"content\\": \\"Synthese detaillee des choix d architecture pour le moteur agentique.\\", \\"sources\\": [{\\"title\\": \\"Doc\\", \\"url\\": \\"https://example.com\\"}]}"}}]}}]}\n\n',
                    'data: {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}\n\n',
                    "data: [DONE]\n\n",
                ]
                return httpx.Response(200, content="".join(chunks).encode("utf-8"), headers={"content-type": "text/event-stream"})
            chunks = [
                'data: {"choices": [{"delta": {"content": "Brouillon créé avec succès."}}]}\n\n',
                'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n',
                "data: [DONE]\n\n",
            ]
            return httpx.Response(200, content="".join(chunks).encode("utf-8"), headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        hermes_agent.httpx,
        "AsyncClient",
        lambda *a, **kw: real_async_client(*a, transport=httpx.MockTransport(openrouter_handler), **kw),
    )

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "local_page",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
    )
    with authenticated_client(s) as client:
        res = client.post(
            "/api/hermes/run",
            json={
                "prompt": "Crée une page brouillon sur l'architecture",
                "execution_mode": "local_autonomous",
                "enabled_tools": ["web_search", "create_page"],
                "auto_learn_skill": False,
            },
        )
        assert res.status_code == 200
        assert "clair_create_page" in captured_tool_names
        ev_list = parse_sse_events(res.text)
        artifacts = next(d for name, d in ev_list if name == "artifacts")
        assert len(artifacts["created_pages"]) == 1
        draft_meta = artifacts["created_pages"][0]
        assert draft_meta["is_published"] is False
        assert draft_meta["title"] == "Brouillon Architecture"

        with client.app.state.sessions() as db:
            pages = db.scalars(select(WebPage)).all()
            assert len(pages) == 1
            assert pages[0].is_published is False

    # Vérifie que si generate_page_html échoue, aucun brouillon orphelin n'est persisté
    async def failing_generate_page_html(*args, **kwargs):
        raise providers.ProviderError("Quota Pages dépassé")

    monkeypatch.setattr(page_service, "generate_page_html", failing_generate_page_html)
    turn_counter["n"] = 0
    s_fail = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "local_page_fail",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
    )
    with authenticated_client(s_fail) as client:
        res = client.post(
            "/api/hermes/run",
            json={
                "prompt": "Crée une page qui échoue",
                "execution_mode": "local_autonomous",
                "enabled_tools": ["create_page"],
                "auto_learn_skill": False,
            },
        )
        assert res.status_code == 200
        ev_list = parse_sse_events(res.text)
        artifacts = next(d for name, d in ev_list if name == "artifacts")
        assert artifacts["created_pages"] == []
        with client.app.state.sessions() as db:
            assert db.scalars(select(WebPage)).all() == []


def test_hermes_mcp_adapter_gateway_draft_and_permissions(tmp_path, monkeypatch):
    """Vérifie l'adaptateur MCP officiel (/api/hermes/mcp) pour Hermes Gateway."""
    from app import page_service
    from app.models import WebPage
    from app.routers.hermes_mcp import register_gateway_mission_lease, unregister_gateway_mission_lease
    from app.tool_registry import PERMISSION_CREATE_PAGE_DRAFT

    async def fake_generate_page_html(*args, title="Brouillon", **kwargs):
        return (title or "Brouillon"), f"<!doctype html><html><body><h1>{title}</h1></body></html>"

    monkeypatch.setattr(page_service, "generate_page_html", fake_generate_page_html)

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "mcp_test",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_key=SecretStr("gw-mcp-secret"),
    )
    with authenticated_client(s) as client:
        # 1. Requête sans Bearer -> 401
        unauth = client.post("/api/hermes/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert unauth.status_code == 401

        auth_headers = {"Authorization": "Bearer gw-mcp-secret"}

        # 2. Initialize
        init_res = client.post(
            "/api/hermes/mcp",
            headers=auth_headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert init_res.status_code == 200
        assert init_res.json()["result"]["serverInfo"]["name"] == "clair-tools-mcp"

        # 3. Découverte globale (Bearer valide, sans session) : tools/list expose les schémas,
        # mais aucun droit d'exécution sans bail de mission valide ; avec sess-denied : tools/list est vide.
        list_discovery = client.post(
            "/api/hermes/mcp",
            headers=auth_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert [t["name"] for t in list_discovery.json()["result"]["tools"]] == ["clair_create_page"]

        with client.app.state.sessions() as db:
            user = db.scalar(select(User).where(User.username == "hermes-tester"))
            assert user is not None
            user_id = user.id

        lease_denied = register_gateway_mission_lease("sess-denied", user_id, set(), model="openrouter/test")
        list_denied = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers, "X-Hermes-Session-Id": "sess-denied", "X-Clair-Mission-Token": lease_denied.mission_token},
            json={"jsonrpc": "2.0", "id": 20, "method": "tools/list"},
        )
        assert list_denied.json()["result"]["tools"] == []
        call_denied = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers, "X-Hermes-Session-Id": "sess-denied", "X-Clair-Mission-Token": lease_denied.mission_token},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "clair_create_page",
                    "arguments": {
                        "title": "Interdit",
                        "content": "Contenu suffisamment long mais non autorisé.",
                    },
                },
            },
        )
        assert call_denied.json()["result"]["isError"] is True
        assert unregister_gateway_mission_lease("sess-denied") == []

        # 4. Avec bail autorisé : tools/list expose clair_create_page et tools/call crée un brouillon
        lease_ok = register_gateway_mission_lease(
            "sess-ok", user_id, {PERMISSION_CREATE_PAGE_DRAFT}, model="openrouter/test"
        )
        list_ok = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers, "X-Hermes-Session-Id": "sess-ok", "X-Clair-Mission-Token": lease_ok.mission_token},
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        )
        assert [t["name"] for t in list_ok.json()["result"]["tools"]] == ["clair_create_page"]

        call_ok = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-ok", "mission_token": lease_ok.mission_token},
                    "name": "clair_create_page",
                    "arguments": {
                        "title": "Page Gateway MCP",
                        "content": "Synthèse générée depuis le conteneur Hermes Gateway via MCP.",
                        "sources": [{"title": "cLAIr", "url": "https://example.org/clair"}],
                    },
                },
            },
        )
        rpc_res = call_ok.json()["result"]
        assert rpc_res["isError"] is False
        assert rpc_res["structuredContent"]["success"] is True
        assert rpc_res["structuredContent"]["is_published"] is False

        created = unregister_gateway_mission_lease("sess-ok")
        assert len(created) == 1
        assert created[0]["title"] == "Page Gateway MCP"
        assert created[0]["is_published"] is False

        with client.app.state.sessions() as db:
            pages = db.scalars(select(WebPage)).all()
            assert len(pages) == 1
            assert pages[0].is_published is False


def test_hermes_mcp_isolation_multi_users_and_origin_boundary(tmp_path, monkeypatch):
    """Vérifie l'isolation stricte des baux MCP entre deux utilisateurs et la portée de l'exemption Origin."""
    from uuid import uuid4
    from app import page_service
    from app.models import WebPage
    from app.routers.hermes_mcp import register_gateway_mission_lease, unregister_gateway_mission_lease
    from app.tool_registry import PERMISSION_CREATE_PAGE_DRAFT

    async def fake_generate_page_html(*args, title="Brouillon", **kwargs):
        return (title or "Brouillon"), f"<!doctype html><html><body><h1>{title}</h1></body></html>"

    monkeypatch.setattr(page_service, "generate_page_html", fake_generate_page_html)

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "mcp_isolation",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_key=SecretStr("gw-mcp-secret"),
    )
    with authenticated_client(s) as client:
        with client.app.state.sessions() as db:
            user_a = db.scalar(select(User).where(User.username == "hermes-tester"))
            assert user_a is not None
            user_b = User(
                id=str(uuid4()),
                username="hermes-tester-b",
                password_hash=hash_password("TestPass123!"),
                is_admin=False,
            )
            db.add(user_b)
            db.commit()
            user_a_id = user_a.id
            user_b_id = user_b.id

        # Deux missions actives simultanément : user_a autorisé, user_b non autorisé
        lease_a = register_gateway_mission_lease(
            "sess-user-a", user_a_id, {PERMISSION_CREATE_PAGE_DRAFT}, model="openrouter/test"
        )
        lease_b = register_gateway_mission_lease("sess-user-b", user_b_id, set(), model="openrouter/test")

        auth_headers = {"Authorization": "Bearer gw-mcp-secret"}

        # 1. Appel sans X-Hermes-Session-Id :
        #    - tools/list authentifié expose les schémas pour la découverte globale Hermes (sans droit d'exécution)
        #    - tools/call sans session reste strictement refusé (aucun repli sur sess-user-a)
        no_sid_list = client.post(
            "/api/hermes/mcp",
            headers=auth_headers,
            json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"},
        )
        assert [t["name"] for t in no_sid_list.json()["result"]["tools"]] == ["clair_create_page"]

        no_sid_call = client.post(
            "/api/hermes/mcp",
            headers=auth_headers,
            json={
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "clair_create_page",
                    "arguments": {"title": "Sans session", "content": "Contenu suffisamment long pour le test."},
                },
            },
        )
        assert no_sid_call.json()["result"]["isError"] is True

        # 2. Appel avec la session de user_b -> refusé (n'hérite pas des droits de user_a)
        user_b_call = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-user-b", "mission_token": lease_b.mission_token},
                    "name": "clair_create_page",
                    "arguments": {"title": "Tentative B", "content": "Contenu suffisamment long pour le test."},
                },
            },
        )
        assert user_b_call.json()["result"]["isError"] is True

        # 2bis. Usurpation de session_id de user_a sans son mission_token (ou avec celui de user_b) -> refusé
        spoof_no_tok = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 121,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-user-a"},
                    "name": "clair_create_page",
                    "arguments": {"title": "Usurpation 1", "content": "Contenu suffisamment long pour le test."},
                },
            },
        )
        assert spoof_no_tok.json()["result"]["isError"] is True

        spoof_wrong_tok = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 122,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-user-a", "mission_token": lease_b.mission_token},
                    "name": "clair_create_page",
                    "arguments": {"title": "Usurpation 2", "content": "Contenu suffisamment long pour le test."},
                },
            },
        )
        assert spoof_wrong_tok.json()["result"]["isError"] is True

        # 3. Appel avec la session et le mission_token authentifié de user_a -> crée le brouillon uniquement pour user_a
        user_a_call = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-user-a", "mission_token": lease_a.mission_token},
                    "name": "clair_create_page",
                    "arguments": {"title": "Brouillon A", "content": "Contenu suffisamment long pour le test."},
                },
            },
        )
        assert user_a_call.json()["result"]["isError"] is False

        assert len(unregister_gateway_mission_lease("sess-user-a")) == 1
        assert unregister_gateway_mission_lease("sess-user-b") == []

        with client.app.state.sessions() as db:
            pages = db.scalars(select(WebPage)).all()
            assert len(pages) == 1
            assert pages[0].user_id == user_a_id
            assert pages[0].is_published is False

        # 4. Vérification de l'exemption Origin : limitée strictement à /api/hermes/mcp + auth obligatoire
        with TestClient(client.app, base_url=s.origins[0]) as raw_client:
            mcp_no_origin_no_auth = raw_client.post(
                "/api/hermes/mcp",
                json={"jsonrpc": "2.0", "id": 14, "method": "initialize"},
            )
            assert mcp_no_origin_no_auth.status_code == 401

            other_post_no_origin = raw_client.post(
                "/api/hermes/run",
                json={"prompt": "test"},
            )
            assert other_post_no_origin.status_code == 403


def test_hermes_mcp_tools_list_authorization_and_prefix_normalization(tmp_path, monkeypatch):
    """Vérifie que tools/list n'expose clair_create_page que pour une mission autorisée,
    et que les préfixes MCP (mcp__clair__... et mcp_clair_...) sont correctement résolus.
    """
    from uuid import uuid4
    from app import page_service
    from app.models import WebPage
    from app.routers.hermes_mcp import register_gateway_mission_lease, unregister_gateway_mission_lease
    from app.tool_registry import PERMISSION_CREATE_PAGE_DRAFT

    async def fake_generate_page_html(*args, title="Brouillon", **kwargs):
        return (title or "Brouillon"), f"<!doctype html><html><body><h1>{title}</h1></body></html>"

    monkeypatch.setattr(page_service, "generate_page_html", fake_generate_page_html)

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "mcp_auth",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_key=SecretStr("gw-secret-123"),
    )
    with authenticated_client(s) as client:
        with client.app.state.sessions() as db:
            user = db.scalar(select(User).where(User.username == "hermes-tester"))
            user_id = user.id

        auth_headers = {"Authorization": "Bearer gw-secret-123"}

        # Mission non autorisée (sans permission create_page)
        lease_unauth = register_gateway_mission_lease("sess-unauth", user_id, set(), model="openrouter/test")
        # Mission autorisée
        lease_auth = register_gateway_mission_lease("sess-auth", user_id, {PERMISSION_CREATE_PAGE_DRAFT}, model="openrouter/test")

        # 1. tools/list avec Bearer sans session -> expose les schémas pour découverte (sans droit d'exécution)
        r_anon = client.post("/api/hermes/mcp", headers=auth_headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert r_anon.status_code == 200
        assert [t["name"] for t in r_anon.json()["result"]["tools"]] == ["clair_create_page"]

        # 1bis. tools/list avec session inconnue -> vide
        r_unknown = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers, "X-Hermes-Session-Id": "sess-unknown"},
            json={"jsonrpc": "2.0", "id": 15, "method": "tools/list"},
        )
        assert r_unknown.json()["result"]["tools"] == []

        # 2. tools/list pour mission non autorisée -> vide
        r_unauth = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers, "X-Hermes-Session-Id": "sess-unauth", "X-Clair-Mission-Token": lease_unauth.mission_token},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert r_unauth.json()["result"]["tools"] == []

        # 3. tools/list pour mission autorisée via X-Hermes-Session-Id + X-Clair-Mission-Token -> expose clair_create_page
        r_auth_header = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers, "X-Hermes-Session-Id": "sess-auth", "X-Clair-Mission-Token": lease_auth.mission_token},
            json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
        tools = r_auth_header.json()["result"]["tools"]
        assert len(tools) == 1
        assert tools[0]["name"] == "clair_create_page"

        # 4. tools/list pour mission autorisée via URL /mcp/{session_id} + X-Clair-Mission-Token -> expose clair_create_page
        r_auth_path = client.post(
            "/api/hermes/mcp/sess-auth",
            headers={**auth_headers, "X-Clair-Mission-Token": lease_auth.mission_token},
            json={"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
        )
        assert len(r_auth_path.json()["result"]["tools"]) == 1

        # 5. tools/list pour mission autorisée via query param + X-Clair-Mission-Token -> expose clair_create_page
        r_auth_query = client.post(
            "/api/hermes/mcp?session_id=sess-auth",
            headers={**auth_headers, "X-Clair-Mission-Token": lease_auth.mission_token},
            json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
        )
        assert len(r_auth_query.json()["result"]["tools"]) == 1

        # 6. tools/call avec nom préfixé mcp__clair__clair_create_page et params._meta -> accepté et normalisé
        r_call_prefixed = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-auth", "mission_token": lease_auth.mission_token},
                    "name": "mcp__clair__clair_create_page",
                    "arguments": {
                        "title": "Page Préfixée",
                        "content": "Contenu structuré valide avec plus de 10 caractères.",
                        "page_type": "educational",
                    },
                },
            },
        )
        assert r_call_prefixed.status_code == 200
        res_call = r_call_prefixed.json()["result"]
        assert res_call["isError"] is False
        assert res_call["structuredContent"]["success"] is True
        assert res_call["structuredContent"]["is_published"] is False

        # 7. tools/call pour mission non autorisée -> refusé
        r_call_unauth = client.post(
            "/api/hermes/mcp",
            headers={**auth_headers},
            json={
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "_meta": {"session_id": "sess-unauth", "mission_token": lease_unauth.mission_token},
                    "name": "clair_create_page",
                    "arguments": {
                        "title": "Page Refusée",
                        "content": "Contenu structuré valide avec plus de 10 caractères.",
                    },
                },
            },
        )
        assert r_call_unauth.json()["result"]["isError"] is True

        unregister_gateway_mission_lease("sess-auth")
        unregister_gateway_mission_lease("sess-unauth")


def test_hermes_gateway_integration_creates_unpublished_draft(tmp_path, monkeypatch):
    """Test d'intégration bout-en-bout : création d'un brouillon non publié via Hermes Gateway."""
    from app import page_service
    from app.models import WebPage

    async def fake_generate_page_html(*args, title="Brouillon", **kwargs):
        return (title or "Brouillon"), f"<!doctype html><html><head><title>{title}</title></head><body><h1>{title}</h1></body></html>"

    monkeypatch.setattr(page_service, "generate_page_html", fake_generate_page_html)

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "gw_integration",
        demo_mode=False,
        llm_api_key=SecretStr("sk-or-test"),
        hermes_api_url="http://clair-hermes:8642",
        hermes_api_key=SecretStr("hermes-test-secret"),
    )

    captured_requests: list[dict] = []

    def mock_gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "hermes-agent"}]})
        if request.url.path == "/v1/chat/completions":
            captured_requests.append(
                {
                    "headers": dict(request.headers),
                    "json": json.loads(request.content.decode("utf-8")),
                }
            )
            # Flux SSE simulant Hermes invoquant l'outil clair_create_page via tool_calls
            tool_call_chunk = {
                "id": "gen-hermes-draft-1",
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_create_page_01",
                                    "type": "function",
                                    "function": {
                                        "name": "clair_create_page",
                                        "arguments": json.dumps(
                                            {
                                                "title": "Guide Architecture Hermes",
                                                "content": "Synthèse détaillée des invariants de sécurité et des permissions.",
                                                "page_type": "educational",
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ],
            }
            msg_chunk = {
                "id": "gen-hermes-draft-1",
                "choices": [
                    {
                        "delta": {
                            "content": "J'ai créé le brouillon cLAIr Page pour documenter l'architecture.",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165},
            }
            sse_body = (
                f"data: {json.dumps(tool_call_chunk)}\n\n"
                f"data: {json.dumps(msg_chunk)}\n\n"
                "data: [DONE]\n\n"
            )
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=sse_body)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_gateway_handler)
    real_async_client = httpx.AsyncClient

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(hermes_agent.httpx, "AsyncClient", mock_async_client)

    with authenticated_client(s) as client:
        # Lancement de la mission avec l'outil create_page autorisé
        resp = client.post(
            "/api/hermes/run",
            json={
                "prompt": "Génère un guide d'architecture sous forme de page web",
                "execution_mode": "gateway",
                "enabled_tools": ["web_search", "create_page"],
            },
        )
        assert resp.status_code == 200
        events = parse_sse_events(resp.text)
        event_types = [t for t, _ in events]
        assert "step" in event_types
        assert "done" in event_types

        # Vérification des requêtes envoyées à Hermes Gateway
        assert len(captured_requests) >= 1
        last_req = captured_requests[-1]
        assert "x-hermes-session-id" in last_req["headers"]
        mission_token = last_req["headers"].get("x-clair-mission-token", "")
        assert len(mission_token) >= 20
        # Le secret de mission ne doit jamais apparaître dans le prompt ou les messages envoyés au LLM
        assert mission_token not in json.dumps(last_req["json"])
        # Vérification que tools est bien exposé à Hermes
        req_tools = last_req["json"].get("tools")
        assert req_tools is not None
        tool_names = [t["function"]["name"] for t in req_tools if "function" in t]
        assert "clair_create_page" in tool_names

        # Vérification en base de données : brouillon créé, non publié, lié à l'utilisateur
        with client.app.state.sessions() as db:
            pages = db.scalars(select(WebPage)).all()
            assert len(pages) == 1
            page = pages[0]
            assert page.title == "Guide Architecture Hermes"
            assert page.is_published is False
            assert page.user_id is not None
