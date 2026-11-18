import { type IndicatorFillConfig } from "./chart-zone-fills";
import { ISO_PRESSURE_STRATEGIES, type IsoPressureMaType, type IsoPressureStrategy } from "./indicators";

export type IndicatorKey =
  | "sma20"
  | "sma50"
  | "sma200"
  | "ema20"
  | "ema50"
  | "boll"
  | "supertrend"
  | "vwap"
  | "sar"
  | "volume"
  | "rsi"
  | "macd"
  | "rex"
  | "isopressure"
  | "stoch"
  | "willr"
  | "cci"
  | "roc"
  | "atr"
  | "adx"
  | "obv";

export type IsoPressureParams = {
  strategy: IsoPressureStrategy;
  length: number;
  showRaw: boolean;
  show5: boolean;
  show20: boolean;
  show50: boolean;
  show100: boolean;
  show200: boolean;
  wrsiTest: number;
  wstochTest: number;
  wcciTest: number;
  wmfiTest: number;
  maTypeTest: IsoPressureMaType;
};

const baseFill = (
  upColor = "#10b981",
  downColor = "#f43f5e",
  reference: IndicatorFillConfig["reference"] = "auto",
  extra: Partial<IndicatorFillConfig> = {},
): IndicatorFillConfig => ({
  enabled: false,
  upColor,
  downColor,
  opacity: 0.16,
  reference,
  ...extra,
});

export type IndicatorParamsMap = {
  sma20: { period: number; fill: IndicatorFillConfig };
  sma50: { period: number; fill: IndicatorFillConfig };
  sma200: { period: number; fill: IndicatorFillConfig };
  ema20: { period: number; fill: IndicatorFillConfig };
  ema50: { period: number; fill: IndicatorFillConfig };
  boll: { period: number; mult: number; fill: IndicatorFillConfig };
  supertrend: { period: number; multiplier: number; fill: IndicatorFillConfig };
  vwap: { fill: IndicatorFillConfig };
  sar: { step: number; max: number; fill: IndicatorFillConfig };
  rsi: { period: number; overbought: number; oversold: number; fill: IndicatorFillConfig };
  macd: { fast: number; slow: number; signal: number; fill: IndicatorFillConfig };
  rex: { period: number; signal: number; fill: IndicatorFillConfig };
  isopressure: IsoPressureParams & { fill: IndicatorFillConfig };
  stoch: { period: number; signal: number; fill: IndicatorFillConfig };
  willr: { period: number; fill: IndicatorFillConfig };
  cci: { period: number; fill: IndicatorFillConfig };
  roc: { period: number; fill: IndicatorFillConfig };
  atr: { period: number; fill: IndicatorFillConfig };
  adx: { period: number; fill: IndicatorFillConfig };
  obv: { fill: IndicatorFillConfig };
};

export type ConfigurableIndicatorKey = keyof IndicatorParamsMap;

export const DEFAULT_INDICATOR_PARAMS: IndicatorParamsMap = {
  sma20: { period: 20, fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  sma50: { period: 50, fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  sma200: { period: 200, fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  ema20: { period: 20, fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  ema50: { period: 50, fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  boll: { period: 20, mult: 2, fill: baseFill("#64748b", "#64748b", "auto", { opacity: 0.12 }) },
  supertrend: {
    period: 10,
    multiplier: 3,
    fill: baseFill("#10b981", "#f43f5e", "close", { enabled: true, opacity: 0.16 }),
  },
  vwap: { fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  sar: { step: 0.02, max: 0.2, fill: baseFill("#10b981", "#f43f5e", "close", { opacity: 0.14 }) },
  rsi: {
    period: 14,
    overbought: 70,
    oversold: 30,
    fill: baseFill("#f43f5e", "#10b981", "auto", { opacity: 0.18, upperThreshold: 70, lowerThreshold: 30 }),
  },
  macd: {
    fast: 12,
    slow: 26,
    signal: 9,
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.16, upperThreshold: 0, lowerThreshold: 0 }),
  },
  rex: {
    period: 14,
    signal: 14,
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.16, upperThreshold: 0, lowerThreshold: 0 }),
  },
  isopressure: {
    strategy: "Best Overall 5 20",
    length: 14,
    showRaw: false,
    show5: true,
    show20: true,
    show50: false,
    show100: false,
    show200: false,
    wrsiTest: 0.3,
    wstochTest: 0.1,
    wcciTest: 0.1,
    wmfiTest: 0.5,
    maTypeTest: "RMA",
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.15, upperThreshold: 0, lowerThreshold: 0 }),
  },
  stoch: {
    period: 14,
    signal: 3,
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.16, upperThreshold: 80, lowerThreshold: 20 }),
  },
  willr: {
    period: 14,
    fill: baseFill("#f43f5e", "#10b981", "auto", { opacity: 0.18, upperThreshold: -20, lowerThreshold: -80 }),
  },
  cci: {
    period: 20,
    fill: baseFill("#f43f5e", "#10b981", "auto", { opacity: 0.18, upperThreshold: 100, lowerThreshold: -100 }),
  },
  roc: {
    period: 12,
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.16, upperThreshold: 0, lowerThreshold: 0 }),
  },
  atr: {
    period: 14,
    fill: baseFill("#f97316", "#64748b", "auto", { opacity: 0.16, upperThreshold: 0, lowerThreshold: 0 }),
  },
  adx: {
    period: 14,
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.15, upperThreshold: 25, lowerThreshold: 25 }),
  },
  obv: {
    fill: baseFill("#10b981", "#f43f5e", "auto", { opacity: 0.15, upperThreshold: 0, lowerThreshold: 0 }),
  },
};

