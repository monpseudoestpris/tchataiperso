import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import current_user, get_settings
from app.finance_indices import (
    get_index_composition,
    list_eodhd_indx_catalog,
    list_principal_indices,
    search_finance_catalog,
)
from app.finance_warehouse import (
    get_cached_symbols_set,
    get_index_constituents,
    get_warehouse_overview,
    save_index_constituents,
    search_warehouse_catalog,
    upsert_eod_bars,
    upsert_instrument,
    warehouse_db_path,
)
from app.main import app


def _make_settings(tmp_path: Path, *, eod_key: str = "") -> Settings:
    return Settings(
        app_data_dir=tmp_path,
        finance_data_dir=tmp_path / "finance",
        demo_mode=False,
        eod_historical_data_key=eod_key,
    )


def test_warehouse_scales_index_constituents_and_catalog_search(tmp_path: Path) -> None:
    s = _make_settings(tmp_path)
    db_path = warehouse_db_path(s)

    bulk_items = [
        {
            "symbol": f"STK{i}.US",
            "eod_ticker": f"STK{i}.US",
            "yahoo_symbol": f"STK{i}",
            "name": f"Company Alpha {i}",
            "sector": "Technology" if i % 2 == 0 else "Healthcare",
            "exchange": "US",
            "weight_pct": round(100.0 / 500, 3),
        }
        for i in range(505)
    ]
    inserted = save_index_constituents(db_path, "SP500", bulk_items)
    assert inserted == 505

    loaded, fetched_at = get_index_constituents(db_path, "SP500", max_age_seconds=3600)
    assert fetched_at is not None
    assert len(loaded) == 505

    upsert_instrument(db_path, {"symbol": "AI.PA", "eod_ticker": "AI.PA", "yahoo_symbol": "AI.PA", "short_name": "Air Liquide"})
    upsert_eod_bars(db_path, "AI.PA", [{"date": "2026-11-16", "open": 170.0, "high": 172.0, "low": 169.5, "close": 171.2, "adjusted_close": 171.2, "volume": 100000}], "EODHD")

    cached = get_cached_symbols_set(db_path)
    assert "AI.PA" in cached
    assert "AI" in cached

    hits = search_warehouse_catalog(db_path, "Alpha 499", limit=10)
    assert any(h["symbol"] == "STK499.US" and h["index_code"] == "SP500" for h in hits)

    overview = get_warehouse_overview(db_path)
    assert overview["instruments_count"] == 1
    assert overview["eod_bars_count"] == 1
    assert overview["index_constituents_count"] == 505


def test_principal_indices_and_cac40_fallback_with_cached_flags(tmp_path: Path) -> None:
    s = _make_settings(tmp_path)
    db_path = warehouse_db_path(s)
    upsert_instrument(db_path, {"symbol": "AI.PA", "eod_ticker": "AI.PA", "yahoo_symbol": "AI.PA", "short_name": "Air Liquide"})
    upsert_eod_bars(db_path, "AI.PA", [{"date": "2026-11-16", "close": 171.0}], "EODHD")

    listing = asyncio.run(list_principal_indices(s, include_quotes=False))
    codes = [idx["code"] for idx in listing["indices"]]
    assert "CAC40" in codes
    assert "SP500" in codes
    assert "NASDAQ100" in codes
    assert "EUROSTOXX50" in codes
    assert listing["warehouse"]["instruments_count"] == 1

    cac = asyncio.run(get_index_composition(s, "CAC40"))
    assert cac is not None
    assert cac["index"]["code"] == "CAC40"
    assert len(cac["constituents"]) == 40
    assert cac["index"]["cached_count"] >= 1
    air_liquide = next(c for c in cac["constituents"] if c["symbol"] == "AI.PA")
    assert air_liquide["cached_in_warehouse"] is True

    matches = search_finance_catalog(s, "LVMH", limit=10)
    assert any(m["eod_ticker"] == "MC.PA" for m in matches)


