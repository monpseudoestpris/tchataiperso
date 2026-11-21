"use client";

import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  searchFinanceCatalog,
  type CatalogSearchItem,
  type FinanceWatchlistMeta,
  type WatchlistItem,
} from "@/lib/api";

import styles from "./finance-fullscreen-ticker-switcher.module.css";

type FinanceFullscreenTickerSwitcherProps = {
  currentSymbol: string;
  currentEodTicker?: string | null;
  currentYahooSymbol?: string | null;
  currentName: string;
  currentPrice?: number | null;
  currentCurrency?: string | null;
  currentChangePct?: number | null;
  loading: boolean;
  watchlist: WatchlistItem[];
  watchlists: FinanceWatchlistMeta[];
  activeListId: string | null;
  watchlistLoading: boolean;
  quickSuggestions: string[];
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  onSelectTicker: (target: string, displayName?: string) => void | Promise<void>;
  onSelectWatchlistTab: (listId: string) => void | Promise<void>;
};

type NavigableOption = {
  key: string;
  target: string;
  displayName: string;
  symbolTag: string;
  subtitle?: string;
  metaBadge?: string;
  price?: number | null;
  currency?: string;
  change1dPct?: number | null;
  cached?: boolean;
  isCurrent?: boolean;
  source: "watchlist" | "catalog" | "direct";
};

function normalizeKey(v?: string | null): string {
  return (v || "").trim().toUpperCase();
}

/**
 * Sélecteur / recherche de ticker dédié au mode Plein Écran du graphique financier.
 * Permet de rechercher n'importe quel titre (catalogue local + saisie libre),
 * de parcourir ses listes de suivi et de passer au titre précédent/suivant en 1 clic.
 */
