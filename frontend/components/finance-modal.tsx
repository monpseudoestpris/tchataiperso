"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { FinanceAiHistoryPanel } from "@/components/finance-ai-history-panel";
import { FinanceCustomIndicatorModal } from "@/components/finance-custom-indicator-modal";
import { FinanceDossierPanel } from "@/components/finance-dossier-panel";
import { FinanceEufundBrowser } from "@/components/finance-eufund-browser";
import { FinanceExpertsPanel } from "@/components/finance-experts-panel";
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
import { FinanceMoatPanel } from "@/components/finance-moat-panel";
import { FinanceNewsPanel } from "@/components/finance-news-panel";
import { FinanceReportsPanel } from "@/components/finance-reports-panel";
import { FinanceStatements } from "@/components/finance-statements";
import { FinanceTvChart } from "@/components/finance-tv-chart";
import { FinanceWatchlistTable } from "@/components/finance-watchlist-table";
import {
  ArrowDownRight,
  ArrowUpRight,
  Award,
  BarChart3,
  Building2,
  Calendar,
  Check,
  ChevronRight,
  ClipboardList,
  Copy,
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
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
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
  fetchCustomIndicators,
  fetchFinanceDetails,
  fetchIndexComposition,
  fetchPrincipalIndices,
  fetchWatchlistState,
  renameWatchlist,
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
  type FinanceWatchlistMeta,
  type FinancialDashboardData,
  type FinancialStats,
  type IndexCompositionResponse,
  type IndexConstituent,
  type Model,
  type PrincipalIndexInfo,
  type WarehouseOverview,
  type WatchlistItem,
} from "@/lib/api";

type FinanceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  initialQuery?: string | null;
  initialData?: FinancialDashboardData | null;
  models?: Model[];
  defaultModel?: string;
  onRefreshModels?: () => Promise<void>;
  onInsertIntoChat?: (text: string) => void;
};

type ActiveTab =
  | "dossier"
  | "experts"
  | "ai_history"
  | "valuation"
  | "profitability"
  | "balance_sheet"
  | "fundamentals"
  | "analysts"
  | "history"
  | "profile"
  | "moat"
  | "news"
  | "reports";

