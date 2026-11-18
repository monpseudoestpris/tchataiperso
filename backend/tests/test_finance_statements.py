import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.finance_provider import (
    extract_eodhd_financial_stats,
    get_unified_financial_statements,
    merge_financial_stats,
)
from app.finance_statements import (
    build_period,
    extract_eodhd_earnings_history,
    is_valid_symbol,
    parse_eodhd_fundamentals_to_series,
    parse_timeseries,
)
from app.finance_warehouse import (
    get_snapshot,
    get_stored_eod_bars,
    get_warehouse_stats,
    load_fundamental_series,
    save_snapshot,
    upsert_eod_bars,
    warehouse_db_path,
)


def _series(type_name: str, values: dict[str, float]) -> dict:
    return {
        "meta": {"symbol": ["X"], "type": [type_name]},
        type_name: [{"asOfDate": d, "reportedValue": {"raw": v}} for d, v in values.items()],
    }


PAYLOAD = {
    "timeseries": {
        "result": [
            _series("annualTotalRevenue", {"2023-12-31": 100.0, "2024-12-31": 120.0}),
            _series("annualNetIncome", {"2023-12-31": 10.0, "2024-12-31": 18.0}),
            _series("annualStockholdersEquity", {"2023-12-31": 50.0, "2024-12-31": 60.0}),
        ]
    }
}

EOD_FUNDAMENTALS_SAMPLE = {
    "General": {
        "Code": "AI",
        "Exchange": "PA",
        "Name": "Air Liquide S.A.",
        "CurrencyCode": "EUR",
        "CountryName": "France",
        "ISIN": "FR0000120073",
        "Sector": "Basic Materials",
        "Industry": "Specialty Chemicals",
        "WebURL": "https://www.airliquide.com",
        "FullTimeEmployees": 67800,
    },
    "Highlights": {
        "MarketCapitalization": 95000000000,
        "EBITDA": 7800000000,
        "PERatio": 28.4,
        "PEGRatio": 2.1,
        "WallStreetTargetPrice": 195.0,
        "BookValue": 48.2,
        "DividendShare": 3.2,
        "DividendYield": 0.019,
        "EarningsShare": 5.9,
        "ProfitMargin": 0.125,
        "OperatingMarginTTM": 0.194,
        "ReturnOnAssetsTTM": 0.072,
        "ReturnOnEquityTTM": 0.145,
        "RevenueTTM": 27500000000,
        "GrossProfitTTM": 17000000000,
        "QuarterlyRevenueGrowthYOY": 0.041,
    },
    "Valuation": {
        "TrailingPE": 28.4,
        "ForwardPE": 24.1,
        "PriceBookMRQ": 3.5,
        "EnterpriseValue": 105000000000,
        "EnterpriseValueEbitda": 13.4,
    },
    "Technicals": {"Beta": 0.78, "52WeekHigh": 188.0, "52WeekLow": 152.0},
    "AnalystRatings": {"Rating": 4.2, "TargetPrice": 195.0, "StrongBuy": 6, "Buy": 10, "Hold": 4, "Sell": 1, "StrongSell": 0},
    "Financials": {
        "Income_Statement": {
            "currency_symbol": "EUR",
            "yearly": {
                f"{yr}-12-31": {
                    "date": f"{yr}-12-31",
                    "totalRevenue": str(20000000000 + i * 1000000000),
                    "costOfRevenue": str(8000000000 + i * 300000000),
                    "operatingIncome": str(3600000000 + i * 250000000),
                    "netIncome": str(2400000000 + i * 180000000),
                    "ebitda": str(5500000000 + i * 300000000),
                }
                for i, yr in enumerate(range(2016, 2026))
            },
            "quarterly": {
                "2025-03-31": {"date": "2025-03-31", "totalRevenue": "6900000000", "netIncome": "850000000"},
            },
        },
        "Balance_Sheet": {
            "yearly": {
                f"{yr}-12-31": {
                    "date": f"{yr}-12-31",
                    "totalAssets": "45000000000",
                    "totalCurrentAssets": "9000000000",
                    "totalCurrentLiabilities": "6000000000",
                    "cash": "2500000000",
                    "shortTermDebt": "1500000000",
                    "longTermDebt": "10500000000",
                    "totalStockholderEquity": "24000000000",
                }
                for yr in range(2016, 2026)
            },
            "quarterly": {},
        },
        "Cash_Flow": {
            "yearly": {
                f"{yr}-12-31": {
                    "date": f"{yr}-12-31",
                    "totalCashFromOperatingActivities": "6200000000",
                    "capitalExpenditures": "-3200000000",
                }
                for yr in range(2016, 2026)
            },
            "quarterly": {},
        },
    },
    "Earnings": {
        "History": {
            "2025-06-30": {
                "date": "2025-06-30",
                "reportDate": "2025-07-29",
                "currency": "EUR",
                "epsActual": 3.45,
                "epsEstimate": 3.30,
                "epsDifference": 0.15,
                "surprisePercent": 4.55,
            }
        }
    },
}


