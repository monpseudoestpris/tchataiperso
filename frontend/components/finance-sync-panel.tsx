"use client";

import {
  CalendarClock,
  Check,
  Download,
  LoaderCircle,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  TrendingUp,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ensureFinanceSyncCatalogCounts,
  fetchEodhdIndxCatalog,
  fetchFinanceSyncPreferences,
  fetchFinanceSyncStatus,
  rebuildFinanceScreener,
  runFinanceSyncNow,
  runFinanceSyncSourceNow,
  updateFinanceSyncPreferences,
  upgradeFinanceWarehouseToEodhd,
  type EodhdIndxCatalogItem,
  type FinanceExchangeSourceStatus,
  type FinanceSyncAvailableIndex,
  type FinanceSyncPreferences,
  type FinanceSyncProgress,
  type FinanceSyncSourceKind,
  type FinanceSyncStateResponse,
  type FinanceWarehouseSourcesSummary,
  type FinanceWatchlistMeta,
  type SupportedExchangeInfo,
} from "@/lib/api";

import { FinanceFundamentalsPlanCard } from "./finance-fundamentals-plan-card";
import { FinanceSyncFooter } from "./finance-sync-footer";
import styles from "./finance-sync-panel.module.css";

const CORE_EXCHANGES = ["PA", "US", "XETRA", "LSE"];

type FinanceSyncPanelProps = {
  watchlists?: FinanceWatchlistMeta[];
  activeListId?: string | null;
  onSynced?: () => void;
  onClose?: () => void;
};

type SyncSourceRowProps = {
  title: string;
  badges?: Array<{ text: string; variant?: "code" | "type" | "info" }>;
  meta: string;
  dailyEnabled: boolean;
  onToggleDaily: () => void;
  onLoadNow: () => void;
  loadingThis: boolean;
  disabled: boolean;
  onRemove?: () => void;
  removeLabel?: string;
};

