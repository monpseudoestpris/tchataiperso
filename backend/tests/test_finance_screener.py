"""Tests du moteur Screener boursier (`finance_screener.py` + `finance_warehouse.py`)."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from app.config import Settings
from app.finance_screener import (
    _POST_FILTER_EVALUATORS,
    get_screener_metadata,
    query_screener,
    rebuild_screener_snapshots_from_warehouse,
    register_post_filter_evaluator,
)
from app.finance_warehouse import (
    save_index_constituents,
    upsert_eod_bars,
    upsert_instrument,
    upsert_screener_snapshots,
    warehouse_db_path,
)


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=True,
    )


def _make_bars(count: int, start: float, step: float) -> list[dict]:
    base = datetime.date(2025, 1, 2)
    out = []
    for i in range(count):
        c = max(2.0, start + i * step)
        out.append(
            {
                "date": (base + datetime.timedelta(days=i)).isoformat(),
                "open": c - 0.2,
                "high": c + 0.8,
                "low": max(1.0, c - 0.8),
                "close": c,
                "adjusted_close": c,
                "volume": 200_000,
            }
        )
    return out


def test_screener_rebuild_and_combined_filters(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)

    upsert_instrument(
        db_path,
        {
            "symbol": "AI.PA",
            "eod_ticker": "AI.PA",
            "yahoo_symbol": "AI.PA",
            "short_name": "Air Liquide",
            "long_name": "Air Liquide S.A.",
            "exchange": "PA",
            "currency": "EUR",
            "sector": "Basic Materials",
        },
    )
    upsert_instrument(
        db_path,
        {
            "symbol": "MC.PA",
            "eod_ticker": "MC.PA",
            "yahoo_symbol": "MC.PA",
            "short_name": "LVMH",
            "long_name": "LVMH Moet Hennessy",
            "exchange": "PA",
            "currency": "EUR",
            "sector": "Consumer Cyclical",
        },
    )
    upsert_eod_bars(db_path, "AI.PA", _make_bars(240, 140.0, 0.25), "eodhd")
    upsert_eod_bars(db_path, "MC.PA", _make_bars(240, 800.0, -0.8), "eodhd")
    save_index_constituents(
        db_path,
        "CAC40",
        [
            {"symbol": "AI.PA", "eod_ticker": "AI.PA", "yahoo_symbol": "AI.PA", "name": "Air Liquide"},
            {"symbol": "MC.PA", "eod_ticker": "MC.PA", "yahoo_symbol": "MC.PA", "name": "LVMH"},
        ],
    )

    rebuilt = rebuild_screener_snapshots_from_warehouse(db_path)
    assert rebuilt["indexed_count"] == 2

    # Injecter des métriques fondamentales distinctes pour tester le filtrage combiné
    upsert_screener_snapshots(
        db_path,
        [
            {
                "symbol": "AI.PA",
                "market_cap": 95_000_000_000,
                "pe_ttm": 24.5,
                "roic_pct": 14.2,
                "ih_score": 7.0,
                "has_fundamentals": 1,
                "bars_count": 240,
            },
            {
                "symbol": "MC.PA",
                "market_cap": 310_000_000_000,
                "pe_ttm": 21.0,
                "roic_pct": 18.5,
                "ih_score": 8.0,
                "has_fundamentals": 1,
                "bars_count": 240,
            },
        ],
        preserve_fundamentals_if_missing=True,
    )

    # Filtre combiné : indice CAC40 + Cours > SMA 200 (technique) + ROIC >= 12% (fondamental)
    res = query_screener(
        settings,
        universe_type="index",
        universe_value="CAC40",
        rules=[
            {"kind": "compare", "left": "price", "op": "gt", "right": "sma200"},
            {"kind": "metric", "field": "roic_pct", "op": "gte", "value": 12},
            {"kind": "signal", "field": "supertrend_dir", "op": "eq", "value": 1},
        ],
        sort_by="roic_pct",
        sort_dir="desc",
    )
    assert res["universe_total"] == 2
    assert res["total"] == 1
    assert res["items"][0]["symbol"] == "AI.PA"
    assert res["items"][0]["has_fundamentals"] is True
    assert "CAC40" in res["items"][0]["indices"]


def test_screener_rejects_sql_injection_and_unknown_fields(tmp_path: Path):
    settings = _settings_for(tmp_path)
    with pytest.raises(ValueError):
        query_screener(
            settings,
            rules=[{"kind": "metric", "field": "pe_ttm; DROP TABLE finance_instruments;--", "op": "lt", "value": 10}],
        )
    with pytest.raises(ValueError):
        query_screener(
            settings,
            rules=[{"kind": "compare", "left": "price", "op": "gt", "right": "pe_ttm"}],
        )
    with pytest.raises(ValueError):
        query_screener(
            settings,
            rules=[{"kind": "metric", "field": "rsi_14", "op": "exec", "value": 30}],
        )


def test_screener_formula_post_filter_extension_hook(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)
    upsert_screener_snapshots(
        db_path,
        [
            {"symbol": "AAA.PA", "name": "Alpha", "price": 50.0, "roic_pct": 10.0, "rsi_14": 35.0, "has_fundamentals": 1, "bars_count": 100},
            {"symbol": "BBB.PA", "name": "Beta", "price": 80.0, "roic_pct": 20.0, "rsi_14": 45.0, "has_fundamentals": 1, "bars_count": 100},
        ],
    )

    # En V1 sans évaluateur enregistré, kind="formula" renvoie une ValueError propre
    with pytest.raises(ValueError):
        query_screener(settings, rules=[{"kind": "formula", "expression": "roic_pct > 15"}])

    # Branchement d'un évaluateur Passe 2 personnalisé (preuve d'extensibilité V2)
    try:
        register_post_filter_evaluator(
            "formula",
            lambda _db, rows, rule: [r for r in rows if (r.get("roic_pct") or 0) > float(rule.get("min_roic", 0))],
        )
        res = query_screener(
            settings,
            rules=[{"kind": "formula", "min_roic": 15}],
        )
        assert res["total"] == 1
        assert res["items"][0]["symbol"] == "BBB.PA"
        meta = get_screener_metadata(settings)
        assert "formula" in meta["formula_engine"]["registered_kinds"]
    finally:
        _POST_FILTER_EVALUATORS.pop("formula", None)


def test_screener_multi_timeframe_and_isopressure_20_gt_50(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)

    # Construire un titre qui repart franchement à la hausse après une baisse (IsoPressure 20 > 50)
    # et un titre qui se retourne franchement à la baisse après une hausse (IsoPressure 20 < 50)
    base = datetime.date(2019, 1, 2)
    bull_bars = []
    bear_bars = []
    for i in range(2400):
        dt = (base + datetime.timedelta(days=i)).isoformat()
        # BULL : baisse lente puis accélération haussière croissante jusqu'au dernier jour
        if i < 1900:
            c_bull = 200.0 - i * 0.05 + (1.2 if i % 4 == 0 else -0.4)
        else:
            t = (i - 1900) / 100.0
            c_bull = 105.0 + 3.0 * t + 2.5 * (t ** 2) + (0.2 if i % 2 == 0 else 0.0)
        # BEAR : hausse lente puis accélération baissière croissante jusqu'au dernier jour
        if i < 1900:
            c_bear = 80.0 + i * 0.08 + (1.0 if i % 4 == 0 else -0.3)
        else:
            t = (i - 1900) / 100.0
            c_bear = max(5.0, 232.0 - 3.0 * t - 4.0 * (t ** 2) - (0.2 if i % 2 == 0 else 0.0))
        bull_bars.append({"date": dt, "open": c_bull - 0.1, "high": c_bull + 0.8, "low": max(1.0, c_bull - 0.8), "close": c_bull, "adjusted_close": c_bull, "volume": 150_000})
        bear_bars.append({"date": dt, "open": c_bear + 0.1, "high": c_bear + 0.8, "low": max(1.0, c_bear - 0.8), "close": c_bear, "adjusted_close": c_bear, "volume": 150_000})

    upsert_instrument(db_path, {"symbol": "BULL.PA", "eod_ticker": "BULL.PA", "short_name": "Bull Corp", "exchange": "PA", "currency": "EUR"})
    upsert_instrument(db_path, {"symbol": "BEAR.PA", "eod_ticker": "BEAR.PA", "short_name": "Bear Corp", "exchange": "PA", "currency": "EUR"})
    upsert_eod_bars(db_path, "BULL.PA", bull_bars, "eodhd")
    upsert_eod_bars(db_path, "BEAR.PA", bear_bars, "eodhd")

    rebuilt = rebuild_screener_snapshots_from_warehouse(db_path)
    assert rebuilt["indexed_count"] == 2

    # 1. Filtrer IsoPressure 20 > IsoPressure 50 en Semaine (week) et en Mois (month)
    for tf in ("day", "week", "month"):
        res = query_screener(
            settings,
            timeframe=tf,
            rules=[{"kind": "compare", "left": "isopressure_p20", "op": "gt", "right": "isopressure_p50"}],
            sort_by="isopressure_20_50_diff",
            sort_dir="desc",
        )
        assert res["timeframe"] == tf
        assert res["total"] == 1
        assert res["items"][0]["symbol"] == "BULL.PA"
        assert res["items"][0]["isopressure_p20"] > res["items"][0]["isopressure_p50"]

    # 2. Mix multi-unités dans la même requête : IsoPressure 20 > 50 en Mois + Cours > SMA 50 en Semaine
    mixed = query_screener(
        settings,
        timeframe="day",
        rules=[
            {"kind": "compare", "left": "isopressure_p20", "op": "gt", "right": "isopressure_p50", "timeframe": "month"},
            {"kind": "compare", "left": "price", "op": "gt", "right": "sma50", "timeframe": "week"},
        ],
    )
    assert mixed["total"] == 1
    assert mixed["items"][0]["symbol"] == "BULL.PA"

    # 3. Unité 3 Mois (quarter) acceptée et retourne les barres agrégées trimestrielles
    q_res = query_screener(settings, timeframe="quarter")
    assert q_res["timeframe"] == "quarter"
    assert q_res["total"] == 2
    assert q_res["items"][0]["tf_bars_count"] >= 20


def test_daily_sync_auto_fetches_major_indices_constituents_and_fundamentals(tmp_path: Path):
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app.finance_funds import get_daily_sync_status, run_daily_sync_now
    from app.finance_indices import INDEX_DEFINITIONS
    from app.finance_warehouse import DEFAULT_SYNC_PREFERENCES, get_sync_preferences, save_sync_preferences

    settings = Settings(
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=False,
    )
    db_path = warehouse_db_path(settings)

    # Par défaut : contenu complet des 9 principaux indices + file priorisée des fondamentaux (budget 10 %)
    defaults = get_sync_preferences(db_path)
    assert DEFAULT_SYNC_PREFERENCES["major_indices_constituents"] is True
    assert defaults["major_indices_constituents"] is True
    assert defaults["screener_fundamentals"] is True
    assert defaults["fundamentals_budget_pct"] == 10
    assert defaults["fundamentals_priority_order"] == ["watchlists", "indices", "full_exchanges"]

    major_codes = [d["code"] for d in INDEX_DEFINITIONS if d.get("tier") == "major"]
    assert len(major_codes) == 9

    called_codes: list[str] = []

    async def _fake_index_perf(_settings, code: str, refresh: bool = False):
        called_codes.append(code)
        return {
            "summary": {"loaded_count": 2, "from_cache_count": 1, "fetched_count": 1},
            "items": [{"symbol": f"TST_{code}.PA", "eod_ticker": f"TST_{code}.PA"}],
        }

    budget_calls: list[int] = []

    async def _fake_budget(_settings, **_kwargs):
        budget_calls.append(1)
        return {"loaded": 3, "errors": 0, "calls": 33, "stopped_reason": "Budget du jour atteint"}

    def _patches():
        return (
            patch("app.finance_indices.list_principal_indices", new=AsyncMock(return_value={"indices": [{"code": c} for c in major_codes]})),
            patch("app.finance_indices.list_eodhd_indx_catalog", new=AsyncMock(return_value={"total": 100})),
            patch("app.finance_indices.get_index_performances", side_effect=_fake_index_perf),
            patch("app.finance_fundamentals_scheduler.run_fundamentals_budget", side_effect=_fake_budget),
        )

    p1, p2, p3, p4 = _patches()
    with p1, p2, p3, p4:
        res = asyncio.run(run_daily_sync_now(settings, refresh=False, respect_enabled=True, trigger="auto"))

    assert res["summary"]["skipped"] is False
    assert called_codes == major_codes
    assert set(res["summary"]["indices"].keys()) == set(major_codes)
    assert budget_calls == [1]
    assert res["summary"]["screener_fundamentals"]["enriched"] == 3
    assert res["summary"]["screener_fundamentals"]["calls"] == 33
    assert res["preferences"]["last_fundamentals_run_at"] is not None
    status_after = get_daily_sync_status()
    assert status_after["is_running"] is False
    assert status_after["percent"] == 100

    # Deuxième exécution : la file est consultée chaque jour (c'est elle qui limite au budget et aux échéances)
    called_codes.clear()
    p1, p2, p3, p4 = _patches()
    with p1, p2, p3, p4:
        asyncio.run(run_daily_sync_now(settings, refresh=False, respect_enabled=True, trigger="auto"))
    assert called_codes == major_codes
    assert budget_calls == [1, 1]

    # Si l'utilisateur désactive `major_indices_constituents` et les fondamentaux, seul `index_codes` est synchronisé
    save_sync_preferences(
        db_path,
        {
            "enabled": True,
            "principal_indices": False,
            "major_indices_constituents": False,
            "screener_fundamentals": False,
            "indx_catalog": False,
            "index_codes": ["SBF120"],
        },
    )
    called_codes.clear()
    budget_calls.clear()
    with (
        patch("app.finance_indices.get_index_performances", side_effect=_fake_index_perf),
        patch("app.finance_fundamentals_scheduler.run_fundamentals_budget", side_effect=_fake_budget),
    ):
        res2 = asyncio.run(run_daily_sync_now(settings, refresh=False, respect_enabled=True))

    assert called_codes == ["SBF120"]
    assert budget_calls == []
    assert list(res2["summary"]["indices"].keys()) == ["SBF120"]


def test_screener_filters_by_index_zone_country_exchange_currency_and_cap(tmp_path: Path):
    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)

    upsert_screener_snapshots(
        db_path,
        [
            {
                "symbol": "AI.PA",
                "eod_ticker": "AI.PA",
                "name": "Air Liquide",
                "exchange": "PA",
                "country": "",  # Déduit automatiquement de PA -> France / europe + eurozone
                "currency": "EUR",
                "sector": "Basic Materials",
                "cap_category": "Large Cap",
                "indices_csv": ",CAC40,EUROSTOXX50,",
                "market_cap": 95_000_000_000,
                "price": 175.0,
                "has_fundamentals": 1,
                "bars_count": 100,
            },
            {
                "symbol": "SAP.XETRA",
                "eod_ticker": "SAP.XETRA",
                "name": "SAP SE",
                "exchange": "XETRA",
                "country": "Germany",  # Normalisé -> Allemagne / europe + eurozone
                "currency": "EUR",
                "sector": "Technology",
                "cap_category": "Mega Cap",
                "indices_csv": ",DAX40,EUROSTOXX50,",
                "market_cap": 260_000_000_000,
                "price": 220.0,
                "has_fundamentals": 1,
                "bars_count": 100,
            },
            {
                "symbol": "NESN.SW",
                "eod_ticker": "NESN.SW",
                "name": "Nestlé",
                "exchange": "SW",
                "country": "Switzerland",  # Normalisé -> Suisse / europe (hors Zone Euro)
                "currency": "CHF",
                "sector": "Consumer Defensive",
                "cap_category": "Mega Cap",
                "indices_csv": ",SMI20,STOXX600,",
                "market_cap": 230_000_000_000,
                "price": 85.0,
                "has_fundamentals": 1,
                "bars_count": 100,
            },
            {
                "symbol": "AAPL.US",
                "eod_ticker": "AAPL.US",
                "name": "Apple Inc.",
                "exchange": "US",
                "country": "USA",  # Normalisé -> États-Unis / north_america
                "currency": "USD",
                "sector": "Technology",
                "cap_category": "Mega Cap",
                "indices_csv": ",SP500,NASDAQ100,",
                "market_cap": 3_400_000_000_000,
                "price": 230.0,
                "has_fundamentals": 1,
                "bars_count": 100,
            },
            {
                "symbol": "7203.T",
                "eod_ticker": "7203.T",
                "name": "Toyota Motor",
                "exchange": "TSE",
                "country": "",  # Déduit -> Japon / asia_pacific
                "currency": "JPY",
                "sector": "Consumer Cyclical",
                "cap_category": "Mega Cap",
                "indices_csv": ",NIKKEI225,",
                "market_cap": 280_000_000_000,
                "price": 2800.0,
                "has_fundamentals": 1,
                "bars_count": 100,
            },
        ],
    )

    # 1. Métadonnées / facettes enrichies
    meta = get_screener_metadata(settings)
    cov = meta["coverage"]
    zone_map = {z["code"]: z["count"] for z in cov["market_zones"]}
    assert zone_map["eurozone"] == 2
    assert zone_map["europe"] == 3
    assert zone_map["north_america"] == 1
    assert zone_map["asia_pacific"] == 1

    country_map = {c["code"]: c["count"] for c in cov["countries"]}
    assert country_map["France"] == 1
    assert country_map["Allemagne"] == 1
    assert country_map["Suisse"] == 1
    assert country_map["États-Unis"] == 1
    assert country_map["Japon"] == 1

    idx_map = {i["code"]: i["count"] for i in cov["indices"]}
    assert idx_map["EUROSTOXX50"] == 2
    assert idx_map["CAC40"] == 1
    assert idx_map["STOXX600"] == 1

    # 2. Filtre par zone boursière : Zone Euro vs Europe vs Amérique du Nord vs Asie-Pacifique
    ez = query_screener(settings, market_zone="eurozone")
    assert {r["symbol"] for r in ez["items"]} == {"AI.PA", "SAP.XETRA"}

    eu = query_screener(settings, market_zone="europe")
    assert {r["symbol"] for r in eu["items"]} == {"AI.PA", "SAP.XETRA", "NESN.SW"}

    na = query_screener(settings, market_zone="north_america")
    assert [r["symbol"] for r in na["items"]] == ["AAPL.US"]

    apac = query_screener(settings, market_zone="asia_pacific")
    assert [r["symbol"] for r in apac["items"]] == ["7203.T"]

    # 3. Filtre par pays (nom français ou alias anglais acceptés)
    fr = query_screener(settings, country="France")
    assert [r["symbol"] for r in fr["items"]] == ["AI.PA"]
    us_alias = query_screener(settings, country="USA")
    assert [r["symbol"] for r in us_alias["items"]] == ["AAPL.US"]

    # 4. Combinaison Indice + Pays + Devise + Cap
    combo = query_screener(
        settings,
        index_code="EUROSTOXX50",
        country="Allemagne",
        currency="EUR",
        cap_category="Mega Cap",
    )
    assert [r["symbol"] for r in combo["items"]] == ["SAP.XETRA"]
    assert combo["items"][0]["market_zone"] == "europe"
    assert combo["items"][0]["country"] == "Allemagne"


def test_screener_lists_all_exchange_catalog_stocks_without_loading_prices(tmp_path: Path):
    from app.finance_warehouse import replace_exchange_symbols, seed_screener_from_exchange_catalogs

    settings = _settings_for(tmp_path)
    db_path = warehouse_db_path(settings)

    # Titre déjà indexé avec cours (constituant d'indice) + catalogue complet Euronext Paris
    upsert_screener_snapshots(
        db_path,
        [{"symbol": "AI.PA", "eod_ticker": "AI.PA", "name": "Air Liquide", "exchange": "PA", "price": 175.0, "bars_count": 100}],
    )
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
    replace_exchange_symbols(
        db_path,
        "XETRA",
        [{"symbol": "SAP", "eod_ticker": "SAP.XETRA", "name": "SAP SE", "country": "Germany", "currency": "EUR", "type": "Common Stock"}],
    )

    assert seed_screener_from_exchange_catalogs(db_path) == 3  # ALO, VIRP, SAP (AI.PA déjà présent, ETF exclu)
    assert seed_screener_from_exchange_catalogs(db_path) == 0  # Idempotent

    paris = query_screener(settings, exchange="PA")
    assert paris["total"] == 3
    assert paris["items"][0]["symbol"] == "AI.PA"  # Le titre avec données reste en tête (valeurs NULL en fin)
    alstom = next(r for r in paris["items"] if r["symbol"] == "ALO.PA")
    assert alstom["price"] is None and alstom["country"] == "France" and alstom["market_zone"] == "europe"

    # Lorsque SAP est indexé ensuite sous une autre clé canonique, la ligne catalogue est remplacée (pas de doublon)
    upsert_screener_snapshots(
        db_path,
        [{"symbol": "SAP.DE", "eod_ticker": "SAP.XETRA", "yahoo_symbol": "SAP.DE", "name": "SAP SE", "exchange": "XETRA", "price": 220.0, "bars_count": 100}],
    )
    de = query_screener(settings, country="Allemagne")
    assert [r["symbol"] for r in de["items"]] == ["SAP.DE"]

    # Compteur de titres sans données + sélection du lot à compléter (filtrée, sans les titres déjà chargés)
    assert paris["missing_data_count"] == 2
    missing = query_screener(settings, exchange="PA", only_missing_data=True, limit=50)
    assert {r["symbol"] for r in missing["items"]} == {"ALO.PA", "VIRP.PA"}


def test_screener_etf_counts_by_exchange_independent_seeding_and_bars_hydration(tmp_path: Path):
    import sqlite3
    from unittest.mock import AsyncMock, MagicMock, patch
    import httpx
    from tests.test_api import authenticated_client
    from app.finance_warehouse import (
        _INITIALIZED_PATHS,
        get_etf_exchange_catalog_counts,
        init_warehouse,
        replace_exchange_symbols,
        seed_etfs_from_exchange_catalog,
        seed_screener_from_exchange_catalogs,
    )

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=False,
        eod_historical_data_key="test-key",
    )
    db_path = warehouse_db_path(settings)

    # 1. Migration douce d'un ancien schéma sans colonne `asset_type`
    legacy_db = tmp_path / "legacy_warehouse.db"
    with sqlite3.connect(legacy_db) as conn:
        conn.executescript(
            """
            CREATE TABLE finance_instruments (
                symbol TEXT PRIMARY KEY, eod_ticker TEXT, yahoo_symbol TEXT, short_name TEXT, long_name TEXT, updated_at TEXT
            );
            CREATE TABLE finance_exchange_symbols (
                exchange_code TEXT NOT NULL, symbol TEXT NOT NULL, eod_ticker TEXT NOT NULL,
                name TEXT NOT NULL, isin TEXT, fund_family TEXT, country TEXT, currency TEXT, type TEXT, fetched_at REAL NOT NULL,
                PRIMARY KEY (exchange_code, symbol)
            ) WITHOUT ROWID;
            CREATE TABLE finance_user_watchlist_items (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, list_id TEXT NOT NULL, symbol TEXT NOT NULL, name TEXT NOT NULL, position INTEGER DEFAULT 0);
            CREATE TABLE finance_sync_preferences (pref_key TEXT PRIMARY KEY, config_json TEXT NOT NULL, last_run_at TEXT, last_status_json TEXT, updated_at TEXT NOT NULL);
            CREATE TABLE finance_screener_snapshots (
                symbol TEXT PRIMARY KEY, eod_ticker TEXT, yahoo_symbol TEXT, name TEXT NOT NULL DEFAULT '',
                exchange TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT '', market_zone TEXT NOT NULL DEFAULT '',
                currency TEXT NOT NULL DEFAULT '', sector TEXT NOT NULL DEFAULT '', industry TEXT NOT NULL DEFAULT '',
                cap_category TEXT NOT NULL DEFAULT '', indices_csv TEXT NOT NULL DEFAULT '',
                market_cap REAL, pe_ttm REAL, roic_pct REAL, ih_score REAL, piotroski_f REAL, rsi_14 REAL,
                computed_at TEXT NOT NULL
            );
            INSERT INTO finance_exchange_symbols VALUES ('PA', 'CW8', 'CW8.PA', 'Amundi MSCI World', NULL, NULL, 'France', 'EUR', 'ETF', 1700000000.0);
            INSERT INTO finance_screener_snapshots (symbol, eod_ticker, name, exchange, computed_at)
            VALUES ('CW8.PA', 'CW8.PA', 'Amundi MSCI World', 'PA', '2026-11-23T00:00:00Z');
            """
        )
    _INITIALIZED_PATHS.discard(str(legacy_db))
    init_warehouse(legacy_db)
    with sqlite3.connect(legacy_db) as conn:
        migrated_type = conn.execute("SELECT asset_type FROM finance_screener_snapshots WHERE symbol = 'CW8.PA'").fetchone()[0]
    assert migrated_type == "etf"

    # 2. Catalogues PA et XETRA déjà synchronisés, US pas encore synchronisé
    replace_exchange_symbols(
        db_path,
        "PA",
        [
            {"symbol": "AI", "eod_ticker": "AI.PA", "name": "Air Liquide", "country": "France", "currency": "EUR", "type": "Common Stock"},
            {"symbol": "CW8", "eod_ticker": "CW8.PA", "name": "Amundi MSCI World UCITS ETF", "country": "France", "currency": "EUR", "type": "ETF"},
            {"symbol": "EWLD", "eod_ticker": "EWLD.PA", "name": "Lyxor MSCI World UCITS ETF", "country": "France", "currency": "EUR", "type": "ETF"},
        ],
    )
    replace_exchange_symbols(
        db_path,
        "XETRA",
        [
            {"symbol": "EXS1", "eod_ticker": "EXS1.XETRA", "name": "iShares Core DAX UCITS ETF", "country": "Germany", "currency": "EUR", "type": "ETF"},
        ],
    )
    seed_screener_from_exchange_catalogs(db_path)

    counts_before = {c["code"]: c for c in get_etf_exchange_catalog_counts(db_path)}
    assert counts_before["PA"]["catalog_synced"] is True
    assert counts_before["PA"]["etf_catalog_count"] == 2
    assert counts_before["PA"]["etf_in_screener_count"] == 0
    assert counts_before["XETRA"]["etf_catalog_count"] == 1
    assert counts_before["US"]["catalog_synced"] is False
    assert counts_before["US"]["etf_catalog_count"] == 0

    # 3. Chargement indépendant de PA uniquement (XETRA reste non chargé dans le Screener)
    seeded_pa = seed_etfs_from_exchange_catalog(db_path, ["PA"])
    assert seeded_pa == {"PA": 2}

    etf_only = query_screener(settings, asset_type="etf")
    assert etf_only["total"] == 2
    assert {r["symbol"] for r in etf_only["items"]} == {"CW8.PA", "EWLD.PA"}
    assert all(r["asset_type"] == "etf" and r["exchange"] == "PA" for r in etf_only["items"])
    assert etf_only["coverage"]["stock_count"] == 1
    assert etf_only["coverage"]["etf_count"] == 2

    stock_only = query_screener(settings, asset_type="stock", exchange="PA")
    assert [r["symbol"] for r in stock_only["items"]] == ["AI.PA"]

    # 4. Endpoints API : compter une bourse avant chargement (seed_screener=False), puis charger (seed_screener=True)
    us_catalog_payload = [
        {"Code": "SPY", "Name": "SPDR S&P 500 ETF Trust", "Country": "USA", "Currency": "USD", "Type": "ETF"},
        {"Code": "QQQ", "Name": "Invesco QQQ Trust", "Country": "USA", "Currency": "USD", "Type": "ETF"},
        {"Code": "AAPL", "Name": "Apple Inc.", "Country": "USA", "Currency": "USD", "Type": "Common Stock"},
    ]
    req = httpx.Request("GET", "https://eodhd.com/api/exchange-symbol-list/US")
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=httpx.Response(200, request=req, json=us_catalog_payload))

    with authenticated_client(settings) as client:
        res_list = client.get("/api/finance/screener/etf-exchanges")
        assert res_list.status_code == 200
        ex_map = {e["code"]: e for e in res_list.json()["exchanges"]}
        assert ex_map["PA"]["etf_in_screener_count"] == 2
        assert ex_map["XETRA"]["etf_in_screener_count"] == 0

        # Étape A : compter les ETFs de US sans rien ajouter au Screener
        with patch("app.finance_funds.httpx.AsyncClient", return_value=fake_client):
            res_count = client.post(
                "/api/finance/screener/etf-exchanges/load",
                json={"exchange": "US", "seed_screener": False},
            )
        assert res_count.status_code == 200
        count_body = res_count.json()
        assert count_body["seeded_count"] == 0
        assert count_body["exchange_info"]["catalog_synced"] is True
        assert count_body["exchange_info"]["etf_catalog_count"] == 2
        assert count_body["exchange_info"]["etf_in_screener_count"] == 0
        assert query_screener(settings, asset_type="etf", exchange="US")["total"] == 0

        # Étape B : charger les 2 ETFs US dans le Screener (0 appel réseau)
        res_seed_us = client.post(
            "/api/finance/screener/etf-exchanges/load",
            json={"exchange": "US", "seed_screener": True},
        )
        assert res_seed_us.status_code == 200
        seed_body = res_seed_us.json()
        assert seed_body["seeded_count"] == 2
        assert seed_body["exchange_info"]["etf_in_screener_count"] == 2

        us_etfs = client.post(
            "/api/finance/screener/query",
            json={"asset_type": "etf", "exchange": "US"},
        )
        assert us_etfs.status_code == 200
        us_body = us_etfs.json()
        assert us_body["total"] == 2
        assert {r["symbol"] for r in us_body["items"]} == {"QQQ.US", "SPY.US"}

        # 5. Hydratation EOD légère (1 call / ETF) pour PA sans écraser les noms du catalogue
        bars_240 = _make_bars(240, 450.0, 0.35)
        with patch("app.finance_dossier._fetch_eodhd_bars_range", new=AsyncMock(return_value=bars_240)):
            res_hyd = client.post(
                "/api/finance/screener/hydrate-bars",
                json={
                    "screener_filters": {"asset_type": "etf", "exchange": "PA"},
                    "batch_size": 50,
                    "background": False,
                },
            )
        assert res_hyd.status_code == 200
        hyd_body = res_hyd.json()
        assert hyd_body["targeted"] == 2
        assert hyd_body["loaded"] == 2
        assert hyd_body["calls"] == 2

    pa_after = query_screener(settings, asset_type="etf", exchange="PA")
    assert pa_after["total"] == 2
    assert pa_after["missing_data_count"] == 0
    cw8 = next(r for r in pa_after["items"] if r["symbol"] == "CW8.PA")
    assert cw8["name"] == "Amundi MSCI World UCITS ETF"
    assert cw8["price"] is not None
    assert cw8["rsi_14"] is not None
    assert cw8["asset_type"] == "etf"
    counts_after = {c["code"]: c for c in get_etf_exchange_catalog_counts(db_path)}
    assert counts_after["PA"]["etf_with_data_count"] == 2
    assert counts_after["US"]["etf_with_data_count"] == 0
