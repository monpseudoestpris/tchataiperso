import type { EodBar } from "@/lib/api";

export type DrawingTool = "none" | "line" | "hline" | "rect";

export type ChartDrawing = {
  id: string;
  type: "line" | "hline" | "rect";
  color: string;
  /** Date ISO ("YYYY-MM-DD" ou "YYYY-MM-DD HH:MM") du 1er point */
  t1: string;
  p1: number;
  /** Date ISO du 2e point (identique à t1 pour hline) */
  t2: string;
  p2: number;
};

export const DRAWING_COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
];

function storageKey(symbol: string): string {
  return `clair_finance_drawings_${symbol.toUpperCase()}`;
}

export function loadChartDrawings(symbol?: string): ChartDrawing[] {
  if (!symbol || typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey(symbol));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveChartDrawings(symbol: string | undefined, drawings: ChartDrawing[]): void {
  if (!symbol || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(symbol), JSON.stringify(drawings));
  } catch {
    // Ignore storage quota errors
  }
}

/**
 * Convertit une date de dessin en index logique dans `rows` (exact ou interpolé par recherche binaire).
 */
export function dateToLogicalIndex(rows: EodBar[], dateStr: string): number | null {
  if (rows.length === 0) return null;
  // Exact match fast path
  const exact = rows.findIndex(r => r.date === dateStr);
  if (exact !== -1) return exact;

  // Binary search for closest position so drawings stay visible across timeframes
  let lo = 0;
  let hi = rows.length - 1;
  if (dateStr <= rows[0].date) return 0;
  if (dateStr >= rows[hi].date) return hi;

  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].date === dateStr) return mid;
    if (rows[mid].date < dateStr) lo = mid + 1;
    else hi = mid - 1;
  }
  return Math.max(0, Math.min(rows.length - 1, lo - 0.5));
}
