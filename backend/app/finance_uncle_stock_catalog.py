"""Catalogue complet et moteur d'évaluation du référentiel Uncle Stock (508 métriques).

Charge la définition canonique des 508 indicateurs et sous-métriques depuis
`backend/app/data/uncle_stock_reference.json` et calcule, pour le titre étudié,
chaque valeur calculable sans jamais remplacer une donnée absente par zéro.
"""

from __future__ import annotations

import functools
import json
import math
import statistics
from pathlib import Path
from typing import Any

from .finance_intrinsic import _ols_linear, _ols_quadratic, compute_rcagr_67

_REFERENCE_JSON_PATH = Path(__file__).resolve().parent / "uncle_stock_reference.json"

_DEFAULT_METHOD = (
    "Appliquer les opérations dans l’ordre de la formule source, en utilisant des données homogènes "
    "(période, devise, unité et signe)."
)
_DEFAULT_NOTES = "Vérifier la période et le signe des postes ; ne pas remplacer une donnée absente par zéro."


@functools.lru_cache(maxsize=1)
def load_uncle_stock_reference() -> list[dict[str, Any]]:
    """Charge en mémoire la table de référence des 508 métriques Uncle Stock."""
    if not _REFERENCE_JSON_PATH.exists():
        return []
    raw = json.loads(_REFERENCE_JSON_PATH.read_text(encoding="utf-8"))
    return raw if isinstance(raw, list) else []


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        out = float(val)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    out = a / b
    return out if math.isfinite(out) else None


def _pick(*vals: float | None) -> float | None:
    for v in vals:
        if v is not None:
            return v
    return None


def _last(vec: list[float | None]) -> float | None:
    for v in reversed(vec):
        if v is not None:
            return v
    return None


def _yr_avg(vec: list[float | None], idx: int) -> float | None:
    cur = vec[idx] if 0 <= idx < len(vec) else None
    if cur is None:
        return None
    prev = vec[idx - 1] if idx > 0 else None
    return (cur + prev) / 2.0 if prev is not None else cur


def _avg_last(vec: list[float | None], k: int | None = None) -> float | None:
    src = vec if k is None else vec[-k:]
    pts = [v for v in src if v is not None]
    return (sum(pts) / len(pts)) if pts else None


def _wavg_last(vec: list[float | None], k: int = 5) -> float | None:
    pts = [v for v in vec[-k:] if v is not None]
    if not pts:
        return None
    w = list(range(1, len(pts) + 1))
    return sum(v * wi for v, wi in zip(pts, w)) / sum(w)


def _cagr(vec: list[float | None], k: int) -> float | None:
    pts = [v for v in vec if v is not None]
    if len(pts) < 2:
        return None
    step = min(k, len(pts) - 1)
    v0, v1 = pts[-1 - step], pts[-1]
    if v0 <= 0 or v1 <= 0 or step <= 0:
        return None
    return (v1 / v0) ** (1.0 / step) - 1.0


def _yoy_growth(vec: list[float | None]) -> float | None:
    pts = [v for v in vec if v is not None]
    if len(pts) < 2 or pts[-2] == 0:
        return None
    return (pts[-1] - pts[-2]) / abs(pts[-2])


def _sd_last(vec: list[float | None], k: int = 5) -> float | None:
    pts = [v for v in vec[-k:] if v is not None]
    return statistics.stdev(pts) if len(pts) >= 2 else None


def _cv_last(vec: list[float | None], k: int = 5) -> float | None:
    pts = [v for v in vec[-k:] if v is not None]
    if len(pts) < 2:
        return None
    mean = sum(pts) / len(pts)
    if mean == 0:
        return None
    return statistics.stdev(pts) / abs(mean)


def _r2(vec: list[float | None]) -> float | None:
    pts = [(float(i), v) for i, v in enumerate(vec) if v is not None]
    if len(pts) < 3:
        return None
    ols = _ols_linear([p[0] for p in pts], [p[1] for p in pts])
    if not ols:
        return None
    slp, icp, _ = ols
    ys = [p[1] for p in pts]
    my = sum(ys) / len(ys)
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot <= 0:
        return 1.0
    ss_res = sum((y - (slp * x + icp)) ** 2 for x, y in pts)
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _diff_series(vec: list[float | None]) -> list[float | None]:
    out: list[float | None] = [None]
    for i in range(1, len(vec)):
        if vec[i] is not None and vec[i - 1] is not None:
            out.append(vec[i] - vec[i - 1])
        else:
            out.append(None)
    return out


def _fmt_num_fr(val: float, digits: int = 2) -> str:
    txt = f"{val:,.{digits}f}".replace(",", "\u202f")
    return txt


def _fmt_value(val: float | None, unit: str, currency: str) -> str:
    if val is None or not math.isfinite(val):
        return "—"
    if unit == "pct":
        return f"{val * 100.0:.2f}%"
    if unit == "pct_already":
        return f"{val:.2f}%"
    if unit == "ratio":
        return f"{val:.2f}×"
    if unit == "currency":
        if abs(val) >= 1e9:
            return f"{_fmt_num_fr(val / 1e9, 2)} Md {currency}"
        if abs(val) >= 1e6:
            return f"{_fmt_num_fr(val / 1e6, 1)} M {currency}"
        return f"{_fmt_num_fr(val, 2)} {currency}"
    if unit == "per_share":
        return f"{val:.2f} {currency}"
    if unit == "days":
        return f"{round(val)} j"
    if unit == "months":
        return f"{val:.1f} mois"
    if unit == "int":
        return f"{round(val):,}".replace(",", "\u202f")
    if unit == "bool":
        return "Oui (1)" if val >= 0.5 else "Non (0)"
    return f"{val:.3f}"


def _build_submetrics(vec: list[float | None], unit: str, currency: str) -> dict[str, str | None] | None:
    valid = [v for v in vec if v is not None]
    if not valid:
        return None
    yr_avg_v = _yr_avg(vec, len(vec) - 1)
    avg5_v = _avg_last(vec, 5)
    wavg5_v = _wavg_last(vec, 5)
    g1y_v = _yoy_growth(vec)
    rcagr67_v, _ = compute_rcagr_67(vec)
    sd5_v = _sd_last(vec, 5)
    cv5_v = _cv_last(vec, 5)
    return {
        "yr_avg": _fmt_value(yr_avg_v, unit, currency) if yr_avg_v is not None else None,
        "avg_5y": _fmt_value(avg5_v, unit, currency) if avg5_v is not None else None,
        "wavg_5y": _fmt_value(wavg5_v, unit, currency) if wavg5_v is not None else None,
        "growth_1y": f"{g1y_v * 100.0:+.1f}%" if g1y_v is not None else None,
        "rcagr_67": f"{rcagr67_v * 100.0:+.1f}%" if rcagr67_v is not None else None,
        "sd_5y": _fmt_value(sd5_v, unit, currency) if sd5_v is not None else None,
        "cv_5y": f"{cv5_v:.2f}" if cv5_v is not None else None,
    }


def _pct_dec(val: Any) -> float | None:
    v = _num(val)
    if v is None:
        return None
    return v / 100.0 if abs(v) > 2.5 else v


def _pad_series(ann_series: dict[str, dict[str, float | None]], dates: list[str], *keys: str) -> list[float | None]:
    out: list[float | None] = []
    for d in dates:
        v: float | None = None
        for k in keys:
            raw = (ann_series.get(k) or {}).get(d)
            v = _num(raw)
            if v is not None:
                break
        out.append(v)
    return out


