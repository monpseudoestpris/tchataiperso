"""Moteur complet du Dossier Boursier Unifié (style fiche fondamentale institutionnelle).

Agrège les données EODHD (prioritaire) et Yahoo Finance (backup) stockées dans
`finance_warehouse.db` sur jusqu'à 10+ ans d'historique pour calculer :
- Synthèse & dynamique du cours (MMA50/MMA200, catégorie de capitalisation)
- Capital, flottant, VAD, valorisation & rentabilité TTM
- Performances boursières ajustées des dividendes (1 mois -> 10 ans)
- Gestion du risque (Volatilité, Semi-volatilité, Max Drawdown, VaR/CVaR 95%, Ulcer, Sharpe, Sortino, Calmar, Martin)
- Parties prenantes (Analystes, Direction, Initiés, Top Fonds & Institutionnels)
- Ratios multi-annuels (Profitabilité, Solvabilité, Distribution, Cycle de conversion & efficacité)
- Scores qualitatifs (IH Score /9 + tendance, F-Score Piotroski, Z-Score Altman)
- Matrice mensuelle des dividendes détachés & comptes annuels/trimestriels simplifiés
- Synthèse éditoriale générée par IA à partir des chiffres vérifiés
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import math
import statistics
import urllib.parse
from typing import Any

import httpx

from .config import Settings
from .finance_eodhd_usage import record_eodhd_call
from .finance_eodhd_extras import (
    fetch_eodhd_earnings_calendar,
    fetch_eodhd_historical_mcap,
    fetch_eodhd_insider_transactions,
    fetch_eodhd_macro_context,
    fetch_eodhd_sentiments,
    resolve_country_iso3,
    resolve_eodhd_logo_url,
)
from .finance_intrinsic import compute_intrinsic_valuations
from .finance_scores import compute_uncle_stock_scores
from .finance_uncle_stock_catalog import compute_uncle_stock_catalog
from .finance_news import _deduplicate_articles, fetch_eodhd_news, fetch_yahoo_symbol_news
from .finance_provider import (
    fetch_eodhd_fundamentals_json,
    get_unified_financial_statements,
    persist_eodhd_fundamentals_to_warehouse,
    resolve_candidate_eod_tickers,
)
from .finance_report_html import build_classy_report_html, extract_report_highlights
from .finance_warehouse import (
    get_instrument_eod_sync_info,
    get_latest_bar_date,
    get_snapshot,
    get_stored_eod_bars,
    get_warehouse_stats,
    has_ai_analysis_for,
    is_eod_fresh_today,
    list_ai_analyses,
    load_fundamental_series,
    resolve_canonical_symbol,
    save_ai_analysis_entry,
    save_snapshot,
    upsert_eod_bars,
    upsert_instrument,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, dict):
        val = val.get("raw")
    if isinstance(val, (int, float)):
        f = float(val)
        return f if math.isfinite(f) else None
    if isinstance(val, str):
        s = val.strip().replace("\xa0", "").replace(" ", "")
        if not s or s.upper() in {"NA", "N/A", "NONE", "NULL", "-"}:
            return None
        try:
            f = float(s)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def _div(a: float | None, b: float | None, scale: float = 1.0, digits: int = 2) -> float | None:
    if a is None or b is None or b == 0:
        return None
    val = (a / b) * scale
    return round(val, digits) if math.isfinite(val) else None


def _yoy_list(values: list[float | None], step: int = 1) -> list[float | None]:
    out: list[float | None] = []
    for i, cur in enumerate(values):
        prev = values[i - step] if i >= step else None
        if cur is None or prev is None or prev == 0:
            out.append(None)
        else:
            out.append(round(((cur - prev) / abs(prev)) * 100.0, 1))
    return out


def _cap_category(market_cap: float | None) -> str:
    if market_cap is None:
        return "Non classé"
    if market_cap >= 200e9:
        return "Méga-Cap"
    if market_cap >= 10e9:
        return "Large-Cap"
    if market_cap >= 2e9:
        return "Mid-Cap"
    if market_cap >= 300e6:
        return "Small-Cap"
    return "Micro-Cap"


def _candidate_eod_tickers(symbol: str) -> list[str]:
    clean = symbol.strip().upper()
    if not clean:
        return []
    if "." in clean:
        return [clean]
    if clean.startswith("^"):
        return [f"{clean[1:]}.INDX"]
    return [f"{clean}.US", clean]


async def _fetch_eodhd_bars_range(ticker: str, api_key: str, from_date: str) -> list[dict[str, Any]]:
    if not api_key or not ticker:
        return []
    url = (
        f"https://eodhd.com/api/eod/{urllib.parse.quote(ticker)}"
        f"?from={urllib.parse.quote(from_date)}&order=a&fmt=json&api_token={urllib.parse.quote(api_key)}"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=20.0
        ) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return [
                        {
                            "date": str(b.get("date") or "")[:10],
                            "open": _num(b.get("open")),
                            "high": _num(b.get("high")),
                            "low": _num(b.get("low")),
                            "close": _num(b.get("close")),
                            "adjusted_close": _num(b.get("adjusted_close") or b.get("close")),
                            "volume": _num(b.get("volume")),
                        }
                        for b in data
                        if isinstance(b, dict) and b.get("date")
                    ]
    except Exception as exc:
        _logger.warning("Erreur /api/eod plage longue (%s): %s", ticker, exc)
    return []


async def _fetch_eodhd_dividends(ticker: str, api_key: str) -> list[dict[str, Any]] | None:
    if not api_key or not ticker:
        return None
    url = (
        f"https://eodhd.com/api/div/{urllib.parse.quote(ticker)}"
        f"?from=1985-01-01&fmt=json&api_token={urllib.parse.quote(api_key)}"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=15.0
        ) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return [
                        {
                            "date": str(d.get("date") or "")[:10],
                            "value": _num(d.get("value")),
                            "unadjusted": _num(d.get("unadjustedValue")),
                            "currency": str(d.get("currency") or "").strip(),
                        }
                        for d in data
                        if isinstance(d, dict) and d.get("date") and _num(d.get("value")) is not None
                    ]
    except Exception as exc:
        _logger.warning("Erreur /api/div (%s): %s", ticker, exc)
    return None


async def _fetch_yahoo_chart_10y(yahoo_symbol: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    url = (
        f"https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(yahoo_symbol)}"
        "?range=10y&interval=1d&events=div"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT}, follow_redirects=True, timeout=20.0
        ) as client:
            record_eodhd_call(url)
            resp = await client.get(url)
            if resp.status_code != 200:
                return [], []
            res = (resp.json().get("chart") or {}).get("result") or []
            if not res:
                return [], []
            item = res[0]
            ts = item.get("timestamp") or []
            quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
            adj = (((item.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
            opens, highs, lows, closes, vols = (
                quote.get("open") or [],
                quote.get("high") or [],
                quote.get("low") or [],
                quote.get("close") or [],
                quote.get("volume") or [],
            )
            bars: list[dict[str, Any]] = []
            for i, t_val in enumerate(ts):
                c_val = _num(closes[i] if i < len(closes) else None)
                if c_val is None:
                    continue
                d_str = datetime.datetime.fromtimestamp(t_val, datetime.timezone.utc).strftime("%Y-%m-%d")
                a_val = _num(adj[i] if i < len(adj) else None) or c_val
                bars.append(
                    {
                        "date": d_str,
                        "open": _num(opens[i] if i < len(opens) else None),
                        "high": _num(highs[i] if i < len(highs) else None),
                        "low": _num(lows[i] if i < len(lows) else None),
                        "close": c_val,
                        "adjusted_close": a_val,
                        "volume": _num(vols[i] if i < len(vols) else None),
                    }
                )
            divs_raw = ((item.get("events") or {}).get("dividends") or {}).values()
            divs = []
            for dv in divs_raw:
                amt = _num(dv.get("amount"))
                dt = dv.get("date")
                if amt is not None and dt is not None:
                    d_str = datetime.datetime.fromtimestamp(dt, datetime.timezone.utc).strftime("%Y-%m-%d")
                    divs.append({"date": d_str, "value": amt, "unadjusted": amt, "currency": ""})
            divs.sort(key=lambda x: x["date"])
            return bars, divs
    except Exception as exc:
        _logger.warning("Erreur Yahoo chart 10y (%s): %s", yahoo_symbol, exc)
    return [], []


async def _fetch_yahoo_extended_summary(yahoo_symbol: str) -> dict[str, Any]:
    from .finance import fetch_yahoo_quote_summary, get_yahoo_crumb_and_client

    modules = (
        "price,summaryDetail,financialData,defaultKeyStatistics,assetProfile,"
        "recommendationTrend,insiderTransactions,institutionOwnership,fundOwnership,majorHoldersBreakdown"
    )
    try:
        client, crumb = await get_yahoo_crumb_and_client()
        try:
            url = (
                f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
                f"{urllib.parse.quote(yahoo_symbol)}?modules={modules}"
            )
            if crumb:
                url += f"&crumb={urllib.parse.quote(crumb)}"
            record_eodhd_call(url)
            resp = await client.get(url)
            if resp.status_code == 200:
                res = (resp.json().get("quoteSummary") or {}).get("result") or []
                if res:
                    return res[0]
            # Fallback sur les 5 modules standards si les modules étendus sont refusés
            return (await fetch_yahoo_quote_summary(client, yahoo_symbol, crumb=crumb)) or {}
        finally:
            await client.aclose()
    except Exception as exc:
        _logger.warning("Erreur Yahoo extended summary (%s): %s", yahoo_symbol, exc)
        return {}


def compute_price_performance_and_risk(
    bars: list[dict[str, Any]],
    currency: str = "USD",
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Calcule la performance ajustée des dividendes (1M -> 10A) et la gestion du risque (1A -> 5A)."""
    pts: list[tuple[datetime.date, float, float]] = []
    for b in bars:
        d_raw = str(b.get("date") or "")[:10]
        adj = _num(b.get("adjusted_close")) or _num(b.get("close"))
        raw_c = _num(b.get("close")) or adj
        if not d_raw or adj is None or adj <= 0 or raw_c is None:
            continue
        try:
            dt = datetime.date.fromisoformat(d_raw)
        except ValueError:
            continue
        pts.append((dt, raw_c, adj))

    if len(pts) < 2:
        return {"horizons": []}, {"horizons": [], "metrics": []}, []

    pts.sort(key=lambda x: x[0])
    last_dt, last_raw, last_adj = pts[-1]

    def _find_anchor(days_back: int) -> tuple[datetime.date, float, float] | None:
        target = last_dt - datetime.timedelta(days=days_back)
        if pts[0][0] > target + datetime.timedelta(days=15):
            return None
        best = pts[0]
        for item in pts:
            if item[0] <= target:
                best = item
            else:
                break
        return best

    horizon_defs = [
        ("1m", "1 mois", 30),
        ("2m", "2 mois", 61),
        ("3m", "3 mois", 91),
        ("6m", "6 mois", 183),
        ("1y", "1 an", 365),
        ("2y", "2 ans", 730),
        ("3y", "3 ans", 1095),
        ("4y", "4 ans", 1461),
        ("5y", "5 ans", 1826),
        ("6y", "6 ans", 2191),
        ("7y", "7 ans", 2556),
        ("8y", "8 ans", 2922),
        ("9y", "9 ans", 3287),
        ("10y", "10 ans", 3652),
    ]
    perf_horizons: list[dict[str, Any]] = []
    for key, label, days in horizon_defs:
        anc = _find_anchor(days)
        pct = round(((last_adj - anc[2]) / anc[2]) * 100.0, 1) if anc and anc[2] > 0 else None
        perf_horizons.append({"key": key, "label": label, "pct": pct})

    # Série mensuelle échantillonnée pour le graphique de performance ajustée
    monthly_chart: list[dict[str, Any]] = []
    seen_ym: set[str] = set()
    base_adj = pts[0][2]
    for dt, raw_c, adj_c in pts:
        ym = dt.strftime("%Y-%m")
        if ym not in seen_ym or dt == last_dt:
            seen_ym.add(ym)
            monthly_chart.append(
                {
                    "date": dt.isoformat(),
                    "price": round(raw_c, 2),
                    "adj_price": round(adj_c, 2),
                    "index_100": round((adj_c / base_adj) * 100.0, 2) if base_adj > 0 else 100.0,
                }
            )

    # Taux sans risque annualisés moyens sur 1..5 ans selon la devise
    rf_rates = (
        [0.035, 0.039, 0.044, 0.045, 0.040]
        if currency.upper() == "USD"
        else [0.028, 0.030, 0.031, 0.030, 0.027]
    )
    risk_cols = [(1, "1 an"), (2, "2 ans"), (3, "3 ans"), (4, "4 ans"), (5, "5 ans")]
    risk_rows: dict[str, list[float | None]] = {
        "volatility": [],
        "semi_volatility": [],
        "max_drawdown": [],
        "max_dd_days": [],
        "var_95": [],
        "cvar_95": [],
        "ulcer": [],
        "sharpe": [],
        "sortino": [],
        "calmar": [],
        "excess_calmar": [],
        "martin": [],
    }

    for idx_y, (years, _) in enumerate(risk_cols):
        cutoff = last_dt - datetime.timedelta(days=int(years * 365.25))
        sub = [p for p in pts if p[0] >= cutoff]
        if len(sub) < 20 or (last_dt - sub[0][0]).days < years * 300:
            for k in risk_rows:
                risk_rows[k].append(None)
            continue

        rets: list[float] = []
        for i in range(1, len(sub)):
            prev_p, cur_p = sub[i - 1][2], sub[i][2]
            if prev_p > 0:
                rets.append((cur_p - prev_p) / prev_p)

        if len(rets) < 15:
            for k in risk_rows:
                risk_rows[k].append(None)
            continue

        vol = statistics.stdev(rets) * math.sqrt(252.0)
        neg_sq = [min(0.0, r) ** 2 for r in rets]
        semi_vol = math.sqrt(sum(neg_sq) / len(rets)) * math.sqrt(252.0)

        # Drawdown & durée maximale sous sommet
        peak = sub[0][2]
        peak_dt = sub[0][0]
        max_dd = 0.0
        max_dd_days = 0
        dd_sq_sum = 0.0
        for dt_i, _, p_i in sub:
            if p_i >= peak:
                peak = p_i
                peak_dt = dt_i
            dd = (peak - p_i) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
            dur = (dt_i - peak_dt).days
            if dur > max_dd_days:
                max_dd_days = dur
            dd_sq_sum += dd * dd

        ulcer = math.sqrt(dd_sq_sum / len(sub))

        sorted_rets = sorted(rets)
        var_idx = max(0, int(0.05 * len(sorted_rets)) - 1)
        var_95 = sorted_rets[var_idx]
        tail = [r for r in sorted_rets if r <= var_95]
        cvar_95 = (sum(tail) / len(tail)) if tail else var_95

        total_ret = (sub[-1][2] / sub[0][2]) - 1.0 if sub[0][2] > 0 else 0.0
        elapsed_years = max(0.5, (sub[-1][0] - sub[0][0]).days / 365.25)
        ann_ret = ((1.0 + total_ret) ** (1.0 / elapsed_years) - 1.0) if (1.0 + total_ret) > 0 else total_ret
        rf = rf_rates[idx_y]
        excess = ann_ret - rf

        risk_rows["volatility"].append(round(vol * 100.0, 1))
        risk_rows["semi_volatility"].append(round(semi_vol * 100.0, 1))
        risk_rows["max_drawdown"].append(round(max_dd * 100.0, 1))
        risk_rows["max_dd_days"].append(float(max_dd_days))
        risk_rows["var_95"].append(round(var_95 * 100.0, 1))
        risk_rows["cvar_95"].append(round(cvar_95 * 100.0, 1))
        risk_rows["ulcer"].append(round(ulcer * 100.0, 1))
        risk_rows["sharpe"].append(round(excess / vol, 2) if vol > 0 else None)
        risk_rows["sortino"].append(round(excess / semi_vol, 2) if semi_vol > 0 else None)
        risk_rows["calmar"].append(round(ann_ret / max_dd, 2) if max_dd > 0 else None)
        risk_rows["excess_calmar"].append(round(excess / max_dd, 2) if max_dd > 0 else None)
        risk_rows["martin"].append(round(excess / ulcer, 2) if ulcer > 0 else None)

    risk_defs = [
        ("volatility", "Volatilité historique (annualisée)", "pct", "stat"),
        ("semi_volatility", "Semi-volatilité (baisses)", "pct", "stat"),
        ("max_drawdown", "Max Drawdown (perte max. depuis sommet)", "pct", "stat"),
        ("max_dd_days", "Durée max. sous un sommet", "days", "stat"),
        ("var_95", "VaR 95% (perte journalière potentielle)", "pct", "stat"),
        ("cvar_95", "CVaR 95% (perte moyenne au-delà VaR)", "pct", "stat"),
        ("ulcer", "Ulcer Index (repli moyen)", "pct", "stat"),
        ("sharpe", "Ratio de Sharpe", "ratio", "ratio"),
        ("sortino", "Ratio de Sortino", "ratio", "ratio"),
        ("calmar", "Ratio de Calmar", "ratio", "ratio"),
        ("excess_calmar", "Excess Calmar", "ratio", "ratio"),
        ("martin", "Ratio de Martin", "ratio", "ratio"),
    ]
    risk_payload = {
        "horizons": [lbl for _, lbl in risk_cols],
        "rf_rates_pct": [round(r * 100.0, 1) for r in rf_rates],
        "metrics": [
            {"key": k, "label": lbl, "format": fmt, "group": grp, "values": risk_rows[k]}
            for k, lbl, fmt, grp in risk_defs
        ],
    }
    return {"horizons": perf_horizons}, risk_payload, monthly_chart