export function FinanceFullscreenTickerSwitcher({
  currentSymbol,
  currentEodTicker,
  currentYahooSymbol,
  currentName,
  currentPrice,
  currentCurrency,
  currentChangePct,
  loading,
  watchlist,
  watchlists,
  activeListId,
  watchlistLoading,
  quickSuggestions,
  isOpen,
  onOpenChange,
  onSelectTicker,
  onSelectWatchlistTab,
}: FinanceFullscreenTickerSwitcherProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [searchText, setSearchText] = useState("");
  const [catalogMatches, setCatalogMatches] = useState<CatalogSearchItem[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const [prevIsOpen, setPrevIsOpen] = useState(isOpen);

  if (isOpen !== prevIsOpen) {
    setPrevIsOpen(isOpen);
    setHighlightedIndex(0);
    if (!isOpen) {
      setSearchText("");
      setCatalogMatches([]);
      setCatalogLoading(false);
    }
  }

  const currentKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const candidate of [currentSymbol, currentEodTicker, currentYahooSymbol]) {
      const norm = normalizeKey(candidate);
      if (norm) keys.add(norm);
    }
    return keys;
  }, [currentSymbol, currentEodTicker, currentYahooSymbol]);

  const isWatchlistItemCurrent = (item: WatchlistItem): boolean => {
    return (
      currentKeys.has(normalizeKey(item.symbol)) ||
      currentKeys.has(normalizeKey(item.eod_ticker)) ||
      currentKeys.has(normalizeKey(item.yahoo_symbol))
    );
  };

  // Focus l'input à l'ouverture
  useEffect(() => {
    if (!isOpen) return;
    const raf = window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    });
    return () => window.cancelAnimationFrame(raf);
  }, [isOpen]);

  // Ferme le popover au clic à l'extérieur
  useEffect(() => {
    if (!isOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        onOpenChange(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [isOpen, onOpenChange]);

  // Recherche catalogue debouncée
  useEffect(() => {
    if (!isOpen) return;
    const trimmed = searchText.trim();
    if (trimmed.length < 2) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setCatalogLoading(true);
      searchFinanceCatalog(trimmed, 15)
        .then(items => {
          if (!cancelled) setCatalogMatches(items);
        })
        .catch(() => {
          if (!cancelled) setCatalogMatches([]);
        })
        .finally(() => {
          if (!cancelled) setCatalogLoading(false);
        });
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [isOpen, searchText]);

  const effectiveCatalogLoading = searchText.trim().length >= 2 && catalogLoading;

  // Navigation Précédent / Suivant dans la liste de suivi active
  const currentWatchlistIdx = useMemo(
    () => watchlist.findIndex(item => isWatchlistItemCurrent(item)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [watchlist, currentKeys],
  );

  const prevWatchlistItem = useMemo(() => {
    if (watchlist.length < 2) return null;
    if (currentWatchlistIdx < 0) return watchlist[watchlist.length - 1];
    return watchlist[(currentWatchlistIdx - 1 + watchlist.length) % watchlist.length];
  }, [watchlist, currentWatchlistIdx]);

  const nextWatchlistItem = useMemo(() => {
    if (watchlist.length < 2) return null;
    if (currentWatchlistIdx < 0) return watchlist[0];
    return watchlist[(currentWatchlistIdx + 1) % watchlist.length];
  }, [watchlist, currentWatchlistIdx]);

  // Liste unifiée des options navigables au clavier
  const options = useMemo<NavigableOption[]>(() => {
    const trimmed = searchText.trim();
    const lower = trimmed.toLowerCase();
    const out: NavigableOption[] = [];
    const seenTargets = new Set<string>();

    const matchingWatchlist = trimmed
      ? watchlist.filter(item => {
          const hay = `${item.symbol} ${item.eod_ticker} ${item.yahoo_symbol} ${item.name}`.toLowerCase();
          return hay.includes(lower);
        })
      : watchlist;

    for (const item of matchingWatchlist) {
      const target = item.eod_ticker || item.yahoo_symbol || item.symbol;
      const norm = normalizeKey(target);
      if (norm) seenTargets.add(norm);
      if (item.symbol) seenTargets.add(normalizeKey(item.symbol));
      out.push({
        key: `wl-${item.id}`,
        target,
        displayName: item.name || item.symbol,
        symbolTag: item.symbol || target,
        metaBadge: item.exchange || undefined,
        price: item.price,
        currency: item.currency,
        change1dPct: item.change_1d_pct,
        isCurrent: isWatchlistItemCurrent(item),
        source: "watchlist",
      });
    }

    if (trimmed.length >= 2) {
      for (const m of catalogMatches) {
        const target = m.eod_ticker || m.yahoo_symbol || m.symbol;
        const normTarget = normalizeKey(target);
        const normSym = normalizeKey(m.symbol);
        if ((normTarget && seenTargets.has(normTarget)) || (normSym && seenTargets.has(normSym))) {
          continue;
        }
        if (normTarget) seenTargets.add(normTarget);
        out.push({
          key: `cat-${target}-${m.index_code ?? ""}`,
          target,
          displayName: m.name || target,
          symbolTag: target,
          subtitle: m.sector || undefined,
          metaBadge: m.index_code || m.exchange || undefined,
          cached: m.cached,
          isCurrent:
            currentKeys.has(normTarget) ||
            currentKeys.has(normSym) ||
            currentKeys.has(normalizeKey(m.yahoo_symbol)),
          source: "catalog",
        });
      }
    }

    if (trimmed.length > 0) {
      out.push({
        key: `direct-${trimmed}`,
        target: trimmed,
        displayName: `Rechercher « ${trimmed} »`,
        symbolTag: "Direct",
        subtitle: "Charger ce ticker, ISIN ou nom de société",
        source: "direct",
      });
    }

    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText, watchlist, catalogMatches, currentKeys]);

  // Garde l'index surligné dans les bornes
  const clampedIndex = options.length > 0 ? Math.min(highlightedIndex, options.length - 1) : 0;

  function triggerSelection(target: string, displayName?: string) {
    const clean = target.trim();
    if (!clean) return;
    onOpenChange(false);
    void onSelectTicker(clean, displayName);
  }

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (options.length > 0) {
        setHighlightedIndex(prev => (prev + 1) % options.length);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (options.length > 0) {
        setHighlightedIndex(prev => (prev - 1 + options.length) % options.length);
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (options[clampedIndex]) {
        const opt = options[clampedIndex];
        triggerSelection(opt.target, opt.source === "direct" ? opt.target : opt.displayName);
      } else if (searchText.trim()) {
        triggerSelection(searchText.trim(), searchText.trim());
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onOpenChange(false);
    }
  }

  const hasWatchlistSection = options.some(o => o.source === "watchlist");
  const hasCatalogSection = options.some(o => o.source === "catalog");

  return (
    <div className={styles.wrapper} ref={rootRef}>
      <div className={styles.triggerGroup}>
        <button
          type="button"
          className={`${styles.triggerBtn} ${isOpen ? styles.triggerBtnOpen : ""}`}
          onClick={() => onOpenChange(!isOpen)}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          title="Changer de ticker ou rechercher une valeur (action, ETF, fonds, ISIN)"
        >
          <span className={styles.triggerIcon}>
            {loading ? <LoaderCircle size={14} className="spin" /> : <Search size={14} />}
          </span>
          <span className={styles.triggerSymbol}>{currentSymbol}</span>
          <span className={styles.triggerName}>{currentName}</span>
          {currentPrice != null && (
            <span className={styles.triggerQuote}>
              {currentPrice.toFixed(2)} {currentCurrency || ""}
              {currentChangePct != null && (
                <span
                  className={
                    currentChangePct >= 0 ? styles.changePositive : styles.changeNegative
                  }
                >
                  {" "}
                  ({currentChangePct >= 0 ? "+" : ""}
                  {currentChangePct.toFixed(2)}%)
                </span>
              )}
            </span>
          )}
          <ChevronDown
            size={14}
            className={`${styles.triggerChevron} ${isOpen ? styles.triggerChevronOpen : ""}`}
          />
        </button>

        {watchlist.length >= 2 && (
          <div className={styles.stepGroup} role="group" aria-label="Parcourir la liste de suivi">
            <button
              type="button"
              className={styles.stepBtn}
              disabled={loading || !prevWatchlistItem}
              onClick={() => {
                if (!prevWatchlistItem) return;
                const target =
                  prevWatchlistItem.eod_ticker ||
                  prevWatchlistItem.yahoo_symbol ||
                  prevWatchlistItem.symbol;
                triggerSelection(target, prevWatchlistItem.name || prevWatchlistItem.symbol);
              }}
              title={
                prevWatchlistItem
                  ? `Titre précédent : ${prevWatchlistItem.name || prevWatchlistItem.symbol} (${prevWatchlistItem.symbol})`
                  : "Titre précédent"
              }
              aria-label="Titre précédent dans la liste de suivi"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              type="button"
              className={styles.stepBtn}
              disabled={loading || !nextWatchlistItem}
              onClick={() => {
                if (!nextWatchlistItem) return;
                const target =
                  nextWatchlistItem.eod_ticker ||
                  nextWatchlistItem.yahoo_symbol ||
                  nextWatchlistItem.symbol;
                triggerSelection(target, nextWatchlistItem.name || nextWatchlistItem.symbol);
              }}
              title={
                nextWatchlistItem
                  ? `Titre suivant : ${nextWatchlistItem.name || nextWatchlistItem.symbol} (${nextWatchlistItem.symbol})`
                  : "Titre suivant"
              }
              aria-label="Titre suivant dans la liste de suivi"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>

      {isOpen && (
        <div
          className={styles.popover}
          role="dialog"
          aria-label="Changer de ticker"
        >
          <div className={styles.searchRow}>
            <Search size={14} className={styles.searchRowIcon} />
            <input
              ref={inputRef}
              type="text"
              className={styles.searchInput}
              placeholder="Rechercher un ticker, une société ou un ISIN (ex. NVDA, MC.PA, Air Liquide)..."
              value={searchText}
              onChange={e => {
                setSearchText(e.target.value);
                setHighlightedIndex(0);
              }}
              onKeyDown={handleInputKeyDown}
              aria-label="Rechercher un ticker"
            />
            {effectiveCatalogLoading && <LoaderCircle size={13} className="spin" />}
            {searchText && (
              <button
                type="button"
                className={styles.clearBtn}
                onClick={() => {
                  setSearchText("");
                  setHighlightedIndex(0);
                  inputRef.current?.focus();
                }}
                aria-label="Effacer la recherche"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {!searchText.trim() && watchlists.length > 1 && (
            <div className={styles.watchlistTabs} role="tablist" aria-label="Listes de suivi">
              {watchlists.map(wl => (
                <button
                  key={wl.id}
                  type="button"
                  role="tab"
                  aria-selected={wl.id === activeListId}
                  className={`${styles.watchlistTab} ${wl.id === activeListId ? styles.watchlistTabActive : ""}`}
                  onClick={() => void onSelectWatchlistTab(wl.id)}
                  disabled={watchlistLoading}
                >
                  <span>{wl.name}</span>
                  <span className={styles.watchlistTabCount}>{wl.items_count}</span>
                </button>
              ))}
            </div>
          )}

          <div className={styles.resultsList} role="listbox" aria-label="Tickers disponibles">
            {options.length === 0 ? (
              <div className={styles.emptyState}>
                {watchlistLoading
                  ? "Chargement de la liste de suivi..."
                  : "Aucun titre dans cette liste. Saisissez un ticker ou choisissez une suggestion ci-dessous."}
              </div>
            ) : (
              options.map((opt, idx) => {
                const prevSource = idx > 0 ? options[idx - 1].source : null;
                const showWatchlistHeading = opt.source === "watchlist" && prevSource !== "watchlist";
                const showCatalogHeading = opt.source === "catalog" && prevSource !== "catalog";
                const isHighlighted = idx === clampedIndex;

                return (
                  <div key={opt.key}>
                    {showWatchlistHeading && (
                      <div className={styles.sectionHeading}>
                        {searchText.trim() ? "Dans votre liste de suivi" : "Liste de suivi"}
                      </div>
                    )}
                    {showCatalogHeading && (
                      <div className={styles.sectionHeading}>
                        {hasWatchlistSection ? "Catalogue & Entrepôt" : "Résultats catalogue"}
                      </div>
                    )}
                    {opt.source === "direct" && (hasWatchlistSection || hasCatalogSection) && (
                      <div className={styles.sectionDivider} />
                    )}
                    <button
                      type="button"
                      role="option"
                      aria-selected={opt.isCurrent || false}
                      className={`${styles.optionRow} ${isHighlighted ? styles.optionRowHighlighted : ""} ${opt.isCurrent ? styles.optionRowCurrent : ""}`}
                      onMouseEnter={() => setHighlightedIndex(idx)}
                      onMouseDown={e => {
                        e.preventDefault();
                        triggerSelection(
                          opt.target,
                          opt.source === "direct" ? opt.target : opt.displayName,
                        );
                      }}
                    >
                      <span
                        className={`${styles.optionSymbol} ${opt.source === "direct" ? styles.optionSymbolDirect : ""}`}
                      >
                        {opt.symbolTag}
                      </span>
                      <span className={styles.optionMain}>
                        <span className={styles.optionName}>{opt.displayName}</span>
                        {opt.subtitle && <span className={styles.optionSub}>{opt.subtitle}</span>}
                      </span>
                      {opt.price != null && (
                        <span className={styles.optionQuote}>
                          <strong>
                            {opt.price.toFixed(2)} {opt.currency || ""}
                          </strong>
                          {opt.change1dPct != null && (
                            <span
                              className={
                                opt.change1dPct >= 0
                                  ? styles.changePositive
                                  : styles.changeNegative
                              }
                            >
                              {opt.change1dPct >= 0 ? "+" : ""}
                              {opt.change1dPct.toFixed(2)}%
                            </span>
                          )}
                        </span>
                      )}
                      {opt.metaBadge && opt.price == null && (
                        <span className={styles.optionMeta}>{opt.metaBadge}</span>
                      )}
                      {opt.cached && (
                        <span
                          className={styles.cachedDot}
                          title="Déjà en entrepôt local"
                        />
                      )}
                      {opt.isCurrent && <Check size={14} className={styles.currentCheck} />}
                    </button>
                  </div>
                );
              })
            )}
          </div>

          {!searchText.trim() && quickSuggestions.length > 0 && (
            <div className={styles.suggestionsBar}>
              <span className={styles.suggestionsLabel}>
                <Sparkles size={11} />
                Accès rapide :
              </span>
              <div className={styles.suggestionsChips}>
                {quickSuggestions.map(name => (
                  <button
                    key={name}
                    type="button"
                    className={styles.suggestionChip}
                    onClick={() => triggerSelection(name, name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
