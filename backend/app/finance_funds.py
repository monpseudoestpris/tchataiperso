"""Catalogue des fonds européens EODHD (`EUFUND`), recherche par ISIN / `type=fund` et extraction du profil fonds."""

from __future__ import annotations

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
    replace_exchange_symbols,
    search_exchange_symbols,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_EUFUND_TTL_SEC = 7 * 24 * 3600


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


def _normalize_eufund_rows(raw: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        code = str(item.get("Code") or "").strip().upper()
        if not code:
            continue
        bare_code = code.split(".", 1)[0]
        eod_ticker = code if "." in code else f"{code}.EUFUND"
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
                "type": str(item.get("Type") or "Fund").strip(),
            }
        )
    return rows


async def sync_eufund_catalog_if_needed(
    settings: Settings,
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], str]:
    """Synchronise `/api/exchange-symbol-list/EUFUND` dans l'entrepôt SQLite si absent ou périmé."""
    db_path = warehouse_db_path(settings)
    meta = get_exchange_catalog_meta(db_path, "EUFUND")
    is_fresh = bool(
        meta["total"] > 0
        and meta["fetched_at"] is not None
        and (time.time() - float(meta["fetched_at"])) <= _EUFUND_TTL_SEC
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

    url = f"https://eodhd.com/api/exchange-symbol-list/EUFUND?api_token={urllib.parse.quote(eod_key)}&fmt=json"
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=35.0,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                raw = resp.json()
                if isinstance(raw, list) and raw:
                    rows = _normalize_eufund_rows(raw)
                    if rows:
                        replace_exchange_symbols(db_path, "EUFUND", rows)
                        updated_meta = get_exchange_catalog_meta(db_path, "EUFUND")
                        return updated_meta, "EODHD EUFUND API"
            else:
                _logger.warning("EODHD EUFUND catalog HTTP %s", resp.status_code)
    except Exception as exc:
        _logger.warning("Échec synchronisation catalogue EUFUND EODHD: %s", exc)

    if meta["total"] > 0:
        return meta, "Entrepôt SQLite (secours)"
    return meta, "Indisponible"


async def list_eufund_catalog(
    settings: Settings,
    *,
    query: str = "",
    currency: str = "",
    country: str = "",
    limit: int = 60,
    offset: int = 0,
    refresh: bool = False,
) -> dict[str, Any]:
    """Liste et filtre les fonds européens EODHD (`EUFUND`) depuis l'entrepôt SQLite."""
    meta, source = await sync_eufund_catalog_if_needed(settings, refresh=refresh)
    db_path = warehouse_db_path(settings)
    search_res = search_exchange_symbols(
        db_path,
        "EUFUND",
        query=query,
        currency=currency,
        country=country,
        limit=limit,
        offset=offset,
    )
    return {
        "exchange": "EUFUND",
        "total": meta["total"],
        "matched": search_res["matched"],
        "offset": max(0, int(offset or 0)),
        "limit": max(1, min(300, int(limit or 60))),
        "source": source,
        "synced_at": _iso_from_ts(meta["fetched_at"]),
        "currencies": meta["currencies"],
        "countries": meta["countries"],
        "items": search_res["items"],
    }


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