function SyncSourceRow({
  title,
  badges = [],
  meta,
  dailyEnabled,
  onToggleDaily,
  onLoadNow,
  loadingThis,
  disabled,
  onRemove,
  removeLabel,
}: SyncSourceRowProps) {
  return (
    <div className={styles.sourceRow}>
      <div className={styles.sourceInfo}>
        <div className={styles.sourceNameLine}>
          <span>{title}</span>
          {badges.map(b => (
            <span
              key={`${b.variant || "code"}-${b.text}`}
              className={
                b.variant === "type"
                  ? styles.typeBadge
                  : b.variant === "info"
                    ? styles.infoBadge
                    : styles.codeBadge
              }
            >
              {b.text}
            </span>
          ))}
        </div>
        <span className={styles.sourceMeta}>{meta}</span>
      </div>

      <button
        type="button"
        role="switch"
        aria-checked={dailyEnabled}
        disabled={disabled}
        className={`${styles.switchBtn} ${dailyEnabled ? styles.switchBtnOn : ""}`}
        onClick={onToggleDaily}
        title="Inclure ou exclure les cours de cette source dans la mise à jour quotidienne automatique"
      >
        <span className={styles.switchTrack}>
          <span className={styles.switchThumb} />
        </span>
        <span>{dailyEnabled ? "Tous les jours : Oui" : "Tous les jours : Non"}</span>
      </button>

      <div className={styles.rowActions}>
        <button
          type="button"
          className={styles.loadBtn}
          disabled={disabled}
          onClick={onLoadNow}
          title="Charger immédiatement les cours disponibles de cette source (en arrière-plan)"
        >
          {loadingThis ? <LoaderCircle size={12} className="spin" /> : <Download size={12} />}
          <span>Charger tout de suite</span>
        </button>
        {onRemove && (
          <button
            type="button"
            className={styles.removeIconBtn}
            disabled={disabled}
            onClick={onRemove}
            aria-label={removeLabel || `Retirer ${title}`}
            title="Retirer cette ligne de ma liste"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Onglet 5 · Données & Synchro :
 * 1. Les Cours (tous les jours) — liste simple de sources avec interrupteur quotidien et action 1-clic.
 * 2. Les Données Fondamentales — chargement étalé sous budget & rafraîchissement après résultats.
 * 3. Pied de page — calls API EODHD, état de la base synchronisée et migration / réindexation.
 */
export function FinanceSyncPanel({ watchlists = [], onSynced, onClose }: FinanceSyncPanelProps) {
  const [prefs, setPrefs] = useState<FinanceSyncPreferences | null>(null);
  const [indices, setIndices] = useState<FinanceSyncAvailableIndex[]>([]);
  const [exchanges, setExchanges] = useState<SupportedExchangeInfo[]>([]);
  const [exchangeSources, setExchangeSources] = useState<FinanceExchangeSourceStatus[]>([]);
  const [screenerSummary, setScreenerSummary] = useState<FinanceSyncStateResponse["screener_summary"] | null>(null);
  const [warehouseSources, setWarehouseSources] = useState<FinanceWarehouseSourcesSummary | null>(null);
  const [liveProgress, setLiveProgress] = useState<FinanceSyncProgress | null>(null);

  const [addIndexOpen, setAddIndexOpen] = useState(false);
  const [indexSearch, setIndexSearch] = useState("");
  const [eodhdIndxItems, setEodhdIndxItems] = useState<EodhdIndxCatalogItem[]>([]);
  const [eodhdIndxLoading, setEodhdIndxLoading] = useState(false);

  const [addStockExchOpen, setAddStockExchOpen] = useState(false);
  const [customStockCode, setCustomStockCode] = useState("");
  const [addEtfExchOpen, setAddEtfExchOpen] = useState(false);
  const [customEtfCode, setCustomEtfCode] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [busySourceKey, setBusySourceKey] = useState<string | null>(null);
  const [savedBanner, setSavedBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [usageRefreshKey, setUsageRefreshKey] = useState(0);
  const precountTriggeredRef = useRef(false);

  const isSyncActive = running || Boolean(liveProgress?.is_running);

  const applyStateResponse = useCallback((res: FinanceSyncStateResponse) => {
    setPrefs(res.preferences);
    if (res.progress) setLiveProgress(res.progress);
    if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
    if (res.exchange_sources) setExchangeSources(res.exchange_sources);
    if (res.screener_summary) setScreenerSummary(res.screener_summary);
    setIndices(res.available_indices || []);
    setExchanges(res.available_exchanges || []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceSyncPreferences()
      .then(res => {
        if (cancelled) return;
        applyStateResponse(res);
        const needsCounts =
          Boolean(res.warehouse_sources?.eodhd_configured) &&
          ((res.exchange_sources || []).some(s => !s.catalog_synced) ||
            (res.available_exchanges || []).some(e => (e.code === "EUFUND" || e.code === "CC") && e.total === 0));
        if (needsCounts && !precountTriggeredRef.current) {
          precountTriggeredRef.current = true;
          ensureFinanceSyncCatalogCounts()
            .then(updated => {
              if (!cancelled) applyStateResponse(updated);
            })
            .catch(() => {});
        }
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
  }, [applyStateResponse]);

  // Suit l'avancement en direct pendant toute synchro (automatique ou ponctuelle)
  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      fetchFinanceSyncStatus()
        .then(status => {
          if (cancelled) return;
          setLiveProgress(prev => {
            if (prev?.is_running && !status.is_running) {
              setUsageRefreshKey(k => k + 1);
              if (status.last_message) {
                setSavedBanner(status.last_message);
              }
              fetchFinanceSyncPreferences()
                .then(res => {
                  if (cancelled) return;
                  applyStateResponse(res);
                  if (onSynced) onSynced();
                })
                .catch(() => {});
            }
            return status;
          });
        })
        .catch(() => {});
    };
    const intervalMs = isSyncActive ? 2000 : 12000;
    const timer = window.setInterval(poll, intervalMs);
    window.addEventListener("finance-sync-started", poll);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("finance-sync-started", poll);
    };
  }, [isSyncActive, applyStateResponse, onSynced]);

  // Recherche dans le catalogue .INDX uniquement lorsque l'utilisateur ouvre "+ Ajouter un indice"
  useEffect(() => {
    if (!addIndexOpen) return;
    const q = indexSearch.trim();
    if (q.length < 2) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setEodhdIndxLoading(true);
      fetchEodhdIndxCatalog(q, 60, false)
        .then(res => {
          if (!cancelled) setEodhdIndxItems(res.items || []);
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
  }, [addIndexOpen, indexSearch]);

  const visibleIndxItems = indexSearch.trim().length >= 2 ? eodhdIndxItems : [];

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
        stock_price_exchanges: next.stock_price_exchanges || [],
        full_data_exchanges: next.full_data_exchanges,
        etf_exchanges: next.etf_exchanges || [],
        fundamentals_watchlists: next.fundamentals_watchlists ?? true,
        fundamentals_indices: next.fundamentals_indices ?? true,
        fundamentals_budget_pct: next.fundamentals_budget_pct,
        fundamentals_quota_safety_pct: next.fundamentals_quota_safety_pct,
        fundamentals_priority_order: next.fundamentals_priority_order,
      });
      applyStateResponse(res);
      setUsageRefreshKey(k => k + 1);
      setSavedBanner("Préférences enregistrées.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d'enregistrer les réglages.");
    } finally {
      setSaving(false);
    }
  }

  function toggleListCode(
    key: "index_codes" | "exchanges" | "stock_price_exchanges" | "etf_exchanges",
    code: string,
  ) {
    if (!prefs || saving || isSyncActive) return;
    const upper = code.toUpperCase();
    const current = prefs[key] || [];
    const nextList = current.includes(upper) ? current.filter(c => c !== upper) : [...current, upper];
    void persistPrefs({ ...prefs, [key]: nextList });
  }

  function toggleStockDailyExchange(code: string) {
    if (!prefs || saving || isSyncActive) return;
    const upper = code.toUpperCase();
    const stockPrices = prefs.stock_price_exchanges || [];
    const fullData = prefs.full_data_exchanges || [];
    const isOn = stockPrices.includes(upper) || fullData.includes(upper);
    if (isOn) {
      void persistPrefs({
        ...prefs,
        stock_price_exchanges: stockPrices.filter(c => c !== upper),
        full_data_exchanges: fullData.filter(c => c !== upper),
      });
    } else {
      void persistPrefs({
        ...prefs,
        stock_price_exchanges: [...stockPrices, upper],
      });
    }
  }

  async function handleRunSource(kind: FinanceSyncSourceKind, code?: string) {
    if (isSyncActive || saving || busySourceKey) return;
    const key = `${kind}:${code || ""}`;
    setBusySourceKey(key);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await runFinanceSyncSourceNow({
        kind,
        code: code || null,
        batch_size: 150,
        background: true,
      });
      applyStateResponse(res);
      if (res.started) {
        window.dispatchEvent(new Event("finance-sync-started"));
        setSavedBanner(`Chargement immédiat (${code || kind}) lancé en arrière-plan…`);
      } else if (res.already_running || res.summary?.skipped) {
        setSavedBanner("Une synchronisation est déjà en cours en arrière-plan.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec du chargement de la source.");
    } finally {
      setBusySourceKey(null);
    }
  }

  async function handleRunNow(forceRefresh = false) {
    if (isSyncActive || saving) return;
    setRunning(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await runFinanceSyncNow(forceRefresh);
      applyStateResponse(res);
      const s = res.summary;
      if (s?.skipped && s.reason === "already_running") {
        setSavedBanner("Une synchronisation est déjà en cours en arrière-plan.");
      } else if (res.started) {
        window.dispatchEvent(new Event("finance-sync-started"));
        setSavedBanner("Synchronisation lancée en arrière-plan — elle continue même si vous changez d'onglet.");
      } else {
        setSavedBanner("Synchronisation terminée.");
        setUsageRefreshKey(k => k + 1);
        if (onSynced) onSynced();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la synchronisation immédiate.");
    } finally {
      setRunning(false);
    }
  }

  async function handleUpgradeWarehouse(forceAllFundamentals: boolean) {
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
      applyStateResponse(res);
      const s = res.summary;
      if (s?.skipped && s.reason === "already_running") {
        setSavedBanner("Une synchronisation est déjà en cours en arrière-plan.");
      } else if (s?.skipped && s.reason === "eodhd_key_missing") {
        setError("Clé API EODHD (EOD_HISTORICAL_DATA_KEY) non configurée.");
      } else if (res.started) {
        window.dispatchEvent(new Event("finance-sync-started"));
        setSavedBanner("Migration / actualisation EODHD lancée en arrière-plan…");
      } else {
        setSavedBanner("Mise à jour EODHD terminée.");
        setUsageRefreshKey(k => k + 1);
        if (onSynced) onSynced();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la mise à jour EODHD.");
    } finally {
      setRunning(false);
    }
  }

  async function handleRebuildScreener() {
    if (isSyncActive || saving) return;
    setRunning(true);
    setError(null);
    setSavedBanner(null);
    try {
      const res = await rebuildFinanceScreener();
      const refreshed = await fetchFinanceSyncPreferences();
      applyStateResponse(refreshed);
      setSavedBanner(`Screener local réindexé (0 call) : ${res.indexed_count} valeur(s) analysée(s).`);
      if (onSynced) onSynced();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de réindexation locale du Screener.");
    } finally {
      setRunning(false);
    }
  }

  const totalWatchlistStocks = useMemo(
    () => watchlists.reduce((acc, wl) => acc + (wl.items_count || 0), 0),
    [watchlists],
  );

  const majorStats = useMemo(() => {
    const majors = indices.filter(i => i.tier === "major");
    return {
      count: majors.length || 9,
      totalStocks: majors.reduce((acc, i) => acc + (i.constituents_count || 0), 0),
      loadedStocks: majors.reduce((acc, i) => acc + (i.loaded_count || 0), 0),
    };
  }, [indices]);

  const selectedIndicesStocksCount = useMemo(() => {
    if (!prefs) return 0;
    const seen = new Set<string>();
    let sum = 0;
    for (const idx of indices) {
      const c = idx.code.toUpperCase();
      const active = (prefs.major_indices_constituents && idx.tier === "major") || prefs.index_codes.includes(c);
      if (active && !seen.has(c)) {
        seen.add(c);
        sum += idx.constituents_count || 0;
      }
    }
    return sum;
  }, [indices, prefs]);

  const extraIndexRows = useMemo(() => {
    if (!prefs) return [];
    const majorSet = new Set(indices.filter(i => i.tier === "major").map(i => i.code.toUpperCase()));
    const byCode = new Map(indices.map(i => [i.code.toUpperCase(), i]));
    return (prefs.index_codes || [])
      .map(c => c.toUpperCase())
      .filter(c => !(prefs.major_indices_constituents && majorSet.has(c)))
      .map(c => {
        const known = byCode.get(c);
        return {
          code: c,
          name: known?.name || c.replace(".INDX", ""),
          flag: known?.flag || "📊",
          count: known?.constituents_count || 0,
          loadedCount: known?.loaded_count || 0,
        };
      });
  }, [indices, prefs]);

  const indexAddCandidates = useMemo(() => {
    if (!prefs) return [];
    const needle = indexSearch.trim().toLowerCase();
    const majorSet = new Set(indices.filter(i => i.tier === "major").map(i => i.code.toUpperCase()));
    const selectedSet = new Set((prefs.index_codes || []).map(c => c.toUpperCase()));
    return indices.filter(idx => {
      const c = idx.code.toUpperCase();
      if (selectedSet.has(c) || (prefs.major_indices_constituents && majorSet.has(c))) return false;
      if (!needle) return true;
      return `${idx.code} ${idx.name} ${idx.region}`.toLowerCase().includes(needle);
    });
  }, [indices, indexSearch, prefs]);

  const exchangeSourceByCode = useMemo(() => {
    const m = new Map<string, FinanceExchangeSourceStatus>();
    for (const s of exchangeSources) m.set(s.code.toUpperCase(), s);
    return m;
  }, [exchangeSources]);

  const visibleStockExchanges = useMemo(() => {
    const visible = new Set(CORE_EXCHANGES);
    for (const c of prefs?.stock_price_exchanges || []) visible.add(c.toUpperCase());
    for (const c of prefs?.full_data_exchanges || []) visible.add(c.toUpperCase());
    for (const s of exchangeSources) {
      if (s.stocks_with_bars > 0 || s.stocks_with_fundamentals > 0) visible.add(s.code.toUpperCase());
    }
    return Array.from(visible).map(
      code =>
        exchangeSourceByCode.get(code) || {
          code,
          label: code,
          country: "",
          flag: "🌐",
          currency: "",
          catalog_synced: false,
          synced_at: null,
          stocks_total: 0,
          stocks_in_screener: 0,
          stocks_with_bars: 0,
          stocks_with_fundamentals: 0,
          etf_total: 0,
          etf_in_screener: 0,
          etf_with_bars: 0,
        },
    );
  }, [exchangeSourceByCode, exchangeSources, prefs]);

  const visibleEtfExchanges = useMemo(() => {
    const visible = new Set(CORE_EXCHANGES);
    for (const c of prefs?.etf_exchanges || []) visible.add(c.toUpperCase());
    for (const s of exchangeSources) {
      if (s.etf_in_screener > 0 || s.etf_with_bars > 0) visible.add(s.code.toUpperCase());
    }
    return Array.from(visible).map(
      code =>
        exchangeSourceByCode.get(code) || {
          code,
          label: code,
          country: "",
          flag: "🌐",
          currency: "",
          catalog_synced: false,
          synced_at: null,
          stocks_total: 0,
          stocks_in_screener: 0,
          stocks_with_bars: 0,
          stocks_with_fundamentals: 0,
          etf_total: 0,
          etf_in_screener: 0,
          etf_with_bars: 0,
        },
    );
  }, [exchangeSourceByCode, exchangeSources, prefs]);

  const addableStockExchanges = useMemo(() => {
    const shown = new Set(visibleStockExchanges.map(s => s.code));
    return exchangeSources.filter(s => !shown.has(s.code));
  }, [exchangeSources, visibleStockExchanges]);

  const addableEtfExchanges = useMemo(() => {
    const shown = new Set(visibleEtfExchanges.map(s => s.code));
    return exchangeSources.filter(s => !shown.has(s.code));
  }, [exchangeSources, visibleEtfExchanges]);

  const catalogRows = useMemo(() => {
    const exchByCode = new Map(exchanges.map(e => [e.code.toUpperCase(), e]));
    const codes = Array.from(new Set(["EUFUND", "CC", ...(prefs?.exchanges || [])]));
    return codes.map(code => {
      const info = exchByCode.get(code);
      const total = info?.total || 0;
      const estimatedTotal = info?.estimated_total || 0;
      const countLabel =
        total > 0
          ? total.toLocaleString("fr-FR")
          : estimatedTotal > 0
            ? `≈ ${estimatedTotal.toLocaleString("fr-FR")}`
            : "0";
      return {
        code,
        label: info?.label || (code === "EUFUND" ? "Fonds Européens OPCVM" : code === "CC" ? "Cryptomonnaies" : code),
        total,
        countLabel,
      };
    });
  }, [exchanges, prefs?.exchanges]);

  const disabledAll = saving || isSyncActive;

  return (
    <section className={styles.root} aria-label="Données et synchronisation boursière">
      {/* En-tête global */}
      <div className={styles.headerCard}>
        <div className={styles.headerTop}>
          <div className={styles.titleRow}>
            <span className={styles.titleIcon}>
              <CalendarClock size={18} />
            </span>
            <div className={styles.titleText}>
              <h3>Données &amp; Synchronisation</h3>
              <p className={styles.subtitle}>
                Choisissez simplement quelles données garder à jour tous les jours (les <strong>cours</strong>) et
                laissez les <strong>fondamentaux</strong> se charger petit à petit.
                {prefs?.last_run_at
                  ? ` · Dernier passage : ${new Date(prefs.last_run_at).toLocaleString("fr-FR", {
                      day: "2-digit",
                      month: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}`
                  : ""}
              </p>
            </div>
          </div>

          <div className={styles.headerActions}>
            {prefs && (
              <button
                type="button"
                role="switch"
                aria-checked={prefs.enabled}
                className={`${styles.switchBtn} ${prefs.enabled ? styles.switchBtnOn : ""}`}
                disabled={disabledAll}
                onClick={() => void persistPrefs({ ...prefs, enabled: !prefs.enabled })}
                title="Activer ou mettre en pause la synchronisation automatique quotidienne en arrière-plan"
              >
                <span className={styles.switchTrack}>
                  <span className={styles.switchThumb} />
                </span>
                <span>{prefs.enabled ? "Auto 24h : Activée" : "Auto 24h : En pause"}</span>
              </button>
            )}
            <button
              type="button"
              className={styles.primaryBtn}
              disabled={loading || disabledAll}
              onClick={() => void handleRunNow(false)}
              title="Exécuter maintenant la synchronisation complète selon vos réglages ci-dessous"
            >
              {isSyncActive ? <LoaderCircle size={13} className="spin" /> : <Play size={13} />}
              <span>{isSyncActive ? "En cours…" : "Tout synchroniser maintenant"}</span>
            </button>
            <button
              type="button"
              className={styles.ghostBtn}
              disabled={loading || disabledAll}
              onClick={() => void handleRunNow(true)}
              title="Forcer le re-téléchargement réseau même pour les valeurs déjà en cache aujourd'hui"
            >
              <RefreshCw size={12} className={isSyncActive ? "spin" : ""} />
              <span>Forcer</span>
            </button>
            {onClose && (
              <button type="button" className={styles.ghostBtn} onClick={onClose} aria-label="Fermer">
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
                <span>· {liveProgress?.current_label || "Traitement des données…"}</span>
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
        {savedBanner && (
          <div className="finance-index-import-banner">
            <Check size={13} style={{ display: "inline", verticalAlign: "-2px", marginRight: 5 }} />
            {savedBanner}
          </div>
        )}
      </div>

      {loading && !prefs ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>Chargement de vos sources de données…</span>
        </div>
      ) : prefs ? (
        <>
          {/* Bloc 1 : Les Cours (tous les jours) */}
          <section className={styles.card} aria-label="Les cours et historiques quotidiens">
            <div className={styles.cardHead}>
              <div className={styles.titleRow}>
                <span className={styles.titleIcon}>
                  <TrendingUp size={17} />
                </span>
                <div className={styles.titleText}>
                  <h3>1. Les Cours · Cotations, historiques &amp; indicateurs (tous les jours)</h3>
                  <p className={styles.subtitle}>
                    Activez <strong>Tous les jours</strong> sur les sources que vous voulez tenir à jour
                    automatiquement, ou cliquez sur <strong>Charger tout de suite</strong> en 1 seul clic.
                  </p>
                </div>
              </div>
            </div>

            {/* Suivi & Indices */}
            <div className={styles.sectionGroup}>
              <div className={styles.groupHeader}>
                <span className={styles.groupTitle}>Mes suivis &amp; Indices</span>
                <button
                  type="button"
                  className={styles.ghostBtn}
                  disabled={disabledAll}
                  onClick={() => setAddIndexOpen(v => !v)}
                >
                  <Plus size={12} />
                  <span>{addIndexOpen ? "Fermer" : "Ajouter un indice"}</span>
                </button>
              </div>

              <div className={styles.sourceList}>
                <SyncSourceRow
                  title="Mes listes de suivi"
                  badges={[
                    { text: "Watchlists", variant: "code" },
                    { text: `${totalWatchlistStocks.toLocaleString("fr-FR")} titres`, variant: "info" },
                  ]}
                  meta={
                    watchlists.length > 0
                      ? `${totalWatchlistStocks.toLocaleString("fr-FR")} titre${totalWatchlistStocks > 1 ? "s" : ""} dans ${watchlists.length} liste${watchlists.length > 1 ? "s" : ""}`
                      : "0 titre · aucune liste de suivi créée"
                  }
                  dailyEnabled={prefs.watchlists}
                  onToggleDaily={() => void persistPrefs({ ...prefs, watchlists: !prefs.watchlists })}
                  onLoadNow={() => void handleRunSource("watchlists")}
                  loadingThis={busySourceKey === "watchlists:"}
                  disabled={disabledAll}
                />

                <SyncSourceRow
                  title="Grands indices mondiaux"
                  badges={[
                    { text: `${majorStats.count} indices`, variant: "code" },
                    { text: `${majorStats.totalStocks.toLocaleString("fr-FR")} actions`, variant: "info" },
                  ]}
                  meta={`${majorStats.loadedStocks.toLocaleString("fr-FR")} / ${majorStats.totalStocks.toLocaleString("fr-FR")} actions avec cours en base (CAC 40, S&P 500, Nasdaq 100, Euro Stoxx 50, DAX…)`}
                  dailyEnabled={prefs.major_indices_constituents}
                  onToggleDaily={() =>
                    void persistPrefs({
                      ...prefs,
                      major_indices_constituents: !prefs.major_indices_constituents,
                      principal_indices: !prefs.major_indices_constituents,
                    })
                  }
                  onLoadNow={() => void handleRunSource("major_indices")}
                  loadingThis={busySourceKey === "major_indices:"}
                  disabled={disabledAll}
                />

                {extraIndexRows.map(idx => (
                  <SyncSourceRow
                    key={idx.code}
                    title={`${idx.flag} ${idx.name}`}
                    badges={[
                      { text: idx.code, variant: "code" },
                      {
                        text: idx.count > 0 ? `${idx.count.toLocaleString("fr-FR")} actions` : "EODHD .INDX",
                        variant: "info",
                      },
                    ]}
                    meta={
                      idx.count > 0
                        ? `${idx.loadedCount.toLocaleString("fr-FR")} / ${idx.count.toLocaleString("fr-FR")} actions avec cours`
                        : "Composition d'indice EODHD (taille connue après premier chargement)"
                    }
                    dailyEnabled={true}
                    onToggleDaily={() => toggleListCode("index_codes", idx.code)}
                    onLoadNow={() => void handleRunSource("index", idx.code)}
                    loadingThis={busySourceKey === `index:${idx.code}`}
                    disabled={disabledAll}
                    onRemove={() => toggleListCode("index_codes", idx.code)}
                    removeLabel={`Retirer l'indice ${idx.name}`}
                  />
                ))}
              </div>

              {addIndexOpen && (
                <div className={styles.addDrawer}>
                  <div className={styles.addForm}>
                    <Search size={13} style={{ opacity: 0.65 }} />
                    <input
                      type="text"
                      className={styles.input}
                      value={indexSearch}
                      onChange={e => setIndexSearch(e.target.value)}
                      placeholder="Rechercher un indice (SBF 120, Russell 2000, MSCI, DAX…)"
                    />
                  </div>
                  <div className={styles.chipGrid}>
                    {indexAddCandidates.slice(0, 24).map(idx => (
                      <button
                        key={idx.code}
                        type="button"
                        className={styles.chip}
                        disabled={disabledAll}
                        onClick={() => toggleListCode("index_codes", idx.code)}
                      >
                        <Plus size={11} />
                        <span>
                          {idx.flag} {idx.name} ({idx.constituents_count.toLocaleString("fr-FR")} actions)
                        </span>
                      </button>
                    ))}
                    {eodhdIndxLoading && <small>Recherche dans le catalogue EODHD .INDX…</small>}
                    {visibleIndxItems.slice(0, 20).map(item => (
                      <button
                        key={item.eod_ticker}
                        type="button"
                        className={styles.chip}
                        disabled={disabledAll}
                        onClick={() => toggleListCode("index_codes", item.eod_ticker)}
                      >
                        <Plus size={11} />
                        <span>
                          {item.name} ({item.eod_ticker})
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Actions par Bourse */}
            <div className={styles.sectionGroup}>
              <div className={styles.groupHeader}>
                <span className={styles.groupTitle}>Actions par bourse (cours &amp; indicateurs 4 unités)</span>
                <button
                  type="button"
                  className={styles.ghostBtn}
                  disabled={disabledAll}
                  onClick={() => setAddStockExchOpen(v => !v)}
                >
                  <Plus size={12} />
                  <span>{addStockExchOpen ? "Fermer" : "Ajouter une bourse d'actions"}</span>
                </button>
              </div>

              <div className={styles.sourceList}>
                {visibleStockExchanges.map(src => {
                  const hasDaily =
                    (prefs.stock_price_exchanges || []).includes(src.code) ||
                    (prefs.full_data_exchanges || []).includes(src.code);
                  const hasFund = (prefs.full_data_exchanges || []).includes(src.code);
                  const prefix = src.counts_estimated ? "≈ " : "";
                  const totalTxt = `${prefix}${src.stocks_total.toLocaleString("fr-FR")}`;
                  const meta = `${src.stocks_with_bars.toLocaleString("fr-FR")} / ${totalTxt} actions avec cours${
                    src.catalog_synced
                      ? ` · ${src.stocks_in_screener.toLocaleString("fr-FR")} au Screener`
                      : " (non chargée)"
                  }`;
                  return (
                    <SyncSourceRow
                      key={`stk-${src.code}`}
                      title={`${src.flag} Actions ${src.label}`}
                      badges={[
                        { text: src.code, variant: "code" },
                        { text: `${totalTxt} actions`, variant: "info" },
                        ...(hasFund ? [{ text: "+ Fondamentaux", variant: "info" as const }] : []),
                      ]}
                      meta={meta}
                      dailyEnabled={hasDaily}
                      onToggleDaily={() => toggleStockDailyExchange(src.code)}
                      onLoadNow={() => void handleRunSource("stocks_exchange", src.code)}
                      loadingThis={busySourceKey === `stocks_exchange:${src.code}`}
                      disabled={disabledAll}
                    />
                  );
                })}
              </div>

              {addStockExchOpen && (
                <div className={styles.addDrawer}>
                  <div className={styles.chipGrid}>
                    {addableStockExchanges.map(src => {
                      const prefix = src.counts_estimated ? "≈ " : "";
                      return (
                        <button
                          key={src.code}
                          type="button"
                          className={styles.chip}
                          disabled={disabledAll}
                          onClick={() => {
                            toggleStockDailyExchange(src.code);
                            setAddStockExchOpen(false);
                          }}
                        >
                          <Plus size={11} />
                          <span>
                            {src.flag} {src.label} ({prefix}
                            {src.stocks_total.toLocaleString("fr-FR")} actions)
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <form
                    className={styles.addForm}
                    onSubmit={e => {
                      e.preventDefault();
                      const clean = customStockCode.trim().toUpperCase();
                      if (clean) {
                        setCustomStockCode("");
                        setAddStockExchOpen(false);
                        void handleRunSource("stocks_exchange", clean);
                      }
                    }}
                  >
                    <input
                      type="text"
                      className={styles.input}
                      value={customStockCode}
                      onChange={e => setCustomStockCode(e.target.value.toUpperCase())}
                      maxLength={12}
                      placeholder="Code bourse EODHD (ex. SW, AS, MI, HK)…"
                      aria-label="Code bourse d'actions à charger"
                    />
                    <button type="submit" className={styles.loadBtn} disabled={!customStockCode.trim() || disabledAll}>
                      <Download size={12} />
                      <span>Charger</span>
                    </button>
                  </form>
                </div>
              )}
            </div>

            {/* ETFs par Bourse */}
            <div className={styles.sectionGroup}>
              <div className={styles.groupHeader}>
                <span className={styles.groupTitle}>ETFs par bourse (cours &amp; technique 4 unités — sans fondamentaux)</span>
                <button
                  type="button"
                  className={styles.ghostBtn}
                  disabled={disabledAll}
                  onClick={() => setAddEtfExchOpen(v => !v)}
                >
                  <Plus size={12} />
                  <span>{addEtfExchOpen ? "Fermer" : "Ajouter une bourse d'ETFs"}</span>
                </button>
              </div>

              <div className={styles.sourceList}>
                {visibleEtfExchanges.map(src => {
                  const hasDaily = (prefs.etf_exchanges || []).includes(src.code);
                  const prefix = src.counts_estimated ? "≈ " : "";
                  const totalTxt = `${prefix}${src.etf_total.toLocaleString("fr-FR")}`;
                  const meta = `${src.etf_with_bars.toLocaleString("fr-FR")} / ${totalTxt} ETFs avec cours${
                    src.catalog_synced
                      ? ` · ${src.etf_in_screener.toLocaleString("fr-FR")} au Screener`
                      : " (non chargée)"
                  }`;
                  return (
                    <SyncSourceRow
                      key={`etf-${src.code}`}
                      title={`${src.flag} ETF ${src.label}`}
                      badges={[
                        { text: "ETF", variant: "type" },
                        { text: src.code, variant: "code" },
                        { text: `${totalTxt} ETFs`, variant: "info" },
                      ]}
                      meta={meta}
                      dailyEnabled={hasDaily}
                      onToggleDaily={() => toggleListCode("etf_exchanges", src.code)}
                      onLoadNow={() => void handleRunSource("etf_exchange", src.code)}
                      loadingThis={busySourceKey === `etf_exchange:${src.code}`}
                      disabled={disabledAll}
                    />
                  );
                })}
              </div>

              {addEtfExchOpen && (
                <div className={styles.addDrawer}>
                  <div className={styles.chipGrid}>
                    {addableEtfExchanges.map(src => {
                      const prefix = src.counts_estimated ? "≈ " : "";
                      return (
                        <button
                          key={src.code}
                          type="button"
                          className={styles.chip}
                          disabled={disabledAll}
                          onClick={() => {
                            toggleListCode("etf_exchanges", src.code);
                            setAddEtfExchOpen(false);
                          }}
                        >
                          <Plus size={11} />
                          <span>
                            {src.flag} {src.label} ({prefix}
                            {src.etf_total.toLocaleString("fr-FR")} ETFs)
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  <form
                    className={styles.addForm}
                    onSubmit={e => {
                      e.preventDefault();
                      const clean = customEtfCode.trim().toUpperCase();
                      if (clean) {
                        setCustomEtfCode("");
                        setAddEtfExchOpen(false);
                        void handleRunSource("etf_exchange", clean);
                      }
                    }}
                  >
                    <input
                      type="text"
                      className={styles.input}
                      value={customEtfCode}
                      onChange={e => setCustomEtfCode(e.target.value.toUpperCase())}
                      maxLength={12}
                      placeholder="Code bourse ETF EODHD (ex. SW, AS, MI, F)…"
                      aria-label="Code bourse ETF à charger"
                    />
                    <button type="submit" className={styles.loadBtn} disabled={!customEtfCode.trim() || disabledAll}>
                      <Download size={12} />
                      <span>Charger</span>
                    </button>
                  </form>
                </div>
              )}
            </div>

            {/* Fonds OPCVM & Catalogues de recherche */}
            <div className={styles.sectionGroup}>
              <div className={styles.groupHeader}>
                <span className={styles.groupTitle}>Fonds OPCVM &amp; Catalogues de recherche</span>
              </div>
              <div className={styles.sourceList}>
                {catalogRows.map(cat => (
                  <SyncSourceRow
                    key={`cat-${cat.code}`}
                    title={cat.label}
                    badges={[
                      { text: cat.code, variant: "code" },
                      { text: `${cat.countLabel} titres`, variant: "info" },
                    ]}
                    meta={
                      cat.total > 0
                        ? `${cat.total.toLocaleString("fr-FR")} instruments référencés`
                        : `${cat.countLabel} instruments dans la liste · non chargée`
                    }
                    dailyEnabled={prefs.exchanges.includes(cat.code)}
                    onToggleDaily={() => toggleListCode("exchanges", cat.code)}
                    onLoadNow={() => void handleRunSource("catalog_exchange", cat.code)}
                    loadingThis={busySourceKey === `catalog_exchange:${cat.code}`}
                    disabled={disabledAll}
                  />
                ))}
              </div>
            </div>
          </section>

          {/* Bloc 2 : Les Données Fondamentales (petit à petit & après publications) */}
          <FinanceFundamentalsPlanCard
            prefs={prefs}
            exchangeSources={exchangeSources}
            watchlistStocksCount={totalWatchlistStocks}
            selectedIndicesStocksCount={selectedIndicesStocksCount}
            disabled={disabledAll}
            refreshKey={usageRefreshKey}
            onChangePrefs={next => void persistPrefs(next)}
          />

          {/* Bloc 3 : En bas — Calls API, Données synchronisées & Maintenance */}
          <FinanceSyncFooter
            refreshKey={usageRefreshKey}
            disabled={disabledAll}
            isSyncActive={isSyncActive}
            warehouseSources={warehouseSources}
            screenerSummary={screenerSummary}
            onUpgradeWarehouse={forceAll => void handleUpgradeWarehouse(forceAll)}
            onRebuildScreener={() => void handleRebuildScreener()}
          />
        </>
      ) : null}
    </section>
  );
}
