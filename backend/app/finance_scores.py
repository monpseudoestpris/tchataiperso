"""Moteur de calcul des 31 scores et indicateurs Uncle Stock.

Implémente les deux modes recommandés par le guide :
- `documented` (« Uncle Stock documenté ») : applique littéralement les facteurs,
  bornes et dénominateurs publiés, tout en traçant les anomalies mathématiques en `warnings`.
- `verified` (« interprété / vérifié ») : corrige les anomalies arithmétiques connues
  (dénominateurs alignés sur l'intervalle réel, étirement sigmoïde paramétré, signe
  Dechow F-Score standard, facteur 3e-9 sur Slater, priorité sectorielle Trap Score).

Chaque score retourne un contrat `ScoreResult` explicable (`components`, `warnings`,
`raw_score`, `clamped_score`, `normalized_score`, `final_score`).
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from .finance_intrinsic import _ols_linear, compute_rcagr_67

_SOURCE_VERSION = "unclestock-scores-v1"


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _signed_log(val: float) -> float:
    """Logarithme signé Uncle Stock : sign(x) * ln(1 + |x|)."""
    if not math.isfinite(val):
        return 0.0
    sign = 1.0 if val > 0 else (-1.0 if val < 0 else 0.0)
    return sign * math.log(1.0 + abs(val))


def _clamp(val: float, lo: float | None = None, hi: float | None = None) -> float:
    if lo is not None and val < lo:
        val = lo
    if hi is not None and val > hi:
        val = hi
    return val


def _logistic(x: float) -> float:
    x_c = _clamp(x, -60.0, 60.0)
    return 1.0 / (1.0 + math.exp(-x_c))


def _sigmoid_stretch(prob: float, k: float = 4.0) -> float:
    """Étire doucement les valeurs autour de 0,50 tout en restant dans [0, 1]."""
    p = _clamp(prob, 0.0, 1.0)
    raw = _logistic(k * (p - 0.5))
    lo = _logistic(-k * 0.5)
    hi = _logistic(k * 0.5)
    return (raw - lo) / (hi - lo) if hi > lo else p


def _weighted_log_normalize(raw: float, k: float = 0.25) -> float:
    """Projette un score log brut sur [0, 100] via une sigmoïde centrée en 0."""
    return round(_logistic(raw * k) * 100.0, 1)


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    v = a / b
    return v if math.isfinite(v) else None


def _series_vals(
    series: dict[str, Any],
    key: str,
    dates: list[str] | None = None,
) -> list[float | None]:
    raw = series.get(key)
    if isinstance(raw, dict):
        if dates:
            return [_num(raw.get(d)) for d in dates]
        return [_num(raw[d]) for d in sorted(raw.keys())]
    if isinstance(raw, (list, tuple)):
        return [_num(v) for v in raw]
    return []


def _latest(vals: list[float | None], back: int = 0) -> float | None:
    """Retourne la dernière valeur non nulle (ou `back` crans valides en arrière)."""
    valid = [v for v in vals if v is not None]
    idx = len(valid) - 1 - back
    if idx < 0 or idx >= len(valid):
        return None
    return valid[idx]


def _pair_latest(vals: list[float | None]) -> tuple[float | None, float | None]:
    """Retourne (valeur N-1, valeur N) sur les deux derniers points connus."""
    valid = [v for v in vals if v is not None]
    if len(valid) < 2:
        return None, (valid[-1] if valid else None)
    return valid[-2], valid[-1]


def _avg_last(vals: list[float | None], n: int) -> float | None:
    valid = [v for v in vals if v is not None][-n:]
    return (sum(valid) / len(valid)) if valid else None


def _wavg_last(vals: list[float | None], n: int = 5) -> float | None:
    valid = [v for v in vals if v is not None][-n:]
    if not valid:
        return None
    weights = list(range(1, len(valid) + 1))
    return sum(v * w for v, w in zip(valid, weights)) / sum(weights)


def _cagr(vals: list[float | None], years: int) -> float | None:
    """Taux de croissance annuel composé décimal sur `years` pas (ex. 0,12 = +12%)."""
    valid = [v for v in vals if v is not None]
    if len(valid) < 2:
        return None
    step = min(years, len(valid) - 1)
    v0 = valid[-1 - step]
    v1 = valid[-1]
    if v0 <= 0 or v1 <= 0 or step <= 0:
        return None
    return (v1 / v0) ** (1.0 / step) - 1.0


def _yoy(vals: list[float | None]) -> float | None:
    prev, cur = _pair_latest(vals)
    if prev is None or cur is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def _rcagr_dec(vals: list[float | None], max_len: int = 15, penalize_67: bool = False) -> float | None:
    clean = [v for v in vals[-max_len:] if v is not None]
    if len(clean) < 3:
        return None
    g_prudent, g_raw = compute_rcagr_67(clean, max_years=max_len)
    return g_prudent if penalize_67 else (g_raw if g_raw is not None else g_prudent)


def _r2_series(vals: list[float | None]) -> float | None:
    clean = [(float(i), v) for i, v in enumerate(vals) if v is not None]
    if len(clean) < 3:
        return None
    xs = [p[0] for p in clean]
    ys = [p[1] for p in clean]
    ols = _ols_linear(xs, ys)
    if not ols:
        return None
    slope, intercept, _ = ols
    mean_y = sum(ys) / len(ys)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot <= 0:
        return 1.0
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    return max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))


def _pct_to_dec(raw: Any) -> float | None:
    v = _num(raw)
    if v is None:
        return None
    return (v / 100.0) if abs(v) > 2.5 else v


def _pct_already(raw: Any) -> float | None:
    v = _num(raw)
    if v is None:
        return None
    return (v * 100.0) if abs(v) <= 2.5 else v


def _comp(
    name: str,
    raw_in: float | None,
    transformed: float | None,
    weight: float,
    contribution: float | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "input": round(raw_in, 4) if raw_in is not None else None,
        "transformed_input": round(transformed, 4) if transformed is not None else None,
        "weight": weight,
        "contribution": round(contribution, 4) if contribution is not None else None,
    }


def _score_result(
    *,
    score_id: str,
    name: str,
    category: str,
    unit: str,
    available: bool,
    raw_score: float | None = None,
    clamped_score: float | None = None,
    normalized_score: float | None = None,
    final_score: float | None = None,
    display_value: str = "—",
    components: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    summary: str = "",
) -> dict[str, Any]:
    return {
        "id": score_id,
        "name": name,
        "category": category,
        "unit": unit,
        "available": available,
        "raw_score": round(raw_score, 3) if raw_score is not None else None,
        "clamped_score": round(clamped_score, 3) if clamped_score is not None else None,
        "normalized_score": round(normalized_score, 2) if normalized_score is not None else None,
        "final_score": round(final_score, 2) if final_score is not None else None,
        "display_value": display_value,
        "components": components or [],
        "warnings": warnings or [],
        "summary": summary,
        "source_version": _SOURCE_VERSION,
    }


def _compute_log_weighted_score(
    terms: list[tuple[str, float, float | None, float | None, float | None]],
) -> tuple[float, list[dict[str, Any]], int]:
    """Évalue Σ w * L(clamp(val, lo, hi)). Retourne (total, components, used_count)."""
    total = 0.0
    comps: list[dict[str, Any]] = []
    used = 0
    for label, weight, val, lo, hi in terms:
        if val is None or not math.isfinite(val):
            comps.append(_comp(label, None, None, weight, None))
            continue
        used += 1
        val_c = _clamp(val, lo, hi)
        tr = _signed_log(val_c)
        contrib = weight * tr
        total += contrib
        comps.append(_comp(label, val, tr, weight, contrib))
    return total, comps, used


def _compute_price_metrics(bars: list[dict[str, Any]] | None, current_price: float | None) -> dict[str, float | None]:
    """Calcule rCAGR, rendement 1 an, 6 mois, 30j/60j, distance MM50, LTM/STM reversal et SD 252."""
    out: dict[str, float | None] = {
        "price_rcagr": None,
        "ret_1y": None,
        "ret_6m": None,
        "ret_30d": None,
        "ret_60d": None,
        "ma50_diff": None,
        "ltm_rev": None,
        "stm_rev": None,
        "price_sd_252": None,
    }
    if not bars:
        return out
    closes = [float(b.get("adjusted_close") or b.get("close")) for b in bars if (b.get("adjusted_close") or b.get("close")) is not None]
    if len(closes) < 20:
        return out
    cur = current_price if (current_price and current_price > 0) else closes[-1]

    if len(closes) >= 252:
        out["ret_1y"] = (cur / closes[-252]) - 1.0
        rets = [(closes[i] / closes[i - 1]) - 1.0 for i in range(len(closes) - 251, len(closes)) if closes[i - 1] > 0]
        if len(rets) >= 30:
            out["price_sd_252"] = statistics.stdev(rets) * math.sqrt(252.0)
    if len(closes) >= 126:
        out["ret_6m"] = (cur / closes[-126]) - 1.0
    if len(closes) >= 43:
        out["ret_60d"] = (cur / closes[-43]) - 1.0
    if len(closes) >= 22:
        out["ret_30d"] = (cur / closes[-22]) - 1.0
    if len(closes) >= 50:
        ma50 = sum(closes[-50:]) / 50.0
        if ma50 > 0:
            out["ma50_diff"] = (cur / ma50) - 1.0
    if len(closes) >= 260:
        # Retournement moyen / long terme approx. vs moyenne 1Y / 3Y
        ma252 = sum(closes[-252:]) / 252.0
        if ma252 > 0:
            out["ltm_rev"] = (cur / ma252) - 1.0
    if out["ret_30d"] is not None:
        out["stm_rev"] = -out["ret_30d"]

    # rCAGR annualisé sur barres échantillonnées mensuellement (~21 séances)
    monthly = closes[::21]
    if len(monthly) >= 6:
        ols = _ols_linear([float(i) / 12.0 for i in range(len(monthly))], [math.log(c) for c in monthly if c > 0])
        if ols:
            out["price_rcagr"] = math.exp(ols[0]) - 1.0
    return out


def _extract_fundamental_bundle(
    ann_series: dict[str, list[float | None]],
    dates: list[str],
    current_price: float | None,
    shares_override: float | None,
    eod_fund: dict[str, Any] | None,
    capital_valuation: dict[str, Any] | None,
    intrinsic_valuation: dict[str, Any] | None,
    piotroski_latest: int | None,
    bars: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Construit l'ensemble des ratios intermédiaires normalisés utilisés par les 31 scores."""
    n = len(dates)

    def pad(key: str) -> list[float | None]:
        raw = _series_vals(ann_series, key, dates)
        if len(raw) < n:
            return [None] * (n - len(raw)) + raw
        return raw[-n:]

    rev = pad("TotalRevenue")
    gp = pad("GrossProfit")
    opinc = pad("OperatingIncome")
    ebitda = pad("EBITDA")
    ebit = pad("EBIT")
    ni = pad("NetIncome")
    eps = pad("DilutedEPS")
    cfo = pad("OperatingCashFlow")
    capex = pad("CapitalExpenditure")
    fcf = pad("FreeCashFlow")
    assets = pad("TotalAssets")
    ca = pad("CurrentAssets")
    cl = pad("CurrentLiabilities")
    cash = pad("CashCashEquivalentsAndShortTermInvestments")
    cash_pure = pad("CashAndCashEquivalents")
    ar = pad("AccountsReceivable")
    inv = pad("Inventory")
    ppe = pad("NetPPE")
    gw = pad("GoodwillAndIntangibleAssets")
    liab = pad("TotalLiabilitiesNetMinorityInterest")
    lt_debt = pad("LongTermDebt")
    tot_debt = pad("TotalDebt")
    net_debt = pad("NetDebt")
    eq = pad("StockholdersEquity")
    ret_earn = pad("RetainedEarnings")
    wc = pad("WorkingCapital")
    shares_l = pad("CommonStockSharesOutstanding")
    div_paid = pad("CashDividendsPaid")
    repurch = pad("RepurchaseOfCapitalStock")
    debt_iss = pad("IssuanceOfDebt")
    sga = pad("SellingGeneralAndAdministration")
    rnd = pad("ResearchAndDevelopment")
    da = pad("DepreciationAndAmortization")
    tax = pad("TaxProvision")
    pretax = pad("PretaxIncome")

    # Séries dérivées multi-exercices
    fcf_l: list[float | None] = []
    cash_l: list[float | None] = []
    cap_inv_l: list[float | None] = []
    tbv_l: list[float | None] = []
    roe_l: list[float | None] = []
    roa_l: list[float | None] = []
    roce_l: list[float | None] = []
    croic_l: list[float | None] = []
    gm_l: list[float | None] = []
    om_l: list[float | None] = []
    nm_l: list[float | None] = []
    at_l: list[float | None] = []
    fat_l: list[float | None] = []
    gp_assets_l: list[float | None] = []
    nwc_assets_l: list[float | None] = []
    eq_ratio_l: list[float | None] = []
    curr_r_l: list[float | None] = []
    quick_r_l: list[float | None] = []
    tax_r_l: list[float | None] = []
    nopat_l: list[float | None] = []
    dso_l: list[float | None] = []
    dio_l: list[float | None] = []
    depr_rate_l: list[float | None] = []
    other_ca_rev_l: list[float | None] = []
    cfo_ni_l: list[float | None] = []
    accruals_assets_l: list[float | None] = []
    nor_l: list[float | None] = []

    for i in range(n):
        c_val = cash[i] if cash[i] is not None else cash_pure[i]
        cash_l.append(c_val)
        f_val = fcf[i]
        if f_val is None and cfo[i] is not None and capex[i] is not None:
            f_val = cfo[i] - abs(capex[i])
        fcf_l.append(f_val)

        eb = ebit[i] if ebit[i] is not None else opinc[i]
        tr = _div(tax[i], pretax[i]) if (tax[i] is not None and pretax[i] and pretax[i] > 0) else 0.25
        tr = _clamp(tr if tr is not None else 0.25, 0.0, 0.50)
        tax_r_l.append(tr)
        nopat_l.append(eb * (1.0 - tr) if eb is not None else None)

        d_val = tot_debt[i] if tot_debt[i] is not None else 0.0
        eq_val = eq[i]
        ci = (eq_val + d_val - (c_val or 0.0)) if eq_val is not None else None
        cap_inv_l.append(ci)
        tbv_l.append((eq_val - (gw[i] or 0.0)) if eq_val is not None else None)

        roe_l.append(_div(ni[i], eq_val) if (eq_val and eq_val > 0) else None)
        roa_l.append(_div(ni[i], assets[i]) if (assets[i] and assets[i] > 0) else None)
        ce = (assets[i] - (cl[i] or 0.0)) if assets[i] is not None else None
        roce_l.append(_div(eb, ce) if (ce and ce > 0) else None)
        croic_l.append(_div(f_val, ci) if (ci and ci > 0) else None)

        gm_l.append(_div(gp[i], rev[i]) if (rev[i] and rev[i] > 0) else None)
        om_l.append(_div(opinc[i], rev[i]) if (rev[i] and rev[i] > 0) else None)
        nm_l.append(_div(ni[i], rev[i]) if (rev[i] and rev[i] > 0) else None)
        at_l.append(_div(rev[i], assets[i]) if (assets[i] and assets[i] > 0) else None)
        fat_l.append(_div(rev[i], ppe[i]) if (ppe[i] and ppe[i] > 0) else None)
        gp_assets_l.append(_div(gp[i], assets[i]) if (assets[i] and assets[i] > 0) else None)

        nwc = wc[i] if wc[i] is not None else ((ca[i] - cl[i]) if (ca[i] is not None and cl[i] is not None) else None)
        nwc_assets_l.append(_div(nwc, assets[i]) if (assets[i] and assets[i] > 0) else None)
        eq_ratio_l.append(_div(eq_val, assets[i]) if (assets[i] and assets[i] > 0) else None)
        curr_r_l.append(_div(ca[i], cl[i]) if (cl[i] and cl[i] > 0) else None)
        quick_num = (ca[i] - (inv[i] or 0.0)) if ca[i] is not None else None
        quick_r_l.append(_div(quick_num, cl[i]) if (cl[i] and cl[i] > 0) else None)

        cogs = (rev[i] - gp[i]) if (rev[i] is not None and gp[i] is not None) else None
        dso_l.append((ar[i] / rev[i] * 365.0) if (ar[i] is not None and rev[i] and rev[i] > 0) else None)
        dio_l.append((inv[i] / abs(cogs) * 365.0) if (inv[i] is not None and cogs and cogs != 0) else None)
        depr_rate_l.append(_div(da[i], (da[i] + ppe[i])) if (da[i] is not None and ppe[i] is not None and (da[i] + ppe[i]) > 0) else None)
        other_ca = (ca[i] - (c_val or 0.0) - (ar[i] or 0.0) - (inv[i] or 0.0)) if ca[i] is not None else None
        other_ca_rev_l.append(_div(other_ca, rev[i]) if (other_ca is not None and rev[i] and rev[i] > 0) else None)
        cfo_ni_l.append(_div(cfo[i], ni[i]) if (cfo[i] is not None and ni[i] and ni[i] > 0) else None)
        accruals_assets_l.append(_div((ni[i] - cfo[i]), assets[i]) if (ni[i] is not None and cfo[i] is not None and assets[i] and assets[i] > 0) else None)
        # Net Owner Return proxy: ΔEq + Dividendes - Charge équité(8% approx)
        if i > 0 and eq[i] is not None and eq[i - 1] and eq[i - 1] > 0:
            dv = abs(div_paid[i] or 0.0)
            nor_l.append((eq[i] + dv - 0.08 * eq[i - 1] - eq[i - 1]) / eq[i - 1])
        else:
            nor_l.append(None)

    cv = capital_valuation or {}
    hl = (eod_fund or {}).get("Highlights") or {}
    val_sec = (eod_fund or {}).get("Valuation") or {}
    sh_st = (eod_fund or {}).get("SharesStats") or {}
    gen = (eod_fund or {}).get("General") or {}
    est = ((eod_fund or {}).get("Earnings") or {}).get("Trend") or {}

    shares = shares_override or _latest(shares_l) or _num(sh_st.get("SharesOutstanding"))
    mcap = _num(cv.get("market_cap")) or _num(hl.get("MarketCapitalization")) or (
        (current_price * shares) if (current_price and shares and shares > 0) else None
    )
    cur_debt = _latest(tot_debt) or 0.0
    cur_cash = _latest(cash_l) or 0.0
    cur_nd = _latest(net_debt)
    if cur_nd is None:
        cur_nd = cur_debt - cur_cash
    ev = (mcap + cur_nd) if mcap is not None else None

    cur_rev = _latest(rev)
    cur_gp = _latest(gp)
    cur_opinc = _latest(opinc)
    cur_ebit = _latest(ebit) or cur_opinc
    cur_ebitda = _latest(ebitda)
    cur_ni = _latest(ni)
    cur_eps = _latest(eps) or _num(hl.get("EarningsShare"))
    cur_cfo = _latest(cfo)
    cur_fcf = _latest(fcf_l)
    cur_nopat = _latest(nopat_l)
    cur_assets = _latest(assets)
    cur_ca = _latest(ca)
    cur_cl = _latest(cl)
    cur_liab = _latest(liab)
    cur_eq = _latest(eq)
    cur_tbv = _latest(tbv_l)
    cur_lt_debt = _latest(lt_debt)
    cur_div = abs(_latest(div_paid) or 0.0) if _latest(div_paid) is not None else None
    cur_repurch = _latest(repurch)  # souvent négatif dans les flux
    buyback_pos = abs(cur_repurch) if (cur_repurch is not None and cur_repurch < 0) else (
        -cur_repurch if cur_repurch is not None else None
    )

    # Rendements & multiples
    pe = _num(cv.get("pe_ttm")) or (_div(current_price, cur_eps) if (current_price and cur_eps and cur_eps > 0) else None)
    pb = _num(cv.get("pb")) or (_div(mcap, cur_eq) if (mcap and cur_eq and cur_eq > 0) else None)
    peg = _num(cv.get("peg"))
    book_to_market = (1.0 / pb) if (pb and pb > 0) else (_div(cur_eq, mcap) if (mcap and mcap > 0 and cur_eq is not None) else None)

    div_yield = _pct_to_dec(cv.get("dividend_yield_pct")) or _pct_to_dec(hl.get("DividendYield"))
    if div_yield is None and cur_div is not None and mcap and mcap > 0:
        div_yield = cur_div / mcap
    buyback_yield = _div(buyback_pos, mcap) if (buyback_pos is not None and mcap and mcap > 0) else None
    net_payout_yield = (
        (div_yield or 0.0) + (buyback_yield or 0.0)
        if (div_yield is not None or buyback_yield is not None)
        else None
    )

    eps_yield = (1.0 / pe) if (pe and pe > 0) else (_div(cur_ni, mcap) if (cur_ni is not None and mcap and mcap > 0) else None)
    ebit_yield = _div(cur_ebit, ev) if (ev and ev > 0) else _div(cur_ebit, mcap)
    ebitda_yield = _div(cur_ebitda, ev) if (ev and ev > 0) else _div(cur_ebitda, mcap)
    opinc_yield = _div(cur_opinc, ev) if (ev and ev > 0) else _div(cur_opinc, mcap)
    rev_yield_ev = _div(cur_rev, ev) if (ev and ev > 0) else None
    rev_yield_price = _div(cur_rev, mcap) if (mcap and mcap > 0) else None
    fcf_yield = _div(cur_fcf, mcap) if (mcap and mcap > 0) else None
    cfo_yield = _div(cur_cfo, mcap) if (mcap and mcap > 0) else None
    cash_nopat_yield = _div(cur_nopat, ev) if (ev and ev > 0) else _div(cur_nopat, mcap)
    payout_ratio = _div(cur_div, cur_ni) if (cur_div is not None and cur_ni and cur_ni > 0) else None

    # Actifs nets (NCAV / NNWC / Non-cash / Fixed)
    ncav = (cur_ca - cur_liab) if (cur_ca is not None and cur_liab is not None) else None
    cur_ar = _latest(ar) or 0.0
    cur_inv = _latest(inv) or 0.0
    nnwc = (cur_cash + 0.75 * cur_ar + 0.5 * cur_inv - cur_liab) if (cur_liab is not None and cur_ca is not None) else None
    non_cash_assets = (cur_assets - cur_cash) if cur_assets is not None else None
    cur_ppe = _latest(ppe)

    # Estimations analystes / révisions
    rec_val = _num(((eod_fund or {}).get("AnalystRatings") or {}).get("Rating"))
    fwd_rev_g = _pct_to_dec(hl.get("QuarterlyRevenueGrowthYOY"))
    fwd_eps_g = _pct_to_dec(cv.get("eps_growth_q_yoy"))
    if isinstance(est, dict):
        # Tente d'extraire la révision / croissance estimée EODHD
        for _, v_est in est.items():
            if isinstance(v_est, dict) and v_est.get("period") in ("+1y", "0y"):
                g_e = _pct_to_dec(v_est.get("growth"))
                if g_e is not None and fwd_eps_g is None:
                    fwd_eps_g = g_e

    price_m = _compute_price_metrics(bars, current_price)
    target_price = _num(cv.get("target_price"))
    expected_price_growth = ((target_price / current_price) - 1.0) if (target_price and current_price and current_price > 0) else None

    iv_obj = intrinsic_valuation or {}
    iv_corr = _num(((iv_obj.get("summary") or {}).get("corrected") or {}).get("intrinsic_value"))
    iv_us = _num(((iv_obj.get("summary") or {}).get("unclestock") or {}).get("intrinsic_value"))
    iv_val = iv_corr or iv_us
    p_iv = (current_price / iv_val) if (current_price and iv_val and iv_val > 0) else None

    country = str(gen.get("CountryName") or gen.get("CountryISO") or "").upper()
    sector = str(gen.get("Sector") or "").lower()

    return {
        "n": n,
        "dates": dates,
        "sector": sector,
        "country": country,
        "currency_mcap_usd": mcap,  # proxy si USD/EUR
        "mcap": mcap,
        "ev": ev,
        "price": current_price,
        "shares": shares,
        "iv_val": iv_val,
        "p_iv": p_iv,
        "pe": pe,
        "pe_5y_avg": _div(_wavg_last([mcap / sh if (mcap and sh) else None for sh in shares_l], 5), _wavg_last(eps, 5)) if False else pe,
        "pb": pb,
        "peg": peg,
        "book_to_market": book_to_market,
        "ev_ebitda": _num(cv.get("ev_ebitda")) or _div(ev, cur_ebitda),
        "p_tbv": _div(mcap, cur_tbv) if (mcap and cur_tbv and cur_tbv > 0) else None,
        "p_non_cash": _div(mcap, non_cash_assets) if (mcap and non_cash_assets and non_cash_assets > 0) else None,
        "p_nnwc": _div(mcap, nnwc) if (mcap and nnwc and nnwc > 0) else None,
        "p_ncav": _div(mcap, ncav) if (mcap and ncav and ncav > 0) else None,
        "p_fixed": _div(mcap, cur_ppe) if (mcap and cur_ppe and cur_ppe > 0) else None,
        "price_to_liab": _div(mcap, cur_liab) if (mcap and cur_liab and cur_liab > 0) else None,
        "epv_to_assets": _div(_div(cur_nopat, 0.09), cur_assets) if (cur_nopat is not None and cur_assets and cur_assets > 0) else None,
        "payback_ratio": _div(mcap, cur_fcf * 5.0) if (mcap and cur_fcf and cur_fcf > 0) else None,
        # Cash & yields
        "div_yield": div_yield,
        "buyback_yield": buyback_yield,
        "net_payout_yield": net_payout_yield,
        "div_rcagr_67": _rcagr_dec([abs(x) if x is not None else None for x in div_paid], 10, True),
        "eps_yield": eps_yield,
        "ebit_yield": ebit_yield,
        "ebitda_yield": ebitda_yield,
        "opinc_yield": opinc_yield,
        "rev_yield_ev": rev_yield_ev,
        "rev_yield_price": rev_yield_price,
        "fcf_yield": fcf_yield,
        "cfo_yield": cfo_yield,
        "cash_nopat_yield": cash_nopat_yield,
        "payout_ratio": payout_ratio,
        # Rentabilité & efficacité
        "croic": _latest(croic_l),
        "croic_3y": _avg_last(croic_l, 3),
        "croic_w5": _wavg_last(croic_l, 5),
        "roce": _latest(roce_l),
        "roce_3y": _avg_last(roce_l, 3),
        "roce_5y": _avg_last(roce_l, 5),
        "roe": _latest(roe_l),
        "roa": _latest(roa_l),
        "roa_yoy": _yoy(roa_l),
        "roa_diff": (_latest(roa_l) - _latest(roa_l, 1)) if (_latest(roa_l) is not None and _latest(roa_l, 1) is not None) else None,
        "roa_avg": _avg_last(roa_l, 5),
        "cash_roa": _div(cur_cfo, cur_assets) if (cur_assets and cur_assets > 0) else None,
        "gross_prof": _wavg_last(gp_assets_l, 5),
        "asset_turnover": _latest(at_l),
        "asset_turnover_w5": _wavg_last(at_l, 5),
        "asset_turnover_yoy": _yoy(at_l),
        "fixed_asset_turnover_w5": _wavg_last(fat_l, 5),
        "gross_margin": _latest(gm_l),
        "gross_margin_w5": _wavg_last(gm_l, 5),
        "gross_margin_yoy": _yoy(gm_l),
        "op_margin": _latest(om_l),
        "op_margin_w5": _wavg_last(om_l, 5),
        "net_margin": _latest(nm_l),
        # Croissance & R2
        "rev_rcagr_15": _rcagr_dec(rev, 15, False),
        "rev_rcagr_67": _rcagr_dec(rev, 15, True),
        "rev_5y_cagr": _cagr(rev, 5),
        "rev_3y_cagr": _cagr(rev, 3),
        "ebitda_rcagr_15": _rcagr_dec(ebitda, 15, False),
        "opinc_rcagr_15": _rcagr_dec(opinc, 15, False),
        "cfo_rcagr_15": _rcagr_dec(cfo, 15, False),
        "fcff_rcagr_15": _rcagr_dec(fcf_l, 15, False),
        "ni_5y_cagr": _cagr(ni, 5),
        "eps_1y_growth": _yoy(eps),
        "eps_rcagr_67": _rcagr_dec(eps, 10, True),
        "tbv_rcagr_15": _rcagr_dec(tbv_l, 15, False),
        "nor_5y_cagr": _avg_last(nor_l, 5),
        "fwd_rev_g": fwd_rev_g,
        "fwd_eps_g": fwd_eps_g,
        "opinc_r2": _r2_series(opinc),
        "rev_r2": _r2_series(rev),
        "gm_r2": _r2_series(gm_l),
        # Bilan & liquidité
        "cur_assets": cur_assets,
        "cur_cl": cur_cl,
        "cur_liab": cur_liab,
        "cur_eq": cur_eq,
        "cur_ni": cur_ni,
        "cur_cfo": cur_cfo,
        "cur_ebit": cur_ebit,
        "cur_rev": cur_rev,
        "cur_ret_earn": _latest(ret_earn),
        "cur_nwc_assets": _latest(nwc_assets_l),
        "cur_quick": _latest(quick_r_l),
        "cur_current": _latest(curr_r_l),
        "current_yoy": _yoy(curr_r_l),
        "equity_ratio": _latest(eq_ratio_l),
        "debt_ratio": _div(cur_debt, cur_assets) if (cur_assets and cur_assets > 0) else None,
        "liab_to_equity": _div(cur_liab, cur_eq) if (cur_eq and cur_eq > 0) else None,
        "net_debt_to_equity": _div(cur_nd, cur_eq) if (cur_eq and cur_eq > 0) else None,
        "net_debt_to_ebitda": _div(cur_nd, cur_ebitda) if (cur_ebitda and cur_ebitda > 0) else None,
        "debt_to_tbv": _div(cur_debt, cur_tbv) if (cur_tbv and cur_tbv > 0) else None,
        "cf_coverage": _div(cur_cfo, cur_debt) if cur_debt > 0 else (1.0 if (cur_cfo and cur_cfo > 0) else None),
        "fcf_to_lt_debt": _div(cur_fcf, cur_lt_debt) if (cur_lt_debt and cur_lt_debt > 0) else (1.0 if (cur_fcf and cur_fcf > 0) else None),
        "lt_debt_yoy": _yoy(lt_debt),
        "inv_1y_growth": _yoy(inv),
        "assets_1y_growth": _yoy(assets),
        "abs_sloan": abs(_latest(accruals_assets_l)) if _latest(accruals_assets_l) is not None else None,
        "accruals_assets": _latest(accruals_assets_l),
        "ext_fin_ratio": _div(((_latest(debt_iss) or 0.0) - (buyback_pos or 0.0)), cur_assets) if (cur_assets and cur_assets > 0) else None,
        "stock_issued_le0": (cur_repurch is not None and cur_repurch <= 0) or (_yoy(shares_l) is not None and _yoy(shares_l) <= 0),
        "buyback_ratio": buyback_yield,
        "ni_never_profitable": not any(v is not None and v > 0 for v in ni),
        "ni_2y_neg": len([v for v in ni[-2:] if v is not None and v <= 0]) == 2,
        "ni_rel_diff": ((ni[-1] - ni[-2]) / (abs(ni[-1]) + abs(ni[-2]))) if (len(ni) >= 2 and ni[-1] is not None and ni[-2] is not None and (abs(ni[-1]) + abs(ni[-2])) > 0) else None,
        "cfo_ni_yoy": _yoy(cfo_ni_l),
        "dso_yoy": _yoy(dso_l),
        "dio_yoy": _yoy(dio_l),
        "other_ca_rev_yoy": _yoy(other_ca_rev_l),
        "depr_rate_yoy": _yoy(depr_rate_l),
        # Séries brutes pour Beneish / Dechow / Mohanram / ESG
        "rev_pair": _pair_latest(rev),
        "gp_pair": _pair_latest(gp),
        "ar_pair": _pair_latest(ar),
        "inv_pair": _pair_latest(inv),
        "assets_pair": _pair_latest(assets),
        "ca_pair": _pair_latest(ca),
        "ppe_pair": _pair_latest(ppe),
        "da_pair": _pair_latest(da),
        "sga_pair": _pair_latest(sga),
        "liab_pair": _pair_latest(liab),
        "cash_pair": _pair_latest(cash_l),
        "rnd_to_assets": _div(_latest(rnd), cur_assets) if (cur_assets and cur_assets > 0) else None,
        "capex_to_assets": _div(abs(_latest(capex)) if _latest(capex) is not None else None, cur_assets) if (cur_assets and cur_assets > 0) else None,
        "roa_vals": [v for v in roa_l if v is not None],
        "rev_growths": [((rev[i] / rev[i - 1]) - 1.0) for i in range(1, n) if rev[i] is not None and rev[i - 1] and rev[i - 1] > 0],
        "debt_or_stock_issued": bool((_latest(debt_iss) or 0.0) > 0 or (cur_repurch is not None and cur_repurch > 0)),
        # Consensus & Initiés
        "insiders_pct": _pct_to_dec(cv.get("insiders_pct")) or _pct_to_dec(sh_st.get("PercentInsiders")),
        "analyst_rec": rec_val,
        "expected_price_growth": expected_price_growth,
        "piotroski_int": piotroski_latest,
        "esg_raw": (eod_fund or {}).get("ESGScores") or {},
        **price_m,
    }