def test_parse_timeseries_strips_prefix():
    parsed = parse_timeseries(PAYLOAD, "annual")
    assert parsed["TotalRevenue"]["2024-12-31"] == 120.0


def test_build_period_computes_ratios():
    period = build_period(PAYLOAD, "annual")
    ratios = {r["key"]: r["values"] for r in period["ratios"]}
    assert period["dates"] == ["2023-12-31", "2024-12-31"]
    assert ratios["revenue_growth"] == [None, 20.0]
    assert ratios["net_margin"] == [10.0, 15.0]
    assert ratios["roe"] == [20.0, 30.0]
    assert "gross_margin" not in ratios  # donnée absente -> ratio omis


def test_build_period_empty_payload():
    period = build_period({}, "quarterly")
    assert period["dates"] == [] and period["ratios"] == []


def test_symbol_validation_rejects_injection():
    assert is_valid_symbol("AI.PA")
    assert not is_valid_symbol("AI.PA?x=1")
    assert not is_valid_symbol("../etc")


def test_parse_eodhd_fundamentals_full_history_and_derived_metrics():
    series = parse_eodhd_fundamentals_to_series(EOD_FUNDAMENTALS_SAMPLE, "annual")
    assert len(series["TotalRevenue"]) == 10  # 2016..2025 sans troncature
    assert series["TotalRevenue"]["2025-12-31"] == 29000000000.0
    assert series["GrossProfit"]["2025-12-31"] == 18300000000.0
    assert series["TotalDebt"]["2025-12-31"] == 12000000000.0
    assert series["NetDebt"]["2025-12-31"] == 9500000000.0
    assert series["WorkingCapital"]["2025-12-31"] == 3000000000.0
    assert series["FreeCashFlow"]["2025-12-31"] == 3000000000.0

    earnings = extract_eodhd_earnings_history(EOD_FUNDAMENTALS_SAMPLE)
    assert len(earnings) == 1
    assert earnings[0]["surprise_pct"] == 4.55


def test_merge_financial_stats_eod_priority_and_yahoo_fallback():
    eod_stats = extract_eodhd_financial_stats(EOD_FUNDAMENTALS_SAMPLE, {"close": 165.0})
    yahoo_stats = {
        "valuation": {"pe_trailing": "30.0", "market_cap": "90 Mrd"},
        "profitability": {"total_revenue": "25 Mrd"},
        "balance_sheet": {"total_cash": "2.0 Mrd"},
        "analysts": {"recommendation": "HOLD", "target_high": "210.00", "target_low": "155.00"},
        "profile": {"sector": "Other"},
    }
    merged, src = merge_financial_stats(eod_stats, yahoo_stats)
    assert src == "eodhd+yahoo"
    assert merged["valuation"]["pe_trailing"] == "28.40"
    assert merged["analysts"]["recommendation"] == "BUY"
    assert merged["analysts"]["target_high"] == "210.00"
    assert merged["analysts"]["target_low"] == "155.00"


def test_warehouse_persistence_and_unified_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "finance_vol",
            eod_historical_data_key="eod-test-key",
            demo_mode=False,
        )
        db_path = warehouse_db_path(settings)
        upsert_eod_bars(
            db_path,
            "AI.PA",
            [
                {"date": "2026-11-12", "open": 170.0, "high": 172.0, "low": 169.0, "close": 171.5, "volume": 500000},
                {"date": "2026-11-13", "open": 171.5, "high": 175.0, "low": 171.0, "close": 174.0, "volume": 610000},
            ],
            "eodhd",
        )
        bars = get_stored_eod_bars(db_path, "AI.PA")
        assert len(bars) == 2 and bars[-1]["close"] == 174.0

        save_snapshot(db_path, "TEST.PA", "eodhd", "probe", {"big": list(range(50))}, {"ok": True}, currency="EUR")
        snap = get_snapshot(db_path, "TEST.PA", "probe", include_raw=True)
        assert snap is not None and snap["raw"]["big"][-1] == 49

        with patch("app.finance_provider.fetch_eodhd_fundamentals_json", new=AsyncMock(return_value=EOD_FUNDAMENTALS_SAMPLE)) as mock_eod, \
             patch("app.finance_provider.fetch_yahoo_timeseries_bundle", new=AsyncMock(return_value=({}, {}))) as mock_yah:
            res1 = asyncio.run(get_unified_financial_statements(settings, "AI.PA", refresh=False))
            assert res1["source_provider"] == "eodhd"
            assert res1["cached"] is False
            assert len(res1["annual"]["dates"]) == 10
            assert mock_eod.await_count == 1
            assert mock_yah.await_count == 0

            # Second call hits local warehouse cache without calling external APIs
            res2 = asyncio.run(get_unified_financial_statements(settings, "AI.PA", refresh=False))
            assert res2["cached"] is True
            assert len(res2["annual"]["dates"]) == 10
            assert mock_eod.await_count == 1

            stats = get_warehouse_stats(db_path, "AI.PA")
            assert stats["annual_periods_count"] == 10
            assert stats["eod_bars_count"] == 2

        # Fallback to Yahoo Finance when EODHD key is absent
        yahoo_only_settings = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "finance_vol_yah",
            eod_historical_data_key="",
            demo_mode=False,
        )
        with patch("app.finance_provider.fetch_yahoo_timeseries_bundle", new=AsyncMock(return_value=(PAYLOAD, {}))):
            res_yah = asyncio.run(get_unified_financial_statements(yahoo_only_settings, "AI.PA", refresh=False))
            assert res_yah["source_provider"] == "yahoo_finance"
            assert res_yah["annual"]["dates"] == ["2023-12-31", "2024-12-31"]
            stored_series, _, _, _ = load_fundamental_series(warehouse_db_path(yahoo_only_settings), "AI.PA", "annual")
            assert stored_series["TotalRevenue"]["2024-12-31"] == 120.0


