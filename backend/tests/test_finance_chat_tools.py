"""Tests complets des 8 outils Finance en lecture seule (`finance_chat_tools.py`)."""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.finance_chat_tools import (
    FINANCE_CHAT_TOOLS,
    FinanceToolContext,
    execute_finance_tool,
)
from app.finance_screener import rebuild_screener_snapshots_from_warehouse
from app.finance_warehouse import (
    replace_exchange_symbols,
    save_ai_analysis_entry,
    save_index_constituents,
    save_snapshot,
    upsert_eod_bars,
    upsert_fundamental_facts,
    upsert_instrument,
    upsert_screener_snapshots,
    warehouse_db_path,
)
from app.models import (
    Base,
    FinanceCustomIndicator,
    FinanceQuarterlyReport,
    FinanceStockMoat,
    FinanceStockNews,
    FinanceWatchlist,
    FinanceWatchlistItem,
    User,
)


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=False,
    )


def _make_bars_with_drop(count: int = 240) -> list[dict]:
    """Génère une série haussière suivie d'une chute marquée (RSI < 40)."""
    base = datetime.date(2025, 1, 2)
    out = []
    for i in range(count):
        if i < count - 15:
            c = 100.0 + i * 0.3
        else:
            c = max(20.0, 100.0 + (count - 15) * 0.3 - (i - (count - 15) + 1) * 4.5)
        out.append(
            {
                "date": (base + datetime.timedelta(days=i)).isoformat(),
                "open": c + 0.5,
                "high": c + 1.2,
                "low": max(1.0, c - 1.2),
                "close": c,
                "adjusted_close": c,
                "volume": 350_000,
            }
        )
    return out


def _make_bars_uptrend(count: int = 560) -> list[dict]:
    """Génère une série de 80+ semaines avec accélération haussière récente (IsoPressure 20 > 50)."""
    base = datetime.date(2024, 1, 2)
    out = []
    for i in range(count):
        if i < count - 150:
            c = 100.0 + (i % 7) * 0.2
        else:
            step = i - (count - 150)
            c = 100.0 + step * 0.8 + (step ** 1.3) * 0.08
        out.append(
            {
                "date": (base + datetime.timedelta(days=i)).isoformat(),
                "open": c - 0.5,
                "high": c + 1.4,
                "low": max(1.0, c - 1.1),
                "close": c,
                "adjusted_close": c,
                "volume": 280_000 + (i * 150 if i >= count - 150 else 0),
            }
        )
    return out


