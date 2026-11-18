import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import current_user, get_settings
from app.finance import (
    _parse_explicit_eod_ticker,
    get_financial_dashboard_data,
    score_eodhd_search_item,
)
from app.finance_dossier import get_financial_dossier
from app.finance_funds import (
    extract_fund_profile,
    list_eufund_catalog,
    looks_like_isin,
    search_eodhd_funds_live,
)
from app.finance_indices import search_finance_catalog
from app.finance_warehouse import (
    get_exchange_catalog_meta,
    lookup_exchange_symbol,
    replace_exchange_symbols,
    search_exchange_symbols,
    warehouse_db_path,
)
from app.finance_watchlist import fetch_watchlist_quotes, resolve_watchlist_instrument
from app.main import app


def _make_settings(tmp_path: Path, *, eod_key: str = "test-eod-key") -> Settings:
    return Settings(
        app_data_dir=tmp_path,
        finance_data_dir=tmp_path / "finance",
        demo_mode=False,
        eod_historical_data_key=eod_key,
    )


def test_parse_isin_and_explicit_eufund_ticker() -> None:
    assert looks_like_isin("FR0013202132") is True
    assert looks_like_isin("FR0010286013") is True
    assert looks_like_isin("AAPL") is False

    assert _parse_explicit_eod_ticker("FR0013202132.EUFUND") == ("FR0013202132", "EUFUND")
    assert _parse_explicit_eod_ticker("0P00001234.EUFUND") == ("0P00001234", "EUFUND")
    assert _parse_explicit_eod_ticker("AI.PA") == ("AI", "PA")

    fund_item = {
        "Code": "FR0013202132",
        "Exchange": "EUFUND",
        "Name": "Sextant Bond Picking A",
        "Type": "Mutual Fund",
        "Country": "France",
        "ISIN": "FR0013202132",
    }
    other_item = {
        "Code": "SEXT",
        "Exchange": "US",
        "Name": "Sextant Corp",
        "Type": "Common Stock",
        "Country": "USA",
    }
    assert score_eodhd_search_item("FR0013202132", fund_item) > score_eodhd_search_item("FR0013202132", other_item)


def test_exchange_catalog_warehouse_and_eufund_sync(tmp_path: Path) -> None:
    s = _make_settings(tmp_path)
    mock_rows = [
        {"Code": "FR0013202132", "Name": "Sextant Bond Picking A", "Country": "France", "Currency": "EUR", "Type": "Fund"},
        {"Code": "FR0010286013", "Name": "Sextant Grand Large A", "Country": "France", "Currency": "EUR", "Type": "Fund"},
        {"Code": "LU0123456789", "Name": "Global Tech Fund USD", "Country": "Luxembourg", "Currency": "USD", "Type": "Fund"},
    ]
    req = httpx.Request("GET", "https://eodhd.com/api/exchange-symbol-list/EUFUND")
    mock_resp = httpx.Response(200, request=req, json=mock_rows)

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.finance_funds.httpx.AsyncClient", return_value=fake_client):
        res = asyncio.run(list_eufund_catalog(s, query="Sextant", currency="EUR", refresh=True))

    assert res["source"] == "EODHD EUFUND API"
    assert res["total"] == 3
    assert res["matched"] == 2
    assert res["currencies"] == ["EUR", "USD"]
    assert res["items"][0]["eod_ticker"] in {"FR0010286013.EUFUND", "FR0013202132.EUFUND"}

    db_path = warehouse_db_path(s)
    meta = get_exchange_catalog_meta(db_path, "EUFUND")
    assert meta["total"] == 3

    hit = lookup_exchange_symbol(db_path, "FR0013202132", "EUFUND")
    assert hit is not None
    assert hit["eod_ticker"] == "FR0013202132.EUFUND"
    assert hit["name"] == "Sextant Bond Picking A"

    cat_hits = search_finance_catalog(s, "Bond Picking", limit=10)
    assert any(c["eod_ticker"] == "FR0013202132.EUFUND" and c["exchange"] == "EUFUND" for c in cat_hits)