def test_all_eodhd_fields_and_yahoo_empty_placeholders():
    rich_eod = {
        **EOD_FUNDAMENTALS_SAMPLE,
        "Financials": {
            "Income_Statement": {
                "currency_symbol": "EUR",
                "yearly": {
                    "2025-12-31": {
                        **EOD_FUNDAMENTALS_SAMPLE["Financials"]["Income_Statement"]["yearly"]["2025-12-31"],
                        "otherOperatingExpenses": "450000000",
                        "loanLossProvision": "12000000",
                    }
                },
            },
            "Balance_Sheet": {
                "yearly": {
                    "2025-12-31": {
                        **EOD_FUNDAMENTALS_SAMPLE["Financials"]["Balance_Sheet"]["yearly"]["2025-12-31"],
                        "goodWill": "1800000000",
                        "intangibleAssets": "700000000",
                        "treasuryStock": "-500000000",
                        "customCapitalReserve": "95000000",
                    }
                },
            },
            "Cash_Flow": {
                "yearly": {
                    "2025-12-31": {
                        **EOD_FUNDAMENTALS_SAMPLE["Financials"]["Cash_Flow"]["yearly"]["2025-12-31"],
                        "effectOfExchangeRateChanges": "-35000000",
                        "changeToInventory": "-80000000",
                    }
                },
            },
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "fin_all_eod",
            eod_historical_data_key="eod-test-key",
            demo_mode=False,
        )
        with patch("app.finance_provider.fetch_eodhd_fundamentals_json", new=AsyncMock(return_value=rich_eod)):
            res = asyncio.run(get_unified_financial_statements(settings, "AI.PA", refresh=False))

        inc_map = {r["key"]: r for r in res["annual"]["income"]}
        bal_map = {r["key"]: r for r in res["annual"]["balance"]}
        cf_map = {r["key"]: r for r in res["annual"]["cashflow"]}

        assert inc_map["eod_income_otherOperatingExpenses"]["values"][-1] == 450000000.0
        assert inc_map["eod_income_loanLossProvision"]["values"][-1] == 12000000.0
        assert bal_map["eod_balance_goodWill"]["values"][-1] == 1800000000.0
        assert bal_map["eod_balance_intangibleAssets"]["values"][-1] == 700000000.0
        assert bal_map["eod_balance_treasuryStock"]["values"][-1] == -500000000.0
        assert bal_map["eod_balance_customCapitalReserve"]["values"][-1] == 95000000.0
        assert cf_map["eod_cashflow_effectOfExchangeRateChanges"]["values"][-1] == -35000000.0
        assert cf_map["eod_cashflow_changeToInventory"]["values"][-1] == -80000000.0

        # Sous Yahoo Finance sans clé EODHD : mêmes lignes standard présentes avec valeurs None (vides)
        yah_settings = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "fin_all_yah",
            eod_historical_data_key="",
            demo_mode=False,
        )
        with patch("app.finance_provider.fetch_yahoo_timeseries_bundle", new=AsyncMock(return_value=(PAYLOAD, {}))):
            res_yah = asyncio.run(get_unified_financial_statements(yah_settings, "AI.PA", refresh=False))
        bal_yah = {r["key"]: r for r in res_yah["annual"]["balance"]}
        assert "eod_balance_treasuryStock" in bal_yah
        assert bal_yah["eod_balance_treasuryStock"]["values"] == [None, None]
        assert "eod_balance_customCapitalReserve" not in bal_yah


