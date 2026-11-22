"""File d'attente des fondamentaux EODHD : priorités, échéances intelligentes et suivi des mises à jour.

Chaque titre suivi a une ligne dans `finance_fundamentals_queue` (clé = ticker EODHD, ex. `AI.PA`) :
- `priority` : 0 = coup de pouce manuel, 1..3 = sources choisies (listes de suivi, indices, bourses
  complètes selon l'ordre de l'utilisateur), 99 = titre seulement consulté (jamais planifié d'office).
- `next_due_at` : prochain contrôle, calculé après chaque chargement à partir de la dernière période
  publiée, de la cadence (trimestrielle / semestrielle) et des dates habituelles de publication.
- `reported_pending` : la société vient de publier d'après le calendrier EODHD → rechargement prioritaire.
"""

from __future__ import annotations

import datetime
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .finance_warehouse import _connect, _norm_sym, _utc_iso

PRIORITY_BOOST = 0
PRIORITY_CONSULTED = 99
SOURCE_KEYS: tuple[str, ...] = ("watchlists", "indices", "full_exchanges")

PUBLICATION_DELAY_DAYS = 3  # Délai laissé à EODHD pour intégrer les comptes publiés
NEXT_PUBLICATION_DAYS = {"quarterly": 130, "semiannual": 240, "annual": 420}
MAX_AGE_DAYS = {"quarterly": 120, "semiannual": 200, "annual": 200}
MIN_REFRESH_DAYS = 20
UNKNOWN_CADENCE_DAYS = 90
STALE_RETRY_STEP_DAYS = 7
MAX_STALE_RETRIES = 3
ERROR_RETRY_DAYS = (1, 3, 7)


@dataclass(frozen=True)
class QueueItem:
    symbol: str
    priority: int
    status: str
    reason: str
    order_class: int


def _parse_date(value: Any) -> datetime.date | None:
    raw = str(value or "").strip()[:10]
    if len(raw) != 10:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso_day(d: datetime.date) -> str:
    return d.isoformat()


# ---------------------------------------------------------------------------
# Lecture des signaux contenus dans un payload EODHD `/api/fundamentals`
# ---------------------------------------------------------------------------

def extract_schedule_signals(fundamentals: dict[str, Any] | None) -> dict[str, Any]:
    """Déduit la dernière période publiée, la cadence et les dates de publication d'un payload EODHD."""
    fin = (fundamentals or {}).get("Financials") or {}
    period_dates: list[datetime.date] = []
    for stmt in ("Income_Statement", "Balance_Sheet"):
        quarterly = ((fin.get(stmt) or {}).get("quarterly")) or {}
        if isinstance(quarterly, dict):
            period_dates.extend(d for d in (_parse_date(k) for k in quarterly.keys()) if d)
    period_dates = sorted(set(period_dates))

    yearly_dates: list[datetime.date] = []
    yearly = (((fin.get("Income_Statement") or {}).get("yearly")) or {})
    if isinstance(yearly, dict):
        yearly_dates = sorted({d for d in (_parse_date(k) for k in yearly.keys()) if d})

    hl_mrq = _parse_date(((fundamentals or {}).get("Highlights") or {}).get("MostRecentQuarter"))
    candidates = [d for d in (period_dates[-1] if period_dates else None, hl_mrq, yearly_dates[-1] if yearly_dates else None) if d]
    period_end = max(candidates) if candidates else None

    cadence = ""
    recent = period_dates[-5:]
    if len(recent) >= 3:
        gaps = [(b - a).days for a, b in zip(recent, recent[1:]) if (b - a).days > 0]
        if gaps:
            med = statistics.median(gaps)
            cadence = "quarterly" if med <= 120 else ("semiannual" if med <= 250 else "annual")
    elif yearly_dates:
        cadence = "semiannual" if len(period_dates) >= 2 else "annual"

    today = datetime.date.today()
    report_dates: list[datetime.date] = []
    history = (((fundamentals or {}).get("Earnings") or {}).get("History")) or {}
    if isinstance(history, dict):
        for item in history.values():
            if isinstance(item, dict):
                rd = _parse_date(item.get("reportDate"))
                if rd and rd <= today:
                    report_dates.append(rd)
    report_dates = sorted(set(report_dates))
    last_report = report_dates[-1] if report_dates else None
    # Jours de l'année habituels de publication (2 dernières années) pour estimer la prochaine
    typical = sorted({(d.month, d.day) for d in report_dates if (today - d).days <= 800})

    return {
        "period_end": _iso_day(period_end) if period_end else None,
        "cadence": cadence,
        "last_report_date": _iso_day(last_report) if last_report else None,
        "typical_report_days": typical,
    }