def _compute_for_mode(d: dict[str, Any], mode: str) -> dict[str, Any]:
    """Calcule l'ensemble des 31 scores pour un mode donné (`documented` ou `verified`)."""
    verified = mode == "verified"
    results: dict[str, dict[str, Any]] = {}

    # 1. Is undervalued
    pb = d["pb"]
    p_iv = d["p_iv"]
    is_undervalued = bool((pb is not None and pb < 1.0) or (p_iv is not None and p_iv < 1.0))
    results["is_undervalued"] = _score_result(
        score_id="is_undervalued",
        name="Is undervalued",
        category="Signal",
        unit="bool",
        available=(pb is not None or p_iv is not None),
        final_score=(1.0 if is_undervalued else 0.0),
        display_value="Oui (Sous-évaluée)" if is_undervalued else "Non",
        components=[
            _comp("Price / Book < 1", pb, None, 1.0, 1.0 if (pb is not None and pb < 1.0) else 0.0),
            _comp("Price / Intrinsic Value < 1", p_iv, None, 1.0, 1.0 if (p_iv is not None and p_iv < 1.0) else 0.0),
        ],
        summary="Vrai si P/B < 1 ou Cours/VI < 1.",
    )

    # 2. Altman Z-Score
    x1 = d["cur_nwc_assets"]
    x2 = _div(d["cur_ret_earn"], d["cur_assets"]) if (d["cur_assets"] and d["cur_assets"] > 0) else None
    x3 = _div(d["cur_ebit"], d["cur_assets"]) if (d["cur_assets"] and d["cur_assets"] > 0) else None
    x4 = d["price_to_liab"]
    x5 = d["asset_turnover"]
    z_terms = [(1.2, "X1 NWC/Assets", x1), (1.4, "X2 Retained/Assets", x2), (3.3, "X3 EBIT/Assets", x3), (0.6, "X4 Capi./Passifs", x4), (0.999, "X5 Rotation actifs", x5)]
    if all(t[2] is not None for t in z_terms):
        z_val = sum(w * float(v) for w, _, v in z_terms)
        z_zone = "Sain (> 3,0)" if z_val > 3.0 else ("Zone grise" if z_val >= 1.8 else "Tension (< 1,8)")
        results["altman_z_score"] = _score_result(
            score_id="altman_z_score",
            name="Altman Z-Score",
            category="Santé & Faillite",
            unit="score",
            available=True,
            raw_score=z_val,
            final_score=z_val,
            display_value=f"{z_val:.2f} · {z_zone}",
            components=[_comp(lbl, v, v, w, w * float(v)) for w, lbl, v in z_terms],
        )
    else:
        results["altman_z_score"] = _score_result(score_id="altman_z_score", name="Altman Z-Score", category="Santé & Faillite", unit="score", available=False, warnings=["Postes bilan/EBIT manquants."])

    # 3. Ohlson O-Score
    cur_assets_m = (d["cur_assets"] / 1e6) if d["cur_assets"] else None
    debt_r = d["debt_ratio"]
    curr_r = d["cur_current"]
    roa = d["roa"]
    cf_cov = d["cf_coverage"]
    if all(v is not None for v in (cur_assets_m, debt_r, x1, curr_r, roa, cf_cov)) and cur_assets_m > 0 and curr_r > 0:
        o_lin = (
            -1.32
            - 0.407 * math.log(max(1e-3, cur_assets_m / 500.0))
            + 6.03 * float(debt_r)
            - 1.43 * float(x1)
            + 0.0757 / float(curr_r)
            - 1.72 * (1.0 if float(debt_r) > 1.0 else 0.0)
            - 2.37 * float(roa)
            - 1.83 * float(cf_cov)
            + 0.285 * (1.0 if d["ni_2y_neg"] else 0.0)
            - 0.521 * float(d["ni_rel_diff"] or 0.0)
        )
        o_prob = _logistic(o_lin)
        results["ohlson_o_score"] = _score_result(
            score_id="ohlson_o_score",
            name="Ohlson O-Score (Prob. défaut)",
            category="Santé & Faillite",
            unit="pct",
            available=True,
            raw_score=o_lin,
            normalized_score=o_prob * 100.0,
            final_score=o_prob * 100.0,
            display_value=f"{o_prob * 100.0:.1f}%",
            warnings=["Hypothèse d'échelle : Total Assets exprimé en M$ / 500."],
            components=[
                _comp("Constante", None, None, 1.0, -1.32),
                _comp("log(Actifs_M / 500)", cur_assets_m / 500.0, math.log(max(1e-3, cur_assets_m / 500.0)), -0.407, -0.407 * math.log(max(1e-3, cur_assets_m / 500.0))),
                _comp("Debt Ratio", debt_r, debt_r, 6.03, 6.03 * float(debt_r)),
                _comp("NWC / Assets", x1, x1, -1.43, -1.43 * float(x1)),
                _comp("ROA", roa, roa, -2.37, -2.37 * float(roa)),
                _comp("CFO / Debt", cf_cov, cf_cov, -1.83, -1.83 * float(cf_cov)),
            ],
        )
    else:
        o_prob = None
        results["ohlson_o_score"] = _score_result(score_id="ohlson_o_score", name="Ohlson O-Score", category="Santé & Faillite", unit="pct", available=False, warnings=["Variables bilan/liquidité insuffisantes."])

    # 4. Beneish M-Score
    rev0, rev1 = d["rev_pair"]
    gp0, gp1 = d["gp_pair"]
    ar0, ar1 = d["ar_pair"]
    a0, a1 = d["assets_pair"]
    ca0, ca1 = d["ca_pair"]
    ppe0, ppe1 = d["ppe_pair"]
    da0, da1 = d["da_pair"]
    sga0, sga1 = d["sga_pair"]
    l0, l1 = d["liab_pair"]
    if all(v is not None and v > 0 for v in (rev0, rev1, a0, a1)) and d["accruals_assets"] is not None:
        dsri = ((ar1 / rev1) / (ar0 / rev0)) if (ar0 and ar1 and ar0 > 0) else 1.0
        gmi = ((gp0 / rev0) / (gp1 / rev1)) if (gp0 and gp1 and gp1 > 0) else 1.0
        aq0 = 1.0 - ((ca0 or 0.0) + (ppe0 or 0.0)) / a0 if (ca0 is not None and ppe0 is not None) else None
        aq1 = 1.0 - ((ca1 or 0.0) + (ppe1 or 0.0)) / a1 if (ca1 is not None and ppe1 is not None) else None
        aqi = (aq1 / aq0) if (aq0 and aq1 and aq0 > 0) else 1.0
        sgi = rev1 / rev0
        dr0 = (da0 / (da0 + ppe0)) if (da0 is not None and ppe0 is not None and (da0 + ppe0) > 0) else None
        dr1 = (da1 / (da1 + ppe1)) if (da1 is not None and ppe1 is not None and (da1 + ppe1) > 0) else None
        depi = (dr0 / dr1) if (dr0 and dr1 and dr1 > 0) else 1.0
        sgai = ((abs(sga1) / rev1) / (abs(sga0) / rev0)) if (sga0 and sga1 and sga0 != 0) else 1.0
        tata = float(d["accruals_assets"])
        lvgi = ((l1 / a1) / (l0 / a0)) if (l0 and l1 and l0 > 0) else 1.0
        m_val = -4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi
        m_bad = m_val > -2.22
        results["beneish_m_score"] = _score_result(
            score_id="beneish_m_score",
            name="Beneish M-Score",
            category="Manipulation comptable",
            unit="score",
            available=True,
            raw_score=m_val,
            final_score=m_val,
            display_value=f"{m_val:.2f} · {'Alerte (> -2,22)' if m_bad else 'Normal'}",
            components=[
                _comp("DSRI", dsri, dsri, 0.920, 0.920 * dsri),
                _comp("GMI", gmi, gmi, 0.528, 0.528 * gmi),
                _comp("AQI", aqi, aqi, 0.404, 0.404 * aqi),
                _comp("SGI", sgi, sgi, 0.892, 0.892 * sgi),
                _comp("DEPI", depi, depi, 0.115, 0.115 * depi),
                _comp("SGAI", sgai, sgai, -0.172, -0.172 * sgai),
                _comp("TATA", tata, tata, 4.679, 4.679 * tata),
                _comp("LVGI", lvgi, lvgi, -0.327, -0.327 * lvgi),
            ],
        )
    else:
        m_val = None
        results["beneish_m_score"] = _score_result(score_id="beneish_m_score", name="Beneish M-Score", category="Manipulation comptable", unit="score", available=False, warnings=["Deux exercices complets requis."])

    # 5. Dechow F-Score
    cash0, cash1 = d["cash_pair"]
    inv0, inv1 = d["inv_pair"]
    if all(v is not None and v > 0 for v in (a0, a1, rev0, rev1)) and d["accruals_assets"] is not None:
        rsst = float(d["accruals_assets"])
        d_ar = ((ar1 / a1) - (ar0 / a0)) if (ar0 is not None and ar1 is not None) else 0.0
        d_inv = ((inv1 / a1) - (inv0 / a0)) if (inv0 is not None and inv1 is not None) else 0.0
        soft_assets = (a1 - (ppe1 or 0.0) - (cash1 or 0.0)) / a1
        cs0 = rev0 - ((ar0 or 0.0) - 0.0)
        cs1 = rev1 - ((ar1 or 0.0) - (ar0 or 0.0))
        cs_g = ((cs1 - cs0) / abs(cs0)) if cs0 > 0 else 0.0
        d_roa = float(d["roa_diff"] or 0.0)
        iss = 1.0 if d["debt_or_stock_issued"] else 0.0
        pv = -7.893 + 0.790 * rsst + 2.518 * d_ar + 1.191 * d_inv + 1.979 * soft_assets + 0.171 * cs_g + 0.932 * d_roa + 1.029 * iss
        f_dechow = (_logistic(pv) if verified else _logistic(-pv)) / 0.0037
        dechow_warn = [] if verified else ["Source indique logistic(-PV)/0,0037 (signe inversé conservé en mode documenté)."]
        results["dechow_f_score"] = _score_result(
            score_id="dechow_f_score",
            name="Dechow F-Score",
            category="Manipulation comptable",
            unit="score",
            available=True,
            raw_score=pv,
            final_score=f_dechow,
            display_value=f"{f_dechow:.2f}",
            warnings=dechow_warn,
            components=[
                _comp("RSST Accruals", rsst, rsst, 0.790, 0.790 * rsst),
                _comp("Δ Créances/Actifs", d_ar, d_ar, 2.518, 2.518 * d_ar),
                _comp("Δ Stocks/Actifs", d_inv, d_inv, 1.191, 1.191 * d_inv),
                _comp("Soft Assets / Actifs", soft_assets, soft_assets, 1.979, 1.979 * soft_assets),
                _comp("Croiss. Cash Sales", cs_g, cs_g, 0.171, 0.171 * cs_g),
                _comp("Δ ROA", d_roa, d_roa, 0.932, 0.932 * d_roa),
                _comp("Émission titres/dette", iss, iss, 1.029, 1.029 * iss),
            ],
        )
    else:
        f_dechow = None
        results["dechow_f_score"] = _score_result(score_id="dechow_f_score", name="Dechow F-Score", category="Manipulation comptable", unit="score", available=False, warnings=["Données multi-exercices insuffisantes."])

    # 6. Montier C-Score [0..6]
    c_rules = [
        ("CFO / Résultat net en baisse", d["cfo_ni_yoy"] is not None and d["cfo_ni_yoy"] < 0),
        ("DSO en hausse", d["dso_yoy"] is not None and d["dso_yoy"] > 0),
        ("DIO (jours de stock) en hausse", d["dio_yoy"] is not None and d["dio_yoy"] > 0),
        ("Autres actifs courants / CA en hausse", d["other_ca_rev_yoy"] is not None and d["other_ca_rev_yoy"] > 0),
        ("Taux d'amortissement en baisse", d["depr_rate_yoy"] is not None and d["depr_rate_yoy"] < 0),
        ("Actifs totaux > +10% sur 1 an", d["assets_1y_growth"] is not None and d["assets_1y_growth"] > 0.10),
    ]
    c_score = sum(1 for _, ok in c_rules if ok)
    results["montier_c_score"] = _score_result(
        score_id="montier_c_score",
        name="Montier C-Score",
        category="Manipulation comptable",
        unit="/6",
        available=d["n"] >= 2,
        raw_score=float(c_score),
        final_score=float(c_score),
        display_value=f"{c_score} / 6",
        components=[_comp(lbl, 1.0 if ok else 0.0, None, 1.0, 1.0 if ok else 0.0) for lbl, ok in c_rules],
    )

    # 7. Growth rate (médiane composite de 16 métriques)
    g_candidates = [
        ("Revenue 15y rCAGR", d["rev_rcagr_15"]),
        ("Revenue 15y rCAGR 67%", d["rev_rcagr_67"]),
        ("Revenue 5y CAGR", d["rev_5y_cagr"]),
        ("Revenue 3y CAGR", d["rev_3y_cagr"]),
        ("EBITDA 15y rCAGR", d["ebitda_rcagr_15"]),
        ("Op. Income 15y rCAGR", d["opinc_rcagr_15"]),
        ("CFO 15y rCAGR", d["cfo_rcagr_15"]),
        ("FCFF 15y rCAGR", d["fcff_rcagr_15"]),
        ("Net Income 5y CAGR", d["ni_5y_cagr"]),
        ("Revenue 1y fwd", d["fwd_rev_g"]),
        ("EPS 1y fwd", d["fwd_eps_g"]),
        ("EPS 1y growth", d["eps_1y_growth"]),
        ("TBV 15y rCAGR", d["tbv_rcagr_15"]),
        ("Net Owner Return 5y", d["nor_5y_cagr"]),
    ]
    g_valid = [v for _, v in g_candidates if v is not None]
    growth_med = statistics.median(g_valid) if g_valid else None
    results["growth_rate"] = _score_result(
        score_id="growth_rate",
        name="Growth rate (composite)",
        category="Qualité & Croissance",
        unit="pct",
        available=growth_med is not None,
        raw_score=(growth_med * 100.0) if growth_med is not None else None,
        final_score=(growth_med * 100.0) if growth_med is not None else None,
        display_value=f"{growth_med * 100.0:+.1f}%" if growth_med is not None else "—",
        components=[_comp(lbl, v, v, 1.0, v) for lbl, v in g_candidates],
    )

    # 8. Predictability Score
    pred_terms = [
        ("Operating Income R²", 22.0, d["opinc_r2"]),
        ("Revenue R²", 12.0, d["rev_r2"]),
        ("Gross Margin R²", 4.0, d["gm_r2"]),
    ]
    if any(t[2] is not None for t in pred_terms):
        p_raw = sum(w * float(v) for _, w, v in pred_terms if v is not None)
        p_clamped = _clamp(p_raw, -13.0, 48.0)
        p_norm = (p_clamped + 13.0) / 61.0
        results["predictability_score"] = _score_result(
            score_id="predictability_score",
            name="Predictability Score",
            category="Qualité & Croissance",
            unit="pct",
            available=True,
            raw_score=p_raw,
            clamped_score=p_clamped,
            normalized_score=p_norm * 100.0,
            final_score=p_norm * 100.0,
            display_value=f"{p_norm * 100.0:.1f}%",
            components=[_comp(lbl, v, v, w, (w * float(v)) if v is not None else None) for lbl, w, v in pred_terms],
        )
    else:
        p_norm = None
        results["predictability_score"] = _score_result(score_id="predictability_score", name="Predictability Score", category="Qualité & Croissance", unit="pct", available=False, warnings=["Au moins 3 exercices requis pour R²."])

    # 9. Quality Score
    q_terms = [
        ("Growth rate", 40.0, growth_med, -0.60, 0.60),
        ("Predictability Score", 5.0, p_norm, 0.0, 1.0),
        ("CROIC", 2.0, d["croic"], -0.90, 0.90),
        ("CROIC (3y avg)", 2.0, d["croic_3y"], -0.90, 0.90),
        ("CROIC (wavg 5y)", 4.0, d["croic_w5"], -0.90, 0.90),
        ("ROCE (Greenblatt)", 1.0, d["roce"], -0.90, 0.90),
        ("ROCE (3y avg)", 2.0, d["roce_3y"], -0.90, 0.90),
        ("ROCE (5y avg)", 2.0, d["roce_5y"], -0.90, 0.90),
        ("Gross Profitability", 3.0, d["gross_prof"], -0.90, 0.90),
        ("Asset turnover", 2.0, d["asset_turnover_w5"], -0.90, 0.90),
        ("Fixed Asset turnover", 1.0, d["fixed_asset_turnover_w5"], -0.90, 0.90),
        ("Gross Margin", 3.0, d["gross_margin_w5"], -0.90, 0.90),
        ("Operating Margin", 5.0, d["op_margin_w5"], -0.90, 0.90),
        ("Inventory 1y growth", -2.0, d["inv_1y_growth"], 0.0, 0.90),
        ("Size (3 * Assets / 1B)", -1.3, (3.0 * d["cur_assets"] / 1e9) if d["cur_assets"] else None, 0.0, None),
    ]
    q_raw, q_comps, q_used = _compute_log_weighted_score(q_terms)
    q_clamped = _clamp(q_raw, -47.0, 45.0)
    q_norm = (q_clamped + 47.0) / 92.0
    q_final = _sigmoid_stretch(q_norm) if verified else q_norm
    results["quality_score"] = _score_result(
        score_id="quality_score",
        name="Quality score",
        category="Scores Uncle Stock",
        unit="pct",
        available=q_used >= 3,
        raw_score=q_raw,
        clamped_score=q_clamped,
        normalized_score=q_norm * 100.0,
        final_score=q_final * 100.0,
        display_value=f"{q_final * 100.0:.1f}%" if q_used >= 3 else "—",
        components=q_comps,
        warnings=([] if verified else ["Paramètres sigmoïde finale absents de la source : affichage avant étirement."]),
    )

    # 10. Financial Health Score
    liq_specs = [
        ("Quick Ratio sigmoid (1)", 700.0, d["cur_quick"], 7.0, 1.0),
        ("Quick Ratio sigmoid (2)", -40.0, d["cur_quick"], 1.5, 2.0),
        ("Current Ratio sigmoid (1)", 250.0, d["cur_current"], 7.0, 1.0),
        ("NWC / Assets sigmoid", 140.0, d["cur_nwc_assets"], 5.0, 0.0),
        ("Current Ratio sigmoid (2)", -40.0, d["cur_current"], 1.5, 2.0),
    ]
    h_raw = 0.0
    h_comps: list[dict[str, Any]] = []
    h_used = 0
    for lbl, w, val, slope, center in liq_specs:
        if val is None:
            h_comps.append(_comp(lbl, None, None, w, None))
            continue
        h_used += 1
        tr = _logistic(slope * (val - center)) - 0.5
        c_val = w * tr
        h_raw += c_val
        h_comps.append(_comp(lbl, val, tr, w, c_val))
    h_log_terms = [
        ("Cash Flow Coverage", 200.0, d["cf_coverage"], -1.0, 1.0),
        ("FCF / LT Debt", 100.0, d["fcf_to_lt_debt"], -1.0, 1.0),
        ("Debt ratio", -60.0, d["debt_ratio"], 0.0, 20.0),
        ("Liabilities / Equity", -40.0, d["liab_to_equity"], 0.0, 20.0),
        ("Net Debt / Equity", -40.0, d["net_debt_to_equity"], 0.0, 20.0),
        ("Net Debt / EBITDA", -30.0, d["net_debt_to_ebitda"], -0.66, 2.0),
        ("Debt / TBV", -20.0, d["debt_to_tbv"], 0.0, 20.0),
        ("Absolute Sloan ratio", -200.0, d["abs_sloan"], 0.0, 1.0),
        ("Ohlson O-score prob.", -1200.0, (o_prob if "ohlson_o_score" in results and results["ohlson_o_score"]["available"] else None), 0.0, 1.0),
    ]
    h_log_tot, h_log_comps, h_log_used = _compute_log_weighted_score(h_log_terms)
    h_raw += h_log_tot
    h_comps.extend(h_log_comps)
    h_clamped = _clamp(h_raw, -2200.0, 840.0)
    h_norm = (h_clamped + 2200.0) / 3040.0 if verified else (h_clamped + 2150.0) / 2990.0
    h_final = _sigmoid_stretch(h_norm) if verified else h_norm
    h_warn = [] if verified else ["Source indique plancher -2200 mais numérateur +2150 / 2990 (peut devenir < 0)."]
    results["financial_health_score"] = _score_result(
        score_id="financial_health_score",
        name="Financial Health score",
        category="Scores Uncle Stock",
        unit="pct",
        available=(h_used + h_log_used) >= 3,
        raw_score=h_raw,
        clamped_score=h_clamped,
        normalized_score=h_norm * 100.0,
        final_score=h_final * 100.0,
        display_value=f"{h_final * 100.0:.1f}%" if (h_used + h_log_used) >= 3 else "—",
        components=h_comps,
        warnings=h_warn,
    )

    # 11. Balance Value Score
    bv_terms = [
        ("Book to Market", 150.0, d["book_to_market"], 0.0, 25.0),
        ("Price / TBV", -40.0, d["p_tbv"], 0.0, 25.0),
        ("Price / Non-cash Assets", -10.0, d["p_non_cash"], 0.0, 75.0),
        ("Price / NNWC", -25.0, d["p_nnwc"], 0.0, 25.0),
        ("Price / NCAV", -15.0, d["p_ncav"], 0.0, 25.0),
        ("Price / Fixed Assets", -5.0, d["p_fixed"], 0.0, 100.0),
    ]
    bv_raw, bv_comps, bv_used = _compute_log_weighted_score(bv_terms)
    bv_clamped = _clamp(bv_raw, -450.0, 620.0)
    bv_norm = (bv_clamped + 450.0) / (1070.0 if verified else 1080.0)
    bv_final = _sigmoid_stretch(bv_norm) if verified else bv_norm
    results["balance_value_score"] = _score_result(
        score_id="balance_value_score",
        name="Balance value score",
        category="Scores Uncle Stock",
        unit="pct",
        available=bv_used >= 1,
        raw_score=bv_raw,
        clamped_score=bv_clamped,
        normalized_score=bv_norm * 100.0,
        final_score=bv_final * 100.0,
        display_value=f"{bv_final * 100.0:.1f}%" if bv_used >= 1 else "—",
        components=bv_comps,
        warnings=([] if verified else ["Dénominateur source 1080 ≠ amplitude 1070."]),
    )

    # 12. Balance Score
    if results["financial_health_score"]["available"] and results["balance_value_score"]["available"]:
        h_dec = _clamp(float(results["financial_health_score"]["final_score"]) / 100.0, 0.0, 1.0)
        bv_dec = _clamp(float(results["balance_value_score"]["final_score"]) / 100.0, 0.0, 1.0)
        b_raw = 2.1 * _signed_log(h_dec) + 0.9 * _signed_log(bv_dec)
        b_clamped = _clamp(b_raw, 0.0, 3.0)
        b_norm = b_clamped / 3.0
        results["balance_score"] = _score_result(
            score_id="balance_score",
            name="Balance score",
            category="Scores Uncle Stock",
            unit="pct",
            available=True,
            raw_score=b_raw,
            clamped_score=b_clamped,
            normalized_score=b_norm * 100.0,
            final_score=b_norm * 100.0,
            display_value=f"{b_norm * 100.0:.1f}%",
            components=[
                _comp("Financial Health score", h_dec, _signed_log(h_dec), 2.1, 2.1 * _signed_log(h_dec)),
                _comp("Balance value score", bv_dec, _signed_log(bv_dec), 0.9, 0.9 * _signed_log(bv_dec)),
            ],
        )
    else:
        results["balance_score"] = _score_result(score_id="balance_score", name="Balance score", category="Scores Uncle Stock", unit="pct", available=False)

    # 13. Yield Score
    roe_pe = (d["roe"] * 100.0 / d["pe"]) if (d["roe"] is not None and d["pe"] and d["pe"] > 0) else None
    y_terms = [
        ("Net Payout yield (3y)", 1100.0, d["net_payout_yield"], -1.0, 1.2),
        ("Dividend rCAGR 67%", 50.0, d["div_rcagr_67"], -0.66, 2.0),
        ("Adj. Op. Income yield", 90.0, d["opinc_yield"], -1.0, 1.2),
        ("Op. Income yield", 120.0, d["opinc_yield"], -1.0, 1.2),
        ("Revenue yield / EV", 50.0, d["rev_yield_ev"], -1.0, 1.2),
        ("EBITDA yield", 40.0, d["ebitda_yield"], -1.0, 1.2),
        ("EBITA yield", 20.0, d["ebit_yield"], -1.0, 1.2),
        ("EBIT yield", 40.0, d["ebit_yield"], -1.0, 1.2),
        ("EPS yield", 50.0, d["eps_yield"], -1.0, 1.2),
        ("CF After Taxes yield", 90.0, d["cfo_yield"], -1.0, 1.2),
        ("Cash-NOPAT yield", 230.0, d["cash_nopat_yield"], -1.0, 1.2),
        ("FCF yield on Price", 90.0, d["fcf_yield"], -1.0, 1.2),
        ("PEGY ratio", -20.0, d["peg"], -0.9, 0.9),
        ("PEG ratio", -10.0, d["peg"], -0.9, 0.9),
        ("ROE / PE", 30.0, roe_pe, None, 7.0),
        ("Payback ratio (5y)", -30.0, d["payback_ratio"], 0.0, 50.0),
        ("Payout ratio", -90.0, d["payout_ratio"], 0.0, 0.90),
    ]
    y_raw, y_comps, y_used = _compute_log_weighted_score(y_terms)
    y_clamped = _clamp(y_raw, -1160.0, 1010.0)
    y_norm = (y_clamped + 1160.0) / (2170.0 if verified else 1810.0)
    y_final = _sigmoid_stretch(y_norm) if verified else y_norm
    results["yield_score"] = _score_result(
        score_id="yield_score",
        name="Yield score",
        category="Scores Uncle Stock",
        unit="pct",
        available=y_used >= 3,
        raw_score=y_raw,
        clamped_score=y_clamped,
        normalized_score=y_norm * 100.0,
        final_score=y_final * 100.0,
        display_value=f"{y_final * 100.0:.1f}%" if y_used >= 3 else "—",
        components=y_comps,
        warnings=([] if verified else ["Dénominateur source 1810 ≠ amplitude 2170 (peut dépasser 100%)."]),
    )

    # 14. Value Score
    if results["yield_score"]["available"] and results["balance_value_score"]["available"]:
        y_dec = _clamp(float(results["yield_score"]["final_score"]) / 100.0, 0.0, 1.0)
        bv_dec = _clamp(float(results["balance_value_score"]["final_score"]) / 100.0, 0.0, 1.0)
        v_raw = 1.9 * _signed_log(y_dec) + 0.3 * _signed_log(bv_dec)
        v_clamped = _clamp(v_raw, 0.0, 2.2)
        v_norm = v_clamped / 2.2
        results["value_score"] = _score_result(
            score_id="value_score",
            name="Value score",
            category="Scores Uncle Stock",
            unit="pct",
            available=True,
            raw_score=v_raw,
            clamped_score=v_clamped,
            normalized_score=v_norm * 100.0,
            final_score=v_norm * 100.0,
            display_value=f"{v_norm * 100.0:.1f}%",
            components=[
                _comp("Yield score", y_dec, _signed_log(y_dec), 1.9, 1.9 * _signed_log(y_dec)),
                _comp("Balance value score", bv_dec, _signed_log(bv_dec), 0.3, 0.3 * _signed_log(bv_dec)),
            ],
        )
    else:
        results["value_score"] = _score_result(score_id="value_score", name="Value score", category="Scores Uncle Stock", unit="pct", available=False)

    # 15. Uncle Stock Score (composite GARP)
    q_dec = _clamp((results["quality_score"]["final_score"] or 0.0) / 100.0, 0.0, 1.0) if results["quality_score"]["available"] else None
    v_dec = _clamp((results["value_score"]["final_score"] or 0.0) / 100.0, 0.0, 1.0) if results["value_score"]["available"] else None
    h_dec = _clamp((results["financial_health_score"]["final_score"] or 0.0) / 100.0, 0.0, 1.0) if results["financial_health_score"]["available"] else None

    us_comps: list[dict[str, Any]] = []
    us_raw = 0.0
    if q_dec is not None:
        us_raw += 330.0 * q_dec
        us_comps.append(_comp("Quality score", q_dec, q_dec, 330.0, 330.0 * q_dec))
    if v_dec is not None:
        us_raw += 210.0 * v_dec
        us_comps.append(_comp("Value score", v_dec, v_dec, 210.0, 210.0 * v_dec))
    if p_iv is not None:
        tr = _signed_log(p_iv)
        us_raw += -160.0 * tr
        us_comps.append(_comp("Price / Intrinsic Value", p_iv, tr, -160.0, -160.0 * tr))
    if h_dec is not None and v_dec is not None:
        inter = (1.0 - h_dec) * (1.5 * (v_dec ** 2) - 1.0)
        us_raw += 330.0 * inter
        us_comps.append(_comp("(1 - Health) * (1.5*V^2 - 1)", inter, inter, 330.0, 330.0 * inter))
    if d["analyst_rec"] is not None:
        us_raw += -10.0 * float(d["analyst_rec"])
        us_comps.append(_comp("Analyst recommendation", d["analyst_rec"], d["analyst_rec"], -10.0, -10.0 * float(d["analyst_rec"])))
    if d["price_rcagr"] is not None:
        tr = _signed_log(_clamp(d["price_rcagr"], -0.66, 2.0))
        us_raw += 50.0 * tr
        us_comps.append(_comp("Price rCAGR", d["price_rcagr"], tr, 50.0, 50.0 * tr))
    if d["expected_price_growth"] is not None:
        tr = _signed_log(d["expected_price_growth"])
        us_raw += 30.0 * tr
        us_comps.append(_comp("Expected price growth", d["expected_price_growth"], tr, 30.0, 30.0 * tr))
    if d["ret_1y"] is not None:
        tr = _signed_log(d["ret_1y"])
        us_raw += 75.0 * tr
        us_comps.append(_comp("Total Return 1y", d["ret_1y"], tr, 75.0, 75.0 * tr))
    if d["ma50_diff"] is not None:
        tr = _signed_log(_clamp(d["ma50_diff"], -0.50, 1.50))
        us_raw += 25.0 * tr
        us_comps.append(_comp("Delta 50d MA", d["ma50_diff"], tr, 25.0, 25.0 * tr))
    if d["ltm_rev"] is not None:
        tr = _signed_log(_clamp(d["ltm_rev"], -1.0, 1.0))
        us_raw += 40.0 * tr
        us_comps.append(_comp("Long term reversal", d["ltm_rev"], tr, 40.0, 40.0 * tr))
    if d["insiders_pct"] is not None:
        us_raw += 100.0 * float(d["insiders_pct"])
        us_comps.append(_comp("% held by insiders", d["insiders_pct"], d["insiders_pct"], 100.0, 100.0 * float(d["insiders_pct"])))

    # Pénalités de risque
    penalties = [
        ("Ohlson O-Score > 50%", (o_prob is not None and o_prob > 0.50), -120.0),
        ("Beneish M-Score > -2.22", (m_val is not None and m_val > -2.22), -30.0),
        ("Dechow F-Score > 1", (f_dechow is not None and f_dechow > 1.0), -30.0),
        ("Montier C-Score >= 5", c_score >= 5, -40.0),
        ("Société jamais rentable", bool(d["ni_never_profitable"]), -20.0),
    ]
    for lbl, trig, pen in penalties:
        if trig:
            us_raw += pen
            us_comps.append(_comp(lbl, 1.0, 1.0, pen, pen))

    us_avail = q_dec is not None or v_dec is not None
    us_clamped = _clamp(us_raw, -890.0, 650.0)
    us_norm = (us_clamped + 890.0) / (1540.0 if verified else 1420.0)
    results["uncle_stock_score"] = _score_result(
        score_id="uncle_stock_score",
        name="Uncle Stock score (GARP)",
        category="Scores Uncle Stock",
        unit="pct",
        available=us_avail,
        raw_score=us_raw,
        clamped_score=us_clamped,
        normalized_score=us_norm * 100.0,
        final_score=us_norm * 100.0,
        display_value=f"{us_norm * 100.0:.1f}%" if us_avail else "—",
        components=us_comps,
        warnings=([] if verified else ["Source normalise (score + 890) / 1420 avec plafond +650 (peut atteindre 108,5%)."]),
    )

    # 16. Piotroski F-Score (entier [0-9] + % continu)
    pio_int = d["piotroski_int"]
    if pio_int is None and d["n"] >= 2:
        # Calcul direct si absent
        pio_rules = [
            (d["cur_ni"] is not None and d["cur_ni"] > 0),
            (d["cur_cfo"] is not None and d["cur_cfo"] > 0),
            (d["roa_yoy"] is not None and d["roa_yoy"] > 0),
            (d["cur_cfo"] is not None and d["cur_ni"] is not None and d["cur_cfo"] > d["cur_ni"]),
            (d["lt_debt_yoy"] is not None and d["lt_debt_yoy"] < 0),
            (d["current_yoy"] is not None and d["current_yoy"] > 0),
            bool(d["stock_issued_le0"]),
            (d["gross_margin_yoy"] is not None and d["gross_margin_yoy"] > 0),
            (d["asset_turnover_yoy"] is not None and d["asset_turnover_yoy"] > 0),
        ]
        pio_int = sum(1 for x in pio_rules if x)
    pio_cont_terms = [
        ("EPS yield", 0.7, d["eps_yield"], None, None),
        ("CFO yield", 0.7, d["cfo_yield"], None, None),
        ("ROA 1y growth", 0.5, d["roa_yoy"], -1.0, 2.0),
        ("LT Debt 1y growth", -0.3, d["lt_debt_yoy"], -1.0, 2.0),
        ("Current Ratio 1y growth", 2.0, d["current_yoy"], -1.0, 2.0),
        ("Buyback ratio", 2.0, d["buyback_ratio"], 0.0, 0.5),
        ("Gross margin 1y growth", 0.5, d["gross_margin_yoy"], -1.0, 2.0),
        ("Asset turnover 1y growth", 1.0, d["asset_turnover_yoy"], -1.0, 2.0),
    ]
    pio_raw_c, pio_comps, _ = _compute_log_weighted_score(pio_cont_terms)
    pio_pct = _weighted_log_normalize(pio_raw_c, 0.35)
    pio_pub = (float(pio_int) + pio_pct / 100.0) if pio_int is not None else None
    results["piotroski_f_score"] = _score_result(
        score_id="piotroski_f_score",
        name="Piotroski F-score",
        category="Scores Factoriels",
        unit="/10",
        available=pio_int is not None,
        raw_score=float(pio_int) if pio_int is not None else None,
        normalized_score=pio_pct,
        final_score=pio_pub,
        display_value=f"{pio_int}/9 ({pio_pub:.2f})" if pio_pub is not None else "—",
        components=pio_comps,
    )

    # 17. Mohanram G-Score [0-7 documenté / 0-8 annoncé]
    roa_vals = d["roa_vals"]
    rev_gs = d["rev_growths"]
    roa_sd = statistics.stdev(roa_vals[-5:]) if len(roa_vals) >= 3 else None
    rev_sd = statistics.stdev(rev_gs[-5:]) if len(rev_gs) >= 3 else None
    g_rules = [
        ("ROA > médiane/réf. (8%)", d["roa"] is not None and d["roa"] > 0.08),
        ("Cash ROA > réf. (10%)", d["cash_roa"] is not None and d["cash_roa"] > 0.10),
        ("Accruals / Assets < 0", d["accruals_assets"] is not None and d["accruals_assets"] < 0),
        ("Stabilité ROA (σ < 5%)", roa_sd is not None and roa_sd < 0.05),
        ("Stabilité croissance CA (σ < 15%)", rev_sd is not None and rev_sd < 0.15),
        ("R&D / Assets > 2%", d["rnd_to_assets"] is not None and d["rnd_to_assets"] > 0.02),
        ("CapEx / Assets > 3%", d["capex_to_assets"] is not None and d["capex_to_assets"] > 0.03),
    ]
    g_int = sum(1 for _, ok in g_rules if ok)
    results["mohanram_g_score"] = _score_result(
        score_id="mohanram_g_score",
        name="Mohanram G-score",
        category="Scores Factoriels",
        unit="/7",
        available=d["roa"] is not None,
        raw_score=float(g_int),
        final_score=float(g_int),
        display_value=f"{g_int} / 7",
        components=[_comp(lbl, 1.0 if ok else 0.0, None, 1.0, 1.0 if ok else 0.0) for lbl, ok in g_rules],
        warnings=["7 critères listés (8e absent de la source) ; seuils de référence fixes faute de médiane sectorielle live."],
    )

    # 18. Levermann Score [-11..+11]
    lev_rules = [
        ("ROE (>20% +1 / <10% -1)", (1 if d["roe"] > 0.20 else (-1 if d["roe"] < 0.10 else 0)) if d["roe"] is not None else None),
        ("Marge EBIT (>12% +1 / <6% -1)", (1 if d["op_margin"] > 0.12 else (-1 if d["op_margin"] < 0.06 else 0)) if d["op_margin"] is not None else None),
        ("Equity ratio (>25% +1 / <15% -1)", (1 if d["equity_ratio"] > 0.25 else (-1 if d["equity_ratio"] < 0.15 else 0)) if d["equity_ratio"] is not None else None),
        ("P/E actuel (<12 +1 / >16 -1)", (1 if d["pe"] < 12.0 else (-1 if d["pe"] > 16.0 else 0)) if (d["pe"] is not None and d["pe"] > 0) else None),
        ("Revisions BPA / Croissance fwd", (1 if d["fwd_eps_g"] > 0.05 else (-1 if d["fwd_eps_g"] < -0.05 else 0)) if d["fwd_eps_g"] is not None else None),
        ("Perf 6 mois (>+5% +1 / <-5% -1)", (1 if d["ret_6m"] > 0.05 else (-1 if d["ret_6m"] < -0.05 else 0)) if d["ret_6m"] is not None else None),
        ("Perf 1 an (>+5% +1 / <-5% -1)", (1 if d["ret_1y"] > 0.05 else (-1 if d["ret_1y"] < -0.05 else 0)) if d["ret_1y"] is not None else None),
    ]
    lev_vals = [v for _, v in lev_rules if v is not None]
    lev_sum = sum(lev_vals) if lev_vals else None
    results["levermann_score"] = _score_result(
        score_id="levermann_score",
        name="Levermann score",
        category="Scores Factoriels",
        unit="pts",
        available=len(lev_vals) >= 3,
        raw_score=float(lev_sum) if lev_sum is not None else None,
        final_score=float(lev_sum) if lev_sum is not None else None,
        display_value=f"{lev_sum:+d} pts" if lev_sum is not None else "—",
        components=[_comp(lbl, float(v) if v is not None else None, None, 1.0, float(v) if v is not None else None) for lbl, v in lev_rules],
    )

    # 19. Company Score [0..5]
    comp_rules = [
        ("Net margin > 10%", d["net_margin"] is not None and d["net_margin"] > 0.10),
        ("Revenue rCAGR 67% > 10%", d["rev_rcagr_67"] is not None and d["rev_rcagr_67"] > 0.10),
        ("ROE > 15%", d["roe"] is not None and d["roe"] > 0.15),
        ("Equity ratio > 40%", d["equity_ratio"] is not None and d["equity_ratio"] > 0.40),
        ("CF Coverage > 33%", d["cf_coverage"] is not None and d["cf_coverage"] > 0.33),
    ]
    comp_int = sum(1 for _, ok in comp_rules if ok)
    comp_cont_raw, _, _ = _compute_log_weighted_score([
        ("Net margin", 1.0, d["net_margin"], -0.9, 0.9),
        ("Rev rCAGR 67%", 1.0, d["rev_rcagr_67"], -0.6, 0.6),
        ("ROE", 1.5, d["roe"], -0.9, 0.9),
        ("Equity ratio", 0.75, d["equity_ratio"], 0.0, 1.0),
        ("CF coverage", 0.75, d["cf_coverage"], -1.0, 1.0),
    ])
    comp_pct = _weighted_log_normalize(comp_cont_raw, 0.5)
    results["company_score"] = _score_result(
        score_id="company_score",
        name="Company score",
        category="Scores Factoriels",
        unit="/5",
        available=d["cur_rev"] is not None,
        raw_score=float(comp_int),
        normalized_score=comp_pct,
        final_score=float(comp_int) + comp_pct / 100.0,
        display_value=f"{comp_int}/5 ({comp_int + comp_pct / 100.0:.2f})",
        components=[_comp(lbl, 1.0 if ok else 0.0, None, 1.0, 1.0 if ok else 0.0) for lbl, ok in comp_rules],
    )

    # 20. O'Shaughnessy Value Composites Three
    vc3_raw, vc3_comps, vc3_used = _compute_log_weighted_score([
        ("Book to Market", 1.0, d["book_to_market"], 0.0, 10.0),
        ("EPS yield", 7.0, d["eps_yield"], -1.0, 1.0),
        ("Revenue yield / Price", 1.0, d["rev_yield_price"], 0.0, 10.0),
        ("EBITDA yield", 3.5, d["ebitda_yield"], -1.0, 1.0),
        ("CFO yield / Price", 3.5, d["cfo_yield"], -1.0, 1.0),
        ("Buyback ratio", 20.0, d["buyback_ratio"], -0.5, 0.5),
    ])
    vc3_norm = _weighted_log_normalize(vc3_raw, 0.35)
    results["oshaughnessy_vc3"] = _score_result(
        score_id="oshaughnessy_vc3",
        name="O'Shaughnessy VC3",
        category="Scores Factoriels",
        unit="pct",
        available=vc3_used >= 2,
        raw_score=vc3_raw,
        normalized_score=vc3_norm,
        final_score=vc3_norm,
        display_value=f"{vc3_norm:.1f}%" if vc3_used >= 2 else "—",
        components=vc3_comps,
    )

    # 21. Greenblatt Score
    gb_terms = [
        ("7 × EBIT yield", 1.0, (7.0 * d["ebit_yield"]) if d["ebit_yield"] is not None else None, -5.0, 5.0),
        ("ROCE (Greenblatt)", 1.0, d["roce"], -1.0, 2.0),
    ]
    gb_raw, gb_comps, gb_used = _compute_log_weighted_score(gb_terms)
    gb_avg = (gb_raw / gb_used) if gb_used else None
    gb_norm = _weighted_log_normalize(gb_avg, 1.2) if gb_avg is not None else None
    results["greenblatt_score"] = _score_result(
        score_id="greenblatt_score",
        name="Greenblatt score",
        category="Scores Factoriels",
        unit="pct",
        available=gb_used >= 1,
        raw_score=gb_avg,
        normalized_score=gb_norm,
        final_score=gb_norm,
        display_value=f"{gb_norm:.1f}%" if gb_norm is not None else "—",
        components=gb_comps,
    )

    # 22. Pim Van Vliet Score
    pvv_raw, pvv_comps, pvv_used = _compute_log_weighted_score([
        ("Price 1y change", 1.0, d["ret_1y"], -0.9, 3.0),
        ("Net Payout yield", 3.0, d["net_payout_yield"], -0.5, 1.0),
        ("Volatilité 252j", -0.25, d["price_sd_252"], 0.0, 2.0),
    ])
    pvv_norm = _weighted_log_normalize(pvv_raw, 1.1) if pvv_used >= 2 else None
    results["pim_van_vliet_score"] = _score_result(
        score_id="pim_van_vliet_score",
        name="Pim Van Vliet score",
        category="Scores Factoriels",
        unit="pct",
        available=pvv_used >= 2,
        raw_score=pvv_raw,
        normalized_score=pvv_norm,
        final_score=pvv_norm,
        display_value=f"{pvv_norm:.1f}%" if pvv_norm is not None else "—",
        components=pvv_comps,
    )

    # 23. ERP5 Score
    erp_raw, erp_comps, erp_used = _compute_log_weighted_score([
        ("7 × EBIT yield", 1.0, (7.0 * d["ebit_yield"]) if d["ebit_yield"] is not None else None, -5.0, 5.0),
        ("ROCE", 1.0, d["roce"], -1.0, 2.0),
        ("ROCE (5y avg)", 1.0, d["roce_5y"], -1.0, 2.0),
        ("0.7 × B/M ÷ 10", 1.0, (0.07 * d["book_to_market"]) if d["book_to_market"] is not None else None, 0.0, 2.0),
    ])
    erp_avg = (erp_raw / erp_used) if erp_used else None
    erp_norm = _weighted_log_normalize(erp_avg, 1.3) if erp_avg is not None else None
    results["erp5_score"] = _score_result(
        score_id="erp5_score",
        name="ERP5 score",
        category="Scores Factoriels",
        unit="pct",
        available=erp_used >= 2,
        raw_score=erp_avg,
        normalized_score=erp_norm,
        final_score=erp_norm,
        display_value=f"{erp_norm:.1f}%" if erp_norm is not None else "—",
        components=erp_comps,
    )

    # 24. Slater Score
    mcap_scale = (3.0 * d["mcap"] / 1e9) if (verified and d["mcap"]) else ((3.0 / 109.0 * d["mcap"] / 1e6) if d["mcap"] else None)
    sl_raw, sl_comps, sl_used = _compute_log_weighted_score([
        ("EPS yield", 0.75, d["eps_yield"], -1.0, 1.0),
        ("EPS rCAGR 67%", 0.75, d["eps_rcagr_67"], -0.66, 2.0),
        ("ROCE", 2.0, d["roce"], -1.0, 2.0),
        ("PEG (forward)", -40.0, d["peg"], 0.0, 10.0),
        ("Dividend yield", 10.0, d["div_yield"], 0.0, 0.25),
        ("Gross margin", 0.75, d["gross_margin_w5"], -0.9, 0.9),
        ("Liabilities / Equity", -1.0, d["liab_to_equity"], 0.0, 20.0),
        ("Current ratio", 20.0, d["cur_current"], 0.0, 10.0),
        ("Price 1y growth", 0.5, d["ret_1y"], -0.9, 3.0),
        ("Market Cap scale", -7.0, mcap_scale, 0.0, None),
    ])
    sl_norm = _weighted_log_normalize(sl_raw, 0.05) if sl_used >= 4 else None
    results["slater_score"] = _score_result(
        score_id="slater_score",
        name="Slater score",
        category="Scores Factoriels",
        unit="pct",
        available=sl_used >= 4,
        raw_score=sl_raw,
        normalized_score=sl_norm,
        final_score=sl_norm,
        display_value=f"{sl_norm:.1f}%" if sl_norm is not None else "—",
        components=sl_comps,
        warnings=([] if verified else ["Expression source « 3 ÷ 109 × Market cap » appliquée littéralement (10⁹ probable)."]),
    )

    # 25. Trap Score [0..12]
    is_fin = any(k in d["sector"] for k in ("financ", "bank", "insur"))
    is_ind = any(k in d["sector"] for k in ("industr", "material", "energy", "util"))
    is_srv = not is_fin and not is_ind
    trap_rules = [
        ("P/E < 10", d["pe"] is not None and d["pe"] < 10.0),
        ("Revenue 5y rCAGR < -10%", d["rev_rcagr_67"] is not None and d["rev_rcagr_67"] < -0.10),
        ("Quick ratio < 0.5", d["cur_quick"] is not None and d["cur_quick"] < 0.5),
        ("Capitaux propres < 0", d["cur_eq"] is not None and d["cur_eq"] < 0),
        ("ROE < 10%", d["roe"] is not None and d["roe"] < 0.10),
        ("Absolute Sloan ratio > 25%", d["abs_sloan"] is not None and d["abs_sloan"] > 0.25),
        ("External Financing Ratio > 25%", d["ext_fin_ratio"] is not None and d["ext_fin_ratio"] > 0.25),
        ("Montier C-Score > 5", c_score > 5),
        ("Beneish M-Score > -1.78", m_val is not None and m_val > -1.78),
        ("EPV / Assets < 75%", d["epv_to_assets"] is not None and d["epv_to_assets"] < 0.75),
    ]
    if not verified or is_ind:
        trap_rules.append(("Secteur Industriel : P/E < 10", d["pe"] is not None and d["pe"] < 10.0))
    if not verified or is_srv:
        trap_rules.append(("Secteur Services : EV/EBITDA < 8", d["ev_ebitda"] is not None and d["ev_ebitda"] < 8.0))
    if not verified or is_fin:
        trap_rules.append(("Secteur Financier : P/B < 0.75", d["pb"] is not None and d["pb"] < 0.75))
    trap_val = sum(1 for _, ok in trap_rules if ok)
    results["trap_score"] = _score_result(
        score_id="trap_score",
        name="Trap score (Value Trap)",
        category="Signal",
        unit="/12",
        available=d["cur_rev"] is not None,
        raw_score=float(trap_val),
        final_score=float(trap_val),
        display_value=f"{trap_val} / 12",
        components=[_comp(lbl, 1.0 if ok else 0.0, None, 1.0, 1.0 if ok else 0.0) for lbl, ok in trap_rules],
        warnings=([] if verified else ["14 lignes sources évaluées sans filtre sectoriel exclusif."]),
    )

    # 26. Categories
    cats: list[str] = []
    if is_undervalued and trap_val < 6:
        cats.append("Value")
    if is_undervalued and trap_val > 5:
        cats.append("Value trap")
    if p_iv is not None and p_iv > 2.0:
        cats.append("Overvalued")
    if d["rev_rcagr_15"] is not None and d["rev_rcagr_15"] > 0.10:
        cats.append("Growth")
    if d["net_payout_yield"] is not None and d["net_payout_yield"] > 0.04:
        cats.append("Income")
    if (results["financial_health_score"]["final_score"] or 100.0) < 28.0 and (results["predictability_score"]["final_score"] or 100.0) < 28.0:
        cats.append("Junk")
    if pio_int is not None and pio_int > 7:
        cats.append("Improving")
    if pio_int is not None and pio_int < 3:
        cats.append("Deteriorating")
    results["categories"] = _score_result(
        score_id="categories",
        name="Categories",
        category="Signal",
        unit="tags",
        available=True,
        final_score=float(len(cats)),
        display_value=", ".join(cats) if cats else "Neutre / Mixte",
        summary="Étiquettes combinables : Value, Value trap, Overvalued, Growth, Income, Junk, Improving, Deteriorating.",
    )

    # 27. Advice
    us_pct = results["uncle_stock_score"]["final_score"]
    exp_ret = d["expected_price_growth"]
    ltm = d["ltm_rev"]
    stm = d["stm_rev"]
    advice_label = "Indisponible"
    if us_pct is not None:
        if us_pct > 72.0:
            if exp_ret is not None and exp_ret < -0.30:
                advice_label = "Hold" if verified else "Buy - Wait"
            elif exp_ret is not None and exp_ret < -0.10 or (ltm is not None and ltm < 0):
                advice_label = "Strong Buy - Wait"
            elif (exp_ret is not None and exp_ret > 0.30 and (ltm or 0.0) >= 0 and (stm or 0.0) >= 0) or (stm is not None and stm > 0):
                advice_label = "Strong Buy - Act"
            else:
                advice_label = "Strong Buy"
        elif us_pct >= 60.0:
            if (exp_ret is not None and exp_ret < -0.15) or (ltm is not None and ltm < 0):
                advice_label = "Hold"
            elif (exp_ret is not None and exp_ret < 0.15) or (stm is not None and stm < 0):
                advice_label = "Buy - Wait"
            elif (exp_ret is not None and exp_ret > 0.40 and (ltm or 0.0) >= 0 and (stm or 0.0) >= 0) or (stm is not None and stm > 0):
                advice_label = "Buy - Act"
            else:
                advice_label = "Buy"
        elif us_pct >= 45.0:
            if (exp_ret is not None and exp_ret < 0.0) or (ltm is not None and ltm < 0) or (stm is not None and stm < 0):
                advice_label = "Sell"
            else:
                advice_label = "Hold"
        elif us_pct >= 30.0:
            if (exp_ret is not None and exp_ret < 0.0 and (ltm or 0.0) <= 0 and (stm or 0.0) <= 0) or (stm is not None and stm < 0):
                advice_label = "Sell - Act"
            elif (exp_ret is not None and exp_ret > 0.30) or (ltm is not None and ltm < 0) or (stm is not None and stm < 0):
                advice_label = "Sell - Wait"
            else:
                advice_label = "Sell"
        else:
            if (exp_ret is not None and exp_ret < 0.10) or (ltm is not None and ltm < 0) or (stm is not None and stm < 0):
                advice_label = "Strong Sell - Act"
            elif (exp_ret is not None and exp_ret > 0.50) or (ltm is not None and ltm > 0):
                advice_label = "Strong Sell - Wait"
            else:
                advice_label = "Strong Sell"

    results["advice"] = _score_result(
        score_id="advice",
        name="Advice (Signal synthétique)",
        category="Signal",
        unit="label",
        available=us_pct is not None,
        final_score=us_pct,
        display_value=advice_label,
        warnings=([] if verified else ["Arbre de décision source contient des branches dupliquées ou inversées."]),
    )

    # 28-31. ESG Scores (données EODHD si présentes, jamais de valeurs inventées)
    esg = d["esg_raw"] if isinstance(d["esg_raw"], dict) else {}
    esg_map = [
        ("esg_score", "ESG score", _num(esg.get("TotalEsg"))),
        ("environment_score", "Environment score", _num(esg.get("EnvironmentScore"))),
        ("social_score", "Social score", _num(esg.get("SocialScore"))),
        ("governance_score", "Governance score", _num(esg.get("GovernanceScore"))),
    ]
    for eid, ename, eval_num in esg_map:
        results[eid] = _score_result(
            score_id=eid,
            name=ename,
            category="ESG",
            unit="/100",
            available=eval_num is not None,
            final_score=eval_num,
            display_value=f"{eval_num:.1f}" if eval_num is not None else "Indisponible",
            warnings=([] if eval_num is not None else ["Données ESG absentes du flux fondamental pour ce titre (non estimées)."]),
        )

    return results