def _build_dividends_matrix(dividends: list[dict[str, Any]]) -> dict[str, Any]:
    if not dividends:
        return {"years": [], "rows": []}
    by_year: dict[int, list[float]] = {}
    for d in dividends:
        d_str = str(d.get("date") or "")[:10]
        val = _num(d.get("value"))
        if len(d_str) < 7 or val is None:
            continue
        try:
            yr = int(d_str[:4])
            mo = int(d_str[5:7])
        except ValueError:
            continue
        if not (1 <= mo <= 12):
            continue
        months = by_year.setdefault(yr, [0.0] * 12)
        months[mo - 1] = round(months[mo - 1] + val, 4)

    rows = []
    for yr in sorted(by_year.keys(), reverse=True):
        months = [round(v, 3) if v > 0 else None for v in by_year[yr]]
        tot = round(sum(v for v in by_year[yr]), 3)
        rows.append({"year": yr, "months": months, "total": tot if tot > 0 else None})
    return {"years": [r["year"] for r in rows], "rows": rows}


def _year_close_price_map(bars: list[dict[str, Any]]) -> dict[str, float]:
    """Renvoie le dernier cours de clôture non ajusté disponible par année (YYYY)."""
    by_year: dict[str, float] = {}
    for b in bars:
        d_str = str(b.get("date") or "")[:10]
        c_val = _num(b.get("close")) or _num(b.get("adjusted_close"))
        if len(d_str) >= 4 and c_val is not None:
            by_year[d_str[:4]] = c_val
    return by_year


def _dedupe_annual_series_by_year(
    ann_series: dict[str, dict[str, float | None]],
) -> tuple[dict[str, dict[str, float | None]], list[str]]:
    """Regroupe les dates annuelles par année fiscale YYYY (fusionne les écarts de date EODHD/Yahoo)."""
    raw_dates = sorted({d for vals in ann_series.values() for d, v in vals.items() if v is not None})
    if not raw_dates:
        return {}, []
    year_to_dates: dict[str, list[str]] = {}
    for d in raw_dates:
        year_to_dates.setdefault(d[:4], []).append(d)

    deduped_dates: list[str] = []
    merged_series: dict[str, dict[str, float | None]] = {}
    for yr in sorted(year_to_dates.keys()):
        yr_dates = year_to_dates[yr]
        canon_date = yr_dates[-1]
        deduped_dates.append(canon_date)
        for metric_key, date_map in ann_series.items():
            chosen: float | None = None
            for d in yr_dates:
                v = date_map.get(d)
                if v is not None:
                    chosen = v
            if chosen is not None:
                merged_series.setdefault(metric_key, {})[canon_date] = chosen
    return merged_series, deduped_dates


