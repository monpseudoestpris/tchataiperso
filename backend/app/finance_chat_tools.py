"""Outils Finance en lecture seule exposés au tchat IA (Screener, Dossiers, Watchlists, Indices, Analyses).

Garanties :
- Lecture 100 % locale sur `finance_warehouse.db` et les tables utilisateur SQLAlchemy pour
  le Screener, les Watchlists, les Indices, les Analyses archivées, les News en cache et le Catalogue.
- Aucune mutation (lecture seule stricte).
- Isolation stricte `user_id` sur toutes les données personnelles (watchlists, MOAT, rapports, news IA, indicateurs).
- Chargement réseau live autorisé uniquement dans `finance_get_stock_dossier` lorsqu'un titre précis
  manque en cache, plafonné à `max_live_dossier_fetches` (défaut : 2 par tour).
"""

from __future__ import annotations

import json
import logging
import math
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .finance_dossier import (
    _build_dividends_matrix,
    _cap_category,
    _compact_annual_table,
    _compute_annual_dossier_tables,
    _compute_price_dynamics,
    _dedupe_annual_series_by_year,
    _div,
    _extract_stakeholders,
    _num,
    _simple_ma,
    compute_price_performance_and_risk,
    get_financial_dossier,
)
from .finance_eodhd_extras import resolve_country_iso3
from .finance_fundamentals_queue import queue_stats
from .finance_geography import canonicalize_country
from .finance_indices import (
    INDEX_DEFINITIONS,
    get_index_performances,
    search_finance_catalog,
)
from .finance_intrinsic import compute_intrinsic_valuations
from .finance_scores import compute_uncle_stock_scores
from .finance_screener import (
    SCREENER_FIELDS,
    SCREENER_PRESETS,
    UNCLE_STOCK_SCORE_IDS,
    get_screener_metadata,
    query_screener,
)
from .finance_statements import build_period_from_series
from .finance_technicals import compute_multi_timeframe_technicals
from .finance_uncle_stock_catalog import compute_uncle_stock_catalog
from .finance_warehouse import (
    get_index_constituents,
    get_instrument_meta,
    get_snapshot,
    get_stored_eod_bars,
    get_warehouse_overview,
    list_ai_analyses,
    load_fundamental_series,
    resolve_canonical_symbol,
    search_exchange_symbols,
    warehouse_db_path,
)
from .finance_watchlist import compute_period_returns
from .models import (
    FinanceCustomIndicator,
    FinanceQuarterlyReport,
    FinanceStockMoat,
    FinanceStockNews,
    FinanceWatchlist,
    FinanceWatchlistItem,
)

_logger = logging.getLogger("uvicorn.error")

_FIELD_ALIASES: dict[str, str] = {
    "piotroski": "piotroski_f",
    "piotroski_score": "piotroski_f",
    "puotrosky": "piotroski_f",
    "ih": "ih_score",
    "altman": "altman_z",
    "rsi": "rsi_14",
    "per": "pe_ttm",
    "pe": "pe_ttm",
    "pb": "pb_ratio",
    "peg": "peg_ratio",
    "roic": "roic_pct",
    "roe": "roe_pct",
    "mos": "mos_intrinsic_pct",
    "margin_of_safety": "mos_intrinsic_pct",
    "dividend_yield": "dividend_yield_pct",
    "fcf_yield": "fcf_yield_pct",
    "op_margin": "op_margin_pct",
    "net_margin": "net_margin_pct",
    "isopressure_20": "isopressure_p20",
    "isopressure_50": "isopressure_p50",
    "isopressure_5": "isopressure_p5",
    "isopressure_100": "isopressure_p100",
    "isopressure_200": "isopressure_p200",
    "supertrend": "supertrend_dir",
}

_TIMEFRAME_ALIASES: dict[str, str] = {
    "jour": "day",
    "daily": "day",
    "1d": "day",
    "semaine": "week",
    "weekly": "week",
    "1w": "week",
    "mois": "month",
    "monthly": "month",
    "1m": "month",
    "trimestre": "quarter",
    "quarterly": "quarter",
    "3m": "quarter",
    "3_months": "quarter",
    "3months": "quarter",
}

_OP_ALIASES: dict[str, str] = {
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
    "=": "eq",
    "==": "eq",
    "!=": "neq",
    "<>": "neq",
}

_VALID_DOSSIER_SECTIONS: frozenset[str] = frozenset(
    {
        "summary",
        "technicals",
        "scores",
        "intrinsic",
        "statements",
        "stakeholders",
        "uncle_stock_ratios",
    }
)

_SCREENER_COMPACT_KEYS: tuple[str, ...] = (
    "symbol",
    "eod_ticker",
    "name",
    "country",
    "market_zone",
    "exchange",
    "currency",
    "sector",
    "cap_category",
    "indices",
    "price",
    "market_cap_m",
    "change_1d_pct",
    "change_1w_pct",
    "change_1m_pct",
    "change_ytd_pct",
    "change_1y_pct",
    "pe_ttm",
    "pe_forward",
    "ev_ebitda",
    "pb_ratio",
    "roic_pct",
    "roe_pct",
    "op_margin_pct",
    "net_debt_ebitda",
    "dividend_yield_pct",
    "fcf_yield_pct",
    "piotroski_f",
    "ih_score",
    "altman_z",
    "mos_intrinsic_pct",
    "rsi_14",
    "isopressure_p20",
    "isopressure_p50",
    "isopressure_20_50_dir",
    "supertrend_dir",
    "has_fundamentals",
    "bars_date",
)

_FIELD_KEYS_SUMMARY = ", ".join(f["key"] for f in SCREENER_FIELDS)
_SCORE_IDS_SUMMARY = ", ".join(sorted(UNCLE_STOCK_SCORE_IDS))


@dataclass
class FinanceToolContext:
    """Contexte d'exécution des outils Finance pour un tour de tchat."""

    settings: Settings
    sessions: sessionmaker | None
    user_id: str | None
    live_dossier_fetches: int = 0
    max_live_dossier_fetches: int = 2
    consulted_symbols: list[str] = field(default_factory=list)
    consulted_tools: list[str] = field(default_factory=list)

    def track_symbol(self, symbol: str | None) -> None:
        clean = str(symbol or "").strip().upper()
        if clean and clean not in self.consulted_symbols:
            self.consulted_symbols.append(clean)


# ---------------------------------------------------------------------------
# Schémas JSON plats des 8 outils (compatibles OpenRouter + OpenAI + Gemini)
# ---------------------------------------------------------------------------

