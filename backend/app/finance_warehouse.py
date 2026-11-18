"""Entrepôt local haute densité (SQLite WAL + snapshots zlib) pour les données boursières.

Isolé dans `Settings.resolved_finance_data_dir` (volume Docker dédié `finance_data`)
afin de stocker sans limite de profondeur les barres EOD, les états financiers
historiques normalisés et les payloads bruts compressés EODHD / Yahoo Finance.
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import sqlite3
import time
import uuid
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import Settings

_logger = logging.getLogger("uvicorn.error")

_WAREHOUSE_FILENAME = "finance_warehouse.db"
_INITIALIZED_PATHS: set[str] = set()
_FTS_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+")


def _build_fts_match_query(query: str, exchange_code: str = "") -> str | None:
    tokens = _FTS_TOKEN_RE.findall((query or "").strip())
    if not tokens or not any(len(t) >= 2 for t in tokens):
        return None
    terms = " AND ".join(f'"{t}"*' for t in tokens[:6])
    exch = _norm_sym(exchange_code)
    if exch and exch != "ALL":
        return f'exchange_code : "{exch}" AND ({terms})'
    return terms


def _fts5_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'finance_exchange_symbols_fts'"
    ).fetchone()
    return bool(row)


def _ensure_exchange_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS finance_exchange_symbols_fts USING fts5(
                exchange_code,
                symbol,
                eod_ticker,
                name,
                isin,
                fund_family,
                country,
                currency,
                type,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """
        )
        sym_cnt = int(conn.execute("SELECT COUNT(*) FROM finance_exchange_symbols").fetchone()[0] or 0)
        if sym_cnt > 0:
            fts_cnt = int(conn.execute("SELECT COUNT(*) FROM finance_exchange_symbols_fts").fetchone()[0] or 0)
            if fts_cnt == 0:
                conn.execute(
                    """
                    INSERT INTO finance_exchange_symbols_fts (
                        exchange_code, symbol, eod_ticker, name, isin, fund_family, country, currency, type
                    )
                    SELECT
                        exchange_code,
                        symbol,
                        eod_ticker,
                        name,
                        COALESCE(isin, ''),
                        COALESCE(fund_family, ''),
                        COALESCE(country, ''),
                        COALESCE(currency, ''),
                        COALESCE(type, '')
                    FROM finance_exchange_symbols
                    """
                )
    except sqlite3.OperationalError as exc:
        _logger.debug("Index FTS5 finance_exchange_symbols indisponible: %s", exc)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS finance_instruments (
    symbol TEXT PRIMARY KEY,
    eod_ticker TEXT,
    yahoo_symbol TEXT,
    isin TEXT,
    short_name TEXT,
    long_name TEXT,
    exchange TEXT,
    currency TEXT,
    country TEXT,
    sector TEXT,
    industry TEXT,
    eod_synced_date TEXT,
    eod_synced_at TEXT,
    eod_synced_bars INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fin_inst_eod ON finance_instruments (eod_ticker);
CREATE INDEX IF NOT EXISTS idx_fin_inst_yahoo ON finance_instruments (yahoo_symbol);
CREATE INDEX IF NOT EXISTS idx_fin_inst_short ON finance_instruments (short_name);
CREATE INDEX IF NOT EXISTS idx_fin_inst_long ON finance_instruments (long_name);

CREATE TABLE IF NOT EXISTS finance_index_constituents (
    index_code TEXT NOT NULL,
    symbol TEXT NOT NULL,
    eod_ticker TEXT,
    yahoo_symbol TEXT,
    name TEXT,
    sector TEXT,
    industry TEXT,
    exchange TEXT,
    weight_pct REAL,
    position INTEGER DEFAULT 0,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (index_code, symbol)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_fin_idx_const_sym ON finance_index_constituents (symbol);
CREATE INDEX IF NOT EXISTS idx_fin_idx_const_eod ON finance_index_constituents (eod_ticker);
CREATE INDEX IF NOT EXISTS idx_fin_idx_const_name ON finance_index_constituents (index_code, name);

CREATE TABLE IF NOT EXISTS finance_exchange_symbols (
    exchange_code TEXT NOT NULL,
    symbol TEXT NOT NULL,
    eod_ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    isin TEXT,
    fund_family TEXT,
    country TEXT,
    currency TEXT,
    type TEXT,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (exchange_code, symbol)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_name ON finance_exchange_symbols (exchange_code, name);
CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_isin ON finance_exchange_symbols (exchange_code, isin);
CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_curr ON finance_exchange_symbols (exchange_code, currency);

CREATE TABLE IF NOT EXISTS finance_eod_bars (
    symbol TEXT NOT NULL,
    bar_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adjusted_close REAL,
    volume REAL,
    source TEXT,
    updated_at TEXT,
    PRIMARY KEY (symbol, bar_date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS finance_fundamental_facts (
    symbol TEXT NOT NULL,
    period_type TEXT NOT NULL,
    period_date TEXT NOT NULL,
    statement_type TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    value REAL,
    currency TEXT,
    source TEXT,
    updated_at TEXT,
    PRIMARY KEY (symbol, period_type, period_date, statement_type, metric_key)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS finance_raw_snapshots (
    symbol TEXT NOT NULL,
    provider TEXT NOT NULL,
    payload_type TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    currency TEXT,
    normalized_json TEXT,
    raw_zlib BLOB,
    PRIMARY KEY (symbol, provider, payload_type)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS finance_user_watchlists (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fin_user_wl_user ON finance_user_watchlists (user_id, position);

CREATE TABLE IF NOT EXISTS finance_user_watchlist_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    list_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    yahoo_symbol TEXT NOT NULL DEFAULT '',
    eod_ticker TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT 'EUR',
    note TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    UNIQUE (list_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_fin_user_wl_items_list ON finance_user_watchlist_items (user_id, list_id, position);

CREATE TABLE IF NOT EXISTS finance_ai_analyses (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    expert_id TEXT NOT NULL DEFAULT '',
    expert_name TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    question TEXT,
    verdict TEXT NOT NULL DEFAULT '',
    conviction TEXT NOT NULL DEFAULT '',
    horizon TEXT NOT NULL DEFAULT '',
    markdown TEXT NOT NULL,
    content_html TEXT NOT NULL DEFAULT '',
    news_sources_json TEXT NOT NULL DEFAULT '[]',
    news_articles_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fin_ai_sym_kind_date ON finance_ai_analyses (symbol, kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fin_ai_date ON finance_ai_analyses (created_at DESC);

CREATE TABLE IF NOT EXISTS finance_sync_preferences (
    pref_key TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    last_run_at TEXT,
    last_status_json TEXT,
    updated_at TEXT NOT NULL
);
"""


def warehouse_db_path(settings: Settings) -> Path:
    """Retourne le chemin vers la base SQLite de l'entrepôt financier."""
    return settings.resolved_finance_data_dir / _WAREHOUSE_FILENAME


def _utc_iso(ts: float | None = None) -> str:
    dt = datetime.datetime.fromtimestamp(ts if ts is not None else time.time(), datetime.timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def init_warehouse(db_path: Path) -> None:
    """Crée le répertoire cible et initialise le schéma SQLite en mode WAL."""
    key = str(db_path)
    if key in _INITIALIZED_PATHS and db_path.exists():
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=15.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=-32768;")
        conn.execute("PRAGMA mmap_size=268435456;")
        conn.executescript(_SCHEMA_SQL)
        inst_cols = {
            str(r[1])
            for r in conn.execute("PRAGMA table_info(finance_instruments)").fetchall()
        }
        if "eod_synced_date" not in inst_cols:
            conn.execute("ALTER TABLE finance_instruments ADD COLUMN eod_synced_date TEXT")
        if "eod_synced_at" not in inst_cols:
            conn.execute("ALTER TABLE finance_instruments ADD COLUMN eod_synced_at TEXT")
        if "eod_synced_bars" not in inst_cols:
            conn.execute("ALTER TABLE finance_instruments ADD COLUMN eod_synced_bars INTEGER DEFAULT 0")
        wl_cols = {
            str(r[1])
            for r in conn.execute("PRAGMA table_info(finance_user_watchlist_items)").fetchall()
        }
        if "note" not in wl_cols:
            conn.execute("ALTER TABLE finance_user_watchlist_items ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        exch_cols = {
            str(r[1])
            for r in conn.execute("PRAGMA table_info(finance_exchange_symbols)").fetchall()
        }
        if "fund_family" not in exch_cols:
            conn.execute("ALTER TABLE finance_exchange_symbols ADD COLUMN fund_family TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_type ON finance_exchange_symbols (exchange_code, type)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_family ON finance_exchange_symbols (exchange_code, fund_family)"
        )
        _ensure_exchange_fts(conn)
        conn.commit()
    _INITIALIZED_PATHS.add(key)


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    init_warehouse(db_path)
    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-32768;")
        conn.execute("PRAGMA mmap_size=268435456;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _norm_sym(symbol: str) -> str:
    return (symbol or "").strip().upper()


def resolve_canonical_symbol(db_path: Path, symbol: str) -> str:
    """Résout un ticker éventuel (Yahoo ou EOD) vers la clé canonique déjà stockée."""
    clean = _norm_sym(symbol)
    if not clean:
        return clean
    if not db_path.exists():
        return clean
    try:
        with _connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT symbol FROM finance_instruments
                WHERE symbol = ? OR eod_ticker = ? OR yahoo_symbol = ?
                LIMIT 1
                """,
                (clean, clean, clean),
            ).fetchone()
            if row and row["symbol"]:
                return str(row["symbol"])
    except Exception as exc:
        _logger.debug("resolve_canonical_symbol fallback (%s): %s", clean, exc)
    return clean


def get_instrument_meta(db_path: Path, symbol: str) -> dict[str, Any] | None:
    """Retourne les métadonnées stockées d'un instrument depuis `finance_instruments`."""
    clean = _norm_sym(symbol)
    if not clean or not db_path.exists():
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT symbol, eod_ticker, yahoo_symbol, isin, short_name, long_name,
                   exchange, currency, country, sector, industry,
                   eod_synced_date, eod_synced_at, eod_synced_bars
            FROM finance_instruments
            WHERE symbol = ? OR eod_ticker = ? OR yahoo_symbol = ?
            LIMIT 1
            """,
            (clean, clean, clean),
        ).fetchone()
    return dict(row) if row else None


def get_instrument_eod_sync_info(db_path: Path, symbol: str) -> dict[str, Any]:
    """Retourne la date de dernière sauvegarde locale EOD et la profondeur stockée pour un symbole."""
    sym = _norm_sym(symbol)
    empty = {
        "eod_synced_date": None,
        "eod_synced_at": None,
        "eod_synced_bars": 0,
        "bars_count": 0,
        "latest_bar_date": None,
    }
    if not sym or not db_path.exists():
        return empty
    with _connect(db_path) as conn:
        inst = conn.execute(
            """
            SELECT eod_synced_date, eod_synced_at, eod_synced_bars
            FROM finance_instruments
            WHERE symbol = ?
            LIMIT 1
            """,
            (sym,),
        ).fetchone()
        agg = conn.execute(
            """
            SELECT COUNT(*) AS cnt, MAX(bar_date) AS max_dt
            FROM finance_eod_bars
            WHERE symbol = ?
            """,
            (sym,),
        ).fetchone()
    return {
        "eod_synced_date": str(inst["eod_synced_date"]) if (inst and inst["eod_synced_date"]) else None,
        "eod_synced_at": str(inst["eod_synced_at"]) if (inst and inst["eod_synced_at"]) else None,
        "eod_synced_bars": int((inst["eod_synced_bars"] if inst else 0) or 0),
        "bars_count": int((agg["cnt"] if agg else 0) or 0),
        "latest_bar_date": str(agg["max_dt"]) if (agg and agg["max_dt"]) else None,
    }


def is_eod_fresh_today(
    sync_info: dict[str, Any] | None,
    *,
    min_bars_needed: int = 1,
    today_iso: str | None = None,
) -> bool:
    """Indique si les barres EOD locales ont déjà été sauvegardées aujourd'hui avec la profondeur requise."""
    if not sync_info:
        return False
    bars_count = int(sync_info.get("bars_count") or 0)
    if bars_count <= 0:
        return False
    today = today_iso or datetime.date.today().isoformat()
    if str(sync_info.get("eod_synced_date") or "") != today:
        return False
    synced_depth = max(bars_count, int(sync_info.get("eod_synced_bars") or 0))
    return synced_depth >= max(1, int(min_bars_needed or 1))


def upsert_instrument(db_path: Path, meta: dict[str, Any]) -> None:
    """Enregistre ou met à jour la fiche instrument."""
    symbol = _norm_sym(str(meta.get("symbol") or ""))
    if not symbol:
        return
    now_iso = _utc_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_instruments (
                symbol, eod_ticker, yahoo_symbol, isin, short_name, long_name,
                exchange, currency, country, sector, industry, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                eod_ticker = COALESCE(NULLIF(excluded.eod_ticker, ''), finance_instruments.eod_ticker),
                yahoo_symbol = COALESCE(NULLIF(excluded.yahoo_symbol, ''), finance_instruments.yahoo_symbol),
                isin = COALESCE(NULLIF(excluded.isin, ''), finance_instruments.isin),
                short_name = COALESCE(NULLIF(excluded.short_name, ''), finance_instruments.short_name),
                long_name = COALESCE(NULLIF(excluded.long_name, ''), finance_instruments.long_name),
                exchange = COALESCE(NULLIF(excluded.exchange, ''), finance_instruments.exchange),
                currency = COALESCE(NULLIF(excluded.currency, ''), finance_instruments.currency),
                country = COALESCE(NULLIF(excluded.country, ''), finance_instruments.country),
                sector = COALESCE(NULLIF(excluded.sector, ''), finance_instruments.sector),
                industry = COALESCE(NULLIF(excluded.industry, ''), finance_instruments.industry),
                updated_at = excluded.updated_at
            """,
            (
                symbol,
                _norm_sym(str(meta.get("eod_ticker") or "")) or None,
                _norm_sym(str(meta.get("yahoo_symbol") or "")) or None,
                (meta.get("isin") or None),
                (meta.get("short_name") or None),
                (meta.get("long_name") or None),
                (meta.get("exchange") or None),
                (meta.get("currency") or None),
                (meta.get("country") or None),
                (meta.get("sector") or None),
                (meta.get("industry") or None),
                now_iso,
            ),
        )


def upsert_eod_bars(
    db_path: Path,
    symbol: str,
    bars: list[dict[str, Any]],
    source: str,
    *,
    requested_limit: int = 0,
) -> int:
    """Insère ou met à jour une liste de barres OHLCV (dates journalières YYYY-MM-DD) et note la date de sauvegarde locale."""
    sym = _norm_sym(symbol)
    if not sym or not bars:
        return 0
    now_iso = _utc_iso()
    today_iso = datetime.date.today().isoformat()
    rows: list[tuple[Any, ...]] = []
    for bar in bars:
        b_date = str(bar.get("date") or "").strip()
        if not b_date or len(b_date) > 10:
            # On ne stocke en table EOD journalière que les séances YYYY-MM-DD (pas l'intraday).
            continue
        rows.append(
            (
                sym,
                b_date,
                bar.get("open"),
                bar.get("high"),
                bar.get("low"),
                bar.get("close"),
                bar.get("adjusted_close", bar.get("close")),
                bar.get("volume"),
                source,
                now_iso,
            )
        )
    if not rows:
        return 0
    depth = max(len(rows), int(requested_limit or 0))
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO finance_eod_bars (
                symbol, bar_date, open, high, low, close, adjusted_close, volume, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, bar_date) DO UPDATE SET
                open = COALESCE(excluded.open, finance_eod_bars.open),
                high = COALESCE(excluded.high, finance_eod_bars.high),
                low = COALESCE(excluded.low, finance_eod_bars.low),
                close = COALESCE(excluded.close, finance_eod_bars.close),
                adjusted_close = COALESCE(excluded.adjusted_close, finance_eod_bars.adjusted_close),
                volume = COALESCE(excluded.volume, finance_eod_bars.volume),
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        conn.execute(
            """
            INSERT INTO finance_instruments (
                symbol, eod_synced_date, eod_synced_at, eod_synced_bars, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                eod_synced_date = excluded.eod_synced_date,
                eod_synced_at = excluded.eod_synced_at,
                eod_synced_bars = MAX(COALESCE(finance_instruments.eod_synced_bars, 0), excluded.eod_synced_bars),
                updated_at = excluded.updated_at
            """,
            (sym, today_iso, now_iso, depth, now_iso),
        )
    return len(rows)


def get_latest_bar_date(db_path: Path, symbol: str) -> str | None:
    """Retourne la date de la dernière barre journalière stockée pour un symbole."""
    sym = _norm_sym(symbol)
    if not sym or not db_path.exists():
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(bar_date) AS max_date FROM finance_eod_bars WHERE symbol = ?",
            (sym,),
        ).fetchone()
        return str(row["max_date"]) if row and row["max_date"] else None


def get_stored_eod_bars(
    db_path: Path,
    symbol: str,
    start_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Retourne les barres EOD stockées triées chronologiquement (du plus ancien au plus récent)."""
    sym = _norm_sym(symbol)
    if not sym or not db_path.exists():
        return []
    with _connect(db_path) as conn:
        if start_date:
            rows = conn.execute(
                """
                SELECT bar_date, open, high, low, close, adjusted_close, volume
                FROM finance_eod_bars
                WHERE symbol = ? AND bar_date >= ?
                ORDER BY bar_date ASC
                """,
                (sym, start_date),
            ).fetchall()
        elif limit:
            rows = conn.execute(
                """
                SELECT bar_date, open, high, low, close, adjusted_close, volume
                FROM (
                    SELECT bar_date, open, high, low, close, adjusted_close, volume
                    FROM finance_eod_bars
                    WHERE symbol = ?
                    ORDER BY bar_date DESC
                    LIMIT ?
                ) sub
                ORDER BY bar_date ASC
                """,
                (sym, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT bar_date, open, high, low, close, adjusted_close, volume
                FROM finance_eod_bars
                WHERE symbol = ?
                ORDER BY bar_date ASC
                """,
                (sym,),
            ).fetchall()
    return [
        {
            "date": r["bar_date"],
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "adjusted_close": r["adjusted_close"],
            "volume": r["volume"],
        }
        for r in rows
    ]


def upsert_fundamental_facts(
    db_path: Path,
    symbol: str,
    period_type: str,
    series: dict[str, dict[str, float | None]],
    statement_map: dict[str, str],
    source: str,
    currency: str = "",
) -> int:
    """Stocke les séries fondamentales normalisées sur tout l'historique disponible."""
    sym = _norm_sym(symbol)
    if not sym or not series:
        return 0
    now_iso = _utc_iso()
    rows: list[tuple[Any, ...]] = []
    for metric_key, date_map in series.items():
        stmt_type = statement_map.get(metric_key, "other")
        for period_date, val in date_map.items():
            if not period_date or val is None:
                continue
            rows.append(
                (
                    sym,
                    period_type,
                    str(period_date)[:10],
                    stmt_type,
                    metric_key,
                    float(val),
                    currency or "",
                    source,
                    now_iso,
                )
            )
    if not rows:
        return 0
    with _connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO finance_fundamental_facts (
                symbol, period_type, period_date, statement_type, metric_key,
                value, currency, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, period_type, period_date, statement_type, metric_key) DO UPDATE SET
                value = excluded.value,
                currency = COALESCE(NULLIF(excluded.currency, ''), finance_fundamental_facts.currency),
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            rows,
        )
    return len(rows)


def load_fundamental_series(
    db_path: Path,
    symbol: str,
    period_type: str,
) -> tuple[dict[str, dict[str, float | None]], str | None, str | None, str | None]:
    """Charge les séries fondamentales stockées pour un symbole et une périodicité.

    Retourne `(series, currency, source, updated_at)`.
    """
    sym = _norm_sym(symbol)
    if not sym or not db_path.exists():
        return {}, None, None, None
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT period_date, metric_key, value, currency, source, updated_at
            FROM finance_fundamental_facts
            WHERE symbol = ? AND period_type = ?
            ORDER BY period_date ASC
            """,
            (sym, period_type),
        ).fetchall()
    if not rows:
        return {}, None, None, None
    series: dict[str, dict[str, float | None]] = {}
    currency: str | None = None
    sources: set[str] = set()
    latest_update: str | None = None
    for r in rows:
        key = str(r["metric_key"])
        series.setdefault(key, {})[str(r["period_date"])] = r["value"]
        if not currency and r["currency"]:
            currency = str(r["currency"])
        if r["source"]:
            sources.add(str(r["source"]))
        upd = r["updated_at"]
        if upd and (latest_update is None or upd > latest_update):
            latest_update = str(upd)
    source_summary = "+".join(sorted(sources)) if sources else None
    return series, currency, source_summary, latest_update


def save_snapshot(
    db_path: Path,
    symbol: str,
    provider: str,
    payload_type: str,
    raw_payload: Any,
    normalized_payload: Any,
    currency: str = "",
) -> None:
    """Sauvegarde un snapshot normalisé + son payload brut compressé en zlib."""
    sym = _norm_sym(symbol)
    if not sym:
        return
    now_ts = time.time()
    norm_json = json.dumps(normalized_payload, ensure_ascii=False, separators=(",", ":")) if normalized_payload is not None else None
    raw_bytes = json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if raw_payload is not None else b""
    compressed = zlib.compress(raw_bytes, level=6) if raw_bytes else None
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_raw_snapshots (
                symbol, provider, payload_type, fetched_at, currency, normalized_json, raw_zlib
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, provider, payload_type) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                currency = COALESCE(NULLIF(excluded.currency, ''), finance_raw_snapshots.currency),
                normalized_json = COALESCE(excluded.normalized_json, finance_raw_snapshots.normalized_json),
                raw_zlib = COALESCE(excluded.raw_zlib, finance_raw_snapshots.raw_zlib)
            """,
            (sym, provider, payload_type, now_ts, currency or "", norm_json, compressed),
        )


def get_snapshot(
    db_path: Path,
    symbol: str,
    payload_type: str,
    provider: str | None = None,
    max_age_seconds: float | None = None,
    include_raw: bool = False,
) -> dict[str, Any] | None:
    """Récupère le snapshot le plus récent pour `(symbol, payload_type)`."""
    sym = _norm_sym(symbol)
    if not sym or not db_path.exists():
        return None
    with _connect(db_path) as conn:
        if provider:
            row = conn.execute(
                """
                SELECT provider, fetched_at, currency, normalized_json, raw_zlib
                FROM finance_raw_snapshots
                WHERE symbol = ? AND provider = ? AND payload_type = ?
                LIMIT 1
                """,
                (sym, provider, payload_type),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT provider, fetched_at, currency, normalized_json, raw_zlib
                FROM finance_raw_snapshots
                WHERE symbol = ? AND payload_type = ?
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (sym, payload_type),
            ).fetchone()
    if not row:
        return None
    fetched_at = float(row["fetched_at"])
    if max_age_seconds is not None and (time.time() - fetched_at) > max_age_seconds:
        return None
    normalized = json.loads(row["normalized_json"]) if row["normalized_json"] else None
    raw = None
    if include_raw and row["raw_zlib"]:
        try:
            raw = json.loads(zlib.decompress(row["raw_zlib"]).decode("utf-8"))
        except Exception as exc:
            _logger.debug("Erreur décompression snapshot (%s/%s): %s", sym, payload_type, exc)
    return {
        "provider": row["provider"],
        "fetched_at": fetched_at,
        "updated_at": _utc_iso(fetched_at),
        "currency": row["currency"] or "",
        "normalized": normalized,
        "raw": raw,
    }


def get_warehouse_stats(db_path: Path, symbol: str) -> dict[str, Any]:
    """Retourne les compteurs de données stockées en entrepôt pour un symbole."""
    sym = _norm_sym(symbol)
    if not sym or not db_path.exists():
        return {
            "eod_bars_count": 0,
            "annual_periods_count": 0,
            "quarterly_periods_count": 0,
            "db_size_bytes": 0,
        }
    with _connect(db_path) as conn:
        bars_cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM finance_eod_bars WHERE symbol = ?", (sym,)
        ).fetchone()["cnt"]
        ann_cnt = conn.execute(
            "SELECT COUNT(DISTINCT period_date) AS cnt FROM finance_fundamental_facts WHERE symbol = ? AND period_type = 'annual'",
            (sym,),
        ).fetchone()["cnt"]
        qtr_cnt = conn.execute(
            "SELECT COUNT(DISTINCT period_date) AS cnt FROM finance_fundamental_facts WHERE symbol = ? AND period_type = 'quarterly'",
            (sym,),
        ).fetchone()["cnt"]
    try:
        db_size = db_path.stat().st_size
    except OSError:
        db_size = 0
    return {
        "eod_bars_count": int(bars_cnt or 0),
        "annual_periods_count": int(ann_cnt or 0),
        "quarterly_periods_count": int(qtr_cnt or 0),
        "db_size_bytes": int(db_size),
    }


def save_index_constituents(
    db_path: Path,
    index_code: str,
    constituents: list[dict[str, Any]],
) -> int:
    """Enregistre en lot la composition complète d'un indice boursier."""
    code = _norm_sym(index_code)
    if not code or not constituents:
        return 0
    now_ts = time.time()
    rows: list[tuple[Any, ...]] = []
    for idx, item in enumerate(constituents):
        sym = _norm_sym(str(item.get("symbol") or item.get("eod_ticker") or ""))
        if not sym:
            continue
        rows.append(
            (
                code,
                sym,
                _norm_sym(str(item.get("eod_ticker") or sym)),
                _norm_sym(str(item.get("yahoo_symbol") or sym)),
                str(item.get("name") or sym).strip(),
                str(item.get("sector") or "").strip(),
                str(item.get("industry") or "").strip(),
                str(item.get("exchange") or "").strip(),
                item.get("weight_pct"),
                int(item.get("position", idx)),
                now_ts,
            )
        )
    if not rows:
        return 0
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM finance_index_constituents WHERE index_code = ?", (code,))
        conn.executemany(
            """
            INSERT INTO finance_index_constituents (
                index_code, symbol, eod_ticker, yahoo_symbol, name,
                sector, industry, exchange, weight_pct, position, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)


def get_index_constituents(
    db_path: Path,
    index_code: str,
    max_age_seconds: float | None = 86400.0,
) -> tuple[list[dict[str, Any]], float | None]:
    """Lit les constituants mémorisés d'un indice (triés par position)."""
    code = _norm_sym(index_code)
    if not code or not db_path.exists():
        return [], None
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT symbol, eod_ticker, yahoo_symbol, name, sector, industry,
                   exchange, weight_pct, position, fetched_at
            FROM finance_index_constituents
            WHERE index_code = ?
            ORDER BY position ASC, symbol ASC
            """,
            (code,),
        ).fetchall()
    if not rows:
        return [], None
    fetched_at = float(rows[0]["fetched_at"])
    if max_age_seconds is not None and (time.time() - fetched_at) > max_age_seconds:
        return [], fetched_at
    items = [
        {
            "symbol": str(r["symbol"]),
            "eod_ticker": str(r["eod_ticker"] or r["symbol"]),
            "yahoo_symbol": str(r["yahoo_symbol"] or r["symbol"]),
            "name": str(r["name"] or r["symbol"]),
            "sector": str(r["sector"] or ""),
            "industry": str(r["industry"] or ""),
            "exchange": str(r["exchange"] or ""),
            "weight_pct": r["weight_pct"],
            "position": int(r["position"] or 0),
        }
        for r in rows
    ]
    return items, fetched_at


def get_cached_symbols_set(db_path: Path) -> set[str]:
    """Retourne l'ensemble des tickers/symboles disposant de données en entrepôt."""
    if not db_path.exists():
        return set()
    out: set[str] = set()
    with _connect(db_path) as conn:
        for r in conn.execute(
            """
            SELECT DISTINCT i.symbol, i.eod_ticker, i.yahoo_symbol
            FROM finance_instruments i
            WHERE EXISTS (SELECT 1 FROM finance_eod_bars b WHERE b.symbol = i.symbol LIMIT 1)
               OR EXISTS (SELECT 1 FROM finance_raw_snapshots s WHERE s.symbol = i.symbol LIMIT 1)
            """
        ).fetchall():
            for col in ("symbol", "eod_ticker", "yahoo_symbol"):
                v = str(r[col] or "").strip().upper()
                if v:
                    out.add(v)
                    if "." in v:
                        out.add(v.split(".", 1)[0])
        for r in conn.execute("SELECT DISTINCT symbol FROM finance_eod_bars").fetchall():
            v = str(r["symbol"] or "").strip().upper()
            if v:
                out.add(v)
    return out


def search_warehouse_catalog(
    db_path: Path,
    query: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Recherche rapide dans les instruments déjà chargés et les indices mémorisés."""
    clean = (query or "").strip()
    if not clean or not db_path.exists():
        return []
    like_pat = f"%{clean.upper()}%"
    cached_syms = get_cached_symbols_set(db_path)
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    with _connect(db_path) as conn:
        inst_rows = conn.execute(
            """
            SELECT symbol, eod_ticker, yahoo_symbol, short_name, long_name, exchange, currency, sector
            FROM finance_instruments
            WHERE UPPER(symbol) LIKE ?
               OR UPPER(COALESCE(eod_ticker, '')) LIKE ?
               OR UPPER(COALESCE(yahoo_symbol, '')) LIKE ?
               OR UPPER(COALESCE(short_name, '')) LIKE ?
               OR UPPER(COALESCE(long_name, '')) LIKE ?
               OR UPPER(COALESCE(isin, '')) LIKE ?
            ORDER BY
                CASE WHEN UPPER(symbol) = ? OR UPPER(COALESCE(yahoo_symbol, '')) = ? THEN 0 ELSE 1 END,
                updated_at DESC
            LIMIT ?
            """,
            (like_pat, like_pat, like_pat, like_pat, like_pat, like_pat, clean.upper(), clean.upper(), limit),
        ).fetchall()
        for r in inst_rows:
            sym = str(r["eod_ticker"] or r["symbol"]).upper()
            if sym in seen:
                continue
            seen.add(sym)
            results.append(
                {
                    "symbol": str(r["symbol"]),
                    "eod_ticker": str(r["eod_ticker"] or r["symbol"]),
                    "yahoo_symbol": str(r["yahoo_symbol"] or r["symbol"]),
                    "name": str(r["long_name"] or r["short_name"] or r["symbol"]),
                    "exchange": str(r["exchange"] or ""),
                    "sector": str(r["sector"] or ""),
                    "index_code": None,
                    "cached": sym in cached_syms or str(r["symbol"]).upper() in cached_syms,
                }
            )
        if len(results) < limit:
            idx_rows = conn.execute(
                """
                SELECT index_code, symbol, eod_ticker, yahoo_symbol, name, sector, exchange
                FROM finance_index_constituents
                WHERE UPPER(symbol) LIKE ?
                   OR UPPER(COALESCE(eod_ticker, '')) LIKE ?
                   OR UPPER(COALESCE(yahoo_symbol, '')) LIKE ?
                   OR UPPER(COALESCE(name, '')) LIKE ?
                   OR UPPER(COALESCE(sector, '')) LIKE ?
                ORDER BY position ASC
                LIMIT ?
                """,
                (like_pat, like_pat, like_pat, like_pat, like_pat, limit * 2),
            ).fetchall()
            for r in idx_rows:
                sym = str(r["eod_ticker"] or r["symbol"]).upper()
                if sym in seen:
                    continue
                seen.add(sym)
                results.append(
                    {
                        "symbol": str(r["symbol"]),
                        "eod_ticker": str(r["eod_ticker"] or r["symbol"]),
                        "yahoo_symbol": str(r["yahoo_symbol"] or r["symbol"]),
                        "name": str(r["name"] or r["symbol"]),
                        "exchange": str(r["exchange"] or ""),
                        "sector": str(r["sector"] or ""),
                        "index_code": str(r["index_code"]),
                        "cached": sym in cached_syms or str(r["symbol"]).upper() in cached_syms,
                    }
                )
                if len(results) >= limit:
                    break
    if len(results) < limit:
        exch_res = search_exchange_symbols(
            db_path,
            "ALL",
            query=clean,
            limit=max(1, limit - len(results)),
            offset=0,
        )
        for item in exch_res.get("items", []):
            sym = str(item.get("eod_ticker") or item.get("symbol") or "").upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            bare_sym = str(item.get("symbol") or sym).upper()
            exch_u = str(item.get("exchange") or "").upper()
            y_sym = bare_sym if exch_u == "US" else str(item.get("eod_ticker") or sym)
            results.append(
                {
                    "symbol": str(item.get("symbol") or sym),
                    "eod_ticker": str(item.get("eod_ticker") or sym),
                    "yahoo_symbol": y_sym,
                    "name": str(item.get("name") or sym),
                    "exchange": exch_u,
                    "sector": str(item.get("fund_family") or item.get("type") or ""),
                    "index_code": None,
                    "cached": bool(item.get("cached_in_warehouse")),
                }
            )
            if len(results) >= limit:
                break
    return results[:limit]


def get_warehouse_overview(db_path: Path) -> dict[str, Any]:
    """Retourne les statistiques globales de capacité de l'entrepôt SQLite."""
    if not db_path.exists():
        return {
            "instruments_count": 0,
            "eod_bars_count": 0,
            "fundamental_facts_count": 0,
            "snapshots_count": 0,
            "index_constituents_count": 0,
            "db_size_bytes": 0,
        }
    with _connect(db_path) as conn:
        inst_cnt = conn.execute("SELECT COUNT(*) FROM finance_instruments").fetchone()[0]
        bars_cnt = conn.execute("SELECT COUNT(*) FROM finance_eod_bars").fetchone()[0]
        facts_cnt = conn.execute("SELECT COUNT(*) FROM finance_fundamental_facts").fetchone()[0]
        snap_cnt = conn.execute("SELECT COUNT(*) FROM finance_raw_snapshots").fetchone()[0]
        idx_cnt = conn.execute("SELECT COUNT(*) FROM finance_index_constituents").fetchone()[0]
    try:
        db_size = db_path.stat().st_size
    except OSError:
        db_size = 0
    return {
        "instruments_count": int(inst_cnt or 0),
        "eod_bars_count": int(bars_cnt or 0),
        "fundamental_facts_count": int(facts_cnt or 0),
        "snapshots_count": int(snap_cnt or 0),
        "index_constituents_count": int(idx_cnt or 0),
        "db_size_bytes": int(db_size),
    }


def sync_user_watchlists_to_warehouse(
    db_path: Path,
    user_id: str,
    watchlists: list[dict[str, Any]],
    items: list[dict[str, Any]],
) -> None:
    """Sauvegarde en miroir dans `finance_warehouse.db` les listes de suivi et actions d'un utilisateur."""
    clean_uid = (user_id or "").strip()
    if not clean_uid:
        return
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM finance_user_watchlist_items WHERE user_id = ?", (clean_uid,))
        conn.execute("DELETE FROM finance_user_watchlists WHERE user_id = ?", (clean_uid,))
        if watchlists:
            conn.executemany(
                """
                INSERT INTO finance_user_watchlists (id, user_id, name, position, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(w["id"]),
                        clean_uid,
                        str(w["name"]),
                        int(w.get("position") or 0),
                        str(w.get("created_at") or _utc_iso()),
                        str(w.get("updated_at") or _utc_iso()),
                    )
                    for w in watchlists
                ],
            )
        if items:
            conn.executemany(
                """
                INSERT OR REPLACE INTO finance_user_watchlist_items
                    (id, user_id, list_id, symbol, yahoo_symbol, eod_ticker, name, exchange, currency, note, position, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(it["id"]),
                        clean_uid,
                        str(it["list_id"]),
                        str(it["symbol"]),
                        str(it.get("yahoo_symbol") or ""),
                        str(it.get("eod_ticker") or ""),
                        str(it.get("name") or it["symbol"]),
                        str(it.get("exchange") or ""),
                        str(it.get("currency") or "EUR"),
                        str(it.get("note") or "")[:240],
                        int(it.get("position") or 0),
                        str(it.get("created_at") or _utc_iso()),
                    )
                    for it in items
                    if it.get("list_id")
                ],
            )


def load_user_watchlists_from_warehouse(db_path: Path, user_id: str) -> dict[str, list[dict[str, Any]]]:
    """Charge depuis `finance_warehouse.db` les listes de suivi et actions mémorisées d'un utilisateur."""
    clean_uid = (user_id or "").strip()
    if not clean_uid or not db_path.exists():
        return {"lists": [], "items": []}
    with _connect(db_path) as conn:
        wl_rows = conn.execute(
            """
            SELECT id, user_id, name, position, created_at, updated_at
            FROM finance_user_watchlists
            WHERE user_id = ?
            ORDER BY position ASC, created_at ASC
            """,
            (clean_uid,),
        ).fetchall()
        item_rows = conn.execute(
            """
            SELECT id, user_id, list_id, symbol, yahoo_symbol, eod_ticker, name, exchange, currency, note, position, created_at
            FROM finance_user_watchlist_items
            WHERE user_id = ?
            ORDER BY position ASC, created_at ASC
            """,
            (clean_uid,),
        ).fetchall()
    return {
        "lists": [dict(r) for r in wl_rows],
        "items": [dict(r) for r in item_rows],
    }


def _row_to_ai_analysis(row: sqlite3.Row) -> dict[str, Any]:
    try:
        news_sources = json.loads(row["news_sources_json"]) if row["news_sources_json"] else []
    except Exception:
        news_sources = []
    try:
        news_articles = json.loads(row["news_articles_json"]) if row["news_articles_json"] else []
    except Exception:
        news_articles = []
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "company_name": row["company_name"] or "",
        "kind": row["kind"],
        "expert_id": row["expert_id"] or "",
        "expert_name": row["expert_name"] or "",
        "model": row["model"] or "",
        "question": row["question"] or None,
        "verdict": row["verdict"] or "",
        "conviction": row["conviction"] or "",
        "horizon": row["horizon"] or "",
        "markdown": row["markdown"] or "",
        "content_html": row["content_html"] or "",
        "news_sources": news_sources if isinstance(news_sources, list) else [],
        "news_articles": news_articles if isinstance(news_articles, list) else [],
        "created_at": row["created_at"],
    }


def save_ai_analysis_entry(
    db_path: Path,
    *,
    symbol: str,
    company_name: str = "",
    kind: str,
    expert_id: str = "",
    expert_name: str = "",
    model: str = "",
    question: str | None = None,
    verdict: str = "",
    conviction: str = "",
    horizon: str = "",
    markdown: str = "",
    content_html: str = "",
    news_sources: list[str] | None = None,
    news_articles: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
    analysis_id: str | None = None,
) -> dict[str, Any]:
    """Enregistre et date une analyse IA (avis d'expert ou synthèse dossier) dans l'historique persistant."""
    sym = _norm_sym(symbol)
    entry_id = analysis_id or str(uuid.uuid4())
    iso_date = created_at or _utc_iso()
    sources_list = list(news_sources or [])
    articles_list = list(news_articles or [])
    sources_json = json.dumps(sources_list, ensure_ascii=False, separators=(",", ":"))
    articles_json = json.dumps(articles_list, ensure_ascii=False, separators=(",", ":"))

    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_ai_analyses (
                id, symbol, company_name, kind, expert_id, expert_name, model,
                question, verdict, conviction, horizon, markdown, content_html,
                news_sources_json, news_articles_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                sym,
                (company_name or "").strip(),
                (kind or "dossier").strip().lower(),
                (expert_id or "").strip(),
                (expert_name or "").strip(),
                (model or "").strip(),
                question.strip() if isinstance(question, str) and question.strip() else None,
                (verdict or "").strip(),
                (conviction or "").strip(),
                (horizon or "").strip(),
                markdown or "",
                content_html or "",
                sources_json,
                articles_json,
                iso_date,
            ),
        )

    return {
        "id": entry_id,
        "symbol": sym,
        "company_name": (company_name or "").strip(),
        "kind": (kind or "dossier").strip().lower(),
        "expert_id": (expert_id or "").strip(),
        "expert_name": (expert_name or "").strip(),
        "model": (model or "").strip(),
        "question": question.strip() if isinstance(question, str) and question.strip() else None,
        "verdict": (verdict or "").strip(),
        "conviction": (conviction or "").strip(),
        "horizon": (horizon or "").strip(),
        "markdown": markdown or "",
        "content_html": content_html or "",
        "news_sources": sources_list,
        "news_articles": articles_list,
        "created_at": iso_date,
    }


def list_ai_analyses(
    db_path: Path,
    *,
    symbol: str | None = None,
    kind: str | None = None,
    expert_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retourne l'historique daté des analyses IA sauvegardées (du plus récent au plus ancien)."""
    if not db_path.exists():
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if symbol and symbol.strip():
        sym = resolve_canonical_symbol(db_path, symbol.strip())
        clauses.append("symbol = ?")
        params.append(sym)
    if kind and kind.strip():
        clauses.append("kind = ?")
        params.append(kind.strip().lower())
    if expert_id and expert_id.strip():
        clauses.append("expert_id = ?")
        params.append(expert_id.strip())

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    safe_limit = max(1, min(500, int(limit or 100)))
    params.append(safe_limit)

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM finance_ai_analyses
            {where_sql}
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_ai_analysis(r) for r in rows]


def get_ai_analysis_entry(db_path: Path, analysis_id: str) -> dict[str, Any] | None:
    """Retourne une analyse IA archivée par son identifiant."""
    clean_id = (analysis_id or "").strip()
    if not clean_id or not db_path.exists():
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM finance_ai_analyses WHERE id = ? LIMIT 1",
            (clean_id,),
        ).fetchone()
    return _row_to_ai_analysis(row) if row else None


def delete_ai_analysis_entry(db_path: Path, analysis_id: str) -> bool:
    """Supprime une analyse IA archivée par son identifiant."""
    clean_id = (analysis_id or "").strip()
    if not clean_id or not db_path.exists():
        return False
    with _connect(db_path) as conn:
        cur = conn.execute("DELETE FROM finance_ai_analyses WHERE id = ?", (clean_id,))
        return (cur.rowcount or 0) > 0


def has_ai_analysis_for(
    db_path: Path,
    symbol: str,
    kind: str,
    expert_id: str = "",
) -> bool:
    """Indique si au moins une analyse datée existe déjà pour `(symbol, kind, expert_id)`."""
    if not db_path.exists():
        return False
    sym = _norm_sym(symbol)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM finance_ai_analyses
            WHERE symbol = ? AND kind = ? AND expert_id = ?
            LIMIT 1
            """,
            (sym, kind.strip().lower(), expert_id.strip()),
        ).fetchone()
    return bool(row)


def replace_exchange_symbols(
    db_path: Path,
    exchange_code: str,
    rows: list[dict[str, Any]],
) -> int:
    """Remplace atomiquement le catalogue des symboles d'un marché EODHD (ex. EUFUND, PA, US) et son index FTS5."""
    exch = _norm_sym(exchange_code)
    if not exch or not rows:
        return 0
    now_ts = time.time()

    with _connect(db_path) as conn:
        existing_families: dict[str, str] = {}
        fam_rows = conn.execute(
            "SELECT symbol, fund_family FROM finance_exchange_symbols WHERE exchange_code = ? AND fund_family IS NOT NULL AND fund_family != ''",
            (exch,),
        ).fetchall()
        for fr in fam_rows:
            existing_families[str(fr["symbol"]).upper()] = str(fr["fund_family"]).strip()

        payload: list[tuple[Any, ...]] = []
        fts_payload: list[tuple[Any, ...]] = []
        seen: set[str] = set()
        for row in rows:
            sym = _norm_sym(str(row.get("symbol") or row.get("code") or ""))
            if not sym or sym in seen:
                continue
            seen.add(sym)
            eod_t = _norm_sym(str(row.get("eod_ticker") or f"{sym}.{exch}"))
            name = str(row.get("name") or sym).strip() or sym
            isin = _norm_sym(str(row.get("isin") or "")) or None
            fam = str(row.get("fund_family") or "").strip() or existing_families.get(sym) or None
            country = str(row.get("country") or "").strip() or None
            currency = _norm_sym(str(row.get("currency") or "")) or None
            itype = str(row.get("type") or "").strip() or None
            payload.append((exch, sym, eod_t, name, isin, fam, country, currency, itype, now_ts))
            fts_payload.append((exch, sym, eod_t, name, isin or "", fam or "", country or "", currency or "", itype or ""))

        if not payload:
            return 0

        conn.execute("DELETE FROM finance_exchange_symbols WHERE exchange_code = ?", (exch,))
        conn.executemany(
            """
            INSERT OR REPLACE INTO finance_exchange_symbols (
                exchange_code, symbol, eod_ticker, name, isin, fund_family, country, currency, type, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        if _fts5_exists(conn):
            try:
                conn.execute("DELETE FROM finance_exchange_symbols_fts WHERE exchange_code = ?", (exch,))
                conn.executemany(
                    """
                    INSERT INTO finance_exchange_symbols_fts (
                        exchange_code, symbol, eod_ticker, name, isin, fund_family, country, currency, type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    fts_payload,
                )
            except sqlite3.OperationalError as exc:
                _logger.warning("Mise à jour FTS5 ignorée pour %s: %s", exch, exc)
    return len(payload)


def update_exchange_symbol_fund_family(
    db_path: Path,
    symbol_or_ticker: str,
    fund_family: str | None,
) -> bool:
    """Enrichit `fund_family` (société de gestion) dans le catalogue local & FTS5 lors d'une consultation."""
    clean_sym = _norm_sym(symbol_or_ticker)
    clean_fam = (fund_family or "").strip()
    if not clean_sym or not clean_fam or not db_path.exists():
        return False
    bare = clean_sym.split(".", 1)[0]
    updated = False
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT exchange_code, symbol, eod_ticker, name, isin, country, currency, type
            FROM finance_exchange_symbols
            WHERE UPPER(eod_ticker) = ? OR UPPER(symbol) = ?
            """,
            (clean_sym, bare),
        ).fetchall()
        if not rows:
            return False
        for r in rows:
            conn.execute(
                """
                UPDATE finance_exchange_symbols
                SET fund_family = ?
                WHERE exchange_code = ? AND symbol = ?
                """,
                (clean_fam[:120], r["exchange_code"], r["symbol"]),
            )
            if _fts5_exists(conn):
                try:
                    conn.execute(
                        "DELETE FROM finance_exchange_symbols_fts WHERE exchange_code = ? AND symbol = ?",
                        (r["exchange_code"], r["symbol"]),
                    )
                    conn.execute(
                        """
                        INSERT INTO finance_exchange_symbols_fts (
                            exchange_code, symbol, eod_ticker, name, isin, fund_family, country, currency, type
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            r["exchange_code"],
                            r["symbol"],
                            r["eod_ticker"],
                            r["name"],
                            r["isin"] or "",
                            clean_fam[:120],
                            r["country"] or "",
                            r["currency"] or "",
                            r["type"] or "",
                        ),
                    )
                except sqlite3.OperationalError:
                    pass
            updated = True
    return updated


def get_exchange_catalog_meta(db_path: Path, exchange_code: str = "ALL") -> dict[str, Any]:
    """Retourne les métadonnées (total, fraîcheur, devises, pays, types, sociétés de gestion) d'un catalogue ou de tous."""
    exch = _norm_sym(exchange_code) or "ALL"
    empty = {
        "total": 0,
        "fetched_at": None,
        "currencies": [],
        "countries": [],
        "types": [],
        "fund_families": [],
        "exchanges": {},
    }
    if not db_path.exists():
        return empty
    all_mode = exch == "ALL"
    where_exch = "" if all_mode else "WHERE exchange_code = ?"
    exch_params: tuple[Any, ...] = () if all_mode else (exch,)

    with _connect(db_path) as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS cnt, MAX(fetched_at) AS max_ts FROM finance_exchange_symbols {where_exch}",
            exch_params,
        ).fetchone()
        total = int((row["cnt"] if row else 0) or 0)
        fetched_at = float(row["max_ts"]) if (row and row["max_ts"] is not None) else None

        exch_rows = conn.execute(
            """
            SELECT exchange_code, COUNT(*) AS cnt, MAX(fetched_at) AS max_ts
            FROM finance_exchange_symbols
            GROUP BY exchange_code
            """
        ).fetchall()
        exchanges_map = {
            str(r["exchange_code"]): {
                "total": int(r["cnt"] or 0),
                "fetched_at": float(r["max_ts"]) if r["max_ts"] is not None else None,
            }
            for r in exch_rows
        }
        if total == 0:
            return {**empty, "exchanges": exchanges_map}

        prefix = "WHERE " if all_mode else "WHERE exchange_code = ? AND "
        curr_rows = conn.execute(
            f"""
            SELECT currency, COUNT(*) AS c
            FROM finance_exchange_symbols
            {prefix}currency IS NOT NULL AND currency != ''
            GROUP BY currency
            ORDER BY c DESC, currency ASC
            LIMIT 40
            """,
            exch_params,
        ).fetchall()
        country_rows = conn.execute(
            f"""
            SELECT country, COUNT(*) AS c
            FROM finance_exchange_symbols
            {prefix}country IS NOT NULL AND country != ''
            GROUP BY country
            ORDER BY c DESC, country ASC
            LIMIT 60
            """,
            exch_params,
        ).fetchall()
        type_rows = conn.execute(
            f"""
            SELECT type, COUNT(*) AS c
            FROM finance_exchange_symbols
            {prefix}type IS NOT NULL AND type != ''
            GROUP BY type
            ORDER BY c DESC, type ASC
            LIMIT 30
            """,
            exch_params,
        ).fetchall()
        fam_rows = conn.execute(
            f"""
            SELECT fund_family, COUNT(*) AS c
            FROM finance_exchange_symbols
            {prefix}fund_family IS NOT NULL AND fund_family != ''
            GROUP BY fund_family
            ORDER BY c DESC, fund_family ASC
            LIMIT 60
            """,
            exch_params,
        ).fetchall()
    return {
        "total": total,
        "fetched_at": fetched_at,
        "currencies": [str(r["currency"]) for r in curr_rows],
        "countries": [str(r["country"]) for r in country_rows],
        "types": [str(r["type"]) for r in type_rows],
        "fund_families": [str(r["fund_family"]) for r in fam_rows],
        "exchanges": exchanges_map,
    }


def search_exchange_symbols(
    db_path: Path,
    exchange_code: str,
    *,
    query: str = "",
    currency: str = "",
    country: str = "",
    instrument_type: str = "",
    fund_family: str = "",
    limit: int = 60,
    offset: int = 0,
) -> dict[str, Any]:
    """Recherche (FTS5 prioritaire + repli LIKE) et pagine les catalogues EODHD stockés (EUFUND, PA, US, XETRA, LSE, CC ou ALL)."""
    exch = _norm_sym(exchange_code) or "ALL"
    if not db_path.exists():
        return {"matched": 0, "items": []}

    all_mode = exch == "ALL"
    base_clauses: list[str] = []
    base_params: list[Any] = []
    if not all_mode:
        base_clauses.append("s.exchange_code = ?")
        base_params.append(exch)

    clean_curr = _norm_sym(currency)
    if clean_curr:
        base_clauses.append("s.currency = ?")
        base_params.append(clean_curr)

    clean_country = (country or "").strip()
    if clean_country:
        base_clauses.append("LOWER(COALESCE(s.country, '')) = ?")
        base_params.append(clean_country.lower())

    clean_type = (instrument_type or "").strip()
    if clean_type:
        base_clauses.append("LOWER(COALESCE(s.type, '')) = ?")
        base_params.append(clean_type.lower())

    clean_fam = (fund_family or "").strip()
    if clean_fam:
        base_clauses.append("LOWER(COALESCE(s.fund_family, '')) = ?")
        base_params.append(clean_fam.lower())

    clean_q = (query or "").strip()
    safe_limit = max(1, min(300, int(limit or 60)))
    safe_offset = max(0, int(offset or 0))
    cached_syms = get_cached_symbols_set(db_path)

    fts_query = _build_fts_match_query(clean_q, exch) if clean_q else None

    order_sql = "ORDER BY s.name ASC, s.symbol ASC"
    order_params: list[Any] = []
    if clean_q:
        q_up = clean_q.upper()
        order_sql = (
            "ORDER BY CASE "
            "WHEN UPPER(s.symbol) = ? OR UPPER(s.eod_ticker) = ? OR UPPER(COALESCE(s.isin, '')) = ? THEN 0 "
            "WHEN UPPER(s.name) LIKE ? THEN 1 "
            "ELSE 2 END, s.name ASC, s.symbol ASC"
        )
        order_params = [q_up, q_up, q_up, f"{q_up}%"]

    rows: list[sqlite3.Row] = []
    matched = 0

    with _connect(db_path) as conn:
        used_fts = False
        if fts_query and _fts5_exists(conn):
            try:
                fts_where = " AND ".join(base_clauses) if base_clauses else "1=1"
                join_sql = (
                    "FROM finance_exchange_symbols s "
                    "JOIN ("
                    "SELECT DISTINCT exchange_code, symbol "
                    "FROM finance_exchange_symbols_fts "
                    "WHERE finance_exchange_symbols_fts MATCH ?"
                    ") f ON f.exchange_code = s.exchange_code AND f.symbol = s.symbol "
                    f"WHERE {fts_where}"
                )
                fts_params = [fts_query, *base_params]
                matched_row = conn.execute(
                    f"SELECT COUNT(*) AS cnt {join_sql}",
                    fts_params,
                ).fetchone()
                matched = int((matched_row["cnt"] if matched_row else 0) or 0)
                rows = conn.execute(
                    f"""
                    SELECT s.exchange_code, s.symbol, s.eod_ticker, s.name, s.isin, s.fund_family, s.country, s.currency, s.type
                    {join_sql}
                    {order_sql}
                    LIMIT ? OFFSET ?
                    """,
                    [*fts_params, *order_params, safe_limit, safe_offset],
                ).fetchall()
                used_fts = True
            except sqlite3.OperationalError:
                used_fts = False

        if not used_fts:
            like_clauses = list(base_clauses)
            like_params = list(base_params)
            if clean_q:
                terms = [t for t in clean_q.upper().split() if t][:5]
                for term in terms:
                    like = f"%{term}%"
                    like_clauses.append(
                        "("
                        "UPPER(s.name) LIKE ? "
                        "OR UPPER(s.symbol) LIKE ? "
                        "OR UPPER(s.eod_ticker) LIKE ? "
                        "OR UPPER(COALESCE(s.isin, '')) LIKE ? "
                        "OR UPPER(COALESCE(s.fund_family, '')) LIKE ?"
                        ")"
                    )
                    like_params.extend([like, like, like, like, like])
            where_sql = " AND ".join(like_clauses) if like_clauses else "1=1"
            matched_row = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM finance_exchange_symbols s WHERE {where_sql}",
                like_params,
            ).fetchone()
            matched = int((matched_row["cnt"] if matched_row else 0) or 0)
            rows = conn.execute(
                f"""
                SELECT s.exchange_code, s.symbol, s.eod_ticker, s.name, s.isin, s.fund_family, s.country, s.currency, s.type
                FROM finance_exchange_symbols s
                WHERE {where_sql}
                {order_sql}
                LIMIT ? OFFSET ?
                """,
                [*like_params, *order_params, safe_limit, safe_offset],
            ).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        sym = str(r["symbol"]).upper()
        eod_t = str(r["eod_ticker"]).upper()
        items.append(
            {
                "symbol": sym,
                "eod_ticker": eod_t,
                "name": str(r["name"] or sym),
                "isin": r["isin"] or None,
                "fund_family": r["fund_family"] or None,
                "country": str(r["country"] or ""),
                "currency": str(r["currency"] or ""),
                "type": str(r["type"] or "Fund"),
                "exchange": str(r["exchange_code"] or exch),
                "cached_in_warehouse": sym in cached_syms or eod_t in cached_syms,
            }
        )
    return {"matched": matched, "items": items}


def lookup_exchange_symbol(
    db_path: Path,
    ticker_or_isin: str,
    exchange_code: str = "EUFUND",
) -> dict[str, Any] | None:
    """Résout un code, ticker EOD ou ISIN depuis `finance_exchange_symbols`."""
    clean = _norm_sym(ticker_or_isin)
    exch = _norm_sym(exchange_code)
    if not clean or not exch or not db_path.exists():
        return None
    bare = clean.split(".", 1)[0]
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT exchange_code, symbol, eod_ticker, name, isin, fund_family, country, currency, type
            FROM finance_exchange_symbols
            WHERE exchange_code = ?
              AND (UPPER(eod_ticker) = ? OR UPPER(symbol) = ? OR UPPER(COALESCE(isin, '')) = ?)
            LIMIT 1
            """,
            (exch, clean, bare, bare),
        ).fetchone()
    if not row:
        return None
    return {
        "symbol": str(row["symbol"]).upper(),
        "eod_ticker": str(row["eod_ticker"]).upper(),
        "name": str(row["name"] or row["symbol"]),
        "isin": row["isin"] or None,
        "fund_family": row["fund_family"] or None,
        "country": str(row["country"] or ""),
        "currency": str(row["currency"] or ""),
        "type": str(row["type"] or "Fund"),
        "exchange": str(row["exchange_code"] or exch),
    }


DEFAULT_SYNC_PREFERENCES: dict[str, Any] = {
    "enabled": True,
    "principal_indices": True,
    "indx_catalog": True,
    "index_codes": [],
    "watchlists": False,
    "exchanges": [],
}


def _normalize_sync_preferences(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}

    def _clean_list(val: Any) -> list[str]:
        if not isinstance(val, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in val:
            code = str(item or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
        return out

    return {
        "enabled": bool(src.get("enabled", DEFAULT_SYNC_PREFERENCES["enabled"])),
        "principal_indices": bool(
            src.get("principal_indices", DEFAULT_SYNC_PREFERENCES["principal_indices"])
        ),
        "indx_catalog": bool(src.get("indx_catalog", DEFAULT_SYNC_PREFERENCES["indx_catalog"])),
        "index_codes": _clean_list(src.get("index_codes")),
        "watchlists": bool(src.get("watchlists", DEFAULT_SYNC_PREFERENCES["watchlists"])),
        "exchanges": _clean_list(src.get("exchanges")),
    }


def get_sync_preferences(db_path: Path, pref_key: str = "default") -> dict[str, Any]:
    """Lit les préférences de synchronisation quotidienne enregistrées (indices activés par défaut)."""
    if not db_path.exists():
        return {
            **DEFAULT_SYNC_PREFERENCES,
            "last_run_at": None,
            "last_status": None,
            "updated_at": None,
        }
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT config_json, last_run_at, last_status_json, updated_at
            FROM finance_sync_preferences
            WHERE pref_key = ?
            """,
            (pref_key,),
        ).fetchone()
    if not row:
        return {
            **DEFAULT_SYNC_PREFERENCES,
            "last_run_at": None,
            "last_status": None,
            "updated_at": None,
        }
    try:
        cfg = _normalize_sync_preferences(json.loads(row["config_json"] or "{}"))
    except Exception:
        cfg = dict(DEFAULT_SYNC_PREFERENCES)
    try:
        last_status = json.loads(row["last_status_json"]) if row["last_status_json"] else None
    except Exception:
        last_status = None
    return {
        **cfg,
        "last_run_at": row["last_run_at"] or None,
        "last_status": last_status,
        "updated_at": row["updated_at"] or None,
    }


def save_sync_preferences(
    db_path: Path,
    config: dict[str, Any],
    pref_key: str = "default",
) -> dict[str, Any]:
    """Enregistre les préférences de synchronisation quotidienne dans `finance_warehouse.db`."""
    clean_cfg = _normalize_sync_preferences(config)
    now_iso = _utc_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_sync_preferences (pref_key, config_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(pref_key) DO UPDATE SET
                config_json = excluded.config_json,
                updated_at = excluded.updated_at
            """,
            (pref_key, json.dumps(clean_cfg, ensure_ascii=False), now_iso),
        )
    return get_sync_preferences(db_path, pref_key=pref_key)


def record_sync_run_status(
    db_path: Path,
    status_payload: dict[str, Any],
    pref_key: str = "default",
) -> dict[str, Any]:
    """Mémorise l'horodatage et le compte-rendu de la dernière exécution de synchro quotidienne."""
    now_iso = _utc_iso()
    current = get_sync_preferences(db_path, pref_key=pref_key)
    cfg = _normalize_sync_preferences(current)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_sync_preferences (pref_key, config_json, last_run_at, last_status_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(pref_key) DO UPDATE SET
                last_run_at = excluded.last_run_at,
                last_status_json = excluded.last_status_json,
                updated_at = excluded.updated_at
            """,
            (
                pref_key,
                json.dumps(cfg, ensure_ascii=False),
                now_iso,
                json.dumps(status_payload, ensure_ascii=False),
                now_iso,
            ),
        )
    return get_sync_preferences(db_path, pref_key=pref_key)


def list_warehouse_watchlist_items_for_sync(db_path: Path) -> list[dict[str, Any]]:
    """Retourne les instruments distincts présents dans les watchlists miroirs pour synchro quotidienne."""
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT symbol, yahoo_symbol, eod_ticker, name, exchange, currency
            FROM finance_user_watchlist_items
            GROUP BY UPPER(COALESCE(NULLIF(eod_ticker, ''), symbol))
            ORDER BY MIN(position) ASC
            """
        ).fetchall()
    return [
        {
            "id": str(r["eod_ticker"] or r["symbol"]),
            "symbol": str(r["symbol"]),
            "yahoo_symbol": str(r["yahoo_symbol"] or r["symbol"]),
            "eod_ticker": str(r["eod_ticker"] or r["symbol"]),
            "name": str(r["name"] or r["symbol"]),
            "exchange": str(r["exchange"] or ""),
            "currency": str(r["currency"] or "EUR"),
            "position": idx,
        }
        for idx, r in enumerate(rows)
    ]