def _compute_annual_dossier_tables(
    ann_series: dict[str, dict[str, float | None]],
    bars: list[dict[str, Any]],
    beta_val: float | None,
) -> dict[str, Any]:
    """Calcule tous les tableaux de ratios, scores (IH, Piotroski, Altman) et synthèses annuelles."""
    ann_series, dates = _dedupe_annual_series_by_year(ann_series)
    if not dates:
        return {
            "years": [],
            "dates": [],
            "summary": [],
            "profitability": [],
            "solvency": [],
            "distribution": [],
            "efficiency": [],
            "ih_score": {"years": [], "criteria": [], "scores": [], "trend_criteria": [], "latest_score": None, "trend": "Neutre"},
            "piotroski": {"years": [], "criteria": [], "scores": [], "latest_score": None},
            "altman": {"years": [], "criteria": [], "scores": [], "latest_score": None},
        }

    years = [d[:4] for d in dates]
    year_prices = _year_close_price_map(bars)

    def at(key: str, i: int) -> float | None:
        return (ann_series.get(key) or {}).get(dates[i])

    def avg2(key: str, i: int) -> float | None:
        cur = at(key, i)
        prev = at(key, i - 1) if i > 0 else None
        if cur is not None and prev is not None:
            return (cur + prev) / 2.0
        return None

    # Extraction des vecteurs annuels en unités brutes (puis formatage côté UI)
    rev_l, gp_l, ebitda_l, ebit_l, opinc_l, pretax_l, tax_l, ni_l = [], [], [], [], [], [], [], []
    ocf_l, capex_l, fcf_l, div_paid_l, shares_l = [], [], [], [], []
    assets_l, ca_l, cash_st_l, cash_pure_l, rec_l, inv_l = [], [], [], [], [], []
    cl_l, ap_l, def_rev_cur_l, st_debt_l, lt_debt_l, tot_debt_l, net_debt_l, liab_l, eq_l, ret_earn_l, wc_l = (
        [], [], [], [], [], [], [], [], [], [], []
    )
    sga_l, int_exp_l, cost_rev_l = [], [], []

    for i in range(len(dates)):
        rev = at("TotalRevenue", i)
        cost = at("CostOfRevenue", i)
        gp = at("GrossProfit", i)
        if gp is None and rev is not None and cost is not None:
            gp = rev - abs(cost)
        opinc = at("OperatingIncome", i) or at("EBIT", i)
        ebit = at("EBIT", i) or opinc
        ebitda = at("EBITDA", i)
        pretax = at("PretaxIncome", i)
        tax = at("TaxProvision", i)
        ni = at("NetIncome", i)
        ocf = at("OperatingCashFlow", i)
        capex = at("CapitalExpenditure", i)
        fcf = at("FreeCashFlow", i)
        if fcf is None and ocf is not None and capex is not None:
            fcf = ocf - abs(capex)
        div_paid = at("CashDividendsPaid", i)
        shares = at("CommonStockSharesOutstanding", i) or at("DilutedAverageShares", i)

        assets = at("TotalAssets", i)
        ca = at("CurrentAssets", i)
        cash_pure = at("CashAndCashEquivalents", i)
        cash_st = at("CashCashEquivalentsAndShortTermInvestments", i)
        if cash_st is None:
            cash_st = cash_pure
        rec = at("AccountsReceivable", i)
        inv = at("Inventory", i)
        cl = at("CurrentLiabilities", i)
        ap = at("AccountsPayable", i)
        def_rev_cur = at("CurrentDeferredRevenue", i)
        st_d = at("ShortTermDebt", i) or at("CurrentDebt", i)
        lt_d = at("LongTermDebt", i)
        tot_d = at("TotalDebt", i)
        if tot_d is None and (st_d is not None or lt_d is not None):
            tot_d = (st_d or 0.0) + (lt_d or 0.0)
        if tot_d is None and assets is not None:
            tot_d = 0.0
        net_d = at("NetDebt", i)
        if net_d is None and tot_d is not None and cash_st is not None:
            net_d = tot_d - cash_st
        liab = at("TotalLiabilitiesNetMinorityInterest", i)
        eq = at("StockholdersEquity", i)
        ret_e = at("RetainedEarnings", i)
        wc = at("WorkingCapital", i)
        if wc is None and ca is not None and cl is not None:
            wc = ca - cl

        rev_l.append(rev); gp_l.append(gp); ebitda_l.append(ebitda); ebit_l.append(ebit); opinc_l.append(opinc)
        pretax_l.append(pretax); tax_l.append(tax); ni_l.append(ni)
        ocf_l.append(ocf); capex_l.append(capex); fcf_l.append(fcf); div_paid_l.append(div_paid); shares_l.append(shares)
        assets_l.append(assets); ca_l.append(ca); cash_st_l.append(cash_st); cash_pure_l.append(cash_pure); rec_l.append(rec); inv_l.append(inv)
        cl_l.append(cl); ap_l.append(ap); def_rev_cur_l.append(def_rev_cur); st_debt_l.append(st_d); lt_debt_l.append(lt_d)
        tot_debt_l.append(tot_d); net_debt_l.append(net_d); liab_l.append(liab); eq_l.append(eq); ret_earn_l.append(ret_e); wc_l.append(wc)
        sga_l.append(at("SellingGeneralAndAdministration", i))
        int_exp_l.append(at("InterestExpense", i))
        cost_rev_l.append(cost)

    # Grandeurs dérivées par exercice
    tax_rate_l: list[float | None] = []
    nopat_l: list[float | None] = []
    cap_inv_l: list[float | None] = []
    roic_l: list[float | None] = []
    croic_l: list[float | None] = []
    roa_l: list[float | None] = []
    roe_l: list[float | None] = []
    ebitda_ps_l: list[float | None] = []
    eps_l: list[float | None] = []
    fcf_ps_l: list[float | None] = []
    mcap_l: list[float | None] = []
    per_l: list[float | None] = []
    pb_l: list[float | None] = []

    for i in range(len(dates)):
        tr = _div(tax_l[i], pretax_l[i], scale=100.0, digits=1) if (tax_l[i] is not None and pretax_l[i] and pretax_l[i] > 0) else None
        if tr is not None:
            tr = max(0.0, min(50.0, tr))
        tax_rate_l.append(tr)
        if opinc_l[i] is not None and tr is not None:
            nopat = opinc_l[i] * (1.0 - (tr / 100.0))
        else:
            nopat = ni_l[i] if ni_l[i] is not None else opinc_l[i]
        nopat_l.append(nopat)

        ci = (eq_l[i] + tot_debt_l[i]) if (eq_l[i] is not None and tot_debt_l[i] is not None) else eq_l[i]
        cap_inv_l.append(ci)

    for i in range(len(dates)):
        avg_ci = (
            (cap_inv_l[i] + cap_inv_l[i - 1]) / 2.0
            if (i > 0 and cap_inv_l[i] is not None and cap_inv_l[i - 1] is not None)
            else None
        )
        roic_l.append(_div(nopat_l[i], avg_ci, scale=100.0, digits=1))
        croic_l.append(_div(fcf_l[i], avg_ci, scale=100.0, digits=1))
        roa_l.append(_div(ni_l[i], avg2("TotalAssets", i), scale=100.0, digits=1))
        roe_l.append(_div(ni_l[i], avg2("StockholdersEquity", i), scale=100.0, digits=1))

        sh = shares_l[i]
        ebitda_ps_l.append(_div(ebitda_l[i], sh, digits=2))
        eps_val = at("DilutedEPS", i) or _div(ni_l[i], sh, digits=2)
        eps_l.append(eps_val)
        fcf_ps_l.append(_div(fcf_l[i], sh, digits=2))

        yr_price = year_prices.get(years[i])
        mcap = (yr_price * sh) if (yr_price is not None and sh is not None and sh > 0) else None
        mcap_l.append(mcap)
        per_l.append(_div(yr_price, eps_val, digits=1) if (yr_price and eps_val and eps_val > 0) else None)
        pb_l.append(_div(mcap, eq_l[i], digits=1) if (mcap and eq_l[i] and eq_l[i] > 0) else None)

    def mk_row(key: str, label: str, fmt: str, vals: list[float | None]) -> dict[str, Any]:
        return {"key": key, "label": label, "format": fmt, "values": vals, "yoy": _yoy_list(vals)}

    # Marges
    gross_m = [_div(gp_l[i], rev_l[i], 100.0, 1) for i in range(len(dates))]
    ebitda_m = [_div(ebitda_l[i], rev_l[i], 100.0, 1) for i in range(len(dates))]
    op_m = [_div(opinc_l[i], rev_l[i], 100.0, 1) for i in range(len(dates))]
    net_m = [_div(ni_l[i], rev_l[i], 100.0, 1) for i in range(len(dates))]
    fcf_m = [_div(fcf_l[i], rev_l[i], 100.0, 1) for i in range(len(dates))]

    summary_rows = [
        mk_row("rev", "Chiffre d'affaires", "amount", rev_l),
        mk_row("ebitda", "EBITDA", "amount", ebitda_l),
        mk_row("opinc", "Résultat opérationnel", "amount", opinc_l),
        mk_row("ni", "Résultat net", "amount", ni_l),
        mk_row("fcf", "Flux de trésorerie libre (FCF)", "amount", fcf_l),
        mk_row("fcf_m", "Marge de FCF", "pct", fcf_m),
        mk_row("roic", "ROIC", "pct", roic_l),
        mk_row("croic", "CROIC", "pct", croic_l),
        mk_row("tax_rate", "Taux d'imposition", "pct", tax_rate_l),
        mk_row("cap_inv", "Capital investi", "amount", cap_inv_l),
        mk_row("shares", "Actions en circulation", "shares", shares_l),
        mk_row("ebitda_ps", "EBITDA par action", "num", ebitda_ps_l),
        mk_row("eps", "Bénéfice par action", "num", eps_l),
        mk_row("fcf_ps", "Free Cash Flow par action", "num", fcf_ps_l),
        mk_row("per", "PER (fin d'exercice)", "x", per_l),
        mk_row("pb", "P/B (cours / capitaux propres)", "x", pb_l),
        mk_row("mcap", "Capitalisation boursière", "amount", mcap_l),
        mk_row("eq", "Capitaux propres", "amount", eq_l),
    ]

    profitability_rows = [
        mk_row("gross_m", "Marge brute", "pct", gross_m),
        mk_row("ebitda_m", "Marge d'EBITDA", "pct", ebitda_m),
        mk_row("op_m", "Marge opérationnelle", "pct", op_m),
        mk_row("net_m", "Marge bénéficiaire", "pct", net_m),
        mk_row("fcf_m", "Marge de FCF", "pct", fcf_m),
        mk_row("roa", "Rentabilité économique (ROA)", "pct", roa_l),
        mk_row("roe", "Rentabilité financière (ROE)", "pct", roe_l),
        mk_row("roic", "Rdt sur capital investi (ROIC)", "pct", roic_l),
        mk_row("croic", "FCF sur capital investi (CROIC)", "pct", croic_l),
    ]

    # Solvabilité
    quick_ratio_l: list[float | None] = []
    curr_ratio_l: list[float | None] = []
    nd_ebitda_l: list[float | None] = []
    debt_assets_l: list[float | None] = []
    debt_eq_l: list[float | None] = []
    cov_ebitda_l: list[float | None] = []
    cov_ebit_l: list[float | None] = []
    cov_ocf_l: list[float | None] = []
    cost_debt_l: list[float | None] = []

    for i in range(len(dates)):
        # Uncle Stock Quick ratio = (Total cash and equivalents + Total receivables) / Current liabilities
        # (repli sur (CurrentAssets - Inventory) / CurrentLiabilities si détail créances absent)
        cash_q = cash_pure_l[i] if cash_pure_l[i] is not None else cash_st_l[i]
        if cl_l[i] and cl_l[i] > 0:
            if cash_q is not None and rec_l[i] is not None:
                quick_num = cash_q + rec_l[i]
            elif ca_l[i] is not None:
                quick_num = ca_l[i] - (inv_l[i] or 0.0)
            else:
                quick_num = None
            quick_ratio_l.append(_div(quick_num, cl_l[i], digits=2))
        else:
            quick_ratio_l.append(None)
        curr_ratio_l.append(_div(ca_l[i], cl_l[i], digits=2))
        nd_ebitda_l.append(_div(net_debt_l[i], ebitda_l[i], digits=2))
        debt_assets_l.append(_div(tot_debt_l[i], assets_l[i], 100.0, 1))
        debt_eq_l.append(_div(tot_debt_l[i], eq_l[i], 100.0, 1))
        ie = abs(int_exp_l[i]) if (int_exp_l[i] is not None and int_exp_l[i] != 0) else None
        cov_ebitda_l.append(_div(ebitda_l[i], ie, digits=1))
        cov_ebit_l.append(_div(ebit_l[i], ie, digits=1))
        cov_ocf_l.append(_div(ocf_l[i], ie, digits=1))
        avg_d = avg2("TotalDebt", i)
        if ie is not None and avg_d and avg_d > 0:
            cost_debt_l.append(_div(ie, avg_d, 100.0, 1))
        elif assets_l[i] is not None and (ie is None or tot_debt_l[i] == 0):
            cost_debt_l.append(0.0)
        else:
            cost_debt_l.append(None)

    solvency_rows = [
        mk_row("quick_r", "Liquidité restreinte", "x", quick_ratio_l),
        mk_row("curr_r", "Liquidité générale", "x", curr_ratio_l),
        mk_row("nd_ebitda", "Dette nette sur EBITDA", "x", nd_ebitda_l),
        mk_row("debt_assets", "Dette sur actifs", "pct", debt_assets_l),
        mk_row("debt_eq", "Dette sur capitaux propres", "pct", debt_eq_l),
        mk_row("cov_ebitda", "Couverture par l'EBITDA", "x", cov_ebitda_l),
        mk_row("cov_ebit", "Couverture par l'EBIT", "x", cov_ebit_l),
        mk_row("cov_ocf", "Couverture par le flux opérationnel", "x", cov_ocf_l),
        mk_row("cost_debt", "Coût de la dette", "pct", cost_debt_l),
    ]

    # Distribution
    payout_ni_l = [_div(abs(div_paid_l[i]) if div_paid_l[i] is not None else None, ni_l[i], 100.0, 1) for i in range(len(dates))]
    payout_fcf_l = [_div(abs(div_paid_l[i]) if div_paid_l[i] is not None else None, fcf_l[i], 100.0, 1) for i in range(len(dates))]
    distribution_rows = [
        mk_row("ni", "Résultat net", "amount", ni_l),
        mk_row("fcf", "Flux de trésorerie libre (FCF)", "amount", fcf_l),
        mk_row("div_paid", "Dividende payé", "amount", div_paid_l),
        mk_row("payout_ni", "Distribution sur résultat net (Payout Ratio)", "pct", payout_ni_l),
        mk_row("payout_fcf", "Distribution sur FCF (Cash Payout)", "pct", payout_fcf_l),
    ]

    # Cycle de conversion & efficacité (conformément au référentiel Uncle Stock : moyennes .yr avg)
    def avg_or_cur(vec: list[float | None], idx: int) -> float | None:
        cur = vec[idx]
        if cur is None:
            return None
        prev = vec[idx - 1] if idx > 0 else None
        return (cur + prev) / 2.0 if prev is not None else cur

    dsi_l, dso_l, dpo_l, ccc_l, asset_turn_l, sga_eq_l, sga_rev_l = [], [], [], [], [], [], []
    for i in range(len(dates)):
        cost_abs = abs(cost_rev_l[i]) if cost_rev_l[i] is not None else None
        avg_inv = avg_or_cur(inv_l, i)
        avg_rec = avg_or_cur(rec_l, i)
        avg_ap = avg_or_cur(ap_l, i)
        avg_def_rev = avg_or_cur(def_rev_cur_l, i)
        avg_assets = avg_or_cur(assets_l, i)
        dsi = _div(avg_inv, cost_abs, 365.0, 0) if (avg_inv is not None and cost_abs and cost_abs > 0) else None
        dso = _div(avg_rec, rev_l[i], 365.0, 0) if (avg_rec is not None and rev_l[i] and rev_l[i] > 0) else None
        dpo = _div(avg_ap, cost_abs, 365.0, 0) if (avg_ap is not None and cost_abs and cost_abs > 0) else None
        d_def_rev = (
            _div(avg_def_rev, rev_l[i], 365.0, 0)
            if (avg_def_rev is not None and avg_def_rev > 0 and rev_l[i] and rev_l[i] > 0)
            else 0.0
        )
        ccc = round(dsi + dso - dpo - (d_def_rev or 0.0), 0) if (dsi is not None and dso is not None and dpo is not None) else None
        dsi_l.append(dsi); dso_l.append(dso); dpo_l.append(dpo); ccc_l.append(ccc)
        asset_turn_l.append(_div(rev_l[i], avg_assets, digits=2))
        sga_abs = abs(sga_l[i]) if sga_l[i] is not None else None
        sga_eq_l.append(_div(sga_abs, eq_l[i], 100.0, 1))
        sga_rev_l.append(_div(sga_abs, rev_l[i], 100.0, 1))

    efficiency_rows = [
        mk_row("dsi", "Nbr de jours en stock (DSI)", "days", dsi_l),
        mk_row("dso", "Délai paiement clients (DSO)", "days", dso_l),
        mk_row("dpo", "Délai paiement fournisseurs (DPO)", "days", dpo_l),
        mk_row("ccc", "Conversion de l'encaisse (CCC)", "days", ccc_l),
        mk_row("asset_turn", "Rotation des actifs", "x", asset_turn_l),
        mk_row("sga_eq", "Frais généraux sur capitaux propres", "pct", sga_eq_l),
        mk_row("sga_rev", "Frais généraux sur CA", "pct", sga_rev_l),
    ]

    # Scores qualitatifs : IH Score, Piotroski F-Score, Altman Z-Score
    ih_payload = _compute_ih_score(
        years, rev_l, ebit_l, pretax_l, roic_l, croic_l, beta_val, cov_ebitda_l, cost_debt_l, op_m, net_m, fcf_m, ebitda_l
    )
    piotroski_payload = _compute_piotroski(
        years, roa_l, ocf_l, ni_l, op_m, asset_turn_l, debt_assets_l, curr_ratio_l, shares_l
    )
    altman_payload = _compute_altman(years, wc_l, ret_earn_l, ebit_l, mcap_l, liab_l, rev_l, assets_l)

    return {
        "years": years,
        "dates": dates,
        "summary": summary_rows,
        "profitability": profitability_rows,
        "solvency": solvency_rows,
        "distribution": distribution_rows,
        "efficiency": efficiency_rows,
        "ih_score": ih_payload,
        "piotroski": piotroski_payload,
        "altman": altman_payload,
    }


