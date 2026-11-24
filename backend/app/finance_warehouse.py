"""Entrepôt local haute densité (SQLite WAL + snapshots zlib) pour les données boursières.

Isolé dans `Settings.resolved_finance_data_dir` (volume Docker dédié `finance_data`)
afin de stocker sans limite de profondeur les barres EOD, les états financiers
historiques normalisés et les payloads bruts compressés EODHD / Yahoo Finance.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sqlite3
import threading
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
_INIT_LOCK = threading.Lock()
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
    last_fundamentals_run_at TEXT,
    last_status_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_screener_snapshots (
    symbol TEXT PRIMARY KEY,
    eod_ticker TEXT,
    yahoo_symbol TEXT,
    asset_type TEXT NOT NULL DEFAULT 'stock',
    name TEXT NOT NULL DEFAULT '',
    exchange TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    market_zone TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    cap_category TEXT NOT NULL DEFAULT '',
    indices_csv TEXT NOT NULL DEFAULT '',
    market_cap REAL,
    price REAL,
    volume REAL,
    avg_volume_20d REAL,
    rel_volume_20d REAL,
    change_1d_pct REAL,
    change_1w_pct REAL,
    change_1m_pct REAL,
    change_3m_pct REAL,
    change_ytd_pct REAL,
    change_1y_pct REAL,
    dist_52w_high_pct REAL,
    dist_52w_low_pct REAL,
    pe_ttm REAL,
    pe_forward REAL,
    peg_ratio REAL,
    ev_ebitda REAL,
    pb_ratio REAL,
    fcf_yield_pct REAL,
    dividend_yield_pct REAL,
    roic_pct REAL,
    roe_pct REAL,
    op_margin_pct REAL,
    net_margin_pct REAL,
    net_debt_ebitda REAL,
    debt_to_equity_pct REAL,
    current_ratio REAL,
    rev_cagr_3y_pct REAL,
    eps_cagr_3y_pct REAL,
    beta REAL,
    analyst_upside_pct REAL,
    ih_score REAL,
    piotroski_f REAL,
    altman_z REAL,
    mos_intrinsic_pct REAL,
    sma20 REAL,
    sma50 REAL,
    sma200 REAL,
    ema20 REAL,
    ema50 REAL,
    dist_sma50_pct REAL,
    dist_sma200_pct REAL,
    rsi_14 REAL,
    macd_line REAL,
    macd_signal REAL,
    macd_hist REAL,
    macd_cross INTEGER,
    sma_golden_cross INTEGER,
    boll_pct_b REAL,
    boll_width_pct REAL,
    adx_14 REAL,
    stoch_k REAL,
    atr_pct REAL,
    roc_12 REAL,
    supertrend_dir INTEGER,
    has_fundamentals INTEGER NOT NULL DEFAULT 0,
    bars_count INTEGER NOT NULL DEFAULT 0,
    bars_date TEXT,
    fundamentals_updated_at TEXT,
    computed_at TEXT NOT NULL,
    scores_json TEXT NOT NULL DEFAULT '{}',
    sparkline_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_fin_scr_exch_sec ON finance_screener_snapshots (exchange, sector);

CREATE TABLE IF NOT EXISTS finance_fundamentals_queue (
    symbol TEXT PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 99,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    last_fetched_at TEXT,
    last_period_end TEXT,
    last_report_date TEXT,
    typical_report_days TEXT NOT NULL DEFAULT '[]',
    cadence TEXT NOT NULL DEFAULT '',
    next_due_at TEXT,
    reported_pending INTEGER NOT NULL DEFAULT 0,
    stale_retries INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_fin_fundq_due ON finance_fundamentals_queue (priority, next_due_at);
CREATE INDEX IF NOT EXISTS idx_fin_scr_mcap ON finance_screener_snapshots (market_cap);
CREATE INDEX IF NOT EXISTS idx_fin_scr_pe ON finance_screener_snapshots (pe_ttm);
CREATE INDEX IF NOT EXISTS idx_fin_scr_roic ON finance_screener_snapshots (roic_pct);
CREATE INDEX IF NOT EXISTS idx_fin_scr_rsi ON finance_screener_snapshots (rsi_14);
CREATE INDEX IF NOT EXISTS idx_fin_scr_scores ON finance_screener_snapshots (ih_score, piotroski_f);

CREATE TABLE IF NOT EXISTS finance_screener_technicals (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    price REAL,
    rel_volume_20d REAL,
    sma20 REAL,
    sma50 REAL,
    sma200 REAL,
    ema20 REAL,
    ema50 REAL,
    dist_sma50_pct REAL,
    dist_sma200_pct REAL,
    rsi_14 REAL,
    macd_line REAL,
    macd_signal REAL,
    macd_hist REAL,
    macd_cross INTEGER,
    sma_golden_cross INTEGER,
    boll_pct_b REAL,
    boll_width_pct REAL,
    adx_14 REAL,
    stoch_k REAL,
    atr_pct REAL,
    roc_12 REAL,
    supertrend_dir INTEGER,
    isopressure_raw REAL,
    isopressure_p5 REAL,
    isopressure_p20 REAL,
    isopressure_p50 REAL,
    isopressure_p100 REAL,
    isopressure_p200 REAL,
    isopressure_20_50_diff REAL,
    isopressure_20_50_dir INTEGER,
    isopressure_20_50_cross INTEGER,
    isopressure_5_20_cross INTEGER,
    bars_count INTEGER NOT NULL DEFAULT 0,
    bars_date TEXT,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (symbol, timeframe)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_fin_scr_tech_tf_rsi ON finance_screener_technicals (timeframe, rsi_14);
CREATE INDEX IF NOT EXISTS idx_fin_scr_tech_tf_iso ON finance_screener_technicals (timeframe, isopressure_20_50_dir, isopressure_20_50_diff);

CREATE TABLE IF NOT EXISTS finance_eodhd_daily_usage (
    usage_day TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (usage_day, endpoint)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS finance_sync_runtime_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_game_profiles (
    user_id TEXT PRIMARY KEY,
    starting_capital REAL NOT NULL DEFAULT 10000.0,
    equity REAL NOT NULL DEFAULT 10000.0,
    rounds_played INTEGER NOT NULL DEFAULT 0,
    trades_taken INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    draws INTEGER NOT NULL DEFAULT 0,
    current_streak INTEGER NOT NULL DEFAULT 0,
    best_streak INTEGER NOT NULL DEFAULT 0,
    total_pnl REAL NOT NULL DEFAULT 0.0,
    gross_profit REAL NOT NULL DEFAULT 0.0,
    gross_loss REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS finance_game_rounds (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    blind_mode INTEGER NOT NULL DEFAULT 1,
    universe_type TEXT NOT NULL,
    universe_value TEXT NOT NULL DEFAULT '',
    timeframe TEXT NOT NULL,
    horizon_code TEXT NOT NULL,
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL DEFAULT '',
    exchange TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    cutoff_index INTEGER NOT NULL,
    horizon_bars INTEGER NOT NULL,
    current_step INTEGER NOT NULL DEFAULT 0,
    cutoff_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    position_side TEXT,
    position_status TEXT NOT NULL DEFAULT 'none',
    position_size_pct REAL NOT NULL DEFAULT 100.0,
    stake_amount REAL NOT NULL DEFAULT 0.0,
    entry_step INTEGER,
    entry_date TEXT,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    exit_step INTEGER,
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    return_pct REAL,
    pnl_amount REAL,
    buy_hold_return_pct REAL,
    bars_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fin_game_rounds_user_date ON finance_game_rounds (user_id, created_at DESC);
"""


