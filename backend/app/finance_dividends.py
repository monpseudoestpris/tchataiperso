"""Service canonique des dividendes boursiers (entrepôt local + EODHD / Yahoo Finance).

Partage le même snapshot `payload_type = 'dividends'` que `finance_dossier.py` dans
`finance_warehouse.db` afin d'éviter tout double appel API EODHD.
"""

from __future__ import annotations

import datetime
import logging
import math
import urllib.parse
from typing import Any

import httpx

from .config import Settings
from .finance_eodhd_usage import record_eodhd_call
from .finance_provider import resolve_candidate_eod_tickers
from .finance_warehouse import (
    get_instrument_meta,
    get_snapshot,
    resolve_canonical_symbol,
    save_snapshot,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _positive_float(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        parsed = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _is_valid_iso_date(raw: str) -> bool:
    if len(raw) != 10:
        return False
    try:
        datetime.date.fromisoformat(raw)
        return True
    except ValueError:
        return False


def normalize_dividend_entries(
    raw: list[dict[str, Any]] | None,
    *,
    fallback_currency: str = "",
) -> list[dict[str, Any]]:
    """Normalise, dédoublonne par date et trie chronologiquement une liste de dividendes."""
    if not isinstance(raw, list):
        return []
    fallback_curr = fallback_currency.strip().upper()
    by_date: dict[str, dict[str, Any]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        date_str = str(entry.get("date") or "").strip()[:10]
        if not _is_valid_iso_date(date_str):
            continue
        value = _positive_float(entry.get("value"))
        if value is None:
            continue
        unadjusted = _positive_float(entry.get("unadjusted") or entry.get("unadjustedValue"))
        currency = str(entry.get("currency") or "").strip().upper() or fallback_curr
        by_date[date_str] = {
            "date": date_str,
            "value": round(value, 6),
            "unadjusted": round(unadjusted, 6) if unadjusted is not None else None,
            "currency": currency,
        }
    return [by_date[d] for d in sorted(by_date.keys())]


async def fetch_eodhd_dividends(ticker: str, api_key: str) -> list[dict[str, Any]] | None:
    """Télécharge l'historique des dividendes depuis EODHD `/api/div/{ticker}`."""
    if not api_key or not ticker:
        return None
    url = (
        f"https://eodhd.com/api/div/{urllib.parse.quote(ticker)}"
        f"?from=1985-01-01&fmt=json&api_token={urllib.parse.quote(api_key)}"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return normalize_dividend_entries(data)
    except (httpx.HTTPError, ValueError) as exc:
        _logger.warning("Erreur /api/div EODHD (%s): %s", ticker, exc)
    return None


async def fetch_yahoo_dividends(yahoo_symbol: str) -> list[dict[str, Any]] | None:
    """Télécharge l'historique des dividendes depuis Yahoo Finance (`events=div`)."""
    if not yahoo_symbol:
        return None
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}"
        "?range=max&interval=1mo&events=div"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            res = (resp.json().get("chart") or {}).get("result") or []
            if not res or not isinstance(res[0], dict):
                return None
            item = res[0]
            meta_currency = str((item.get("meta") or {}).get("currency") or "").strip().upper()
            divs_map = ((item.get("events") or {}).get("dividends") or {})
            if not isinstance(divs_map, dict):
                return []
            extracted: list[dict[str, Any]] = []
            for dv in divs_map.values():
                if not isinstance(dv, dict):
                    continue
                amt = _positive_float(dv.get("amount"))
                ts = dv.get("date")
                if amt is None or not isinstance(ts, (int, float)):
                    continue
                d_str = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")
                extracted.append(
                    {
                        "date": d_str,
                        "value": amt,
                        "unadjusted": amt,
                        "currency": meta_currency,
                    }
                )
            return normalize_dividend_entries(extracted, fallback_currency=meta_currency)
    except (httpx.HTTPError, ValueError) as exc:
        _logger.warning("Erreur dividendes Yahoo Finance (%s): %s", yahoo_symbol, exc)
    return None


async def get_stock_dividends(
    settings: Settings,
    symbol: str,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Retourne les dividendes historiques normalisés d'un titre (cache entrepôt prioritaire)."""
    db_path = warehouse_db_path(settings)
    clean_sym = symbol.strip().upper()
    canonical = resolve_canonical_symbol(db_path, clean_sym)
    meta = get_instrument_meta(db_path, canonical) or {}
    fallback_currency = str(meta.get("currency") or "").strip().upper()
    ttl_seconds = max(3600, int(settings.finance_fundamentals_ttl_hours) * 3600)

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    prefer_eod = bool(eod_key and not settings.demo_mode)
    is_eufund = canonical.upper().endswith(".EUFUND")

    if not refresh:
        cached_snap = (
            get_snapshot(db_path, canonical, "dividends", provider="eodhd", max_age_seconds=ttl_seconds, include_raw=True)
            if prefer_eod
            else get_snapshot(db_path, canonical, "dividends", max_age_seconds=ttl_seconds, include_raw=True)
        )
        if cached_snap and isinstance(cached_snap.get("raw"), list):
            divs = normalize_dividend_entries(cached_snap["raw"], fallback_currency=fallback_currency)
            resolved_curr = (
                str(cached_snap.get("currency") or "").strip().upper()
                or (divs[-1]["currency"] if divs else "")
                or fallback_currency
            )
            return {
                "symbol": clean_sym,
                "canonical_symbol": canonical,
                "currency": resolved_curr,
                "source": str(cached_snap.get("provider") or "eodhd"),
                "cached": True,
                "dividends": divs,
            }

    if settings.demo_mode:
        return {
            "symbol": clean_sym,
            "canonical_symbol": canonical,
            "currency": fallback_currency,
            "source": "demo",
            "cached": False,
            "dividends": [],
        }

    fetched: list[dict[str, Any]] | None = None
    source = "eodhd"

    if prefer_eod:
        candidates = resolve_candidate_eod_tickers(db_path, canonical) or [canonical]
        for cand in candidates[:3]:
            cand_divs = await fetch_eodhd_dividends(cand, eod_key)
            if cand_divs is not None:
                fetched = cand_divs
                source = "eodhd"
                break

    if fetched is None and not is_eufund:
        if not refresh and prefer_eod:
            fb_snap = get_snapshot(
                db_path,
                canonical,
                "dividends",
                provider="yahoo_finance",
                max_age_seconds=ttl_seconds,
                include_raw=True,
            )
            if fb_snap and isinstance(fb_snap.get("raw"), list):
                divs = normalize_dividend_entries(fb_snap["raw"], fallback_currency=fallback_currency)
                resolved_curr = (
                    str(fb_snap.get("currency") or "").strip().upper()
                    or (divs[-1]["currency"] if divs else "")
                    or fallback_currency
                )
                return {
                    "symbol": clean_sym,
                    "canonical_symbol": canonical,
                    "currency": resolved_curr,
                    "source": "yahoo_finance",
                    "cached": True,
                    "dividends": divs,
                }

        yahoo_lookup = str(meta.get("yahoo_symbol") or "").strip() or (
            canonical[:-3] if canonical.endswith(".US") else canonical
        )
        y_divs = await fetch_yahoo_dividends(yahoo_lookup)
        if y_divs is not None:
            fetched = y_divs
            source = "yahoo_finance"

    normalized = normalize_dividend_entries(fetched, fallback_currency=fallback_currency)
    resolved_curr = (normalized[-1]["currency"] if normalized else "") or fallback_currency

    if fetched is not None:
        save_snapshot(
            db_path,
            canonical,
            source,
            "dividends",
            normalized,
            None,
            currency=resolved_curr or None,
        )

    return {
        "symbol": clean_sym,
        "canonical_symbol": canonical,
        "currency": resolved_curr,
        "source": source if fetched is not None else "none",
        "cached": False,
        "dividends": normalized,
    }
