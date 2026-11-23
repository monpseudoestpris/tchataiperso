"use client";

import { ArrowDown, ArrowUp, BarChart3, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchFundamentalsQueue,
  runFundamentalsQueueNow,
  type FinanceExchangeSourceStatus,
  type FinanceSyncPreferences,
  type FundamentalsQueueState,
} from "@/lib/api";

import styles from "./finance-sync-panel.module.css";

const SOURCE_LABELS: Record<FinanceSyncPreferences["fundamentals_priority_order"][number], string> = {
  watchlists: "Mes listes de suivi",
  indices: "Actions des indices que je suis",
  full_exchanges: "Bourses d'actions complètes",
};

function fmt(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("fr-FR");
}

/**
 * Bloc 2 de l'onglet 5 : chargement progressif & rafraîchissement après publication des fondamentaux.
 */
export function FinanceFundamentalsPlanCard({
  prefs,
  exchangeSources = [],
  watchlistStocksCount = 0,
  selectedIndicesStocksCount = 0,
  disabled,
  refreshKey = 0,
  onChangePrefs,
}: {
  prefs: FinanceSyncPreferences;
  exchangeSources?: FinanceExchangeSourceStatus[];
  watchlistStocksCount?: number;
  selectedIndicesStocksCount?: number;
  disabled: boolean;
  refreshKey?: number;
  onChangePrefs: (next: FinanceSyncPreferences) => void;
}) {
  const [state, setState] = useState<FundamentalsQueueState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const watchlistsOn = prefs.fundamentals_watchlists ?? true;
  const indicesOn = prefs.fundamentals_indices ?? true;
  const fullDataSet = new Set((prefs.full_data_exchanges || []).map(c => c.toUpperCase()));

  useEffect(() => {
    let cancelled = false;
    fetchFundamentalsQueue()
      .then(res => {
        if (!cancelled) {
          setState(res);
          setError(null);
        }
      })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : "File des fondamentaux indisponible.");
      });
    return () => {
      cancelled = true;
    };
  }, [
    refreshKey,
    reloadTick,
    prefs.fundamentals_budget_pct,
    prefs.fundamentals_priority_order,
    prefs.full_data_exchanges,
    watchlistsOn,
    indicesOn,
  ]);

  function moveSource(index: number, delta: -1 | 1) {
    const order = [...prefs.fundamentals_priority_order];
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    onChangePrefs({ ...prefs, fundamentals_priority_order: order });
  }

  function toggleFullExchange(code: string) {
    const upper = code.toUpperCase();
    const current = prefs.full_data_exchanges || [];
    const next = current.includes(upper) ? current.filter(c => c !== upper) : [...current, upper];
    onChangePrefs({ ...prefs, full_data_exchanges: next });
  }

  async function handleRunNow() {
    setStarting(true);
    setMessage(null);
    setError(null);
    try {
      const res = await runFundamentalsQueueNow();
      window.dispatchEvent(new Event("finance-sync-started"));
      setMessage(
        res.started
          ? "Chargement d'un lot de fondamentaux lancé en arrière-plan (dans la limite du budget du jour)."
          : "Une tâche de synchronisation est déjà en cours — réessayez une fois terminée.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de lancer le lot de fondamentaux.");
    } finally {
      setStarting(false);
    }
  }

  const selectableExchanges = exchangeSources;
  const s = state?.stats;
  const b = state?.budget;

  return (
    <section className={styles.card} aria-label="Données fondamentales progressives">
      <div className={styles.cardHead}>
        <div className={styles.titleRow}>
          <span className={styles.titleIcon}>
            <BarChart3 size={17} />
          </span>
          <div className={styles.titleText}>
            <h3>2. Données Fondamentales · Petit à petit &amp; après résultats</h3>
            <p className={styles.subtitle}>
              Bilans, ratios et scores (10 calls/action) : ne sont pas rechargés tous les jours mais étalés selon
              votre plafond quotidien et rafraîchis dès qu&apos;une entreprise publie ses résultats.
            </p>
          </div>
        </div>

        <div className={styles.headActions}>
          <button
            type="button"
            role="switch"
            aria-checked={prefs.screener_fundamentals}
            disabled={disabled}
            className={`${styles.switchBtn} ${prefs.screener_fundamentals ? styles.switchBtnOn : ""}`}
            onClick={() => onChangePrefs({ ...prefs, screener_fundamentals: !prefs.screener_fundamentals })}
            title="Activer ou suspendre l'enrichissement progressif des fondamentaux lors de la synchro quotidienne"
          >
            <span className={styles.switchTrack}>
              <span className={styles.switchThumb} />
            </span>
            <span>{prefs.screener_fundamentals ? "Auto progressif : Oui" : "Auto progressif : Non"}</span>
          </button>

          <button
            type="button"
            className={styles.loadBtn}
            disabled={disabled || starting}
            onClick={() => void handleRunNow()}
            title="Traiter tout de suite un lot des actions les plus prioritaires, dans la limite du budget du jour"
          >
            {starting ? <LoaderCircle size={13} className="spin" /> : <Play size={13} />}
            <span>Charger un lot maintenant</span>
          </button>

          <button
            type="button"
            className={styles.ghostBtn}
            disabled={disabled}
            onClick={() => setReloadTick(t => t + 1)}
            aria-label="Actualiser l'état de la file des fondamentaux"
            title="Actualiser les compteurs"
          >
            <RefreshCw size={12} />
          </button>
        </div>
      </div>

      {s && (
        <div className={styles.inlineControlRow}>
          <strong>
            {fmt(s.up_to_date)} / {fmt(s.tracked)} actions à jour
          </strong>
          <span>·</span>
          <span>
            <strong>{fmt(s.to_process)}</strong> à traiter ({fmt(s.never_loaded)} jamais chargées,{" "}
            {fmt(s.reported)} résultats publiés, {fmt(s.due)} échus{s.boosted ? `, ${fmt(s.boosted)} prioritaires` : ""})
          </span>
          {state && state.estimated_days > 0 && (
            <>
              <span>·</span>
              <span>
                ≈ <strong>{state.estimated_days}</strong> jour{state.estimated_days > 1 ? "s" : ""} restant
                {state.estimated_days > 1 ? "s" : ""}
              </span>
            </>
          )}
        </div>
      )}

      <div className={styles.priorityList}>
        {prefs.fundamentals_priority_order.map((src, idx) => (
          <div key={src} className={styles.priorityRow}>
            <div className={styles.priorityLeft}>
              <span className={styles.rankBadge}>{idx + 1}</span>
              {src === "watchlists" && (
                <label className={styles.inlineField} style={{ cursor: disabled ? "default" : "pointer" }}>
                  <input
                    type="checkbox"
                    checked={watchlistsOn}
                    disabled={disabled}
                    onChange={() => onChangePrefs({ ...prefs, fundamentals_watchlists: !watchlistsOn })}
                  />
                  <strong>{SOURCE_LABELS.watchlists}</strong>
                  <span className={styles.codeBadge}>
                    {watchlistStocksCount.toLocaleString("fr-FR")} titre{watchlistStocksCount > 1 ? "s" : ""}
                  </span>
                </label>
              )}
              {src === "indices" && (
                <label className={styles.inlineField} style={{ cursor: disabled ? "default" : "pointer" }}>
                  <input
                    type="checkbox"
                    checked={indicesOn}
                    disabled={disabled}
                    onChange={() => onChangePrefs({ ...prefs, fundamentals_indices: !indicesOn })}
                  />
                  <strong>{SOURCE_LABELS.indices}</strong>
                  <span className={styles.codeBadge}>
                    {selectedIndicesStocksCount.toLocaleString("fr-FR")} actions
                  </span>
                </label>
              )}
              {src === "full_exchanges" && (
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                  <strong>{SOURCE_LABELS.full_exchanges} :</strong>
                  {selectableExchanges.map(ex => {
                    const active = fullDataSet.has(ex.code);
                    const totalLabel = `${ex.counts_estimated ? "≈ " : ""}${ex.stocks_total.toLocaleString("fr-FR")}`;
                    const detail = ` (${ex.stocks_with_fundamentals.toLocaleString("fr-FR")} / ${totalLabel})`;
                    return (
                      <button
                        key={ex.code}
                        type="button"
                        disabled={disabled}
                        className={`${styles.chip} ${active ? styles.chipActive : ""}`}
                        onClick={() => toggleFullExchange(ex.code)}
                        title={`Inclure progressivement les fondamentaux de toutes les actions de ${ex.label}`}
                      >
                        <span>{ex.flag}</span>
                        <span>
                          {ex.code}
                          {detail}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className={styles.rowActions}>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={disabled || idx === 0}
                onClick={() => moveSource(idx, -1)}
                aria-label={`Monter ${SOURCE_LABELS[src]}`}
                title="Augmenter la priorité"
              >
                <ArrowUp size={12} />
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={disabled || idx === prefs.fundamentals_priority_order.length - 1}
                onClick={() => moveSource(idx, 1)}
                aria-label={`Descendre ${SOURCE_LABELS[src]}`}
                title="Baisser la priorité"
              >
                <ArrowDown size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.inlineControlRow}>
        <label className={styles.inlineField}>
          <span>Rythme max :</span>
          <select
            className={styles.select}
            value={prefs.fundamentals_budget_pct}
            disabled={disabled}
            onChange={e => onChangePrefs({ ...prefs, fundamentals_budget_pct: Number(e.target.value) })}
            aria-label="Rythme quotidien des fondamentaux"
          >
            {[5, 10, 20, 30, 50].map(p => (
              <option key={p} value={p}>
                {p} % du quota/jour
              </option>
            ))}
          </select>
        </label>
        {b && (
          <span>
            ≈ <strong>{fmt(b.titles_per_day)}</strong> actions/jour ({fmt(b.budget_calls)} calls) · utilisé aujourd&apos;hui
            : {fmt(b.spent_today)}
          </span>
        )}
        <label className={styles.inlineField}>
          <span>Arrêt sécurité sous</span>
          <select
            className={styles.select}
            value={prefs.fundamentals_quota_safety_pct}
            disabled={disabled}
            onChange={e => onChangePrefs({ ...prefs, fundamentals_quota_safety_pct: Number(e.target.value) })}
            aria-label="Marge de sécurité du quota"
          >
            {[10, 15, 25, 40].map(p => (
              <option key={p} value={p}>
                {p} % restants
              </option>
            ))}
          </select>
        </label>
      </div>

      {state && state.next_items.length > 0 && (
        <details className={styles.detailsBox}>
          <summary>Voir les {state.next_items.length} prochaines actions en file d&apos;attente</summary>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, columns: 2 }}>
            {state.next_items.map(it => (
              <li key={it.symbol}>
                <code>{it.symbol}</code> · {it.why}
                {it.reason ? ` (${it.reason})` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}

      {message && <div className="finance-index-import-banner">✓ {message}</div>}
      {error && <div className="finance-modal-error">⚠️ {error}</div>}
    </section>
  );
}