def warehouse_db_path(settings: Settings) -> Path:
    """Retourne le chemin vers la base SQLite de l'entrepôt financier."""
    primary_dir = settings.resolved_finance_data_dir
    fallback_dir = (settings.app_data_dir / "finance").resolve()
    if primary_dir != fallback_dir:
        try:
            primary_dir.mkdir(parents=True, exist_ok=True)
            if os.access(primary_dir, os.W_OK | os.X_OK):
                return primary_dir / _WAREHOUSE_FILENAME
            _logger.warning(
                "Répertoire entrepôt financier non accessible en écriture (%s); repli sur %s",
                primary_dir,
                fallback_dir,
            )
        except OSError as exc:
            _logger.warning(
                "Impossible de créer le répertoire entrepôt financier (%s: %s); repli sur %s",
                primary_dir,
                exc,
                fallback_dir,
            )
        return fallback_dir / _WAREHOUSE_FILENAME
    return primary_dir / _WAREHOUSE_FILENAME


def _utc_iso(ts: float | None = None) -> str:
    dt = datetime.datetime.fromtimestamp(ts if ts is not None else time.time(), datetime.timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def init_warehouse(db_path: Path) -> None:
    """Crée le répertoire cible et initialise le schéma SQLite en mode WAL (thread-safe)."""
    key = str(db_path)
    if key in _INITIALIZED_PATHS and db_path.exists():
        return
    with _INIT_LOCK:
        if key in _INITIALIZED_PATHS and db_path.exists():
            return
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA busy_timeout=30000;")
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
            sync_cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(finance_sync_preferences)").fetchall()
            }
            if "last_fundamentals_run_at" not in sync_cols:
                conn.execute("ALTER TABLE finance_sync_preferences ADD COLUMN last_fundamentals_run_at TEXT")
            scr_cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(finance_screener_snapshots)").fetchall()
            }
            if "market_zone" not in scr_cols:
                conn.execute("ALTER TABLE finance_screener_snapshots ADD COLUMN market_zone TEXT NOT NULL DEFAULT ''")
            added_asset_type = "asset_type" not in scr_cols
            if added_asset_type:
                conn.execute("ALTER TABLE finance_screener_snapshots ADD COLUMN asset_type TEXT NOT NULL DEFAULT 'stock'")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fin_scr_geo ON finance_screener_snapshots (market_zone, country, exchange)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fin_scr_eod ON finance_screener_snapshots (eod_ticker)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fin_scr_asset_exch ON finance_screener_snapshots (asset_type, exchange)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_type ON finance_exchange_symbols (exchange_code, type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fin_exch_sym_family ON finance_exchange_symbols (exchange_code, fund_family)"
            )
            if added_asset_type:
                conn.execute(
                    """
                    UPDATE finance_screener_snapshots
                    SET asset_type = 'etf'
                    WHERE COALESCE(asset_type, 'stock') != 'etf'
                      AND EXISTS (
                          SELECT 1 FROM finance_exchange_symbols e
                          WHERE (e.eod_ticker = finance_screener_snapshots.symbol
                                 OR e.eod_ticker = finance_screener_snapshots.eod_ticker)
                            AND LOWER(COALESCE(e.type, '')) = 'etf'
                      )
                    """
                )
            _ensure_exchange_fts(conn)
            conn.commit()
        _INITIALIZED_PATHS.add(key)


@contextmanager
def _connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    init_warehouse(db_path)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=30000;")
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


def checkpoint_warehouse(db_path: Path) -> dict[str, Any]:
    """Force un checkpoint WAL complet (TRUNCATE) sur finance_warehouse.db avant arrêt propre."""
    if not db_path.exists():
        return {"checkpointed": True, "exists": False, "busy": 0, "log_frames": 0, "checkpointed_frames": 0}
    with sqlite3.connect(db_path, timeout=30.0) as conn:
        conn.execute("PRAGMA busy_timeout=30000;")
        row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);").fetchone()
        conn.execute("PRAGMA optimize;")
        conn.commit()
    busy, log_frames, ckpt_frames = (int(row[0]), int(row[1]), int(row[2])) if row and len(row) >= 3 else (0, 0, 0)
    return {
        "checkpointed": busy == 0,
        "exists": True,
        "busy": busy,
        "log_frames": log_frames,
        "checkpointed_frames": ckpt_frames,
    }


def _norm_sym(symbol: str) -> str:
    return (symbol or "").strip().upper()


def increment_eodhd_usage(db_path: Path, usage_day: str, endpoint: str, delta: int = 1) -> None:
    """Incrémente atomiquement le compteur quotidien d'appels EODHD dans `finance_warehouse.db`."""
    if not usage_day or not endpoint or delta <= 0:
        return
    now_iso = _utc_iso()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_eodhd_daily_usage (usage_day, endpoint, requests, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(usage_day, endpoint) DO UPDATE SET
                requests = requests + excluded.requests,
                updated_at = excluded.updated_at
            """,
            (usage_day, endpoint, int(delta), now_iso),
        )


def load_eodhd_usage(db_path: Path, usage_day: str) -> dict[str, int]:
    """Charge les compteurs d'appels EODHD du jour UTC depuis `finance_warehouse.db`."""
    if not usage_day:
        return {}
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT endpoint, requests FROM finance_eodhd_daily_usage WHERE usage_day = ?",
            (usage_day,),
        ).fetchall()
    return {str(row["endpoint"]): int(row["requests"]) for row in rows if int(row["requests"]) > 0}


def save_sync_runtime_state(db_path: Path, state: dict[str, Any]) -> None:
    """Persiste l'état courant d'avancement de la synchronisation Finance dans `finance_warehouse.db`."""
    now_iso = _utc_iso()
    payload = json.dumps(state, ensure_ascii=False)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_sync_runtime_state (id, state_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (payload, now_iso),
        )