def compute_next_due(
    *,
    fetched_on: datetime.date,
    period_end: str | None,
    cadence: str,
    typical_report_days: Iterable[Iterable[int]] = (),
) -> datetime.date:
    """Calcule la date du prochain contrôle des fondamentaux (cf. règles du plan)."""
    max_age = MAX_AGE_DAYS.get(cadence, UNKNOWN_CADENCE_DAYS)
    ceiling = fetched_on + datetime.timedelta(days=max_age)
    floor = fetched_on + datetime.timedelta(days=MIN_REFRESH_DAYS)

    estimate: datetime.date | None = None
    # 1. Saison habituelle de publication de la société
    for year in (fetched_on.year, fetched_on.year + 1):
        for md in typical_report_days:
            month, day = list(md)[:2]
            try:
                cand = datetime.date(year, int(month), int(day))
            except ValueError:
                try:
                    cand = datetime.date(year, int(month), 28)  # 29 février une année non bissextile
                except ValueError:
                    continue
            if cand > floor and (estimate is None or cand < estimate):
                estimate = cand
    # 2. Sinon : fin de la dernière période + délai typique de la prochaine publication
    pe = _parse_date(period_end)
    if estimate is None and pe and cadence in NEXT_PUBLICATION_DAYS:
        estimate = pe + datetime.timedelta(days=NEXT_PUBLICATION_DAYS[cadence])
    if estimate is None:
        estimate = fetched_on + datetime.timedelta(days=UNKNOWN_CADENCE_DAYS)

    due = estimate + datetime.timedelta(days=PUBLICATION_DELAY_DAYS)
    return max(floor, min(due, ceiling))


# ---------------------------------------------------------------------------
# Alimentation & priorités
# ---------------------------------------------------------------------------

def enqueue_symbols(db_path: Path, symbols: Iterable[str], priority: int, reason: str) -> int:
    """Ajoute des titres à la file (ou améliore leur priorité s'ils y sont déjà)."""
    now_iso = _utc_iso()
    rows = [(s, int(priority), reason, now_iso) for s in {_norm_sym(x) for x in symbols} if s]
    if not rows:
        return 0
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO finance_fundamentals_queue (symbol, priority, reason, status, updated_at)
            VALUES (?, ?, ?, 'pending', ?)
            ON CONFLICT(symbol) DO UPDATE SET
                reason = CASE WHEN excluded.priority < finance_fundamentals_queue.priority
                              THEN excluded.reason ELSE finance_fundamentals_queue.reason END,
                priority = MIN(finance_fundamentals_queue.priority, excluded.priority),
                updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def boost_symbols(db_path: Path, symbols: Iterable[str]) -> int:
    """Coup de pouce manuel : place les titres en tête de file (priorité 0, échéance immédiate)."""
    clean = sorted({_norm_sym(x) for x in symbols if _norm_sym(x)})
    if not clean:
        return 0
    enqueue_symbols(db_path, clean, PRIORITY_BOOST, "Coup de pouce manuel")
    with _connect(db_path) as conn:
        conn.executemany(
            "UPDATE finance_fundamentals_queue SET next_due_at = NULL WHERE symbol = ?",
            [(s,) for s in clean],
        )
    return len(clean)


def reset_source_priorities(db_path: Path) -> None:
    """Remet les priorités « sources » à 99 avant de les recalculer (les coups de pouce sont conservés)."""
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE finance_fundamentals_queue SET priority = ? WHERE priority BETWEEN 1 AND 98",
            (PRIORITY_CONSULTED,),
        )


