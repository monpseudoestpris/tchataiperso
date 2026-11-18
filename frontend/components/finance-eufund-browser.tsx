"use client";

import { Check, Globe, LoaderCircle, Plus, RefreshCw, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchExchangeCatalog,
  searchEodhdFundsLive,
  type EodhdEufundItem,
  type FinanceWatchlistMeta,
  type SupportedExchangeInfo,
} from "@/lib/api";

const PAGE_STEP = 60;

const DEFAULT_EXCHANGES: SupportedExchangeInfo[] = [
  { code: "EUFUND", label: "Fonds EU", description: "Fonds européens OPCVM / SICAV", total: 0, synced_at: null },
  { code: "PA", label: "Paris (PA)", description: "Euronext Paris (actions & ETF)", total: 0, synced_at: null },
  { code: "US", label: "US", description: "NYSE / NASDAQ / ARCA", total: 0, synced_at: null },
  { code: "XETRA", label: "Xetra", description: "Allemagne (Deutsche Börse)", total: 0, synced_at: null },
  { code: "LSE", label: "Londres (LSE)", description: "London Stock Exchange", total: 0, synced_at: null },
  { code: "CC", label: "Crypto (CC)", description: "Cryptomonnaies", total: 0, synced_at: null },
];

export function FinanceEufundBrowser({
  selectedSymbol,
  watchlists,
  activeListId,
  onSelectFund,
  onAddWatchlist,
  onClose,
}: {
  selectedSymbol?: string | null;
  watchlists: FinanceWatchlistMeta[];
  activeListId: string | null;
  onSelectFund: (item: EodhdEufundItem) => void;
  onAddWatchlist: (item: EodhdEufundItem, targetListId?: string | null) => Promise<void>;
  onClose: () => void;
}) {
  const [exchange, setExchange] = useState<string>("EUFUND");
  const [query, setQuery] = useState("");
  const [currency, setCurrency] = useState("");
  const [country, setCountry] = useState("");
  const [instrumentType, setInstrumentType] = useState("");
  const [fundFamily, setFundFamily] = useState("");
  const [items, setItems] = useState<EodhdEufundItem[]>([]);
  const [supportedExchanges, setSupportedExchanges] = useState<SupportedExchangeInfo[]>(DEFAULT_EXCHANGES);
  const [currencies, setCurrencies] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [fundFamilies, setFundFamilies] = useState<string[]>([]);
  const [meta, setMeta] = useState<{ total: number; matched: number; source: string; syncedAt: string | null } | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [liveSearching, setLiveSearching] = useState(false);
  const [liveSource, setLiveSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [targetListId, setTargetListId] = useState<string>("");
  const [addingTicker, setAddingTicker] = useState<string | null>(null);
  const [addedTickers, setAddedTickers] = useState<Record<string, boolean>>({});
  const effectiveTargetListId = targetListId || activeListId || watchlists[0]?.id || "";

  async function loadCatalog(opts?: { offset?: number; append?: boolean; refresh?: boolean; targetExchange?: string }) {
    const off = opts?.offset ?? 0;
    const append = Boolean(opts?.append);
    const refresh = Boolean(opts?.refresh);
    const exch = opts?.targetExchange ?? exchange;
    if (append) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    setError(null);
    setLiveSource(null);
    try {
      const res = await fetchExchangeCatalog({
        exchange: exch,
        q: query,
        currency,
        country,
        type: instrumentType,
        fundFamily,
        limit: PAGE_STEP,
        offset: off,
        refresh,
      });
      setItems(prev => (append ? [...prev, ...(res.items || [])] : res.items || []));
      if (res.supported_exchanges && res.supported_exchanges.length > 0) {
        setSupportedExchanges(res.supported_exchanges);
      }
      setCurrencies(res.currencies || []);
      setCountries(res.countries || []);
      setTypes(res.types || []);
      setFundFamilies(res.fund_families || []);
      setMeta({
        total: res.total,
        matched: res.matched,
        source: res.source,
        syncedAt: res.synced_at,
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impossible de charger le catalogue EODHD.");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadCatalog({ offset: 0, append: false, refresh: false });
    }, query ? 180 : 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exchange, query, currency, country, instrumentType, fundFamily]);

  function handleSelectExchange(nextExchange: string) {
    setExchange(nextExchange);
    setCurrency("");
    setCountry("");
    setInstrumentType("");
    setFundFamily("");
  }

  async function handleLiveSearch() {
    const clean = query.trim();
    if (clean.length < 2 || liveSearching) return;
    setLiveSearching(true);
    setError(null);
    try {
      const res = await searchEodhdFundsLive(clean, 40);
      setItems(res.items || []);
      setLiveSource(res.source);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Échec de la recherche EODHD (type=fund).");
    } finally {
      setLiveSearching(false);
    }
  }

  async function handleAdd(e: React.MouseEvent, item: EodhdEufundItem) {
    e.stopPropagation();
    if (addingTicker === item.eod_ticker) return;
    setAddingTicker(item.eod_ticker);
    setError(null);
    try {
      await onAddWatchlist(item, effectiveTargetListId || null);
      setAddedTickers(prev => ({ ...prev, [item.eod_ticker]: true }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Impossible d'ajouter ${item.name} à la liste.`);
    } finally {
      setAddingTicker(null);
    }
  }

  const remaining = meta && !liveSource ? Math.max(0, meta.matched - items.length) : 0;
  const selectedUpper = (selectedSymbol || "").toUpperCase();
  const totalAllExchanges = supportedExchanges.reduce((acc, s) => acc + (s.total || 0), 0);

  return (
    <section className="finance-index-drawer finance-eufund-drawer" aria-label="Catalogue multi-marchés et fonds EODHD">
      <div className="finance-index-drawer-head">
        <div className="finance-index-drawer-title">
          <span className="finance-index-drawer-flag">🏦</span>
          <div>
            <strong>
              Catalogue Marchés &amp; Fonds EODHD · {exchange === "ALL" ? "Tous les marchés" : exchange} (
              {meta ? `${meta.total.toLocaleString("fr-FR")} titres` : "…"})
            </strong>
            <small>
              {liveSource
                ? `Recherche en direct : ${liveSource}`
                : meta
                  ? `Source : ${meta.source}${
                      meta.syncedAt ? ` · Synchro ${new Date(meta.syncedAt).toLocaleDateString("fr-FR")}` : ""
                    } · Recherche FTS5 locale instantanée`
                  : `Interrogation de /api/exchange-symbol-list/${exchange}…`}
            </small>
          </div>
        </div>
        <div className="finance-index-drawer-actions">
          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={loading}
            onClick={() => void loadCatalog({ offset: 0, append: false, refresh: true })}
            title={
              exchange === "ALL"
                ? "Re-télécharger tous les marchés configurés depuis EODHD"
                : `Re-télécharger la liste complète ${exchange} depuis EODHD`
            }
          >
            <RefreshCw size={12} className={loading ? "spin" : ""} />
            <span>{exchange === "ALL" ? "Synchroniser tout" : `Synchroniser ${exchange}`}</span>
          </button>
          <button type="button" className="finance-tf-btn" onClick={onClose} aria-label="Fermer le catalogue des marchés">
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="finance-index-drawer-filters">
        <div className="finance-timeframe-selector" role="group" aria-label="Choisir une place boursière">
          {supportedExchanges.map(ex => (
            <button
              key={ex.code}
              type="button"
              className={`finance-tf-btn ${exchange === ex.code ? "active" : ""}`}
              onClick={() => handleSelectExchange(ex.code)}
              title={ex.description}
            >
              <span>{ex.label}</span>
              {ex.total > 0 && <small> ({ex.total.toLocaleString("fr-FR")})</small>}
            </button>
          ))}
          <button
            type="button"
            className={`finance-tf-btn ${exchange === "ALL" ? "active" : ""}`}
            onClick={() => handleSelectExchange("ALL")}
            title="Rechercher simultanément sur tous les marchés déjà synchronisés en base"
          >
            <span>Tous</span>
            {totalAllExchanges > 0 && <small> ({totalAllExchanges.toLocaleString("fr-FR")})</small>}
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
            placeholder="Rechercher par nom, ticker, ISIN ou société de gestion (ex. Sextant, LVMH, Amundi, NVDA)…"
          />
        </div>

        {types.length > 0 && (
          <select
            className="finance-index-sector-select"
            value={instrumentType}
            onChange={e => setInstrumentType(e.target.value)}
            aria-label="Filtrer par type d'actif"
          >
            <option value="">Tous types ({types.length})</option>
            {types.map(t => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        )}

        {fundFamilies.length > 0 && (
          <select
            className="finance-index-sector-select"
            value={fundFamily}
            onChange={e => setFundFamily(e.target.value)}
            aria-label="Filtrer par société de gestion"
          >
            <option value="">Toutes sociétés de gestion</option>
            {fundFamilies.map(fam => (
              <option key={fam} value={fam}>
                {fam}
              </option>
            ))}
          </select>
        )}

        {currencies.length > 0 && (
          <select
            className="finance-index-sector-select"
            value={currency}
            onChange={e => setCurrency(e.target.value)}
            aria-label="Filtrer par devise"
          >
            <option value="">Toutes devises</option>
            {currencies.map(c => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}

        {countries.length > 0 && (
          <select
            className="finance-index-sector-select"
            value={country}
            onChange={e => setCountry(e.target.value)}
            aria-label="Filtrer par pays"
          >
            <option value="">Tous pays</option>
            {countries.map(c => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}

        {watchlists.length > 1 && (
          <select
            className="finance-index-sector-select"
            value={effectiveTargetListId}
            onChange={e => setTargetListId(e.target.value)}
            aria-label="Liste cible pour l'ajout"
            title="Liste dans laquelle le bouton + ajoutera la valeur"
          >
            {watchlists.map(wl => (
              <option key={wl.id} value={wl.id}>
                Liste : {wl.name}
              </option>
            ))}
          </select>
        )}

        {query.trim().length >= 2 && (
          <button
            type="button"
            className={`finance-tf-btn ${liveSource ? "active" : ""}`}
            onClick={() => void handleLiveSearch()}
            disabled={liveSearching}
            title="Interroger l'API EODHD /api/search?type=fund en direct (utile pour un ISIN précis)"
          >
            {liveSearching ? <LoaderCircle size={12} className="spin" /> : <Globe size={12} />}
            <span>Recherche EODHD (type=fund)</span>
          </button>
        )}

        {meta && !liveSource && (
          <span className="finance-index-filter-count">
            {items.length} / {meta.matched.toLocaleString("fr-FR")} titres
          </span>
        )}
      </div>

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {loading && items.length === 0 ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>Synchronisation du catalogue {exchange} EODHD…</span>
        </div>
      ) : items.length === 0 ? (
        <div className="finance-index-drawer-empty">
          <span>
            Aucun titre trouvé dans le catalogue local pour cette recherche.
          </span>
          {query.trim().length >= 2 && (
            <button
              type="button"
              className="finance-tf-btn"
              onClick={() => void handleLiveSearch()}
              disabled={liveSearching}
            >
              {liveSearching ? <LoaderCircle size={12} className="spin" /> : <Globe size={12} />}
              <span>Tester la recherche en direct EODHD (type=fund)</span>
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="finance-index-constituents-grid">
            {items.map(item => {
              const isSelected =
                !!selectedUpper &&
                (selectedUpper === item.eod_ticker.toUpperCase() || selectedUpper === item.symbol.toUpperCase());
              const isAdded = Boolean(addedTickers[item.eod_ticker]);
              const isBusy = addingTicker === item.eod_ticker;
              return (
                <div
                  key={item.eod_ticker}
                  role="button"
                  tabIndex={0}
                  className={`finance-index-stock-card ${isSelected ? "is-selected" : ""}`}
                  onClick={() => onSelectFund(item)}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelectFund(item);
                    }
                  }}
                  title={`Charger ${item.name} (${item.eod_ticker})`}
                >
                  <div className="finance-index-stock-top">
                    <span className="finance-symbol-tag">{item.eod_ticker}</span>
                    <div className="finance-index-stock-badges">
                      {item.currency && <span className="finance-search-dropdown-idx">{item.currency}</span>}
                      {item.cached_in_warehouse && (
                        <span className="finance-cached-dot" title="Cours / données déjà en entrepôt local" />
                      )}
                      <button
                        type="button"
                        className={`finance-index-add-btn ${isAdded ? "is-added" : ""}`}
                        disabled={isBusy}
                        onClick={e => void handleAdd(e, item)}
                        title={isAdded ? "Ajouté à votre liste" : "Ajouter ce titre à votre liste"}
                        aria-label={`Ajouter ${item.name} à votre liste`}
                      >
                        {isBusy ? (
                          <LoaderCircle size={11} className="spin" />
                        ) : isAdded ? (
                          <Check size={11} />
                        ) : (
                          <Plus size={11} />
                        )}
                      </button>
                    </div>
                  </div>
                  <strong className="finance-index-stock-name">{item.name}</strong>
                  <small className="finance-index-stock-meta">
                    {[
                      item.exchange,
                      item.type,
                      item.fund_family || "",
                      item.isin ? `ISIN ${item.isin}` : "",
                      item.country,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </div>
              );
            })}
          </div>
          {remaining > 0 && (
            <div className="finance-index-drawer-more">
              <button
                type="button"
                className="finance-tf-btn"
                disabled={loadingMore}
                onClick={() => void loadCatalog({ offset: items.length, append: true, refresh: false })}
              >
                {loadingMore ? <LoaderCircle size={12} className="spin" /> : null}
                <span>
                  Afficher {Math.min(PAGE_STEP, remaining)} de plus ({remaining.toLocaleString("fr-FR")} restants)
                </span>
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
