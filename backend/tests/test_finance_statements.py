from app.finance_statements import build_period, is_valid_symbol, parse_timeseries


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