def _seed_annual_fundamentals(db_path: Path, symbol: str, currency: str = "EUR") -> None:
    series = {
        "TotalRevenue": {"2022-12-31": 20e9, "2023-12-31": 22e9, "2024-12-31": 25e9, "2025-12-31": 28e9},
        "GrossProfit": {"2022-12-31": 11e9, "2023-12-31": 12.5e9, "2024-12-31": 14.5e9, "2025-12-31": 16.8e9},
        "OperatingIncome": {"2022-12-31": 3.5e9, "2023-12-31": 4.0e9, "2024-12-31": 4.8e9, "2025-12-31": 5.6e9},
        "NetIncome": {"2022-12-31": 2.4e9, "2023-12-31": 2.8e9, "2024-12-31": 3.4e9, "2025-12-31": 4.0e9},
        "OperatingCashFlow": {"2022-12-31": 3.8e9, "2023-12-31": 4.3e9, "2024-12-31": 5.1e9, "2025-12-31": 5.9e9},
        "CapitalExpenditure": {"2022-12-31": -1.2e9, "2023-12-31": -1.3e9, "2024-12-31": -1.4e9, "2025-12-31": -1.5e9},
        "TotalAssets": {"2022-12-31": 40e9, "2023-12-31": 42e9, "2024-12-31": 44e9, "2025-12-31": 46e9},
        "CurrentAssets": {"2022-12-31": 12e9, "2023-12-31": 13e9, "2024-12-31": 14e9, "2025-12-31": 15.5e9},
        "CurrentLiabilities": {"2022-12-31": 8e9, "2023-12-31": 8.1e9, "2024-12-31": 8.2e9, "2025-12-31": 8.0e9},
        "LongTermDebt": {"2022-12-31": 9e9, "2023-12-31": 8.5e9, "2024-12-31": 8.0e9, "2025-12-31": 7.2e9},
        "TotalDebt": {"2022-12-31": 10e9, "2023-12-31": 9.5e9, "2024-12-31": 9.0e9, "2025-12-31": 8.0e9},
        "CashAndCashEquivalents": {"2022-12-31": 2.5e9, "2023-12-31": 3.0e9, "2024-12-31": 3.5e9, "2025-12-31": 4.2e9},
        "StockholdersEquity": {"2022-12-31": 20e9, "2023-12-31": 21.5e9, "2024-12-31": 23e9, "2025-12-31": 25e9},
        "RetainedEarnings": {"2022-12-31": 12e9, "2023-12-31": 13.5e9, "2024-12-31": 15e9, "2025-12-31": 17e9},
        "CommonStockSharesOutstanding": {"2022-12-31": 520e6, "2023-12-31": 520e6, "2024-12-31": 518e6, "2025-12-31": 515e6},
        "DilutedEPS": {"2022-12-31": 4.6, "2023-12-31": 5.38, "2024-12-31": 6.56, "2025-12-31": 7.77},
        "EBITDA": {"2022-12-31": 5.2e9, "2023-12-31": 5.9e9, "2024-12-31": 6.8e9, "2025-12-31": 7.8e9},
    }
    stmt_map = {k: "income" for k in series}
    upsert_fundamental_facts(db_path, symbol, "annual", series, stmt_map, "eodhd", currency=currency)
    save_snapshot(
        db_path,
        symbol,
        "eodhd",
        "fundamentals",
        {
            "General": {
                "Code": symbol.split(".")[0],
                "Exchange": symbol.split(".")[1] if "." in symbol else "PA",
                "Name": f"Société {symbol}",
                "CurrencyCode": currency,
                "CountryName": "France" if symbol.endswith(".PA") else "USA",
                "Sector": "Industrials",
                "Industry": "Specialty Chemicals",
                "ISIN": f"FR0000{symbol[:4]}",
            },
            "Highlights": {
                "MarketCapitalization": 45_000_000_000,
                "PERatio": 14.5,
                "DividendYield": 0.024,
                "OperatingMarginTTM": 0.20,
                "ProfitMargin": 0.142,
                "ReturnOnEquityTTM": 0.16,
                "WallStreetTargetPrice": 195.0,
            },
            "Valuation": {"TrailingPE": 14.5, "ForwardPE": 13.0, "EnterpriseValueEbitda": 9.2, "PriceBookMRQ": 1.8},
            "SharesStats": {"SharesOutstanding": 515_000_000},
        },
        None,
        currency=currency,
    )


