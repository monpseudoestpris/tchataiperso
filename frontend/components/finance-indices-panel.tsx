"use client";

import { Check, ChevronDown, ChevronUp, Database, Globe2, LoaderCircle, Plus, RefreshCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  fetchEodhdIndxCatalog,
  type EodhdIndxCatalogItem,
  type IndexCompositionResponse,
  type IndexConstituent,
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
  onToggleIndex,
  onToggleCatalog,
  onOpenMinorTier,
}: {
  indices: PrincipalIndexInfo[];
  warehouse: WarehouseOverview | null;
  activeCode: string | null;
  loadingIndex: boolean;
  catalogOpen: boolean;
  onToggleIndex: (code: string) => void;
  onToggleCatalog: () => void;
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

export function FinanceIndexCompositionDrawer({
  composition,
  loading,
  error,
  selectedSymbol,
  onSelectStock,
  onAddWatchlist,
  onRefresh,
  onClose,
}: {
  composition: IndexCompositionResponse | null;
  loading: boolean;
  error: string | null;
  selectedSymbol?: string | null;
  onSelectStock: (item: IndexConstituent) => void;
  onAddWatchlist?: (item: IndexConstituent) => Promise<void>;
  onRefresh: () => void;
  onClose: () => void;
}) {
  const [filterText, setFilterText] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [onlyCached, setOnlyCached] = useState(false);
  const [visibleLimit, setVisibleLimit] = useState(PAGE_STEP);
  const [addingSym, setAddingSym] = useState<string | null>(null);
  const [addedSyms, setAddedSyms] = useState<Record<string, boolean>>({});

  const filtered = useMemo(() => {
    const items = composition?.constituents || [];
    const q = filterText.trim().toLowerCase();
    return items.filter(c => {
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
  }, [composition, filterText, sectorFilter, onlyCached]);

  const visibleItems = filtered.slice(0, visibleLimit);
  const remaining = Math.max(0, filtered.length - visibleItems.length);
  const selectedUpper = (selectedSymbol || "").toUpperCase();

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
                  {composition.index.cached_count} déjà chargées en entrepôt
                </small>
              </div>
            </>
          ) : (
            <strong>Chargement de la composition…</strong>
          )}
        </div>
        <div className="finance-index-drawer-actions">
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
