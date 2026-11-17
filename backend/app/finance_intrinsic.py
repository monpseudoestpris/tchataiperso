"""Module de valorisation intrinsèque (méthodologie Uncle Stock + mode indépendant corrigé).

Implémente l'ensemble des modèles de valorisation et métriques de coût du capital :
- Coût des capitaux propres (CAPM borné [0, 2] et DDM), coût de la dette après impôts, WACC (avec plancher), Charge d'équité
- rCAGR 67% (régression log-linéaire prudente ajustée de la dispersion)
- Retours propriétaires : Total Owner Return, Net Owner Return, Rate of Return (Buffett IRR), Forward Rate of Return (Yacktman)
- Les 13 composantes pondérées d'Uncle Stock :
  DCF FCF (5), Buffett DDM+BV (4), Residual Income (3), Graham Formula (3), EPV (3),
  Value Driver McKinsey (2), Lynch (2), Graham Number (2), Multiple EBITDA 7.5x (2),
  Hold 5 Years (1), DCF FCF No Growth (1), Adjusted Lynch (1), Cours actuel (1)
- Les méthodes complémentaires :
  DCF Owner Earnings (OE), DCF OE Linéaire, DCF OE Quadratique, DCF OE Régression (min),
  O'Malley Formula, x Years Payback (+ solveur de payback en années)
- Agrégation double :
  1) Mode Fidèle Uncle Stock (13 composantes dont Cours poids 1, formules littérales)
  2) Mode Indépendant Corrigé (exclut le Cours, corrige EPV après impôts, Value Driver en equity, Graham parenthèses globales, et filtre les modèles économiquement aberrants)
- Analyse de sensibilité (WACC x croissance) et 3 scénarios (Prudent, Central, Optimiste).
"""

from __future__ import annotations

import math
from typing import Any

_ERP_DAMODARAN = 0.046  # Prime de risque actions baseline Damodaran (4,6 %)

_MARGINAL_TAX_RATES = {
    "USA": 0.21,
    "FRA": 0.25,
    "DEU": 0.30,
    "GBR": 0.25,
    "CHE": 0.15,
    "NLD": 0.258,
    "BEL": 0.25,
    "ITA": 0.24,
    "ESP": 0.25,
    "JPN": 0.306,
    "CAN": 0.265,
    "AUS": 0.30,
    "IRL": 0.125,
    "SWE": 0.206,
    "DNK": 0.22,
    "FIN": 0.20,
    "NOR": 0.22,
    "CHN": 0.25,
    "TWN": 0.20,
    "KOR": 0.24,
}

_CURRENCY_RF_FALLBACK = {
    "USD": 0.042,
    "EUR": 0.030,
    "GBP": 0.042,
    "CHF": 0.012,
    "JPY": 0.012,
    "CAD": 0.035,
}


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _ols_linear(xs: list[float], ys: list[float]) -> tuple[float, float, float] | None:
    """Retourne `(slope, intercept, se_slope)` par moindres carrés ordinaires."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    if n > 2:
        sse = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        se_slope = math.sqrt(max(0.0, sse / (n - 2)) / sxx)
    else:
        se_slope = 0.0
    return slope, intercept, se_slope


def _ols_quadratic(xs: list[float], ys: list[float]) -> tuple[float, float, float] | None:
    """Ajuste `a*x^2 + b*x + c` sur `(xs, ys)` via système normal 3x3 (pivot de Gauss)."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    # Centrer x pour la stabilité numérique, puis reconvertir dans la coordonnée d'origine
    mx = sum(xs) / n
    dxs = [x - mx for x in xs]
    s0 = float(n)
    s1 = sum(dxs)
    s2 = sum(dx ** 2 for dx in dxs)
    s3 = sum(dx ** 3 for dx in dxs)
    s4 = sum(dx ** 4 for dx in dxs)
    t0 = sum(ys)
    t1 = sum(dx * y for dx, y in zip(dxs, ys))
    t2 = sum((dx ** 2) * y for dx, y in zip(dxs, ys))

    mat = [
        [s4, s3, s2, t2],
        [s3, s2, s1, t1],
        [s2, s1, s0, t0],
    ]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(mat[r][col]))
        if abs(mat[piv][col]) < 1e-12:
            return None
        mat[col], mat[piv] = mat[piv], mat[col]
        div = mat[col][col]
        for j in range(col, 4):
            mat[col][j] /= div
        for r in range(3):
            if r != col:
                fac = mat[r][col]
                for j in range(col, 4):
                    mat[r][j] -= fac * mat[col][j]

    a_c, b_c, c_c = mat[0][3], mat[1][3], mat[2][3]
    # Re-développer a_c*(x - mx)^2 + b_c*(x - mx) + c_c = a*x^2 + b*x + c
    a = a_c
    b = b_c - 2.0 * a_c * mx
    c = a_c * (mx ** 2) - b_c * mx + c_c
    if not all(math.isfinite(v) for v in (a, b, c)):
        return None
    return a, b, c


def compute_rcagr_67(
    values: list[float | None],
    *,
    max_years: int = 15,
    min_positive_ratio: float = 0.67,
    cap_min: float = -0.25,
    cap_max: float = 0.30,
) -> tuple[float | None, float | None]:
    """Calcule `(rCAGR_67, rCAGR_brut)` via régression log-linéaire prudente.

    - Requiert au moins `min_positive_ratio` de valeurs strictement positives sur la fenêtre.
    - Déplace la pente vers le bas de `0.44 * erreur_standard` (~67e percentile conservateur)
      afin de pénaliser les séries irrégulières tout en restant fidèle à la tendance OLS.
    """
    window = [v for v in values[-max_years:] if v is not None]
    if len(window) < 2:
        return None, None
    pos_pts = [(float(i), math.log(v)) for i, v in enumerate(values[-max_years:]) if v is not None and v > 0]
    if len(pos_pts) < max(2, math.ceil(len(window) * min_positive_ratio)):
        return None, None

    xs = [p[0] for p in pos_pts]
    lns = [p[1] for p in pos_pts]
    res = _ols_linear(xs, lns)
    if res is None:
        return None, None
    slope, _intercept, se_slope = res
    raw_rcagr = math.exp(slope) - 1.0
    # Estimation prudente (67e percentile conservateur = ~0,44 écart-type sous la pente moyenne)
    prudent_slope = slope - 0.44 * se_slope
    prudent_rcagr = math.exp(prudent_slope) - 1.0

    # Garde-fous pour éviter les divergences exponentielles sur séries très courtes ou explosives
    clamped_prudent = max(cap_min, min(cap_max, prudent_rcagr))
    clamped_raw = max(-0.40, min(0.60, raw_rcagr))
    return round(clamped_prudent, 5), round(clamped_raw, 5)


def _pv_5y_plus_perpetuity(cf0: float, g: float, discount_rate: float) -> tuple[float, float, float] | None:
    """Somme actualisée sur 5 ans + valeur terminale sans croissance post-année 5.

    Retourne `(total_pv, pv_5y, pv_terminal)`.
    """
    if discount_rate <= 0:
        return None
    pv_5y = 0.0
    cf5 = cf0
    for t in range(1, 6):
        cf_t = cf0 * ((1.0 + g) ** t)
        pv_5y += cf_t / ((1.0 + discount_rate) ** t)
        if t == 5:
            cf5 = cf_t
    vt5 = cf5 / discount_rate
    pv_tv = vt5 / ((1.0 + discount_rate) ** 5)
    return pv_5y + pv_tv, pv_5y, pv_tv


def _buffett_ddm_bv(div_ps: float, g_div: float, bvps: float, g_bv: float, r: float) -> tuple[float, float, float] | None:
    """Intrinsic Value (Buffett) : 10 ans de dividendes actualisés + BVPS année 10 actualisée."""
    if r <= 0:
        return None
    pv_divs = sum((div_ps * ((1.0 + g_div) ** t)) / ((1.0 + r) ** t) for t in range(1, 11))
    pv_bv10 = (bvps * ((1.0 + g_bv) ** 10)) / ((1.0 + r) ** 10)
    return pv_divs + pv_bv10, pv_divs, pv_bv10


