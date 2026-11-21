"""Moteur Python pur d'indicateurs techniques pour le Screener boursier.

Aligné mathématiquement sur `frontend/lib/indicators.ts` sans dépendance externe lourde
(ni pandas, ni numpy, ni TA-Lib). Conçu pour calculer en < 0,5 ms par action les niveaux
courants et signaux de croisement récents à partir des barres OHLCV stockées dans
`finance_warehouse.db`, tout en exposant les séries complètes pour les futures formules
personnalisées du screener.
"""

from __future__ import annotations

import math
from typing import Any

from .finance_watchlist import compute_period_returns

Num = float | None


def _num(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round_opt(val: float | None, digits: int = 2) -> float | None:
    if val is None or not math.isfinite(val):
        return None
    return round(val, digits)


def sma(values: list[float], period: int) -> list[Num]:
    """Moyenne mobile simple (SMA) alignée sur la longueur de `values`."""
    n = len(values)
    out: list[Num] = [None] * n
    if period < 1 or n < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: list[float], period: int) -> list[Num]:
    """Moyenne mobile exponentielle (EMA) initialisée sur la première SMA."""
    n = len(values)
    out: list[Num] = [None] * n
    if period < 1 or n < period:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = (values[i] - prev) * k + prev
        out[i] = prev
    return out


