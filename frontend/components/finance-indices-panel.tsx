"use client";

import { ArrowDown, ArrowUp, BarChart2, CalendarClock, Check, ChevronDown, ChevronUp, Database, FolderPlus, Globe2, LayoutGrid, LoaderCircle, Plus, RefreshCw, Search, Table2, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";

import {
  fetchEodhdIndxCatalog,
  type EodhdIndxCatalogItem,
  type IndexCompositionResponse,
  type IndexConstituent,
  type IndexPerformanceItem,
  type IndexPerformancesResponse,
  type PrincipalIndexInfo,
  type WarehouseOverview,
} from "@/lib/api";

const PAGE_STEP = 60;

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 Ko";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
  return `${Math.round(bytes / 1024)} Ko`;
}

export function FinanceIndicesStrip({
  indices,
  warehouse,
  activeCode,
  loadingIndex,
  catalogOpen,
  eufundCatalogOpen,
  syncOpen,
  onToggleIndex,
  onToggleCatalog,
  onToggleEufundCatalog,
  onToggleSync,
  onOpenMinorTier,
}: {
  indices: PrincipalIndexInfo[];
  warehouse: WarehouseOverview | null;
  activeCode: string | null;
  loadingIndex: boolean;
  catalogOpen: boolean;
  eufundCatalogOpen?: boolean;
  syncOpen?: boolean;
  onToggleIndex: (code: string) => void;
  onToggleCatalog: () => void;
  onToggleEufundCatalog?: () => void;
  onToggleSync?: () => void;
  onOpenMinorTier?: () => void;
}) {
  const [tierView, setTierView] = useState<"major" | "minor" | "all">("major");

  const majorIndices = useMemo(() => indices.filter(i => (i.tier ?? "major") === "major"), [indices]);
  const minorIndices = useMemo(() => indices.filter(i => i.tier === "minor"), [indices]);
  const visibleIndices = useMemo(() => {
    if (tierView === "major") return majorIndices;
    if (tierView === "minor") return minorIndices;
    return indices;
  }, [tierView, majorIndices, minorIndices, indices]);

  if (indices.length === 0) return null;

  function switchTier(next: "major" | "minor" | "all") {
    setTierView(next);
    if ((next === "minor" || next === "all") && onOpenMinorTier) {
      onOpenMinorTier();
    }
  }

  return (
    <div className="finance-indices-strip">
      <div className="finance-indices-strip-controls">
        <span className="finance-chips-label finance-indices-label">
          <Globe2 size={13} />
          <span>Indices :</span>
        </span>
        <div className="finance-timeframe-selector" role="group" aria-label="Catégorie d'indices">
          <button
            type="button"
            className={`finance-tf-btn ${tierView === "major" ? "active" : ""}`}
            onClick={() => switchTier("major")}
          >
            Principaux ({majorIndices.length})
          </button>
          <button
            type="button"
            className={`finance-tf-btn ${tierView === "minor" ? "active" : ""}`}
            onClick={() => switchTier("minor")}
          >
            Secondaires &amp; Mid/Small ({minorIndices.length})
          </button>
          <button
            type="button"
            className={`finance-tf-btn ${tierView === "all" ? "active" : ""}`}
            onClick={() => switchTier("all")}
          >
            Tous ({indices.length})
          </button>
        </div>
        <button
          type="button"
          className={`finance-tf-btn finance-indx-catalog-btn ${catalogOpen ? "active" : ""}`}
          onClick={onToggleCatalog}
          title="Parcourir tous les indices disponibles dans l'API EODHD (/exchange-symbol-list/INDX)"
        >
          <Search size={11} />
          <span>Catalogue EODHD (.INDX)</span>
        </button>
        {onToggleEufundCatalog && (
          <button
            type="button"
            className={`finance-tf-btn finance-indx-catalog-btn ${eufundCatalogOpen ? "active" : ""}`}
            onClick={onToggleEufundCatalog}
            title="Parcourir les catalogues EODHD (EUFUND, PA, US, XETRA, LSE, CC) et rechercher par nom, ticker, ISIN ou société de gestion"
          >
            <Search size={11} />
            <span>Marchés &amp; Fonds (.EUFUND, PA, US…)</span>
          </button>
        )}
        {onToggleSync && (
          <button
            type="button"
            className={`finance-tf-btn finance-indx-catalog-btn ${syncOpen ? "active" : ""}`}
            onClick={onToggleSync}
            title="Choisir ce qui est synchronisé automatiquement chaque jour (indices, actions d'indices, listes, marchés)"
          >
            <CalendarClock size={11} />
            <span>Synchro auto</span>
          </button>
        )}
        {warehouse && warehouse.instruments_count > 0 && (
          <span
            className="finance-warehouse-pill"
            title={`${warehouse.instruments_count} valeurs · ${warehouse.eod_bars_count.toLocaleString("fr-FR")} barres EOD · ${warehouse.fundamental_facts_count.toLocaleString("fr-FR")} faits fondamentaux`}
          >
            <Database size={11} />
            <span>
              {warehouse.instruments_count} en entrepôt · {formatBytes(warehouse.db_size_bytes)}
            </span>
          </span>
        )}
      </div>

      <div className="finance-indices-pills">
        {visibleIndices.map(idx => {
          const isActive = activeCode === idx.code;
          const hasChg = idx.change_pct != null && Number.isFinite(idx.change_pct);
          const isUp = (idx.change_pct ?? 0) >= 0;
          return (
            <button
              key={idx.code}
              type="button"
              className={`finance-index-pill ${isActive ? "active" : ""}`}
              onClick={() => onToggleIndex(idx.code)}
              title={`${idx.description} (${idx.eod_ticker})`}
            >
              <span className="finance-index-flag">{idx.flag}</span>
              <span className="finance-index-name">{idx.name}</span>
              {idx.last_price != null && (
                <span className="finance-index-level">
                  {idx.last_price.toLocaleString("fr-FR", { maximumFractionDigits: 0 })}
                </span>
              )}
              {hasChg && (
                <span className={`finance-index-chg ${isUp ? "is-up" : "is-down"}`}>
                  {isUp ? "+" : ""}
                  {idx.change_pct!.toFixed(2)}%
                </span>
              )}
              {idx.constituents_count > 0 && (
                <span className="finance-index-count">{idx.constituents_count}</span>
              )}
              {isActive && loadingIndex ? (
                <LoaderCircle size={12} className="spin" />
              ) : isActive ? (
                <ChevronUp size={12} />
              ) : (
                <ChevronDown size={12} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function FinanceEodhdIndxBrowser({
  activeCode,
  onSelectIndexCode,
  onClose,
}: {
  activeCode: string | null;
  onSelectIndexCode: (eodTicker: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<EodhdIndxCatalogItem[]>([]);
  const [meta, setMeta] = useState<{ total: number; matched: number; source: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCatalog(q: string, refresh = false) {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchEodhdIndxCatalog(q, 120, refresh);
      setItems(res.items || []);
      setMeta({ total: res.total, matched: res.matched, source: res.source });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Impossible de charger le catalogue INDX EODHD.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadCatalog(query, false);
    }, query ? 180 : 0);
    return () => window.clearTimeout(timer);
  }, [query]);

  return (
    <section className="finance-index-drawer" aria-label="Catalogue complet des indices EODHD INDX">
      <div className="finance-index-drawer-head">
        <div className="finance-index-drawer-title">
          <span className="finance-index-drawer-flag">🌐</span>
          <div>
            <strong>
              Catalogue complet des indices EODHD ({meta ? `${meta.total} indices` : "…"})
            </strong>
            <small>
              {meta
                ? `Source : ${meta.source} · Cliquez sur un indice pour charger sa composition EODHD`
                : "Interrogation de /api/exchange-symbol-list/INDX…"}
            </small>
          </div>
        </div>
        <div className="finance-index-drawer-actions">
          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={loading}
            onClick={() => void loadCatalog(query, true)}
            title="Re-télécharger la liste complète des indices EODHD"
          >
            <RefreshCw size={12} className={loading ? "spin" : ""} />
            <span>Actualiser</span>
          </button>
          <button type="button" className="finance-tf-btn" onClick={onClose} aria-label="Fermer le catalogue INDX">
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="finance-index-drawer-filters">
        <div className="finance-index-filter-input-wrap">
          <Search size={13} />
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Rechercher un indice mondial ou sectoriel (ex. SBF, Russell, Mid, Small, Nikkei, MSCI, STOXX, France…)"
          />
        </div>
        {meta && (
          <span className="finance-index-filter-count">
            {items.length} affichés / {meta.matched} correspondants
          </span>
        )}
      </div>

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {loading && items.length === 0 ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>Chargement du catalogue EODHD INDX…</span>
        </div>
      ) : items.length === 0 ? (
        <div className="finance-index-drawer-empty">Aucun indice trouvé pour cette recherche.</div>
      ) : (
        <div className="finance-index-constituents-grid">
          {items.map(item => (
            <button
              key={item.eod_ticker}
              type="button"
              className={`finance-index-stock-card finance-indx-cat-card ${activeCode === item.eod_ticker ? "is-selected" : ""}`}
              onClick={() => onSelectIndexCode(item.eod_ticker)}
              title={`Ouvrir la composition de ${item.name} (${item.eod_ticker})`}
            >
              <div className="finance-index-stock-top">
                <span className="finance-symbol-tag">{item.eod_ticker}</span>
                {item.currency && <span className="finance-search-dropdown-idx">{item.currency}</span>}
              </div>
              <strong className="finance-index-stock-name">{item.name}</strong>
              {item.country && <small className="finance-index-stock-meta">{item.country}</small>}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

type PerfSortKey =
  | "name"
  | "weight_pct"
  | "price"
  | "change_1d_pct"
  | "change_1w_pct"
  | "change_1m_pct"
  | "change_3m_pct"
  | "change_ytd_pct"
  | "change_1y_pct";

function IndexPerfCell({ value }: { value: number | null | undefined }) {
  if (value == null || !Number.isFinite(value)) {
    return <span className="finance-perf-na">—</span>;
  }
  const cls = value > 0 ? "is-up" : value < 0 ? "is-down" : "is-flat";
  return (
    <span className={`finance-perf-pill ${cls}`}>
      {value > 0 ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

function buildSmoothSparklinePath(coords: Array<{ x: number; y: number }>): string {
  if (coords.length === 0) return "";
  if (coords.length === 1) return `M ${coords[0].x.toFixed(1)} ${coords[0].y.toFixed(1)}`;
  let d = `M ${coords[0].x.toFixed(1)} ${coords[0].y.toFixed(1)}`;
  for (let i = 1; i < coords.length - 1; i += 1) {
    const xc = ((coords[i].x + coords[i + 1].x) / 2).toFixed(1);
    const yc = ((coords[i].y + coords[i + 1].y) / 2).toFixed(1);
    d += ` Q ${coords[i].x.toFixed(1)} ${coords[i].y.toFixed(1)} ${xc} ${yc}`;
  }
  const last = coords[coords.length - 1];
  d += ` L ${last.x.toFixed(1)} ${last.y.toFixed(1)}`;
  return d;
}

function IndexStockSparkline({
  symbol,
  points,
  changePct,
  compact = false,
  loading = false,
}: {
  symbol: string;
  points?: number[];
  changePct?: number | null;
  compact?: boolean;
  loading?: boolean;
}) {
  const rawGradId = useId();
  const gradId = `idx-spark-${rawGradId.replace(/[^a-zA-Z0-9_-]/g, "")}`;

  const validPoints = useMemo(
    () => (points ?? []).filter((v): v is number => typeof v === "number" && Number.isFinite(v) && v > 0),
    [points],
  );

  if (validPoints.length < 2) {
    return (
      <div
        className={`finance-sparkline-wrap is-empty ${compact ? "is-compact" : ""}`}
        title={loading ? `Chargement du cours de ${symbol}…` : `Historique miniature indisponible pour ${symbol}`}
      >
        {loading ? (
          <LoaderCircle size={12} className="spin text-emerald" />
        ) : (
          <span className="finance-sparkline-empty">—</span>
        )}
      </div>
    );
  }

  const width = compact ? 108 : 132;
  const height = compact ? 28 : 36;
  const padX = 3;
  const padY = 4;
  const plotW = width - padX * 2;
  const plotH = height - padY * 2;

  const firstVal = validPoints[0];
  const lastVal = validPoints[validPoints.length - 1];
  const minVal = Math.min(...validPoints);
  const maxVal = Math.max(...validPoints);
  const span = maxVal - minVal;

  const coords = validPoints.map((val, idx) => {
    const x = padX + (idx / (validPoints.length - 1)) * plotW;
    const y =
      span > 0
        ? padY + (1 - (val - minVal) / span) * plotH
        : padY + plotH / 2;
    return { x, y };
  });

  const baselineY = coords[0].y;
  const lineD = buildSmoothSparklinePath(coords);
  const areaD = `${lineD} L ${coords[coords.length - 1].x.toFixed(1)} ${(height - padY).toFixed(1)} L ${coords[0].x.toFixed(1)} ${(height - padY).toFixed(1)} Z`;

  const isUp = lastVal >= firstVal;
  const stroke = isUp ? "#10b981" : "#f43f5e";
  const periodPct = firstVal > 0 ? ((lastVal - firstVal) / firstVal) * 100 : 0;
  const lastCoord = coords[coords.length - 1];

  const dayHint =
    changePct != null && Number.isFinite(changePct)
      ? ` · Jour ${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%`
      : "";
  const tooltip = `Tendance 3M (${symbol}) : ${periodPct >= 0 ? "+" : ""}${periodPct.toFixed(2)}%${dayHint} · Bas ${minVal.toFixed(2)} · Haut ${maxVal.toFixed(2)} · Dernier ${lastVal.toFixed(2)}`;

  return (
    <div
      className={`finance-sparkline-wrap ${compact ? "is-compact" : ""} ${isUp ? "is-up" : "is-down"}`}
      title={tooltip}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="finance-sparkline-svg"
        role="img"
        aria-label={tooltip}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <line
          x1={padX}
          y1={baselineY}
          x2={width - padX}
          y2={baselineY}
          stroke={stroke}
          strokeOpacity="0.35"
          strokeWidth="1"
          strokeDasharray="2 2"
        />
        <path d={areaD} fill={`url(#${gradId})`} />
        <path
          d={lineD}
          fill="none"
          stroke={stroke}
          strokeWidth={compact ? "1.6" : "1.8"}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={lastCoord.x} cy={lastCoord.y} r={compact ? "2.1" : "2.4"} fill={stroke} />
      </svg>
    </div>
  );
}

export function FinanceIndexCompositionDrawer({
  composition,
  performances,
  performancesLoading = false,
  importingWatchlist = false,
  importBanner = null,
  loading,
  error,
  selectedSymbol,
  onSelectStock,
  onAddWatchlist,
  onLoadPerformances,
  onImportToWatchlist,
  onRefresh,
  onClose,
}: {
  composition: IndexCompositionResponse | null;
  performances?: IndexPerformancesResponse | null;
  performancesLoading?: boolean;
  importingWatchlist?: boolean;
  importBanner?: string | null;
  loading: boolean;
  error: string | null;
  selectedSymbol?: string | null;
  onSelectStock: (item: IndexConstituent) => void;
  onAddWatchlist?: (item: IndexConstituent) => Promise<void>;
  onLoadPerformances?: (forceRefresh?: boolean) => Promise<void>;
  onImportToWatchlist?: () => Promise<void>;
  onRefresh: () => void;
  onClose: () => void;
}) {
  const [viewMode, setViewMode] = useState<"cards" | "table" | null>(null);
  const effectiveViewMode: "cards" | "table" =
    viewMode ?? ((performances?.summary?.synced_today_count ?? 0) > 0 ? "table" : "cards");
  const [filterText, setFilterText] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [onlyCached, setOnlyCached] = useState(false);
  const [visibleLimit, setVisibleLimit] = useState(PAGE_STEP);
  const [addingSym, setAddingSym] = useState<string | null>(null);
  const [addedSyms, setAddedSyms] = useState<Record<string, boolean>>({});
  const [sortKey, setSortKey] = useState<PerfSortKey>("change_1d_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const activeItems = useMemo<(IndexConstituent | IndexPerformanceItem)[]>(() => {
    if (effectiveViewMode === "table" && performances?.items?.length) {
      return performances.items;
    }
    const base = composition?.constituents || [];
    if (!performances?.items?.length) {
      return base;
    }
    const perfByKey = new Map<string, IndexPerformanceItem>();
    for (const p of performances.items) {
      if (p.symbol) perfByKey.set(p.symbol.toUpperCase(), p);
      if (p.eod_ticker) perfByKey.set(p.eod_ticker.toUpperCase(), p);
      if (p.yahoo_symbol) perfByKey.set(p.yahoo_symbol.toUpperCase(), p);
    }
    return base.map(c => {
      const match =
        perfByKey.get((c.symbol || "").toUpperCase()) ||
        perfByKey.get((c.eod_ticker || "").toUpperCase()) ||
        perfByKey.get((c.yahoo_symbol || "").toUpperCase());
      if (!match) return c;
      return {
        ...c,
        currency: match.currency ?? c.currency,
        price: match.price ?? c.price,
        change_1d_pct: match.change_1d_pct ?? c.change_1d_pct,
        sparkline: match.sparkline?.length ? match.sparkline : c.sparkline,
        cached_in_warehouse: match.cached_in_warehouse || c.cached_in_warehouse,
      };
    });
  }, [effectiveViewMode, performances, composition]);

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    return activeItems.filter(c => {
      if (onlyCached && !c.cached_in_warehouse) return false;
      if (sectorFilter && c.sector !== sectorFilter) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.symbol.toLowerCase().includes(q) ||
        c.yahoo_symbol.toLowerCase().includes(q) ||
        c.sector.toLowerCase().includes(q)
      );
    });
  }, [activeItems, filterText, sectorFilter, onlyCached]);

  const sortedPerfItems = useMemo(() => {
    const list = [...filtered] as IndexPerformanceItem[];
    list.sort((a, b) => {
      if (sortKey === "name") {
        const cmp = a.name.localeCompare(b.name, "fr");
        return sortDir === "asc" ? cmp : -cmp;
      }
      const va = a[sortKey] ?? null;
      const vb = b[sortKey] ?? null;
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      return sortDir === "asc" ? Number(va) - Number(vb) : Number(vb) - Number(va);
    });
    return list;
  }, [filtered, sortKey, sortDir]);

  const visibleItems = filtered.slice(0, visibleLimit);
  const remaining = Math.max(0, filtered.length - visibleItems.length);
  const selectedUpper = (selectedSymbol || "").toUpperCase();

  function toggleSort(key: PerfSortKey) {
    if (sortKey === key) {
      setSortDir(prev => (prev === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  function renderSortIcon(key: PerfSortKey) {
    if (sortKey !== key) return null;
    return sortDir === "asc" ? <ArrowUp size={11} /> : <ArrowDown size={11} />;
  }

  async function handleSwitchToTable() {
    setViewMode("table");
    if (!performances && onLoadPerformances && !performancesLoading) {
      await onLoadPerformances(false);
    }
  }

  async function handleBatchLoad(forceRefresh = false) {
    setViewMode("table");
    if (onLoadPerformances) {
      await onLoadPerformances(forceRefresh);
    }
  }

  async function handleAdd(e: React.MouseEvent, item: IndexConstituent) {
    e.stopPropagation();
    if (!onAddWatchlist || addingSym === item.symbol) return;
    setAddingSym(item.symbol);
    try {
      await onAddWatchlist(item);
      setAddedSyms(prev => ({ ...prev, [item.symbol]: true }));
    } finally {
      setAddingSym(null);
    }
  }

  return (
    <section className="finance-index-drawer" aria-label="Composition de l'indice">
      <div className="finance-index-drawer-head">
        <div className="finance-index-drawer-title">
          {composition ? (
            <>
              <span className="finance-index-drawer-flag">{composition.index.flag}</span>
              <div>
                <strong>
                  Composition {composition.index.name} ({composition.constituents.length} valeurs)
                </strong>
                <small>
                  {composition.index.region} · {composition.index.eod_ticker} · Source : {composition.index.source} ·{" "}
                  {performances?.index?.cached_count ?? composition.index.cached_count} en entrepôt
                  {(performances?.summary?.synced_today_count ?? composition.index.synced_today_count ?? 0) > 0
                    ? ` · ${performances?.summary?.synced_today_count ?? composition.index.synced_today_count} sauvées aujourd'hui`
                    : ""}
                </small>
              </div>
            </>
          ) : (
            <strong>Chargement de la composition…</strong>
          )}
        </div>
        <div className="finance-index-drawer-actions">
          {composition && composition.constituents.length > 0 && (
            <>
              <div className="finance-timeframe-selector" role="group" aria-label="Mode d'affichage de l'indice">
                <button
                  type="button"
                  className={`finance-tf-btn ${effectiveViewMode === "cards" ? "active" : ""}`}
                  onClick={() => setViewMode("cards")}
                  title="Vue en cartes"
                >
                  <LayoutGrid size={12} />
                  <span>Cartes</span>
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${effectiveViewMode === "table" ? "active" : ""}`}
                  onClick={() => void handleSwitchToTable()}
                  title="Afficher le tableau comparatif des performances"
                >
                  <Table2 size={12} />
                  <span>Tableau Perfos</span>
                </button>
              </div>
              {onLoadPerformances && (
                <button
                  type="button"
                  className="finance-tf-btn active finance-stmt-refresh-btn"
                  disabled={performancesLoading || loading}
                  onClick={() =>
                    void handleBatchLoad(
                      Boolean(
                        performances &&
                          performances.summary.loaded_count >= performances.summary.total_count,
                      ),
                    )
                  }
                  title="Télécharger les actions manquantes ou recalculer toutes les performances depuis le réseau"
                >
                  {performancesLoading ? <LoaderCircle size={12} className="spin" /> : <BarChart2 size={12} />}
                  <span>
                    {performancesLoading
                      ? "Chargement de l'indice…"
                      : performances && performances.summary.loaded_count < performances.summary.total_count
                        ? "Compléter l'indice"
                        : performances
                          ? "Recalculer perfos"
                          : "Charger tout l'indice"}
                  </span>
                </button>
              )}
              {onImportToWatchlist && (
                <button
                  type="button"
                  className="finance-tf-btn finance-stmt-refresh-btn"
                  disabled={importingWatchlist || loading}
                  onClick={() => void onImportToWatchlist()}
                  title={`Créer ou compléter une liste « ${composition.index.name} » avec toutes les valeurs de cet indice`}
                >
                  {importingWatchlist ? <LoaderCircle size={12} className="spin" /> : <FolderPlus size={12} />}
                  <span>Liste « {composition.index.name} »</span>
                </button>
              )}
            </>
          )}
          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={loading}
            onClick={onRefresh}
            title="Re-synchroniser la composition depuis EODHD"
          >
            <RefreshCw size={12} className={loading ? "spin" : ""} />
            <span>Actualiser</span>
          </button>
          <button
            type="button"
            className="finance-tf-btn"
            onClick={onClose}
            aria-label="Fermer la composition de l'indice"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {importBanner && <div className="finance-index-import-banner">✓ {importBanner}</div>}

      {composition && (
        <div className="finance-index-drawer-filters">
          <div className="finance-index-filter-input-wrap">
            <Search size={13} />
            <input
              type="text"
              value={filterText}
              onChange={e => {
                setFilterText(e.target.value);
                setVisibleLimit(PAGE_STEP);
              }}
              placeholder={`Filtrer dans ${composition.index.name} (nom, ticker, secteur)…`}
            />
          </div>
          {composition.index.sectors.length > 0 && (
            <select
              className="finance-index-sector-select"
              value={sectorFilter}
              onChange={e => {
                setSectorFilter(e.target.value);
                setVisibleLimit(PAGE_STEP);
              }}
              aria-label="Filtrer par secteur"
            >
              <option value="">Tous les secteurs ({composition.index.sectors.length})</option>
              {composition.index.sectors.map(sec => (
                <option key={sec} value={sec}>
                  {sec}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className={`finance-tf-btn ${onlyCached ? "active" : ""}`}
            onClick={() => {
              setOnlyCached(prev => !prev);
              setVisibleLimit(PAGE_STEP);
            }}
            title="Afficher uniquement les actions déjà présentes dans la base locale"
          >
            <Database size={12} />
            <span>En entrepôt ({composition.index.cached_count})</span>
          </button>
          <span className="finance-index-filter-count">
            {filtered.length} / {composition.constituents.length}
          </span>
        </div>
      )}

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {loading && !composition ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>Récupération des constituants…</span>
        </div>
      ) : effectiveViewMode === "table" && performancesLoading && !performances ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>
            Chargement de toutes les actions de {composition?.index.name || "l'indice"} en entrepôt et calcul des performances…
          </span>
        </div>
      ) : effectiveViewMode === "table" && performances ? (
        <>
          <div className="finance-index-perf-summary">
            <div className="finance-index-perf-kpi">
              <span>Actions chargées</span>
              <strong>
                {performances.summary.loaded_count} / {performances.summary.total_count}
              </strong>
              {(performances.summary.synced_today_count ?? 0) > 0 && (
                <small className="text-emerald">
                  Sauvegardé aujourd&apos;hui
                  {performances.summary.last_synced_at
                    ? ` · ${new Date(performances.summary.last_synced_at).toLocaleTimeString("fr-FR", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}`
                    : ""}
                  {(performances.summary.fetched_count ?? 0) === 0
                    ? " (100% BDD)"
                    : (performances.summary.from_cache_count ?? 0) > 0
                      ? ` (${performances.summary.from_cache_count} BDD · ${performances.summary.fetched_count} réseau)`
                      : ""}
                </small>
              )}
            </div>
            <div className="finance-index-perf-kpi">
              <span>Hausses / Baisses (1J)</span>
              <strong>
                <span className="text-emerald">{performances.summary.gainers_1d} ↑</span> ·{" "}
                <span className="text-rose">{performances.summary.losers_1d} ↓</span>
              </strong>
            </div>
            <div className="finance-index-perf-kpi">
              <span>Moy. Jour</span>
              <IndexPerfCell value={performances.summary.avg_1d_pct} />
            </div>
            <div className="finance-index-perf-kpi">
              <span>Moy. Mois</span>
              <IndexPerfCell value={performances.summary.avg_1m_pct} />
            </div>
            <div className="finance-index-perf-kpi">
              <span>Moy. YTD</span>
              <IndexPerfCell value={performances.summary.avg_ytd_pct} />
            </div>
            <div className="finance-index-perf-kpi">
              <span>Moy. 1 An</span>
              <IndexPerfCell value={performances.summary.avg_1y_pct} />
            </div>
          </div>

          {sortedPerfItems.length === 0 ? (
            <div className="finance-index-drawer-empty">
              Aucune valeur ne correspond à ce filtre dans cet indice.
            </div>
          ) : (
            <div className="finance-table-wrapper finance-index-perf-table-wrap">
              <table className="finance-data-table finance-watchlist-table">
                <thead>
                  <tr>
                    <th>
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("name")}>
                        Action {renderSortIcon("name")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("weight_pct")}>
                        Poids {renderSortIcon("weight_pct")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("price")}>
                        Cours {renderSortIcon("price")}
                      </button>
                    </th>
                    <th className="finance-sparkline-col">Courbe (3M)</th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1d_pct")}>
                        Jour {renderSortIcon("change_1d_pct")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1w_pct")}>
                        Semaine {renderSortIcon("change_1w_pct")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1m_pct")}>
                        Mois {renderSortIcon("change_1m_pct")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_3m_pct")}>
                        3 Mois {renderSortIcon("change_3m_pct")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_ytd_pct")}>
                        YTD {renderSortIcon("change_ytd_pct")}
                      </button>
                    </th>
                    <th className="is-num">
                      <button type="button" className="finance-sort-btn" onClick={() => toggleSort("change_1y_pct")}>
                        1 An {renderSortIcon("change_1y_pct")}
                      </button>
                    </th>
                    <th className="is-actions"></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPerfItems.map(item => {
                    const isSelected =
                      selectedUpper &&
                      (selectedUpper === item.symbol.toUpperCase() ||
                        selectedUpper === item.eod_ticker.toUpperCase() ||
                        selectedUpper === item.yahoo_symbol.toUpperCase());
                    const isAdded = Boolean(addedSyms[item.symbol]);
                    const isBusy = addingSym === item.symbol;
                    return (
                      <tr
                        key={item.symbol}
                        className={`finance-watchlist-row ${isSelected ? "is-selected" : ""}`}
                        onClick={() => onSelectStock(item)}
                        title={`Ouvrir ${item.name} (${item.eod_ticker})`}
                      >
                        <td>
                          <div className="finance-wl-identity">
                            <strong>{item.name}</strong>
                            <div className="finance-wl-meta">
                              <span className="finance-symbol-tag">{item.eod_ticker || item.symbol}</span>
                              {item.sector && <span className="finance-wl-exch">{item.sector}</span>}
                            </div>
                          </div>
                        </td>
                        <td className="is-num">
                          {item.weight_pct != null ? `${item.weight_pct.toFixed(2)}%` : <span className="finance-perf-na">—</span>}
                        </td>
                        <td className="is-num">
                          {item.price != null ? (
                            <strong className="finance-wl-price">
                              {item.price.toFixed(2)} <small>{item.currency}</small>
                            </strong>
                          ) : (
                            <span className="finance-perf-na">—</span>
                          )}
                        </td>
                        <td className="finance-sparkline-cell">
                          <IndexStockSparkline
                            symbol={item.symbol}
                            points={item.sparkline}
                            changePct={item.change_1d_pct}
                            compact
                            loading={performancesLoading}
                          />
                        </td>
                        <td className="is-num"><IndexPerfCell value={item.change_1d_pct} /></td>
                        <td className="is-num"><IndexPerfCell value={item.change_1w_pct} /></td>
                        <td className="is-num"><IndexPerfCell value={item.change_1m_pct} /></td>
                        <td className="is-num"><IndexPerfCell value={item.change_3m_pct} /></td>
                        <td className="is-num"><IndexPerfCell value={item.change_ytd_pct} /></td>
                        <td className="is-num"><IndexPerfCell value={item.change_1y_pct} /></td>
                        <td className="is-actions">
                          {onAddWatchlist && (
                            <button
                              type="button"
                              className={`finance-index-add-btn ${isAdded ? "is-added" : ""}`}
                              disabled={isBusy}
                              onClick={e => void handleAdd(e, item)}
                              title={isAdded ? "Ajoutée au suivi" : "Ajouter au tableau de suivi"}
                              aria-label={`Ajouter ${item.name} au suivi`}
                            >
                              {isBusy ? <LoaderCircle size={11} className="spin" /> : isAdded ? <Check size={11} /> : <Plus size={11} />}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : visibleItems.length === 0 ? (
        <div className="finance-index-drawer-empty">
          {composition && composition.constituents.length === 0
            ? `EODHD ne fournit pas le détail « Components » pour ${composition.index.eod_ticker}. Vous pouvez rechercher directement les valeurs dans la barre ci-dessus ou choisir un autre indice.`
            : "Aucune valeur ne correspond à ce filtre dans cet indice."}
        </div>
      ) : (
        <>
          <div className="finance-index-constituents-grid">
            {visibleItems.map(item => {
              const isSelected =
                selectedUpper &&
                (selectedUpper === item.symbol.toUpperCase() ||
                  selectedUpper === item.eod_ticker.toUpperCase() ||
                  selectedUpper === item.yahoo_symbol.toUpperCase());
              const isAdded = Boolean(addedSyms[item.symbol]);
              const isBusy = addingSym === item.symbol;
              return (
                <div
                  key={item.symbol}
                  role="button"
                  tabIndex={0}
                  className={`finance-index-stock-card ${isSelected ? "is-selected" : ""}`}
                  onClick={() => onSelectStock(item)}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectStock(item);
                    }
                  }}
                  title={`Charger ${item.name} (${item.eod_ticker})`}
                >
                  <div className="finance-index-stock-top">
                    <span className="finance-symbol-tag">{item.yahoo_symbol || item.symbol}</span>
                    <div className="finance-index-stock-badges">
                      {item.cached_in_warehouse && (
                        <span className="finance-cached-dot" title="Données déjà en entrepôt local" />
                      )}
                      {onAddWatchlist && (
                        <button
                          type="button"
                          className={`finance-index-add-btn ${isAdded ? "is-added" : ""}`}
                          disabled={isBusy}
                          onClick={e => void handleAdd(e, item)}
                          title={isAdded ? "Ajoutée au suivi" : "Ajouter au tableau de suivi"}
                          aria-label={`Ajouter ${item.name} au suivi`}
                        >
                          {isBusy ? (
                            <LoaderCircle size={11} className="spin" />
                          ) : isAdded ? (
                            <Check size={11} />
                          ) : (
                            <Plus size={11} />
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                  <strong className="finance-index-stock-name">{item.name}</strong>
                  <div className="finance-index-stock-spark-row">
                    <div className="finance-index-stock-price-block">
                      {item.price != null ? (
                        <strong className="finance-index-stock-price">
                          {item.price.toFixed(2)}{" "}
                          <small>{item.currency || composition?.index.currency || ""}</small>
                        </strong>
                      ) : (
                        <span className="finance-perf-na">—</span>
                      )}
                      <IndexPerfCell value={item.change_1d_pct} />
                    </div>
                    <IndexStockSparkline
                      symbol={item.symbol}
                      points={item.sparkline}
                      changePct={item.change_1d_pct}
                      loading={performancesLoading}
                    />
                  </div>
                  {(item.sector || item.weight_pct != null) && (
                    <small className="finance-index-stock-meta">
                      {item.sector || item.exchange}
                      {item.weight_pct != null ? ` · ${item.weight_pct.toFixed(2)}%` : ""}
                    </small>
                  )}
                </div>
              );
            })}
          </div>
          {remaining > 0 && (
            <div className="finance-index-drawer-more">
              <button
                type="button"
                className="finance-tf-btn"
                onClick={() => setVisibleLimit(prev => prev + PAGE_STEP)}
              >
                Afficher {Math.min(PAGE_STEP, remaining)} de plus ({remaining} restantes)
              </button>
              <button
                type="button"
                className="finance-tf-btn"
                onClick={() => setVisibleLimit(filtered.length)}
              >
                Tout afficher ({filtered.length})
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
