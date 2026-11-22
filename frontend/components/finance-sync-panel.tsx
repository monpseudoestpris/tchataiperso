"use client";

import { CalendarClock, Check, Database, Download, LoaderCircle, Play, RefreshCw, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  fetchEodhdIndxCatalog,
  fetchFinanceScreenerMeta,
  fetchFinanceSyncPreferences,
  fetchFinanceSyncStatus,
  hydrateFinanceScreener,
  rebuildFinanceScreener,
  runFinanceSyncNow,
  updateFinanceSyncPreferences,
  upgradeFinanceWarehouseToEodhd,
  type EodhdIndxCatalogItem,
  type FinanceSyncAvailableIndex,
  type FinanceSyncPreferences,
  type FinanceSyncProgress,
  type FinanceWarehouseSourcesSummary,
  type FinanceWatchlistMeta,
  type ScreenerCoverage,
  type SupportedExchangeInfo,
} from "@/lib/api";

import { FinanceEodhdUsageCard } from "./finance-eodhd-usage-card";
import { FinanceFundamentalsPlanCard } from "./finance-fundamentals-plan-card";

/**
 * Centre de contrôle des données & synchronisations financières (Onglet 5 · Données & Synchro) :
 * gère la priorité / migration EODHD, la synchro quotidienne automatique des indices, la fréquence
 * hebdomadaire des fondamentaux, les catalogues marchés et l'enrichissement / réindexation du Screener.
 */
