"""Tests de la synchro « bourse complète » (`finance_exchange_full_sync.py`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import httpx

from app.config import Settings
from app.finance_exchange_full_sync import (
    get_full_exchange_coverage,
    update_exchange_last_day_prices,
)
from app.finance_warehouse import (
    get_stored_eod_bars,
    replace_exchange_symbols,
    seed_screener_from_exchange_catalogs,
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


def _seed_paris(db_path: Path) -> None:
    replace_exchange_symbols(
        db_path,
        "PA",
        [
            {"symbol": "AI", "eod_ticker": "AI.PA", "name": "Air Liquide", "country": "France", "currency": "EUR", "type": "Common Stock"},
            {"symbol": "ALO", "eod_ticker": "ALO.PA", "name": "Alstom", "country": "France", "currency": "EUR", "type": "Common Stock"},
            {"symbol": "VIRP", "eod_ticker": "VIRP.PA", "name": "Virbac", "country": "France", "currency": "EUR", "type": "Common Stock"},
            {"symbol": "CW8", "eod_ticker": "CW8.PA", "name": "Amundi MSCI World", "country": "France", "currency": "EUR", "type": "ETF"},
        ],
    )


def test_coverage_and_missing_symbols_follow_catalog(tmp_path: Path):
    settings = _settings(tmp_path)
    db_path = warehouse_db_path(settings)
    _seed_paris(db_path)
    upsert_screener_snapshots(
        db_path,
        [{"symbol": "AI.PA", "eod_ticker": "AI.PA", "name": "Air Liquide", "exchange": "PA", "price": 175.0, "bars_count": 100}],
    )
    seed_screener_from_exchange_catalogs(db_path)

    cov = get_full_exchange_coverage(db_path, ["PA"])
    assert cov["PA"] == {"total": 3, "with_data": 1}  # ETF exclu


def test_bulk_last_day_updates_only_already_loaded_symbols(tmp_path: Path):
    settings = _settings(tmp_path)
    db_path = warehouse_db_path(settings)
    upsert_instrument(db_path, {"symbol": "AI.PA", "eod_ticker": "AI.PA", "short_name": "Air Liquide", "exchange": "PA", "currency": "EUR"})
    upsert_eod_bars(
        db_path,
        "AI.PA",
        [{"date": "2026-11-19", "open": 170, "high": 172, "low": 169, "close": 171, "adjusted_close": 171, "volume": 1000}],
        "eodhd",
    )

    payload = [
        {"code": "AI", "exchange_short_name": "PA", "date": "2026-11-20", "open": 171, "high": 176, "low": 170, "close": 175, "adjusted_close": 175, "volume": 2000},
        {"code": "ALO", "exchange_short_name": "PA", "date": "2026-11-20", "open": 20, "high": 21, "low": 19, "close": 20.5, "adjusted_close": 20.5, "volume": 5000},
    ]
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=payload)

    real_client = httpx.AsyncClient

    def _client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return real_client(*args, **kwargs)

    with patch("app.finance_exchange_full_sync.httpx.AsyncClient", side_effect=_client_factory):
        res = asyncio.run(update_exchange_last_day_prices(settings, "PA"))

    assert res == {"updated": 1, "error": None}
    assert seen_urls and "/api/eod-bulk-last-day/PA" in seen_urls[0]
    ai_dates = [b["date"] for b in get_stored_eod_bars(db_path, "AI.PA", limit=None)]
    assert ai_dates == ["2026-11-19", "2026-11-20"]
    assert get_stored_eod_bars(db_path, "ALO.PA", limit=None) == []  # Pas d'historique partiel pour un titre jamais chargé


def test_bulk_last_day_requires_eodhd_key_outside_demo(tmp_path: Path):
    res = asyncio.run(update_exchange_last_day_prices(_settings(tmp_path, demo=True), "PA"))
    assert res["updated"] == 0 and res["error"]
