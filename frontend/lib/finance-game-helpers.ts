/** Helpers purs pour le jeu « Trading Replay » (formatage, SL/TP rapides, overlays graphique). */

import type { GameHorizon, GamePositionSide, GameRoundView, GameTimeframe } from "./finance-game-api";

export type HorizonOption = {
  value: GameHorizon;
  label: string;
};

export const HORIZONS_BY_TIMEFRAME: Record<GameTimeframe, HorizonOption[]> = {
  day: [
    { value: "1w", label: "1 sem" },
    { value: "1m", label: "1 mois" },
    { value: "3m", label: "3 mois" },
    { value: "6m", label: "6 mois" },
    { value: "1y", label: "1 an" },
  ],
  week: [
    { value: "1m", label: "1 mois" },
    { value: "3m", label: "3 mois" },
    { value: "6m", label: "6 mois" },
    { value: "1y", label: "1 an" },
    { value: "2y", label: "2 ans" },
    { value: "3y", label: "3 ans" },
    { value: "5y", label: "5 ans" },
  ],
  month: [
    { value: "6m", label: "6 mois" },
    { value: "1y", label: "1 an" },
    { value: "2y", label: "2 ans" },
    { value: "3y", label: "3 ans" },
    { value: "5y", label: "5 ans" },
  ],
};

export const DEFAULT_HORIZON_BY_TIMEFRAME: Record<GameTimeframe, GameHorizon> = {
  day: "3m",
  week: "1y",
  month: "2y",
};

export function resolveHorizonForTimeframe(
  timeframe: GameTimeframe,
  currentHorizon: GameHorizon,
): GameHorizon {
  const allowed = HORIZONS_BY_TIMEFRAME[timeframe];
  if (allowed.some(opt => opt.value === currentHorizon)) {
    return currentHorizon;
  }
  return DEFAULT_HORIZON_BY_TIMEFRAME[timeframe];
}

export type ChartPriceLineOverlay = {
  price: number;
  color: string;
  title: string;
  lineStyle?: number;
};

export type ChartMarkerOverlay = {
  time: string;
  position: "aboveBar" | "belowBar" | "inBar";
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  color: string;
  text: string;
};

export function formatRelativeSessionLabel(
  index: number,
  cutoffIndex: number,
  timeframe: GameTimeframe,
): string {
  const delta = index - cutoffIndex;
  if (delta === 0) return "T0";
  const prefix = timeframe === "week" ? "S" : timeframe === "month" ? "M" : "J";
  return delta > 0 ? `${prefix}+${delta}` : `${prefix}${delta}`;
}

export function computeQuickSlTp(
  price: number,
  side: GamePositionSide,
  slPct: number,
  tpPct: number,
): { sl: number; tp: number } {
  if (!Number.isFinite(price) || price <= 0) {
    return { sl: 0, tp: 0 };
  }
  const factorSl = Math.abs(slPct) / 100;
  const factorTp = Math.abs(tpPct) / 100;
  const decimals = price >= 100 ? 2 : price >= 10 ? 3 : 4;
  const roundPrice = (v: number) => Number(Math.max(0.0001, v).toFixed(decimals));

  if (side === "long") {
    return {
      sl: roundPrice(price * (1 - factorSl)),
      tp: roundPrice(price * (1 + factorTp)),
    };
  }
  return {
    sl: roundPrice(price * (1 + factorSl)),
    tp: roundPrice(price * (1 - factorTp)),
  };
}

export function formatSignedPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} %`;
}

export function formatCurrencyAmount(value: number | null | undefined, currency?: string | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const formatted = value.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency ? `${formatted} ${currency}` : `${formatted} €`;
}

export function formatSignedCurrency(value: number | null | undefined, currency?: string | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const absFormatted = Math.abs(value).toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return currency ? `${sign}${absFormatted} ${currency}` : `${sign}${absFormatted} €`;
}

export function buildRoundChartOverlays(round: GameRoundView): {
  priceLines: ChartPriceLineOverlay[];
  markers: ChartMarkerOverlay[];
} {
  const priceLines: ChartPriceLineOverlay[] = [];
  const markers: ChartMarkerOverlay[] = [];

  const cutoffBar = round.bars[round.cutoff_index];
  if (cutoffBar?.date) {
    markers.push({
      time: cutoffBar.date,
      position: "aboveBar",
      shape: "circle",
      color: "#b4532a",
      text: "T0",
    });
  }

  if (round.entry_price != null && round.entry_date) {
    const isLong = round.position_side === "long";
    priceLines.push({
      price: round.entry_price,
      color: isLong ? "#059669" : "#e11d48",
      title: isLong ? "Entrée Achat" : "Entrée Vente",
      lineStyle: 2,
    });
    markers.push({
      time: round.entry_date,
      position: isLong ? "belowBar" : "aboveBar",
      shape: isLong ? "arrowUp" : "arrowDown",
      color: isLong ? "#10b981" : "#f43f5e",
      text: isLong ? "ACHAT" : "VENTE",
    });
  }

  if (round.stop_loss != null) {
    priceLines.push({
      price: round.stop_loss,
      color: "#ef4444",
      title: "SL",
      lineStyle: 3,
    });
  }

  if (round.take_profit != null) {
    priceLines.push({
      price: round.take_profit,
      color: "#10b981",
      title: "TP",
      lineStyle: 3,
    });
  }

  if (round.exit_price != null && round.exit_date) {
    const isWin = (round.pnl_amount ?? 0) >= 0;
    const exitLabel =
      round.exit_reason === "take_profit"
        ? "TP"
        : round.exit_reason === "stop_loss"
          ? "SL"
          : round.exit_reason === "horizon_end"
            ? "FIN"
            : "SORTIE";
    markers.push({
      time: round.exit_date,
      position: round.position_side === "long" ? "aboveBar" : "belowBar",
      shape: "square",
      color: isWin ? "#059669" : "#dc2626",
      text: exitLabel,
    });
  }

  markers.sort((a, b) => a.time.localeCompare(b.time));
  return { priceLines, markers };
}
