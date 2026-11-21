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
