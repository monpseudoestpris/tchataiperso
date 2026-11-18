"use client";

import { useState } from "react";

import type { DossierMetricRow, FinancialDossier } from "@/lib/api";

type SeriesKind = "bar" | "line";

type ChartSeriesSpec = {
  key: string;
  label: string;
  color: string;
  kind: SeriesKind;
  values: (number | null)[];
};

function findMetricValues(rows: DossierMetricRow[], keys: string[]): (number | null)[] {
  for (const k of keys) {
    const found = rows.find(r => r.key === k);
    if (found && found.values.some(v => v != null)) {
      return found.values;
    }
  }
  return [];
}

function niceBounds(vals: number[]): { min: number; max: number } {
  if (vals.length === 0) return { min: 0, max: 100 };
  let min = Math.min(0, ...vals);
  let max = Math.max(0, ...vals);
  if (min === max) {
    max = min === 0 ? 10 : min * 1.2;
  }
  const pad = (max - min) * 0.14;
  if (min < 0) min -= pad * 0.5;
  max += pad;
  return { min, max };
}

function fmtChartValue(v: number | null, unit: "mln" | "pct" | "days", currency = "USD"): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (unit === "pct") {
    return `${v.toLocaleString("fr-FR", { maximumFractionDigits: 1 })}%`;
  }
  if (unit === "days") {
    return `${Math.round(v)} j`;
  }
  const mln = Math.round(v / 1e6).toLocaleString("fr-FR");
  return `${mln} M ${currency}`;
}

function fmtShortPointLabel(v: number, unit: "mln" | "pct" | "days"): string {
  if (unit === "pct") return `${Math.round(v)}%`;
  if (unit === "days") return `${Math.round(v)}`;
  const mln = v / 1e6;
  if (Math.abs(mln) >= 1000) return `${Math.round(mln).toLocaleString("fr-FR")}`;
  return `${Math.round(mln)}`;
}