def _sum_optional(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def _compute_balance_pack(
    ann_series: dict[str, dict[str, float | None]],
    dates: list[str],
    pref_override: float | None,
    nci_override: float | None,
) -> dict[str, list[float | None]]:
    """Construit toutes les séries du bilan (101 postes Uncle Stock)."""
    n = len(dates)
    p = lambda *keys: _pad_series(ann_series, dates, *keys)  # noqa: E731

    cash_eq = p("CashAndCashEquivalents")
    st_inv = p("eod_balance_shortTermInvestments")
    cash_st = p("CashCashEquivalentsAndShortTermInvestments")
    ar = p("AccountsReceivable")
    inv = p("Inventory")
    other_ca = p("eod_balance_otherCurrentAssets")
    ca = p("CurrentAssets")
    gross_ppe = p("eod_balance_propertyPlantEquipment")
    acc_dep = p("eod_balance_accumulatedDepreciation", "eod_balance_accumulatedAmortization")
    net_ppe = p("NetPPE")
    gw = p("eod_balance_goodWill")
    intang = p("eod_balance_intangibleAssets")
    gw_int = p("GoodwillAndIntangibleAssets")
    lt_inv = p("eod_balance_longTermInvestments")
    dta = p("eod_balance_deferredLongTermAssetCharges")
    other_nca = p("eod_balance_otherNonCurrAssets", "eod_balance_otherAssets")
    nca_raw = p("eod_balance_nonCurrentAssetsTotal")
    earning_assets = p("eod_balance_earningAssets")
    assets = p("TotalAssets")
    ap = p("AccountsPayable")
    def_rev_cur = p("CurrentDeferredRevenue")
    other_cl = p("eod_balance_otherCurrentLiab")
    notes_st = p("eod_balance_shortLongTermDebt")
    st_debt_raw = p("ShortTermDebt", "CurrentDebt")
    st_lease = p("eod_balance_capitalLeaseObligationsCurrent")
    cl = p("CurrentLiabilities")
    lt_debt_raw = p("LongTermDebt", "eod_balance_longTermDebtTotal")
    lt_lease = p("eod_balance_capitalLeaseObligations")
    def_rev_nc = p("NonCurrentDeferredRevenue")
    dtl_nc = p("eod_balance_deferredLongTermLiab")
    other_ncl = p("eod_balance_otherNonCurrLiab", "eod_balance_nonCurrentLiabilitiesOther", "eod_balance_otherLiab")
    ncl_raw = p("eod_balance_nonCurrentLiabilitiesTotal")
    tot_debt_raw = p("TotalDebt")
    tot_liab_raw = p("TotalLiabilitiesNetMinorityInterest")
    common_st = p("eod_balance_commonStock")
    pref_st = p("eod_balance_preferredStockTotalEquity", "eod_balance_preferredStockRedeemable")
    ret_earn = p("RetainedEarnings")
    treasury_st = p("eod_balance_treasuryStock")
    aoci = p("eod_balance_otherStockholderEquity")
    nci_bal = p("eod_balance_noncontrollingInterestInConsolidatedEntity", "eod_balance_minorityInterest")
    eq_sh = p("StockholdersEquity")
    tbv_raw = p("eod_balance_netTangibleAssets")
    net_debt_raw = p("NetDebt")
    wc_raw = p("WorkingCapital")
    rev = p("TotalRevenue")

    # Séries dérivées passe 1 (nécessaires avant Excess Cash'')
    cash_and_st_l: list[float | None] = []
    st_inv_l: list[float | None] = []
    cash_eq_l: list[float | None] = []
    non_cash_ca_l: list[float | None] = []
    tot_rec_l: list[float | None] = []
    gross_ppe_l: list[float | None] = []
    net_ppe_l: list[float | None] = []
    gw_int_l: list[float | None] = []
    nca_l: list[float | None] = []
    non_cash_a_l: list[float | None] = []
    soft_a_l: list[float | None] = []
    inv_tot_l: list[float | None] = []
    asset_qual_l: list[float | None] = []
    other_ca_rev_l: list[float | None] = []
    st_debt_l: list[float | None] = []
    st_debt_lease_l: list[float | None] = []
    lt_debt_lease_l: list[float | None] = []
    tot_debt_l: list[float | None] = []
    tot_debt_lease_l: list[float | None] = []
    ext_debt_l: list[float | None] = []
    nibcl_l: list[float | None] = []
    ncl_l: list[float | None] = []
    tot_liab_l: list[float | None] = []
    def_rev_tot_l: list[float | None] = []
    dtl_tot_l: list[float | None] = []
    adj_liab_l: list[float | None] = []
    net_liab_l: list[float | None] = []
    op_liab_l: list[float | None] = []
    excess_cash_l: list[float | None] = []
    excess_cash_p_l: list[float | None] = []
    cash_to_a_ratio_l: list[float | None] = []
    nwc_l: list[float | None] = []
    ncwc_l: list[float | None] = []
    eq_tot_l: list[float | None] = []
    sh_eq_l: list[float | None] = []
    nci_l: list[float | None] = []
    sh_eq_treas_l: list[float | None] = []
    share_cap_l: list[float | None] = []
    core_cap_l: list[float | None] = []
    tang_a_l: list[float | None] = []
    cbv_l: list[float | None] = []
    tbv_l: list[float | None] = []
    ptbv_l: list[float | None] = []
    ctbv_l: list[float | None] = []
    gw_to_eq_l: list[float | None] = []
    cap_emp_l: list[float | None] = []
    ce_gb_l: list[float | None] = []
    gross_inv_l: list[float | None] = []
    net_nc_oa_l: list[float | None] = []
    noa_l: list[float | None] = []
    noa_p_l: list[float | None] = []
    inv_cap_l: list[float | None] = []
    net_worth_l: list[float | None] = []
    net_debt_p_l: list[float | None] = []
    nnwc_l: list[float | None] = []
    ncav_l: list[float | None] = []
    net_cash_l: list[float | None] = []
    net_fin_a_l: list[float | None] = []
    cash_rev_adj_l: list[float | None] = []

    for i in range(n):
        c_eq = cash_eq[i]
        c_st = cash_st[i] if cash_st[i] is not None else c_eq
        si_v = st_inv[i]
        if si_v is None and c_st is not None and c_eq is not None and c_st >= c_eq:
            si_v = c_st - c_eq
        cash_eq_l.append(c_eq if c_eq is not None else c_st)
        st_inv_l.append(si_v)
        cash_and_st_l.append(c_st)

        ncca = (ca[i] - c_st) if (ca[i] is not None and c_st is not None) else None
        non_cash_ca_l.append(ncca)
        tot_rec_l.append(ar[i])
        other_ca_rev_l.append(_div(other_ca[i], rev[i]) if (rev[i] and rev[i] > 0) else None)

        n_ppe = net_ppe[i]
        g_ppe = gross_ppe[i]
        if g_ppe is None and n_ppe is not None and acc_dep[i] is not None:
            g_ppe = n_ppe + abs(acc_dep[i])
        gross_ppe_l.append(g_ppe)
        net_ppe_l.append(n_ppe)

        gi = gw_int[i] if gw_int[i] is not None else _sum_optional(gw[i], intang[i])
        gw_int_l.append(gi)

        nca = nca_raw[i] if nca_raw[i] is not None else (
            (assets[i] - ca[i]) if (assets[i] is not None and ca[i] is not None) else None
        )
        nca_l.append(nca)

        nca_cash = (assets[i] - (cash_eq_l[-1] or 0.0)) if (assets[i] is not None and cash_eq_l[-1] is not None) else None
        non_cash_a_l.append(nca_cash)
        soft_a_l.append((nca_cash - n_ppe) if (nca_cash is not None and n_ppe is not None) else None)
        inv_tot_l.append(_sum_optional(si_v, lt_inv[i]))
        asset_qual_l.append(_div((nca - n_ppe) if (nca is not None and n_ppe is not None) else None, assets[i]))

        st_d = _pick(st_debt_raw[i], notes_st[i])
        st_debt_l.append(st_d)
        st_dl = _sum_optional(st_d, st_lease[i])
        st_debt_lease_l.append(st_dl)

        lt_d = lt_debt_raw[i]
        lt_dl = _sum_optional(lt_d, lt_lease[i])
        lt_debt_lease_l.append(lt_dl)

        td = tot_debt_raw[i] if tot_debt_raw[i] is not None else _sum_optional(st_d, lt_d)
        tot_debt_l.append(td)
        tdl = _sum_optional(st_dl, lt_dl) if (st_dl is not None or lt_dl is not None) else td
        tot_debt_lease_l.append(tdl)

        pref_i = pref_st[i] if pref_st[i] is not None else (pref_override if (i == n - 1 and pref_override is not None) else None)
        ext_d = (tdl + max(0.0, pref_i or 0.0)) if tdl is not None else None
        ext_debt_l.append(ext_d)

        nib = (cl[i] - (st_dl or 0.0)) if cl[i] is not None else None
        nibcl_l.append(nib)

        ncl = ncl_raw[i] if ncl_raw[i] is not None else (
            (tot_liab_raw[i] - cl[i]) if (tot_liab_raw[i] is not None and cl[i] is not None) else None
        )
        ncl_l.append(ncl)

        tl = tot_liab_raw[i] if tot_liab_raw[i] is not None else (
            (cl[i] + ncl) if (cl[i] is not None and ncl is not None) else None
        )
        tot_liab_l.append(tl)

        dr_tot = _sum_optional(def_rev_cur[i], def_rev_nc[i])
        def_rev_tot_l.append(dr_tot)
        dtl_tot_l.append(dtl_nc[i])
        adj_liab_l.append((tl - (dr_tot or 0.0) - (dtl_nc[i] or 0.0)) if tl is not None else None)
        net_liab_l.append((tl - c_st) if (tl is not None and c_st is not None) else None)
        op_liab_l.append((tl - (tdl or 0.0)) if tl is not None else None)

        exc = (c_st - max(0.0, nib - ncca)) if (c_st is not None and nib is not None and ncca is not None) else None
        exc_p = (c_st - max(0.0, cl[i] - ncca)) if (c_st is not None and cl[i] is not None and ncca is not None) else None
        excess_cash_l.append(max(0.0, exc) if exc is not None else None)
        excess_cash_p_l.append(max(0.0, exc_p) if exc_p is not None else None)
        cash_to_a_ratio_l.append(_div(c_st, assets[i]))

        nwc = wc_raw[i] if wc_raw[i] is not None else ((ca[i] - cl[i]) if (ca[i] is not None and cl[i] is not None) else None)
        nwc_l.append(nwc)
        ncwc = (ncca - nib) if (ncca is not None and nib is not None) else None
        ncwc_l.append(ncwc)

        sh_eq = eq_sh[i]
        sh_eq_l.append(sh_eq)
        nci_v = nci_bal[i] if nci_bal[i] is not None else (nci_override if (i == n - 1 and nci_override is not None) else None)
        nci_l.append(nci_v)
        eq_tot = (sh_eq + (nci_v or 0.0)) if sh_eq is not None else (
            (assets[i] - tl) if (assets[i] is not None and tl is not None) else None
        )
        eq_tot_l.append(eq_tot)

        sh_eq_treas_l.append((sh_eq - (treasury_st[i] or 0.0)) if (sh_eq is not None and treasury_st[i] is not None) else sh_eq)
        share_cap_l.append(_sum_optional(common_st[i], pref_st[i]))
        if common_st[i] is not None or ret_earn[i] is not None or aoci[i] is not None:
            core_cap_l.append((common_st[i] or 0.0) + (ret_earn[i] or 0.0) + (aoci[i] or 0.0))
        else:
            core_cap_l.append(sh_eq)

        ta = (assets[i] - (gi or 0.0)) if assets[i] is not None else None
        tang_a_l.append(ta)

        cbv = (sh_eq - max(0.0, pref_i or 0.0)) if sh_eq is not None else None
        cbv_l.append(cbv)
        tbv = tbv_raw[i] if tbv_raw[i] is not None else ((sh_eq - (gi or 0.0)) if sh_eq is not None else None)
        tbv_l.append(tbv)
        ptbv_l.append(_div(ta * sh_eq if (ta is not None and sh_eq is not None) else None, assets[i]))
        ctbv_l.append((tbv - max(0.0, pref_i or 0.0)) if tbv is not None else None)
        gw_to_eq_l.append((gw[i] + eq_tot) if (gw[i] is not None and eq_tot is not None) else None)

        cap_emp_l.append((assets[i] - cl[i]) if (assets[i] is not None and cl[i] is not None) else None)
        ce_gb_l.append((max(0.0, ncwc) + n_ppe) if (ncwc is not None and n_ppe is not None) else None)
        gross_inv_l.append((max(0.0, ncwc) + g_ppe + (lt_lease[i] or 0.0)) if (ncwc is not None and g_ppe is not None) else None)

        if nca is not None and ncl is not None:
            net_nc_oa_l.append(nca - (lt_inv[i] or 0.0) - (ncl - (lt_dl or 0.0)))
        else:
            net_nc_oa_l.append(None)
        noa_l.append((ncwc + net_nc_oa_l[-1]) if (ncwc is not None and net_nc_oa_l[-1] is not None) else None)

        nd_p = net_debt_raw[i] if net_debt_raw[i] is not None else (
            (tdl - c_st) if (tdl is not None and c_st is not None) else None
        )
        net_debt_p_l.append(nd_p)
        noa_p_l.append((eq_tot + nd_p - (lt_inv[i] or 0.0)) if (eq_tot is not None and nd_p is not None) else None)

        inv_cap_v = (assets[i] - nib - (excess_cash_p_l[-1] or 0.0)) if (assets[i] is not None and nib is not None) else None
        inv_cap_l.append(inv_cap_v)
        if inv_cap_v is not None and tdl is not None:
            net_worth_l.append(inv_cap_v + (excess_cash_p_l[-1] or 0.0) - tdl - max(0.0, pref_i or 0.0))
        else:
            net_worth_l.append(cbv)

        if cash_eq_l[-1] is not None and ar[i] is not None and inv[i] is not None and tl is not None:
            nnwc_l.append(cash_eq_l[-1] + 0.75 * ar[i] + 0.50 * inv[i] - tl)
        else:
            nnwc_l.append(None)
        ncav_l.append((ca[i] - tl) if (ca[i] is not None and tl is not None) else None)
        net_cash_l.append((c_st - (lt_dl or 0.0)) if (c_st is not None and lt_dl is not None) else None)
        net_fin_a_l.append(((inv_tot_l[-1] or 0.0) - ext_d) if (inv_tot_l[-1] is not None or ext_d is not None) and ext_d is not None else None)
        cash_rev_adj_l.append((ar[i] - (dr_tot or 0.0)) if ar[i] is not None else None)

    # Pass 2 : Excess Cash'', Net debt, Operational Invested Capital, RSST Acruals
    valid_cta = [v for v in cash_to_a_ratio_l if v is not None]
    med_cta = statistics.median(valid_cta) if valid_cta else None
    excess_cash_pp_l: list[float | None] = []
    net_debt_l: list[float | None] = []
    op_inv_cap_l: list[float | None] = []
    for i in range(n):
        c_st = cash_and_st_l[i]
        if c_st is not None and assets[i] is not None and med_cta is not None and nwc_l[i] is not None and ncwc_l[i] is not None:
            wc_diff_term = c_st - (nwc_l[i] - ncwc_l[i])
            req_cash = 0.5 * (med_cta * assets[i] + wc_diff_term)
            exc_pp = max(0.0, c_st - max(0.0, req_cash))
        else:
            exc_pp = excess_cash_p_l[i]
        excess_cash_pp_l.append(exc_pp)
        nd = (tot_debt_lease_l[i] - exc_pp) if (tot_debt_lease_l[i] is not None and exc_pp is not None) else net_debt_p_l[i]
        net_debt_l.append(nd)
        if eq_tot_l[i] is not None and nd is not None:
            op_inv_cap_l.append(eq_tot_l[i] + nd - (lt_inv[i] or 0.0) - (dta[i] or 0.0))
        else:
            op_inv_cap_l.append(None)

    noa_p_diff = _diff_series(noa_p_l)
    net_fin_diff = _diff_series(net_fin_a_l)
    rsst_acc_l = [
        (noa_p_diff[i] + net_fin_diff[i]) if (noa_p_diff[i] is not None and net_fin_diff[i] is not None) else noa_p_diff[i]
        for i in range(n)
    ]

    return {
        "Total cash and equivalents": cash_eq_l,
        "Short term investments": st_inv_l,
        "Cash and short term investments": cash_and_st_l,
        "Non-cash current assets": non_cash_ca_l,
        "Accounts receivable": ar,
        "Total receivables": tot_rec_l,
        "Inventory": inv,
        "Other Current Assets": other_ca,
        "Other Current Assets/ Revenue": other_ca_rev_l,
        "Current assets": ca,
        "Gross Property, Plant and Equipment": gross_ppe_l,
        "Accumulated depreciation": acc_dep,
        "Net Property, Plant and Equipment": net_ppe_l,
        "Goodwill": gw,
        "Intangible assets": intang,
        "Goodwill & Intangibles": gw_int_l,
        "Long-term Investments": lt_inv,
        "Deferred Tax Asset": dta,
        "Other long-term Assets": other_nca,
        "Non-current Assets": nca_l,
        "Earning Assets": earning_assets,
        "Non-cash Assets": non_cash_a_l,
        "Soft Assets": soft_a_l,
        "Investments": inv_tot_l,
        "Total Assets": assets,
        "Asset quality": asset_qual_l,
        "Accounts Payable": ap,
        "Deferred revenue, Current": def_rev_cur,
        "Other Current Liabilities": other_cl,
        "Non-Interest-Bearing Current Liabilities (NIBCL)": nibcl_l,
        "Notes payable/ Short-term debt": notes_st,
        "Short-term debt": st_debt_l,
        "Short-term Lease": st_lease,
        "Short-term Debt and lease obligations": st_debt_lease_l,
        "Current Liabilities": cl,
        "Long-term Debt": lt_debt_raw,
        "Long-term Lease": lt_lease,
        "Long-term Debt and lease obligations": lt_debt_lease_l,
        "Deferred revenue, Non-current": def_rev_nc,
        "Deferred Tax Liabilities, Non-current": dtl_nc,
        "Other long-term Liabilities": other_ncl,
        "Non-current Liabilities": ncl_l,
        "Total Debt": tot_debt_l,
        "Total Debt and Lease": tot_debt_lease_l,
        "Extended Debt": ext_debt_l,
        "Deferred revenue": def_rev_tot_l,
        "Deferred Tax Liabilities": dtl_tot_l,
        "Total Liabilities": tot_liab_l,
        "Adjusted Total Liabilities": adj_liab_l,
        "Net Liabilities": net_liab_l,
        "Total Operating Liabilities": op_liab_l,
        "Excess Cash": excess_cash_l,
        "Excess Cash'": excess_cash_p_l,
        "Excess Cash''": excess_cash_pp_l,
        "Net debt": net_debt_l,
        "Net debt'": net_debt_p_l,
        "Cash revenue adjustment": cash_rev_adj_l,
        "Common stock": common_st,
        "Preferred stock": pref_st,
        "Share capital": share_cap_l,
        "Retained earnings": ret_earn,
        "Treasury Stock": treasury_st,
        "Accumulated other comprehensive income": aoci,
        "Core Capital": core_cap_l,
        "Tangible Assets": tang_a_l,
        "Shareholders' Equity": sh_eq_l,
        "Shareholders' Equity and Treasury Stock": sh_eq_treas_l,
        "Non-Controlling Interest": nci_l,
        "Equity": eq_tot_l,
        "Goodwill to Equity": gw_to_eq_l,
        "Common Book Value": cbv_l,
        "Proportional Tangible Book Value": ptbv_l,
        "Tangible Book Value": tbv_l,
        "Common Tangible Book Value": ctbv_l,
        "Capital Employed": cap_emp_l,
        "Capital Employed (Greenblatt)": ce_gb_l,
        "Gross Investment": gross_inv_l,
        "Net Non-current Operating Assets": net_nc_oa_l,
        "Net Operating Assets": noa_l,
        "Net Operating Assets'": noa_p_l,
        "Operational Invested Capital": op_inv_cap_l,
        "Invested Capital": inv_cap_l,
        "Net Worth": net_worth_l,
        "NNWC": nnwc_l,
        "NCAV": ncav_l,
        "Net cash": net_cash_l,
        "Net Working Capital": nwc_l,
        "Non-cash working capital": ncwc_l,
        "Net Financial Assets": net_fin_a_l,
        "RSST Acruals": rsst_acc_l,
    }


def _compute_income_cashflow_pack(
    ann_series: dict[str, dict[str, float | None]],
    dates: list[str],
    bal: dict[str, list[float | None]],
    shares_v: list[float | None],
    wacc: float | None,
    ke_capm: float | None,
    marginal_tax: float,
) -> tuple[dict[str, list[float | None]], dict[str, list[float | None]]]:
    """Construit les séries Compte de résultat (70) et Cash-flow (57) Uncle Stock."""
    n = len(dates)
    p = lambda *keys: _pad_series(ann_series, dates, *keys)  # noqa: E731

    int_inc = p("eod_income_interestIncome")
    net_int_inc_raw = p("eod_income_netInterestIncome")
    rev = p("TotalRevenue")
    cost_rev = p("CostOfRevenue")
    gp_raw = p("GrossProfit")
    rnd = p("ResearchAndDevelopment")
    sga = p("SellingGeneralAndAdministration")
    opex_raw = p("OperatingExpense", "eod_income_operatingExpenses")
    opinc_raw = p("OperatingIncome")
    ebitda_raw = p("EBITDA")
    ebit_raw = p("EBIT")
    other_inc = p("eod_income_totalOtherIncomeExpenseNet", "eod_income_nonOperatingIncomeNetOther")
    int_exp = p("InterestExpense")
    pretax = p("PretaxIncome")
    tax_exp = p("TaxProvision")
    ni_cont = p("eod_income_netIncomeFromContinuingOps", "NetIncome")
    ni_disc = p("eod_income_discontinuedOperations")
    nci_inc = p("eod_income_minorityInterest")
    ni_raw = p("NetIncome")
    eps_raw = p("DilutedEPS", "BasicEPS")
    unusual_raw = p("eod_income_nonRecurring", "eod_income_extraordinaryItems")

    da_cf = p("DepreciationAndAmortization")
    amort_raw = p("eod_income_reconciledDepreciation")
    sbc = p("StockBasedCompensation")
    def_tax_cf = p("eod_cashflow_deferredTaxes")
    non_cash_other = p("eod_cashflow_otherNonCashItems")
    dwc = p("ChangeInWorkingCapital")
    d_ar = p("eod_cashflow_changeToAccountReceivables")
    d_inv = p("eod_cashflow_changeToInventory")
    d_ap = p("eod_cashflow_changeToLiabilities")
    d_other_wc = p("eod_cashflow_changeToOperatingActivities")
    cfi = p("InvestingCashFlow")
    other_cfi = p("eod_cashflow_otherCashflowsFromInvestingActivities")
    debt_iss = p("eod_cashflow_longTermDebtIssuance")
    debt_rep = p("eod_cashflow_debtRepayment", "eod_cashflow_longTermDebtPayments")
    net_borrow_raw = p("IssuanceOfDebt")
    stock_iss = p("eod_cashflow_netIssuanceOfCommonStock", "eod_cashflow_saleOfStock")
    stock_rep = p("RepurchaseOfCapitalStock")
    div_paid = p("CashDividendsPaid")
    other_cff = p("eod_cashflow_otherCashflowsFromFinancingActivities")
    cff = p("FinancingCashFlow")
    cfo = p("OperatingCashFlow")
    capex_raw = p("CapitalExpenditure")
    fcf_raw = p("FreeCashFlow")
    net_chg_cash = p("eod_cashflow_changeInCash")

    # Series Compte de résultat
    gp_l: list[float | None] = []
    opex_l: list[float | None] = []
    tot_opex_l: list[float | None] = []
    opinc_l: list[float | None] = []
    adj_oi_l: list[float | None] = []
    ebit_l: list[float | None] = []
    ebitda_l: list[float | None] = []
    ebita_l: list[float | None] = []
    oi_ai_l: list[float | None] = []
    adj_oiai_l: list[float | None] = []
    tax_r_l: list[float | None] = []
    nopat_l: list[float | None] = []
    rnd_amort_l: list[float | None] = []
    adj_nopat_l: list[float | None] = []
    adj_earn_l: list[float | None] = []
    consol_inc_l: list[float | None] = []
    ni_l: list[float | None] = []
    eps_l: list[float | None] = []
    div_ps_l: list[float | None] = []
    chg_re_l: list[float | None] = []
    ri_l: list[float | None] = []
    eva_l: list[float | None] = []
    billings_l: list[float | None] = []
    net_int_inc_l: list[float | None] = []

    def_rev_diff = _diff_series(bal["Deferred revenue"])
    ar_diff = _diff_series(bal["Accounts receivable"])
    assets_l = bal["Total Assets"]

    # R&D Amortization (amortissement linéaire 5 ans à 20% par an sur la fenêtre R&D)
    for i in range(n):
        win = [abs(rnd[j]) for j in range(max(0, i - 4), i + 1) if rnd[j] is not None]
        rnd_amort_l.append((sum(win) / len(win)) if win else None)

    for i in range(n):
        r_i = rev[i]
        c_abs = abs(cost_rev[i]) if cost_rev[i] is not None else None
        gp_i = gp_raw[i] if gp_raw[i] is not None else ((r_i - c_abs) if (r_i is not None and c_abs is not None) else None)
        gp_l.append(gp_i)

        oi_i = opinc_raw[i] if opinc_raw[i] is not None else ebit_raw[i]
        opinc_l.append(oi_i)
        eb_i = ebit_raw[i] if ebit_raw[i] is not None else oi_i
        ebit_l.append(eb_i)

        if opex_raw[i] is not None:
            if gp_i is not None and opex_raw[i] > gp_i and c_abs is not None:
                opex_i = max(0.0, opex_raw[i] - c_abs)
            else:
                opex_i = abs(opex_raw[i])
        elif gp_i is not None and oi_i is not None:
            opex_i = max(0.0, gp_i - oi_i)
        else:
            opex_i = None
        opex_l.append(opex_i)
        tot_opex_l.append((opex_i + c_abs) if (opex_i is not None and c_abs is not None) else opex_raw[i])

        da_abs = abs(da_cf[i]) if da_cf[i] is not None else None
        if gp_i is not None and sga[i] is not None and opex_i is not None:
            sga_da = abs(sga[i]) + (da_abs or 0.0)
            adj_oi_i = gp_i - min(sga_da, opex_i)
        else:
            adj_oi_i = oi_i
        adj_oi_l.append(adj_oi_i)

        ebitda_i = ebitda_raw[i] if ebitda_raw[i] is not None else ((eb_i + da_abs) if (eb_i is not None and da_abs is not None) else None)
        ebitda_l.append(ebitda_i)
        ebita_l.append(ebitda_i)  # Approximation lorsque la part d'amortissement incorporel isolée est absente

        ie_abs = abs(int_exp[i]) if int_exp[i] is not None else None
        oi_ai_l.append((oi_i - (ie_abs or 0.0)) if oi_i is not None else None)
        adj_oiai_l.append((adj_oi_i - (ie_abs or 0.0)) if adj_oi_i is not None else None)

        if tax_exp[i] is not None and pretax[i] is not None and pretax[i] > 0:
            tr: float | None = max(0.0, min(0.50, tax_exp[i] / pretax[i]))
        else:
            tr = None
        tax_r_l.append(tr)
        eff_tr = tr if tr is not None else marginal_tax
        nopat_i = (oi_i * (1.0 - eff_tr)) if oi_i is not None else None
        nopat_l.append(nopat_i)
        adj_nopat_l.append((nopat_i + (rnd_amort_l[i] or 0.0)) if nopat_i is not None else None)

        ci_i = ni_cont[i] if ni_cont[i] is not None else ni_raw[i]
        consol = (ci_i + (ni_disc[i] or 0.0)) if ci_i is not None else ni_raw[i]
        consol_inc_l.append(consol)
        ni_i = ni_raw[i] if ni_raw[i] is not None else ((consol - (nci_inc[i] or 0.0)) if consol is not None else None)
        ni_l.append(ni_i)
        adj_earn_l.append((ci_i + (rnd_amort_l[i] or 0.0)) if ci_i is not None else None)

        sh = shares_v[i]
        eps_i = eps_raw[i] if eps_raw[i] is not None else (_div(ni_i, sh) if (ni_i is not None and sh and sh > 0) else None)
        eps_l.append(eps_i)
        div_abs = abs(div_paid[i]) if div_paid[i] is not None else None
        div_ps_i = _div(div_abs, sh) if (div_abs is not None and sh and sh > 0) else None
        div_ps_l.append(div_ps_i)
        chg_re_l.append((eps_i - div_ps_i) if (eps_i is not None and div_ps_i is not None) else None)

        cbv_i = bal["Common Book Value"][i]
        eq_chg_ps = (ke_capm * (cbv_i / sh)) if (ke_capm is not None and cbv_i is not None and sh and sh > 0) else None
        ri_l.append((eps_i - eq_chg_ps) if (eps_i is not None and eq_chg_ps is not None) else None)

        ce_i = bal["Capital Employed"][i]
        eva_l.append((nopat_i - ce_i * wacc) if (nopat_i is not None and ce_i is not None and wacc is not None) else None)
        billings_l.append((r_i + (def_rev_diff[i] or 0.0)) if (r_i is not None and def_rev_diff[i] is not None) else r_i)
        net_int_inc_l.append(
            net_int_inc_raw[i]
            if net_int_inc_raw[i] is not None
            else ((int_inc[i] - (ie_abs or 0.0)) if int_inc[i] is not None else None)
        )

    # Normalised Operating Income = Revenue × Adjusted Operating Margin.10y avg
    adj_op_m_l = [_div(adj_oi_l[i], rev[i]) if (rev[i] and rev[i] > 0) else None for i in range(n)]
    adj_m_10y = _avg_last(adj_op_m_l, 10)
    ebit_m_l = [_div(ebit_l[i], rev[i]) if (rev[i] and rev[i] > 0) else None for i in range(n)]
    ebit_m_3y = _avg_last(ebit_m_l, 3)

    norm_oi_l = [(rev[i] * adj_m_10y) if (rev[i] is not None and adj_m_10y is not None) else opinc_l[i] for i in range(n)]
    norm_oi_at_l = [(norm_oi_l[i] * (1.0 - (tax_r_l[i] if tax_r_l[i] is not None else marginal_tax))) if norm_oi_l[i] is not None else None for i in range(n)]
    norm_ebit_l = [(rev[i] * ebit_m_3y) if (rev[i] is not None and ebit_m_3y is not None) else ebit_l[i] for i in range(n)]
    adj_ebit_l = [
        (norm_ebit_l[i] + 0.25 * abs(rnd[i] or 0.0) + 0.25 * abs(sga[i] or 0.0))
        if norm_ebit_l[i] is not None
        else None
        for i in range(n)
    ]
    adj_inc_at_l = [(adj_ebit_l[i] * (1.0 - (tax_r_l[i] if tax_r_l[i] is not None else marginal_tax))) if adj_ebit_l[i] is not None else None for i in range(n)]

    # Series Cash-Flow
    capex_abs_l = [abs(capex_raw[i]) if capex_raw[i] is not None else None for i in range(n)]
    fcf_l: list[float | None] = []
    fcff_l: list[float | None] = []
    adj_fcff_l: list[float | None] = []
    fcfe_l: list[float | None] = []
    net_borrow_l: list[float | None] = []
    stock_iss_net_l: list[float | None] = []
    maint_dep_l: list[float | None] = []
    growth_capex_l: list[float | None] = []
    lt_reinv_l: list[float | None] = []
    burn_rate_l: list[float | None] = []
    oe_p_l: list[float | None] = []
    oe_l: list[float | None] = []
    oe_pp_l: list[float | None] = []
    adj_oe_l: list[float | None] = []
    firm_e_l: list[float | None] = []
    firm_e_p_l: list[float | None] = []
    cash_nopat_l: list[float | None] = []
    cfat_l: list[float | None] = []
    adj_cfo_l: list[float | None] = []
    ccfat_l: list[float | None] = []

    for i in range(n):
        f_i = fcf_raw[i]
        if f_i is None and cfo[i] is not None and capex_abs_l[i] is not None:
            f_i = cfo[i] - capex_abs_l[i]
        fcf_l.append(f_i)

        nb = net_borrow_raw[i] if net_borrow_raw[i] is not None else (
            (debt_iss[i] - abs(debt_rep[i])) if (debt_iss[i] is not None and debt_rep[i] is not None) else None
        )
        net_borrow_l.append(nb)

        si_n = (stock_iss[i] or 0.0) - abs(stock_rep[i] or 0.0) if (stock_iss[i] is not None or stock_rep[i] is not None) else None
        stock_iss_net_l.append(si_n)

        ie_abs = abs(int_exp[i]) if int_exp[i] is not None else 0.0
        tr = tax_r_l[i] if tax_r_l[i] is not None else marginal_tax
        fcff_i = (f_i + ie_abs * (1.0 - tr)) if f_i is not None else None
        fcff_l.append(fcff_i)
        adj_fcff_l.append((fcff_i + (rnd_amort_l[i] or 0.0)) if fcff_i is not None else None)
        fcfe_l.append((f_i + (nb or 0.0)) if f_i is not None else None)

        da_abs = abs(da_cf[i]) if da_cf[i] is not None else None
        maint_dep_l.append(da_abs)
        growth_capex_l.append((capex_abs_l[i] - da_abs) if (capex_abs_l[i] is not None and da_abs is not None) else None)

        if rnd[i] is not None or capex_abs_l[i] is not None:
            lt_reinv_l.append(abs(rnd[i] or 0.0) + (capex_abs_l[i] or 0.0))
        else:
            lt_reinv_l.append(None)

        burn_rate_l.append(max(0.0, -net_chg_cash[i] / 12.0) if net_chg_cash[i] is not None else None)

        nci_v = nci_inc[i] or 0.0
        sbc_abs = abs(sbc[i]) if sbc[i] is not None else 0.0
        if cfo[i] is not None and da_abs is not None:
            oep = cfo[i] - nci_v - da_abs
            oe = cfo[i] - sbc_abs - nci_v - da_abs
        elif f_i is not None:
            oep = f_i - nci_v
            oe = f_i - sbc_abs - nci_v
        else:
            oep = None
            oe = None
        oe_p_l.append(oep)
        oe_l.append(oe)
        adj_oe_l.append((oep + (rnd_amort_l[i] or 0.0)) if oep is not None else None)

        if ni_l[i] is not None and da_abs is not None:
            oepp = ni_l[i] + da_abs + (def_tax_cf[i] or 0.0) + (non_cash_other[i] or 0.0) + (dwc[i] or 0.0) - da_abs
        else:
            oepp = oep
        oe_pp_l.append(oepp)

        fe = (oe + nci_v + ie_abs * (1.0 - tr)) if oe is not None else None
        fep = (oep + nci_v + ie_abs * (1.0 - tr)) if oep is not None else None
        firm_e_l.append(fe)
        firm_e_p_l.append(fep)
        cash_nopat_l.append((fep - (dwc[i] or 0.0)) if fep is not None else ((cfo[i] + ie_abs * (1.0 - tr)) if cfo[i] is not None else None))

        cfat_l.append((nopat_l[i] + (da_abs or 0.0) + (non_cash_other[i] or 0.0)) if nopat_l[i] is not None else None)
        adj_cfo_l.append((cfo[i] - sbc_abs) if cfo[i] is not None else None)
        ccfat_l.append((ni_l[i] + (da_abs or 0.0)) if ni_l[i] is not None else None)

    # Normalised Owner Earnings = Revenue × Owner Earnings margin.6y avg
    oe_margin_l = [_div(oe_p_l[i], rev[i]) if (rev[i] and rev[i] > 0) else None for i in range(n)]
    oe_m_6y = _avg_last(oe_margin_l, 6)
    norm_oe_l = [(rev[i] * oe_m_6y) if (rev[i] is not None and oe_m_6y is not None) else oe_p_l[i] for i in range(n)]

    # Predictive Owner Earnings via quadratic regression over OE
    pred_oe: float | None = None
    oe_pts = [(float(int(dates[i][:4]) - 1900), oe_l[i]) for i in range(n) if oe_l[i] is not None and len(dates[i]) >= 4]
    if len(oe_pts) >= 4:
        qfit = _ols_quadratic([p_x[0] for p_x in oe_pts], [p_x[1] for p_x in oe_pts])
        if qfit:
            qa, qb, qc = qfit
            nx = (int(dates[-1][:4]) + 1) - 1900
            pred_oe = qa * (nx ** 2) + qb * nx + qc
    pred_oe_l = [None] * max(0, n - 1) + ([pred_oe] if n > 0 else [])

    # Quality of earnings
    cash_sales_l = [(rev[i] - (ar_diff[i] or 0.0)) if (rev[i] is not None and ar_diff[i] is not None) else rev[i] for i in range(n)]
    bill_to_rev_l = [_div(billings_l[i], rev[i]) for i in range(n)]
    days_def_rev_l = [
        (_yr_avg(bal["Deferred revenue, Current"], i) / rev[i] * 365.0)
        if (_yr_avg(bal["Deferred revenue, Current"], i) is not None and rev[i] and rev[i] > 0)
        else None
        for i in range(n)
    ]
    fcf_ebitda_l = [_div(fcff_l[i], ebitda_l[i]) for i in range(n)]
    cf_eps_l = [
        _div((oe_l[i] / shares_v[i]) if (oe_l[i] is not None and shares_v[i]) else None, eps_l[i])
        for i in range(n)
    ]
    ccr_l = [_div(cfo[i], ni_cont[i] if ni_cont[i] is not None else ni_l[i]) for i in range(n)]
    agg_acc_l = [
        ((ni_cont[i] or ni_l[i]) - (cfo[i] + cfi[i]))
        if ((ni_cont[i] is not None or ni_l[i] is not None) and cfo[i] is not None and cfi[i] is not None)
        else None
        for i in range(n)
    ]
    acc_assets_l = [
        _div((ni_cont[i] or ni_l[i]) - cfo[i], _yr_avg(assets_l, i))
        if ((ni_cont[i] is not None or ni_l[i] is not None) and cfo[i] is not None and _yr_avg(assets_l, i))
        else None
        for i in range(n)
    ]
    sloan_l = [
        _div(agg_acc_l[i], _yr_avg(assets_l, i)) if (agg_acc_l[i] is not None and _yr_avg(assets_l, i)) else acc_assets_l[i]
        for i in range(n)
    ]
    abs_sloan_l = [abs(v) if v is not None else None for v in sloan_l]
    noa_acc_l = [
        _div(bal["Net Operating Assets'"][i] - bal["Net Operating Assets'"][i - 1], _yr_avg(assets_l, i))
        if (i > 0 and bal["Net Operating Assets'"][i] is not None and bal["Net Operating Assets'"][i - 1] is not None and _yr_avg(assets_l, i))
        else None
        for i in range(n)
    ]
    rsst_acc_a_l = [
        _div(bal["RSST Acruals"][i], _yr_avg(assets_l, i)) if (bal["RSST Acruals"][i] is not None and _yr_avg(assets_l, i)) else None
        for i in range(n)
    ]
    soft_a_assets_l = [_div(bal["Soft Assets"][i], assets_l[i]) for i in range(n)]
    payout_l = [
        _div(div_ps_l[i], eps_l[i]) if (div_ps_l[i] is not None and eps_l[i] and eps_l[i] > 0)
        else _div(abs(div_paid[i]) if div_paid[i] is not None else None, ni_l[i])
        for i in range(n)
    ]
    owner_payout_l = [
        _div(abs(div_paid[i]) if div_paid[i] is not None else None, oe_p_l[i])
        if (oe_p_l[i] and oe_p_l[i] > 0)
        else None
        for i in range(n)
    ]

    # Dividend Cushion Ratio = (Net cash + 5y FCF est) / 5y Dividend Paid est
    div_cushion_l: list[float | None] = [None] * n
    if n > 0 and fcf_l[-1] is not None and div_paid[-1] is not None and abs(div_paid[-1]) > 0:
        div5 = abs(div_paid[-1]) * 5.0
        fcf5 = fcf_l[-1] * 5.0
        nc_v = bal["Net cash"][-1] or 0.0
        div_cushion_l[-1] = (nc_v + fcf5) / div5

    cf_earn_l = [
        _div((ccfat_l[i] / shares_v[i]) if (ccfat_l[i] is not None and shares_v[i]) else None, eps_l[i])
        for i in range(n)
    ]
    sbc_rev_l = [_div(abs(sbc[i]) if sbc[i] is not None else None, rev[i]) for i in range(n)]
    eva_diff_l = _diff_series(eva_l)

    inc_pack = {
        "Total Interest Income": int_inc,
        "Net Interest Income": net_int_inc_l,
        "Revenue": rev,
        "Billings": billings_l,
        "Cost of Revenue": [abs(v) if v is not None else None for v in cost_rev],
        "Gross profit": gp_l,
        "Research & Development": [abs(v) if v is not None else None for v in rnd],
        "Selling General & Administrative expenses": [abs(v) if v is not None else None for v in sga],
        "Operating Expenses (OpEx)": opex_l,
        "Unusual expense (income)": unusual_raw,
        "Total Operating Expenses": tot_opex_l,
        "Operating Income": opinc_l,
        "Normalised Operating Income": norm_oi_l,
        "Adjusted Operating Income": adj_oi_l,
        "EBITDA": ebitda_l,
        "EBITA": ebita_l,
        "Normalized EBIT": norm_ebit_l,
        "Adjusted EBIT": adj_ebit_l,
        "Other Income (Expenses), Net": other_inc,
        "Interest expense": [abs(v) if v is not None else None for v in int_exp],
        "Operating Income After Interest": oi_ai_l,
        "Adjusted Operating Income After Interest": adj_oiai_l,
        "Income before tax": pretax,
        "Income tax expense": tax_exp,
        "Tax rate": tax_r_l,
        "Adjusted Net Operating Profit After Tax (NOPAT)": adj_nopat_l,
        "Net Operating Profit After Tax (NOPAT)": nopat_l,
        "Normalised Operating Income after tax": norm_oi_at_l,
        "Adjusted income after tax": adj_inc_at_l,
        "Adjusted Earnings": adj_earn_l,
        "Net income from continuing operations (IAT)": ni_cont,
        "Net income from discontinuing operations": ni_disc,
        "Consolidated income": consol_inc_l,
        "Net income to non-controlling interests": nci_inc,
        "Net income": ni_l,
        "Earnings Per Share (EPS)": eps_l,
        "Residual Income": ri_l,
        "Traditional Gross Dividend": div_ps_l,
        "Net Dividend": div_ps_l,
        "Change to Retained Earnings": chg_re_l,
        "Cash Flow / Earnings": cf_earn_l,
        "Cash Flow based Aggregate Accruals": agg_acc_l,
        "Economic Value Added": eva_l,
        "EVA diff": eva_diff_l,
        "Cash Sales": cash_sales_l,
        "Cash revenue adjustment": bal["Cash revenue adjustment"],
        "Billings / Revenue": bill_to_rev_l,
        "Days Current Deferred Revenue": days_def_rev_l,
        "Free Cash Flow / EBITDA": fcf_ebitda_l,
        "CF / EPS": cf_eps_l,
        "Cash Conversion Ratio (CCR)": ccr_l,
        "Accruals to Total Assets": acc_assets_l,
        "Sloan ratio": sloan_l,
        "Absolute Sloan ratio": abs_sloan_l,
        "NOA Accruals to Total Assets": noa_acc_l,
        "RSST Accruals to Total Assets": rsst_acc_a_l,
        "Soft Assets to Total Assets": soft_a_assets_l,
        "Payout ratio": payout_l,
        "Owner Payout ratio": owner_payout_l,
        "Dividend Cushion ratio": div_cushion_l,
    }

    cf_pack = {
        "Depreciation": [abs(v) if v is not None else None for v in da_cf],
        "Amortization": [abs(v) if v is not None else None for v in amort_raw],
        "R&D Amortization": rnd_amort_l,
        "Depreciation and amortization": [abs(v) if v is not None else None for v in da_cf],
        "Stock based compensation": [abs(v) if v is not None else None for v in sbc],
        "Stock based compensation / Revenue": sbc_rev_l,
        "Change in Deferred income taxes": def_tax_cf,
        "Other non-cash items": non_cash_other,
        "Change in non-cash Working Capital": dwc,
        "Change in Accounts Receivable": d_ar,
        "Change in Inventory": d_inv,
        "Change in Accounts Payable": d_ap,
        "Change in Other Working Capital": d_other_wc,
        "Cash Flow from Investing": cfi,
        "Other Cash Flows from Investing": other_cfi,
        "Debt issued": debt_iss,
        "Debt repaid": [abs(v) if v is not None else None for v in debt_rep],
        "Net Borrowings": net_borrow_l,
        "Common stock issued": stock_iss,
        "Common stock repurchased": [abs(v) if v is not None else None for v in stock_rep],
        "Common stock issued (repurchased)": stock_iss_net_l,
        "Dividend Paid": [abs(v) if v is not None else None for v in div_paid],
        "Other Cash Flows from Financing": other_cff,
        "Cash Flow from Financing": cff,
        "Maintenance Capital Expenditures (Accounting Depreciation)": maint_dep_l,
        "Maintenance Capital Expenditures (mix)": maint_dep_l,
        "Growth Capital Expenditures": growth_capex_l,
        "Capital Expenditures (CapEx)": capex_abs_l,
        "Net Capital Expenditures": capex_abs_l,
        "Long-term Reinvestments": lt_reinv_l,
        "Net Change in Cash": net_chg_cash,
        "Burn rate": burn_rate_l,
        "Firm Earnings": firm_e_l,
        "Firm Earnings'": firm_e_p_l,
        "Cash-NOPAT": cash_nopat_l,
        "Adjusted Free Cash Flow to the Firm": adj_fcff_l,
        "Free Cash Flow to the Firm": fcff_l,
        "Cash Flow After Taxes (CFAT)": cfat_l,
        "Cash Flow from Operations": cfo,
        "Adjusted Cash Flow from Operations": adj_cfo_l,
        "Free Cash Flow to Equity": fcfe_l,
        "Free Cash Flow": fcf_l,
        "Common Cash Flow After Tax (CCFAT)": ccfat_l,
        "Adjusted Owner Earnings": adj_oe_l,
        "Normalised Owner Earnings": norm_oe_l,
        "Owner Earnings": oe_l,
        "Predictive Owner Earnings": pred_oe_l,
        "Owner Earnings'": oe_p_l,
        "Owner Earnings''": oe_pp_l,
    }
    return inc_pack, cf_pack


def _compute_technical_and_market(
    bars: list[dict[str, Any]] | None,
    cur_price: float | None,
    cap_val: dict[str, Any] | None,
    eod_fund: dict[str, Any] | None,
    intrinsic_val: dict[str, Any] | None,
    risk_payload: dict[str, Any] | None,
    perf_payload: dict[str, Any] | None,
    bal: dict[str, list[float | None]],
    inc: dict[str, list[float | None]],
    cf: dict[str, list[float | None]],
    shares_eff: float | None,
    macro_ctx: dict[str, Any] | None,
    stakeholders: dict[str, Any] | None,
) -> dict[str, tuple[float | None, str, str | None]]:
    """Calcule les 72 métriques de 'Marché et valorisation' (val, unit, substitution)."""
    out: dict[str, tuple[float | None, str, str | None]] = {}
    cv = cap_val or {}
    hl = (eod_fund or {}).get("Highlights") or {}
    sh_st = (eod_fund or {}).get("SharesStats") or {}
    coc = (intrinsic_val or {}).get("cost_of_capital") or {}
    owr = (intrinsic_val or {}).get("owner_returns") or {}
    iv_sum = (intrinsic_val or {}).get("summary") or {}
    methods = {m["id"]: m for m in ((intrinsic_val or {}).get("methods") or []) if isinstance(m, dict)}

    closes: list[float] = []
    vols: list[float] = []
    for b in bars or []:
        c = _num(b.get("adjusted_close") or b.get("close"))
        if c is not None and c > 0:
            closes.append(c)
        v = _num(b.get("volume"))
        if v is not None and v >= 0:
            vols.append(v)

    price = cur_price if (cur_price is not None and cur_price > 0) else (closes[-1] if closes else None)
    mma50 = _num(cv.get("mma50")) or ((sum(closes[-50:]) / 50.0) if len(closes) >= 50 else None)
    mma200 = _num(cv.get("mma200")) or ((sum(closes[-200:]) / 200.0) if len(closes) >= 200 else None)
    high_52w = _num(cv.get("high_52w")) or (max(closes[-252:]) if len(closes) >= 20 else None)
    low_52w = _num(cv.get("low_52w")) or (min(closes[-252:]) if len(closes) >= 20 else None)
    avg_vol = (sum(vols[-30:]) / len(vols[-30:])) if vols else None
    last_vol = vols[-1] if vols else None

    if price is not None:
        out["Price"] = (price, "per_share", None)
    if mma50 is not None:
        out["x Days Simple Moving Average"] = (mma50, "per_share", "MMA 50 séances")
    if price is not None and mma50 and mma50 > 0:
        out["Price vs ma"] = ((price - mma50) / mma50, "pct", f"({price:.2f} − {mma50:.2f}) / {mma50:.2f}")
    if len(closes) >= 60:
        ma50_prev10 = sum(closes[-60:-10]) / 50.0
        if mma50 is not None and ma50_prev10 > 0:
            out["Moving Average Slope"] = ((mma50 - ma50_prev10) / ma50_prev10, "pct", "Pente MMA50 sur 10 séances")
    if len(closes) >= 302:
        ma50_1y = sum(closes[-302:-252]) / 50.0
        if mma50 is not None and ma50_1y > 0:
            out["Moving Average Growth"] = ((mma50 - ma50_1y) / abs(ma50_1y), "pct", "Évolution MMA50 sur 1 an")
    if price is not None and high_52w and high_52w > 0:
        out["Price vs top"] = ((price - high_52w) / high_52w, "pct", f"({price:.2f} − {high_52w:.2f}) / {high_52w:.2f}")
    if mma50 is not None and mma200 is not None and mma200 > 0:
        out["Golden Cross"] = (1.0 if mma50 > mma200 else 0.0, "bool", f"MMA50={mma50:.2f} vs MMA200={mma200:.2f}")

    # RSI 14j
    if len(closes) >= 15:
        gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(len(closes) - 14, len(closes))]
        losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(len(closes) - 14, len(closes))]
        ag, al = sum(gains) / 14.0, sum(losses) / 14.0
        rsi = 100.0 if al == 0 else (100.0 - 100.0 / (1.0 + ag / al))
        out["Relative Strength Index"] = (rsi, "num", f"RSI 14 séances = {rsi:.1f}")

    # MACD normalisé (EMA12 - EMA26) / EMA26
    if len(closes) >= 26:
        ema12, ema26 = closes[0], closes[0]
        k12, k26 = 2.0 / 13.0, 2.0 / 27.0
        for c in closes[1:]:
            ema12 = c * k12 + ema12 * (1.0 - k12)
            ema26 = c * k26 + ema26 * (1.0 - k26)
        if ema26 > 0:
            out["Normalized MACD"] = ((ema12 - ema26) / ema26, "pct", "(EMA12 − EMA26) / EMA26")

    # Fractal Efficiency Ratio (Kaufman ER sur 20 séances)
    if len(closes) >= 22:
        net_ch = abs(closes[-1] - closes[-21])
        sum_ch = sum(abs(closes[i] - closes[i - 1]) for i in range(len(closes) - 20, len(closes)))
        if sum_ch > 0:
            out["Fractal Efficiency Ratio"] = (net_ch / sum_ch, "num", "20 séances")

    if len(closes) >= 22 and price is not None and closes[-22] > 0:
        stm = -((price / closes[-22]) - 1.0)
        out["Short term reversal"] = (stm, "pct", "−Performance 1 mois")
    if len(closes) >= 252 and price is not None:
        ma252 = sum(closes[-252:]) / 252.0
        if ma252 > 0:
            out["Long term reversal"] = ((price / ma252) - 1.0, "pct", "Écart vs MM252")

    perf_map = {h.get("key"): _num(h.get("pct")) for h in ((perf_payload or {}).get("horizons") or [])}
    if perf_map.get("1y") is not None:
        p1y = perf_map["1y"] / 100.0
        out["Price growth"] = (p1y, "pct", "Performance boursière 1 an ajustée")
        out["Annualized Total Return"] = (p1y, "pct", "Rendement total annualisé 1 an")

    risk_map = {m.get("key"): (m.get("values") or []) for m in ((risk_payload or {}).get("metrics") or [])}
    if risk_map.get("sharpe") and risk_map["sharpe"][0] is not None:
        out["Sharpe ratio"] = (risk_map["sharpe"][0], "num", "Horizon 1 an")
    if risk_map.get("sortino") and risk_map["sortino"][0] is not None:
        out["Sortino ratio"] = (risk_map["sortino"][0], "num", "Horizon 1 an")

    beta_v = _num(coc.get("beta_raw")) or _num(hl.get("Beta"))
    if beta_v is not None:
        out["Beta"] = (beta_v, "num", None)
    if last_vol is not None:
        out["Volume"] = (last_vol, "int", "Dernière séance")
    if avg_vol is not None and price is not None:
        out["Dollar volume"] = (avg_vol * price, "currency", f"Vol. moy. 30j × {price:.2f}")

    # Market Cap & Targets
    mcap = _num(cv.get("market_cap")) or _num(hl.get("MarketCapitalization")) or (
        (price * shares_eff) if (price and shares_eff) else None
    )
    analyst_target = _num(cv.get("target_price")) or _num((stakeholders or {}).get("analysts", {}).get("target_price"))
    iv_corr = _num((iv_sum.get("corrected") or {}).get("intrinsic_value"))
    iv_us = _num((iv_sum.get("unclestock") or {}).get("intrinsic_value"))
    us_target = iv_corr or iv_us
    if analyst_target is not None:
        out["Analyst Price target"] = (analyst_target, "per_share", None)
    if us_target is not None:
        out["Uncle Stock Price target"] = (us_target, "per_share", "Valeur intrinsèque synthétique")
    pt_vals = [v for v in (analyst_target, us_target) if v is not None]
    if pt_vals:
        out["Price target"] = (statistics.median(pt_vals), "per_share", None)

    tdl_last = _last(bal["Total Debt and Lease"])
    nd_last = _last(bal["Net debt"])
    nd_p_last = _last(bal["Net debt'"])
    pref_last = _last(bal["Preferred stock"]) or 0.0
    nci_last = _last(bal["Non-Controlling Interest"]) or 0.0
    if mcap is not None:
        out["Market cap"] = (mcap, "currency", None)
        if tdl_last is not None:
            out["Financing"] = (mcap + tdl_last, "currency", None)
        if nd_last is not None:
            out["Enterprise Value"] = (mcap + nd_last + max(0.0, pref_last) + max(0.0, nci_last), "currency", None)
        if nd_p_last is not None:
            out["Enterprise Value'"] = (mcap + nd_p_last + max(0.0, pref_last) + max(0.0, nci_last), "currency", None)

    # Intrinsic values & Cost of Capital
    if owr.get("total_owner_return_pct") is not None:
        out["Total Owner Return"] = (owr["total_owner_return_pct"] / 100.0, "pct", None)
    if owr.get("net_owner_return_pct") is not None:
        out["Net Owner Return"] = (owr["net_owner_return_pct"] / 100.0, "pct", None)
    if iv_corr is not None or iv_us is not None:
        out["Intrinsic value"] = (iv_corr or iv_us, "per_share", "Moyenne pondérée des méthodes valides")

    iv_name_map = {
        "dcf_fcf": "Intrinsic value (DCF FCF)",
        "dcf_oe": "Intrinsic value (DCF OE)",
        "dcf_oe_linear": "Intrinsic Value (DCF OE linear)",
        "dcf_oe_quadratic": "Intrinsic Value (DCF OE quadratic)",
        "payback_x_years": "Intrinsic Value x years payback",
        "dcf_oe_regression": "Intrinsic Value (DCF OE regression)",
        "dcf_fcf_no_growth": "Intrinsic value (DCF FCF) no growth",
        "buffett": "Intrinsic Value (Buffett)",
        "hold_5y": "Intrinsic Value (Hold 5 years)",
        "residual_income": "Intrinsic Value (Residual Income Model)",
        "lynch": "Intrinsic Value (Lynch)",
        "adjusted_lynch": "Adjusted Intrinsic Value (Lynch)",
        "graham_formula": "Intrinsic value (Graham formula)",
        "omalley": "Intrinsic Value (O'Malley formula)",
        "graham_number": "Graham number",
        "value_driver": "Intrinsic Value (Value Driver Formula)",
    }
    for mid, mname in iv_name_map.items():
        m_obj = methods.get(mid)
        if m_obj:
            v_m = _num(m_obj.get("corrected_value")) or _num(m_obj.get("unclestock_value"))
            if v_m is not None:
                out[mname] = (v_m, "per_share", "; ".join(m_obj.get("assumptions") or []) or None)

    epv_obj = methods.get("epv")
    if epv_obj:
        epv_firm = _num((epv_obj.get("intermediates") or {}).get("epv_firm_pretax"))
        epv_eq = _num(epv_obj.get("unclestock_value")) or _num(epv_obj.get("corrected_value"))
        if epv_firm is not None:
            out["Earnings Power Value"] = (epv_firm, "currency", None)
        if epv_eq is not None:
            out["Earnings Power Value of Equity"] = (epv_eq, "per_share", None)
    eb75 = methods.get("ebitda_7_5x")
    if eb75 and _num(eb75.get("corrected_value")) is not None:
        out["Intrinsic Value based on EBITDA"] = (_num(eb75.get("corrected_value")), "per_share", None)

    if owr.get("buffett_rate_of_return_pct") is not None:
        out["Rate of Return (Buffett)"] = (owr["buffett_rate_of_return_pct"] / 100.0, "pct", None)
    if coc.get("after_tax_cost_of_debt_pct") is not None:
        out["After-Tax Cost of Debt"] = (coc["after_tax_cost_of_debt_pct"] / 100.0, "pct", None)
    if coc.get("cost_of_equity_capm_pct") is not None:
        out["Cost of Equity (CAPM)"] = (coc["cost_of_equity_capm_pct"] / 100.0, "pct", None)
    if coc.get("cost_of_equity_ddm_pct") is not None:
        out["Cost of Equity (DDM)"] = (coc["cost_of_equity_ddm_pct"] / 100.0, "pct", None)
    if coc.get("equity_charge_total") is not None:
        out["Equity charge"] = (_num(coc.get("equity_charge_total")), "currency", None)
    if coc.get("wacc_pct") is not None:
        out["WACC"] = (coc["wacc_pct"] / 100.0, "pct", None)

    # Shares & ownership
    if shares_eff is not None and shares_eff > 0:
        out["Total Common Shares Outstanding"] = (shares_eff, "int", None)
        out["Adjusted Total Common Shares Outstanding"] = (shares_eff, "int", None)
        eq_last = _last(bal["Equity"])
        tot_sh = shares_eff * (1.0 + pref_last / eq_last) if (eq_last and eq_last > 0 and pref_last) else shares_eff
        out["Total Shares Outstanding"] = (tot_sh, "int", None)
    if avg_vol is not None and shares_eff and shares_eff > 0:
        out["Share Turnover"] = ((avg_vol * 252.0) / shares_eff, "ratio", "Volume annualisé / Actions")

    float_pct = _pct_dec(cv.get("float_pct"))
    if float_pct is not None and shares_eff and shares_eff > 0:
        flt_sh = float_pct * shares_eff
        out["Float %"] = (float_pct, "pct", None)
        out["Floating Stock"] = (flt_sh, "int", None)
        short_flt = _pct_dec(cv.get("short_pct_float"))
        if short_flt is not None:
            out["Short percentage of Float"] = (short_flt, "pct", None)
            if avg_vol and avg_vol > 0:
                out["Short-Interest ratio"] = ((short_flt * flt_sh) / avg_vol, "days", "Jours pour couvrir")
    elif _pct_dec(cv.get("short_pct_float")) is not None:
        out["Short percentage of Float"] = (_pct_dec(cv.get("short_pct_float")), "pct", None)

    st_rep = _last(cf["Common stock issued (repurchased)"])
    if st_rep is not None and mcap and mcap > 0:
        out["Buyback ratio"] = (-st_rep / mcap, "pct", None)

    if _pct_dec(cv.get("institutions_pct")) is not None:
        out["% held by institutions"] = (_pct_dec(cv.get("institutions_pct")), "pct", None)
    if _pct_dec(cv.get("insiders_pct")) is not None:
        out["% held by insiders"] = (_pct_dec(cv.get("insiders_pct")), "pct", None)
    n_analysts = _num((stakeholders or {}).get("analysts", {}).get("total"))
    if n_analysts is not None and n_analysts > 0:
        out["Number of analysts"] = (n_analysts, "int", None)
        out["Analyst coverage"] = (n_analysts, "int", None)
    inf_v = _num(((macro_ctx or {}).get("inflation_pct") or {}).get("value"))
    if inf_v is not None:
        out["Inflation"] = (inf_v / 100.0, "pct", None)

    return out


