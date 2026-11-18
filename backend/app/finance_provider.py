"""Couche d'abstraction unifiée EOD Historical Data (prioritaire) + Yahoo Finance (backup).

Normalise les formats hétérogènes des fournisseurs vers un contrat canonique unique
et orchestre la persistance dans l'entrepôt local `finance_warehouse.db`.
"""

from __future__ import annotations

import logging
import math
import urllib.parse
from typing import Any

import httpx

from .config import Settings
from .finance_statements import (
    STATEMENT_TYPE_BY_KEY,
    build_period_from_series,
    build_statement_type_map,
    extract_eodhd_earnings_history,
    fetch_yahoo_timeseries_bundle,
    merge_statement_series,
    parse_eodhd_fundamentals_to_series,
    parse_timeseries,
)
from .finance_warehouse import (
    get_snapshot,
    get_warehouse_stats,
    load_fundamental_series,
    resolve_canonical_symbol,
    save_snapshot,
    update_exchange_symbol_fund_family,
    upsert_fundamental_facts,
    upsert_instrument,
    warehouse_db_path,
)

_logger = logging.getLogger("uvicorn.error")

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, dict):
        val = val.get("raw")
    if isinstance(val, (int, float)):
        return float(val) if math.isfinite(float(val)) else None
    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned or cleaned.upper() in ("NA", "N/A", "NONE", "NULL", "-"):
            return None
        try:
            parsed = float(cleaned)
            return parsed if math.isfinite(parsed) else None
        except ValueError:
            return None
    return None


def _fmt_num(val: Any, suffix: str = "", default: str = "N/A") -> str:
    if isinstance(val, dict) and val.get("fmt"):
        return f"{val['fmt']}{(' ' + suffix) if suffix else ''}".strip()
    num = _num(val)
    if num is None:
        return default
    abs_v = abs(num)
    if abs_v >= 1e12:
        res = f"{num / 1e12:.2f} T"
    elif abs_v >= 1e9:
        res = f"{num / 1e9:.2f} Mrd"
    elif abs_v >= 1e6:
        res = f"{num / 1e6:.2f} M"
    elif abs_v >= 1e3:
        res = f"{num:,.2f}".replace(",", " ")
    else:
        res = f"{num:.2f}"
    return f"{res} {suffix}".strip() if suffix else res


def _fmt_pct(val: Any, default: str = "N/A") -> str:
    if isinstance(val, dict) and val.get("fmt"):
        return str(val["fmt"])
    num = _num(val)
    if num is None:
        return default
    pct = num * 100 if abs(num) < 1.0 else num
    return f"{pct:+.2f}%"