def load_sync_runtime_state(db_path: Path) -> dict[str, Any] | None:
    """Charge le dernier état persisté de la synchronisation Finance depuis `finance_warehouse.db`."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT state_json FROM finance_sync_runtime_state WHERE id = 1"
        ).fetchone()
    if not row or not row["state_json"]:
        return None
    try:
        parsed = json.loads(row["state_json"])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


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
    """Retourne la date de dernière sauvegarde locale EOD, la profondeur et la source pour un symbole."""
    sym = _norm_sym(symbol)
    empty = {
        "eod_synced_date": None,
        "eod_synced_at": None,
        "eod_synced_bars": 0,
        "bars_count": 0,
        "latest_bar_date": None,
        "latest_bar_source": None,
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
        latest_row = conn.execute(
            """
            SELECT source
            FROM finance_eod_bars
            WHERE symbol = ?
            ORDER BY bar_date DESC
            LIMIT 1
            """,
            (sym,),
        ).fetchone()
    return {
        "eod_synced_date": str(inst["eod_synced_date"]) if (inst and inst["eod_synced_date"]) else None,
        "eod_synced_at": str(inst["eod_synced_at"]) if (inst and inst["eod_synced_at"]) else None,
        "eod_synced_bars": int((inst["eod_synced_bars"] if inst else 0) or 0),
        "bars_count": int((agg["cnt"] if agg else 0) or 0),
        "latest_bar_date": str(agg["max_dt"]) if (agg and agg["max_dt"]) else None,
        "latest_bar_source": str(latest_row["source"]) if (latest_row and latest_row["source"]) else None,
    }


def is_eod_fresh_today(
    sync_info: dict[str, Any] | None,
    *,
    min_bars_needed: int = 1,
    today_iso: str | None = None,
    prefer_source: str | None = None,
) -> bool:
    """Indique si les barres EOD locales ont déjà été sauvegardées aujourd'hui avec la profondeur et la source requises."""
    if not sync_info:
        return False
    bars_count = int(sync_info.get("bars_count") or 0)
    if bars_count <= 0:
        return False
    if prefer_source:
        latest_src = str(sync_info.get("latest_bar_source") or "").strip().lower()
        if latest_src and latest_src != prefer_source.strip().lower():
            return False
    today = today_iso or datetime.date.today().isoformat()
    if str(sync_info.get("eod_synced_date") or "") != today:
        return False
    synced_depth = max(bars_count, int(sync_info.get("eod_synced_bars") or 0))
    return synced_depth >= max(1, int(min_bars_needed or 1))


def get_warehouse_eod_source_breakdown(db_path: Path) -> dict[str, Any]:
    """Recense les titres EODHD vs Yahoo Finance dans l'entrepôt (barres EOD & états financiers)."""
    empty: dict[str, Any] = {
        "eodhd_fundamentals_count": 0,
        "yahoo_only_fundamentals_count": 0,
        "yahoo_only_fundamentals_symbols": [],
        "all_fundamentals_symbols": [],
        "eodhd_bars_symbols_count": 0,
        "yahoo_only_bars_symbols_count": 0,
        "yahoo_only_bars_symbols": [],
        "total_bars_symbols": 0,
    }
    if not db_path.exists():
        return empty
    with _connect(db_path) as conn:
        eod_fund_syms = {
            _norm_sym(str(r["symbol"]))
            for r in conn.execute(
                """
                SELECT DISTINCT symbol FROM finance_raw_snapshots
                WHERE payload_type = 'fundamentals' AND provider = 'eodhd'
                UNION
                SELECT DISTINCT symbol FROM finance_fundamental_facts
                WHERE source = 'eodhd'
                """
            ).fetchall()
            if r["symbol"]
        }
        all_fund_syms = {
            _norm_sym(str(r["symbol"]))
            for r in conn.execute(
                """
                SELECT DISTINCT symbol FROM finance_raw_snapshots
                WHERE payload_type = 'fundamentals'
                UNION
                SELECT DISTINCT symbol FROM finance_fundamental_facts
                UNION
                SELECT DISTINCT symbol FROM finance_screener_snapshots
                WHERE has_fundamentals = 1
                """
            ).fetchall()
            if r["symbol"]
        }
        yahoo_only_fund = sorted(all_fund_syms - eod_fund_syms)

        bar_rows = conn.execute(
            """
            SELECT b.symbol, b.source
            FROM finance_eod_bars b
            INNER JOIN (
                SELECT symbol, MAX(bar_date) AS max_dt
                FROM finance_eod_bars
                GROUP BY symbol
            ) m ON m.symbol = b.symbol AND m.max_dt = b.bar_date
            """
        ).fetchall()
        eod_bar_syms: set[str] = set()
        non_eod_bar_syms: set[str] = set()
        for r in bar_rows:
            sym = _norm_sym(str(r["symbol"] or ""))
            if not sym:
                continue
            src = str(r["source"] or "").strip().lower()
            if src == "eodhd":
                eod_bar_syms.add(sym)
            else:
                non_eod_bar_syms.add(sym)

    return {
        "eodhd_fundamentals_count": len(eod_fund_syms),
        "yahoo_only_fundamentals_count": len(yahoo_only_fund),
        "yahoo_only_fundamentals_symbols": yahoo_only_fund,
        "all_fundamentals_symbols": sorted(all_fund_syms),
        "eodhd_bars_symbols_count": len(eod_bar_syms),
        "yahoo_only_bars_symbols_count": len(non_eod_bar_syms),
        "yahoo_only_bars_symbols": sorted(non_eod_bar_syms),
        "total_bars_symbols": len(eod_bar_syms) + len(non_eod_bar_syms),
    }


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
    *,
    prefer_source: str | None = "eodhd",
) -> tuple[dict[str, dict[str, float | None]], str | None, str | None, str | None]:
    """Charge les séries fondamentales stockées pour un symbole et une périodicité.

    Lorsque `prefer_source` (par défaut `"eodhd"`) est présent pour ce symbole et cette
    périodicité, ses données priment exclusivement afin d'éviter le mélange de dates fiscales
    entre EODHD et d'anciens snapshots Yahoo Finance.

    Retourne `(series, currency, source, updated_at)`.
    """
    sym = _norm_sym(symbol)
    if not sym or not db_path.exists():
        return {}, None, None, None
    with _connect(db_path) as conn:
        rows: list[sqlite3.Row] = []
        if prefer_source:
            rows = conn.execute(
                """
                SELECT period_date, metric_key, value, currency, source, updated_at
                FROM finance_fundamental_facts
                WHERE symbol = ? AND period_type = ? AND source = ?
                ORDER BY period_date ASC
                """,
                (sym, period_type, prefer_source),
            ).fetchall()
        if not rows:
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
    "major_indices_constituents": True,
    "screener_fundamentals": True,
    "screener_fundamentals_daily_cap": 40,
    "screener_fundamentals_interval_days": 7,
    "indx_catalog": True,
    "index_codes": [],
    "watchlists": False,
    "exchanges": [],
    "stock_price_exchanges": [],
    "full_data_exchanges": [],
    "etf_exchanges": [],
    "fundamentals_watchlists": True,
    "fundamentals_indices": True,
    "fundamentals_budget_pct": 10,
    "fundamentals_quota_safety_pct": 15,
    "fundamentals_priority_order": ["watchlists", "indices", "full_exchanges"],
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

    raw_cap = src.get("screener_fundamentals_daily_cap", DEFAULT_SYNC_PREFERENCES["screener_fundamentals_daily_cap"])
    try:
        daily_cap = max(5, min(200, int(raw_cap)))
    except (TypeError, ValueError):
        daily_cap = int(DEFAULT_SYNC_PREFERENCES["screener_fundamentals_daily_cap"])

    raw_interval = src.get(
        "screener_fundamentals_interval_days",
        DEFAULT_SYNC_PREFERENCES["screener_fundamentals_interval_days"],
    )
    try:
        interval_days = max(1, min(90, int(raw_interval)))
    except (TypeError, ValueError):
        interval_days = int(DEFAULT_SYNC_PREFERENCES["screener_fundamentals_interval_days"])

    def _bounded_int(key: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(src.get(key, DEFAULT_SYNC_PREFERENCES[key]))))
        except (TypeError, ValueError):
            return int(DEFAULT_SYNC_PREFERENCES[key])

    default_order = list(DEFAULT_SYNC_PREFERENCES["fundamentals_priority_order"])
    raw_order = src.get("fundamentals_priority_order")
    order = [k for k in raw_order if k in default_order] if isinstance(raw_order, list) else []
    order = list(dict.fromkeys(order)) + [k for k in default_order if k not in order]

    return {
        "enabled": bool(src.get("enabled", DEFAULT_SYNC_PREFERENCES["enabled"])),
        "principal_indices": bool(
            src.get("principal_indices", DEFAULT_SYNC_PREFERENCES["principal_indices"])
        ),
        "major_indices_constituents": bool(
            src.get("major_indices_constituents", DEFAULT_SYNC_PREFERENCES["major_indices_constituents"])
        ),
        "screener_fundamentals": bool(
            src.get("screener_fundamentals", DEFAULT_SYNC_PREFERENCES["screener_fundamentals"])
        ),
        "screener_fundamentals_daily_cap": daily_cap,
        "screener_fundamentals_interval_days": interval_days,
        "indx_catalog": bool(src.get("indx_catalog", DEFAULT_SYNC_PREFERENCES["indx_catalog"])),
        "index_codes": _clean_list(src.get("index_codes")),
        "watchlists": bool(src.get("watchlists", DEFAULT_SYNC_PREFERENCES["watchlists"])),
        "exchanges": _clean_list(src.get("exchanges")),
        "stock_price_exchanges": _clean_list(src.get("stock_price_exchanges")),
        "full_data_exchanges": _clean_list(src.get("full_data_exchanges")),
        "etf_exchanges": _clean_list(src.get("etf_exchanges")),
        "fundamentals_watchlists": bool(
            src.get("fundamentals_watchlists", DEFAULT_SYNC_PREFERENCES["fundamentals_watchlists"])
        ),
        "fundamentals_indices": bool(
            src.get("fundamentals_indices", DEFAULT_SYNC_PREFERENCES["fundamentals_indices"])
        ),
        "fundamentals_budget_pct": _bounded_int("fundamentals_budget_pct", 1, 50),
        "fundamentals_quota_safety_pct": _bounded_int("fundamentals_quota_safety_pct", 5, 50),
        "fundamentals_priority_order": order,
    }