/** Graphique en barres des performances boursières ajustées (1 an à 10 ans). */
export function DividendPerfBarChart({
  title,
  horizons,
}: {
  title: string;
  horizons: { key: string; label: string; pct: number | null }[];
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const annualHorizons = horizons.filter(h => /^\d+y$/.test(h.key) && h.pct != null);
  if (annualHorizons.length < 2) return null;

  const w = 780;
  const h = 230;
  const padL = 22;
  const padR = 64;
  const padT = 26;
  const padB = 34;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const pcts = annualHorizons.map(item => item.pct as number);
  const { min, max } = niceBounds(pcts);
  const span = max - min || 1;
  const zeroY = padT + ((max - 0) / span) * plotH;
  const step = plotW / annualHorizons.length;
  const barW = Math.min(54, Math.max(18, step * 0.68));
  const ticks = 4;

  const active = hoverIdx != null && annualHorizons[hoverIdx] ? annualHorizons[hoverIdx] : null;
  const activeBarY =
    active && active.pct != null ? padT + ((max - active.pct) / span) * plotH : null;

  return (
    <div className="finance-ih-chart-card">
      <div className="finance-ih-card-head">
        <strong>{title}</strong>
      </div>
      <div className="finance-ih-chart-body">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          className="finance-ih-svg"
          role="img"
          aria-label={title}
          onMouseLeave={() => setHoverIdx(null)}
        >
          {Array.from({ length: ticks + 1 }).map((_, idx) => {
            const val = min + ((max - min) * idx) / ticks;
            const y = padT + ((max - val) / span) * plotH;
            return (
              <g key={idx}>
                <line x1={padL} y1={y} x2={w - padR} y2={y} className="finance-ih-gridline" />
                <text x={w - padR + 6} y={y + 4} className="finance-ih-axis-text">
                  {Math.round(val).toLocaleString("fr-FR")}%
                </text>
              </g>
            );
          })}
          <line x1={padL} y1={zeroY} x2={w - padR} y2={zeroY} className="finance-ih-zeroline" />

          {annualHorizons.map((item, idx) => {
            const val = item.pct as number;
            const xCenter = padL + idx * step + step / 2;
            const yVal = padT + ((max - val) / span) * plotH;
            const yTop = Math.min(yVal, zeroY);
            const barH = Math.max(2, Math.abs(zeroY - yVal));
            const isPos = val >= 0;
            const fill = isPos ? "#8eb845" : "#e11d48";
            const labelY = isPos ? Math.max(padT - 6, yTop - 6) : Math.min(h - padB + 12, yTop + barH + 12);
            return (
              <g key={item.key} onMouseEnter={() => setHoverIdx(idx)} style={{ cursor: "crosshair" }}>
                <rect
                  x={padL + idx * step}
                  y={padT}
                  width={step}
                  height={plotH}
                  fill="transparent"
                />
                <rect
                  x={xCenter - barW / 2}
                  y={yTop}
                  width={barW}
                  height={barH}
                  rx={2}
                  fill={fill}
                  opacity={hoverIdx === null || hoverIdx === idx ? 0.92 : 0.65}
                />
                <text
                  x={xCenter}
                  y={labelY}
                  textAnchor="middle"
                  className={`finance-ih-point-label ${isPos ? "is-pos" : "is-neg"}`}
                >
                  {Math.round(val).toLocaleString("fr-FR")}%
                </text>
                <text x={xCenter} y={h - 10} textAnchor="middle" className="finance-ih-axis-text">
                  {item.label}
                </text>
              </g>
            );
          })}

          {hoverIdx != null && active && activeBarY != null && (
            <g pointerEvents="none">
              <line
                x1={padL + hoverIdx * step + step / 2}
                y1={padT}
                x2={padL + hoverIdx * step + step / 2}
                y2={h - padB}
                className="finance-ih-crosshair"
              />
              <line
                x1={padL}
                y1={activeBarY}
                x2={w - padR}
                y2={activeBarY}
                className="finance-ih-crosshair"
              />
              <rect
                x={w - padR + 2}
                y={activeBarY - 9}
                width={58}
                height={18}
                rx={4}
                className="finance-ih-crosshair-badge"
              />
              <text x={w - padR + 31} y={activeBarY + 3} textAnchor="middle" className="finance-ih-crosshair-badge-text">
                {active.pct != null ? `${active.pct >= 0 ? "+" : ""}${active.pct.toFixed(1)}%` : "—"}
              </text>
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

/** Moteur SVG générique pour les graphiques multi-séries annuels du dossier. */
function MultiSeriesAnnualChart({
  title,
  years,
  series,
  unit,
  currency = "USD",
  showPointLabels = false,
}: {
  title: string;
  years: string[];
  series: ChartSeriesSpec[];
  unit: "mln" | "pct" | "days";
  currency?: string;
  showPointLabels?: boolean;
}) {
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const nonEmptySeries = series.filter(s => s.values.some(v => v != null));
  if (years.length < 2 || nonEmptySeries.length === 0) return null;

  const activeSeries = nonEmptySeries.filter(s => !hidden[s.key]);
  const allVals = activeSeries.flatMap(s => s.values.filter((v): v is number => v != null));
  const { min, max } = niceBounds(allVals);
  const span = max - min || 1;

  const w = 780;
  const h = 240;
  const padL = 22;
  const padR = unit === "mln" ? 78 : 54;
  const padT = 26;
  const padB = 34;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;
  const zeroY = padT + ((max - 0) / span) * plotH;
  const step = plotW / years.length;

  const barSeries = activeSeries.filter(s => s.kind === "bar");
  const lineSeries = activeSeries.filter(s => s.kind === "line");
  const ticks = 4;
  const labelStride = years.length > 14 ? 2 : 1;

  function toggleSeries(key: string) {
    setHidden(prev => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="finance-ih-chart-card">
      <div className="finance-ih-card-head">
        <strong>{title}</strong>
      </div>
      <div className="finance-ih-chart-body">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          className="finance-ih-svg"
          role="img"
          aria-label={title}
          onMouseLeave={() => setHoverIdx(null)}
        >
          {Array.from({ length: ticks + 1 }).map((_, idx) => {
            const val = min + ((max - min) * idx) / ticks;
            const y = padT + ((max - val) / span) * plotH;
            return (
              <g key={idx}>
                <line x1={padL} y1={y} x2={w - padR} y2={y} className="finance-ih-gridline" />
                <text x={w - padR + 6} y={y + 4} className="finance-ih-axis-text">
                  {fmtShortPointLabel(val, unit)}
                  {unit === "pct" ? "%" : unit === "mln" ? " M" : ""}
                </text>
              </g>
            );
          })}
          <line x1={padL} y1={zeroY} x2={w - padR} y2={zeroY} className="finance-ih-zeroline" />

          {/* Barres éventuelles (ex. CA ou Dividendes) */}
          {barSeries.map((s, bIdx) => {
            const groupW = Math.min(44, step * 0.62);
            const singleW = Math.max(8, groupW / Math.max(1, barSeries.length));
            return (
              <g key={s.key}>
                {years.map((yr, i) => {
                  const val = s.values[i];
                  if (val == null) return null;
                  const xCenter = padL + i * step + step / 2;
                  const offset = (bIdx - (barSeries.length - 1) / 2) * singleW;
                  const yVal = padT + ((max - val) / span) * plotH;
                  const yTop = Math.min(yVal, zeroY);
                  const bh = Math.max(2, Math.abs(zeroY - yVal));
                  return (
                    <rect
                      key={`${s.key}-${yr}-${i}`}
                      x={xCenter + offset - singleW / 2}
                      y={yTop}
                      width={singleW}
                      height={bh}
                      rx={2}
                      fill={s.color}
                      opacity={0.28}
                    />
                  );
                })}
              </g>
            );
          })}

          {/* Courbes */}
          {lineSeries.map(s => {
            const pts = years
              .map((yr, i) => {
                const v = s.values[i];
                if (v == null) return null;
                const x = padL + i * step + step / 2;
                const y = padT + ((max - v) / span) * plotH;
                return { x, y, v, yr, i };
              })
              .filter((p): p is { x: number; y: number; v: number; yr: string; i: number } => p !== null);
            if (pts.length === 0) return null;
            const pathD = pts.map((p, idx) => `${idx === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
            return (
              <g key={s.key}>
                <path d={pathD} fill="none" stroke={s.color} strokeWidth={2.2} strokeLinejoin="round" />
                {pts.map(p => (
                  <g key={`${s.key}-pt-${p.i}`}>
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={hoverIdx === p.i ? 4.8 : 3.2}
                      fill={s.color}
                      stroke="#ffffff"
                      strokeWidth={1.2}
                    />
                    {showPointLabels && p.i % labelStride === 0 && (
                      <text
                        x={p.x}
                        y={p.y - 7}
                        textAnchor="middle"
                        className="finance-ih-point-label"
                      >
                        {fmtShortPointLabel(p.v, unit)}
                      </text>
                    )}
                  </g>
                ))}
              </g>
            );
          })}

          {/* Axes X + zones interactives */}
          {years.map((yr, i) => {
            const xCenter = padL + i * step + step / 2;
            return (
              <g key={`x-${yr}-${i}`} onMouseEnter={() => setHoverIdx(i)} style={{ cursor: "crosshair" }}>
                <rect x={padL + i * step} y={padT} width={step} height={plotH} fill="transparent" />
                {(years.length <= 15 || i % 2 === 0 || i === years.length - 1) && (
                  <text
                    x={xCenter}
                    y={h - 10}
                    textAnchor="middle"
                    className={`finance-ih-axis-text ${hoverIdx === i ? "is-active" : ""}`}
                  >
                    {yr}
                  </text>
                )}
              </g>
            );
          })}

          {/* Réticule + info-bulle flottante façon Investisseurs Heureux */}
          {hoverIdx != null && years[hoverIdx] && (() => {
            const x = padL + hoverIdx * step + step / 2;
            const boxW = 195;
            const boxH = 24 + activeSeries.length * 16;
            const boxX = x > w * 0.58 ? x - boxW - 12 : x + 12;
            const boxY = padT + 4;
            return (
              <g pointerEvents="none">
                <line x1={x} y1={padT} x2={x} y2={h - padB} className="finance-ih-crosshair" />
                <rect
                  x={boxX}
                  y={boxY}
                  width={boxW}
                  height={boxH}
                  rx={6}
                  className="finance-ih-tooltip-box"
                />
                <text x={boxX + 9} y={boxY + 15} className="finance-ih-tooltip-title">
                  Exercice fiscal : {years[hoverIdx]}
                </text>
                {activeSeries.map((s, sIdx) => (
                  <text
                    key={`tt-${s.key}`}
                    x={boxX + 9}
                    y={boxY + 31 + sIdx * 16}
                    className="finance-ih-tooltip-row"
                    fill={s.color}
                  >
                    {s.label} : {fmtChartValue(s.values[hoverIdx] ?? null, unit, currency)}
                  </text>
                ))}
              </g>
            );
          })()}
        </svg>

        <div className="finance-ih-legend">
          {nonEmptySeries.map(s => {
            const isOff = Boolean(hidden[s.key]);
            return (
              <button
                key={s.key}
                type="button"
                className={`finance-ih-legend-btn ${isOff ? "is-muted" : ""}`}
                onClick={() => toggleSeries(s.key)}
              >
                <span className="finance-ih-legend-dot" style={{ background: s.color }} />
                <span>{s.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** Graphique des profits et résultats (CA, Résultat opérationnel, Résultat net, FCF). */
export function ProfitsResultsChart({ dossier }: { dossier: FinancialDossier }) {
  const tbl = dossier.annual_tables;
  const rows = tbl.summary || [];
  const name = dossier.header?.name || dossier.symbol;
  const series: ChartSeriesSpec[] = [
    {
      key: "rev",
      label: "Chiffre d'affaires",
      color: "#0284c7",
      kind: "bar",
      values: findMetricValues(rows, ["rev"]),
    },
    {
      key: "opinc",
      label: "Résultat opérationnel",
      color: "#6366f1",
      kind: "line",
      values: findMetricValues(rows, ["opinc"]),
    },
    {
      key: "ni",
      label: "Résultat net",
      color: "#f59e0b",
      kind: "line",
      values: findMetricValues(rows, ["ni"]),
    },
    {
      key: "fcf",
      label: "Flux de trésorerie (FCF)",
      color: "#10b981",
      kind: "line",
      values: findMetricValues(rows, ["fcf"]),
    },
  ];
  return (
    <MultiSeriesAnnualChart
      title={`Graphique des profits et résultats de ${name}`}
      years={tbl.years || []}
      series={series}
      unit="mln"
      currency={dossier.currency}
    />
  );
}

/** Graphique de la rentabilité et des marges (Marge op., Marge nette, Marge FCF). */
export function ProfitabilityMarginsChart({ dossier }: { dossier: FinancialDossier }) {
  const tbl = dossier.annual_tables;
  const rows = tbl.profitability || [];
  const name = dossier.header?.name || dossier.symbol;
  const series: ChartSeriesSpec[] = [
    {
      key: "op_m",
      label: "Marge opérationnelle",
      color: "#2563eb",
      kind: "line",
      values: findMetricValues(rows, ["op_m"]),
    },
    {
      key: "net_m",
      label: "Marge bénéficiaire",
      color: "#dc2626",
      kind: "line",
      values: findMetricValues(rows, ["net_m"]),
    },
    {
      key: "fcf_m",
      label: "Marge de flux de trésorerie",
      color: "#16a34a",
      kind: "line",
      values: findMetricValues(rows, ["fcf_m"]),
    },
  ];
  return (
    <MultiSeriesAnnualChart
      title={`Graphique de la rentabilité et des marges de ${name}`}
      years={tbl.years || []}
      series={series}
      unit="pct"
      showPointLabels
    />
  );
}

/** Graphique des dividendes vs résultat net et flux de trésorerie libre. */
export function DividendsHistoryChart({ dossier }: { dossier: FinancialDossier }) {
  const tbl = dossier.annual_tables;
  const rows = tbl.distribution || [];
  const name = dossier.header?.name || dossier.symbol;
  const rawDiv = findMetricValues(rows, ["div_paid"]);
  const absDiv = rawDiv.map(v => (v != null ? Math.abs(v) : null));
  const series: ChartSeriesSpec[] = [
    {
      key: "div_paid",
      label: "Dividendes",
      color: "#2563eb",
      kind: "bar",
      values: absDiv,
    },
    {
      key: "ni",
      label: "Résultat net",
      color: "#dc2626",
      kind: "line",
      values: findMetricValues(rows, ["ni"]),
    },
    {
      key: "fcf",
      label: "Flux de trésorerie",
      color: "#16a34a",
      kind: "line",
      values: findMetricValues(rows, ["fcf"]),
    },
  ];
  return (
    <MultiSeriesAnnualChart
      title={`Graphique des dividendes de ${name}`}
      years={tbl.years || []}
      series={series}
      unit="mln"
      currency={dossier.currency}
    />
  );
}

/** Graphique du cycle de conversion de trésorerie (DSI, DSO, DPO). */
export function CashConversionChart({ dossier }: { dossier: FinancialDossier }) {
  const tbl = dossier.annual_tables;
  const rows = tbl.efficiency || [];
  const name = dossier.header?.name || dossier.symbol;
  const series: ChartSeriesSpec[] = [
    {
      key: "dsi",
      label: "DSI",
      color: "#2563eb",
      kind: "line",
      values: findMetricValues(rows, ["dsi"]),
    },
    {
      key: "dso",
      label: "DSO",
      color: "#dc2626",
      kind: "line",
      values: findMetricValues(rows, ["dso"]),
    },
    {
      key: "dpo",
      label: "DPO",
      color: "#16a34a",
      kind: "line",
      values: findMetricValues(rows, ["dpo"]),
    },
  ];
  return (
    <MultiSeriesAnnualChart
      title={`Graphique du cycle de conversion de trésorerie de ${name}`}
      years={tbl.years || []}
      series={series}
      unit="days"
      showPointLabels
    />
  );
}