def _setup_fixture(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)

    # Instruments FR et US
    for sym, name, country, exch, curr in [
        ("AI.PA", "Air Liquide", "France", "PA", "EUR"),
        ("MC.PA", "LVMH", "France", "PA", "EUR"),
        ("SU.PA", "Schneider Electric", "France", "PA", "EUR"),
        ("AAPL.US", "Apple Inc", "États-Unis", "US", "USD"),
    ]:
        upsert_instrument(
            db_path,
            {
                "symbol": sym,
                "eod_ticker": sym,
                "yahoo_symbol": sym[:-3] if sym.endswith(".US") else sym,
                "short_name": name,
                "long_name": name,
                "exchange": exch,
                "currency": curr,
                "country": country,
                "sector": "Industrials" if sym != "AAPL.US" else "Technology",
            },
        )

    upsert_eod_bars(db_path, "AI.PA", _make_bars_with_drop(240), "eodhd")
    upsert_eod_bars(db_path, "MC.PA", _make_bars_uptrend(560), "eodhd")
    upsert_eod_bars(db_path, "SU.PA", _make_bars_with_drop(240), "eodhd")
    upsert_eod_bars(db_path, "AAPL.US", _make_bars_with_drop(240), "eodhd")

    _seed_annual_fundamentals(db_path, "AI.PA", "EUR")
    _seed_annual_fundamentals(db_path, "MC.PA", "EUR")
    _seed_annual_fundamentals(db_path, "SU.PA", "EUR")
    _seed_annual_fundamentals(db_path, "AAPL.US", "USD")

    save_index_constituents(
        db_path,
        "CAC40",
        [
            {"symbol": "AI.PA", "eod_ticker": "AI.PA", "yahoo_symbol": "AI.PA", "name": "Air Liquide", "weight_pct": 8.5},
            {"symbol": "MC.PA", "eod_ticker": "MC.PA", "yahoo_symbol": "MC.PA", "name": "LVMH", "weight_pct": 11.2},
            {"symbol": "SU.PA", "eod_ticker": "SU.PA", "yahoo_symbol": "SU.PA", "name": "Schneider Electric", "weight_pct": 7.4},
        ],
    )
    replace_exchange_symbols(
        db_path,
        "PA",
        [
            {"symbol": "AI", "name": "Air Liquide", "country": "France", "currency": "EUR", "type": "Common Stock", "isin": "FR0000120073"},
            {"symbol": "MC", "name": "LVMH", "country": "France", "currency": "EUR", "type": "Common Stock", "isin": "FR0000121014"},
            {"symbol": "VIE", "name": "Veolia Environnement", "country": "France", "currency": "EUR", "type": "Common Stock", "isin": "FR0000124141"},
        ],
    )

    rebuild_screener_snapshots_from_warehouse(db_path)
    # Ajuster piotroski_f de SU.PA à 3 pour tester le filtrage > 5
    upsert_screener_snapshots(
        db_path,
        [
            {
                "symbol": "SU.PA",
                "eod_ticker": "SU.PA",
                "yahoo_symbol": "SU.PA",
                "name": "Schneider Electric",
                "exchange": "PA",
                "country": "France",
                "market_zone": "europe",
                "currency": "EUR",
                "sector": "Industrials",
                "piotroski_f": 3,
                "has_fundamentals": 1,
                "computed_at": "2026-11-22T00:00:00Z",
            }
        ],
        preserve_fundamentals_if_missing=True,
    )

    save_ai_analysis_entry(
        db_path,
        symbol="AI.PA",
        company_name="Air Liquide",
        kind="expert",
        expert_id="buffett",
        expert_name="Warren Buffett",
        model="google/gemini-4-hydrogen",
        verdict="Achat long terme",
        conviction="8/10",
        horizon="10 ans",
        markdown="### Avis Warren Buffett\nAir Liquide possède un fossé économique solide sur les gaz industriels.",
    )
    save_snapshot(
        db_path,
        "AI.PA",
        "eodhd",
        "news",
        [],
        {
            "source": "EOD Historical Data",
            "provider": "eodhd",
            "items": [
                {
                    "title": "Air Liquide signe un contrat hydrogène majeur",
                    "source": "Reuters",
                    "published_at": "2026-11-20 10:00",
                    "snippet": "Nouveau contrat de long terme en Europe.",
                    "url": "https://example.com/ai-news",
                }
            ],
        },
    )

    # SQLAlchemy DB in-memory avec 2 utilisateurs distincts
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with SessionLocal() as db:
        u1 = User(id="user-1", username="user1", password_hash="x", active=True)
        u2 = User(id="user-2", username="user2", password_hash="x", active=True)
        db.add_all([u1, u2])
        db.flush()

        wl1 = FinanceWatchlist(id="wl-1", user_id="user-1", name="PEA France", position=0)
        wl2 = FinanceWatchlist(id="wl-2", user_id="user-2", name="Liste Secrète U2", position=0)
        db.add_all([wl1, wl2])
        db.flush()

        db.add_all(
            [
                FinanceWatchlistItem(
                    user_id="user-1",
                    list_id="wl-1",
                    symbol="AI.PA",
                    eod_ticker="AI.PA",
                    yahoo_symbol="AI.PA",
                    name="Air Liquide",
                    exchange="PA",
                    currency="EUR",
                    note="Cœur de portefeuille",
                    position=0,
                ),
                FinanceWatchlistItem(
                    user_id="user-2",
                    list_id="wl-2",
                    symbol="AAPL.US",
                    eod_ticker="AAPL.US",
                    yahoo_symbol="AAPL",
                    name="Apple Inc",
                    exchange="US",
                    currency="USD",
                    note="Secret U2",
                    position=0,
                ),
            ]
        )
        db.add(
            FinanceCustomIndicator(
                user_id="user-1",
                name="Mon RSI Lissé",
                formula="EMA(RSI(14), 5)",
                pane="oscillator",
            )
        )
        db.add_all(
            [
                FinanceStockMoat(
                    user_id="user-1",
                    symbol="AI.PA",
                    company_name="Air Liquide",
                    moat_rating="wide",
                    moat_score=86,
                    pillars=[{"name": "Coûts de transfert", "score": 9}],
                    strengths=["Contrats 15 ans"],
                    weaknesses=["Intensité capitalistique"],
                    summary_markdown="Large avantage concurrentiel dans les gaz industriels.",
                ),
                FinanceStockMoat(
                    user_id="user-2",
                    symbol="AAPL.US",
                    company_name="Apple Inc",
                    moat_rating="wide",
                    moat_score=92,
                    summary_markdown="Analyse secrète U2.",
                ),
                FinanceQuarterlyReport(
                    user_id="user-1",
                    symbol="AI.PA",
                    company_name="Air Liquide",
                    title="Résultats T3 2026",
                    period_label="Q3 2026",
                    source_type="pdf",
                    extracted_text="Le chiffre d'affaires hydrogène progresse de 14 % sur le trimestre.",
                    summary_markdown="Croissance organique solide au T3 2026.",
                    key_metrics={"revenue_growth_pct": 14.0},
                ),
                FinanceStockNews(
                    user_id="user-1",
                    symbol="AI.PA",
                    company_name="Air Liquide",
                    search_query="Air Liquide hydrogène",
                    summary_markdown="Synthèse veille : accélération sur l'hydrogène décarboné.",
                    articles=[],
                ),
            ]
        )
        db.commit()

    return settings, SessionLocal


