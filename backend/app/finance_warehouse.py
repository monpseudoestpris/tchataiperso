"""Entrepôt local haute densité (SQLite WAL + snapshots zlib) pour les données boursières.

Isolé dans `Settings.resolved_finance_data_dir` (volume Docker dédié `finance_data`)
afin de stocker sans limite de profondeur les barres EOD, les états financiers
historiques normalisés et les payloads bruts compressés EODHD / Yahoo Finance.
"""

from __future__ import annotations

import datetime
import json
import logging
import sqlite3
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import Settings

_logger = logging.getLogger("uvicorn.error")

_WAREHOUSE_FILENAME = "finance_warehouse.db"
_INITIALIZED_PATHS: set[str] = set()

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


def upsert_eod_bars(db_path: Path, symbol: str, bars: list[dict[str, Any]], source: str) -> int:
    """Insère ou met à jour une liste de barres OHLCV (dates journalières YYYY-MM-DD)."""
    sym = _norm_sym(symbol)
    if not sym or not bars:
        return 0
    now_iso = _utc_iso()
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
