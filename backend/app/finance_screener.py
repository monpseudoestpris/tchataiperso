"""Moteur du Screener Boursier intégré (Fondamentaux + Scores + Technique).

Architecture évolutive en 2 passes pensée dès la V1 pour accueillir des formules
personnalisées en V2 sans modification de schéma ni d'API :
  - Passe 1 (SQL SQLite WAL < 10 ms) : applique les filtres d'univers, de métriques
    (`kind="metric"`), de comparaisons entre champs (`kind="compare"`) et de signaux
    techniques (`kind="signal"`) sur la table matérialisée `finance_screener_snapshots`.
  - Passe 2 (Post-filtre Python extensible) : exécute les évaluateurs enregistrés via
    `register_post_filter_evaluator(...)` (ex. futures règles `kind="formula"` /
    `kind="custom_indicator"`) uniquement sur les candidats survivants de la Passe 1.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import math
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .finance_technicals import compute_technical_snapshot
from .finance_warehouse import (
    _connect,
    _norm_sym,
    _utc_iso,
    get_instrument_meta,
    get_screener_coverage,
    get_snapshot,
    get_stored_eod_bars,
    get_symbol_indices_map,
    list_warehouse_screener_symbols,
    load_fundamental_series,
    resolve_canonical_symbol,
    upsert_screener_snapshots,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Registre extensible Passe 2 (point d'ancrage V2 pour formules personnalisées)
# ---------------------------------------------------------------------------

PostFilterEvaluator = Callable[[Path, list[dict[str, Any]], dict[str, Any]], list[dict[str, Any]]]
_POST_FILTER_EVALUATORS: dict[str, PostFilterEvaluator] = {}


def register_post_filter_evaluator(kind: str, evaluator: PostFilterEvaluator) -> None:
    """Enregistre un évaluateur de post-filtre Passe 2 (ex. `formula`, `custom_indicator`)."""
    clean_kind = str(kind or "").strip().lower()
    if clean_kind:
        _POST_FILTER_EVALUATORS[clean_kind] = evaluator


def list_registered_post_filter_kinds() -> list[str]:
    """Retourne les types de règles Passe 2 actuellement enregistrés."""
    return sorted(_POST_FILTER_EVALUATORS.keys())


# ---------------------------------------------------------------------------
# Catalogue canonique des champs filtrables & triables (Whitelist SQL stricte)
# ---------------------------------------------------------------------------

SCREENER_FIELDS: tuple[dict[str, Any], ...] = (
    # Performance & Prix
    {"key": "price", "label": "Cours", "category": "performance", "type": "number", "unit": "currency", "comparable": True, "description": "Dernier cours de clôture EOD"},
    {"key": "market_cap", "label": "Capitalisation (M)", "category": "valuation", "type": "number", "unit": "millions", "scale": 1e6, "description": "Capitalisation boursière exprimée en millions"},
    {"key": "change_1d_pct", "label": "Variation 1J (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Variation journalière (%)"},
    {"key": "change_1w_pct", "label": "Variation 1 Sem. (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Variation sur 1 semaine (%)"},
    {"key": "change_1m_pct", "label": "Variation 1 Mois (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Variation sur 1 mois (%)"},
    {"key": "change_3m_pct", "label": "Variation 3 Mois (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Variation sur 3 mois (%)"},
    {"key": "change_ytd_pct", "label": "Variation YTD (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Variation depuis le 1er janvier (%)"},
    {"key": "change_1y_pct", "label": "Variation 1 An (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Variation sur 1 an (%)"},
    {"key": "dist_52w_high_pct", "label": "Écart Plus-Haut 52S (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Distance en % par rapport au plus haut 52 semaines"},
    {"key": "dist_52w_low_pct", "label": "Écart Plus-Bas 52S (%)", "category": "performance", "type": "number", "unit": "pct", "description": "Distance en % par rapport au plus bas 52 semaines"},
    {"key": "rel_volume_20d", "label": "Volume relatif (×20j)", "category": "technical", "type": "number", "unit": "ratio", "description": "Dernier volume / moyenne 20 séances"},
    # Valorisation
    {"key": "pe_ttm", "label": "PER (TTM)", "category": "valuation", "type": "number", "unit": "ratio", "description": "Ratio Cours / Bénéfice glissant 12 mois"},
    {"key": "pe_forward", "label": "PER Forward", "category": "valuation", "type": "number", "unit": "ratio", "description": "PER estimé sur les bénéfices futurs"},
    {"key": "peg_ratio", "label": "Ratio PEG", "category": "valuation", "type": "number", "unit": "ratio", "description": "PER rapporté à la croissance attendue"},
    {"key": "ev_ebitda", "label": "VE / EBITDA", "category": "valuation", "type": "number", "unit": "ratio", "description": "Valeur d'entreprise sur EBITDA"},
    {"key": "pb_ratio", "label": "Price / Book (P/B)", "category": "valuation", "type": "number", "unit": "ratio", "description": "Cours rapporté aux capitaux propres"},
    {"key": "fcf_yield_pct", "label": "FCF Yield (%)", "category": "valuation", "type": "number", "unit": "pct", "description": "Free Cash-Flow / Capitalisation boursière (%)"},
    {"key": "dividend_yield_pct", "label": "Rendement dividende (%)", "category": "valuation", "type": "number", "unit": "pct", "description": "Rendement annuel du dividende (%)"},
    {"key": "analyst_upside_pct", "label": "Potentiel analystes (%)", "category": "valuation", "type": "number", "unit": "pct", "description": "Écart entre l'objectif moyen analystes et le cours"},
    # Qualité, Rentabilité, Bilan & Croissance
    {"key": "roic_pct", "label": "ROIC (%)", "category": "quality", "type": "number", "unit": "pct", "description": "Rentabilité du capital investi (%)"},
    {"key": "roe_pct", "label": "ROE (%)", "category": "quality", "type": "number", "unit": "pct", "description": "Rentabilité des capitaux propres (%)"},
    {"key": "op_margin_pct", "label": "Marge opérationnelle (%)", "category": "quality", "type": "number", "unit": "pct", "description": "Résultat opérationnel / Chiffre d'affaires (%)"},
    {"key": "net_margin_pct", "label": "Marge nette (%)", "category": "quality", "type": "number", "unit": "pct", "description": "Résultat net / Chiffre d'affaires (%)"},
    {"key": "net_debt_ebitda", "label": "Dette nette / EBITDA", "category": "quality", "type": "number", "unit": "ratio", "description": "Levier financier (plus bas = bilan plus sain)"},
    {"key": "debt_to_equity_pct", "label": "Dette / Fonds propres (%)", "category": "quality", "type": "number", "unit": "pct", "description": "Ratio d'endettement sur capitaux propres (%)"},
    {"key": "current_ratio", "label": "Liquidité générale", "category": "quality", "type": "number", "unit": "ratio", "description": "Actif courant / Passif courant"},
    {"key": "rev_cagr_3y_pct", "label": "Croissance CA 3A (%/an)", "category": "quality", "type": "number", "unit": "pct", "description": "CAGR annuel du chiffre d'affaires sur 3 exercices"},
    {"key": "eps_cagr_3y_pct", "label": "Croissance BPA 3A (%/an)", "category": "quality", "type": "number", "unit": "pct", "description": "CAGR annuel du bénéfice par action sur 3 exercices"},
    {"key": "beta", "label": "Bêta", "category": "quality", "type": "number", "unit": "ratio", "description": "Sensibilité historique au marché"},
    # Scores & Valorisation intrinsèque
    {"key": "ih_score", "label": "IH Score (/9)", "category": "scores", "type": "number", "unit": "score9", "description": "Score qualité fondamental IH sur 9"},
    {"key": "piotroski_f", "label": "Piotroski F-Score (/9)", "category": "scores", "type": "number", "unit": "score9", "description": "Score de solidité financière Piotroski sur 9"},
    {"key": "altman_z", "label": "Altman Z-Score", "category": "scores", "type": "number", "unit": "ratio", "description": "Indicateur de solvabilité (> 3 = zone sûre)"},
    {"key": "mos_intrinsic_pct", "label": "Marge de Sécurité (%)", "category": "scores", "type": "number", "unit": "pct", "description": "Décote / surcote vs valeur intrinsèque pondérée (%)"},
    # Indicateurs techniques & Signaux
    {"key": "sma20", "label": "SMA 20", "category": "technical", "type": "number", "unit": "currency", "comparable": True, "description": "Moyenne mobile simple 20 séances"},
    {"key": "sma50", "label": "SMA 50", "category": "technical", "type": "number", "unit": "currency", "comparable": True, "description": "Moyenne mobile simple 50 séances"},
    {"key": "sma200", "label": "SMA 200", "category": "technical", "type": "number", "unit": "currency", "comparable": True, "description": "Moyenne mobile simple 200 séances"},
    {"key": "ema20", "label": "EMA 20", "category": "technical", "type": "number", "unit": "currency", "comparable": True, "description": "Moyenne mobile exponentielle 20 séances"},
    {"key": "ema50", "label": "EMA 50", "category": "technical", "type": "number", "unit": "currency", "comparable": True, "description": "Moyenne mobile exponentielle 50 séances"},
    {"key": "dist_sma50_pct", "label": "Écart SMA 50 (%)", "category": "technical", "type": "number", "unit": "pct", "description": "Position du cours par rapport à la SMA 50 (%)"},
    {"key": "dist_sma200_pct", "label": "Écart SMA 200 (%)", "category": "technical", "type": "number", "unit": "pct", "description": "Position du cours par rapport à la SMA 200 (%)"},
    {"key": "rsi_14", "label": "RSI (14)", "category": "technical", "type": "number", "unit": "index", "description": "Relative Strength Index (< 30 survente, > 70 surachat)"},
    {"key": "macd_hist", "label": "MACD Histogramme", "category": "technical", "type": "number", "unit": "ratio", "description": "Écart MACD − Signal (> 0 momentum haussier)"},
    {"key": "macd_cross", "label": "Croisement MACD (3j)", "category": "technical", "type": "signal", "options": [{"value": 1, "label": "Croisement haussier récent"}, {"value": -1, "label": "Croisement baissier récent"}], "description": "Signal de croisement MACD/Signal sur les 3 dernières séances"},
    {"key": "sma_golden_cross", "label": "Tendance SMA 50/200", "category": "technical", "type": "signal", "options": [{"value": 2, "label": "Golden Cross récent (≤ 5j)"}, {"value": 1, "label": "SMA 50 > SMA 200 (Haussier)"}, {"value": -1, "label": "SMA 50 < SMA 200 (Baissier)"}, {"value": -2, "label": "Death Cross récent (≤ 5j)"}], "description": "Position et croisement récent SMA 50 vs SMA 200"},
    {"key": "boll_pct_b", "label": "Bollinger %B (%)", "category": "technical", "type": "number", "unit": "pct", "description": "Position dans les bandes (0% = bande basse, 100% = bande haute)"},
    {"key": "boll_width_pct", "label": "Largeur Bollinger (%)", "category": "technical", "type": "number", "unit": "pct", "description": "Écart relatif des bandes (squeeze si faible)"},
    {"key": "adx_14", "label": "ADX (14)", "category": "technical", "type": "number", "unit": "index", "description": "Force de la tendance (> 25 tendance marquée)"},
    {"key": "stoch_k", "label": "Stochastique %K", "category": "technical", "type": "number", "unit": "index", "description": "Oscillateur stochastique 14j (0–100)"},
    {"key": "atr_pct", "label": "Volatilité ATR (%)", "category": "technical", "type": "number", "unit": "pct", "description": "ATR(14) rapporté au cours (%)"},
    {"key": "roc_12", "label": "ROC 12j (%)", "category": "technical", "type": "number", "unit": "pct", "description": "Momentum Rate of Change sur 12 séances"},
    {"key": "supertrend_dir", "label": "Supertrend (10, 3)", "category": "technical", "type": "signal", "options": [{"value": 1, "label": "Haussier (+1)"}, {"value": -1, "label": "Baissier (-1)"}], "description": "Direction courante du Supertrend"},
)

_FIELD_BY_KEY: dict[str, dict[str, Any]] = {f["key"]: f for f in SCREENER_FIELDS}
_SORTABLE_COLUMNS: frozenset[str] = frozenset(
    {"symbol", "name", "exchange", "sector", "bars_date", "has_fundamentals", *_FIELD_BY_KEY.keys()}
)
_COMPARABLE_COLUMNS: frozenset[str] = frozenset(
    f["key"] for f in SCREENER_FIELDS if f.get("comparable")
)

_ALLOWED_METRIC_OPS: dict[str, str] = {
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "=",
    "neq": "!=",
}

SCREENER_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "id": "quality_moat",
        "name": "Qualité & Moat (Buffett)",
        "description": "Entreprises rentables (ROIC ≥ 12 %, marge op. ≥ 15 %), peu endettées et IH Score élevé.",
        "sort_by": "roic_pct",
        "sort_dir": "desc",
        "rules": [
            {"kind": "metric", "field": "roic_pct", "op": "gte", "value": 12},
            {"kind": "metric", "field": "op_margin_pct", "op": "gte", "value": 15},
            {"kind": "metric", "field": "net_debt_ebitda", "op": "lte", "value": 2.5},
            {"kind": "metric", "field": "ih_score", "op": "gte", "value": 6},
        ],
    },
    {
        "id": "value_mos",
        "name": "Value & Marge de sécurité",
        "description": "Décote intrinsèque ≥ 15 %, Piotroski F-Score ≥ 6 et VE/EBITDA raisonnable.",
        "sort_by": "mos_intrinsic_pct",
        "sort_dir": "desc",
        "rules": [
            {"kind": "metric", "field": "mos_intrinsic_pct", "op": "gte", "value": 15},
            {"kind": "metric", "field": "piotroski_f", "op": "gte", "value": 6},
            {"kind": "metric", "field": "ev_ebitda", "op": "lte", "value": 12},
        ],
    },
    {
        "id": "garp_growth",
        "name": "GARP (Peter Lynch)",
        "description": "Croissance du CA ≥ 8 %/an, ROE ≥ 15 % et PEG ≤ 1,6.",
        "sort_by": "rev_cagr_3y_pct",
        "sort_dir": "desc",
        "rules": [
            {"kind": "metric", "field": "rev_cagr_3y_pct", "op": "gte", "value": 8},
            {"kind": "metric", "field": "roe_pct", "op": "gte", "value": 15},
            {"kind": "metric", "field": "peg_ratio", "op": "lte", "value": 1.6},
        ],
    },
    {
        "id": "oversold_uptrend",
        "name": "Rebond sur-vendu (Haussier)",
        "description": "Tendance de fond haussière (Cours > SMA 200) avec repli court terme (RSI 14 ≤ 40).",
        "sort_by": "rsi_14",
        "sort_dir": "asc",
        "rules": [
            {"kind": "compare", "left": "price", "op": "gt", "right": "sma200"},
            {"kind": "metric", "field": "rsi_14", "op": "lte", "value": 40},
        ],
    },
    {
        "id": "breakout_supertrend",
        "name": "Momentum & Supertrend",
        "description": "Supertrend haussier, alignement Cours > SMA 50 > SMA 200 et tendance ADX ≥ 20.",
        "sort_by": "change_3m_pct",
        "sort_dir": "desc",
        "rules": [
            {"kind": "signal", "field": "supertrend_dir", "op": "eq", "value": 1},
            {"kind": "compare", "left": "price", "op": "gt", "right": "sma50"},
            {"kind": "compare", "left": "sma50", "op": "gt", "right": "sma200"},
            {"kind": "metric", "field": "adx_14", "op": "gte", "value": 20},
        ],
    },
)


# ---------------------------------------------------------------------------
# Helpers d'extraction numérique & construction des snapshots
# ---------------------------------------------------------------------------

def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, dict):
        val = val.get("raw")
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round_opt(val: float | None, digits: int = 2) -> float | None:
    if val is None or not math.isfinite(val):
        return None
    return round(val, digits)


def _pct_norm(val: Any) -> float | None:
    v = _num(val)
    if v is None:
        return None
    return round(v * 100.0, 2) if abs(v) <= 2.5 else round(v, 2)


def _last_non_null(values: list[Any] | None) -> float | None:
    if not values:
        return None
    for v in reversed(values):
        n = _num(v)
        if n is not None:
            return n
    return None


def _find_table_latest(rows: list[dict[str, Any]] | None, key: str) -> float | None:
    for r in rows or []:
        if r.get("key") == key:
            return _last_non_null(r.get("values"))
    return None


def _cagr_from_series(date_map: dict[str, float | None] | None, years: int = 3) -> float | None:
    if not date_map:
        return None
    pts = [
        _num(date_map[d])
        for d in sorted(date_map.keys())
        if _num(date_map[d]) is not None
    ]
    valid = [v for v in pts if v is not None]
    if len(valid) < 2:
        return None
    step = min(years, len(valid) - 1)
    v0, v1 = valid[-1 - step], valid[-1]
    if v0 <= 0 or v1 <= 0 or step <= 0:
        return None
    return round(((v1 / v0) ** (1.0 / step) - 1.0) * 100.0, 2)


def _format_indices_csv(indices: list[str] | None) -> str:
    clean = sorted({_norm_sym(c) for c in (indices or []) if _norm_sym(c)})
    return f",{','.join(clean)}," if clean else ""


def _extract_scores_compact(uncle_stock_scores: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in (uncle_stock_scores or {}).get("items") or []:
        if not item.get("available"):
            continue
        sid = str(item.get("id") or "").strip()
        val = _num((item.get("verified") or {}).get("final_score"))
        if sid and val is not None:
            out[sid] = round(val, 2)
    return out


def build_screener_snapshot_from_dossier(
    dossier: dict[str, Any],
    bars: list[dict[str, Any]] | None,
    *,
    meta: dict[str, Any] | None = None,
    indices_list: list[str] | None = None,
) -> dict[str, Any]:
    """Construit une ligne complète `finance_screener_snapshots` à partir d'un dossier calculé."""
    canonical = _norm_sym(str(dossier.get("symbol") or ""))
    hdr = dossier.get("header") or {}
    cap = dossier.get("capital_valuation") or {}
    ann = dossier.get("annual_tables") or {}
    stk = dossier.get("stakeholders") or {}
    intr = dossier.get("intrinsic_valuation") or {}

    tech = compute_technical_snapshot(bars or [])
    price = _num(cap.get("price")) or tech["price"]
    market_cap = _num(cap.get("market_cap")) or _num(hdr.get("market_cap"))

    # FCF Yield = dernier FCF annuel / Market Cap (%)
    latest_fcf = _find_table_latest(ann.get("distribution"), "fcf")
    fcf_yield_pct = (
        round((latest_fcf / market_cap) * 100.0, 2)
        if (latest_fcf is not None and market_cap and market_cap > 0)
        else None
    )

    # CAGR 3A CA & BPA depuis les tableaux annuels si présents
    rev_row = next((r for r in (ann.get("summary") or []) if r.get("key") in ("rev", "revenue")), None)
    eps_row = next((r for r in (ann.get("summary") or []) if r.get("key") in ("eps", "diluted_eps")), None)

    def _cagr_list(vals: list[Any] | None, years: int = 3) -> float | None:
        pts = [n for n in (_num(v) for v in (vals or [])) if n is not None]
        if len(pts) < 2:
            return None
        step = min(years, len(pts) - 1)
        v0, v1 = pts[-1 - step], pts[-1]
        if v0 <= 0 or v1 <= 0 or step <= 0:
            return None
        return round(((v1 / v0) ** (1.0 / step) - 1.0) * 100.0, 2)

    rev_cagr_3y = _cagr_list((rev_row or {}).get("values"), 3)
    eps_cagr_3y = _cagr_list((eps_row or {}).get("values"), 3)

    target_price = _num((stk.get("analysts") or {}).get("target_price")) or _num(cap.get("target_price"))
    analyst_upside = (
        round(((target_price - price) / price) * 100.0, 2)
        if (target_price and price and price > 0)
        else None
    )

    mos_pct = _num((intr.get("summary") or {}).get("margin_of_safety_corrected_pct"))
    if mos_pct is None:
        mos_pct = _num((intr.get("summary") or {}).get("margin_of_safety_pct"))

    roic_val = _find_table_latest(ann.get("profitability"), "roic")
    roe_val = _num(cap.get("roe_ttm"))
    if roe_val is None:
        roe_val = _find_table_latest(ann.get("profitability"), "roe")
    op_margin = _num(cap.get("op_margin_ttm"))
    if op_margin is None:
        op_margin = _find_table_latest(ann.get("profitability"), "op_m")
    net_margin = _num(cap.get("net_margin_ttm"))
    if net_margin is None:
        net_margin = _find_table_latest(ann.get("profitability"), "net_m")

    has_fund = any(
        v is not None
        for v in (
            market_cap,
            _num(cap.get("pe_ttm")),
            _num(cap.get("ev_ebitda")),
            roic_val,
            roe_val,
            _num((ann.get("ih_score") or {}).get("latest_score")),
            _num((ann.get("piotroski") or {}).get("latest_score")),
        )
    )

    return {
        "symbol": canonical,
        "eod_ticker": _norm_sym(str((meta or {}).get("eod_ticker") or canonical)) or canonical,
        "yahoo_symbol": _norm_sym(str((meta or {}).get("yahoo_symbol") or canonical)) or canonical,
        "name": str(hdr.get("name") or (meta or {}).get("long_name") or (meta or {}).get("short_name") or canonical),
        "exchange": str((meta or {}).get("exchange") or ""),
        "country": str((meta or {}).get("country") or ""),
        "currency": str(dossier.get("currency") or (meta or {}).get("currency") or ""),
        "sector": str(hdr.get("sector") or (meta or {}).get("sector") or ""),
        "industry": str(hdr.get("industry") or (meta or {}).get("industry") or ""),
        "cap_category": str(hdr.get("cap_category") or ""),
        "indices_csv": _format_indices_csv(indices_list),
        "market_cap": _round_opt(market_cap, 0),
        "price": _round_opt(price, 4),
        "volume": tech["volume"],
        "avg_volume_20d": tech["avg_volume_20d"],
        "rel_volume_20d": tech["rel_volume_20d"],
        "change_1d_pct": tech["change_1d_pct"],
        "change_1w_pct": tech["change_1w_pct"],
        "change_1m_pct": tech["change_1m_pct"],
        "change_3m_pct": tech["change_3m_pct"],
        "change_ytd_pct": tech["change_ytd_pct"],
        "change_1y_pct": tech["change_1y_pct"],
        "dist_52w_high_pct": tech["dist_52w_high_pct"],
        "dist_52w_low_pct": tech["dist_52w_low_pct"],
        "pe_ttm": _round_opt(_num(cap.get("pe_ttm")), 2),
        "pe_forward": _round_opt(_num(cap.get("pe_forward")), 2),
        "peg_ratio": _round_opt(_num(cap.get("peg")), 2),
        "ev_ebitda": _round_opt(_num(cap.get("ev_ebitda")), 2),
        "pb_ratio": _round_opt(_num(cap.get("pb")), 2),
        "fcf_yield_pct": fcf_yield_pct,
        "dividend_yield_pct": _round_opt(_num(cap.get("dividend_yield_pct")) or _num(hdr.get("dividend_yield_pct")), 2),
        "roic_pct": _round_opt(roic_val, 2),
        "roe_pct": _round_opt(roe_val, 2),
        "op_margin_pct": _round_opt(op_margin, 2),
        "net_margin_pct": _round_opt(net_margin, 2),
        "net_debt_ebitda": _round_opt(_find_table_latest(ann.get("solvency"), "nd_ebitda"), 2),
        "debt_to_equity_pct": _round_opt(_find_table_latest(ann.get("solvency"), "debt_eq"), 2),
        "current_ratio": _round_opt(_find_table_latest(ann.get("solvency"), "curr_r"), 2),
        "rev_cagr_3y_pct": rev_cagr_3y,
        "eps_cagr_3y_pct": eps_cagr_3y,
        "beta": _round_opt(_num(hdr.get("beta")), 2),
        "analyst_upside_pct": analyst_upside,
        "ih_score": _round_opt(_num((ann.get("ih_score") or {}).get("latest_score")), 1),
        "piotroski_f": _round_opt(_num((ann.get("piotroski") or {}).get("latest_score")), 0),
        "altman_z": _round_opt(_num((ann.get("altman") or {}).get("latest_score")), 2),
        "mos_intrinsic_pct": _round_opt(mos_pct, 1),
        "sma20": tech["sma20"],
        "sma50": tech["sma50"],
        "sma200": tech["sma200"],
        "ema20": tech["ema20"],
        "ema50": tech["ema50"],
        "dist_sma50_pct": tech["dist_sma50_pct"],
        "dist_sma200_pct": tech["dist_sma200_pct"],
        "rsi_14": tech["rsi_14"],
        "macd_line": tech["macd_line"],
        "macd_signal": tech["macd_signal"],
        "macd_hist": tech["macd_hist"],
        "macd_cross": tech["macd_cross"],
        "sma_golden_cross": tech["sma_golden_cross"],
        "boll_pct_b": tech["boll_pct_b"],
        "boll_width_pct": tech["boll_width_pct"],
        "adx_14": tech["adx_14"],
        "stoch_k": tech["stoch_k"],
        "atr_pct": tech["atr_pct"],
        "roc_12": tech["roc_12"],
        "supertrend_dir": tech["supertrend_dir"],
        "has_fundamentals": 1 if has_fund else 0,
        "bars_count": tech["bars_count"],
        "bars_date": tech["bars_date"],
        "fundamentals_updated_at": _utc_iso() if has_fund else None,
        "computed_at": _utc_iso(),
        "scores_json": _extract_scores_compact(dossier.get("uncle_stock_scores")),
        "sparkline_json": tech["sparkline"],
    }


