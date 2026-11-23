/** Types et clients HTTP Finance : Screener boursier, quota EODHD et file priorisée des fondamentaux. */

import { api } from "./api-client";
import type { FinanceSyncProgress, FinanceWatchlistMeta } from "./api";

// ---------------------------------------------------------------------------
// Screener boursier intégré (Fondamentaux & Indicateurs techniques)
// ---------------------------------------------------------------------------

export type ScreenerTimeframe = "day" | "week" | "month" | "quarter";

export type ScreenerAssetType = "" | "stock" | "etf";

export type ScreenerEtfExchangeInfo = {
  code: string;
  label: string;
  country: string;
  flag: string;
  catalog_synced: boolean;
  total_symbols: number;
  etf_catalog_count: number;
  etf_in_screener_count: number;
  etf_with_data_count: number;
  synced_at: string | null;
};

export type ScreenerFieldOption = {
  value: number;
  label: string;
};

export type ScreenerFieldMeta = {
  key: string;
  label: string;
  category: "performance" | "valuation" | "quality" | "scores" | "technical";
  type: "number" | "signal";
  unit?: string;
  scale?: number;
  comparable?: boolean;
  compare_group?: "price" | "isopressure";
  supports_timeframe?: boolean;
  options?: ScreenerFieldOption[];
  description?: string;
};

export type ScreenerRule =
  | {
      kind: "metric";
      field: string;
      op: "gt" | "gte" | "lt" | "lte" | "eq" | "neq" | "between" | "is_not_null";
      value?: number;
      value_max?: number;
      timeframe?: ScreenerTimeframe;
    }
  | {
      kind: "compare";
      left: string;
      op: "gt" | "gte" | "lt" | "lte";
      right: string;
      multiplier?: number;
      timeframe?: ScreenerTimeframe;
    }
  | {
      kind: "signal";
      field: string;
      op: "eq" | "in";
      value: number | number[];
      timeframe?: ScreenerTimeframe;
    };

export type ScreenerPreset = {
  id: string;
  name: string;
  description: string;
  sort_by: string;
  sort_dir: "asc" | "desc";
  rules: ScreenerRule[];
};

export type ScreenerFacetItem = {
  code: string;
  label: string;
  count: number;
};

export type ScreenerCountryFacet = ScreenerFacetItem & {
  flag: string;
};

export type ScreenerZoneFacet = ScreenerFacetItem & {
  name: string;
  flag: string;
};

export type ScreenerIndexFacet = {
  code: string;
  name: string;
  flag: string;
  region: string;
  tier: string;
  count: number;
};

export type ScreenerCoverage = {
  total_snapshots: number;
  with_technicals: number;
  with_fundamentals: number;
  stock_count?: number;
  etf_count?: number;
  warehouse_symbols_count: number;
  sectors: string[];
  exchanges: string[];
  exchange_items?: ScreenerFacetItem[];
  etf_exchanges?: ScreenerEtfExchangeInfo[];
  currencies: string[];
  countries?: ScreenerCountryFacet[];
  market_zones?: ScreenerZoneFacet[];
  indices?: ScreenerIndexFacet[];
  cap_categories?: ScreenerFacetItem[];
  last_computed_at: string | null;
};

export type ScreenerMetaResponse = {
  fields: ScreenerFieldMeta[];
  timeframes?: Array<{ key: ScreenerTimeframe; label: string }>;
  presets: ScreenerPreset[];
  coverage: ScreenerCoverage;
  formula_engine: {
    ready: boolean;
    registered_kinds: string[];
  };
};