export type ParamFieldDef =
  | {
      type?: "number";
      field: string;
      label: string;
      min: number;
      max: number;
      step: number;
    }
  | {
      type: "select";
      field: string;
      label: string;
      options: readonly string[];
    }
  | {
      type: "boolean";
      field: string;
      label: string;
    };

export const INDICATOR_PARAM_DEFS: Record<
  ConfigurableIndicatorKey,
  { title: string; fields: ParamFieldDef[] }
> = {
  sma20: { title: "SMA 1", fields: [{ field: "period", label: "Période", min: 2, max: 500, step: 1 }] },
  sma50: { title: "SMA 2", fields: [{ field: "period", label: "Période", min: 2, max: 500, step: 1 }] },
  sma200: { title: "SMA 3", fields: [{ field: "period", label: "Période", min: 2, max: 500, step: 1 }] },
  ema20: { title: "EMA 1", fields: [{ field: "period", label: "Période", min: 2, max: 500, step: 1 }] },
  ema50: { title: "EMA 2", fields: [{ field: "period", label: "Période", min: 2, max: 500, step: 1 }] },
  boll: {
    title: "Bandes de Bollinger",
    fields: [
      { field: "period", label: "Période", min: 2, max: 200, step: 1 },
      { field: "mult", label: "Écart-type (σ)", min: 0.5, max: 6, step: 0.1 },
    ],
  },
  supertrend: {
    title: "Supertrend",
    fields: [
      { field: "period", label: "Période ATR", min: 2, max: 100, step: 1 },
      { field: "multiplier", label: "Multiplicateur", min: 0.5, max: 10, step: 0.1 },
    ],
  },
  vwap: {
    title: "VWAP",
    fields: [],
  },
  sar: {
    title: "Parabolic SAR",
    fields: [
      { field: "step", label: "Pas (Step)", min: 0.005, max: 0.2, step: 0.005 },
      { field: "max", label: "Maximum", min: 0.05, max: 1, step: 0.05 },
    ],
  },
  rsi: {
    title: "RSI",
    fields: [
      { field: "period", label: "Période", min: 2, max: 100, step: 1 },
      { field: "overbought", label: "Surachat", min: 50, max: 95, step: 1 },
      { field: "oversold", label: "Survente", min: 5, max: 50, step: 1 },
    ],
  },
  macd: {
    title: "MACD",
    fields: [
      { field: "fast", label: "Rapide", min: 2, max: 100, step: 1 },
      { field: "slow", label: "Lente", min: 3, max: 200, step: 1 },
      { field: "signal", label: "Signal", min: 2, max: 50, step: 1 },
    ],
  },
  rex: {
    title: "Rex Oscillator (REX)",
    fields: [
      { field: "period", label: "Période REX", min: 2, max: 100, step: 1 },
      { field: "signal", label: "Signal", min: 2, max: 100, step: 1 },
    ],
  },
  isopressure: {
    title: "IsoPressure (Isostock backtested)",
    fields: [
      { type: "select", field: "strategy", label: "Stratégie", options: ISO_PRESSURE_STRATEGIES },
      { field: "length", label: "Période", min: 2, max: 100, step: 1 },
      { type: "boolean", field: "showRaw", label: "Brute" },
      { type: "boolean", field: "show5", label: "Pression 5" },
      { type: "boolean", field: "show20", label: "Pression 20" },
      { type: "boolean", field: "show50", label: "Pression 50" },
      { type: "boolean", field: "show100", label: "Pression 100" },
      { type: "boolean", field: "show200", label: "Pression 200" },
      { field: "wrsiTest", label: "Poids RSI (Test)", min: 0, max: 1, step: 0.05 },
      { field: "wstochTest", label: "Poids Stoch (Test)", min: 0, max: 1, step: 0.05 },
      { field: "wcciTest", label: "Poids CCI (Test)", min: 0, max: 1, step: 0.05 },
      { field: "wmfiTest", label: "Poids MFI (Test)", min: 0, max: 1, step: 0.05 },
      { type: "select", field: "maTypeTest", label: "MA (Test)", options: ["RMA", "KMA", "EMA", "WMA", "DEMA", "ALMA", "HMA"] },
    ],
  },
  stoch: {
    title: "Stochastique",
    fields: [
      { field: "period", label: "Période %K", min: 2, max: 100, step: 1 },
      { field: "signal", label: "Lissage %D", min: 1, max: 30, step: 1 },
    ],
  },
  willr: { title: "Williams %R", fields: [{ field: "period", label: "Période", min: 2, max: 100, step: 1 }] },
  cci: { title: "CCI", fields: [{ field: "period", label: "Période", min: 2, max: 200, step: 1 }] },
  roc: { title: "ROC (%)", fields: [{ field: "period", label: "Période", min: 1, max: 200, step: 1 }] },
  atr: { title: "ATR", fields: [{ field: "period", label: "Période", min: 2, max: 100, step: 1 }] },
  adx: { title: "ADX / +DI / -DI", fields: [{ field: "period", label: "Période", min: 2, max: 100, step: 1 }] },
  obv: { title: "OBV (On-Balance Volume)", fields: [] },
};