def test_dossier_performance_risk_scores_and_dividends():
    import datetime
    from app.finance_dossier import (
        _build_dividends_matrix,
        compute_price_performance_and_risk,
        get_financial_dossier,
    )

    # 1. Synthetic 6-year daily bar series with upward trend
    start = datetime.date(2020, 1, 2)
    bars = []
    price = 100.0
    for d_off in range(2200):
        cur = start + datetime.timedelta(days=d_off)
        if cur.weekday() >= 5:
            continue
        price *= 1.0005 if (d_off % 7 != 0) else 0.9985
        bars.append({"date": cur.isoformat(), "close": round(price, 2), "adjusted_close": round(price * 1.02, 2)})

    perf, risk, chart = compute_price_performance_and_risk(bars, currency="USD")
    perf_map = {h["key"]: h["pct"] for h in perf["horizons"]}
    assert perf_map["1y"] is not None and perf_map["5y"] is not None
    assert len(chart) >= 50
    risk_map = {m["key"]: m["values"] for m in risk["metrics"]}
    assert risk_map["volatility"][0] is not None
    assert risk_map["sharpe"][0] is not None
    assert risk_map["max_drawdown"][0] is not None

    # 2. Dividends matrix (monthly Jan..Dec + total)
    div_mat = _build_dividends_matrix([
        {"date": "2025-02-10", "value": 0.25},
        {"date": "2025-05-12", "value": 0.26},
        {"date": "2025-08-11", "value": 0.26},
        {"date": "2025-11-10", "value": 0.26},
    ])
    assert div_mat["years"] == [2025]
    assert div_mat["rows"][0]["months"][1] == 0.25  # Feb
    assert div_mat["rows"][0]["total"] == 1.03

    # 3. Full dossier integration with mocked EODHD fundamentals, bars, and dividends
    rich_eod = {
        **EOD_FUNDAMENTALS_SAMPLE,
        "General": {
            **EOD_FUNDAMENTALS_SAMPLE["General"],
            "Officers": {"0": {"Name": "François Jackow", "Title": "CEO", "YearBorn": "1969"}},
        },
        "InsiderTransactions": {
            "0": {
                "date": "2026-10-15",
                "ownerName": "Jackow F.",
                "ownerTitle": "CEO",
                "transactionCode": "P",
                "transactionAcquiredDisposed": "A",
                "transactionAmount": 1000,
                "transactionPrice": 175.0,
            }
        },
        "Holders": {
            "Funds": {"0": {"name": "Vanguard Global Fund", "date": "2026-09-30", "currentShares": 5000000, "totalAssets": 3.2, "change_p": 1.5}},
            "Institutions": {"0": {"name": "BlackRock Inc.", "date": "2026-09-30", "currentShares": 12000000, "totalAssets": 4.8, "change_p": 0.8}},
        },
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            _env_file=None,
            app_data_dir=Path(tmpdir),
            finance_data_dir=Path(tmpdir) / "fin_dossier",
            eod_historical_data_key="eod-test-key",
            demo_mode=False,
        )
        with patch("app.finance_provider.fetch_eodhd_fundamentals_json", new=AsyncMock(return_value=rich_eod)), \
             patch("app.finance_dossier._fetch_eodhd_bars_range", new=AsyncMock(return_value=bars)), \
             patch("app.finance_dossier._fetch_eodhd_dividends", new=AsyncMock(return_value=[{"date": "2025-05-12", "value": 3.2}])), \
             patch("app.finance_dossier._fetch_yahoo_extended_summary", new=AsyncMock()) as mock_y_ext, \
             patch("app.finance_dossier._fetch_yahoo_chart_10y", new=AsyncMock()) as mock_y_chart:
            dossier = asyncio.run(get_financial_dossier(settings, "AI.PA", refresh=False))
            mock_y_ext.assert_not_called()
            mock_y_chart.assert_not_called()

    assert dossier["header"]["ih_score"] is not None
    assert dossier["stakeholders"]["officers"][0]["name"] == "François Jackow"
    assert dossier["stakeholders"]["insiders"][0]["action"] == "Achat"
    assert dossier["stakeholders"]["funds"][0]["name"] == "Vanguard Global Fund"
    assert dossier["annual_tables"]["piotroski"]["latest_score"] is not None
    assert len(dossier["annual_tables"]["summary"]) >= 10
    assert dossier["dividends_matrix"]["years"] == [2025]

    # 4. Deduplication of two annual dates within the same calendar year
    from app.finance_dossier import _compute_annual_dossier_tables

    dup_tables = _compute_annual_dossier_tables(
        {
            "TotalRevenue": {"2025-09-27": 391000000000.0, "2026-06-30": 450000000000.0, "2026-09-26": 478000000000.0},
            "NetIncome": {"2025-09-27": 93000000000.0, "2026-06-30": 120000000000.0},
        },
        bars=[],
        beta_val=1.1,
    )
    assert dup_tables["years"] == ["2025", "2026"]
    rev_row = next(r for r in dup_tables["summary"] if r["key"] == "rev")
    ni_row = next(r for r in dup_tables["summary"] if r["key"] == "ni")
    assert rev_row["values"] == [391000000000.0, 478000000000.0]
    assert ni_row["values"] == [93000000000.0, 120000000000.0]

    # 5. NVIDIA-like 52-week fiscal calendar (Jan 25..30 vs Earnings.Annual Jan 31) + zero interest expense
    nvda_eod = {
        "Financials": {
            "Income_Statement": {
                "yearly": {
                    "2022-01-30": {"date": "2022-01-30", "totalRevenue": "26914000000", "costOfRevenue": "9439000000", "operatingIncome": "10041000000", "ebitda": "11215000000", "incomeBeforeTax": "9941000000", "incomeTaxExpense": "189000000", "netIncome": "9752000000"},
                    "2023-01-29": {"date": "2023-01-29", "totalRevenue": "26974000000", "costOfRevenue": "11618000000", "operatingIncome": "4224000000", "ebitda": "5768000000", "incomeBeforeTax": "4181000000", "incomeTaxExpense": "-187000000", "netIncome": "4368000000"},
                    "2024-01-28": {"date": "2024-01-28", "totalRevenue": "60922000000", "costOfRevenue": "16621000000", "operatingIncome": "32972000000", "ebitda": "34480000000", "incomeBeforeTax": "33818000000", "incomeTaxExpense": "4058000000", "netIncome": "29760000000"},
                    "2025-01-26": {"date": "2025-01-26", "totalRevenue": "130497000000", "costOfRevenue": "32639000000", "operatingIncome": "81453000000", "ebitda": "83317000000", "incomeBeforeTax": "84026000000", "incomeTaxExpense": "11146000000", "netIncome": "72880000000"},
                    "2026-01-25": {"date": "2026-01-25", "totalRevenue": "180000000000", "costOfRevenue": "43000000000", "operatingIncome": "112000000000", "ebitda": "115000000000", "incomeBeforeTax": "115000000000", "incomeTaxExpense": "16000000000", "netIncome": "99000000000"},
                }
            },
            "Balance_Sheet": {
                "yearly": {
                    "2022-01-30": {"date": "2022-01-30", "totalAssets": "44187000000", "totalCurrentAssets": "28829000000", "totalCurrentLiabilities": "4335000000", "cash": "1990000000", "totalStockholderEquity": "26612000000", "commonStockSharesOutstanding": "25060000000"},
                    "2023-01-29": {"date": "2023-01-29", "totalAssets": "41182000000", "totalCurrentAssets": "23073000000", "totalCurrentLiabilities": "6563000000", "cash": "3389000000", "totalStockholderEquity": "22101000000", "commonStockSharesOutstanding": "24661000000"},
                    "2024-01-28": {"date": "2024-01-28", "totalAssets": "65728000000", "totalCurrentAssets": "44345000000", "totalCurrentLiabilities": "10631000000", "cash": "7280000000", "totalStockholderEquity": "42978000000", "commonStockSharesOutstanding": "24640000000"},
                    "2025-01-26": {"date": "2025-01-26", "totalAssets": "111601000000", "totalCurrentAssets": "80126000000", "totalCurrentLiabilities": "18047000000", "cash": "8589000000", "totalStockholderEquity": "79327000000", "commonStockSharesOutstanding": "24477000000"},
                    "2026-01-25": {"date": "2026-01-25", "totalAssets": "155000000000", "totalCurrentAssets": "115000000000", "totalCurrentLiabilities": "22000000000", "cash": "15000000000", "totalStockholderEquity": "118000000000", "commonStockSharesOutstanding": "24300000000"},
                }
            },
            "Cash_Flow": {
                "yearly": {
                    "2022-01-30": {"date": "2022-01-30", "totalCashFromOperatingActivities": "9108000000", "capitalExpenditures": "-976000000"},
                    "2023-01-29": {"date": "2023-01-29", "totalCashFromOperatingActivities": "5641000000", "capitalExpenditures": "-1833000000"},
                    "2024-01-28": {"date": "2024-01-28", "totalCashFromOperatingActivities": "28090000000", "capitalExpenditures": "-1069000000"},
                    "2025-01-26": {"date": "2025-01-26", "totalCashFromOperatingActivities": "64089000000", "capitalExpenditures": "-3236000000"},
                    "2026-01-25": {"date": "2026-01-25", "totalCashFromOperatingActivities": "85000000000", "capitalExpenditures": "-4000000000"},
                }
            },
        },
        "Earnings": {
            "Annual": {
                "2022-01-31": {"date": "2022-01-31", "epsActual": 0.44},
                "2023-01-31": {"date": "2023-01-31", "epsActual": 0.33},
                "2024-01-31": {"date": "2024-01-31", "epsActual": 1.30},
                "2025-01-31": {"date": "2025-01-31", "epsActual": 2.99},
                "2026-01-31": {"date": "2026-01-31", "epsActual": 4.05},
            }
        },
    }
    nvda_series = parse_eodhd_fundamentals_to_series(nvda_eod, "annual")
    assert sorted(nvda_series["DilutedEPS"].keys()) == [
        "2022-01-30", "2023-01-29", "2024-01-28", "2025-01-26", "2026-01-25"
    ]
    nvda_tables = _compute_annual_dossier_tables(nvda_series, bars=[], beta_val=2.1)
    assert nvda_tables["years"] == ["2022", "2023", "2024", "2025", "2026"]
    assert nvda_tables["ih_score"]["latest_score"] >= 5.5
    assert nvda_tables["piotroski"]["scores"][-1] >= 5
    assert nvda_tables["piotroski"]["scores"][-2] >= 7