def get_sync_preferences(db_path: Path, pref_key: str = "default") -> dict[str, Any]:
    """Lit les préférences de synchronisation quotidienne enregistrées (indices activés par défaut)."""
    if not db_path.exists():
        return {
            **DEFAULT_SYNC_PREFERENCES,
            "last_run_at": None,
            "last_fundamentals_run_at": None,
            "last_status": None,
            "updated_at": None,
        }
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT config_json, last_run_at, last_fundamentals_run_at, last_status_json, updated_at
            FROM finance_sync_preferences
            WHERE pref_key = ?
            """,
            (pref_key,),
        ).fetchone()
    if not row:
        return {
            **DEFAULT_SYNC_PREFERENCES,
            "last_run_at": None,
            "last_fundamentals_run_at": None,
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
        "last_fundamentals_run_at": row["last_fundamentals_run_at"] or None,
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
    *,
    fundamentals_ran: bool = False,
) -> dict[str, Any]:
    """Mémorise l'horodatage et le compte-rendu de la dernière exécution de synchro quotidienne."""
    now_iso = _utc_iso()
    current = get_sync_preferences(db_path, pref_key=pref_key)
    cfg = _normalize_sync_preferences(current)
    next_fund_iso = now_iso if fundamentals_ran else current.get("last_fundamentals_run_at")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO finance_sync_preferences (
                pref_key, config_json, last_run_at, last_fundamentals_run_at, last_status_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(pref_key) DO UPDATE SET
                last_run_at = excluded.last_run_at,
                last_fundamentals_run_at = COALESCE(excluded.last_fundamentals_run_at, finance_sync_preferences.last_fundamentals_run_at),
                last_status_json = excluded.last_status_json,
                updated_at = excluded.updated_at
            """,
            (
                pref_key,
                json.dumps(cfg, ensure_ascii=False),
                now_iso,
                next_fund_iso,
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


_SCREENER_SNAPSHOT_COLS: tuple[str, ...] = (
    "symbol",
    "eod_ticker",
    "yahoo_symbol",
    "asset_type",
    "name",
    "exchange",
    "country",
    "market_zone",
    "currency",
    "sector",
    "industry",
    "cap_category",
    "indices_csv",
    "market_cap",
    "price",
    "volume",
    "avg_volume_20d",
    "rel_volume_20d",
    "change_1d_pct",
    "change_1w_pct",
    "change_1m_pct",
    "change_3m_pct",
    "change_ytd_pct",
    "change_1y_pct",
    "dist_52w_high_pct",
    "dist_52w_low_pct",
    "pe_ttm",
    "pe_forward",
    "peg_ratio",
    "ev_ebitda",
    "pb_ratio",
    "fcf_yield_pct",
    "dividend_yield_pct",
    "roic_pct",
    "roe_pct",
    "op_margin_pct",
    "net_margin_pct",
    "net_debt_ebitda",
    "debt_to_equity_pct",
    "current_ratio",
    "rev_cagr_3y_pct",
    "eps_cagr_3y_pct",
    "beta",
    "analyst_upside_pct",
    "ih_score",
    "piotroski_f",
    "altman_z",
    "mos_intrinsic_pct",
    "sma20",
    "sma50",
    "sma200",
    "ema20",
    "ema50",
    "dist_sma50_pct",
    "dist_sma200_pct",
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "macd_cross",
    "sma_golden_cross",
    "boll_pct_b",
    "boll_width_pct",
    "adx_14",
    "stoch_k",
    "atr_pct",
    "roc_12",
    "supertrend_dir",
    "has_fundamentals",
    "bars_count",
    "bars_date",
    "fundamentals_updated_at",
    "computed_at",
    "scores_json",
    "sparkline_json",
)

_SCREENER_PRESERVE_IF_NULL_COLS: frozenset[str] = frozenset(
    {
        "eod_ticker",
        "yahoo_symbol",
        "country",
        "currency",
        "sector",
        "industry",
        "cap_category",
        "market_cap",
        "pe_ttm",
        "pe_forward",
        "peg_ratio",
        "ev_ebitda",
        "pb_ratio",
        "fcf_yield_pct",
        "dividend_yield_pct",
        "roic_pct",
        "roe_pct",
        "op_margin_pct",
        "net_margin_pct",
        "net_debt_ebitda",
        "debt_to_equity_pct",
        "current_ratio",
        "rev_cagr_3y_pct",
        "eps_cagr_3y_pct",
        "beta",
        "analyst_upside_pct",
        "ih_score",
        "piotroski_f",
        "altman_z",
        "mos_intrinsic_pct",
        "fundamentals_updated_at",
    }
)


def upsert_screener_snapshots(
    db_path: Path,
    rows: list[dict[str, Any]],
    *,
    preserve_fundamentals_if_missing: bool = True,
    batch_size: int = 40,
) -> int:
    """Insère ou met à jour par micro-lots les lignes matérialisées du Screener dans `finance_warehouse.db`."""
    if not rows:
        return 0
    now_iso = _utc_iso()
    placeholders = ", ".join("?" for _ in _SCREENER_SNAPSHOT_COLS)
    col_list = ", ".join(_SCREENER_SNAPSHOT_COLS)
    update_parts: list[str] = []
    for col in _SCREENER_SNAPSHOT_COLS:
        if col == "symbol":
            continue
        if col == "asset_type":
            update_parts.append(
                "asset_type = CASE WHEN excluded.asset_type = 'etf' "
                "OR finance_screener_snapshots.asset_type = 'etf' THEN 'etf' ELSE 'stock' END"
            )
        elif col in ("name", "exchange", "country", "market_zone", "currency", "sector", "industry", "cap_category", "indices_csv"):
            update_parts.append(f"{col} = COALESCE(NULLIF(excluded.{col}, ''), finance_screener_snapshots.{col})")
        elif col == "has_fundamentals":
            update_parts.append("has_fundamentals = MAX(finance_screener_snapshots.has_fundamentals, excluded.has_fundamentals)")
        elif col == "bars_count":
            update_parts.append("bars_count = MAX(finance_screener_snapshots.bars_count, excluded.bars_count)")
        elif col == "scores_json":
            update_parts.append(
                "scores_json = CASE WHEN excluded.scores_json IS NOT NULL AND excluded.scores_json != '{}' "
                "THEN excluded.scores_json ELSE finance_screener_snapshots.scores_json END"
            )
        elif col == "sparkline_json":
            update_parts.append(
                "sparkline_json = CASE WHEN excluded.sparkline_json IS NOT NULL AND excluded.sparkline_json != '[]' "
                "THEN excluded.sparkline_json ELSE finance_screener_snapshots.sparkline_json END"
            )
        elif col == "computed_at":
            update_parts.append("computed_at = excluded.computed_at")
        elif preserve_fundamentals_if_missing:
            update_parts.append(f"{col} = COALESCE(excluded.{col}, finance_screener_snapshots.{col})")
        else:
            update_parts.append(f"{col} = excluded.{col}")

    sql = (
        f"INSERT INTO finance_screener_snapshots ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT(symbol) DO UPDATE SET {', '.join(update_parts)}"
    )

    from .finance_geography import canonicalize_country, resolve_market_zone

    non_null_text_cols = ("name", "exchange", "country", "market_zone", "currency", "sector", "industry", "cap_category", "indices_csv")
    prepared: list[tuple[Any, ...]] = []
    for row in rows:
        sym = _norm_sym(str(row.get("symbol") or ""))
        if not sym:
            continue
        payload = {**row, "symbol": sym, "computed_at": row.get("computed_at") or now_iso}
        payload["asset_type"] = "etf" if str(payload.get("asset_type") or "").strip().lower() == "etf" else "stock"
        for txt_col in non_null_text_cols:
            if payload.get(txt_col) is None:
                payload[txt_col] = ""
        canon_country = canonicalize_country(
            str(payload.get("country") or ""),
            exchange=str(payload.get("exchange") or ""),
            symbol=str(payload.get("eod_ticker") or sym),
        )
        if canon_country:
            payload["country"] = canon_country
        if not payload.get("market_zone"):
            payload["market_zone"] = resolve_market_zone(
                str(payload.get("country") or ""),
                exchange=str(payload.get("exchange") or ""),
                symbol=str(payload.get("eod_ticker") or sym),
            )
        if isinstance(payload.get("scores_json"), dict):
            payload["scores_json"] = json.dumps(payload["scores_json"], ensure_ascii=False, separators=(",", ":"))
        elif not payload.get("scores_json"):
            payload["scores_json"] = "{}"
        if isinstance(payload.get("sparkline_json"), list):
            payload["sparkline_json"] = json.dumps(payload["sparkline_json"], separators=(",", ":"))
        elif not payload.get("sparkline_json"):
            payload["sparkline_json"] = "[]"
        payload["has_fundamentals"] = 1 if payload.get("has_fundamentals") else 0
        payload["bars_count"] = int(payload.get("bars_count") or 0)
        prepared.append(tuple(payload.get(col) for col in _SCREENER_SNAPSHOT_COLS))

    if not prepared:
        return 0

    # Supprime les lignes « catalogue » (sans cours ni fondamentaux) devenues des doublons d'un titre
    # désormais indexé sous une autre clé canonique (ex. SAP.XETRA -> SAP.DE).
    sym_idx = _SCREENER_SNAPSHOT_COLS.index("symbol")
    eod_idx = _SCREENER_SNAPSHOT_COLS.index("eod_ticker")
    yah_idx = _SCREENER_SNAPSHOT_COLS.index("yahoo_symbol")
    dedup_params: list[tuple[str, str, str]] = []
    for tup in prepared:
        sym = str(tup[sym_idx] or "")
        for alias in {str(tup[eod_idx] or ""), str(tup[yah_idx] or "")}:
            alias_norm = _norm_sym(alias)
            if alias_norm and alias_norm != sym:
                dedup_params.append((sym, alias_norm, alias_norm))

    step = max(1, int(batch_size or 40))
    for i in range(0, len(prepared), step):
        chunk = prepared[i : i + step]
        with _connect(db_path) as conn:
            conn.executemany(sql, chunk)
    if dedup_params:
        with _connect(db_path) as conn:
            conn.executemany(
                """
                DELETE FROM finance_screener_snapshots
                WHERE symbol != ? AND (symbol = ? OR eod_ticker = ?)
                  AND bars_count = 0 AND has_fundamentals = 0 AND price IS NULL
                """,
                dedup_params,
            )
    return len(prepared)


_SCREENER_TECH_COLS: tuple[str, ...] = (
    "symbol",
    "timeframe",
    "price",
    "rel_volume_20d",
    "sma20",
    "sma50",
    "sma200",
    "ema20",
    "ema50",
    "dist_sma50_pct",
    "dist_sma200_pct",
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "macd_cross",
    "sma_golden_cross",
    "boll_pct_b",
    "boll_width_pct",
    "adx_14",
    "stoch_k",
    "atr_pct",
    "roc_12",
    "supertrend_dir",
    "isopressure_raw",
    "isopressure_p5",
    "isopressure_p20",
    "isopressure_p50",
    "isopressure_p100",
    "isopressure_p200",
    "isopressure_20_50_diff",
    "isopressure_20_50_dir",
    "isopressure_20_50_cross",
    "isopressure_5_20_cross",
    "bars_count",
    "bars_date",
    "computed_at",
)


def upsert_screener_technicals(
    db_path: Path,
    rows: list[dict[str, Any]],
    *,
    batch_size: int = 80,
) -> int:
    """Insère ou met à jour par micro-lots les indicateurs techniques multi-unités (`day`/`week`/`month`/`quarter`)."""
    if not rows:
        return 0
    now_iso = _utc_iso()
    col_list = ", ".join(_SCREENER_TECH_COLS)
    placeholders = ", ".join("?" for _ in _SCREENER_TECH_COLS)
    updates = ", ".join(
        f"{c} = excluded.{c}" for c in _SCREENER_TECH_COLS if c not in ("symbol", "timeframe")
    )
    sql = (
        f"INSERT INTO finance_screener_technicals ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT(symbol, timeframe) DO UPDATE SET {updates}"
    )
    prepared: list[tuple[Any, ...]] = []
    for row in rows:
        sym = _norm_sym(str(row.get("symbol") or ""))
        tf = str(row.get("timeframe") or "").strip().lower()
        if not sym or tf not in ("day", "week", "month", "quarter"):
            continue
        payload = {
            **row,
            "symbol": sym,
            "timeframe": tf,
            "bars_count": int(row.get("bars_count") or 0),
            "computed_at": row.get("computed_at") or now_iso,
        }
        prepared.append(tuple(payload.get(col) for col in _SCREENER_TECH_COLS))

    if not prepared:
        return 0
    step = max(1, int(batch_size or 80))
    for i in range(0, len(prepared), step):
        chunk = prepared[i : i + step]
        with _connect(db_path) as conn:
            conn.executemany(sql, chunk)
    return len(prepared)


def get_symbol_indices_map(db_path: Path) -> dict[str, list[str]]:
    """Retourne un dictionnaire `symbole_normalisé -> [codes d'indices triés]` depuis `finance_index_constituents`."""
    if not db_path.exists():
        return {}
    out: dict[str, set[str]] = {}
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT index_code, symbol, eod_ticker, yahoo_symbol FROM finance_index_constituents"
        ).fetchall()
    for r in rows:
        idx_code = _norm_sym(str(r["index_code"] or ""))
        if not idx_code:
            continue
        for key in (r["symbol"], r["eod_ticker"], r["yahoo_symbol"]):
            norm = _norm_sym(str(key or ""))
            if norm:
                out.setdefault(norm, set()).add(idx_code)
    return {k: sorted(v) for k, v in out.items()}


def list_warehouse_screener_symbols(db_path: Path) -> list[str]:
    """Liste tous les symboles canoniques possédant au moins des barres EOD ou des fondamentaux en entrepôt."""
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT symbol FROM (
                SELECT symbol FROM finance_eod_bars
                UNION
                SELECT symbol FROM finance_fundamental_facts
                UNION
                SELECT symbol FROM finance_raw_snapshots WHERE payload_type = 'fundamentals'
            )
            ORDER BY symbol ASC
            """
        ).fetchall()
    return [_norm_sym(str(r["symbol"])) for r in rows if r["symbol"]]


