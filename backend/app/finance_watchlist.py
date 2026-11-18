"""Suivi d'actions (Watchlist) : résolution d'instruments et calcul des performances 1J, 1S, 1M, 3M, 1A."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

import httpx
from fastapi import HTTPException

from .config import Settings
from .finance_funds import looks_like_isin
from .finance_warehouse import (
    get_instrument_meta,
    get_snapshot,
    get_stored_eod_bars,
    lookup_exchange_symbol,
    resolve_canonical_symbol,
    upsert_eod_bars,
    warehouse_db_path,
)
from .finance import (
    DEFAULT_USER_AGENT,
    _safe_float,
    fetch_eodhd_fundamentals,
    fetch_eodhd_historical_eod,
    fetch_eodhd_realtime,
    fetch_yahoo_chart,
    get_yahoo_crumb_and_client,
    lookup_eodhd_search_metadata,
    query_variants,
    search_eodhd_ticker,
    search_yahoo_ticker,
)

_logger = logging.getLogger("uvicorn.error")

DEFAULT_WATCHLIST_SEEDS: list[dict[str, str]] = [
    {"symbol": "AI.PA", "yahoo_symbol": "AI.PA", "eod_ticker": "AI.PA", "name": "Air Liquide", "exchange": "PA", "currency": "EUR"},
    {"symbol": "MC.PA", "yahoo_symbol": "MC.PA", "eod_ticker": "MC.PA", "name": "LVMH", "exchange": "PA", "currency": "EUR"},
    {"symbol": "TTE.PA", "yahoo_symbol": "TTE.PA", "eod_ticker": "TTE.PA", "name": "TotalEnergies", "exchange": "PA", "currency": "EUR"},
    {"symbol": "AAPL", "yahoo_symbol": "AAPL", "eod_ticker": "AAPL.US", "name": "Apple", "exchange": "NASDAQ", "currency": "USD"},
    {"symbol": "NVDA", "yahoo_symbol": "NVDA", "eod_ticker": "NVDA.US", "name": "Nvidia", "exchange": "NASDAQ", "currency": "USD"},
    {"symbol": "MSFT", "yahoo_symbol": "MSFT", "eod_ticker": "MSFT.US", "name": "Microsoft", "exchange": "NASDAQ", "currency": "USD"},
]


def _parse_bar_date(raw_date: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(raw_date[:10])
    except (TypeError, ValueError):
        return None


def _pick_reference_close(
    dated_bars: list[tuple[datetime.date, float]],
    target_date: datetime.date,
    fallback_offset: int,
) -> float | None:
    """Retourne la clôture la plus récente <= target_date, avec repli par nombre de séances."""
    if len(dated_bars) < 2:
        return None
    candidate: float | None = None
    for bar_date, close_val in dated_bars:
        if bar_date <= target_date:
            candidate = close_val
        else:
            break
    if candidate is not None:
        return candidate
    # Si target_date précède légèrement la première barre (ex. 1 an exact vs 251 séances),
    # utiliser la borne la plus proche si la série couvre une fenêtre suffisante.
    idx = max(0, len(dated_bars) - 1 - fallback_offset)
    if idx < len(dated_bars) - 1:
        return dated_bars[idx][1]
    return dated_bars[0][1]


def compute_period_returns(
    bars: list[dict[str, Any]],
    current_price: float | None = None,
    rt_change_pct: float | None = None,
) -> dict[str, float | None]:
    """
    Calcule les variations en pourcentage sur 1J, 1S, 1M, 3M et 1A
    à partir d'une série chronologique de barres journalières.
    """
    dated_bars: list[tuple[datetime.date, float]] = []
    for bar in bars:
        d = _parse_bar_date(str(bar.get("date") or ""))
        c = _safe_float(bar.get("adjusted_close") or bar.get("close"))
        if d is not None and c is not None and c > 0:
            dated_bars.append((d, c))
    dated_bars.sort(key=lambda item: item[0])

    if not dated_bars:
        return {
            "price": current_price,
            "change_1d_pct": rt_change_pct,
            "change_1w_pct": None,
            "change_1m_pct": None,
            "change_3m_pct": None,
            "change_1y_pct": None,
        }

    latest_date, latest_close = dated_bars[-1]
    effective_price = current_price if current_price is not None and current_price > 0 else latest_close

    def _pct(ref_close: float | None) -> float | None:
        if ref_close is None or ref_close <= 0 or effective_price is None:
            return None
        return round(((effective_price - ref_close) / ref_close) * 100.0, 2)

    change_1d = rt_change_pct
    if change_1d is None and len(dated_bars) >= 2:
        prev_close = dated_bars[-2][1]
        change_1d = _pct(prev_close)

    # Pour 1W/1M/3M/1A, si la série compte assez de jours calendaires on prend le delta calendaire.
    total_span_days = (latest_date - dated_bars[0][0]).days

    def _horizon_pct(days: int, trading_offset: int, min_span_days: int) -> float | None:
        if len(dated_bars) < 2:
            return None
        if total_span_days < min_span_days and len(dated_bars) <= trading_offset:
            return None
        ref_close = _pick_reference_close(
            dated_bars,
            latest_date - datetime.timedelta(days=days),
            fallback_offset=trading_offset,
        )
        return _pct(ref_close)

    return {
        "price": round(effective_price, 4) if effective_price is not None else None,
        "change_1d_pct": round(change_1d, 2) if change_1d is not None else None,
        "change_1w_pct": _horizon_pct(7, 5, 4),
        "change_1m_pct": _horizon_pct(30, 21, 20),
        "change_3m_pct": _horizon_pct(90, 63, 60),
        "change_1y_pct": _horizon_pct(365, 250, 200),
    }


async def resolve_watchlist_instrument(settings: Settings, query: str) -> dict[str, str]:
    """Résout une requête libre (nom d'entreprise, ticker, ISIN) en instrument financier normalisé."""
    clean_q = query.strip().strip("$")
    if not clean_q:
        raise HTTPException(400, "Veuillez saisir un nom d'action ou un ticker.")

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    db_path = warehouse_db_path(settings)

    eod_item: dict[str, Any] | None = None
    if (clean_q.upper().endswith(".EUFUND") or looks_like_isin(clean_q)) and not settings.demo_mode:
        cat_hit = lookup_exchange_symbol(db_path, clean_q, "EUFUND")
        if cat_hit:
            eod_item = {
                "Code": cat_hit["symbol"],
                "Exchange": cat_hit["exchange"],
                "Name": cat_hit["name"],
                "ticker": cat_hit["eod_ticker"],
                "Type": cat_hit["type"],
                "Country": cat_hit["country"],
                "Currency": cat_hit["currency"] or "EUR",
                "ISIN": cat_hit["isin"],
            }

    if eod_item is None and eod_key and not settings.demo_mode:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
                timeout=12.0,
            ) as client:
                for variant in query_variants(clean_q):
                    eod_item = await search_eodhd_ticker(client, variant, eod_key)
                    if eod_item:
                        break
                if not eod_item:
                    eod_item = await search_eodhd_ticker(client, clean_q, eod_key, asset_type="fund")

                # Enrichir le nom réel et la devise si le ticker est explicite (ex. FR0013202132.EUFUND)
                if eod_item and str(eod_item.get("Name") or "").upper() == str(eod_item.get("ticker") or "").upper():
                    t_code = str(eod_item["ticker"])
                    inst_meta = get_instrument_meta(db_path, t_code)
                    if inst_meta and (inst_meta.get("long_name") or inst_meta.get("short_name")):
                        raw_nm = str(inst_meta.get("long_name") or inst_meta.get("short_name") or "").strip()
                        if raw_nm and raw_nm.upper() != t_code.upper():
                            eod_item["Name"] = raw_nm
                        if inst_meta.get("currency"):
                            eod_item["Currency"] = str(inst_meta["currency"]).strip().upper()
                    if str(eod_item.get("Name") or "").upper() == t_code.upper():
                        search_meta = await lookup_eodhd_search_metadata(client, t_code, eod_key)
                        if search_meta and search_meta.get("Name") and str(search_meta["Name"]).upper() != t_code.upper():
                            eod_item["Name"] = str(search_meta["Name"]).strip()
                            if search_meta.get("Currency"):
                                eod_item["Currency"] = str(search_meta["Currency"]).strip().upper()
                            if search_meta.get("Exchange"):
                                eod_item["Exchange"] = str(search_meta["Exchange"]).strip().upper()
                    if str(eod_item.get("Name") or "").upper() == t_code.upper():
                        snap = get_snapshot(db_path, t_code, "fundamentals", provider="eodhd", include_raw=True)
                        fund_raw = snap.get("raw") if (snap and isinstance(snap.get("raw"), dict)) else None
                        if fund_raw is None:
                            fund_raw = await fetch_eodhd_fundamentals(client, t_code, eod_key)
                        if isinstance(fund_raw, dict):
                            gen = fund_raw.get("General") or {}
                            if gen.get("Name"):
                                eod_item["Name"] = str(gen["Name"]).strip()
                            if gen.get("CurrencyCode"):
                                eod_item["Currency"] = str(gen["CurrencyCode"]).strip().upper()
                            if gen.get("Exchange"):
                                eod_item["Exchange"] = str(gen["Exchange"]).strip().upper()
        except Exception as exc:
            _logger.debug("Résolution EODHD watchlist ignorée (%s): %s", clean_q, exc)

    is_eufund = bool(
        eod_item
        and (
            str(eod_item.get("Exchange") or "").upper() == "EUFUND"
            or str(eod_item.get("ticker") or "").upper().endswith(".EUFUND")
        )
    )

    yahoo_quote: dict[str, Any] | None = None
    yahoo_chart: dict[str, Any] | None = None
    if not settings.demo_mode and not is_eufund:
        try:
            client, _ = await get_yahoo_crumb_and_client()
            try:
                lookup = (eod_item.get("ticker") if eod_item else None) or clean_q
                if lookup.endswith(".US"):
                    lookup = lookup[:-3]
                for variant in query_variants(lookup):
                    yahoo_quote = await search_yahoo_ticker(client, variant)
                    if yahoo_quote:
                        break
                sym_to_check = (yahoo_quote.get("symbol") if yahoo_quote else None) or (
                    lookup.upper() if ("." in lookup or len(lookup) <= 6) else None
                )
                if sym_to_check:
                    yahoo_chart = await fetch_yahoo_chart(client, sym_to_check, range_period="5d", interval="1d")
            finally:
                await client.aclose()
        except Exception as exc:
            _logger.debug("Résolution Yahoo watchlist ignorée (%s): %s", clean_q, exc)

    if not eod_item and not yahoo_quote and not yahoo_chart:
        if settings.demo_mode:
            sym = clean_q.upper().replace(" ", "")[:16]
            return {
                "symbol": sym,
                "yahoo_symbol": sym,
                "eod_ticker": sym,
                "name": clean_q,
                "exchange": "DEMO",
                "currency": "EUR" if "." in sym else "USD",
            }
        raise HTTPException(404, f"Action ou ticker introuvable pour « {query} ».")

    meta = (yahoo_chart or {}).get("meta") or {}
    yahoo_sym = (
        (yahoo_quote.get("symbol") if yahoo_quote else None)
        or meta.get("symbol")
        or ""
    )
    eod_ticker = (eod_item.get("ticker") if eod_item else None) or ""
    symbol = eod_ticker or yahoo_sym or clean_q.upper()
    name = (
        (yahoo_quote.get("shortname") if yahoo_quote else None)
        or (yahoo_quote.get("longname") if yahoo_quote else None)
        or meta.get("shortName")
        or (eod_item.get("Name") if eod_item else None)
        or symbol
    )
    name = str(name).strip() if is_eufund else str(name).split(" - ")[0].split(" (")[0].strip()
    exchange = (
        (eod_item.get("Exchange") if eod_item else None)
        or (yahoo_quote.get("exchDisp") if yahoo_quote else None)
        or meta.get("exchangeName")
        or (symbol.split(".")[1] if "." in symbol else "Marché")
    )
    currency = (
        (eod_item.get("Currency") if eod_item else None)
        or meta.get("currency")
        or ("USD" if str(exchange).upper() in {"US", "NASDAQ", "NYSE", "NMS", "NYQ"} else "EUR")
    )
    return {
        "symbol": str(symbol).upper()[:32],
        "yahoo_symbol": str(yahoo_sym or symbol).upper()[:32],
        "eod_ticker": str(eod_ticker or symbol).upper()[:32],
        "name": name[:200],
        "exchange": str(exchange)[:80],
        "currency": str(currency).upper()[:16],
    }


