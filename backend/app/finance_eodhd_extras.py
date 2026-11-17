"""Connecteurs complémentaires EOD Historical Data (Fundamentals & EOD All-World).

Regroupe les flux complémentaires inclus dans les abonnements EODHD :
- Logo officiel (`General.LogoURL` / `/img/logos/{EXCHANGE}/{CODE}.png`)
- Sentiment agrégé et volume médiatique (`/api/sentiments`)
- Capitalisation boursière historique (`/api/historical-market-cap/{ticker}`)
- Calendrier corporate & prochains résultats (`/api/calendar/earnings`)
- Transactions d'initiés SEC Form 4 (`/api/insider-transactions`)
- Contexte macroéconomique & taux US Treasury (`/api/macro-indicator`, `/api/ust/bill-rates`)
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import urllib.parse
from typing import Any

import httpx

_logger = logging.getLogger("uvicorn.error")

_TIMEOUT = httpx.Timeout(12.0, connect=5.0)

_COUNTRY_ISO3_FALLBACK = {
    "US": "USA",
    "FR": "FRA",
    "DE": "DEU",
    "GB": "GBR",
    "UK": "GBR",
    "NL": "NLD",
    "CH": "CHE",
    "JP": "JPN",
    "CA": "CAN",
    "IT": "ITA",
    "ES": "ESP",
    "BE": "BEL",
    "SE": "SWE",
    "DK": "DNK",
    "FI": "FIN",
    "NO": "NOR",
    "IE": "IRL",
    "AU": "AUS",
    "HK": "HKG",
    "CN": "CHN",
    "KR": "KOR",
    "TW": "TWN",
}


def _fnum(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        out = float(str(val).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def resolve_eodhd_logo_url(eod_fund: dict[str, Any] | None, canonical: str) -> str | None:
    """Retourne l'URL publique du logo officiel EODHD (40 000+ logos)."""
    gen = (eod_fund or {}).get("General") or {}
    raw_logo = str(gen.get("LogoURL") or "").strip()
    if raw_logo:
        if raw_logo.startswith(("https://", "http://")):
            return raw_logo.replace("http://", "https://", 1)
        if raw_logo.startswith("/"):
            return f"https://eodhd.com{raw_logo}"
    code = str(gen.get("Code") or "").strip().upper()
    exch = str(gen.get("Exchange") or "").strip().upper()
    if not code and "." in canonical:
        code, exch = canonical.split(".", 1)
    if code and exch:
        return f"https://eodhd.com/img/logos/{urllib.parse.quote(exch)}/{urllib.parse.quote(code)}.png"
    return None


def resolve_country_iso3(eod_fund: dict[str, Any] | None, canonical: str) -> str:
    """Déduit le code ISO-3 du pays pour `/api/macro-indicator/{country}`."""
    gen = (eod_fund or {}).get("General") or {}
    iso = str(gen.get("CountryISO") or "").strip().upper()
    if len(iso) == 3:
        return iso
    if len(iso) == 2 and iso in _COUNTRY_ISO3_FALLBACK:
        return _COUNTRY_ISO3_FALLBACK[iso]
    if canonical.endswith(".PA"):
        return "FRA"
    if canonical.endswith(".DE") or canonical.endswith(".F"):
        return "DEU"
    if canonical.endswith(".L"):
        return "GBR"
    if canonical.endswith(".AS"):
        return "NLD"
    if canonical.endswith(".SW"):
        return "CHE"
    return "USA"