def compute_uncle_stock_scores(
    *,
    ann_series: dict[str, list[float | None]],
    dates: list[str],
    current_price: float | None = None,
    shares_override: float | None = None,
    eod_fund: dict[str, Any] | None = None,
    capital_valuation: dict[str, Any] | None = None,
    intrinsic_valuation: dict[str, Any] | None = None,
    piotroski_score: int | None = None,
    bars: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calcule les 31 scores et indicateurs Uncle Stock en deux modes (`verified` et `documented`)."""
    if not dates:
        return {"available": False, "reason": "Historique annuel insuffisant.", "documented": {}, "verified": {}, "items": []}

    bundle = _extract_fundamental_bundle(
        ann_series=ann_series,
        dates=dates,
        current_price=current_price,
        shares_override=shares_override,
        eod_fund=eod_fund,
        capital_valuation=capital_valuation,
        intrinsic_valuation=intrinsic_valuation,
        piotroski_latest=piotroski_score,
        bars=bars,
    )

    doc_map = _compute_for_mode(bundle, "documented")
    ver_map = _compute_for_mode(bundle, "verified")

    ordered_ids = [
        "advice", "categories", "is_undervalued", "trap_score",
        "uncle_stock_score", "quality_score", "value_score", "yield_score",
        "balance_score", "balance_value_score", "financial_health_score",
        "growth_rate", "predictability_score",
        "piotroski_f_score", "mohanram_g_score", "montier_c_score", "levermann_score",
        "company_score", "oshaughnessy_vc3", "greenblatt_score", "pim_van_vliet_score",
        "erp5_score", "slater_score",
        "altman_z_score", "ohlson_o_score", "beneish_m_score", "dechow_f_score",
        "esg_score", "environment_score", "social_score", "governance_score",
    ]
    items = []
    for sid in ordered_ids:
        v = ver_map[sid]
        d = doc_map[sid]
        items.append({
            "id": sid,
            "name": v["name"],
            "category": v["category"],
            "unit": v["unit"],
            "available": v["available"],
            "verified": v,
            "documented": d,
        })

    return {
        "available": True,
        "source_version": _SOURCE_VERSION,
        "summary": {
            "advice_verified": ver_map["advice"]["display_value"],
            "advice_documented": doc_map["advice"]["display_value"],
            "categories": ver_map["categories"]["display_value"],
            "uncle_stock_score_verified": ver_map["uncle_stock_score"]["final_score"],
            "uncle_stock_score_documented": doc_map["uncle_stock_score"]["final_score"],
            "quality_score": ver_map["quality_score"]["final_score"],
            "value_score": ver_map["value_score"]["final_score"],
            "financial_health_score": ver_map["financial_health_score"]["final_score"],
            "trap_score": ver_map["trap_score"]["final_score"],
        },
        "items": items,
    }
