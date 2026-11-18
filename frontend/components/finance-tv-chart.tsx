"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type Logical,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { ChevronDown, ChevronUp, Eraser, Minus, MousePointer, Pencil, Plus, RotateCcw, Settings2, Square, Trash2, TrendingUp, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FinanceHoverTip } from "@/components/finance-info-tip";
import type { CustomIndicator, EodBar } from "@/lib/api";
import {
  dateToLogicalIndex,
  DRAWING_COLORS,
  loadChartDrawings,
  saveChartDrawings,
  type ChartDrawing,
  type DrawingTool,
} from "@/lib/chart-drawings";
import { evaluateCustomIndicator } from "@/lib/custom-indicators";
import {
  attachZoneFill,
  buildBollingerFillSpecs,
  buildCustomOscillatorFillSpecs,
  buildDualCurveFillSpecs,
  buildOscillatorBandFillSpecs,
  buildOverlayLineFillSpecs,
  buildSupertrendFillSpecs,
  buildThresholdSplitFillSpecs,
  getCustomFillReferenceOptions,
  getFillReferenceOptions,
  resolveDefaultCustomFill,
  supportsCustomThresholds,
  type IndicatorFillConfig,
  type IndicatorFillReference,
} from "@/lib/chart-zone-fills";
import {
  DEFAULT_INDICATOR_PARAMS,
  formatIndicatorLabel,
  INDICATOR_PARAM_DEFS,
  isConfigurableIndicator,
  loadCustomIndicatorFills,
  loadIndicatorParams,
  saveCustomIndicatorFills,
  saveIndicatorParams,
  type ConfigurableIndicatorKey,
  type IndicatorKey,
  type IndicatorParamsMap,
} from "@/lib/indicator-params";
import {
  adx,
  atr,
  bollinger,
  cci,
  ema,
  isoPressure,
  macd,
  obv,
  parabolicSar,
  rex,
  roc,
  rsi,
  sma,
  stochastic,
  supertrend,
  vwap,
  williamsR,
  type Num,
} from "@/lib/indicators";

const OVERLAY_KEYS: IndicatorKey[] = [
  "sma20", "sma50", "sma200", "ema20", "ema50", "boll", "supertrend", "vwap", "sar", "volume",
];

const OSCILLATOR_KEYS: IndicatorKey[] = [
  "rsi", "macd", "rex", "isopressure", "stoch", "willr", "cci", "roc", "atr", "adx", "obv",
];

/** "YYYY-MM-DD" reste une date métier ; "YYYY-MM-DD HH:MM" (intraday) devient un timestamp UTC. */
function toTime(date: string): Time {
  if (date.length <= 10) return date;
  return (Date.parse(date.replace(" ", "T") + ":00Z") / 1000) as UTCTimestamp;
}

function pick(times: Time[], values: Num[]) {
  return values.flatMap((v, i) => (v == null || !Number.isFinite(v) ? [] : [{ time: times[i], value: v }]));
}

type FinanceTvChartProps = {
  bars: EodBar[];
  symbol?: string;
  dark: boolean;
  fullscreen?: boolean;
  customIndicators?: CustomIndicator[];
  onOpenIndicatorEditor?: (indicator?: CustomIndicator | null) => void;
  onDeleteCustomIndicator?: (id: string) => void;
};

type ProjectedDrawing = {
  id: string;
  type: "line" | "hline" | "rect";
  color: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  priceLabel?: string;
};

