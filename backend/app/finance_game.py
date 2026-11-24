"""Moteur local du jeu « Trading Replay » (simulateur boursier sur historique réel).

Fonctionne à 100 % sur `finance_warehouse.db` sans aucun appel réseau ni consommation
de crédits EODHD. Garantit l'isolation par `user_id` et l'étanchéité du Mode Aveugle
côté serveur jusqu'à la clôture de chaque manche.
"""

from __future__ import annotations

import calendar
import datetime
import json
import random
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .finance_warehouse import (
    _connect,
    _norm_sym,
    _utc_iso,
    get_instrument_meta,
    get_stored_eod_bars,
    resolve_canonical_symbol,
)

DEFAULT_STARTING_CAPITAL = 10000.0

VALID_TIMEFRAMES = ("day", "week", "month")
VALID_HORIZONS = ("1w", "1m", "3m", "6m", "1y", "2y", "3y", "5y")
VALID_UNIVERSES = ("all", "index", "watchlist", "symbol")

HORIZON_BARS: dict[str, dict[str, int]] = {
    "day": {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252},
    "week": {"1m": 4, "3m": 13, "6m": 26, "1y": 52, "2y": 104, "3y": 156, "5y": 260},
    "month": {"6m": 6, "1y": 12, "2y": 24, "3y": 36, "5y": 60},
}

MIN_HISTORY_BARS: dict[str, int] = {"day": 120, "week": 45, "month": 20}
TARGET_HISTORY_BARS: dict[str, int] = {"day": 260, "week": 160, "month": 72}
_RAW_DAYS_FACTOR: dict[str, int] = {"day": 1, "week": 5, "month": 21}


def _bucket_key(date_str: str, timeframe: str) -> str:
    day_part = date_str[:10]
    if timeframe == "month":
        return day_part[:7]
    if timeframe == "week":
        parts = day_part.split("-")
        if len(parts) == 3:
            try:
                dt = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                monday = dt - datetime.timedelta(days=dt.weekday())
                return monday.isoformat()
            except ValueError:
                return day_part
    return day_part


def aggregate_eod_bars(bars: list[dict[str, Any]], timeframe: str) -> list[dict[str, Any]]:
    """Agrège une série EOD journalière en bougies `day`, `week` ou `month`."""
    if timeframe not in VALID_TIMEFRAMES:
        raise ValueError(f"Unité temporelle invalide : {timeframe}")

    clean_bars: list[dict[str, Any]] = []
    for raw in bars:
        date_str = str(raw.get("date") or "")[:10]
        close = raw.get("close")
        if not date_str or close is None or float(close) <= 0:
            continue
        c_val = float(close)
        o_val = float(raw["open"]) if raw.get("open") is not None and float(raw["open"]) > 0 else c_val
        h_val = float(raw["high"]) if raw.get("high") is not None and float(raw["high"]) > 0 else max(o_val, c_val)
        l_val = float(raw["low"]) if raw.get("low") is not None and float(raw["low"]) > 0 else min(o_val, c_val)
        v_val = float(raw["volume"]) if raw.get("volume") is not None else 0.0
        clean_bars.append(
            {
                "date": date_str,
                "open": round(o_val, 6),
                "high": round(max(h_val, o_val, c_val), 6),
                "low": round(min(l_val, o_val, c_val), 6),
                "close": round(c_val, 6),
                "volume": max(0.0, v_val),
            }
        )

    clean_bars.sort(key=lambda b: b["date"])
    if timeframe == "day" or not clean_bars:
        return clean_bars

    out: list[dict[str, Any]] = []
    current_key: str | None = None
    acc: dict[str, Any] | None = None

    for bar in clean_bars:
        key = _bucket_key(bar["date"], timeframe)
        if key != current_key or acc is None:
            if acc is not None:
                out.append(acc)
            current_key = key
            acc = dict(bar)
            continue
        acc["date"] = bar["date"]
        acc["high"] = max(acc["high"], bar["high"])
        acc["low"] = min(acc["low"], bar["low"])
        acc["close"] = bar["close"]
        acc["volume"] = acc["volume"] + bar["volume"]

    if acc is not None:
        out.append(acc)
    return out


def build_synthetic_dates(count: int, timeframe: str) -> list[str]:
    """Génère `count` dates synthétiques monotones valides pour le Mode Aveugle."""
    if count <= 0:
        return []
    dates: list[str] = []
    if timeframe == "day":
        cur = datetime.date(2000, 1, 3)
        while len(dates) < count:
            if cur.weekday() < 5:
                dates.append(cur.isoformat())
            cur += datetime.timedelta(days=1)
        return dates
    if timeframe == "week":
        cur = datetime.date(2000, 1, 7)
        for _ in range(count):
            dates.append(cur.isoformat())
            cur += datetime.timedelta(days=7)
        return dates

    year, month = 2000, 1
    for _ in range(count):
        last_day = calendar.monthrange(year, month)[1]
        dates.append(datetime.date(year, month, min(28, last_day)).isoformat())
        month += 1
        if month > 12:
            month = 1
            year += 1
    return dates


