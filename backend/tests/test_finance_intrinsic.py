"""Tests unitaires du module de valorisation intrinsèque (`backend/app/finance_intrinsic.py`)."""

from __future__ import annotations

from app.finance_intrinsic import (
    _buffett_ddm_bv,
    _pv_5y_plus_perpetuity,
    compute_intrinsic_valuations,
    compute_rcagr_67,
)


def test_guide_numerical_building_blocks():
    # Exemple DCF FCF : FCFF0 = 100M, g = 4%, WACC = 9%, NetDebt = 250M, NCI = 20M, N = 50M -> 20.88
    tot_pv, pv_5y, pv_tv = _pv_5y_plus_perpetuity(100e6, 0.04, 0.09)
    assert round(pv_5y / 1e6, 2) == 435.26
    assert round(pv_tv / 1e6, 2) == 878.60
    iv_dcf = (tot_pv - 270e6) / 50e6
    assert round(iv_dcf, 2) == 20.88

    # DCF No Growth : (100/0.09 - 270) / 50 = 16.82
    iv_ng = (100e6 / 0.09 - 270e6) / 50e6
    assert round(iv_ng, 2) == 16.82

    # Buffett DDM + BV : BVPS=30, Div=1.20, gD=3%, gB=5%, Ke=10% -> 8.51 + 18.84 = 27.35
    iv_b, pv_divs, pv_bv10 = _buffett_ddm_bv(1.20, 0.03, 30.0, 0.05, 0.10)
    assert round(pv_divs, 2) == 8.51
    assert round(pv_bv10, 2) == 18.84
    assert round(iv_b, 2) == 27.35

    # Residual Income : BVPS=30, EPS=4, Ke=10%, g=3% -> RI0=1 -> 30 + 4.12 + 7.20 = 41.32
    pv_ri, pv_ri5, pv_ritv = _pv_5y_plus_perpetuity(1.0, 0.03, 0.10)
    assert round(pv_ri5, 2) == 4.12
    assert round(pv_ritv, 2) == 7.20
    assert round(30.0 + pv_ri, 2) == 41.32


def test_rcagr_67_steady_and_volatile_series():
    steady = [100.0 * (1.10 ** i) for i in range(8)]
    g_prudent, g_raw = compute_rcagr_67(steady)
    assert g_raw is not None and abs(g_raw - 0.10) < 1e-4
    assert g_prudent is not None and abs(g_prudent - 0.10) < 1e-4

    # Série avec trop de zéros/négatifs -> refusé (< 67%)
    mostly_neg = [-10.0, -5.0, -2.0, 10.0]
    assert compute_rcagr_67(mostly_neg) == (None, None)


