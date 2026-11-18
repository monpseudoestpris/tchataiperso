import type {
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Logical,
  PrimitivePaneViewZOrder,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";

export type IndicatorFillReference = "auto" | "close" | "hl2" | "high_low" | "threshold";

export type IndicatorFillConfig = {
  enabled: boolean;
  upColor: string;
  downColor: string;
  opacity: number;
  reference: IndicatorFillReference;
  upperThreshold?: number;
  lowerThreshold?: number;
};

export type FillReferenceOption = {
  value: IndicatorFillReference;
  label: string;
};

export type ZoneFillMode = "between" | "above_only" | "below_only";

export type ZoneFillSegmentSpec = {
  a: (number | null)[];
  b: (number | null)[];
  regime?: (1 | -1 | 0 | null)[];
  upColor: string;
  downColor: string;
  opacity: number;
  mode?: ZoneFillMode;
};

export const DEFAULT_CUSTOM_FILL: IndicatorFillConfig = {
  enabled: false,
  upColor: "#10b981",
  downColor: "#f43f5e",
  opacity: 0.16,
  reference: "auto",
  upperThreshold: 0,
  lowerThreshold: 0,
};

type CanvasTarget = Parameters<IPrimitivePaneRenderer["draw"]>[0];

export function hexToRgba(color: string, alpha: number): string {
  const clamped = Math.max(0.02, Math.min(0.85, Number.isFinite(alpha) ? alpha : 0.16));
  const clean = color.trim();
  const shortHex = /^#([0-9a-fA-F]{3})$/.exec(clean);
  if (shortHex) {
    const [r, g, b] = shortHex[1].split("").map(ch => parseInt(ch + ch, 16));
    return `rgba(${r}, ${g}, ${b}, ${clamped})`;
  }
  const fullHex = /^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$/.exec(clean);
  if (fullHex) {
    const r = parseInt(fullHex[1].slice(0, 2), 16);
    const g = parseInt(fullHex[1].slice(2, 4), 16);
    const b = parseInt(fullHex[1].slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${clamped})`;
  }
  return clean;
}

export function constSeries(length: number, value: number): (number | null)[] {
  return Array.from({ length }, () => value);
}

const OVERLAY_REF_OPTIONS: FillReferenceOption[] = [
  { value: "close", label: "Cours (Clôture)" },
  { value: "hl2", label: "Milieu (Haut+Bas)/2" },
  { value: "high_low", label: "Mèches (Haut / Bas)" },
  { value: "threshold", label: "Seuil horizontal fixe" },
];

const BOLL_REF_OPTIONS: FillReferenceOption[] = [
  { value: "auto", label: "Canal (Bande Sup ↔ Inf)" },
  { value: "close", label: "Médiane ↔ Clôture" },
  { value: "hl2", label: "Médiane ↔ (H+L)/2" },
  { value: "threshold", label: "Médiane ↔ Seuil fixe" },
];

const OSCILLATOR_SIGNAL_REF_OPTIONS: FillReferenceOption[] = [
  { value: "auto", label: "Signal / Bandes auto" },
  { value: "threshold", label: "Seuils fixes (Haut / Bas)" },
];

const OSCILLATOR_THRESHOLD_REF_OPTIONS: FillReferenceOption[] = [
  { value: "auto", label: "Zones Surachat / Survente" },
  { value: "threshold", label: "Seuils personnalisés" },
];

export function getFillReferenceOptions(key: string): FillReferenceOption[] {
  if (key === "boll") return BOLL_REF_OPTIONS;
  if (
    key === "sma20" ||
    key === "sma50" ||
    key === "sma200" ||
    key === "ema20" ||
    key === "ema50" ||
    key === "supertrend" ||
    key === "vwap" ||
    key === "sar"
  ) {
    return OVERLAY_REF_OPTIONS;
  }
  if (key === "macd" || key === "rex" || key === "isopressure" || key === "stoch" || key === "adx" || key === "obv") {
    return OSCILLATOR_SIGNAL_REF_OPTIONS;
  }
  return OSCILLATOR_THRESHOLD_REF_OPTIONS;
}

export function supportsCustomThresholds(key: string, fill: IndicatorFillConfig): boolean {
  if (fill.reference === "threshold") return true;
  return (
    fill.reference === "auto" &&
    (key === "willr" || key === "cci" || key === "roc" || key === "atr")
  );
}

type PolyVertex = { x: number; ya: number; yb: number };

function flushPolygon(ctx: CanvasRenderingContext2D, pts: PolyVertex[], color: string, opacity: number) {
  if (pts.length < 2) return;
  ctx.fillStyle = hexToRgba(color, opacity);
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].ya);
  for (let i = 1; i < pts.length; i++) {
    ctx.lineTo(pts[i].x, pts[i].ya);
  }
  for (let i = pts.length - 1; i >= 0; i--) {
    ctx.lineTo(pts[i].x, pts[i].yb);
  }
  ctx.closePath();
  ctx.fill();
}

function drawRegimeSpec(
  ctx: CanvasRenderingContext2D,
  chart: IChartApiBase<Time>,
  series: ISeriesApi<SeriesType, Time>,
  times: Time[],
  spec: ZoneFillSegmentSpec,
  startIdx: number,
  endIdx: number,
) {
  const ts = chart.timeScale();
  const regime = spec.regime!;
  let run: PolyVertex[] = [];
  let runSide: 1 | -1 | 0 = 0;

  for (let i = startIdx; i <= endIdx; i++) {
    const r = regime[i];
    const va = spec.a[i];
    const vb = spec.b[i];
    if ((r !== 1 && r !== -1) || va == null || vb == null || !Number.isFinite(va) || !Number.isFinite(vb)) {
      flushPolygon(ctx, run, runSide === 1 ? spec.upColor : spec.downColor, spec.opacity);
      run = [];
      runSide = 0;
      continue;
    }

    const x = ts.timeToCoordinate(times[i]) ?? ts.logicalToCoordinate(i as Logical);
    const ya = series.priceToCoordinate(va);
    const yb = series.priceToCoordinate(vb);
    if (x == null || ya == null || yb == null || !Number.isFinite(x) || !Number.isFinite(ya) || !Number.isFinite(yb)) {
      flushPolygon(ctx, run, runSide === 1 ? spec.upColor : spec.downColor, spec.opacity);
      run = [];
      runSide = 0;
      continue;
    }

    if (runSide !== 0 && r !== runSide) {
      flushPolygon(ctx, run, runSide === 1 ? spec.upColor : spec.downColor, spec.opacity);
      run = [];
    }
    runSide = r;
    run.push({ x, ya, yb });
  }

  flushPolygon(ctx, run, runSide === 1 ? spec.upColor : spec.downColor, spec.opacity);
}

function shouldFillSide(side: 1 | -1, mode: ZoneFillMode): boolean {
  if (mode === "between") return true;
  if (mode === "above_only") return side === 1;
  return side === -1;
}

function drawCrossingSpec(
  ctx: CanvasRenderingContext2D,
  chart: IChartApiBase<Time>,
  series: ISeriesApi<SeriesType, Time>,
  times: Time[],
  spec: ZoneFillSegmentSpec,
  startIdx: number,
  endIdx: number,
) {
  const ts = chart.timeScale();
  const mode: ZoneFillMode = spec.mode ?? "between";
  let run: PolyVertex[] = [];
  let runSide: 1 | -1 | 0 = 0;
  let prev: { x: number; ya: number; yb: number; va: number; vb: number; diff: number } | null = null;

  const flushRun = () => {
    if (runSide !== 0) {
      flushPolygon(ctx, run, runSide === 1 ? spec.upColor : spec.downColor, spec.opacity);
    }
    run = [];
    runSide = 0;
  };

  for (let i = startIdx; i <= endIdx; i++) {
    const va = spec.a[i];
    const vb = spec.b[i];
    if (va == null || vb == null || !Number.isFinite(va) || !Number.isFinite(vb)) {
      flushRun();
      prev = null;
      continue;
    }

    const x = ts.timeToCoordinate(times[i]) ?? ts.logicalToCoordinate(i as Logical);
    const ya = series.priceToCoordinate(va);
    const yb = series.priceToCoordinate(vb);
    if (x == null || ya == null || yb == null || !Number.isFinite(x) || !Number.isFinite(ya) || !Number.isFinite(yb)) {
      flushRun();
      prev = null;
      continue;
    }

    const diff = va - vb;
    const currPt: PolyVertex = { x, ya, yb };

    if (prev && ((prev.diff > 0 && diff < 0) || (prev.diff < 0 && diff > 0))) {
      const t = Math.abs(prev.diff) / (Math.abs(prev.diff) + Math.abs(diff));
      const vCross = prev.va + t * (va - prev.va);
      const xCross = prev.x + t * (x - prev.x);
      const yCross = series.priceToCoordinate(vCross);
      const prevSide: 1 | -1 = prev.diff > 0 ? 1 : -1;
      const nextSide: 1 | -1 = diff > 0 ? 1 : -1;

      if (yCross != null && Number.isFinite(yCross)) {
        const crossPt: PolyVertex = { x: xCross, ya: yCross, yb: yCross };
        if (runSide === prevSide) {
          run.push(crossPt);
        }
        flushRun();
        if (shouldFillSide(nextSide, mode)) {
          runSide = nextSide;
          run = [crossPt, currPt];
        }
      } else {
        flushRun();
      }
    } else if (diff === 0) {
      if (runSide !== 0) {
        run.push(currPt);
      }
      flushRun();
    } else {
      const side: 1 | -1 = diff > 0 ? 1 : -1;
      const wantFill = shouldFillSide(side, mode);
      if (runSide === side) {
        run.push(currPt);
      } else {
        flushRun();
        if (wantFill) {
          runSide = side;
          if (prev && prev.diff === 0) {
            run = [{ x: prev.x, ya: prev.ya, yb: prev.yb }, currPt];
          } else {
            run = [currPt];
          }
        }
      }
    }

    prev = { x, ya, yb, va, vb, diff };
  }

  flushRun();
}

class ZoneFillRenderer implements IPrimitivePaneRenderer {
  private readonly getContext: () => {
    attached: SeriesAttachedParameter<Time, SeriesType> | null;
    times: Time[];
    specs: ZoneFillSegmentSpec[];
  };

  constructor(
    getContext: () => {
      attached: SeriesAttachedParameter<Time, SeriesType> | null;
      times: Time[];
      specs: ZoneFillSegmentSpec[];
    },
  ) {
    this.getContext = getContext;
  }

  draw(target: CanvasTarget): void {
    const { attached, times, specs } = this.getContext();
    if (!attached || times.length < 2 || specs.length === 0) return;

    const { chart, series } = attached;
    const vis = chart.timeScale().getVisibleLogicalRange();
    const startIdx = vis ? Math.max(0, Math.floor(vis.from) - 2) : 0;
    const endIdx = vis ? Math.min(times.length - 1, Math.ceil(vis.to) + 2) : times.length - 1;
    if (endIdx <= startIdx) return;

    target.useMediaCoordinateSpace(({ context }) => {
      context.save();
      for (const spec of specs) {
        if (spec.regime) {
          drawRegimeSpec(context, chart, series, times, spec, startIdx, endIdx);
        } else {
          drawCrossingSpec(context, chart, series, times, spec, startIdx, endIdx);
        }
      }
      context.restore();
    });
  }
}

class ZoneFillPaneView implements IPrimitivePaneView {
  private readonly _renderer: ZoneFillRenderer;

  constructor(renderer: ZoneFillRenderer) {
    this._renderer = renderer;
  }

  zOrder(): PrimitivePaneViewZOrder {
    return "bottom";
  }

  renderer(): IPrimitivePaneRenderer {
    return this._renderer;
  }
}

export class ZoneFillPrimitive implements ISeriesPrimitive<Time> {
  private _attached: SeriesAttachedParameter<Time, SeriesType> | null = null;
  private readonly _times: Time[];
  private readonly _specs: ZoneFillSegmentSpec[];
  private readonly _paneViews: readonly IPrimitivePaneView[];

  constructor(times: Time[], specs: ZoneFillSegmentSpec[]) {
    this._times = times;
    this._specs = specs;
    const renderer = new ZoneFillRenderer(() => ({
      attached: this._attached,
      times: this._times,
      specs: this._specs,
    }));
    this._paneViews = [new ZoneFillPaneView(renderer)];
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._attached = param;
    param.requestUpdate();
  }

  detached(): void {
    this._attached = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this._paneViews;
  }
}

export function getCustomFillReferenceOptions(pane: "overlay" | "oscillator"): FillReferenceOption[] {
  return pane === "overlay" ? OVERLAY_REF_OPTIONS : OSCILLATOR_THRESHOLD_REF_OPTIONS;
}

export function buildPriceReference(
  reference: IndicatorFillReference,
  closes: number[],
  highs: number[],
  lows: number[],
  threshold?: number,
  regime?: (1 | -1 | 0 | null)[],
  indicatorValues?: (number | null)[],
): (number | null)[] {
  if (reference === "hl2") {
    return highs.map((h, i) => (h + lows[i]) / 2);
  }
  if (reference === "high_low") {
    return closes.map((c, i) => {
      if (regime) return regime[i] === 1 ? lows[i] : highs[i];
      const iv = indicatorValues?.[i];
      if (iv != null && Number.isFinite(iv)) return c >= iv ? lows[i] : highs[i];
      return c;
    });
  }
  if (reference === "threshold") {
    const level = threshold ?? closes[closes.length - 1] ?? 0;
    return constSeries(closes.length, level);
  }
  return closes;
}

export function buildOverlayLineFillSpecs(
  values: (number | null)[],
  fill: IndicatorFillConfig,
  closes: number[],
  highs: number[],
  lows: number[],
): ZoneFillSegmentSpec[] {
  const ref = fill.reference === "auto" ? "close" : fill.reference;
  const priceRef = buildPriceReference(ref, closes, highs, lows, fill.upperThreshold, undefined, values);
  return [
    {
      a: priceRef,
      b: values,
      upColor: fill.upColor,
      downColor: fill.downColor,
      opacity: fill.opacity,
      mode: "between",
    },
  ];
}

export function buildSupertrendFillSpecs(
  stValue: (number | null)[],
  stDirection: (1 | -1 | null)[],
  fill: IndicatorFillConfig,
  closes: number[],
  highs: number[],
  lows: number[],
): ZoneFillSegmentSpec[] {
  const ref = fill.reference === "auto" ? "close" : fill.reference;
  const priceRef = buildPriceReference(ref, closes, highs, lows, fill.upperThreshold, stDirection);
  return [
    {
      a: stValue,
      b: priceRef,
      regime: stDirection,
      upColor: fill.upColor,
      downColor: fill.downColor,
      opacity: fill.opacity,
      mode: "between",
    },
  ];
}

export function buildBollingerFillSpecs(
  upper: (number | null)[],
  mid: (number | null)[],
  lower: (number | null)[],
  fill: IndicatorFillConfig,
  closes: number[],
  highs: number[],
  lows: number[],
): ZoneFillSegmentSpec[] {
  if (fill.reference === "auto") {
    const ones = upper.map(() => 1 as const);
    const negOnes = lower.map(() => -1 as const);
    return [
      {
        a: upper,
        b: mid,
        regime: ones,
        upColor: fill.upColor,
        downColor: fill.downColor,
        opacity: fill.opacity,
        mode: "between",
      },
      {
        a: mid,
        b: lower,
        regime: negOnes,
        upColor: fill.upColor,
        downColor: fill.downColor,
        opacity: fill.opacity,
        mode: "between",
      },
    ];
  }
  return buildOverlayLineFillSpecs(mid, fill, closes, highs, lows);
}

export function buildOscillatorBandFillSpecs(
  values: (number | null)[],
  fill: IndicatorFillConfig,
  defaultUpper: number,
  defaultLower: number,
): ZoneFillSegmentSpec[] {
  const upper = fill.reference === "threshold" ? (fill.upperThreshold ?? defaultUpper) : defaultUpper;
  const lower = fill.reference === "threshold" ? (fill.lowerThreshold ?? defaultLower) : defaultLower;
  return [
    {
      a: values,
      b: constSeries(values.length, upper),
      upColor: fill.upColor,
      downColor: fill.downColor,
      opacity: fill.opacity,
      mode: "above_only",
    },
    {
      a: values,
      b: constSeries(values.length, lower),
      upColor: fill.upColor,
      downColor: fill.downColor,
      opacity: fill.opacity,
      mode: "below_only",
    },
  ];
}

export function buildThresholdSplitFillSpecs(
  values: (number | null)[],
  fill: IndicatorFillConfig,
  defaultThreshold: number,
): ZoneFillSegmentSpec[] {
  const upper = fill.upperThreshold ?? defaultThreshold;
  const lower = fill.lowerThreshold ?? upper;
  if (upper > lower) {
    return [
      {
        a: values,
        b: constSeries(values.length, upper),
        upColor: fill.upColor,
        downColor: fill.downColor,
        opacity: fill.opacity,
        mode: "above_only",
      },
      {
        a: values,
        b: constSeries(values.length, lower),
        upColor: fill.upColor,
        downColor: fill.downColor,
        opacity: fill.opacity,
        mode: "below_only",
      },
    ];
  }
  return [
    {
      a: values,
      b: constSeries(values.length, upper),
      upColor: fill.upColor,
      downColor: fill.downColor,
      opacity: fill.opacity,
      mode: "between",
    },
  ];
}

export function buildDualCurveFillSpecs(
  fast: (number | null)[],
  slow: (number | null)[],
  fill: IndicatorFillConfig,
  defaultThreshold: number,
): ZoneFillSegmentSpec[] {
  if (fill.reference === "threshold") {
    return buildThresholdSplitFillSpecs(fast, fill, defaultThreshold);
  }
  return [
    {
      a: fast,
      b: slow,
      upColor: fill.upColor,
      downColor: fill.downColor,
      opacity: fill.opacity,
      mode: "between",
    },
  ];
}

export function buildCustomOscillatorFillSpecs(
  values: (number | null)[],
  fill: IndicatorFillConfig,
  guideValues: number[],
): ZoneFillSegmentSpec[] {
  if (fill.reference === "auto") {
    const finiteGuides = guideValues.filter(v => Number.isFinite(v));
    if (finiteGuides.length >= 2) {
      return buildOscillatorBandFillSpecs(values, fill, Math.max(...finiteGuides), Math.min(...finiteGuides));
    }
    if (finiteGuides.length === 1) {
      return buildThresholdSplitFillSpecs(
        values,
        { ...fill, upperThreshold: finiteGuides[0], lowerThreshold: finiteGuides[0] },
        finiteGuides[0],
      );
    }
  }
  return buildThresholdSplitFillSpecs(values, fill, 0);
}

export function resolveDefaultCustomFill(pane: "overlay" | "oscillator", guideValues: number[] = []): IndicatorFillConfig {
  const finiteGuides = guideValues.filter(v => Number.isFinite(v));
  const upper = finiteGuides.length > 0 ? Math.max(...finiteGuides) : 0;
  const lower = finiteGuides.length > 0 ? Math.min(...finiteGuides) : 0;
  return {
    enabled: false,
    upColor: pane === "oscillator" && finiteGuides.length >= 2 ? "#f43f5e" : "#10b981",
    downColor: pane === "oscillator" && finiteGuides.length >= 2 ? "#10b981" : "#f43f5e",
    opacity: 0.16,
    reference: pane === "overlay" ? "close" : "auto",
    upperThreshold: upper,
    lowerThreshold: lower,
  };
}

export function attachZoneFill(
  series: ISeriesApi<SeriesType, Time> | null | undefined,
  times: Time[],
  specs: ZoneFillSegmentSpec[],
  fill: IndicatorFillConfig,
): void {
  if (!series || !fill.enabled || specs.length === 0 || times.length < 2) return;
  series.attachPrimitive(new ZoneFillPrimitive(times, specs));
}
