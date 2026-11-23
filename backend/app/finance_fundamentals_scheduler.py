"""Planificateur quotidien des fondamentaux EODHD : budget, priorités, calendrier des résultats.

Chaque passage :
1. Recalcule les priorités de la file depuis les préférences (listes de suivi, indices, bourses complètes).
2. Lit 1×/jour le calendrier des résultats EODHD (1 call) pour repérer les sociétés qui viennent de publier.
3. Charge les titres les plus prioritaires en mode « léger » (fondamentaux 10 + historique 1 si absent, sans
   sentiment / initiés / capitalisation historique / macro), par lots, dans la limite du budget du jour
   (% de la limite journalière du compte) et en s'arrêtant si le quota restant passe sous la marge de sécurité.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import urllib.parse
from typing import Any, Callable

import httpx

from .config import Settings
from .finance_eodhd_usage import endpoint_cost, fetch_eodhd_account_usage, record_eodhd_call
from .finance_fundamentals_queue import (
    SOURCE_KEYS,
    enqueue_symbols,
    mark_reported,
    queue_stats,
    record_failure,
    reset_source_priorities,
    select_due_batch,
)
from .finance_warehouse import (
    _connect,
    _norm_sym,
    get_index_constituents,
    get_snapshot,
    get_stored_eod_bars,
    get_sync_preferences,
    list_warehouse_watchlist_items_for_sync,
    resolve_canonical_symbol,
    save_snapshot,
    upsert_eod_bars,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

_BUDGET_KEY = "__FUNDAMENTALS_BUDGET__"
_BUDGET_TYPE = "fundamentals_budget"
_FALLBACK_DAILY_LIMIT = 100_000
_BATCH_SIZE = 25
_CONCURRENCY = 4
_HISTORY_YEARS = 15
_EXCLUDED_SUFFIXES = (".EUFUND", ".INDX", ".CC", ".FOREX", ".MONEY")

LIGHT_LOAD_CALLS = endpoint_cost("fundamentals") + endpoint_cost("eod")


def _today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _eligible(sym: str) -> bool:
    return bool(sym) and "." in sym and not sym.endswith(_EXCLUDED_SUFFIXES)


# ---------------------------------------------------------------------------
# Budget du jour (persisté dans l'entrepôt)
# ---------------------------------------------------------------------------

def _read_budget_state(db_path) -> dict[str, Any]:
    snap = get_snapshot(db_path, _BUDGET_KEY, _BUDGET_TYPE)
    state = (snap or {}).get("normalized") or {}
    if state.get("day") != _today_utc():
        return {"day": _today_utc(), "spent": 0, "loaded": 0, "calendar_done": False}
    return {"spent": 0, "loaded": 0, "calendar_done": False, **state}


def _write_budget_state(db_path, state: dict[str, Any]) -> None:
    save_snapshot(db_path, _BUDGET_KEY, "local", _BUDGET_TYPE, None, state)


async def compute_budget(settings: Settings) -> dict[str, Any]:
    """Budget du jour : `pct` % de la limite journalière du compte (lue via `/api/user`)."""
    db_path = warehouse_db_path(settings)
    prefs = get_sync_preferences(db_path)
    account = await fetch_eodhd_account_usage(settings, force=True)
    daily_limit = int((account or {}).get("daily_limit") or _FALLBACK_DAILY_LIMIT)
    budget = int(daily_limit * int(prefs.get("fundamentals_budget_pct") or 10) / 100)
    safety_floor = int(daily_limit * int(prefs.get("fundamentals_quota_safety_pct") or 15) / 100)
    state = _read_budget_state(db_path)
    return {
        "daily_limit": daily_limit,
        "daily_limit_known": bool(account and account.get("daily_limit")),
        "budget_calls": budget,
        "spent_today": int(state.get("spent") or 0),
        "remaining_budget": max(0, budget - int(state.get("spent") or 0)),
        "titles_per_day": budget // LIGHT_LOAD_CALLS,
        "safety_floor": safety_floor,
        "account_remaining": (account or {}).get("remaining_today"),
    }


# ---------------------------------------------------------------------------
# Alimentation de la file depuis les préférences
# ---------------------------------------------------------------------------

def _source_symbols(db_path, prefs: dict[str, Any], source: str) -> list[str]:
    if source == "watchlists":
        if not prefs.get("fundamentals_watchlists", True):
            return []
        return [
            _norm_sym(str(it.get("eod_ticker") or it.get("symbol") or ""))
            for it in list_warehouse_watchlist_items_for_sync(db_path)
        ]
    if source == "indices":
        if not prefs.get("fundamentals_indices", True):
            return []
        from .finance_indices import INDEX_DEFINITIONS

        codes = [str(c).upper() for c in (prefs.get("index_codes") or [])]
        if prefs.get("major_indices_constituents", True):
            codes += [str(d["code"]).upper() for d in INDEX_DEFINITIONS if d.get("tier") == "major"]
        out: list[str] = []
        for code in dict.fromkeys(codes):
            rows, _ = get_index_constituents(db_path, code, max_age_seconds=None)
            out.extend(_norm_sym(str(r.get("eod_ticker") or r.get("symbol") or "")) for r in rows)
        return out
    if source == "full_exchanges":
        codes = [_norm_sym(c) for c in (prefs.get("full_data_exchanges") or []) if _norm_sym(c)]
        if not codes:
            return []
        marks = ", ".join("?" for _ in codes)
        with _connect(db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT eod_ticker FROM finance_exchange_symbols
                WHERE exchange_code IN ({marks}) AND LOWER(COALESCE(type, '')) = 'common stock'
                """,
                codes,
            ).fetchall()
        return [_norm_sym(str(r["eod_ticker"] or "")) for r in rows]
    return []


