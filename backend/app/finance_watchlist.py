"""Suivi d'actions (Watchlist) : résolution d'instruments et calcul des performances 1J, 1S, 1M, 3M, 1A."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

import httpx
from fastapi import HTTPException

from .config import Settings
from .finance import (
    DEFAULT_USER_AGENT,
    _safe_float,
    fetch_eodhd_historical_eod,
    fetch_eodhd_realtime,
    fetch_yahoo_chart,
    get_yahoo_crumb_and_client,
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
        c = _safe_float(bar.get("close"))
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

    eod_item: dict[str, Any] | None = None
    if eod_key and not settings.demo_mode:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
                timeout=10.0,
            ) as client:
                for variant in query_variants(clean_q):
                    eod_item = await search_eodhd_ticker(client, variant, eod_key)
                    if eod_item:
                        break
        except Exception as exc:
            _logger.debug("Résolution EODHD watchlist ignorée (%s): %s", clean_q, exc)

    yahoo_quote: dict[str, Any] | None = None
    yahoo_chart: dict[str, Any] | None = None
    if not settings.demo_mode:
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
    name = str(name).split(" - ")[0].split(" (")[0].strip()
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
) -> dict[str, Any]:
    base_payload = {
        "id": item.id,
        "symbol": item.symbol,
        "yahoo_symbol": item.yahoo_symbol or item.symbol,
        "eod_ticker": item.eod_ticker or item.symbol,
        "name": item.name,
        "exchange": item.exchange or "",
        "currency": item.currency or "EUR",
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

    async with sem:
        bars: list[dict[str, Any]] = []
        current_price: float | None = None
        rt_change_pct: float | None = None
        currency = item.currency or "EUR"

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=True,
                timeout=10.0,
            ) as client:
                chart = await fetch_yahoo_chart(client, yahoo_sym, range_period="1y", interval="1d")
                if chart:
                    meta = chart.get("meta") or {}
                    current_price = _safe_float(meta.get("regularMarketPrice"))
                    prev_close = _safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
                    if current_price is not None and prev_close and prev_close > 0:
                        rt_change_pct = round(((current_price - prev_close) / prev_close) * 100.0, 2)
                    if meta.get("currency"):
                        currency = str(meta["currency"])
                    bars = _yahoo_chart_to_daily_bars(chart)

                if eod_key and item.eod_ticker:
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
                        bars = list(reversed(eod_bars))
        except Exception as exc:
            _logger.warning("Échec récupération variations watchlist pour %s: %s", item.symbol, exc)

        metrics = compute_period_returns(bars, current_price=current_price, rt_change_pct=rt_change_pct)
        base_payload.update(metrics)
        base_payload["currency"] = currency
        return base_payload


async def fetch_watchlist_quotes(settings: Settings, items: list[Any]) -> list[dict[str, Any]]:
    """Enrichit les actions suivies avec leur cours et évolutions 1J, 1S, 1M, 3M et 1A."""
    if not items:
        return []
    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    sem = asyncio.Semaphore(5)
    tasks = [_fetch_single_watchlist_quote(settings, item, eod_key, sem) for item in items]
    return list(await asyncio.gather(*tasks))
