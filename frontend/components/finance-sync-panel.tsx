"use client";

import { CalendarClock, Check, Database, LoaderCircle, Play, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchFinanceSyncPreferences,
  fetchFinanceSyncStatus,
  runFinanceSyncNow,
  updateFinanceSyncPreferences,
  upgradeFinanceWarehouseToEodhd,
  type FinanceSyncAvailableIndex,
  type FinanceSyncPreferences,
  type FinanceSyncProgress,
  type FinanceWarehouseSourcesSummary,
  type SupportedExchangeInfo,
} from "@/lib/api";

/**
 * Panneau de configuration de la synchronisation quotidienne automatique :
 * permet à l'utilisateur de choisir exactement ce qui doit être mis à jour chaque jour
 * (indices de base activés par défaut, actions d'indices, watchlists, et gros catalogues EODHD).
 */
export function FinanceSyncPanel({
  onSynced,
  onClose,
}: {
  onSynced?: () => void;
  onClose: () => void;
}) {
  const [prefs, setPrefs] = useState<FinanceSyncPreferences | null>(null);
  const [indices, setIndices] = useState<FinanceSyncAvailableIndex[]>([]);
  const [exchanges, setExchanges] = useState<SupportedExchangeInfo[]>([]);
  const [showAllIndices, setShowAllIndices] = useState(false);
  const [liveProgress, setLiveProgress] = useState<FinanceSyncProgress | null>(null);
  const [warehouseSources, setWarehouseSources] = useState<FinanceWarehouseSourcesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [savedBanner, setSavedBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isSyncActive = running || Boolean(liveProgress?.is_running);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceSyncPreferences()
      .then(res => {
        if (cancelled) return;
        setPrefs(res.preferences);
        if (res.progress) setLiveProgress(res.progress);
        if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
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
              fetchFinanceSyncPreferences()
                .then(res => {
                  if (cancelled) return;
                  setPrefs(res.preferences);
                  if (res.warehouse_sources) setWarehouseSources(res.warehouse_sources);
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
      });
      setPrefs(res.preferences);
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

  function toggleListCode(key: "index_codes" | "exchanges", code: string) {
    if (!prefs || saving || running) return;
    const upper = code.toUpperCase();
    const exists = prefs[key].includes(upper);
    const nextList = exists ? prefs[key].filter(c => c !== upper) : [...prefs[key], upper];
    void persistPrefs({ ...prefs, [key]: nextList });
  }

  async function handleRunNow(forceRefresh = false) {
    if (running || saving) return;
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
        setSavedBanner("Une synchronisation quotidienne est déjà en cours en arrière-plan.");
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
      }
      if (onSynced) onSynced();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la synchronisation immédiate.");
    } finally {
      setRunning(false);
    }
  }

  async function handleUpgradeWarehouseToEodhd(forceAllFundamentals: boolean) {
    if (running || saving) return;
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
      } else {
        setSavedBanner(
          `Mise à jour EODHD terminée : ${s?.bars_upgraded ?? 0}/${s?.bars_targeted ?? 0} cours EOD mis à jour, ${s?.fundamentals_upgraded ?? 0}/${s?.fundamentals_targeted ?? 0} états financiers mis à jour depuis EODHD.`,
        );
      }
      if (onSynced) onSynced();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la mise à jour EODHD.");
    } finally {
      setRunning(false);
    }
  }

  const displayedIndices = showAllIndices ? indices : indices.filter(idx => idx.tier === "major");

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
            disabled={loading || running || saving}
            onClick={() => void handleRunNow(false)}
            title="Exécuter maintenant la synchronisation pour les éléments cochés ci-dessous"
          >
            {running ? <LoaderCircle size={12} className="spin" /> : <Play size={12} />}
            <span>{running ? "Synchronisation…" : "Synchroniser maintenant"}</span>
          </button>
          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={loading || running || saving}
            onClick={() => void handleRunNow(true)}
            title="Forcer le re-téléchargement réseau même pour les valeurs déjà en cache aujourd'hui"
          >
            <RefreshCw size={12} className={running ? "spin" : ""} />
            <span>Forcer</span>
          </button>
          <button type="button" className="finance-tf-btn" onClick={onClose} aria-label="Fermer les réglages de synchro">
            <X size={13} />
          </button>
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
                  disabled={running || saving || !warehouseSources.eodhd_configured}
                  onClick={() => void handleUpgradeWarehouseToEodhd(false)}
                  title="Remplace uniquement les cours et états financiers encore issus de Yahoo Finance par des données EODHD"
                >
                  {running ? <LoaderCircle size={12} className="spin" /> : <RefreshCw size={12} />}
                  <span>
                    Migrer les données Yahoo vers EODHD (
                    {warehouseSources.yahoo_only_fundamentals_count + warehouseSources.yahoo_only_bars_symbols_count})
                  </span>
                </button>
                <button
                  type="button"
                  className="finance-tf-btn"
                  disabled={running || saving || !warehouseSources.eodhd_configured}
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

          {/* Bloc 2 : Constituants complets d'indices (cours EOD + Screener + Tableau Perfos) */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>2. Contenu complet des indices (cours EOD, Screener &amp; Tableau Perfos)</strong>
              <button
                type="button"
                className="finance-tf-btn"
                onClick={() => setShowAllIndices(prev => !prev)}
              >
                {showAllIndices ? "Indices principaux uniquement" : `Tous les indices (${indices.length})`}
              </button>
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
                  Récupérer automatiquement chaque jour le contenu des 9 principaux indices (CAC 40, S&amp;P 500, NASDAQ 100, Dow Jones 30, EURO STOXX 50, DAX 40, FTSE 100, SMI 20, Nikkei 225)
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
                  Enrichir les fondamentaux &amp; historiques 10 ans pour le Screener :{" "}
                  <select
                    value={prefs.screener_fundamentals_interval_days}
                    disabled={saving || running || !prefs.screener_fundamentals}
                    onClick={e => e.stopPropagation()}
                    onChange={e =>
                      void persistPrefs({
                        ...prefs,
                        screener_fundamentals_interval_days: Number(e.target.value) || 7,
                      })
                    }
                    aria-label="Fréquence de rafraîchissement des données fondamentales"
                  >
                    <option value={7}>1× / semaine (7 j)</option>
                    <option value={14}>1× / 2 semaines (14 j)</option>
                    <option value={30}>1× / mois (30 j)</option>
                  </select>{" "}
                  ·{" "}
                  <select
                    value={prefs.screener_fundamentals_daily_cap}
                    disabled={saving || running || !prefs.screener_fundamentals}
                    onClick={e => e.stopPropagation()}
                    onChange={e =>
                      void persistPrefs({
                        ...prefs,
                        screener_fundamentals_daily_cap: Number(e.target.value) || 40,
                      })
                    }
                    aria-label="Nombre maximal de dossiers fondamentaux enrichis par passe"
                  >
                    <option value={20}>20 valeurs / passe</option>
                    <option value={40}>40 valeurs / passe</option>
                    <option value={80}>80 valeurs / passe</option>
                    <option value={120}>120 valeurs / passe</option>
                  </select>
                  {prefs.last_fundamentals_run_at
                    ? ` (dernière passe : ${new Date(prefs.last_fundamentals_run_at).toLocaleDateString("fr-FR")})`
                    : ""}
                </span>
              </label>
            </div>
            <div className="finance-sync-pills-grid">
              {displayedIndices.map(idx => {
                const autoIncluded = prefs.major_indices_constituents && idx.tier === "major";
                const checked = autoIncluded || prefs.index_codes.includes(idx.code.toUpperCase());
                return (
                  <label
                    key={idx.code}
                    className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                    title={
                      autoIncluded
                        ? `${idx.name} (${idx.constituents_count} actions) — inclus automatiquement chaque jour`
                        : `${idx.name} (${idx.constituents_count} actions)`
                    }
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={saving || running || autoIncluded}
                      onChange={() => toggleListCode("index_codes", idx.code)}
                    />
                    <span>{idx.flag}</span>
                    <span>{idx.name}</span>
                    <small>{autoIncluded ? `Auto · ${idx.constituents_count}` : `(${idx.constituents_count})`}</small>
                  </label>
                );
              })}
            </div>
          </div>

          {/* Bloc 3 : Watchlists & Catalogues de marchés */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>3. Listes de suivi &amp; Catalogues complets de marchés</strong>
              <small>Optionnel · Ne chargez que les places qui vous servent</small>
            </div>
            <div className="finance-sync-check-row">
              <label className="finance-sync-check">
                <input
                  type="checkbox"
                  checked={prefs.watchlists}
                  disabled={saving || running}
                  onChange={() => toggleBool("watchlists")}
                />
                <span>Cours quotidiens de toutes les valeurs présentes dans mes listes de suivi</span>
              </label>
            </div>
            <div className="finance-sync-pills-grid">
              {exchanges.map(ex => {
                const checked = prefs.exchanges.includes(ex.code.toUpperCase());
                return (
                  <label
                    key={ex.code}
                    className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                    title={ex.description}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={saving || running}
                      onChange={() => toggleListCode("exchanges", ex.code)}
                    />
                    <span>{ex.label}</span>
                    {ex.total > 0 && <small>({ex.total.toLocaleString("fr-FR")})</small>}
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
