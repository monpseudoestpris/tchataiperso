/** Client HTTP et types TypeScript pour le jeu « Trading Replay » du Mode Finance. */

import { api } from "./api-client";
import type { EodBar } from "./api";

export type GameTimeframe = "day" | "week" | "month";
export type GameHorizon = "1w" | "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "5y";
export type GameUniverseType = "all" | "index" | "watchlist" | "symbol";
export type GamePositionSide = "long" | "short";
export type GamePositionStatus = "none" | "open" | "closed" | "skipped";
export type GameExitReason = "manual" | "stop_loss" | "take_profit" | "horizon_end" | "skipped";

export type GameProfile = {
  starting_capital: number;
  equity: number;
  total_pnl: number;
  total_return_pct: number;
  rounds_played: number;
  trades_taken: number;
  wins: number;
  losses: number;
  draws: number;
  winrate_pct: number | null;
  current_streak: number;
  best_streak: number;
  profit_factor: number | null;
  updated_at: string;
};

export type GameRoundSummary = {
  id: string;
  symbol: string;
  company_name: string;
  timeframe: GameTimeframe;
  horizon_code: GameHorizon;
  blind_mode: boolean;
  cutoff_date: string;
  end_date: string;
  position_side: GamePositionSide | null;
  position_status: GamePositionStatus;
  exit_reason: GameExitReason | null;
  return_pct: number | null;
  pnl_amount: number | null;
  buy_hold_return_pct: number | null;
  finished_at: string | null;
};

export type GameRoundView = {
  id: string;
  status: "active" | "finished";
  blind_mode: boolean;
  is_revealed: boolean;
  universe_type: GameUniverseType;
  universe_value: string;
  timeframe: GameTimeframe;
  horizon_code: GameHorizon;
  symbol: string | null;
  company_name: string;
  exchange: string | null;
  sector: string | null;
  currency: string | null;
  cutoff_index: number;
  horizon_bars: number;
  current_step: number;
  remaining_bars: number;
  cutoff_date: string | null;
  end_date: string | null;
  cutoff_price: number;
  current_price: number;
  change_from_cutoff_pct: number;
  position_side: GamePositionSide | null;
  position_status: GamePositionStatus;
  position_size_pct: number;
  stake_amount: number;
  entry_step: number | null;
  entry_date: string | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  exit_step: number | null;
  exit_date: string | null;
  exit_price: number | null;
  exit_reason: GameExitReason | null;
  return_pct: number | null;
  pnl_amount: number | null;
  unrealized_return_pct: number | null;
  unrealized_pnl: number | null;
  buy_hold_return_pct: number | null;
  triggered_event: GameExitReason | null;
  bars: EodBar[];
  created_at: string;
  finished_at: string | null;
};

export type GameStateResponse = {
  profile: GameProfile;
  active_round: GameRoundView | null;
  history: GameRoundSummary[];
  eligible_symbols_count: number;
};

export type GameRoundActionResponse = {
  round: GameRoundView;
  profile: GameProfile;
};

export async function fetchGameState(): Promise<GameStateResponse> {
  return api<GameStateResponse>("/finance/game/state");
}

export async function startGameRound(body: {
  universe_type: GameUniverseType;
  universe_value?: string;
  timeframe: GameTimeframe;
  horizon_code: GameHorizon;
  blind_mode: boolean;
}): Promise<GameRoundActionResponse> {
  return api<GameRoundActionResponse>("/finance/game/rounds", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchGameRound(roundId: string): Promise<GameRoundActionResponse> {
  return api<GameRoundActionResponse>(`/finance/game/rounds/${encodeURIComponent(roundId)}`);
}

export async function openGamePosition(
  roundId: string,
  body: {
    side: GamePositionSide;
    size_pct: number;
    stop_loss?: number | null;
    take_profit?: number | null;
  },
): Promise<GameRoundActionResponse> {
  return api<GameRoundActionResponse>(`/finance/game/rounds/${encodeURIComponent(roundId)}/position`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function stepGameRound(roundId: string, steps = 1): Promise<GameRoundActionResponse> {
  return api<GameRoundActionResponse>(`/finance/game/rounds/${encodeURIComponent(roundId)}/step`, {
    method: "POST",
    body: JSON.stringify({ steps }),
  });
}

export async function closeGamePosition(roundId: string, finishNow = false): Promise<GameRoundActionResponse> {
  return api<GameRoundActionResponse>(`/finance/game/rounds/${encodeURIComponent(roundId)}/close`, {
    method: "POST",
    body: JSON.stringify({ finish_now: finishNow }),
  });
}

export async function finishGameRound(roundId: string): Promise<GameRoundActionResponse> {
  return api<GameRoundActionResponse>(`/finance/game/rounds/${encodeURIComponent(roundId)}/finish`, {
    method: "POST",
  });
}

export async function resetGameProfile(body: {
  starting_capital?: number;
  clear_history?: boolean;
} = {}): Promise<GameStateResponse> {
  return api<GameStateResponse>("/finance/game/reset", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
