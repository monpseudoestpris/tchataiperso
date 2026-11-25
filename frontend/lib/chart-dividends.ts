/**
 * Projection & mise en forme des versements de dividendes sur une courbe boursière
 * (compatible Jour / Semaine / Mois / 3 Mois et intraday).
 */

import type { EodBar } from "./api";
import { getBucketKey, type BarInterval } from "./bar-aggregation";
import type { StockDividendItem } from "./finance-api";
import type { ChartMarkerOverlay } from "./finance-game-helpers";

export type ProjectedBarDividend = {
  barDate: string;
  barIndex: number;
  totalAmount: number;
  currency: string;
  yieldPct: number | null;
  events: StockDividendItem[];
};

const MAX_LABELED_MARKERS = 16;
const DAY_SNAP_TOLERANCE_DAYS = 5;

function parseIsoDayMs(isoDay: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDay);
  if (!m) return null;
  const ms = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isFinite(ms) ? ms : null;
}

/**
 * Associe chaque versement de dividende à la barre correspondante de la série affichée.
 * Agrège automatiquement si plusieurs versements tombent dans le même bucket (ex. 3 Mois).
 */
export function projectDividendsToBars(
  bars: EodBar[],
  dividends: StockDividendItem[],
  interval: BarInterval,
  fallbackCurrency = "",
): ProjectedBarDividend[] {
  if (bars.length === 0 || dividends.length === 0) return [];

  const firstDay = bars[0].date.slice(0, 10);
  const lastDay = bars[bars.length - 1].date.slice(0, 10);
  const firstMs = parseIsoDayMs(firstDay);
  const lastMs = parseIsoDayMs(lastDay);
  if (firstMs == null || lastMs == null) return [];

  const isIntraday = bars[0].date.length > 10;
  const fallbackCurr = fallbackCurrency.trim().toUpperCase();

  // Indexation des barres par date exacte (YYYY-MM-DD) ou clé de bucket agrégé
  const barIndexByDay = new Map<string, number>();
  const barIndexByBucket = new Map<string, number>();
  const barDaysMs: { index: number; dayMs: number }[] = [];

  for (let i = 0; i < bars.length; i += 1) {
    const dayStr = bars[i].date.slice(0, 10);
    if (!barIndexByDay.has(dayStr)) {
      barIndexByDay.set(dayStr, i);
      const dayMs = parseIsoDayMs(dayStr);
      if (dayMs != null) {
        barDaysMs.push({ index: i, dayMs });
      }
    }
    if (interval !== "day" && !isIntraday) {
      const bucket = getBucketKey(dayStr, interval);
      barIndexByBucket.set(bucket, i);
    }
  }

  const groupedByBarIndex = new Map<number, StockDividendItem[]>();
  const toleranceMs = DAY_SNAP_TOLERANCE_DAYS * 86_400_000;

  for (const div of dividends) {
    if (!div || !div.date || !Number.isFinite(div.value) || div.value <= 0) continue;
    const divDay = div.date.slice(0, 10);
    const divMs = parseIsoDayMs(divDay);
    if (divMs == null) continue;

    let targetIndex: number | undefined;

    if (interval !== "day" && !isIntraday) {
      const bucket = getBucketKey(divDay, interval);
      targetIndex = barIndexByBucket.get(bucket);
    } else {
      // Hors fenêtre visible (avec marge de tolérance uniquement si la barre cible est dans la fenêtre)
      if (divMs < firstMs - toleranceMs || divMs > lastMs) continue;
      targetIndex = barIndexByDay.get(divDay);
      if (targetIndex === undefined && !isIntraday) {
        // Si le détachement tombe un week-end/férié, rattacher à la 1re séance suivante <= 5 jours
        for (const entry of barDaysMs) {
          if (entry.dayMs >= divMs && entry.dayMs - divMs <= toleranceMs) {
            targetIndex = entry.index;
            break;
          }
          if (entry.dayMs > divMs + toleranceMs) break;
        }
      }
    }

    if (targetIndex === undefined) continue;
    const list = groupedByBarIndex.get(targetIndex);
    if (list) {
      list.push(div);
    } else {
      groupedByBarIndex.set(targetIndex, [div]);
    }
  }

  const projected: ProjectedBarDividend[] = [];
  const sortedIndices = Array.from(groupedByBarIndex.keys()).sort((a, b) => a - b);

  for (const barIndex of sortedIndices) {
    const events = groupedByBarIndex.get(barIndex)!;
    const bar = bars[barIndex];
    const totalAmount = Number(
      events.reduce((acc, ev) => acc + ev.value, 0).toFixed(4),
    );
    const currency =
      events.find(ev => ev.currency && ev.currency.trim())?.currency?.trim().toUpperCase() ||
      fallbackCurr;
    const closePrice = bar.close;
    const yieldPct =
      closePrice != null && Number.isFinite(closePrice) && closePrice > 0
        ? Number(((totalAmount / closePrice) * 100).toFixed(2))
        : null;

    projected.push({
      barDate: bar.date,
      barIndex,
      totalAmount,
      currency,
      yieldPct,
      events,
    });
  }

  return projected;
}

export function formatDividendAmount(value: number, currency?: string): string {
  const digits = value >= 10 ? 2 : value >= 1 ? 2 : 3;
  const formatted = value.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: digits,
  });
  return currency ? `${formatted} ${currency}` : formatted;
}

/**
 * Construit les marqueurs TradingView (`lightweight-charts` v5) pour les dividendes projetés.
 * Bascule automatiquement vers un marqueur compact "D" au-delà de 16 versements visibles.
 */
export function buildDividendChartMarkers(
  projected: ProjectedBarDividend[],
  dark: boolean,
): ChartMarkerOverlay[] {
  if (projected.length === 0) return [];
  const compact = projected.length > MAX_LABELED_MARKERS;
  const color = dark ? "#f59e0b" : "#b45309";

  return projected.map(item => ({
    time: item.barDate,
    position: "belowBar",
    shape: "circle",
    color,
    text: compact ? "D" : `D ${formatDividendAmount(item.totalAmount)}`,
  }));
}

/** Résumé lisible (une ligne) d'un versement ou groupe de versements sur une bougie. */
export function formatDividendHoverSummary(item: ProjectedBarDividend): string {
  const amountStr = formatDividendAmount(item.totalAmount, item.currency);
  const yieldStr = item.yieldPct != null ? ` (${item.yieldPct.toFixed(2)} %)` : "";
  if (item.events.length === 1) {
    const ev = item.events[0];
    const unadjNote =
      ev.unadjusted != null && Math.abs(ev.unadjusted - ev.value) > 0.005
        ? ` · brut ${formatDividendAmount(ev.unadjusted, item.currency)}`
        : "";
    return `Dividende ${ev.date} : ${amountStr}${yieldStr}${unadjNote}`;
  }
  const dates = item.events.map(ev => ev.date).join(", ");
  return `${item.events.length} dividendes (${dates}) : ${amountStr}${yieldStr}`;
}
