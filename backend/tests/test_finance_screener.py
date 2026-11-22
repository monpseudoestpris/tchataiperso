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

    from app.finance_funds import run_daily_sync_now
    from app.finance_indices import INDEX_DEFINITIONS
    from app.finance_warehouse import DEFAULT_SYNC_PREFERENCES, get_sync_preferences, save_sync_preferences

    settings = Settings(
        app_data_dir=tmp_path / "app_data",
        finance_data_dir=tmp_path / "finance_data",
        demo_mode=False,
    )
    db_path = warehouse_db_path(settings)

    # Par défaut : contenu complet des 9 principaux indices + fondamentaux Screener activés
    defaults = get_sync_preferences(db_path)
    assert DEFAULT_SYNC_PREFERENCES["major_indices_constituents"] is True
    assert defaults["major_indices_constituents"] is True
    assert defaults["screener_fundamentals"] is True
    assert defaults["screener_fundamentals_daily_cap"] == 40

    major_codes = [d["code"] for d in INDEX_DEFINITIONS if d.get("tier") == "major"]
    assert len(major_codes) == 9

    called_codes: list[str] = []

    async def _fake_index_perf(_settings, code: str, refresh: bool = False):
        called_codes.append(code)
        return {
            "summary": {"loaded_count": 2, "from_cache_count": 1, "fetched_count": 1},
            "items": [{"symbol": f"TST_{code}.PA", "eod_ticker": f"TST_{code}.PA"}],
        }

    hydrate_calls: list[dict] = []

    async def _fake_hydrate(_settings, **kwargs):
        hydrate_calls.append(kwargs)
        return {"fundamentals_enriched": 3, "fundamentals_cached": 6, "fundamentals_errors": 0}

    with (
        patch("app.finance_indices.list_principal_indices", new=AsyncMock(return_value={"indices": [{"code": c} for c in major_codes]})),
        patch("app.finance_indices.list_eodhd_indx_catalog", new=AsyncMock(return_value={"total": 100})),
        patch("app.finance_indices.get_index_performances", side_effect=_fake_index_perf),
        patch("app.finance_screener.hydrate_screener_universe", side_effect=_fake_hydrate),
    ):
        res = asyncio.run(run_daily_sync_now(settings, refresh=False, respect_enabled=True))

    assert res["summary"]["skipped"] is False
    assert called_codes == major_codes
    assert set(res["summary"]["indices"].keys()) == set(major_codes)
    assert len(hydrate_calls) == 1
    assert hydrate_calls[0]["max_fundamentals"] == 40
    assert res["summary"]["screener_fundamentals"]["enriched"] == 3

    # Si l'utilisateur désactive `major_indices_constituents`, seul `index_codes` est synchronisé
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
    hydrate_calls.clear()
    with (
        patch("app.finance_indices.get_index_performances", side_effect=_fake_index_perf),
        patch("app.finance_screener.hydrate_screener_universe", side_effect=_fake_hydrate),
    ):
        res2 = asyncio.run(run_daily_sync_now(settings, refresh=False, respect_enabled=True))

    assert called_codes == ["SBF120"]
    assert hydrate_calls == []
    assert list(res2["summary"]["indices"].keys()) == ["SBF120"]