def test_tool_schemas_are_flat_and_gemini_compatible():
    assert len(FINANCE_CHAT_TOOLS) == 8
    for tool in FINANCE_CHAT_TOOLS:
        raw = str(tool)
        assert "$defs" not in raw
        assert "anyOf" not in raw
        assert tool["type"] == "function"


def test_screener_tool_french_piotroski_and_rsi_and_coverage(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    ctx = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    res = asyncio.run(
        execute_finance_tool(
            "finance_screener_query",
            {
                "country": "France",
                "rules": [
                    {"kind": "metric", "field": "puotrosky", "op": ">", "value": 5},
                    {"kind": "metric", "field": "rsi", "op": "<", "value": 40},
                ],
                "sort_by": "piotroski_f",
                "sort_dir": "desc",
            },
            ctx,
        )
    )
    syms = [it["symbol"] for it in res["items"]]
    assert syms == ["AI.PA"]
    assert res["total"] == 1
    assert res["with_fundamentals_count"] == 3  # AI.PA, MC.PA, SU.PA
    assert res["missing_data_count"] == 1  # VIE.PA du catalogue PA
    assert res["items"][0]["piotroski_f"] > 5
    assert res["items"][0]["rsi_14"] < 40


def test_screener_tool_weekly_isopressure_and_uncle_stock_score(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    ctx = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    # 1. Test multi-unités semaine IsoPressure 20 > 50 (MC.PA haussière)
    res_iso = asyncio.run(
        execute_finance_tool(
            "finance_screener_query",
            {
                "country": "France",
                "timeframe": "semaine",
                "rules": [
                    {"kind": "compare", "left": "isopressure_p20", "op": "gt", "right": "isopressure_p50"}
                ],
            },
            ctx,
        )
    )
    assert "MC.PA" in [it["symbol"] for it in res_iso["items"]]

    # 2. Test filtrage direct sur un des 31 scores Uncle Stock peuplés dans scores_json
    res_score = asyncio.run(
        execute_finance_tool(
            "finance_screener_query",
            {
                "country": "France",
                "rules": [
                    {"kind": "score", "field": "quality_score", "op": "gte", "value": 10}
                ],
                "sort_by": "score:quality_score",
            },
            ctx,
        )
    )
    assert res_score["total"] >= 1
    assert "quality_score" in (res_score["items"][0].get("scores") or {})


def test_screener_tool_watchlist_and_user_isolation_and_sqli_guard(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    ctx_u1 = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    res_wl = asyncio.run(
        execute_finance_tool("finance_screener_query", {"watchlist": "PEA France"}, ctx_u1)
    )
    assert [it["symbol"] for it in res_wl["items"]] == ["AI.PA"]

    # user-1 ne peut pas voir la watchlist de user-2
    res_other = asyncio.run(
        execute_finance_tool("finance_screener_query", {"watchlist": "Liste Secrète U2"}, ctx_u1)
    )
    assert "error" in res_other
    assert res_other["available_watchlists"] == ["PEA France"]

    # Rejet strict des champs/opérateurs/scores hors whitelist
    bad_field = asyncio.run(
        execute_finance_tool(
            "finance_screener_query",
            {"rules": [{"kind": "metric", "field": "price; DROP TABLE users;--", "op": "gt", "value": 1}]},
            ctx_u1,
        )
    )
    assert "error" in bad_field

    bad_score = asyncio.run(
        execute_finance_tool(
            "finance_screener_query",
            {"rules": [{"kind": "score", "field": "unknown_score') OR 1=1--", "op": "gt", "value": 1}]},
            ctx_u1,
        )
    )
    assert "error" in bad_score


def test_overview_watchlists_indices_analyses_news_and_catalog(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    ctx = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    ov = asyncio.run(execute_finance_tool("finance_get_warehouse_overview", {}, ctx))
    assert ov["screener_coverage"]["with_fundamentals"] >= 3
    assert [w["name"] for w in ov["user_watchlists"]] == ["PEA France"]
    assert ov["user_custom_indicators"][0]["name"] == "Mon RSI Lissé"

    wls = asyncio.run(execute_finance_tool("finance_get_watchlists", {}, ctx))
    assert len(wls["watchlists"]) == 1
    assert wls["watchlists"][0]["items"][0]["note"] == "Cœur de portefeuille"
    assert wls["watchlists"][0]["items"][0]["piotroski_f"] is not None

    idx_list = asyncio.run(execute_finance_tool("finance_get_indices", {}, ctx))
    assert any(i["code"] == "CAC40" for i in idx_list["indices"])

    cac = asyncio.run(execute_finance_tool("finance_get_indices", {"index_code": "CAC40"}, ctx))
    assert cac["total_constituents"] == 3
    assert any(it["symbol"] == "AI.PA" and it["piotroski_f"] is not None for it in cac["items"])

    analyses = asyncio.run(
        execute_finance_tool("finance_get_saved_analyses", {"query": "hydrogène"}, ctx)
    )
    kinds = {it["kind"] for it in analyses["items"]}
    assert {"report", "news"}.issubset(kinds)
    # Isolation : jamais de MOAT appartenant à user-2
    all_analyses = asyncio.run(execute_finance_tool("finance_get_saved_analyses", {}, ctx))
    assert all(it.get("summary_markdown") != "Analyse secrète U2." for it in all_analyses["items"])

    news = asyncio.run(execute_finance_tool("finance_get_news", {"symbol": "AI.PA"}, ctx))
    assert len(news["cached_feed"]["items"]) == 1
    assert len(news["saved_news_syntheses"]) == 1

    cat = asyncio.run(execute_finance_tool("finance_search_catalog", {"query": "Veolia"}, ctx))
    assert any(it["eod_ticker"] == "VIE.PA" for it in cat["items"])


def test_stock_dossier_local_zero_network_and_live_cap(tmp_path: Path):
    settings, SessionLocal = _setup_fixture(tmp_path)
    ctx = FinanceToolContext(settings=settings, sessions=SessionLocal, user_id="user-1")

    # 1. Titre en cache : 100 % local sans aucun appel get_financial_dossier réseau
    with patch("app.finance_chat_tools.get_financial_dossier", new=AsyncMock(side_effect=AssertionError("Pas de réseau attendu"))):
        res = asyncio.run(
            execute_finance_tool(
                "finance_get_stock_dossier",
                {
                    "symbol": "AI.PA",
                    "sections": ["summary", "technicals", "scores", "intrinsic", "statements", "uncle_stock_ratios"],
                    "ratios_query": "ROIC",
                },
                ctx,
            )
        )
    assert res["loaded_live"] is False
    assert res["symbol"] == "AI.PA"
    assert "week" in res["technicals"]
    assert res["scores"]["piotroski"]["latest_score"] is not None
    assert res["intrinsic"]["available"] is True
    assert res["uncle_stock_ratios"]["computed_count"] > 0
    assert res["uncle_stock_ratios"]["matched_count"] >= 1

    # 1b. Titre absent du cache avec allow_live_fetch=False : aucun appel réseau ni incrément du quota
    with patch(
        "app.finance_chat_tools.get_financial_dossier",
        new=AsyncMock(side_effect=AssertionError("Pas de réseau quand allow_live_fetch=False")),
    ):
        r0 = asyncio.run(
            execute_finance_tool(
                "finance_get_stock_dossier",
                {"symbol": "ORA.PA", "allow_live_fetch": False},
                ctx,
            )
        )
    assert "error" in r0
    assert ctx.live_dossier_fetches == 0

    # 2. Titres absents du cache : maximum 2 chargements live par tour
    mock_live = AsyncMock(
        side_effect=lambda s, sym, refresh=False: {
            "symbol": sym,
            "currency": "EUR",
            "source_provider": "eodhd",
            "header": {"name": f"Live {sym}"},
            "capital_valuation": {"price": 50.0},
            "performance": {"horizons": []},
            "risk": {"horizons": [], "metrics": []},
            "annual_tables": {"years": [], "ih_score": {}, "piotroski": {}, "altman": {}},
            "uncle_stock_scores": {"available": False, "items": []},
            "intrinsic_valuation": {"available": False, "methods": []},
            "stakeholders": {},
        }
    )
    with patch("app.finance_chat_tools.get_financial_dossier", new=mock_live):
        r1 = asyncio.run(execute_finance_tool("finance_get_stock_dossier", {"symbol": "ORA.PA"}, ctx))
        r2 = asyncio.run(execute_finance_tool("finance_get_stock_dossier", {"symbol": "BNP.PA"}, ctx))
        r3 = asyncio.run(execute_finance_tool("finance_get_stock_dossier", {"symbol": "ACA.PA"}, ctx))

    assert r1["loaded_live"] is True
    assert r2["loaded_live"] is True
    assert "error" in r3
    assert mock_live.await_count == 2
