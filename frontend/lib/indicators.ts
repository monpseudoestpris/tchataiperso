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
  MFI,
  OBV,
  PSAR,
  ROC,
  RSI,
  SMA,
  Stochastic,
  WMA,
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

export function mfi(
  high: number[],
  low: number[],
  close: number[],
  volume: number[],
  period = 14,
): Num[] {
  return align(close.length, MFI.calculate({ high, low, close, volume, period }), plain);
}

export type IsoPressureMaType = "RMA" | "KMA" | "EMA" | "WMA" | "DEMA" | "ALMA" | "HMA";

export const ISO_PRESSURE_STRATEGIES = [
  "Daily best perfo 5 20 - 9",
  "Best Overall 5 20",
  "Best Overall 20 50",
  "Best Overall 5 20 with KMA",
  "Safety 5 20",
  "Safety 20 50",
  "Best overall wo MFI",
  "Expectancy per period 5 20 - 9",
  "ratios - 20 50 - 9",
  "Best ar KMA - 9 - no mfi",
  "Test",
] as const;

export type IsoPressureStrategy = (typeof ISO_PRESSURE_STRATEGIES)[number];

/** Applique une moyenne mobile sur la portion valide (sans null en tête) tout en gardant l'alignement. */
function applyOnValid(series: Num[], fn: (valid: number[]) => Num[]): Num[] {
  const firstValid = series.findIndex(v => v != null && Number.isFinite(v));
  if (firstValid === -1) return new Array(series.length).fill(null);
  // Si des trous apparaissent après firstValid, on les remplace par la dernière valeur valide pour la continuité.
  const valid: number[] = [];
  let last = series[firstValid] as number;
  for (let i = firstValid; i < series.length; i++) {
    const v = series[i];
    if (v != null && Number.isFinite(v)) last = v;
    valid.push(last);
  }
  const computed = fn(valid);
  return new Array<Num>(firstValid).fill(null).concat(computed);
}

function rmaRaw(values: number[], period: number): Num[] {
  const n = values.length;
  const out: Num[] = new Array(n).fill(null);
  if (period < 1 || n < period) return out;
  let sum = 0;
  for (let i = 0; i < period; i++) sum += values[i];
  let prev = sum / period;
  out[period - 1] = prev;
  const alpha = 1 / period;
  for (let i = period; i < n; i++) {
    prev = alpha * values[i] + (1 - alpha) * prev;
    out[i] = prev;
  }
  return out;
}

function kmaRaw(values: number[], period: number): Num[] {
  const n = values.length;
  const out: Num[] = new Array(n).fill(null);
  if (period < 1 || n <= period) return out;
  const fastSC = 2 / (2 + 1);
  const slowSC = 2 / (30 + 1);
  let prev = values[period - 1];
  out[period - 1] = prev;
  for (let i = period; i < n; i++) {
    const change = Math.abs(values[i] - values[i - period]);
    let volatility = 0;
    for (let j = i - period + 1; j <= i; j++) {
      volatility += Math.abs(values[j] - values[j - 1]);
    }
    const er = volatility === 0 ? 0 : change / volatility;
    const sc = Math.pow(er * (fastSC - slowSC) + slowSC, 2);
    prev = prev + sc * (values[i] - prev);
    out[i] = prev;
  }
  return out;
}

function wmaRaw(values: number[], period: number): Num[] {
  if (period <= 1) return values.slice();
  return align(values.length, WMA.calculate({ period, values }), plain);
}

function demaRaw(values: number[], period: number): Num[] {
  const e1 = ema(values, period);
  const e2 = applyOnValid(e1, valid => ema(valid, period));
  return e1.map((v1, i) => {
    const v2 = e2[i];
    return v1 == null || v2 == null ? null : 2 * v1 - v2;
  });
}

function almaRaw(values: number[], period: number, offset = 0.85, sigma = 6): Num[] {
  const n = values.length;
  const out: Num[] = new Array(n).fill(null);
  if (period < 1 || n < period) return out;
  const m = offset * (period - 1);
  const s = period / sigma;
  const weights: number[] = new Array(period);
  let norm = 0;
  for (let j = 0; j < period; j++) {
    const w = Math.exp(-Math.pow(j - m, 2) / (2 * s * s));
    weights[j] = w;
    norm += w;
  }
  for (let i = period - 1; i < n; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += values[i - (period - 1 - j)] * weights[j];
    }
    out[i] = sum / norm;
  }
  return out;
}

function hmaRaw(values: number[], period: number): Num[] {
  if (period <= 1) return values.slice();
  const half = Math.max(1, Math.floor(period / 2));
  const sqrtP = Math.max(1, Math.floor(Math.sqrt(period)));
  const wHalf = wmaRaw(values, half);
  const wFull = wmaRaw(values, period);
  const diff: Num[] = wFull.map((vf, i) => {
    const vh = wHalf[i];
    return vh == null || vf == null ? null : 2 * vh - vf;
  });
  return applyOnValid(diff, valid => wmaRaw(valid, sqrtP));
}