DEFAULT_ETF_EXCHANGE_CODES: tuple[str, ...] = (
    "PA",
    "XETRA",
    "US",
    "LSE",
    "SW",
    "AS",
    "MI",
    "BR",
    "MC",
    "TO",
)
_EXCLUDED_ETF_EXCHANGES: frozenset[str] = frozenset({"ALL", "EUFUND", "CC", "INDX"})


def resolve_symbol_asset_type(
    db_path: Path,
    symbol: str,
    eod_ticker: str = "",
    raw_type: str = "",
) -> str:
    """Résout le type d'actif Screener (`'etf'` ou `'stock'`) depuis le type brut ou l'entrepôt local."""
    raw_l = str(raw_type or "").strip().lower()
    if raw_l == "etf":
        return "etf"
    keys = [k for k in {_norm_sym(symbol), _norm_sym(eod_ticker)} if k]
    if not keys or not db_path.exists():
        return "stock"
    marks = ", ".join("?" for _ in keys)
    with _connect(db_path) as conn:
        exch_hit = conn.execute(
            f"""
            SELECT 1 FROM finance_exchange_symbols
            WHERE LOWER(COALESCE(type, '')) = 'etf'
              AND (UPPER(eod_ticker) IN ({marks}) OR UPPER(symbol) IN ({marks}))
            LIMIT 1
            """,
            [*keys, *keys],
        ).fetchone()
        if exch_hit:
            return "etf"
        scr_hit = conn.execute(
            f"""
            SELECT 1 FROM finance_screener_snapshots
            WHERE asset_type = 'etf'
              AND (UPPER(symbol) IN ({marks}) OR UPPER(COALESCE(eod_ticker, '')) IN ({marks}))
            LIMIT 1
            """,
            [*keys, *keys],
        ).fetchone()
        if scr_hit:
            return "etf"
    return "stock"