def test_resolve_gemini_hydrogen_model():
    from app.finance_dossier import _resolve_gemini_hydrogen_model

    s = Settings(
        _env_file=None,
        llm_models='[{"id":"openai/gpt-4o-mini","name":"GPT-4o mini"},{"id":"google/gemini-4-hydrogen-lite","name":"Gemini 4 Hydrogen Lite"},{"id":"google/gemini-4-hydrogen","name":"Gemini 4 Hydrogen"}]',
        default_model="openai/gpt-4o-mini",
        demo_mode=True,
    )
    assert _resolve_gemini_hydrogen_model(s) == "google/gemini-4-hydrogen"
    assert _resolve_gemini_hydrogen_model(s, "custom/model") == "custom/model"


def test_generate_dossier_ai_analysis_calls_llm_without_key_typeerror():
    import httpx
    from unittest.mock import MagicMock
    from app.finance_dossier import generate_dossier_ai_analysis

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(
            _env_file=None,
            finance_data_dir=tmpdir,
            llm_api_key="test-openrouter-key",
            llm_base_url="https://openrouter.ai/api/v1",
            llm_models='[{"id":"openai/gpt-4o-mini","name":"GPT-4o mini"},{"id":"google/gemini-4-hydrogen","name":"Gemini 4 Hydrogen"}]',
            default_model="openai/gpt-4o-mini",
            demo_mode=False,
        )
        fake_dossier = {
            "symbol": "NVDA.US",
            "currency": "USD",
            "header": {
                "name": "NVIDIA Corp",
                "cap_category": "Méga-Cap",
                "market_cap": 3500000000000.0,
                "sector": "Technology",
                "industry": "Semiconductors",
                "ih_score": 6.8,
                "ih_trend": "stable",
                "price_dynamics": "Positif",
                "dividend_yield_pct": 0.03,
                "beta": 2.1,
                "employees": 36000,
                "description": "GPU & AI computing leader.",
            },
            "capital_valuation": {"pe_ttm": 45.0, "ev_ebitda": 38.0, "op_margin_ttm": 62.0},
            "performance": {"horizons": [{"label": "1A", "pct": 42.5}]},
            "risk": {"horizons": ["1A"], "metrics": [{"label": "Volatilité", "values": [38.0]}]},
            "stakeholders": {
                "analysts": {"rating": "Achat", "target_price": 180.0},
                "officers": [{"name": "Jensen Huang", "title": "CEO"}],
                "insiders": [],
                "insiders_net_amount": None,
                "institutions": [],
                "funds": [],
            },
            "annual_tables": {
                "years": ["2025", "2026"],
                "summary": [],
                "profitability": [],
                "solvency": [],
                "distribution": [],
                "efficiency": [],
                "ih_score": {"years": ["2025", "2026"], "latest_score": 6.8, "trend": "stable", "scores": [6.5, 6.8]},
                "piotroski": {"years": ["2025", "2026"], "latest_score": 7, "scores": [8, 7]},
                "altman": {"years": ["2025", "2026"], "latest_score": 12.4, "scores": [10.2, 12.4]},
            },
            "dividends_matrix": {"rows": []},
            "statements": {
                "annual": {
                    "dates": ["2025-01-26", "2026-01-25"],
                    "income": [{"key": "TotalRevenue", "label": "Chiffre d'affaires", "values": [130.5e9, 180.0e9]}],
                    "balance": [{"key": "NetDebt", "label": "Dette nette", "values": [-10e9, -15e9]}],
                    "cashflow": [{"key": "FreeCashFlow", "label": "Free Cash Flow", "values": [60.8e9, 81.0e9]}],
                },
                "quarterly": {"dates": ["2026-01-25"], "income": []},
                "earnings_history": [],
            },
            "news": {
                "source": "EOD Historical Data",
                "provider": "eodhd",
                "items": [
                    {
                        "title": "NVIDIA Blackwell demand accelerates",
                        "url": "https://example.com/nvda-news",
                        "source": "reuters.com",
                        "published_at": "2026-11-16 14:00",
                        "snippet": "Strong datacenter backlog.",
                        "sentiment": {"polarity": 0.72},
                    }
                ],
            },
        }

        captured: dict = {}

        def _make_resp(*args, **kwargs):
            captured["url"] = args[0] if args else kwargs.get("url")
            captured["headers"] = kwargs.get("headers")
            captured["json"] = kwargs.get("json")
            req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            return httpx.Response(
                200,
                request=req,
                json={"choices": [{"message": {"content": "### Synthèse NVDA\n\n- Solide."}}]},
            )

        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        fake_client.post = AsyncMock(side_effect=_make_resp)

        with (
            patch("app.finance_dossier.get_financial_dossier", new=AsyncMock(return_value=fake_dossier)),
            patch("app.config.Settings.get_models", return_value=s.configured_models),
            patch("app.finance_dossier.httpx.AsyncClient", return_value=fake_client),
        ):
            res = asyncio.run(generate_dossier_ai_analysis(s, "NVDA.US"))

        assert res["model"] == "google/gemini-4-hydrogen"
        assert "Synthèse NVDA" in res["markdown"]
        assert captured["headers"]["Authorization"] == "Bearer test-openrouter-key"
        assert captured["json"]["model"] == "google/gemini-4-hydrogen"
        assert captured["json"]["max_tokens"] == 16384
        sent_prompt = captured["json"]["messages"][0]["content"]
        assert "ANALYSTE FINANCIER D'ÉLITE" in sent_prompt
        assert "APPROCHE BUFFETT" in sent_prompt
        assert "APPROCHE DAMODARAN" in sent_prompt
        assert "RED FLAGS" in sent_prompt
        assert "Jensen Huang" in sent_prompt
        assert "180000000000.0" in sent_prompt
        assert "NVIDIA Blackwell demand accelerates" in sent_prompt


