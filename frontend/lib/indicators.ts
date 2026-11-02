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