export type ScreenerRow = {
  symbol: string;
  eod_ticker: string | null;
  yahoo_symbol: string | null;
  asset_type?: "stock" | "etf";
  name: string;
  exchange: string;
  country: string;
  market_zone?: string;
  currency: string;
  sector: string;
  industry: string;
  cap_category: string;
  indices: string[];
  timeframe?: ScreenerTimeframe;
  tf_bars_count?: number;
  market_cap: number | null;
  market_cap_m: number | null;
  price: number | null;
  volume: number | null;
  rel_volume_20d: number | null;
  change_1d_pct: number | null;
  change_1w_pct: number | null;
  change_1m_pct: number | null;
  change_3m_pct: number | null;
  change_ytd_pct: number | null;
  change_1y_pct: number | null;
  dist_52w_high_pct: number | null;
  dist_52w_low_pct: number | null;
  pe_ttm: number | null;
  pe_forward: number | null;
  peg_ratio: number | null;
  ev_ebitda: number | null;
  pb_ratio: number | null;
  fcf_yield_pct: number | null;
  dividend_yield_pct: number | null;
  roic_pct: number | null;
  roe_pct: number | null;
  op_margin_pct: number | null;
  net_margin_pct: number | null;
  net_debt_ebitda: number | null;
  debt_to_equity_pct: number | null;
  current_ratio: number | null;
  rev_cagr_3y_pct: number | null;
  eps_cagr_3y_pct: number | null;
  beta: number | null;
  analyst_upside_pct: number | null;
  ih_score: number | null;
  piotroski_f: number | null;
  altman_z: number | null;
  mos_intrinsic_pct: number | null;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  ema20: number | null;
  ema50: number | null;
  dist_sma50_pct: number | null;
  dist_sma200_pct: number | null;
  rsi_14: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  macd_cross: number | null;
  sma_golden_cross: number | null;
  boll_pct_b: number | null;
  boll_width_pct: number | null;
  adx_14: number | null;
  stoch_k: number | null;
  atr_pct: number | null;
  roc_12: number | null;
  supertrend_dir: number | null;
  isopressure_raw: number | null;
  isopressure_p5: number | null;
  isopressure_p20: number | null;
  isopressure_p50: number | null;
  isopressure_p100: number | null;
  isopressure_p200: number | null;
  isopressure_20_50_diff: number | null;
  isopressure_20_50_dir: number | null;
  isopressure_20_50_cross: number | null;
  isopressure_5_20_cross: number | null;
  has_fundamentals: boolean;
  bars_count: number;
  bars_date: string | null;
  fundamentals_updated_at: string | null;
  computed_at: string;
  sparkline: number[];
};

export type ScreenerQueryRequest = {
  timeframe?: ScreenerTimeframe;
  asset_type?: ScreenerAssetType;
  universe_type?: "all" | "index" | "watchlist" | "exchange" | "zone" | "country";
  universe_value?: string | null;
  index_code?: string;
  market_zone?: string;
  country?: string;
  cap_category?: string;
  search?: string;
  sector?: string;
  exchange?: string;
  currency?: string;
  only_with_fundamentals?: boolean;
  rules?: ScreenerRule[];
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  offset?: number;
};

export type ScreenerQueryResponse = {
  timeframe?: ScreenerTimeframe;
  total: number;
  universe_total: number;
  missing_data_count?: number;
  offset: number;
  limit: number;
  items: ScreenerRow[];
  coverage: ScreenerCoverage;
};

export type ScreenerHydrateResponse = {
  started?: boolean;
  already_running?: boolean;
  progress?: FinanceSyncProgress;
  universe_type: string;
  universe_value: string | null;
  symbols_count: number;
  eod_loaded: number;
  indexed_count: number;
  fundamentals_enriched: number;
  fundamentals_cached: number;
  fundamentals_errors: number;
  coverage: ScreenerCoverage;
};

export async function fetchFinanceScreenerMeta(
  assetType: ScreenerAssetType = "",
): Promise<ScreenerMetaResponse> {
  const qs = assetType ? `?asset_type=${encodeURIComponent(assetType)}` : "";
  return api<ScreenerMetaResponse>(`/finance/screener/meta${qs}`);
}

export type ScreenerEtfExchangeLoadResponse = {
  exchange: string;
  source: string;
  seeded_count: number;
  exchange_info: ScreenerEtfExchangeInfo | null;
  etf_exchanges: ScreenerEtfExchangeInfo[];
  coverage: ScreenerCoverage;
};