def test_eufund_live_search_and_router(tmp_path: Path) -> None:
    s = _make_settings(tmp_path)
    fake_user = MagicMock(id="u-fund")

    mock_search = [
        {
            "Code": "FR0013202132",
            "Exchange": "EUFUND",
            "Name": "Sextant Bond Picking A",
            "Type": "Mutual Fund",
            "Country": "France",
            "Currency": "EUR",
            "ISIN": "FR0013202132",
            "previousClose": 128.45,
        }
    ]
    req = httpx.Request("GET", "https://eodhd.com/api/search/FR0013202132")
    mock_resp = httpx.Response(200, request=req, json=mock_search)
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=mock_resp)

    with patch("app.finance_funds.httpx.AsyncClient", return_value=fake_client):
        res = asyncio.run(search_eodhd_funds_live(s, "FR0013202132"))
    assert len(res["items"]) == 1
    assert res["items"][0]["eod_ticker"] == "FR0013202132.EUFUND"

    db_path = warehouse_db_path(s)
    replace_exchange_symbols(
        db_path,
        "EUFUND",
        [{"symbol": "FR0013202132", "eod_ticker": "FR0013202132.EUFUND", "name": "Sextant Bond Picking A", "isin": "FR0013202132", "currency": "EUR", "country": "France"}],
    )
    app.dependency_overrides[get_settings] = lambda: s
    app.dependency_overrides[current_user] = lambda: fake_user
    try:
        client = TestClient(app)
        resp_cat = client.get("/api/finance/funds/eufund?q=Sextant")
        assert resp_cat.status_code == 200
        assert resp_cat.json()["items"][0]["eod_ticker"] == "FR0013202132.EUFUND"
    finally:
        app.dependency_overrides.clear()


def test_eufund_watchlist_resolution_nav_quotes_and_dashboard(tmp_path: Path) -> None:
    s = _make_settings(tmp_path)
    db_path = warehouse_db_path(s)
    replace_exchange_symbols(
        db_path,
        "EUFUND",
        [
            {
                "symbol": "FR0013202132",
                "eod_ticker": "FR0013202132.EUFUND",
                "name": "Sextant Bond Picking A",
                "isin": "FR0013202132",
                "currency": "EUR",
                "country": "France",
                "type": "Fund",
            }
        ],
    )

    resolved = asyncio.run(resolve_watchlist_instrument(s, "FR0013202132.EUFUND"))
    assert resolved["eod_ticker"] == "FR0013202132.EUFUND"
    assert resolved["name"] == "Sextant Bond Picking A"
    assert resolved["exchange"] == "EUFUND"
    assert resolved["currency"] == "EUR"

    nav_bars_desc = [
        {"date": "2026-11-17", "open": 130.0, "high": 130.0, "low": 130.0, "close": 130.0, "adjusted_close": 130.0, "volume": 0},
        {"date": "2026-11-16", "open": 128.0, "high": 128.0, "low": 128.0, "close": 128.0, "adjusted_close": 128.0, "volume": 0},
        {"date": "2026-11-10", "open": 125.0, "high": 125.0, "low": 125.0, "close": 125.0, "adjusted_close": 125.0, "volume": 0},
        {"date": "2026-10-17", "open": 120.0, "high": 120.0, "low": 120.0, "close": 120.0, "adjusted_close": 120.0, "volume": 0},
    ]

    wl_item = SimpleNamespace(
        id="w-1",
        list_id="l-1",
        symbol="FR0013202132.EUFUND",
        yahoo_symbol="FR0013202132.EUFUND",
        eod_ticker="FR0013202132.EUFUND",
        name="Sextant Bond Picking A",
        exchange="EUFUND",
        currency="EUR",
        position=0,
    )
    with patch("app.finance_watchlist.fetch_eodhd_historical_eod", new=AsyncMock(return_value=nav_bars_desc)):
        quotes = asyncio.run(fetch_watchlist_quotes(s, [wl_item]))

    assert len(quotes) == 1
    assert quotes[0]["price"] == 130.0
    assert quotes[0]["change_1d_pct"] == round(((130.0 - 128.0) / 128.0) * 100.0, 2)
    assert quotes[0]["change_1w_pct"] == 4.0

    # Dashboard avec NAV EOD uniquement (sans real-time, sans Yahoo)
    fund_payload = {
        "General": {
            "Code": "FR0013202132",
            "Exchange": "EUFUND",
            "Name": "Sextant Bond Picking A",
            "Type": "Mutual Fund",
            "CurrencyCode": "EUR",
            "ISIN": "FR0013202132",
            "Fund_Family": "Amiral Gestion",
            "Category": "Obligations Internationales",
        },
        "Mutual_Fund": {
            "Ongoing_Charge": 0.0115,
            "TotalAssets": 450_000_000,
            "Asset_Allocation": {"Bond": {"Name": "Obligations", "Assets_%": 88.5}, "Cash": {"Name": "Liquidités", "Assets_%": 11.5}},
            "Top_Holdings": {"0": {"Code": "TITR1", "Name": "Oblig Entreprise X", "Assets_%": 3.4}},
        },
    }
    with (
        patch("app.finance.fetch_eodhd_realtime", new=AsyncMock(return_value=None)),
        patch("app.finance.fetch_eodhd_historical_eod", new=AsyncMock(return_value=nav_bars_desc)),
        patch("app.finance.fetch_eodhd_fundamentals", new=AsyncMock(return_value=fund_payload)),
    ):
        dash = asyncio.run(get_financial_dashboard_data(s, "FR0013202132.EUFUND"))

    assert dash["symbol"] == "FR0013202132.EUFUND"
    assert dash["short_name"] == "Sextant Bond Picking A"
    assert dash["price"] == 130.0
    assert dash["previous_close"] == 128.0
    assert dash["change"] == 2.0
    assert dash["financial_stats"]["valuation"]["expense_ratio"] == "1.15%"

    prof = extract_fund_profile(fund_payload, symbol="FR0013202132.EUFUND")
    assert prof is not None
    assert prof["fund_family"] == "Amiral Gestion"
    assert prof["expense_ratio_pct"] == 1.15
    assert prof["top_holdings"][0]["name"] == "Oblig Entreprise X"

    with (
        patch("app.finance_dossier._fetch_eodhd_bars_range", new=AsyncMock(return_value=list(reversed(nav_bars_desc)))),
        patch("app.finance_dossier._fetch_eodhd_dividends", new=AsyncMock(return_value=[])),
        patch("app.finance_dossier._sync_dossier_news", new=AsyncMock(return_value={"source": "none", "provider": "none", "items": []})),
        patch("app.finance_dossier._sync_eodhd_extras", new=AsyncMock(return_value={})),
    ):
        dossier = asyncio.run(get_financial_dossier(s, "FR0013202132.EUFUND"))

    assert dossier["symbol"] == "FR0013202132.EUFUND"
    assert dossier["fund_profile"] is not None
    assert dossier["fund_profile"]["fund_family"] == "Amiral Gestion"
    assert dossier["header"]["isin"] == "FR0013202132"


