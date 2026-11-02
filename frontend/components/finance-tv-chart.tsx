"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { EodBar } from "@/lib/api";
import {
  adx,
  atr,
  bollinger,
  cci,
  ema,
  macd,
  obv,
  parabolicSar,
  roc,
  rsi,
  sma,
  stochastic,
  vwap,
  williamsR,
  type Num,
} from "@/lib/indicators";

type IndicatorKey =
  | "sma20" | "sma50" | "sma200" | "ema20" | "ema50" | "boll" | "vwap" | "sar" | "volume"
  | "rsi" | "macd" | "stoch" | "willr" | "cci" | "roc" | "atr" | "adx" | "obv";

const OVERLAYS: { key: IndicatorKey; label: string }[] = [
  { key: "sma20", label: "SMA 20" },
  { key: "sma50", label: "SMA 50" },
  { key: "sma200", label: "SMA 200" },
  { key: "ema20", label: "EMA 20" },
  { key: "ema50", label: "EMA 50" },
  { key: "boll", label: "Bollinger" },
  { key: "vwap", label: "VWAP" },
  { key: "sar", label: "SAR" },
  { key: "volume", label: "Volume" },
];

const OSCILLATORS: { key: IndicatorKey; label: string }[] = [
  { key: "rsi", label: "RSI 14" },
  { key: "macd", label: "MACD" },
  { key: "stoch", label: "Stoch." },
  { key: "willr", label: "Williams %R" },
  { key: "cci", label: "CCI 20" },
  { key: "roc", label: "ROC 12" },
  { key: "atr", label: "ATR 14" },
  { key: "adx", label: "ADX 14" },
  { key: "obv", label: "OBV" },
];

const OSCILLATOR_KEYS = OSCILLATORS.map(o => o.key);

/** "YYYY-MM-DD" reste une date métier ; "YYYY-MM-DD HH:MM" (intraday) devient un timestamp UTC. */
function toTime(date: string): Time {
  if (date.length <= 10) return date;
  return (Date.parse(date.replace(" ", "T") + ":00Z") / 1000) as UTCTimestamp;
}

function pick(times: Time[], values: Num[]) {
  return values.flatMap((v, i) => (v == null ? [] : [{ time: times[i], value: v }]));
}

/** Graphique en chandeliers (TradingView lightweight-charts) avec indicateurs techniques. */
export function FinanceTvChart({ bars, dark }: { bars: EodBar[]; dark: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [active, setActive] = useState<Set<IndicatorKey>>(new Set(["sma20", "volume", "rsi"]));

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const rows = bars.filter(
      b => b.close != null && b.open != null && b.high != null && b.low != null,
    );
    const times = rows.map(b => toTime(b.date));
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

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#f43f5e",
      borderVisible: false,
      wickUpColor: "#10b981",
      wickDownColor: "#f43f5e",
    });
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

    if (active.has("sma20")) addLine(sma(closes, 20), "#3b82f6");
    if (active.has("sma50")) addLine(sma(closes, 50), "#f59e0b");
    if (active.has("sma200")) addLine(sma(closes, 200), "#ef4444");
    if (active.has("ema20")) addLine(ema(closes, 20), "#a855f7");
    if (active.has("ema50")) addLine(ema(closes, 50), "#ec4899");
    if (active.has("vwap")) {
      addLine(vwap(highs, lows, closes, volumes, rows.map(b => b.date.slice(0, 10))), "#0ea5e9");
    }
    if (active.has("sar")) {
      const sar = chart.addSeries(LineSeries, {
        color: "#f97316",
        lineVisible: false,
        pointMarkersVisible: true,
        pointMarkersRadius: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      sar.setData(pick(times, parabolicSar(highs, lows)));
    }
    if (active.has("boll")) {
      const b = bollinger(closes);
      addLine(b.upper, "#94a3b8");
      addLine(b.mid, "#64748b");
      addLine(b.lower, "#94a3b8");
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

    let pane = 1;
    const guides = (line: ReturnType<typeof addLine>, levels: [number, string][]) =>
      levels.forEach(([price, color]) =>
        line.createPriceLine({ price, color, lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" }),
      );
    // Un panneau dédié par oscillateur actif, dans l'ordre de la barre d'outils.
    for (const key of OSCILLATOR_KEYS) {
      if (!active.has(key)) continue;
      if (key === "rsi") {
        guides(addLine(rsi(closes, 14), "#8b5cf6", pane, "RSI 14"), [[70, "#f43f5e"], [30, "#10b981"]]);
      } else if (key === "macd") {
        const m = macd(closes);
        const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
        hist.setData(
          m.hist.flatMap((v, i) =>
            v == null ? [] : [{ time: times[i], value: v, color: v >= 0 ? "#10b98199" : "#f43f5e99" }],
          ),
        );
        addLine(m.line, "#3b82f6", pane, "MACD");
        addLine(m.signal, "#f59e0b", pane, "Signal");
      } else if (key === "stoch") {
        const st = stochastic(highs, lows, closes);
        guides(addLine(st.k, "#3b82f6", pane, "%K"), [[80, "#f43f5e"], [20, "#10b981"]]);
        addLine(st.d, "#f59e0b", pane, "%D");
      } else if (key === "willr") {
        guides(addLine(williamsR(highs, lows, closes), "#14b8a6", pane, "%R"), [[-20, "#f43f5e"], [-80, "#10b981"]]);
      } else if (key === "cci") {
        guides(addLine(cci(highs, lows, closes), "#6366f1", pane, "CCI"), [[100, "#f43f5e"], [-100, "#10b981"]]);
      } else if (key === "roc") {
        guides(addLine(roc(closes), "#0ea5e9", pane, "ROC"), [[0, "#94a3b8"]]);
      } else if (key === "atr") {
        addLine(atr(highs, lows, closes), "#f97316", pane, "ATR");
      } else if (key === "adx") {
        const a = adx(highs, lows, closes);
        guides(addLine(a.adx, "#0f172a", pane, "ADX"), [[25, "#94a3b8"]]);
        addLine(a.plusDi, "#10b981", pane, "+DI");
        addLine(a.minusDi, "#f43f5e", pane, "-DI");
      } else if (key === "obv") {
        addLine(obv(closes, volumes), "#a855f7", pane, "OBV");
      }
      pane++;
    }

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, active, dark]);

  function toggle(key: IndicatorKey) {
    setActive(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const panes = 1 + OSCILLATOR_KEYS.filter(k => active.has(k)).length;
  return (
    <div className="finance-tv-wrap">
      {[
        ["Tendance & prix", OVERLAYS],
        ["Oscillateurs", OSCILLATORS],
      ].map(([title, list]) => (
        <div key={title as string} className="finance-tv-toolbar">
          <small>{title as string}</small>
          {(list as typeof OVERLAYS).map(i => (
            <button
              key={i.key}
              type="button"
              className={`finance-tf-btn ${active.has(i.key) ? "active" : ""}`}
              onClick={() => toggle(i.key)}
            >
              {i.label}
            </button>
          ))}
        </div>
      ))}
      {bars.length < 2 ? (
        <div className="finance-chart-empty">Pas assez de données pour cette durée.</div>
      ) : (
        <div ref={containerRef} className="finance-tv-chart" style={{ height: 300 + (panes - 1) * 140 }} />
      )}
    </div>
  );
}
