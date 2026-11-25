"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { FinanceAiHistoryPanel } from "@/components/finance-ai-history-panel";
import { FinanceCustomIndicatorModal } from "@/components/finance-custom-indicator-modal";
import { FinanceDossierPanel } from "@/components/finance-dossier-panel";
import { FinanceEufundBrowser } from "@/components/finance-eufund-browser";
import { FinanceExpertsPanel } from "@/components/finance-experts-panel";
import { FinanceFullscreenTickerSwitcher } from "@/components/finance-fullscreen-ticker-switcher";
import { FinanceGamePanel } from "@/components/finance-game-panel";
import { FinanceHelpGuideId, FinanceHelpModal } from "@/components/finance-help-modal";
import { FinanceThemeSwitcher, useInterfaceTheme } from "@/components/finance-theme-switcher";
import { ModelModal } from "@/components/model-modal";
import {
  FinanceEodhdIndxBrowser,
  FinanceIndexCompositionDrawer,
  FinanceIndicesStrip,
} from "@/components/finance-indices-panel";
import { FinanceMetricLabel } from "@/components/finance-info-tip";
import {
  aggregateBars,
  BAR_INTERVAL_LABELS,
  type BarInterval,
} from "@/lib/bar-aggregation";
import {
  buildDividendChartMarkers,
  formatDividendHoverSummary,
  projectDividendsToBars,
  type ProjectedBarDividend,
} from "@/lib/chart-dividends";
import type { IndicatorFillConfig } from "@/lib/chart-zone-fills";
import {
  DEFAULT_INDICATOR_PARAMS,
  loadCustomIndicatorFills,
  loadIndicatorParams,
  type ConfigurableIndicatorKey,
  type IndicatorKey,
  type IndicatorParamsMap,
} from "@/lib/indicator-params";
import { FinanceMoatPanel } from "@/components/finance-moat-panel";
import { FinanceNewsPanel } from "@/components/finance-news-panel";
import { FinanceReportsPanel } from "@/components/finance-reports-panel";
import { FinanceScreenerPanel } from "@/components/finance-screener-panel";
import { FinanceSyncPanel } from "@/components/finance-sync-panel";
import { FinanceStatements } from "@/components/finance-statements";
import { FinanceTvChart } from "@/components/finance-tv-chart";
import { FinanceWatchlistTable } from "@/components/finance-watchlist-table";
import {
  ArrowDownRight,
  ArrowUpRight,
  Award,
  BarChart3,
  Building2,
  Check,
  ChevronRight,
  ClipboardList,
  Coins,
  Copy,
  Database,
  ExternalLink,
  FileText,
  HelpCircle,
  History,
  LineChart,
  LoaderCircle,
  Maximize2,
  MessageSquarePlus,
  Minimize2,
  Newspaper,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Trophy,
  Wallet,
  X,
} from "lucide-react";
import {
  addWatchlistItem,
  api,
  createCustomIndicator,
  createWatchlist,
  deleteCustomIndicator,
  deleteWatchlist,
  deleteWatchlistItem,
  fetchCachedIndexPerformances,
  fetchCustomIndicators,
  fetchFinanceDetails,
  fetchFinanceDividends,
  fetchFinanceSyncStatus,
  fetchIndexComposition,
  fetchPrincipalIndices,
  fetchWatchlistState,
  importIndexToWatchlist,
  loadIndexPerformances,
  renameWatchlist,
  reorderWatchlistItems,
  searchFinanceCatalog,
  seedDefaultWatchlist,
  updateCustomIndicator,
  updateWatchlistItemNote,
  type CatalogSearchItem,
  type Config,
  type CustomIndicator,
  type CustomIndicatorGuideLine,
  type EodBar,
  type EodhdEufundItem,
  type FinanceRange,
  type FinanceSyncProgress,
  type FinanceWatchlistMeta,
  type FinancialDashboardData,
  type FinancialStats,
  type IndexCompositionResponse,
  type IndexConstituent,
  type IndexPerformancesResponse,
  type Model,
  type PrincipalIndexInfo,
  type QuarterlyReport,
  type StockDividendItem,
  type WarehouseOverview,
  type WatchlistItem,
} from "@/lib/api";

export type FinanceMainTab =
  | "search_indices"
  | "fundamentals"
  | "chart_tech"
  | "screener"
  | "data_sync"
  | "trading_game";

type FinanceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  initialQuery?: string | null;
  initialData?: FinancialDashboardData | null;
  initialMainTab?: FinanceMainTab | null;
  models?: Model[];
  defaultModel?: string;
  onRefreshModels?: () => Promise<void>;
  onInsertIntoChat?: (text: string) => void;
  onOpenReportAsDoc?: (report: QuarterlyReport, openVoiceFullscreen?: boolean) => Promise<void> | void;
};

type MainTab = FinanceMainTab;

type ActiveTab =
  | "dossier"
  | "valuation"
  | "profitability"
  | "balance_sheet"
  | "fundamentals"
  | "analysts"
  | "profile"
  | "moat"
  | "experts"
  | "ai_history"
  | "news"
  | "reports";

const WATCHLIST_SEED_STORAGE_KEY = "clair_watchlist_seeded_v1";
const WATCHLIST_ACTIVE_LIST_KEY = "clair_active_watchlist_id_v1";
const WATCHLIST_SIDEBAR_OPEN_KEY = "clair_finance_wl_sidebar_open_v1";
const WATCHLIST_SIDEBAR_WIDE_KEY = "clair_finance_wl_sidebar_wide_v1";
const CHART_TABS_STORAGE_KEY = "clair_finance_chart_tabs_v1";
const ACTIVE_CHART_TAB_STORAGE_KEY = "clair_finance_active_chart_tab_v1";

type DailyFinanceRange = Exclude<FinanceRange, "1d" | "1w">;

type ChartTabConfig = {
  id: string;
  name: string;
  barInterval: BarInterval;
  timeframe: FinanceRange;
  chartView: "advanced" | "line";
  showDividends?: boolean;
  activeNative: IndicatorKey[];
  activeCustomIds: string[];
  indicatorParams: IndicatorParamsMap;
  customFills: Record<string, IndicatorFillConfig>;
};

const DAILY_RANGE_ORDER: DailyFinanceRange[] = ["1m", "3m", "6m", "1y", "2y", "5y", "10y", "max"];
const DAILY_RANGE_BAR_LIMITS: Record<DailyFinanceRange, number> = {
  "1m": 30,
  "3m": 66,
  "6m": 132,
  "1y": 260,
  "2y": 520,
  "5y": 1300,
  "10y": 2600,
  max: 7500,
};

function isDailyRange(tf: FinanceRange): tf is DailyFinanceRange {
  return tf !== "1d" && tf !== "1w";
}

function getDailyRangeRank(tf: DailyFinanceRange): number {
  return DAILY_RANGE_ORDER.indexOf(tf);
}

function getWidestDailyRange(tabs: ChartTabConfig[]): DailyFinanceRange {
  let bestRank = getDailyRangeRank("1y");
  for (const t of tabs) {
    if (isDailyRange(t.timeframe)) {
      const r = getDailyRangeRank(t.timeframe);
      if (r > bestRank) bestRank = r;
    }
  }
  return DAILY_RANGE_ORDER[bestRank] || "1y";
}

function normalizeIndicatorParams(raw: unknown): IndicatorParamsMap {
  const merged: IndicatorParamsMap = { ...DEFAULT_INDICATOR_PARAMS };
  if (!raw || typeof raw !== "object") return merged;
  const parsed = raw as Record<string, unknown>;
  for (const k of Object.keys(DEFAULT_INDICATOR_PARAMS) as ConfigurableIndicatorKey[]) {
    const entry = parsed[k] as ({ fill?: Partial<IndicatorFillConfig> } & Record<string, unknown>) | undefined;
    if (entry && typeof entry === "object") {
      const def = DEFAULT_INDICATOR_PARAMS[k];
      merged[k] = {
        ...def,
        ...entry,
        fill: {
          ...def.fill,
          ...(entry.fill && typeof entry.fill === "object" ? entry.fill : {}),
        },
      } as never;
    }
  }
  return merged;
}

function createDefaultChartTabs(): ChartTabConfig[] {
  const baseFills = loadCustomIndicatorFills();
  return [
    {
      id: "tab-daily",
      name: "Journalier",
      barInterval: "day",
      timeframe: "6m",
      chartView: "advanced",
      activeNative: ["sma20", "volume", "rsi"],
      activeCustomIds: [],
      indicatorParams: loadIndicatorParams(),
      customFills: { ...baseFills },
    },
    {
      id: "tab-weekly",
      name: "Hebdomadaire",
      barInterval: "week",
      timeframe: "5y",
      chartView: "advanced",
      activeNative: ["sma20", "sma50", "volume", "macd"],
      activeCustomIds: [],
      indicatorParams: loadIndicatorParams(),
      customFills: { ...baseFills },
    },
    {
      id: "tab-monthly",
      name: "Mensuel",
      barInterval: "month",
      timeframe: "10y",
      chartView: "advanced",
      activeNative: ["sma20", "supertrend", "volume", "rsi"],
      activeCustomIds: [],
      indicatorParams: loadIndicatorParams(),
      customFills: { ...baseFills },
    },
  ];
}

function loadSavedChartTabs(): ChartTabConfig[] {
  if (typeof window === "undefined") return createDefaultChartTabs();
  try {
    const raw = window.localStorage.getItem(CHART_TABS_STORAGE_KEY);
    if (!raw) return createDefaultChartTabs();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return createDefaultChartTabs();
    const validRanges = new Set<FinanceRange>(["1d", "1w", "1m", "3m", "6m", "1y", "2y", "5y", "10y", "max"]);
    const validIntervals = new Set<BarInterval>(Object.keys(BAR_INTERVAL_LABELS) as BarInterval[]);
    const restored: ChartTabConfig[] = [];
    for (let i = 0; i < parsed.length; i += 1) {
      const item = parsed[i];
      if (!item || typeof item !== "object") continue;
      const obj = item as Partial<ChartTabConfig>;
      const id = typeof obj.id === "string" && obj.id.trim() ? obj.id : `tab-${i + 1}`;
      const name = typeof obj.name === "string" && obj.name.trim() ? obj.name.trim() : `Vue ${i + 1}`;
      const barInterval = obj.barInterval && validIntervals.has(obj.barInterval) ? obj.barInterval : "day";
      const timeframe = obj.timeframe && validRanges.has(obj.timeframe) ? obj.timeframe : "6m";
      const chartView = obj.chartView === "line" ? "line" : "advanced";
      const activeNative = Array.isArray(obj.activeNative)
        ? obj.activeNative.filter((k): k is IndicatorKey => typeof k === "string")
        : (["sma20", "volume", "rsi"] as IndicatorKey[]);
      const activeCustomIds = Array.isArray(obj.activeCustomIds)
        ? obj.activeCustomIds.filter((idStr): idStr is string => typeof idStr === "string")
        : [];
      const customFills =
        obj.customFills && typeof obj.customFills === "object"
          ? (obj.customFills as Record<string, IndicatorFillConfig>)
          : {};
      restored.push({
        id,
        name,
        barInterval,
        timeframe,
        chartView,
        showDividends: Boolean(obj.showDividends),
        activeNative,
        activeCustomIds,
        indicatorParams: normalizeIndicatorParams(obj.indicatorParams),
        customFills,
      });
    }
    return restored.length > 0 ? restored : createDefaultChartTabs();
  } catch {
    return createDefaultChartTabs();
  }
}

const QUICK_SUGGESTIONS = [
  "Air Liquide",
  "LVMH",
  "TotalEnergies",
  "Apple",
  "Tesla",
  "Nvidia",
  "Stellantis",
  "Microsoft",
];

const TIMEFRAME_LABELS: Record<FinanceRange, string> = {
  "1d": "1 J",
  "1w": "1 Sem.",
  "1m": "1 Mois",
  "3m": "3 Mois",
  "6m": "6 Mois",
  "1y": "1 An",
  "2y": "2 Ans",
  "5y": "5 Ans",
  "10y": "10 Ans",
  max: "Max",
};

function formatAnalystRecommendation(rec?: string | null): {
  label: string;
  tone: "buy" | "hold" | "sell" | "neutral";
} {
  if (!rec || rec === "NONE" || rec === "N/A" || rec.trim() === "") {
    return { label: "Non disponible", tone: "neutral" };
  }
  const upper = rec.toUpperCase();
  if (upper.includes("STRONG_BUY")) return { label: "Achat Fort", tone: "buy" };
  if (upper.includes("BUY")) return { label: "Achat", tone: "buy" };
  if (upper.includes("HOLD")) return { label: "Conserver", tone: "hold" };
  if (upper.includes("UNDERPERFORM")) return { label: "Sous-pondérer", tone: "sell" };
  if (upper.includes("SELL")) return { label: "Vente", tone: "sell" };
  return { label: upper, tone: "neutral" };
}