def mark_reported(db_path: Path, reported: dict[str, tuple[str, str | None]]) -> int:
    """Signale les sociétés qui viennent de publier : `{ticker: (report_date, period_end)}`."""
    updates: list[tuple[str, str, str, str]] = []
    for sym, (report_date, period_end) in reported.items():
        rd = _parse_date(report_date)
        clean = _norm_sym(sym)
        if not rd or not clean:
            continue
        due = _iso_day(rd + datetime.timedelta(days=PUBLICATION_DELAY_DAYS))
        updates.append((due, clean, str(period_end or "9999-12-31")[:10], report_date[:10]))
    if not updates:
        return 0
    changed = 0
    with _connect(db_path) as conn:
        for due, sym, pe, rd in updates:
            cur = conn.execute(
                """
                UPDATE finance_fundamentals_queue
                SET reported_pending = 1, next_due_at = ?, stale_retries = 0
                WHERE symbol = ? AND status = 'ok'
                  AND (last_period_end IS NULL OR last_period_end < ?)
                  AND (last_report_date IS NULL OR last_report_date < ?)
                """,
                (due, sym, pe, rd),
            )
            changed += int(cur.rowcount or 0)
    return changed


# ---------------------------------------------------------------------------
# Sélection du lot du jour
# ---------------------------------------------------------------------------

_ORDER_CLASS_SQL = """
    CASE
        WHEN q.priority = 0 THEN 0
        WHEN q.priority >= 99 THEN NULL
        WHEN q.reported_pending = 1 AND (q.next_due_at IS NULL OR q.next_due_at <= :today) THEN 1
        WHEN q.status = 'pending' AND (q.next_due_at IS NULL OR q.next_due_at <= :today) THEN 2
        WHEN q.next_due_at IS NULL OR q.next_due_at <= :today THEN 3
        ELSE NULL
    END
"""


