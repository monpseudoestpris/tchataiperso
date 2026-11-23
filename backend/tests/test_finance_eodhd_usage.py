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


def test_eodhd_usage_persists_across_memory_reset(tmp_path):
    db_path = tmp_path / "finance_warehouse.db"
    usage.configure_usage_db(db_path)
    try:
        with usage._LOCK:
            usage._USAGE.clear()
            usage._USAGE_DAY = ""
        usage.record_eodhd_call("https://eodhd.com/api/eod/AI.PA?api_token=x")
        usage.record_eodhd_call("https://eodhd.com/api/fundamentals/AI.PA?api_token=x")

        # Simule un redémarrage du processus (cache RAM vidé)
        with usage._LOCK:
            usage._USAGE.clear()
            usage._USAGE_DAY = ""

        local = usage.get_local_usage()
        assert local["total_requests"] == 2
        assert local["total_calls"] == 11
    finally:
        usage.configure_usage_db(None)


def test_daily_sync_progress_persists_across_memory_reset(tmp_path):
    from app import finance_funds as funds

    db_path = tmp_path / "finance_warehouse.db"
    funds.configure_sync_state_db(db_path)
    try:
        funds._DAILY_SYNC_PROGRESS.clear()
        funds._DAILY_SYNC_PROGRESS.update(funds._DAILY_SYNC_PROGRESS_DEFAULT)
        funds._update_sync_progress(
            is_running=True,
            trigger="manual",
            phase="fundamentals",
            completed_steps=4,
            total_steps=10,
            last_message="Synchro en cours",
        )

        # Simule un redémarrage du processus (RAM réinitialisée)
        funds._DAILY_SYNC_PROGRESS.clear()
        funds._DAILY_SYNC_PROGRESS.update(funds._DAILY_SYNC_PROGRESS_DEFAULT)
        funds._DAILY_SYNC_RUNNING = False

        restored = funds.get_daily_sync_status()
        assert restored["phase"] == "fundamentals"
        assert restored["completed_steps"] == 4
        assert restored["percent"] == 40
        assert restored["is_running"] is False
    finally:
        funds.configure_sync_state_db(None)


def test_app_state_locks_prunes_idle_entries():
    import asyncio
    from types import SimpleNamespace
    from app import deps

    locks: dict[str, asyncio.Lock] = {f"u:{i}": asyncio.Lock() for i in range(deps._MAX_CONVERSATION_LOCKS)}
    active_lock = asyncio.Lock()
    asyncio.run(active_lock.acquire())
    locks["u:active"] = active_lock

    fake_req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(locks=locks)))
    new_lock = deps.claim(fake_req, "u", "new-conv")

    assert new_lock is locks["u:new-conv"]
    assert "u:active" in locks
    assert len(locks) == 2
    active_lock.release()
