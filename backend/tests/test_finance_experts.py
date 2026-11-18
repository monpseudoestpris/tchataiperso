"""Tests unitaires du module « Avis de l'expert » (`backend/app/finance_experts.py`)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import current_user, get_settings
from app.finance_experts import (
    FINANCE_EXPERT_PERSONAS,
    generate_finance_expert_opinion,
    list_finance_experts_and_cached,
)
from app.models import User
from app.routers.finance import router as finance_router


def _mock_dossier() -> dict:
    return {
        "symbol": "AI.PA",
        "currency": "EUR",
        "source_provider": "eodhd",
        "source_label": "EOD Historical Data",
        "header": {
            "name": "Air Liquide SA",
            "cap_category": "Large Cap",
            "market_cap": 95e9,
            "dividend_yield_pct": 1.9,
            "beta": 0.78,
            "ih_score": 7.5,
            "ih_quality": "Solide",
            "ih_trend": "Haussière",
            "price_dynamics": "Positif (+12.4%)",
            "sector": "Basic Materials",
            "industry": "Specialty Chemicals",
            "employees": 67800,
            "website": "https://www.airliquide.com",
            "address": "Paris, France",
            "isin": "FR0000120073",
            "description": "Gaz industriels et médicaux.",
        },
        "capital_valuation": {
            "pe_ttm": 25.0,
            "ev_ebitda": 13.0,
            "op_margin_ttm": 19.5,
            "roe_ttm": 14.5,
        },
        "performance": {"horizons": [{"key": "1y", "label": "1 An", "pct": 12.4}]},
        "performance_chart": [{"date": "2026-11-17", "value": 168.0}],
        "risk": {"horizons": ["1A"], "metrics": []},
        "stakeholders": {"analysts": {"total": 20, "target_price": 190.0}, "officers": [], "insiders": [], "funds": [], "institutions": []},
        "annual_tables": {
            "years": ["2024", "2025"],
            "summary": [],
            "profitability": [],
            "solvency": [],
            "distribution": [],
            "efficiency": [],
            "ih_score": {"years": ["2025"], "criteria": [], "latest_score": 7.5, "quality_label": "Solide", "trend": "Haussière"},
            "piotroski": {"years": ["2025"], "scores": [8], "latest_score": 8},
            "altman": {"years": ["2025"], "scores": [3.4], "latest_score": 3.4},
        },
        "dividends_matrix": {"years": [2025], "rows": [{"year": 2025, "months": [None] * 12, "total": 3.3}]},
        "statements": {
            "annual": {"dates": ["2025-12-31"], "income": [{"key": "TotalRevenue", "label": "Chiffre d'affaires", "values": [27.5e9]}], "balance": [], "cashflow": [], "ratios": []},
            "quarterly": {"dates": [], "income": [], "balance": [], "cashflow": [], "ratios": []},
            "earnings_history": [],
        },
        "news": {"items": []},
        "uncle_stock_scores": {
            "available": True,
            "summary": {"advice_verified": "Buy", "uncle_stock_score_verified": 74.2},
            "items": [{"id": "quality_score", "name": "Quality score", "category": "Scores Uncle Stock", "available": True, "verified": {"display_value": "81.0%"}, "documented": {"display_value": "81.0%"}}],
        },
        "intrinsic_valuation": {
            "available": True,
            "summary": {"corrected": {"intrinsic_value": 195.0, "margin_of_safety_pct": 13.8}},
            "cost_of_capital": {"wacc_pct": 7.4},
            "owner_returns": {"total_owner_return_pct": 5.2},
            "methods": [],
            "scenarios": [],
        },
    }


def test_list_experts_and_demo_opinion_persisted():
    assert len(FINANCE_EXPERT_PERSONAS) == 12
    ids = {e["id"] for e in FINANCE_EXPERT_PERSONAS}
    assert {"warren_buffett", "peter_lynch", "charlie_munger", "benjamin_graham", "aswath_damodaran", "investment_committee"} <= ids

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(_env_file=None, app_data_dir=Path(tmpdir), finance_data_dir=Path(tmpdir) / "fin", demo_mode=True)
        with patch("app.finance_experts.get_financial_dossier", new=AsyncMock(return_value=_mock_dossier())):
            op = asyncio.run(
                generate_finance_expert_opinion(s, "AI.PA", expert_id="warren_buffett", question="Moat durable ?")
            )
        assert op["expert_id"] == "warren_buffett"
        assert op["expert_name"] == "Warren Buffett"
        assert "74.2/100" in op["markdown"]
        assert "+13.8%" in op["markdown"]

        listed = list_finance_experts_and_cached(s, "AI.PA")
        assert len(listed["experts"]) == 12
        assert "warren_buffett" in listed["cached_opinions"]
        assert listed["cached_opinions"]["warren_buffett"]["question"] == "Moat durable ?"


def test_generate_expert_uses_chosen_model_and_all_figures():
    captured_payload: dict = {}

    class _FakeResp:
        status_code = 200
        is_success = True
        def json(self):
            return {"choices": [{"message": {"content": "### 1. Verdict d'expert & Conviction\nAchat fort — PEG attractif."}}]}

    class _FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, headers=None, json=None):
            captured_payload.update(json or {})
            return _FakeResp()

    mock_live_news = {
        "articles": [
            {
                "title": "Air Liquide signe un contrat hydrogène majeur",
                "url": "https://example.com/news-ai",
                "source": "SearXNG",
                "published_at": "2026-11-18",
                "snippet": "Nouvel investissement industriel de 400 M€.",
            }
        ],
        "sources_used": ["EODHD News", "SearXNG"],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "fin",
            llm_api_key="sk-test-key",
            demo_mode=False,
        )
        with (
            patch("app.finance_experts.get_financial_dossier", new=AsyncMock(return_value=_mock_dossier())),
            patch("app.finance_experts.collect_latest_stock_news", new=AsyncMock(return_value=mock_live_news)) as mock_news_fn,
            patch("app.finance_experts.httpx.AsyncClient", return_value=_FakeClient()),
        ):
            op = asyncio.run(
                generate_finance_expert_opinion(
                    s,
                    "AI.PA",
                    expert_id="peter_lynch",
                    model_id="anthropic/claude-sonnet-4",
                    question="Est-ce un Stalwart ou un Fast Grower ?",
                )
            )

    mock_news_fn.assert_awaited_once()
    assert op["model"] == "anthropic/claude-sonnet-4"
    assert op["news_sources"] == ["EODHD News", "SearXNG"]
    assert len(op["news_articles"]) == 1
    assert captured_payload["model"] == "anthropic/claude-sonnet-4"
    prompt = captured_payload["messages"][0]["content"]
    assert "Peter Lynch" in prompt
    assert "Stalwart ou un Fast Grower" in prompt
    assert "Air Liquide signe un contrat hydrogène majeur" in prompt
    assert "scores_unclestock_31" in prompt
    assert "valeurs_intrinseques" in prompt
    assert "27500000000" in prompt


def test_finance_experts_router_endpoints():
    app = FastAPI()
    app.include_router(finance_router, prefix="/api/finance")

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(_env_file=None, app_data_dir=Path(tmpdir), finance_data_dir=Path(tmpdir) / "fin", demo_mode=True)
        fake_user = MagicMock(spec=User)
        fake_user.id = "u-1"
        app.dependency_overrides[get_settings] = lambda: s
        app.dependency_overrides[current_user] = lambda: fake_user

        client = TestClient(app)
        resp_list = client.get("/api/finance/experts?symbol=AI.PA")
        assert resp_list.status_code == 200
        assert len(resp_list.json()["experts"]) == 12

        resp_bad = client.post("/api/finance/dossier/expert", json={"symbol": "AI.PA", "expert_id": "unknown_guru"})
        assert resp_bad.status_code == 400

        with patch("app.finance_experts.get_financial_dossier", new=AsyncMock(return_value=_mock_dossier())):
            resp_ok = client.post(
                "/api/finance/dossier/expert",
                json={"symbol": "AI.PA", "expert_id": "charlie_munger", "model_id": "openai/gpt-4.1"},
            )
            resp_ok2 = client.post(
                "/api/finance/dossier/expert",
                json={
                    "symbol": "AI.PA",
                    "expert_id": "charlie_munger",
                    "model_id": "anthropic/claude-sonnet-4",
                    "question": "Qualité du bilan ?",
                },
            )
        assert resp_ok.status_code == 200
        assert resp_ok2.status_code == 200
        assert resp_ok.json()["expert_id"] == "charlie_munger"
        assert resp_ok.json()["id"] != resp_ok2.json()["id"]
        assert "clair-rep-root" in resp_ok.json()["content_html"]

        listed_after = client.get("/api/finance/experts?symbol=AI.PA").json()
        assert len(listed_after["history"]) == 2
        assert listed_after["history"][0]["question"] == "Qualité du bilan ?"

        hist_resp = client.get("/api/finance/ai-history?symbol=AI.PA&kind=expert")
        assert hist_resp.status_code == 200
        hist_items = hist_resp.json()["items"]
        assert len(hist_items) == 2

        del_resp = client.delete(f"/api/finance/ai-history/{hist_items[0]['id']}")
        assert del_resp.status_code == 204
        assert len(client.get("/api/finance/ai-history?symbol=AI.PA&kind=expert").json()["items"]) == 1


def test_classy_html_report_escapes_xss_and_renders_sections():
    from app.finance_report_html import build_classy_report_html

    md = """### 1. Verdict d'expert & Conviction
- **Décision analytique** : Achat fort
- **Conviction** : `8 / 10`
- **Horizon** : 3-5 ans

### 2. Tableau
| Indicateur | Valeur | Lecture |
|---|---|---|
| ROE | +18.4% | Solide |

### 3. Ce qui séduit
- Moat large <script>alert(1)</script>

### 4. Risques & Red Flags
- Dette contrôlée [lien malicieux](javascript:alert(1))
"""
    rendered = build_classy_report_html(
        md,
        title="Avis de Warren Buffett — Air Liquide",
        symbol="AI.PA",
        model="gemini-hydrogen",
        created_at="2026-11-18T12:00:00Z",
        accent="#059669",
        monogram="WB",
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "javascript:" not in rendered
    assert "clair-rep-verdict-pill is-bull" in rendered
    assert "clair-rep-card is-bull" in rendered
    assert "clair-rep-card is-bear" in rendered
    assert "clair-rep-pos" in rendered
    assert "width:80%" in rendered