def _solve_buffett_irr(price: float, div_ps: float, g_div: float, bvps: float, g_bv: float) -> float | None:
    """Résout par dichotomie le taux `r` tel que `IntrinsicValue_Buffett(r) == Price`."""
    if price <= 0 or bvps <= 0:
        return None

    def _val(r: float) -> float:
        res = _buffett_ddm_bv(div_ps, g_div, bvps, g_bv, r)
        return res[0] if res else float("nan")

    lo, hi = 0.001, 1.50
    v_lo, v_hi = _val(lo), _val(hi)
    if not (math.isfinite(v_lo) and math.isfinite(v_hi)) or v_lo < price or v_hi > price:
        return None
    for _ in range(55):
        mid = 0.5 * (lo + hi)
        if _val(mid) > price:
            lo = mid
        else:
            hi = mid
    return round(0.5 * (lo + hi), 5)


def _method_entry(
    method_id: str,
    name: str,
    category: str,
    weight: int,
    *,
    unclestock_val: float | None,
    corrected_val: float | None,
    current_price: float | None,
    status_unclestock: str = "valid",
    status_corrected: str = "valid",
    exclusion_reason: str | None = None,
    warnings: list[str] | None = None,
    assumptions: list[str] | None = None,
    intermediates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construit l'objet standardisé d'une méthode de valorisation."""
    def _ratios(val: float | None, st: str) -> tuple[float | None, float | None]:
        if st != "valid" or val is None or val <= 0 or current_price is None or current_price <= 0:
            return None, None
        p_iv = current_price / val
        mos = (1.0 - p_iv) * 100.0
        return round(p_iv, 3), round(mos, 1)

    u_val = round(unclestock_val, 2) if (unclestock_val is not None and math.isfinite(unclestock_val)) else None
    c_val = round(corrected_val, 2) if (corrected_val is not None and math.isfinite(corrected_val)) else None
    p_iv_u, mos_u = _ratios(u_val, status_unclestock)
    p_iv_c, mos_c = _ratios(c_val, status_corrected)

    return {
        "id": method_id,
        "name": name,
        "category": category,
        "weight": weight,
        "unclestock_value": u_val,
        "corrected_value": c_val,
        "status_unclestock": status_unclestock if u_val is not None else ("excluded" if status_unclestock == "excluded" else "unavailable"),
        "status_corrected": status_corrected if c_val is not None else ("excluded" if status_corrected == "excluded" else "unavailable"),
        "price_to_iv_unclestock": p_iv_u,
        "margin_of_safety_unclestock_pct": mos_u,
        "price_to_iv_corrected": p_iv_c,
        "margin_of_safety_corrected_pct": mos_c,
        "exclusion_reason": exclusion_reason,
        "warnings": warnings or [],
        "assumptions": assumptions or [],
        "intermediates": intermediates or {},
    }


def _compute_dcf_sensitivity_and_scenarios(
    fcff0: float,
    g_base: float,
    wacc_base: float,
    deductions: float,
    shares: float,
    current_price: float | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Calcule 3 scénarios (Prudent, Central, Optimiste) et la matrice WACC × g."""
    def _eval(g_val: float, w_val: float) -> float | None:
        if w_val <= 0.02 or shares <= 0:
            return None
        res = _pv_5y_plus_perpetuity(fcff0, g_val, w_val)
        if res is None:
            return None
        eq = res[0] - deductions
        return round(eq / shares, 2)

    scenarios_spec = [
        ("prudent", "Prudent", max(-0.10, g_base - 0.02), min(0.20, wacc_base + 0.015)),
        ("central", "Central (Base)", g_base, wacc_base),
        ("optimiste", "Optimiste", min(0.25, g_base + 0.02), max(0.04, wacc_base - 0.01)),
    ]
    scenarios: list[dict[str, Any]] = []
    for key, label, g_s, w_s in scenarios_spec:
        iv = _eval(g_s, w_s)
        mos = (
            round((1.0 - current_price / iv) * 100.0, 1)
            if (iv and iv > 0 and current_price and current_price > 0)
            else None
        )
        scenarios.append({
            "key": key,
            "label": label,
            "growth_pct": round(g_s * 100.0, 2),
            "wacc_pct": round(w_s * 100.0, 2),
            "intrinsic_value": iv,
            "margin_of_safety_pct": mos,
        })

    wacc_steps = [round(max(0.04, wacc_base + d), 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    growth_steps = [round(max(-0.05, min(0.25, g_base + d)), 4) for d in (-0.03, -0.015, 0.0, 0.015, 0.03)]
    rows = []
    for w_s in wacc_steps:
        cells = []
        for g_s in growth_steps:
            iv = _eval(g_s, w_s)
            cells.append({
                "growth_pct": round(g_s * 100.0, 2),
                "wacc_pct": round(w_s * 100.0, 2),
                "value": iv,
                "undervalued": bool(iv is not None and current_price is not None and iv > current_price),
            })
        rows.append({"wacc_pct": round(w_s * 100.0, 2), "cells": cells})

    sensitivity = {
        "growth_headers_pct": [round(g_s * 100.0, 2) for g_s in growth_steps],
        "rows": rows,
    }
    return scenarios, sensitivity


def compute_intrinsic_valuations(
    *,
    ann_series: dict[str, dict[str, float | None]],
    dates: list[str],
    current_price: float | None,
    currency: str,
    country_iso3: str = "USA",
    beta: float | None = None,
    shares_override: float | None = None,
    dividend_yield_pct: float | None = None,
    preferred_stock: float | None = None,
    minority_interest: float | None = None,
    macro_context: dict[str, Any] | None = None,
    piotroski_score: int | None = None,
    bars: list[dict[str, Any]] | None = None,
    payback_years: int = 5,
) -> dict[str, Any]:
    """Calcule toutes les valeurs intrinsèques (Uncle Stock + mode corrigé) à partir des séries normalisées."""
    cur_upper = (currency or "USD").strip().upper()
    iso_upper = (country_iso3 or "USA").strip().upper()

    # 1. Taux sans risque & hypothèses macroéconomiques
    ust_rf_pct = _num(((macro_context or {}).get("us_treasury") or {}).get("risk_free_pct"))
    rf_usd = (ust_rf_pct / 100.0) if (ust_rf_pct is not None and ust_rf_pct > 0) else _CURRENCY_RF_FALLBACK["USD"]
    rf_curr = rf_usd if cur_upper == "USD" else _CURRENCY_RF_FALLBACK.get(cur_upper, rf_usd)
    rf_30y = rf_usd + 0.004  # Proxy Treasury 30 ans (+40 bps sur courbe courte/1y)
    bond_rate_20y = max(0.044, rf_usd + 0.011)  # Corporate A 20 ans (plancher 4,4 % historique Graham)
    bond_rate_pct = bond_rate_20y * 100.0
    marginal_tax = _MARGINAL_TAX_RATES.get(iso_upper, 0.25)
    inflation_val = _num(((macro_context or {}).get("inflation_pct") or {}).get("value"))
    inflation = (inflation_val / 100.0) if (inflation_val is not None and -0.05 < inflation_val < 20.0) else 0.025

    def _series_vec(key: str) -> list[float | None]:
        src = ann_series.get(key) or {}
        return [_num(src.get(d)) for d in dates]

    rev_v = _series_vec("TotalRevenue")
    gp_v = _series_vec("GrossProfit")
    opinc_v = _series_vec("OperatingIncome")
    ebit_v = _series_vec("EBIT")
    ebitda_v = _series_vec("EBITDA")
    int_exp_v = _series_vec("InterestExpense")
    pretax_v = _series_vec("PretaxIncome")
    tax_v = _series_vec("TaxProvision")
    ni_v = _series_vec("NetIncome")
    eps_v = _series_vec("DilutedEPS")
    shares_v = _series_vec("CommonStockSharesOutstanding")
    dil_shares_v = _series_vec("DilutedAverageShares")
    eq_v = _series_vec("StockholdersEquity")
    gw_int_v = _series_vec("GoodwillAndIntangibleAssets")
    tot_debt_v = _series_vec("TotalDebt")
    net_debt_v = _series_vec("NetDebt")
    cash_v = _series_vec("CashCashEquivalentsAndShortTermInvestments")
    cash_alt_v = _series_vec("CashAndCashEquivalents")
    sga_v = _series_vec("SellingGeneralAndAdministration")
    ocf_v = _series_vec("OperatingCashFlow")
    capex_v = _series_vec("CapitalExpenditure")
    fcf_v = _series_vec("FreeCashFlow")
    sbc_v = _series_vec("StockBasedCompensation")
    dwc_v = _series_vec("ChangeInWorkingCapital")
    div_paid_v = _series_vec("CashDividendsPaid")

    n_periods = len(dates)
    pref = max(0.0, _num(preferred_stock) or 0.0)
    nci = max(0.0, _num(minority_interest) or 0.0)

    def _last(vec: list[float | None]) -> float | None:
        for v in reversed(vec):
            if v is not None:
                return v
        return None

    # Nombre d'actions cohérent (diluées / circulation / fallback market cap)
    shares_latest = _num(shares_override) or _last(shares_v) or _last(dil_shares_v)
    if not shares_latest or shares_latest <= 0:
        return {
            "available": False,
            "reason": "Nombre d'actions ou états financiers annuels insuffisants pour valoriser le titre.",
            "cost_of_capital": {},
            "owner_returns": {},
            "summary": {"unclestock": None, "corrected": None},
            "methods": [],
            "scenarios": [],
            "sensitivity": None,
        }

    # Construction des séries dérivées annuelles
    fcff_v: list[float | None] = []
    oe_v: list[float | None] = []
    cash_nopat_v: list[float | None] = []
    nopat_v: list[float | None] = []
    cbv_v: list[float | None] = []
    tcbv_v: list[float | None] = []
    adj_oiai_v: list[float | None] = []
    croic_v: list[float | None] = []
    reinvest_v: list[float | None] = []
    div_ps_v: list[float | None] = []
    eff_eps_v: list[float | None] = []

    for i in range(n_periods):
        sh_i = shares_v[i] or dil_shares_v[i] or shares_latest
        ocf_i = ocf_v[i]
        capex_i = abs(capex_v[i]) if capex_v[i] is not None else None
        fcf_i = fcf_v[i]
        if fcf_i is None and ocf_i is not None and capex_i is not None:
            fcf_i = ocf_i - capex_i

        int_i = abs(int_exp_v[i]) if int_exp_v[i] is not None else 0.0
        pretax_i = pretax_v[i]
        tax_i = tax_v[i]
        eff_tax = (
            max(0.0, min(0.50, tax_i / pretax_i))
            if (tax_i is not None and pretax_i is not None and pretax_i > 0)
            else marginal_tax
        )
        fcff_i = (fcf_i + int_i * (1.0 - eff_tax)) if fcf_i is not None else None
        fcff_v.append(fcff_i)

        # Owner Earnings (CFO - SBC - NCI - CapEx) ; repli propre sur FCF si SBC absent
        sbc_i = abs(sbc_v[i]) if sbc_v[i] is not None else 0.0
        oe_i = (fcf_i - sbc_i) if fcf_i is not None else None
        oe_v.append(oe_i)

        opinc_i = opinc_v[i] if opinc_v[i] is not None else ebit_v[i]
        nopat_i = (opinc_i * (1.0 - eff_tax)) if opinc_i is not None else ni_v[i]
        nopat_v.append(nopat_i)

        # Cash-NOPAT : CFO après ajustement intérêts ou EBITDA*(1-T) / CFO
        cn_i = (ocf_i + int_i * (1.0 - eff_tax)) if ocf_i is not None else nopat_i
        cash_nopat_v.append(cn_i)

        eq_i = eq_v[i]
        cbv_i = (eq_i - pref) if eq_i is not None else None
        cbv_v.append(cbv_i)
        gw_i = abs(gw_int_v[i]) if gw_int_v[i] is not None else 0.0
        tcbv_v.append((cbv_i - gw_i) if cbv_i is not None else None)

        # Adjusted Operating Income After Interest (Carlisle: GP - min(SG&A + DA, OpEx) - Int)
        gp_i = gp_v[i]
        if gp_i is not None and sga_v[i] is not None:
            adj_oi = max(gp_i - abs(sga_v[i]), opinc_i if opinc_i is not None else gp_i - abs(sga_v[i]))
            adj_oiai_v.append(adj_oi - int_i)
        elif opinc_i is not None:
            adj_oiai_v.append(opinc_i - int_i)
        else:
            adj_oiai_v.append(None)

        td_i = tot_debt_v[i] if tot_debt_v[i] is not None else 0.0
        ci_i = (eq_i + td_i) if (eq_i is not None and (eq_i + td_i) > 0) else None
        croic_v.append((cn_i / ci_i) if (cn_i is not None and ci_i) else None)

        if cn_i is not None and cn_i > 0 and capex_i is not None:
            dwc_i = dwc_v[i] or 0.0
            rr_i = max(-0.5, min(1.5, (capex_i + dwc_i) / cn_i))
            reinvest_v.append(rr_i)
        else:
            reinvest_v.append(None)

        dp_i = abs(div_paid_v[i]) if div_paid_v[i] is not None else 0.0
        div_ps_v.append((dp_i / sh_i) if sh_i > 0 else None)

        eps_i = eps_v[i]
        if eps_i is None and ni_v[i] is not None and sh_i > 0:
            eps_i = ni_v[i] / sh_i
        eff_eps_v.append(eps_i)

    # Valeurs courantes (dernier exercice disponible)
    latest_fcff = _last(fcff_v)
    latest_oe = _last(oe_v)
    latest_fcf = _last(fcf_v)
    latest_ebitda = _last(ebitda_v)
    latest_opinc = _last(opinc_v) or _last(ebit_v)
    latest_nopat = _last(nopat_v)
    latest_cn = _last(cash_nopat_v)
    latest_eps = _last(eff_eps_v)
    latest_cbv = _last(cbv_v)
    latest_tcbv = _last(tcbv_v)
    latest_cbv_ps = (latest_cbv / shares_latest) if (latest_cbv is not None and shares_latest > 0) else None
    latest_tcbv_ps = (latest_tcbv / shares_latest) if (latest_tcbv is not None and shares_latest > 0) else None

    latest_div_ps = _last(div_ps_v) or 0.0
    if latest_div_ps == 0.0 and dividend_yield_pct and current_price:
        latest_div_ps = current_price * (dividend_yield_pct / 100.0)

    latest_tot_debt = _last(tot_debt_v) or 0.0
    latest_cash = _last(cash_v) or _last(cash_alt_v) or 0.0
    latest_net_debt = _last(net_debt_v)
    if latest_net_debt is None:
        latest_net_debt = latest_tot_debt - latest_cash
    deductions = latest_net_debt + nci + pref

    # 2. Coût des capitaux propres, Coût de la dette, WACC
    beta_clamped = max(0.0, min(2.0, beta)) if beta is not None else None
    ke_capm = (rf_curr + beta_clamped * _ERP_DAMODARAN) if beta_clamped is not None else 0.085

    fh_score = max(0, min(4, round((piotroski_score or 5) * 4 / 9)))
    kd_pretax = rf_curr + (bond_rate_20y - rf_usd) + 0.0025 * (4 - fh_score)
    kd_after_tax = max(0.01, kd_pretax * (1.0 - marginal_tax))

    market_cap = (current_price * shares_latest) if (current_price and current_price > 0) else (latest_cbv or 0.0)
    financing_total = max(1.0, market_cap + max(0.0, latest_tot_debt))
    eq_ratio = max(0.0, min(1.0, market_cap / financing_total))
    debt_ratio = 1.0 - eq_ratio

    wacc_floor = max(0.04, rf_curr + 0.03)
    wacc_raw = eq_ratio * ke_capm + debt_ratio * kd_after_tax
    wacc = max(wacc_floor, wacc_raw)

    # Taux de croissance prudents rCAGR 67%
    g_fcff, g_fcff_raw = compute_rcagr_67(fcff_v)
    g_oe, g_oe_raw = compute_rcagr_67(oe_v)
    g_ebitda, g_ebitda_raw = compute_rcagr_67(ebitda_v)
    g_eps, g_eps_raw = compute_rcagr_67(eff_eps_v)
    g_cbv, _ = compute_rcagr_67(cbv_v)
    g_div, _ = compute_rcagr_67(div_ps_v)
    if g_div is None:
        g_div = 0.0

    # Residual Income par action historique + rCAGR 67%
    ri_ps_v: list[float | None] = []
    for i in range(n_periods):
        sh_i = shares_v[i] or dil_shares_v[i] or shares_latest
        bv_ps_i = (cbv_v[i] / sh_i) if (cbv_v[i] is not None and sh_i > 0) else None
        if eff_eps_v[i] is not None and bv_ps_i is not None:
            ri_ps_v.append(eff_eps_v[i] - ke_capm * bv_ps_i)
        else:
            ri_ps_v.append(None)
    latest_ri_ps = _last(ri_ps_v)
    g_ri, _ = compute_rcagr_67(ri_ps_v)

    equity_charge_ps = (ke_capm * latest_cbv_ps) if latest_cbv_ps is not None else None
    equity_charge_total = (ke_capm * latest_cbv) if latest_cbv is not None else None

    # Cost of Equity (DDM)
    div_yield_dec = (
        (dividend_yield_pct / 100.0)
        if dividend_yield_pct is not None
        else ((latest_div_ps / current_price) if (current_price and current_price > 0) else 0.0)
    )
    ke_ddm = div_yield_dec + (g_div or 0.0)

    # Total Owner Return & Net Owner Return (sur dernier exercice disponible t1 -> t2)
    total_owner_return_pct: float | None = None
    net_owner_return_pct: float | None = None
    valid_cbv_idx = [i for i, v in enumerate(cbv_v) if v is not None and v > 0]
    if len(valid_cbv_idx) >= 2:
        i1, i2 = valid_cbv_idx[-2], valid_cbv_idx[-1]
        cbv1, cbv2 = cbv_v[i1], cbv_v[i2]
        div_t2 = abs(div_paid_v[i2]) if div_paid_v[i2] is not None else (latest_div_ps * shares_latest)
        if cbv1 and cbv1 > 0 and cbv2 is not None:
            total_owner_return_pct = round(((cbv2 + div_t2 - cbv1) / cbv1) * 100.0, 2)
            eq_chg_t1 = ke_capm * cbv1
            net_owner_return_pct = round(((cbv2 + div_t2 - eq_chg_t1 - cbv1) / cbv1) * 100.0, 2)

    # Normalisations 5 ans & 10 ans
    def _avg_last(vec: list[float | None], k: int) -> float | None:
        pts = [v for v in vec[-k:] if v is not None]
        return (sum(pts) / len(pts)) if pts else None

    norm_opinc = _avg_last(opinc_v, 5) or latest_opinc
    norm_nopat = _avg_last(nopat_v, 5) or latest_nopat
    croic_5y = _avg_last(croic_v, 5)
    reinvest_5y = _avg_last(reinvest_v, 5)

    # =========================================================================
    # CALCUL DES 13 COMPOSANTES PONDÉRÉES + MÉTHODES COMPLÉMENTAIRES
    # =========================================================================
    methods: list[dict[str, Any]] = []

    # 1. DCF FCF (poids: 5)
    g_dcf_fcf = g_fcff if g_fcff is not None else (g_ebitda if g_ebitda is not None else 0.03)
    if latest_fcff is not None and latest_fcff > 0:
        res = _pv_5y_plus_perpetuity(latest_fcff, g_dcf_fcf, wacc)
        if res:
            ev_dcf, pv_5y, pv_tv = res
            eq_dcf = ev_dcf - deductions
            iv_dcf = eq_dcf / shares_latest
            st = "valid" if iv_dcf > 0 else "excluded"
            methods.append(_method_entry(
                "dcf_fcf",
                "DCF FCF (Unlevered)",
                "weighted",
                5,
                unclestock_val=iv_dcf,
                corrected_val=iv_dcf if iv_dcf > 0 else None,
                current_price=current_price,
                status_unclestock="valid",
                status_corrected=st,
                exclusion_reason="Valeur des fonds propres négative après déduction de la dette nette" if st == "excluded" else None,
                assumptions=[
                    f"FCFF₀ = {latest_fcff / 1e6:,.1f} M {cur_upper}",
                    f"Croissance prudente (rCAGR 67%) = {g_dcf_fcf * 100:.2f}%",
                    f"WACC = {wacc * 100:.2f}% (horizon 5 ans, croissance terminale 0%)",
                ],
                intermediates={
                    "fcff_initial": round(latest_fcff, 2),
                    "pv_5y_cashflows": round(pv_5y, 2),
                    "pv_terminal_value": round(pv_tv, 2),
                    "enterprise_value": round(ev_dcf, 2),
                    "deductions_net_debt_nci_pref": round(-deductions, 2),
                    "equity_value": round(eq_dcf, 2),
                    "shares": round(shares_latest, 0),
                },
            ))
        else:
            methods.append(_method_entry("dcf_fcf", "DCF FCF (Unlevered)", "weighted", 5, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="unavailable", status_corrected="unavailable", exclusion_reason="WACC invalide"))
    else:
        methods.append(_method_entry(
            "dcf_fcf", "DCF FCF (Unlevered)", "weighted", 5,
            unclestock_val=None, corrected_val=None, current_price=current_price,
            status_unclestock="excluded", status_corrected="excluded",
            exclusion_reason="FCFF négatif ou indisponible — perpétuité DCF non pertinente",
        ))

    # 2. Buffett (poids: 4)
    if latest_cbv_ps is not None and latest_cbv_ps > 0:
        g_b = g_cbv if g_cbv is not None else 0.04
        res_b = _buffett_ddm_bv(latest_div_ps, g_div, latest_cbv_ps, g_b, ke_capm)
        if res_b:
            iv_b, pv_divs, pv_bv10 = res_b
            methods.append(_method_entry(
                "buffett",
                "Intrinsic Value (Buffett)",
                "weighted",
                4,
                unclestock_val=iv_b,
                corrected_val=iv_b,
                current_price=current_price,
                assumptions=[
                    f"Dividende/action = {latest_div_ps:.2f} {cur_upper} (g = {g_div * 100:.2f}%)",
                    f"BVPS = {latest_cbv_ps:.2f} {cur_upper} (g = {g_b * 100:.2f}%)",
                    f"Ke CAPM = {ke_capm * 100:.2f}% sur 10 ans",
                ],
                intermediates={
                    "pv_10y_dividends_ps": round(pv_divs, 2),
                    "pv_year10_book_ps": round(pv_bv10, 2),
                },
            ))
    else:
        methods.append(_method_entry(
            "buffett", "Intrinsic Value (Buffett)", "weighted", 4,
            unclestock_val=None, corrected_val=None, current_price=current_price,
            status_unclestock="excluded", status_corrected="excluded",
            exclusion_reason="Valeur comptable commune négative ou indisponible",
        ))

    # 3. Residual Income Model (poids: 3)
    if latest_cbv_ps is not None and latest_ri_ps is not None:
        g_r = g_ri if g_ri is not None else (g_eps if g_eps is not None else 0.02)
        res_ri = _pv_5y_plus_perpetuity(latest_ri_ps, g_r, ke_capm)
        if res_ri:
            pv_ri_tot, pv_ri_5y, pv_ri_tv = res_ri
            iv_ri = latest_cbv_ps + pv_ri_tot
            st_c = "valid" if iv_ri > 0 else "excluded"
            methods.append(_method_entry(
                "residual_income",
                "Residual Income Model",
                "weighted",
                3,
                unclestock_val=iv_ri,
                corrected_val=iv_ri if iv_ri > 0 else None,
                current_price=current_price,
                status_corrected=st_c,
                exclusion_reason="Revenu résiduel total négatif" if st_c == "excluded" else None,
                assumptions=[
                    f"BVPS₀ = {latest_cbv_ps:.2f} · RI₀ = {latest_ri_ps:.2f} {cur_upper}/act.",
                    f"g(RI) = {g_r * 100:.2f}% · Ke = {ke_capm * 100:.2f}%",
                ],
                intermediates={
                    "bvps": round(latest_cbv_ps, 2),
                    "residual_income_ps": round(latest_ri_ps, 2),
                    "equity_charge_ps": round(equity_charge_ps or 0.0, 2),
                    "pv_5y_residual": round(pv_ri_5y, 2),
                    "pv_terminal_residual": round(pv_ri_tv, 2),
                },
            ))
    else:
        methods.append(_method_entry("residual_income", "Residual Income Model", "weighted", 3, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="unavailable", status_corrected="unavailable", exclusion_reason="EPS ou BVPS indisponible"))

    # 4. Graham Formula (poids: 3) — gère explicitement l'ambiguïté de parenthèse documentée !
    if latest_eps is not None and latest_eps > 0:
        g_graham = min(0.15, max(0.0, g_eps if g_eps is not None else 0.05))
        g_term = 100.0 * math.log(1.0 + g_graham)
        bond_factor = 4.4 / bond_rate_pct
        iv_graham_literal = latest_eps * (7.0 + g_term * bond_factor)
        iv_graham_corrected = latest_eps * (7.0 + g_term) * bond_factor
        methods.append(_method_entry(
            "graham_formula",
            "Graham Formula",
            "weighted",
            3,
            unclestock_val=iv_graham_literal,
            corrected_val=iv_graham_corrected,
            current_price=current_price,
            warnings=["Ambiguïté parenthèse Uncle Stock : facteur obligataire 4,4/Y appliqué au seul terme de croissance en mode littéral vs toute l'expression en mode corrigé."],
            assumptions=[
                f"EPS = {latest_eps:.2f} {cur_upper} · g plafonné = {g_graham * 100:.2f}% (100×ln(1+g) = {g_term:.2f})",
                f"Taux obligataire Corporate A 20A = {bond_rate_pct:.2f}%",
            ],
            intermediates={
                "eps": round(latest_eps, 2),
                "g_capped_pct": round(g_graham * 100.0, 2),
                "corporate_bond_rate_pct": round(bond_rate_pct, 2),
                "literal_formula": round(iv_graham_literal, 2),
                "outer_parens_corrected": round(iv_graham_corrected, 2),
            },
        ))
    else:
        methods.append(_method_entry("graham_formula", "Graham Formula", "weighted", 3, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="EPS négatif ou nul"))

    # 5. Earnings Power Value of Equity (poids: 3) — littéral (pré-impôts) vs corrigé (NOPAT après impôts)
    if norm_opinc is not None and norm_opinc > 0:
        epv_firm_lit = norm_opinc / wacc
        epv_eq_lit = (epv_firm_lit - deductions) / shares_latest
        nopat_ref = norm_nopat if (norm_nopat is not None and norm_nopat > 0) else norm_opinc * (1.0 - marginal_tax)
        epv_firm_corr = nopat_ref / wacc
        epv_eq_corr = (epv_firm_corr - deductions) / shares_latest
        st_c = "valid" if epv_eq_corr > 0 else "excluded"
        methods.append(_method_entry(
            "epv",
            "Earnings Power Value (EPV)",
            "weighted",
            3,
            unclestock_val=epv_eq_lit,
            corrected_val=epv_eq_corr if epv_eq_corr > 0 else None,
            current_price=current_price,
            status_corrected=st_c,
            warnings=["La formule littérale Uncle Stock utilise l'Operating Income avant impôts ; le mode corrigé utilise le NOPAT normalisé après impôts."],
            exclusion_reason="EPV des fonds propres négative après dette nette" if st_c == "excluded" else None,
            assumptions=[
                f"OI normalisé (5A) = {norm_opinc / 1e6:,.1f} M · NOPAT normalisé = {nopat_ref / 1e6:,.1f} M",
                f"WACC = {wacc * 100:.2f}%",
            ],
            intermediates={
                "epv_firm_pretax": round(epv_firm_lit, 2),
                "epv_firm_after_tax": round(epv_firm_corr, 2),
                "deductions": round(-deductions, 2),
            },
        ))
    else:
        methods.append(_method_entry("epv", "Earnings Power Value (EPV)", "weighted", 3, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="Résultat opérationnel normalisé négatif ou absent"))

    # 6. Value Driver Formula McKinsey (poids: 2)
    if latest_cn is not None and latest_cn > 0 and croic_5y is not None and croic_5y > 0 and reinvest_5y is not None:
        g1 = min(0.8 * wacc, croic_5y * reinvest_5y)
        if g1 < -0.03:
            methods.append(_method_entry(
                "value_driver", "Value Driver (McKinsey)", "weighted", 2,
                unclestock_val=None, corrected_val=None, current_price=current_price,
                status_unclestock="excluded", status_corrected="excluded",
                exclusion_reason=f"g1 = {g1 * 100:.2f}% < -3% (exclu par la règle McKinsey/Uncle Stock)",
            ))
        else:
            if g1 <= 0.0:
                g_vd = 0.0
            elif g1 <= 0.05:
                g_vd = g1
            else:
                g_vd = max(0.05, 0.5 * (g1 + 0.04))
            g_vd = min(g_vd, wacc * 0.85)  # assure WACC - g > 0
            denom = wacc - g_vd
            if denom > 0.002 and (1.0 - g_vd / croic_5y) > 0:
                v_firm_vd = (latest_cn * (1.0 + g_vd) * (1.0 - g_vd / croic_5y)) / denom
                iv_vd_lit = v_firm_vd / shares_latest
                iv_vd_corr = (v_firm_vd - deductions) / shares_latest
                st_c = "valid" if iv_vd_corr > 0 else "excluded"
                methods.append(_method_entry(
                    "value_driver",
                    "Value Driver (McKinsey)",
                    "weighted",
                    2,
                    unclestock_val=iv_vd_lit,
                    corrected_val=iv_vd_corr if iv_vd_corr > 0 else None,
                    current_price=current_price,
                    status_corrected=st_c,
                    warnings=["La formule brute valorise l'entreprise (EV) ; le mode corrigé retranche dette nette, minoritaires et préférentielles."],
                    exclusion_reason="Valeur des fonds propres négative après déduction de dette nette" if st_c == "excluded" else None,
                    assumptions=[
                        f"Cash-NOPAT = {latest_cn / 1e6:,.1f} M · CROIC 5A = {croic_5y * 100:.1f}% · RR 5A = {reinvest_5y * 100:.1f}%",
                        f"g1 = {g1 * 100:.2f}% → g retenu = {g_vd * 100:.2f}% · WACC = {wacc * 100:.2f}%",
                    ],
                    intermediates={
                        "enterprise_value_vd": round(v_firm_vd, 2),
                        "reinvestment_factor": round(1.0 - g_vd / croic_5y, 4),
                        "g1_pct": round(g1 * 100.0, 2),
                        "g_used_pct": round(g_vd * 100.0, 2),
                    },
                ))
            else:
                methods.append(_method_entry("value_driver", "Value Driver (McKinsey)", "weighted", 2, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="WACC - g ou taux de réinvestissement non exploitable"))
    else:
        methods.append(_method_entry("value_driver", "Value Driver (McKinsey)", "weighted", 2, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="unavailable", status_corrected="unavailable", exclusion_reason="Cash-NOPAT, CROIC ou taux de réinvestissement 5A manquant"))

    # 7. Intrinsic Value (Lynch) (poids: 2)
    if latest_eps is not None and latest_eps > 0 and g_ebitda is not None and g_ebitda > 0:
        g_l = min(0.35, g_ebitda)  # Garde-fou anti-outlier en mode corrigé (et cap rCAGR 30% en brut)
        iv_lynch_lit = latest_eps * (g_ebitda * 100.0)
        iv_lynch_corr = latest_eps * (min(0.25, g_l) * 100.0)
        w_l = ["Croissance EBITDA élevée : plafonnée à 25% en mode corrigé (PER max 25x)"] if g_ebitda > 0.25 else []
        methods.append(_method_entry(
            "lynch",
            "Intrinsic Value (Lynch)",
            "weighted",
            2,
            unclestock_val=iv_lynch_lit,
            corrected_val=iv_lynch_corr,
            current_price=current_price,
            warnings=w_l,
            assumptions=[
                f"EPS = {latest_eps:.2f} · EBITDA rCAGR = {g_ebitda * 100:.2f}%",
                "Règle Lynch : juste PER = taux de croissance en %",
            ],
            intermediates={"eps": round(latest_eps, 2), "ebitda_rcagr_pct": round(g_ebitda * 100.0, 2)},
        ))
    else:
        methods.append(_method_entry("lynch", "Intrinsic Value (Lynch)", "weighted", 2, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="EPS ou croissance EBITDA négative/indisponible"))

    # 8. Graham Number (poids: 2)
    if latest_eps is not None and latest_eps > 0 and latest_tcbv_ps is not None and latest_tcbv_ps > 0:
        iv_gn = math.sqrt(22.5 * latest_eps * latest_tcbv_ps)
        methods.append(_method_entry(
            "graham_number",
            "Graham Number",
            "weighted",
            2,
            unclestock_val=iv_gn,
            corrected_val=iv_gn,
            current_price=current_price,
            assumptions=[
                f"EPS = {latest_eps:.2f} · Common Tangible BVPS = {latest_tcbv_ps:.2f}",
                "Formule : sqrt(22,5 × EPS × TBVPS)",
            ],
            intermediates={"eps": round(latest_eps, 2), "tbvps": round(latest_tcbv_ps, 2)},
        ))
    else:
        methods.append(_method_entry("graham_number", "Graham Number", "weighted", 2, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="EPS ou actif net tangible négatif (racine carrée impossible)"))

    # 9. EBITDA 7.5x (poids: 2)
    if latest_ebitda is not None and latest_ebitda > 0:
        ev_eb = 7.5 * latest_ebitda
        eq_eb = ev_eb - deductions
        iv_eb = eq_eb / shares_latest
        st_c = "valid" if iv_eb > 0 else "excluded"
        methods.append(_method_entry(
            "ebitda_7_5x",
            "Intrinsic Value (7,5× EBITDA)",
            "weighted",
            2,
            unclestock_val=iv_eb,
            corrected_val=iv_eb if iv_eb > 0 else None,
            current_price=current_price,
            status_corrected=st_c,
            exclusion_reason="Valeur des fonds propres négative à 7,5× EBITDA" if st_c == "excluded" else None,
            assumptions=[f"EBITDA = {latest_ebitda / 1e6:,.1f} M · Multiple fixe EV/EBITDA = 7,5×"],
            intermediates={"enterprise_value_7_5x": round(ev_eb, 2), "deductions": round(-deductions, 2), "equity_value": round(eq_eb, 2)},
        ))
    else:
        methods.append(_method_entry("ebitda_7_5x", "Intrinsic Value (7,5× EBITDA)", "weighted", 2, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="EBITDA négatif ou indisponible"))

    # 10. Hold 5 Years (poids: 1)
    oe_ps = (latest_oe / shares_latest) if (latest_oe is not None and shares_latest > 0) else None
    g_h5 = g_oe if g_oe is not None else (g_fcff if g_fcff is not None else 0.03)
    # Rendement moyen 5A d'OE sur le prix (via cours de clôture de fin d'année ou cours actuel en repli)
    oe_yields_5y: list[float] = []
    year_close: dict[str, float] = {}
    for b in bars or []:
        ds = str(b.get("date") or "")[:10]
        cv = _num(b.get("adjusted_close") or b.get("close"))
        if len(ds) >= 4 and cv and cv > 0:
            year_close[ds[:4]] = cv
    for i in range(max(0, n_periods - 5), n_periods):
        sh_i = shares_v[i] or dil_shares_v[i] or shares_latest
        yr_i = dates[i][:4]
        px_i = year_close.get(yr_i) or current_price
        if oe_v[i] is not None and oe_v[i] > 0 and sh_i > 0 and px_i and px_i > 0:
            oe_yields_5y.append((oe_v[i] / sh_i) / px_i)
    avg_oe_yield = (sum(oe_yields_5y) / len(oe_yields_5y)) if oe_yields_5y else None
    payouts_5y = [
        min(1.0, abs(div_paid_v[i]) / oe_v[i])
        for i in range(max(0, n_periods - 5), n_periods)
        if div_paid_v[i] is not None and oe_v[i] is not None and oe_v[i] > 0
    ]
    avg_oe_payout = (sum(payouts_5y) / len(payouts_5y)) if payouts_5y else 0.0
    if oe_ps is not None and oe_ps > 0 and avg_oe_yield and avg_oe_yield > 0.005:
        oe5 = oe_ps * ((1.0 + g_h5) ** 5)
        p5 = oe5 / avg_oe_yield
        pv_p5 = p5 / ((1.0 + ke_capm) ** 5)
        pv_dist = sum(
            ((oe_ps * ((1.0 + g_h5) ** t) * avg_oe_payout) / ((1.0 + ke_capm) ** t))
            for t in range(1, 6)
        )
        iv_h5 = pv_p5 + pv_dist
        methods.append(_method_entry(
            "hold_5y",
            "Intrinsic Value (Hold 5 Years)",
            "weighted",
            1,
            unclestock_val=iv_h5,
            corrected_val=iv_h5,
            current_price=current_price,
            assumptions=[
                f"OE₀/act. = {oe_ps:.2f} · g(OE) = {g_h5 * 100:.2f}%",
                f"Rendement moyen OE 5A = {avg_oe_yield * 100:.2f}% · Payout moyen = {avg_oe_payout * 100:.1f}%",
            ],
            intermediates={"predicted_price_y5": round(p5, 2), "pv_resale_y5": round(pv_p5, 2), "pv_5y_payouts": round(pv_dist, 2)},
        ))
    else:
        methods.append(_method_entry("hold_5y", "Intrinsic Value (Hold 5 Years)", "weighted", 1, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="Owner Earnings ou rendement OE moyen sur 5A insuffisant"))

    # 11. DCF FCF No Growth (poids: 1)
    if latest_fcff is not None and latest_fcff > 0:
        ev_ng = latest_fcff / wacc
        eq_ng = ev_ng - deductions
        iv_ng = eq_ng / shares_latest
        st_c = "valid" if iv_ng > 0 else "excluded"
        methods.append(_method_entry(
            "dcf_fcf_no_growth",
            "DCF FCF (No Growth)",
            "weighted",
            1,
            unclestock_val=iv_ng,
            corrected_val=iv_ng if iv_ng > 0 else None,
            current_price=current_price,
            status_corrected=st_c,
            exclusion_reason="Valeur des fonds propres négative sans croissance" if st_c == "excluded" else None,
            assumptions=[f"FCFF₀ = {latest_fcff / 1e6:,.1f} M · WACC = {wacc * 100:.2f}% · Croissance = 0%"],
            intermediates={"enterprise_value": round(ev_ng, 2), "equity_value": round(eq_ng, 2)},
        ))
    else:
        methods.append(_method_entry("dcf_fcf_no_growth", "DCF FCF (No Growth)", "weighted", 1, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="FCFF négatif ou indisponible"))

    # 12. Adjusted Lynch (poids: 1)
    if latest_eps is not None and latest_eps > 0 and g_ebitda is not None and g_ebitda > 0:
        fair_peg_lit = min(3.0, 0.5 * ((10.0 * g_ebitda - 1.5) ** 2) + 1.98)
        iv_lynch_base = latest_eps * (g_ebitda * 100.0)
        iv_adj_lynch_lit = fair_peg_lit * iv_lynch_base
        g_lc = min(0.25, g_ebitda)
        fair_peg_c = min(3.0, 0.5 * ((10.0 * g_lc - 1.5) ** 2) + 1.98)
        iv_adj_lynch_c = fair_peg_c * (latest_eps * (g_lc * 100.0))
        methods.append(_method_entry(
            "adjusted_lynch",
            "Adjusted Intrinsic Value (Lynch)",
            "weighted",
            1,
            unclestock_val=iv_adj_lynch_lit,
            corrected_val=iv_adj_lynch_c,
            current_price=current_price,
            assumptions=[f"fairPEG(g) = {fair_peg_lit:.2f} (plafonné à 3,0) × Lynch"],
            intermediates={"fair_peg": round(fair_peg_lit, 3)},
        ))
    else:
        methods.append(_method_entry("adjusted_lynch", "Adjusted Intrinsic Value (Lynch)", "weighted", 1, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="EPS ou croissance EBITDA négative/indisponible"))

    # 13. Prix actuel (poids: 1 — uniquement en mode Uncle Stock, exclu en mode indépendant)
    methods.append(_method_entry(
        "current_price",
        "Cours actuel (référence marché)",
        "weighted",
        1,
        unclestock_val=current_price,
        corrected_val=None,
        current_price=current_price,
        status_unclestock="valid" if (current_price and current_price > 0) else "unavailable",
        status_corrected="excluded",
        exclusion_reason="Exclu du mode indépendant pour éviter d'ancrer la valeur intrinsèque sur le prix de marché",
    ))

    # =========================================================================
    # MÉTHODES COMPLÉMENTAIRES (hors moyenne des 13 composantes)
    # =========================================================================

    # C1. DCF Owner Earnings (levered at Ke)
    if latest_oe is not None and latest_oe > 0:
        g_doe = g_oe if g_oe is not None else (g_fcff if g_fcff is not None else 0.03)
        res_oe = _pv_5y_plus_perpetuity(latest_oe, g_doe, ke_capm)
        if res_oe:
            eq_oe, pv5_oe, pvt_oe = res_oe
            methods.append(_method_entry(
                "dcf_oe", "DCF Owner Earnings (OE)", "complementary", 0,
                unclestock_val=eq_oe / shares_latest,
                corrected_val=eq_oe / shares_latest,
                current_price=current_price,
                assumptions=[f"OE₀ = {latest_oe / 1e6:,.1f} M · g(OE) = {g_doe * 100:.2f}% · Ke = {ke_capm * 100:.2f}%"],
                intermediates={"pv_5y_oe": round(pv5_oe, 2), "pv_terminal_oe": round(pvt_oe, 2), "equity_value": round(eq_oe, 2)},
            ))
    else:
        methods.append(_method_entry("dcf_oe", "DCF Owner Earnings (OE)", "complementary", 0, unclestock_val=None, corrected_val=None, current_price=current_price, status_unclestock="excluded", status_corrected="excluded", exclusion_reason="Owner Earnings négatifs ou indisponibles"))

    # C2, C3, C4. DCF OE Linéaire (10A), Quadratique (full history), Régression (min)
    r_reg = rf_30y + 0.05
    oe_pts = [(float(int(d[:4]) - 1900), v) for d, v in zip(dates, oe_v) if v is not None]
    last_year = int(dates[-1][:4]) if dates else 2025
    iv_lin_ps: float | None = None
    iv_quad_ps: float | None = None

    if len(oe_pts) >= 3:
        pts_10y = oe_pts[-10:]
        ols_l = _ols_linear([p[0] for p in pts_10y], [p[1] for p in pts_10y])
        if ols_l:
            slp, icp, _ = ols_l
            pv_lin = sum(
                (slp * ((last_year + t) - 1900) + icp) / ((1.0 + r_reg) ** t)
                for t in range(1, 101)
            )
            iv_lin_ps = pv_lin / shares_latest
            methods.append(_method_entry(
                "dcf_oe_linear", "DCF OE Linéaire (100 ans)", "complementary", 0,
                unclestock_val=iv_lin_ps,
                corrected_val=iv_lin_ps if iv_lin_ps > 0 else None,
                current_price=current_price,
                status_corrected="valid" if iv_lin_ps > 0 else "excluded",
                assumptions=[f"Régression linéaire sur {len(pts_10y)} ans · Taux r = Rf30Y + 5% = {r_reg * 100:.2f}%"],
                intermediates={"slope": round(slp, 2), "intercept": round(icp, 2), "equity_value": round(pv_lin, 2)},
            ))

    if len(oe_pts) >= 4:
        ols_q = _ols_quadratic([p[0] for p in oe_pts], [p[1] for p in oe_pts])
        if ols_q:
            qa, qb, qc = ols_q
            pv_quad = sum(
                (qa * (((last_year + t) - 1900) ** 2) + qb * ((last_year + t) - 1900) + qc) / ((1.0 + r_reg) ** t)
                for t in range(1, 101)
            )
            iv_quad_ps = pv_quad / shares_latest
            methods.append(_method_entry(
                "dcf_oe_quadratic", "DCF OE Quadratique (100 ans)", "complementary", 0,
                unclestock_val=iv_quad_ps,
                corrected_val=iv_quad_ps if iv_quad_ps > 0 else None,
                current_price=current_price,
                status_corrected="valid" if iv_quad_ps > 0 else "excluded",
                warnings=["Extrapolation polynomiale sur 100 ans très sensible aux accélérations récentes."],
                assumptions=[f"Régression quadratique sur {len(oe_pts)} exercices · r = {r_reg * 100:.2f}%"],
                intermediates={"a": round(qa, 2), "b": round(qb, 2), "c": round(qc, 2), "equity_value": round(pv_quad, 2)},
            ))

    if iv_lin_ps is not None or iv_quad_ps is not None:
        candidates_reg = [v for v in (iv_lin_ps, iv_quad_ps) if v is not None]
        iv_reg = min(candidates_reg)
        methods.append(_method_entry(
            "dcf_oe_regression", "DCF OE Régression (min)", "complementary", 0,
            unclestock_val=iv_reg,
            corrected_val=iv_reg if iv_reg > 0 else None,
            current_price=current_price,
            status_corrected="valid" if iv_reg > 0 else "excluded",
            assumptions=["Minimum conservateur entre régression linéaire et quadratique"],
        ))

    # C5. O'Malley Formula : OE_pred * (15 + 10*g) * 4.4 / Y
    oe_pred_total: float | None = None
    if len(oe_pts) >= 4:
        ols_q = _ols_quadratic([p[0] for p in oe_pts], [p[1] for p in oe_pts])
        if ols_q:
            qa, qb, qc = ols_q
            nx = (last_year + 1) - 1900
            oe_pred_total = qa * (nx ** 2) + qb * nx + qc
    if oe_pred_total is None and latest_oe is not None:
        oe_pred_total = latest_oe * (1.0 + (g_oe or 0.03))
    if oe_pred_total is not None and oe_pred_total > 0 and g_oe is not None:
        oe_pred_ps = oe_pred_total / shares_latest
        iv_om = oe_pred_ps * (15.0 + 10.0 * max(-0.2, g_oe)) * (4.4 / bond_rate_pct)
        methods.append(_method_entry(
            "omalley", "O'Malley Formula", "complementary", 0,
            unclestock_val=iv_om,
            corrected_val=iv_om if iv_om > 0 else None,
            current_price=current_price,
            status_corrected="valid" if iv_om > 0 else "excluded",
            assumptions=[f"OE prédictif/act. = {oe_pred_ps:.2f} · g(OE) = {g_oe * 100:.2f}% · Y = {bond_rate_pct:.2f}%"],
        ))

    # C6. x Years Payback (+ Payback en années pour récupérer MarketCap - CBV)
    oiai_pts = [(float(int(d[:4]) - 1900), v) for d, v in zip(dates, adj_oiai_v) if v is not None]
    estimated_payback_years: float | None = None
    if len(oiai_pts) >= 3 and latest_cbv is not None:
        oiai_10y = oiai_pts[-10:]
        ols_pb = _ols_linear([p[0] for p in oiai_10y], [p[1] for p in oiai_10y])
        if ols_pb:
            slp_pb, icp_pb, _ = ols_pb
            fut_after_tax = sum(
                (slp_pb * ((last_year + t) - 1900) + icp_pb) * (1.0 - marginal_tax)
                for t in range(1, max(1, payback_years) + 1)
            )
            eq_pb = latest_cbv + fut_after_tax
            iv_pb = eq_pb / shares_latest
            methods.append(_method_entry(
                "payback_x_years", f"Payback {payback_years} ans (sans actualisation)", "complementary", 0,
                unclestock_val=iv_pb,
                corrected_val=iv_pb if iv_pb > 0 else None,
                current_price=current_price,
                status_corrected="valid" if iv_pb > 0 else "excluded",
                warnings=["Formule sans actualisation des bénéfices futurs (indicateur de récupération)."],
                assumptions=[f"CBV + {payback_years} ans d'Adjusted OIAI × (1 - {marginal_tax * 100:.0f}%)"],
                intermediates={"cbv": round(latest_cbv, 2), "projected_oiai_after_tax": round(fut_after_tax, 2)},
            ))
            # Payback en années pour récupérer MarketCap - CBV
            target_gap = market_cap - latest_cbv
            if target_gap <= 0:
                estimated_payback_years = 0.0
            else:
                cum = 0.0
                for yr_idx in range(1, 51):
                    yr_profit = (slp_pb * ((last_year + yr_idx) - 1900) + icp_pb) * (1.0 - marginal_tax)
                    if yr_profit <= 0:
                        break
                    if cum + yr_profit >= target_gap:
                        frac = (target_gap - cum) / yr_profit
                        estimated_payback_years = round((yr_idx - 1) + frac, 1)
                        break
                    cum += yr_profit

    # =========================================================================
    # AGRÉGATION DOUBLE (Mode Uncle Stock vs Mode Indépendant Corrigé)
    # =========================================================================
    def _aggregate(mode: str) -> dict[str, Any] | None:
        num_sum = 0.0
        den_sum = 0
        used_count = 0
        for m in methods:
            if m["category"] != "weighted" or m["weight"] <= 0:
                continue
            st = m[f"status_{mode}"]
            val = m[f"{mode}_value"]
            if st == "valid" and val is not None and val > 0:
                num_sum += m["weight"] * val
                den_sum += m["weight"]
                used_count += 1
        if den_sum <= 0:
            return None
        iv_global = num_sum / den_sum
        p_to_iv = (current_price / iv_global) if (current_price and iv_global > 0) else None
        mos = ((1.0 - p_to_iv) * 100.0) if p_to_iv is not None else None
        return {
            "intrinsic_value": round(iv_global, 2),
            "price_to_iv": round(p_to_iv, 3) if p_to_iv is not None else None,
            "margin_of_safety_pct": round(mos, 1) if mos is not None else None,
            "weight_used": den_sum,
            "weight_max": 30 if mode == "unclestock" else 29,
            "methods_used": used_count,
            "methods_total": 13 if mode == "unclestock" else 12,
        }

    # Buffett IRR & Forward Rate of Return (Donald Yacktman)
    buffett_irr = (
        _solve_buffett_irr(current_price, latest_div_ps, g_div, latest_cbv_ps, g_cbv or 0.04)
        if (current_price and latest_cbv_ps and latest_cbv_ps > 0)
        else None
    )
    fcf_yield_on_price = (
        ((latest_fcf / shares_latest) / current_price)
        if (latest_fcf is not None and current_price and current_price > 0)
        else None
    )
    ebitda_6y_cagr, _ = compute_rcagr_67(ebitda_v, max_years=6)
    forward_ror = (
        round((fcf_yield_on_price + (ebitda_6y_cagr or 0.0) + inflation) * 100.0, 2)
        if fcf_yield_on_price is not None
        else None
    )

    # Scénarios & sensibilité sur DCF FCF si FCFF positif
    scenarios: list[dict[str, Any]] = []
    sensitivity: dict[str, Any] | None = None
    if latest_fcff is not None and latest_fcff > 0:
        scenarios, sensitivity = _compute_dcf_sensitivity_and_scenarios(
            latest_fcff, g_dcf_fcf, wacc, deductions, shares_latest, current_price
        )

    return {
        "available": True,
        "currency": cur_upper,
        "country_iso3": iso_upper,
        "current_price": round(current_price, 2) if current_price is not None else None,
        "shares": round(shares_latest, 0),
        "cost_of_capital": {
            "risk_free_rate_pct": round(rf_curr * 100.0, 2),
            "risk_free_30y_pct": round(rf_30y * 100.0, 2),
            "corporate_bond_20y_pct": round(bond_rate_pct, 2),
            "erp_pct": round(_ERP_DAMODARAN * 100.0, 2),
            "marginal_tax_rate_pct": round(marginal_tax * 100.0, 1),
            "beta_raw": round(beta, 2) if beta is not None else None,
            "beta_clamped": round(beta_clamped, 2) if beta_clamped is not None else None,
            "cost_of_equity_capm_pct": round(ke_capm * 100.0, 2),
            "cost_of_equity_ddm_pct": round(ke_ddm * 100.0, 2),
            "financial_health_score_0_4": fh_score,
            "after_tax_cost_of_debt_pct": round(kd_after_tax * 100.0, 2),
            "equity_financing_pct": round(eq_ratio * 100.0, 1),
            "debt_financing_pct": round(debt_ratio * 100.0, 1),
            "wacc_raw_pct": round(wacc_raw * 100.0, 2),
            "wacc_floor_pct": round(wacc_floor * 100.0, 2),
            "wacc_pct": round(wacc * 100.0, 2),
            "equity_charge_total": round(equity_charge_total, 2) if equity_charge_total is not None else None,
            "equity_charge_ps": round(equity_charge_ps, 2) if equity_charge_ps is not None else None,
        },
        "growth_inputs": {
            "fcff_rcagr_67_pct": round(g_fcff * 100.0, 2) if g_fcff is not None else None,
            "fcff_rcagr_raw_pct": round(g_fcff_raw * 100.0, 2) if g_fcff_raw is not None else None,
            "oe_rcagr_67_pct": round(g_oe * 100.0, 2) if g_oe is not None else None,
            "ebitda_rcagr_67_pct": round(g_ebitda * 100.0, 2) if g_ebitda is not None else None,
            "eps_rcagr_67_pct": round(g_eps * 100.0, 2) if g_eps is not None else None,
            "cbv_rcagr_67_pct": round(g_cbv * 100.0, 2) if g_cbv is not None else None,
            "div_rcagr_67_pct": round(g_div * 100.0, 2) if g_div is not None else None,
        },
        "owner_returns": {
            "total_owner_return_pct": total_owner_return_pct,
            "net_owner_return_pct": net_owner_return_pct,
            "buffett_rate_of_return_pct": round(buffett_irr * 100.0, 2) if buffett_irr is not None else None,
            "forward_rate_of_return_pct": forward_ror,
            "payback_years_market": estimated_payback_years,
        },
        "summary": {
            "unclestock": _aggregate("unclestock"),
            "corrected": _aggregate("corrected"),
        },
        "methods": methods,
        "scenarios": scenarios,
        "sensitivity": sensitivity,
    }