def sync_screener_snapshot_from_dossier(
    db_path: Path,
    dossier: dict[str, Any],
    bars: list[dict[str, Any]] | None,
) -> None:
    """Met à jour immédiatement la ligne Screener suite au calcul d'un dossier boursier."""
    canonical = _norm_sym(str(dossier.get("symbol") or ""))
    if not canonical:
        return
    meta = get_instrument_meta(db_path, canonical)
    idx_map = get_symbol_indices_map(db_path)
    indices = idx_map.get(canonical) or idx_map.get(_norm_sym(str((meta or {}).get("eod_ticker") or ""))) or []
    row = build_screener_snapshot_from_dossier(dossier, bars, meta=meta, indices_list=indices)
    upsert_screener_snapshots(db_path, [row], preserve_fundamentals_if_missing=False)


def build_screener_snapshot_from_warehouse(
    db_path: Path,
    symbol: str,
    *,
    indices_map: dict[str, list[str]] | None = None,
) -> dict[str, Any] | None:
    """Reconstruit une ligne Screener 100 % localement depuis `finance_warehouse.db` (0 appel réseau)."""
    from .finance_dossier import _cap_category, _compute_annual_dossier_tables, _dedupe_annual_series_by_year
    from .finance_eodhd_extras import resolve_country_iso3
    from .finance_intrinsic import compute_intrinsic_valuations

    canonical = resolve_canonical_symbol(db_path, symbol)
    if not canonical:
        return None
    meta = get_instrument_meta(db_path, canonical) or {}
    bars = get_stored_eod_bars(db_path, canonical, limit=600)
    ann_series, ann_curr, _, ann_upd = load_fundamental_series(db_path, canonical, "annual")
    eod_snap = get_snapshot(db_path, canonical, "fundamentals", provider="eodhd", include_raw=True)
    eod_fund = eod_snap.get("raw") if (eod_snap and isinstance(eod_snap.get("raw"), dict)) else None
    yahoo_snap = get_snapshot(db_path, canonical, "quote_summary_ext", provider="yahoo_finance", include_raw=True)
    yahoo_sum = yahoo_snap.get("raw") if (yahoo_snap and isinstance(yahoo_snap.get("raw"), dict)) else None

    if not bars and not ann_series and not eod_fund and not yahoo_sum:
        return None

    tech = compute_technical_snapshot(bars)
    gen = (eod_fund or {}).get("General") or {}
    hl = (eod_fund or {}).get("Highlights") or {}
    val = (eod_fund or {}).get("Valuation") or {}
    eod_tech = (eod_fund or {}).get("Technicals") or {}
    divs_meta = (eod_fund or {}).get("SplitsDividends") or {}
    shares_st = (eod_fund or {}).get("SharesStats") or {}

    y_price = (yahoo_sum or {}).get("price") or {}
    y_det = (yahoo_sum or {}).get("summaryDetail") or {}
    y_fin = (yahoo_sum or {}).get("financialData") or {}
    y_stat = (yahoo_sum or {}).get("defaultKeyStatistics") or {}
    y_prof = (yahoo_sum or {}).get("assetProfile") or {}

    price = tech["price"] or _num(y_price.get("regularMarketPrice"))
    market_cap = _num(hl.get("MarketCapitalization")) or _num(y_price.get("marketCap"))
    div_yield_raw = (
        _num(hl.get("DividendYield"))
        or _num(divs_meta.get("ForwardAnnualDividendYield"))
        or _num(y_det.get("dividendYield"))
    )
    div_yield_pct = (
        round(div_yield_raw * 100.0, 2)
        if (div_yield_raw is not None and abs(div_yield_raw) < 1.0)
        else _round_opt(div_yield_raw, 2)
    )
    beta_val = _num(eod_tech.get("Beta")) or _num(y_stat.get("beta")) or _num(y_det.get("beta"))
    currency = str(
        gen.get("CurrencyCode")
        or y_price.get("currency")
        or meta.get("currency")
        or ann_curr
        or ""
    ).strip().upper()

    pe_ttm = _num(val.get("TrailingPE") or hl.get("PERatio") or y_stat.get("trailingPE"))
    pe_forward = _num(val.get("ForwardPE") or y_stat.get("forwardPE"))
    peg_ratio = _num(hl.get("PEGRatio") or y_stat.get("pegRatio"))
    ev_ebitda = _num(val.get("EnterpriseValueEbitda") or y_stat.get("enterpriseToEbitda"))
    pb_ratio = _num(val.get("PriceBookMRQ") or y_stat.get("priceToBook"))
    op_margin = _pct_norm(hl.get("OperatingMarginTTM") or y_fin.get("operatingMargins"))
    net_margin = _pct_norm(hl.get("ProfitMargin") or y_fin.get("profitMargins"))
    roe_pct = _pct_norm(hl.get("ReturnOnEquityTTM") or y_fin.get("returnOnEquity"))
    target_price = _num(hl.get("WallStreetTargetPrice") or y_fin.get("targetMeanPrice"))
    analyst_upside = (
        round(((target_price - price) / price) * 100.0, 2)
        if (target_price and price and price > 0)
        else None
    )

    roic_pct: float | None = None
    net_debt_ebitda: float | None = None
    debt_eq_pct: float | None = None
    curr_ratio: float | None = None
    fcf_yield_pct: float | None = None
    rev_cagr_3y: float | None = None
    eps_cagr_3y: float | None = None
    ih_score: float | None = None
    piotroski_f: float | None = None
    altman_z: float | None = None
    mos_pct: float | None = None

    if ann_series:
        annual_tables = _compute_annual_dossier_tables(ann_series, bars, beta_val)
        roic_pct = _find_table_latest(annual_tables.get("profitability"), "roic")
        if roe_pct is None:
            roe_pct = _find_table_latest(annual_tables.get("profitability"), "roe")
        if op_margin is None:
            op_margin = _find_table_latest(annual_tables.get("profitability"), "op_m")
        if net_margin is None:
            net_margin = _find_table_latest(annual_tables.get("profitability"), "net_m")
        net_debt_ebitda = _find_table_latest(annual_tables.get("solvency"), "nd_ebitda")
        debt_eq_pct = _find_table_latest(annual_tables.get("solvency"), "debt_eq")
        curr_ratio = _find_table_latest(annual_tables.get("solvency"), "curr_r")
        ih_score = _num((annual_tables.get("ih_score") or {}).get("latest_score"))
        piotroski_f = _num((annual_tables.get("piotroski") or {}).get("latest_score"))
        altman_z = _num((annual_tables.get("altman") or {}).get("latest_score"))

        latest_fcf = _find_table_latest(annual_tables.get("distribution"), "fcf")
        if latest_fcf is not None and market_cap and market_cap > 0:
            fcf_yield_pct = round((latest_fcf / market_cap) * 100.0, 2)

        deduped_ann, deduped_dates = _dedupe_annual_series_by_year(ann_series)
        rev_cagr_3y = _cagr_from_series(deduped_ann.get("TotalRevenue"), 3)
        eps_cagr_3y = _cagr_from_series(deduped_ann.get("DilutedEPS"), 3)

        shares_out = _num(shares_st.get("SharesOutstanding")) or _num(y_stat.get("sharesOutstanding"))
        eff_shares = shares_out or ((market_cap / price) if (market_cap and price and price > 0) else None)
        if price and price > 0 and deduped_dates:
            try:
                intr = compute_intrinsic_valuations(
                    ann_series=deduped_ann,
                    dates=deduped_dates,
                    current_price=price,
                    currency=currency or "USD",
                    country_iso3=resolve_country_iso3(eod_fund, canonical),
                    beta=beta_val,
                    shares_override=eff_shares,
                    dividend_yield_pct=div_yield_pct,
                    piotroski_score=int(piotroski_f) if piotroski_f is not None else None,
                    bars=bars,
                )
                mos_pct = _num((intr.get("summary") or {}).get("margin_of_safety_corrected_pct"))
                if mos_pct is None:
                    mos_pct = _num((intr.get("summary") or {}).get("margin_of_safety_pct"))
            except Exception as exc:
                _logger.debug("Calcul intrinsèque screener ignoré pour %s: %s", canonical, exc)

    idx_lookup = indices_map if indices_map is not None else get_symbol_indices_map(db_path)
    indices = (
        idx_lookup.get(canonical)
        or idx_lookup.get(_norm_sym(str(meta.get("eod_ticker") or "")))
        or idx_lookup.get(_norm_sym(str(meta.get("yahoo_symbol") or "")))
        or []
    )

    has_fund = any(
        v is not None
        for v in (market_cap, pe_ttm, ev_ebitda, roic_pct, roe_pct, ih_score, piotroski_f)
    )
    fund_updated = (
        (eod_snap.get("updated_at") if eod_snap else None)
        or (yahoo_snap.get("updated_at") if yahoo_snap else None)
        or ann_upd
    )

    return {
        "symbol": canonical,
        "eod_ticker": _norm_sym(str(meta.get("eod_ticker") or canonical)) or canonical,
        "yahoo_symbol": _norm_sym(str(meta.get("yahoo_symbol") or canonical)) or canonical,
        "name": str(
            gen.get("Name")
            or y_price.get("longName")
            or meta.get("long_name")
            or meta.get("short_name")
            or canonical
        ),
        "exchange": str(gen.get("Exchange") or meta.get("exchange") or ""),
        "country": str(gen.get("CountryName") or y_prof.get("country") or meta.get("country") or ""),
        "currency": currency,
        "sector": str(gen.get("Sector") or y_prof.get("sector") or meta.get("sector") or ""),
        "industry": str(gen.get("Industry") or y_prof.get("industry") or meta.get("industry") or ""),
        "cap_category": _cap_category(market_cap) if market_cap is not None else "",
        "indices_csv": _format_indices_csv(indices),
        "market_cap": _round_opt(market_cap, 0),
        "price": _round_opt(price, 4),
        "volume": tech["volume"],
        "avg_volume_20d": tech["avg_volume_20d"],
        "rel_volume_20d": tech["rel_volume_20d"],
        "change_1d_pct": tech["change_1d_pct"],
        "change_1w_pct": tech["change_1w_pct"],
        "change_1m_pct": tech["change_1m_pct"],
        "change_3m_pct": tech["change_3m_pct"],
        "change_ytd_pct": tech["change_ytd_pct"],
        "change_1y_pct": tech["change_1y_pct"],
        "dist_52w_high_pct": tech["dist_52w_high_pct"],
        "dist_52w_low_pct": tech["dist_52w_low_pct"],
        "pe_ttm": _round_opt(pe_ttm, 2),
        "pe_forward": _round_opt(pe_forward, 2),
        "peg_ratio": _round_opt(peg_ratio, 2),
        "ev_ebitda": _round_opt(ev_ebitda, 2),
        "pb_ratio": _round_opt(pb_ratio, 2),
        "fcf_yield_pct": fcf_yield_pct,
        "dividend_yield_pct": div_yield_pct,
        "roic_pct": _round_opt(roic_pct, 2),
        "roe_pct": _round_opt(roe_pct, 2),
        "op_margin_pct": _round_opt(op_margin, 2),
        "net_margin_pct": _round_opt(net_margin, 2),
        "net_debt_ebitda": _round_opt(net_debt_ebitda, 2),
        "debt_to_equity_pct": _round_opt(debt_eq_pct, 2),
        "current_ratio": _round_opt(curr_ratio, 2),
        "rev_cagr_3y_pct": rev_cagr_3y,
        "eps_cagr_3y_pct": eps_cagr_3y,
        "beta": _round_opt(beta_val, 2),
        "analyst_upside_pct": analyst_upside,
        "ih_score": _round_opt(ih_score, 1),
        "piotroski_f": _round_opt(piotroski_f, 0),
        "altman_z": _round_opt(altman_z, 2),
        "mos_intrinsic_pct": _round_opt(mos_pct, 1),
        "sma20": tech["sma20"],
        "sma50": tech["sma50"],
        "sma200": tech["sma200"],
        "ema20": tech["ema20"],
        "ema50": tech["ema50"],
        "dist_sma50_pct": tech["dist_sma50_pct"],
        "dist_sma200_pct": tech["dist_sma200_pct"],
        "rsi_14": tech["rsi_14"],
        "macd_line": tech["macd_line"],
        "macd_signal": tech["macd_signal"],
        "macd_hist": tech["macd_hist"],
        "macd_cross": tech["macd_cross"],
        "sma_golden_cross": tech["sma_golden_cross"],
        "boll_pct_b": tech["boll_pct_b"],
        "boll_width_pct": tech["boll_width_pct"],
        "adx_14": tech["adx_14"],
        "stoch_k": tech["stoch_k"],
        "atr_pct": tech["atr_pct"],
        "roc_12": tech["roc_12"],
        "supertrend_dir": tech["supertrend_dir"],
        "has_fundamentals": 1 if has_fund else 0,
        "bars_count": tech["bars_count"],
        "bars_date": tech["bars_date"],
        "fundamentals_updated_at": fund_updated if has_fund else None,
        "computed_at": _utc_iso(),
        "scores_json": {},
        "sparkline_json": tech["sparkline"],
    }