def _ensure_profile_row(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM finance_game_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if row is not None:
        return row
    now_iso = _utc_iso()
    conn.execute(
        """
        INSERT INTO finance_game_profiles (
            user_id, starting_capital, equity, rounds_played, trades_taken,
            wins, losses, draws, current_streak, best_streak,
            total_pnl, gross_profit, gross_loss, updated_at
        ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0.0, ?)
        """,
        (user_id, DEFAULT_STARTING_CAPITAL, DEFAULT_STARTING_CAPITAL, now_iso),
    )
    created = conn.execute(
        "SELECT * FROM finance_game_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    assert created is not None
    return created


def _serialize_profile(row: sqlite3.Row) -> dict[str, Any]:
    starting = float(row["starting_capital"])
    equity = float(row["equity"])
    trades_taken = int(row["trades_taken"])
    wins = int(row["wins"])
    losses = int(row["losses"])
    draws = int(row["draws"])
    gross_profit = float(row["gross_profit"])
    gross_loss = float(row["gross_loss"])
    total_pnl = float(row["total_pnl"])
    winrate_pct = round((wins / trades_taken) * 100.0, 1) if trades_taken > 0 else None
    profit_factor = (
        round(gross_profit / gross_loss, 2)
        if gross_loss > 0
        else (round(gross_profit, 2) if gross_profit > 0 else None)
    )
    total_return_pct = round(((equity - starting) / starting) * 100.0, 2) if starting > 0 else 0.0
    return {
        "starting_capital": round(starting, 2),
        "equity": round(equity, 2),
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": total_return_pct,
        "rounds_played": int(row["rounds_played"]),
        "trades_taken": trades_taken,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "winrate_pct": winrate_pct,
        "current_streak": int(row["current_streak"]),
        "best_streak": int(row["best_streak"]),
        "profit_factor": profit_factor,
        "updated_at": str(row["updated_at"]),
    }


def _min_raw_bars_needed(timeframe: str, horizon_code: str) -> int:
    min_hist = MIN_HISTORY_BARS[timeframe]
    horizon_bars = HORIZON_BARS[timeframe][horizon_code]
    return (min_hist + horizon_bars) * _RAW_DAYS_FACTOR[timeframe]


def list_eligible_symbols(
    db_path: Path,
    user_id: str,
    universe_type: str,
    universe_value: str,
    min_raw_bars: int,
) -> list[str]:
    """Retourne les tickers de l'univers demandé disposant d'au moins `min_raw_bars` barres EOD."""
    if not db_path.exists():
        return []
    u_type = (universe_type or "all").strip().lower()
    u_val = (universe_value or "").strip()

    if u_type == "symbol":
        if not u_val:
            raise ValueError("Veuillez saisir un ticker ou un nom d'action pour le mode « Action précise ».")
        canonical = resolve_canonical_symbol(db_path, u_val)
        with _connect(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM finance_eod_bars WHERE symbol = ?",
                (canonical,),
            ).fetchone()
            cnt = int(row["cnt"]) if row else 0
            if cnt >= min_raw_bars:
                return [canonical]
            like_q = f"%{u_val}%"
            alt = conn.execute(
                """
                SELECT b.symbol, COUNT(*) AS cnt
                FROM finance_eod_bars b
                LEFT JOIN finance_instruments i ON i.symbol = b.symbol
                WHERE UPPER(b.symbol) = UPPER(?)
                   OR LOWER(COALESCE(i.short_name, '')) LIKE LOWER(?)
                   OR LOWER(COALESCE(i.long_name, '')) LIKE LOWER(?)
                GROUP BY b.symbol
                HAVING COUNT(*) >= ?
                ORDER BY cnt DESC
                LIMIT 1
                """,
                (u_val, like_q, like_q, min_raw_bars),
            ).fetchone()
            return [str(alt["symbol"])] if alt else []

    with _connect(db_path) as conn:
        if u_type == "index":
            if not u_val:
                raise ValueError("Veuillez sélectionner un indice boursier.")
            rows = conn.execute(
                """
                SELECT b.symbol
                FROM finance_eod_bars b
                INNER JOIN finance_index_constituents c
                    ON (c.symbol = b.symbol OR c.eod_ticker = b.symbol)
                WHERE UPPER(c.index_code) = UPPER(?)
                GROUP BY b.symbol
                HAVING COUNT(*) >= ?
                """,
                (u_val, min_raw_bars),
            ).fetchall()
            return [str(r["symbol"]) for r in rows]

        if u_type == "watchlist":
            if not u_val:
                raise ValueError("Veuillez sélectionner une watchlist.")
            rows = conn.execute(
                """
                SELECT b.symbol
                FROM finance_eod_bars b
                INNER JOIN finance_user_watchlist_items w
                    ON (w.symbol = b.symbol OR w.eod_ticker = b.symbol)
                WHERE w.user_id = ? AND w.list_id = ?
                GROUP BY b.symbol
                HAVING COUNT(*) >= ?
                """,
                (user_id, u_val, min_raw_bars),
            ).fetchall()
            return [str(r["symbol"]) for r in rows]

        rows = conn.execute(
            """
            SELECT symbol
            FROM finance_eod_bars
            GROUP BY symbol
            HAVING COUNT(*) >= ?
            """,
            (min_raw_bars,),
        ).fetchall()
        return [str(r["symbol"]) for r in rows]


def _resolve_symbol_metadata(conn: sqlite3.Connection, db_path: Path, symbol: str) -> dict[str, str]:
    meta = get_instrument_meta(db_path, symbol) or {}
    company_name = str(meta.get("long_name") or meta.get("short_name") or "").strip()
    exchange = str(meta.get("exchange") or "").strip()
    sector = str(meta.get("sector") or "").strip()
    currency = str(meta.get("currency") or "").strip()

    if not company_name or not sector or not currency or not exchange:
        snap = conn.execute(
            """
            SELECT name, exchange, sector, currency
            FROM finance_screener_snapshots
            WHERE symbol = ? OR eod_ticker = ?
            LIMIT 1
            """,
            (symbol, symbol),
        ).fetchone()
        if snap:
            company_name = company_name or str(snap["name"] or "").strip()
            exchange = exchange or str(snap["exchange"] or "").strip()
            sector = sector or str(snap["sector"] or "").strip()
            currency = currency or str(snap["currency"] or "").strip()

    return {
        "company_name": company_name or symbol,
        "exchange": exchange,
        "sector": sector,
        "currency": currency or "USD",
    }


def evaluate_intrabar_exit(
    side: str,
    bar: dict[str, Any],
    stop_loss: float | None,
    take_profit: float | None,
) -> tuple[float, str] | None:
    """Évalue si un Stop-Loss ou Take-Profit se déclenche sur `bar` (gaps inclus, SL prioritaire)."""
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    sl = float(stop_loss) if stop_loss is not None else None
    tp = float(take_profit) if take_profit is not None else None

    if side == "long":
        if sl is not None and o <= sl:
            return (o, "stop_loss")
        if tp is not None and o >= tp:
            return (o, "take_profit")
        if sl is not None and l <= sl:
            return (sl, "stop_loss")
        if tp is not None and h >= tp:
            return (tp, "take_profit")
        return None

    if side == "short":
        if sl is not None and o >= sl:
            return (o, "stop_loss")
        if tp is not None and o <= tp:
            return (o, "take_profit")
        if sl is not None and h >= sl:
            return (sl, "stop_loss")
        if tp is not None and l <= tp:
            return (tp, "take_profit")
        return None

    return None


def _compute_return_and_pnl(
    side: str,
    entry_price: float,
    exit_price: float,
    stake_amount: float,
) -> tuple[float, float]:
    direction = 1.0 if side == "long" else -1.0
    raw_pct = direction * ((exit_price - entry_price) / entry_price) * 100.0
    if side == "long":
        raw_pct = max(-100.0, raw_pct)
    return_pct = round(raw_pct, 2)
    pnl_amount = round(stake_amount * (raw_pct / 100.0), 2)
    return return_pct, pnl_amount


def _settle_trade(
    conn: sqlite3.Connection,
    user_id: str,
    round_row: sqlite3.Row,
    *,
    exit_step: int,
    exit_date: str,
    exit_price: float,
    exit_reason: str,
) -> tuple[float, float]:
    side = str(round_row["position_side"])
    entry_price = float(round_row["entry_price"])
    stake_amount = float(round_row["stake_amount"])
    return_pct, pnl_amount = _compute_return_and_pnl(side, entry_price, exit_price, stake_amount)
    now_iso = _utc_iso()

    conn.execute(
        """
        UPDATE finance_game_rounds
        SET position_status = 'closed',
            exit_step = ?,
            exit_date = ?,
            exit_price = ?,
            exit_reason = ?,
            return_pct = ?,
            pnl_amount = ?
        WHERE id = ? AND user_id = ?
        """,
        (exit_step, exit_date, round(exit_price, 6), exit_reason, return_pct, pnl_amount, round_row["id"], user_id),
    )

    profile = _ensure_profile_row(conn, user_id)
    new_equity = round(max(0.0, float(profile["equity"]) + pnl_amount), 2)
    trades_taken = int(profile["trades_taken"]) + 1
    wins = int(profile["wins"])
    losses = int(profile["losses"])
    draws = int(profile["draws"])
    current_streak = int(profile["current_streak"])
    best_streak = int(profile["best_streak"])
    gross_profit = float(profile["gross_profit"])
    gross_loss = float(profile["gross_loss"])

    if pnl_amount > 0.01:
        wins += 1
        current_streak += 1
        best_streak = max(best_streak, current_streak)
        gross_profit += pnl_amount
    elif pnl_amount < -0.01:
        losses += 1
        current_streak = 0
        gross_loss += abs(pnl_amount)
    else:
        draws += 1

    total_pnl = round(float(profile["total_pnl"]) + pnl_amount, 2)
    conn.execute(
        """
        UPDATE finance_game_profiles
        SET equity = ?,
            trades_taken = ?,
            wins = ?,
            losses = ?,
            draws = ?,
            current_streak = ?,
            best_streak = ?,
            total_pnl = ?,
            gross_profit = ?,
            gross_loss = ?,
            updated_at = ?
        WHERE user_id = ?
        """,
        (
            new_equity,
            trades_taken,
            wins,
            losses,
            draws,
            current_streak,
            best_streak,
            total_pnl,
            round(gross_profit, 2),
            round(gross_loss, 2),
            now_iso,
            user_id,
        ),
    )
    return return_pct, pnl_amount


def _finalize_round_row(conn: sqlite3.Connection, user_id: str, round_id: str) -> None:
    row = conn.execute(
        "SELECT status, position_status FROM finance_game_rounds WHERE id = ? AND user_id = ?",
        (round_id, user_id),
    ).fetchone()
    if row is None or str(row["status"]) == "finished":
        return
    now_iso = _utc_iso()
    pos_status = str(row["position_status"])
    if pos_status == "none":
        conn.execute(
            """
            UPDATE finance_game_rounds
            SET status = 'finished',
                position_status = 'skipped',
                exit_reason = 'skipped',
                finished_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now_iso, round_id, user_id),
        )
    else:
        conn.execute(
            """
            UPDATE finance_game_rounds
            SET status = 'finished',
                finished_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (now_iso, round_id, user_id),
        )
    _ensure_profile_row(conn, user_id)
    conn.execute(
        """
        UPDATE finance_game_profiles
        SET rounds_played = rounds_played + 1,
            updated_at = ?
        WHERE user_id = ?
        """,
        (now_iso, user_id),
    )


def _close_abandoned_active_rounds(conn: sqlite3.Connection, user_id: str) -> None:
    active_rows = conn.execute(
        "SELECT * FROM finance_game_rounds WHERE user_id = ? AND status = 'active'",
        (user_id,),
    ).fetchall()
    for row in active_rows:
        if str(row["position_status"]) == "open":
            all_bars = json.loads(row["bars_json"])
            cur_idx = int(row["cutoff_index"]) + int(row["current_step"])
            cur_bar = all_bars[cur_idx]
            _settle_trade(
                conn,
                user_id,
                row,
                exit_step=int(row["current_step"]),
                exit_date=str(cur_bar["date"]),
                exit_price=float(cur_bar["close"]),
                exit_reason="manual",
            )
        _finalize_round_row(conn, user_id, str(row["id"]))


def serialize_round_for_client(
    row: sqlite3.Row,
    *,
    triggered_event: str | None = None,
) -> dict[str, Any]:
    """Sérialise une manche en masquant strictement le futur et (si aveugle) l'identité/dates."""
    all_bars: list[dict[str, Any]] = json.loads(row["bars_json"])
    status = str(row["status"])
    blind_mode = bool(row["blind_mode"])
    timeframe = str(row["timeframe"])
    cutoff_index = int(row["cutoff_index"])
    horizon_bars = int(row["horizon_bars"])
    current_step = int(row["current_step"])

    visible_end = cutoff_index + (horizon_bars if status == "finished" else current_step)
    visible_end = min(visible_end, len(all_bars) - 1)
    visible_slice = [dict(b) for b in all_bars[: visible_end + 1]]

    mask_identity = status == "active" and blind_mode
    synthetic_dates: list[str] = []
    if mask_identity:
        synthetic_dates = build_synthetic_dates(len(visible_slice), timeframe)
        for idx, bar in enumerate(visible_slice):
            bar["date"] = synthetic_dates[idx]

    cutoff_bar = visible_slice[cutoff_index]
    current_bar = visible_slice[min(cutoff_index + current_step, len(visible_slice) - 1)]
    cutoff_price = float(cutoff_bar["close"])
    current_price = float(current_bar["close"])
    change_from_cutoff_pct = (
        round(((current_price - cutoff_price) / cutoff_price) * 100.0, 2)
        if cutoff_price > 0
        else 0.0
    )

    pos_status = str(row["position_status"])
    pos_side = str(row["position_side"]) if row["position_side"] else None
    entry_step = int(row["entry_step"]) if row["entry_step"] is not None else None
    exit_step = int(row["exit_step"]) if row["exit_step"] is not None else None

    entry_date = str(row["entry_date"]) if row["entry_date"] else None
    exit_date = str(row["exit_date"]) if row["exit_date"] else None
    if mask_identity:
        if entry_step is not None and 0 <= cutoff_index + entry_step < len(synthetic_dates):
            entry_date = synthetic_dates[cutoff_index + entry_step]
        if exit_step is not None and 0 <= cutoff_index + exit_step < len(synthetic_dates):
            exit_date = synthetic_dates[cutoff_index + exit_step]

    unrealized_return_pct: float | None = None
    unrealized_pnl: float | None = None
    if pos_status == "open" and pos_side and row["entry_price"] is not None:
        unrealized_return_pct, unrealized_pnl = _compute_return_and_pnl(
            pos_side,
            float(row["entry_price"]),
            current_price,
            float(row["stake_amount"]),
        )

    is_finished = status == "finished"
    return {
        "id": str(row["id"]),
        "status": status,
        "blind_mode": blind_mode,
        "is_revealed": is_finished or not blind_mode,
        "universe_type": str(row["universe_type"]),
        "universe_value": str(row["universe_value"]),
        "timeframe": timeframe,
        "horizon_code": str(row["horizon_code"]),
        "symbol": None if mask_identity else str(row["symbol"]),
        "company_name": "Action Mystère" if mask_identity else str(row["company_name"]),
        "exchange": None if mask_identity else (str(row["exchange"]) or None),
        "sector": None if mask_identity else (str(row["sector"]) or None),
        "currency": None if mask_identity else (str(row["currency"]) or None),
        "cutoff_index": cutoff_index,
        "horizon_bars": horizon_bars,
        "current_step": current_step,
        "remaining_bars": max(0, horizon_bars - current_step),
        "cutoff_date": None if mask_identity else str(row["cutoff_date"]),
        "end_date": str(row["end_date"]) if is_finished else None,
        "cutoff_price": round(cutoff_price, 4),
        "current_price": round(current_price, 4),
        "change_from_cutoff_pct": change_from_cutoff_pct,
        "position_side": pos_side,
        "position_status": pos_status,
        "position_size_pct": float(row["position_size_pct"]),
        "stake_amount": float(row["stake_amount"]),
        "entry_step": entry_step,
        "entry_date": entry_date,
        "entry_price": float(row["entry_price"]) if row["entry_price"] is not None else None,
        "stop_loss": float(row["stop_loss"]) if row["stop_loss"] is not None else None,
        "take_profit": float(row["take_profit"]) if row["take_profit"] is not None else None,
        "exit_step": exit_step,
        "exit_date": exit_date,
        "exit_price": float(row["exit_price"]) if row["exit_price"] is not None else None,
        "exit_reason": str(row["exit_reason"]) if row["exit_reason"] else None,
        "return_pct": float(row["return_pct"]) if row["return_pct"] is not None else None,
        "pnl_amount": float(row["pnl_amount"]) if row["pnl_amount"] is not None else None,
        "unrealized_return_pct": unrealized_return_pct,
        "unrealized_pnl": unrealized_pnl,
        "buy_hold_return_pct": float(row["buy_hold_return_pct"]) if is_finished and row["buy_hold_return_pct"] is not None else None,
        "triggered_event": triggered_event,
        "bars": visible_slice,
        "created_at": str(row["created_at"]),
        "finished_at": str(row["finished_at"]) if row["finished_at"] else None,
    }


def _serialize_round_summary(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "symbol": str(row["symbol"]),
        "company_name": str(row["company_name"]),
        "timeframe": str(row["timeframe"]),
        "horizon_code": str(row["horizon_code"]),
        "blind_mode": bool(row["blind_mode"]),
        "cutoff_date": str(row["cutoff_date"]),
        "end_date": str(row["end_date"]),
        "position_side": str(row["position_side"]) if row["position_side"] else None,
        "position_status": str(row["position_status"]),
        "exit_reason": str(row["exit_reason"]) if row["exit_reason"] else None,
        "return_pct": float(row["return_pct"]) if row["return_pct"] is not None else None,
        "pnl_amount": float(row["pnl_amount"]) if row["pnl_amount"] is not None else None,
        "buy_hold_return_pct": float(row["buy_hold_return_pct"]) if row["buy_hold_return_pct"] is not None else None,
        "finished_at": str(row["finished_at"]) if row["finished_at"] else None,
    }


def _load_owned_round(conn: sqlite3.Connection, user_id: str, round_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM finance_game_rounds WHERE id = ? AND user_id = ?",
        (round_id, user_id),
    ).fetchone()
    if row is None:
        raise KeyError("Manche introuvable.")
    return row


def start_game_round(
    db_path: Path,
    user_id: str,
    *,
    universe_type: str = "all",
    universe_value: str = "",
    timeframe: str = "day",
    horizon_code: str = "3m",
    blind_mode: bool = True,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Tire une action et une date de coupure T0, puis ouvre une nouvelle manche."""
    u_type = (universe_type or "all").strip().lower()
    u_val = (universe_value or "").strip()
    tf = (timeframe or "day").strip().lower()
    hz = (horizon_code or "3m").strip().lower()

    if u_type not in VALID_UNIVERSES:
        raise ValueError(f"Univers inconnu : {universe_type}")
    if tf not in VALID_TIMEFRAMES:
        raise ValueError(f"Unité temporelle invalide : {timeframe}")
    if hz not in VALID_HORIZONS or hz not in HORIZON_BARS[tf]:
        allowed = ", ".join(HORIZON_BARS[tf].keys())
        raise ValueError(f"Horizon « {horizon_code} » incompatible avec l'unité « {tf} » (autorisés : {allowed}).")

    min_hist = MIN_HISTORY_BARS[tf]
    target_hist = TARGET_HISTORY_BARS[tf]
    horizon_bars = HORIZON_BARS[tf][hz]
    min_needed_agg = min_hist + horizon_bars
    min_raw = _min_raw_bars_needed(tf, hz)

    candidates = list_eligible_symbols(db_path, user_id, u_type, u_val, min_raw_bars=min_raw)
    if not candidates:
        raise ValueError(
            f"Aucune action dans cet univers ne dispose d'au moins {min_raw} barres EOD locales. "
            "Synchronisez des cours dans l'onglet « Données & Synchro » ou élargissez l'univers."
        )

    prng = rng or random.Random()
    with _connect(db_path) as conn:
        recent_rows = conn.execute(
            """
            SELECT symbol FROM finance_game_rounds
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()
        recent_syms = {str(r["symbol"]) for r in recent_rows}

    fresh_pool = [s for s in candidates if s not in recent_syms]
    ordered_pool = (fresh_pool if fresh_pool else list(candidates))
    prng.shuffle(ordered_pool)
    if len(fresh_pool) > 0 and len(fresh_pool) < len(candidates):
        fallback_pool = [s for s in candidates if s in recent_syms]
        prng.shuffle(fallback_pool)
        ordered_pool.extend(fallback_pool)

    chosen_symbol: str | None = None
    chosen_bars: list[dict[str, Any]] = []
    for sym in ordered_pool[:30]:
        raw_bars = get_stored_eod_bars(db_path, sym)
        agg = aggregate_eod_bars(raw_bars, tf)
        if len(agg) >= min_needed_agg:
            chosen_symbol = sym
            chosen_bars = agg
            break

    if not chosen_symbol:
        raise ValueError(
            f"Historique insuffisant après agrégation ({min_needed_agg} bougies requises). "
            "Essayez un horizon plus court ou l'unité Journalier."
        )

    max_cutoff_abs = len(chosen_bars) - 1 - horizon_bars
    min_cutoff_abs = min_hist - 1
    cutoff_abs = prng.randint(min_cutoff_abs, max_cutoff_abs)
    slice_start = max(0, cutoff_abs - target_hist + 1)
    slice_end = cutoff_abs + 1 + horizon_bars
    window_bars = chosen_bars[slice_start:slice_end]
    cutoff_index = cutoff_abs - slice_start

    cutoff_bar = window_bars[cutoff_index]
    end_bar = window_bars[-1]
    cutoff_close = float(cutoff_bar["close"])
    end_close = float(end_bar["close"])
    buy_hold_pct = round(((end_close - cutoff_close) / cutoff_close) * 100.0, 2) if cutoff_close > 0 else 0.0

    round_id = str(uuid.uuid4())
    now_iso = _utc_iso()

    with _connect(db_path) as conn:
        _ensure_profile_row(conn, user_id)
        _close_abandoned_active_rounds(conn, user_id)
        meta = _resolve_symbol_metadata(conn, db_path, chosen_symbol)
        conn.execute(
            """
            INSERT INTO finance_game_rounds (
                id, user_id, status, blind_mode, universe_type, universe_value,
                timeframe, horizon_code, symbol, company_name, exchange, sector, currency,
                cutoff_index, horizon_bars, current_step, cutoff_date, end_date,
                position_side, position_status, position_size_pct, stake_amount,
                buy_hold_return_pct, bars_json, created_at
            ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL, 'none', 100.0, 0.0, ?, ?, ?)
            """,
            (
                round_id,
                user_id,
                1 if blind_mode else 0,
                u_type,
                u_val,
                tf,
                hz,
                chosen_symbol,
                meta["company_name"],
                meta["exchange"],
                meta["sector"],
                meta["currency"],
                cutoff_index,
                horizon_bars,
                str(cutoff_bar["date"]),
                str(end_bar["date"]),
                buy_hold_pct,
                json.dumps(window_bars, separators=(",", ":")),
                now_iso,
            ),
        )
        round_row = _load_owned_round(conn, user_id, round_id)
        profile_row = _ensure_profile_row(conn, user_id)

    return {
        "round": serialize_round_for_client(round_row),
        "profile": _serialize_profile(profile_row),
    }


def open_round_position(
    db_path: Path,
    user_id: str,
    round_id: str,
    *,
    side: str,
    size_pct: float = 100.0,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict[str, Any]:
    """Ouvre la position (Long ou Short) de la manche au cours de clôture courant."""
    clean_side = (side or "").strip().lower()
    if clean_side not in ("long", "short"):
        raise ValueError("Le sens de l'ordre doit être 'long' (achat) ou 'short' (vente).")
    if size_pct < 10.0 or size_pct > 100.0:
        raise ValueError("La taille de position doit être comprise entre 10 % et 100 %.")

    with _connect(db_path) as conn:
        row = _load_owned_round(conn, user_id, round_id)
        if str(row["status"]) != "active":
            raise ValueError("Cette manche est déjà terminée.")
        if str(row["position_status"]) != "none":
            raise ValueError("Une position a déjà été enregistrée sur cette manche.")

        profile_row = _ensure_profile_row(conn, user_id)
        equity = float(profile_row["equity"])
        if equity <= 0:
            raise ValueError("Votre capital virtuel est épuisé. Réinitialisez le portefeuille pour continuer.")

        all_bars = json.loads(row["bars_json"])
        cur_step = int(row["current_step"])
        cur_bar = all_bars[int(row["cutoff_index"]) + cur_step]
        entry_price = float(cur_bar["close"])

        sl_val = float(stop_loss) if stop_loss is not None else None
        tp_val = float(take_profit) if take_profit is not None else None
        if sl_val is not None and sl_val <= 0:
            raise ValueError("Le Stop-Loss doit être strictement positif.")
        if tp_val is not None and tp_val <= 0:
            raise ValueError("Le Take-Profit doit être strictement positif.")

        if clean_side == "long":
            if sl_val is not None and sl_val >= entry_price:
                raise ValueError("En Achat (Long), le Stop-Loss doit être inférieur au prix d'entrée.")
            if tp_val is not None and tp_val <= entry_price:
                raise ValueError("En Achat (Long), le Take-Profit doit être supérieur au prix d'entrée.")
        else:
            if sl_val is not None and sl_val <= entry_price:
                raise ValueError("En Vente (Short), le Stop-Loss doit être supérieur au prix d'entrée.")
            if tp_val is not None and tp_val >= entry_price:
                raise ValueError("En Vente (Short), le Take-Profit doit être inférieur au prix d'entrée.")

        stake_amount = round(equity * (float(size_pct) / 100.0), 2)
        conn.execute(
            """
            UPDATE finance_game_rounds
            SET position_side = ?,
                position_status = 'open',
                position_size_pct = ?,
                stake_amount = ?,
                entry_step = ?,
                entry_date = ?,
                entry_price = ?,
                stop_loss = ?,
                take_profit = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                clean_side,
                round(float(size_pct), 2),
                stake_amount,
                cur_step,
                str(cur_bar["date"]),
                round(entry_price, 6),
                round(sl_val, 6) if sl_val is not None else None,
                round(tp_val, 6) if tp_val is not None else None,
                round_id,
                user_id,
            ),
        )
        updated_row = _load_owned_round(conn, user_id, round_id)
        updated_profile = _ensure_profile_row(conn, user_id)

    return {
        "round": serialize_round_for_client(updated_row),
        "profile": _serialize_profile(updated_profile),
    }


def step_round(
    db_path: Path,
    user_id: str,
    round_id: str,
    *,
    steps: int = 1,
) -> dict[str, Any]:
    """Avance la manche de `steps` bougies en vérifiant SL/TP à chaque bougie traversée."""
    if steps < 1 or steps > 1500:
        raise ValueError("Le nombre de bougies doit être compris entre 1 et 1500.")

    triggered_event: str | None = None
    with _connect(db_path) as conn:
        row = _load_owned_round(conn, user_id, round_id)
        if str(row["status"]) != "active":
            raise ValueError("Cette manche est déjà terminée.")

        all_bars = json.loads(row["bars_json"])
        cutoff_index = int(row["cutoff_index"])
        horizon_bars = int(row["horizon_bars"])
        cur_step = int(row["current_step"])
        target_step = min(horizon_bars, cur_step + steps)

        while cur_step < target_step:
            cur_step += 1
            bar = all_bars[cutoff_index + cur_step]
            row = _load_owned_round(conn, user_id, round_id)
            if str(row["position_status"]) == "open":
                hit = evaluate_intrabar_exit(
                    str(row["position_side"]),
                    bar,
                    float(row["stop_loss"]) if row["stop_loss"] is not None else None,
                    float(row["take_profit"]) if row["take_profit"] is not None else None,
                )
                if hit is not None:
                    exit_price, exit_reason = hit
                    _settle_trade(
                        conn,
                        user_id,
                        row,
                        exit_step=cur_step,
                        exit_date=str(bar["date"]),
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                    )
                    triggered_event = exit_reason
                    break

        conn.execute(
            "UPDATE finance_game_rounds SET current_step = ? WHERE id = ? AND user_id = ?",
            (cur_step, round_id, user_id),
        )

        if cur_step >= horizon_bars:
            row = _load_owned_round(conn, user_id, round_id)
            if str(row["position_status"]) == "open":
                final_bar = all_bars[cutoff_index + cur_step]
                _settle_trade(
                    conn,
                    user_id,
                    row,
                    exit_step=cur_step,
                    exit_date=str(final_bar["date"]),
                    exit_price=float(final_bar["close"]),
                    exit_reason="horizon_end",
                )
                triggered_event = triggered_event or "horizon_end"
            _finalize_round_row(conn, user_id, round_id)

        final_row = _load_owned_round(conn, user_id, round_id)
        profile_row = _ensure_profile_row(conn, user_id)

    return {
        "round": serialize_round_for_client(final_row, triggered_event=triggered_event),
        "profile": _serialize_profile(profile_row),
    }


def close_round_position(
    db_path: Path,
    user_id: str,
    round_id: str,
    *,
    finish_now: bool = False,
) -> dict[str, Any]:
    """Clôture manuellement la position ouverte au cours de clôture de la bougie courante."""
    with _connect(db_path) as conn:
        row = _load_owned_round(conn, user_id, round_id)
        if str(row["status"]) != "active":
            raise ValueError("Cette manche est déjà terminée.")
        if str(row["position_status"]) != "open":
            raise ValueError("Aucune position ouverte à clôturer.")

        all_bars = json.loads(row["bars_json"])
        cutoff_index = int(row["cutoff_index"])
        cur_step = int(row["current_step"])
        cur_bar = all_bars[cutoff_index + cur_step]
        _settle_trade(
            conn,
            user_id,
            row,
            exit_step=cur_step,
            exit_date=str(cur_bar["date"]),
            exit_price=float(cur_bar["close"]),
            exit_reason="manual",
        )

        if finish_now or cur_step >= int(row["horizon_bars"]):
            conn.execute(
                "UPDATE finance_game_rounds SET current_step = ? WHERE id = ? AND user_id = ?",
                (int(row["horizon_bars"]), round_id, user_id),
            )
            _finalize_round_row(conn, user_id, round_id)

        updated_row = _load_owned_round(conn, user_id, round_id)
        profile_row = _ensure_profile_row(conn, user_id)

    return {
        "round": serialize_round_for_client(updated_row, triggered_event="manual"),
        "profile": _serialize_profile(profile_row),
    }


def finish_round(db_path: Path, user_id: str, round_id: str) -> dict[str, Any]:
    """Avance jusqu'à la fin de l'horizon (en évaluant SL/TP) et révèle l'action."""
    with _connect(db_path) as conn:
        row = _load_owned_round(conn, user_id, round_id)
        if str(row["status"]) == "finished":
            profile_row = _ensure_profile_row(conn, user_id)
            return {
                "round": serialize_round_for_client(row),
                "profile": _serialize_profile(profile_row),
            }

        remaining = int(row["horizon_bars"]) - int(row["current_step"])

    if remaining > 0:
        return step_round(db_path, user_id, round_id, steps=remaining)

    with _connect(db_path) as conn:
        row = _load_owned_round(conn, user_id, round_id)
        if str(row["position_status"]) == "open":
            all_bars = json.loads(row["bars_json"])
            cur_step = int(row["current_step"])
            final_bar = all_bars[int(row["cutoff_index"]) + cur_step]
            _settle_trade(
                conn,
                user_id,
                row,
                exit_step=cur_step,
                exit_date=str(final_bar["date"]),
                exit_price=float(final_bar["close"]),
                exit_reason="horizon_end",
            )
        _finalize_round_row(conn, user_id, round_id)
        updated_row = _load_owned_round(conn, user_id, round_id)
        profile_row = _ensure_profile_row(conn, user_id)

    return {
        "round": serialize_round_for_client(updated_row),
        "profile": _serialize_profile(profile_row),
    }


def get_game_round(db_path: Path, user_id: str, round_id: str) -> dict[str, Any]:
    """Charge une manche existante appartenant à `user_id`."""
    with _connect(db_path) as conn:
        row = _load_owned_round(conn, user_id, round_id)
        profile_row = _ensure_profile_row(conn, user_id)
    return {
        "round": serialize_round_for_client(row),
        "profile": _serialize_profile(profile_row),
    }


def get_game_state(db_path: Path, user_id: str, *, history_limit: int = 25) -> dict[str, Any]:
    """Retourne le portefeuille virtuel, la manche active éventuelle et l'historique récent."""
    with _connect(db_path) as conn:
        profile_row = _ensure_profile_row(conn, user_id)
        active_row = conn.execute(
            """
            SELECT * FROM finance_game_rounds
            WHERE user_id = ? AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        history_rows = conn.execute(
            """
            SELECT * FROM finance_game_rounds
            WHERE user_id = ? AND status = 'finished'
            ORDER BY COALESCE(finished_at, created_at) DESC
            LIMIT ?
            """,
            (user_id, history_limit),
        ).fetchall()
        eligible_cnt_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM (
                SELECT symbol FROM finance_eod_bars
                GROUP BY symbol
                HAVING COUNT(*) >= ?
            )
            """,
            (_min_raw_bars_needed("day", "1w"),),
        ).fetchone()

    return {
        "profile": _serialize_profile(profile_row),
        "active_round": serialize_round_for_client(active_row) if active_row else None,
        "history": [_serialize_round_summary(r) for r in history_rows],
        "eligible_symbols_count": int(eligible_cnt_row["cnt"]) if eligible_cnt_row else 0,
    }


def reset_game_profile(
    db_path: Path,
    user_id: str,
    *,
    starting_capital: float = DEFAULT_STARTING_CAPITAL,
    clear_history: bool = False,
) -> dict[str, Any]:
    """Réinitialise le capital virtuel et les compteurs de performance de l'utilisateur."""
    cap = round(max(100.0, float(starting_capital)), 2)
    now_iso = _utc_iso()
    with _connect(db_path) as conn:
        _ensure_profile_row(conn, user_id)
        if clear_history:
            conn.execute("DELETE FROM finance_game_rounds WHERE user_id = ?", (user_id,))
        else:
            # Si une manche est active, la fermer sans altérer les nouveaux compteurs
            active_rows = conn.execute(
                "SELECT id FROM finance_game_rounds WHERE user_id = ? AND status = 'active'",
                (user_id,),
            ).fetchall()
            for r in active_rows:
                conn.execute(
                    """
                    UPDATE finance_game_rounds
                    SET status = 'finished', position_status = 'skipped', exit_reason = 'skipped', finished_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (now_iso, str(r["id"]), user_id),
                )
        conn.execute(
            """
            UPDATE finance_game_profiles
            SET starting_capital = ?,
                equity = ?,
                rounds_played = 0,
                trades_taken = 0,
                wins = 0,
                losses = 0,
                draws = 0,
                current_streak = 0,
                best_streak = 0,
                total_pnl = 0.0,
                gross_profit = 0.0,
                gross_loss = 0.0,
                updated_at = ?
            WHERE user_id = ?
            """,
            (cap, cap, now_iso, user_id),
        )
    return get_game_state(db_path, user_id)