def get_etf_exchange_catalog_counts(db_path: Path) -> list[dict[str, Any]]:
    """Retourne, par bourse d'origine, le nombre d'ETFs disponibles, référencés au Screener et chargés."""
    from .finance_geography import canonicalize_country, country_flag, exchange_display_label

    catalog_stats: dict[str, dict[str, Any]] = {}
    screener_stats: dict[str, dict[str, int]] = {}
    extra_codes: set[str] = set()

    if db_path.exists():
        with _connect(db_path) as conn:
            cat_rows = conn.execute(
                """
                SELECT UPPER(exchange_code) AS exch,
                       COUNT(*) AS total_symbols,
                       SUM(CASE WHEN LOWER(COALESCE(type, '')) = 'etf' THEN 1 ELSE 0 END) AS etf_count,
                       MAX(fetched_at) AS max_ts
                FROM finance_exchange_symbols
                WHERE exchange_code != ''
                GROUP BY UPPER(exchange_code)
                """
            ).fetchall()
            for r in cat_rows:
                code = _norm_sym(str(r["exch"] or ""))
                if not code or code in _EXCLUDED_ETF_EXCHANGES:
                    continue
                extra_codes.add(code)
                catalog_stats[code] = {
                    "total_symbols": int(r["total_symbols"] or 0),
                    "etf_catalog_count": int(r["etf_count"] or 0),
                    "fetched_at": float(r["max_ts"]) if r["max_ts"] is not None else None,
                }

            scr_rows = conn.execute(
                """
                SELECT UPPER(exchange) AS exch,
                       COUNT(*) AS in_screener,
                       SUM(CASE WHEN price IS NOT NULL OR bars_count > 0 THEN 1 ELSE 0 END) AS with_data
                FROM finance_screener_snapshots
                WHERE asset_type = 'etf' AND exchange != ''
                GROUP BY UPPER(exchange)
                """
            ).fetchall()
            for r in scr_rows:
                code = _norm_sym(str(r["exch"] or ""))
                if not code or code in _EXCLUDED_ETF_EXCHANGES:
                    continue
                extra_codes.add(code)
                screener_stats[code] = {
                    "etf_in_screener_count": int(r["in_screener"] or 0),
                    "etf_with_data_count": int(r["with_data"] or 0),
                }

    default_order = {c: i for i, c in enumerate(DEFAULT_ETF_EXCHANGE_CODES)}
    ordered_codes = sorted(
        set(DEFAULT_ETF_EXCHANGE_CODES) | extra_codes,
        key=lambda c: (
            0 if c in default_order else 1,
            default_order.get(c, 999),
            -(catalog_stats.get(c, {}).get("etf_catalog_count", 0)),
            c,
        ),
    )

    out: list[dict[str, Any]] = []
    for code in ordered_codes:
        c_info = catalog_stats.get(code) or {}
        s_info = screener_stats.get(code) or {}
        country = canonicalize_country("", exchange=code)
        total_syms = int(c_info.get("total_symbols") or 0)
        etf_cat = int(c_info.get("etf_catalog_count") or 0)
        in_scr = int(s_info.get("etf_in_screener_count") or 0)
        with_data = int(s_info.get("etf_with_data_count") or 0)
        # Inclure les bourses par défaut, celles qui contiennent des ETFs, ou celles déjà présentes au Screener
        if code not in default_order and etf_cat == 0 and in_scr == 0:
            continue
        out.append(
            {
                "code": code,
                "label": exchange_display_label(code),
                "country": country,
                "flag": country_flag(country) if country else "🌐",
                "catalog_synced": total_syms > 0,
                "total_symbols": total_syms,
                "etf_catalog_count": etf_cat,
                "etf_in_screener_count": in_scr,
                "etf_with_data_count": with_data,
                "synced_at": _utc_iso(c_info["fetched_at"]) if c_info.get("fetched_at") is not None else None,
            }
        )
    return out