def _compute_ih_score(
    years: list[str],
    rev_l: list[float | None],
    ebit_l: list[float | None],
    pretax_l: list[float | None],
    roic_l: list[float | None],
    croic_l: list[float | None],
    beta_val: float | None,
    cov_ebitda_l: list[float | None],
    cost_debt_l: list[float | None],
    op_m: list[float | None],
    net_m: list[float | None],
    fcf_m: list[float | None],
    ebitda_l: list[float | None] | None = None,
) -> dict[str, Any]:
    n = len(years)
    criteria_defs = [
        ("rev_up", "CA ↗"),
        ("ebit_up", "EBIT ↗"),
        ("ebt_up", "Résultat avant impôts ↗"),
        ("roic_10", "ROIC ≥ 10%"),
        ("roic_15", "ROIC ≥ 15%"),
        ("croic_10", "CROIC ≥ 10%"),
        ("beta_ok", "Bêta ≤ 0,8"),
        ("cov_ok", "Couverture par l'EBITDA ≥ 4"),
        ("debt_cost_ok", "Coût de la dette ≤ 4,5%"),
    ]

    def _growth_pts(vec: list[float | None], i: int) -> float:
        if i == 0 or vec[i] is None or vec[i - 1] is None or vec[i - 1] == 0:
            return 0.0
        if vec[i] > vec[i - 1]:
            return 1.0
        if ((vec[i] - vec[i - 1]) / abs(vec[i - 1])) >= -0.02:
            return 0.5
        return 0.0

    matrix: dict[str, list[float]] = {k: [] for k, _ in criteria_defs}
    for i in range(n):
        matrix["rev_up"].append(_growth_pts(rev_l, i))
        matrix["ebit_up"].append(_growth_pts(ebit_l, i))
        matrix["ebt_up"].append(_growth_pts(pretax_l, i))
        matrix["roic_10"].append(1.0 if (roic_l[i] is not None and roic_l[i] >= 10.0) else 0.0)
        matrix["roic_15"].append(
            1.0 if (roic_l[i] is not None and roic_l[i] >= 15.0) else (0.5 if (roic_l[i] is not None and roic_l[i] >= 12.0) else 0.0)
        )
        matrix["croic_10"].append(1.0 if (croic_l[i] is not None and croic_l[i] >= 10.0) else 0.0)
        b_score = 0.0
        if beta_val is not None:
            if beta_val <= 0.8:
                b_score = 1.0
            elif beta_val > 1.3:
                b_score = -1.0 if i == n - 1 else 0.0
        matrix["beta_ok"].append(b_score)
        eb_val = ebitda_l[i] if ebitda_l else None
        cov_pass = (cov_ebitda_l[i] is not None and cov_ebitda_l[i] >= 4.0) or (
            cov_ebitda_l[i] is None and eb_val is not None and eb_val > 0
        )
        matrix["cov_ok"].append(1.0 if cov_pass else 0.0)
        matrix["debt_cost_ok"].append(1.0 if (cost_debt_l[i] is not None and cost_debt_l[i] <= 4.5) else 0.0)

    # Moyenne sur les 4 derniers exercices (ou disponibles)
    tail_len = min(4, n)
    criteria_rows = []
    total_score = 0.0
    for k, lbl in criteria_defs:
        vals = matrix[k]
        avg = round(sum(vals[-tail_len:]) / tail_len, 2) if tail_len > 0 else 0.0
        total_score += avg
        criteria_rows.append({"key": k, "label": lbl, "values": vals, "avg": avg})

    trend_defs = [
        ("roic_t", "ROIC → ou ↗", roic_l),
        ("croic_t", "CROIC → ou ↗", croic_l),
        ("opm_t", "Marge opérationnelle → ou ↗", op_m),
        ("nm_t", "Marge nette → ou ↗", net_m),
        ("fcfm_t", "Marge de FCF → ou ↗", fcf_m),
    ]
    trend_rows = []
    trend_sum = 0.0
    for k, lbl, vec in trend_defs:
        t_vals: list[float] = []
        for i in range(n):
            if i == 0 or vec[i] is None or vec[i - 1] is None:
                t_vals.append(0.0)
            elif vec[i] >= vec[i - 1]:
                t_vals.append(1.0)
            elif abs(vec[i] - vec[i - 1]) <= 1.0:
                t_vals.append(0.5)
            else:
                t_vals.append(0.0)
        avg = round(sum(t_vals[-tail_len:]) / tail_len, 2) if tail_len > 0 else 0.0
        trend_sum += avg
        trend_rows.append({"key": k, "label": lbl, "values": t_vals, "avg": avg})

    avg_trend = trend_sum / len(trend_defs) if trend_defs else 0.0
    trend_label = "Haussière" if avg_trend >= 0.65 else ("Stable" if avg_trend >= 0.35 else "Baissière")
    latest_score = round(max(0.0, min(9.0, total_score)), 1)
    qual = "Solide" if latest_score >= 6.0 else ("Correct" if latest_score >= 4.0 else "Fragile")
    return {
        "years": years,
        "criteria": criteria_rows,
        "trend_criteria": trend_rows,
        "latest_score": latest_score,
        "quality_label": qual,
        "trend": trend_label,
    }


def _compute_piotroski(
    years: list[str],
    roa_l: list[float | None],
    ocf_l: list[float | None],
    ni_l: list[float | None],
    op_m: list[float | None],
    asset_turn_l: list[float | None],
    debt_assets_l: list[float | None],
    curr_ratio_l: list[float | None],
    shares_l: list[float | None],
) -> dict[str, Any]:
    n = len(years)
    defs = [
        ("roa_pos", "ROA > 0"),
        ("roa_up", "ROA ↗"),
        ("cfo_pos", "CFO > 0"),
        ("cfo_gt_ni", "CFO > Résultat net"),
        ("opm_up", "Marge opérationnelle ↗"),
        ("turn_up", "Rotation des actifs ↗"),
        ("debt_down", "Dette sur actifs ↘"),
        ("liq_up", "Liquidité générale ↗"),
        ("shares_down", "Actions en circulation → ou ↘"),
    ]
    mat: dict[str, list[int]] = {k: [] for k, _ in defs}
    totals: list[int] = []
    for i in range(n):
        c1 = 1 if (roa_l[i] is not None and roa_l[i] > 0) else 0
        c2 = 1 if (i > 0 and roa_l[i] is not None and roa_l[i - 1] is not None and roa_l[i] > roa_l[i - 1]) else 0
        c3 = 1 if (ocf_l[i] is not None and ocf_l[i] > 0) else 0
        c4 = 1 if (ocf_l[i] is not None and ni_l[i] is not None and ocf_l[i] > ni_l[i]) else 0
        c5 = 1 if (i > 0 and op_m[i] is not None and op_m[i - 1] is not None and op_m[i] > op_m[i - 1]) else 0
        c6 = 1 if (i > 0 and asset_turn_l[i] is not None and asset_turn_l[i - 1] is not None and asset_turn_l[i] > asset_turn_l[i - 1]) else 0
        c7 = 1 if (i > 0 and debt_assets_l[i] is not None and debt_assets_l[i - 1] is not None and debt_assets_l[i] <= debt_assets_l[i - 1]) else 0
        c8 = 1 if (i > 0 and curr_ratio_l[i] is not None and curr_ratio_l[i - 1] is not None and curr_ratio_l[i] > curr_ratio_l[i - 1]) else 0
        c9 = 1 if (i > 0 and shares_l[i] is not None and shares_l[i - 1] is not None and shares_l[i] <= shares_l[i - 1]) else 0
        vals = [c1, c2, c3, c4, c5, c6, c7, c8, c9]
        for idx_k, (k, _) in enumerate(defs):
            mat[k].append(vals[idx_k])
        totals.append(sum(vals))

    return {
        "years": years,
        "criteria": [{"key": k, "label": lbl, "values": mat[k]} for k, lbl in defs],
        "scores": totals,
        "latest_score": totals[-1] if totals else None,
    }


def _compute_altman(
    years: list[str],
    wc_l: list[float | None],
    ret_earn_l: list[float | None],
    ebit_l: list[float | None],
    mcap_l: list[float | None],
    liab_l: list[float | None],
    rev_l: list[float | None],
    assets_l: list[float | None],
) -> dict[str, Any]:
    x1_l, x2_l, x3_l, x4_l, x5_l, z_l = [], [], [], [], [], []
    for i in range(len(years)):
        a = assets_l[i]
        x1 = round(1.2 * (wc_l[i] / a), 2) if (a and wc_l[i] is not None) else None
        x2 = round(1.4 * (ret_earn_l[i] / a), 2) if (a and ret_earn_l[i] is not None) else None
        x3 = round(3.3 * (ebit_l[i] / a), 2) if (a and ebit_l[i] is not None) else None
        x4 = round(0.6 * (mcap_l[i] / liab_l[i]), 2) if (liab_l[i] and mcap_l[i] is not None) else None
        x5 = round(rev_l[i] / a, 2) if (a and rev_l[i] is not None) else None
        parts = [x1, x2, x3, x4, x5]
        z = round(sum(p for p in parts if p is not None), 2) if (x3 is not None and x4 is not None and x5 is not None) else None
        x1_l.append(x1); x2_l.append(x2); x3_l.append(x3); x4_l.append(x4); x5_l.append(x5); z_l.append(z)

    return {
        "years": years,
        "criteria": [
            {"key": "x1", "label": "Critère X1 × 1,2 (BFR / Actifs)", "values": x1_l},
            {"key": "x2", "label": "Critère X2 × 1,4 (Résultats non dist. / Actifs)", "values": x2_l},
            {"key": "x3", "label": "Critère X3 × 3,3 (EBIT / Actifs)", "values": x3_l},
            {"key": "x4", "label": "Critère X4 × 0,6 (Capi. / Passifs)", "values": x4_l},
            {"key": "x5", "label": "Critère X5 (Rotation actifs)", "values": x5_l},
        ],
        "scores": z_l,
        "latest_score": z_l[-1] if z_l else None,
    }


