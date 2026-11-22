"""Catalogue des fonds européens EODHD (`EUFUND`), recherche par ISIN / `type=fund` et extraction du profil fonds."""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import re
import time
import urllib.parse
from typing import Any

import httpx

from .config import Settings
from .finance_warehouse import (
    get_exchange_catalog_meta,
    get_sync_preferences,
    get_warehouse_eod_source_breakdown,
    list_warehouse_watchlist_items_for_sync,
    record_sync_run_status,
    replace_exchange_symbols,
    save_sync_preferences,
    search_exchange_symbols,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")
_DAILY_SYNC_LOCK = asyncio.Lock()
_DAILY_SYNC_RUNNING = False
_DAILY_SYNC_PROGRESS: dict[str, Any] = {
    "is_running": False,
    "trigger": None,
    "phase": "idle",
    "current_label": "",
    "completed_steps": 0,
    "total_steps": 0,
    "percent": 0,
    "indices_done": 0,
    "indices_total": 0,
    "fundamentals_done": 0,
    "fundamentals_total": 0,
    "started_at": None,
    "updated_at": None,
}


def _update_sync_progress(**patch: Any) -> None:
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    _DAILY_SYNC_PROGRESS.update(patch)
    _DAILY_SYNC_PROGRESS["updated_at"] = now_iso
    total = int(_DAILY_SYNC_PROGRESS.get("total_steps") or 0)
    done = int(_DAILY_SYNC_PROGRESS.get("completed_steps") or 0)
    if total > 0:
        _DAILY_SYNC_PROGRESS["percent"] = max(0, min(100, round((done / total) * 100)))
    elif not _DAILY_SYNC_PROGRESS.get("is_running"):
        _DAILY_SYNC_PROGRESS["percent"] = 0


def get_daily_sync_status() -> dict[str, Any]:
    """Retourne instantanément l'état en direct de la synchronisation automatique (0 I/O)."""
    return dict(_DAILY_SYNC_PROGRESS)


def _is_fundamentals_sync_due(
    last_fundamentals_run_at: str | None,
    interval_days: int,
    *,
    force: bool = False,
) -> tuple[bool, str | None]:
    """Vérifie si l'enrichissement fondamental périodique (par défaut 1×/semaine) est dû."""
    if force or not last_fundamentals_run_at:
        return True, None
    try:
        raw = str(last_fundamentals_run_at).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        last_dt = datetime.datetime.fromisoformat(raw)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
        due_dt = last_dt + datetime.timedelta(days=max(1, int(interval_days or 7)))
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        return now_dt >= due_dt, due_dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    except ValueError:
        return True, None

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_EXCHANGE_CODE_RE = re.compile(r"^[A-Z0-9_-]{1,12}$")
_DEFAULT_EXCHANGE_CODES: tuple[str, ...] = ("EUFUND", "PA", "US", "XETRA", "LSE", "CC")

SUPPORTED_EXCHANGE_CATALOGS: tuple[dict[str, str], ...] = (
    {"code": "EUFUND", "label": "Fonds EU", "description": "Fonds européens OPCVM / SICAV"},
    {"code": "PA", "label": "Paris (PA)", "description": "Euronext Paris (actions & ETF)"},
    {"code": "US", "label": "US", "description": "NYSE / NASDAQ / ARCA (actions & ETF)"},
    {"code": "XETRA", "label": "Xetra", "description": "Allemagne (Deutsche Börse Xetra)"},
    {"code": "LSE", "label": "Londres (LSE)", "description": "London Stock Exchange"},
    {"code": "CC", "label": "Crypto (CC)", "description": "Cryptomonnaies EODHD"},
)


def _exchange_ttl_seconds(settings: Settings) -> int:
    hours = int(getattr(settings, "finance_exchange_catalog_ttl_hours", 24) or 24)
    return max(3600, hours * 3600)


def parse_auto_sync_exchange_codes(settings: Settings) -> list[str]:
    raw = str(getattr(settings, "finance_exchange_auto_sync_codes", "") or "")
    codes: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        code = part.strip().upper()
        if not code or code == "ALL" or not _EXCHANGE_CODE_RE.fullmatch(code) or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes


def looks_like_isin(value: str) -> bool:
    """Indique si la chaîne correspond au format standard d'un code ISIN (12 caractères)."""
    return bool(_ISIN_RE.fullmatch((value or "").strip().upper()))


def is_fund_instrument(eod_fund: dict[str, Any] | None, symbol: str = "", exchange: str = "") -> bool:
    """Détecte si un actif correspond à un fonds / OPCVM (notamment `EUFUND`)."""
    sym_u = (symbol or "").strip().upper()
    exch_u = (exchange or "").strip().upper()
    if sym_u.endswith(".EUFUND") or exch_u == "EUFUND":
        return True
    if not isinstance(eod_fund, dict):
        return False
    gen = eod_fund.get("General") or {}
    g_exch = str(gen.get("Exchange") or "").strip().upper()
    g_type = str(gen.get("Type") or "").strip().upper()
    if g_exch == "EUFUND" or "FUND" in g_type:
        return True
    return bool(eod_fund.get("Mutual_Fund"))


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, dict):
        val = val.get("raw")
    if isinstance(val, (int, float)):
        f = float(val)
        return f if math.isfinite(f) else None
    if isinstance(val, str):
        cleaned = val.strip().rstrip("%").replace(",", ".")
        if not cleaned or cleaned.upper() in ("NA", "N/A", "NONE", "NULL", "-"):
            return None
        try:
            f = float(cleaned)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def _pct(val: Any) -> float | None:
    n = _num(val)
    if n is None:
        return None
    # EODHD renvoie parfois des pourcentages en fraction (0.015) ou déjà en points (1.5)
    return round(n * 100.0, 2) if 0 < abs(n) < 0.35 else round(n, 2)


