"""Tests de la file des fondamentaux (`finance_fundamentals_queue.py`)."""

from __future__ import annotations

import datetime
from pathlib import Path

from app.config import Settings
from app.finance_fundamentals_queue import (
    boost_symbols,
    compute_next_due,
    enqueue_symbols,
    extract_schedule_signals,
    get_symbol_schedule,
    is_fresh_by_schedule,
    mark_reported,
    queue_stats,
    record_failure,
    record_fetch,
    reset_source_priorities,
    select_due_batch,
)
from app.finance_warehouse import upsert_screener_snapshots, warehouse_db_path

D = datetime.date


def _db(tmp_path: Path) -> Path:
    return warehouse_db_path(Settings(app_data_dir=tmp_path / "a", finance_data_dir=tmp_path / "f", demo_mode=True))


def _payload(period_dates: list[str], report_dates: list[str] | None = None) -> dict:
    return {
        "General": {"Code": "X", "CurrencyCode": "EUR"},
        "Financials": {"Income_Statement": {"quarterly": {d: {"date": d, "totalRevenue": "1"} for d in period_dates}}},
        "Earnings": {"History": {rd: {"reportDate": rd, "date": rd} for rd in (report_dates or [])}},
    }


def test_extract_signals_detects_cadence_and_report_season():
    q = extract_schedule_signals(_payload(["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]))
    assert q["period_end"] == "2026-09-30" and q["cadence"] == "quarterly"

    s = extract_schedule_signals(
        _payload(["2024-12-31", "2025-06-30", "2025-12-31", "2026-06-30"], ["2025-07-28", "2026-01-29", "2026-07-27"])
    )
    assert s["cadence"] == "semiannual"
    assert s["last_report_date"] == "2026-07-27"
    assert (1, 29) in s["typical_report_days"] and (7, 27) in s["typical_report_days"]


def test_compute_next_due_rules():
    # Saison habituelle de publication (fin janvier) + 3 jours de délai d'intégration
    due = compute_next_due(fetched_on=D(2026, 8, 1), period_end="2026-06-30", cadence="semiannual", typical_report_days=[(1, 29), (7, 27)])
    assert due == D(2027, 2, 1)
    # Repli sur la fin de période : trimestriel = +130 j (+3), plafonné à 120 j après le chargement
    due_q = compute_next_due(fetched_on=D(2026, 11, 1), period_end="2026-09-30", cadence="quarterly")
    assert due_q == D(2027, 2, 10)
    due_cap = compute_next_due(fetched_on=D(2026, 11, 1), period_end="2026-03-31", cadence="semiannual")
    assert due_cap >= D(2026, 11, 21)  # Jamais moins de 20 jours
    assert compute_next_due(fetched_on=D(2026, 11, 1), period_end=None, cadence="") == D(2027, 1, 30)


def test_priorities_boost_and_selection_order(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_symbols(db, ["AI.PA", "MC.PA", "ALO.PA"], 3, "Bourse complète")
    enqueue_symbols(db, ["MC.PA"], 2, "Indice suivi")  # La meilleure priorité gagne
    enqueue_symbols(db, ["ALO.PA"], 3, "Bourse complète")
    upsert_screener_snapshots(db, [{"symbol": "AI.PA", "market_cap": 9e10}, {"symbol": "ALO.PA", "market_cap": 1e10}])

    order = [it.symbol for it in select_due_batch(db, limit=10)]
    assert order == ["MC.PA", "AI.PA", "ALO.PA"]  # Priorité 2, puis capitalisation décroissante

    boost_symbols(db, ["ALO.PA"])
    assert select_due_batch(db, limit=1)[0].symbol == "ALO.PA"

    reset_source_priorities(db)  # Les sources sont recalculées, le coup de pouce reste
    batch = select_due_batch(db, limit=10)
    assert [it.symbol for it in batch] == ["ALO.PA"]  # Les autres repassent à 99 (non planifiés)


def test_record_fetch_schedules_and_retries_when_period_did_not_advance(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_symbols(db, ["AI.PA"], 1, "Liste de suivi")
    pay = _payload(["2025-12-31", "2026-03-31", "2026-06-30"])
    res = record_fetch(db, "AI.PA", pay, today=D(2026, 8, 1))
    assert res["period_end"] == "2026-06-30" and res["next_due_at"] > "2026-08-21"
    assert is_fresh_by_schedule(db, ["AI.PA"], today=D(2026, 8, 2)) is True

    # Échéance atteinte mais EODHD n'a pas encore la nouvelle période → réessai à +7 j
    due = D.fromisoformat(res["next_due_at"])
    assert is_fresh_by_schedule(db, ["AI.PA"], today=due) is False
    retry = record_fetch(db, "AI.PA", pay, today=due)
    assert retry["next_due_at"] == (due + datetime.timedelta(days=7)).isoformat()

    # Nouvelle période publiée → retour à la cadence normale
    newer = record_fetch(db, "AI.PA", _payload(["2026-03-31", "2026-06-30", "2026-09-30"]), today=due + datetime.timedelta(days=7))
    assert newer["advanced"] is True
    sched = get_symbol_schedule(db, ["AI.PA"])
    assert sched["last_period_end"] == "2026-09-30" and sched["status"] == "ok"


def test_mark_reported_and_failures(tmp_path: Path):
    db = _db(tmp_path)
    enqueue_symbols(db, ["AI.PA", "MC.PA"], 1, "Liste de suivi")
    record_fetch(db, "AI.PA", _payload(["2026-03-31", "2026-06-30"]), today=D(2026, 8, 1))
    today = datetime.date.today()
    assert mark_reported(db, {"AI.PA": (today.isoformat(), "2026-09-30")}) == 1
    assert mark_reported(db, {"AI.PA": ("2026-01-01", "2026-03-31")}) == 0  # Période déjà connue
    stats = queue_stats(db)
    assert stats["reported"] == 1 and stats["never_loaded"] == 1

    record_failure(db, "MC.PA", "HTTP 404")
    sched = get_symbol_schedule(db, ["MC.PA"])
    assert sched["status"] == "pending" or sched["status"] == "error"
    assert queue_stats(db)["errors"] == 1