export function FinanceModal({
  isOpen,
  onClose,
  initialQuery,
  initialData,
  initialMainTab,
  models: propModels,
  defaultModel: propDefaultModel,
  onRefreshModels,
  onInsertIntoChat,
  onOpenReportAsDoc,
}: FinanceModalProps) {
  const theme = useInterfaceTheme();
  const [fallbackModels, setFallbackModels] = useState<Model[]>([]);
  const [fallbackDefaultModel, setFallbackDefaultModel] = useState<string>("");
  const [selectedExpertModel, setSelectedExpertModel] = useState<string>("");
  const [modelModalOpen, setModelModalOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<FinancialDashboardData | null>(initialData || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mainTab, setMainTab] = useState<MainTab>("fundamentals");
  const [mountedMainTabs, setMountedMainTabs] = useState<Partial<Record<MainTab, boolean>>>({
    fundamentals: true,
  });
  if (!mountedMainTabs[mainTab]) {
    setMountedMainTabs(prev => ({ ...prev, [mainTab]: true }));
  }
  const [prevOpenSessionKey, setPrevOpenSessionKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("dossier");
  const [mountedSubTabs, setMountedSubTabs] = useState<Partial<Record<ActiveTab, boolean>>>({
    dossier: true,
  });
  if (!mountedSubTabs[activeTab]) {
    setMountedSubTabs(prev => ({ ...prev, [activeTab]: true }));
  }
  const [chartTabs, setChartTabs] = useState<ChartTabConfig[]>(() => loadSavedChartTabs());
  const [activeChartTabId, setActiveChartTabId] = useState<string>(() => {
    if (typeof window === "undefined") return "tab-daily";
    return window.localStorage.getItem(ACTIVE_CHART_TAB_STORAGE_KEY) || "tab-daily";
  });
  const [dailyBars, setDailyBars] = useState<EodBar[]>(() => initialData?.eod_bars || []);
  const [loadedDailyRange, setLoadedDailyRange] = useState<DailyFinanceRange>("1m");
  const [intradayBarsByRange, setIntradayBarsByRange] = useState<Partial<Record<"1d" | "1w", EodBar[]>>>({});
  const [renamingChartTabId, setRenamingChartTabId] = useState<string | null>(null);
  const [renamingChartTabValue, setRenamingChartTabValue] = useState<string>("");
  const [rangeLoading, setRangeLoading] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [fullscreenTickerOpen, setFullscreenTickerOpen] = useState(false);
  const [hoveredBarIndex, setHoveredBarIndex] = useState<number | null>(null);
  const [dividendsBySymbol, setDividendsBySymbol] = useState<
    Record<string, { items: StockDividendItem[]; currency: string }>
  >({});
  const [dividendsLoadingSymbol, setDividendsLoadingSymbol] = useState<string | null>(null);
  const [dividendsError, setDividendsError] = useState<string | null>(null);
  const [dividendsRetryNonce, setDividendsRetryNonce] = useState(0);
  const activeChartTab = useMemo(
    () => chartTabs.find(t => t.id === activeChartTabId) ?? chartTabs[0],
    [chartTabs, activeChartTabId],
  );
  const [copied, setCopied] = useState(false);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchlists, setWatchlists] = useState<FinanceWatchlistMeta[]>([]);
  const [activeListId, setActiveListId] = useState<string | null>(null);
  const [heroFollowListId, setHeroFollowListId] = useState<string>("");
  const [heroFollowBusy, setHeroFollowBusy] = useState(false);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [customIndicators, setCustomIndicators] = useState<CustomIndicator[]>([]);
  const [indicatorModalOpen, setIndicatorModalOpen] = useState(false);
  const [editingIndicator, setEditingIndicator] = useState<CustomIndicator | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [helpGuide, setHelpGuide] = useState<FinanceHelpGuideId>("intrinsic");

  function openHelpGuide(guide: FinanceHelpGuideId = "intrinsic") {
    setHelpGuide(guide);
    setHelpOpen(true);
  }
  const [indices, setIndices] = useState<PrincipalIndexInfo[]>([]);
  const [warehouseStats, setWarehouseStats] = useState<WarehouseOverview | null>(null);
  const [activeIndexCode, setActiveIndexCode] = useState<string | null>(null);
  const [indexComposition, setIndexComposition] = useState<IndexCompositionResponse | null>(null);
  const [indexPerformancesByCode, setIndexPerformancesByCode] = useState<
    Record<string, IndexPerformancesResponse>
  >({});
  const [indexPerfLoading, setIndexPerfLoading] = useState(false);
  const [indexImportBusy, setIndexImportBusy] = useState(false);
  const [indexImportBanner, setIndexImportBanner] = useState<string | null>(null);
  const [indexLoading, setIndexLoading] = useState(false);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indxCatalogOpen, setIndxCatalogOpen] = useState(false);
  const [eufundCatalogOpen, setEufundCatalogOpen] = useState(false);
  const [syncProgress, setSyncProgress] = useState<FinanceSyncProgress | null>(null);
  const [watchlistSidebarOpen, setWatchlistSidebarOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem(WATCHLIST_SIDEBAR_OPEN_KEY) !== "0";
  });
  const [watchlistSidebarWide, setWatchlistSidebarWide] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(WATCHLIST_SIDEBAR_WIDE_KEY) === "1";
  });

  function toggleWatchlistSidebar(force?: boolean) {
    setWatchlistSidebarOpen(prev => {
      const next = force ?? !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(WATCHLIST_SIDEBAR_OPEN_KEY, next ? "1" : "0");
      }
      return next;
    });
  }

  function toggleWatchlistSidebarWide() {
    setWatchlistSidebarWide(prev => {
      const next = !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(WATCHLIST_SIDEBAR_WIDE_KEY, next ? "1" : "0");
      }
      return next;
    });
  }
  const [minorQuotesLoaded, setMinorQuotesLoaded] = useState(false);
  const [catalogMatches, setCatalogMatches] = useState<CatalogSearchItem[]>([]);
  const [searchFocused, setSearchFocused] = useState(false);
  const chartSectionRef = useRef<HTMLDivElement | null>(null);
  const modalBodyRef = useRef<HTMLDivElement | null>(null);

  const availableModels = propModels && propModels.length > 0 ? propModels : fallbackModels;
  const resolvedExpertModel =
    selectedExpertModel || propDefaultModel || fallbackDefaultModel || availableModels[0]?.id || "";
  const resolvedExpertModelInfo = useMemo(
    () => availableModels.find(m => m.id === resolvedExpertModel),
    [availableModels, resolvedExpertModel],
  );

  async function refreshModelsForFinance() {
    if (onRefreshModels) {
      await onRefreshModels();
      return;
    }
    try {
      const res = await api<{ models: Model[]; default_model?: string }>("/models?refresh=true");
      if (res?.models?.length) {
        setFallbackModels(res.models);
        if (res.default_model) setFallbackDefaultModel(res.default_model);
      }
    } catch {
      const cfg = await api<Config>("/config");
      setFallbackModels(cfg.models || []);
      if (cfg.default_model) setFallbackDefaultModel(cfg.default_model);
    }
  }

  const currentOpenSessionKey = isOpen ? `${initialQuery ?? ""}::${initialData?.symbol ?? ""}::${initialMainTab ?? ""}` : null;
  if (currentOpenSessionKey !== prevOpenSessionKey) {
    setPrevOpenSessionKey(currentOpenSessionKey);
    if (isOpen) {
      if (initialMainTab) {
        setMainTab(initialMainTab);
      } else if (initialData || (initialQuery || "").trim()) {
        setMainTab("fundamentals");
      } else if (!data) {
        setMainTab("search_indices");
      }
    }
  }

  function switchMainTab(next: MainTab) {
    setMainTab(next);
    if (next === "chart_tech" && data) {
      void ensureBarsForTab(activeChartTab, data);
    }
    window.requestAnimationFrame(() => {
      modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // Synchronize synchronous state when opening modal or changing initial props
  const openSyncKey = isOpen
    ? `${initialQuery ?? ""}::${initialData?.symbol ?? ""}::${initialMainTab ?? ""}`
    : null;
  const [prevOpenSyncKey, setPrevOpenSyncKey] = useState<string | null>(null);
  if (openSyncKey !== prevOpenSyncKey) {
    setPrevOpenSyncKey(openSyncKey);
    if (isOpen) {
      if (initialData) {
        setData(initialData);
        setDailyBars(initialData.eod_bars || []);
        setLoadedDailyRange("1m");
        setIntradayBarsByRange({});
        setQuery(initialData.short_name || initialData.symbol);
        setError(null);
      } else {
        const targetQuery = (initialQuery || "").trim();
        if (targetQuery) {
          setQuery(targetQuery);
        } else if (!data && initialMainTab !== "screener") {
          setQuery("Air Liquide");
        }
      }
    }
  }

  const openFetchRef = useRef({
    loadWorkspaceData,
    loadDetails,
    hasData: Boolean(data),
    hasPropModels: Boolean(propModels && propModels.length > 0),
  });
  useEffect(() => {
    openFetchRef.current = {
      loadWorkspaceData,
      loadDetails,
      hasData: Boolean(data),
      hasPropModels: Boolean(propModels && propModels.length > 0),
    };
  });

  // Trigger async fetches when opening modal
  useEffect(() => {
    if (!isOpen) return;

    void openFetchRef.current.loadWorkspaceData();
    if (!openFetchRef.current.hasPropModels) {
      api<Config>("/config")
        .then(cfg => {
          setFallbackModels(cfg.models || []);
          if (cfg.default_model) setFallbackDefaultModel(cfg.default_model);
        })
        .catch(() => {});
    }

    if (initialData) return;

    const targetQuery = (initialQuery || "").trim();
    if (targetQuery) {
      void openFetchRef.current.loadDetails(targetQuery);
    } else if (!openFetchRef.current.hasData && initialMainTab !== "screener") {
      // Default to Air Liquide if no initial query
      void openFetchRef.current.loadDetails("Air Liquide");
    }
  }, [isOpen, initialQuery, initialData, initialMainTab]);

  // Suit l'état en direct de la synchro auto en arrière-plan tant que la modale Finances est ouverte
  const isBgSyncRunning = Boolean(syncProgress?.is_running);
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    const poll = () => {
      fetchFinanceSyncStatus()
        .then(st => {
          if (cancelled) return;
          setSyncProgress(prev => {
            if (prev?.is_running && !st.is_running) {
              void loadWorkspaceData(false);
            }
            return st;
          });
        })
        .catch(() => {});
    };
    poll();
    const timer = window.setInterval(poll, isBgSyncRunning ? 2500 : 18000);
    window.addEventListener("finance-sync-started", poll);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("finance-sync-started", poll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, isBgSyncRunning]);

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (modelModalOpen) {
          setModelModalOpen(false);
          return;
        }
        if (helpOpen) {
          setHelpOpen(false);
          return;
        }
        if (indicatorModalOpen) {
          setIndicatorModalOpen(false);
          setEditingIndicator(null);
          return;
        }
        if (fullscreenTickerOpen) {
          setFullscreenTickerOpen(false);
          return;
        }
        if (chartFullscreen) {
          setChartFullscreen(false);
          return;
        }
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, modelModalOpen, helpOpen, indicatorModalOpen, fullscreenTickerOpen, chartFullscreen, onClose]);

  const visibleCatalogMatches = searchFocused && query.trim().length >= 2 ? catalogMatches : [];

  useEffect(() => {
    if (!isOpen) return;
    const trimmed = query.trim();
    if (!searchFocused || trimmed.length < 2) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      searchFinanceCatalog(trimmed, 18)
        .then(items => {
          if (!cancelled) setCatalogMatches(items);
        })
        .catch(() => {
          if (!cancelled) setCatalogMatches([]);
        });
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [isOpen, query, searchFocused]);

  async function loadWorkspaceData(forceRefreshWatchlist = false, targetListId?: string | null) {
    setWatchlistLoading(true);
    try {
      const alreadySeeded =
        typeof window !== "undefined" &&
        window.localStorage.getItem(WATCHLIST_SEED_STORAGE_KEY) === "1";
      const storedListId =
        typeof window !== "undefined" ? window.localStorage.getItem(WATCHLIST_ACTIVE_LIST_KEY) : null;
      const listParam =
        targetListId !== undefined ? targetListId : (activeListId ?? storedListId);

      // Si l'ID mémorisé localement n'existe plus côté BDD, retomber proprement sur la liste par défaut
      const wlState = await fetchWatchlistState(
        !alreadySeeded,
        true,
        listParam,
        forceRefreshWatchlist,
      ).catch(async () => {
        if (listParam) {
          return fetchWatchlistState(!alreadySeeded, true, null, forceRefreshWatchlist);
        }
        throw new Error("Impossible de charger les listes de suivi depuis la base de données.");
      });

      const resolvedId = wlState.active_list_id || null;
      setWatchlist(wlState.items || []);
      setWatchlists(wlState.lists || []);
      setActiveListId(resolvedId);
      setHeroFollowListId(prev => prev || resolvedId || "");
      if (typeof window !== "undefined") {
        if (resolvedId) {
          window.localStorage.setItem(WATCHLIST_ACTIVE_LIST_KEY, resolvedId);
        }
        if (!alreadySeeded) {
          window.localStorage.setItem(WATCHLIST_SEED_STORAGE_KEY, "1");
        }
      }

      const [inds, idxRes] = await Promise.all([
        fetchCustomIndicators().catch(() => null),
        fetchPrincipalIndices(true).catch(() => null),
      ]);
      if (inds) setCustomIndicators(inds);
      if (idxRes) {
        setIndices(idxRes.indices || []);
        setWarehouseStats(idxRes.warehouse || null);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impossible d'actualiser les listes de suivi.");
    } finally {
      setWatchlistLoading(false);
    }
  }

  async function handleSelectWatchlistTab(listId: string) {
    setActiveListId(listId);
    setHeroFollowListId(listId);
    if (typeof window !== "undefined") {
      if (listId) {
        window.localStorage.setItem(WATCHLIST_ACTIVE_LIST_KEY, listId);
      } else {
        window.localStorage.removeItem(WATCHLIST_ACTIVE_LIST_KEY);
      }
    }
    setWatchlistLoading(true);
    try {
      const wlState = await fetchWatchlistState(false, true, listId || null);
      setWatchlist(wlState.items || []);
      setWatchlists(wlState.lists || []);
      const resolvedId = wlState.active_list_id || listId || null;
      setActiveListId(resolvedId);
      if (typeof window !== "undefined" && resolvedId) {
        window.localStorage.setItem(WATCHLIST_ACTIVE_LIST_KEY, resolvedId);
      }
    } finally {
      setWatchlistLoading(false);
    }
  }

  async function handleCreateWatchlist(name: string) {
    const created = await createWatchlist(name);
    setWatchlists(prev => [...prev, created]);
    await handleSelectWatchlistTab(created.id);
  }

  async function handleRenameWatchlist(listId: string, name: string) {
    const updated = await renameWatchlist(listId, name);
    setWatchlists(prev => prev.map(l => (l.id === listId ? updated : l)));
  }

  async function handleDeleteWatchlist(listId: string) {
    await deleteWatchlist(listId);
    const nextLists = watchlists.filter(l => l.id !== listId);
    setWatchlists(nextLists);
    const fallbackId = nextLists[0]?.id || null;
    await handleSelectWatchlistTab(fallbackId || "");
  }

  const activeIndexPerformances = useMemo(() => {
    if (!activeIndexCode) return null;
    return (
      indexPerformancesByCode[activeIndexCode] ||
      Object.values(indexPerformancesByCode).find(
        p => p.index.code === activeIndexCode || p.index.eod_ticker === activeIndexCode,
      ) ||
      null
    );
  }, [activeIndexCode, indexPerformancesByCode]);

  async function handleToggleIndex(code: string, forceRefresh = false) {
    if (!forceRefresh && activeIndexCode === code) {
      setActiveIndexCode(null);
      setIndexComposition(null);
      setIndexImportBanner(null);
      setIndexError(null);
      return;
    }
    setIndxCatalogOpen(false);
    setEufundCatalogOpen(false);
    setActiveIndexCode(code);
    setIndexImportBanner(null);
    setIndexLoading(true);
    setIndexError(null);
    window.requestAnimationFrame(() => {
      modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
    try {
      const [compRes, cachedPerfRes] = await Promise.all([
        fetchIndexComposition(code, forceRefresh),
        !forceRefresh ? fetchCachedIndexPerformances(code).catch(() => null) : Promise.resolve(null),
      ]);
      setIndexComposition(compRes);
      if (
        cachedPerfRes &&
        ((cachedPerfRes.summary.synced_today_count ?? 0) > 0 || cachedPerfRes.summary.loaded_count > 0)
      ) {
        setIndexPerformancesByCode(prev => ({
          ...prev,
          [code]: cachedPerfRes,
          [cachedPerfRes.index.code]: cachedPerfRes,
        }));
        if (cachedPerfRes.warehouse) setWarehouseStats(cachedPerfRes.warehouse);
      }
      if (
        compRes.constituents.length > 0 &&
        compRes.constituents.length <= 120 &&
        (cachedPerfRes?.summary.loaded_count ?? 0) < compRes.constituents.length
      ) {
        void handleLoadIndexPerformances(code, false);
      }
    } catch (err: any) {
      setIndexError(err?.message || "Impossible de charger la composition de l'indice.");
    } finally {
      setIndexLoading(false);
    }
  }

  async function handleLoadIndexPerformances(code: string, forceRefresh = false) {
    if (!code || indexPerfLoading) return;
    setIndexPerfLoading(true);
    setIndexError(null);
    try {
      const res = await loadIndexPerformances(code, forceRefresh);
      setIndexPerformancesByCode(prev => ({
        ...prev,
        [code]: res,
        [res.index.code]: res,
      }));
      if (res.warehouse) setWarehouseStats(res.warehouse);
      setIndexComposition(prev =>
        prev
          ? {
              ...prev,
              index: {
                ...prev.index,
                cached_count: res.index.cached_count,
                synced_today_count: res.index.synced_today_count,
              },
              constituents: prev.constituents.map(c => {
                const match = res.items.find(it => it.symbol === c.symbol);
                return match
                  ? {
                      ...c,
                      cached_in_warehouse: match.cached_in_warehouse,
                      price: match.price,
                      currency: match.currency,
                      change_1d_pct: match.change_1d_pct,
                      sparkline: match.sparkline ?? c.sparkline,
                    }
                  : c;
              }),
            }
          : prev,
      );
    } catch (err: any) {
      setIndexError(err?.message || "Impossible de charger les performances de l'indice.");
    } finally {
      setIndexPerfLoading(false);
    }
  }

  async function handleImportIndexToWatchlist(code: string) {
    if (!code || indexImportBusy) return;
    setIndexImportBusy(true);
    setIndexImportBanner(null);
    setIndexError(null);
    try {
      const res = await importIndexToWatchlist(code);
      setWatchlists(prev => {
        const exists = prev.some(l => l.id === res.list.id);
        return exists ? prev.map(l => (l.id === res.list.id ? res.list : l)) : [...prev, res.list];
      });
      setIndexImportBanner(
        res.added_count > 0
          ? `${res.added_count} valeurs ajoutées à la liste « ${res.list.name} » (${res.list.items_count} au total).`
          : `Toutes les valeurs de l'indice sont déjà présentes dans la liste « ${res.list.name} ».`,
      );
      toggleWatchlistSidebar(true);
      await handleSelectWatchlistTab(res.list.id);
    } catch (err: any) {
      setIndexError(err?.message || "Impossible d'importer l'indice dans une liste.");
    } finally {
      setIndexImportBusy(false);
    }
  }

  function handleOpenMinorTier() {
    if (minorQuotesLoaded) return;
    setMinorQuotesLoaded(true);
    fetchPrincipalIndices(true, "all")
      .then(r => {
        setIndices(r.indices || []);
        setWarehouseStats(r.warehouse || null);
      })
      .catch(() => {});
  }

  async function handleSelectIndexStock(item: IndexConstituent) {
    const target = item.eod_ticker || item.yahoo_symbol || item.symbol;
    setQuery(item.name || target);
    setSearchFocused(false);
    await loadDetails(target);
    fetchPrincipalIndices(false)
      .then(r => {
        setIndices(r.indices || []);
        setWarehouseStats(r.warehouse || null);
      })
      .catch(() => {});
  }

  async function handleAddIndexStockToWatchlist(item: IndexConstituent) {
    const target = item.eod_ticker || item.yahoo_symbol || item.symbol;
    await handleAddWatchlistStock(target);
  }

  async function handleSelectEufund(item: EodhdEufundItem) {
    const target = item.eod_ticker || item.symbol;
    setQuery(item.name || target);
    setSearchFocused(false);
    await loadDetails(target);
  }

  async function handleAddEufundToWatchlist(item: EodhdEufundItem, targetListId?: string | null) {
    const target = item.eod_ticker || item.symbol;
    await handleAddWatchlistStock(target, targetListId);
  }

  function persistChartTabs(nextTabs: ChartTabConfig[], nextActiveId?: string) {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(CHART_TABS_STORAGE_KEY, JSON.stringify(nextTabs));
      if (nextActiveId !== undefined) {
        window.localStorage.setItem(ACTIVE_CHART_TAB_STORAGE_KEY, nextActiveId);
      }
    } catch {
      // Ignore storage quota errors
    }
  }

  function updateChartTab(tabIdToUpdate: string, updater: (prev: ChartTabConfig) => ChartTabConfig) {
    setChartTabs(prev => {
      const next = prev.map(t => (t.id === tabIdToUpdate ? updater(t) : t));
      persistChartTabs(next);
      return next;
    });
  }

  async function ensureBarsForTab(tab: ChartTabConfig, targetData: FinancialDashboardData | null = data) {
    if (!targetData) return;
    const symbolTarget = targetData.eod_ticker || targetData.yahoo_symbol || targetData.symbol;
    if (!symbolTarget) return;
    const tf = tab.timeframe;
    if (tf === "1d" || tf === "1w") {
      if (intradayBarsByRange[tf]) return;
      setRangeLoading(true);
      try {
        const res = await fetchFinanceDetails(symbolTarget, tf);
        setIntradayBarsByRange(prev => ({ ...prev, [tf]: res.eod_bars || [] }));
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Impossible de charger cette durée intraday.");
      } finally {
        setRangeLoading(false);
      }
      return;
    }
    const widestDaily = getWidestDailyRange(chartTabs);
    const fetchRange = getDailyRangeRank(tf) > getDailyRangeRank(widestDaily) ? tf : widestDaily;
    if (
      getDailyRangeRank(tf) <= getDailyRangeRank(loadedDailyRange) &&
      (dailyBars.length > 0 || loadedDailyRange === fetchRange)
    ) {
      return;
    }
    setRangeLoading(true);
    try {
      const res = await fetchFinanceDetails(symbolTarget, fetchRange);
      setDailyBars(res.eod_bars || []);
      setLoadedDailyRange(fetchRange);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impossible de charger cette durée d'affichage.");
    } finally {
      setRangeLoading(false);
    }
  }

  async function loadDetails(searchTarget: string) {
    const q = searchTarget.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setHoveredBarIndex(null);
    try {
      const widestDaily = getWidestDailyRange(chartTabs);
      const activeTf = activeChartTab.timeframe;
      const needsIntraday = activeTf === "1d" || activeTf === "1w";
      const [dailyRes, intradayRes] = await Promise.all([
        fetchFinanceDetails(q, widestDaily),
        needsIntraday ? fetchFinanceDetails(q, activeTf).catch(() => null) : Promise.resolve(null),
      ]);
      setData(dailyRes);
      setDailyBars(dailyRes.eod_bars || []);
      setLoadedDailyRange(widestDaily);
      setIntradayBarsByRange(
        needsIntraday && intradayRes?.eod_bars ? { [activeTf]: intradayRes.eod_bars } : {},
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Impossible de charger les données financières pour cette action.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectWatchlistStock(item: WatchlistItem) {
    const target = item.eod_ticker || item.yahoo_symbol || item.symbol;
    setQuery(item.name || item.symbol);
    if (mainTab === "search_indices") {
      setMainTab("fundamentals");
    }
    await loadDetails(target);
    window.requestAnimationFrame(() => {
      modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  async function handleAddWatchlistStock(symbolInput: string, targetListId?: string | null) {
    const destId = targetListId === undefined ? activeListId : targetListId;
    const created = await addWatchlistItem(symbolInput, destId);
    if (!destId || destId === activeListId) {
      setWatchlist(prev => {
        const exists = prev.some(entry => entry.id === created.id);
        return exists ? prev.map(entry => (entry.id === created.id ? created : entry)) : [...prev, created];
      });
    }
    setWatchlists(prev =>
      prev.map(l =>
        l.id === (created.list_id || destId)
          ? { ...l, items_count: l.items_count + (watchlist.some(w => w.id === created.id) ? 0 : 1) }
          : l,
      ),
    );
    if (typeof window !== "undefined") {
      window.localStorage.setItem(WATCHLIST_SEED_STORAGE_KEY, "1");
    }
  }

  async function handleHeroFollowCurrent() {
    if (!data || heroFollowBusy) return;
    const targetTicker = data.eod_ticker || data.yahoo_symbol || data.symbol;
    const destId = heroFollowListId || activeListId;
    setHeroFollowBusy(true);
    try {
      await handleAddWatchlistStock(targetTicker, destId);
      if (destId && destId !== activeListId) {
        await handleSelectWatchlistTab(destId);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impossible d'ajouter cette action au suivi.");
    } finally {
      setHeroFollowBusy(false);
    }
  }

  async function handleRemoveWatchlistStock(itemId: string) {
    await deleteWatchlistItem(itemId);
    setWatchlist(prev => prev.filter(entry => entry.id !== itemId));
    setWatchlists(prev =>
      prev.map(l => (l.id === activeListId ? { ...l, items_count: Math.max(0, l.items_count - 1) } : l)),
    );
  }

  async function handleUpdateWatchlistItemNote(itemId: string, note: string) {
    const updated = await updateWatchlistItemNote(itemId, note);
    setWatchlist(prev =>
      prev.map(entry => (entry.id === itemId ? { ...entry, note: updated.note ?? note } : entry)),
    );
  }

  async function handleReorderWatchlistItems(orderedIds: string[]) {
    if (!activeListId || orderedIds.length === 0) return;
    const previous = watchlist;
    const byId = new Map(previous.map(item => [item.id, item]));
    const reordered: WatchlistItem[] = [];
    const seen = new Set<string>();
    for (const id of orderedIds) {
      const found = byId.get(id);
      if (found && !seen.has(id)) {
        seen.add(id);
        reordered.push({ ...found, position: reordered.length });
      }
    }
    for (const item of previous) {
      if (!seen.has(item.id)) {
        reordered.push({ ...item, position: reordered.length });
      }
    }
    setWatchlist(reordered);
    try {
      await reorderWatchlistItems(activeListId, reordered.map(item => item.id));
    } catch (err) {
      setWatchlist(previous);
      throw err;
    }
  }

  async function handleSeedDefaults() {
    setWatchlistLoading(true);
    try {
      const seeded = await seedDefaultWatchlist(activeListId);
      setWatchlist(seeded);
      setWatchlists(prev =>
        prev.map(l => (l.id === activeListId ? { ...l, items_count: seeded.length } : l)),
      );
      if (typeof window !== "undefined") {
        window.localStorage.setItem(WATCHLIST_SEED_STORAGE_KEY, "1");
      }
    } finally {
      setWatchlistLoading(false);
    }
  }

  async function handleSaveCustomIndicator(payload: {
    id?: string;
    name: string;
    formula: string;
    pane: "overlay" | "oscillator";
    series_type: "line" | "histogram" | "dots";
    color: string;
    guide_lines: CustomIndicatorGuideLine[];
    enabled_by_default: boolean;
  }) {
    if (payload.id) {
      const updated = await updateCustomIndicator(payload.id, {
        name: payload.name,
        formula: payload.formula,
        pane: payload.pane,
        series_type: payload.series_type,
        color: payload.color,
        guide_lines: payload.guide_lines,
        enabled_by_default: payload.enabled_by_default,
      });
      setCustomIndicators(prev => prev.map(item => (item.id === updated.id ? updated : item)));
    } else {
      const created = await createCustomIndicator({
        name: payload.name,
        formula: payload.formula,
        pane: payload.pane,
        series_type: payload.series_type,
        color: payload.color,
        guide_lines: payload.guide_lines,
        enabled_by_default: payload.enabled_by_default,
      });
      setCustomIndicators(prev => [...prev, created]);
      if (created.enabled_by_default) {
        updateChartTab(activeChartTab.id, prev => ({
          ...prev,
          activeCustomIds: prev.activeCustomIds.includes(created.id)
            ? prev.activeCustomIds
            : [...prev.activeCustomIds, created.id],
        }));
      }
    }
  }

  async function handleDeleteCustomIndicator(indicatorId: string) {
    await deleteCustomIndicator(indicatorId);
    setCustomIndicators(prev => prev.filter(item => item.id !== indicatorId));
    setChartTabs(prev => {
      const next = prev.map(t =>
        t.activeCustomIds.includes(indicatorId)
          ? { ...t, activeCustomIds: t.activeCustomIds.filter(id => id !== indicatorId) }
          : t,
      );
      persistChartTabs(next);
      return next;
    });
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) {
      void loadDetails(query.trim());
    }
  }

  function handleSelectChartTab(nextTabId: string) {
    const nextTab = chartTabs.find(t => t.id === nextTabId);
    if (!nextTab) return;
    setActiveChartTabId(nextTabId);
    setHoveredBarIndex(null);
    persistChartTabs(chartTabs, nextTabId);
    void ensureBarsForTab(nextTab);
  }

  function handleAddChartTab() {
    const newId = `tab-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const newTab: ChartTabConfig = {
      id: newId,
      name: `Vue ${chartTabs.length + 1}`,
      barInterval: "day",
      timeframe: "1y",
      chartView: "advanced",
      activeNative: ["sma20", "volume", "rsi"],
      activeCustomIds: [],
      indicatorParams: loadIndicatorParams(),
      customFills: loadCustomIndicatorFills(),
    };
    setChartTabs(prev => {
      const next = [...prev, newTab];
      persistChartTabs(next, newId);
      return next;
    });
    setActiveChartTabId(newId);
    setHoveredBarIndex(null);
    void ensureBarsForTab(newTab);
  }

  function handleDuplicateChartTab(sourceId: string) {
    const source = chartTabs.find(t => t.id === sourceId);
    if (!source) return;
    const newId = `tab-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const copyTab: ChartTabConfig = {
      ...source,
      id: newId,
      name: `${source.name} (copie)`,
      activeNative: [...source.activeNative],
      activeCustomIds: [...source.activeCustomIds],
      indicatorParams: normalizeIndicatorParams(source.indicatorParams),
      customFills: { ...source.customFills },
    };
    setChartTabs(prev => {
      const idx = prev.findIndex(t => t.id === sourceId);
      const next =
        idx >= 0 ? [...prev.slice(0, idx + 1), copyTab, ...prev.slice(idx + 1)] : [...prev, copyTab];
      persistChartTabs(next, newId);
      return next;
    });
    setActiveChartTabId(newId);
    setHoveredBarIndex(null);
    void ensureBarsForTab(copyTab);
  }

  function handleDeleteChartTab(targetId: string) {
    if (chartTabs.length <= 1) return;
    const idx = chartTabs.findIndex(t => t.id === targetId);
    const nextTabs = chartTabs.filter(t => t.id !== targetId);
    let nextActive = activeChartTabId;
    if (activeChartTabId === targetId) {
      const fallback = nextTabs[Math.max(0, Math.min(idx, nextTabs.length - 1))] ?? nextTabs[0];
      nextActive = fallback.id;
      setActiveChartTabId(nextActive);
      setHoveredBarIndex(null);
      void ensureBarsForTab(fallback);
    }
    setChartTabs(nextTabs);
    persistChartTabs(nextTabs, nextActive);
  }

  function commitRenameChartTab() {
    if (!renamingChartTabId) return;
    const trimmed = renamingChartTabValue.trim();
    if (trimmed) {
      updateChartTab(renamingChartTabId, prev => ({ ...prev, name: trimmed }));
    }
    setRenamingChartTabId(null);
    setRenamingChartTabValue("");
  }

  function handleChangeBarInterval(interval: BarInterval) {
    setHoveredBarIndex(null);
    let nextTf = activeChartTab.timeframe;
    if (interval === "week") {
      if (nextTf === "1d" || nextTf === "1w" || nextTf === "1m" || nextTf === "3m") {
        nextTf = "2y";
      }
    } else if (interval === "month" || interval === "quarter") {
      if (!isDailyRange(nextTf) || getDailyRangeRank(nextTf) < getDailyRangeRank("5y")) {
        nextTf = "5y";
      }
    }
    const updatedTab: ChartTabConfig = {
      ...activeChartTab,
      barInterval: interval,
      timeframe: nextTf,
    };
    updateChartTab(activeChartTab.id, () => updatedTab);
    if (nextTf !== activeChartTab.timeframe) {
      void ensureBarsForTab(updatedTab);
    }
  }

  // Filter & aggregate bars according to active chart tab timeframe and bar interval
  const rawTabBars = useMemo(() => {
    if (!data) return [];
    const tf = activeChartTab.timeframe;
    if (tf === "1d" || tf === "1w") {
      return intradayBarsByRange[tf] ?? [];
    }
    const sourceDaily = dailyBars.length > 0 ? dailyBars : data.eod_bars || [];
    const limit = DAILY_RANGE_BAR_LIMITS[tf];
    return sourceDaily.length > limit ? sourceDaily.slice(-limit) : sourceDaily;
  }, [data, activeChartTab.timeframe, intradayBarsByRange, dailyBars]);

  const filteredBars = useMemo(() => {
    if (rawTabBars.length === 0) return [];
    return aggregateBars(rawTabBars, activeChartTab.barInterval);
  }, [rawTabBars, activeChartTab.barInterval]);

  const dividendSymbolTarget = data ? (data.eod_ticker || data.yahoo_symbol || data.symbol || "").trim() : "";
  const dividendSymbolKey = dividendSymbolTarget.toUpperCase();
  const showDividends = Boolean(activeChartTab.showDividends);
  const cachedDividendsEntry = dividendSymbolKey ? dividendsBySymbol[dividendSymbolKey] : undefined;
  const dividendsLoading = Boolean(
    showDividends && dividendSymbolKey && dividendsLoadingSymbol === dividendSymbolKey,
  );

  useEffect(() => {
    if (!showDividends || !dividendSymbolTarget || !dividendSymbolKey) return;
    if (dividendsBySymbol[dividendSymbolKey] && dividendsRetryNonce === 0) return;
    const controller = new AbortController();
    setDividendsLoadingSymbol(dividendSymbolKey);
    setDividendsError(null);
    fetchFinanceDividends(dividendSymbolTarget, dividendsRetryNonce > 0, controller.signal)
      .then(res => {
        if (controller.signal.aborted) return;
        setDividendsBySymbol(prev => ({
          ...prev,
          [dividendSymbolKey]: {
            items: res.dividends || [],
            currency: res.currency || data?.currency || "",
          },
        }));
        if (dividendsRetryNonce > 0) setDividendsRetryNonce(0);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setDividendsError(
          err instanceof Error ? err.message : "Impossible de charger les versements de dividendes.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDividendsLoadingSymbol(prev => (prev === dividendSymbolKey ? null : prev));
        }
      });
    return () => controller.abort();
  }, [showDividends, dividendSymbolTarget, dividendSymbolKey, dividendsBySymbol, dividendsRetryNonce, data?.currency]);

  const projectedDividends = useMemo<ProjectedBarDividend[]>(() => {
    if (!showDividends || !cachedDividendsEntry || filteredBars.length === 0) return [];
    return projectDividendsToBars(
      filteredBars,
      cachedDividendsEntry.items,
      activeChartTab.barInterval,
      cachedDividendsEntry.currency || data?.currency || "",
    );
  }, [showDividends, cachedDividendsEntry, filteredBars, activeChartTab.barInterval, data?.currency]);

  const dividendByDate = useMemo(() => {
    const map = new Map<string, ProjectedBarDividend>();
    for (const item of projectedDividends) {
      map.set(item.barDate.slice(0, 10), item);
    }
    return map;
  }, [projectedDividends]);

  const dividendByBarIndex = useMemo(() => {
    const map = new Map<number, ProjectedBarDividend>();
    for (const item of projectedDividends) {
      map.set(item.barIndex, item);
    }
    return map;
  }, [projectedDividends]);

  const dividendMarkers = useMemo(
    () => (showDividends ? buildDividendChartMarkers(projectedDividends, theme.mode === "dark") : []),
    [showDividends, projectedDividends, theme.mode],
  );

  // Recharge la durée sélectionnée sur l'onglet actif si elle dépasse la profondeur déjà en mémoire
  async function changeTimeframe(tf: FinanceRange) {
    if (tf === activeChartTab.timeframe || !data) return;
    setHoveredBarIndex(null);
    const updatedTab: ChartTabConfig = {
      ...activeChartTab,
      timeframe: tf,
    };
    updateChartTab(activeChartTab.id, () => updatedTab);
    await ensureBarsForTab(updatedTab);
  }

  // Timeframe stats calculation
  const timeframeStats = useMemo(() => {
    if (filteredBars.length < 2) return null;
    const firstClose = filteredBars[0].close ?? 0;
    const lastClose = filteredBars[filteredBars.length - 1].close ?? 0;
    const diff = lastClose - firstClose;
    const diffPct = firstClose > 0 ? (diff / firstClose) * 100 : 0;
    const high = Math.max(...filteredBars.map(b => b.high ?? b.close ?? 0));
    const low = Math.min(...filteredBars.map(b => b.low ?? b.close ?? 9999999));
    return {
      diff,
      diffPct,
      high,
      low,
      isPositive: diff >= 0,
    };
  }, [filteredBars]);

  const activeBar = hoveredBarIndex != null ? filteredBars[hoveredBarIndex] : null;

  function copyMarkdownSummary() {
    if (!data) return;
    const stats = data.financial_stats;
    const text = [
      `# 📈 ${data.long_name} (${data.symbol})`,
      `> Cotation en direct EOD : **${data.price} ${data.currency}** (${data.change_percent ? (data.change_percent >= 0 ? "+" : "") + data.change_percent.toFixed(2) + "%" : "N/A"})`,
      "",
      `### 📊 Valorisation & Multiples (Yahoo Finance)`,
      `- Capitalisation : ${stats.valuation.market_cap || "N/A"}`,
      `- Ratio P/E actuel : ${stats.valuation.pe_trailing || "N/A"} (Forward : ${stats.valuation.pe_forward || "N/A"})`,
      `- Ratio PEG : ${stats.valuation.peg_ratio || "N/A"} · P/B : ${stats.valuation.price_to_book || "N/A"}`,
      `- EV/EBITDA : ${stats.valuation.ev_to_ebitda || "N/A"} · Bêta : ${stats.valuation.beta || "N/A"}`,
      `- Dividende : ${stats.valuation.dividend_yield || "N/A"} (annuel : ${stats.valuation.dividend_rate || "N/A"})`,
      "",
      `### 💰 Rentabilité & Résultats`,
      `- Chiffre d'affaires : ${stats.profitability.total_revenue || "N/A"} (${stats.profitability.revenue_growth || "N/A"})`,
      `- Marge brute : ${stats.profitability.gross_margin || "N/A"} · Marge nette : ${stats.profitability.profit_margin || "N/A"}`,
      `- EBITDA : ${stats.profitability.ebitda || "N/A"}`,
      `- Free Cash Flow : ${stats.profitability.free_cashflow || "N/A"}`,
      "",
      `### 🎯 Consensus des Analystes`,
      `- Recommandation : ${stats.analysts.recommendation || "N/A"}`,
      `- Objectif moyen : ${stats.analysts.target_mean || "N/A"} (Haut : ${stats.analysts.target_high || "N/A"} / Bas : ${stats.analysts.target_low || "N/A"})`,
      `- Potentiel estimé : ${stats.analysts.upside_potential_pct != null ? (stats.analysts.upside_potential_pct >= 0 ? "+" : "") + stats.analysts.upside_potential_pct.toFixed(2) + "%" : "N/A"}`,
    ].join("\n");

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  }

  function insertIntoChat() {
    if (!data || !onInsertIntoChat) return;
    const summary = `Donne-moi une analyse détaillée de l'action **${data.long_name}** (${data.symbol}) avec son cours actuel (${data.price} ${data.currency}) et ses données financières clés.`;
    onInsertIntoChat(summary);
    onClose();
  }

  if (!isOpen) return null;

  function renderHeroBanner(showTabShortcuts = false) {
    if (!data) return null;
    return (
      <div className="finance-hero-banner">
        <div className="finance-hero-left">
          {/* Nom de l'action affichée + tickers */}
          <div className="finance-hero-identity">
            <div className="finance-hero-title-row">
              <h3 className="finance-hero-company-name">
                {data.long_name || data.short_name || data.symbol}
              </h3>
              <div className="finance-hero-tags">
                <span className="finance-symbol-tag" title="Symbole boursier principal">
                  {data.symbol}
                </span>
                {data.yahoo_symbol && data.yahoo_symbol !== data.symbol && (
                  <span className="finance-symbol-tag is-alt" title="Ticker Yahoo Finance">
                    Yahoo: {data.yahoo_symbol}
                  </span>
                )}
                {data.exchange && (
                  <span className="finance-exchange-tag" title="Place boursière">
                    {data.exchange}
                  </span>
                )}
                {data.isin && (
                  <span className="finance-isin-tag" title="Code ISIN">
                    ISIN: {data.isin}
                  </span>
                )}
                {(() => {
                  const targetListId = heroFollowListId || activeListId;
                  const isFollowedInActive =
                    (!targetListId || targetListId === activeListId) &&
                    watchlist.some(w => {
                      const curSet = new Set(
                        [data.symbol, data.yahoo_symbol, data.eod_ticker]
                          .filter(Boolean)
                          .map(s => String(s).toUpperCase()),
                      );
                      return (
                        curSet.has(w.symbol.toUpperCase()) ||
                        curSet.has(w.yahoo_symbol.toUpperCase()) ||
                        curSet.has(w.eod_ticker.toUpperCase())
                      );
                    });
                  return (
                    <span className="finance-hero-follow-group">
                      {watchlists.length > 1 && (
                        <select
                          className="finance-hero-follow-select"
                          value={targetListId || ""}
                          onChange={e => setHeroFollowListId(e.target.value)}
                          aria-label="Choisir la liste cible"
                          title="Liste dans laquelle ajouter l'action"
                        >
                          {watchlists.map(wl => (
                            <option key={wl.id} value={wl.id}>
                              {wl.name}
                            </option>
                          ))}
                        </select>
                      )}
                      <button
                        type="button"
                        className={`finance-hero-follow-btn ${isFollowedInActive ? "is-followed" : ""}`}
                        onClick={() => void handleHeroFollowCurrent()}
                        disabled={heroFollowBusy}
                        title={
                          isFollowedInActive
                            ? "Action déjà suivie dans cette liste"
                            : "Ajouter cette action à la liste de suivi"
                        }
                      >
                        {heroFollowBusy ? (
                          <LoaderCircle size={13} className="spin" />
                        ) : isFollowedInActive ? (
                          <Check size={13} />
                        ) : (
                          <Plus size={13} />
                        )}
                        <span>{isFollowedInActive ? "Suivie" : "Suivre"}</span>
                      </button>
                    </span>
                  );
                })()}
              </div>
            </div>
            {data.short_name && data.long_name && data.short_name !== data.long_name && (
              <p className="finance-hero-company-sub">{data.short_name}</p>
            )}
          </div>

          <div className="finance-price-row">
            <span className="finance-hero-price">
              {data.price != null ? data.price.toFixed(2) : "N/A"}{" "}
              <small className="finance-hero-curr">{data.currency}</small>
            </span>
            {data.change_percent != null && (
              <span
                className={`finance-hero-change ${data.change_percent >= 0 ? "is-up" : "is-down"}`}
              >
                {data.change_percent >= 0 ? (
                  <ArrowUpRight size={18} />
                ) : (
                  <ArrowDownRight size={18} />
                )}
                <span>
                  {data.change ? `${data.change >= 0 ? "+" : ""}${data.change.toFixed(2)} ` : ""}
                  ({data.change_percent >= 0 ? "+" : ""}
                  {data.change_percent.toFixed(2)}%)
                </span>
              </span>
            )}
          </div>
          <div className="finance-hero-sub-stats">
            <span>
              Ouv. : <strong>{data.open != null ? data.open.toFixed(2) : "-"}</strong>
            </span>
            <span>·</span>
            <span>
              Haut : <strong>{data.high != null ? data.high.toFixed(2) : "-"}</strong>
            </span>
            <span>·</span>
            <span>
              Bas : <strong>{data.low != null ? data.low.toFixed(2) : "-"}</strong>
            </span>
            <span>·</span>
            <span>
              Volume :{" "}
              <strong>
                {data.volume != null ? data.volume.toLocaleString("fr-FR") : "-"}
              </strong>
            </span>
            <span>·</span>
            <span>
              Clôt. veille :{" "}
              <strong>
                {data.previous_close != null ? data.previous_close.toFixed(2) : "-"}
              </strong>
            </span>
          </div>
        </div>

        <div className="finance-hero-right">
          {(() => {
            const recInfo = formatAnalystRecommendation(data.financial_stats.analysts.recommendation);
            const rawTarget = data.financial_stats.analysts.target_mean;
            const hasValidTarget = rawTarget && rawTarget !== "N/A" && rawTarget.trim() !== "";
            const hasOpinions = !!data.financial_stats.analysts.opinions_count;
            return (
              <div className="finance-analyst-badge-hero">
                <div className="finance-analyst-hero-header">
                  <span className="finance-analyst-hero-label">Consensus Analystes</span>
                  {hasOpinions && (
                    <span className="finance-analyst-hero-count">
                      ({data.financial_stats.analysts.opinions_count} avis)
                    </span>
                  )}
                </div>
                <div className="finance-analyst-hero-body">
                  <span className={`finance-rec-pill tone-${recInfo.tone}`}>
                    {recInfo.label}
                  </span>
                  {hasValidTarget ? (
                    <div className="finance-analyst-hero-target-wrap">
                      <span className="finance-analyst-hero-target">
                        Obj. moyen : <strong>{data.financial_stats.analysts.target_mean} {data.currency}</strong>
                      </span>
                      {data.financial_stats.analysts.upside_potential_pct != null && (
                        <span
                          className={`finance-upside-chip ${
                            data.financial_stats.analysts.upside_potential_pct >= 0 ? "is-up" : "is-down"
                          }`}
                        >
                          {data.financial_stats.analysts.upside_potential_pct >= 0 ? "+" : ""}
                          {data.financial_stats.analysts.upside_potential_pct.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="finance-analyst-hero-no-target">Objectif non renseigné</span>
                  )}
                </div>
              </div>
            );
          })()}

          {showTabShortcuts && (
            <div className="finance-hero-tab-shortcuts">
              <button
                type="button"
                className="finance-hero-shortcut-btn"
                onClick={() => switchMainTab("fundamentals")}
              >
                <ClipboardList size={13} />
                <span>Fondamentaux &amp; Ratios</span>
                <ChevronRight size={13} />
              </button>
              <button
                type="button"
                className="finance-hero-shortcut-btn is-primary"
                onClick={() => switchMainTab("chart_tech")}
              >
                <LineChart size={13} />
                <span>Cours &amp; Indicateurs techniques</span>
                <ChevronRight size={13} />
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="modal-backdrop finance-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-container finance-modal-container"
        onClick={e => e.stopPropagation()}
        aria-label="Tableau de bord financier & Courbe de cours"
      >
        {/* Header */}
        <div className="finance-modal-header">
          <div className="finance-modal-header-top">
            <div className="finance-modal-title-wrap">
              <span className="finance-modal-badge-icon">
                <LineChart size={20} />
              </span>
              <div>
                <div className="finance-modal-title-row">
                  <h2>{data?.short_name || "Analyse Boursière"}</h2>
                  {data?.symbol && <span className="finance-symbol-tag">{data.symbol}</span>}
                  <div className="finance-source-pills">
                    <span className="finance-live-pill is-eod" title="Cotations en direct et historique de marché">
                      EOD Historical Data
                    </span>
                    <span className="finance-live-pill is-yahoo" title="États financiers, valorisation et consensus">
                      Yahoo Finance
                    </span>
                  </div>
                </div>
                <p className="finance-modal-sub">
                  {data?.long_name
                    ? `${data.long_name} · Marché : ${data.exchange}${data.isin ? ` · ISIN : ${data.isin}` : ""}`
                    : "Cours de bourse en temps réel & données financières complètes"}
                </p>
              </div>
            </div>

            <div className="finance-modal-header-actions">
              {syncProgress?.is_running && (
                <button
                  type="button"
                  className="finance-sync-live-pill"
                  onClick={() => switchMainTab("data_sync")}
                  title="Synchronisation / mise à jour en cours — cliquer pour ouvrir l'onglet 5 · Données & Synchro"
                >
                  <LoaderCircle size={13} className="spin" />
                  <span>
                    {syncProgress.current_label || "Synchro auto en cours…"}
                    {syncProgress.total_steps > 0 ? ` (${syncProgress.percent}%)` : ""}
                  </span>
                </button>
              )}
              <button
                type="button"
                className={`finance-help-btn finance-wl-toggle-btn ${watchlistSidebarOpen ? "active" : ""}`}
                onClick={() => toggleWatchlistSidebar()}
                aria-expanded={watchlistSidebarOpen}
                title={
                  watchlistSidebarOpen
                    ? "Rétracter la barre des listes de suivi à droite"
                    : "Déplier la barre des listes de suivi à droite"
                }
              >
                {watchlistSidebarOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
                <span>Listes ({watchlist.length})</span>
              </button>
              <FinanceThemeSwitcher />
              <button
                type="button"
                className="finance-help-btn"
                onClick={() => openHelpGuide("intrinsic")}
                aria-label="Aide — Formules et Scores Uncle Stock"
                title="Guides détaillés : Valeurs intrinsèques (20 chapitres) & Scores Uncle Stock (36 chapitres)"
              >
                <HelpCircle size={16} />
                <span>Aide · Formules &amp; Scores</span>
              </button>
              <button
                type="button"
                className="finance-modal-close-btn"
                onClick={onClose}
                aria-label="Fermer la fenêtre Marchés Financiers"
                title="Fermer (Échap)"
              >
                <X size={20} />
              </button>
            </div>
          </div>

          <nav
            className="finance-main-tabs-nav"
            role="tablist"
            aria-label="Sections principales Finances"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "search_indices"}
              className={`finance-main-tab-btn ${mainTab === "search_indices" ? "active" : ""}`}
              onClick={() => switchMainTab("search_indices")}
            >
              <span className="finance-main-tab-num">1</span>
              <Search size={15} />
              <span className="finance-main-tab-label">Recherche &amp; Indices</span>
              <span className="finance-main-tab-meta">
                {activeIndexCode || (indices.length > 0 ? `${indices.length} indices` : "Actions · Fonds")}
              </span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "fundamentals"}
              className={`finance-main-tab-btn ${mainTab === "fundamentals" ? "active" : ""}`}
              onClick={() => switchMainTab("fundamentals")}
            >
              <span className="finance-main-tab-num">2</span>
              <ClipboardList size={15} />
              <span className="finance-main-tab-label">Fondamentaux &amp; Ratios</span>
              {data?.symbol && (
                <span className="finance-main-tab-meta">{data.symbol}</span>
              )}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "chart_tech"}
              className={`finance-main-tab-btn ${mainTab === "chart_tech" ? "active" : ""}`}
              onClick={() => switchMainTab("chart_tech")}
            >
              <span className="finance-main-tab-num">3</span>
              <LineChart size={15} />
              <span className="finance-main-tab-label">Cours &amp; Indicateurs techniques</span>
              {data?.price != null && (
                <span className="finance-main-tab-meta">
                  {data.price.toFixed(2)} {data.currency}
                </span>
              )}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "screener"}
              className={`finance-main-tab-btn ${mainTab === "screener" ? "active" : ""}`}
              onClick={() => switchMainTab("screener")}
            >
              <span className="finance-main-tab-num">4</span>
              <SlidersHorizontal size={15} />
              <span className="finance-main-tab-label">Screener</span>
              <span className="finance-main-tab-meta">Fondamental · Tech</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "data_sync"}
              className={`finance-main-tab-btn ${mainTab === "data_sync" ? "active" : ""}`}
              onClick={() => switchMainTab("data_sync")}
            >
              <span className="finance-main-tab-num">5</span>
              <Database size={15} />
              <span className="finance-main-tab-label">Données &amp; Synchro</span>
              <span className="finance-main-tab-meta">
                {syncProgress?.is_running ? `En cours ${syncProgress.percent}%` : "EODHD · Auto 24h"}
              </span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mainTab === "trading_game"}
              className={`finance-main-tab-btn ${mainTab === "trading_game" ? "active" : ""}`}
              onClick={() => switchMainTab("trading_game")}
            >
              <span className="finance-main-tab-num">6</span>
              <Trophy size={15} />
              <span className="finance-main-tab-label">Défi Replay</span>
              <span className="finance-main-tab-meta">Jeu · Aveugle</span>
            </button>
          </nav>
        </div>

        {/* Workspace : contenu principal à gauche + barre rétractable des listes à droite */}
        <div className="finance-modal-workspace">
          <div className="finance-modal-body" ref={modalBodyRef}>
            {error && (
              <div className="finance-modal-error" role="alert">
                <span>⚠️ {error}</span>
                <button type="button" onClick={() => void loadDetails(query)}>
                  <RefreshCw size={14} /> Réessayer
                </button>
              </div>
            )}

            {/* ONGLET 1 : Recherche, Suggestions, Indices & Catalogues */}
            {(mainTab === "search_indices" || mountedMainTabs.search_indices) && (
              <div hidden={mainTab !== "search_indices"}>
                <div className="finance-modal-search-bar">
                  <div className="finance-search-autocomplete-wrap">
                    <form className="finance-search-form" onSubmit={handleSearchSubmit}>
                      <Search size={16} className="finance-search-icon" />
                      <input
                        type="text"
                        className="finance-search-input"
                        placeholder="Rechercher une action, un fonds EUFUND, un ISIN ou ticker (ex. Air Liquide, NVDA, FR0013202132.EUFUND)..."
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onFocus={() => setSearchFocused(true)}
                        onBlur={() => {
                          window.setTimeout(() => setSearchFocused(false), 180);
                        }}
                        disabled={loading}
                      />
                      <button type="submit" className="finance-search-submit" disabled={loading || !query.trim()}>
                        {loading ? <LoaderCircle size={15} className="spin" /> : "Rechercher"}
                      </button>
                    </form>
                    {visibleCatalogMatches.length > 0 && (
                      <div className="finance-search-dropdown" role="listbox" aria-label="Suggestions catalogue et entrepôt">
                        {visibleCatalogMatches.map(m => (
                          <button
                            key={`${m.eod_ticker}-${m.index_code ?? ""}`}
                            type="button"
                            className="finance-search-dropdown-item"
                            onMouseDown={e => {
                              e.preventDefault();
                              setQuery(m.name || m.eod_ticker);
                              setSearchFocused(false);
                              void loadDetails(m.eod_ticker || m.yahoo_symbol || m.symbol);
                            }}
                          >
                            <span className="finance-symbol-tag">{m.eod_ticker || m.yahoo_symbol || m.symbol}</span>
                            <strong className="finance-search-dropdown-name">{m.name}</strong>
                            {m.sector && <small className="finance-search-dropdown-meta">{m.sector}</small>}
                            {(m.index_code || m.exchange) && (
                              <span className="finance-search-dropdown-idx">{m.index_code || m.exchange}</span>
                            )}
                            {m.cached && <span className="finance-cached-dot" title="Déjà en entrepôt local" />}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="finance-quick-chips">
                    <span className="finance-chips-label">Suggestions :</span>
                    {QUICK_SUGGESTIONS.map(name => (
                      <button
                        key={name}
                        type="button"
                        className={`finance-chip ${data?.short_name?.toLowerCase().includes(name.toLowerCase()) ? "active" : ""}`}
                        onClick={() => {
                          setQuery(name);
                          void loadDetails(name);
                        }}
                        disabled={loading}
                      >
                        {name}
                      </button>
                    ))}
                  </div>

                  <FinanceIndicesStrip
                    indices={indices}
                    warehouse={warehouseStats}
                    activeCode={activeIndexCode}
                    loadingIndex={indexLoading}
                    catalogOpen={indxCatalogOpen}
                    eufundCatalogOpen={eufundCatalogOpen}
                    syncOpen={mainTab === "data_sync"}
                    onToggleIndex={code => void handleToggleIndex(code)}
                    onToggleCatalog={() => {
                      setEufundCatalogOpen(false);
                      setIndxCatalogOpen(prev => {
                        const next = !prev;
                        if (next) {
                          window.requestAnimationFrame(() => {
                            modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
                          });
                        }
                        return next;
                      });
                      setActiveIndexCode(null);
                    }}
                    onToggleEufundCatalog={() => {
                      setIndxCatalogOpen(false);
                      setActiveIndexCode(null);
                      setEufundCatalogOpen(prev => {
                        const next = !prev;
                        if (next) {
                          window.requestAnimationFrame(() => {
                            modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
                          });
                        }
                        return next;
                      });
                    }}
                    onToggleSync={() => {
                      switchMainTab("data_sync");
                    }}
                    onOpenMinorTier={handleOpenMinorTier}
                  />
                </div>

                {data && renderHeroBanner(true)}

                {indxCatalogOpen && (
                  <FinanceEodhdIndxBrowser
                    activeCode={activeIndexCode}
                    onSelectIndexCode={eodTicker => void handleToggleIndex(eodTicker)}
                    onClose={() => setIndxCatalogOpen(false)}
                  />
                )}

                {eufundCatalogOpen && (
                  <FinanceEufundBrowser
                    selectedSymbol={data?.eod_ticker || data?.yahoo_symbol || data?.symbol || null}
                    watchlists={watchlists}
                    activeListId={activeListId}
                    onSelectFund={item => void handleSelectEufund(item)}
                    onAddWatchlist={handleAddEufundToWatchlist}
                    onClose={() => setEufundCatalogOpen(false)}
                  />
                )}

                {activeIndexCode && (
                  <FinanceIndexCompositionDrawer
                    key={activeIndexCode}
                    composition={
                      indexComposition &&
                      (indexComposition.index.code === activeIndexCode ||
                        indexComposition.index.eod_ticker === activeIndexCode)
                        ? indexComposition
                        : null
                    }
                    performances={activeIndexPerformances}
                    performancesLoading={indexPerfLoading}
                    importingWatchlist={indexImportBusy}
                    importBanner={indexImportBanner}
                    loading={indexLoading}
                    error={indexError}
                    selectedSymbol={data?.eod_ticker || data?.yahoo_symbol || data?.symbol || null}
                    onSelectStock={item => void handleSelectIndexStock(item)}
                    onAddWatchlist={handleAddIndexStockToWatchlist}
                    onLoadPerformances={forceRefresh => handleLoadIndexPerformances(activeIndexCode, Boolean(forceRefresh))}
                    onImportToWatchlist={() => handleImportIndexToWatchlist(activeIndexCode)}
                    onRefresh={() => void handleToggleIndex(activeIndexCode, true)}
                    onClose={() => {
                      setActiveIndexCode(null);
                      setIndexComposition(null);
                      setIndexImportBanner(null);
                      setIndexError(null);
                    }}
                  />
                )}

                {!activeIndexCode && !indxCatalogOpen && !eufundCatalogOpen && (
                  <div className="finance-search-tab-hint">
                    <Search size={16} />
                    <div>
                      <strong>Explorer les marchés, indices et fonds</strong>
                      <p>
                        Cliquez sur un indice ci-dessus (ex. CAC 40, S&amp;P 500, NASDAQ 100) ou ouvrez un
                        catalogue (.INDX, .EUFUND, PA, US) pour afficher sa composition, charger le tableau
                        de performances de toutes ses actions et les importer en liste de suivi.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {mainTab !== "search_indices" && mainTab !== "data_sync" && mainTab !== "trading_game" && loading && !data && (
              <div className="finance-modal-loading">
                <LoaderCircle size={36} className="spin text-emerald" />
                <p>Téléchargement des cours live et des états financiers (EOD Historical Data)…</p>
              </div>
            )}

            {/* ONGLET 4 : Screener boursier multi-critères */}
            {(mainTab === "screener" || mountedMainTabs.screener) && (
              <div hidden={mainTab !== "screener"}>
                <FinanceScreenerPanel
                  indices={indices}
                  watchlists={watchlists}
                  activeListId={activeListId}
                  onOpenStock={async (target, displayName, openTab) => {
                    setQuery(displayName || target);
                    setMainTab(openTab);
                    await loadDetails(target);
                    window.requestAnimationFrame(() => {
                      modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
                    });
                  }}
                  onWatchlistExported={async listId => {
                    toggleWatchlistSidebar(true);
                    await handleSelectWatchlistTab(listId);
                  }}
                  onOpenDataSync={() => switchMainTab("data_sync")}
                />
              </div>
            )}

            {/* ONGLET 5 : Gestion des données, EODHD & Synchronisations */}
            {(mainTab === "data_sync" || mountedMainTabs.data_sync) && (
              <div hidden={mainTab !== "data_sync"}>
                <FinanceSyncPanel
                  watchlists={watchlists}
                  activeListId={activeListId}
                  onSynced={() => {
                    void loadWorkspaceData(false);
                  }}
                />
              </div>
            )}

            {/* ONGLET 6 : Jeu Trading Replay */}
            {(mainTab === "trading_game" || mountedMainTabs.trading_game) && (
              <div hidden={mainTab !== "trading_game"}>
                <FinanceGamePanel
                  isActive={isOpen && mainTab === "trading_game"}
                  dark={theme.mode === "dark"}
                  indices={indices}
                  watchlists={watchlists}
                  activeListId={activeListId}
                  customIndicators={customIndicators}
                  onOpenStock={async (target, displayName, openTab) => {
                    setQuery(displayName || target);
                    setMainTab(openTab);
                    await loadDetails(target);
                    window.requestAnimationFrame(() => {
                      modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
                    });
                  }}
                  onOpenDataSync={() => switchMainTab("data_sync")}
                />
              </div>
            )}

            {/* ONGLET 3 : Cours & Indicateurs techniques */}
            {mainTab === "chart_tech" && data && (
              <>
                {renderHeroBanner(false)}
                <div
                  className={`finance-chart-section${chartFullscreen ? " is-fullscreen" : ""}`}
                  ref={chartSectionRef}
                >
                <div className="finance-chart-tabs-bar" role="tablist" aria-label="Onglets graphiques personnalisés">
                  <div className="finance-chart-tabs-list">
                    {chartTabs.map(tab => {
                      const isTabActive = tab.id === activeChartTab.id;
                      const isRenaming = renamingChartTabId === tab.id;
                      const indCount = tab.activeNative.length + tab.activeCustomIds.length;
                      return (
                        <div
                          key={tab.id}
                          className={`finance-chart-tab-item ${isTabActive ? "active" : ""}`}
                        >
                          {isRenaming ? (
                            <input
                              type="text"
                              className="finance-chart-tab-rename-input"
                              value={renamingChartTabValue}
                              autoFocus
                              onChange={e => setRenamingChartTabValue(e.target.value)}
                              onBlur={commitRenameChartTab}
                              onKeyDown={e => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  commitRenameChartTab();
                                } else if (e.key === "Escape") {
                                  e.preventDefault();
                                  setRenamingChartTabId(null);
                                  setRenamingChartTabValue("");
                                }
                              }}
                              aria-label="Nom de l'onglet graphique"
                            />
                          ) : (
                            <button
                              type="button"
                              role="tab"
                              aria-selected={isTabActive}
                              className="finance-chart-tab-select"
                              onClick={() => handleSelectChartTab(tab.id)}
                              onDoubleClick={() => {
                                setRenamingChartTabId(tab.id);
                                setRenamingChartTabValue(tab.name);
                              }}
                              title="Cliquer pour afficher · Double-cliquer pour renommer"
                            >
                              <span className="finance-chart-tab-name">{tab.name}</span>
                              <span className="finance-chart-tab-badge">
                                {BAR_INTERVAL_LABELS[tab.barInterval]} · {TIMEFRAME_LABELS[tab.timeframe]}
                              </span>
                              <span className="finance-chart-tab-ind-count" title={`${indCount} indicateur(s) actif(s)`}>
                                {indCount} ind.
                              </span>
                            </button>
                          )}
                          <span className="finance-chart-tab-actions">
                            <button
                              type="button"
                              className="finance-chart-tab-icon-btn"
                              onClick={() => {
                                setRenamingChartTabId(tab.id);
                                setRenamingChartTabValue(tab.name);
                              }}
                              title="Renommer cet onglet"
                              aria-label={`Renommer ${tab.name}`}
                            >
                              <Pencil size={11} />
                            </button>
                            <button
                              type="button"
                              className="finance-chart-tab-icon-btn"
                              onClick={() => handleDuplicateChartTab(tab.id)}
                              title="Dupliquer cet onglet"
                              aria-label={`Dupliquer ${tab.name}`}
                            >
                              <Copy size={11} />
                            </button>
                            {chartTabs.length > 1 && (
                              <button
                                type="button"
                                className="finance-chart-tab-icon-btn is-danger"
                                onClick={() => handleDeleteChartTab(tab.id)}
                                title="Supprimer cet onglet"
                                aria-label={`Supprimer ${tab.name}`}
                              >
                                <X size={11} />
                              </button>
                            )}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  <button
                    type="button"
                    className="finance-chart-tab-add-btn"
                    onClick={handleAddChartTab}
                    title="Ajouter un nouvel onglet graphique avec son propre pas et ses propres indicateurs"
                  >
                    <Plus size={13} />
                    <span>Nouvel onglet</span>
                  </button>
                </div>

                <div className="finance-chart-header">
                  <div className="finance-chart-title">
                    {chartFullscreen ? (
                      <FinanceFullscreenTickerSwitcher
                        currentSymbol={data.symbol}
                        currentEodTicker={data.eod_ticker}
                        currentYahooSymbol={data.yahoo_symbol}
                        currentName={data.long_name || data.short_name || data.symbol}
                        currentPrice={data.price}
                        currentCurrency={data.currency}
                        currentChangePct={data.change_percent}
                        loading={loading}
                        watchlist={watchlist}
                        watchlists={watchlists}
                        activeListId={activeListId}
                        watchlistLoading={watchlistLoading}
                        quickSuggestions={QUICK_SUGGESTIONS}
                        isOpen={fullscreenTickerOpen}
                        onOpenChange={setFullscreenTickerOpen}
                        onSelectTicker={async (target, displayName) => {
                          setQuery(displayName || target);
                          await loadDetails(target);
                        }}
                        onSelectWatchlistTab={handleSelectWatchlistTab}
                      />
                    ) : (
                      <span className="chart-icon-wrap">
                        <TrendingUp size={16} />
                      </span>
                    )}
                    <div>
                      {!chartFullscreen && (
                        <strong>
                          {data.long_name || data.short_name || data.symbol} ({data.symbol}) — {activeChartTab.name}
                        </strong>
                      )}
                      <small>
                        {filteredBars.length} points · {TIMEFRAME_LABELS[activeChartTab.timeframe]} · Barres :{" "}
                        {BAR_INTERVAL_LABELS[activeChartTab.barInterval]} ·{" "}
                        {timeframeStats ? (
                          <span className={timeframeStats.isPositive ? "text-emerald" : "text-rose"}>
                            {timeframeStats.diff >= 0 ? "+" : ""}
                            {timeframeStats.diff.toFixed(2)} {data.currency} (
                            {timeframeStats.diffPct >= 0 ? "+" : ""}
                            {timeframeStats.diffPct.toFixed(2)}%)
                          </span>
                        ) : (
                          "Données historiques de cotation"
                        )}
                      </small>
                    </div>
                  </div>

                  <div className="finance-chart-header-controls">
                    {chartFullscreen && (
                      <div className="finance-timeframe-selector finance-chart-view-toggle is-inline">
                        {(["advanced", "line"] as const).map(v => (
                          <button
                            key={v}
                            type="button"
                            className={`finance-tf-btn ${activeChartTab.chartView === v ? "active" : ""}`}
                            onClick={() =>
                              updateChartTab(activeChartTab.id, prev => ({ ...prev, chartView: v }))
                            }
                          >
                            {v === "line" ? "Courbe" : "Analyse technique"}
                          </button>
                        ))}
                      </div>
                    )}

                    <div className="finance-timeframe-selector" role="group" aria-label="Unité des barres" title="Unité des barres">
                      {(Object.keys(BAR_INTERVAL_LABELS) as BarInterval[]).map(interval => (
                        <button
                          key={interval}
                          type="button"
                          className={`finance-tf-btn ${activeChartTab.barInterval === interval ? "active" : ""}`}
                          onClick={() => handleChangeBarInterval(interval)}
                        >
                          {BAR_INTERVAL_LABELS[interval]}
                        </button>
                      ))}
                    </div>

                    <div className="finance-timeframe-selector">
                      {(Object.keys(TIMEFRAME_LABELS) as FinanceRange[]).map(tf => (
                        <button
                          key={tf}
                          type="button"
                          disabled={rangeLoading}
                          className={`finance-tf-btn ${activeChartTab.timeframe === tf ? "active" : ""}`}
                          onClick={() => void changeTimeframe(tf)}
                        >
                          {TIMEFRAME_LABELS[tf]}
                        </button>
                      ))}
                    </div>

                    <button
                      type="button"
                      className={`finance-tf-btn${showDividends ? " active" : ""}`}
                      aria-pressed={showDividends}
                      onClick={() => {
                        setDividendsError(null);
                        updateChartTab(activeChartTab.id, prev => ({
                          ...prev,
                          showDividends: !prev.showDividends,
                        }));
                      }}
                      title={
                        showDividends
                          ? "Masquer les versements de dividendes sur la courbe"
                          : "Afficher les versements de dividendes sur la courbe"
                      }
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 5,
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {dividendsLoading ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <Coins size={13} />
                      )}
                      <span>
                        Dividendes
                        {showDividends && cachedDividendsEntry
                          ? ` (${projectedDividends.length})`
                          : ""}
                      </span>
                    </button>

                    <button
                      type="button"
                      className={`finance-chart-fullscreen-btn${chartFullscreen ? " active" : ""}`}
                      onClick={() => {
                        setChartFullscreen(prev => {
                          if (prev) setFullscreenTickerOpen(false);
                          return !prev;
                        });
                      }}
                      title={
                        chartFullscreen
                          ? "Revenir au mode réduit (Échap)"
                          : "Passer la courbe et les indicateurs en plein écran"
                      }
                      aria-label={chartFullscreen ? "Revenir au mode réduit" : "Passer en plein écran"}
                    >
                      {chartFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                      <span>{chartFullscreen ? "Mode réduit" : "Plein écran"}</span>
                    </button>
                  </div>
                </div>

                {chartFullscreen && error && (
                  <div className="finance-modal-error" role="alert">
                    <span>⚠️ {error}</span>
                    <button type="button" onClick={() => setError(null)} aria-label="Fermer l'erreur">
                      <X size={14} /> Fermer
                    </button>
                  </div>
                )}

                {!chartFullscreen && (
                  <div className="finance-timeframe-selector finance-chart-view-toggle">
                    {(["advanced", "line"] as const).map(v => (
                      <button
                        key={v}
                        type="button"
                        className={`finance-tf-btn ${activeChartTab.chartView === v ? "active" : ""}`}
                        onClick={() =>
                          updateChartTab(activeChartTab.id, prev => ({ ...prev, chartView: v }))
                        }
                      >
                        {v === "line" ? "Courbe" : "Analyse technique"}
                      </button>
                    ))}
                  </div>
                )}

                {showDividends && dividendsError && (
                  <div className="finance-modal-error" role="alert" style={{ marginBottom: 8 }}>
                    <span>{dividendsError}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setDividendsError(null);
                        setDividendsRetryNonce(n => n + 1);
                      }}
                    >
                      <RefreshCw size={13} /> Réessayer
                    </button>
                  </div>
                )}

                {showDividends && !dividendsLoading && !dividendsError && cachedDividendsEntry && projectedDividends.length === 0 && (
                  <div
                    role="status"
                    style={{
                      fontSize: 12,
                      color: "var(--muted, #64748b)",
                      marginBottom: 8,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <Coins size={13} />
                    <span>Aucun versement de dividende détecté sur la période affichée.</span>
                  </div>
                )}

                {activeChartTab.chartView === "advanced" && (
                  <FinanceTvChart
                    bars={filteredBars}
                    symbol={data.symbol}
                    tabId={activeChartTab.id}
                    dark={theme.mode === "dark"}
                    fullscreen={chartFullscreen}
                    customIndicators={customIndicators}
                    activeNativeKeys={activeChartTab.activeNative}
                    onChangeActiveNativeKeys={keys =>
                      updateChartTab(activeChartTab.id, prev => ({ ...prev, activeNative: keys }))
                    }
                    activeCustomIds={activeChartTab.activeCustomIds}
                    onChangeActiveCustomIds={ids =>
                      updateChartTab(activeChartTab.id, prev => ({ ...prev, activeCustomIds: ids }))
                    }
                    indicatorParams={activeChartTab.indicatorParams}
                    onChangeIndicatorParams={nextParams =>
                      updateChartTab(activeChartTab.id, prev => ({ ...prev, indicatorParams: nextParams }))
                    }
                    customFills={activeChartTab.customFills}
                    onChangeCustomFills={nextFills =>
                      updateChartTab(activeChartTab.id, prev => ({ ...prev, customFills: nextFills }))
                    }
                    onOpenIndicatorEditor={ind => {
                      setEditingIndicator(ind ?? null);
                      setIndicatorModalOpen(true);
                    }}
                    onDeleteCustomIndicator={id => void handleDeleteCustomIndicator(id)}
                    markers={dividendMarkers}
                    dividendByDate={showDividends ? dividendByDate : undefined}
                  />
                )}

                {/* SVG Price Chart */}
                <div className="finance-svg-chart-container" hidden={activeChartTab.chartView === "advanced"}>
                  {filteredBars.length >= 2 ? (
                    <InteractivePriceChart
                      bars={filteredBars}
                      currency={data.currency}
                      hoveredIndex={hoveredBarIndex}
                      onHover={setHoveredBarIndex}
                      dividendsByBarIndex={showDividends ? dividendByBarIndex : undefined}
                    />
                  ) : (
                    <div className="finance-chart-empty">
                      <span>Données de courbe insuffisantes pour cette sélection</span>
                    </div>
                  )}

                  {/* Active Bar Hover Details Card */}
                  {activeBar && (
                    <div className="finance-chart-hover-pill">
                      <span>📅 {activeBar.date}</span>
                      <span>·</span>
                      <span>
                        Clôture : <strong>{activeBar.close?.toFixed(2)} {data.currency}</strong>
                      </span>
                      <span>·</span>
                      <span>Ouv. : {activeBar.open?.toFixed(2)}</span>
                      <span>·</span>
                      <span>Haut : {activeBar.high?.toFixed(2)}</span>
                      <span>·</span>
                      <span>Bas : {activeBar.low?.toFixed(2)}</span>
                      {activeBar.volume && (
                        <>
                          <span>·</span>
                          <span>Vol. : {activeBar.volume.toLocaleString("fr-FR")}</span>
                        </>
                      )}
                      {showDividends && hoveredBarIndex != null && dividendByBarIndex.get(hoveredBarIndex) && (
                        <>
                          <span>·</span>
                          <strong style={{ color: theme.mode === "dark" ? "#fbbf24" : "#b45309" }}>
                            {formatDividendHoverSummary(dividendByBarIndex.get(hoveredBarIndex)!)}
                          </strong>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
              </>
            )}

            {/* ONGLET 2 : Fondamentaux & Ratios classés par type */}
            {(mainTab === "fundamentals" || mountedMainTabs.fundamentals) && data && (
              <div hidden={mainTab !== "fundamentals"}>
                {renderHeroBanner(false)}
                <div className="finance-stats-section">
                  <div className="finance-tabs-nav">
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "dossier" ? "active" : ""}`}
                      onClick={() => setActiveTab("dossier")}
                    >
                      <ClipboardList size={15} />
                      <span>Fiche Complète</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "valuation" ? "active" : ""}`}
                      onClick={() => setActiveTab("valuation")}
                    >
                      <Target size={15} />
                      <span>Valorisation &amp; Multiples</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "profitability" ? "active" : ""}`}
                      onClick={() => setActiveTab("profitability")}
                    >
                      <TrendingUp size={15} />
                      <span>Rentabilité &amp; CA</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "balance_sheet" ? "active" : ""}`}
                      onClick={() => setActiveTab("balance_sheet")}
                    >
                      <Wallet size={15} />
                      <span>Bilan &amp; Trésorerie</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "fundamentals" ? "active" : ""}`}
                      onClick={() => setActiveTab("fundamentals")}
                    >
                      <BarChart3 size={15} />
                      <span>Fondamentaux (Historique)</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "analysts" ? "active" : ""}`}
                      onClick={() => setActiveTab("analysts")}
                    >
                      <Sparkles size={15} />
                      <span>Consensus Analystes</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "profile" ? "active" : ""}`}
                      onClick={() => setActiveTab("profile")}
                    >
                      <Building2 size={15} />
                      <span>Profil Entreprise</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "moat" ? "active" : ""}`}
                      onClick={() => setActiveTab("moat")}
                    >
                      <ShieldCheck size={15} />
                      <span>MOAT</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "experts" ? "active" : ""}`}
                      onClick={() => setActiveTab("experts")}
                    >
                      <Award size={15} />
                      <span>Avis de l&apos;expert</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "ai_history" ? "active" : ""}`}
                      onClick={() => setActiveTab("ai_history")}
                    >
                      <History size={15} />
                      <span>Archives IA</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "news" ? "active" : ""}`}
                      onClick={() => setActiveTab("news")}
                    >
                      <Newspaper size={15} />
                      <span>Actualités &amp; Veille</span>
                    </button>
                    <button
                      type="button"
                      className={`finance-tab-btn ${activeTab === "reports" ? "active" : ""}`}
                      onClick={() => setActiveTab("reports")}
                    >
                      <FileText size={15} />
                      <span>Rapports trimestriels</span>
                    </button>
                  </div>

                {/* Tab 0: Fiche Complète (Investisseur Institutionnel) */}
                {(activeTab === "dossier" || mountedSubTabs.dossier) && (
                  <div className="finance-tab-content" hidden={activeTab !== "dossier"}>
                    <FinanceDossierPanel
                      symbol={data.eod_ticker || data.yahoo_symbol || data.symbol}
                      onInsertIntoChat={onInsertIntoChat}
                      onOpenHelp={openHelpGuide}
                    />
                  </div>
                )}

                {/* Tab 0b: Avis de l'expert (Buffett, Lynch, Munger, Graham, Damodaran...) */}
                {(activeTab === "experts" || mountedSubTabs.experts) && (
                  <div className="finance-tab-content" hidden={activeTab !== "experts"}>
                    <FinanceExpertsPanel
                      symbol={data.eod_ticker || data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      selectedModel={resolvedExpertModel}
                      selectedModelInfo={resolvedExpertModelInfo}
                      onOpenModelModal={() => setModelModalOpen(true)}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}

                {/* Tab 0c: Archives IA datées */}
                {activeTab === "ai_history" && (
                  <div className="finance-tab-content">
                    <FinanceAiHistoryPanel
                      symbol={data.eod_ticker || data.yahoo_symbol || data.symbol}
                      onSelectSymbol={sym => {
                        setMainTab("fundamentals");
                        setActiveTab("dossier");
                        void loadDetails(sym);
                      }}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}

                {/* Tab 1: Valorisation & Multiples */}
                {activeTab === "valuation" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table">
                        <thead>
                          <tr>
                            <th>Indicateur boursier</th>
                            <th>Valeur déclarée</th>
                            <th>Explication / Rôle</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><FinanceMetricLabel termKey="market_cap" label="Capitalisation boursière" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.market_cap || "N/A"}</span></td>
                            <td className="finance-metric-desc">Valeur totale de l'entreprise sur les marchés d'actions</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="pe_ttm" label="Ratio C/B actuel (Trailing P/E)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.pe_trailing || "N/A"}</span></td>
                            <td className="finance-metric-desc">Cours rapporté au bénéfice net par action des 12 derniers mois</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="pe_forward" label="Ratio C/B prévisionnel (Forward P/E)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.pe_forward || "N/A"}</span></td>
                            <td className="finance-metric-desc">Cours rapporté aux bénéfices futurs estimés par le consensus</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="peg" label="Ratio PEG (Price/Earnings-to-Growth)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.peg_ratio || "N/A"}</span></td>
                            <td className="finance-metric-desc">P/E pondéré par la croissance attendue (&lt; 1 indique une sous-évaluation)</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="pb" label="Price-to-Book (P/B)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.price_to_book || "N/A"}</span></td>
                            <td className="finance-metric-desc">Rapport entre le cours et la valeur comptable nette par action</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="ev_ebitda" label="Valeur d'Entreprise / EBITDA (EV/EBITDA)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.ev_to_ebitda || "N/A"}</span></td>
                            <td className="finance-metric-desc">Multiple d'acquisition opérationnel, indépendant de la structure de dette</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="beta" label="Bêta (volatilité)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.beta || "N/A"}</span></td>
                            <td className="finance-metric-desc">Sensibilité aux mouvements du marché (1.0 = identique à l'indice)</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="eps" label="Bénéfice par action (BPA Trailing / Forward)" strong /></td>
                            <td>
                              <span className="finance-metric-val">
                                {data.financial_stats.valuation.trailing_eps || "N/A"}{" "}
                                <small>({data.financial_stats.valuation.forward_eps ? `futur : ${data.financial_stats.valuation.forward_eps}` : ""})</small>
                              </span>
                            </td>
                            <td className="finance-metric-desc">Quote-part de bénéfice net revenant à chaque action ordinaire</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="dividend_yield" label="Rendement du dividende" strong /></td>
                            <td>
                              <span className="finance-metric-val text-emerald">
                                {data.financial_stats.valuation.dividend_yield || "N/A"}{" "}
                                {data.financial_stats.valuation.dividend_rate ? `(${data.financial_stats.valuation.dividend_rate} ${data.currency})` : ""}
                              </span>
                            </td>
                            <td className="finance-metric-desc">Rémunération annuelle de l'actionnaire en dividende</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="payout_ni" label="Taux de distribution (Payout Ratio)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.payout_ratio || "N/A"}</span></td>
                            <td className="finance-metric-desc">Part des bénéfices nets redistribuée aux actionnaires</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="w52_range" label="Fourchette 52 semaines" strong /></td>
                            <td>
                              <span className="finance-metric-val">
                                {data.financial_stats.valuation.w52_low || "N/A"} - {data.financial_stats.valuation.w52_high || "N/A"} {data.currency}
                              </span>
                            </td>
                            <td className="finance-metric-desc">Plus bas et plus haut cours enregistrés sur un an glissant</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Tab 2: Rentabilité & CA */}
                {activeTab === "profitability" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table">
                        <thead>
                          <tr>
                            <th>Indicateur financier</th>
                            <th>Montant / Ratio déclaré</th>
                            <th>Signification</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><FinanceMetricLabel termKey="rev" label="Chiffre d'affaires (Total Revenue)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.total_revenue || "N/A"}</span></td>
                            <td className="finance-metric-desc">Revenus globaux déclarés sur l'exercice</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="rev_growth" label="Croissance du chiffre d'affaires" strong /></td>
                            <td>
                              <span className={`finance-metric-val ${data.financial_stats.profitability.revenue_growth?.startsWith("+") ? "text-emerald" : ""}`}>
                                {data.financial_stats.profitability.revenue_growth || "N/A"}
                              </span>
                            </td>
                            <td className="finance-metric-desc">Progression annuelle des ventes en rythme annuel</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="gross_m" label="Marge brute (Gross Margin)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.gross_margin || "N/A"}</span></td>
                            <td className="finance-metric-desc">Revenus déduits du coût direct des ventes</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="op_m" label="Marge opérationnelle (Operating Margin)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.operating_margin || "N/A"}</span></td>
                            <td className="finance-metric-desc">Résultat d'exploitation rapporté au chiffre d'affaires</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="net_m" label="Marge nette (Profit Margin)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.profit_margin || "N/A"}</span></td>
                            <td className="finance-metric-desc">Rentabilité finale après impôts, intérêts et charges</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="ebitda" label="EBITDA (Résultat opérationnel brut)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.ebitda || "N/A"}</span></td>
                            <td className="finance-metric-desc">Bénéfice avant intérêts, impôts, dépréciations et amortissements</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="ni" label="Bénéfice net attribuable (Net Income)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.net_income || "N/A"}</span></td>
                            <td className="finance-metric-desc">Bénéfice net consolidé part du groupe</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="roe" label="Rentabilité des capitaux propres (ROE)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.roe || "N/A"}</span></td>
                            <td className="finance-metric-desc">Efficacité avec laquelle la société réinvestit les capitaux actionnaires</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Tab 3: Bilan & Trésorerie */}
                {activeTab === "balance_sheet" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table">
                        <thead>
                          <tr>
                            <th>Poste de Bilan / Flux</th>
                            <th>Montant</th>
                            <th>Analyse</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><FinanceMetricLabel termKey="fcf" label="Flux de trésorerie disponible (Free Cash Flow)" strong /></td>
                            <td><span className="finance-metric-val text-emerald">{data.financial_stats.balance_sheet.total_cash || data.financial_stats.profitability.free_cashflow || "N/A"}</span></td>
                            <td className="finance-metric-desc">Trésorerie nette générée après investissements matériels (CAPEX)</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="ocf" label="Flux de trésorerie d'exploitation" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.operating_cashflow || "N/A"}</span></td>
                            <td className="finance-metric-desc">Trésorerie opérationnelle tirée de l'activité courante</td>
                          </tr>
                          <tr>
                            <td><strong>Trésorerie totale disponible (Cash)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.total_cash || "N/A"}</span></td>
                            <td className="finance-metric-desc">Liquidités et équivalents de trésorerie au bilan</td>
                          </tr>
                          <tr>
                            <td><strong>Dette totale déclarée</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.total_debt || "N/A"}</span></td>
                            <td className="finance-metric-desc">Ensemble des dettes financières à court et long terme</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="debt_eq" label="Ratio Dette / Fonds propres (Debt-to-Equity)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.debt_to_equity || "N/A"}</span></td>
                            <td className="finance-metric-desc">Niveau d'endettement par rapport aux capitaux propres de la société</td>
                          </tr>
                          <tr>
                            <td><FinanceMetricLabel termKey="curr_r" label="Ratio de liquidité générale (Current Ratio)" strong /></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.current_ratio || "N/A"}</span></td>
                            <td className="finance-metric-desc">Capacité à rembourser les dettes à court terme (&gt; 1.0 est sain)</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  <FinanceStatements symbol={data.eod_ticker || data.yahoo_symbol || data.symbol} currency={data.currency} />
                  </div>
                  )}

                {/* Tab 3b: Historique complet des données fondamentales */}
                {(activeTab === "fundamentals" || mountedSubTabs.fundamentals) && (
                  <div className="finance-tab-content" hidden={activeTab !== "fundamentals"}>
                    <FinanceStatements
                      symbol={data.eod_ticker || data.yahoo_symbol || data.symbol}
                      currency={data.currency}
                    />
                  </div>
                )}

                {/* Tab 4: Consensus Analystes */}
                {activeTab === "analysts" && (
                  <div className="finance-tab-content">
                    <div className="finance-analyst-cards-grid">
                      <div className="finance-analyst-card-highlight">
                        <span className="card-kpi-label">Recommandation du Marché</span>
                        <div className="card-kpi-badge-row">
                          {(() => {
                            const recInfo = formatAnalystRecommendation(data.financial_stats.analysts.recommendation);
                            return (
                              <span className={`recommendation-badge tone-${recInfo.tone}`}>
                                {recInfo.label}
                              </span>
                            );
                          })()}
                          {data.financial_stats.analysts.opinions_count && (
                            <small className="analysts-count-tag">{data.financial_stats.analysts.opinions_count} analystes suivis</small>
                          )}
                        </div>
                      </div>

                      <div className="finance-analyst-card">
                        <span className="card-kpi-label">Objectif Moyen</span>
                        <strong className="card-kpi-value text-emerald">
                          {data.financial_stats.analysts.target_mean ? `${data.financial_stats.analysts.target_mean} ${data.currency}` : "N/A"}
                        </strong>
                        {data.financial_stats.analysts.upside_potential_pct != null && (
                          <span className={`kpi-upside-badge ${data.financial_stats.analysts.upside_potential_pct >= 0 ? "is-up" : "is-down"}`}>
                            Potentiel : {data.financial_stats.analysts.upside_potential_pct >= 0 ? "+" : ""}{data.financial_stats.analysts.upside_potential_pct.toFixed(2)}%
                          </span>
                        )}
                      </div>

                      <div className="finance-analyst-card">
                        <span className="card-kpi-label">Objectif le plus haut</span>
                        <strong className="card-kpi-value">
                          {data.financial_stats.analysts.target_high ? `${data.financial_stats.analysts.target_high} ${data.currency}` : "N/A"}
                        </strong>
                        <small className="card-kpi-hint">Hypothèse haussière maximale</small>
                      </div>

                      <div className="finance-analyst-card">
                        <span className="card-kpi-label">Objectif le plus bas</span>
                        <strong className="card-kpi-value">
                          {data.financial_stats.analysts.target_low ? `${data.financial_stats.analysts.target_low} ${data.currency}` : "N/A"}
                        </strong>
                        <small className="card-kpi-hint">Hypothèse baissière minimale</small>
                      </div>
                    </div>
                  </div>
                )}

                {/* Tab 6: Profil de l'entreprise */}
                {activeTab === "profile" && (
                  <div className="finance-tab-content">
                    <div className="finance-profile-card">
                      <div className="finance-profile-grid">
                        <div>
                          <span className="profile-label">Secteur d'activité</span>
                          <strong>{data.financial_stats.profile.sector || "N/A"}</strong>
                        </div>
                        <div>
                          <span className="profile-label">Industrie</span>
                          <strong>{data.financial_stats.profile.industry || "N/A"}</strong>
                        </div>
                        <div>
                          <span className="profile-label">Siège social / Pays</span>
                          <strong>{data.financial_stats.profile.country || "N/A"}</strong>
                        </div>
                        <div>
                          <span className="profile-label">Effectif déclaré</span>
                          <strong>{data.financial_stats.profile.employees || "Non communiqué"}</strong>
                        </div>
                      </div>

                      {data.financial_stats.profile.website && (
                        <div className="finance-profile-site">
                          <span className="profile-label">Site officiel :</span>
                          <a
                            href={data.financial_stats.profile.website}
                            target="_blank"
                            rel="noreferrer"
                            className="site-link"
                          >
                            <span>{data.financial_stats.profile.website}</span>
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      )}

                      {data.financial_stats.profile.summary && (
                        <div className="finance-profile-desc">
                          <span className="profile-label">Activité & Positionnement stratégique :</span>
                          <p>{data.financial_stats.profile.summary}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Tab 7: Analyse MOAT */}
                {(activeTab === "moat" || mountedSubTabs.moat) && (
                  <div className="finance-tab-content" hidden={activeTab !== "moat"}>
                    <FinanceMoatPanel
                      symbol={data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      financialStats={data.financial_stats}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}

                {/* Tab 8: Actualités & Veille IA */}
                {(activeTab === "news" || mountedSubTabs.news) && (
                  <div className="finance-tab-content" hidden={activeTab !== "news"}>
                    <FinanceNewsPanel
                      symbol={data.eod_ticker || data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}

                {/* Tab 8: Rapports trimestriels PDF / Texte */}
                {(activeTab === "reports" || mountedSubTabs.reports) && (
                  <div className="finance-tab-content" hidden={activeTab !== "reports"}>
                    <FinanceReportsPanel
                      symbol={data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      onInsertIntoChat={onInsertIntoChat}
                      onOpenReportAsDoc={onOpenReportAsDoc}
                    />
                  </div>
                )}
              </div>
            </div>
          )}
          </div>

          {/* Barre latérale rétractable sur la droite : Listes de suivi */}
          <aside
            className={`finance-watchlist-sidebar ${watchlistSidebarOpen ? "is-open" : "is-collapsed"} ${watchlistSidebarWide ? "is-wide" : ""}`}
            aria-label="Barre latérale des listes de suivi"
          >
            {watchlistSidebarOpen ? (
              <div className="finance-watchlist-sidebar-scroll">
                <FinanceWatchlistTable
                  lists={watchlists}
                  activeListId={activeListId}
                  items={watchlist}
                  loading={watchlistLoading}
                  selectedSymbol={data?.eod_ticker || data?.yahoo_symbol || data?.symbol || null}
                  inSidebar
                  sidebarWide={watchlistSidebarWide}
                  onToggleSidebarWide={toggleWatchlistSidebarWide}
                  onCollapseSidebar={() => toggleWatchlistSidebar(false)}
                  onSelectList={listId => void handleSelectWatchlistTab(listId)}
                  onCreateList={handleCreateWatchlist}
                  onRenameList={handleRenameWatchlist}
                  onDeleteList={handleDeleteWatchlist}
                  onSelectStock={item => void handleSelectWatchlistStock(item)}
                  onAddStock={handleAddWatchlistStock}
                  onUpdateItemNote={handleUpdateWatchlistItemNote}
                  onRemoveStock={handleRemoveWatchlistStock}
                  onReorderItems={handleReorderWatchlistItems}
                  onRefresh={() => void loadWorkspaceData(true)}
                  onSeedDefaults={handleSeedDefaults}
                />
              </div>
            ) : (
              <button
                type="button"
                className="finance-watchlist-rail-btn"
                onClick={() => toggleWatchlistSidebar(true)}
                title="Déplier les listes de suivi"
                aria-label="Déplier les listes de suivi"
              >
                <PanelRightOpen size={16} />
                <span className="finance-watchlist-rail-count">{watchlist.length}</span>
                <span className="finance-watchlist-rail-label">Listes de suivi</span>
              </button>
            )}
          </aside>
        </div>

        {/* Footer actions */}
        <div className="finance-modal-footer">
          <div className="finance-footer-left">
            {data?.url_eod && (
              <a
                href={data.url_eod}
                target="_blank"
                rel="noreferrer"
                className="finance-external-link is-eod"
                title="Consulter la fiche officielle sur EOD Historical Data"
              >
                <span>Fiche EODHD</span>
                <ExternalLink size={12} />
              </a>
            )}
            {data?.url_yahoo && (
              <a
                href={data.url_yahoo}
                target="_blank"
                rel="noreferrer"
                className="finance-external-link is-yahoo"
                title="Consulter la fiche officielle sur Yahoo Finance"
              >
                <span>Fiche Yahoo Finance</span>
                <ExternalLink size={12} />
              </a>
            )}
          </div>

          <div className="finance-footer-right">
            <button
              type="button"
              className="finance-copy-btn"
              onClick={copyMarkdownSummary}
              disabled={!data}
              title="Copier la synthèse financière au format Markdown"
            >
              {copied ? <Check size={14} className="text-emerald" /> : <Copy size={14} />}
              <span>{copied ? "Rapport copié !" : "Copier le rapport"}</span>
            </button>

            {onInsertIntoChat && (
              <button
                type="button"
                className="finance-insert-btn"
                onClick={insertIntoChat}
                disabled={!data}
                title="Poser une question sur cette action dans la discussion courante"
              >
                <MessageSquarePlus size={14} />
                <span>Poser une question à l'IA</span>
              </button>
            )}
          </div>
        </div>
      </div>

      <FinanceCustomIndicatorModal
        isOpen={indicatorModalOpen}
        onClose={() => {
          setIndicatorModalOpen(false);
          setEditingIndicator(null);
        }}
        bars={filteredBars}
        initialIndicator={editingIndicator}
        onSave={handleSaveCustomIndicator}
      />

      <FinanceHelpModal
        isOpen={helpOpen}
        initialGuide={helpGuide}
        onClose={() => setHelpOpen(false)}
      />

      {modelModalOpen && (
        <ModelModal
          currentModel={resolvedExpertModel}
          models={availableModels}
          onSelectModel={modelId => {
            setSelectedExpertModel(modelId);
            setModelModalOpen(false);
          }}
          onClose={() => setModelModalOpen(false)}
          onRefreshModels={refreshModelsForFinance}
        />
      )}
    </div>
  );
}

/**
 * Interactive SVG Line & Area Chart for Stock Price history
 */
function InteractivePriceChart({
  bars,
  currency,
  hoveredIndex,
  onHover,
  dividendsByBarIndex,
}: {
  bars: EodBar[];
  currency: string;
  hoveredIndex: number | null;
  onHover: (idx: number | null) => void;
  dividendsByBarIndex?: ReadonlyMap<number, ProjectedBarDividend>;
}) {
  const width = 800;
  const height = 220;
  const paddingX = 40;
  const paddingY = 24;

  const validPoints = useMemo(() => {
    return bars
      .map((b, i) => ({
        index: i,
        date: b.date,
        price: b.close ?? 0,
        high: b.high ?? b.close ?? 0,
        low: b.low ?? b.close ?? 0,
        volume: b.volume ?? 0,
      }))
      .filter(p => p.price > 0);
  }, [bars]);

  if (validPoints.length < 2) return null;

  const minPrice = Math.min(...validPoints.map(p => p.price));
  const maxPrice = Math.max(...validPoints.map(p => p.price));
  const priceRange = maxPrice - minPrice || 1;

  const chartW = width - paddingX * 2;
  const chartH = height - paddingY * 2;

  const isUp = validPoints[validPoints.length - 1].price >= validPoints[0].price;
  const strokeColor = isUp ? "#10b981" : "#f43f5e";
  const gradientId = isUp ? "emeraldGradient" : "roseGradient";

  // Coordinates mapping
  const points = validPoints.map((p, i) => {
    const x = paddingX + (i / (validPoints.length - 1)) * chartW;
    const y = height - paddingY - ((p.price - minPrice) / priceRange) * chartH;
    return { ...p, x, y };
  });

  const pathD = points.reduce((acc, pt, i) => {
    return i === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`;
  }, "");

  const areaD = `${pathD} L ${points[points.length - 1].x} ${height - paddingY} L ${points[0].x} ${height - paddingY} Z`;

  // Grid levels (3 horizontal lines)
  const gridLevels = [
    { label: maxPrice.toFixed(2), y: paddingY },
    { label: ((maxPrice + minPrice) / 2).toFixed(2), y: height / 2 },
    { label: minPrice.toFixed(2), y: height - paddingY },
  ];

  return (
    <div className="finance-svg-wrapper">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="finance-chart-svg"
        onMouseLeave={() => onHover(null)}
      >
        <defs>
          <linearGradient id="emeraldGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
          </linearGradient>
          <linearGradient id="roseGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Grid Lines */}
        {gridLevels.map((g, i) => (
          <g key={i}>
            <line
              x1={paddingX}
              y1={g.y}
              x2={width - paddingX}
              y2={g.y}
              stroke="var(--line, rgba(148, 163, 184, 0.2))"
              strokeDasharray="4 4"
            />
            <text
              x={width - paddingX + 6}
              y={g.y + 4}
              fontSize="10"
              fill="var(--muted, #94a3b8)"
              fontFamily="sans-serif"
            >
              {g.label}
            </text>
          </g>
        ))}

        {/* Area fill */}
        <path d={areaD} fill={`url(#${gradientId})`} />

        {/* Main Price Line */}
        <path
          d={pathD}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Interactive hover crosshair and dots */}
        {points.map((pt, i) => {
          const isHovered = hoveredIndex === pt.index;
          const divInfo = dividendsByBarIndex?.get(pt.index);
          return (
            <g
              key={i}
              className="chart-point-group"
              onMouseEnter={() => onHover(pt.index)}
              style={{ cursor: "pointer" }}
            >
              {/* Invisible wide hit area */}
              <rect
                x={pt.x - chartW / points.length / 2}
                y={0}
                width={chartW / points.length}
                height={height}
                fill="transparent"
              />

              {divInfo && (
                <g>
                  <line
                    x1={pt.x}
                    y1={pt.y + 4}
                    x2={pt.x}
                    y2={height - paddingY}
                    stroke="#d97706"
                    strokeWidth="1"
                    strokeDasharray="2 3"
                    opacity="0.65"
                  />
                  <circle
                    cx={pt.x}
                    cy={height - paddingY + 10}
                    r="7"
                    fill="#d97706"
                    stroke="#ffffff"
                    strokeWidth="1.2"
                  />
                  <text
                    x={pt.x}
                    y={height - paddingY + 13}
                    textAnchor="middle"
                    fontSize="8.5"
                    fontWeight="700"
                    fill="#ffffff"
                    fontFamily="sans-serif"
                  >
                    D
                  </text>
                  <title>{formatDividendHoverSummary(divInfo)}</title>
                </g>
              )}

              {isHovered && (
                <>
                  <line
                    x1={pt.x}
                    y1={paddingY}
                    x2={pt.x}
                    y2={height - paddingY}
                    stroke="var(--text, #334155)"
                    strokeWidth="1.5"
                    strokeDasharray="3 3"
                    opacity="0.6"
                  />
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="5"
                    fill={strokeColor}
                    stroke="#ffffff"
                    strokeWidth="2.5"
                  />
                </>
              )}
            </g>
          );
        })}

        {/* Start and end points */}
        <circle cx={points[0].x} cy={points[0].y} r="3.5" fill={strokeColor} opacity="0.8" />
        <circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r="4.5"
          fill={strokeColor}
        />
      </svg>
    </div>
  );
}