function maSeries(series: Num[], maType: IsoPressureMaType, period: number): Num[] {
  return applyOnValid(series, valid => {
    switch (maType) {
      case "RMA":
        return rmaRaw(valid, period);
      case "KMA":
        return kmaRaw(valid, period);
      case "EMA":
        return ema(valid, period);
      case "WMA":
        return wmaRaw(valid, period);
      case "DEMA":
        return demaRaw(valid, period);
      case "ALMA":
        return almaRaw(valid, period);
      case "HMA":
        return hmaRaw(valid, period);
    }
  });
}

// [wrsi, wstoch, wcci, wmfi, ematypeCode] (0=RMA, 1=KMA, 2=EMA, 3=WMA, 4=DEMA, 5=ALMA, 6=HMA)
const STRATEGY_PRESETS: Record<Exclude<IsoPressureStrategy, "Test">, [number, number, number, number, IsoPressureMaType]> = {
  "Daily best perfo 5 20 - 9": [0.1, 0.1, 0.3, 0.0, "HMA"],
  "Best Overall 5 20": [0.3, 0.1, 0.1, 0.5, "RMA"],
  "Best Overall 20 50": [0.5, 0.1, 0.1, 0.1, "RMA"],
  "Best Overall 5 20 with KMA": [0.3, 0.1, 0.1, 0.5, "KMA"],
  "Safety 5 20": [0.2, 0.3, 0.2, 0.5, "HMA"],
  "Safety 20 50": [0.3, 0.2, 0.5, 0.0, "ALMA"],
  "Best overall wo MFI": [0.5, 0.1, 0.1, 0.0, "RMA"],
  "Expectancy per period 5 20 - 9": [0.1, 0.1, 0.2, 0.0, "HMA"],
  "ratios - 20 50 - 9": [0.2, 0.1, 0.5, 0.0, "KMA"],
  "Best ar KMA - 9 - no mfi": [0.3, 0.2, 0.5, 0.0, "KMA"],
};

export type IsoPressureOptions = {
  strategy: IsoPressureStrategy;
  length: number;
  wrsiTest: number;
  wstochTest: number;
  wcciTest: number;
  wmfiTest: number;
  maTypeTest: IsoPressureMaType;
};

/**
 * IsoPressure (Isostock pressure backtested) — portage du script Pine v5.
 * Combine RSI, Stochastique (%D), Close normalisé par EMA(12), CCI et MFI,
 * puis lisse la pression brute sur 5, 20, 50, 100 et 200 périodes.
 */
export function isoPressure(
  high: number[],
  low: number[],
  close: number[],
  volume: number[],
  opts: IsoPressureOptions,
): {
  raw: Num[];
  p5: Num[];
  p20: Num[];
  p50: Num[];
  p100: Num[];
  p200: Num[];
} {
  const n = close.length;
  const [wrsi, wstoch, wcci, wmfi, maType] =
    opts.strategy === "Test"
      ? [opts.wrsiTest, opts.wstochTest, opts.wcciTest, opts.wmfiTest, opts.maTypeTest]
      : STRATEGY_PRESETS[opts.strategy];

  const wclose = 1.0 - wrsi - wcci - wmfi - wstoch;
  const poidsCci = 0.1;

  const rsiVals = rsi(close, opts.length);
  const cciVals = cci(high, low, close, opts.length);
  const hasVolume = volume.some(v => v != null && Number.isFinite(v) && v > 0);
  const mfiVals = hasVolume ? mfi(high, low, close, volume, opts.length) : null;
  const ksVals = stochastic(high, low, close, 14, 3).d;
  const maxVal = ema(close, 12);

  const raw: Num[] = new Array(n).fill(null);
  for (let i = 0; i < n; i++) {
    const r = rsiVals[i];
    const k = ksVals[i];
    const mv = maxVal[i];
    const c = cciVals[i];
    if (r == null || k == null || mv == null || mv === 0 || c == null) continue;
    const mfiTerm = mfiVals ? (mfiVals[i] == null ? null : (mfiVals[i] as number) * wmfi) : 0;
    if (mfiTerm == null) continue;
    raw[i] = r * wrsi + k * wstoch + ((close[i] * wclose) / mv) * 100 + c * poidsCci + mfiTerm;
  }

  return {
    raw,
    p5: maSeries(raw, maType, 5),
    p20: maSeries(raw, maType, 20),
    p50: maSeries(raw, maType, 50),
    p100: maSeries(raw, maType, 100),
    p200: maSeries(raw, maType, 200),
  };
}