def refresh_queue_from_preferences(settings: Settings) -> dict[str, int]:
    """Recalcule les priorités : position de chaque source dans `fundamentals_priority_order` (1, 2, 3)."""
    db_path = warehouse_db_path(settings)
    prefs = get_sync_preferences(db_path)
    order = [s for s in (prefs.get("fundamentals_priority_order") or SOURCE_KEYS) if s in SOURCE_KEYS]
    labels = {"watchlists": "Liste de suivi", "indices": "Indice suivi", "full_exchanges": "Bourse complète"}
    reset_source_priorities(db_path)
    counts: dict[str, int] = {}
    for rank, source in enumerate(order, start=1):
        syms = [s for s in _source_symbols(db_path, prefs, source) if _eligible(s)]
        counts[source] = enqueue_symbols(db_path, syms, rank, labels[source])
    return counts


# ---------------------------------------------------------------------------
# Calendrier des résultats (1 call / jour)
# ---------------------------------------------------------------------------

async def apply_earnings_calendar(settings: Settings, *, days_back: int = 3) -> int:
    """Repère les sociétés qui viennent de publier (`actual` renseigné) et les marque « à rafraîchir »."""
    if settings.demo_mode or not settings.enabled(settings.eod_historical_data_key):
        return 0
    key = settings.eod_historical_data_key.get_secret_value()
    today = datetime.date.today()
    url = (
        "https://eodhd.com/api/calendar/earnings"
        f"?from={(today - datetime.timedelta(days=days_back)).isoformat()}&to={today.isoformat()}"
        f"&api_token={urllib.parse.quote(key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
        if resp.status_code != 200:
            return 0
        raw = resp.json()
    except Exception as exc:
        _logger.debug("Calendrier des résultats EODHD indisponible: %s", exc)
        return 0
    items = raw.get("earnings") if isinstance(raw, dict) else raw
    reported: dict[str, tuple[str, str | None]] = {}
    for it in items or []:
        if not isinstance(it, dict) or it.get("actual") is None:
            continue
        code = _norm_sym(str(it.get("code") or ""))
        rd = str(it.get("report_date") or "")[:10]
        if code and rd and rd <= today.isoformat():
            reported[code] = (rd, str(it.get("date") or "")[:10] or None)
    return mark_reported(warehouse_db_path(settings), reported)


# ---------------------------------------------------------------------------
# Chargement léger d'un titre
# ---------------------------------------------------------------------------

async def load_fundamentals_light(settings: Settings, symbol: str) -> dict[str, Any]:
    """Fondamentaux (10 calls) + historique des cours s'il manque (1 call), puis recalcul local du Screener."""
    from .finance_dossier import _fetch_eodhd_bars_range
    from .finance_provider import (
        fetch_eodhd_fundamentals_json,
        persist_eodhd_fundamentals_to_warehouse,
        resolve_candidate_eod_tickers,
    )
    from .finance_screener import rebuild_screener_snapshots_from_warehouse

    db_path = warehouse_db_path(settings)
    key = settings.eod_historical_data_key.get_secret_value()
    clean = _norm_sym(symbol)
    canonical = resolve_canonical_symbol(db_path, clean)
    candidates = list(dict.fromkeys([clean, *resolve_candidate_eod_tickers(db_path, canonical)]))[:2]
    calls = 0
    payload: dict[str, Any] | None = None
    used = clean
    for cand in candidates:
        calls += endpoint_cost("fundamentals")
        payload = await fetch_eodhd_fundamentals_json(cand, key)
        if payload:
            used = cand
            break
    if not payload:
        return {"ok": False, "calls": calls, "error": "Fondamentaux indisponibles chez EODHD"}

    # Enregistre les états + met à jour l'échéancier (hook `record_fetch` dans la persistance)
    persist_eodhd_fundamentals_to_warehouse(settings, canonical, payload, eod_ticker=used)
    if not get_stored_eod_bars(db_path, canonical, limit=1):
        calls += endpoint_cost("eod")
        start = (datetime.date.today() - datetime.timedelta(days=365 * _HISTORY_YEARS)).isoformat()
        bars = await _fetch_eodhd_bars_range(used, key, start)
        if bars:
            upsert_eod_bars(db_path, canonical, bars, "eodhd")
    rebuild_screener_snapshots_from_warehouse(db_path, [canonical])
    return {"ok": True, "calls": calls}


# ---------------------------------------------------------------------------
# Passage quotidien sous budget
# ---------------------------------------------------------------------------

async def run_fundamentals_budget(
    settings: Settings,
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Traite la file dans la limite du budget du jour et de la marge de sécurité du quota."""
    db_path = warehouse_db_path(settings)
    summary: dict[str, Any] = {"loaded": 0, "errors": 0, "calls": 0, "stopped_reason": None, "reported_marked": 0}
    if settings.demo_mode or not settings.enabled(settings.eod_historical_data_key):
        summary["stopped_reason"] = "Clé EODHD requise"
        return summary

    summary["queued"] = refresh_queue_from_preferences(settings)
    state = _read_budget_state(db_path)
    if not state.get("calendar_done"):
        summary["reported_marked"] = await apply_earnings_calendar(settings)
        state["calendar_done"] = True
        state["spent"] = int(state.get("spent") or 0) + endpoint_cost("calendar")
        _write_budget_state(db_path, state)

    budget = await compute_budget(settings)
    remaining = int(budget["remaining_budget"])
    target_total = min(remaining // LIGHT_LOAD_CALLS, queue_stats(db_path)["to_process"])
    done = 0
    sem = asyncio.Semaphore(_CONCURRENCY)
    processed: set[str] = set()

    async def _one(sym: str) -> dict[str, Any]:
        async with sem:
            try:
                return await load_fundamentals_light(settings, sym)
            except Exception as exc:
                _logger.debug("Chargement léger des fondamentaux ignoré (%s): %s", sym, exc)
                return {"ok": False, "calls": endpoint_cost("fundamentals"), "error": str(exc)}

    while remaining >= LIGHT_LOAD_CALLS:
        account = await fetch_eodhd_account_usage(settings, force=True)
        acc_left = (account or {}).get("remaining_today")
        if acc_left is not None and acc_left < budget["safety_floor"]:
            summary["stopped_reason"] = "Quota du compte sous la marge de sécurité"
            break
        batch_size = min(_BATCH_SIZE, remaining // LIGHT_LOAD_CALLS)
        batch = [it for it in select_due_batch(db_path, limit=batch_size + len(processed)) if it.symbol not in processed][:batch_size]
        if not batch:
            break
        results = await asyncio.gather(*(_one(it.symbol) for it in batch))
        for it, res in zip(batch, results):
            processed.add(it.symbol)
            calls = int(res.get("calls") or 0)
            remaining -= calls
            summary["calls"] += calls
            done += 1
            if res.get("ok"):
                summary["loaded"] += 1
            else:
                summary["errors"] += 1
                record_failure(db_path, it.symbol, str(res.get("error") or "Échec"))
            if on_progress is not None:
                try:
                    on_progress(done, max(done, target_total), it.symbol)
                except Exception:
                    pass
        state["spent"] = int(state.get("spent") or 0) + sum(int(r.get("calls") or 0) for r in results)
        state["loaded"] = int(state.get("loaded") or 0) + sum(1 for r in results if r.get("ok"))
        _write_budget_state(db_path, state)
    else:
        summary["stopped_reason"] = summary["stopped_reason"] or "Budget du jour atteint"

    summary["stats"] = queue_stats(db_path)
    return summary