def _extract_stakeholders(
    eod_fund: dict[str, Any] | None,
    yahoo_sum: dict[str, Any] | None,
) -> dict[str, Any]:
    """Extrait Analystes, Direction, Initiés et Top Fonds/Institutionnels (EODHD prioritaire + backup Yahoo)."""
    eod = eod_fund or {}
    yah = yahoo_sum or {}

    # 1. Analystes
    ratings = eod.get("AnalystRatings") or {}
    sb = int(_num(ratings.get("StrongBuy")) or 0)
    b = int(_num(ratings.get("Buy")) or 0)
    h = int(_num(ratings.get("Hold")) or 0)
    s = int(_num(ratings.get("Sell")) or 0)
    ss = int(_num(ratings.get("StrongSell")) or 0)
    tot_a = sb + b + h + s + ss
    target_a = _num(ratings.get("TargetPrice")) or _num((eod.get("Highlights") or {}).get("WallStreetTargetPrice"))
    if tot_a == 0 and yah:
        trend = (yah.get("recommendationTrend") or {}).get("trend") or []
        if trend:
            cur = trend[0]
            sb = int(cur.get("strongBuy") or 0)
            b = int(cur.get("buy") or 0)
            h = int(cur.get("hold") or 0)
            s = int(cur.get("sell") or 0)
            ss = int(cur.get("strongSell") or 0)
            tot_a = sb + b + h + s + ss
        if target_a is None:
            target_a = _num((yah.get("financialData") or {}).get("targetMeanPrice"))

    # 2. Direction
    officers: list[dict[str, Any]] = []
    cur_year = datetime.date.today().year
    raw_officers = (eod.get("General") or {}).get("Officers") or {}
    if isinstance(raw_officers, dict) and raw_officers:
        for off in raw_officers.values():
            if not isinstance(off, dict) or not off.get("Name"):
                continue
            yb = _num(off.get("YearBorn"))
            age = int(cur_year - yb) if (yb and 1920 < yb < cur_year - 18) else None
            officers.append({"name": str(off["Name"]), "title": str(off.get("Title") or ""), "age": age})
    if not officers and yah:
        for off in (yah.get("assetProfile") or {}).get("companyOfficers") or []:
            if isinstance(off, dict) and off.get("name"):
                officers.append(
                    {"name": str(off["name"]), "title": str(off.get("title") or ""), "age": off.get("age")}
                )

    # 3. Opérations d'initiés
    insiders: list[dict[str, Any]] = []
    raw_insiders = eod.get("InsiderTransactions") or {}
    ins_iter = raw_insiders.values() if isinstance(raw_insiders, dict) else (raw_insiders if isinstance(raw_insiders, list) else [])
    for tr in ins_iter:
        if not isinstance(tr, dict):
            continue
        code = str(tr.get("transactionCode") or "").upper()
        acq_disp = str(tr.get("transactionAcquiredDisposed") or "").upper()
        shares = _num(tr.get("transactionAmount"))
        price = _num(tr.get("transactionPrice"))
        amount = (shares * price) if (shares is not None and price is not None) else None
        is_sale = acq_disp == "D" or code == "S"
        action = "Vente" if is_sale else ("Achat" if (acq_disp == "A" or code == "P") else (code or "Opération"))
        signed_amount = (-abs(amount) if is_sale else abs(amount)) if amount is not None else None
        insiders.append(
            {
                "date": str(tr.get("date") or tr.get("transactionDate") or "")[:10],
                "name": str(tr.get("ownerName") or ""),
                "relation": str(tr.get("ownerTitle") or tr.get("ownerRelationship") or ""),
                "action": action,
                "shares": shares,
                "price": price,
                "amount": amount,
                "signed_amount": signed_amount,
            }
        )
    if not insiders and yah:
        for tr in (yah.get("insiderTransactions") or {}).get("transactions") or []:
            if not isinstance(tr, dict):
                continue
            shares = _num(tr.get("shares"))
            val = _num(tr.get("value"))
            txt = str(tr.get("transactionText") or "")
            is_sale = "sale" in txt.lower()
            insiders.append(
                {
                    "date": str((tr.get("startDate") or {}).get("fmt") or "")[:10],
                    "name": str(tr.get("filerName") or ""),
                    "relation": str(tr.get("filerRelation") or ""),
                    "action": "Vente" if is_sale else ("Achat" if "purchase" in txt.lower() else txt[:24]),
                    "shares": shares,
                    "price": _div(val, shares, digits=2),
                    "amount": val,
                    "signed_amount": (-abs(val) if is_sale else abs(val)) if val is not None else None,
                }
            )
    insiders.sort(key=lambda x: x["date"], reverse=True)
    insiders = insiders[:45]
    net_insider_amount = sum(t["signed_amount"] for t in insiders if t["signed_amount"] is not None)

    # 4. Top Fonds & Institutionnels
    def _map_eod_holders(bucket: Any) -> list[dict[str, Any]]:
        items = bucket.values() if isinstance(bucket, dict) else (bucket if isinstance(bucket, list) else [])
        out: list[dict[str, Any]] = []
        for h_item in items:
            if not isinstance(h_item, dict) or not h_item.get("name"):
                continue
            out.append(
                {
                    "name": str(h_item["name"]),
                    "date": str(h_item.get("date") or "")[:10],
                    "shares": _num(h_item.get("currentShares") or h_item.get("totalShares")),
                    "weight_pct": _num(h_item.get("totalAssets")),
                    "change_pct": _num(h_item.get("change_p")),
                }
            )
        out.sort(key=lambda x: x["shares"] or 0.0, reverse=True)
        return out[:25]

    holders = eod.get("Holders") or {}
    funds = _map_eod_holders(holders.get("Funds"))
    institutions = _map_eod_holders(holders.get("Institutions"))
    if not funds and yah:
        for h_item in (yah.get("fundOwnership") or {}).get("ownershipList") or []:
            if isinstance(h_item, dict) and h_item.get("organization"):
                funds.append(
                    {
                        "name": str(h_item["organization"]),
                        "date": str((h_item.get("reportDate") or {}).get("fmt") or "")[:10],
                        "shares": _num(h_item.get("position")),
                        "weight_pct": _num(h_item.get("pctHeld")),
                        "change_pct": _num(h_item.get("pctChange")),
                    }
                )
    if not institutions and yah:
        for h_item in (yah.get("institutionOwnership") or {}).get("ownershipList") or []:
            if isinstance(h_item, dict) and h_item.get("organization"):
                institutions.append(
                    {
                        "name": str(h_item["organization"]),
                        "date": str((h_item.get("reportDate") or {}).get("fmt") or "")[:10],
                        "shares": _num(h_item.get("position")),
                        "weight_pct": _num(h_item.get("pctHeld")),
                        "change_pct": _num(h_item.get("pctChange")),
                    }
                )

    return {
        "analysts": {
            "total": tot_a,
            "strong_buy": sb,
            "buy": b,
            "hold": h,
            "sell": s,
            "strong_sell": ss,
            "target_price": target_a,
            "rating": _num(ratings.get("Rating")),
        },
        "officers": officers[:16],
        "insiders": insiders,
        "insiders_net_amount": round(net_insider_amount, 2) if insiders else None,
        "funds": funds,
        "institutions": institutions,
    }


def _compute_price_dynamics(
    price: float | None,
    mma50: float | None,
    mma200: float | None,
) -> str:
    if price is None or mma50 is None or mma200 is None:
        return "Neutre"
    if price > mma50 and mma50 > mma200:
        return "Positif (accélération)"
    if price > mma200:
        return "Positif"
    if price > mma50:
        return "Rebond court terme"
    if price < mma50 and mma50 < mma200:
        return "Négatif (accélération)"
    return "Négatif"


def _simple_ma(bars: list[dict[str, Any]], window: int) -> float | None:
    closes = [(_num(b.get("close")) or _num(b.get("adjusted_close"))) for b in bars[-window:]]
    valid = [c for c in closes if c is not None]
    if len(valid) < max(5, window // 2):
        return None
    return round(sum(valid) / len(valid), 2)


async def _sync_dossier_news(
    settings: Settings,
    db_path: Any,
    canonical: str,
    yahoo_lookup: str,
    eod_key: str,
    ttl_seconds: int,
    refresh: bool,
) -> dict[str, Any]:
    """Récupère les actualités boursières (EODHD prioritaire + Yahoo backup) avec cache BDD 6h."""
    news_ttl = min(max(300, ttl_seconds), 6 * 3600)
    prefer_eod = bool(eod_key and not settings.demo_mode)
    cached = (
        None
        if refresh
        else (
            get_snapshot(db_path, canonical, "news", provider="eodhd", max_age_seconds=news_ttl, include_raw=False)
            if prefer_eod
            else get_snapshot(db_path, canonical, "news", max_age_seconds=news_ttl, include_raw=False)
        )
    )
    if cached and isinstance(cached.get("normalized"), dict):
        norm = cached["normalized"]
        return {
            "source": norm.get("source") or "EOD Historical Data",
            "provider": norm.get("provider") or "eodhd",
            "updated_at": cached.get("updated_at"),
            "items": norm.get("items") or [],
        }

    items: list[dict[str, Any]] = []
    provider = "yahoo_finance"
    source_label = "Yahoo Finance"

    if not settings.demo_mode:
        if eod_key:
            for cand in resolve_candidate_eod_tickers(db_path, canonical)[:3]:
                eod_items = await fetch_eodhd_news(cand, eod_key, limit=15)
                if eod_items:
                    items = eod_items
                    provider = "eodhd"
                    source_label = "EOD Historical Data"
                    break

        if not items:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
                timeout=10.0,
            ) as client:
                y_items = await fetch_yahoo_symbol_news(client, yahoo_lookup, limit=12)
            if y_items:
                items = y_items
                provider = "yahoo_finance"
                source_label = "Yahoo Finance"

    items = _deduplicate_articles(items, limit=15)
    normalized = {"source": source_label, "provider": provider, "items": items}
    save_snapshot(db_path, canonical, provider, "news", items, normalized)
    return {
        "source": source_label,
        "provider": provider,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "items": items,
    }


async def _sync_eodhd_extras(
    settings: Settings,
    db_path: Any,
    canonical: str,
    eod_fund: dict[str, Any] | None,
    eod_key: str,
    ttl_seconds: int,
    refresh: bool,
) -> dict[str, Any]:
    """Synchronise avec cache BDD les flux complémentaires EODHD (sentiments, hist. cap, calendrier, initiés, macro)."""
    if settings.demo_mode or not eod_key:
        return {
            "sentiments": None,
            "historical_mcap": None,
            "earnings_calendar": [],
            "insider_transactions": [],
            "macro_context": None,
        }

    eod_t = (resolve_candidate_eod_tickers(db_path, canonical) or [canonical])[0]
    country_iso3 = resolve_country_iso3(eod_fund, canonical)
    macro_sym = f"__MACRO_{country_iso3}__"

    def _cached(sym: str, snap_type: str, age_sec: int) -> Any:
        if refresh:
            return None
        snap = get_snapshot(db_path, sym, snap_type, max_age_seconds=age_sec, include_raw=False)
        return snap.get("normalized") if snap else None

    c_sent = _cached(canonical, "sentiments", min(ttl_seconds, 6 * 3600))
    c_mcap = _cached(canonical, "historical_mcap", max(ttl_seconds, 24 * 3600))
    c_cal = _cached(canonical, "earnings_calendar", min(ttl_seconds, 6 * 3600))
    c_ins = _cached(canonical, "insider_transactions", min(ttl_seconds, 12 * 3600))
    c_macro = _cached(macro_sym, "macro_context", max(ttl_seconds, 24 * 3600))

    async def _get_sent():
        if isinstance(c_sent, dict):
            return c_sent
        res = await fetch_eodhd_sentiments(eod_t, eod_key)
        if res:
            save_snapshot(db_path, canonical, "eodhd", "sentiments", res, res)
        return res

    async def _get_mcap():
        if isinstance(c_mcap, dict):
            return c_mcap
        res = await fetch_eodhd_historical_mcap(eod_t, eod_key)
        if res:
            save_snapshot(db_path, canonical, "eodhd", "historical_mcap", res, res)
        return res

    async def _get_cal():
        if isinstance(c_cal, dict):
            return c_cal.get("items") or []
        res = await fetch_eodhd_earnings_calendar(eod_t, eod_key)
        if res is not None:
            save_snapshot(db_path, canonical, "eodhd", "earnings_calendar", res, {"items": res})
            return res
        return []

    async def _get_ins():
        if isinstance(c_ins, dict):
            return c_ins.get("items") or []
        res = await fetch_eodhd_insider_transactions(eod_t, eod_key)
        if res is not None:
            save_snapshot(db_path, canonical, "eodhd", "insider_transactions", res, {"items": res})
            return res
        return []

    async def _get_macro():
        if isinstance(c_macro, dict):
            return c_macro
        res = await fetch_eodhd_macro_context(country_iso3, eod_key)
        if res:
            save_snapshot(db_path, macro_sym, "eodhd", "macro_context", res, res)
        return res

    sentiments, historical_mcap, earnings_calendar, insider_tx, macro_ctx = await asyncio.gather(
        _get_sent(), _get_mcap(), _get_cal(), _get_ins(), _get_macro()
    )
    return {
        "sentiments": sentiments,
        "historical_mcap": historical_mcap,
        "earnings_calendar": earnings_calendar,
        "insider_transactions": insider_tx,
        "macro_context": macro_ctx,
    }


def _fundamentals_schedule_safe(db_path: Any, canonical: str) -> dict[str, Any] | None:
    """Fraîcheur des fondamentaux (période publiée, publication, prochain contrôle) pour l'affichage."""
    try:
        from .finance_fundamentals_queue import get_symbol_schedule

        return get_symbol_schedule(db_path, [canonical, *resolve_candidate_eod_tickers(db_path, canonical)])
    except Exception as exc:
        _logger.debug("Échéancier des fondamentaux indisponible (%s): %s", canonical, exc)
        return None