def _yahoo_chart_to_daily_bars(chart: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not chart or "timestamp" not in chart:
        return []
    ts = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    bars: list[dict[str, Any]] = []
    for idx, t_val in enumerate(ts):
        c_val = _safe_float(closes[idx] if idx < len(closes) else None)
        if c_val is None or t_val is None:
            continue
        d_str = datetime.datetime.fromtimestamp(t_val, datetime.timezone.utc).strftime("%Y-%m-%d")
        bars.append({"date": d_str, "close": c_val})
    return bars


async def _fetch_single_watchlist_quote(
    settings: Settings,
    item: Any,
    eod_key: str,
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    base_payload = {
        "id": item.id,
        "list_id": getattr(item, "list_id", None),
        "symbol": item.symbol,
        "yahoo_symbol": item.yahoo_symbol or item.symbol,
        "eod_ticker": item.eod_ticker or item.symbol,
        "name": item.name,
        "exchange": item.exchange or "",
        "currency": item.currency or "EUR",
        "note": getattr(item, "note", "") or "",
        "position": item.position,
        "price": None,
        "change_1d_pct": None,
        "change_1w_pct": None,
        "change_1m_pct": None,
        "change_3m_pct": None,
        "change_1y_pct": None,
    }
    if settings.demo_mode:
        return base_payload

    yahoo_sym = item.yahoo_symbol or item.symbol
    if yahoo_sym.endswith(".US"):
        yahoo_sym = yahoo_sym[:-3]

    db_path = warehouse_db_path(settings)
    lookup_sym = item.eod_ticker or item.symbol or yahoo_sym
    canonical = resolve_canonical_symbol(db_path, lookup_sym)
    stored_bars = get_stored_eod_bars(db_path, canonical, limit=270)
    fresh_cutoff = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    has_fresh_stored = bool(stored_bars and str(stored_bars[-1].get("date") or "") >= fresh_cutoff)

    async with sem:
        bars: list[dict[str, Any]] = stored_bars if has_fresh_stored else []
        current_price: float | None = None
        rt_change_pct: float | None = None
        currency = item.currency or "EUR"

        try:
            is_eufund = str(item.eod_ticker or "").upper().endswith(".EUFUND") or str(item.exchange or "").upper() == "EUFUND"
            if eod_key and item.eod_ticker:
                if not is_eufund:
                    rt_data = await fetch_eodhd_realtime(client, item.eod_ticker, eod_key)
                    if rt_data:
                        rt_p = _safe_float(rt_data.get("close"))
                        rt_chg = _safe_float(rt_data.get("change_p"))
                        if rt_p is not None and rt_p > 0:
                            current_price = rt_p
                        if rt_chg is not None:
                            rt_change_pct = rt_chg
                if not bars:
                    eod_bars = await fetch_eodhd_historical_eod(client, item.eod_ticker, eod_key, limit=270)
                    if eod_bars:
                        bars = list(reversed(eod_bars))
                        try:
                            upsert_eod_bars(db_path, canonical, bars, "eodhd")
                        except Exception:
                            pass

            if not bars and not is_eufund:
                chart = await fetch_yahoo_chart(client, yahoo_sym, range_period="1y", interval="1d")
                if chart:
                    meta = chart.get("meta") or {}
                    if current_price is None:
                        current_price = _safe_float(meta.get("regularMarketPrice"))
                    prev_close = _safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
                    if rt_change_pct is None and current_price is not None and prev_close and prev_close > 0:
                        rt_change_pct = round(((current_price - prev_close) / prev_close) * 100.0, 2)
                    if meta.get("currency"):
                        currency = str(meta["currency"])
                    bars = _yahoo_chart_to_daily_bars(chart)
        except Exception as exc:
            _logger.warning("Échec récupération variations watchlist pour %s: %s", item.symbol, exc)

        metrics = compute_period_returns(bars, current_price=current_price, rt_change_pct=rt_change_pct)
        base_payload.update(metrics)
        base_payload["currency"] = currency
        return base_payload


async def repair_watchlist_item_names(settings: Settings, items: list[Any]) -> bool:
    """Enrichit les items dont le nom vaut encore le ticker brut (ex. `FR0013202132.EUFUND`)."""
    if not items or settings.demo_mode:
        return False
    db_path = warehouse_db_path(settings)
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    candidates: list[tuple[Any, str]] = []
    for item in items:
        cur_name = str(getattr(item, "name", "") or "").strip().upper()
        sym_u = str(getattr(item, "symbol", "") or "").strip().upper()
        eod_u = str(getattr(item, "eod_ticker", "") or "").strip().upper()
        if not cur_name or cur_name in {sym_u, eod_u} or cur_name.endswith(".EUFUND"):
            candidates.append((item, eod_u or sym_u))
    if not candidates:
        return False

    changed = False
    unresolved: list[tuple[Any, str]] = []
    for item, lookup_sym in candidates:
        resolved_name: str | None = None
        resolved_curr: str | None = None
        if lookup_sym.endswith(".EUFUND") or str(getattr(item, "exchange", "") or "").upper() == "EUFUND":
            cat = lookup_exchange_symbol(db_path, lookup_sym, "EUFUND")
            if cat and cat.get("name") and str(cat["name"]).upper() != lookup_sym:
                resolved_name = str(cat["name"]).strip()
                resolved_curr = str(cat.get("currency") or "").strip().upper() or None
        if not resolved_name:
            inst = get_instrument_meta(db_path, lookup_sym)
            if inst:
                cand_name = str(inst.get("long_name") or inst.get("short_name") or "").strip()
                if cand_name and cand_name.upper() != lookup_sym:
                    resolved_name = cand_name
                    resolved_curr = str(inst.get("currency") or "").strip().upper() or None
        if resolved_name:
            item.name = resolved_name[:200]
            if resolved_curr and not item.currency:
                item.currency = resolved_curr[:16]
            changed = True
        elif eod_key:
            unresolved.append((item, lookup_sym))

    if unresolved and eod_key:
        async with httpx.AsyncClient(
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
            timeout=10.0,
        ) as client:
            for item, lookup_sym in unresolved:
                meta = await lookup_eodhd_search_metadata(client, lookup_sym, eod_key)
                if meta and meta.get("Name") and str(meta["Name"]).upper() != lookup_sym:
                    item.name = str(meta["Name"]).strip()[:200]
                    if meta.get("Currency"):
                        item.currency = str(meta["Currency"]).strip().upper()[:16]
                    changed = True
                    continue
                fund_raw = await fetch_eodhd_fundamentals(client, lookup_sym, eod_key)
                if isinstance(fund_raw, dict):
                    gen = fund_raw.get("General") or {}
                    if gen.get("Name") and str(gen["Name"]).upper() != lookup_sym:
                        item.name = str(gen["Name"]).strip()[:200]
                        if gen.get("CurrencyCode"):
                            item.currency = str(gen["CurrencyCode"]).strip().upper()[:16]
                        changed = True

    return changed


async def fetch_watchlist_quotes(settings: Settings, items: list[Any]) -> list[dict[str, Any]]:
    """Enrichit les actions suivies avec leur cours et évolutions 1J, 1S, 1M, 3M et 1A."""
    if not items:
        return []
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
        timeout=10.0,
    ) as client:
        tasks = [_fetch_single_watchlist_quote(settings, item, eod_key, sem, client) for item in items]
        return list(await asyncio.gather(*tasks))
