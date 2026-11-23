"""Tests de l'agent d'outils Finance (`finance_chat_agent.py`) et de la propagation `thoughtSignature`."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

from app.config import Settings
from app.context import build_context
from app.finance_chat_agent import (
    should_enable_finance_tools,
    should_suppress_auto_web_search,
    stream_finance_chat_turn,
)
from app.finance_chat_tools import FinanceToolContext
from app.google_cloud import (
    gemini_native_to_openai_dict,
    iter_gemini_sse_as_openai_data,
    openai_to_gemini_native_request,
)
from tests.test_finance_chat_tools import _setup_fixture


def test_intent_detection_and_web_suppression():
    # Détection positive y compris fautes de frappe et cashtags
    assert should_enable_finance_tools(
        "toutes les actions francaises qui ont un score de puotrosky > 5 et RSI plus petit que 40"
    )
    assert should_enable_finance_tools("IsoPressure 20 > 50 sur l'unité semaine")
    assert should_enable_finance_tools("Analyse ma watchlist PEA")
    assert should_enable_finance_tools("Que vaut $NVDA en marge de sécurité ?")
    assert should_enable_finance_tools("Compare les résultats de AI.PA")

    # Continuité conversationnelle sur un tour suivant court
    history_fin = [
        {"role": "user", "content": "Actions françaises Piotroski > 5"},
        {
            "role": "assistant",
            "content": "Voici le tableau.",
            "sources": [{"provider": "finance_warehouse", "title": "Entrepôt"}],
        },
    ]
    assert should_enable_finance_tools("Et en semaine avec son MOAT ?", history_fin)

    # Messages non financiers : aucun déclenchement
    assert not should_enable_finance_tools("Écris un poème sur l'automne")
    assert not should_enable_finance_tools("Donne-moi une recette de crêpes")

    # Suppression Web Auto pour requêtes entrepôt (y compris relance multi-tour), mais conservée si recherche web explicite
    assert should_suppress_auto_web_search("actions françaises Piotroski > 5 et RSI < 40")
    assert should_suppress_auto_web_search("et en semaine ?", finance_mode=False, finance_tools_active=True) is True
    assert should_suppress_auto_web_search("cherche sur internet les actualités récentes d'Air Liquide") is False
    assert (
        should_suppress_auto_web_search(
            "cherche sur le web les dernières nouvelles",
            finance_mode=False,
            finance_tools_active=True,
        )
        is False
    )


def test_gemini_thought_signature_roundtrip():
    native_resp = {
        "responseId": "resp-1",
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Réflexion interne", "thought": True},
                        {
                            "functionCall": {"name": "finance_screener_query", "args": {"country": "France"}},
                            "thoughtSignature": "sig-abc-123",
                        },
                    ]
                },
                "finishReason": "STOP",
            }
        ],
    }
    openai_msg = gemini_native_to_openai_dict(native_resp, "gemini-4-neon")
    tc = openai_msg["choices"][0]["message"]["tool_calls"][0]
    assert tc["thought_signature"] == "sig-abc-123"
    assert tc["extra_content"]["google"]["thought_signature"] == "sig-abc-123"

    rebuilt_native = openai_to_gemini_native_request(
        {
            "model": "gemini-4-neon",
            "messages": [
                {"role": "user", "content": "Actions françaises ?"},
                openai_msg["choices"][0]["message"],
                {"role": "tool", "tool_call_id": tc["id"], "name": "finance_screener_query", "content": '{"total": 1}'},
            ],
        },
        bare_model="gemini-4-neon",
    )
    model_parts = rebuilt_native["contents"][1]["parts"]
    assert model_parts[0]["thoughtSignature"] == "sig-abc-123"
    assert model_parts[0]["functionCall"]["name"] == "finance_screener_query"

    # Vérifier aussi le flux SSE
    sse_payload = json.dumps(native_resp, ensure_ascii=False)

    class _FakeResp:
        async def aiter_lines(self):
            yield f"data: {sse_payload}"
            yield ""
            yield "data: [DONE]"
            yield ""

    async def _collect():
        out = []
        async for item in iter_gemini_sse_as_openai_data(_FakeResp(), "gemini-4-neon"):
            out.append(item)
        return out

    chunks = asyncio.run(_collect())
    first_chunk = json.loads(chunks[0])
    assert first_chunk["choices"][0]["delta"]["tool_calls"][0]["thought_signature"] == "sig-abc-123"


def test_stream_finance_chat_turn_react_loop(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    settings.llm_api_key = "test-key"  # type: ignore[assignment]
    ctx = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    captured_payloads: list[dict] = []

    @asynccontextmanager
    async def fake_open_chat_stream(s, payload, **kwargs):
        captured_payloads.append(payload)
        turn_num = len(captured_payloads)
        resp = httpx.Response(200)

        async def _iter():
            if turn_num == 1:
                yield json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": "call_scr_1",
                                            "thought_signature": "sig-turn-1",
                                            "function": {
                                                "name": "finance_screener_query",
                                                "arguments": json.dumps(
                                                    {
                                                        "country": "France",
                                                        "rules": [
                                                            {"kind": "metric", "field": "piotroski_f", "op": "gt", "value": 5},
                                                            {"kind": "metric", "field": "rsi_14", "op": "lt", "value": 40},
                                                        ],
                                                    }
                                                ),
                                            },
                                        }
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ]
                    }
                )
            else:
                yield json.dumps(
                    {
                        "choices": [
                            {
                                "delta": {"content": "Voici [AI.PA](clair-finance://ticker/AI.PA) (Piotroski > 5, RSI < 40)."},
                                "finish_reason": "stop",
                            }
                        ]
                    }
                )
            yield "[DONE]"

        yield resp, _iter(), "OpenRouter"

    messages = build_context(
        settings,
        summary="",
        memories=[],
        messages=[{"role": "user", "content": "Actions françaises Piotroski > 5 et RSI < 40 ?", "attachments": []}],
        sources=[],
        vision=False,
        finance_tools_active=True,
    )

    async def _run():
        events = []
        with patch("app.finance_chat_agent.open_chat_stream", new=fake_open_chat_stream):
            async for ev in stream_finance_chat_turn(
                settings=settings,
                model="openai/gpt-5",
                messages=messages,
                tool_ctx=ctx,
            ):
                events.append(ev)
        return events

    events = asyncio.run(_run())
    assert len(captured_payloads) == 2

    # Vérifier que le tour 2 a bien reçu l'appel outil + thought_signature + résultat réel AI.PA
    second_msgs = captured_payloads[1]["messages"]
    tool_msgs = [m for m in second_msgs if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    tool_json = json.loads(tool_msgs[0]["content"])
    assert tool_json["items"][0]["symbol"] == "AI.PA"

    assistant_tc_msgs = [m for m in second_msgs if m.get("role") == "assistant" and m.get("tool_calls")]
    assert assistant_tc_msgs[0]["tool_calls"][0]["thought_signature"] == "sig-turn-1"

    deltas = "".join(e["text"] for e in events if e.get("type") == "delta")
    assert "AI.PA" in deltas
    done_ev = [e for e in events if e.get("type") == "done"][-1]
    assert any(src.get("provider") == "finance_warehouse" for src in done_ev["sources"])


def test_stream_finance_chat_turn_fallback_when_tools_unsupported(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    settings.llm_api_key = "test-key"  # type: ignore[assignment]
    ctx = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    @asynccontextmanager
    async def fake_open_chat_stream_400(s, payload, **kwargs):
        async def _empty():
            if False:
                yield ""

        yield httpx.Response(400), _empty(), "OpenRouter"

    async def fake_router(s, q, turns):
        return [{"name": "finance_screener_query", "arguments": {"country": "France"}}]

    captured_final_messages: list[dict] = []

    async def fake_stream_chat_events(s, msgs, model, **kwargs):
        captured_final_messages.extend(msgs)
        yield {"type": "delta", "text": "Réponse compatibilité avec AI.PA."}

    messages = build_context(
        settings,
        summary="",
        memories=[],
        messages=[{"role": "user", "content": "Actions françaises", "attachments": []}],
        sources=[],
        vision=False,
        finance_tools_active=True,
    )

    async def _run():
        events = []
        with (
            patch("app.finance_chat_agent.open_chat_stream", new=fake_open_chat_stream_400),
            patch("app.finance_chat_agent._plan_finance_tools_via_json_router", new=fake_router),
            patch("app.finance_chat_agent.providers.stream_chat_events", new=fake_stream_chat_events),
        ):
            async for ev in stream_finance_chat_turn(
                settings=settings,
                model="legacy/no-tools-model",
                messages=messages,
                tool_ctx=ctx,
            ):
                events.append(ev)
        return events

    events = asyncio.run(_run())
    assert any("AI.PA" in m.get("content", "") for m in captured_final_messages if isinstance(m.get("content"), str))
    assert any(e.get("type") == "delta" and "compatibilité" in e.get("text", "") for e in events)
    done_ev = [e for e in events if e.get("type") == "done"][-1]
    assert any(src.get("provider") == "finance_warehouse" for src in done_ev["sources"])


def test_messages_router_e2e_finance_tools_and_web_suppression(tmp_path: Path, monkeypatch):
    """Vérifie le branchement bout en bout dans `POST /api/conversations/{id}/messages`."""
    from app import providers as app_providers
    from app.routers import messages as msg_router
    from tests.test_api import authenticated_client, events as parse_sse

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        database_url=f"sqlite:///{tmp_path}/chat.db",
        demo_mode=False,
        llm_api_key="secret",
        searxng_url="http://clair-searxng:8080",
        auto_web_search=True,
    )

    called_decide_web = False
    called_legacy_finance = False

    async def fail_decide_web(*args, **kwargs):
        nonlocal called_decide_web
        called_decide_web = True
        return True, "Should not run"

    async def fail_legacy_finance(*args, **kwargs):
        nonlocal called_legacy_finance
        called_legacy_finance = True
        return []

    async def fake_stream_finance_turn(*, settings, model, messages, tool_ctx, **kwargs):
        assert any("FINANCE" in m["content"].upper() for m in messages if m["role"] == "system")
        tool_ctx.track_symbol("AI.PA")
        yield {"type": "status", "message": "🔍 Screener Finance : France…"}
        yield {"type": "delta", "text": "Action retenue : [AI.PA](clair-finance://ticker/AI.PA)."}
        yield {
            "type": "done",
            "sources": [
                {
                    "title": "Entrepôt Finance · AI.PA (AI.PA)",
                    "url": "clair-finance://ticker/AI.PA",
                    "snippet": "Données locales consultées.",
                    "provider": "finance_warehouse",
                }
            ],
        }

    async def fake_classify(*args, **kwargs):
        return {"title": "Screening France", "theme": "Finance & Droit", "keywords": ["screener"]}

    monkeypatch.setattr(app_providers, "decide_web_search", fail_decide_web)
    monkeypatch.setattr(msg_router, "process_message_finance_inquiries", fail_legacy_finance)
    monkeypatch.setattr(msg_router, "stream_finance_chat_turn", fake_stream_finance_turn)
    monkeypatch.setattr(app_providers, "classify_conversation", fake_classify)

    with authenticated_client(settings) as client:
        conv_id = client.post("/api/conversations", json={"model": settings.default_model}).json()["id"]
        resp = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "content": "Donne toutes les actions francaises avec score de puotrosky > 5 et RSI < 40",
                "model": settings.default_model,
            },
        )
        assert resp.status_code == 200, resp.text
        parsed = parse_sse(resp)
        assert parsed[-1][0] == "done"
        saved_msg = parsed[-1][1]["message"]
        assert "AI.PA" in saved_msg["content"]
        assert any(s.get("provider") == "finance_warehouse" for s in saved_msg["sources"])
        assert called_decide_web is False
        assert called_legacy_finance is False
