"""Tests unitaires du moteur des 31 scores Uncle Stock (`backend/app/finance_scores.py`)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.finance_scores import compute_uncle_stock_scores


def _sample_healthy_inputs(*, sector: str = "Technology", with_esg: bool = True, undervalued: bool = True):
    dates = [f"{yr}-12-31" for yr in range(2019, 2026)]
    n = len(dates)
    ann_series = {
        "TotalRevenue": [800e6 * (1.10 ** i) for i in range(n)],
        "GrossProfit": [460e6 * (1.11 ** i) for i in range(n)],
        "OperatingIncome": [160e6 * (1.11 ** i) for i in range(n)],
        "EBITDA": [195e6 * (1.11 ** i) for i in range(n)],
        "EBIT": [160e6 * (1.11 ** i) for i in range(n)],
        "NetIncome": [120e6 * (1.11 ** i) for i in range(n)],
        "DilutedEPS": [2.4 * (1.11 ** i) for i in range(n)],
        "OperatingCashFlow": [180e6 * (1.10 ** i) for i in range(n)],
        "CapitalExpenditure": [-35e6 * (1.05 ** i) for i in range(n)],
        "FreeCashFlow": [145e6 * (1.11 ** i) for i in range(n)],
        "TotalAssets": [1100e6 * (1.06 ** i) for i in range(n)],
        "CurrentAssets": [500e6 * (1.06 ** i) for i in range(n)],
        "CurrentLiabilities": [210e6 * (1.04 ** i) for i in range(n)],
        "CashCashEquivalentsAndShortTermInvestments": [240e6 * (1.08 ** i) for i in range(n)],
        "CashAndCashEquivalents": [200e6 * (1.08 ** i) for i in range(n)],
        "AccountsReceivable": [110e6 * (1.05 ** i) for i in range(n)],
        "Inventory": [65e6 * (1.04 ** i) for i in range(n)],
        "NetPPE": [260e6 * (1.04 ** i) for i in range(n)],
        "GoodwillAndIntangibleAssets": [120e6 for _ in range(n)],
        "TotalLiabilitiesNetMinorityInterest": [420e6 * (1.03 ** i) for i in range(n)],
        "LongTermDebt": [160e6 * (0.96 ** i) for i in range(n)],
        "TotalDebt": [185e6 * (0.96 ** i) for i in range(n)],
        "NetDebt": [0.0 for _ in range(n)],
        "StockholdersEquity": [680e6 * (1.09 ** i) for i in range(n)],
        "RetainedEarnings": [450e6 * (1.10 ** i) for i in range(n)],
        "WorkingCapital": [290e6 * (1.07 ** i) for i in range(n)],
        "CommonStockSharesOutstanding": [50_000_000.0 * (0.99 ** i) for i in range(n)],
        "CashDividendsPaid": [-25e6 * (1.06 ** i) for i in range(n)],
        "RepurchaseOfCapitalStock": [-30e6 for _ in range(n)],
        "IssuanceOfDebt": [0.0 for _ in range(n)],
        "SellingGeneralAndAdministration": [140e6 * (1.06 ** i) for i in range(n)],
        "ResearchAndDevelopment": [75e6 * (1.08 ** i) for i in range(n)],
        "DepreciationAndAmortization": [35e6 * (1.06 ** i) for i in range(n)],
        "TaxProvision": [38e6 * (1.10 ** i) for i in range(n)],
        "PretaxIncome": [158e6 * (1.11 ** i) for i in range(n)],
    }

    current_price = 38.0 if undervalued else 120.0
    iv_corrected = 62.0 if undervalued else 62.0
    mos_pct = ((iv_corrected - current_price) / iv_corrected) * 100.0

    eod_fund = {
        "General": {"Sector": sector, "Industry": "Software", "CountryISO": "FR"},
        "Highlights": {"MarketCapitalization": current_price * 47_000_000.0, "DividendYield": 0.022},
        "Valuation": {"TrailingPE": 14.5, "ForwardPE": 13.0, "PriceBookMRQ": 2.4, "EnterpriseValueEbitda": 9.0},
        "Holders": {"InsidersPercentHeld": 0.06},
        "AnalystRatings": {"TargetPrice": 58.0, "Rating": 4.2},
    }
    if with_esg:
        eod_fund["ESGScores"] = {
            "TotalEsg": 71.0,
            "EnvironmentScore": 69.0,
            "SocialScore": 73.0,
            "GovernanceScore": 78.0,
        }

    capital_valuation = {
        "market_cap": current_price * 47_000_000.0,
        "enterprise_value": current_price * 47_000_000.0 - 50e6,
        "pe_ratio": 14.5,
        "forward_pe": 13.0,
        "price_to_book": 2.4,
        "price_to_sales": 1.9,
        "ev_to_ebitda": 9.0,
        "dividend_yield": 0.022,
        "beta": 0.95,
    }
    intrinsic_valuation = {
        "available": True,
        "summary": {
            "corrected": {
                "intrinsic_value": iv_corrected,
                "margin_of_safety_pct": mos_pct,
                "price_to_iv": current_price / iv_corrected,
            },
            "unclestock": {
                "intrinsic_value": iv_corrected * 0.95,
                "margin_of_safety_pct": mos_pct - 2.0,
                "price_to_iv": current_price / (iv_corrected * 0.95),
            },
        },
        "owner_returns": {"total_owner_return_pct": 6.4},
    }
    # Barres de cours sur ~260 séances pour alimenter momentum / volatilité
    bars = [{"date": f"2025-{1 + (i // 22):02d}-{1 + (i % 22):02d}", "close": 30.0 + (i * 0.03), "adj_close": 30.0 + (i * 0.03)} for i in range(260)]
    return {
        "ann_series": ann_series,
        "dates": dates,
        "current_price": current_price,
        "shares_override": 47_000_000.0,
        "eod_fund": eod_fund,
        "capital_valuation": capital_valuation,
        "intrinsic_valuation": intrinsic_valuation,
        "piotroski_score": 8,
        "bars": bars,
    }


def test_all_31_scores_present_and_dual_mode_differences():
    payload = compute_uncle_stock_scores(**_sample_healthy_inputs())
    assert payload["available"] is True
    assert payload["source_version"] == "unclestock-scores-v1"
    assert len(payload["items"]) == 31

    by_id = {item["id"]: item for item in payload["items"]}

    # Uncle Stock score : dénominateur 1540 (vérifié) vs 1420 (documenté + alerte)
    us = by_id["uncle_stock_score"]
    assert us["available"] is True
    assert us["documented"]["warnings"]
    assert not us["verified"]["warnings"]
    # À même raw_score clamped, documented > verified car /1420 > /1540
    assert us["documented"]["normalized_score"] >= us["verified"]["normalized_score"]

    # Yield score : dénominateur 2170 (vérifié) vs 1810 (documenté)
    ys = by_id["yield_score"]
    assert ys["available"] is True
    assert ys["documented"]["warnings"]
    assert not ys["verified"]["warnings"]
    assert ys["documented"]["normalized_score"] != ys["verified"]["normalized_score"]

    # Dechow F-Score : signe PV inversé en mode documenté
    dech = by_id["dechow_f_score"]
    assert dech["available"] is True
    assert dech["documented"]["warnings"]
    assert not dech["verified"]["warnings"]
    assert dech["verified"]["final_score"] != dech["documented"]["final_score"]

    # Scores factoriels et risques clés calculés proprement
    for sid in (
        "advice",
        "categories",
        "is_undervalued",
        "trap_score",
        "quality_score",
        "value_score",
        "balance_score",
        "balance_value_score",
        "financial_health_score",
        "growth_rate",
        "predictability_score",
        "piotroski_f_score",
        "mohanram_g_score",
        "montier_c_score",
        "levermann_score",
        "company_score",
        "oshaughnessy_vc3",
        "greenblatt_score",
        "pim_van_vliet_score",
        "erp5_score",
        "slater_score",
        "altman_z_score",
        "ohlson_o_score",
        "beneish_m_score",
        "esg_score",
        "environment_score",
        "social_score",
        "governance_score",
    ):
        assert sid in by_id
        assert by_id[sid]["verified"]["available"] is True

    assert by_id["is_undervalued"]["verified"]["final_score"] == 1.0
    assert by_id["trap_score"]["verified"]["final_score"] < 40.0
    assert "Strong Buy" in payload["summary"]["advice_verified"] or "Buy" in payload["summary"]["advice_verified"]


def test_esg_missing_and_financial_sector_trap_branch():
    inputs = _sample_healthy_inputs(sector="Financial Services", with_esg=False, undervalued=False)
    payload = compute_uncle_stock_scores(**inputs)
    by_id = {item["id"]: item for item in payload["items"]}

    for sid in ("esg_score", "environment_score", "social_score", "governance_score"):
        assert by_id[sid]["verified"]["available"] is False

    assert by_id["is_undervalued"]["verified"]["final_score"] == 0.0
    trap = by_id["trap_score"]
    assert trap["available"] is True
    # En mode vérifié, la branche Financial Services exclut la branche non-financière Altman Z
    assert not any("Altman" in c["name"] for c in trap["verified"]["components"])


def test_get_financial_dossier_embeds_uncle_stock_scores():
    from app.finance_dossier import get_financial_dossier

    inputs = _sample_healthy_inputs()
    overview = {
        "symbol": "TEST.PA",
        "eod_ticker": "TEST.PA",
        "yahoo_symbol": "TEST.PA",
        "name": "Test SA",
        "currency": "EUR",
        "exchange": "PA",
        "current_price": inputs["current_price"],
        "previous_close": 37.5,
        "change": 0.5,
        "change_pct": 1.33,
        "shares_outstanding": inputs["shares_override"],
        "capital_valuation": inputs["capital_valuation"],
        "eod_bars": inputs["bars"],
        "sources_used": ["EOD Historical Data"],
    }
    fund_payload = {
        **inputs["eod_fund"],
        "General": {"Code": "TEST", "Name": "Test SA", "Exchange": "PA", "CurrencyCode": "EUR", "CountryISO": "FR", "Sector": "Technology"},
        "SharesStats": {"SharesOutstanding": inputs["shares_override"]},
        "Financials": {
            "Income_Statement": {
                "yearly": {
                    d: {
                        "totalRevenue": inputs["ann_series"]["TotalRevenue"][i],
                        "grossProfit": inputs["ann_series"]["GrossProfit"][i],
                        "operatingIncome": inputs["ann_series"]["OperatingIncome"][i],
                        "ebitda": inputs["ann_series"]["EBITDA"][i],
                        "ebit": inputs["ann_series"]["EBIT"][i],
                        "netIncome": inputs["ann_series"]["NetIncome"][i],
                        "dilutedEps": inputs["ann_series"]["DilutedEPS"][i],
                        "researchDevelopment": inputs["ann_series"]["ResearchAndDevelopment"][i],
                        "sellingGeneralAdministrative": inputs["ann_series"]["SellingGeneralAndAdministration"][i],
                        "incomeBeforeTax": inputs["ann_series"]["PretaxIncome"][i],
                        "incomeTaxExpense": inputs["ann_series"]["TaxProvision"][i],
                    }
                    for i, d in enumerate(inputs["dates"])
                }
            },
            "Balance_Sheet": {
                "yearly": {
                    d: {
                        "totalAssets": inputs["ann_series"]["TotalAssets"][i],
                        "totalCurrentAssets": inputs["ann_series"]["CurrentAssets"][i],
                        "totalCurrentLiabilities": inputs["ann_series"]["CurrentLiabilities"][i],
                        "cashAndShortTermInvestments": inputs["ann_series"]["CashCashEquivalentsAndShortTermInvestments"][i],
                        "cash": inputs["ann_series"]["CashAndCashEquivalents"][i],
                        "netReceivables": inputs["ann_series"]["AccountsReceivable"][i],
                        "inventory": inputs["ann_series"]["Inventory"][i],
                        "propertyPlantAndEquipmentNet": inputs["ann_series"]["NetPPE"][i],
                        "goodWill": inputs["ann_series"]["GoodwillAndIntangibleAssets"][i],
                        "totalLiab": inputs["ann_series"]["TotalLiabilitiesNetMinorityInterest"][i],
                        "longTermDebt": inputs["ann_series"]["LongTermDebt"][i],
                        "shortLongTermDebtTotal": inputs["ann_series"]["TotalDebt"][i],
                        "netDebt": inputs["ann_series"]["NetDebt"][i],
                        "totalStockholderEquity": inputs["ann_series"]["StockholdersEquity"][i],
                        "retainedEarnings": inputs["ann_series"]["RetainedEarnings"][i],
                        "netWorkingCapital": inputs["ann_series"]["WorkingCapital"][i],
                        "commonStockSharesOutstanding": inputs["ann_series"]["CommonStockSharesOutstanding"][i],
                    }
                    for i, d in enumerate(inputs["dates"])
                }
            },
            "Cash_Flow": {
                "yearly": {
                    d: {
                        "totalCashFromOperatingActivities": inputs["ann_series"]["OperatingCashFlow"][i],
                        "capitalExpenditures": inputs["ann_series"]["CapitalExpenditure"][i],
                        "freeCashFlow": inputs["ann_series"]["FreeCashFlow"][i],
                        "dividendsPaid": inputs["ann_series"]["CashDividendsPaid"][i],
                        "salePurchaseOfStock": inputs["ann_series"]["RepurchaseOfCapitalStock"][i],
                        "netBorrowings": inputs["ann_series"]["IssuanceOfDebt"][i],
                        "depreciation": inputs["ann_series"]["DepreciationAndAmortization"][i],
                    }
                    for i, d in enumerate(inputs["dates"])
                }
            },
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "fin_scores",
            eod_historical_data_key="eod-test-key",
            demo_mode=False,
        )
        with (
            patch("app.finance_provider.fetch_eodhd_fundamentals_json", new=AsyncMock(return_value=fund_payload)),
            patch("app.finance_dossier._fetch_eodhd_bars_range", new=AsyncMock(return_value=inputs["bars"])),
            patch("app.finance_dossier._fetch_eodhd_dividends", new=AsyncMock(return_value=[{"date": "2025-05-12", "value": 0.52}])),
            patch("app.finance_dossier._fetch_yahoo_extended_summary", new=AsyncMock()),
            patch("app.finance_dossier._fetch_yahoo_chart_10y", new=AsyncMock()),
            patch("app.finance_dossier._sync_dossier_news", new=AsyncMock(return_value={"source": "Mock", "provider": "mock", "items": []})),
            patch("app.finance_dossier._sync_eodhd_extras", new=AsyncMock(return_value={})),
        ):
            dossier = asyncio.run(get_financial_dossier(s, "TEST.PA", refresh=False))

    scores = dossier.get("uncle_stock_scores")
    assert scores is not None
    assert scores["available"] is True
    assert len(scores["items"]) == 31
    assert scores["summary"]["uncle_stock_score_verified"] is not None