async def get_financial_dossier(
    settings: Settings,
    symbol: str,
    refresh: bool = False,
) -> dict[str, Any]:
    """Construit le dossier complet d'une valeur (EODHD prioritaire + cache BDD + backup Yahoo)."""
    db_path = warehouse_db_path(settings)
    clean_sym = symbol.strip()
    canonical = resolve_canonical_symbol(db_path, clean_sym)
    ttl_seconds = max(60, int(settings.finance_fundamentals_ttl_hours) * 3600)

    # 1. Récupérer / synchroniser les états financiers (remplit aussi le snapshot EODHD / Yahoo en BDD)
    statements = await get_unified_financial_statements(settings, canonical, refresh=refresh)
    canonical = statements.get("canonical_symbol") or canonical

    eod_snap = get_snapshot(db_path, canonical, "fundamentals", provider="eodhd", include_raw=True)
    eod_fund = eod_snap.get("raw") if (eod_snap and isinstance(eod_snap.get("raw"), dict)) else None

    yahoo_snap = get_snapshot(db_path, canonical, "quote_summary_ext", provider="yahoo_finance", include_raw=True)
    yahoo_sum = yahoo_snap.get("raw") if (yahoo_snap and isinstance(yahoo_snap.get("raw"), dict)) else None

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )
    is_eufund = canonical.upper().endswith(".EUFUND")

    if eod_fund is None and eod_key:
        for cand in resolve_candidate_eod_tickers(db_path, canonical):
            fetched = await fetch_eodhd_fundamentals_json(cand, eod_key)
            if fetched:
                eod_fund = fetched
                persist_eodhd_fundamentals_to_warehouse(settings, canonical, fetched, eod_ticker=cand)
                break

    yahoo_lookup = canonical[:-3] if canonical.endswith(".US") else canonical
    if not is_eufund and yahoo_sum is None and eod_fund is None:
        yahoo_sum = await _fetch_yahoo_extended_summary(yahoo_lookup)
        if yahoo_sum:
            save_snapshot(db_path, canonical, "yahoo_finance", "quote_summary_ext", yahoo_sum, None)

    # 2. Synchroniser 10+ ans de barres EOD journalières & l'historique des dividendes (EODHD prioritaire)
    stored_bars = get_stored_eod_bars(db_path, canonical)
    latest_date = get_latest_bar_date(db_path, canonical)
    sync_info = get_instrument_eod_sync_info(db_path, canonical)
    prefer_eod_bars = bool(eod_key and not settings.demo_mode)
    fresh_bars_today = not refresh and is_eod_fresh_today(
        sync_info,
        min_bars_needed=2000,
        prefer_source="eodhd" if prefer_eod_bars else None,
    )
    latest_bar_is_non_eod = bool(
        prefer_eod_bars
        and sync_info.get("latest_bar_source")
        and str(sync_info.get("latest_bar_source")).lower() != "eodhd"
    )
    today_date = datetime.date.today()
    need_bars_sync = refresh or latest_bar_is_non_eod or (
        not fresh_bars_today
        and (
            len(stored_bars) < 200
            or (latest_date is not None and (today_date - datetime.date.fromisoformat(latest_date)).days >= 2)
        )
    )

    div_snap = (
        get_snapshot(db_path, canonical, "dividends", provider="eodhd", max_age_seconds=ttl_seconds, include_raw=True)
        if prefer_eod_bars
        else get_snapshot(db_path, canonical, "dividends", max_age_seconds=ttl_seconds, include_raw=True)
    )
    div_fallback_snap = (
        get_snapshot(db_path, canonical, "dividends", provider="yahoo_finance", max_age_seconds=ttl_seconds, include_raw=True)
        if (prefer_eod_bars and div_snap is None and not refresh)
        else None
    )
    stored_divs: list[dict[str, Any]] = (div_snap.get("raw") if div_snap else None) or []
    need_divs_sync = refresh or div_snap is None

    if need_bars_sync or need_divs_sync:
        new_bars: list[dict[str, Any]] = []
        new_divs: list[dict[str, Any]] | None = None
        bars_source = "eodhd"
        divs_source = "eodhd"
        eod_cand_list = resolve_candidate_eod_tickers(db_path, canonical) or [canonical]

        if prefer_eod_bars:
            from_dt = (
                (datetime.date.fromisoformat(latest_date) - datetime.timedelta(days=7)).isoformat()
                if (latest_date and len(stored_bars) >= 1500 and not refresh and not latest_bar_is_non_eod)
                else (today_date - datetime.timedelta(days=3800)).isoformat()
            )
            for eod_t in eod_cand_list[:3]:
                tasks = []
                if need_bars_sync and not new_bars:
                    tasks.append(_fetch_eodhd_bars_range(eod_t, eod_key, from_dt))
                else:
                    tasks.append(asyncio.sleep(0, result=[]))
                if need_divs_sync and new_divs is None:
                    tasks.append(_fetch_eodhd_dividends(eod_t, eod_key))
                else:
                    tasks.append(asyncio.sleep(0, result=None))
                cand_bars, cand_divs = await asyncio.gather(*tasks)
                if cand_bars and not new_bars:
                    new_bars = cand_bars
                    bars_source = "eodhd"
                if cand_divs is not None and new_divs is None:
                    new_divs = cand_divs
                    divs_source = "eodhd"
                if (not need_bars_sync or new_bars) and (not need_divs_sync or new_divs is not None):
                    break

        # Yahoo Finance uniquement en backup si EODHD n'a pas fourni les données (hors fonds EUFUND)
        if not is_eufund and ((need_bars_sync and not new_bars) or (need_divs_sync and new_divs is None)):
            if need_divs_sync and new_divs is None and div_fallback_snap and isinstance(div_fallback_snap.get("raw"), list):
                stored_divs = div_fallback_snap["raw"]
                need_divs_sync = False
            if (need_bars_sync and not new_bars) or (need_divs_sync and new_divs is None):
                y_bars, y_divs = await _fetch_yahoo_chart_10y(yahoo_lookup)
                if need_bars_sync and not new_bars and y_bars:
                    new_bars = y_bars
                    bars_source = "yahoo_finance"
                if need_divs_sync and new_divs is None and y_divs is not None:
                    new_divs = y_divs
                    divs_source = "yahoo_finance"

        if new_bars:
            upsert_eod_bars(
                db_path,
                canonical,
                new_bars,
                bars_source,
                requested_limit=2500,
            )
            stored_bars = get_stored_eod_bars(db_path, canonical)
        if new_divs is not None:
            stored_divs = new_divs
            save_snapshot(
                db_path,
                canonical,
                divs_source,
                "dividends",
                new_divs,
                None,
            )

    # 3. Assemblage des sections du dossier
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
        str(gen.get("CurrencyCode") or y_price.get("currency") or statements.get("currency") or "USD")
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

    ann_series, _, _, _ = load_fundamental_series(db_path, canonical, "annual")
    qtr_series, _, _, _ = load_fundamental_series(db_path, canonical, "quarterly")
    perf_payload, risk_payload, monthly_chart = compute_price_performance_and_risk(stored_bars, currency=currency)
    annual_tables = _compute_annual_dossier_tables(ann_series, stored_bars, beta_val)
    stakeholders = _extract_stakeholders(eod_fund, yahoo_sum)
    dividends_matrix = _build_dividends_matrix(stored_divs)

    shares_out = _num(shares_st.get("SharesOutstanding")) or _num(y_stat.get("sharesOutstanding"))
    shares_float = _num(shares_st.get("SharesFloat")) or _num(y_stat.get("floatShares"))
    float_pct = _div(shares_float, shares_out, 100.0, 1)

    addr_parts = [
        gen.get("Address") or y_prof.get("address1"),
        y_prof.get("city"),
        y_prof.get("state"),
        gen.get("CountryName") or y_prof.get("country"),
        y_prof.get("zip"),
    ]
    address = ", ".join(str(p).strip() for p in addr_parts if p and str(p).strip())

    ih_info = annual_tables["ih_score"]
    price_dynamics = _compute_price_dynamics(price, mma50, mma200)

    # Relire les analyses IA sauvegardées & datées (et migrer un éventuel ancien snapshot)
    ai_snap = get_snapshot(db_path, canonical, "ai_analysis", include_raw=False)
    company_display = str(gen.get("Name") or y_price.get("longName") or y_price.get("shortName") or canonical)
    if ai_snap and ai_snap.get("normalized") and (ai_snap["normalized"] or {}).get("markdown"):
        if not has_ai_analysis_for(db_path, canonical, "dossier"):
            norm_ai = ai_snap["normalized"]
            md_ai = str(norm_ai.get("markdown") or "")
            created_ai = str(ai_snap.get("updated_at") or "")
            hl_ai = extract_report_highlights(md_ai)
            html_ai = str(norm_ai.get("content_html") or "") or build_classy_report_html(
                md_ai,
                title=f"Synthèse Fondamentale IA — {company_display}",
                subtitle="Analyse institutionnelle complète multi-exercices",
                symbol=canonical,
                model=str(norm_ai.get("model") or ""),
                created_at=created_ai,
                accent="#4f46e5",
                badge_label="Analyse Dossier IA",
            )
            save_ai_analysis_entry(
                db_path,
                symbol=canonical,
                company_name=company_display,
                kind="dossier",
                model=str(norm_ai.get("model") or ""),
                verdict=str(norm_ai.get("verdict") or hl_ai["verdict"]),
                conviction=str(norm_ai.get("conviction") or hl_ai["conviction"]),
                horizon=str(norm_ai.get("horizon") or hl_ai["horizon"]),
                markdown=md_ai,
                content_html=html_ai,
                created_at=created_ai or None,
            )
    ai_history = list_ai_analyses(db_path, symbol=canonical, kind="dossier", limit=100)
    for item in ai_history:
        if not item.get("content_html"):
            item["content_html"] = build_classy_report_html(
                item.get("markdown") or "",
                title=f"Synthèse Fondamentale IA — {company_display}",
                subtitle="Analyse institutionnelle complète multi-exercices",
                symbol=canonical,
                model=item.get("model") or "",
                created_at=item.get("created_at") or "",
                accent="#4f46e5",
                badge_label="Analyse Dossier IA",
            )
        item["updated_at"] = item.get("created_at")

    news_payload, eod_extras = await asyncio.gather(
        _sync_dossier_news(settings, db_path, canonical, yahoo_lookup, eod_key, ttl_seconds, refresh),
        _sync_eodhd_extras(settings, db_path, canonical, eod_fund, eod_key, ttl_seconds, refresh),
    )

    if eod_extras.get("sentiments"):
        news_payload["sentiment_summary"] = eod_extras["sentiments"]

    extra_insiders = eod_extras.get("insider_transactions") or []
    if extra_insiders:
        existing_keys = {
            (r.get("date"), (r.get("name") or "").lower(), r.get("action"), r.get("shares"))
            for r in (stakeholders.get("insiders") or [])
        }
        merged_ins = list(stakeholders.get("insiders") or [])
        for row in extra_insiders:
            k = (row.get("date"), (row.get("name") or "").lower(), row.get("action"), row.get("shares"))
            if k not in existing_keys:
                existing_keys.add(k)
                merged_ins.append(row)
        merged_ins.sort(key=lambda r: r.get("date") or "", reverse=True)
        stakeholders["insiders"] = merged_ins[:30]
        signed_vals = [r["signed_amount"] for r in stakeholders["insiders"] if r.get("signed_amount") is not None]
        if signed_vals:
            stakeholders["insiders_net_amount"] = round(sum(signed_vals), 0)

    upsert_instrument(
        db_path,
        {
            "symbol": canonical,
            "short_name": (gen.get("Name") or y_price.get("shortName") or canonical).split(" - ")[0],
            "long_name": gen.get("Name") or y_price.get("longName") or canonical,
            "exchange": gen.get("Exchange") or y_price.get("exchangeName"),
            "currency": currency,
            "country": gen.get("CountryName") or y_prof.get("country"),
            "sector": gen.get("Sector") or y_prof.get("sector"),
            "industry": gen.get("Industry") or y_prof.get("industry"),
        },
    )

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
        macro_context=eod_extras.get("macro_context"),
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
        macro_context=eod_extras.get("macro_context"),
        stakeholders=stakeholders,
        preferred_stock=preferred_stock,
        minority_interest=minority_interest,
        employees=employees_val,
    )

    from .finance_funds import extract_fund_profile
    from .finance_warehouse import lookup_exchange_symbol

    cat_hit = lookup_exchange_symbol(db_path, canonical, "EUFUND") if is_eufund else None
    fund_profile = extract_fund_profile(eod_fund, cat_hit, symbol=canonical)
    if (not currency or currency == "USD") and cat_hit and cat_hit.get("currency"):
        currency = str(cat_hit["currency"]).upper()
    display_name = gen.get("Name") or (cat_hit.get("name") if cat_hit else None) or y_price.get("longName") or canonical

    dossier_payload = {
        "symbol": canonical,
        "currency": currency,
        "source_provider": statements.get("source_provider") or ("eodhd" if (eod_fund or is_eufund) else "yahoo_finance"),
        "source_label": statements.get("source_label") or ("EOD Historical Data" if (eod_fund or is_eufund) else "Yahoo Finance"),
        "warehouse_stats": get_warehouse_stats(db_path, canonical),
        "fundamentals_schedule": _fundamentals_schedule_safe(db_path, canonical),
        "header": {
            "name": display_name,
            "logo_url": resolve_eodhd_logo_url(eod_fund, canonical),
            "cap_category": _cap_category(market_cap),
            "market_cap": market_cap,
            "dividend_yield_pct": div_yield_pct,
            "beta": round(beta_val, 2) if beta_val is not None else None,
            "ih_score": ih_info.get("latest_score"),
            "ih_quality": ih_info.get("quality_label"),
            "ih_trend": ih_info.get("trend"),
            "price_dynamics": price_dynamics,
            "sector": gen.get("Sector") or (fund_profile.get("category") if fund_profile else None) or y_prof.get("sector"),
            "industry": gen.get("Industry") or (fund_profile.get("fund_family") if fund_profile else None) or y_prof.get("industry"),
            "employees": _num(gen.get("FullTimeEmployees")) or _num(y_prof.get("fullTimeEmployees")),
            "website": gen.get("WebURL") or (fund_profile.get("website") if fund_profile else "") or y_prof.get("website") or "",
            "address": address,
            "isin": gen.get("ISIN") or (cat_hit.get("isin") if cat_hit else None),
            "description": gen.get("Description") or (fund_profile.get("description") if fund_profile else "") or y_prof.get("longBusinessSummary") or "",
        },
        "fund_profile": fund_profile,
        "capital_valuation": cap_val_dict,
        "performance": perf_payload,
        "performance_chart": monthly_chart,
        "risk": risk_payload,
        "stakeholders": stakeholders,
        "annual_tables": annual_tables,
        "dividends_matrix": dividends_matrix,
        "statements": {
            "annual": statements.get("annual"),
            "quarterly": statements.get("quarterly"),
            "earnings_history": statements.get("earnings_history") or [],
        },
        "news": news_payload,
        "historical_market_cap": eod_extras.get("historical_mcap"),
        "earnings_calendar": eod_extras.get("earnings_calendar") or [],
        "macro_context": eod_extras.get("macro_context"),
        "intrinsic_valuation": intrinsic_valuation,
        "uncle_stock_scores": uncle_stock_scores,
        "uncle_stock_catalog": uncle_stock_catalog,
        "ai_analysis": ai_history[0] if ai_history else None,
        "ai_history": ai_history,
    }
    try:
        from .finance_screener import sync_screener_snapshot_from_dossier

        sync_screener_snapshot_from_dossier(db_path, dossier_payload, stored_bars)
    except Exception as exc:
        _logger.debug("Mise à jour snapshot screener ignorée (%s): %s", canonical, exc)
    return dossier_payload


