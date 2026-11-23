"""Tests des sources unifiées de synchro (cours quotidiens vs fondamentales progressives)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.finance_eodhd_usage import estimate_daily_sync_cost
from app.finance_fundamentals_queue import PRIORITY_CONSULTED, queue_stats
from app.finance_fundamentals_scheduler import refresh_queue_from_preferences
from app.finance_funds import run_daily_sync_now
from app.finance_sync_sources import get_unified_exchange_sources
from app.finance_warehouse import (
    get_sync_preferences,
    replace_exchange_symbols,
    save_index_constituents,
    save_sync_preferences,
    seed_screener_from_exchange_catalogs,
    sync_user_watchlists_to_warehouse,
    upsert_eod_bars,
    upsert_instrument,
    upsert_screener_snapshots,
    warehouse_db_path,
)


def _settings(tmp_path: Path, *, demo: bool = False) -> Settings:
    return Settings(
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=demo,
        eod_historical_data_key="test-key",
    )


def _seed_catalogs(db_path: Path) -> None:
    replace_exchange_symbols(
        db_path,
        "PA",
        [
            {"symbol": "AI", "eod_ticker": "AI.PA", "name": "Air Liquide", "country": "France", "currency": "EUR", "type": "Common Stock"},
            {"symbol": "MC", "eod_ticker": "MC.PA", "name": "LVMH", "country": "France", "currency": "EUR", "type": "Common Stock"},
            {"symbol": "CW8", "eod_ticker": "CW8.PA", "name": "Amundi MSCI World", "country": "France", "currency": "EUR", "type": "ETF"},
        ],
    )
    replace_exchange_symbols(
        db_path,
        "US",
        [
            {"symbol": "AAPL", "eod_ticker": "AAPL.US", "name": "Apple", "country": "USA", "currency": "USD", "type": "Common Stock"},
            {"symbol": "SPY", "eod_ticker": "SPY.US", "name": "SPDR S&P 500", "country": "USA", "currency": "USD", "type": "ETF"},
        ],
    )


def test_unified_exchange_sources_and_selective_stock_seeding(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db_path = warehouse_db_path(settings)
    _seed_catalogs(db_path)

    # Le référencement sélectif sur PA n'injecte pas les actions US
    seeded_pa = seed_screener_from_exchange_catalogs(db_path, ["PA"])
    assert seeded_pa == 2

    upsert_screener_snapshots(
        db_path,
        [
            {
                "symbol": "AI.PA",
                "eod_ticker": "AI.PA",
                "asset_type": "stock",
                "name": "Air Liquide",
                "exchange": "PA",
                "price": 175.0,
                "bars_count": 200,
                "has_fundamentals": True,
            },
            {
                "symbol": "CW8.PA",
                "eod_ticker": "CW8.PA",
                "asset_type": "etf",
                "name": "Amundi MSCI World",
                "exchange": "PA",
                "price": 520.0,
                "bars_count": 200,
                "has_fundamentals": False,
            },
        ],
    )

    by_code = {s["code"]: s for s in get_unified_exchange_sources(db_path)}
    assert by_code["PA"]["counts_estimated"] is False
    assert by_code["PA"]["stocks_total"] == 2
    assert by_code["PA"]["stocks_in_screener"] == 2
    assert by_code["PA"]["stocks_with_bars"] == 1
    assert by_code["PA"]["stocks_with_fundamentals"] == 1
    assert by_code["PA"]["etf_total"] == 1
    assert by_code["PA"]["etf_in_screener"] == 1
    assert by_code["PA"]["etf_with_bars"] == 1

    assert by_code["US"]["counts_estimated"] is False
    assert by_code["US"]["stocks_total"] == 1
    assert by_code["US"]["stocks_in_screener"] == 0
    assert by_code["US"]["etf_total"] == 1
    assert by_code["US"]["etf_in_screener"] == 0

    # Bourses non encore synchronisées : ordres de grandeur fournis pour affichage immédiat
    assert by_code["XETRA"]["catalog_synced"] is False
    assert by_code["XETRA"]["counts_estimated"] is True
    assert by_code["XETRA"]["stocks_total"] > 0
    assert by_code["XETRA"]["etf_total"] > 0
    assert by_code["LSE"]["counts_estimated"] is True
    assert by_code["LSE"]["stocks_total"] > 0
    assert by_code["LSE"]["etf_total"] > 0


def test_run_source_endpoint_loads_stocks_etf_and_validates(tmp_path: Path) -> None:
    from tests.test_api import authenticated_client

    settings = _settings(tmp_path)
    db_path = warehouse_db_path(settings)
    _seed_catalogs(db_path)

    bars_sample = [
        {
            "date": f"2026-10-{day:02d}",
            "open": 100.0 + day,
            "high": 102.0 + day,
            "low": 99.0 + day,
            "close": 101.0 + day,
            "adjusted_close": 101.0 + day,
            "volume": 50_000,
        }
        for day in range(1, 25)
    ]

    with authenticated_client(settings) as client:
        # Validations strictes (HTTP 400)
        assert client.post("/api/finance/sync-preferences/run-source", json={"kind": "unknown"}).status_code == 400
        assert (
            client.post("/api/finance/sync-preferences/run-source", json={"kind": "etf_exchange", "code": "EUFUND"})
            .status_code
            == 400
        )

        with (
            patch("app.finance_funds.sync_exchange_catalog_if_needed", new=AsyncMock(return_value=({"total": 3, "fetched_at": None}, "Entrepôt SQLite"))),
            patch("app.finance_exchange_full_sync.update_exchange_last_day_prices", new=AsyncMock(return_value={"updated": 0, "error": None})),
            patch("app.finance_dossier._fetch_eodhd_bars_range", new=AsyncMock(return_value=bars_sample)),
            patch("app.finance_sync_sources.fetch_eodhd_account_usage", new=AsyncMock(return_value={"daily_limit": 100_000, "remaining_today": 90_000})),
        ):
            # 1 clic sur ETF PA : référence CW8.PA + charge ses barres, sans injecter les actions US ou PA
            res_etf = client.post(
                "/api/finance/sync-preferences/run-source",
                json={"kind": "etf_exchange", "code": "PA", "background": False},
            )
            assert res_etf.status_code == 200
            body_etf = res_etf.json()
            assert body_etf["summary"]["kind"] == "etf_exchange"
            assert body_etf["summary"]["seeded"] == 1
            assert body_etf["summary"]["hydrated"]["loaded"] == 1
            pa_src = next(s for s in body_etf["exchange_sources"] if s["code"] == "PA")
            assert pa_src["etf_with_bars"] == 1
            assert pa_src["stocks_in_screener"] == 0

            # 1 clic sur Actions PA : référence AI.PA + MC.PA + charge leurs barres, sans toucher US
            res_stk = client.post(
                "/api/finance/sync-preferences/run-source",
                json={"kind": "stocks_exchange", "code": "PA", "background": False},
            )
            assert res_stk.status_code == 200
            body_stk = res_stk.json()
            assert body_stk["summary"]["seeded"] == 2
            assert body_stk["summary"]["hydrated"]["loaded"] == 2
            pa_after = next(s for s in body_stk["exchange_sources"] if s["code"] == "PA")
            us_after = next(s for s in body_stk["exchange_sources"] if s["code"] == "US")
            assert pa_after["stocks_with_bars"] == 2
            assert us_after["stocks_in_screener"] == 0


def test_daily_sync_mutualizes_bulk_and_respects_fundamentals_toggles(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    db_path = warehouse_db_path(settings)
    _seed_catalogs(db_path)

    upsert_instrument(db_path, {"symbol": "OR.PA", "eod_ticker": "OR.PA", "short_name": "L'Oréal", "exchange": "PA"})
    upsert_eod_bars(
        db_path,
        "OR.PA",
        [{"date": "2026-11-20", "open": 350, "high": 355, "low": 348, "close": 352, "adjusted_close": 352, "volume": 1000}],
        "eodhd",
    )
    sync_user_watchlists_to_warehouse(
        db_path,
        "u1",
        [{"id": "wl1", "name": "Ma liste"}],
        [{"id": "it1", "list_id": "wl1", "symbol": "OR.PA", "eod_ticker": "OR.PA", "name": "L'Oréal"}],
    )
    save_index_constituents(db_path, "CAC40", [{"symbol": "AIR.PA", "eod_ticker": "AIR.PA", "name": "Airbus"}])

    save_sync_preferences(
        db_path,
        {
            "enabled": True,
            "principal_indices": False,
            "major_indices_constituents": False,
            "indx_catalog": False,
            "screener_fundamentals": False,
            "index_codes": ["CAC40"],
            "watchlists": False,
            "exchanges": [],
            "stock_price_exchanges": ["PA"],
            "full_data_exchanges": [],
            "etf_exchanges": ["PA"],
            "fundamentals_watchlists": False,
            "fundamentals_indices": False,
        },
    )

    prefs = get_sync_preferences(db_path)
    est = estimate_daily_sync_cost(prefs, 100_000)
    assert est["max_daily_calls"] == 100  # PA dédoublonné entre stock_price_exchanges et etf_exchanges

    # Les toggles fondamentaux désactivent bien watchlists et indices dans la file
    counts = refresh_queue_from_preferences(settings)
    assert counts == {"watchlists": 0, "indices": 0, "full_exchanges": 0}
    assert queue_stats(db_path)["tracked"] == 0
    assert PRIORITY_CONSULTED == 99

    bulk_calls: list[str] = []

    async def _fake_bulk(_settings: Settings, code: str) -> dict:
        bulk_calls.append(code)
        return {"updated": 1, "error": None}

    with (
        patch("app.finance_funds.sync_exchange_catalog_if_needed", new=AsyncMock(return_value=({"total": 3, "fetched_at": None}, "Entrepôt SQLite"))),
        patch("app.finance_indices.get_index_performances", new=AsyncMock(return_value={"summary": {"loaded_count": 1, "from_cache_count": 1, "fetched_count": 0}, "items": []})),
        patch("app.finance_exchange_full_sync.update_exchange_last_day_prices", side_effect=_fake_bulk),
        patch("app.finance_sync_sources.hydrate_exchange_missing_bars_with_safety", new=AsyncMock(return_value={"targeted": 0, "loaded": 0, "errors": 0, "calls": 0})),
    ):
        res = asyncio.run(run_daily_sync_now(settings))

    assert bulk_calls == ["PA"]
    assert res["summary"]["daily_bars"]["bulk_codes"] == ["PA"]
    by_code = {s["code"]: s for s in res["exchange_sources"]}
    assert by_code["US"]["stocks_in_screener"] == 0


def test_ensure_counts_and_secondary_index_nominal_counts(tmp_path: Path) -> None:
    from app.finance_indices import list_principal_indices
    from app.finance_warehouse import get_screener_coverage, replace_exchange_symbols
    from tests.test_api import authenticated_client

    settings = _settings(tmp_path)
    db_path = warehouse_db_path(settings)

    # Indices secondaires non chargés : la taille de la liste reste connue
    idx_data = asyncio.run(list_principal_indices(settings, include_quotes=False, tier="all"))
    by_idx = {i["code"]: i for i in idx_data["indices"]}
    assert by_idx["SBF120"]["constituents_count"] >= 100
    assert by_idx["STOXX600"]["constituents_count"] == 600
    assert by_idx["SP400"]["constituents_count"] == 400
    assert by_idx["FTSE250"]["constituents_count"] == 250
    assert by_idx["CAC40"]["loaded_count"] == 0

    # Pré-comptage léger : récupère les listes manquantes sans injecter de lignes dans le Screener
    async def _fake_sync(_settings: Settings, code: str, *, refresh: bool = False):
        replace_exchange_symbols(
            db_path,
            code,
            [
                {"symbol": f"S1_{code}", "eod_ticker": f"S1.{code}", "name": "Stock 1", "type": "Common Stock"},
                {"symbol": f"E1_{code}", "eod_ticker": f"E1.{code}", "name": "ETF 1", "type": "ETF"},
            ],
        )
        return {"total": 2, "fetched_at": 1.0}, "Entrepôt SQLite"

    with (
        authenticated_client(settings) as client,
        patch("app.finance_funds.sync_exchange_catalog_if_needed", side_effect=_fake_sync),
    ):
        res = client.post("/api/finance/sync-preferences/ensure-counts", json={"codes": ["PA", "XETRA"]})
        assert res.status_code == 200
        body = res.json()
        by_ex = {s["code"]: s for s in body["exchange_sources"]}
        assert by_ex["PA"]["counts_estimated"] is False
        assert by_ex["PA"]["stocks_total"] == 1
        assert by_ex["PA"]["etf_total"] == 1
        assert by_ex["XETRA"]["counts_estimated"] is False
        assert get_screener_coverage(db_path)["total_snapshots"] == 0