def test_compute_intrinsic_valuations_full_suite():
    dates = ["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]
    shares = 50_000_000.0
    ann_series = {
        "TotalRevenue": {d: 800e6 * (1.06 ** i) for i, d in enumerate(dates)},
        "GrossProfit": {d: 400e6 * (1.06 ** i) for i, d in enumerate(dates)},
        "OperatingIncome": {d: 110e6 * (1.05 ** i) for i, d in enumerate(dates)},
        "EBITDA": {d: 130e6 * (1.06 ** i) for i, d in enumerate(dates)},
        "InterestExpense": {d: 10e6 for d in dates},
        "PretaxIncome": {d: 100e6 * (1.05 ** i) for i, d in enumerate(dates)},
        "TaxProvision": {d: 25e6 * (1.05 ** i) for i, d in enumerate(dates)},
        "NetIncome": {d: 80e6 * (1.06 ** i) for i, d in enumerate(dates)},
        "DilutedEPS": {d: (80e6 * (1.06 ** i)) / shares for i, d in enumerate(dates)},
        "CommonStockSharesOutstanding": {d: shares for d in dates},
        "StockholdersEquity": {d: 500e6 + 60e6 * i for i, d in enumerate(dates)},
        "GoodwillAndIntangibleAssets": {d: 50e6 for d in dates},
        "TotalDebt": {d: 300e6 for d in dates},
        "CashCashEquivalentsAndShortTermInvestments": {d: 50e6 for d in dates},
        "OperatingCashFlow": {d: 120e6 * (1.05 ** i) for i, d in enumerate(dates)},
        "CapitalExpenditure": {d: -25e6 for d in dates},
        "FreeCashFlow": {d: 120e6 * (1.05 ** i) - 25e6 for i, d in enumerate(dates)},
        "CashDividendsPaid": {d: -20e6 * (1.04 ** i) for i, d in enumerate(dates)},
        "SellingGeneralAndAdministration": {d: 120e6 for d in dates},
    }
    bars = [
        {"date": "2021-12-30", "close": 16.0, "adjusted_close": 16.0},
        {"date": "2022-12-30", "close": 17.0, "adjusted_close": 17.0},
        {"date": "2023-12-29", "close": 18.0, "adjusted_close": 18.0},
        {"date": "2024-12-31", "close": 19.0, "adjusted_close": 19.0},
        {"date": "2025-12-31", "close": 20.0, "adjusted_close": 20.0},
    ]

    res = compute_intrinsic_valuations(
        ann_series=ann_series,
        dates=dates,
        current_price=20.0,
        currency="EUR",
        country_iso3="FRA",
        beta=1.1,
        minority_interest=20_000_000.0,
        preferred_stock=0.0,
        piotroski_score=7,
        bars=bars,
    )

    assert res["available"] is True
    assert res["cost_of_capital"]["wacc_pct"] >= res["cost_of_capital"]["wacc_floor_pct"]
    assert res["owner_returns"]["total_owner_return_pct"] is not None
    assert res["owner_returns"]["net_owner_return_pct"] is not None
    assert res["owner_returns"]["forward_rate_of_return_pct"] is not None

    # Vérifier la présence des 13 composantes pondérées + méthodes complémentaires
    by_id = {m["id"]: m for m in res["methods"]}
    weighted = [m for m in res["methods"] if m["category"] == "weighted"]
    assert sum(m["weight"] for m in weighted) == 30
    assert by_id["current_price"]["status_unclestock"] == "valid"
    assert by_id["current_price"]["status_corrected"] == "excluded"

    # Graham Formula distingue mode littéral vs parenthèses globales
    assert by_id["graham_formula"]["unclestock_value"] != by_id["graham_formula"]["corrected_value"]
    # EPV distingue pré-impôts (littéral) vs NOPAT (corrigé)
    assert by_id["epv"]["unclestock_value"] > by_id["epv"]["corrected_value"]
    # Value Driver retranche dette nette / minoritaires en mode corrigé
    assert by_id["value_driver"]["unclestock_value"] > by_id["value_driver"]["corrected_value"]

    assert res["summary"]["unclestock"]["intrinsic_value"] > 0
    assert res["summary"]["corrected"]["intrinsic_value"] > 0
    assert len(res["scenarios"]) == 3
    assert res["sensitivity"] is not None and len(res["sensitivity"]["rows"]) == 5


def test_compute_intrinsic_valuations_excludes_negative_earnings():
    dates = ["2024-12-31", "2025-12-31"]
    ann_series = {
        "NetIncome": {"2024-12-31": -10e6, "2025-12-31": -15e6},
        "DilutedEPS": {"2024-12-31": -1.0, "2025-12-31": -1.5},
        "CommonStockSharesOutstanding": {"2024-12-31": 10e6, "2025-12-31": 10e6},
        "StockholdersEquity": {"2024-12-31": 50e6, "2025-12-31": 35e6},
        "FreeCashFlow": {"2024-12-31": -5e6, "2025-12-31": -8e6},
        "EBITDA": {"2024-12-31": -2e6, "2025-12-31": -4e6},
    }
    res = compute_intrinsic_valuations(
        ann_series=ann_series,
        dates=dates,
        current_price=5.0,
        currency="USD",
    )
    by_id = {m["id"]: m for m in res["methods"]}
    assert by_id["dcf_fcf"]["status_corrected"] == "excluded"
    assert by_id["graham_formula"]["status_corrected"] == "excluded"
    assert by_id["graham_number"]["status_corrected"] == "excluded"
    assert by_id["ebitda_7_5x"]["status_corrected"] == "excluded"
    assert res["scenarios"] == []