def rma(values: list[float], period: int) -> list[Num]:
    """Moyenne mobile de Wilder (RMA), utilisée par RSI, ATR et ADX."""
    n = len(values)
    out: list[Num] = [None] * n
    if period < 1 or n < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    alpha = 1.0 / period
    for i in range(period, n):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def rsi(values: list[float], period: int = 14) -> list[Num]:
    """Relative Strength Index (Wilder, 0–100)."""
    n = len(values)
    out: list[Num] = [None] * n
    if period < 1 or n <= period:
        return out
    gains: list[float] = [0.0] * n
    losses: list[float] = [0.0] * n
    for i in range(1, n):
        diff = values[i] - values[i - 1]
        if diff > 0:
            gains[i] = diff
        elif diff < 0:
            losses[i] = -diff

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = 100.0 if avg_loss == 0 else (100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = 100.0 if avg_loss == 0 else (100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
    return out


def macd(
    values: list[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> dict[str, list[Num]]:
    """MACD (ligne, signal, histogramme)."""
    n = len(values)
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    line: list[Num] = [
        (ef - es) if (ef is not None and es is not None) else None
        for ef, es in zip(ema_fast, ema_slow)
    ]
    first_valid = next((i for i, v in enumerate(line) if v is not None), None)
    signal: list[Num] = [None] * n
    if first_valid is not None:
        valid_line = [float(v) for v in line[first_valid:] if v is not None]
        sig_slice = ema(valid_line, signal_period)
        for idx, s_val in enumerate(sig_slice):
            if first_valid + idx < n:
                signal[first_valid + idx] = s_val
    hist: list[Num] = [
        (l_v - s_v) if (l_v is not None and s_v is not None) else None
        for l_v, s_v in zip(line, signal)
    ]
    return {"line": line, "signal": signal, "hist": hist}


def bollinger(values: list[float], period: int = 20, mult: float = 2.0) -> dict[str, list[Num]]:
    """Bandes de Bollinger (mid, upper, lower)."""
    n = len(values)
    mid = sma(values, period)
    upper: list[Num] = [None] * n
    lower: list[Num] = [None] * n
    if period < 2 or n < period:
        return {"mid": mid, "upper": upper, "lower": lower}
    for i in range(period - 1, n):
        m = mid[i]
        if m is None:
            continue
        var = sum((values[j] - m) ** 2 for j in range(i - period + 1, i + 1)) / period
        sd = math.sqrt(var)
        upper[i] = m + mult * sd
        lower[i] = m - mult * sd
    return {"mid": mid, "upper": upper, "lower": lower}


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Num]:
    """Average True Range (Wilder)."""
    n = len(closes)
    out: list[Num] = [None] * n
    if period < 1 or n < period:
        return out
    tr: list[float] = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    return rma(tr, period)


def adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> dict[str, list[Num]]:
    """Average Directional Index (ADX, +DI, -DI)."""
    n = len(closes)
    adx_out: list[Num] = [None] * n
    pdi_out: list[Num] = [None] * n
    mdi_out: list[Num] = [None] * n
    if period < 2 or n < period * 2:
        return {"adx": adx_out, "plus_di": pdi_out, "minus_di": mdi_out}

    tr_l = [0.0] * n
    pdm_l = [0.0] * n
    mdm_l = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        pdm_l[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        mdm_l[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr_l[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    smooth_tr = sum(tr_l[1 : period + 1])
    smooth_pdm = sum(pdm_l[1 : period + 1])
    smooth_mdm = sum(mdm_l[1 : period + 1])
    dx_vals: list[float | None] = [None] * n

    for i in range(period, n):
        if i > period:
            smooth_tr = smooth_tr - (smooth_tr / period) + tr_l[i]
            smooth_pdm = smooth_pdm - (smooth_pdm / period) + pdm_l[i]
            smooth_mdm = smooth_mdm - (smooth_mdm / period) + mdm_l[i]
        if smooth_tr > 0:
            pdi = 100.0 * (smooth_pdm / smooth_tr)
            mdi = 100.0 * (smooth_mdm / smooth_tr)
            pdi_out[i] = pdi
            mdi_out[i] = mdi
            di_sum = pdi + mdi
            dx_vals[i] = (100.0 * abs(pdi - mdi) / di_sum) if di_sum > 0 else 0.0

    valid_dx = [(i, v) for i, v in enumerate(dx_vals) if v is not None]
    if len(valid_dx) >= period:
        first_adx_idx = valid_dx[period - 1][0]
        prev_adx = sum(v for _, v in valid_dx[:period]) / period
        adx_out[first_adx_idx] = prev_adx
        for i, dx_v in valid_dx[period:]:
            prev_adx = ((prev_adx * (period - 1)) + dx_v) / period
            adx_out[i] = prev_adx

    return {"adx": adx_out, "plus_di": pdi_out, "minus_di": mdi_out}


def stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
    signal_period: int = 3,
) -> dict[str, list[Num]]:
    """Oscillateur Stochastique (%K et %D)."""
    n = len(closes)
    k_vals: list[Num] = [None] * n
    if period < 1 or n < period:
        return {"k": k_vals, "d": [None] * n}
    for i in range(period - 1, n):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        denom = hh - ll
        k_vals[i] = 50.0 if denom <= 0 else ((closes[i] - ll) / denom) * 100.0

    d_vals: list[Num] = [None] * n
    first_k = next((i for i, v in enumerate(k_vals) if v is not None), None)
    if first_k is not None:
        valid_k = [float(v) for v in k_vals[first_k:] if v is not None]
        d_slice = sma(valid_k, signal_period)
        for idx, dv in enumerate(d_slice):
            if first_k + idx < n:
                d_vals[first_k + idx] = dv
    return {"k": k_vals, "d": d_vals}


def supertrend(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> dict[str, list[Any]]:
    """Supertrend (période ATR 10, multiplicateur 3), aligné sur `frontend/lib/indicators.ts`."""
    n = len(closes)
    atr_vals = atr(highs, lows, closes, period)
    values: list[Num] = [None] * n
    directions: list[int | None] = [None] * n

    prev_upper: float | None = None
    prev_lower: float | None = None
    prev_dir: int | None = None

    for i in range(n):
        a = atr_vals[i]
        if a is None:
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + multiplier * a
        basic_lower = hl2 - multiplier * a

        final_upper = (
            basic_upper
            if (prev_upper is None or basic_upper < prev_upper or closes[i - 1] > prev_upper)
            else prev_upper
        )
        final_lower = (
            basic_lower
            if (prev_lower is None or basic_lower > prev_lower or closes[i - 1] < prev_lower)
            else prev_lower
        )

        if prev_dir is None:
            direction = 1 if closes[i] >= hl2 else -1
        elif prev_dir == -1 and closes[i] > final_upper:
            direction = 1
        elif prev_dir == 1 and closes[i] < final_lower:
            direction = -1
        else:
            direction = prev_dir

        directions[i] = direction
        values[i] = final_lower if direction == 1 else final_upper
        prev_upper = final_upper
        prev_lower = final_lower
        prev_dir = direction

    return {"value": values, "direction": directions}


def roc(values: list[float], period: int = 12) -> list[Num]:
    """Rate of Change (%)."""
    n = len(values)
    out: list[Num] = [None] * n
    if period < 1 or n <= period:
        return out
    for i in range(period, n):
        prev = values[i - period]
        if prev != 0:
            out[i] = ((values[i] - prev) / prev) * 100.0
    return out


def extract_sparkline(bars: list[dict[str, Any]], max_points: int = 28, window_bars: int = 66) -> list[float]:
    """Extrait une série miniature normalisée des derniers cours de clôture."""
    if not bars or max_points < 2:
        return []
    window = bars[-window_bars:] if window_bars > 0 else bars
    closes: list[float] = []
    for b in window:
        c = _num(b.get("close")) or _num(b.get("adjusted_close"))
        if c is not None and c > 0:
            closes.append(round(c, 2))
    if len(closes) <= max_points:
        return closes
    step = (len(closes) - 1) / float(max_points - 1)
    sampled = [closes[min(len(closes) - 1, round(i * step))] for i in range(max_points)]
    sampled[0] = closes[0]
    sampled[-1] = closes[-1]
    return sampled


def _recent_cross_signal(series_a: list[Num], series_b: list[Num], lookback: int = 3) -> int:
    """Détecte un croisement entre `series_a` et `series_b` sur les `lookback` dernières séances.

    Retourne `+1` (croisement haussier), `-1` (croisement baissier) ou `0` (aucun).
    """
    n = min(len(series_a), len(series_b))
    if n < 2:
        return 0
    start = max(1, n - max(1, lookback))
    for i in range(n - 1, start - 1, -1):
        a0, b0 = series_a[i - 1], series_b[i - 1]
        a1, b1 = series_a[i], series_b[i]
        if a0 is None or b0 is None or a1 is None or b1 is None:
            continue
        if a0 <= b0 and a1 > b1:
            return 1
        if a0 >= b0 and a1 < b1:
            return -1
    return 0


def compute_technical_snapshot(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcule l'ensemble des métriques techniques & de performance pour la table screener.

    Garantit qu'aucune donnée insuffisante n'est remplacée par 0 (toujours `None`).
    """
    empty: dict[str, Any] = {
        "price": None,
        "volume": None,
        "avg_volume_20d": None,
        "rel_volume_20d": None,
        "change_1d_pct": None,
        "change_1w_pct": None,
        "change_1m_pct": None,
        "change_3m_pct": None,
        "change_ytd_pct": None,
        "change_1y_pct": None,
        "dist_52w_high_pct": None,
        "dist_52w_low_pct": None,
        "sma20": None,
        "sma50": None,
        "sma200": None,
        "ema20": None,
        "ema50": None,
        "dist_sma50_pct": None,
        "dist_sma200_pct": None,
        "rsi_14": None,
        "macd_line": None,
        "macd_signal": None,
        "macd_hist": None,
        "macd_cross": None,
        "sma_golden_cross": None,
        "boll_pct_b": None,
        "boll_width_pct": None,
        "adx_14": None,
        "stoch_k": None,
        "atr_pct": None,
        "roc_12": None,
        "supertrend_dir": None,
        "bars_date": None,
        "bars_count": 0,
        "sparkline": [],
    }
    if not bars:
        return empty

    # Filtrer les barres valides chronologiquement
    clean_bars: list[dict[str, Any]] = []
    for b in bars:
        c = _num(b.get("close")) or _num(b.get("adjusted_close"))
        if c is None or c <= 0:
            continue
        o = _num(b.get("open")) or c
        h = _num(b.get("high")) or max(o, c)
        l = _num(b.get("low")) or min(o, c)
        v = _num(b.get("volume"))
        clean_bars.append(
            {
                "date": str(b.get("date") or "")[:10],
                "open": o,
                "high": max(h, o, c),
                "low": min(l, o, c),
                "close": c,
                "adjusted_close": _num(b.get("adjusted_close")) or c,
                "volume": v if (v is not None and v >= 0) else 0.0,
            }
        )
    if not clean_bars:
        return empty

    clean_bars.sort(key=lambda r: r["date"])
    closes = [float(b["close"]) for b in clean_bars]
    highs = [float(b["high"]) for b in clean_bars]
    lows = [float(b["low"]) for b in clean_bars]
    vols = [float(b["volume"]) for b in clean_bars]

    last_close = closes[-1]
    last_vol = vols[-1] if vols[-1] > 0 else None
    last_date = clean_bars[-1]["date"] or None

    returns = compute_period_returns(clean_bars)

    # Volumes moyens 20 séances
    non_zero_vols = [v for v in vols[-20:] if v > 0]
    avg_vol_20 = (sum(non_zero_vols) / len(non_zero_vols)) if len(non_zero_vols) >= 5 else None
    rel_vol_20 = (last_vol / avg_vol_20) if (last_vol and avg_vol_20 and avg_vol_20 > 0) else None

    # Plus haut / plus bas 52 semaines (~252 séances)
    win_52w = clean_bars[-252:]
    high_52w = max(b["high"] for b in win_52w) if len(win_52w) >= 20 else None
    low_52w = min(b["low"] for b in win_52w) if len(win_52w) >= 20 else None
    dist_52w_high = ((last_close - high_52w) / high_52w * 100.0) if (high_52w and high_52w > 0) else None
    dist_52w_low = ((last_close - low_52w) / low_52w * 100.0) if (low_52w and low_52w > 0) else None

    sma20_s = sma(closes, 20)
    sma50_s = sma(closes, 50)
    sma200_s = sma(closes, 200)
    ema20_s = ema(closes, 20)
    ema50_s = ema(closes, 50)

    sma20_v = sma20_s[-1]
    sma50_v = sma50_s[-1]
    sma200_v = sma200_s[-1]
    ema20_v = ema20_s[-1]
    ema50_v = ema50_s[-1]

    dist_sma50 = ((last_close - sma50_v) / sma50_v * 100.0) if (sma50_v and sma50_v > 0) else None
    dist_sma200 = ((last_close - sma200_v) / sma200_v * 100.0) if (sma200_v and sma200_v > 0) else None

    rsi_v = rsi(closes, 14)[-1]
    macd_res = macd(closes, 12, 26, 9)
    macd_line_v = macd_res["line"][-1]
    macd_sig_v = macd_res["signal"][-1]
    macd_hist_v = macd_res["hist"][-1]
    macd_cross_v = _recent_cross_signal(macd_res["line"], macd_res["signal"], lookback=3) if macd_sig_v is not None else None

    # Golden Cross / Death Cross (SMA 50 vs SMA 200 : état + croisement récent)
    sma_golden: int | None = None
    if sma50_v is not None and sma200_v is not None:
        recent_gc = _recent_cross_signal(sma50_s, sma200_s, lookback=5)
        if recent_gc != 0:
            sma_golden = recent_gc * 2  # +2 = Golden Cross récent, -2 = Death Cross récent
        else:
            sma_golden = 1 if sma50_v > sma200_v else -1

    boll = bollinger(closes, 20, 2.0)
    b_up, b_mid, b_lo = boll["upper"][-1], boll["mid"][-1], boll["lower"][-1]
    boll_pct_b: float | None = None
    boll_width_pct: float | None = None
    if b_up is not None and b_lo is not None and b_mid is not None:
        span = b_up - b_lo
        if span > 0:
            boll_pct_b = ((last_close - b_lo) / span) * 100.0
        if b_mid > 0:
            boll_width_pct = (span / b_mid) * 100.0

    adx_v = adx(highs, lows, closes, 14)["adx"][-1]
    stoch_k_v = stochastic(highs, lows, closes, 14, 3)["k"][-1]
    atr_v = atr(highs, lows, closes, 14)[-1]
    atr_pct_v = (atr_v / last_close * 100.0) if (atr_v is not None and last_close > 0) else None
    roc_12_v = roc(closes, 12)[-1]
    st_dir = supertrend(highs, lows, closes, 10, 3.0)["direction"][-1]

    return {
        "price": _round_opt(last_close, 4),
        "volume": _round_opt(last_vol, 0),
        "avg_volume_20d": _round_opt(avg_vol_20, 0),
        "rel_volume_20d": _round_opt(rel_vol_20, 2),
        "change_1d_pct": _round_opt(returns.get("change_1d_pct"), 2),
        "change_1w_pct": _round_opt(returns.get("change_1w_pct"), 2),
        "change_1m_pct": _round_opt(returns.get("change_1m_pct"), 2),
        "change_3m_pct": _round_opt(returns.get("change_3m_pct"), 2),
        "change_ytd_pct": _round_opt(returns.get("change_ytd_pct"), 2),
        "change_1y_pct": _round_opt(returns.get("change_1y_pct"), 2),
        "dist_52w_high_pct": _round_opt(dist_52w_high, 2),
        "dist_52w_low_pct": _round_opt(dist_52w_low, 2),
        "sma20": _round_opt(sma20_v, 4),
        "sma50": _round_opt(sma50_v, 4),
        "sma200": _round_opt(sma200_v, 4),
        "ema20": _round_opt(ema20_v, 4),
        "ema50": _round_opt(ema50_v, 4),
        "dist_sma50_pct": _round_opt(dist_sma50, 2),
        "dist_sma200_pct": _round_opt(dist_sma200, 2),
        "rsi_14": _round_opt(rsi_v, 2),
        "macd_line": _round_opt(macd_line_v, 4),
        "macd_signal": _round_opt(macd_sig_v, 4),
        "macd_hist": _round_opt(macd_hist_v, 4),
        "macd_cross": macd_cross_v,
        "sma_golden_cross": sma_golden,
        "boll_pct_b": _round_opt(boll_pct_b, 2),
        "boll_width_pct": _round_opt(boll_width_pct, 2),
        "adx_14": _round_opt(adx_v, 2),
        "stoch_k": _round_opt(stoch_k_v, 2),
        "atr_pct": _round_opt(atr_pct_v, 2),
        "roc_12": _round_opt(roc_12_v, 2),
        "supertrend_dir": st_dir,
        "bars_date": last_date,
        "bars_count": len(clean_bars),
        "sparkline": extract_sparkline(clean_bars),
    }