async def fetch_eodhd_sentiments(
    ticker: str,
    api_key: str,
    days: int = 90,
) -> dict[str, Any] | None:
    """Récupère les scores de sentiment quotidiens EODHD (`/api/sentiments`)."""
    if not ticker or not api_key:
        return None
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=max(14, days))).isoformat()
    url = (
        f"https://eodhd.com/api/sentiments?s={urllib.parse.quote(ticker)}"
        f"&from={start}&to={today.isoformat()}&api_token={urllib.parse.quote(api_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            raw = resp.json()
    except Exception as exc:
        _logger.debug("Erreur sentiments EODHD (%s): %s", ticker, exc)
        return None

    rows: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for val in raw.values():
            if isinstance(val, list):
                rows = val
                break
    elif isinstance(raw, list):
        rows = raw

    series: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        dt = str(item.get("date") or "").strip()[:10]
        norm = _fnum(item.get("normalized"))
        cnt = _fnum(item.get("count"))
        if dt and norm is not None:
            series.append({
                "date": dt,
                "normalized": round(norm, 3),
                "count": int(cnt) if cnt is not None else 0,
            })

    series.sort(key=lambda r: r["date"])
    if not series:
        return None

    total_articles = sum(r["count"] for r in series)
    avg_norm = round(sum(r["normalized"] for r in series) / len(series), 3)
    latest = series[-1]
    return {
        "avg_normalized": avg_norm,
        "latest_normalized": latest["normalized"],
        "latest_date": latest["date"],
        "article_count": total_articles,
        "days_covered": len(series),
        "series": series[-30:],
    }


async def fetch_eodhd_historical_mcap(
    ticker: str,
    api_key: str,
    years: int = 10,
) -> dict[str, Any] | None:
    """Récupère l'historique de capitalisation boursière (`/api/historical-market-cap/{ticker}`)."""
    if not ticker or not api_key:
        return None
    start = (datetime.date.today() - datetime.timedelta(days=max(365, years * 366))).isoformat()
    url = (
        f"https://eodhd.com/api/historical-market-cap/{urllib.parse.quote(ticker)}"
        f"?from={start}&api_token={urllib.parse.quote(api_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            raw = resp.json()
    except Exception as exc:
        _logger.debug("Erreur historical-market-cap EODHD (%s): %s", ticker, exc)
        return None

    items = list(raw.values()) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    points: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        dt = str(item.get("date") or "").strip()[:10]
        val = _fnum(item.get("value"))
        if dt and val is not None and val > 0:
            points.append({"date": dt, "value": round(val, 2)})

    points.sort(key=lambda p: p["date"])
    if not points:
        return None

    vals = [p["value"] for p in points]
    # Échantillonner au plus ~60 points pour l'affichage SVG & JSON compact
    if len(points) > 60:
        step = len(points) / 60.0
        sampled = [points[int(i * step)] for i in range(59)] + [points[-1]]
    else:
        sampled = points

    return {
        "latest_value": vals[-1],
        "latest_date": points[-1]["date"],
        "min_value": min(vals),
        "max_value": max(vals),
        "points": sampled,
    }


async def fetch_eodhd_earnings_calendar(
    ticker: str,
    api_key: str,
) -> list[dict[str, Any]] | None:
    """Récupère les prochaines et récentes publications du calendrier (`/api/calendar/earnings`)."""
    if not ticker or not api_key:
        return None
    today = datetime.date.today()
    from_dt = (today - datetime.timedelta(days=120)).isoformat()
    to_dt = (today + datetime.timedelta(days=180)).isoformat()
    url = (
        f"https://eodhd.com/api/calendar/earnings?symbols={urllib.parse.quote(ticker)}"
        f"&from={from_dt}&to={to_dt}&api_token={urllib.parse.quote(api_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            raw = resp.json()
    except Exception as exc:
        _logger.debug("Erreur calendar/earnings EODHD (%s): %s", ticker, exc)
        return None

    entries = raw.get("earnings") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
    if not isinstance(entries, list):
        return None

    out: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        rep_dt = str(item.get("report_date") or "").strip()[:10]
        fiscal_dt = str(item.get("date") or "").strip()[:10]
        if not (rep_dt or fiscal_dt):
            continue
        out.append({
            "report_date": rep_dt,
            "fiscal_date": fiscal_dt,
            "timing": str(item.get("before_after_market") or "").strip(),
            "currency": str(item.get("currency") or "").strip(),
            "estimate": _fnum(item.get("estimate")),
            "actual": _fnum(item.get("actual")),
            "difference": _fnum(item.get("difference")),
            "surprise_pct": _fnum(item.get("percent")),
        })

    out.sort(key=lambda r: r.get("report_date") or r.get("fiscal_date") or "", reverse=True)
    return out[:12]


async def fetch_eodhd_insider_transactions(
    ticker: str,
    api_key: str,
    limit: int = 40,
) -> list[dict[str, Any]] | None:
    """Récupère les transactions d'initiés SEC Form 4 (`/api/insider-transactions`)."""
    if not ticker or not api_key:
        return None
    url = (
        f"https://eodhd.com/api/insider-transactions?code={urllib.parse.quote(ticker)}"
        f"&limit={max(1, min(limit, 100))}&api_token={urllib.parse.quote(api_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            raw = resp.json()
    except Exception as exc:
        _logger.debug("Erreur insider-transactions EODHD (%s): %s", ticker, exc)
        return None

    if not isinstance(raw, list):
        return None

    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        dt = str(item.get("transactionDate") or item.get("date") or "").strip()[:10]
        name = str(item.get("ownerName") or "").strip()
        if not name:
            continue
        tx_code = str(item.get("transactionCode") or "").strip().upper()
        acq_disp = str(item.get("transactionAcquiredDisposed") or "").strip().upper()
        is_sale = tx_code == "S" or acq_disp == "D"
        is_buy = tx_code == "P" or acq_disp == "A"
        shares = _fnum(item.get("transactionAmount"))
        price_tx = _fnum(item.get("transactionPrice"))
        amount = (shares * price_tx) if (shares is not None and price_tx is not None) else None
        signed = (-abs(amount) if is_sale else abs(amount)) if (amount is not None and (is_sale or is_buy)) else None
        action = "Vente" if is_sale else ("Achat" if is_buy else (tx_code or "Opération"))
        out.append({
            "date": dt,
            "name": name,
            "relation": str(item.get("ownerTitle") or item.get("ownerRelationship") or "").strip(),
            "action": action,
            "shares": shares,
            "price": price_tx,
            "amount": amount,
            "signed_amount": signed,
        })

    out.sort(key=lambda r: r.get("date") or "", reverse=True)
    return out[:30]


async def fetch_eodhd_macro_context(
    country_iso3: str,
    api_key: str,
) -> dict[str, Any] | None:
    """Récupère les indicateurs macroéconomiques + taux sans risque US Treasury."""
    if not api_key:
        return None
    country = (country_iso3 or "USA").strip().upper()
    year = datetime.date.today().year

    async def _fetch_indicator(client: httpx.AsyncClient, indicator: str) -> dict[str, Any] | None:
        url = (
            f"https://eodhd.com/api/macro-indicator/{urllib.parse.quote(country)}"
            f"?indicator={indicator}&api_token={urllib.parse.quote(api_key)}&fmt=json"
        )
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            arr = resp.json()
            if not isinstance(arr, list) or not arr:
                return None
            valid = [x for x in arr if isinstance(x, dict) and _fnum(x.get("Value")) is not None]
            if not valid:
                return None
            valid.sort(key=lambda x: str(x.get("Date") or ""))
            latest = valid[-1]
            return {
                "value": round(float(_fnum(latest.get("Value")) or 0.0), 2),
                "date": str(latest.get("Date") or "")[:10],
                "country": str(latest.get("CountryName") or country),
            }
        except Exception:
            return None

    async def _fetch_ust_rate(client: httpx.AsyncClient) -> dict[str, Any] | None:
        url = (
            f"https://eodhd.com/api/ust/bill-rates"
            f"?filter[year]={year}&api_token={urllib.parse.quote(api_key)}&fmt=json"
        )
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            raw = resp.json()
            rows = raw.get("data") if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
            if not isinstance(rows, list) or not rows:
                return None
            rows_sorted = sorted(
                (r for r in rows if isinstance(r, dict) and r.get("date")),
                key=lambda r: str(r.get("date") or ""),
            )
            if not rows_sorted:
                return None
            latest = rows_sorted[-1]
            r_52w = _fnum(latest.get("close_52wk_coupon_equivalent"))
            r_13w = _fnum(latest.get("close_13wk_coupon_equivalent"))
            r_4wk = _fnum(latest.get("close_4wk_coupon_equivalent")) or _fnum(
                latest.get("round_b1_close_4wk_bank_discount_rate")
            )
            rf = r_52w if r_52w is not None else (r_13w if r_13w is not None else r_4wk)
            if rf is None:
                return None
            return {
                "date": str(latest.get("date") or "")[:10],
                "rate_52w_pct": round(r_52w, 2) if r_52w is not None else None,
                "rate_13w_pct": round(r_13w, 2) if r_13w is not None else None,
                "rate_4wk_pct": round(r_4wk, 2) if r_4wk is not None else None,
                "risk_free_pct": round(rf, 2),
            }
        except Exception:
            return None

    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
        gdp, inflation, unemp, ust = await asyncio.gather(
            _fetch_indicator(client, "gdp_growth_annual"),
            _fetch_indicator(client, "inflation_consumer_prices_annual"),
            _fetch_indicator(client, "unemployment_total_percent"),
            _fetch_ust_rate(client),
        )

    if not any((gdp, inflation, unemp, ust)):
        return None

    return {
        "country_iso3": country,
        "country_name": (gdp or inflation or unemp or {}).get("country") or country,
        "gdp_growth_pct": gdp,
        "inflation_pct": inflation,
        "unemployment_pct": unemp,
        "us_treasury": ust,
    }