def compute_uncle_stock_catalog(
    *,
    ann_series: dict[str, dict[str, float | None]],
    qtr_series: dict[str, dict[str, float | None]] | None = None,
    dates: list[str],
    qtr_dates: list[str] | None = None,
    current_price: float | None = None,
    currency: str = "USD",
    shares_override: float | None = None,
    eod_fund: dict[str, Any] | None = None,
    capital_valuation: dict[str, Any] | None = None,
    intrinsic_valuation: dict[str, Any] | None = None,
    uncle_stock_scores: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    performance: dict[str, Any] | None = None,
    bars: list[dict[str, Any]] | None = None,
    macro_context: dict[str, Any] | None = None,
    stakeholders: dict[str, Any] | None = None,
    preferred_stock: float | None = None,
    minority_interest: float | None = None,
    employees: float | None = None,
) -> dict[str, Any]:
    """Évalue les 508 entrées du référentiel Uncle Stock pour un titre donné."""
    ref_rows = load_uncle_stock_reference()
    if not ref_rows:
        return {"total_count": 0, "computed_count": 0, "years": [], "categories": [], "items": []}

    cur = (currency or "USD").upper()
    n = len(dates)
    years = [d[:4] for d in dates[-5:]]
    shares_raw = _pad_series(ann_series, dates, "CommonStockSharesOutstanding", "DilutedAverageShares")
    shares_last = _num(shares_override) or _last(shares_raw)
    shares_v = [shares_raw[i] or shares_last for i in range(n)]

    coc = (intrinsic_valuation or {}).get("cost_of_capital") or {}
    wacc_dec = (_num(coc.get("wacc_pct")) / 100.0) if coc.get("wacc_pct") is not None else None
    ke_dec = (_num(coc.get("cost_of_equity_capm_pct")) / 100.0) if coc.get("cost_of_equity_capm_pct") is not None else None
    m_tax = (_num(coc.get("marginal_tax_rate_pct")) / 100.0) if coc.get("marginal_tax_rate_pct") is not None else 0.25
    rf_rate = (_num(coc.get("risk_free_rate_pct")) / 100.0) if coc.get("risk_free_rate_pct") is not None else 0.035

    bal = _compute_balance_pack(ann_series, dates, preferred_stock, minority_interest)
    inc, cf = _compute_income_cashflow_pack(ann_series, dates, bal, shares_v, wacc_dec, ke_dec, m_tax)
    mkt = _compute_technical_and_market(
        bars=bars,
        cur_price=current_price,
        cap_val=capital_valuation,
        eod_fund=eod_fund,
        intrinsic_val=intrinsic_valuation,
        risk_payload=risk,
        perf_payload=performance,
        bal=bal,
        inc=inc,
        cf=cf,
        shares_eff=shares_last,
        macro_ctx=macro_context,
        stakeholders=stakeholders,
    )

    # Calcul des séries de ratios Liquidité / Solvabilité / Rentabilité
    rev = inc["Revenue"]
    gp = inc["Gross profit"]
    oi = inc["Operating Income"]
    adj_oi = inc["Adjusted Operating Income"]
    ebitda = inc["EBITDA"]
    ebita = inc["EBITA"]
    ebit = inc["Adjusted EBIT"]
    ebit_std = _pad_series(ann_series, dates, "EBIT", "OperatingIncome")
    nopat = inc["Net Operating Profit After Tax (NOPAT)"]
    adj_nopat = inc["Adjusted Net Operating Profit After Tax (NOPAT)"]
    ni = inc["Net income"]
    ni_cont = inc["Net income from continuing operations (IAT)"]
    adj_earn = inc["Adjusted Earnings"]
    eps = inc["Earnings Per Share (EPS)"]
    cfo = cf["Cash Flow from Operations"]
    fcf = cf["Free Cash Flow"]
    fcff = cf["Free Cash Flow to the Firm"]
    adj_fcff = cf["Adjusted Free Cash Flow to the Firm"]
    capex = cf["Capital Expenditures (CapEx)"]
    dep = cf["Depreciation"]
    div_paid = cf["Dividend Paid"]
    oe = cf["Owner Earnings"]
    oe_p = cf["Owner Earnings'"]
    oe_pp = cf["Owner Earnings''"]
    firm_e = cf["Firm Earnings"]
    cash_nopat = cf["Cash-NOPAT"]
    lt_reinv = cf["Long-term Reinvestments"]
    rnd = inc["Research & Development"]
    sga = inc["Selling General & Administrative expenses"]
    opex = inc["Operating Expenses (OpEx)"]
    ie = inc["Interest expense"]
    cost_rev = inc["Cost of Revenue"]

    assets = bal["Total Assets"]
    tang_a = bal["Tangible Assets"]
    ca = bal["Current assets"]
    non_cash_ca = bal["Non-cash current assets"]
    cash_st = bal["Cash and short term investments"]
    cash_eq = bal["Total cash and equivalents"]
    ar = bal["Accounts receivable"]
    inv = bal["Inventory"]
    net_ppe = bal["Net Property, Plant and Equipment"]
    gross_ppe = bal["Gross Property, Plant and Equipment"]
    cl = bal["Current Liabilities"]
    nibcl = bal["Non-Interest-Bearing Current Liabilities (NIBCL)"]
    ncl = bal["Non-current Liabilities"]
    tl = bal["Total Liabilities"]
    tdl = bal["Total Debt and Lease"]
    tot_debt = bal["Total Debt"]
    lt_dl = bal["Long-term Debt and lease obligations"]
    lt_lease = bal["Long-term Lease"]
    nd = bal["Net debt"]
    eq_sh = bal["Shareholders' Equity"]
    eq_sh_t = bal["Shareholders' Equity and Treasury Stock"]
    eq_tot = bal["Equity"]
    cbv = bal["Common Book Value"]
    tbv = bal["Tangible Book Value"]
    ctbv = bal["Common Tangible Book Value"]
    core_cap = bal["Core Capital"]
    nwc = bal["Net Working Capital"]
    inv_cap = bal["Invested Capital"]
    ce = bal["Capital Employed"]
    ce_gb = bal["Capital Employed (Greenblatt)"]
    gi = bal["Gross Investment"]
    noa_p = bal["Net Operating Assets'"]
    ap = bal["Accounts Payable"]
    ret_earn = bal["Retained earnings"]

    ratio_series: dict[str, tuple[list[float | None], str]] = {}

    def add_rs(name: str, vec: list[float | None], unit: str) -> None:
        ratio_series[name] = (vec, unit)

    # Liquidité (17)
    add_rs("Current ratio", [_div(ca[i], cl[i]) for i in range(n)], "ratio")
    add_rs("Current Liability Coverage Ratio", [_div(cfo[i] - (div_paid[i] or 0.0) if cfo[i] is not None else None, cl[i]) for i in range(n)], "ratio")
    add_rs("Cash ratio", [_div(cash_st[i], cl[i]) for i in range(n)], "ratio")
    add_rs("Free Cash Current Liability Coverage Ratio", [_div(oe_p[i], cl[i]) for i in range(n)], "ratio")
    add_rs("Free Cash Current Liability Net Coverage Ratio", [_div(oe_p[i] - (div_paid[i] or 0.0) if oe_p[i] is not None else None, cl[i]) for i in range(n)], "ratio")
    add_rs("Quick ratio", [
        _div((cash_eq[i] + ar[i]) if (cash_eq[i] is not None and ar[i] is not None) else ((ca[i] - (inv[i] or 0.0)) if ca[i] is not None else None), cl[i])
        for i in range(n)
    ], "ratio")
    add_rs("Complete Quick ratio", [_div((cash_st[i] + oe_p[i]) if (cash_st[i] is not None and oe_p[i] is not None) else None, cl[i]) for i in range(n)], "ratio")
    add_rs("Net Complete Quick ratio", [_div((cash_st[i] + oe_p[i] - (div_paid[i] or 0.0)) if (cash_st[i] is not None and oe_p[i] is not None) else None, cl[i]) for i in range(n)], "ratio")
    add_rs("Cash to Current Assets", [_div(cash_st[i], ca[i]) for i in range(n)], "pct")
    add_rs("Cash to Assets", [_div(cash_st[i], assets[i]) for i in range(n)], "pct")
    add_rs("Net Working Capital to Assets", [_div(nwc[i], assets[i]) for i in range(n)], "pct")
    add_rs("Days Sales Outstanding", [(_yr_avg(ar, i) / rev[i] * 365.0) if (_yr_avg(ar, i) is not None and rev[i] and rev[i] > 0) else None for i in range(n)], "days")
    add_rs("Days Payable Outstanding", [(_yr_avg(ap, i) / cost_rev[i] * 365.0) if (_yr_avg(ap, i) is not None and cost_rev[i] and cost_rev[i] > 0) else None for i in range(n)], "days")
    add_rs("Flow ratio", [_div(non_cash_ca[i], nibcl[i]) for i in range(n)], "ratio")
    add_rs("Months Before Cash Runs Out", [_div(cash_st[i], cf["Burn rate"][i]) if (cf["Burn rate"][i] and cf["Burn rate"][i] > 0) else None for i in range(n)], "months")

    # Solvabilité (25)
    add_rs("Debt ratio", [_div(tl[i], assets[i]) for i in range(n)], "pct")
    add_rs("Long term debt ratio", [_div(ncl[i], assets[i]) for i in range(n)], "pct")
    add_rs("Total Debt/ Assets", [_div(tdl[i], assets[i]) for i in range(n)], "pct")
    add_rs("Net Debt/ Assets", [_div(nd[i], assets[i]) for i in range(n)], "pct")
    add_rs("Total debt / Equity", [_div(tot_debt[i], eq_sh[i]) for i in range(n)], "pct")
    add_rs("Liabilities / Equity", [_div(tl[i], eq_sh[i]) for i in range(n)], "pct")
    add_rs("Long-term Debt/ Equity ratio", [_div(lt_dl[i], eq_sh[i]) for i in range(n)], "pct")
    add_rs("Net Debt / Equity", [_div(nd[i], eq_sh[i]) for i in range(n)], "pct")
    add_rs("Debt / Tangible Book value", [_div(tl[i], tbv[i]) for i in range(n)], "pct")
    add_rs("Net Debt to Tangible Equity", [_div(nd[i], tbv[i]) for i in range(n)], "pct")
    add_rs("Equity ratio", [_div(eq_tot[i], assets[i]) for i in range(n)], "pct")
    add_rs("Equity multiplier", [_div(assets[i], eq_tot[i]) for i in range(n)], "ratio")
    add_rs("Tier 1 Capital ratio", [_div(core_cap[i], 0.8 * bal["Non-cash Assets"][i]) if bal["Non-cash Assets"][i] else None for i in range(n)], "pct")
    add_rs("LT debt / Working capital", [_div(lt_dl[i], nwc[i]) for i in range(n)], "ratio")
    add_rs("Net Debt / EBITDA", [_div(nd[i], ebitda[i]) for i in range(n)], "ratio")
    add_rs("Net Debt / FCFF", [_div(nd[i], fcff[i]) for i in range(n)], "ratio")
    add_rs("Cash to Debt", [_div(cash_st[i], tot_debt[i]) for i in range(n)], "pct")
    add_rs("Cash Flow Coverage Ratio", [_div(cfo[i], tl[i]) for i in range(n)], "pct")
    add_rs("Free Cash Flow / Long Term Debt", [_div(fcff[i], lt_dl[i]) for i in range(n)], "pct")
    add_rs("Debt leverage ratio", [_div(_yr_avg(tl, i), ebitda[i]) for i in range(n)], "ratio")
    add_rs("Adjusted Interest Coverage Ratio", [_div(adj_fcff[i], ie[i]) for i in range(n)], "ratio")
    add_rs("Interest Coverage ratio", [_div(ebit_std[i], ie[i]) for i in range(n)], "ratio")
    add_rs("Interest expense to Debt ratio", [_div(ie[i], tot_debt[i]) for i in range(n)], "pct")
    a_diff = _diff_series(assets)
    add_rs("External Financing Ratio", [_div(a_diff[i] - cfo[i] if (a_diff[i] is not None and cfo[i] is not None) else None, assets[i]) for i in range(n)], "pct")
    ev_last = _num(mkt.get("Enterprise Value", (None,))[0])
    mc_last = _num(mkt.get("Market cap", (None,))[0])
    add_rs("Enterprise Value to Market Cap", [None] * max(0, n - 1) + ([_div(ev_last, mc_last)] if n > 0 else []), "ratio")

    # Rentabilité — Based on Investment
    add_rs("Asset Turnover", [_div(rev[i], _yr_avg(assets, i)) for i in range(n)], "ratio")
    add_rs("Fixed Assets Turnover", [_div(rev[i], _yr_avg(net_ppe, i)) for i in range(n)], "ratio")
    add_rs("Inventory Turnover", [_div(rev[i], _yr_avg(inv, i)) for i in range(n)], "ratio")
    add_rs("Cash Turnover Ratio", [_div(rev[i], _yr_avg(cash_eq, i)) for i in range(n)], "ratio")
    add_rs("Gross Profitability Ratio", [_div(gp[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("EBITA Return on Assets (EBITA ROA)", [_div(ebita[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("EBIT Return on Assets (EBIT ROA)", [_div(ebit_std[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("Return on Assets (ROA)", [_div(nopat[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("Cash Return on Assets (Cash ROA)", [_div(cfo[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("Cash-NOPAT Return On Assets (Cash-NOPAT ROA)", [_div(cash_nopat[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("Tangible Gross Profitability Ratio", [_div(gp[i], _yr_avg(tang_a, i)) for i in range(n)], "pct")
    add_rs("EBITA return on Tangible Assets (EBITA ROTA)", [_div(ebita[i], _yr_avg(tang_a, i)) for i in range(n)], "pct")
    add_rs("EBIT return on Tangible Assets (EBIT ROTA)", [_div(ebit_std[i], _yr_avg(tang_a, i)) for i in range(n)], "pct")
    add_rs("Cash-NOPAT Return On Tangible Assets", [_div(cash_nopat[i], _yr_avg(tang_a, i)) for i in range(n)], "pct")
    add_rs("Owner Return on Tangible Assets", [_div(oe_pp[i], _yr_avg(tang_a, i)) for i in range(n)], "pct")
    add_rs("Cash Return on Gross Investment", [_div(ebitda[i], _yr_avg(gi, i)) for i in range(n)], "pct")
    roic_v = [_div(nopat[i], _yr_avg(inv_cap, i)) for i in range(n)]
    add_rs("Return on Invested Capital (ROIC)", roic_v, "pct")
    add_rs("Economic spread", [(roic_v[i] - wacc_dec) if (roic_v[i] is not None and wacc_dec is not None) else None for i in range(n)], "pct")
    add_rs("ROIC / WACC", [_div(roic_v[i], wacc_dec) for i in range(n)], "ratio")
    add_rs("Adjusted Return on Invested Capital (ROIC)", [_div(adj_earn[i], _yr_avg(inv_cap, i)) for i in range(n)], "pct")
    add_rs("Cash Return on Invested Capital (CROIC)", [_div(cash_nopat[i], _yr_avg(inv_cap, i)) for i in range(n)], "pct")
    add_rs("Owner Return on Invested Capital (OROIC)", [_div(oe[i], _yr_avg(inv_cap, i)) for i in range(n)], "pct")
    add_rs("Adjusted Return on Capital Employed (Adjusted ROCE)", [_div(adj_oi[i], _yr_avg(ce_gb, i)) for i in range(n)], "pct")
    add_rs("Return on Capital Employed (ROCE)", [_div(ebit_std[i], _yr_avg(ce_gb, i)) for i in range(n)], "pct")
    add_rs("Adjusted After Tax Return on Capital Employed (Adjusted AT ROCE)", [
        _div(adj_fcff[i], (_yr_avg(ce_gb, i) - (_yr_avg(lt_lease, i) or 0.0)) if _yr_avg(ce_gb, i) is not None else None)
        for i in range(n)
    ], "pct")
    add_rs("After Tax Return on Capital Employed (AT ROCE)", [_div(nopat[i], _yr_avg(ce, i)) for i in range(n)], "pct")
    add_rs("Cash Return on Capital Employed (CROCE)", [_div(fcff[i], _yr_avg(ce, i)) for i in range(n)], "pct")
    add_rs("Cash Return on Capital Employed' (CROCE')", [_div(firm_e[i], _yr_avg(ce_gb, i)) for i in range(n)], "pct")
    add_rs("Return on Net Operating Assets", [_div(adj_oi[i], _yr_avg(noa_p, i)) for i in range(n)], "pct")
    add_rs("R&D / Assets", [_div(rnd[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("CapEx / Assets", [_div(capex[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("CapEx / Fixed Assets", [_div(capex[i], _yr_avg(gross_ppe, i)) for i in range(n)], "pct")
    add_rs("Depreciation rate", [_div(dep[i], gross_ppe[i]) for i in range(n)], "pct")
    add_rs("CapEx / Depreciation", [_div(capex[i], _yr_avg(dep, i)) for i in range(n)], "ratio")
    dwc_cf = cf["Change in non-cash Working Capital"]
    add_rs("Long-term Reinvestment rate", [
        _div((dwc_cf[i] or 0.0) + lt_reinv[i], adj_nopat[i])
        if (lt_reinv[i] is not None and adj_nopat[i] and adj_nopat[i] > 0)
        else None
        for i in range(n)
    ], "pct")
    add_rs("Long-term Reinvestments / Assets", [_div(lt_reinv[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    if employees and employees > 0:
        add_rs("Revenue per Employee", [_div(rev[i], employees) if i == n - 1 else None for i in range(n)], "currency")
        add_rs("Profit per Employee", [_div(ni_cont[i] or ni[i], employees) if i == n - 1 else None for i in range(n)], "currency")
    add_rs("Retained Earnings / Total Assets", [_div(ret_earn[i], _yr_avg(assets, i)) for i in range(n)], "pct")
    add_rs("Return on Research Capital", [_div(gp[i], rnd[i]) for i in range(n)], "ratio")
    epv_firm_v = _num(mkt.get("Earnings Power Value", (None,))[0])
    add_rs("Earnings Power Value/ Assets", [None] * max(0, n - 1) + ([_div(epv_firm_v, assets[-1])] if (n > 0 and epv_firm_v is not None) else ([None] if n > 0 else [])), "pct")
    add_rs("Inventory/ Assets", [_div(inv[i], assets[i]) for i in range(n)], "pct")
    add_rs("Accounts Receivable/ Assets", [_div(ar[i], assets[i]) for i in range(n)], "pct")
    add_rs("Cash Return on Equity (Cash ROE)", [_div(cfo[i], _yr_avg(eq_tot, i)) for i in range(n)], "pct")
    cbv_ps_l = [_div(cbv[i], shares_v[i]) for i in range(n)]
    ctbv_ps_l = [_div(ctbv[i], shares_v[i]) for i in range(n)]
    add_rs("Return on Equity (ROE)", [_div(eps[i], _yr_avg(cbv_ps_l, i)) for i in range(n)], "pct")
    add_rs("Adjusted Return on Equity (ROE)", [_div(ni[i], _yr_avg(eq_sh_t, i)) for i in range(n)], "pct")
    add_rs("Return on Tangible Equity (ROTE)", [_div(eps[i], _yr_avg(ctbv_ps_l, i)) for i in range(n)], "pct")
    add_rs("Owner Return on Equity", [_div(oe[i], _yr_avg(eq_sh, i)) for i in range(n)], "pct")
    add_rs("Owner' Return on Equity", [_div(oe_p[i], _yr_avg(eq_sh, i)) for i in range(n)], "pct")
    # Return on Retained Earnings (5y)
    rore_v: float | None = None
    if n >= 6 and eps[-1] is not None and eps[-6] is not None:
        ch_re_5y = [inc["Change to Retained Earnings"][j] for j in range(n - 5, n) if inc["Change to Retained Earnings"][j] is not None]
        if len(ch_re_5y) >= 3 and sum(ch_re_5y) > 0:
            rore_v = (eps[-1] - eps[-6]) / sum(ch_re_5y)
    add_rs("Return on Retained Earnings (RORE)", [None] * max(0, n - 1) + ([rore_v] if n > 0 else []), "pct")
    add_rs("R&D / Book", [_div(rnd[i], _yr_avg(eq_sh, i)) for i in range(n)], "pct")

    # Rentabilité — Based on Sales
    add_rs("Gross margin", [_div(gp[i], rev[i]) for i in range(n)], "pct")
    ebitda_m_l = [_div(ebitda[i], rev[i]) for i in range(n)]
    add_rs("EBITDA margin", ebitda_m_l, "pct")
    add_rs("EBITA margin", [_div(ebita[i], rev[i]) for i in range(n)], "pct")
    add_rs("Operating Margin", [_div(oi[i], rev[i]) for i in range(n)], "pct")
    add_rs("Adjusted Operating Margin", [_div(adj_oi[i], rev[i]) for i in range(n)], "pct")
    add_rs("EBIT margin", [_div(ebit_std[i], rev[i]) for i in range(n)], "pct")
    add_rs("Operating Cash Flow margin", [_div(cfo[i], rev[i]) for i in range(n)], "pct")
    add_rs("Owner Earnings margin", [_div(oe_p[i], rev[i]) for i in range(n)], "pct")
    add_rs("Free Cash Flow margin", [_div(fcf[i], rev[i]) for i in range(n)], "pct")
    add_rs("Adjusted Earnings margin", [_div(adj_earn[i], rev[i]) for i in range(n)], "pct")
    add_rs("Net margin", [_div(ni[i], rev[i]) for i in range(n)], "pct")
    add_rs("EVA margin", [_div(inc["Economic Value Added"][i], rev[i]) for i in range(n)], "pct")
    add_rs("EVA momentum", [_div(inc["EVA diff"][i], rev[i]) for i in range(n)], "pct")
    add_rs("R&D to Revenue", [_div(rnd[i], rev[i]) for i in range(n)], "pct")
    add_rs("Cost-to-Income Ratio", [_div(opex[i], oi[i]) for i in range(n)], "pct")
    add_rs("Operating Expense Ratio (OER)", [_div(opex[i], rev[i]) for i in range(n)], "pct")
    add_rs("Selling General & Administrative expenses/ Revenue", [_div(sga[i], rev[i]) for i in range(n)], "pct")
    add_rs("Selling General & Administrative expenses/ Gross Profit", [_div(sga[i], gp[i]) for i in range(n)], "pct")
    add_rs("Depreciation/ Gross Profit", [_div(dep[i], gp[i]) for i in range(n)], "pct")
    add_rs("Capital Expenditures/ Revenue", [_div(capex[i], rev[i]) for i in range(n)], "pct")
    add_rs("Capital Expenditures/ Operating Income", [_div(capex[i], (gp[i] - sga[i]) if (gp[i] is not None and sga[i] is not None) else None) for i in range(n)], "pct")
    add_rs("Capital Expenditures/ Cash Flow from Operations", [_div(capex[i], cfo[i]) for i in range(n)], "pct")
    dsi_l = [(_yr_avg(inv, i) / cost_rev[i] * 365.0) if (_yr_avg(inv, i) is not None and cost_rev[i] and cost_rev[i] > 0) else None for i in range(n)]
    add_rs("Days Inventory Outstanding", dsi_l, "days")
    dso_l, _ = ratio_series["Days Sales Outstanding"]
    dpo_l, _ = ratio_series["Days Payable Outstanding"]
    def_d_l = inc["Days Current Deferred Revenue"]
    add_rs("Cash Conversion Cycle", [
        (dsi_l[i] + dso_l[i] - dpo_l[i] - (def_d_l[i] or 0.0))
        if (dsi_l[i] is not None and dso_l[i] is not None and dpo_l[i] is not None)
        else None
        for i in range(n)
    ], "days")
    # The Rule of 40 = Revenue 1y growth (quarterly if >=5q, else annual) + EBITDA margin
    q_rev_g = _pct_dec((capital_valuation or {}).get("rev_growth_q_yoy"))
    if q_rev_g is None and qtr_series and qtr_dates and len(qtr_dates) >= 5:
        qv0 = _num((qtr_series.get("TotalRevenue") or {}).get(qtr_dates[-5]))
        qv1 = _num((qtr_series.get("TotalRevenue") or {}).get(qtr_dates[-1]))
        if qv0 and qv1 and qv0 > 0:
            q_rev_g = (qv1 - qv0) / abs(qv0)
    if q_rev_g is None:
        q_rev_g = _yoy_growth(rev)
    r40_l = [None] * n
    if n > 0 and q_rev_g is not None and ebitda_m_l[-1] is not None:
        r40_l[-1] = q_rev_g + ebitda_m_l[-1]
    add_rs("The Rule of 40", r40_l, "pct")

    # Sous-métriques démonstratives évaluées sur le CA (TotalRevenue) ou le Cours (Price)
    closes = [c for c in (_num(b.get("adjusted_close") or b.get("close")) for b in (bars or [])) if c is not None and c > 0]
    p_cur = current_price or (closes[-1] if closes else None)
    hi52 = _num((capital_valuation or {}).get("high_52w")) or (max(closes[-252:]) if len(closes) >= 20 else None)
    lo52 = _num((capital_valuation or {}).get("low_52w")) or (min(closes[-252:]) if len(closes) >= 20 else None)
    mma50 = _num((capital_valuation or {}).get("mma50")) or ((sum(closes[-50:]) / 50.0) if len(closes) >= 50 else None)
    mma200 = _num((capital_valuation or {}).get("mma200")) or ((sum(closes[-200:]) / 200.0) if len(closes) >= 200 else None)

    rev_rcagr_67, rev_rcagr_raw = compute_rcagr_67(rev)
    rev_5y_pts = [v for v in rev[-5:] if v is not None]
    submetric_vals: dict[str, tuple[float | None, str, str]] = {
        "amount": (_last(rev), "currency", "Dernier CA annuel"),
        "per share": (_div(_last(rev), shares_last), "per_share", "CA par action"),
        "wavg": (_wavg_last(rev, 5), "currency", "Moy. pondérée 5A (CA)"),
        "wavg/share": (_div(_wavg_last(rev, 5), shares_last), "per_share", "CA moy. pond. / action"),
        "xy avg": (_avg_last(rev, 5), "currency", "Moyenne 5A (CA)"),
        "cycle avg": (max([v for v in (_avg_last(rev, 10), 0.5 * _avg_last(rev, 5) if _avg_last(rev, 5) else None) if v is not None], default=None), "currency", "max(moy 10A ; 0,5×moy 5A) sur CA"),
        "xy weakest": (min(rev_5y_pts, default=None), "currency", "Minimum 5A (CA)"),
        "xy best": (max(rev_5y_pts, default=None), "currency", "Maximum 5A (CA)"),
        "xy SD": (_sd_last(rev, 5), "currency", "Écart-type 5A (CA)"),
        "xy CV": (_cv_last(rev, 5), "num", "Coeff. variation 5A (CA)"),
        "daily": (_div(_last(rev), 365.0), "currency", "CA journalier (/ 365)"),
        "y sum": (sum(rev_5y_pts) if rev_5y_pts else None, "currency", "Somme 5A (CA)"),
        "1y growth": (_yoy_growth(rev), "pct", "Croissance 1A du CA"),
        "xy diff": ((rev[-1] - rev[-min(5, n)]) if (n >= 2 and rev[-1] is not None and rev[-min(5, n)] is not None) else None, "currency", "Variation absolue CA (5A)"),
        "R2": (_r2(rev), "num", "Régularité R² (CA)"),
        "xy rCAGR": (rev_rcagr_raw, "pct", "rCAGR log-linéaire (CA)"),
        "rCAGR 67%": (rev_rcagr_67, "pct", "rCAGR 67% prudent (CA)"),
        "CAGR": (_cagr(rev, 5), "pct", "CAGR 5A (CA)"),
        "Xy CAGR": (_cagr(rev, 5), "pct", "CAGR sur 5 ans (CA)"),
        "xy median": (statistics.median([v for v in rev[-5:] if v is not None]) if any(v is not None for v in rev[-5:]) else None, "currency", "Médiane 5A (CA)"),
        "diff xy avg": (_div(_last(rev) - _avg_last(rev, 5), abs(_avg_last(rev, 5))) if (_last(rev) is not None and _avg_last(rev, 5)) else None, "pct", "Écart CA vs moy. 5A"),
        "dif vs 1y bottom": (_div(p_cur - lo52, lo52) if (p_cur is not None and lo52) else None, "pct", "Cours vs + bas 52 sem."),
        "dif vs x wk top": (_div(p_cur - hi52, hi52) if (p_cur is not None and hi52) else None, "pct", "Cours vs + haut 52 sem."),
        "pos vs 1y": (_div(p_cur - lo52, hi52 - lo52) if (p_cur is not None and hi52 is not None and lo52 is not None and hi52 > lo52) else None, "pct", "Position dans le range 52 sem."),
        "yr range %": (_div(hi52 - lo52, 0.5 * (hi52 + lo52)) if (hi52 is not None and lo52 is not None and (hi52 + lo52) > 0) else None, "pct", "Amplitude 52 sem."),
        "smaX": (mma50, "per_share", "MMA 50 séances"),
        "maX vs maY": (_div(mma50 - mma200, mma200) if (mma50 is not None and mma200) else None, "pct", "MMA50 vs MMA200"),
        "FV": ((_last(rev) * ((1.0 + max(-0.5, (_cagr(rev, 3) or 0.0) - rf_rate)) ** 6)) if (_last(rev) is not None and _cagr(rev, 3) is not None) else None, "currency", "Valeur future 6A (CA)"),
    }

    # Substitutions chiffrées explicites pour les ratios clés du référentiel
    last_i = n - 1
    avg_a_last = _yr_avg(assets, last_i) if n > 0 else None
    avg_ic_last = _yr_avg(inv_cap, last_i) if n > 0 else None
    avg_cbv_ps_last = _yr_avg(cbv_ps_l, last_i) if n > 0 else None
    avg_ce_gb_last = _yr_avg(ce_gb, last_i) if n > 0 else None
    key_subs: dict[str, str] = {}
    if n > 0:
        if _last(nopat) is not None and avg_a_last:
            key_subs["Return on Assets (ROA)"] = f"{_fmt_value(_last(nopat), 'currency', cur)} / {_fmt_value(avg_a_last, 'currency', cur)}"
        if _last(eps) is not None and avg_cbv_ps_last:
            key_subs["Return on Equity (ROE)"] = f"{_fmt_value(_last(eps), 'per_share', cur)} / {_fmt_value(avg_cbv_ps_last, 'per_share', cur)}"
        if _last(nopat) is not None and avg_ic_last:
            key_subs["Return on Invested Capital (ROIC)"] = f"{_fmt_value(_last(nopat), 'currency', cur)} / {_fmt_value(avg_ic_last, 'currency', cur)}"
        if _last(cash_nopat) is not None and avg_ic_last:
            key_subs["Cash Return on Invested Capital (CROIC)"] = f"{_fmt_value(_last(cash_nopat), 'currency', cur)} / {_fmt_value(avg_ic_last, 'currency', cur)}"
        if _last(ebit_std) is not None and avg_ce_gb_last:
            key_subs["Return on Capital Employed (ROCE)"] = f"{_fmt_value(_last(ebit_std), 'currency', cur)} / {_fmt_value(avg_ce_gb_last, 'currency', cur)}"
        if _last(rev) is not None and avg_a_last:
            key_subs["Asset Turnover"] = f"{_fmt_value(_last(rev), 'currency', cur)} / {_fmt_value(avg_a_last, 'currency', cur)}"
        if _last(ca) is not None and _last(cl) is not None:
            key_subs["Current ratio"] = f"{_fmt_value(_last(ca), 'currency', cur)} / {_fmt_value(_last(cl), 'currency', cur)}"
        if _last(cl) is not None and (_last(cash_eq) is not None and _last(ar) is not None):
            key_subs["Quick ratio"] = f"({_fmt_value(_last(cash_eq), 'currency', cur)} + {_fmt_value(_last(ar), 'currency', cur)}) / {_fmt_value(_last(cl), 'currency', cur)}"
        if _last(tl) is not None and _last(assets) is not None:
            key_subs["Debt ratio"] = f"{_fmt_value(_last(tl), 'currency', cur)} / {_fmt_value(_last(assets), 'currency', cur)}"
        if _last(inv_cap) is not None and _last(assets) is not None and _last(nibcl) is not None:
            ex_cash_p_last = _last(bal["Excess Cash'"])
            key_subs["Invested Capital"] = (
                f"{_fmt_value(_last(assets), 'currency', cur)} − {_fmt_value(_last(nibcl), 'currency', cur)} − "
                f"{_fmt_value(ex_cash_p_last, 'currency', cur)}"
            )

    # Assemblage final dans l'ordre exact des 508 lignes du référentiel
    unit_map_inc_cf: dict[str, str] = {
        "Tax rate": "pct",
        "Earnings Per Share (EPS)": "per_share",
        "Residual Income": "per_share",
        "Traditional Gross Dividend": "per_share",
        "Net Dividend": "per_share",
        "Change to Retained Earnings": "per_share",
        "Cash Flow / Earnings": "ratio",
        "Billings / Revenue": "pct",
        "Days Current Deferred Revenue": "days",
        "Free Cash Flow / EBITDA": "pct",
        "CF / EPS": "ratio",
        "Cash Conversion Ratio (CCR)": "pct",
        "Accruals to Total Assets": "pct",
        "Sloan ratio": "pct",
        "Absolute Sloan ratio": "pct",
        "NOA Accruals to Total Assets": "pct",
        "RSST Accruals to Total Assets": "pct",
        "Soft Assets to Total Assets": "pct",
        "Payout ratio": "pct",
        "Owner Payout ratio": "pct",
        "Dividend Cushion ratio": "ratio",
        "Stock based compensation / Revenue": "pct",
        "Other Current Assets/ Revenue": "pct",
        "Asset quality": "pct",
        "Burn rate": "currency",
    }

    items: list[dict[str, Any]] = []
    cat_counts: dict[str, dict[str, int]] = {}
    computed_total = 0

    for idx, ref in enumerate(ref_rows):
        cat = str(ref.get("category") or "")
        sec = str(ref.get("section") or "")
        name = str(ref.get("name") or "")
        formula = str(ref.get("formula") or "")
        desc = str(ref.get("description") or "")
        method = str(ref.get("method") or "")
        notes = str(ref.get("notes") or "")
        example = str(ref.get("example") or "")

        cat_entry = cat_counts.setdefault(cat, {"total": 0, "computed": 0})
        cat_entry["total"] += 1

        if name == "Home":
            items.append({
                "id": f"ref_{idx}",
                "category": cat,
                "section": sec,
                "name": name,
                "formula": formula,
                "description": desc,
                "unit": "doc",
                "available": False,
                "latest_value": None,
                "formatted_value": "—",
                "values_by_year": [],
                "submetrics": None,
                "substitution": None,
            })
            continue

        latest_v: float | None = None
        values_5y: list[float | None] = []
        subm: dict[str, str | None] | None = None
        unit = "currency"
        sub_note: str | None = None

        if name in ratio_series:
            vec, unit = ratio_series[name]
            latest_v = _last(vec)
            values_5y = [round(v, 4) if v is not None else None for v in vec[-5:]]
            subm = _build_submetrics(vec, unit, cur)
        elif name in bal:
            vec = bal[name]
            unit = unit_map_inc_cf.get(name, "currency")
            latest_v = _last(vec)
            values_5y = [round(v, 4) if v is not None else None for v in vec[-5:]]
            subm = _build_submetrics(vec, unit, cur)
        elif name in inc:
            vec = inc[name]
            unit = unit_map_inc_cf.get(name, "currency")
            latest_v = _last(vec)
            values_5y = [round(v, 4) if v is not None else None for v in vec[-5:]]
            subm = _build_submetrics(vec, unit, cur)
        elif name in cf:
            vec = cf[name]
            unit = unit_map_inc_cf.get(name, "currency")
            latest_v = _last(vec)
            values_5y = [round(v, 4) if v is not None else None for v in vec[-5:]]
            subm = _build_submetrics(vec, unit, cur)
        elif cat == "Marché et valorisation" and name in mkt:
            v_m, u_m, s_m = mkt[name]
            latest_v = v_m
            unit = u_m
            sub_note = s_m
        elif cat == "Sous-métriques" and name in submetric_vals:
            v_s, u_s, s_s = submetric_vals[name]
            latest_v = v_s
            unit = u_s
            sub_note = s_s

        if not sub_note and name in key_subs:
            sub_note = key_subs[name]

        avail = latest_v is not None and math.isfinite(latest_v)
        if avail:
            computed_total += 1
            cat_entry["computed"] += 1

        entry: dict[str, Any] = {
            "id": f"ref_{idx}",
            "category": cat,
            "section": sec,
            "name": name,
            "formula": formula,
            "description": desc,
            "unit": unit,
            "available": avail,
            "latest_value": round(latest_v, 4) if avail else None,
            "formatted_value": _fmt_value(latest_v, unit, cur) if avail else "—",
            "values_by_year": values_5y,
            "submetrics": subm,
            "substitution": sub_note,
        }
        if method and method != _DEFAULT_METHOD:
            entry["method"] = method
        if notes and notes != _DEFAULT_NOTES:
            entry["notes"] = notes
        if example:
            entry["example"] = example
        items.append(entry)

    categories = [
        {"name": cat, "total": counts["total"], "computed": counts["computed"]}
        for cat, counts in cat_counts.items()
    ]
    return {
        "total_count": len(ref_rows),
        "computed_count": computed_total,
        "years": years,
        "categories": categories,
        "items": items,
    }
