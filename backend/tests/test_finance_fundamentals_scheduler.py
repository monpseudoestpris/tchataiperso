"""Tests du planificateur des fondamentaux (`finance_fundamentals_scheduler.py`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import finance_eodhd_usage as usage
from app.config import Settings
from app.finance_fundamentals_queue import get_symbol_schedule, queue_stats, record_fetch
from app.finance_fundamentals_scheduler import load_fundamentals_light, run_fundamentals_budget
from app.finance_warehouse import (
    get_stored_eod_bars,
    replace_exchange_symbols,
    save_index_constituents,
    save_sync_preferences,
    warehouse_db_path,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        app_data_dir=tmp_path / "a",
        finance_data_dir=tmp_path / "f",
        demo_mode=False,
        eod_historical_data_key="test-key",
    )


def _seed(db: Path, n: int = 20) -> None:
    replace_exchange_symbols(
        db,
        "PA",
        [
            {"symbol": f"S{i:02d}", "eod_ticker": f"S{i:02d}.PA", "name": f"Société {i}", "country": "France", "currency": "EUR", "type": "Common Stock"}
            for i in range(n)
        ],
    )
    save_index_constituents(db, "CAC40", [{"symbol": "S19.PA", "eod_ticker": "S19.PA", "name": "Société 19"}])
    save_sync_preferences(db, {"full_data_exchanges": ["PA"], "major_indices_constituents": True, "fundamentals_budget_pct": 10})


def _fake_payload() -> dict:
    return {
        "General": {"Code": "S", "Name": "Société", "CurrencyCode": "EUR", "Exchange": "PA", "CountryName": "France"},
        "Financials": {"Income_Statement": {"quarterly": {d: {"date": d, "totalRevenue": "100"} for d in ("2026-03-31", "2026-06-30", "2026-09-30")}}},
    }


def test_budget_respected_and_priorities_followed(tmp_path: Path):
    settings = _settings(tmp_path)
    db = warehouse_db_path(settings)
    _seed(db)
    loaded: list[str] = []

    async def _fake_light(_settings, symbol: str):
        loaded.append(symbol)
        record_fetch(db, symbol, _fake_payload())
        return {"ok": True, "calls": 11}

    account = {"daily_limit": 1000, "remaining_today": 900}
    with (
        patch("app.finance_fundamentals_scheduler.fetch_eodhd_account_usage", new=AsyncMock(return_value=account)),
        patch("app.finance_fundamentals_scheduler.apply_earnings_calendar", new=AsyncMock(return_value=0)),
        patch("app.finance_fundamentals_scheduler.load_fundamentals_light", side_effect=_fake_light),
    ):
        res = asyncio.run(run_fundamentals_budget(settings))
        # Budget = 10 % de 1 000 = 100 calls, dont 1 pour le calendrier → 9 titres à 11 calls
        assert res["loaded"] == 9 and len(loaded) == 9
        assert loaded[0] == "S19.PA"  # Indice suivi (priorité 2) avant la bourse complète (priorité 3)
        assert res["stopped_reason"] == "Budget du jour atteint"

        # Deuxième passage le même jour : budget épuisé, rien n'est rechargé
        res2 = asyncio.run(run_fundamentals_budget(settings))
        assert res2["loaded"] == 0
    assert queue_stats(db)["never_loaded"] == 11


def test_stops_when_account_quota_below_safety_margin(tmp_path: Path):
    settings = _settings(tmp_path)
    db = warehouse_db_path(settings)
    _seed(db, n=5)
    light = AsyncMock(return_value={"ok": True, "calls": 11})
    with (
        patch("app.finance_fundamentals_scheduler.fetch_eodhd_account_usage", new=AsyncMock(return_value={"daily_limit": 100_000, "remaining_today": 1_000})),
        patch("app.finance_fundamentals_scheduler.apply_earnings_calendar", new=AsyncMock(return_value=0)),
        patch("app.finance_fundamentals_scheduler.load_fundamentals_light", new=light),
    ):
        res = asyncio.run(run_fundamentals_budget(settings))
    assert res["loaded"] == 0 and light.await_count == 0
    assert res["stopped_reason"] == "Quota du compte sous la marge de sécurité"


def test_light_loader_fetches_only_fundamentals_and_history(tmp_path: Path):
    settings = _settings(tmp_path)
    db = warehouse_db_path(settings)
    with usage._LOCK:
        usage._USAGE.clear()
        usage._USAGE_DAY = ""

    async def _fake_fund(ticker: str, _key: str):
        usage.record_eodhd_call(f"https://eodhd.com/api/fundamentals/{ticker}")
        return _fake_payload()

    async def _fake_bars(ticker: str, _key: str, _from: str):
        usage.record_eodhd_call(f"https://eodhd.com/api/eod/{ticker}")
        return [{"date": "2026-11-20", "open": 10, "high": 11, "low": 9, "close": 10.5, "adjusted_close": 10.5, "volume": 1000}]

    with (
        patch("app.finance_provider.fetch_eodhd_fundamentals_json", side_effect=_fake_fund),
        patch("app.finance_dossier._fetch_eodhd_bars_range", side_effect=_fake_bars),
    ):
        res = asyncio.run(load_fundamentals_light(settings, "ALO.PA"))

    assert res == {"ok": True, "calls": 11}
    assert [b["date"] for b in get_stored_eod_bars(db, "ALO.PA", limit=None)] == ["2026-11-20"]
    endpoints = {it["endpoint"] for it in usage.get_local_usage()["by_endpoint"]}
    assert endpoints == {"fundamentals", "eod"}  # Aucun sentiment / initiés / capitalisation historique / macro
    sched = get_symbol_schedule(db, ["ALO.PA"])
    assert sched and sched["last_period_end"] == "2026-09-30" and sched["cadence"] == "quarterly"