export async function loadScreenerEtfExchange(body: {
  exchange: string;
  seed_screener?: boolean;
  refresh_catalog?: boolean;
}): Promise<ScreenerEtfExchangeLoadResponse> {
  return api<ScreenerEtfExchangeLoadResponse>("/finance/screener/etf-exchanges/load", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function hydrateScreenerBarsBatch(body: {
  symbols?: string[];
  screener_filters?: ScreenerQueryRequest;
  batch_size?: number;
  background?: boolean;
}): Promise<{
  started?: boolean;
  already_running?: boolean;
  targeted?: number;
  loaded?: number;
  errors?: number;
  calls?: number;
  progress?: FinanceSyncProgress;
}> {
  return api("/finance/screener/hydrate-bars", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function queryFinanceScreener(
  body: ScreenerQueryRequest,
): Promise<ScreenerQueryResponse> {
  return api<ScreenerQueryResponse>("/finance/screener/query", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function rebuildFinanceScreener(): Promise<{
  indexed_count: number;
  coverage: ScreenerCoverage;
}> {
  return api<{ indexed_count: number; coverage: ScreenerCoverage }>("/finance/screener/rebuild", {
    method: "POST",
  });
}

export async function hydrateFinanceScreener(body: {
  universe_type: "all" | "index" | "watchlist";
  universe_value?: string | null;
  include_fundamentals?: boolean;
  max_fundamentals?: number;
  refresh_eod?: boolean;
  background?: boolean;
}): Promise<ScreenerHydrateResponse> {
  return api<ScreenerHydrateResponse>("/finance/screener/hydrate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function exportScreenerToWatchlist(body: {
  list_name?: string;
  list_id?: string | null;
  items: Array<{
    symbol: string;
    eod_ticker?: string | null;
    yahoo_symbol?: string | null;
    name?: string;
    exchange?: string;
    currency?: string;
  }>;
}): Promise<{ list: FinanceWatchlistMeta; added_count: number }> {
  return api<{ list: FinanceWatchlistMeta; added_count: number }>(
    "/finance/screener/export-watchlist",
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

// ---------------------------------------------------------------------------
// Consommation de l'API EODHD (quota, appels du jour, barème)
// ---------------------------------------------------------------------------

export type EodhdUsageEndpoint = {
  endpoint: string;
  label: string;
  requests: number;
  unit_cost: number;
  calls: number;
};

export type EodhdUsageReport = {
  account: {
    subscription: string;
    api_requests_today: number | null;
    api_requests_date: string | null;
    daily_limit: number | null;
    extra_limit: number | null;
    remaining_today: number | null;
  } | null;
  local: {
    date: string;
    total_requests: number;
    total_calls: number;
    by_endpoint: EodhdUsageEndpoint[];
  };
  cost_table: Array<{ endpoint: string; unit_cost: number; label: string }>;
  sync_estimate: {
    lines: Array<{ label: string; calls: number; periodic?: boolean }>;
    max_daily_calls: number;
    light_load_calls?: number;
    full_dossier_calls_estimate?: number;
    note: string;
  };
  source_url: string;
};

export async function fetchEodhdUsage(): Promise<EodhdUsageReport> {
  return api<EodhdUsageReport>("/finance/eodhd-usage");
}

// ---------------------------------------------------------------------------
// File priorisée des fondamentaux (budget quotidien, échéances intelligentes)
// ---------------------------------------------------------------------------

export type FundamentalsSchedule = {
  symbol: string;
  status: "pending" | "ok" | "error";
  last_fetched_at: string | null;
  last_period_end: string | null;
  last_report_date: string | null;
  cadence: "quarterly" | "semiannual" | "annual" | "";
  next_due_at: string | null;
  reported_pending: number;
  priority: number;
};

export type FundamentalsQueueState = {
  stats: {
    tracked: number;
    never_loaded: number;
    reported: number;
    due: number;
    up_to_date: number;
    errors: number;
    boosted: number;
    to_process: number;
  };
  budget: {
    daily_limit: number;
    daily_limit_known: boolean;
    budget_calls: number;
    spent_today: number;
    remaining_budget: number;
    titles_per_day: number;
    safety_floor: number;
    account_remaining: number | null;
  };
  estimated_days: number;
  next_items: Array<{ symbol: string; priority: number; reason: string; why: string }>;
};

export async function fetchFundamentalsQueue(): Promise<FundamentalsQueueState> {
  return api<FundamentalsQueueState>("/finance/fundamentals-queue");
}

export async function runFundamentalsQueueNow(): Promise<{ started: boolean; already_running: boolean }> {
  return api<{ started: boolean; already_running: boolean }>("/finance/fundamentals-queue/run", { method: "POST" });
}

export async function boostFundamentalsQueue(body: {
  symbols?: string[];
  screener_filters?: ScreenerQueryRequest;
  batch_size?: number;
  run?: boolean;
}): Promise<{ boosted: number; started: boolean; already_running: boolean }> {
  return api<{ boosted: number; started: boolean; already_running: boolean }>("/finance/fundamentals-queue/boost", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