def rebuild_screener_snapshots_from_warehouse(
    db_path: Path,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Reconstruit la table matérialisée du Screener depuis les données locales (0 appel réseau)."""
    target_syms = (
        [_norm_sym(s) for s in symbols if _norm_sym(s)]
        if symbols is not None
        else list_warehouse_screener_symbols(db_path)
    )
    if not target_syms:
        return {"indexed_count": 0, "coverage": get_screener_coverage(db_path)}

    idx_map = get_symbol_indices_map(db_path)
    rows: list[dict[str, Any]] = []
    for sym in target_syms:
        try:
            snap = build_screener_snapshot_from_warehouse(db_path, sym, indices_map=idx_map)
            if snap:
                rows.append(snap)
        except Exception as exc:
            _logger.debug("Snapshot screener ignoré pour %s: %s", sym, exc)

    indexed = upsert_screener_snapshots(db_path, rows, preserve_fundamentals_if_missing=True, batch_size=40)
    return {"indexed_count": indexed, "coverage": get_screener_coverage(db_path)}


# ---------------------------------------------------------------------------
# Moteur de requête Screener (Passe 1 SQL whitelistée + Passe 2 extensible)
# ---------------------------------------------------------------------------

def _compile_rule_sql(rule: dict[str, Any]) -> tuple[str | None, list[Any], bool]:
    """Compile une règle déclarative en clause SQL paramétrée sûre.

    Retourne `(sql_clause, params, is_post_filter)`.
    Lève `ValueError` sur tout champ ou opérateur hors whitelist.
    """
    if not isinstance(rule, dict):
        raise ValueError("Règle de filtrage invalide.")
    kind = str(rule.get("kind") or "metric").strip().lower()

    if kind in ("formula", "custom_indicator"):
        if kind not in _POST_FILTER_EVALUATORS:
            raise ValueError(
                f"Le type de règle « {kind} » est prévu pour les formules personnalisées (non activé en V1)."
            )
        return None, [], True

    if kind == "compare":
        left = str(rule.get("left") or "").strip()
        right = str(rule.get("right") or "").strip()
        op = str(rule.get("op") or "").strip().lower()
        if left not in _COMPARABLE_COLUMNS or right not in _COMPARABLE_COLUMNS:
            raise ValueError(f"Comparaison inter-indicateurs non autorisée : {left!r} / {right!r}.")
        if op not in ("gt", "gte", "lt", "lte"):
            raise ValueError(f"Opérateur de comparaison invalide : {op!r}.")
        mult = _num(rule.get("multiplier"))
        sql_op = _ALLOWED_METRIC_OPS[op]
        if mult is not None and mult != 1.0:
            return f"({left} IS NOT NULL AND {right} IS NOT NULL AND {left} {sql_op} ({right} * ?))", [mult], False
        return f"({left} IS NOT NULL AND {right} IS NOT NULL AND {left} {sql_op} {right})", [], False

    field = str(rule.get("field") or "").strip()
    meta = _FIELD_BY_KEY.get(field)
    if not meta:
        raise ValueError(f"Champ de screening inconnu : {field!r}.")
    op = str(rule.get("op") or "").strip().lower()
    scale = float(meta.get("scale") or 1.0)

    if op == "is_not_null":
        return f"{field} IS NOT NULL", [], False

    if kind == "signal" or meta.get("type") == "signal":
        if op == "eq":
            val = _num(rule.get("value"))
            if val is None:
                raise ValueError(f"Valeur requise pour le signal {field}.")
            return f"{field} = ?", [int(val)], False
        if op == "in":
            raw_vals = rule.get("value")
            if not isinstance(raw_vals, list) or not raw_vals:
                raise ValueError(f"Liste de valeurs requise pour {field}.")
            ints = [int(v) for v in (_num(x) for x in raw_vals) if v is not None]
            if not ints:
                raise ValueError(f"Valeurs invalides pour {field}.")
            marks = ", ".join("?" for _ in ints)
            return f"{field} IN ({marks})", ints, False
        raise ValueError(f"Opérateur de signal invalide pour {field} : {op!r}.")

    if op == "between":
        lo = _num(rule.get("value"))
        hi = _num(rule.get("value_max"))
        if lo is None or hi is None:
            raise ValueError(f"Bornes min et max requises pour « between » sur {field}.")
        low_v, high_v = (lo * scale, hi * scale) if lo <= hi else (hi * scale, lo * scale)
        return f"({field} IS NOT NULL AND {field} BETWEEN ? AND ?)", [low_v, high_v], False

    if op in _ALLOWED_METRIC_OPS:
        val = _num(rule.get("value"))
        if val is None:
            raise ValueError(f"Valeur numérique requise pour {field}.")
        return f"({field} IS NOT NULL AND {field} {_ALLOWED_METRIC_OPS[op]} ?)", [val * scale], False

    raise ValueError(f"Opérateur invalide pour {field} : {op!r}.")


def _row_to_screener_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    try:
        d["sparkline"] = json.loads(d.pop("sparkline_json", "[]") or "[]")
    except Exception:
        d["sparkline"] = []
    try:
        d["scores"] = json.loads(d.pop("scores_json", "{}") or "{}")
    except Exception:
        d["scores"] = {}
    d["has_fundamentals"] = bool(d.get("has_fundamentals"))
    raw_idx = str(d.pop("indices_csv", "") or "")
    d["indices"] = [p for p in raw_idx.split(",") if p]
    if d.get("market_cap") is not None:
        d["market_cap_m"] = round(float(d["market_cap"]) / 1e6, 1)
    else:
        d["market_cap_m"] = None
    return d


def query_screener(
    settings: Settings,
    *,
    universe_type: str = "all",
    universe_value: str | None = None,
    watchlist_symbols: list[str] | None = None,
    search: str = "",
    sector: str = "",
    exchange: str = "",
    currency: str = "",
    only_with_fundamentals: bool = False,
    rules: list[dict[str, Any]] | None = None,
    sort_by: str = "market_cap",
    sort_dir: str = "desc",
    limit: int = 100,
    offset: int = 0,
    auto_backfill: bool = True,
) -> dict[str, Any]:
    """Exécute une requête multi-critères (Passe 1 SQLite + Passe 2 extensible) sur `finance_screener_snapshots`."""
    db_path = warehouse_db_path(settings)
    cov = get_screener_coverage(db_path)
    if auto_backfill and cov["total_snapshots"] == 0 and cov["warehouse_symbols_count"] > 0:
        rebuild_screener_snapshots_from_warehouse(db_path)
        cov = get_screener_coverage(db_path)

    clauses: list[str] = []
    params: list[Any] = []

    u_type = (universe_type or "all").strip().lower()
    u_val = _norm_sym(universe_value or "")
    if u_type == "index" and u_val:
        clauses.append("indices_csv LIKE ?")
        params.append(f"%,{u_val},%")
    elif u_type == "exchange" and u_val:
        clauses.append("UPPER(exchange) = ?")
        params.append(u_val)
    elif u_type == "watchlist":
        wl_syms = sorted({_norm_sym(s) for s in (watchlist_symbols or []) if _norm_sym(s)})
        if not wl_syms:
            return {
                "total": 0,
                "universe_total": 0,
                "offset": 0,
                "limit": max(1, min(300, int(limit or 100))),
                "items": [],
                "coverage": cov,
            }
        marks = ", ".join("?" for _ in wl_syms)
        clauses.append(
            f"(UPPER(symbol) IN ({marks}) OR UPPER(COALESCE(eod_ticker, '')) IN ({marks}) "
            f"OR UPPER(COALESCE(yahoo_symbol, '')) IN ({marks}))"
        )
        params.extend(wl_syms * 3)

    universe_where = " AND ".join(clauses) if clauses else "1=1"
    universe_params = list(params)

    clean_search = (search or "").strip()
    if clean_search:
        like = f"%{clean_search.upper()}%"
        clauses.append("(UPPER(symbol) LIKE ? OR UPPER(COALESCE(eod_ticker, '')) LIKE ? OR UPPER(name) LIKE ?)")
        params.extend([like, like, like])
    if sector.strip():
        clauses.append("LOWER(sector) = ?")
        params.append(sector.strip().lower())
    if exchange.strip():
        clauses.append("UPPER(exchange) = ?")
        params.append(exchange.strip().upper())
    if currency.strip():
        clauses.append("UPPER(currency) = ?")
        params.append(currency.strip().upper())
    if only_with_fundamentals:
        clauses.append("has_fundamentals = 1")

    post_rules: list[dict[str, Any]] = []
    for r in rules or []:
        sql_part, sql_params, is_post = _compile_rule_sql(r)
        if is_post:
            post_rules.append(r)
        elif sql_part:
            clauses.append(sql_part)
            params.extend(sql_params)

    where_sql = " AND ".join(clauses) if clauses else "1=1"

    safe_sort = sort_by if sort_by in _SORTABLE_COLUMNS else "market_cap"
    safe_dir = "ASC" if str(sort_dir or "").strip().lower() == "asc" else "DESC"
    # Placer toujours les NULL en fin de tri pour un classement financier lisible
    order_sql = f"ORDER BY ({safe_sort} IS NULL) ASC, {safe_sort} {safe_dir}, symbol ASC"

    safe_limit = max(1, min(300, int(limit or 100)))
    safe_offset = max(0, int(offset or 0))

    if not db_path.exists():
        return {
            "total": 0,
            "universe_total": 0,
            "offset": safe_offset,
            "limit": safe_limit,
            "items": [],
            "coverage": cov,
        }

    with _connect(db_path) as conn:
        u_total_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM finance_screener_snapshots WHERE {universe_where}",
            universe_params,
        ).fetchone()
        universe_total = int((u_total_row["cnt"] if u_total_row else 0) or 0)

        if not post_rules:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM finance_screener_snapshots WHERE {where_sql}",
                params,
            ).fetchone()
            total = int((total_row["cnt"] if total_row else 0) or 0)
            raw_rows = conn.execute(
                f"SELECT * FROM finance_screener_snapshots WHERE {where_sql} {order_sql} LIMIT ? OFFSET ?",
                [*params, safe_limit, safe_offset],
            ).fetchall()
            items = [_row_to_screener_dict(r) for r in raw_rows]
        else:
            # Passe 2 : évaluation Python extensible sur les candidats survivants de la Passe 1
            raw_rows = conn.execute(
                f"SELECT * FROM finance_screener_snapshots WHERE {where_sql} {order_sql}",
                params,
            ).fetchall()
            candidates = [_row_to_screener_dict(r) for r in raw_rows]
            for pr in post_rules:
                kind = str(pr.get("kind") or "").strip().lower()
                evaluator = _POST_FILTER_EVALUATORS.get(kind)
                if evaluator:
                    candidates = evaluator(db_path, candidates, pr)
            total = len(candidates)
            items = candidates[safe_offset : safe_offset + safe_limit]

    return {
        "total": total,
        "universe_total": universe_total,
        "offset": safe_offset,
        "limit": safe_limit,
        "items": items,
        "coverage": cov,
    }


def get_screener_metadata(settings: Settings) -> dict[str, Any]:
    """Retourne le schéma des filtres, les presets et la couverture locale du Screener."""
    db_path = warehouse_db_path(settings)
    cov = get_screener_coverage(db_path)
    if cov["total_snapshots"] == 0 and cov["warehouse_symbols_count"] > 0:
        rebuild_screener_snapshots_from_warehouse(db_path)
        cov = get_screener_coverage(db_path)
    return {
        "fields": list(SCREENER_FIELDS),
        "presets": list(SCREENER_PRESETS),
        "coverage": cov,
        "formula_engine": {
            "ready": True,
            "registered_kinds": list_registered_post_filter_kinds(),
        },
    }


async def hydrate_screener_universe(
    settings: Settings,
    *,
    universe_type: str = "index",
    universe_value: str | None = None,
    watchlist_symbols: list[str] | None = None,
    include_fundamentals: bool = True,
    max_fundamentals: int = 40,
    refresh_eod: bool = False,
) -> dict[str, Any]:
    """Enrichit les cours EOD (et optionnellement les fondamentaux manquants) d'un univers pour le Screener."""
    from .finance_dossier import get_financial_dossier
    from .finance_indices import get_index_performances

    db_path = warehouse_db_path(settings)
    u_type = (universe_type or "index").strip().lower()
    u_val = _norm_sym(universe_value or "")
    target_symbols: list[str] = []
    eod_loaded = 0

    if u_type == "index" and u_val:
        perf = await get_index_performances(settings, u_val, refresh=refresh_eod, cache_only=False)
        if perf is None:
            raise ValueError(f"Indice inconnu : {u_val}")
        for item in perf.get("items") or []:
            sym = _norm_sym(str(item.get("eod_ticker") or item.get("symbol") or ""))
            if sym:
                target_symbols.append(sym)
        eod_loaded = int((perf.get("summary") or {}).get("loaded_count") or 0)
    elif u_type == "watchlist":
        target_symbols = sorted({_norm_sym(s) for s in (watchlist_symbols or []) if _norm_sym(s)})
    else:
        target_symbols = list_warehouse_screener_symbols(db_path)

    # Indexer d'abord tout ce qui est déjà en cache (cours + techniques)
    rebuild_res = rebuild_screener_snapshots_from_warehouse(db_path, target_symbols or None)

    fundamentals_enriched = 0
    fundamentals_skipped_cached = 0
    fundamentals_errors = 0

    if include_fundamentals and target_symbols and not settings.demo_mode:
        ttl_sec = max(3600, int(settings.finance_fundamentals_ttl_hours) * 3600)
        to_fetch: list[str] = []
        for sym in target_symbols:
            canonical = resolve_canonical_symbol(db_path, sym)
            snap = get_snapshot(db_path, canonical, "fundamentals", max_age_seconds=ttl_sec)
            if snap:
                fundamentals_skipped_cached += 1
            else:
                to_fetch.append(canonical)

        cap = max(1, min(120, int(max_fundamentals or 40)))
        sem = asyncio.Semaphore(4)

        async def _enrich_one(sym: str) -> bool:
            async with sem:
                try:
                    await get_financial_dossier(settings, sym, refresh=False)
                    return True
                except Exception as exc:
                    _logger.debug("Hydratation fondamentale ignorée (%s): %s", sym, exc)
                    return False

        results = await asyncio.gather(*(_enrich_one(s) for s in to_fetch[:cap]))
        fundamentals_enriched = sum(1 for ok in results if ok)
        fundamentals_errors = sum(1 for ok in results if not ok)

    return {
        "universe_type": u_type,
        "universe_value": u_val or None,
        "symbols_count": len(target_symbols),
        "eod_loaded": eod_loaded,
        "indexed_count": rebuild_res["indexed_count"],
        "fundamentals_enriched": fundamentals_enriched,
        "fundamentals_cached": fundamentals_skipped_cached,
        "fundamentals_errors": fundamentals_errors,
        "coverage": get_screener_coverage(db_path),
    }