/** Graphique en chandeliers (TradingView lightweight-charts) avec indicateurs natifs, personnalisés et outils de dessin. */
export function FinanceTvChart({
  bars,
  symbol,
  dark,
  fullscreen = false,
  customIndicators = [],
  onOpenIndicatorEditor,
  onDeleteCustomIndicator,
}: FinanceTvChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const rowsRef = useRef<EodBar[]>([]);
  const [active, setActive] = useState<Set<IndicatorKey>>(new Set(["sma20", "volume", "rsi"]));
  const [activeCustom, setActiveCustom] = useState<Set<string>>(new Set());
  const [params, setParams] = useState<IndicatorParamsMap>(() => loadIndicatorParams());
  const [customFills, setCustomFills] = useState<Record<string, IndicatorFillConfig>>(() => loadCustomIndicatorFills());
  const [editingParamKey, setEditingParamKey] = useState<ConfigurableIndicatorKey | null>(null);
  const [editingCustomId, setEditingCustomId] = useState<string | null>(null);
  const [toolbarsCollapsed, setToolbarsCollapsed] = useState(false);
  const seenCustomIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    saveIndicatorParams(params);
  }, [params]);

  useEffect(() => {
    saveCustomIndicatorFills(customFills);
  }, [customFills]);

  // Drawing state
  const [tool, setTool] = useState<DrawingTool>("none");
  const [drawColor, setDrawColor] = useState<string>(DRAWING_COLORS[0]);
  const [drawings, setDrawings] = useState<ChartDrawing[]>(() => loadChartDrawings(symbol));
  const [draft, setDraft] = useState<ChartDrawing | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const dragStartPxRef = useRef<{ x: number; y: number } | null>(null);
  const [overlaySize, setOverlaySize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [projectedDrawings, setProjectedDrawings] = useState<ProjectedDrawing[]>([]);
  const [projectedDraft, setProjectedDraft] = useState<ProjectedDrawing | null>(null);

  // Sync drawings when symbol changes
  useEffect(() => {
    setDrawings(loadChartDrawings(symbol));
    setDraft(null);
    setSelectedId(null);
  }, [symbol]);

  useEffect(() => {
    saveChartDrawings(symbol, drawings);
  }, [symbol, drawings]);

  // Active automatiquement tout nouvel indicateur personnalisé ayant enabled_by_default
  useEffect(() => {
    const newIds: string[] = [];
    for (const ind of customIndicators) {
      if (!seenCustomIdsRef.current.has(ind.id)) {
        seenCustomIdsRef.current.add(ind.id);
        if (ind.enabled_by_default) {
          newIds.push(ind.id);
        }
      }
    }
    if (newIds.length > 0) {
      setActiveCustom(prev => {
        const next = new Set(prev);
        for (const id of newIds) next.add(id);
        return next;
      });
    }
  }, [customIndicators]);

  const customResults = useMemo(() => {
    const rows = bars.filter(
      b => b.close != null && b.open != null && b.high != null && b.low != null,
    );
    const out: Record<string, { values?: Num[]; error?: string }> = {};
    for (const ind of customIndicators) {
      if (!activeCustom.has(ind.id)) continue;
      try {
        out[ind.id] = { values: evaluateCustomIndicator(ind.formula, rows) };
      } catch (err) {
        out[ind.id] = { error: err instanceof Error ? err.message : "Erreur de formule." };
      }
    }
    return out;
  }, [bars, customIndicators, activeCustom]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const rows = bars.filter(
      b => b.close != null && b.open != null && b.high != null && b.low != null,
    );
    const times = rows.map(b => toTime(b.date));
    const opens = rows.map(b => b.open as number);
    const closes = rows.map(b => b.close as number);
    const highs = rows.map(b => b.high as number);
    const lows = rows.map(b => b.low as number);
    const volumes = rows.map(b => b.volume ?? 0);

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: dark ? "#cbd5e1" : "#334155",
        panes: { separatorColor: dark ? "#334155" : "#cbd5e1" },
      },
      grid: {
        vertLines: { color: dark ? "#1e293b" : "#f1f5f9" },
        horzLines: { color: dark ? "#1e293b" : "#f1f5f9" },
      },
      timeScale: { timeVisible: rows.length > 0 && rows[0].date.length > 10 },
    });
    chartRef.current = chart;
    rowsRef.current = rows;

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
    });
    candlesRef.current = candles;
    candles.setData(
      rows.map((b, i) => ({
        time: times[i],
        open: b.open as number,
        high: b.high as number,
        low: b.low as number,
        close: b.close as number,
      })),
    );

    const addLine = (values: Num[], color: string, pane = 0, title?: string) => {
      const s = chart.addSeries(
        LineSeries,
        { color, lineWidth: 2, priceLineVisible: false, lastValueVisible: pane > 0, title },
        pane,
      );
      s.setData(pick(times, values));
      return s;
    };

    const plotCustomSeries = (ind: CustomIndicator, values: Num[], paneIndex: number) => {
      const pts = pick(times, values);
      if (pts.length === 0) return;

      let primarySeries: ReturnType<typeof addLine> | null = null;
      if (ind.series_type === "histogram") {
        const hist = chart.addSeries(
          HistogramSeries,
          { color: ind.color, priceLineVisible: false, lastValueVisible: paneIndex > 0, title: ind.name },
          paneIndex,
        );
        hist.setData(
          pts.map(p => ({
            time: p.time,
            value: p.value,
            color: ind.pane === "oscillator" ? (p.value >= 0 ? `${ind.color}cc` : "#f43f5ecc") : ind.color,
          })),
        );
        primarySeries = hist as unknown as ReturnType<typeof addLine>;
      } else if (ind.series_type === "dots") {
        const dots = chart.addSeries(
          LineSeries,
          {
            color: ind.color,
            lineVisible: false,
            pointMarkersVisible: true,
            pointMarkersRadius: 2,
            priceLineVisible: false,
            lastValueVisible: paneIndex > 0,
            title: ind.name,
          },
          paneIndex,
        );
        dots.setData(pts);
        primarySeries = dots;
      } else {
        primarySeries = addLine(values, ind.color, paneIndex, ind.name);
      }

      if (primarySeries) {
        const customFill =
          customFills[ind.id] ??
          resolveDefaultCustomFill(
            ind.pane,
            (ind.guide_lines || []).map(g => g.value),
          );
        if (customFill.enabled) {
          const specs =
            ind.pane === "overlay"
              ? buildOverlayLineFillSpecs(values, customFill, closes, highs, lows)
              : buildCustomOscillatorFillSpecs(
                  values,
                  customFill,
                  (ind.guide_lines || []).map(g => g.value),
                );
          attachZoneFill(primarySeries, times, specs, customFill);
        }
      }

      if (primarySeries && Array.isArray(ind.guide_lines)) {
        for (const guide of ind.guide_lines) {
          if (typeof guide?.value === "number" && Number.isFinite(guide.value)) {
            primarySeries.createPriceLine({
              price: guide.value,
              color: guide.color || "#94a3b8",
              lineWidth: 1,
              lineStyle: 2,
              axisLabelVisible: false,
              title: "",
            });
          }
        }
      }
    };

    if (active.has("sma20")) {
      const vals = sma(closes, params.sma20.period);
      const s = addLine(vals, "#3b82f6");
      attachZoneFill(s, times, buildOverlayLineFillSpecs(vals, params.sma20.fill, closes, highs, lows), params.sma20.fill);
    }
    if (active.has("sma50")) {
      const vals = sma(closes, params.sma50.period);
      const s = addLine(vals, "#f59e0b");
      attachZoneFill(s, times, buildOverlayLineFillSpecs(vals, params.sma50.fill, closes, highs, lows), params.sma50.fill);
    }
    if (active.has("sma200")) {
      const vals = sma(closes, params.sma200.period);
      const s = addLine(vals, "#ef4444");
      attachZoneFill(s, times, buildOverlayLineFillSpecs(vals, params.sma200.fill, closes, highs, lows), params.sma200.fill);
    }
    if (active.has("ema20")) {
      const vals = ema(closes, params.ema20.period);
      const s = addLine(vals, "#a855f7");
      attachZoneFill(s, times, buildOverlayLineFillSpecs(vals, params.ema20.fill, closes, highs, lows), params.ema20.fill);
    }
    if (active.has("ema50")) {
      const vals = ema(closes, params.ema50.period);
      const s = addLine(vals, "#ec4899");
      attachZoneFill(s, times, buildOverlayLineFillSpecs(vals, params.ema50.fill, closes, highs, lows), params.ema50.fill);
    }
    if (active.has("vwap")) {
      const vals = vwap(highs, lows, closes, volumes, rows.map(b => b.date.slice(0, 10)));
      const s = addLine(vals, "#0ea5e9");
      attachZoneFill(s, times, buildOverlayLineFillSpecs(vals, params.vwap.fill, closes, highs, lows), params.vwap.fill);
    }
    if (active.has("sar")) {
      const sarVals = parabolicSar(highs, lows, params.sar.step, params.sar.max);
      const sar = chart.addSeries(LineSeries, {
        color: "#f97316",
        lineVisible: false,
        pointMarkersVisible: true,
        pointMarkersRadius: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      sar.setData(pick(times, sarVals));
      attachZoneFill(sar, times, buildOverlayLineFillSpecs(sarVals, params.sar.fill, closes, highs, lows), params.sar.fill);
    }
    if (active.has("boll")) {
      const b = bollinger(closes, params.boll.period, params.boll.mult);
      addLine(b.upper, "#94a3b8");
      const midSeries = addLine(b.mid, "#64748b");
      addLine(b.lower, "#94a3b8");
      attachZoneFill(
        midSeries,
        times,
        buildBollingerFillSpecs(b.upper, b.mid, b.lower, params.boll.fill, closes, highs, lows),
        params.boll.fill,
      );
    }
    if (active.has("supertrend")) {
      const st = supertrend(highs, lows, closes, params.supertrend.period, params.supertrend.multiplier);
      const stSeries = chart.addSeries(LineSeries, {
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        title: "Supertrend",
      });
      stSeries.setData(
        st.value.flatMap((v, i) =>
          v == null || !Number.isFinite(v)
            ? []
            : [
                {
                  time: times[i],
                  value: v,
                  color: st.direction[i] === 1 ? "#10b981" : "#f43f5e",
                },
              ],
        ),
      );
      attachZoneFill(
        stSeries,
        times,
        buildSupertrendFillSpecs(st.value, st.direction, params.supertrend.fill, closes, highs, lows),
        params.supertrend.fill,
      );
    }
    if (active.has("volume")) {
      const vol = chart.addSeries(
        HistogramSeries,
        { priceFormat: { type: "volume" }, priceScaleId: "vol", lastValueVisible: false, priceLineVisible: false },
        0,
      );
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      vol.setData(
        rows.flatMap((b, i) =>
          b.volume == null
            ? []
            : [{ time: times[i], value: b.volume, color: (b.close as number) >= (b.open as number) ? "#10b98155" : "#f43f5e55" }],
        ),
      );
    }

    // Indicateurs personnalisés en superposition (Overlay) sur le graphique principal (pane 0)
    for (const ind of customIndicators) {
      if (ind.pane !== "overlay" || !activeCustom.has(ind.id)) continue;
      const res = customResults[ind.id];
      if (res?.values) {
        plotCustomSeries(ind, res.values, 0);
      }
    }

    let pane = 1;
    const guides = (line: ReturnType<typeof addLine>, levels: [number, string][]) =>
      levels.forEach(([price, color]) =>
        line.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" }),
      );
    // Un panneau dédié par oscillateur natif actif, dans l'ordre de la barre d'outils.
    for (const key of OSCILLATOR_KEYS) {
      if (!active.has(key)) continue;
      if (key === "rsi") {
        const rsiVals = rsi(closes, params.rsi.period);
        const s = addLine(rsiVals, "#8b5cf6", pane, `RSI ${params.rsi.period}`);
        guides(s, [
          [params.rsi.overbought, "#f43f5e"],
          [params.rsi.oversold, "#10b981"],
        ]);
        attachZoneFill(
          s,
          times,
          buildOscillatorBandFillSpecs(rsiVals, params.rsi.fill, params.rsi.overbought, params.rsi.oversold),
          params.rsi.fill,
        );
      } else if (key === "macd") {
        const m = macd(closes, params.macd.fast, params.macd.slow, params.macd.signal);
        const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
        hist.setData(
          m.hist.flatMap((v, i) =>
            v == null ? [] : [{ time: times[i], value: v, color: v >= 0 ? "#10b98199" : "#f43f5e99" }],
          ),
        );
        const macdSeries = addLine(m.line, "#3b82f6", pane, "MACD");
        addLine(m.signal, "#f59e0b", pane, "Signal");
        attachZoneFill(macdSeries, times, buildDualCurveFillSpecs(m.line, m.signal, params.macd.fill, 0), params.macd.fill);
      } else if (key === "rex") {
        const r = rex(opens, highs, lows, closes, params.rex.period, params.rex.signal);
        const rexSeries = addLine(r.rex, "#3b82f6", pane, "REX");
        guides(rexSeries, [[0, "#94a3b8"]]);
        addLine(r.signal, "#f59e0b", pane, "Signal");
        attachZoneFill(rexSeries, times, buildDualCurveFillSpecs(r.rex, r.signal, params.rex.fill, 0), params.rex.fill);
      } else if (key === "isopressure") {
        const ipCfg = params.isopressure;
        const ip = isoPressure(highs, lows, closes, volumes, ipCfg);
        let firstIpSeries: ReturnType<typeof addLine> | null = null;
        const visibleCurves: Num[][] = [];
        if (ipCfg.showRaw) {
          firstIpSeries ??= addLine(ip.raw, "#94a3b8", pane, "Pression brute");
          visibleCurves.push(ip.raw);
        }
        if (ipCfg.show5) {
          const s = addLine(ip.p5, "#a855f7", pane, "Pression 5");
          firstIpSeries ??= s;
          visibleCurves.push(ip.p5);
        }
        if (ipCfg.show20) {
          const s = addLine(ip.p20, "#3b82f6", pane, "Pression 20");
          firstIpSeries ??= s;
          visibleCurves.push(ip.p20);
        }
        if (ipCfg.show50) {
          const s = addLine(ip.p50, "#f97316", pane, "Pression 50");
          firstIpSeries ??= s;
          visibleCurves.push(ip.p50);
        }
        if (ipCfg.show100) {
          const s = addLine(ip.p100, "#ef4444", pane, "Pression 100");
          firstIpSeries ??= s;
          visibleCurves.push(ip.p100);
        }
        if (ipCfg.show200) {
          const s = addLine(ip.p200, dark ? "#e2e8f0" : "#0f172a", pane, "Pression 200");
          firstIpSeries ??= s;
          visibleCurves.push(ip.p200);
        }
        if (firstIpSeries && visibleCurves.length > 0) {
          const specs =
            visibleCurves.length >= 2 && ipCfg.fill.reference !== "threshold"
              ? buildDualCurveFillSpecs(visibleCurves[0], visibleCurves[1], ipCfg.fill, 0)
              : buildThresholdSplitFillSpecs(visibleCurves[0], ipCfg.fill, 0);
          attachZoneFill(firstIpSeries, times, specs, ipCfg.fill);
        }
      } else if (key === "stoch") {
        const st = stochastic(highs, lows, closes, params.stoch.period, params.stoch.signal);
        const kSeries = addLine(st.k, "#3b82f6", pane, "%K");
        guides(kSeries, [[80, "#f43f5e"], [20, "#10b981"]]);
        addLine(st.d, "#f59e0b", pane, "%D");
        const stochSpecs =
          params.stoch.fill.reference === "threshold"
            ? buildOscillatorBandFillSpecs(st.k, params.stoch.fill, 80, 20)
            : buildDualCurveFillSpecs(st.k, st.d, params.stoch.fill, 50);
        attachZoneFill(kSeries, times, stochSpecs, params.stoch.fill);
      } else if (key === "willr") {
        const wrVals = williamsR(highs, lows, closes, params.willr.period);
        const s = addLine(wrVals, "#14b8a6", pane, "%R");
        guides(s, [[-20, "#f43f5e"], [-80, "#10b981"]]);
        attachZoneFill(s, times, buildOscillatorBandFillSpecs(wrVals, params.willr.fill, -20, -80), params.willr.fill);
      } else if (key === "cci") {
        const cciVals = cci(highs, lows, closes, params.cci.period);
        const s = addLine(cciVals, "#6366f1", pane, "CCI");
        guides(s, [[100, "#f43f5e"], [-100, "#10b981"]]);
        attachZoneFill(s, times, buildOscillatorBandFillSpecs(cciVals, params.cci.fill, 100, -100), params.cci.fill);
      } else if (key === "roc") {
        const rocVals = roc(closes, params.roc.period);
        const s = addLine(rocVals, "#0ea5e9", pane, "ROC");
        guides(s, [[0, "#94a3b8"]]);
        attachZoneFill(s, times, buildThresholdSplitFillSpecs(rocVals, params.roc.fill, 0), params.roc.fill);
      } else if (key === "atr") {
        const atrVals = atr(highs, lows, closes, params.atr.period);
        const s = addLine(atrVals, "#f97316", pane, "ATR");
        attachZoneFill(s, times, buildThresholdSplitFillSpecs(atrVals, params.atr.fill, 0), params.atr.fill);
      } else if (key === "adx") {
        const a = adx(highs, lows, closes, params.adx.period);
        const adxSeries = addLine(a.adx, "#0f172a", pane, "ADX");
        guides(adxSeries, [[25, "#94a3b8"]]);
        addLine(a.plusDi, "#10b981", pane, "+DI");
        addLine(a.minusDi, "#f43f5e", pane, "-DI");
        const adxSpecs =
          params.adx.fill.reference === "threshold"
            ? buildThresholdSplitFillSpecs(a.adx, params.adx.fill, 25)
            : buildDualCurveFillSpecs(a.plusDi, a.minusDi, params.adx.fill, 25);
        attachZoneFill(adxSeries, times, adxSpecs, params.adx.fill);
      } else if (key === "obv") {
        const obvVals = obv(closes, volumes);
        const obvSeries = addLine(obvVals, "#a855f7", pane, "OBV");
        const obvSignal = ema(
          obvVals.map(v => v ?? 0),
          20,
        );
        attachZoneFill(obvSeries, times, buildDualCurveFillSpecs(obvVals, obvSignal, params.obv.fill, 0), params.obv.fill);
      }
      pane++;
    }

    // Panneau dédié pour chaque oscillateur personnalisé actif
    for (const ind of customIndicators) {
      if (ind.pane !== "oscillator" || !activeCustom.has(ind.id)) continue;
      const res = customResults[ind.id];
      if (res?.values) {
        plotCustomSeries(ind, res.values, pane);
        pane++;
      }
    }

    chart.timeScale().fitContent();

    const updateSizeAndProjections = () => {
      const size = chart.paneSize(0);
      setOverlaySize({ width: size.width, height: size.height });
    };
    updateSizeAndProjections();

    const ro = new ResizeObserver(updateSizeAndProjections);
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
    };
  }, [bars, active, activeCustom, customIndicators, customResults, dark, params, customFills]);

  const projectDrawing = useCallback((d: ChartDrawing, paneWidth: number): ProjectedDrawing | null => {
    const chart = chartRef.current;
    const candles = candlesRef.current;
    const rows = rowsRef.current;
    if (!chart || !candles || rows.length === 0) return null;

    const y1 = candles.priceToCoordinate(d.p1);
    if (y1 == null) return null;

    if (d.type === "hline") {
      return {
        id: d.id,
        type: "hline",
        color: d.color,
        x1: 0,
        y1,
        x2: paneWidth,
        y2: y1,
        priceLabel: d.p1.toFixed(2),
      };
    }

    const idx1 = dateToLogicalIndex(rows, d.t1);
    const idx2 = dateToLogicalIndex(rows, d.t2);
    if (idx1 == null || idx2 == null) return null;
    const x1 = chart.timeScale().logicalToCoordinate(idx1 as Logical);
    const x2 = chart.timeScale().logicalToCoordinate(idx2 as Logical);
    const y2 = candles.priceToCoordinate(d.p2);
    if (x1 == null || x2 == null || y2 == null) return null;

    return {
      id: d.id,
      type: d.type,
      color: d.color,
      x1,
      y1,
      x2,
      y2,
    };
  }, []);

  const recomputeOverlay = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const size = chart.paneSize(0);
    setOverlaySize({ width: size.width, height: size.height });
    setProjectedDrawings(
      drawings.flatMap(d => {
        const p = projectDrawing(d, size.width);
        return p ? [p] : [];
      }),
    );
    setProjectedDraft(draft ? projectDrawing(draft, size.width) : null);
  }, [drawings, draft, projectDrawing]);

  useEffect(() => {
    recomputeOverlay();
    const chart = chartRef.current;
    if (!chart) return;
    const handler = () => recomputeOverlay();
    chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
    };
  }, [recomputeOverlay, bars, active, activeCustom, fullscreen]);

  // Delete selected drawing with Delete / Backspace
  useEffect(() => {
    if (!selectedId) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Delete" || e.key === "Backspace") {
        const target = e.target as HTMLElement | null;
        if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
        e.preventDefault();
        setDrawings(prev => prev.filter(d => d.id !== selectedId));
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedId]);

  function pointFromEvent(e: React.MouseEvent<SVGSVGElement>): { date: string; price: number; px: { x: number; y: number } } | null {
    const chart = chartRef.current;
    const candles = candlesRef.current;
    const rows = rowsRef.current;
    if (!chart || !candles || rows.length === 0) return null;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const price = candles.coordinateToPrice(y);
    const logical = chart.timeScale().coordinateToLogical(x);
    if (price == null || logical == null) return null;
    const clampedIdx = Math.max(0, Math.min(rows.length - 1, Math.round(logical)));
    return { date: rows[clampedIdx].date, price: Number(price), px: { x, y } };
  }

  function commitDraft(nextDraft: ChartDrawing) {
    setDrawings(prev => [...prev, nextDraft]);
    setDraft(null);
    dragStartPxRef.current = null;
    setSelectedId(nextDraft.id);
  }

  function deleteDrawing(id: string) {
    setDrawings(prev => prev.filter(d => d.id !== id));
    setSelectedId(prev => (prev === id ? null : prev));
  }

  function startShapeDrag(
    e: React.MouseEvent,
    projected: ProjectedDrawing,
    mode: "move" | "p1" | "p2",
  ) {
    if (tool !== "none") return;
    e.stopPropagation();
    e.preventDefault();
    setSelectedId(projected.id);

    const svgEl = svgRef.current;
    const chart = chartRef.current;
    const candles = candlesRef.current;
    const rows = rowsRef.current;
    const orig = drawings.find(d => d.id === projected.id);
    if (!svgEl || !chart || !candles || rows.length === 0 || !orig) return;

    const rect = svgEl.getBoundingClientRect();
    const startX = e.clientX - rect.left;
    const startY = e.clientY - rect.top;

    chart.applyOptions({ handleScroll: { mouseWheel: true, pressedMouseMove: false } });

    const pxToDate = (x: number): string | null => {
      const logical = chart.timeScale().coordinateToLogical(x);
      if (logical == null) return null;
      const idx = Math.max(0, Math.min(rows.length - 1, Math.round(logical)));
      return rows[idx].date;
    };

    const onMouseMove = (ev: MouseEvent) => {
      const curX = ev.clientX - rect.left;
      const curY = ev.clientY - rect.top;
      const dx = curX - startX;
      const dy = curY - startY;

      setDrawings(prev =>
        prev.map(d => {
          if (d.id !== orig.id) return d;
          if (mode === "move") {
            const p1 = candles.coordinateToPrice(projected.y1 + dy);
            if (p1 == null) return d;
            if (orig.type === "hline") {
              return { ...d, p1: Number(p1), p2: Number(p1) };
            }
            const p2 = candles.coordinateToPrice(projected.y2 + dy);
            const t1 = pxToDate(projected.x1 + dx);
            const t2 = pxToDate(projected.x2 + dx);
            if (p2 == null || !t1 || !t2) return d;
            return { ...d, t1, p1: Number(p1), t2, p2: Number(p2) };
          }
          const price = candles.coordinateToPrice(curY);
          const date = pxToDate(curX);
          if (price == null || !date) return d;
          if (mode === "p1") return { ...d, t1: date, p1: Number(price) };
          return { ...d, t2: date, p2: Number(price) };
        }),
      );
    };

    const onMouseUp = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      chartRef.current?.applyOptions({ handleScroll: { mouseWheel: true, pressedMouseMove: true } });
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  function handleOverlayMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    if (tool === "none") {
      setSelectedId(null);
      return;
    }
    const pt = pointFromEvent(e);
    if (!pt) return;

    if (tool === "hline") {
      const id = `d_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      commitDraft({
        id,
        type: "hline",
        color: drawColor,
        t1: pt.date,
        p1: pt.price,
        t2: pt.date,
        p2: pt.price,
      });
      return;
    }

    if (!draft) {
      const id = `d_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      dragStartPxRef.current = pt.px;
      setDraft({
        id,
        type: tool,
        color: drawColor,
        t1: pt.date,
        p1: pt.price,
        t2: pt.date,
        p2: pt.price,
      });
    } else {
      commitDraft({ ...draft, t2: pt.date, p2: pt.price });
    }
  }

  function handleOverlayMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!draft) return;
    const pt = pointFromEvent(e);
    if (!pt) return;
    setDraft(prev => (prev ? { ...prev, t2: pt.date, p2: pt.price } : null));
  }

  function handleOverlayMouseUp(e: React.MouseEvent<SVGSVGElement>) {
    if (!draft || !dragStartPxRef.current) return;
    const pt = pointFromEvent(e);
    if (!pt) return;
    const dx = pt.px.x - dragStartPxRef.current.x;
    const dy = pt.px.y - dragStartPxRef.current.y;
    if (Math.hypot(dx, dy) > 8) {
      commitDraft({ ...draft, t2: pt.date, p2: pt.price });
    }
  }

  function toggle(key: IndicatorKey) {
    setActive(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleCustom(id: string) {
    setActiveCustom(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const customOverlays = customIndicators.filter(ind => ind.pane === "overlay");
  const customOscillators = customIndicators.filter(ind => ind.pane === "oscillator");
  const activeCustomOscCount = customOscillators.filter(
    ind => activeCustom.has(ind.id) && customResults[ind.id]?.values,
  ).length;
  const panes = 1 + OSCILLATOR_KEYS.filter(k => active.has(k)).length + activeCustomOscCount;
  const customFormulaErrors = customIndicators
    .filter(ind => activeCustom.has(ind.id) && customResults[ind.id]?.error)
    .map(ind => `${ind.name} : ${customResults[ind.id]?.error}`);

  const showToolbars = !fullscreen || !toolbarsCollapsed;

  function renderNativePill(key: IndicatorKey) {
    const isActive = active.has(key);
    const label = formatIndicatorLabel(key, params);
    const configurable = isConfigurableIndicator(key);
    if (!configurable) {
      return (
        <FinanceHoverTip key={key} termKey={key} delayMs={220}>
          <button
            type="button"
            className={`finance-tf-btn ${isActive ? "active" : ""}`}
            onClick={() => toggle(key)}
          >
            {label}
          </button>
        </FinanceHoverTip>
      );
    }
    const isEditing = editingParamKey === key;
    const fillEnabled = params[key].fill.enabled;
    return (
      <FinanceHoverTip key={key} termKey={key} delayMs={220}>
        <span
          className={`finance-native-ind-pill ${isActive ? "active" : ""} ${isEditing ? "is-editing" : ""}`}
        >
          <button type="button" className="finance-native-ind-toggle" onClick={() => toggle(key)}>
            <span>{label}</span>
            {fillEnabled && (
              <span
                className="finance-ind-fill-dot"
                style={{
                  background: `linear-gradient(135deg, ${params[key].fill.upColor} 50%, ${params[key].fill.downColor} 50%)`,
                }}
                title="Zone remplie active"
              />
            )}
          </button>
          <button
            type="button"
            className="finance-native-ind-gear"
            onClick={() => {
              setEditingCustomId(null);
              setEditingParamKey(prev => (prev === key ? null : key));
            }}
            title={`Paramétrer ${INDICATOR_PARAM_DEFS[key].title}`}
            aria-label={`Paramétrer ${label}`}
          >
            <Settings2 size={10} />
          </button>
        </span>
      </FinanceHoverTip>
    );
  }

  function renderCustomPill(ind: CustomIndicator) {
    const isActive = activeCustom.has(ind.id);
    const isEditing = editingCustomId === ind.id;
    const customFill = customFills[ind.id];
    const summary =
      ind.pane === "overlay"
        ? "Indicateur technique personnalisé superposé au graphique."
        : "Oscillateur technique personnalisé affiché dans un panneau dédié.";
    return (
      <FinanceHoverTip
        key={ind.id}
        delayMs={220}
        definition={{ title: ind.name, summary, formula: ind.formula }}
      >
        <span className={`finance-custom-ind-pill ${isActive ? "active" : ""} ${isEditing ? "is-editing" : ""}`}>
          <button
            type="button"
            className="finance-custom-ind-toggle"
            onClick={() => toggleCustom(ind.id)}
          >
            <span className="finance-custom-dot" style={{ background: ind.color }} />
            <span>{ind.name}</span>
            {customFill?.enabled && (
              <span
                className="finance-ind-fill-dot"
                style={{
                  background: `linear-gradient(135deg, ${customFill.upColor} 50%, ${customFill.downColor} 50%)`,
                }}
                title="Zone remplie active"
              />
            )}
          </button>
          <button
            type="button"
            className="finance-custom-ind-action"
            onClick={() => {
              setEditingParamKey(null);
              setEditingCustomId(prev => (prev === ind.id ? null : ind.id));
            }}
            title="Paramétrer la zone remplie"
            aria-label={`Zone remplie ${ind.name}`}
          >
            <Settings2 size={10} />
          </button>
          {onOpenIndicatorEditor && (
            <button
              type="button"
              className="finance-custom-ind-action"
              onClick={() => onOpenIndicatorEditor(ind)}
              title="Modifier cet indicateur"
              aria-label={`Modifier ${ind.name}`}
            >
              <Pencil size={10} />
            </button>
          )}
          {onDeleteCustomIndicator && (
            <button
              type="button"
              className="finance-custom-ind-action is-del"
              onClick={() => onDeleteCustomIndicator(ind.id)}
              title="Supprimer cet indicateur"
              aria-label={`Supprimer ${ind.name}`}
            >
              <Trash2 size={10} />
            </button>
          )}
        </span>
      </FinanceHoverTip>
    );
  }

  const editingMeta = editingParamKey ? INDICATOR_PARAM_DEFS[editingParamKey] : null;
  const editingValues = editingParamKey
    ? (params[editingParamKey] as unknown as Record<string, number | string | boolean>)
    : null;
  const editingCustomInd = editingCustomId
    ? customIndicators.find(ind => ind.id === editingCustomId) ?? null
    : null;
  const editingFill: IndicatorFillConfig | null = editingParamKey
    ? params[editingParamKey].fill
    : editingCustomInd
      ? customFills[editingCustomInd.id] ??
        resolveDefaultCustomFill(
          editingCustomInd.pane,
          (editingCustomInd.guide_lines || []).map(g => g.value),
        )
      : null;

  const updateEditingFill = (patch: Partial<IndicatorFillConfig>) => {
    if (editingParamKey) {
      setParams(prev => ({
        ...prev,
        [editingParamKey]: {
          ...prev[editingParamKey],
          fill: {
            ...prev[editingParamKey].fill,
            ...patch,
          },
        },
      }));
    } else if (editingCustomInd && editingFill) {
      setCustomFills(prev => ({
        ...prev,
        [editingCustomInd.id]: {
          ...editingFill,
          ...patch,
        },
      }));
    }
  };

  const editingRefOptions = editingParamKey
    ? getFillReferenceOptions(editingParamKey)
    : editingCustomInd
      ? getCustomFillReferenceOptions(editingCustomInd.pane)
      : [];
  const showFillThresholds = Boolean(
    editingFill &&
      editingFill.enabled &&
      (editingParamKey
        ? supportsCustomThresholds(editingParamKey, editingFill)
        : editingFill.reference === "threshold"),
  );

  return (
    <div className={`finance-tv-wrap${fullscreen ? " is-fullscreen" : ""}`}>
      {fullscreen && (
        <div className="finance-tv-collapse-row">
          <button
            type="button"
            className="finance-tv-collapse-btn"
            onClick={() => setToolbarsCollapsed(prev => !prev)}
          >
            {toolbarsCollapsed ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
            <span>
              {toolbarsCollapsed
                ? `Afficher les indicateurs (${active.size + activeCustom.size} actifs)`
                : "Masquer la barre d'indicateurs"}
            </span>
          </button>
        </div>
      )}

      {showToolbars && (
        <>
      <div className="finance-tv-toolbar">
        <small>Tendance & prix</small>
        {OVERLAY_KEYS.map(renderNativePill)}
        {customOverlays.map(renderCustomPill)}
        {onOpenIndicatorEditor && (
          <button
            type="button"
            className="finance-custom-add-btn"
            onClick={() => onOpenIndicatorEditor(null)}
            title="Créer un indicateur personnalisé façon TradingView"
          >
            <Plus size={12} />
            <span>Indicateur perso</span>
          </button>
        )}
      </div>

      <div className="finance-tv-toolbar">
        <small>Oscillateurs</small>
        {OSCILLATOR_KEYS.map(renderNativePill)}
        {customOscillators.map(renderCustomPill)}
          </div>

          {((editingParamKey && editingMeta && editingValues) || editingCustomInd) && editingFill && (
            <div className="finance-ind-params-panel">
              <strong className="finance-ind-params-title">
                {editingMeta ? editingMeta.title : `${editingCustomInd!.name} (Perso)`}
              </strong>
              <div className="finance-ind-params-fields">
                {editingParamKey &&
                  editingMeta &&
                  editingValues &&
                  editingMeta.fields
                    .filter(f => {
                      if (
                        editingParamKey === "isopressure" &&
                        editingValues.strategy !== "Test" &&
                        (f.field === "wrsiTest" ||
                          f.field === "wstochTest" ||
                          f.field === "wcciTest" ||
                          f.field === "wmfiTest" ||
                          f.field === "maTypeTest")
                      ) {
                        return false;
                      }
                      return true;
                    })
                    .map(f => {
                      if (f.type === "select") {
                        return (
                          <label key={f.field} className="finance-ind-param-field">
                            <span>{f.label}</span>
                            <select
                              value={String(editingValues[f.field] ?? f.options[0])}
                              onChange={e => {
                                const val = e.target.value;
                                setParams(prev => ({
                                  ...prev,
                                  [editingParamKey]: {
                                    ...prev[editingParamKey],
                                    [f.field]: val,
                                  },
                                }));
                              }}
                            >
                              {f.options.map(opt => (
                                <option key={opt} value={opt}>
                                  {opt}
                                </option>
                              ))}
                            </select>
                          </label>
                        );
                      }
                      if (f.type === "boolean") {
                        return (
                          <label key={f.field} className="finance-ind-param-field is-checkbox">
                            <input
                              type="checkbox"
                              checked={Boolean(editingValues[f.field])}
                              onChange={e => {
                                const checked = e.target.checked;
                                setParams(prev => ({
                                  ...prev,
                                  [editingParamKey]: {
                                    ...prev[editingParamKey],
                                    [f.field]: checked,
                                  },
                                }));
                              }}
                            />
                            <span>{f.label}</span>
                          </label>
                        );
                      }
                      return (
                        <label key={f.field} className="finance-ind-param-field">
                          <span>{f.label}</span>
                          <input
                            type="number"
                            min={f.min}
                            max={f.max}
                            step={f.step}
                            value={Number(editingValues[f.field] ?? f.min)}
                            onChange={e => {
                              const raw = Number(e.target.value);
                              if (!Number.isFinite(raw)) return;
                              const clamped = Math.max(f.min, Math.min(f.max, raw));
                              setParams(prev => ({
                                ...prev,
                                [editingParamKey]: {
                                  ...prev[editingParamKey],
                                  [f.field]: clamped,
                                },
                              }));
                            }}
                          />
                        </label>
                      );
                    })}

                <div className="finance-ind-fill-group">
                  <label className="finance-ind-param-field is-checkbox">
                    <input
                      type="checkbox"
                      checked={editingFill.enabled}
                      onChange={e => updateEditingFill({ enabled: e.target.checked })}
                    />
                    <span>Zone remplie</span>
                  </label>

                  {editingFill.enabled && (
                    <>
                      <label className="finance-ind-param-field">
                        <span>Référence</span>
                        <select
                          value={editingFill.reference}
                          onChange={e =>
                            updateEditingFill({ reference: e.target.value as IndicatorFillReference })
                          }
                        >
                          {editingRefOptions.map(opt => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="finance-ind-param-field is-color" title="Couleur haussière / haute">
                        <span>Haussier</span>
                        <input
                          type="color"
                          value={editingFill.upColor}
                          onChange={e => updateEditingFill({ upColor: e.target.value })}
                        />
                      </label>

                      <label className="finance-ind-param-field is-color" title="Couleur baissière / basse">
                        <span>Baissier</span>
                        <input
                          type="color"
                          value={editingFill.downColor}
                          onChange={e => updateEditingFill({ downColor: e.target.value })}
                        />
                      </label>

                      <label className="finance-ind-param-field is-range">
                        <span>Opacité ({Math.round(editingFill.opacity * 100)}%)</span>
                        <input
                          type="range"
                          min={5}
                          max={65}
                          step={1}
                          value={Math.round(editingFill.opacity * 100)}
                          onChange={e => updateEditingFill({ opacity: Number(e.target.value) / 100 })}
                        />
                      </label>

                      {showFillThresholds && (
                        <>
                          <label className="finance-ind-param-field">
                            <span>Seuil +</span>
                            <input
                              type="number"
                              step="any"
                              value={editingFill.upperThreshold ?? 0}
                              onChange={e => {
                                const val = Number(e.target.value);
                                if (Number.isFinite(val)) updateEditingFill({ upperThreshold: val });
                              }}
                            />
                          </label>
                          <label className="finance-ind-param-field">
                            <span>Seuil -</span>
                            <input
                              type="number"
                              step="any"
                              value={editingFill.lowerThreshold ?? 0}
                              onChange={e => {
                                const val = Number(e.target.value);
                                if (Number.isFinite(val)) updateEditingFill({ lowerThreshold: val });
                              }}
                            />
                          </label>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>
              <div className="finance-ind-params-actions">
                <button
                  type="button"
                  className="finance-tf-btn finance-draw-btn"
                  onClick={() => {
                    if (editingParamKey) {
                      setParams(prev => ({
                        ...prev,
                        [editingParamKey]: DEFAULT_INDICATOR_PARAMS[editingParamKey],
                      }));
                    } else if (editingCustomInd) {
                      setCustomFills(prev => ({
                        ...prev,
                        [editingCustomInd.id]: resolveDefaultCustomFill(
                          editingCustomInd.pane,
                          (editingCustomInd.guide_lines || []).map(g => g.value),
                        ),
                      }));
                    }
                  }}
                  title="Rétablir les valeurs par défaut"
                >
                  <RotateCcw size={11} />
                  <span>Défaut</span>
                </button>
                <button
                  type="button"
                  className="finance-tf-btn finance-draw-btn"
                  onClick={() => {
                    setEditingParamKey(null);
                    setEditingCustomId(null);
                  }}
                  aria-label="Fermer les paramètres"
                >
                  <X size={11} />
                  <span>Fermer</span>
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {customFormulaErrors.length > 0 && (
        <div className="finance-watchlist-error">⚠️ {customFormulaErrors.join(" · ")}</div>
      )}

      <div className="finance-tv-draw-toolbar">
        <small>Dessin</small>
        <button
          type="button"
          className={`finance-tf-btn finance-draw-btn ${tool === "none" ? "active" : ""}`}
          onClick={() => {
            setTool("none");
            setDraft(null);
          }}
          title="Curseur (navigation & sélection)"
        >
          <MousePointer size={11} />
          <span>Curseur</span>
        </button>
        <button
          type="button"
          className={`finance-tf-btn finance-draw-btn ${tool === "line" ? "active" : ""}`}
          onClick={() => {
            setTool("line");
            setDraft(null);
            setSelectedId(null);
          }}
          title="Tracer une ligne (2 clics ou glisser)"
        >
          <TrendingUp size={11} />
          <span>Ligne</span>
        </button>
        <button
          type="button"
          className={`finance-tf-btn finance-draw-btn ${tool === "hline" ? "active" : ""}`}
          onClick={() => {
            setTool("hline");
            setDraft(null);
            setSelectedId(null);
          }}
          title="Tracer une ligne horizontale (1 clic)"
        >
          <Minus size={11} />
          <span>Horizontale</span>
        </button>
        <button
          type="button"
          className={`finance-tf-btn finance-draw-btn ${tool === "rect" ? "active" : ""}`}
          onClick={() => {
            setTool("rect");
            setDraft(null);
            setSelectedId(null);
          }}
          title="Tracer un rectangle (2 clics ou glisser)"
        >
          <Square size={11} />
          <span>Rectangle</span>
        </button>

        <span className="finance-draw-colors" aria-label="Couleur de dessin">
          {DRAWING_COLORS.map(c => (
            <button
              key={c}
              type="button"
              className={`finance-draw-color-dot ${drawColor === c ? "active" : ""}`}
              style={{ background: c }}
              onClick={() => setDrawColor(c)}
              aria-label={`Couleur ${c}`}
            />
          ))}
        </span>

        {selectedId && (
          <button
            type="button"
            className="finance-tf-btn finance-draw-btn is-danger"
            onClick={() => {
              setDrawings(prev => prev.filter(d => d.id !== selectedId));
              setSelectedId(null);
            }}
            title="Supprimer le tracé sélectionné (Suppr)"
          >
            <Trash2 size={11} />
            <span>Supprimer</span>
          </button>
        )}

        {drawings.length > 0 && (
          <button
            type="button"
            className="finance-tf-btn finance-draw-btn"
            onClick={() => {
              setDrawings([]);
              setDraft(null);
              setSelectedId(null);
            }}
            title="Effacer tous les tracés de cette action"
          >
            <Eraser size={11} />
            <span>Effacer ({drawings.length})</span>
          </button>
        )}
      </div>

      {bars.length < 2 ? (
        <div className="finance-chart-empty">Pas assez de données pour cette durée.</div>
      ) : (
        <div
          className="finance-tv-canvas-stage"
          style={
            fullscreen
              ? { flex: 1, minHeight: Math.max(420, 320 + (panes - 1) * 150) }
              : { height: 300 + (panes - 1) * 140 }
          }
        >
          <div ref={containerRef} className="finance-tv-chart" style={{ height: "100%" }} />
          {overlaySize.width > 0 && overlaySize.height > 0 && (
            <svg
              ref={svgRef}
              className={`finance-tv-draw-overlay${tool !== "none" ? " is-drawing" : ""}`}
              width={overlaySize.width}
              height={overlaySize.height}
              viewBox={`0 0 ${overlaySize.width} ${overlaySize.height}`}
              onMouseDown={handleOverlayMouseDown}
              onMouseMove={handleOverlayMouseMove}
              onMouseUp={handleOverlayMouseUp}
            >
              {[...projectedDrawings, ...(projectedDraft ? [projectedDraft] : [])].map(item => {
                const isSelected = item.id === selectedId && !projectedDraft;
                const isDraft = projectedDraft?.id === item.id;
                if (item.type === "rect") {
                  const rx = Math.min(item.x1, item.x2);
                  const ry = Math.min(item.y1, item.y2);
                  const rw = Math.max(1, Math.abs(item.x2 - item.x1));
                  const rh = Math.max(1, Math.abs(item.y2 - item.y1));
                  return (
                    <g key={item.id}>
                      <rect
                        x={rx}
                        y={ry}
                        width={rw}
                        height={rh}
                        fill={item.color}
                        fillOpacity={isSelected ? 0.22 : 0.14}
                        stroke={item.color}
                        strokeWidth={isSelected ? 2.5 : 1.5}
                        strokeDasharray={isDraft ? "5 4" : undefined}
                        className="finance-draw-shape"
                        onMouseDown={e => startShapeDrag(e, item, "move")}
                        onContextMenu={e => {
                          if (tool !== "none") return;
                          e.preventDefault();
                          e.stopPropagation();
                          deleteDrawing(item.id);
                        }}
                      />
                      {isSelected && (
                        <>
                          <circle
                            cx={item.x1}
                            cy={item.y1}
                            r={5}
                            fill="#ffffff"
                            stroke={item.color}
                            strokeWidth={2}
                            className="finance-draw-handle"
                            onMouseDown={e => startShapeDrag(e, item, "p1")}
                          />
                          <circle
                            cx={item.x2}
                            cy={item.y2}
                            r={5}
                            fill="#ffffff"
                            stroke={item.color}
                            strokeWidth={2}
                            className="finance-draw-handle"
                            onMouseDown={e => startShapeDrag(e, item, "p2")}
                          />
                          <g
                            transform={`translate(${rx + rw - 10}, ${Math.max(10, ry - 10)})`}
                            className="finance-draw-delete-badge"
                            onMouseDown={e => e.stopPropagation()}
                            onClick={e => {
                              e.stopPropagation();
                              deleteDrawing(item.id);
                            }}
                          >
                            <circle r={9} fill="#ef4444" stroke="#ffffff" strokeWidth={1.5} />
                            <text x={0} y={3.5} textAnchor="middle" fill="#ffffff" fontSize={11} fontWeight={700}>
                              ×
                            </text>
                          </g>
                        </>
                      )}
                    </g>
                  );
                }

                return (
                  <g
                    key={item.id}
                    className="finance-draw-shape"
                    onMouseDown={e => startShapeDrag(e, item, "move")}
                    onContextMenu={e => {
                      if (tool !== "none") return;
                      e.preventDefault();
                      e.stopPropagation();
                      deleteDrawing(item.id);
                    }}
                  >
                    <line
                      x1={item.x1}
                      y1={item.y1}
                      x2={item.x2}
                      y2={item.y2}
                      stroke="transparent"
                      strokeWidth={12}
                    />
                    <line
                      x1={item.x1}
                      y1={item.y1}
                      x2={item.x2}
                      y2={item.y2}
                      stroke={item.color}
                      strokeWidth={isSelected ? 3 : 2}
                      strokeDasharray={item.type === "hline" ? "6 4" : isDraft ? "5 4" : undefined}
                    />
                    {item.priceLabel && (
                      <g transform={`translate(${Math.max(8, item.x2 - 58)}, ${item.y1 - 18})`}>
                        <rect width={54} height={16} rx={4} fill={item.color} />
                        <text x={27} y={11.5} textAnchor="middle" fill="#ffffff" fontSize={10} fontWeight={700}>
                          {item.priceLabel}
                        </text>
                      </g>
                    )}
                    {isSelected && item.type !== "hline" && (
                      <>
                        <circle
                          cx={item.x1}
                          cy={item.y1}
                          r={5}
                          fill="#ffffff"
                          stroke={item.color}
                          strokeWidth={2}
                          className="finance-draw-handle"
                          onMouseDown={e => startShapeDrag(e, item, "p1")}
                        />
                        <circle
                          cx={item.x2}
                          cy={item.y2}
                          r={5}
                          fill="#ffffff"
                          stroke={item.color}
                          strokeWidth={2}
                          className="finance-draw-handle"
                          onMouseDown={e => startShapeDrag(e, item, "p2")}
                        />
                      </>
                    )}
                    {isSelected && (
                      <g
                        transform={`translate(${
                          item.type === "hline" ? Math.max(24, item.x2 - 74) : (item.x1 + item.x2) / 2
                        }, ${Math.max(12, (item.y1 + item.y2) / 2 - 14)})`}
                        className="finance-draw-delete-badge"
                        onMouseDown={e => e.stopPropagation()}
                        onClick={e => {
                          e.stopPropagation();
                          deleteDrawing(item.id);
                        }}
                      >
                        <circle r={9} fill="#ef4444" stroke="#ffffff" strokeWidth={1.5} />
                        <text x={0} y={3.5} textAnchor="middle" fill="#ffffff" fontSize={11} fontWeight={700}>
                          ×
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>
          )}
        </div>
      )}
    </div>
  );
}