def test_dossier_news_eodhd_priority_and_yahoo_backup():
    from app.finance_dossier import _sync_dossier_news

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(_env_file=None, finance_data_dir=tmpdir, demo_mode=False)
        db_path = warehouse_db_path(s)
        eod_sample = [
            {
                "title": "EOD News Item",
                "url": "https://example.com/eod-news",
                "source": "example.com",
                "published_at": "2026-11-17 10:00",
                "snippet": "EOD content",
                "tags": ["EARNINGS"],
                "sentiment": {"polarity": 0.4},
            }
        ]
        yahoo_mock = AsyncMock(return_value=[])
        with (
            patch("app.finance_dossier.fetch_eodhd_news", new=AsyncMock(return_value=eod_sample)) as eod_mock,
            patch("app.finance_dossier.fetch_yahoo_symbol_news", new=yahoo_mock),
        ):
            res = asyncio.run(
                _sync_dossier_news(s, db_path, "NVDA.US", "NVDA", "fake-eod-key", 3600, refresh=True)
            )
        assert res["provider"] == "eodhd"
        assert res["source"] == "EOD Historical Data"
        assert len(res["items"]) == 1
        assert res["items"][0]["title"] == "EOD News Item"
        eod_mock.assert_called_once()
        yahoo_mock.assert_not_called()

        # Backup Yahoo si EODHD indisponible (None)
        y_sample = [
            {
                "title": "Yahoo Backup Item",
                "url": "https://finance.yahoo.com/news/item1",
                "source": "Reuters",
                "published_at": "2026-11-17 09:00 UTC",
                "snippet": "",
            }
        ]
        with (
            patch("app.finance_dossier.fetch_eodhd_news", new=AsyncMock(return_value=None)),
            patch("app.finance_dossier.fetch_yahoo_symbol_news", new=AsyncMock(return_value=y_sample)),
        ):
            res2 = asyncio.run(
                _sync_dossier_news(s, db_path, "NVDA.US", "NVDA", "fake-eod-key", 3600, refresh=True)
            )
        assert res2["provider"] == "yahoo_finance"
        assert res2["items"][0]["title"] == "Yahoo Backup Item"