def _resolve_gemini_hydrogen_model(settings: Settings, explicit_model_id: str | None = None) -> str:
    """Sélectionne Gemini Hydrogen dans le catalogue de modèles configuré (avec repli sûr)."""
    if explicit_model_id and explicit_model_id.strip():
        return explicit_model_id.strip()

    candidates: list[dict[str, Any]] = []
    try:
        candidates = list(settings.models or [])
    except Exception:
        candidates = []
    if not candidates:
        try:
            candidates = list(settings.configured_models or [])
        except Exception:
            candidates = []

    matches: list[tuple[int, str]] = []
    for item in candidates:
        mid = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        hay = f"{mid} {name}".lower()
        if "hydrogen" in hay and "gemini" in hay:
            score = 0 if "lite" in hay else 10
            if "4" in hay:
                score += 5
            matches.append((score, mid))

    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        return matches[0][1]

    return "google/gemini-4-hydrogen"


def _compact_annual_table(years: list[str], rows: list[dict[str, Any]], max_years: int = 8) -> dict[str, Any]:
    if not years or not rows:
        return {}
    start = max(0, len(years) - max_years)
    yrs = years[start:]
    out: dict[str, Any] = {}
    for r in rows:
        vals = {y: v for y, v in zip(yrs, (r.get("values") or [])[start:]) if v is not None}
        if vals:
            out[r["label"]] = vals
    return out


def _compact_statement_period(period: dict[str, Any] | None, max_periods: int = 6) -> dict[str, Any]:
    """Extrait les postes financiers annuels ou trimestriels les plus récents pour le contexte IA."""
    if not period:
        return {}
    dates = list(period.get("dates") or [])
    if not dates:
        return {}
    start = max(0, len(dates) - max_periods)
    sliced_dates = dates[start:]
    out: dict[str, Any] = {"dates": sliced_dates}
    for section in ("income", "balance", "cashflow", "ratios"):
        sec_map: dict[str, dict[str, Any]] = {}
        for row in period.get(section) or []:
            vals = {
                d: v
                for d, v in zip(sliced_dates, (row.get("values") or [])[start:])
                if v is not None
            }
            if vals:
                sec_map[str(row.get("label") or row.get("key") or "")] = vals
        if sec_map:
            out[section] = sec_map
    return out


