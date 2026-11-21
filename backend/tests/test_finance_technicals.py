"""Tests unitaires du moteur d'indicateurs techniques Python (`finance_technicals.py`)."""

from __future__ import annotations

import datetime

from app.finance_technicals import (
    adx,
    atr,
    bollinger,
    compute_technical_snapshot,
    ema,
    macd,
    rsi,
    sma,
    stochastic,
    supertrend,
)


def _make_trend_bars(count: int, *, start: float = 100.0, step: float = 0.5) -> list[dict]:
    base_date = datetime.date(2025, 1, 2)
    bars: list[dict] = []
    for i in range(count):
        close = max(1.0, start + i * step + (1.2 if i % 2 == 0 else -0.6))
        open_p = max(1.0, close - 0.3)
        high = max(open_p, close) + 1.1
        low = max(0.5, min(open_p, close) - 0.9)
        bars.append(
            {
                "date": (base_date + datetime.timedelta(days=i)).isoformat(),
                "open": round(open_p, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "adjusted_close": round(close, 4),
                "volume": 100_000 + (i % 5) * 10_000,
            }
        )
    return bars


def test_sma_and_ema_basic():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sma(vals, 3) == [None, None, 2.0, 3.0, 4.0]
    e = ema(vals, 3)
    assert e[:2] == [None, None]
    assert e[2] == 2.0
    assert e[3] == 3.0
    assert e[4] == 4.0


def test_rsi_monotonic_up_and_down():
    up = [10.0 + i for i in range(30)]
    down = [100.0 - i for i in range(30)]
    rsi_up = rsi(up, 14)
    rsi_down = rsi(down, 14)
    assert rsi_up[-1] == 100.0
    assert rsi_down[-1] is not None and rsi_down[-1] < 1.0


def test_short_series_returns_none_never_zero():
    bars = _make_trend_bars(10)
    snap = compute_technical_snapshot(bars)
    assert snap["price"] is not None
    assert snap["bars_count"] == 10
    assert snap["sma20"] is None
    assert snap["sma50"] is None
    assert snap["sma200"] is None
    assert snap["rsi_14"] is None
    assert snap["macd_line"] is None
    assert snap["adx_14"] is None


def test_full_snapshot_on_uptrend_series():
    bars = _make_trend_bars(260, start=100.0, step=0.4)
    snap = compute_technical_snapshot(bars)

    assert snap["bars_count"] == 260
    assert snap["price"] is not None
    assert snap["sma20"] is not None
    assert snap["sma50"] is not None
    assert snap["sma200"] is not None
    assert snap["price"] > snap["sma50"] > snap["sma200"]
    assert snap["dist_sma200_pct"] is not None and snap["dist_sma200_pct"] > 0
    assert snap["rsi_14"] is not None and 50.0 < snap["rsi_14"] <= 100.0
    assert snap["supertrend_dir"] == 1
    assert snap["sma_golden_cross"] in (1, 2)
    assert snap["adx_14"] is not None and snap["adx_14"] > 15.0
    assert snap["atr_pct"] is not None and snap["atr_pct"] > 0
    assert len(snap["sparkline"]) == 28


def test_oscillators_alignment_lengths():
    bars = _make_trend_bars(60)
    h = [b["high"] for b in bars]
    l = [b["low"] for b in bars]
    c = [b["close"] for b in bars]

    assert len(macd(c)["hist"]) == 60
    assert len(bollinger(c)["upper"]) == 60
    assert len(atr(h, l, c)) == 60
    assert len(adx(h, l, c)["adx"]) == 60
    assert len(stochastic(h, l, c)["k"]) == 60
    assert len(supertrend(h, l, c)["direction"]) == 60
