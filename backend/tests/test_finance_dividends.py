"""Tests du service et de l'endpoint `/api/finance/dividends` (hors réseau)."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import hash_password
from app.config import Settings
from app.finance_dividends import get_stock_dividends, normalize_dividend_entries
from app.finance_warehouse import save_snapshot, upsert_instrument, warehouse_db_path
from app.main import create_app
from app.models import Base, User


def _settings_for(tmp_path: Path, *, demo_mode: bool = False) -> Settings:
    return Settings(
        _env_file=None,
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=demo_mode,
    )


@contextmanager
def _auth_client(settings: Settings, username: str = "investor"):
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        if not db.scalar(select(User).where(User.is_admin.is_(True))):
            db.add(User(username="__admin__", password_hash=hash_password("admin secret phrase"), is_admin=True))
        if not db.scalar(select(User).where(User.username == username)):
            db.add(User(username=username, password_hash=hash_password("super secret phrase"), is_admin=False))
        db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        res = client.post("/api/auth/login", json={"username": username, "password": "super secret phrase"})
        assert res.status_code == 200
        yield client


def test_normalize_dividend_entries_filters_dedupes_and_sorts():
    raw = [
        {"date": "2025-05-19", "value": 3.3, "unadjustedValue": 3.3, "currency": "eur"},
        {"date": "2024-05-20", "value": "3.20", "unadjusted": 3.2},
        {"date": "2024-05-20", "value": 3.25, "unadjusted": 3.25, "currency": "EUR"},
        {"date": "bad-date", "value": 1.0},
        {"date": "2023-05-15", "value": 0},
        {"date": "2022-05-15", "value": -1.5},
    ]
    cleaned = normalize_dividend_entries(raw, fallback_currency="EUR")
    assert [d["date"] for d in cleaned] == ["2024-05-20", "2025-05-19"]
    assert cleaned[0]["value"] == 3.25
    assert cleaned[1]["currency"] == "EUR"


def test_get_stock_dividends_uses_warehouse_cache_without_network(tmp_path: Path):
    settings = _settings_for(tmp_path, demo_mode=False)
    db_path = warehouse_db_path(settings)
    upsert_instrument(db_path, {"symbol": "AI.PA", "eod_ticker": "AI.PA", "currency": "EUR"})
    save_snapshot(
        db_path,
        "AI.PA",
        "eodhd",
        "dividends",
        [
            {"date": "2025-05-19", "value": 3.3, "unadjusted": 3.3, "currency": "EUR"},
            {"date": "2024-05-20", "value": 3.2, "unadjusted": 3.2, "currency": "EUR"},
        ],
        None,
        currency="EUR",
    )

    with (
        patch("app.finance_dividends.fetch_eodhd_dividends", new_callable=AsyncMock) as mock_eod,
        patch("app.finance_dividends.fetch_yahoo_dividends", new_callable=AsyncMock) as mock_yahoo,
    ):
        res = asyncio.run(get_stock_dividends(settings, "AI.PA"))

    assert res["cached"] is True
    assert res["source"] == "eodhd"
    assert res["currency"] == "EUR"
    assert [d["date"] for d in res["dividends"]] == ["2024-05-20", "2025-05-19"]
    mock_eod.assert_not_called()
    mock_yahoo.assert_not_called()


def test_get_stock_dividends_falls_back_to_yahoo_and_persists(tmp_path: Path):
    settings = _settings_for(tmp_path, demo_mode=False)
    db_path = warehouse_db_path(settings)
    upsert_instrument(db_path, {"symbol": "AAPL.US", "eod_ticker": "AAPL.US", "yahoo_symbol": "AAPL", "currency": "USD"})

    yahoo_payload = [
        {"date": "2025-02-10", "value": 0.25, "unadjusted": 0.25, "currency": "USD"},
    ]
    with patch("app.finance_dividends.fetch_yahoo_dividends", new_callable=AsyncMock, return_value=yahoo_payload) as mock_y:
        first = asyncio.run(get_stock_dividends(settings, "AAPL.US"))
        second = asyncio.run(get_stock_dividends(settings, "AAPL.US"))

    assert first["cached"] is False
    assert first["source"] == "yahoo_finance"
    assert len(first["dividends"]) == 1
    assert second["cached"] is True
    assert second["dividends"] == first["dividends"]
    assert mock_y.call_count == 1


def test_api_finance_dividends_validation_and_cached_response(tmp_path: Path):
    settings = _settings_for(tmp_path, demo_mode=False)
    db_path = warehouse_db_path(settings)
    upsert_instrument(db_path, {"symbol": "TTE.PA", "eod_ticker": "TTE.PA", "currency": "EUR"})
    save_snapshot(
        db_path,
        "TTE.PA",
        "eodhd",
        "dividends",
        [{"date": "2025-03-26", "value": 0.79, "unadjusted": 0.79, "currency": "EUR"}],
        None,
        currency="EUR",
    )

    with _auth_client(settings) as client:
        bad = client.get("/api/finance/dividends?symbol=BAD%20SYMBOL!!")
        assert bad.status_code == 400

        ok = client.get("/api/finance/dividends?symbol=TTE.PA")
        assert ok.status_code == 200
        body = ok.json()
        assert body["canonical_symbol"] == "TTE.PA"
        assert body["cached"] is True
        assert len(body["dividends"]) == 1
        assert body["dividends"][0]["value"] == 0.79