def build_dossier_facts_context(dossier: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Assemble le contexte chiffré vérifié complet d'un dossier pour l'analyse IA ou les experts."""
    canonical = dossier["symbol"]
    hdr = dossier["header"]
    cap = dossier["capital_valuation"]
    ann_tbl = dossier["annual_tables"]
    ann_years = ann_tbl.get("years") or []
    stk = dossier["stakeholders"]

    perf = {h["label"]: h["pct"] for h in dossier["performance"]["horizons"] if h["pct"] is not None}
    risk_all = {
        m["label"]: {h: v for h, v in zip(dossier["risk"].get("horizons") or [], m.get("values") or []) if v is not None}
        for m in dossier["risk"].get("metrics", [])
        if any(v is not None for v in (m.get("values") or []))
    }

    ann_stmt = (dossier.get("statements") or {}).get("annual") or {}
    qtr_stmt = (dossier.get("statements") or {}).get("quarterly") or {}
    ann_comp = _compact_statement_period(ann_stmt, max_periods=6)
    qtr_comp = _compact_statement_period(qtr_stmt, max_periods=5)

    perf_series = dossier.get("performance_chart") or []
    ref_price_date = perf_series[-1]["date"] if perf_series and isinstance(perf_series[-1], dict) else None
    today_iso = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    ann_span = f"{ann_years[0]}–{ann_years[-1]}" if len(ann_years) >= 2 else (ann_years[0] if ann_years else "N/A")
    q_dates = qtr_comp.get("dates") or []
    period_label = f"exercices {ann_span}" + (f" & dernier trimestre {q_dates[-1]}" if q_dates else "")

    facts_context = {
        "entreprise": hdr["name"],
        "symbole": canonical,
        "devise": dossier["currency"],
        "source_principale": dossier.get("source_label") or dossier.get("source_provider") or "EOD Historical Data / Yahoo Finance",
        "date_generation_analyse": today_iso,
        "date_reference_cours": ref_price_date or today_iso,
        "en_tete": {
            "categorie_cap": hdr.get("cap_category"),
            "capitalisation": hdr.get("market_cap"),
            "rendement_dividende_pct": hdr.get("dividend_yield_pct"),
            "beta": hdr.get("beta"),
            "dynamique_cours": hdr.get("price_dynamics"),
            "secteur": hdr.get("sector"),
            "industrie": hdr.get("industry"),
            "effectif": hdr.get("employees"),
            "site_web": hdr.get("website"),
            "siege": hdr.get("address"),
            "isin": hdr.get("isin"),
            "activite": (hdr.get("description") or "")[:1000],
        },
        "capital_et_valorisation": cap,
        "performances_ajustees_pct": perf,
        "gestion_du_risque_1a_5a": risk_all,
        "parties_prenantes": {
            "analystes": stk.get("analysts"),
            "direction": (stk.get("officers") or [])[:8],
            "cumul_inities": stk.get("insiders_net_amount"),
            "dernieres_operations_inities": (stk.get("insiders") or [])[:8],
            "top_fonds": (stk.get("funds") or [])[:5],
            "top_institutionnels": (stk.get("institutions") or [])[:5],
        },
        "fondamentaux_synthese": _compact_annual_table(ann_years, ann_tbl.get("summary") or []),
        "ratios_profitabilite": _compact_annual_table(ann_years, ann_tbl.get("profitability") or []),
        "ratios_solvabilite": _compact_annual_table(ann_years, ann_tbl.get("solvency") or []),
        "ratios_distribution": _compact_annual_table(ann_years, ann_tbl.get("distribution") or []),
        "ratios_efficacite": _compact_annual_table(ann_years, ann_tbl.get("efficiency") or []),
        "scores_qualitatifs": {
            "ih_score": {
                "score": ann_tbl["ih_score"].get("latest_score"),
                "qualite": ann_tbl["ih_score"].get("quality_label"),
                "tendance": ann_tbl["ih_score"].get("trend"),
                "criteres_moyennes": {c["label"]: c.get("avg") for c in ann_tbl["ih_score"].get("criteria") or []},
            },
            "piotroski_f_score": {
                "dernier": ann_tbl["piotroski"].get("latest_score"),
                "historique": dict(zip(ann_tbl["piotroski"].get("years") or [], ann_tbl["piotroski"].get("scores") or [])),
            },
            "altman_z_score": {
                "dernier": ann_tbl["altman"].get("latest_score"),
                "historique": dict(zip(ann_tbl["altman"].get("years") or [], ann_tbl["altman"].get("scores") or [])),
            },
        },
        "dividendes_annuels": {
            str(r["year"]): r["total"]
            for r in (dossier.get("dividends_matrix") or {}).get("rows", [])[:8]
            if r.get("total") is not None
        },
        "comptes_annuels_detailles": ann_comp,
        "comptes_trimestriels_recents": qtr_comp,
        "surprises_bpa_recentes": ((dossier.get("statements") or {}).get("earnings_history") or [])[:8],
        "actualites_recentes": [
            {
                "date": n.get("published_at"),
                "source": n.get("source"),
                "titre": n.get("title"),
                "sentiment": (n.get("sentiment") or {}).get("polarity") if isinstance(n.get("sentiment"), dict) else None,
                "extrait": (n.get("snippet") or "")[:280],
            }
            for n in ((dossier.get("news") or {}).get("items") or [])[:10]
        ],
        "sentiment_marche_eodhd": (dossier.get("news") or {}).get("sentiment_summary"),
        "capitalisation_historique": {
            k: (dossier.get("historical_market_cap") or {}).get(k)
            for k in ("latest_value", "latest_date", "min_value", "max_value")
        } if dossier.get("historical_market_cap") else None,
        "calendrier_prochains_resultats": (dossier.get("earnings_calendar") or [])[:6],
        "contexte_macro_taux": dossier.get("macro_context"),
        "scores_unclestock_31": (
            {
                "synthese": (dossier.get("uncle_stock_scores") or {}).get("summary"),
                "scores": [
                    {
                        "id": s.get("id"),
                        "name": s.get("name"),
                        "category": s.get("category"),
                        "verified": (s.get("verified") or {}).get("display_value"),
                        "documented": (s.get("documented") or {}).get("display_value"),
                    }
                    for s in ((dossier.get("uncle_stock_scores") or {}).get("items") or [])
                    if s.get("available")
                ],
            }
            if (dossier.get("uncle_stock_scores") or {}).get("available")
            else None
        ),
        "valeurs_intrinseques": (
            {
                "synthese": (dossier.get("intrinsic_valuation") or {}).get("summary"),
                "cout_du_capital": (dossier.get("intrinsic_valuation") or {}).get("cost_of_capital"),
                "retours_proprietaires": (dossier.get("intrinsic_valuation") or {}).get("owner_returns"),
                "methodes": [
                    {
                        "nom": m["name"],
                        "poids": m["weight"],
                        "valeur_corrigee": m["corrected_value"],
                        "valeur_unclestock": m["unclestock_value"],
                        "mos_corrigee_pct": m["margin_of_safety_corrected_pct"],
                        "statut": m["status_corrected"],
                    }
                    for m in ((dossier.get("intrinsic_valuation") or {}).get("methods") or [])
                ],
                "scenarios_dcf": (dossier.get("intrinsic_valuation") or {}).get("scenarios"),
            }
            if (dossier.get("intrinsic_valuation") or {}).get("available")
            else None
        ),
    }
    return facts_context, period_label


def _finalize_and_save_dossier_analysis(
    db_path: Any,
    *,
    canonical: str,
    company_name: str,
    currency: str,
    markdown: str,
    model: str,
) -> dict[str, Any]:
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    hl = extract_report_highlights(markdown)
    content_html = build_classy_report_html(
        markdown,
        title=f"Synthèse Fondamentale IA — {company_name or canonical}",
        subtitle="Analyse institutionnelle complète multi-exercices",
        symbol=canonical,
        model=model,
        created_at=now_iso,
        accent="#4f46e5",
        badge_label="Analyse Dossier IA",
    )
    entry = save_ai_analysis_entry(
        db_path,
        symbol=canonical,
        company_name=company_name,
        kind="dossier",
        model=model,
        verdict=hl["verdict"],
        conviction=hl["conviction"],
        horizon=hl["horizon"],
        markdown=markdown,
        content_html=content_html,
        created_at=now_iso,
    )
    saved_snap = {
        "id": entry["id"],
        "markdown": markdown,
        "content_html": content_html,
        "verdict": hl["verdict"],
        "conviction": hl["conviction"],
        "horizon": hl["horizon"],
        "model": model,
    }
    save_snapshot(db_path, canonical, "clair", "ai_analysis", None, saved_snap, currency=currency)
    return {
        **entry,
        "updated_at": entry["created_at"],
    }


async def generate_dossier_ai_analysis(
    settings: Settings,
    symbol: str,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Génère et sauvegarde une analyse fondamentale complète basée sur tous les résultats du dossier (modèle Gemini Hydrogen)."""
    from .google_cloud import can_fallback_to_model, has_llm_access, post_chat_completion
    from .providers import ProviderError, _check_response, _json

    dossier = await get_financial_dossier(settings, symbol, refresh=False)
    canonical = dossier["symbol"]
    db_path = warehouse_db_path(settings)
    hdr = dossier["header"]
    cap = dossier["capital_valuation"]
    ann_tbl = dossier["annual_tables"]
    facts_context, period_label = build_dossier_facts_context(dossier)

    chosen_model = _resolve_gemini_hydrogen_model(settings, model_id)
    if settings.demo_mode or not has_llm_access(settings, chosen_model):
        md = (
            f"### Synthèse fondamentale — {hdr['name']} ({canonical})\n\n"
            f"- **Positionnement** : {hdr['sector'] or 'N/A'} ({hdr['industry'] or 'N/A'}), capitalisation **{hdr['cap_category']}**.\n"
            f"- **Qualité & Solidité** : IH Score **{hdr['ih_score'] or 'N/A'}/9** (tendance {hdr['ih_trend']}), "
            f"F-Score Piotroski **{ann_tbl['piotroski'].get('latest_score') or 'N/A'}/9**, "
            f"Z-Score Altman **{ann_tbl['altman'].get('latest_score') or 'N/A'}**.\n"
            f"- **Valorisation TTM** : PER **{cap.get('pe_ttm') or 'N/A'}**, VE/EBITDA **{cap.get('ev_ebitda') or 'N/A'}**, "
            f"marge opérationnelle **{cap.get('op_margin_ttm') or 'N/A'}%**."
        )
        return _finalize_and_save_dossier_analysis(
            db_path,
            canonical=canonical,
            company_name=str(hdr.get("name") or canonical),
            currency=str(dossier["currency"] or ""),
            markdown=md,
            model="synthese-locale",
        )

    context_json = json.dumps(facts_context, ensure_ascii=False, separators=(",", ":"))
    source_name = facts_context["source_principale"]
    prompt = f"""# PROMPT — ANALYSTE FINANCIER D'ÉLITE

## 1. RÔLE ET MISSION

Tu es un analyste financier senior travaillant pour un fonds d'investissement international, spécialisé dans l'analyse fondamentale, la valorisation et l'allocation de capital à long terme.

Tu combines les approches de :

- **Warren Buffett** : qualité de l'entreprise, avantages concurrentiels durables (moat), génération de cash-flow, discipline de valorisation.
- **Charlie Munger** : modèles mentaux, incitations des dirigeants, risques cachés, inversion du raisonnement.
- **Peter Lynch** : croissance, compréhension du modèle économique, rapport croissance/valorisation, classification des entreprises.
- **Benjamin Graham** : marge de sécurité, solidité du bilan, protection contre les pertes permanentes.
- **Howard Marks** : cycles économiques, psychologie du marché, asymétrie risque/rendement.
- **Aswath Damodaran** : valorisation intrinsèque, DCF, coût du capital, scénarios probabilistes.

Ta mission consiste à analyser les résultats financiers de **{hdr['name']} ({canonical})** pour **{period_label}** et à produire un rapport d'investissement structuré, critique, quantifié et exploitable.

Tu ne cherches ni à confirmer le discours du management ni à justifier le cours actuel.

Tu cherches à identifier ce que les chiffres disent réellement.

---

## 2. COLLECTE ET FIABILITÉ DES DONNÉES

Utilise exclusivement les données vérifiées issues de la fiche boursière de l'application (source : {source_name}, date d'analyse : {facts_context['date_generation_analyse']}, date de référence du cours : {facts_context['date_reference_cours']}) fournies en annexe JSON ci-dessous, incluant les comptes annuels, comptes trimestriels, TTM, scores qualitatifs (IH Score, Piotroski F-Score, Altman Z-Score), profil de risque 1A–5A, performances ajustées, consensus analystes, direction, opérations d'initiés, actionnariat institutionnel et surprises BPA.

Compare systématiquement :

- La période actuelle avec la même période de l'année précédente.
- La période actuelle avec la période précédente lorsque pertinent.
- Les tendances sur 3 à 5 ans (ou tout l'historique fourni).
- Les résultats avec le consensus des analystes et les estimations de BPA, si disponibles.

**Règles impératives :**

- N'invente jamais de données manquantes.
- Indique la source ({source_name}) et la date de chaque donnée importante.
- Sépare faits vérifiés, estimations, hypothèses et opinions.
- Précise les unités, devises ({dossier['currency']}) et périodes.
- Signale toute divergence ou donnée absente entre périodes/sources.
- Identifie les éléments exceptionnels et les variations inhabituelles observables dans les comptes.
- Si les données fournies ne permettent pas une conclusion fiable sur un point précis (ex. WACC exact, échéancier détaillé de dette, engagements hors bilan, clients individuels, transactions non détaillées), indique explicitement « Données insuffisantes » sur ce point sans bloquer le reste de l'analyse.

---

## 3. STRUCTURE OBLIGATOIRE DU RAPPORT

### A. SYNTHÈSE EXÉCUTIVE

Commence par un tableau :

| Indicateur | Résultat | Évaluation |
|---|---|---|
| Qualité de l'entreprise | /10 | |
| Croissance | /10 | |
| Rentabilité | /10 | |
| Solidité financière | /10 | |
| Génération de cash | /10 | |
| Avantage concurrentiel | /10 | |
| Qualité du management | /10 | |
| Valorisation | /10 | |
| Risques | /10 | |

Ajoute :

- Verdict fondamental en 3 phrases maximum.
- Trois forces principales.
- Trois faiblesses principales.
- Une surprise positive et une surprise négative, si elles existent (en exploitant notamment les surprises BPA, scores et ratios).
- Ce que le marché semble anticiper (cours vs MMA50/200, multiples et consensus).
- Ce qui pourrait changer la thèse d'investissement.

Attribue un score global sur 100, avec pondération explicite des critères (et rapprochement avec l'IH Score /9, F-Score Piotroski /9 et Z-Score Altman).

### B. ANALYSE DES RÉSULTATS FINANCIERS

Présente un tableau comprenant, lorsque disponibles :

| Indicateur | Actuel | N-1 | Variation | Interprétation |
|---|---|---|---|---|
| Chiffre d'affaires | | | | |
| Croissance organique | | | | |
| Marge brute | | | | |
| EBITDA | | | | |
| Marge opérationnelle | | | | |
| Résultat net | | | | |
| BPA dilué | | | | |
| Cash-flow opérationnel | | | | |
| Capex | | | | |
| Free cash-flow | | | | |
| Dette nette | | | | |
| Nombre d'actions diluées | | | | |

Analyse :

- Les moteurs réels de la croissance (annuels et derniers trimestres).
- Les effets prix, volumes, mix, change et acquisitions (ou « Données insuffisantes » si non ventilés).
- La soutenabilité des marges.
- Les écarts entre bénéfices comptables et cash-flow.
- La qualité des bénéfices (y compris surprises BPA).
- Le besoin en fonds de roulement et le cycle de conversion (DSI, DSO, DPO, stocks, créances, fournisseurs).
- Les anomalies comptables ou divergences éventuelles.
- L'effet des rachats d'actions sur le BPA.

Explique ce qui s'améliore réellement et ce qui pourrait masquer une dégradation.

### C. QUALITÉ ÉCONOMIQUE — APPROCHE BUFFETT

Évalue :

- La simplicité et la prévisibilité du modèle économique.
- La capacité de fixation des prix (marge brute et stabilité).
- Les coûts de changement pour les clients.
- Les effets de réseau.
- Les avantages de coûts, d'échelle, de marque ou de réglementation.
- La durabilité des marges.
- La rentabilité du capital investi (ROIC, CROIC, ROE, ROA).
- Le ROIC comparé à un WACC estimé (en précisant l'hypothèse de WACC).
- La capacité de réinvestissement rentable.
- La conversion des bénéfices en cash (FCF / Résultat net).

Détermine si l'entreprise possède un avantage concurrentiel :

**Aucun / Faible / Modéré / Fort / Exceptionnel**

Précise pourquoi cet avantage pourrait se renforcer ou disparaître.

### D. CROISSANCE — APPROCHE PETER LYNCH

Classe l'entreprise :

- Slow grower.
- Stalwart.
- Fast grower.
- Cyclical.
- Turnaround.
- Asset play.

Analyse :

- Le potentiel de croissance sur 3 à 5 ans.
- La taille du marché accessible.
- Les gains ou pertes de parts de marché.
- Les relais de croissance.
- Les risques de saturation.
- Le rapport entre croissance anticipée et valorisation.
- Le PEG, lorsque son utilisation est pertinente.

Distingue croissance structurelle, cyclique et artificielle.

### E. BILAN ET RISQUE DE PERTE PERMANENTE — APPROCHE GRAHAM

Examine :

- Dette nette / EBITDA (et Dette / Capitaux propres, Altman Z-Score, Piotroski F-Score).
- Couverture des intérêts / couverture par l'EBITDA et coût de la dette.
- Liquidité disponible (ratio de liquidité générale, trésorerie).
- Échéancier de dette, besoins de refinancement et engagements hors bilan (« Données insuffisantes » si non fournis dans les états).
- Dilution potentielle (évolution du nombre d'actions).
- Dépendance au financement externe.
- Résilience en scénario de récession et profil de risque boursier (volatilité, semi-volatilité, Max Drawdown, VaR/CVaR 95%, Ulcer, Sharpe, Sortino, Calmar, Martin).

Réponds explicitement :

**Quels événements pourraient provoquer une perte permanente de capital pour l'actionnaire ?**

Classe chaque risque par probabilité qualitative, gravité et horizon.

### F. MANAGEMENT ET ALLOCATION DU CAPITAL — APPROCHE MUNGER

Analyse :

- Équipe dirigeante, incitations et alignement des intérêts (part des initiés et opérations d'initiés fournies).
- Actionnariat institutionnel et principaux fonds.
- Discipline des acquisitions (« Données insuffisantes » si non détaillées).
- Rachats d'actions : création ou destruction de valeur ?
- Dividendes et réinvestissements (rendement, payout ratio, régularité).
- Rémunération en actions / dilution.
- Cohérence stratégique et transparence (ou « Données insuffisantes » pour les déclarations verbales absentes du dossier).

Recherche toute contradiction entre création de valeur opérationnelle et mouvements d'initiés / allocation du capital.

### G. VALORISATION — APPROCHE DAMODARAN

Utilise plusieurs méthodes selon leur pertinence.

**1. Multiples de valorisation**

- PER actuel (TTM) et prévisionnel.
- EV/EBITDA.
- EV/EBIT (si calculable).
- Price / Free Cash Flow (ou rendement FCF).
- EV / Sales (VE/CA).
- Free Cash Flow Yield.
- Comparaison historique sur les exercices disponibles et consensus (objectif de cours).
- Comparaison sectorielle (« Données insuffisantes » si absente du dossier).

**2. DCF simplifié mais explicite**

Présente :

- Free cash-flow de départ normalisé.
- Croissance prévue (hypothèse explicitée).
- Marges futures.
- Réinvestissements nécessaires.
- WACC estimé et justifié (avec bêta disponible).
- Croissance terminale.
- Valeur terminale.
- Dette nette et autres ajustements.
- Nombre d'actions diluées.

Calcule une valeur intrinsèque par action (ou une fourchette) uniquement si les informations sont suffisantes ; sinon explique les hypothèses requises.

**3. Scénarios de valorisation**

| Scénario | Hypothèses clés | Valeur/action | Probabilité |
|---|---|---|---|
| Bear | | | |
| Base | | | |
| Bull | | | |

Calcule la valeur espérée pondérée par les probabilités.

Mesure la marge de sécurité par rapport au cours de référence, daté.

Présente une analyse de sensibilité aux principales hypothèses (WACC / croissance terminale).

Ne crée pas de fausse précision : indique une fourchette lorsque les hypothèses sont incertaines.

### H. ANALYSE DES ANTICIPATIONS DU MARCHÉ — APPROCHE HOWARD MARKS

Détermine :

- Quelles hypothèses de croissance semblent déjà intégrées dans le cours (y compris reverse DCF simplifié si possible).
- Si la valorisation exige une exécution exceptionnelle.
- Les principaux facteurs susceptibles de surprendre positivement ou négativement.
- Les effets du cycle économique et performances ajustées (1M à 10A).
- L'influence des taux d'intérêt, du bêta et de la liquidité.
- Le risque de contraction des multiples.

Distingue clairement :

**Une excellente entreprise** et **un excellent investissement au prix actuel**.

### I. RED FLAGS — ANALYSE FORENSIQUE

Recherche systématiquement (et indique « RAS », « Alerte » ou « Données insuffisantes » pour chacun) :

- Résultat net en hausse mais cash-flow en baisse.
- Créances augmentant plus vite que le chiffre d'affaires.
- Stocks anormalement élevés.
- Multiplication des ajustements non-GAAP.
- Dégradation du besoin en fonds de roulement.
- Capitalisation agressive des dépenses.
- Croissance obtenue principalement par acquisitions.
- Dilution masquée par le BPA ajusté.
- Rachats d'actions financés par dette.
- Dépendance excessive à un client, produit, fournisseur ou zone géographique.

---

DONNÉES COMPLÈTES VÉRIFIÉES DU DOSSIER ({canonical}) :
{context_json}"""

    async def _call_model(target_model: str) -> str:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await post_chat_completion(
                settings,
                {
                    "model": target_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.25,
                    "max_tokens": 16384,
                },
                client=client,
                extra_headers={"HTTP-Referer": "https://clair.app"},
            )
            _check_response(resp, "Fournisseur IA")
            data = _json(resp, "Fournisseur IA")
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            if not content:
                raise ProviderError(f"Le modèle {target_model} a renvoyé une réponse vide.")
            return content

    used_model = chosen_model
    try:
        md = await _call_model(chosen_model)
    except Exception as primary_exc:
        fallback = (settings.default_model or "").strip()
        if fallback and fallback != chosen_model and can_fallback_to_model(settings, chosen_model, fallback):
            _logger.warning(
                "Échec analyse dossier avec %s (%s), repli sur %s", chosen_model, primary_exc, fallback
            )
            used_model = fallback
            md = await _call_model(fallback)
        else:
            raise

    return _finalize_and_save_dossier_analysis(
        db_path,
        canonical=canonical,
        company_name=str(hdr.get("name") or canonical),
        currency=str(dossier["currency"] or ""),
        markdown=md,
        model=used_model,
    )