def test_eodhd_extras_sync_and_logo_resolution():
    from app.finance_dossier import _sync_eodhd_extras
    from app.finance_eodhd_extras import resolve_country_iso3, resolve_eodhd_logo_url

    fund_sample = {"General": {"LogoURL": "/img/logos/US/NVDA.png", "CountryISO": "US", "Code": "NVDA", "Exchange": "US"}}
    assert resolve_eodhd_logo_url(fund_sample, "NVDA.US") == "https://eodhd.com/img/logos/US/NVDA.png"
    assert resolve_country_iso3(fund_sample, "NVDA.US") == "USA"
    assert resolve_country_iso3(None, "AI.PA") == "FRA"

    with tempfile.TemporaryDirectory() as tmpdir:
        s = Settings(_env_file=None, finance_data_dir=tmpdir, demo_mode=False)
        db_path = warehouse_db_path(s)
        with (
            patch("app.finance_dossier.fetch_eodhd_sentiments", new=AsyncMock(return_value={"avg_normalized": 0.42, "latest_normalized": 0.5, "latest_date": "2026-11-17", "article_count": 38, "days_covered": 30, "series": []})),
            patch("app.finance_dossier.fetch_eodhd_historical_mcap", new=AsyncMock(return_value={"latest_value": 3.5e12, "latest_date": "2026-11-14", "min_value": 4e11, "max_value": 3.6e12, "points": []})),
            patch("app.finance_dossier.fetch_eodhd_earnings_calendar", new=AsyncMock(return_value=[{"report_date": "2026-11-19", "fiscal_date": "2026-10-31", "timing": "AfterMarket", "currency": "USD", "estimate": 0.75, "actual": None, "difference": None, "surprise_pct": None}])),
            patch("app.finance_dossier.fetch_eodhd_insider_transactions", new=AsyncMock(return_value=[{"date": "2026-11-10", "name": "Jensen Huang", "relation": "CEO", "action": "Vente", "shares": 10000.0, "price": 140.0, "amount": 1400000.0, "signed_amount": -1400000.0}])),
            patch("app.finance_dossier.fetch_eodhd_macro_context", new=AsyncMock(return_value={"country_iso3": "USA", "country_name": "United States", "gdp_growth_pct": {"value": 2.8, "date": "2025-12-31"}, "inflation_pct": None, "unemployment_pct": None, "us_treasury": {"date": "2026-11-14", "rate_52w_pct": 4.25, "rate_13w_pct": 4.4, "rate_4wk_pct": 4.5, "risk_free_pct": 4.25}})),
        ):
            extras = asyncio.run(_sync_eodhd_extras(s, db_path, "NVDA.US", fund_sample, "fake-key", 3600, refresh=True))

        assert extras["sentiments"]["avg_normalized"] == 0.42
        assert extras["historical_mcap"]["latest_value"] == 3.5e12
        assert extras["earnings_calendar"][0]["report_date"] == "2026-11-19"
        assert extras["insider_transactions"][0]["name"] == "Jensen Huang"
        assert extras["macro_context"]["us_treasury"]["risk_free_pct"] == 4.25

        # Vérifie la relecture depuis le cache SQLite sans nouvel appel réseau
        with (
            patch("app.finance_dossier.fetch_eodhd_sentiments", side_effect=AssertionError("should use cache")),
            patch("app.finance_dossier.fetch_eodhd_historical_mcap", side_effect=AssertionError("should use cache")),
            patch("app.finance_dossier.fetch_eodhd_earnings_calendar", side_effect=AssertionError("should use cache")),
            patch("app.finance_dossier.fetch_eodhd_insider_transactions", side_effect=AssertionError("should use cache")),
            patch("app.finance_dossier.fetch_eodhd_macro_context", side_effect=AssertionError("should use cache")),
        ):
            cached_extras = asyncio.run(_sync_eodhd_extras(s, db_path, "NVDA.US", fund_sample, "fake-key", 3600, refresh=False))
        assert cached_extras["sentiments"]["article_count"] == 38
        assert cached_extras["macro_context"]["us_treasury"]["rate_52w_pct"] == 4.25