export function FinanceSyncPanel({
  watchlists = [],
  activeListId = null,
  onSynced,
  onClose,
}: {
  watchlists?: FinanceWatchlistMeta[];
  activeListId?: string | null;
  onSynced?: () => void;
  onClose?: () => void;
}) {
  const [prefs, setPrefs] = useState<FinanceSyncPreferences | null>(null);
  const [indices, setIndices] = useState<FinanceSyncAvailableIndex[]>([]);
  const [exchanges, setExchanges] = useState<SupportedExchangeInfo[]>([]);
  const [indxCatalogTotal, setIndxCatalogTotal] = useState<number>(0);
  const [indexFilterMode, setIndexFilterMode] = useState<"all" | "major" | "selected" | "eodhd_indx">("all");
  const [indexSearch, setIndexSearch] = useState<string>("");
  const [eodhdIndxItems, setEodhdIndxItems] = useState<EodhdIndxCatalogItem[]>([]);
  const [eodhdIndxLoading, setEodhdIndxLoading] = useState<boolean>(false);
  const [exchangeFilterMode, setExchangeFilterMode] = useState<"all" | "loaded" | "selected">("all");
  const [exchangeSearch, setExchangeSearch] = useState<string>("");
  const [refreshingCatalogs, setRefreshingCatalogs] = useState<boolean>(false);
  const [liveProgress, setLiveProgress] = useState<FinanceSyncProgress | null>(null);
  const [warehouseSources, setWarehouseSources] = useState<FinanceWarehouseSourcesSummary | null>(null);
  const [screenerCoverage, setScreenerCoverage] = useState<ScreenerCoverage | null>(null);
  const [hydrateUniverseType, setHydrateUniverseType] = useState<"all" | "index" | "watchlist">("all");
  const [hydrateUniverseValue, setHydrateUniverseValue] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [savedBanner, setSavedBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fullCoverage, setFullCoverage] = useState<Record<string, { total: number; with_data: number }>>({});
  const [usageRefreshKey, setUsageRefreshKey] = useState<number>(0);

  const isSyncActive = running || Boolean(liveProgress?.is_running);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchFinanceSyncPreferences(),
      fetchFinanceScreenerMeta().catch(() => null),
    ])
      .then(([res, meta]) => {
        if (cancelled) return;
        setPrefs(res.preferences);
        setFullCoverage(res.full_exchange_coverage || {});
        if (res.progress) setLiveProgress(res.progress);
        if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
        if (res.eodhd_indx_catalog_total != null) setIndxCatalogTotal(res.eodhd_indx_catalog_total);
        if (meta?.coverage) setScreenerCoverage(meta.coverage);
        setIndices(res.available_indices || []);
        setExchanges(res.available_exchanges || []);
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Impossible de charger les préférences de synchronisation.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Suit l'avancement en direct pendant toute synchro (automatique ou manuelle)
  useEffect(() => {
    let cancelled = false;
    const intervalMs = isSyncActive ? 2000 : 12000;
    const timer = window.setInterval(() => {
      fetchFinanceSyncStatus()
        .then(status => {
          if (cancelled) return;
          setLiveProgress(prev => {
            if (prev?.is_running && !status.is_running) {
              setUsageRefreshKey(k => k + 1);
              if (status.last_message) {
                setSavedBanner(status.last_message);
              }
              Promise.all([
                fetchFinanceSyncPreferences(),
                fetchFinanceScreenerMeta().catch(() => null),
              ])
                .then(([res, meta]) => {
                  if (cancelled) return;
                  setPrefs(res.preferences);
                  setFullCoverage(res.full_exchange_coverage || {});
                  if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
                  if (meta?.coverage) setScreenerCoverage(meta.coverage);
                  setExchanges(res.available_exchanges || []);
                  if (onSynced) onSynced();
                })
                .catch(() => {});
            }
            return status;
          });
        })
        .catch(() => {});
    }, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isSyncActive, onSynced]);

  async function persistPrefs(next: FinanceSyncPreferences) {
    setPrefs(next);
    setSaving(true);
    setSavedBanner(null);
    setError(null);
    try {
      const res = await updateFinanceSyncPreferences({
        enabled: next.enabled,
        principal_indices: next.principal_indices,
        major_indices_constituents: next.major_indices_constituents,
        screener_fundamentals: next.screener_fundamentals,
        screener_fundamentals_daily_cap: next.screener_fundamentals_daily_cap,
        screener_fundamentals_interval_days: next.screener_fundamentals_interval_days,
        indx_catalog: next.indx_catalog,
        index_codes: next.index_codes,
        watchlists: next.watchlists,
        exchanges: next.exchanges,
        full_data_exchanges: next.full_data_exchanges,
        fundamentals_budget_pct: next.fundamentals_budget_pct,
        fundamentals_quota_safety_pct: next.fundamentals_quota_safety_pct,
        fundamentals_priority_order: next.fundamentals_priority_order,
      });
      setPrefs(res.preferences);
      setFullCoverage(res.full_exchange_coverage || {});
      setUsageRefreshKey(k => k + 1);
      if (res.progress) setLiveProgress(res.progress);
      setExchanges(res.available_exchanges || []);
      setSavedBanner("Préférences enregistrées.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d'enregistrer les réglages.");
    } finally {
      setSaving(false);
    }
  }

  function toggleBool(
    key:
      | "enabled"
      | "principal_indices"
      | "major_indices_constituents"
      | "screener_fundamentals"
      | "indx_catalog"
      | "watchlists",
  ) {
    if (!prefs || saving || running) return;
    void persistPrefs({ ...prefs, [key]: !prefs[key] });
  }

  // Recherche dans le catalogue complet EODHD .INDX lorsque l'utilisateur filtre ou sélectionne l'onglet EODHD .INDX
  useEffect(() => {
    const q = indexSearch.trim();
    if (indexFilterMode !== "eodhd_indx" && q.length < 2) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setEodhdIndxLoading(true);
      fetchEodhdIndxCatalog(q, 150, false)
        .then(res => {
          if (cancelled) return;
          setEodhdIndxItems(res.items || []);
          if (res.total) setIndxCatalogTotal(res.total);
        })
        .catch(() => {})
        .finally(() => {
          if (!cancelled) setEodhdIndxLoading(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [indexFilterMode, indexSearch]);

  async function handleRefreshEodhdCatalogs() {
    if (refreshingCatalogs || saving) return;
    setRefreshingCatalogs(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await fetchFinanceSyncPreferences(true);
      setPrefs(res.preferences);
      if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
      if (res.eodhd_indx_catalog_total != null) setIndxCatalogTotal(res.eodhd_indx_catalog_total);
      setIndices(res.available_indices || []);
      setExchanges(res.available_exchanges || []);
      setSavedBanner(
        `Listes EODHD actualisées (${res.available_exchanges.length} bourses/listes, ${res.eodhd_indx_catalog_total ?? 0} indices .INDX).`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d'actualiser les listes EODHD.");
    } finally {
      setRefreshingCatalogs(false);
    }
  }

  function isIndexChecked(code: string, tier?: "major" | "minor"): boolean {
    if (!prefs) return false;
    const upper = code.toUpperCase();
    if (prefs.major_indices_constituents && tier === "major") return true;
    return prefs.index_codes.includes(upper);
  }

  function toggleIndexCode(code: string, tier?: "major" | "minor") {
    if (!prefs || saving || running) return;
    const upper = code.toUpperCase();
    // Si "9 principaux auto" est actif et qu'on décoche un indice majeur, on bascule en sélection individuelle
    if (prefs.major_indices_constituents && tier === "major") {
      const majorCodes = indices.filter(i => i.tier === "major").map(i => i.code.toUpperCase());
      const expanded = Array.from(new Set([...prefs.index_codes, ...majorCodes])).filter(c => c !== upper);
      void persistPrefs({
        ...prefs,
        major_indices_constituents: false,
        index_codes: expanded,
      });
      return;
    }
    const exists = prefs.index_codes.includes(upper);
    const nextList = exists ? prefs.index_codes.filter(c => c !== upper) : [...prefs.index_codes, upper];
    void persistPrefs({ ...prefs, index_codes: nextList });
  }

  function toggleListCode(key: "index_codes" | "exchanges" | "full_data_exchanges", code: string) {
    if (!prefs || saving || running) return;
    const upper = code.toUpperCase();
    const exists = prefs[key].includes(upper);
    const nextList = exists ? prefs[key].filter(c => c !== upper) : [...prefs[key], upper];
    void persistPrefs({ ...prefs, [key]: nextList });
  }

  async function handleRunNow(forceRefresh = false) {
    if (isSyncActive || saving) return;
    setRunning(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await runFinanceSyncNow(forceRefresh);
      setPrefs(res.preferences);
      if (res.progress) setLiveProgress(res.progress);
      if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
      setExchanges(res.available_exchanges || []);
      const s = res.summary;
      if (s?.skipped && s.reason === "already_running") {
        setSavedBanner("Une synchronisation est déjà en cours en arrière-plan.");
      } else if (res.started) {
        if (typeof window !== "undefined") window.dispatchEvent(new Event("finance-sync-started"));
        setSavedBanner("Synchronisation lancée en arrière-plan — vous pouvez changer d'onglet librement, elle continue sur le serveur.");
      } else {
        const idxCount = Object.keys(s?.indices || {}).length;
        const exchCount = Object.keys(s?.exchanges || {}).length;
        const sf = s?.screener_fundamentals;
        const fundMsg = sf?.skipped
          ? "fondamentaux à jour (cycle hebdomadaire)"
          : `${sf?.enriched ?? 0} fondamentaux enrichis`;
        setSavedBanner(
          `Synchronisation terminée (${s?.principal_indices_count ?? 0} indices, ${idxCount} compositions + technique multi-unités, ${fundMsg}, ${s?.watchlist_items_count ?? 0} suivi(s), ${exchCount} marché(s)).`,
        );
        if (onSynced) onSynced();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la synchronisation immédiate.");
    } finally {
      setRunning(false);
    }
  }

  async function handleUpgradeWarehouseToEodhd(forceAllFundamentals: boolean) {
    if (isSyncActive || saving) return;
    setRunning(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await upgradeFinanceWarehouseToEodhd({
        include_bars: true,
        include_fundamentals: true,
        force_all_fundamentals: forceAllFundamentals,
        max_fundamentals: 250,
        max_bars: 600,
      });
      setPrefs(res.preferences);
      if (res.progress) setLiveProgress(res.progress);
      if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
      const s = res.summary;
      if (s?.skipped && s.reason === "already_running") {
        setSavedBanner("Une synchronisation est déjà en cours en arrière-plan.");
      } else if (s?.skipped && s.reason === "eodhd_key_missing") {
        setError("Clé API EODHD (EOD_HISTORICAL_DATA_KEY) non configurée.");
      } else if (res.started) {
        if (typeof window !== "undefined") window.dispatchEvent(new Event("finance-sync-started"));
        setSavedBanner("Mise à jour EODHD lancée en arrière-plan — vous pouvez changer d'onglet librement, elle continue sur le serveur.");
      } else {
        setSavedBanner(
          `Mise à jour EODHD terminée : ${s?.bars_upgraded ?? 0}/${s?.bars_targeted ?? 0} cours EOD mis à jour, ${s?.fundamentals_upgraded ?? 0}/${s?.fundamentals_targeted ?? 0} états financiers mis à jour depuis EODHD.`,
        );
        if (onSynced) onSynced();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la mise à jour EODHD.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRebuildScreenerCache() {
    if (isSyncActive || saving) return;
    setRunning(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await rebuildFinanceScreener();
      setScreenerCoverage(res.coverage);
      setSavedBanner(
        `Index local du Screener reconstruit (Jour, Semaine, Mois, 3 Mois + IsoPressure) : ${res.indexed_count} valeur(s) analysée(s) depuis SQLite.`,
      );
      if (onSynced) onSynced();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de reconstruction locale du Screener.");
    } finally {
      setRunning(false);
    }
  }

  async function handleHydrateScreenerNow() {
    if (isSyncActive || saving) return;
    setRunning(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await hydrateFinanceScreener({
        universe_type: hydrateUniverseType,
        universe_value: hydrateUniverseType === "all" ? null : hydrateUniverseValue || null,
        include_fundamentals: true,
        max_fundamentals: prefs?.screener_fundamentals_daily_cap || 40,
        refresh_eod: false,
        background: true,
      });
      if (res.progress) setLiveProgress(res.progress);
      if (res.coverage) setScreenerCoverage(res.coverage);
      if (res.already_running) {
        setSavedBanner("Une synchronisation ou migration est déjà en cours en arrière-plan.");
      } else if (res.started) {
        if (typeof window !== "undefined") window.dispatchEvent(new Event("finance-sync-started"));
        setSavedBanner("Enrichissement Screener lancé en arrière-plan — vous pouvez changer d'onglet librement, il continue sur le serveur.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de l'enrichissement Screener.");
    } finally {
      setRunning(false);
    }
  }

  const selectedIndicesSummary = useMemo(() => {
    if (!prefs) return { count: 0, stocks: 0 };
    let count = 0;
    let stocks = 0;
    const counted = new Set<string>();
    for (const idx of indices) {
      const c = idx.code.toUpperCase();
      const checked = (prefs.major_indices_constituents && idx.tier === "major") || prefs.index_codes.includes(c);
      if (checked && !counted.has(c)) {
        counted.add(c);
        count += 1;
        stocks += idx.constituents_count || 0;
      }
    }
    for (const extra of prefs.index_codes) {
      const c = extra.toUpperCase();
      if (!counted.has(c)) {
        counted.add(c);
        count += 1;
      }
    }
    return { count, stocks };
  }, [indices, prefs]);

  const displayedIndices = useMemo(() => {
    const needle = indexSearch.trim().toLowerCase();
    return indices.filter(idx => {
      if (indexFilterMode === "major" && idx.tier !== "major") return false;
      if (indexFilterMode === "selected") {
        const checked = Boolean(
          prefs && ((prefs.major_indices_constituents && idx.tier === "major") || prefs.index_codes.includes(idx.code.toUpperCase())),
        );
        if (!checked) return false;
      }
      if (needle) {
        const hay = `${idx.code} ${idx.eod_ticker || ""} ${idx.name} ${idx.region}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [indices, indexFilterMode, indexSearch, prefs]);

  const displayedExchanges = useMemo(() => {
    const needle = exchangeSearch.trim().toLowerCase();
    return exchanges.filter(ex => {
      if (exchangeFilterMode === "loaded" && ex.total <= 0) return false;
      if (exchangeFilterMode === "selected" && !prefs?.exchanges.includes(ex.code.toUpperCase())) return false;
      if (needle) {
        const hay = `${ex.code} ${ex.label} ${ex.description} ${ex.country || ""} ${ex.currency || ""}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [exchanges, exchangeFilterMode, exchangeSearch, prefs]);

  const totalWatchlistStocks = useMemo(
    () => watchlists.reduce((acc, wl) => acc + (wl.items_count || 0), 0),
    [watchlists],
  );

  const selectedExchangesSummary = useMemo(() => {
    if (!prefs) return { count: 0, stocks: 0 };
    const sel = new Set(prefs.exchanges.map(c => c.toUpperCase()));
    let stocks = 0;
    for (const ex of exchanges) {
      if (sel.has(ex.code.toUpperCase())) {
        stocks += ex.total || 0;
      }
    }
    return { count: sel.size, stocks };
  }, [exchanges, prefs]);

  return (
    <section className="finance-index-drawer finance-sync-drawer" aria-label="Configuration de la synchronisation quotidienne">
      <div className="finance-index-drawer-head">
        <div className="finance-index-drawer-title">
          <span className="finance-index-drawer-flag">
            <CalendarClock size={18} />
          </span>
          <div>
            <strong>Synchronisation quotidienne automatique</strong>
            <small>
              Choisissez précisément les données à charger chaque jour (les indices boursiers sont activés de base).
              {prefs?.last_run_at
                ? ` · Dernière exécution : ${new Date(prefs.last_run_at).toLocaleString("fr-FR", {
                    day: "2-digit",
                    month: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}`
                : ""}
            </small>
          </div>
        </div>
        <div className="finance-index-drawer-actions">
          {prefs && (
            <button
              type="button"
              className={`finance-tf-btn ${prefs.enabled ? "active" : ""}`}
              disabled={saving || running}
              onClick={() => toggleBool("enabled")}
              title="Activer ou suspendre la synchronisation quotidienne automatique en arrière-plan"
            >
              {prefs.enabled ? <Check size={12} /> : null}
              <span>{prefs.enabled ? "Auto 24h : Activée" : "Auto 24h : En pause"}</span>
            </button>
          )}
          <button
            type="button"
            className="finance-tf-btn active finance-stmt-refresh-btn"
            disabled={loading || isSyncActive || saving}
            onClick={() => void handleRunNow(false)}
            title="Exécuter maintenant la synchronisation pour les éléments cochés ci-dessous"
          >
            {isSyncActive ? <LoaderCircle size={12} className="spin" /> : <Play size={12} />}
            <span>{isSyncActive ? "Synchronisation…" : "Synchroniser maintenant"}</span>
          </button>
          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={loading || isSyncActive || saving}
            onClick={() => void handleRunNow(true)}
            title="Forcer le re-téléchargement réseau même pour les valeurs déjà en cache aujourd'hui"
          >
            <RefreshCw size={12} className={isSyncActive ? "spin" : ""} />
            <span>Forcer</span>
          </button>
          {onClose && (
            <button type="button" className="finance-tf-btn" onClick={onClose} aria-label="Fermer les réglages de synchro">
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {error && <div className="finance-modal-error">⚠️ {error}</div>}
      {isSyncActive && (
        <div className="finance-sync-progress-box" role="status" aria-live="polite">
          <div className="finance-sync-progress-head">
            <span className="finance-sync-progress-title">
              <LoaderCircle size={14} className="spin" />
              <strong>
                {liveProgress?.trigger === "auto" ? "Synchronisation automatique en cours" : "Synchronisation en cours"}
              </strong>
              <span>· {liveProgress?.current_label || "Traitement des marchés…"}</span>
            </span>
            <span className="finance-sync-progress-pct">
              {liveProgress?.total_steps ? `${liveProgress.percent}%` : ""}
            </span>
          </div>
          <div className="finance-sync-progress-track">
            <div
              className="finance-sync-progress-fill"
              style={{ width: `${Math.max(8, liveProgress?.percent || 12)}%` }}
            />
          </div>
        </div>
      )}
      {savedBanner && <div className="finance-index-import-banner">✓ {savedBanner}</div>}

      {loading && !prefs ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>Chargement de vos préférences de synchronisation…</span>
        </div>
      ) : prefs ? (
        <div className="finance-sync-sections">
          <FinanceEodhdUsageCard refreshKey={usageRefreshKey} />

          {/* Bloc 0 : Sources EODHD vs Yahoo Finance dans l'entrepôt */}
          {warehouseSources && (
            <div className="finance-sync-card">
              <div className="finance-sync-card-head">
                <strong>
                  <Database size={14} style={{ display: "inline", verticalAlign: "-2px", marginRight: 6 }} />
                  Priorité EOD Historical Data (EODHD)
                </strong>
                <small>
                  États financiers : {warehouseSources.eodhd_fundamentals_count} EODHD
                  {warehouseSources.yahoo_only_fundamentals_count > 0
                    ? ` · ${warehouseSources.yahoo_only_fundamentals_count} Yahoo à migrer`
                    : " · 0 Yahoo restant"}
                  {" · "}Cours : {warehouseSources.eodhd_bars_symbols_count}/{warehouseSources.total_bars_symbols} EODHD
                </small>
              </div>
              <div className="finance-sync-check-row" style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                <button
                  type="button"
                  className="finance-tf-btn active"
                  disabled={isSyncActive || saving || !warehouseSources.eodhd_configured}
                  onClick={() => void handleUpgradeWarehouseToEodhd(false)}
                  title="Remplace uniquement les cours et états financiers encore issus de Yahoo Finance par des données EODHD"
                >
                  {isSyncActive ? <LoaderCircle size={12} className="spin" /> : <RefreshCw size={12} />}
                  <span>
                    Migrer les données Yahoo vers EODHD (
                    {warehouseSources.yahoo_only_fundamentals_count + warehouseSources.yahoo_only_bars_symbols_count})
                  </span>
                </button>
                <button
                  type="button"
                  className="finance-tf-btn"
                  disabled={isSyncActive || saving || !warehouseSources.eodhd_configured}
                  onClick={() => void handleUpgradeWarehouseToEodhd(true)}
                  title="Re-télécharge tous les états financiers de l'entrepôt depuis EODHD et réindexe le Screener"
                >
                  <Database size={12} />
                  <span>Tout actualiser depuis EODHD</span>
                </button>
              </div>
            </div>
          )}

          {/* Bloc 1 : Indices de base */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>1. Indices boursiers (de base)</strong>
              <small>Recommandé · ~10 requêtes légères par jour</small>
            </div>
            <div className="finance-sync-check-row">
              <label className="finance-sync-check">
                <input
                  type="checkbox"
                  checked={prefs.principal_indices}
                  disabled={saving || running}
                  onChange={() => toggleBool("principal_indices")}
                />
                <span>Cotations des indices principaux (CAC 40, S&amp;P 500, NASDAQ 100, EURO STOXX 50…)</span>
              </label>
              <label className="finance-sync-check">
                <input
                  type="checkbox"
                  checked={prefs.indx_catalog}
                  disabled={saving || running}
                  onChange={() => toggleBool("indx_catalog")}
                />
                <span>Catalogue général des indices EODHD (.INDX)</span>
              </label>
            </div>
          </div>

          {/* Bloc 2 : Tous les indices boursiers EODHD (cochables un par un avec nombre d'actions) */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>
                2. Indices boursiers EODHD ({selectedIndicesSummary.count} coché{selectedIndicesSummary.count > 1 ? "s" : ""} ·{" "}
                {selectedIndicesSummary.stocks.toLocaleString("fr-FR")} actions)
              </strong>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                <button
                  type="button"
                  className={`finance-tf-btn ${indexFilterMode === "all" ? "active" : ""}`}
                  onClick={() => setIndexFilterMode("all")}
                >
                  Tous ({indices.length})
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${indexFilterMode === "major" ? "active" : ""}`}
                  onClick={() => setIndexFilterMode("major")}
                >
                  9 principaux
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${indexFilterMode === "selected" ? "active" : ""}`}
                  onClick={() => setIndexFilterMode("selected")}
                >
                  Cochés ({selectedIndicesSummary.count})
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${indexFilterMode === "eodhd_indx" ? "active" : ""}`}
                  onClick={() => setIndexFilterMode("eodhd_indx")}
                  title="Parcourir et cocher n'importe quel indice du catalogue complet EODHD .INDX"
                >
                  Catalogue EODHD .INDX ({indxCatalogTotal > 0 ? indxCatalogTotal.toLocaleString("fr-FR") : "…"})
                </button>
              </div>
            </div>
            <div className="finance-sync-check-row">
              <label className="finance-sync-check">
                <input
                  type="checkbox"
                  checked={prefs.major_indices_constituents}
                  disabled={saving || running}
                  onChange={() => toggleBool("major_indices_constituents")}
                />
                <span>
                  Inclure automatiquement les 9 principaux indices chaque jour (ou décochez-en un ci-dessous pour choisir un par un)
                </span>
              </label>
              <label className="finance-sync-check">
                <input
                  type="checkbox"
                  checked={prefs.screener_fundamentals}
                  disabled={saving || running}
                  onChange={() => toggleBool("screener_fundamentals")}
                />
                <span>
                  Charger les fondamentaux &amp; historiques pour le Screener via la file priorisée (voir « Plan de
                  chargement des fondamentaux »)
                </span>
              </label>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0" }}>
              <Search size={13} style={{ opacity: 0.65, flexShrink: 0 }} />
              <input
                type="text"
                value={indexSearch}
                onChange={e => setIndexSearch(e.target.value)}
                placeholder="Filtrer un indice par nom, code ou pays (ex. CAC, S&P, DAX, STOXX, RUSSELL, MSCI)…"
                style={{
                  flex: 1,
                  padding: "6px 10px",
                  borderRadius: 8,
                  border: "1px solid var(--fin-border, #cbd5e1)",
                  background: "var(--fin-panel, transparent)",
                  fontSize: 12.5,
                }}
              />
              {indexSearch && (
                <button type="button" className="finance-tf-btn" onClick={() => setIndexSearch("")}>
                  Effacer
                </button>
              )}
            </div>

            {indexFilterMode !== "eodhd_indx" && (
              <div className="finance-sync-pills-grid" style={{ maxHeight: 260, overflowY: "auto", paddingRight: 4 }}>
                {displayedIndices.map(idx => {
                  const checked = isIndexChecked(idx.code, idx.tier);
                  const countLabel =
                    idx.constituents_count > 0
                      ? `${idx.constituents_count.toLocaleString("fr-FR")} actions`
                      : "composition EODHD";
                  return (
                    <label
                      key={idx.code}
                      className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                      title={`${idx.name} (${idx.eod_ticker || idx.code}) — ${countLabel} · ${idx.region}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={saving || running}
                        onChange={() => toggleIndexCode(idx.code, idx.tier)}
                      />
                      <span>{idx.flag}</span>
                      <span>{idx.name}</span>
                      <small>{countLabel}</small>
                    </label>
                  );
                })}
                {displayedIndices.length === 0 && (
                  <small style={{ opacity: 0.75, padding: "4px 2px" }}>
                    Aucun indice prédéfini ne correspond — consultez les résultats EODHD .INDX ci-dessous.
                  </small>
                )}
              </div>
            )}

            {(indexFilterMode === "eodhd_indx" || indexSearch.trim().length >= 2) && (
              <div style={{ marginTop: 8 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <small style={{ fontWeight: 600, opacity: 0.85 }}>
                    Indices du catalogue complet EODHD (.INDX)
                    {eodhdIndxLoading ? " — recherche…" : ` (${eodhdIndxItems.length} affiché${eodhdIndxItems.length > 1 ? "s" : ""})`}
                  </small>
                </div>
                <div className="finance-sync-pills-grid" style={{ maxHeight: 220, overflowY: "auto", paddingRight: 4 }}>
                  {eodhdIndxItems.map(item => {
                    const code = item.eod_ticker.toUpperCase();
                    const known = indices.find(
                      i => i.code.toUpperCase() === code || (i.eod_ticker || "").toUpperCase() === code,
                    );
                    const targetCode = known ? known.code : code;
                    const checked = isIndexChecked(targetCode, known?.tier);
                    const countLabel =
                      known && known.constituents_count > 0
                        ? `${known.constituents_count.toLocaleString("fr-FR")} actions`
                        : item.country || "EODHD .INDX";
                    return (
                      <label
                        key={code}
                        className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                        title={`${item.name} (${code}) · ${item.country} ${item.currency}`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={saving || running}
                          onChange={() => toggleIndexCode(targetCode, known?.tier)}
                        />
                        <span>🌐</span>
                        <span>{item.name}</span>
                        <small>{code} · {countLabel}</small>
                      </label>
                    );
                  })}
                  {!eodhdIndxLoading && eodhdIndxItems.length === 0 && (
                    <small style={{ opacity: 0.75 }}>Aucun indice .INDX trouvé pour cette recherche.</small>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Bloc 3 : Watchlists & Toutes les bourses / listes présentes dans EODHD */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>
                3. Listes de suivi &amp; Toutes les bourses / listes EODHD ({selectedExchangesSummary.count} cochée
                {selectedExchangesSummary.count > 1 ? "s" : ""}
                {selectedExchangesSummary.stocks > 0
                  ? ` · ${selectedExchangesSummary.stocks.toLocaleString("fr-FR")} titres en base`
                  : ""}
                )
              </strong>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                <button
                  type="button"
                  className={`finance-tf-btn ${exchangeFilterMode === "all" ? "active" : ""}`}
                  onClick={() => setExchangeFilterMode("all")}
                >
                  Toutes ({exchanges.length})
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${exchangeFilterMode === "loaded" ? "active" : ""}`}
                  onClick={() => setExchangeFilterMode("loaded")}
                >
                  Chargées ({exchanges.filter(e => e.total > 0).length})
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${exchangeFilterMode === "selected" ? "active" : ""}`}
                  onClick={() => setExchangeFilterMode("selected")}
                >
                  Cochées ({selectedExchangesSummary.count})
                </button>
                <button
                  type="button"
                  className="finance-tf-btn"
                  disabled={refreshingCatalogs || saving}
                  onClick={() => void handleRefreshEodhdCatalogs()}
                  title="Récupérer la liste complète à jour des bourses et indices disponibles sur EODHD"
                >
                  <RefreshCw size={11} className={refreshingCatalogs ? "spin" : ""} />
                  <span>Actualiser listes EODHD</span>
                </button>
              </div>
            </div>
            <div className="finance-sync-check-row">
              <label className="finance-sync-check">
                <input
                  type="checkbox"
                  checked={prefs.watchlists}
                  disabled={saving || running}
                  onChange={() => toggleBool("watchlists")}
                />
                <span>
                  Cours quotidiens de toutes mes listes de suivi
                  {watchlists.length > 0
                    ? ` (${totalWatchlistStocks.toLocaleString("fr-FR")} actions dans ${watchlists.length} liste${watchlists.length > 1 ? "s" : ""})`
                    : ""}
                </span>
              </label>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0" }}>
              <Search size={13} style={{ opacity: 0.65, flexShrink: 0 }} />
              <input
                type="text"
                value={exchangeSearch}
                onChange={e => setExchangeSearch(e.target.value)}
                placeholder="Filtrer une bourse ou liste EODHD (ex. PA, US, XETRA, LSE, SW, EUFUND, France, EUR)…"
                style={{
                  flex: 1,
                  padding: "6px 10px",
                  borderRadius: 8,
                  border: "1px solid var(--fin-border, #cbd5e1)",
                  background: "var(--fin-panel, transparent)",
                  fontSize: 12.5,
                }}
              />
              {exchangeSearch && (
                <button type="button" className="finance-tf-btn" onClick={() => setExchangeSearch("")}>
                  Effacer
                </button>
              )}
            </div>
            <div className="finance-sync-pills-grid" style={{ maxHeight: 280, overflowY: "auto", paddingRight: 4 }}>
              {displayedExchanges.map(ex => {
                const checked = prefs.exchanges.includes(ex.code.toUpperCase());
                const countText =
                  ex.total > 0 ? `${ex.total.toLocaleString("fr-FR")} titres` : "non chargée";
                return (
                  <label
                    key={ex.code}
                    className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                    title={`${ex.description} — ${countText}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={saving || running}
                      onChange={() => toggleListCode("exchanges", ex.code)}
                    />
                    <span>{ex.label}</span>
                    <small>
                      {countText}
                      {ex.currency ? ` · ${ex.currency}` : ""}
                    </small>
                  </label>
                );
              })}
              {displayedExchanges.length === 0 && (
                <small style={{ opacity: 0.75, padding: "4px 2px" }}>
                  Aucune place boursière ne correspond à ce filtre.
                </small>
              )}
            </div>
          </div>

          {/* Bloc 3 bis : Bourses complètes (toutes les actions avec cours & fondamentaux, complétion progressive) */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>
                Bourses complètes : toutes les actions avec cours &amp; fondamentaux (
                {(prefs.full_data_exchanges || []).length} choisie
                {(prefs.full_data_exchanges || []).length > 1 ? "s" : ""})
              </strong>
            </div>
            <small style={{ opacity: 0.8, display: "block", marginBottom: 8 }}>
              Chaque jour : cours du jour de toutes les actions déjà chargées (1 appel EODHD groupé par bourse, 100 calls).
              Les actions encore vides entrent dans le « Plan de chargement des fondamentaux » ci-dessous et sont
              chargées progressivement selon votre budget et vos priorités : rien n&apos;est chargé d&apos;un coup.
            </small>
            <div className="finance-sync-pills-grid" style={{ maxHeight: 200, overflowY: "auto", paddingRight: 4 }}>
              {exchanges
                .filter(ex => ex.total > 0 && !["EUFUND", "CC"].includes(ex.code.toUpperCase()))
                .map(ex => {
                  const code = ex.code.toUpperCase();
                  const checked = (prefs.full_data_exchanges || []).includes(code);
                  const cov = fullCoverage[code];
                  return (
                    <label
                      key={code}
                      className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                      title={`${ex.description} — charger toutes les actions de cette bourse progressivement`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={saving || running}
                        onChange={() => toggleListCode("full_data_exchanges", code)}
                      />
                      <span>{ex.label}</span>
                      <small>
                        {checked && cov
                          ? `${cov.with_data.toLocaleString("fr-FR")} / ${cov.total.toLocaleString("fr-FR")} actions avec données`
                          : "toutes les actions"}
                      </small>
                    </label>
                  );
                })}
            </div>
          </div>

          <FinanceFundamentalsPlanCard
            prefs={prefs}
            disabled={saving || running}
            refreshKey={usageRefreshKey}
            onChangePrefs={next => void persistPrefs(next)}
          />

          {/* Bloc 4 : Enrichissement manuel & Indexation du Screener */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>4. Enrichissement manuel &amp; Indexation du Screener</strong>
              <small>
                {screenerCoverage
                  ? `${screenerCoverage.total_snapshots} titres indexés (4 unités + IsoPressure) · ${screenerCoverage.with_fundamentals} avec fondamentaux`
                  : "Cours EOD + indicateurs multi-unités + états financiers EODHD"}
              </small>
            </div>
            <div className="finance-sync-check-row" style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
              <select
                value={hydrateUniverseType}
                disabled={isSyncActive || saving}
                onChange={e => {
                  const next = e.target.value as "all" | "index" | "watchlist";
                  setHydrateUniverseType(next);
                  if (next === "index") {
                    setHydrateUniverseValue(indices[0]?.code || "CAC40");
                  } else if (next === "watchlist") {
                    setHydrateUniverseValue(activeListId || watchlists[0]?.id || "");
                  } else {
                    setHydrateUniverseValue("");
                  }
                }}
                aria-label="Univers à enrichir"
              >
                <option value="all">Tout l&apos;entrepôt local</option>
                <option value="index">Par indice boursier</option>
                {watchlists.length > 0 && <option value="watchlist">Ma liste de suivi</option>}
              </select>
              {hydrateUniverseType === "index" && (
                <select
                  value={hydrateUniverseValue}
                  disabled={isSyncActive || saving}
                  onChange={e => setHydrateUniverseValue(e.target.value)}
                  aria-label="Indice à enrichir"
                >
                  {indices.map(idx => (
                    <option key={idx.code} value={idx.code}>
                      {idx.flag} {idx.name} ({idx.code})
                    </option>
                  ))}
                </select>
              )}
              {hydrateUniverseType === "watchlist" && watchlists.length > 0 && (
                <select
                  value={hydrateUniverseValue}
                  disabled={isSyncActive || saving}
                  onChange={e => setHydrateUniverseValue(e.target.value)}
                  aria-label="Liste de suivi à enrichir"
                >
                  {watchlists.map(wl => (
                    <option key={wl.id} value={wl.id}>
                      {wl.name} ({wl.items_count})
                    </option>
                  ))}
                </select>
              )}
              <button
                type="button"
                className="finance-tf-btn active"
                disabled={isSyncActive || saving}
                onClick={() => void handleHydrateScreenerNow()}
                title="Télécharge les cours EOD manquants et enrichit les dossiers fondamentaux EODHD en arrière-plan"
              >
                {isSyncActive ? <LoaderCircle size={12} className="spin" /> : <Download size={12} />}
                <span>Enrichir univers (EODHD)</span>
              </button>
              <button
                type="button"
                className="finance-tf-btn"
                disabled={isSyncActive || saving}
                onClick={() => void handleRebuildScreenerCache()}
                title="Recalcule immédiatement tous les indicateurs (Jour, Semaine, Mois, 3 Mois + IsoPressure) depuis SQLite sans appel réseau"
              >
                <RefreshCw size={12} />
                <span>Réindexer cache local</span>
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