export function isConfigurableIndicator(key: IndicatorKey): key is ConfigurableIndicatorKey {
  return key in INDICATOR_PARAM_DEFS;
}

export function formatIndicatorLabel(key: IndicatorKey, params: IndicatorParamsMap): string {
  switch (key) {
    case "sma20":
      return `SMA ${params.sma20.period}`;
    case "sma50":
      return `SMA ${params.sma50.period}`;
    case "sma200":
      return `SMA ${params.sma200.period}`;
    case "ema20":
      return `EMA ${params.ema20.period}`;
    case "ema50":
      return `EMA ${params.ema50.period}`;
    case "boll":
      return `Bollinger (${params.boll.period}, ${params.boll.mult})`;
    case "supertrend":
      return `Supertrend (${params.supertrend.period}, ${params.supertrend.multiplier})`;
    case "vwap":
      return "VWAP";
    case "sar":
      return "SAR";
    case "volume":
      return "Volume";
    case "rsi":
      return `RSI ${params.rsi.period}`;
    case "macd":
      return `MACD (${params.macd.fast},${params.macd.slow},${params.macd.signal})`;
    case "rex":
      return `REX (${params.rex.period},${params.rex.signal})`;
    case "isopressure":
      return `IsoPressure (${params.isopressure.length})`;
    case "stoch":
      return `Stoch. (${params.stoch.period},${params.stoch.signal})`;
    case "willr":
      return `Williams %R (${params.willr.period})`;
    case "cci":
      return `CCI ${params.cci.period}`;
    case "roc":
      return `ROC ${params.roc.period}`;
    case "atr":
      return `ATR ${params.atr.period}`;
    case "adx":
      return `ADX ${params.adx.period}`;
    case "obv":
      return "OBV";
  }
}

const STORAGE_KEY = "clair_finance_indicator_params_v1";
const CUSTOM_FILLS_STORAGE_KEY = "clair_finance_custom_fills_v1";

export function loadIndicatorParams(): IndicatorParamsMap {
  if (typeof window === "undefined") return DEFAULT_INDICATOR_PARAMS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_INDICATOR_PARAMS;
    const parsed = JSON.parse(raw) as Partial<IndicatorParamsMap>;
    const merged: IndicatorParamsMap = { ...DEFAULT_INDICATOR_PARAMS };
    for (const k of Object.keys(DEFAULT_INDICATOR_PARAMS) as ConfigurableIndicatorKey[]) {
      const entry = parsed[k] as ({ fill?: Partial<IndicatorFillConfig> } & Record<string, unknown>) | undefined;
      if (entry && typeof entry === "object") {
        const def = DEFAULT_INDICATOR_PARAMS[k];
        merged[k] = {
          ...def,
          ...entry,
          fill: {
            ...def.fill,
            ...(entry.fill && typeof entry.fill === "object" ? entry.fill : {}),
          },
        } as never;
      }
    }
    return merged;
  } catch {
    return DEFAULT_INDICATOR_PARAMS;
  }
}

export function loadCustomIndicatorFills(): Record<string, IndicatorFillConfig> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(CUSTOM_FILLS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Partial<IndicatorFillConfig>>;
    const out: Record<string, IndicatorFillConfig> = {};
    for (const [id, cfg] of Object.entries(parsed)) {
      if (cfg && typeof cfg === "object") {
        out[id] = {
          enabled: Boolean(cfg.enabled),
          upColor: typeof cfg.upColor === "string" ? cfg.upColor : "#10b981",
          downColor: typeof cfg.downColor === "string" ? cfg.downColor : "#f43f5e",
          opacity: typeof cfg.opacity === "number" ? cfg.opacity : 0.16,
          reference: (cfg.reference as IndicatorFillConfig["reference"]) ?? "auto",
          upperThreshold: typeof cfg.upperThreshold === "number" ? cfg.upperThreshold : 0,
          lowerThreshold: typeof cfg.lowerThreshold === "number" ? cfg.lowerThreshold : 0,
        };
      }
    }
    return out;
  } catch {
    return {};
  }
}

export function saveCustomIndicatorFills(fills: Record<string, IndicatorFillConfig>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CUSTOM_FILLS_STORAGE_KEY, JSON.stringify(fills));
  } catch {
    // Ignore storage quota errors
  }
}

export function saveIndicatorParams(params: IndicatorParamsMap): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(params));
  } catch {
    // Ignore storage quota errors
  }
}
