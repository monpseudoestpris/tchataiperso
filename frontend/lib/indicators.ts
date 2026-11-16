/**
 * Indicateurs techniques : adaptateur autour de la librairie `technicalindicators`.
 *
 * La librairie renvoie des séries plus courtes que l'entrée (période de chauffe) ;
 * `align` les recale à droite et complète avec `null` pour garder un index par barre.
 * Seul le VWAP est calculé ici (remise à zéro par session, absente de la librairie).
 */
import {
  ADX,
  ATR,
  BollingerBands,
  CCI,
  EMA,
  MACD,
  OBV,
  PSAR,
  ROC,
  RSI,
  SMA,
  Stochastic,
  WilliamsR,
} from "technicalindicators";

export type Num = number | null;

/** Recale une série de la librairie sur `length` barres (valeurs manquantes -> null). */
function align<T>(length: number, series: T[], pick: (item: T) => number | undefined): Num[] {
  const out: Num[] = new Array(length).fill(null);
  const offset = length - series.length;
  series.forEach((item, i) => {
    const v = pick(item);
    out[offset + i] = v != null && Number.isFinite(v) ? v : null;
  });
  return out;
}

const plain = (v: number) => v;

export function sma(values: number[], period: number): Num[] {
  return align(values.length, SMA.calculate({ period, values }), plain);
}

export function ema(values: number[], period: number): Num[] {
  return align(values.length, EMA.calculate({ period, values }), plain);
}

export function rsi(values: number[], period = 14): Num[] {
  return align(values.length, RSI.calculate({ period, values }), plain);
}

/** MACD (12, 26, 9) : ligne, signal et histogramme. */
export function macd(values: number[], fast = 12, slow = 26, signalPeriod = 9) {
  const res = MACD.calculate({
    values,
    fastPeriod: fast,
    slowPeriod: slow,
    signalPeriod,
    SimpleMAOscillator: false,
    SimpleMASignal: false,
  });
  const n = values.length;
  return {
    line: align(n, res, r => r.MACD),
    signal: align(n, res, r => r.signal),
    hist: align(n, res, r => r.histogram),
  };
}

/** Bandes de Bollinger (20, 2σ). */
export function bollinger(values: number[], period = 20, mult = 2) {
  const res = BollingerBands.calculate({ period, stdDev: mult, values });
  const n = values.length;
  return {
    mid: align(n, res, r => r.middle),
    upper: align(n, res, r => r.upper),
    lower: align(n, res, r => r.lower),
  };
}

/** Oscillateur stochastique : %K et %D (SMA 3 de %K). */
export function stochastic(high: number[], low: number[], close: number[], period = 14, signalPeriod = 3) {
  const res = Stochastic.calculate({ high, low, close, period, signalPeriod });
  const n = close.length;
  return { k: align(n, res, r => r.k), d: align(n, res, r => r.d) };
}

export function williamsR(high: number[], low: number[], close: number[], period = 14): Num[] {
  return align(close.length, WilliamsR.calculate({ high, low, close, period }), plain);
}

export function atr(high: number[], low: number[], close: number[], period = 14): Num[] {
  return align(close.length, ATR.calculate({ high, low, close, period }), plain);
}

export function cci(high: number[], low: number[], close: number[], period = 20): Num[] {
  return align(close.length, CCI.calculate({ high, low, close, period }), plain);
}

export function obv(close: number[], volume: number[]): Num[] {
  return align(close.length, OBV.calculate({ close, volume }), plain);
}

export function roc(values: number[], period = 12): Num[] {
  return align(values.length, ROC.calculate({ period, values }), plain);
}

/** ADX avec +DI / -DI. */
export function adx(high: number[], low: number[], close: number[], period = 14) {
  const res = ADX.calculate({ high, low, close, period });
  const n = close.length;
  return {
    adx: align(n, res, r => r.adx),
    plusDi: align(n, res, r => r.pdi),
    minusDi: align(n, res, r => r.mdi),
  };
}

/** Parabolic SAR (pas 0.02, maximum 0.2). */
export function parabolicSar(high: number[], low: number[], step = 0.02, max = 0.2): Num[] {
  return align(high.length, PSAR.calculate({ high, low, step, max }), plain);
}

/** VWAP ; remis à zéro à chaque changement de clé de session (ex. jour en intraday). */
export function vwap(high: number[], low: number[], close: number[], volume: number[], sessionKeys: string[]): Num[] {
  let pv = 0;
  let vol = 0;
  return close.map((c, i) => {
    if (i > 0 && sessionKeys[i] !== sessionKeys[i - 1]) {
      pv = 0;
      vol = 0;
    }
    const v = volume[i] ?? 0;
    pv += ((high[i] + low[i] + c) / 3) * v;
    vol += v;
    return vol === 0 ? null : pv / vol;
  });
}

/** Supertrend (période ATR 10, multiplicateur 3). */
export function supertrend(
  high: number[],
  low: number[],
  close: number[],
  period = 10,
  multiplier = 3,
): { value: Num[]; direction: (1 | -1 | null)[] } {
  const n = close.length;
  const atrVals = atr(high, low, close, period);
  const value: Num[] = new Array(n).fill(null);
  const direction: (1 | -1 | null)[] = new Array(n).fill(null);

  let prevFinalUpper: number | null = null;
  let prevFinalLower: number | null = null;
  let prevDir: 1 | -1 | null = null;

  for (let i = 0; i < n; i++) {
    const a = atrVals[i];
    if (a == null) continue;
    const hl2 = (high[i] + low[i]) / 2;
    const basicUpper = hl2 + multiplier * a;
    const basicLower = hl2 - multiplier * a;

    const finalUpper: number =
      prevFinalUpper == null || basicUpper < prevFinalUpper || close[i - 1] > prevFinalUpper
        ? basicUpper
        : prevFinalUpper;
    const finalLower: number =
      prevFinalLower == null || basicLower > prevFinalLower || close[i - 1] < prevFinalLower
        ? basicLower
        : prevFinalLower;

    let dir: 1 | -1;
    if (prevDir == null) {
      dir = close[i] >= hl2 ? 1 : -1;
    } else if (prevDir === -1 && close[i] > finalUpper) {
      dir = 1;
    } else if (prevDir === 1 && close[i] < finalLower) {
      dir = -1;
    } else {
      dir = prevDir;
    }

    direction[i] = dir;
    value[i] = dir === 1 ? finalLower : finalUpper;
    prevFinalUpper = finalUpper;
    prevFinalLower = finalLower;
    prevDir = dir;
  }

  return { value, direction };
}

/**
 * Rex Oscillator (REX, 14, Signal 14).
 * TVB = 3*close - (open + high + low) = (close - low) + (close - high) + (close - open)
 */
export function rex(
  open: number[],
  high: number[],
  low: number[],
  close: number[],
  period = 14,
  signalPeriod = 14,
): { rex: Num[]; signal: Num[] } {
  const n = close.length;
  const tvb = close.map((c, i) => 3 * c - (open[i] + high[i] + low[i]));
  const rexLine = sma(tvb, period);

  // SMA of rexLine over non-null prefix
  const firstValid = rexLine.findIndex(v => v != null);
  if (firstValid === -1) {
    return { rex: rexLine, signal: new Array(n).fill(null) };
  }
  const validSlice = rexLine.slice(firstValid) as number[];
  const sigSlice = sma(validSlice, signalPeriod);
  const signal: Num[] = new Array(firstValid).fill(null).concat(sigSlice);

  return { rex: rexLine, signal };
}
