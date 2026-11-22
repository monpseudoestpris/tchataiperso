"""Tests du suivi de consommation EODHD (`finance_eodhd_usage.py`)."""

from __future__ import annotations

from app import finance_eodhd_usage as usage


def test_endpoint_parsing_ignores_non_eodhd_urls():
    assert usage.endpoint_from_url("https://eodhd.com/api/fundamentals/AI.PA?api_token=x") == "fundamentals"
    assert usage.endpoint_from_url("https://eodhd.com/api/eod-bulk-last-day/PA?fmt=json") == "eod-bulk-last-day"
    assert usage.endpoint_from_url("https://query2.finance.yahoo.com/v8/finance/chart/AI.PA") is None
    assert usage.endpoint_from_url("https://evil.example/eodhd.com/api/eod/X") is None


def test_local_counter_applies_cost_table():
    with usage._LOCK:
        usage._USAGE.clear()
        usage._USAGE_DAY = ""
    for url in (
        "https://eodhd.com/api/eod/AI.PA?api_token=x",
        "https://eodhd.com/api/eod/MC.PA?api_token=x",
        "https://eodhd.com/api/fundamentals/AI.PA?api_token=x",
        "https://eodhd.com/api/eod-bulk-last-day/PA?api_token=x",
        "https://eodhd.com/api/user?api_token=x",  # Gratuit : non comptabilisé
        "https://query1.finance.yahoo.com/v8/finance/chart/AI.PA",  # Hors EODHD
    ):
        usage.record_eodhd_call(url)

    local = usage.get_local_usage()
    by_ep = {it["endpoint"]: it for it in local["by_endpoint"]}
    assert local["total_requests"] == 4
    assert local["total_calls"] == 2 * 1 + 10 + 100
    assert by_ep["eod-bulk-last-day"]["calls"] == 100
    assert local["by_endpoint"][0]["endpoint"] == "eod-bulk-last-day"  # Trié par coût décroissant


def test_daily_sync_estimate_uses_fundamentals_budget():
    prefs = {"full_data_exchanges": ["PA"], "screener_fundamentals": True, "fundamentals_budget_pct": 10}
    est = usage.estimate_daily_sync_cost(prefs, 100_000)
    calls = [line["calls"] for line in est["lines"]]
    assert calls == [100, 10_000 + 1]  # bulk Paris + budget 10 % (+ calendrier)
    assert est["max_daily_calls"] == 10_101
    assert est["light_load_calls"] == 11