const WATCHLIST_SEED_STORAGE_KEY = "clair_watchlist_seeded_v1";
const WATCHLIST_ACTIVE_LIST_KEY = "clair_active_watchlist_id_v1";
const WATCHLIST_SIDEBAR_OPEN_KEY = "clair_finance_wl_sidebar_open_v1";
const WATCHLIST_SIDEBAR_WIDE_KEY = "clair_finance_wl_sidebar_wide_v1";

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
  models: propModels,
  defaultModel: propDefaultModel,
  onRefreshModels,
  onInsertIntoChat,
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
  const [activeTab, setActiveTab] = useState<ActiveTab>("valuation");
  const [timeframe, setTimeframe] = useState<FinanceRange>("1m");
  const [barInterval, setBarInterval] = useState<BarInterval>("day");
  const [rangeLoading, setRangeLoading] = useState(false);
  const [chartView, setChartView] = useState<"line" | "advanced">("line");
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [hoveredBarIndex, setHoveredBarIndex] = useState<number | null>(null);
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
  const [indexLoading, setIndexLoading] = useState(false);
  const [indexError, setIndexError] = useState<string | null>(null);
  const [indxCatalogOpen, setIndxCatalogOpen] = useState(false);
  const [eufundCatalogOpen, setEufundCatalogOpen] = useState(false);
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

  // Synchronize when opening modal
  useEffect(() => {
    if (!isOpen) return;

    void loadWorkspaceData();
    if (!propModels || propModels.length === 0) {
      api<Config>("/config")
        .then(cfg => {
          setFallbackModels(cfg.models || []);
          if (cfg.default_model) setFallbackDefaultModel(cfg.default_model);
        })
        .catch(() => {});
    }

    if (initialData) {
      setData(initialData);
      setQuery(initialData.short_name || initialData.symbol);
      setError(null);
      return;
    }

    const targetQuery = (initialQuery || "").trim();
    if (targetQuery) {
      setQuery(targetQuery);
      void loadDetails(targetQuery);
    } else if (!data) {
      // Default to Air Liquide if no initial query
      setQuery("Air Liquide");
      void loadDetails("Air Liquide");
    }
  }, [isOpen, initialQuery, initialData]);

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
        if (chartFullscreen) {
          setChartFullscreen(false);
          return;
        }
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, modelModalOpen, helpOpen, indicatorModalOpen, chartFullscreen, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const trimmed = query.trim();
    if (!searchFocused || trimmed.length < 2) {
      setCatalogMatches([]);
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
      const wlState = await fetchWatchlistState(!alreadySeeded, true, listParam).catch(async () => {
        if (listParam) {
          return fetchWatchlistState(!alreadySeeded, true, null);
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

  async function handleToggleIndex(code: string, forceRefresh = false) {
    if (!forceRefresh && activeIndexCode === code) {
      setActiveIndexCode(null);
      setIndexComposition(null);
      setIndexError(null);
      return;
    }
    setIndxCatalogOpen(false);
    setEufundCatalogOpen(false);
    setActiveIndexCode(code);
    setIndexLoading(true);
    setIndexError(null);
    window.requestAnimationFrame(() => {
      modalBodyRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
    try {
      const res = await fetchIndexComposition(code, forceRefresh);
      setIndexComposition(res);
    } catch (err: any) {
      setIndexError(err?.message || "Impossible de charger la composition de l'indice.");
    } finally {
      setIndexLoading(false);
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

  async function loadDetails(searchTarget: string) {
    const q = searchTarget.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchFinanceDetails(q, timeframe);
      setData(res);
    } catch (err: any) {
      setError(err?.message || "Impossible de charger les données financières pour cette action.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectWatchlistStock(item: WatchlistItem) {
    const target = item.eod_ticker || item.yahoo_symbol || item.symbol;
    setQuery(item.name || item.symbol);
    setChartView("advanced");
    await loadDetails(target);
    window.requestAnimationFrame(() => {
      chartSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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
    }
  }

  async function handleDeleteCustomIndicator(indicatorId: string) {
    await deleteCustomIndicator(indicatorId);
    setCustomIndicators(prev => prev.filter(item => item.id !== indicatorId));
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) {
      void loadDetails(query.trim());
    }
  }

  // Filter & aggregate bars according to selected timeframe and bar interval
  const filteredBars = useMemo(() => {
    if (!data?.eod_bars || data.eod_bars.length === 0) return [];
    return aggregateBars(data.eod_bars, barInterval);
  }, [data?.eod_bars, barInterval]);

  // Recharge uniquement la courbe quand la durée d'affichage change
  async function changeTimeframe(tf: FinanceRange) {
    if (tf === timeframe || !data) return;
    const previous = timeframe;
    setTimeframe(tf);
    setHoveredBarIndex(null);
    setRangeLoading(true);
    try {
      const res = await fetchFinanceDetails(data.yahoo_symbol || data.symbol, tf);
      setData(prev => (prev ? { ...prev, eod_bars: res.eod_bars } : res));
    } catch (err: any) {
      setTimeframe(previous);
      setError(err?.message || "Impossible de charger cette durée d'affichage.");
    } finally {
      setRangeLoading(false);
    }
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

  return (
    <div className="modal-backdrop finance-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-container finance-modal-container"
        onClick={e => e.stopPropagation()}
        aria-label="Tableau de bord financier & Courbe de cours"
      >
        {/* Header */}
        <div className="finance-modal-header">
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

        {/* Search & Suggestions Bar */}
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
            {searchFocused && catalogMatches.length > 0 && (
              <div className="finance-search-dropdown" role="listbox" aria-label="Suggestions catalogue et entrepôt">
                {catalogMatches.map(m => (
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
            onOpenMinorTier={handleOpenMinorTier}
          />
        </div>

        {/* Workspace : contenu principal à gauche + barre rétractable des listes à droite */}
        <div className="finance-modal-workspace">
          <div className="finance-modal-body" ref={modalBodyRef}>
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
                loading={indexLoading}
                error={indexError}
                selectedSymbol={data?.eod_ticker || data?.yahoo_symbol || data?.symbol || null}
                onSelectStock={item => void handleSelectIndexStock(item)}
                onAddWatchlist={handleAddIndexStockToWatchlist}
                onRefresh={() => void handleToggleIndex(activeIndexCode, true)}
                onClose={() => {
                  setActiveIndexCode(null);
                  setIndexComposition(null);
                  setIndexError(null);
                }}
              />
            )}

            {error && (
            <div className="finance-modal-error" role="alert">
              <span>⚠️ {error}</span>
              <button type="button" onClick={() => void loadDetails(query)}>
                <RefreshCw size={14} /> Réessayer
              </button>
            </div>
          )}

          {loading && !data && (
            <div className="finance-modal-loading">
              <LoaderCircle size={36} className="spin text-emerald" />
              <p>Téléchargement des cours live (EOD) et des états financiers (Yahoo Finance)…</p>
            </div>
          )}

          {data && (
            <>
              {/* Live Quote Hero Banner */}
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
                </div>
              </div>

              {/* Section 1: Courbe interactive du cours via EOD */}
              <div
                className={`finance-chart-section${chartFullscreen ? " is-fullscreen" : ""}`}
                ref={chartSectionRef}
              >
                <div className="finance-chart-header">
                  <div className="finance-chart-title">
                    <span className="chart-icon-wrap">
                      <TrendingUp size={16} />
                    </span>
                    <div>
                      <strong>
                        {data.long_name || data.short_name || data.symbol} ({data.symbol})
                      </strong>
                      <small>
                        {filteredBars.length} points · {TIMEFRAME_LABELS[timeframe]} · Barres :{" "}
                        {BAR_INTERVAL_LABELS[barInterval]} ·{" "}
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
                        {(["line", "advanced"] as const).map(v => (
                          <button
                            key={v}
                            type="button"
                            className={`finance-tf-btn ${chartView === v ? "active" : ""}`}
                            onClick={() => setChartView(v)}
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
                          className={`finance-tf-btn ${barInterval === interval ? "active" : ""}`}
                          onClick={() => {
                            setBarInterval(interval);
                            setHoveredBarIndex(null);
                          }}
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
                          className={`finance-tf-btn ${timeframe === tf ? "active" : ""}`}
                          onClick={() => void changeTimeframe(tf)}
                        >
                          {TIMEFRAME_LABELS[tf]}
                        </button>
                      ))}
                    </div>

                    <button
                      type="button"
                      className={`finance-chart-fullscreen-btn${chartFullscreen ? " active" : ""}`}
                      onClick={() => setChartFullscreen(prev => !prev)}
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

                {!chartFullscreen && (
                  <div className="finance-timeframe-selector finance-chart-view-toggle">
                    {(["line", "advanced"] as const).map(v => (
                      <button
                        key={v}
                        type="button"
                        className={`finance-tf-btn ${chartView === v ? "active" : ""}`}
                        onClick={() => setChartView(v)}
                      >
                        {v === "line" ? "Courbe" : "Analyse technique"}
                      </button>
                    ))}
                  </div>
                )}

                {chartView === "advanced" && (
                  <FinanceTvChart
                    bars={filteredBars}
                    symbol={data.symbol}
                    dark={theme.mode === "dark"}
                    fullscreen={chartFullscreen}
                    customIndicators={customIndicators}
                    onOpenIndicatorEditor={ind => {
                      setEditingIndicator(ind ?? null);
                      setIndicatorModalOpen(true);
                    }}
                    onDeleteCustomIndicator={id => void handleDeleteCustomIndicator(id)}
                  />
                )}

                {/* SVG Price Chart */}
                <div className="finance-svg-chart-container" hidden={chartView === "advanced"}>
                  {filteredBars.length >= 2 ? (
                    <InteractivePriceChart
                      bars={filteredBars}
                      currency={data.currency}
                      hoveredIndex={hoveredBarIndex}
                      onHover={setHoveredBarIndex}
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
                    </div>
                  )}
                </div>
              </div>

              {/* Section 2: Navigation par onglets des statistiques financières complètes */}
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
                    className={`finance-tab-btn ${activeTab === "valuation" ? "active" : ""}`}
                    onClick={() => setActiveTab("valuation")}
                  >
                    <Target size={15} />
                    <span>Valorisation & Multiples</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "profitability" ? "active" : ""}`}
                    onClick={() => setActiveTab("profitability")}
                  >
                    <TrendingUp size={15} />
                    <span>Rentabilité & CA</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "balance_sheet" ? "active" : ""}`}
                    onClick={() => setActiveTab("balance_sheet")}
                  >
                    <Wallet size={15} />
                    <span>Bilan & Trésorerie</span>
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
                    className={`finance-tab-btn ${activeTab === "history" ? "active" : ""}`}
                    onClick={() => setActiveTab("history")}
                  >
                    <Calendar size={15} />
                    <span>Séances EOD ({data.eod_bars.length})</span>
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
                {activeTab === "dossier" && (
                  <div className="finance-tab-content">
                    <FinanceDossierPanel
                      symbol={data.eod_ticker || data.yahoo_symbol || data.symbol}
                      onInsertIntoChat={onInsertIntoChat}
                      onOpenHelp={openHelpGuide}
                    />
                  </div>
                )}

                {/* Tab 0b: Avis de l'expert (Buffett, Lynch, Munger, Graham, Damodaran...) */}
                {activeTab === "experts" && (
                  <div className="finance-tab-content">
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
                {activeTab === "fundamentals" && (
                  <div className="finance-tab-content">
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

                {/* Tab 5: Historique des séances EOD */}
                {activeTab === "history" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table finance-history-table">
                        <thead>
                          <tr>
                            <th>Date séance</th>
                            <th><FinanceMetricLabel termKey="close_adj" label="Clôture aj." /></th>
                            <th><FinanceMetricLabel termKey="var_day" label="Variation" /></th>
                            <th><FinanceMetricLabel termKey="open_adj" label="Ouverture aj." /></th>
                            <th><FinanceMetricLabel termKey="high_adj" label="Plus haut aj." /></th>
                            <th><FinanceMetricLabel termKey="low_adj" label="Plus bas aj." /></th>
                            <th><FinanceMetricLabel termKey="volume" label="Volume d'échanges" /></th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.eod_bars.length === 0 ? (
                            <tr>
                              <td colSpan={7} className="text-center">Aucun historique disponible</td>
                            </tr>
                          ) : (
                            data.eod_bars.slice(-60).reverse().map((bar, idx, arr) => {
                              const prevClose = idx + 1 < arr.length ? arr[idx + 1].close : null;
                              const diff = bar.close != null && prevClose != null ? bar.close - prevClose : null;
                              const diffPct = diff != null && prevClose ? (diff / prevClose) * 100 : null;
                              return (
                                <tr key={bar.date}>
                                  <td><strong>{bar.date}</strong></td>
                                  <td><strong>{bar.close?.toFixed(2)} {data.currency}</strong></td>
                                  <td>
                                    {diffPct != null ? (
                                      <span className={diffPct >= 0 ? "text-emerald" : "text-rose"}>
                                        {diffPct >= 0 ? "+" : ""}{diffPct.toFixed(2)}%
                                      </span>
                                    ) : (
                                      "—"
                                    )}
                                  </td>
                                  <td>{bar.open?.toFixed(2) || "-"}</td>
                                  <td>{bar.high?.toFixed(2) || "-"}</td>
                                  <td>{bar.low?.toFixed(2) || "-"}</td>
                                  <td>{bar.volume != null ? bar.volume.toLocaleString("fr-FR") : "-"}</td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
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
                {activeTab === "moat" && (
                  <div className="finance-tab-content">
                    <FinanceMoatPanel
                      symbol={data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      financialStats={data.financial_stats}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}

                {/* Tab 8: Actualités & Veille IA */}
                {activeTab === "news" && (
                  <div className="finance-tab-content">
                    <FinanceNewsPanel
                      symbol={data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}

                {/* Tab 8: Rapports trimestriels PDF / Texte */}
                {activeTab === "reports" && (
                  <div className="finance-tab-content">
                    <FinanceReportsPanel
                      symbol={data.yahoo_symbol || data.symbol}
                      companyName={data.long_name || data.short_name || data.symbol}
                      onInsertIntoChat={onInsertIntoChat}
                    />
                  </div>
                )}
              </div>
            </>
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
}: {
  bars: EodBar[];
  currency: string;
  hoveredIndex: number | null;
  onHover: (idx: number | null) => void;
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
          const isHovered = hoveredIndex === i;
          return (
            <g
              key={i}
              className="chart-point-group"
              onMouseEnter={() => onHover(i)}
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