def test_eodhd_live_index_components_parsed_and_cached(tmp_path: Path) -> None:
    s = _make_settings(tmp_path, eod_key="test-eod-key")

    mock_payload = {
        "General": {"Code": "GSPC", "Name": "S&P 500"},
        "Components": {
            "0": {"Code": "NVDA", "Exchange": "US", "Name": "NVIDIA Corporation", "Sector": "Technology", "Industry": "Semiconductors", "Weight": 6.8},
            "1": {"Code": "MSFT", "Exchange": "US", "Name": "Microsoft Corporation", "Sector": "Technology", "Industry": "Software", "Weight": 6.2},
            "2": {"Code": "BRK-B", "Exchange": "US", "Name": "Berkshire Hathaway Inc.", "Sector": "Financial Services", "Industry": "Insurance"},
        },
    }
    req = httpx.Request("GET", "https://eodhd.com/api/fundamentals/GSPC.INDX")
    mock_resp = httpx.Response(200, request=req, json=mock_payload)

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.finance_indices.httpx.AsyncClient", return_value=fake_client):
        sp = asyncio.run(get_index_composition(s, "SP500", refresh=True))

    assert sp is not None
    assert "EODHD" in sp["index"]["source"]
    assert len(sp["constituents"]) == 3
    assert sp["constituents"][0]["eod_ticker"] == "NVDA.US"
    assert sp["constituents"][0]["yahoo_symbol"] == "NVDA"
    assert sp["constituents"][0]["weight_pct"] == 6.8


def test_finance_indices_router_endpoints(tmp_path: Path) -> None:
    s = _make_settings(tmp_path)
    fake_user = MagicMock(id="u-test")

    app.dependency_overrides[get_settings] = lambda: s
    app.dependency_overrides[current_user] = lambda: fake_user
    try:
        client = TestClient(app)
        res_list = client.get("/api/finance/indices?include_quotes=false")
        assert res_list.status_code == 200
        assert len(res_list.json()["indices"]) >= 8

        res_cac = client.get("/api/finance/indices/CAC40")
        assert res_cac.status_code == 200
        assert len(res_cac.json()["constituents"]) == 40

        res_unknown = client.get("/api/finance/indices/UNKNOWN999")
        assert res_unknown.status_code == 404

        res_search = client.get("/api/finance/catalog/search?q=Sanofi")
        assert res_search.status_code == 200
        assert any(i["eod_ticker"] == "SAN.PA" for i in res_search.json()["items"])

        res_minor = client.get("/api/finance/indices/AEX25")
        assert res_minor.status_code == 200
        assert len(res_minor.json()["constituents"]) == 25

        res_catalog = client.get("/api/finance/indices/eodhd-catalog?q=SBF")
        assert res_catalog.status_code == 200
        assert any("PX4" in i["eod_ticker"] or "SBF" in i["name"] for i in res_catalog.json()["items"])
    finally:
        app.dependency_overrides.clear()


def test_eodhd_indx_catalog_endpoint_mocked_and_cached(tmp_path: Path) -> None:
    s = _make_settings(tmp_path, eod_key="test-eod-key")
    mock_rows = [
        {"Code": "PX4", "Name": "SBF 120", "Country": "France", "Currency": "EUR", "Type": "INDEX"},
        {"Code": "RUT", "Name": "Russell 2000", "Country": "USA", "Currency": "USD", "Type": "INDEX"},
        {"Code": "MDAXI", "Name": "MDAX", "Country": "Germany", "Currency": "EUR", "Type": "INDEX"},
    ]
    req = httpx.Request("GET", "https://eodhd.com/api/exchange-symbol-list/INDX")
    mock_resp = httpx.Response(200, request=req, json=mock_rows)

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.finance_indices.httpx.AsyncClient", return_value=fake_client):
        cat = asyncio.run(list_eodhd_indx_catalog(s, query="Russell", refresh=True))

    assert cat["source"] == "EODHD INDX API"
    assert cat["total"] == 3
    assert cat["matched"] == 1
    assert cat["items"][0]["eod_ticker"] == "RUT.INDX"

    # Vérifie ensuite l'ouverture dynamique d'un ticker .INDX depuis le catalogue mémorisé
    comp = asyncio.run(get_index_composition(s, "RUT.INDX"))
    assert comp is not None
    assert comp["index"]["eod_ticker"] == "RUT.INDX"
    assert len(comp["constituents"]) >= 15