def _latest_eod_row(section: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(section, dict) or not section:
        return {}
    valid_dates = sorted(k for k in section.keys() if isinstance(section.get(k), dict))
    return section[valid_dates[-1]] if valid_dates else {}


def _map_eod_rating(rating_val: float | None) -> str:
    if rating_val is None or rating_val <= 0:
        return "N/A"
    if rating_val >= 4.3:
        return "STRONG_BUY"
    if rating_val >= 3.5:
        return "BUY"
    if rating_val >= 2.5:
        return "HOLD"
    if rating_val >= 1.7:
        return "UNDERPERFORM"
    return "SELL"


def extract_eodhd_financial_stats(
    fundamentals: dict[str, Any] | None,
    rt_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convertit un payload `/api/fundamentals` EODHD vers la structure canonique `FinancialStats`."""
    if not isinstance(fundamentals, dict) or not fundamentals:
        return {}

    gen = fundamentals.get("General") or {}
    hl = fundamentals.get("Highlights") or {}
    val = fundamentals.get("Valuation") or {}
    tech = fundamentals.get("Technicals") or {}
    div = fundamentals.get("SplitsDividends") or {}
    ratings = fundamentals.get("AnalystRatings") or {}
    fin = fundamentals.get("Financials") or {}

    latest_inc = _latest_eod_row((fin.get("Income_Statement") or {}).get("yearly"))
    latest_bal = _latest_eod_row((fin.get("Balance_Sheet") or {}).get("quarterly")) or _latest_eod_row(
        (fin.get("Balance_Sheet") or {}).get("yearly")
    )
    latest_cf = _latest_eod_row((fin.get("Cash_Flow") or {}).get("yearly"))

    curr_p = _num((rt_data or {}).get("close")) or _num((rt_data or {}).get("previousClose"))
    target_mean = _num(hl.get("WallStreetTargetPrice") or ratings.get("TargetPrice"))
    upside_pct = None
    if curr_p and target_mean and curr_p > 0:
        upside_pct = round(((target_mean - curr_p) / curr_p) * 100, 2)

    rev_ttm = _num(hl.get("RevenueTTM")) or _num(latest_inc.get("totalRevenue"))
    gp_ttm = _num(hl.get("GrossProfitTTM")) or _num(latest_inc.get("grossProfit"))
    gross_margin = (gp_ttm / rev_ttm) if (gp_ttm is not None and rev_ttm and rev_ttm != 0) else None
    ebitda_val = _num(hl.get("EBITDA")) or _num(latest_inc.get("ebitda"))
    net_inc = _num(latest_inc.get("netIncome"))

    total_cash = _num(latest_bal.get("cashAndShortTermInvestments")) or _num(latest_bal.get("cash"))
    total_debt = _num(latest_bal.get("shortLongTermDebtTotal"))
    if total_debt is None:
        st_d = _num(latest_bal.get("shortTermDebt")) or _num(latest_bal.get("shortLongTermDebt"))
        lt_d = _num(latest_bal.get("longTermDebt")) or _num(latest_bal.get("longTermDebtTotal"))
        if st_d is not None or lt_d is not None:
            total_debt = (st_d or 0.0) + (lt_d or 0.0)
    equity = _num(latest_bal.get("totalStockholderEquity"))
    debt_to_equity_pct = (total_debt / equity * 100.0) if (total_debt is not None and equity and equity > 0) else None

    curr_assets = _num(latest_bal.get("totalCurrentAssets"))
    curr_liab = _num(latest_bal.get("totalCurrentLiabilities"))
    inventory = _num(latest_bal.get("inventory")) or 0.0
    current_ratio = (curr_assets / curr_liab) if (curr_assets is not None and curr_liab and curr_liab > 0) else None
    quick_ratio = (
        ((curr_assets - inventory) / curr_liab)
        if (curr_assets is not None and curr_liab and curr_liab > 0)
        else None
    )

    ocf = _num(latest_cf.get("totalCashFromOperatingActivities"))
    capex = _num(latest_cf.get("capitalExpenditures"))
    fcf = _num(latest_cf.get("freeCashFlow"))
    if fcf is None and ocf is not None and capex is not None:
        fcf = ocf - abs(capex)

    opinions_sum = sum(
        int(_num(ratings.get(k)) or 0)
        for k in ("StrongBuy", "Buy", "Hold", "Sell", "StrongSell")
    )
    opinions_count = float(opinions_sum) if opinions_sum > 0 else None
    rec = _map_eod_rating(_num(ratings.get("Rating")))

    div_yield = _num(hl.get("DividendYield")) or _num(div.get("ForwardAnnualDividendYield"))
    div_rate = _num(hl.get("DividendShare")) or _num(div.get("ForwardAnnualDividendRate"))
    payout = _num(div.get("PayoutRatio"))

    mf = fundamentals.get("Mutual_Fund") or fundamentals.get("ETF_Data") or {}
    fund_summary = mf.get("Fund_Summary") if isinstance(mf.get("Fund_Summary"), dict) else {}
    net_assets = _num(mf.get("TotalAssets") or mf.get("NetAssets") or hl.get("NetAssets"))
    expense_ratio = _num(
        mf.get("Ongoing_Charge")
        or mf.get("ExpenseRatio")
        or mf.get("NetExpenseRatio")
        or hl.get("ExpenseRatio")
        or fund_summary.get("Ongoing_Charge")
        or fund_summary.get("NetExpenseRatio")
    )
    if expense_ratio is not None and 0 < abs(expense_ratio) < 0.35:
        expense_ratio_fmt = f"{expense_ratio * 100:.2f}%"
    elif expense_ratio is not None:
        expense_ratio_fmt = f"{expense_ratio:.2f}%"
    else:
        expense_ratio_fmt = None

    return {
        "valuation": {
            "market_cap": _fmt_num(hl.get("MarketCapitalization") or net_assets),
            "market_cap_raw": _num(hl.get("MarketCapitalization") or net_assets),
            "pe_trailing": _fmt_num(val.get("TrailingPE") or hl.get("PERatio")),
            "pe_forward": _fmt_num(val.get("ForwardPE")),
            "peg_ratio": _fmt_num(hl.get("PEGRatio")),
            "price_to_book": _fmt_num(val.get("PriceBookMRQ")),
            "enterprise_value": _fmt_num(val.get("EnterpriseValue")),
            "ev_to_ebitda": _fmt_num(val.get("EnterpriseValueEbitda")),
            "beta": _fmt_num(tech.get("Beta") or mf.get("Beta")),
            "trailing_eps": _fmt_num(hl.get("DilutedEpsTTM") or hl.get("EarningsShare")),
            "forward_eps": _fmt_num(hl.get("EPSEstimateNextYear") or hl.get("EPSEstimateCurrentYear")),
            "dividend_rate": _fmt_num(div_rate),
            "dividend_yield": _fmt_pct(div_yield or mf.get("Yield")),
            "payout_ratio": _fmt_pct(payout),
            "w52_high": _fmt_num(tech.get("52WeekHigh")),
            "w52_low": _fmt_num(tech.get("52WeekLow")),
            **({"expense_ratio": expense_ratio_fmt} if expense_ratio_fmt else {}),
        },
        "profitability": {
            "total_revenue": _fmt_num(rev_ttm),
            "total_revenue_raw": rev_ttm,
            "revenue_growth": _fmt_pct(hl.get("QuarterlyRevenueGrowthYOY")),
            "gross_margin": _fmt_pct(gross_margin),
            "operating_margin": _fmt_pct(hl.get("OperatingMarginTTM")),
            "profit_margin": _fmt_pct(hl.get("ProfitMargin")),
            "ebitda": _fmt_num(ebitda_val),
            "ebitda_raw": ebitda_val,
            "net_income": _fmt_num(net_inc),
            "free_cashflow": _fmt_num(fcf),
            "operating_cashflow": _fmt_num(ocf),
            "roe": _fmt_pct(hl.get("ReturnOnEquityTTM")),
            "roa": _fmt_pct(hl.get("ReturnOnAssetsTTM")),
        },
        "balance_sheet": {
            "total_cash": _fmt_num(total_cash),
            "total_debt": _fmt_num(total_debt),
            "debt_to_equity": _fmt_num(debt_to_equity_pct, suffix="%"),
            "current_ratio": _fmt_num(current_ratio),
            "quick_ratio": _fmt_num(quick_ratio),
            "book_value": _fmt_num(hl.get("BookValue")),
        },
        "analysts": {
            "recommendation": rec,
            "opinions_count": opinions_count,
            "target_mean": _fmt_num(target_mean),
            "target_high": "N/A",
            "target_low": "N/A",
            "upside_potential_pct": upside_pct,
        },
        "profile": {
            "sector": gen.get("Sector") or gen.get("Category") or mf.get("Fund_Category") or "N/A",
            "industry": gen.get("Industry") or gen.get("Fund_Family") or mf.get("Company_Name") or "N/A",
            "country": gen.get("CountryName") or "N/A",
            "employees": _fmt_num(gen.get("FullTimeEmployees"), default="Non communiqué"),
            "website": gen.get("WebURL") or mf.get("Company_URL") or "",
            "summary": (gen.get("Description") or fund_summary.get("Summary") or "")[:1200],
        },
    }


def _is_missing_stat(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        stripped = val.strip()
        return stripped in ("", "N/A", "Non communiqué", "Marché")
    return False


def merge_financial_stats(
    primary_eod: dict[str, Any] | None,
    fallback_yahoo: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    """Fusionne `primary_eod` (prioritaire) et `fallback_yahoo` (secours champ par champ).

    Retourne `(stats_fusionnées, source_provider)`.
    """
    eod = primary_eod or {}
    yah = fallback_yahoo or {}
    has_eod = bool(eod)
    has_yah = bool(yah)
    if not has_eod:
        return yah, ("yahoo_finance" if has_yah else "none")
    if not has_yah:
        return eod, "eodhd"

    merged: dict[str, Any] = {}
    used_yahoo = False
    for section in ("valuation", "profitability", "balance_sheet", "analysts", "profile"):
        e_sec = dict(eod.get(section) or {})
        y_sec = dict(yah.get(section) or {})
        out_sec: dict[str, Any] = {}
        for key in set(e_sec.keys()) | set(y_sec.keys()):
            e_val = e_sec.get(key)
            y_val = y_sec.get(key)
            if not _is_missing_stat(e_val):
                out_sec[key] = e_val
            elif not _is_missing_stat(y_val):
                out_sec[key] = y_val
                used_yahoo = True
            else:
                out_sec[key] = e_val if key in e_sec else y_val
        merged[section] = out_sec

    source = "eodhd+yahoo" if used_yahoo else "eodhd"
    return merged, source


def extract_eodhd_highlights_summary(fundamentals: dict[str, Any] | None) -> dict[str, Any]:
    """Extrait les métadonnées complémentaires EODHD (actionnariat, dividendes, dates)."""
    if not isinstance(fundamentals, dict) or not fundamentals:
        return {}
    shares = fundamentals.get("SharesStats") or {}
    divs = fundamentals.get("SplitsDividends") or {}
    hl = fundamentals.get("Highlights") or {}
    return {
        "shares_outstanding": _num(shares.get("SharesOutstanding")),
        "shares_float": _num(shares.get("SharesFloat")),
        "pct_insiders": _num(shares.get("PercentInsiders")),
        "pct_institutions": _num(shares.get("PercentInstitutions")),
        "ex_dividend_date": divs.get("ExDividendDate") or None,
        "dividend_date": divs.get("DividendDate") or None,
        "forward_dividend_yield": _num(divs.get("ForwardAnnualDividendYield") or hl.get("DividendYield")),
        "payout_ratio": _num(divs.get("PayoutRatio")),
    }


def _candidate_eod_tickers(symbol: str) -> list[str]:
    clean = symbol.strip().upper()
    if not clean:
        return []
    if "." in clean:
        return [clean]
    if clean.startswith("^"):
        return [f"{clean[1:]}.INDX"]
    return [f"{clean}.US", clean]


async def fetch_eodhd_fundamentals_json(ticker: str, api_key: str) -> dict[str, Any] | None:
    """Télécharge `/api/fundamentals/{ticker}` depuis EOD Historical Data."""
    if not api_key or not ticker:
        return None
    url = (
        f"https://eodhd.com/api/fundamentals/{urllib.parse.quote(ticker)}"
        f"?api_token={urllib.parse.quote(api_key)}&fmt=json"
    )
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _DEFAULT_USER_AGENT},
            follow_redirects=True,
            timeout=20.0,
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and any(
                    k in data for k in ("General", "Highlights", "Valuation", "Financials", "Mutual_Fund", "ETF_Data")
                ):
                    return data
    except Exception as exc:
        _logger.warning("Erreur /api/fundamentals EODHD (%s): %s", ticker, exc)
    return None


def persist_eodhd_fundamentals_to_warehouse(
    settings: Settings,
    symbol: str,
    fundamentals: dict[str, Any],
    eod_ticker: str | None = None,
    yahoo_symbol: str | None = None,
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, float | None]], list[dict[str, Any]]]:
    """Normalise et enregistre un payload EODHD `/api/fundamentals` dans l'entrepôt local."""
    db_path = warehouse_db_path(settings)
    gen = fundamentals.get("General") or {}
    currency = (
        str(
            gen.get("CurrencyCode")
            or ((fundamentals.get("Financials") or {}).get("Income_Statement") or {}).get("currency_symbol")
            or ""
        )
        .strip()
        .upper()
    )
    annual_series = parse_eodhd_fundamentals_to_series(fundamentals, "annual")
    quarterly_series = parse_eodhd_fundamentals_to_series(fundamentals, "quarterly")
    earnings_history = extract_eodhd_earnings_history(fundamentals)
    highlights = extract_eodhd_highlights_summary(fundamentals)

    upsert_instrument(
        db_path,
        {
            "symbol": symbol,
            "eod_ticker": eod_ticker or symbol,
            "yahoo_symbol": yahoo_symbol,
            "isin": gen.get("ISIN"),
            "short_name": (gen.get("Name") or "").split(" - ")[0].split(" (")[0].strip() or None,
            "long_name": gen.get("Name"),
            "exchange": gen.get("Exchange"),
            "currency": currency,
            "country": gen.get("CountryName"),
            "sector": gen.get("Sector"),
            "industry": gen.get("Industry"),
        },
    )
    mf = fundamentals.get("Mutual_Fund") or {}
    etf = fundamentals.get("ETF_Data") or {}
    fund_family = (
        mf.get("Fund_Family")
        or etf.get("Company_Name")
        or gen.get("FundFamily")
        or ""
    ).strip()
    if fund_family:
        try:
            update_exchange_symbol_fund_family(db_path, eod_ticker or symbol, fund_family)
        except Exception:
            pass
    if annual_series:
        upsert_fundamental_facts(
            db_path, symbol, "annual", annual_series, build_statement_type_map(annual_series), "eodhd", currency
        )
    if quarterly_series:
        upsert_fundamental_facts(
            db_path, symbol, "quarterly", quarterly_series, build_statement_type_map(quarterly_series), "eodhd", currency
        )
    save_snapshot(
        db_path,
        symbol,
        "eodhd",
        "fundamentals",
        fundamentals,
        {"earnings_history": earnings_history, "highlights": highlights, "currency": currency},
        currency=currency,
    )
    return annual_series, quarterly_series, earnings_history


async def get_unified_financial_statements(
    settings: Settings,
    symbol: str,
    refresh: bool = False,
) -> dict[str, Any]:
    """Renvoie l'historique complet des états financiers (EODHD prioritaire, cache BDD, backup Yahoo)."""
    db_path = warehouse_db_path(settings)
    clean_sym = symbol.strip()
    canonical = resolve_canonical_symbol(db_path, clean_sym)
    ttl_seconds = max(60, int(settings.finance_fundamentals_ttl_hours) * 3600)

    # 1. Lecture depuis l'entrepôt si cache frais et aucun refresh demandé
    if not refresh:
        cached_snap = get_snapshot(db_path, canonical, "fundamentals", max_age_seconds=ttl_seconds)
        ann_series, ann_curr, ann_src, ann_upd = load_fundamental_series(db_path, canonical, "annual")
        qtr_series, qtr_curr, qtr_src, qtr_upd = load_fundamental_series(db_path, canonical, "quarterly")
        # Compléter automatiquement les champs EODHD étendus depuis le snapshot brut si mis en cache avant cette extension
        if (
            cached_snap
            and cached_snap.get("provider") == "eodhd"
            and not any(k.startswith("eod_") for k in ann_series)
            and not any(k.startswith("eod_") for k in qtr_series)
        ):
            raw_snap = get_snapshot(
                db_path, canonical, "fundamentals", provider="eodhd", max_age_seconds=ttl_seconds, include_raw=True
            )
            raw_fund = (raw_snap or {}).get("raw")
            if isinstance(raw_fund, dict) and raw_fund.get("Financials"):
                ext_ann = parse_eodhd_fundamentals_to_series(raw_fund, "annual")
                ext_qtr = parse_eodhd_fundamentals_to_series(raw_fund, "quarterly")
                snap_curr = str(cached_snap.get("currency") or ann_curr or qtr_curr or "")
                if ext_ann:
                    upsert_fundamental_facts(
                        db_path, canonical, "annual", ext_ann, build_statement_type_map(ext_ann), "eodhd", snap_curr
                    )
                    ann_series = merge_statement_series(ext_ann, ann_series)
                if ext_qtr:
                    upsert_fundamental_facts(
                        db_path, canonical, "quarterly", ext_qtr, build_statement_type_map(ext_qtr), "eodhd", snap_curr
                    )
                    qtr_series = merge_statement_series(ext_qtr, qtr_series)
        if cached_snap and (
            ("TotalRevenue" in ann_series or "TotalAssets" in ann_series)
            or ("TotalRevenue" in qtr_series or "TotalAssets" in qtr_series)
        ):
            norm_meta = cached_snap.get("normalized") or {}
            prov = cached_snap.get("provider") or ann_src or qtr_src or "eodhd"
            return {
                "symbol": clean_sym,
                "canonical_symbol": canonical,
                "currency": cached_snap.get("currency") or ann_curr or qtr_curr or norm_meta.get("currency") or "",
                "source_provider": prov,
                "source_label": _provider_label(prov),
                "cached": True,
                "updated_at": cached_snap.get("updated_at") or ann_upd or qtr_upd,
                "warehouse_stats": get_warehouse_stats(db_path, canonical),
                "annual": build_period_from_series(ann_series, annual=True),
                "quarterly": build_period_from_series(qtr_series, annual=False),
                "earnings_history": norm_meta.get("earnings_history") or [],
                "highlights": norm_meta.get("highlights") or {},
            }

    eod_key = (
        settings.eod_historical_data_key.get_secret_value()
        if settings.enabled(settings.eod_historical_data_key)
        else ""
    )

    eod_fundamentals: dict[str, Any] | None = None
    used_eod_ticker: str | None = None
    if eod_key:
        for cand in _candidate_eod_tickers(canonical):
            payload = await fetch_eodhd_fundamentals_json(cand, eod_key)
            if payload:
                eod_fundamentals = payload
                used_eod_ticker = cand
                break
        if eod_fundamentals is None and canonical != clean_sym.upper():
            for cand in _candidate_eod_tickers(clean_sym):
                payload = await fetch_eodhd_fundamentals_json(cand, eod_key)
                if payload:
                    eod_fundamentals = payload
                    used_eod_ticker = cand
                    break

    ann_eod: dict[str, dict[str, float | None]] = {}
    qtr_eod: dict[str, dict[str, float | None]] = {}
    earnings_history: list[dict[str, Any]] = []
    highlights: dict[str, Any] = {}
    currency = ""

    if eod_fundamentals:
        ann_eod, qtr_eod, earnings_history = persist_eodhd_fundamentals_to_warehouse(
            settings,
            canonical,
            eod_fundamentals,
            eod_ticker=used_eod_ticker,
            yahoo_symbol=clean_sym.upper(),
        )
        highlights = extract_eodhd_highlights_summary(eod_fundamentals)
        currency = str((eod_fundamentals.get("General") or {}).get("CurrencyCode") or "").strip().upper()

    # 2. Backup Yahoo Finance si EODHD indisponible ou sans séries d'états financiers (sauf fonds EUFUND)
    ann_yah: dict[str, dict[str, float | None]] = {}
    qtr_yah: dict[str, dict[str, float | None]] = {}
    if not ann_eod and not qtr_eod and not canonical.upper().endswith(".EUFUND"):
        yahoo_lookup = clean_sym[:-3] if clean_sym.upper().endswith(".US") else clean_sym
        y_annual_raw, y_quarterly_raw = await fetch_yahoo_timeseries_bundle(yahoo_lookup)
        ann_yah = parse_timeseries(y_annual_raw, "annual")
        qtr_yah = parse_timeseries(y_quarterly_raw, "quarterly")
        if ann_yah or qtr_yah:
            upsert_instrument(db_path, {"symbol": canonical, "yahoo_symbol": yahoo_lookup.upper()})
            if ann_yah:
                upsert_fundamental_facts(
                    db_path, canonical, "annual", ann_yah, STATEMENT_TYPE_BY_KEY, "yahoo_finance", currency
                )
            if qtr_yah:
                upsert_fundamental_facts(
                    db_path, canonical, "quarterly", qtr_yah, STATEMENT_TYPE_BY_KEY, "yahoo_finance", currency
                )
            save_snapshot(
                db_path,
                canonical,
                "yahoo_finance",
                "fundamentals",
                {"annual": y_annual_raw, "quarterly": y_quarterly_raw},
                {"earnings_history": [], "highlights": {}, "currency": currency},
                currency=currency,
            )

    # 3. Relire l'historique cumulé en entrepôt pour conserver les anciens exercices déjà téléchargés
    stored_ann, stored_curr_a, stored_src_a, upd_a = load_fundamental_series(db_path, canonical, "annual")
    stored_qtr, stored_curr_q, stored_src_q, upd_q = load_fundamental_series(db_path, canonical, "quarterly")

    final_ann = merge_statement_series(ann_eod or ann_yah, stored_ann)
    final_qtr = merge_statement_series(qtr_eod or qtr_yah, stored_qtr)

    if ann_eod or qtr_eod:
        prov = "eodhd"
    elif ann_yah or qtr_yah:
        prov = "yahoo_finance"
    else:
        prov = stored_src_a or stored_src_q or "yahoo_finance"

    return {
        "symbol": clean_sym,
        "canonical_symbol": canonical,
        "currency": currency or stored_curr_a or stored_curr_q or "",
        "source_provider": prov,
        "source_label": _provider_label(prov),
        "cached": False,
        "updated_at": upd_a or upd_q,
        "warehouse_stats": get_warehouse_stats(db_path, canonical),
        "annual": build_period_from_series(final_ann, annual=True),
        "quarterly": build_period_from_series(final_qtr, annual=False),
        "earnings_history": earnings_history,
        "highlights": highlights,
    }


def _provider_label(provider: str) -> str:
    if provider == "eodhd":
        return "EOD Historical Data"
    if provider == "eodhd+yahoo":
        return "EOD Historical Data + Yahoo Finance"
    if provider == "yahoo_finance":
        return "Yahoo Finance (secours)"
    return provider or "Source unifiée"