def select_due_batch(db_path: Path, *, limit: int, today: datetime.date | None = None) -> list[QueueItem]:
    """Retourne les `limit` titres à traiter en premier (coup de pouce, publiés, jamais chargés, échus)."""
    if limit <= 0:
        return []
    day = _iso_day(today or datetime.date.today())
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT symbol, priority, status, reason, order_class FROM (
                SELECT q.symbol, q.priority, q.status, q.reason, {_ORDER_CLASS_SQL} AS order_class,
                       (SELECT MAX(s.market_cap) FROM finance_screener_snapshots s
                        WHERE s.symbol = q.symbol OR s.eod_ticker = q.symbol) AS mcap
                FROM finance_fundamentals_queue q
            )
            WHERE order_class IS NOT NULL
            ORDER BY order_class ASC, priority ASC, (mcap IS NULL) ASC, mcap DESC, symbol ASC
            LIMIT :limit
            """,
            {"today": day, "limit": int(limit)},
        ).fetchall()
    return [
        QueueItem(
            symbol=str(r["symbol"]),
            priority=int(r["priority"]),
            status=str(r["status"]),
            reason=str(r["reason"] or ""),
            order_class=int(r["order_class"]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Résultats de chargement
# ---------------------------------------------------------------------------

def record_fetch(
    db_path: Path,
    symbol: str,
    fundamentals: dict[str, Any] | None,
    *,
    aliases: Iterable[str] = (),
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """Enregistre un chargement réussi des fondamentaux et calcule le prochain contrôle.

    Appelé pour TOUT chargement EODHD (file, fiche consultée, Screener) afin que la fraîcheur soit
    partagée. Si la période publiée n'a pas avancé alors qu'un rafraîchissement était attendu,
    un nouvel essai est programmé à +7 j, +14 j, +21 j (3 au plus) avant de revenir à la cadence normale.
    """
    key = _norm_sym(symbol)
    if not key:
        return {}
    day = today or datetime.date.today()
    signals = extract_schedule_signals(fundamentals)
    keys = [key, *[_norm_sym(a) for a in aliases if _norm_sym(a) and _norm_sym(a) != key]]
    marks = ", ".join("?" for _ in keys)
    now_iso = _utc_iso()

    with _connect(db_path) as conn:
        prev = conn.execute(
            f"SELECT * FROM finance_fundamentals_queue WHERE symbol IN ({marks}) ORDER BY priority ASC LIMIT 1",
            keys,
        ).fetchone()
        target = str(prev["symbol"]) if prev else key
        prev_pe = str(prev["last_period_end"] or "") if prev else ""
        prev_due = _parse_date(prev["next_due_at"]) if prev else None
        was_expected = bool(prev and prev["status"] == "ok" and (prev["reported_pending"] or (prev_due and prev_due <= day)))
        advanced = bool(signals["period_end"] and signals["period_end"] > prev_pe)
        stale_retries = int(prev["stale_retries"] or 0) if prev else 0

        if was_expected and not advanced and stale_retries < MAX_STALE_RETRIES:
            stale_retries += 1
            next_due = day + datetime.timedelta(days=STALE_RETRY_STEP_DAYS * stale_retries)
            reported_pending = int(prev["reported_pending"] or 0)
        else:
            stale_retries = 0
            reported_pending = 0
            next_due = compute_next_due(
                fetched_on=day,
                period_end=signals["period_end"],
                cadence=signals["cadence"],
                typical_report_days=signals["typical_report_days"],
            )

        priority = int(prev["priority"]) if prev else PRIORITY_CONSULTED
        if priority == PRIORITY_BOOST:
            priority = PRIORITY_CONSULTED  # Le coup de pouce est consommé ; la source le redéfinira
        conn.execute(
            """
            INSERT INTO finance_fundamentals_queue (
                symbol, priority, reason, status, last_fetched_at, last_period_end, last_report_date,
                typical_report_days, cadence, next_due_at, reported_pending, stale_retries, attempts,
                last_error, updated_at
            ) VALUES (?, ?, ?, 'ok', ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                priority = excluded.priority,
                status = 'ok',
                last_fetched_at = excluded.last_fetched_at,
                last_period_end = COALESCE(excluded.last_period_end, finance_fundamentals_queue.last_period_end),
                last_report_date = COALESCE(excluded.last_report_date, finance_fundamentals_queue.last_report_date),
                typical_report_days = excluded.typical_report_days,
                cadence = excluded.cadence,
                next_due_at = excluded.next_due_at,
                reported_pending = excluded.reported_pending,
                stale_retries = excluded.stale_retries,
                attempts = 0,
                last_error = NULL,
                updated_at = excluded.updated_at
            """,
            (
                target,
                priority,
                str(prev["reason"] or "") if prev else "Consultation",
                now_iso,
                signals["period_end"],
                signals["last_report_date"],
                json.dumps(signals["typical_report_days"]),
                signals["cadence"],
                _iso_day(next_due),
                reported_pending,
                stale_retries,
                now_iso,
            ),
        )
    return {"symbol": target, "next_due_at": _iso_day(next_due), "advanced": advanced, **signals}


def record_failure(db_path: Path, symbol: str, error: str, *, today: datetime.date | None = None) -> None:
    """Enregistre un échec et espace les réessais (1 j, 3 j, 7 j…)."""
    key = _norm_sym(symbol)
    if not key:
        return
    day = today or datetime.date.today()
    with _connect(db_path) as conn:
        row = conn.execute("SELECT attempts, status FROM finance_fundamentals_queue WHERE symbol = ?", (key,)).fetchone()
        attempts = int(row["attempts"] or 0) + 1 if row else 1
        delay = ERROR_RETRY_DAYS[min(attempts, len(ERROR_RETRY_DAYS)) - 1]
        status = "ok" if (row and row["status"] == "ok") else "error"
        conn.execute(
            """
            UPDATE finance_fundamentals_queue
            SET attempts = ?, last_error = ?, status = ?, next_due_at = ?,
                priority = CASE WHEN priority = 0 THEN 99 ELSE priority END, updated_at = ?
            WHERE symbol = ?
            """,
            (attempts, error[:300], status, _iso_day(day + datetime.timedelta(days=delay)), _utc_iso(), key),
        )


def is_fresh_by_schedule(db_path: Path, symbols: Iterable[str], *, today: datetime.date | None = None) -> bool | None:
    """`True` si les fondamentaux sont à jour selon l'échéancier, `False` s'ils sont échus, `None` si inconnus."""
    keys = [k for k in {_norm_sym(s) for s in symbols} if k]
    if not keys or not db_path.exists():
        return None
    marks = ", ".join("?" for _ in keys)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT next_due_at, reported_pending FROM finance_fundamentals_queue
            WHERE symbol IN ({marks}) AND status = 'ok' AND last_fetched_at IS NOT NULL
            ORDER BY last_fetched_at DESC LIMIT 1
            """,
            keys,
        ).fetchone()
    if not row:
        return None
    due = _parse_date(row["next_due_at"])
    if row["reported_pending"] and due and due <= (today or datetime.date.today()):
        return False
    return bool(due and due > (today or datetime.date.today()))


