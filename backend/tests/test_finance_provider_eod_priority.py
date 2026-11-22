"""Tests de priorité stricte EODHD sur les états financiers (`finance_provider.py` + `finance_warehouse.py`)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import SecretStr

from app.config import Settings
from app.finance_provider import get_unified_financial_statements, resolve_candidate_eod_tickers
from app.finance_statements import STATEMENT_TYPE_BY_KEY
from app.finance_warehouse import (
    load_fundamental_series,
    save_snapshot,
    upsert_fundamental_facts,
    upsert_instrument,
    warehouse_db_path,
)


def _sample_eod_payload(code: str = "SAP.XETRA", rev: float = 34_000_000_000.0) -> dict:
    return {
        "General": {"Code": code, "Name": "SAP SE", "Exchange": "XETRA", "CurrencyCode": "EUR"},
        "Highlights": {"MarketCapitalization": 260_000_000_000.0},
        "Financials": {
            "Income_Statement": {
                "currency_symbol": "EUR",
                "yearly": {
                    "2024-12-31": {"totalRevenue": str(rev), "netIncome": "4200000000"},
                },
                "quarterly": {},
            },
            "Balance_Sheet": {
                "currency_symbol": "EUR",
                "yearly": {
                    "2024-12-31": {"totalAssets": "75000000000", "totalStockholderEquity": "45000000000"},
                },
                "quarterly": {},
            },
            "Cash_Flow": {"currency_symbol": "EUR", "yearly": {}, "quarterly": {}},
        },
    }


def test_yahoo_suffix_maps_to_eod_exchange_candidates(tmp_path: Path):
    settings = Settings(app_data_dir=tmp_path / "app", finance_data_dir=tmp_path / "fin")
    db_path = warehouse_db_path(settings)
    assert resolve_candidate_eod_tickers(db_path, "SAP.DE")[:2] == ["SAP.XETRA", "SAP.F"]
    assert resolve_candidate_eod_tickers(db_path, "SHEL.L")[0] == "SHEL.LSE"
    assert resolve_candidate_eod_tickers(db_path, "7203.T")[0] == "7203.TSE"

    upsert_instrument(db_path, {"symbol": "SAP.DE", "eod_ticker": "SAP.XETRA", "yahoo_symbol": "SAP.DE"})
    assert resolve_candidate_eod_tickers(db_path, "SAP.DE")[0] == "SAP.XETRA"


def test_cached_yahoo_statements_upgraded_to_eodhd_when_key_present(tmp_path: Path):
    settings = Settings(
        app_data_dir=tmp_path / "app",
        finance_data_dir=tmp_path / "fin",
        eod_historical_data_key=SecretStr("demo-eod-token"),
        demo_mode=False,
    )
    db_path = warehouse_db_path(settings)

    # Simuler un ancien cache Yahoo Finance (avec une date fiscale décalée)
    upsert_fundamental_facts(
        db_path,
        "SAP.DE",
        "annual",
        {"TotalRevenue": {"2024-12-28": 31_000_000_000.0}},
        STATEMENT_TYPE_BY_KEY,
        "yahoo_finance",
        "EUR",
    )
    save_snapshot(
        db_path,
        "SAP.DE",
        "yahoo_finance",
        "fundamentals",
        {"annual": {}},
        {"earnings_history": [], "highlights": {}, "currency": "EUR"},
        currency="EUR",
    )

    fetched_tickers: list[str] = []

    async def _fake_fetch_eod(ticker: str, _key: str):
        fetched_tickers.append(ticker)
        if ticker == "SAP.XETRA":
            return _sample_eod_payload("SAP.XETRA", rev=34_176_000_000.0)
        return None

    with (
        patch("app.finance_provider.fetch_eodhd_fundamentals_json", side_effect=_fake_fetch_eod),
        patch("app.finance_provider.fetch_yahoo_timeseries_bundle", new=AsyncMock(side_effect=AssertionError("Yahoo ne doit pas être appelé quand EODHD réussit"))),
    ):
        res = asyncio.run(get_unified_financial_statements(settings, "SAP.DE", refresh=False))

    assert fetched_tickers == ["SAP.XETRA"]
    assert res["source_provider"] == "eodhd"
    assert res["source_label"] == "EOD Historical Data"
    # Les dates fiscales Yahoo (2024-12-28) ne polluent plus les états EODHD (2024-12-31)
    assert res["annual"]["dates"] == ["2024-12-31"]
    rev_row = next(r for r in res["annual"]["income"] if r["key"] == "TotalRevenue")
    assert rev_row["values"] == [34_176_000_000.0]

    # load_fundamental_series renvoie exclusivement les lignes EODHD quand elles existent
    series, _, src, _ = load_fundamental_series(db_path, "SAP.DE", "annual")
    assert src == "eodhd"
    assert list(series["TotalRevenue"].keys()) == ["2024-12-31"]


def test_is_eod_fresh_today_and_source_breakdown_detect_yahoo_only(tmp_path: Path):
    from app.finance_warehouse import (
        get_instrument_eod_sync_info,
        get_warehouse_eod_source_breakdown,
        is_eod_fresh_today,
        upsert_eod_bars,
    )

    settings = Settings(app_data_dir=tmp_path / "app", finance_data_dir=tmp_path / "fin")
    db_path = warehouse_db_path(settings)
    bars = [{"date": f"2026-01-{d:02d}", "open": 100, "high": 102, "low": 99, "close": 101, "adjusted_close": 101, "volume": 1000} for d in range(1, 25)]

    upsert_eod_bars(db_path, "AI.PA", bars, "yahoo_finance", requested_limit=24)
    sync_info = get_instrument_eod_sync_info(db_path, "AI.PA")
    assert sync_info["latest_bar_source"] == "yahoo_finance"
    assert is_eod_fresh_today(sync_info, min_bars_needed=20) is True
    assert is_eod_fresh_today(sync_info, min_bars_needed=20, prefer_source="eodhd") is False

    br = get_warehouse_eod_source_breakdown(db_path)
    assert br["yahoo_only_bars_symbols"] == ["AI.PA"]
    assert br["eodhd_bars_symbols_count"] == 0

    upsert_eod_bars(db_path, "AI.PA", bars, "eodhd", requested_limit=24)
    sync_info_eod = get_instrument_eod_sync_info(db_path, "AI.PA")
    assert is_eod_fresh_today(sync_info_eod, min_bars_needed=20, prefer_source="eodhd") is True
    br_after = get_warehouse_eod_source_breakdown(db_path)
    assert br_after["yahoo_only_bars_symbols"] == []
    assert br_after["eodhd_bars_symbols_count"] == 1


def test_screener_hydrate_and_upgrade_warehouse_migrate_yahoo_to_eodhd(tmp_path: Path):
    from app.finance_funds import upgrade_warehouse_to_eodhd
    from app.finance_screener import hydrate_screener_universe
    from app.finance_warehouse import get_warehouse_eod_source_breakdown, upsert_eod_bars

    settings = Settings(
        app_data_dir=tmp_path / "app",
        finance_data_dir=tmp_path / "fin",
        eod_historical_data_key=SecretStr("demo-eod-token"),
        demo_mode=False,
    )
    db_path = warehouse_db_path(settings)

    # Semer un titre entièrement issu de Yahoo Finance (barres + snapshot fondamentaux)
    y_bars = [{"date": f"2026-01-{d:02d}", "open": 50, "high": 52, "low": 49, "close": 51, "adjusted_close": 51, "volume": 500} for d in range(1, 25)]
    upsert_eod_bars(db_path, "SAP.DE", y_bars, "yahoo_finance", requested_limit=24)
    upsert_fundamental_facts(
        db_path,
        "SAP.DE",
        "annual",
        {"TotalRevenue": {"2024-12-28": 31_000_000_000.0}},
        STATEMENT_TYPE_BY_KEY,
        "yahoo_finance",
        "EUR",
    )
    save_snapshot(
        db_path,
        "SAP.DE",
        "yahoo_finance",
        "fundamentals",
        {"annual": {}},
        {"earnings_history": [], "highlights": {}, "currency": "EUR"},
        currency="EUR",
    )

    # 1. hydrate_screener_universe NE doit PAS sauter SAP.DE sous prétexte qu'il a un snapshot Yahoo frais
    hydrated_calls: list[str] = []

    async def _fake_dossier_for_hydrate(_settings, sym: str, refresh: bool = False):
        hydrated_calls.append(sym)
        return {"symbol": sym, "source_provider": "eodhd"}

    with patch("app.finance_dossier.get_financial_dossier", side_effect=_fake_dossier_for_hydrate):
        h_res = asyncio.run(
            hydrate_screener_universe(
                settings,
                universe_type="all",
                include_fundamentals=True,
                max_fundamentals=10,
                refresh_eod=False,
            )
        )
    assert hydrated_calls == ["SAP.DE"]
    assert h_res["fundamentals_enriched"] == 1
    assert h_res["fundamentals_cached"] == 0

    # 2. upgrade_warehouse_to_eodhd migre les barres Yahoo ET les fondamentaux Yahoo vers EODHD
    async def _fake_eod_bars(_client, ticker: str, _key: str, limit: int = 2600):
        if ticker == "SAP.XETRA":
            return list(reversed(y_bars))
        return []

    async def _fake_dossier_upgrade(_settings, sym: str, refresh: bool = False):
        assert refresh is True
        save_snapshot(
            db_path,
            sym,
            "eodhd",
            "fundamentals",
            _sample_eod_payload("SAP.XETRA"),
            {"earnings_history": [], "highlights": {}, "currency": "EUR"},
            currency="EUR",
        )
        return {"symbol": sym, "source_provider": "eodhd"}

    with (
        patch("app.finance.fetch_eodhd_historical_eod", side_effect=_fake_eod_bars),
        patch("app.finance_dossier.get_financial_dossier", side_effect=_fake_dossier_upgrade),
    ):
        up_res = asyncio.run(upgrade_warehouse_to_eodhd(settings))

    assert up_res["summary"]["skipped"] is False
    assert up_res["summary"]["bars_upgraded"] == 1
    assert up_res["summary"]["fundamentals_upgraded"] == 1
    br_after = get_warehouse_eod_source_breakdown(db_path)
    assert br_after["yahoo_only_bars_symbols_count"] == 0
    assert br_after["yahoo_only_fundamentals_count"] == 0
    assert br_after["eodhd_bars_symbols_count"] == 1
    assert br_after["eodhd_fundamentals_count"] == 1


def test_background_eodhd_upgrade_and_screener_hydrate_detach_cleanly(tmp_path: Path):
    from app import finance_funds
    from app.finance_funds import (
        get_daily_sync_status,
        start_eodhd_upgrade_background,
        start_screener_hydrate_background,
    )

    settings = Settings(
        app_data_dir=tmp_path / "app",
        finance_data_dir=tmp_path / "fin",
        eod_historical_data_key=SecretStr("demo-eod-token"),
        demo_mode=False,
    )

    async def _run() -> None:
        res_up = await start_eodhd_upgrade_background(settings)
        assert res_up["started"] is True
        task = finance_funds._ACTIVE_SYNC_TASK
        assert task is not None
        await task
        st = get_daily_sync_status()
        assert st["is_running"] is False
        assert st["last_message"] and "Mise à jour EODHD terminée" in st["last_message"]

        with patch(
            "app.finance_screener.hydrate_screener_universe",
            new=AsyncMock(
                return_value={
                    "indexed_count": 5,
                    "fundamentals_enriched": 2,
                    "fundamentals_cached": 3,
                    "fundamentals_errors": 0,
                }
            ),
        ):
            res_hy = await start_screener_hydrate_background(
                settings,
                universe_type="all",
                include_fundamentals=True,
                max_fundamentals=10,
            )
            assert res_hy["started"] is True
            task2 = finance_funds._ACTIVE_SYNC_TASK
            assert task2 is not None
            await task2
            st2 = get_daily_sync_status()
            assert st2["is_running"] is False
            assert st2["last_message"] and "Enrichissement Screener terminé" in st2["last_message"]

    asyncio.run(_run())


def test_russell_2000_composition_falls_back_to_iwm_etf_holdings(tmp_path: Path):
    from app.finance_indices import get_index_composition

    settings = Settings(
        app_data_dir=tmp_path / "app",
        finance_data_dir=tmp_path / "fin",
        eod_historical_data_key=SecretStr("demo-eod-token"),
        demo_mode=False,
    )

    called_urls: list[str] = []

    class _FakeResp:
        def __init__(self, status_code: int, payload: object):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    async def _fake_get(self, url: str, **kwargs):
        called_urls.append(url)
        if "RUT.INDX" in url and "filter=Components" in url:
            # Simuler l'indisponibilité licence FTSE Russell sur RUT.INDX
            return _FakeResp(200, {})
        if "IWM.US" in url and "filter=ETF_Data::Holdings" in url:
            return _FakeResp(
                200,
                {
                    "SMCI.US": {
                        "Code": "SMCI",
                        "Exchange": "US",
                        "Name": "Super Micro Computer",
                        "Sector": "Technology",
                        "Industry": "Computer Hardware",
                        "Assets_%": 0.45,
                    },
                    "FTAI.US": {
                        "Code": "FTAI",
                        "Exchange": "US",
                        "Name": "FTAI Aviation",
                        "Sector": "Industrials",
                        "Industry": "Aerospace",
                        "Assets_%": 0.52,
                    },
                    "CASH_USD": {
                        "Code": "CASH",
                        "Exchange": "US",
                        "Name": "Cash",
                        "Assets_%": 0.10,
                    },
                },
            )
        return _FakeResp(404, {})

    with patch("httpx.AsyncClient.get", new=_fake_get):
        res = asyncio.run(get_index_composition(settings, "RUT", refresh=True))

    assert res is not None
    assert res["index"]["source"] == "EODHD ETF (IWM.US)"
    assert res["index"]["constituents_count"] == 2
    # Trié par pondération décroissante et sans ligne CASH
    assert [c["eod_ticker"] for c in res["constituents"]] == ["FTAI.US", "SMCI.US"]
    assert res["constituents"][0]["weight_pct"] == 0.52
    assert any("RUT.INDX" in u and "filter=Components" in u for u in called_urls)
    assert any("IWM.US" in u and "filter=ETF_Data::Holdings" in u for u in called_urls)
