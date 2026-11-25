import type { EodBar } from "./api";

export type BarInterval = "day" | "week" | "month" | "quarter";

export const BAR_INTERVAL_LABELS: Record<BarInterval, string> = {
  day: "Jour",
  week: "Semaine",
  month: "Mois",
  quarter: "3 Mois",
};

export function getBucketKey(dateStr: string, interval: Exclude<BarInterval, "day">): string {
  const dayPart = dateStr.slice(0, 10);
  const [yStr, mStr, dStr] = dayPart.split("-");
  const y = Number(yStr);
  const m = Number(mStr);
  const d = Number(dStr);
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) {
    return dayPart;
  }

  if (interval === "month") {
    return `${yStr}-${mStr}`;
  }
  if (interval === "quarter") {
    const q = Math.floor((m - 1) / 3) + 1;
    return `${yStr}-Q${q}`;
  }

  // Semaine ISO (lundi -> dimanche) en UTC pour éviter tout décalage horaire local.
  const utc = new Date(Date.UTC(y, m - 1, d));
  const mondayOffset = (utc.getUTCDay() + 6) % 7;
  utc.setUTCDate(utc.getUTCDate() - mondayOffset);
  return utc.toISOString().slice(0, 10);
}

/**
 * Agrège une série chronologique de barres OHLCV selon l'unité demandée
 * (jour, semaine, mois ou 3 mois / trimestre).
 */
export function aggregateBars(bars: EodBar[], interval: BarInterval): EodBar[] {
  if (interval === "day" || bars.length === 0) return bars;

  const out: EodBar[] = [];
  let currentKey: string | null = null;
  let acc: EodBar | null = null;

  for (const bar of bars) {
    const key = getBucketKey(bar.date, interval);
    const barOpen = bar.open ?? bar.close;
    const barHigh = bar.high ?? bar.close ?? bar.open;
    const barLow = bar.low ?? bar.close ?? bar.open;
    const barClose = bar.close ?? bar.open;
    const datePart = bar.date.slice(0, 10);

    if (key !== currentKey || !acc) {
      if (acc) out.push(acc);
      currentKey = key;
      acc = {
        date: datePart,
        open: barOpen,
        high: barHigh,
        low: barLow,
        close: barClose,
        volume: bar.volume,
      };
      continue;
    }

    acc.date = datePart;
    if (acc.open == null && barOpen != null) acc.open = barOpen;
    if (barHigh != null) acc.high = acc.high == null ? barHigh : Math.max(acc.high, barHigh);
    if (barLow != null) acc.low = acc.low == null ? barLow : Math.min(acc.low, barLow);
    if (barClose != null) acc.close = barClose;
    if (bar.volume != null) acc.volume = (acc.volume ?? 0) + bar.volume;
  }

  if (acc) out.push(acc);
  return out;
}