def get_symbol_schedule(db_path: Path, symbols: Iterable[str]) -> dict[str, Any] | None:
    """Retourne l'état de fraîcheur d'un titre pour l'affichage (période, publication, prochain contrôle)."""
    keys = [k for k in {_norm_sym(s) for s in symbols} if k]
    if not keys or not db_path.exists():
        return None
    marks = ", ".join("?" for _ in keys)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT symbol, status, last_fetched_at, last_period_end, last_report_date, cadence,
                   next_due_at, reported_pending, priority
            FROM finance_fundamentals_queue WHERE symbol IN ({marks})
            ORDER BY (last_fetched_at IS NULL) ASC, last_fetched_at DESC LIMIT 1
            """,
            keys,
        ).fetchone()
    return dict(row) if row else None


def queue_stats(db_path: Path, *, today: datetime.date | None = None) -> dict[str, Any]:
    """Compteurs de la file pour l'onglet 5."""
    day = _iso_day(today or datetime.date.today())
    with _connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN priority < 99 THEN 1 ELSE 0 END) AS tracked,
                SUM(CASE WHEN priority < 99 AND status = 'pending' THEN 1 ELSE 0 END) AS never_loaded,
                SUM(CASE WHEN priority < 99 AND status = 'ok' AND reported_pending = 1 THEN 1 ELSE 0 END) AS reported,
                SUM(CASE WHEN priority < 99 AND status = 'ok' AND reported_pending = 0
                          AND (next_due_at IS NULL OR next_due_at <= :today) THEN 1 ELSE 0 END) AS due,
                SUM(CASE WHEN priority < 99 AND status = 'ok' AND next_due_at > :today
                          AND reported_pending = 0 THEN 1 ELSE 0 END) AS up_to_date,
                SUM(CASE WHEN priority < 99 AND status = 'error' THEN 1 ELSE 0 END) AS errors,
                SUM(CASE WHEN priority = 0 THEN 1 ELSE 0 END) AS boosted
            FROM finance_fundamentals_queue
            """,
            {"today": day},
        ).fetchone()
    stats = {k: int((row[k] if row else 0) or 0) for k in ("tracked", "never_loaded", "reported", "due", "up_to_date", "errors", "boosted")}
    stats["to_process"] = stats["never_loaded"] + stats["reported"] + stats["due"] + stats["errors"] + stats["boosted"]
    return stats


def list_next_items(db_path: Path, *, limit: int = 30) -> list[dict[str, Any]]:
    """Les prochains titres qui seront traités, avec la raison."""
    labels = {0: "Coup de pouce", 1: "Résultats publiés", 2: "Jamais chargé", 3: "Rafraîchissement échu"}
    return [
        {"symbol": it.symbol, "priority": it.priority, "reason": it.reason, "why": labels.get(it.order_class, "")}
        for it in select_due_batch(db_path, limit=limit)
    ]