FINANCE_CHAT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "finance_screener_query",
            "description": (
                "Interroge le Screener boursier local SQLite pour filtrer et trier les actions par pays, "
                "zone, indice, bourse, secteur, watchlist, métriques fondamentales (piotroski_f, ih_score, "
                "altman_z, mos_intrinsic_pct, pe_ttm, ev_ebitda, roic_pct, roe_pct, op_margin_pct, "
                "net_debt_ebitda, dividend_yield_pct, rev_cagr_3y_pct...), indicateurs techniques multi-unités "
                "(rsi_14, sma20/50/200, ema20/50, macd_hist, macd_cross, sma_golden_cross, boll_pct_b, adx_14, "
                "stoch_k, atr_pct, supertrend_dir, isopressure_p5/p20/p50/p100/p200, isopressure_20_50_diff/dir/cross) "
                "et les 31 scores Uncle Stock (kind='score', ex. uncle_stock_score, quality_score, value_score, greenblatt_score)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Pays (ex. 'France', 'États-Unis', 'Allemagne', 'Royaume-Uni', 'Suisse').",
                    },
                    "market_zone": {
                        "type": "string",
                        "enum": ["eurozone", "europe", "north_america", "asia_pacific", "latin_america", "mea"],
                        "description": "Zone boursière.",
                    },
                    "index_code": {
                        "type": "string",
                        "description": "Code d'indice boursier (ex. 'CAC40', 'SP500', 'NASDAQ100', 'DAX', 'STOXX600').",
                    },
                    "exchange": {
                        "type": "string",
                        "description": "Place boursière EODHD (ex. 'PA', 'US', 'XETRA', 'LSE').",
                    },
                    "sector": {"type": "string", "description": "Secteur GICS (ex. 'Technology', 'Industrials')."},
                    "currency": {"type": "string", "description": "Devise (ex. 'EUR', 'USD')."},
                    "cap_category": {
                        "type": "string",
                        "description": "Catégorie de capitalisation (ex. 'Large-Cap', 'Mid-Cap', 'Small-Cap', 'Méga-Cap').",
                    },
                    "watchlist": {
                        "type": "string",
                        "description": "Nom ou identifiant d'une liste de suivi de l'utilisateur.",
                    },
                    "search": {"type": "string", "description": "Filtre texte sur le nom ou le ticker."},
                    "only_with_fundamentals": {
                        "type": "boolean",
                        "description": "Si vrai, exclut les actions sans fondamentaux calculés.",
                    },
                    "timeframe": {
                        "type": "string",
                        "enum": ["day", "week", "month", "quarter"],
                        "description": "Unité temporelle principale pour les indicateurs techniques (défaut: 'day').",
                    },
                    "preset_id": {
                        "type": "string",
                        "enum": ["isopressure_20_50", "quality_moat", "value_mos", "garp_growth", "oversold_uptrend", "breakout_supertrend"],
                        "description": "Applique un preset du Screener (cumulable avec `rules`).",
                    },
                    "rules": {
                        "type": "array",
                        "description": "Liste de règles de filtrage cumulatives (ET logique).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["metric", "compare", "signal", "score"],
                                    "description": "metric (nombre), compare (champ vs champ), signal (1/-1/2/-2), score (score Uncle Stock).",
                                },
                                "field": {
                                    "type": "string",
                                    "description": "Nom du champ (metric/signal/score), ex. 'piotroski_f', 'rsi_14', 'uncle_stock_score'.",
                                },
                                "left": {
                                    "type": "string",
                                    "description": "Champ gauche pour kind='compare' (ex. 'isopressure_p20', 'price', 'sma50').",
                                },
                                "right": {
                                    "type": "string",
                                    "description": "Champ droit pour kind='compare' (ex. 'isopressure_p50', 'sma200').",
                                },
                                "op": {
                                    "type": "string",
                                    "enum": ["gt", "gte", "lt", "lte", "eq", "neq", "between", "in", "is_not_null"],
                                    "description": "Opérateur de comparaison.",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "Valeur seuil numérique (ex. 5 pour > 5, 40 pour < 40, 1 pour signal haussier).",
                                },
                                "value_max": {
                                    "type": "number",
                                    "description": "Borne haute si op='between'.",
                                },
                                "values": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "description": "Liste de valeurs entières si kind='signal' et op='in'.",
                                },
                                "timeframe": {
                                    "type": "string",
                                    "enum": ["day", "week", "month", "quarter"],
                                    "description": "Unité temporelle spécifique à cette règle (optionnel).",
                                },
                            },
                        },
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Champ de tri (défaut 'market_cap', ou 'piotroski_f', 'rsi_14', 'mos_intrinsic_pct', 'score:uncle_stock_score'...).",
                    },
                    "sort_dir": {"type": "string", "enum": ["asc", "desc"]},
                    "limit": {"type": "integer", "description": "Nombre max de titres retournés (1 à 100, défaut 40)."},
                    "offset": {"type": "integer", "description": "Décalage pour paginer (défaut 0)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_get_warehouse_overview",
            "description": (
                "Retourne l'inventaire complet de l'entrepôt Finance local : couverture du Screener, "
                "pays/zones/indices/bourses/secteurs disponibles avec compteurs, champs et presets du Screener, "
                "watchlists personnelles de l'utilisateur, indicateurs techniques personnalisés et file des fondamentaux."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_queue": {
                        "type": "boolean",
                        "description": "Inclure les statistiques de la file d'enrichissement des fondamentaux (défaut: true).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_get_stock_dossier",
            "description": (
                "Consulte la fiche boursière complète d'une entreprise, d'un ETF ou d'un fonds : "
                "cours & valorisation, technique multi-unités (Jour/Semaine/Mois/3 Mois + IsoPressure), "
                "scores (Piotroski, IH Score, Altman Z + 31 scores Uncle Stock), 13 valorisations intrinsèques "
                "(DCF, Graham, EPV, Buffett, Lynch, marge de sécurité), états financiers 10 ans, parties prenantes, "
                "dividendes et catalogue des 508 ratios Uncle Stock. Lit le cache local en priorité (0 crédit)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Ticker (ex. 'AI.PA', 'AAPL.US', 'MC.PA'), ISIN ou nom d'entreprise.",
                    },
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "summary",
                                "technicals",
                                "scores",
                                "intrinsic",
                                "statements",
                                "stakeholders",
                                "uncle_stock_ratios",
                            ],
                        },
                        "description": "Sections à extraire (défaut: ['summary', 'scores', 'intrinsic', 'technicals']).",
                    },
                    "ratios_query": {
                        "type": "string",
                        "description": "Filtre texte si 'uncle_stock_ratios' est demandé (ex. 'ROIC', 'Marge', 'Dette').",
                    },
                    "allow_live_fetch": {
                        "type": "boolean",
                        "description": "Autorise un téléchargement live uniquement si le titre manque totalement en cache (plafonné à 2/tour).",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_get_watchlists",
            "description": (
                "Consulte les listes de suivi (watchlists) personnelles de l'utilisateur avec notes personnelles, "
                "cours, variations 1J/1S/1M/3M/1A et principaux indicateurs issus de l'entrepôt local."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "watchlist_name": {
                        "type": "string",
                        "description": "Filtrer sur le nom d'une liste précise (optionnel).",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_get_indices",
            "description": (
                "Liste les indices boursiers disponibles et leurs cotations en cache, ou retourne la composition "
                "et les performances des actions d'un indice (ex. 'CAC40', 'SP500', 'NASDAQ100', 'DAX', 'STOXX600')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "index_code": {
                        "type": "string",
                        "description": "Code de l'indice à détailler (optionnel ; si omis, liste tous les indices).",
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": [
                            "weight_pct",
                            "change_1d_pct",
                            "change_1m_pct",
                            "change_ytd_pct",
                            "change_1y_pct",
                            "piotroski_f",
                            "rsi_14",
                            "pe_ttm",
                        ],
                        "description": "Critère de tri des constituants.",
                    },
                    "limit": {"type": "integer", "description": "Nombre max de constituants retournés (défaut 50, max 200)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_get_saved_analyses",
            "description": (
                "Consulte les analyses IA déjà archivées de l'utilisateur : analyses MOAT, avis d'experts célèbres "
                "(Buffett, Munger, Lynch, Dalio...), synthèses de dossiers boursiers, et rapports trimestriels PDF/texte importés."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Filtrer par ticker (optionnel)."},
                    "kind": {
                        "type": "string",
                        "enum": ["all", "moat", "expert", "dossier", "report", "news"],
                        "description": "Type d'archive à consulter (défaut: 'all').",
                    },
                    "expert_id": {"type": "string", "description": "Identifiant d'expert (optionnel)."},
                    "query": {"type": "string", "description": "Mot-clé recherché dans les titres, résumés ou rapports."},
                    "limit": {"type": "integer", "description": "Nombre max d'éléments (défaut 15, max 40)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_get_news",
            "description": (
                "Consulte les dépêches boursières déjà en cache local (EODHD/Yahoo avec sentiment) et les synthèses "
                "d'actualités IA sauvegardées par l'utilisateur pour un titre donné (0 appel réseau)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker de l'entreprise (ex. 'AI.PA', 'NVDA.US')."},
                    "limit": {"type": "integer", "description": "Nombre max de dépêches (défaut 15, max 30)."},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finance_search_catalog",
            "description": (
                "Recherche rapide par nom, ticker ou code ISIN dans l'entrepôt local, les catalogues de bourses "
                "synchronisés (PA, US, XETRA, LSE...) et les fonds européens EUFUND (0 appel réseau)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nom, ticker ou ISIN recherché."},
                    "exchange": {"type": "string", "description": "Code bourse EODHD (ex. 'PA', 'US', 'EUFUND', 'ALL')."},
                    "instrument_type": {"type": "string", "description": "Type d'instrument (ex. 'Common Stock', 'ETF', 'Fund')."},
                    "country": {"type": "string", "description": "Filtre pays optionnel."},
                    "currency": {"type": "string", "description": "Filtre devise optionnel."},
                    "limit": {"type": "integer", "description": "Nombre max de résultats (défaut 25, max 60)."},
                },
                "required": ["query"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers internes de normalisation & troncature
# ---------------------------------------------------------------------------

def _fold(text: str) -> str:
    norm = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).lower().strip()


def _normalize_timeframe(tf: Any, default: str = "day") -> str:
    raw = _fold(str(tf or ""))
    if not raw:
        return default
    mapped = _TIMEFRAME_ALIASES.get(raw, raw)
    return mapped if mapped in ("day", "week", "month", "quarter") else default


def _normalize_field_name(field_name: Any) -> str:
    raw = str(field_name or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    if low.startswith("score:"):
        return f"score:{low.split(':', 1)[1].strip()}"
    return _FIELD_ALIASES.get(low, raw)


def _normalize_rule(raw_rule: Any, default_tf: str) -> dict[str, Any]:
    if not isinstance(raw_rule, dict):
        raise ValueError("Chaque règle doit être un objet JSON.")
    r = dict(raw_rule)
    kind = str(r.get("kind") or "metric").strip().lower()
    op = str(r.get("op") or "").strip().lower()
    op = _OP_ALIASES.get(op, op)
    r["op"] = op

    if r.get("timeframe"):
        r["timeframe"] = _normalize_timeframe(r["timeframe"], default=default_tf)

    if kind == "compare":
        r["left"] = _normalize_field_name(r.get("left"))
        r["right"] = _normalize_field_name(r.get("right"))
        r["kind"] = "compare"
        return r

    raw_field = _normalize_field_name(r.get("field"))
    if raw_field in UNCLE_STOCK_SCORE_IDS and kind != "score":
        kind = "score"
    elif raw_field.startswith("score:"):
        kind = "score"
        raw_field = raw_field.split(":", 1)[1].strip()
    r["kind"] = kind
    r["field"] = raw_field

    if kind == "signal" and op == "in" and r.get("value") is None and isinstance(r.get("values"), list):
        r["value"] = r["values"]
    return r


def _compact_screener_item(item: dict[str, Any], extra_keys: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in _SCREENER_COMPACT_KEYS:
        if k in item and item[k] is not None and item[k] != "" and item[k] != []:
            out[k] = item[k]
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    requested_scores: dict[str, Any] = {}
    for ek in extra_keys:
        if ek.startswith("score:"):
            sid = ek.split(":", 1)[1]
            if sid in scores:
                requested_scores[sid] = scores[sid]
        elif ek in UNCLE_STOCK_SCORE_IDS and ek in scores:
            requested_scores[ek] = scores[ek]
        elif ek in item and item[ek] is not None:
            out[ek] = item[ek]
    if requested_scores:
        out["scores"] = requested_scores
    return out


def _resolve_watchlist_symbols(
    ctx: FinanceToolContext,
    watchlist_ref: str,
) -> tuple[str | None, list[str], list[str]]:
    """Retourne (matched_name, symbols, available_names) strictement pour `ctx.user_id`."""
    if ctx.sessions is None or not ctx.user_id:
        return None, [], []
    ref_fold = _fold(watchlist_ref)
    with ctx.sessions() as db:
        lists = list(
            db.scalars(
                select(FinanceWatchlist)
                .where(FinanceWatchlist.user_id == ctx.user_id)
                .order_by(FinanceWatchlist.position.asc(), FinanceWatchlist.created_at.asc())
            )
        )
        names = [wl.name for wl in lists]
        target = next(
            (wl for wl in lists if wl.id == watchlist_ref.strip() or _fold(wl.name) == ref_fold),
            None,
        )
        if target is None and ref_fold:
            target = next((wl for wl in lists if ref_fold in _fold(wl.name)), None)
        if target is None:
            return None, [], names
        rows = db.execute(
            select(
                FinanceWatchlistItem.symbol,
                FinanceWatchlistItem.eod_ticker,
                FinanceWatchlistItem.yahoo_symbol,
            ).where(
                FinanceWatchlistItem.user_id == ctx.user_id,
                FinanceWatchlistItem.list_id == target.id,
            )
        ).all()
        syms = [str(s).strip().upper() for row in rows for s in row if s and str(s).strip()]
        return target.name, syms, names


def _resolve_local_symbol(settings: Settings, raw_symbol: str) -> str:
    db_path = warehouse_db_path(settings)
    clean = str(raw_symbol or "").strip().strip("$")
    if not clean:
        return ""
    canonical = resolve_canonical_symbol(db_path, clean)
    # Si le nom ressemblait à une société (espaces ou pas de point et introuvable en cache),
    # tenter la recherche catalogue locale pour trouver le ticker exact.
    if (
        not get_instrument_meta(db_path, canonical)
        and not get_stored_eod_bars(db_path, canonical, limit=1)
        and not load_fundamental_series(db_path, canonical, "annual")[0]
    ):
        hits = search_finance_catalog(settings, clean, limit=5)
        if hits:
            best = hits[0]
            cand = str(best.get("eod_ticker") or best.get("symbol") or "").strip().upper()
            if cand:
                return resolve_canonical_symbol(db_path, cand)
    return canonical


def _build_local_dossier(settings: Settings, symbol: str) -> dict[str, Any] | None:
    """Assemble un dossier boursier 100 % localement depuis `finance_warehouse.db` (0 appel réseau)."""
    db_path = warehouse_db_path(settings)
    canonical = resolve_canonical_symbol(db_path, symbol)
    if not canonical:
        return None

    meta = get_instrument_meta(db_path, canonical) or {}
    stored_bars = get_stored_eod_bars(db_path, canonical, limit=None)
    ann_series, ann_curr, ann_src, _ = load_fundamental_series(db_path, canonical, "annual")
    qtr_series, qtr_curr, _, _ = load_fundamental_series(db_path, canonical, "quarterly")
    eod_snap = get_snapshot(db_path, canonical, "fundamentals", provider="eodhd", include_raw=True)
    eod_fund = eod_snap.get("raw") if (eod_snap and isinstance(eod_snap.get("raw"), dict)) else None
    yahoo_snap = get_snapshot(db_path, canonical, "quote_summary_ext", provider="yahoo_finance", include_raw=True)
    yahoo_sum = yahoo_snap.get("raw") if (yahoo_snap and isinstance(yahoo_snap.get("raw"), dict)) else None

    if not stored_bars and not ann_series and not eod_fund and not yahoo_sum:
        return None

    gen = (eod_fund or {}).get("General") or {}
    hl = (eod_fund or {}).get("Highlights") or {}
    val = (eod_fund or {}).get("Valuation") or {}
    tech = (eod_fund or {}).get("Technicals") or {}
    shares_st = (eod_fund or {}).get("SharesStats") or {}
    divs_meta = (eod_fund or {}).get("SplitsDividends") or {}

    y_price = (yahoo_sum or {}).get("price") or {}
    y_det = (yahoo_sum or {}).get("summaryDetail") or {}
    y_fin = (yahoo_sum or {}).get("financialData") or {}
    y_stat = (yahoo_sum or {}).get("defaultKeyStatistics") or {}
    y_prof = (yahoo_sum or {}).get("assetProfile") or {}

    currency = (
        str(gen.get("CurrencyCode") or y_price.get("currency") or meta.get("currency") or ann_curr or qtr_curr or "USD")
        .strip()
        .upper()
    )
    market_cap = _num(hl.get("MarketCapitalization")) or _num(y_price.get("marketCap"))
    div_yield_raw = _num(hl.get("DividendYield")) or _num(divs_meta.get("ForwardAnnualDividendYield")) or _num(y_det.get("dividendYield"))
    div_yield_pct = round(div_yield_raw * 100.0, 2) if (div_yield_raw is not None and abs(div_yield_raw) < 1.0) else div_yield_raw
    beta_val = _num(tech.get("Beta")) or _num(y_stat.get("beta")) or _num(y_det.get("beta"))

    last_bar_price = (_num(stored_bars[-1].get("close")) or _num(stored_bars[-1].get("adjusted_close"))) if stored_bars else None
    price = last_bar_price or _num(y_price.get("regularMarketPrice"))
    mma50 = _num(tech.get("50DayMA")) or _simple_ma(stored_bars, 50)
    mma200 = _num(tech.get("200DayMA")) or _simple_ma(stored_bars, 200)
    low_52w = _num(tech.get("52WeekLow")) or _num(y_det.get("fiftyTwoWeekLow"))
    high_52w = _num(tech.get("52WeekHigh")) or _num(y_det.get("fiftyTwoWeekHigh"))

    perf_payload, risk_payload, _ = compute_price_performance_and_risk(stored_bars, currency=currency)
    annual_tables = _compute_annual_dossier_tables(ann_series, stored_bars, beta_val)
    stakeholders = _extract_stakeholders(eod_fund, yahoo_sum)

    div_snap = get_snapshot(db_path, canonical, "dividends", include_raw=True)
    stored_divs: list[dict[str, Any]] = (div_snap.get("raw") if (div_snap and isinstance(div_snap.get("raw"), list)) else []) or []
    dividends_matrix = _build_dividends_matrix(stored_divs)

    shares_out = _num(shares_st.get("SharesOutstanding")) or _num(y_stat.get("sharesOutstanding"))
    shares_float = _num(shares_st.get("SharesFloat")) or _num(y_stat.get("floatShares"))
    float_pct = _div(shares_float, shares_out, 100.0, 1)

    def _pct_val(raw: Any) -> float | None:
        v = _num(raw)
        if v is None:
            return None
        return round(v * 100.0, 1) if abs(v) <= 2.5 else round(v, 1)

    rev_ttm = _num(hl.get("RevenueTTM")) or _num(y_fin.get("totalRevenue"))
    gp_ttm = _num(hl.get("GrossProfitTTM"))

    bal_yearly = ((eod_fund or {}).get("Financials") or {}).get("Balance_Sheet", {}).get("yearly") or {}
    latest_bal_row: dict[str, Any] = {}
    if isinstance(bal_yearly, dict) and bal_yearly:
        valid_bal_dates = sorted(k for k in bal_yearly.keys() if isinstance(bal_yearly.get(k), dict))
        if valid_bal_dates:
            latest_bal_row = bal_yearly[valid_bal_dates[-1]]
    preferred_stock = _num(latest_bal_row.get("preferredStockTotalEquity")) or _num(latest_bal_row.get("preferredStockRedeemable"))
    minority_interest = _num(latest_bal_row.get("noncontrollingInterestInConsolidatedEntity")) or _num(latest_bal_row.get("minorityInterest"))

    deduped_ann_series, deduped_ann_dates = _dedupe_annual_series_by_year(ann_series)
    piotroski_latest = annual_tables["piotroski"].get("latest_score")
    effective_shares = shares_out or ((market_cap / price) if (market_cap and price and price > 0) else None)

    macro_snap = get_snapshot(db_path, canonical, "macro_context", include_raw=False)
    macro_ctx = macro_snap.get("normalized") if macro_snap else None

    intrinsic_valuation = compute_intrinsic_valuations(
        ann_series=deduped_ann_series,
        dates=deduped_ann_dates,
        current_price=price,
        currency=currency,
        country_iso3=resolve_country_iso3(eod_fund, canonical),
        beta=beta_val,
        shares_override=effective_shares,
        dividend_yield_pct=div_yield_pct,
        preferred_stock=preferred_stock,
        minority_interest=minority_interest,
        macro_context=macro_ctx if isinstance(macro_ctx, dict) else None,
        piotroski_score=int(piotroski_latest) if isinstance(piotroski_latest, (int, float)) else None,
        bars=stored_bars,
    )

    cap_val_dict = {
        "shares_outstanding": shares_out,
        "float_pct": float_pct,
        "insiders_pct": _num(shares_st.get("PercentInsiders")) or _pct_val(y_stat.get("heldPercentInsiders")),
        "institutions_pct": _num(shares_st.get("PercentInstitutions")) or _pct_val(y_stat.get("heldPercentInstitutions")),
        "short_ratio": _num(shares_st.get("ShortRatio")) or _num(tech.get("ShortRatio")) or _num(y_stat.get("shortRatio")),
        "short_pct_float": _pct_val(shares_st.get("ShortPercentFloat") or tech.get("ShortPercent") or y_stat.get("shortPercentOfFloat")),
        "pe_ttm": _num(val.get("TrailingPE") or hl.get("PERatio") or y_stat.get("trailingPE")),
        "pe_forward": _num(val.get("ForwardPE") or y_stat.get("forwardPE")),
        "peg": _num(hl.get("PEGRatio") or y_stat.get("pegRatio")),
        "pb": _num(val.get("PriceBookMRQ") or y_stat.get("priceToBook")),
        "ev_ebitda": _num(val.get("EnterpriseValueEbitda") or y_stat.get("enterpriseToEbitda")),
        "ev_revenue": _num(val.get("EnterpriseValueRevenue") or y_stat.get("enterpriseToRevenue")),
        "op_margin_ttm": _pct_val(hl.get("OperatingMarginTTM") or y_fin.get("operatingMargins")),
        "net_margin_ttm": _pct_val(hl.get("ProfitMargin") or y_fin.get("profitMargins")),
        "gross_margin_ttm": _div(gp_ttm, rev_ttm, 100.0, 1) or _pct_val(y_fin.get("grossMargins")),
        "roe_ttm": _pct_val(hl.get("ReturnOnEquityTTM") or y_fin.get("returnOnEquity")),
        "roa_ttm": _pct_val(hl.get("ReturnOnAssetsTTM") or y_fin.get("returnOnAssets")),
        "rev_growth_q_yoy": _pct_val(hl.get("QuarterlyRevenueGrowthYOY") or y_fin.get("revenueGrowth")),
        "eps_growth_q_yoy": _pct_val(hl.get("QuarterlyEarningsGrowthYOY") or y_fin.get("earningsGrowth")),
        "market_cap": market_cap,
        "dividend_yield_pct": div_yield_pct,
        "price": price,
        "target_price": stakeholders["analysts"]["target_price"],
        "mma50": mma50,
        "mma200": mma200,
        "low_52w": low_52w,
        "high_52w": high_52w,
    }

    uncle_stock_scores = compute_uncle_stock_scores(
        ann_series=deduped_ann_series,
        dates=deduped_ann_dates,
        current_price=price,
        shares_override=effective_shares,
        eod_fund=eod_fund,
        capital_valuation=cap_val_dict,
        intrinsic_valuation=intrinsic_valuation,
        piotroski_score=int(piotroski_latest) if isinstance(piotroski_latest, (int, float)) else None,
        bars=stored_bars,
    )

    deduped_qtr_dates = sorted({d for v in qtr_series.values() for d in v.keys()})
    employees_val = _num(gen.get("FullTimeEmployees")) or _num(y_prof.get("fullTimeEmployees"))
    uncle_stock_catalog = compute_uncle_stock_catalog(
        ann_series=deduped_ann_series,
        qtr_series=qtr_series,
        dates=deduped_ann_dates,
        qtr_dates=deduped_qtr_dates,
        current_price=price,
        currency=currency,
        shares_override=effective_shares,
        eod_fund=eod_fund,
        capital_valuation=cap_val_dict,
        intrinsic_valuation=intrinsic_valuation,
        uncle_stock_scores=uncle_stock_scores,
        risk=risk_payload,
        performance=perf_payload,
        bars=stored_bars,
        macro_context=macro_ctx if isinstance(macro_ctx, dict) else None,
        stakeholders=stakeholders,
        preferred_stock=preferred_stock,
        minority_interest=minority_interest,
        employees=employees_val,
    )

    display_name = str(
        gen.get("Name")
        or y_price.get("longName")
        or meta.get("long_name")
        or meta.get("short_name")
        or canonical
    )
    ih_info = annual_tables["ih_score"]

    ann_stmt = build_period_from_series(ann_series, annual=True) if ann_series else {}
    qtr_stmt = build_period_from_series(qtr_series, annual=False) if qtr_series else {}

    return {
        "symbol": canonical,
        "currency": currency,
        "source_provider": ann_src or ("eodhd" if eod_fund else "yahoo_finance"),
        "stored_bars": stored_bars,
        "header": {
            "name": display_name,
            "cap_category": _cap_category(market_cap),
            "market_cap": market_cap,
            "dividend_yield_pct": div_yield_pct,
            "beta": round(beta_val, 2) if beta_val is not None else None,
            "ih_score": ih_info.get("latest_score"),
            "ih_quality": ih_info.get("quality_label"),
            "ih_trend": ih_info.get("trend"),
            "price_dynamics": _compute_price_dynamics(price, mma50, mma200),
            "sector": gen.get("Sector") or y_prof.get("sector") or meta.get("sector") or "",
            "industry": gen.get("Industry") or y_prof.get("industry") or meta.get("industry") or "",
            "country": gen.get("CountryName") or y_prof.get("country") or meta.get("country") or "",
            "exchange": gen.get("Exchange") or y_price.get("exchangeName") or meta.get("exchange") or "",
            "employees": employees_val,
            "website": gen.get("WebURL") or y_prof.get("website") or "",
            "isin": gen.get("ISIN") or meta.get("isin"),
            "description": (gen.get("Description") or y_prof.get("longBusinessSummary") or "")[:900],
        },
        "capital_valuation": cap_val_dict,
        "performance": perf_payload,
        "risk": risk_payload,
        "stakeholders": stakeholders,
        "annual_tables": annual_tables,
        "dividends_matrix": dividends_matrix,
        "statements": {"annual": ann_stmt, "quarterly": qtr_stmt},
        "intrinsic_valuation": intrinsic_valuation,
        "uncle_stock_scores": uncle_stock_scores,
        "uncle_stock_catalog": uncle_stock_catalog,
        "loaded_live": False,
    }


def _compact_statement_rows(period_data: dict[str, Any] | None, max_periods: int = 6) -> dict[str, Any]:
    if not isinstance(period_data, dict):
        return {}
    dates = list(period_data.get("dates") or [])[-max_periods:]
    if not dates:
        return {}
    offset = len(period_data.get("dates") or []) - len(dates)
    out: dict[str, Any] = {"dates": dates}
    for sec in ("income", "balance", "cashflow", "ratios"):
        rows_out = []
        for row in period_data.get(sec) or []:
            vals = list(row.get("values") or [])[offset:]
            if any(v is not None for v in vals):
                rows_out.append({"label": row.get("label") or row.get("key"), "values": vals})
        if rows_out:
            out[sec] = rows_out[:22]
    return out


# ---------------------------------------------------------------------------
# Implémentation des 8 outils
# ---------------------------------------------------------------------------

def _tool_screener_query(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    tf = _normalize_timeframe(args.get("timeframe"), default="day")
    raw_rules = args.get("rules") if isinstance(args.get("rules"), list) else []
    rules = [_normalize_rule(r, tf) for r in raw_rules]

    sort_by = _normalize_field_name(args.get("sort_by") or "market_cap") or "market_cap"
    sort_dir = str(args.get("sort_dir") or "desc").strip().lower()
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    preset_id = str(args.get("preset_id") or "").strip().lower()
    if preset_id:
        preset = next((p for p in SCREENER_PRESETS if p["id"] == preset_id), None)
        if not preset:
            return {"error": f"Preset inconnu : {preset_id!r}. Disponibles : {[p['id'] for p in SCREENER_PRESETS]}"}
        preset_rules = [_normalize_rule(r, tf) for r in preset["rules"]]
        rules = [*preset_rules, *rules]
        if not args.get("sort_by"):
            sort_by = preset.get("sort_by") or sort_by
            sort_dir = preset.get("sort_dir") or sort_dir

    universe_type = "all"
    universe_value: str | None = None
    wl_symbols: list[str] | None = None
    wl_matched_name: str | None = None
    watchlist_ref = str(args.get("watchlist") or "").strip()
    if watchlist_ref:
        wl_matched_name, wl_syms, available_names = _resolve_watchlist_symbols(ctx, watchlist_ref)
        if wl_matched_name is None:
            return {
                "error": f"Liste de suivi « {watchlist_ref} » introuvable.",
                "available_watchlists": available_names,
            }
        universe_type = "watchlist"
        wl_symbols = wl_syms

    raw_country = str(args.get("country") or "").strip()
    country = canonicalize_country(raw_country) if raw_country else ""

    limit = max(1, min(100, int(args.get("limit") or 40)))
    offset = max(0, int(args.get("offset") or 0))

    try:
        res = query_screener(
            ctx.settings,
            timeframe=tf,
            universe_type=universe_type,
            universe_value=universe_value,
            watchlist_symbols=wl_symbols,
            index_code=str(args.get("index_code") or "").strip(),
            market_zone=str(args.get("market_zone") or "").strip(),
            country=country,
            cap_category=str(args.get("cap_category") or "").strip(),
            search=str(args.get("search") or "").strip(),
            sector=str(args.get("sector") or "").strip(),
            exchange=str(args.get("exchange") or "").strip(),
            currency=str(args.get("currency") or "").strip(),
            only_with_fundamentals=bool(args.get("only_with_fundamentals", False)),
            rules=rules,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        return {
            "error": str(exc),
            "valid_fields_hint": _FIELD_KEYS_SUMMARY,
            "valid_score_ids_hint": _SCORE_IDS_SUMMARY,
        }

    extra_keys: set[str] = {sort_by}
    for r in rules:
        for rk in (r.get("field"), r.get("left"), r.get("right")):
            if rk:
                extra_keys.add(str(rk))

    items = [_compact_screener_item(it, extra_keys) for it in res.get("items") or []]
    for it in items[:8]:
        ctx.track_symbol(it.get("eod_ticker") or it.get("symbol"))

    return {
        "timeframe": res.get("timeframe"),
        "total": res.get("total", 0),
        "returned": len(items),
        "offset": res.get("offset", 0),
        "universe_total": res.get("universe_total", 0),
        "with_fundamentals_count": res.get("with_fundamentals_count", 0),
        "missing_data_count": res.get("missing_data_count", 0),
        "filters_applied": {
            "country": country or None,
            "market_zone": args.get("market_zone") or None,
            "index_code": args.get("index_code") or None,
            "exchange": args.get("exchange") or None,
            "sector": args.get("sector") or None,
            "watchlist": wl_matched_name,
            "preset_id": preset_id or None,
            "rules": rules,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        },
        "items": items,
    }


def _tool_warehouse_overview(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    db_path = warehouse_db_path(ctx.settings)
    meta = get_screener_metadata(ctx.settings)
    cov = meta.get("coverage") or {}

    watchlists_info: list[dict[str, Any]] = []
    custom_indicators_info: list[dict[str, Any]] = []
    if ctx.sessions is not None and ctx.user_id:
        with ctx.sessions() as db:
            wls = list(
                db.scalars(
                    select(FinanceWatchlist)
                    .where(FinanceWatchlist.user_id == ctx.user_id)
                    .order_by(FinanceWatchlist.position.asc(), FinanceWatchlist.created_at.asc())
                )
            )
            counts_rows = db.execute(
                select(FinanceWatchlistItem.list_id, func.count(FinanceWatchlistItem.id))
                .where(FinanceWatchlistItem.user_id == ctx.user_id)
                .group_by(FinanceWatchlistItem.list_id)
            ).all()
            cnt_map = {str(lid): int(c) for lid, c in counts_rows if lid}
            watchlists_info = [
                {"id": wl.id, "name": wl.name, "items_count": cnt_map.get(wl.id, 0)}
                for wl in wls
            ]
            inds = list(
                db.scalars(
                    select(FinanceCustomIndicator)
                    .where(FinanceCustomIndicator.user_id == ctx.user_id)
                    .order_by(FinanceCustomIndicator.created_at.asc())
                )
            )
            custom_indicators_info = [
                {
                    "name": ind.name,
                    "formula": ind.formula,
                    "pane": ind.pane,
                    "enabled_by_default": ind.enabled_by_default,
                }
                for ind in inds
            ]

    out: dict[str, Any] = {
        "warehouse": get_warehouse_overview(db_path),
        "screener_coverage": {
            "total_snapshots": cov.get("total_snapshots", 0),
            "with_technicals": cov.get("with_technicals", 0),
            "with_fundamentals": cov.get("with_fundamentals", 0),
            "warehouse_symbols_count": cov.get("warehouse_symbols_count", 0),
            "last_computed_at": cov.get("last_computed_at"),
            "countries": (cov.get("countries") or [])[:30],
            "market_zones": cov.get("market_zones") or [],
            "indices": (cov.get("indices") or [])[:40],
            "exchanges": (cov.get("exchange_items") or [])[:30],
            "sectors": cov.get("sectors") or [],
            "currencies": cov.get("currencies") or [],
            "cap_categories": cov.get("cap_categories") or [],
        },
        "screener_presets": [
            {"id": p["id"], "name": p["name"], "description": p["description"]}
            for p in meta.get("presets") or []
        ],
        "screener_fields": [
            {"key": f["key"], "label": f["label"], "category": f["category"], "supports_timeframe": bool(f.get("supports_timeframe"))}
            for f in meta.get("fields") or []
        ],
        "uncle_stock_score_ids": sorted(UNCLE_STOCK_SCORE_IDS),
        "user_watchlists": watchlists_info,
        "user_custom_indicators": custom_indicators_info,
    }
    if args.get("include_queue", True):
        out["fundamentals_queue"] = queue_stats(db_path)
    return out


async def _tool_stock_dossier(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    raw_symbol = str(args.get("symbol") or "").strip()
    if not raw_symbol:
        return {"error": "Paramètre `symbol` requis."}

    resolved = _resolve_local_symbol(ctx.settings, raw_symbol)
    raw_sections = args.get("sections")
    if isinstance(raw_sections, list) and raw_sections:
        sections = {str(s).strip().lower() for s in raw_sections if str(s).strip().lower() in _VALID_DOSSIER_SECTIONS}
    else:
        sections = {"summary", "scores", "intrinsic", "technicals"}
    if not sections:
        sections = {"summary", "scores", "intrinsic", "technicals"}

    dossier = _build_local_dossier(ctx.settings, resolved)
    loaded_live = False

    if dossier is None:
        allow_live_raw = args.get("allow_live_fetch", True)
        allow_live = not (
            allow_live_raw is False
            or (isinstance(allow_live_raw, str) and allow_live_raw.strip().lower() == "false")
        )
        if not allow_live:
            return {
                "symbol": resolved,
                "error": f"Aucune donnée locale en cache pour « {raw_symbol} » (téléchargement réseau désactivé).",
            }
        if ctx.settings.demo_mode:
            return {
                "symbol": resolved,
                "error": f"Aucune donnée locale en cache pour « {raw_symbol} » (mode démo sans téléchargement réseau).",
            }
        if ctx.live_dossier_fetches >= ctx.max_live_dossier_fetches:
            return {
                "symbol": resolved,
                "error": (
                    f"« {raw_symbol} » est absent du cache local et le plafond de "
                    f"{ctx.max_live_dossier_fetches} chargements réseau par tour est atteint."
                ),
            }
        try:
            dossier = await get_financial_dossier(ctx.settings, resolved, refresh=False)
            ctx.live_dossier_fetches += 1
            loaded_live = True
        except Exception as exc:
            return {"symbol": resolved, "error": f"Impossible de charger le dossier pour « {raw_symbol} » : {exc}"}

    canon = str(dossier.get("symbol") or resolved)
    ctx.track_symbol(canon)
    hdr = dossier.get("header") or {}
    cap = dossier.get("capital_valuation") or {}
    ann_tbl = dossier.get("annual_tables") or {}

    result: dict[str, Any] = {
        "symbol": canon,
        "name": hdr.get("name") or canon,
        "currency": dossier.get("currency"),
        "source_provider": dossier.get("source_provider"),
        "loaded_live": loaded_live,
    }

    if "summary" in sections:
        perf = dossier.get("performance") or {}
        risk = dossier.get("risk") or {}
        result["summary"] = {
            "header": {
                "cap_category": hdr.get("cap_category"),
                "market_cap": hdr.get("market_cap"),
                "dividend_yield_pct": hdr.get("dividend_yield_pct"),
                "beta": hdr.get("beta"),
                "sector": hdr.get("sector"),
                "industry": hdr.get("industry"),
                "country": hdr.get("country"),
                "exchange": hdr.get("exchange"),
                "isin": hdr.get("isin"),
                "employees": hdr.get("employees"),
                "price_dynamics": hdr.get("price_dynamics"),
                "description": (hdr.get("description") or "")[:500],
            },
            "capital_valuation": cap,
            "performances_pct": {
                h["label"]: h["pct"]
                for h in (perf.get("horizons") or [])
                if h.get("pct") is not None
            },
            "risk": {
                m["label"]: {
                    h: v
                    for h, v in zip(risk.get("horizons") or [], m.get("values") or [])
                    if v is not None
                }
                for m in (risk.get("metrics") or [])[:8]
                if any(v is not None for v in (m.get("values") or []))
            },
        }

    if "technicals" in sections:
        bars = dossier.get("stored_bars")
        if bars is None:
            bars = get_stored_eod_bars(warehouse_db_path(ctx.settings), canon, limit=None)
        result["technicals"] = compute_multi_timeframe_technicals(bars or [])

    if "scores" in sections:
        us = dossier.get("uncle_stock_scores") or {}
        result["scores"] = {
            "ih_score": ann_tbl.get("ih_score"),
            "piotroski": ann_tbl.get("piotroski"),
            "altman": ann_tbl.get("altman"),
            "uncle_stock_summary": us.get("summary"),
            "uncle_stock_scores": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "category": item.get("category"),
                    "verified": (item.get("verified") or {}).get("display_value"),
                    "verified_score": (item.get("verified") or {}).get("final_score"),
                    "documented": (item.get("documented") or {}).get("display_value"),
                }
                for item in (us.get("items") or [])
                if item.get("available")
            ],
        }

    if "intrinsic" in sections:
        intr = dossier.get("intrinsic_valuation") or {}
        result["intrinsic"] = {
            "available": bool(intr.get("available")),
            "summary": intr.get("summary"),
            "cost_of_capital": intr.get("cost_of_capital"),
            "owner_returns": intr.get("owner_returns"),
            "methods": [
                {
                    "name": m.get("name"),
                    "weight": m.get("weight"),
                    "corrected_value": m.get("corrected_value"),
                    "unclestock_value": m.get("unclestock_value"),
                    "mos_corrected_pct": m.get("margin_of_safety_corrected_pct"),
                    "status_corrected": m.get("status_corrected"),
                }
                for m in (intr.get("methods") or [])
            ],
            "scenarios": intr.get("scenarios"),
        }

    if "statements" in sections:
        ann_years = ann_tbl.get("years") or []
        stmts = dossier.get("statements") or {}
        result["statements"] = {
            "annual_ratios": {
                "summary": _compact_annual_table(ann_years, ann_tbl.get("summary") or [], max_years=6),
                "profitability": _compact_annual_table(ann_years, ann_tbl.get("profitability") or [], max_years=6),
                "solvency": _compact_annual_table(ann_years, ann_tbl.get("solvency") or [], max_years=6),
                "distribution": _compact_annual_table(ann_years, ann_tbl.get("distribution") or [], max_years=6),
                "efficiency": _compact_annual_table(ann_years, ann_tbl.get("efficiency") or [], max_years=6),
            },
            "annual_statements": _compact_statement_rows(stmts.get("annual"), max_periods=6),
            "quarterly_statements": _compact_statement_rows(stmts.get("quarterly"), max_periods=4),
            "dividends_annual": [
                {"year": r.get("year"), "total": r.get("total")}
                for r in ((dossier.get("dividends_matrix") or {}).get("rows") or [])[:8]
                if r.get("total") is not None
            ],
        }

    if "stakeholders" in sections:
        stk = dossier.get("stakeholders") or {}
        result["stakeholders"] = {
            "analysts": stk.get("analysts"),
            "officers": (stk.get("officers") or [])[:8],
            "insiders_net_amount": stk.get("insiders_net_amount"),
            "insiders": (stk.get("insiders") or [])[:8],
            "funds": (stk.get("funds") or [])[:6],
            "institutions": (stk.get("institutions") or [])[:6],
        }

    if "uncle_stock_ratios" in sections:
        cat = dossier.get("uncle_stock_catalog") or {}
        items = [it for it in (cat.get("items") or []) if it.get("available")]
        q_fold = _fold(str(args.get("ratios_query") or ""))
        if q_fold:
            items = [
                it
                for it in items
                if q_fold in _fold(f"{it.get('name', '')} {it.get('category', '')} {it.get('section', '')} {it.get('description', '')}")
            ]
        result["uncle_stock_ratios"] = {
            "total_count": cat.get("total_count", 0),
            "computed_count": cat.get("computed_count", 0),
            "years": cat.get("years") or [],
            "matched_count": len(items),
            "items": [
                {
                    "name": it.get("name"),
                    "category": it.get("category"),
                    "section": it.get("section"),
                    "formatted_value": it.get("formatted_value"),
                    "latest_value": it.get("latest_value"),
                    "values_by_year": it.get("values_by_year"),
                }
                for it in items[:35]
            ],
        }

    return result


def _tool_watchlists(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    if ctx.sessions is None or not ctx.user_id:
        return {"error": "Contexte utilisateur indisponible pour lire les listes de suivi."}
    db_path = warehouse_db_path(ctx.settings)
    filter_name = _fold(str(args.get("watchlist_name") or ""))

    with ctx.sessions() as db:
        lists = list(
            db.scalars(
                select(FinanceWatchlist)
                .where(FinanceWatchlist.user_id == ctx.user_id)
                .order_by(FinanceWatchlist.position.asc(), FinanceWatchlist.created_at.asc())
            )
        )
        if filter_name:
            lists = [wl for wl in lists if filter_name in _fold(wl.name) or wl.id == args.get("watchlist_name")]
        if not lists:
            return {"watchlists": [], "message": "Aucune liste de suivi correspondante."}

        items_by_list: dict[str, list[FinanceWatchlistItem]] = {}
        all_syms: set[str] = set()
        for wl in lists:
            wl_items = list(
                db.scalars(
                    select(FinanceWatchlistItem)
                    .where(
                        FinanceWatchlistItem.user_id == ctx.user_id,
                        FinanceWatchlistItem.list_id == wl.id,
                    )
                    .order_by(FinanceWatchlistItem.position.asc(), FinanceWatchlistItem.created_at.asc())
                )
            )
            items_by_list[wl.id] = wl_items
            for it in wl_items:
                for cand in (it.eod_ticker, it.symbol, it.yahoo_symbol):
                    if cand:
                        all_syms.add(cand.upper())

    snap_by_sym: dict[str, dict[str, Any]] = {}
    if all_syms:
        scr = query_screener(
            ctx.settings,
            universe_type="watchlist",
            watchlist_symbols=sorted(all_syms),
            limit=300,
            auto_backfill=False,
        )
        for row in scr.get("items") or []:
            for k in (row.get("symbol"), row.get("eod_ticker"), row.get("yahoo_symbol")):
                if k:
                    snap_by_sym[str(k).upper()] = row

    out_lists: list[dict[str, Any]] = []
    for wl in lists:
        enriched_items: list[dict[str, Any]] = []
        for it in items_by_list.get(wl.id, []):
            tkr = (it.eod_ticker or it.symbol).upper()
            ctx.track_symbol(tkr)
            snap = snap_by_sym.get(tkr) or snap_by_sym.get(it.symbol.upper()) or snap_by_sym.get((it.yahoo_symbol or "").upper())
            if snap is None:
                canon = resolve_canonical_symbol(db_path, tkr)
                bars = get_stored_eod_bars(db_path, canon, limit=400)
                ret = compute_period_returns(bars) if bars else {}
            else:
                ret = {}
            enriched_items.append(
                {
                    "symbol": it.symbol,
                    "eod_ticker": it.eod_ticker or it.symbol,
                    "name": (snap or {}).get("name") or it.name,
                    "exchange": (snap or {}).get("exchange") or it.exchange,
                    "currency": (snap or {}).get("currency") or it.currency,
                    "note": it.note or "",
                    "price": (snap or {}).get("price") if snap else ret.get("price"),
                    "change_1d_pct": (snap or {}).get("change_1d_pct") if snap else ret.get("change_1d_pct"),
                    "change_1w_pct": (snap or {}).get("change_1w_pct") if snap else ret.get("change_1w_pct"),
                    "change_1m_pct": (snap or {}).get("change_1m_pct") if snap else ret.get("change_1m_pct"),
                    "change_3m_pct": (snap or {}).get("change_3m_pct") if snap else ret.get("change_3m_pct"),
                    "change_1y_pct": (snap or {}).get("change_1y_pct") if snap else ret.get("change_1y_pct"),
                    "pe_ttm": (snap or {}).get("pe_ttm"),
                    "roic_pct": (snap or {}).get("roic_pct"),
                    "piotroski_f": (snap or {}).get("piotroski_f"),
                    "ih_score": (snap or {}).get("ih_score"),
                    "rsi_14": (snap or {}).get("rsi_14"),
                    "mos_intrinsic_pct": (snap or {}).get("mos_intrinsic_pct"),
                }
            )
        out_lists.append({"id": wl.id, "name": wl.name, "count": len(enriched_items), "items": enriched_items})
    return {"watchlists": out_lists}


async def _tool_indices(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    db_path = warehouse_db_path(ctx.settings)
    raw_code = str(args.get("index_code") or "").strip().upper()
    if not raw_code:
        rows = []
        for defn in INDEX_DEFINITIONS:
            code = defn["code"]
            stored, _ = get_index_constituents(db_path, code, max_age_seconds=None)
            snap = get_snapshot(db_path, defn["eod_ticker"], "index_quote", max_age_seconds=None)
            q = (snap or {}).get("normalized") if isinstance(snap, dict) else {}
            rows.append(
                {
                    "code": code,
                    "name": defn["name"],
                    "region": defn.get("region"),
                    "tier": defn.get("tier"),
                    "currency": defn.get("currency"),
                    "constituents_in_cache": len(stored or []),
                    "last_price": (q or {}).get("last_price"),
                    "change_pct": (q or {}).get("change_pct"),
                    "as_of": (q or {}).get("as_of"),
                }
            )
        return {"indices": rows}

    perf = await get_index_performances(ctx.settings, raw_code, refresh=False, cache_only=True)
    if perf is None:
        return {
            "error": f"Indice inconnu : {raw_code!r}.",
            "available_indices": [d["code"] for d in INDEX_DEFINITIONS],
        }

    # Enrichir les constituants avec les métriques Screener en cache
    scr = query_screener(ctx.settings, index_code=raw_code, limit=300, auto_backfill=False)
    scr_map: dict[str, dict[str, Any]] = {}
    for srow in scr.get("items") or []:
        for k in (srow.get("symbol"), srow.get("eod_ticker")):
            if k:
                scr_map[str(k).upper()] = srow

    items = []
    for item in perf.get("items") or []:
        eod_t = str(item.get("eod_ticker") or item.get("symbol") or "").upper()
        s_extra = scr_map.get(eod_t) or scr_map.get(str(item.get("symbol") or "").upper()) or {}
        items.append(
            {
                "symbol": item.get("symbol"),
                "eod_ticker": eod_t,
                "name": item.get("name"),
                "sector": item.get("sector"),
                "weight_pct": item.get("weight_pct"),
                "price": item.get("price"),
                "currency": item.get("currency"),
                "change_1d_pct": item.get("change_1d_pct"),
                "change_1m_pct": item.get("change_1m_pct"),
                "change_ytd_pct": item.get("change_ytd_pct"),
                "change_1y_pct": item.get("change_1y_pct"),
                "piotroski_f": s_extra.get("piotroski_f"),
                "rsi_14": s_extra.get("rsi_14"),
                "pe_ttm": s_extra.get("pe_ttm"),
                "roic_pct": s_extra.get("roic_pct"),
                "mos_intrinsic_pct": s_extra.get("mos_intrinsic_pct"),
            }
        )

    sort_by = str(args.get("sort_by") or "weight_pct").strip()
    reverse = sort_by not in ("rsi_14", "pe_ttm")

    def _idx_sort_key(row: dict[str, Any]) -> tuple[bool, float]:
        val = row.get(sort_by)
        if val is None:
            return (True, 0.0)
        num = float(val)
        return (False, -num if reverse else num)

    items.sort(key=_idx_sort_key)
    limit = max(1, min(200, int(args.get("limit") or 50)))
    sliced = items[:limit]
    for it in sliced[:6]:
        ctx.track_symbol(it.get("eod_ticker") or it.get("symbol"))

    return {
        "index": perf.get("index"),
        "summary": perf.get("summary"),
        "total_constituents": len(items),
        "returned": len(sliced),
        "items": sliced,
    }


def _tool_saved_analyses(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    db_path = warehouse_db_path(ctx.settings)
    raw_sym = str(args.get("symbol") or "").strip().upper()
    kind = str(args.get("kind") or "all").strip().lower()
    expert_id = str(args.get("expert_id") or "").strip() or None
    q_fold = _fold(str(args.get("query") or ""))
    limit = max(1, min(40, int(args.get("limit") or 15)))

    items: list[dict[str, Any]] = []
    if kind in ("all", "expert", "dossier") or expert_id:
        wh_kind = None if kind == "all" else kind
        for entry in list_ai_analyses(
            db_path,
            symbol=raw_sym or None,
            kind=wh_kind,
            expert_id=expert_id,
            limit=limit,
        ):
            items.append(
                {
                    "id": entry.get("id"),
                    "kind": entry.get("kind"),
                    "symbol": entry.get("symbol"),
                    "company_name": entry.get("company_name"),
                    "expert_id": entry.get("expert_id"),
                    "expert_name": entry.get("expert_name"),
                    "model": entry.get("model"),
                    "verdict": entry.get("verdict"),
                    "conviction": entry.get("conviction"),
                    "horizon": entry.get("horizon"),
                    "question": entry.get("question"),
                    "summary_markdown": str(entry.get("markdown") or "")[:2400],
                    "created_at": entry.get("created_at"),
                }
            )

    if ctx.sessions is not None and ctx.user_id and not expert_id:
        sym_aliases: list[str] | None = None
        if raw_sym:
            canon = resolve_canonical_symbol(db_path, raw_sym)
            sym_aliases = sorted({raw_sym, canon, raw_sym.split(".")[0], canon.split(".")[0]})

        with ctx.sessions() as db:
            if kind in ("all", "moat"):
                stmt = select(FinanceStockMoat).where(FinanceStockMoat.user_id == ctx.user_id)
                if sym_aliases:
                    stmt = stmt.where(FinanceStockMoat.symbol.in_(sym_aliases))
                for m in db.scalars(stmt.order_by(FinanceStockMoat.created_at.desc()).limit(limit)):
                    items.append(
                        {
                            "id": m.id,
                            "kind": "moat",
                            "symbol": m.symbol,
                            "company_name": m.company_name,
                            "moat_rating": m.moat_rating,
                            "moat_score": m.moat_score,
                            "pillars": m.pillars,
                            "strengths": m.strengths,
                            "weaknesses": m.weaknesses,
                            "summary_markdown": (m.summary_markdown or "")[:2400],
                            "created_at": m.created_at.isoformat() if m.created_at else "",
                        }
                    )

            if kind in ("all", "report"):
                stmt = select(FinanceQuarterlyReport).where(FinanceQuarterlyReport.user_id == ctx.user_id)
                if sym_aliases:
                    stmt = stmt.where(FinanceQuarterlyReport.symbol.in_(sym_aliases))
                for r in db.scalars(stmt.order_by(FinanceQuarterlyReport.created_at.desc()).limit(limit)):
                    excerpt = ""
                    if q_fold and r.extracted_text:
                        idx = _fold(r.extracted_text).find(q_fold)
                        if idx != -1:
                            start = max(0, idx - 250)
                            excerpt = r.extracted_text[start : start + 1200]
                    items.append(
                        {
                            "id": r.id,
                            "kind": "report",
                            "symbol": r.symbol,
                            "company_name": r.company_name,
                            "title": r.title,
                            "period_label": r.period_label,
                            "key_metrics": r.key_metrics,
                            "summary_markdown": (r.summary_markdown or "")[:2400],
                            "matching_excerpt": excerpt or None,
                            "created_at": r.created_at.isoformat() if r.created_at else "",
                        }
                    )

            if kind in ("all", "news"):
                stmt = select(FinanceStockNews).where(FinanceStockNews.user_id == ctx.user_id)
                if sym_aliases:
                    stmt = stmt.where(FinanceStockNews.symbol.in_(sym_aliases))
                for n in db.scalars(stmt.order_by(FinanceStockNews.created_at.desc()).limit(limit)):
                    items.append(
                        {
                            "id": n.id,
                            "kind": "news",
                            "symbol": n.symbol,
                            "company_name": n.company_name,
                            "search_query": n.search_query,
                            "summary_markdown": (n.summary_markdown or "")[:2400],
                            "created_at": n.created_at.isoformat() if n.created_at else "",
                        }
                    )

    if q_fold:
        filtered = []
        for it in items:
            blob = _fold(
                " ".join(
                    str(it.get(k) or "")
                    for k in ("symbol", "company_name", "title", "expert_name", "verdict", "summary_markdown", "matching_excerpt")
                )
            )
            if q_fold in blob:
                filtered.append(it)
        items = filtered

    items.sort(key=lambda it: str(it.get("created_at") or ""), reverse=True)
    sliced = items[:limit]
    for it in sliced[:6]:
        ctx.track_symbol(it.get("symbol"))
    return {"total": len(items), "returned": len(sliced), "items": sliced}


def _tool_news(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    raw_sym = str(args.get("symbol") or "").strip().upper()
    if not raw_sym:
        return {"error": "Paramètre `symbol` requis."}
    db_path = warehouse_db_path(ctx.settings)
    canonical = _resolve_local_symbol(ctx.settings, raw_sym)
    limit = max(1, min(30, int(args.get("limit") or 15)))
    ctx.track_symbol(canonical)

    cached_feed: dict[str, Any] | None = None
    for snap_sym in (canonical, raw_sym):
        snap = get_snapshot(db_path, snap_sym, "news", provider="eodhd", include_raw=False) or get_snapshot(
            db_path, snap_sym, "news", include_raw=False
        )
        if snap and isinstance(snap.get("normalized"), dict):
            norm = snap["normalized"]
            feed_items = norm.get("items") or []
            if feed_items:
                cached_feed = {
                    "source": norm.get("source") or "EOD Historical Data",
                    "updated_at": snap.get("updated_at"),
                    "items": [
                        {
                            "title": n.get("title"),
                            "source": n.get("source"),
                            "published_at": n.get("published_at"),
                            "sentiment": n.get("sentiment"),
                            "snippet": (n.get("snippet") or "")[:300],
                            "url": n.get("url"),
                        }
                        for n in feed_items[:limit]
                    ],
                }
                break

    user_news: list[dict[str, Any]] = []
    if ctx.sessions is not None and ctx.user_id:
        aliases = sorted({raw_sym, canonical, raw_sym.split(".")[0], canonical.split(".")[0]})
        with ctx.sessions() as db:
            rows = list(
                db.scalars(
                    select(FinanceStockNews)
                    .where(
                        FinanceStockNews.user_id == ctx.user_id,
                        FinanceStockNews.symbol.in_(aliases),
                    )
                    .order_by(FinanceStockNews.created_at.desc())
                    .limit(10)
                )
            )
            user_news = [
                {
                    "search_query": r.search_query,
                    "summary_markdown": (r.summary_markdown or "")[:2000],
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]

    return {
        "symbol": canonical,
        "cached_feed": cached_feed or {"items": [], "note": "Aucune dépêche en cache local pour ce titre."},
        "saved_news_syntheses": user_news,
    }


def _tool_search_catalog(args: dict[str, Any], ctx: FinanceToolContext) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "Paramètre `query` requis."}
    limit = max(1, min(60, int(args.get("limit") or 25)))
    exchange = str(args.get("exchange") or "ALL").strip().upper() or "ALL"
    instrument_type = str(args.get("instrument_type") or "").strip()
    country = str(args.get("country") or "").strip()
    currency = str(args.get("currency") or "").strip()

    db_path = warehouse_db_path(ctx.settings)
    seen: set[str] = set()
    items: list[dict[str, Any]] = []

    if exchange == "ALL" and not instrument_type and not country and not currency:
        for hit in search_finance_catalog(ctx.settings, query, limit=limit):
            tkr = str(hit.get("eod_ticker") or hit.get("symbol") or "").upper()
            if tkr and tkr not in seen:
                seen.add(tkr)
                items.append(
                    {
                        "symbol": hit.get("symbol"),
                        "eod_ticker": tkr,
                        "name": hit.get("name"),
                        "exchange": hit.get("exchange"),
                        "currency": hit.get("currency"),
                        "sector": hit.get("sector"),
                        "source": hit.get("source"),
                        "cached_in_warehouse": bool(hit.get("cached_in_warehouse")),
                    }
                )

    exch_res = search_exchange_symbols(
        db_path,
        exchange,
        query=query,
        currency=currency,
        country=country,
        instrument_type=instrument_type,
        limit=limit,
    )
    for row in exch_res.get("items") or []:
        tkr = str(row.get("eod_ticker") or row.get("symbol") or "").upper()
        if tkr and tkr not in seen:
            seen.add(tkr)
            items.append(
                {
                    "symbol": row.get("symbol"),
                    "eod_ticker": tkr,
                    "name": row.get("name"),
                    "exchange": row.get("exchange_code") or row.get("exchange"),
                    "country": row.get("country"),
                    "currency": row.get("currency"),
                    "type": row.get("type"),
                    "isin": row.get("isin"),
                    "fund_family": row.get("fund_family"),
                    "cached_in_warehouse": bool(row.get("cached_in_warehouse")),
                }
            )
            if len(items) >= limit:
                break

    for it in items[:5]:
        ctx.track_symbol(it.get("eod_ticker") or it.get("symbol"))
    return {"query": query, "returned": len(items[:limit]), "items": items[:limit]}


# ---------------------------------------------------------------------------
# Point d'entrée d'exécution & libellés SSE
# ---------------------------------------------------------------------------

def _sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def format_tool_status_label(name: str, args: dict[str, Any]) -> str:
    if name == "finance_screener_query":
        parts = []
        if args.get("country"):
            parts.append(str(args["country"]))
        elif args.get("market_zone"):
            parts.append(str(args["market_zone"]))
        if args.get("index_code"):
            parts.append(str(args["index_code"]))
        if args.get("watchlist"):
            parts.append(f"liste « {args['watchlist']} »")
        for r in (args.get("rules") or [])[:3]:
            if isinstance(r, dict):
                if r.get("kind") == "compare":
                    parts.append(f"{r.get('left')} {r.get('op')} {r.get('right')}")
                elif r.get("field"):
                    val = r.get("value")
                    parts.append(f"{r.get('field')} {r.get('op', '')} {val if val is not None else ''}".strip())
        detail = " · ".join(p for p in parts if p) or "tous critères"
        return f"🔍 Screener Finance : {detail[:90]}…"
    if name == "finance_get_warehouse_overview":
        return "🗄️ Inventaire de l'entrepôt Finance & listes disponibles…"
    if name == "finance_get_stock_dossier":
        return f"📊 Dossier financier : {args.get('symbol', '')}…"
    if name == "finance_get_watchlists":
        wl = str(args.get("watchlist_name") or "").strip()
        return f"⭐ Consultation des listes de suivi{f' ({wl})' if wl else ''}…"
    if name == "finance_get_indices":
        code = str(args.get("index_code") or "").strip()
        return f"📈 Indice boursier : {code or 'vue globale'}…"
    if name == "finance_get_saved_analyses":
        sym = str(args.get("symbol") or "").strip()
        return f"🧠 Archives IA Finance (MOAT, experts, rapports){f' · {sym}' if sym else ''}…"
    if name == "finance_get_news":
        return f"📰 Actualités en cache : {args.get('symbol', '')}…"
    if name == "finance_search_catalog":
        return f"🔎 Recherche catalogue boursier : « {args.get('query', '')} »…"
    return f"📊 Consultation Finance ({name})…"


async def execute_finance_tool(
    name: str,
    raw_args: dict[str, Any] | str | None,
    ctx: FinanceToolContext,
) -> dict[str, Any]:
    """Exécute un outil Finance en lecture seule et retourne un dictionnaire JSON-sérialisable."""
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args) if raw_args.strip() else {}
        except ValueError as exc:
            return {"error": f"Arguments JSON invalides : {exc}"}
    elif isinstance(raw_args, dict):
        args = dict(raw_args)
    else:
        args = {}

    if not isinstance(args, dict):
        return {"error": "Les arguments doivent former un objet JSON."}

    if name not in ctx.consulted_tools:
        ctx.consulted_tools.append(name)

    try:
        if name == "finance_screener_query":
            res = _tool_screener_query(args, ctx)
        elif name == "finance_get_warehouse_overview":
            res = _tool_warehouse_overview(args, ctx)
        elif name == "finance_get_stock_dossier":
            res = await _tool_stock_dossier(args, ctx)
        elif name == "finance_get_watchlists":
            res = _tool_watchlists(args, ctx)
        elif name == "finance_get_indices":
            res = await _tool_indices(args, ctx)
        elif name == "finance_get_saved_analyses":
            res = _tool_saved_analyses(args, ctx)
        elif name == "finance_get_news":
            res = _tool_news(args, ctx)
        elif name == "finance_search_catalog":
            res = _tool_search_catalog(args, ctx)
        else:
            res = {"error": f"Outil Finance inconnu : {name}"}
    except Exception as exc:
        _logger.exception("Erreur outil Finance %s: %s", name, exc)
        res = {"error": f"Échec lors de l'exécution de `{name}` : {exc}"}

    return _sanitize_for_json(res)