def test_news_endpoint_includes_eodhd_feed_and_cache(tmp_path: Path):
    from tests.test_api import authenticated_client

    s = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        finance_data_dir=tmp_path / "finance",
        demo_mode=False,
        eod_historical_data_key="fake-eod-key",
        openrouter_api_key="",
        brave_api_key="",
        duckduckgo_instant_answers_enabled=False,
    )
    eod_sample = [
        {
            "title": "Air Liquide signe un contrat majeur hydrogène",
            "url": "https://example.com/news/ai-h2",
            "source": "example.com",
            "date": "2026-11-18 10:00",
            "published_at": "2026-11-18 10:00",
            "snippet": "Nouveau contrat de long terme en Europe.",
            "tags": ["HYDROGEN", "EARNINGS"],
            "sentiment": {"polarity": 0.62, "pos": 0.7, "neu": 0.25, "neg": 0.05},
        }
    ]
    with authenticated_client(s) as client:
        with patch("app.finance_news.fetch_eodhd_news", new=AsyncMock(return_value=eod_sample)) as mock_eod:
            res1 = client.get("/api/finance/news?symbol=AI.PA")
        assert res1.status_code == 200
        body1 = res1.json()
        assert body1["items"] == []
        assert body1["feed"] is not None
        assert body1["feed"]["provider"] == "eodhd"
        assert body1["feed"]["items"][0]["title"] == "Air Liquide signe un contrat majeur hydrogène"
        assert body1["feed"]["items"][0]["tags"] == ["HYDROGEN", "EARNINGS"]
        assert body1["feed"]["items"][0]["sentiment"]["polarity"] == 0.62
        assert mock_eod.await_count == 1

        # 2e appel sans refresh -> 0 appel réseau grâce au cache entrepôt 6h
        with patch("app.finance_news.fetch_eodhd_news", side_effect=AssertionError("Doit utiliser le cache")):
            res2 = client.get("/api/finance/news?symbol=AI.PA")
        assert res2.status_code == 200
        assert res2.json()["feed"]["items"][0]["title"] == "Air Liquide signe un contrat majeur hydrogène"

        # refresh=true -> re-télécharge
        with patch("app.finance_news.fetch_eodhd_news", new=AsyncMock(return_value=eod_sample)) as mock_ref:
            res3 = client.get("/api/finance/news?symbol=AI.PA&refresh=true")
        assert res3.status_code == 200
        assert mock_ref.await_count == 1
