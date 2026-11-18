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
    list_warehouse_watchlist_items_for_sync,
    record_sync_run_status,
    replace_exchange_symbols,
    save_sync_preferences,
    search_exchange_symbols,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

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
    return {
        "preferences": prefs,
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
) -> dict[str, Any]:
    """Exécute la synchronisation quotidienne selon les choix utilisateur (indices de base + sélections)."""
    from types import SimpleNamespace
    from .finance_indices import get_index_performances, list_eodhd_indx_catalog, list_principal_indices
    from .finance_watchlist import fetch_watchlist_quotes

    db_path = warehouse_db_path(settings)
    prefs = get_sync_preferences(db_path)
    if respect_enabled and not prefs.get("enabled", True):
        return {
            **(await get_daily_sync_state(settings)),
            "summary": {"skipped": True, "reason": "disabled"},
        }

    summary: dict[str, Any] = {
        "skipped": False,
        "principal_indices_count": 0,
        "indx_catalog_total": 0,
        "indices": {},
        "watchlist_items_count": 0,
        "exchanges": {},
        "errors": [],
    }

    if prefs.get("principal_indices"):
        try:
            idx_res = await list_principal_indices(settings, include_quotes=True, tier="major")
            summary["principal_indices_count"] = len(idx_res.get("indices") or [])
        except Exception as exc:
            summary["errors"].append(f"indices: {exc}")

    if prefs.get("indx_catalog"):
        try:
            cat_res = await list_eodhd_indx_catalog(settings, limit=50, refresh=refresh)
            summary["indx_catalog_total"] = int(cat_res.get("total") or 0)
        except Exception as exc:
            summary["errors"].append(f"indx_catalog: {exc}")

    for code in prefs.get("index_codes") or []:
        try:
            perf_res = await get_index_performances(settings, code, refresh=refresh)
            if perf_res:
                s_perf = perf_res.get("summary") or {}
                summary["indices"][code] = {
                    "loaded_count": int(s_perf.get("loaded_count") or 0),
                    "from_cache_count": int(s_perf.get("from_cache_count") or 0),
                    "fetched_count": int(s_perf.get("fetched_count") or 0),
                }
        except Exception as exc:
            summary["errors"].append(f"index:{code}: {exc}")

    if prefs.get("watchlists"):
        try:
            raw_items = list_warehouse_watchlist_items_for_sync(db_path)
            if raw_items:
                wl_objs = [SimpleNamespace(**it) for it in raw_items]
                enriched = await fetch_watchlist_quotes(settings, wl_objs, refresh=refresh)
                summary["watchlist_items_count"] = len(enriched)
        except Exception as exc:
            summary["errors"].append(f"watchlists: {exc}")

    exch_codes: list[str] = []
    seen_exch: set[str] = set()
    for code in [*(prefs.get("exchanges") or []), *parse_auto_sync_exchange_codes(settings)]:
        clean_c = str(code or "").strip().upper()
        if clean_c and clean_c != "ALL" and _EXCHANGE_CODE_RE.fullmatch(clean_c) and clean_c not in seen_exch:
            seen_exch.add(clean_c)
            exch_codes.append(clean_c)

    if exch_codes:
        exch_res = await sync_configured_exchange_catalogs(settings, refresh=refresh, codes=exch_codes)
        summary["exchanges"] = exch_res.get("exchanges") or {}

    record_sync_run_status(db_path, summary)
    state = await get_daily_sync_state(settings)
    return {**state, "summary": summary}


async def run_daily_exchange_catalog_sync_loop(settings: Settings) -> None:
    """Tâche de fond quotidienne exécutant uniquement les éléments sélectionnés par l'utilisateur (indices par défaut)."""
    try:
        await asyncio.sleep(15.0)
        while True:
            try:
                if (
                    not settings.demo_mode
                    and getattr(settings, "finance_exchange_auto_sync_enabled", True)
                    and settings.enabled(settings.eod_historical_data_key)
                ):
                    db_path = warehouse_db_path(settings)
                    prefs = get_sync_preferences(db_path)
                    today_prefix = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                    last_run = str(prefs.get("last_run_at") or "")
                    updated = str(prefs.get("updated_at") or "")
                    already_ran_today = last_run.startswith(today_prefix) and (not updated or updated <= last_run)
                    if prefs.get("enabled", True) and not already_ran_today:
                        res = await run_daily_sync_now(settings, refresh=False, respect_enabled=True)
                        s_info = res.get("summary") or {}
                        if not s_info.get("skipped"):
                            _logger.info(
                                "Synchro quotidienne terminée (indices=%s, constituants=%d, watchlist=%d, marchés=%d).",
                                s_info.get("principal_indices_count", 0),
                                len(s_info.get("indices") or {}),
                                s_info.get("watchlist_items_count", 0),
                                len(s_info.get("exchanges") or {}),
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _logger.warning("Erreur boucle synchro quotidienne finance: %s", exc)
            sleep_sec = min(_exchange_ttl_seconds(settings), 6 * 3600)
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
