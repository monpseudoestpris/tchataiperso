"use client";

import { CalendarClock, Check, LoaderCircle, Play, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchFinanceSyncPreferences,
  runFinanceSyncNow,
  updateFinanceSyncPreferences,
  type FinanceSyncAvailableIndex,
  type FinanceSyncPreferences,
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
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [savedBanner, setSavedBanner] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceSyncPreferences()
      .then(res => {
        if (cancelled) return;
        setPrefs(res.preferences);
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

  async function persistPrefs(next: FinanceSyncPreferences) {
    setPrefs(next);
    setSaving(true);
    setSavedBanner(null);
    setError(null);
    try {
      const res = await updateFinanceSyncPreferences({
        enabled: next.enabled,
        principal_indices: next.principal_indices,
        indx_catalog: next.indx_catalog,
        index_codes: next.index_codes,
        watchlists: next.watchlists,
        exchanges: next.exchanges,
      });
      setPrefs(res.preferences);
      setExchanges(res.available_exchanges || []);
      setSavedBanner("Préférences enregistrées.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible d'enregistrer les réglages.");
    } finally {
      setSaving(false);
    }
  }

  function toggleBool(key: "enabled" | "principal_indices" | "indx_catalog" | "watchlists") {
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
      setExchanges(res.available_exchanges || []);
      const s = res.summary;
      const idxCount = Object.keys(s?.indices || {}).length;
      const exchCount = Object.keys(s?.exchanges || {}).length;
      setSavedBanner(
        `Synchronisation terminée (${s?.principal_indices_count ?? 0} indices, ${idxCount} compositions complètes, ${s?.watchlist_items_count ?? 0} suivi(s), ${exchCount} marché(s)).`,
      );
      if (onSynced) onSynced();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Échec de la synchronisation immédiate.");
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
      {savedBanner && <div className="finance-index-import-banner">✓ {savedBanner}</div>}

      {loading && !prefs ? (
        <div className="finance-index-drawer-loading">
          <LoaderCircle size={18} className="spin text-emerald" />
          <span>Chargement de vos préférences de synchronisation…</span>
        </div>
      ) : prefs ? (
        <div className="finance-sync-sections">
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

          {/* Bloc 2 : Constituants complets d'indices (cours EOD + Tableau Perfos) */}
          <div className="finance-sync-card">
            <div className="finance-sync-card-head">
              <strong>2. Actions complètes d&apos;indices (Tableau Perfos prêt d&apos;avance)</strong>
              <button
                type="button"
                className="finance-tf-btn"
                onClick={() => setShowAllIndices(prev => !prev)}
              >
                {showAllIndices ? "Indices principaux uniquement" : `Tous les indices (${indices.length})`}
              </button>
            </div>
            <div className="finance-sync-pills-grid">
              {displayedIndices.map(idx => {
                const checked = prefs.index_codes.includes(idx.code.toUpperCase());
                return (
                  <label
                    key={idx.code}
                    className={`finance-sync-pill ${checked ? "is-checked" : ""}`}
                    title={`${idx.name} (${idx.constituents_count} actions)`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={saving || running}
                      onChange={() => toggleListCode("index_codes", idx.code)}
                    />
                    <span>{idx.flag}</span>
                    <span>{idx.name}</span>
                    <small>({idx.constituents_count})</small>
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