def test_eufund_name_repair_via_search_and_watchlist_note_crud(tmp_path: Path) -> None:
    from tests.test_api import authenticated_client

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        finance_data_dir=tmp_path / "finance",
        demo_mode=False,
        eod_historical_data_key="test-eod-key",
        openrouter_api_key="",
        brave_api_key="",
        duckduckgo_instant_answers_enabled=False,
    )

    mock_search_rows = [
        {
            "Code": "FR0013202132",
            "Exchange": "EUFUND",
            "Name": "Sextant Bond Picking A",
            "Type": "Mutual Fund",
            "Country": "France",
            "Currency": "EUR",
            "ISIN": "FR0013202132",
        }
    ]
    req = httpx.Request("GET", "https://eodhd.com/api/search/FR0013202132")
    mock_resp = httpx.Response(200, request=req, json=mock_search_rows)

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=mock_resp)

    with (
        patch("app.finance_watchlist.httpx.AsyncClient", return_value=fake_client),
        patch("app.finance_watchlist.fetch_eodhd_fundamentals", new=AsyncMock(return_value=None)),
    ):
        resolved = asyncio.run(resolve_watchlist_instrument(s, "FR0013202132.EUFUND"))
    assert resolved["name"] == "Sextant Bond Picking A"
    assert resolved["exchange"] == "EUFUND"

    with authenticated_client(s) as client:
        with (
            patch("app.finance_watchlist.httpx.AsyncClient", return_value=fake_client),
            patch("app.finance_watchlist.fetch_eodhd_fundamentals", new=AsyncMock(return_value=None)),
            patch(
                "app.finance_watchlist.fetch_eodhd_historical_eod",
                new=AsyncMock(return_value=[{"date": "2026-11-17", "close": 130.0}]),
            ),
        ):
            add_res = client.post(
                "/api/finance/watchlist",
                json={"query": "FR0013202132.EUFUND", "note": "Fonds obligataire Amiral"},
            )
            assert add_res.status_code == 201
            item = add_res.json()
            assert item["name"] == "Sextant Bond Picking A"
            assert item["note"] == "Fonds obligataire Amiral"

            patch_res = client.patch(
                f"/api/finance/watchlist/{item['id']}",
                json={"note": "Sextant Bond Picking - Assurance Vie"},
            )
            assert patch_res.status_code == 200
            assert patch_res.json()["note"] == "Sextant Bond Picking - Assurance Vie"

            wl_res = client.get("/api/finance/watchlist?include_quotes=false")
            assert wl_res.status_code == 200
            listed = wl_res.json()["items"]
            assert any(i["id"] == item["id"] and i["note"] == "Sextant Bond Picking - Assurance Vie" for i in listed)