def _iso_from_ts(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_exchange_rows(raw: list[Any], exchange_code: str = "EUFUND") -> list[dict[str, Any]]:
    exch = (exchange_code or "EUFUND").strip().upper()
    default_type = "Fund" if exch == "EUFUND" else ("Currency" if exch == "CC" else "Common Stock")
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("Code") or "").strip().upper()
        if not code:
            continue
        bare_code = code.split(".", 1)[0]
        eod_ticker = code if "." in code else f"{code}.{exch}"
        raw_isin = str(item.get("Isin") or item.get("ISIN") or "").strip().upper()
        isin = raw_isin if looks_like_isin(raw_isin) else (bare_code if looks_like_isin(bare_code) else "")
        rows.append(
            {
                "symbol": bare_code,
                "eod_ticker": eod_ticker,
                "name": str(item.get("Name") or bare_code).strip(),
                "isin": isin or None,
                "country": str(item.get("Country") or "").strip(),
                "currency": str(item.get("Currency") or "").strip().upper(),
                "type": str(item.get("Type") or default_type).strip(),
            }
        )
    return rows


def _normalize_eufund_rows(raw: list[Any]) -> list[dict[str, Any]]:
    return _normalize_exchange_rows(raw, "EUFUND")


async def sync_exchange_catalog_if_needed(
    settings: Settings,
    exchange_code: str = "EUFUND",
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    """Synchronise `/api/exchange-symbol-list/{EXCHANGE}` dans l'entrepôt SQLite (TTL quotidien 24h par défaut)."""
    exch = (exchange_code or "EUFUND").strip().upper()
    if not _EXCHANGE_CODE_RE.fullmatch(exch) or exch == "ALL":
        raise ValueError(f"Code marché EODHD invalide : {exchange_code!r}")

    db_path = warehouse_db_path(settings)
    meta = get_exchange_catalog_meta(db_path, exch)
    ttl_sec = _exchange_ttl_seconds(settings)
    is_fresh = bool(
        meta["total"] > 0
        and meta["fetched_at"] is not None
        and (time.time() - float(meta["fetched_at"])) <= ttl_sec
    )
    if not refresh and is_fresh:
        return meta, "Entrepôt SQLite"

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    if not eod_key or settings.demo_mode:
        if meta["total"] > 0:
            return meta, "Entrepôt SQLite"
        return meta, ("Mode démo" if settings.demo_mode else "Clé EODHD requise")

    url = (
        f"https://eodhd.com/api/exchange-symbol-list/{urllib.parse.quote(exch)}"
        f"?api_token={urllib.parse.quote(eod_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=120.0,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                raw = resp.json()
                if isinstance(raw, list) and raw:
                    rows = _normalize_exchange_rows(raw, exch)
                    if rows:
                        replace_exchange_symbols(db_path, exch, rows)
                        updated_meta = get_exchange_catalog_meta(db_path, exch)
                        api_label = "EODHD EUFUND API" if exch == "EUFUND" else f"EODHD {exch} API"
                        return updated_meta, api_label
            else:
                _logger.warning("EODHD %s catalog HTTP %s", exch, resp.status_code)
    except Exception as exc:
        _logger.warning("Échec synchronisation catalogue %s EODHD: %s", exch, exc)

    if meta["total"] > 0:
        return meta, "Entrepôt SQLite (secours)"
    return meta, "Indisponible"


async def sync_eufund_catalog_if_needed(
    settings: Settings,
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    """Synchronise `/api/exchange-symbol-list/EUFUND` dans l'entrepôt SQLite si absent ou périmé."""
    return await sync_exchange_catalog_if_needed(settings, "EUFUND", refresh=refresh)


async def sync_configured_exchange_catalogs(
    settings: Settings,
    *,
    refresh: bool = False,
    codes: list[str] | None = None,
) -> dict[str, Any]:
    """Synchronise séquentiellement les places boursières demandées (`EUFUND, PA, US, XETRA, LSE, CC`)."""
    raw_codes = codes if codes is not None else (parse_auto_sync_exchange_codes(settings) or list(_DEFAULT_EXCHANGE_CODES))
    target_codes = [c.strip().upper() for c in raw_codes if c.strip()]
    results: dict[str, dict[str, Any]] = {}
    fetched_count = 0
    for code in target_codes:
        if not _EXCHANGE_CODE_RE.fullmatch(code) or code == "ALL":
            continue
        meta, source = await sync_exchange_catalog_if_needed(settings, code, refresh=refresh)
        if source.startswith("EODHD"):
            fetched_count += 1
        results[code] = {
            "total": meta["total"],
            "source": source,
            "synced_at": _iso_from_ts(meta["fetched_at"]),
        }
    return {
        "codes": list(results.keys()),
        "fetched_exchanges": fetched_count,
        "exchanges": results,
    }


async def get_daily_sync_state(settings: Settings) -> dict[str, Any]:
    """Retourne les préférences de synchro quotidienne + la liste des indices et marchés disponibles."""
    from .finance_indices import list_principal_indices

    db_path = warehouse_db_path(settings)
    prefs = get_sync_preferences(db_path)
    all_meta = get_exchange_catalog_meta(db_path, "ALL")
    indices_payload = await list_principal_indices(settings, include_quotes=False, tier="all")
    available_indices = [
        {
            "code": idx["code"],
            "name": idx.get("name") or idx["code"],
            "flag": idx.get("flag") or "",
            "tier": idx.get("tier") or "major",
            "region": idx.get("region") or "",
            "constituents_count": int(idx.get("constituents_count") or 0),
        }
        for idx in (indices_payload.get("indices") or [])
    ]
    src_breakdown = get_warehouse_eod_source_breakdown(db_path)
    return {
        "preferences": prefs,
        "is_running": _DAILY_SYNC_RUNNING,
        "progress": get_daily_sync_status(),
        "warehouse_sources": {
            "eodhd_fundamentals_count": src_breakdown["eodhd_fundamentals_count"],
            "yahoo_only_fundamentals_count": src_breakdown["yahoo_only_fundamentals_count"],
            "eodhd_bars_symbols_count": src_breakdown["eodhd_bars_symbols_count"],
            "yahoo_only_bars_symbols_count": src_breakdown["yahoo_only_bars_symbols_count"],
            "total_bars_symbols": src_breakdown["total_bars_symbols"],
            "eodhd_configured": bool(settings.enabled(settings.eod_historical_data_key) and not settings.demo_mode),
        },
        "available_indices": available_indices,
        "available_exchanges": _build_supported_exchanges_status(all_meta),
    }


async def update_daily_sync_preferences(
    settings: Settings,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Enregistre les préférences de synchro quotidienne puis retourne l'état complet."""
    db_path = warehouse_db_path(settings)
    save_sync_preferences(db_path, config)
    return await get_daily_sync_state(settings)


async def run_daily_sync_now(
    settings: Settings,
    *,
    refresh: bool = False,
    respect_enabled: bool = False,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Exécute la synchronisation (cours quotidiens + fondamentaux 1×/semaine) avec suivi d'avancement live."""
    global _DAILY_SYNC_RUNNING
    from types import SimpleNamespace
    from .finance_indices import (
        INDEX_DEFINITIONS,
        get_index_performances,
        list_eodhd_indx_catalog,
        list_principal_indices,
    )
    from .finance_screener import hydrate_screener_universe
    from .finance_watchlist import fetch_watchlist_quotes

    db_path = warehouse_db_path(settings)
    prefs = get_sync_preferences(db_path)
    if respect_enabled and not prefs.get("enabled", True):
        return {
            **(await get_daily_sync_state(settings)),
            "summary": {"skipped": True, "reason": "disabled"},
        }

    if _DAILY_SYNC_LOCK.locked():
        return {
            **(await get_daily_sync_state(settings)),
            "summary": {"skipped": True, "reason": "already_running"},
        }

    # Préparer la liste des indices cibles pour le suivi d'avancement précis
    target_index_codes: list[str] = []
    seen_idx: set[str] = set()
    if prefs.get("major_indices_constituents", True):
        for defn in INDEX_DEFINITIONS:
            if defn.get("tier") == "major":
                c = str(defn["code"]).upper()
                if c not in seen_idx:
                    seen_idx.add(c)
                    target_index_codes.append(c)
    for code in prefs.get("index_codes") or []:
        c = str(code or "").strip().upper()
        if c and c not in seen_idx:
            seen_idx.add(c)
            target_index_codes.append(c)

    exch_codes: list[str] = []
    seen_exch: set[str] = set()
    for code in [*(prefs.get("exchanges") or []), *parse_auto_sync_exchange_codes(settings)]:
        clean_c = str(code or "").strip().upper()
        if clean_c and clean_c != "ALL" and _EXCHANGE_CODE_RE.fullmatch(clean_c) and clean_c not in seen_exch:
            seen_exch.add(clean_c)
            exch_codes.append(clean_c)

    fund_interval_days = int(prefs.get("screener_fundamentals_interval_days") or 7)
    fund_due, fund_next_due_at = _is_fundamentals_sync_due(
        prefs.get("last_fundamentals_run_at"),
        fund_interval_days,
        force=refresh,
    )
    will_run_fundamentals = bool(
        prefs.get("screener_fundamentals", True)
        and target_index_codes
        and not settings.demo_mode
        and fund_due
    )

    total_steps = (
        (1 if prefs.get("principal_indices") else 0)
        + (1 if prefs.get("indx_catalog") else 0)
        + len(target_index_codes)
        + (1 if will_run_fundamentals else 0)
        + (1 if prefs.get("watchlists") else 0)
        + (1 if exch_codes else 0)
    )
    total_steps = max(1, total_steps)
    completed_steps = 0

    async with _DAILY_SYNC_LOCK:
        _DAILY_SYNC_RUNNING = True
        started_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        _update_sync_progress(
            is_running=True,
            trigger=trigger,
            phase="starting",
            current_label="Démarrage de la synchronisation…",
            completed_steps=0,
            total_steps=total_steps,
            indices_done=0,
            indices_total=len(target_index_codes),
            fundamentals_done=0,
            fundamentals_total=0,
            started_at=started_iso,
        )
        fundamentals_ran = False
        try:
            summary: dict[str, Any] = {
                "skipped": False,
                "principal_indices_count": 0,
                "indx_catalog_total": 0,
                "indices": {},
                "screener_fundamentals": {
                    "skipped": False,
                    "reason": None,
                    "next_due_at": fund_next_due_at,
                    "enriched": 0,
                    "cached": 0,
                    "errors": 0,
                },
                "watchlist_items_count": 0,
                "exchanges": {},
                "errors": [],
            }

            if prefs.get("principal_indices"):
                _update_sync_progress(
                    phase="principal_indices",
                    current_label="Cotations des principaux indices…",
                    completed_steps=completed_steps,
                )
                try:
                    idx_res = await list_principal_indices(settings, include_quotes=True, tier="major")
                    summary["principal_indices_count"] = len(idx_res.get("indices") or [])
                except Exception as exc:
                    summary["errors"].append(f"indices: {exc}")
                completed_steps += 1
                _update_sync_progress(completed_steps=completed_steps)

            if prefs.get("indx_catalog"):
                _update_sync_progress(
                    phase="indx_catalog",
                    current_label="Catalogue des indices EODHD (.INDX)…",
                    completed_steps=completed_steps,
                )
                try:
                    cat_res = await list_eodhd_indx_catalog(settings, limit=50, refresh=refresh)
                    summary["indx_catalog_total"] = int(cat_res.get("total") or 0)
                except Exception as exc:
                    summary["errors"].append(f"indx_catalog: {exc}")
                completed_steps += 1
                _update_sync_progress(completed_steps=completed_steps)

            synced_symbols: list[str] = []
            seen_syms: set[str] = set()
            for idx_pos, code in enumerate(target_index_codes, start=1):
                _update_sync_progress(
                    phase="index_constituents",
                    current_label=f"Indice {code} ({idx_pos}/{len(target_index_codes)})…",
                    indices_done=idx_pos - 1,
                    completed_steps=completed_steps,
                )
                try:
                    perf_res = await get_index_performances(settings, code, refresh=refresh)
                    if perf_res:
                        s_perf = perf_res.get("summary") or {}
                        summary["indices"][code] = {
                            "loaded_count": int(s_perf.get("loaded_count") or 0),
                            "from_cache_count": int(s_perf.get("from_cache_count") or 0),
                            "fetched_count": int(s_perf.get("fetched_count") or 0),
                        }
                        for item in perf_res.get("items") or []:
                            sym = str(item.get("eod_ticker") or item.get("symbol") or "").strip().upper()
                            if sym and sym not in seen_syms:
                                seen_syms.add(sym)
                                synced_symbols.append(sym)
                except Exception as exc:
                    summary["errors"].append(f"index:{code}: {exc}")
                completed_steps += 1
                _update_sync_progress(indices_done=idx_pos, completed_steps=completed_steps)

            # Enrichissement fondamental périodique (par défaut 1 fois / semaine, pas tous les jours)
            if prefs.get("screener_fundamentals", True) and synced_symbols and not settings.demo_mode:
                if not fund_due:
                    summary["screener_fundamentals"] = {
                        "skipped": True,
                        "reason": "weekly_cooldown",
                        "last_run_at": prefs.get("last_fundamentals_run_at"),
                        "next_due_at": fund_next_due_at,
                        "enriched": 0,
                        "cached": 0,
                        "errors": 0,
                    }
                else:
                    daily_cap = max(5, min(200, int(prefs.get("screener_fundamentals_daily_cap") or 40)))
                    _update_sync_progress(
                        phase="screener_fundamentals",
                        current_label="Fondamentaux hebdomadaires (Screener)…",
                        fundamentals_done=0,
                        fundamentals_total=min(daily_cap, len(synced_symbols)),
                        completed_steps=completed_steps,
                    )

                    def _on_fund_progress(done_n: int, tot_n: int, sym: str) -> None:
                        _update_sync_progress(
                            phase="screener_fundamentals",
                            current_label=f"Fondamentaux {sym} ({done_n}/{tot_n})…",
                            fundamentals_done=done_n,
                            fundamentals_total=tot_n,
                        )

                    try:
                        hyd_res = await hydrate_screener_universe(
                            settings,
                            universe_type="watchlist",
                            watchlist_symbols=synced_symbols,
                            include_fundamentals=True,
                            max_fundamentals=daily_cap,
                            refresh_eod=False,
                            on_progress=_on_fund_progress,
                        )
                        fundamentals_ran = True
                        summary["screener_fundamentals"] = {
                            "skipped": False,
                            "reason": None,
                            "enriched": int(hyd_res.get("fundamentals_enriched") or 0),
                            "cached": int(hyd_res.get("fundamentals_cached") or 0),
                            "errors": int(hyd_res.get("fundamentals_errors") or 0),
                        }
                    except Exception as exc:
                        summary["errors"].append(f"screener_fundamentals: {exc}")
                    completed_steps += 1
                    _update_sync_progress(completed_steps=completed_steps)

            if prefs.get("watchlists"):
                _update_sync_progress(
                    phase="watchlists",
                    current_label="Mise à jour des listes de suivi…",
                    completed_steps=completed_steps,
                )
                try:
                    raw_items = list_warehouse_watchlist_items_for_sync(db_path)
                    if raw_items:
                        wl_objs = [SimpleNamespace(**it) for it in raw_items]
                        enriched = await fetch_watchlist_quotes(settings, wl_objs, refresh=refresh)
                        summary["watchlist_items_count"] = len(enriched)
                except Exception as exc:
                    summary["errors"].append(f"watchlists: {exc}")
                completed_steps += 1
                _update_sync_progress(completed_steps=completed_steps)

            if exch_codes:
                _update_sync_progress(
                    phase="exchanges",
                    current_label=f"Catalogues marchés ({', '.join(exch_codes)})…",
                    completed_steps=completed_steps,
                )
                exch_res = await sync_configured_exchange_catalogs(settings, refresh=refresh, codes=exch_codes)
                summary["exchanges"] = exch_res.get("exchanges") or {}
                completed_steps += 1
                _update_sync_progress(completed_steps=completed_steps)

            record_sync_run_status(db_path, summary, fundamentals_ran=fundamentals_ran)
        finally:
            _DAILY_SYNC_RUNNING = False
            _update_sync_progress(
                is_running=False,
                phase="idle",
                current_label="",
                completed_steps=total_steps,
                total_steps=total_steps,
                percent=100,
            )

    state = await get_daily_sync_state(settings)
    return {**state, "summary": summary}


async def upgrade_warehouse_to_eodhd(
    settings: Settings,
    *,
    include_bars: bool = True,
    include_fundamentals: bool = True,
    force_all_fundamentals: bool = False,
    max_fundamentals: int = 250,
    max_bars: int = 600,
) -> dict[str, Any]:
    """Met à jour en lot les cours EOD et états financiers de l'entrepôt local depuis EODHD (avec suivi live)."""
    global _DAILY_SYNC_RUNNING
    from .finance import DEFAULT_USER_AGENT, _to_adjusted_ohlc_bar, fetch_eodhd_historical_eod
    from .finance_dossier import get_financial_dossier
    from .finance_provider import resolve_candidate_eod_tickers
    from .finance_screener import rebuild_screener_snapshots_from_warehouse
    from .finance_warehouse import upsert_eod_bars

    db_path = warehouse_db_path(settings)
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    if settings.demo_mode or not eod_key:
        state = await get_daily_sync_state(settings)
        return {
            **state,
            "summary": {
                "skipped": True,
                "reason": "eodhd_key_missing" if not eod_key else "demo_mode",
                "bars_upgraded": 0,
                "bars_errors": 0,
                "fundamentals_upgraded": 0,
                "fundamentals_errors": 0,
            },
        }

    if _DAILY_SYNC_LOCK.locked():
        state = await get_daily_sync_state(settings)
        return {**state, "summary": {"skipped": True, "reason": "already_running"}}

    breakdown = get_warehouse_eod_source_breakdown(db_path)
    bars_targets = (
        list(breakdown["yahoo_only_bars_symbols"])[: max(1, min(1500, int(max_bars or 600)))]
        if include_bars
        else []
    )
    if include_fundamentals:
        raw_fund_targets = (
            list(breakdown["all_fundamentals_symbols"])
            if force_all_fundamentals
            else list(breakdown["yahoo_only_fundamentals_symbols"])
        )
        # Prioriser toujours les titres Yahoo-only en tête de file
        yahoo_first = set(breakdown["yahoo_only_fundamentals_symbols"])
        raw_fund_targets.sort(key=lambda s: (0 if s in yahoo_first else 1, s))
        fund_targets = raw_fund_targets[: max(1, min(500, int(max_fundamentals or 250)))]
    else:
        fund_targets = []

    total_steps = max(1, len(bars_targets) + len(fund_targets) + 1)
    completed_steps = 0
    bars_upgraded = 0
    bars_errors = 0
    fundamentals_upgraded = 0
    fundamentals_errors = 0

    async with _DAILY_SYNC_LOCK:
        _DAILY_SYNC_RUNNING = True
        started_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        _update_sync_progress(
            is_running=True,
            trigger="manual",
            phase="eodhd_upgrade",
            current_label="Migration de l'entrepôt vers EODHD…",
            completed_steps=0,
            total_steps=total_steps,
            indices_done=0,
            indices_total=len(bars_targets),
            fundamentals_done=0,
            fundamentals_total=len(fund_targets),
            started_at=started_iso,
        )
        try:
            # 1. Migrer les barres EOD qui provenaient de Yahoo Finance vers EODHD
            if bars_targets:
                sem_bars = asyncio.Semaphore(8)
                bars_done = 0

                async with httpx.AsyncClient(
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                    follow_redirects=True,
                    timeout=15.0,
                ) as client:

                    async def _upgrade_bars_one(sym: str) -> bool:
                        nonlocal bars_done, completed_steps
                        async with sem_bars:
                            ok = False
                            try:
                                for cand in resolve_candidate_eod_tickers(db_path, sym)[:3]:
                                    raw_eod = await fetch_eodhd_historical_eod(client, cand, eod_key, limit=2600)
                                    if not raw_eod:
                                        continue
                                    parsed: list[dict[str, Any]] = []
                                    for b in reversed(raw_eod):
                                        d_str = str(b.get("date") or "")[:10]
                                        adj_bar = _to_adjusted_ohlc_bar(
                                            d_str,
                                            b.get("open"),
                                            b.get("high"),
                                            b.get("low"),
                                            b.get("close"),
                                            b.get("adjusted_close"),
                                            b.get("volume"),
                                        )
                                        if adj_bar:
                                            parsed.append(adj_bar)
                                    if parsed:
                                        upsert_eod_bars(db_path, sym, parsed, "eodhd", requested_limit=len(parsed))
                                        ok = True
                                        break
                            except Exception as exc:
                                _logger.debug("Migration cours EODHD ignorée (%s): %s", sym, exc)
                            finally:
                                bars_done += 1
                                completed_steps += 1
                                _update_sync_progress(
                                    phase="eodhd_upgrade_bars",
                                    current_label=f"Cours EODHD : {sym} ({bars_done}/{len(bars_targets)})…",
                                    indices_done=bars_done,
                                    completed_steps=completed_steps,
                                )
                            return ok

                    b_res = await asyncio.gather(*(_upgrade_bars_one(s) for s in bars_targets))
                    bars_upgraded = sum(1 for ok in b_res if ok)
                    bars_errors = sum(1 for ok in b_res if not ok)

            # 2. Mettre à jour les états financiers / dossiers fondamentaux depuis EODHD
            if fund_targets:
                sem_fund = asyncio.Semaphore(4)
                fund_done = 0

                async def _upgrade_fund_one(sym: str) -> bool:
                    nonlocal fund_done, completed_steps
                    async with sem_fund:
                        ok = False
                        try:
                            dossier = await get_financial_dossier(settings, sym, refresh=True)
                            ok = str((dossier or {}).get("source_provider") or "").lower().startswith("eodhd")
                        except Exception as exc:
                            _logger.debug("Migration fondamentaux EODHD ignorée (%s): %s", sym, exc)
                        finally:
                            fund_done += 1
                            completed_steps += 1
                            _update_sync_progress(
                                phase="eodhd_upgrade_fundamentals",
                                current_label=f"États financiers EODHD : {sym} ({fund_done}/{len(fund_targets)})…",
                                fundamentals_done=fund_done,
                                completed_steps=completed_steps,
                            )
                        return ok

                f_res = await asyncio.gather(*(_upgrade_fund_one(s) for s in fund_targets))
                fundamentals_upgraded = sum(1 for ok in f_res if ok)
                fundamentals_errors = sum(1 for ok in f_res if not ok)

            # 3. Reconstruire l'index matérialisé Screener (4 unités + IsoPressure + fondamentaux EODHD)
            _update_sync_progress(
                phase="eodhd_upgrade_rebuild",
                current_label="Réindexation du Screener avec les données EODHD…",
                completed_steps=completed_steps,
            )
            touched = sorted(set(bars_targets) | set(fund_targets))
            rebuild_screener_snapshots_from_warehouse(db_path, touched or None)
            completed_steps = total_steps
        finally:
            _DAILY_SYNC_RUNNING = False
            _update_sync_progress(
                is_running=False,
                phase="idle",
                current_label="",
                completed_steps=total_steps,
                total_steps=total_steps,
                percent=100,
            )

    state = await get_daily_sync_state(settings)
    return {
        **state,
        "summary": {
            "skipped": False,
            "bars_targeted": len(bars_targets),
            "bars_upgraded": bars_upgraded,
            "bars_errors": bars_errors,
            "fundamentals_targeted": len(fund_targets),
            "fundamentals_upgraded": fundamentals_upgraded,
            "fundamentals_errors": fundamentals_errors,
            "force_all_fundamentals": force_all_fundamentals,
        },
    }


async def run_daily_exchange_catalog_sync_loop(settings: Settings) -> None:
    """Tâche de fond quotidienne récupérant automatiquement les principaux indices, leur contenu et les sélections."""
    try:
        await asyncio.sleep(15.0)
        while True:
            try:
                if not settings.demo_mode and getattr(settings, "finance_exchange_auto_sync_enabled", True):
                    db_path = warehouse_db_path(settings)
                    prefs = get_sync_preferences(db_path)
                    today_prefix = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                    last_run = str(prefs.get("last_run_at") or "")
                    updated = str(prefs.get("updated_at") or "")
                    already_ran_today = last_run.startswith(today_prefix) and (not updated or updated <= last_run)
                    if prefs.get("enabled", True) and not already_ran_today:
                        res = await run_daily_sync_now(settings, refresh=False, respect_enabled=True, trigger="auto")
                        s_info = res.get("summary") or {}
                        if not s_info.get("skipped"):
                            sf = s_info.get("screener_fundamentals") or {}
                            _logger.info(
                                "Synchro quotidienne terminée (indices=%s, compositions=%d, fondamentaux=%d, watchlist=%d, marchés=%d).",
                                s_info.get("principal_indices_count", 0),
                                len(s_info.get("indices") or {}),
                                sf.get("enriched", 0),
                                s_info.get("watchlist_items_count", 0),
                                len(s_info.get("exchanges") or {}),
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _logger.warning("Erreur boucle synchro quotidienne finance: %s", exc)
            sleep_sec = min(_exchange_ttl_seconds(settings), 4 * 3600)
            await asyncio.sleep(sleep_sec)
    except asyncio.CancelledError:
        return


def _build_supported_exchanges_status(meta: dict[str, Any]) -> list[dict[str, Any]]:
    exch_map = meta.get("exchanges") or {}
    out: list[dict[str, Any]] = []
    known_codes: set[str] = set()
    for entry in SUPPORTED_EXCHANGE_CATALOGS:
        c = entry["code"]
        known_codes.add(c)
        info = exch_map.get(c) or {}
        out.append(
            {
                **entry,
                "total": int(info.get("total") or 0),
                "synced_at": _iso_from_ts(info.get("fetched_at")),
            }
        )
    for c, info in sorted(exch_map.items()):
        if c not in known_codes:
            out.append(
                {
                    "code": c,
                    "label": c,
                    "description": f"Marché {c}",
                    "total": int(info.get("total") or 0),
                    "synced_at": _iso_from_ts(info.get("fetched_at")),
                }
            )
    return out


async def list_exchange_catalog(
    settings: Settings,
    *,
    exchange: str = "EUFUND",
    query: str = "",
    currency: str = "",
    country: str = "",
    instrument_type: str = "",
    fund_family: str = "",
    limit: int = 60,
    offset: int = 0,
    refresh: bool = False,
) -> dict[str, Any]:
    """Liste et filtre un catalogue EODHD (`EUFUND`, `PA`, `US`, `XETRA`, `LSE`, `CC` ou `ALL`) depuis SQLite/FTS5."""
    exch = (exchange or "EUFUND").strip().upper()
    db_path = warehouse_db_path(settings)
    if exch == "ALL":
        if refresh:
            sync_summary = await sync_configured_exchange_catalogs(settings, refresh=True)
            source = (
                "EODHD Multi-Marchés API"
                if sync_summary.get("fetched_exchanges", 0) > 0
                else "Entrepôt SQLite"
            )
        else:
            source = "Entrepôt SQLite"
        meta = get_exchange_catalog_meta(db_path, "ALL")
    else:
        _, source = await sync_exchange_catalog_if_needed(settings, exch, refresh=refresh)
        # Charger les totaux par marché pour afficher les compteurs dans les onglets UI
        meta = get_exchange_catalog_meta(db_path, exch)
        all_meta = get_exchange_catalog_meta(db_path, "ALL")
        meta = {**meta, "exchanges": all_meta.get("exchanges") or {}}

    search_res = search_exchange_symbols(
        db_path,
        exch,
        query=query,
        currency=currency,
        country=country,
        instrument_type=instrument_type,
        fund_family=fund_family,
        limit=limit,
        offset=offset,
    )
    return {
        "exchange": exch,
        "supported_exchanges": _build_supported_exchanges_status(meta),
        "total": meta["total"],
        "matched": search_res["matched"],
        "offset": max(0, int(offset or 0)),
        "limit": max(1, min(300, int(limit or 60))),
        "source": source,
        "synced_at": _iso_from_ts(meta["fetched_at"]),
        "currencies": meta["currencies"],
        "countries": meta["countries"],
        "types": meta.get("types") or [],
        "fund_families": meta.get("fund_families") or [],
        "items": search_res["items"],
    }


async def list_eufund_catalog(
    settings: Settings,
    *,
    query: str = "",
    currency: str = "",
    country: str = "",
    instrument_type: str = "",
    fund_family: str = "",
    limit: int = 60,
    offset: int = 0,
    refresh: bool = False,
) -> dict[str, Any]:
    """Liste et filtre les fonds européens EODHD (`EUFUND`) depuis l'entrepôt SQLite."""
    return await list_exchange_catalog(
        settings,
        exchange="EUFUND",
        query=query,
        currency=currency,
        country=country,
        instrument_type=instrument_type,
        fund_family=fund_family,
        limit=limit,
        offset=offset,
        refresh=refresh,
    )


async def search_eodhd_funds_live(
    settings: Settings,
    query: str,
    limit: int = 25,
) -> dict[str, Any]:
    """Recherche directe de fonds par nom ou ISIN (catalogue local `EUFUND` + `/api/search/?type=fund`)."""
    clean_q = (query or "").strip()
    if not clean_q:
        return {"query": "", "source": "aucune", "items": []}

    db_path = warehouse_db_path(settings)
    local_res = search_exchange_symbols(db_path, "EUFUND", query=clean_q, limit=limit, offset=0)
    merged: list[dict[str, Any]] = list(local_res["items"])
    seen = {str(it.get("eod_ticker") or "").upper() for it in merged}

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    source = "Entrepôt SQLite" if merged else "Aucun résultat"

    if eod_key and not settings.demo_mode and len(clean_q) >= 2:
        url = (
            f"https://eodhd.com/api/search/{urllib.parse.quote(clean_q)}"
            f"?api_token={urllib.parse.quote(eod_key)}&type=fund&limit={max(10, min(50, limit * 2))}&fmt=json"
        )
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=12.0,
            ) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    raw = resp.json()
                    if isinstance(raw, list):
                        live_count = 0
                        for item in raw:
                            if not isinstance(item, dict):
                                continue
                            code = str(item.get("Code") or "").strip().upper()
                            exch = str(item.get("Exchange") or "").strip().upper()
                            if not code:
                                continue
                            eod_ticker = f"{code}.{exch}" if exch and "." not in code else code
                            if eod_ticker in seen:
                                continue
                            seen.add(eod_ticker)
                            raw_isin = str(item.get("ISIN") or item.get("Isin") or "").strip().upper()
                            bare = code.split(".", 1)[0]
                            isin = raw_isin if looks_like_isin(raw_isin) else (bare if looks_like_isin(bare) else None)
                            merged.append(
                                {
                                    "symbol": bare,
                                    "eod_ticker": eod_ticker,
                                    "name": str(item.get("Name") or eod_ticker).strip(),
                                    "isin": isin,
                                    "country": str(item.get("Country") or "").strip(),
                                    "currency": str(item.get("Currency") or "").strip().upper(),
                                    "type": str(item.get("Type") or "Fund").strip(),
                                    "exchange": exch or "EUFUND",
                                    "previous_close": _num(item.get("previousClose")),
                                    "cached_in_warehouse": False,
                                }
                            )
                            live_count += 1
                        if live_count > 0:
                            source = "EODHD Search (type=fund)" if not local_res["items"] else "Entrepôt + EODHD Search"
        except Exception as exc:
            _logger.debug("Erreur recherche live EODHD type=fund (%s): %s", clean_q, exc)

    # Prioriser EUFUND et correspondances ISIN exactes
    q_up = clean_q.upper()
    merged.sort(
        key=lambda it: (
            0 if str(it.get("isin") or "").upper() == q_up or str(it.get("symbol") or "").upper() == q_up else 1,
            0 if str(it.get("exchange") or "").upper() == "EUFUND" else 1,
            str(it.get("name") or "").lower(),
        )
    )
    return {
        "query": clean_q,
        "source": source,
        "items": merged[:limit],
    }


def _extract_weighted_entries(node: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    """Normalise un bloc EODHD de pondérations (`Top_Holdings`, `Asset_Allocation`, `Sector_Weights`, `World_Regions`)."""
    out: list[dict[str, Any]] = []
    if isinstance(node, dict):
        for key, val in node.items():
            if isinstance(val, dict):
                label = str(val.get("Name") or val.get("name") or val.get("Code") or key).strip()
                weight = _num(
                    val.get("Assets_%")
                    or val.get("Equity_%")
                    or val.get("Weight")
                    or val.get("weight")
                    or val.get("Net_%")
                    or val.get("Long_%")
                )
                code = str(val.get("Code") or key).strip()
                sector = str(val.get("Sector") or "").strip()
                country = str(val.get("Country") or "").strip()
                if weight is not None or label:
                    out.append(
                        {
                            "name": label,
                            "code": code if code != label else "",
                            "weight_pct": round(weight, 2) if weight is not None else None,
                            "sector": sector,
                            "country": country,
                        }
                    )
            else:
                weight = _num(val)
                if weight is not None:
                    out.append({"name": str(key).replace("_", " ").strip(), "code": "", "weight_pct": round(weight, 2)})
    elif isinstance(node, list):
        for val in node:
            if not isinstance(val, dict):
                continue
            label = str(val.get("Name") or val.get("name") or val.get("Code") or "").strip()
            weight = _num(val.get("Assets_%") or val.get("Weight") or val.get("weight"))
            if label:
                out.append(
                    {
                        "name": label,
                        "code": str(val.get("Code") or "").strip(),
                        "weight_pct": round(weight, 2) if weight is not None else None,
                        "sector": str(val.get("Sector") or "").strip(),
                        "country": str(val.get("Country") or "").strip(),
                    }
                )
    out.sort(key=lambda r: (r["weight_pct"] is None, -(r["weight_pct"] or 0.0)))
    return out[:limit]


def extract_fund_profile(
    eod_fund: dict[str, Any] | None,
    eod_item: dict[str, Any] | None = None,
    *,
    symbol: str = "",
) -> dict[str, Any] | None:
    """Construit un profil structuré de fonds à partir des données EODHD (`General`, `Highlights`, `Mutual_Fund`, `ETF_Data`)."""
    eod_fund = eod_fund if isinstance(eod_fund, dict) else {}
    gen = eod_fund.get("General") or {}
    hl = eod_fund.get("Highlights") or {}
    tech = eod_fund.get("Technicals") or {}
    mf = eod_fund.get("Mutual_Fund") or {}
    etf = eod_fund.get("ETF_Data") or {}
    fund_block = mf if isinstance(mf, dict) and mf else (etf if isinstance(etf, dict) else {})

    exch = str(gen.get("Exchange") or (eod_item or {}).get("Exchange") or (eod_item or {}).get("exchange") or "").upper()
    itype = str(gen.get("Type") or (eod_item or {}).get("Type") or (eod_item or {}).get("type") or "")
    if not is_fund_instrument(eod_fund, symbol=symbol, exchange=exch) and "FUND" not in itype.upper():
        return None

    summary_block = fund_block.get("Fund_Summary") if isinstance(fund_block.get("Fund_Summary"), dict) else {}
    morningstar = fund_block.get("MorningStar") if isinstance(fund_block.get("MorningStar"), dict) else {}

    expense_ratio = _pct(
        fund_block.get("Ongoing_Charge")
        or fund_block.get("ExpenseRatio")
        or fund_block.get("NetExpenseRatio")
        or hl.get("ExpenseRatio")
        or summary_block.get("Ongoing_Charge")
        or summary_block.get("NetExpenseRatio")
    )
    net_assets = _num(
        fund_block.get("TotalAssets")
        or fund_block.get("NetAssets")
        or hl.get("MarketCapitalization")
        or hl.get("NetAssets")
    )
    yield_pct = _pct(fund_block.get("Yield") or hl.get("DividendYield"))

    asset_allocation = _extract_weighted_entries(fund_block.get("Asset_Allocation"), limit=8)
    sector_weights = _extract_weighted_entries(
        fund_block.get("Sector_Weights") or (fund_block.get("Asset_Allocation") or {}).get("Sector_Weights"),
        limit=10,
    )
    world_regions = _extract_weighted_entries(fund_block.get("World_Regions"), limit=10)
    top_holdings = _extract_weighted_entries(
        fund_block.get("Top_Holdings") or fund_block.get("Holdings"),
        limit=15,
    )

    return {
        "is_fund": True,
        "name": str(gen.get("Name") or (eod_item or {}).get("Name") or (eod_item or {}).get("name") or symbol),
        "isin": gen.get("ISIN") or (eod_item or {}).get("ISIN") or (eod_item or {}).get("isin"),
        "exchange": exch or "EUFUND",
        "fund_type": itype or "Mutual Fund",
        "category": str(
            gen.get("Category")
            or fund_block.get("Fund_Category")
            or gen.get("Fund_Category")
            or ""
        ).strip() or None,
        "fund_family": str(
            gen.get("Fund_Family")
            or fund_block.get("Company_Name")
            or gen.get("Company_Name")
            or ""
        ).strip() or None,
        "currency": str(gen.get("CurrencyCode") or (eod_item or {}).get("Currency") or (eod_item or {}).get("currency") or "").upper() or None,
        "country": str(gen.get("CountryName") or (eod_item or {}).get("Country") or (eod_item or {}).get("country") or "").strip() or None,
        "inception_date": str(fund_block.get("Inception_Date") or gen.get("IPODate") or "").strip() or None,
        "expense_ratio_pct": expense_ratio,
        "net_assets": net_assets,
        "yield_pct": yield_pct,
        "morningstar_rating": _num(morningstar.get("Ratio")),
        "morningstar_category": str(morningstar.get("Category_Benchmark") or "").strip() or None,
        "beta": _num(tech.get("Beta") or fund_block.get("Beta")),
        "description": str(gen.get("Description") or summary_block.get("Summary") or "").strip()[:1200] or None,
        "website": str(gen.get("WebURL") or fund_block.get("Company_URL") or "").strip() or None,
        "asset_allocation": asset_allocation,
        "sector_weights": sector_weights,
        "world_regions": world_regions,
        "top_holdings": top_holdings,
    }