def seed_etfs_from_exchange_catalog(db_path: Path, exchange_codes: list[str]) -> dict[str, int]:
    """Référence indépendamment dans le Screener les ETFs des bourses demandées (0 appel réseau)."""
    clean_codes = [
        c
        for c in dict.fromkeys(_norm_sym(x) for x in exchange_codes)
        if c and c not in _EXCLUDED_ETF_EXCHANGES
    ]
    if not clean_codes or not db_path.exists():
        return {}
    from .finance_geography import canonicalize_country, resolve_market_zone

    now_iso = _utc_iso()
    added_by_exchange: dict[str, int] = {}
    with _connect(db_path) as conn:
        for code in clean_codes:
            upd_cur = conn.execute(
                """
                UPDATE finance_screener_snapshots
                SET asset_type = 'etf',
                    exchange = COALESCE(NULLIF(exchange, ''), ?)
                WHERE COALESCE(asset_type, 'stock') != 'etf'
                  AND EXISTS (
                      SELECT 1 FROM finance_exchange_symbols e
                      WHERE e.exchange_code = ?
                        AND LOWER(COALESCE(e.type, '')) = 'etf'
                        AND (e.eod_ticker = finance_screener_snapshots.symbol
                             OR e.eod_ticker = finance_screener_snapshots.eod_ticker)
                  )
                """,
                (code, code),
            )
            rows = conn.execute(
                """
                SELECT e.exchange_code, e.eod_ticker, e.name, e.country, e.currency
                FROM finance_exchange_symbols e
                WHERE e.exchange_code = ?
                  AND LOWER(COALESCE(e.type, '')) = 'etf'
                  AND NOT EXISTS (
                      SELECT 1 FROM finance_screener_snapshots s
                      WHERE s.symbol = e.eod_ticker OR s.eod_ticker = e.eod_ticker
                  )
                """,
                (code,),
            ).fetchall()
            payload: list[tuple[Any, ...]] = []
            for r in rows:
                eod = _norm_sym(str(r["eod_ticker"] or ""))
                if not eod:
                    continue
                exch = str(r["exchange_code"] or code).strip().upper()
                country = canonicalize_country(str(r["country"] or ""), exchange=exch, symbol=eod)
                zone = resolve_market_zone(country, exchange=exch, symbol=eod)
                payload.append(
                    (
                        eod,
                        eod,
                        "etf",
                        str(r["name"] or eod).strip() or eod,
                        exch,
                        country,
                        zone,
                        str(r["currency"] or "").strip().upper(),
                        now_iso,
                    )
                )
            if payload:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO finance_screener_snapshots
                        (symbol, eod_ticker, asset_type, name, exchange, country, market_zone, currency, computed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
            added_by_exchange[code] = len(payload) + int(upd_cur.rowcount or 0)
    return added_by_exchange


def seed_screener_from_exchange_catalogs(
    db_path: Path,
    exchange_codes: list[str] | None = None,
) -> int:
    """Référence dans le Screener toutes les actions ordinaires des catalogues de bourses synchronisés.

    Insère des lignes « catalogue » légères (nom, place, pays, zone, devise) sans cours ni
    fondamentaux : aucun appel réseau. Les données sont complétées plus tard, titre par titre,
    lors d'une consultation ou d'un enrichissement. Les lignes déjà présentes ne sont jamais modifiées.
    """
    if not db_path.exists():
        return 0
    from .finance_geography import canonicalize_country, resolve_market_zone

    filter_sql = ""
    params: list[Any] = []
    if exchange_codes is not None:
        clean_codes = [
            c
            for c in dict.fromkeys(_norm_sym(x) for x in exchange_codes)
            if c and c not in _EXCLUDED_ETF_EXCHANGES
        ]
        if not clean_codes:
            return 0
        marks = ", ".join("?" for _ in clean_codes)
        filter_sql = f"AND UPPER(e.exchange_code) IN ({marks})"
        params.extend(clean_codes)

    now_iso = _utc_iso()
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT e.exchange_code, e.eod_ticker, e.name, e.country, e.currency
            FROM finance_exchange_symbols e
            WHERE LOWER(COALESCE(e.type, '')) = 'common stock'
              AND e.exchange_code NOT IN ('EUFUND', 'CC')
              {filter_sql}
              AND NOT EXISTS (
                  SELECT 1 FROM finance_screener_snapshots s
                  WHERE s.symbol = e.eod_ticker OR s.eod_ticker = e.eod_ticker
              )
            """,
            params,
        ).fetchall()
        payload: list[tuple[Any, ...]] = []
        for r in rows:
            eod = _norm_sym(str(r["eod_ticker"] or ""))
            if not eod:
                continue
            exch = str(r["exchange_code"] or "").strip().upper()
            country = canonicalize_country(str(r["country"] or ""), exchange=exch, symbol=eod)
            zone = resolve_market_zone(country, exchange=exch, symbol=eod)
            payload.append(
                (
                    eod,
                    eod,
                    str(r["name"] or eod).strip() or eod,
                    exch,
                    country,
                    zone,
                    str(r["currency"] or "").strip().upper(),
                    now_iso,
                )
            )
        if payload:
            conn.executemany(
                """
                INSERT OR IGNORE INTO finance_screener_snapshots
                    (symbol, eod_ticker, name, exchange, country, market_zone, currency, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
    return len(payload)


def backfill_screener_geography(db_path: Path) -> int:
    """Normalise `country` et remplit `market_zone` sur les lignes existantes de `finance_screener_snapshots`."""
    if not db_path.exists():
        return 0
    from .finance_geography import canonicalize_country, resolve_market_zone

    updates: list[tuple[str, str, str]] = []
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT symbol, eod_ticker, exchange, country, market_zone FROM finance_screener_snapshots"
        ).fetchall()
        for r in rows:
            sym = str(r["symbol"] or "")
            raw_country = str(r["country"] or "")
            raw_zone = str(r["market_zone"] or "")
            exch = str(r["exchange"] or "")
            eod = str(r["eod_ticker"] or sym)
            canon_country = canonicalize_country(raw_country, exchange=exch, symbol=eod)
            zone = resolve_market_zone(canon_country, exchange=exch, symbol=eod)
            if canon_country != raw_country or zone != raw_zone:
                updates.append((canon_country, zone, sym))
        if updates:
            conn.executemany(
                "UPDATE finance_screener_snapshots SET country = ?, market_zone = ? WHERE symbol = ?",
                updates,
            )
    return len(updates)


def get_screener_coverage(db_path: Path, *, asset_type: str = "") -> dict[str, Any]:
    """Retourne la couverture actuelle et les facettes (indices, zones, pays, bourses, secteurs, devises) du Screener."""
    from .finance_geography import (
        EUROZONE_COUNTRIES,
        MARKET_ZONES,
        country_flag,
        exchange_display_label,
        format_market_zone_item,
    )
    from .finance_indices import INDEX_DEFINITIONS

    clean_asset = str(asset_type or "").strip().lower()
    if clean_asset not in ("stock", "etf"):
        clean_asset = ""
    asset_sql = (
        "asset_type = 'etf'"
        if clean_asset == "etf"
        else ("COALESCE(asset_type, 'stock') != 'etf'" if clean_asset == "stock" else "1=1")
    )
    etf_exchanges = get_etf_exchange_catalog_counts(db_path)

    empty = {
        "total_snapshots": 0,
        "with_technicals": 0,
        "with_fundamentals": 0,
        "stock_count": 0,
        "etf_count": 0,
        "warehouse_symbols_count": 0,
        "sectors": [],
        "exchanges": [],
        "exchange_items": [],
        "etf_exchanges": etf_exchanges,
        "currencies": [],
        "countries": [],
        "market_zones": [],
        "indices": [],
        "cap_categories": [],
        "last_computed_at": None,
    }
    if not db_path.exists():
        return empty
    with _connect(db_path) as conn:
        agg = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN bars_count >= 20 THEN 1 ELSE 0 END) AS with_tech,
                SUM(CASE WHEN has_fundamentals = 1 THEN 1 ELSE 0 END) AS with_fund,
                SUM(CASE WHEN COALESCE(asset_type, 'stock') != 'etf' THEN 1 ELSE 0 END) AS stock_cnt,
                SUM(CASE WHEN asset_type = 'etf' THEN 1 ELSE 0 END) AS etf_cnt,
                MAX(computed_at) AS last_comp
            FROM finance_screener_snapshots
            """
        ).fetchone()
        wh_cnt = conn.execute(
            "SELECT COUNT(DISTINCT symbol) AS cnt FROM finance_eod_bars"
        ).fetchone()
        sectors = [
            str(r["sector"])
            for r in conn.execute(
                f"SELECT DISTINCT sector FROM finance_screener_snapshots WHERE sector != '' AND {asset_sql} ORDER BY sector ASC"
            ).fetchall()
        ]
        exch_rows = conn.execute(
            f"""
            SELECT exchange, COUNT(*) AS cnt
            FROM finance_screener_snapshots
            WHERE exchange != '' AND {asset_sql}
            GROUP BY exchange
            ORDER BY cnt DESC, exchange ASC
            """
        ).fetchall()
        exchanges = sorted(str(r["exchange"]) for r in exch_rows)
        exchange_items = [
            {
                "code": str(r["exchange"]),
                "label": exchange_display_label(str(r["exchange"])),
                "count": int(r["cnt"] or 0),
            }
            for r in exch_rows
        ]
        currencies = [
            str(r["currency"])
            for r in conn.execute(
                f"SELECT DISTINCT currency FROM finance_screener_snapshots WHERE currency != '' AND {asset_sql} ORDER BY currency ASC"
            ).fetchall()
        ]
        country_rows = conn.execute(
            f"""
            SELECT country, COUNT(*) AS cnt
            FROM finance_screener_snapshots
            WHERE country != '' AND {asset_sql}
            GROUP BY country
            ORDER BY cnt DESC, country ASC
            """
        ).fetchall()
        countries = [
            {
                "code": str(r["country"]),
                "label": f"{country_flag(str(r['country']))} {r['country']}",
                "flag": country_flag(str(r["country"])),
                "count": int(r["cnt"] or 0),
            }
            for r in country_rows
        ]
        zone_rows = conn.execute(
            f"""
            SELECT market_zone, COUNT(*) AS cnt
            FROM finance_screener_snapshots
            WHERE market_zone != '' AND {asset_sql}
            GROUP BY market_zone
            """
        ).fetchall()
        zone_counts: dict[str, int] = {str(r["market_zone"]): int(r["cnt"] or 0) for r in zone_rows}
        eurozone_count = sum(
            int(r["cnt"] or 0)
            for r in country_rows
            if str(r["country"]) in EUROZONE_COUNTRIES
        )
        if eurozone_count > 0:
            zone_counts["eurozone"] = eurozone_count
        market_zones = [
            format_market_zone_item(z["code"], zone_counts[z["code"]])
            for z in MARKET_ZONES
            if zone_counts.get(z["code"], 0) > 0
        ]

        cap_rows = conn.execute(
            f"""
            SELECT cap_category, COUNT(*) AS cnt
            FROM finance_screener_snapshots
            WHERE cap_category != '' AND {asset_sql}
            GROUP BY cap_category
            ORDER BY cnt DESC, cap_category ASC
            """
        ).fetchall()
        cap_categories = [
            {"code": str(r["cap_category"]), "label": str(r["cap_category"]), "count": int(r["cnt"] or 0)}
            for r in cap_rows
        ]

        idx_counts: dict[str, int] = {}
        for r in conn.execute(
            f"SELECT indices_csv FROM finance_screener_snapshots WHERE indices_csv != '' AND {asset_sql}"
        ).fetchall():
            raw_csv = str(r["indices_csv"] or "")
            for part in raw_csv.split(","):
                code = part.strip().upper()
                if code:
                    idx_counts[code] = idx_counts.get(code, 0) + 1

    idx_defs = {str(d["code"]).upper(): d for d in INDEX_DEFINITIONS}
    def_order = {str(d["code"]).upper(): i for i, d in enumerate(INDEX_DEFINITIONS)}
    indices_facets = []
    for code, cnt in sorted(idx_counts.items(), key=lambda kv: (def_order.get(kv[0], 9999), -kv[1], kv[0])):
        d = idx_defs.get(code) or {}
        indices_facets.append(
            {
                "code": code,
                "name": str(d.get("name") or code),
                "flag": str(d.get("flag") or "📊"),
                "region": str(d.get("region") or ""),
                "tier": str(d.get("tier") or "custom"),
                "count": cnt,
            }
        )

    return {
        "total_snapshots": int((agg["total"] if agg else 0) or 0),
        "with_technicals": int((agg["with_tech"] if agg else 0) or 0),
        "with_fundamentals": int((agg["with_fund"] if agg else 0) or 0),
        "stock_count": int((agg["stock_cnt"] if agg else 0) or 0),
        "etf_count": int((agg["etf_cnt"] if agg else 0) or 0),
        "warehouse_symbols_count": int((wh_cnt["cnt"] if wh_cnt else 0) or 0),
        "sectors": sectors,
        "exchanges": exchanges,
        "exchange_items": exchange_items,
        "etf_exchanges": etf_exchanges,
        "currencies": currencies,
        "countries": countries,
        "market_zones": market_zones,
        "indices": indices_facets,
        "cap_categories": cap_categories,
        "last_computed_at": str(agg["last_comp"]) if (agg and agg["last_comp"]) else None,
    }
