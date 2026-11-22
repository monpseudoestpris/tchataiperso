"use client";

import { ArrowDown, ArrowUp, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  fetchFundamentalsQueue,
  runFundamentalsQueueNow,
  type FinanceSyncPreferences,
  type FundamentalsQueueState,
} from "@/lib/api";

const SOURCE_LABELS: Record<FinanceSyncPreferences["fundamentals_priority_order"][number], string> = {
  watchlists: "Listes de suivi",
  indices: "Indices choisis",
  full_exchanges: "Bourses complètes",
};

function fmt(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("fr-FR");
}

/**
 * Carte « Plan de chargement des fondamentaux » (onglet 5) : budget quotidien, ordre des priorités,
 * état de la file (jamais chargés, résultats publiés, échus, à jour) et prochains titres traités.
 */
export function FinanceFundamentalsPlanCard({
  prefs,
  disabled,
  refreshKey = 0,
  onChangePrefs,
}: {
  prefs: FinanceSyncPreferences;
  disabled: boolean;
  refreshKey?: number;
  onChangePrefs: (next: FinanceSyncPreferences) => void;
}) {
  const [state, setState] = useState<FundamentalsQueueState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);
  const [showNext, setShowNext] = useState(false);

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
  }, [refreshKey, reloadTick, prefs.fundamentals_budget_pct, prefs.fundamentals_priority_order, prefs.full_data_exchanges]);

  function moveSource(index: number, delta: -1 | 1) {
    const order = [...prefs.fundamentals_priority_order];
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    onChangePrefs({ ...prefs, fundamentals_priority_order: order });
  }

  async function handleRunNow() {
    setStarting(true);
    setMessage(null);
    try {
      const res = await runFundamentalsQueueNow();
      window.dispatchEvent(new Event("finance-sync-started"));
      setMessage(
        res.started
          ? "Passage lancé en arrière-plan (dans la limite du budget du jour)."
          : "Une synchronisation est déjà en cours : réessayez une fois terminée.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de lancer le passage.");
    } finally {
      setStarting(false);
    }
  }

  const s = state?.stats;
  const b = state?.budget;

  return (
    <div className="finance-sync-card">
      <div className="finance-sync-card-head">
        <strong>Plan de chargement des fondamentaux (étalé, priorisé, rafraîchi après publication)</strong>
        <div style={{ display: "flex", gap: 6 }}>
          <button type="button" className="finance-tf-btn" onClick={() => setReloadTick(t => t + 1)}>
            <RefreshCw size={11} />
            <span>Actualiser</span>
          </button>
          <button
            type="button"
            className="finance-tf-btn active"
            disabled={disabled || starting || !prefs.screener_fundamentals}
            onClick={() => void handleRunNow()}
            title="Traite tout de suite les titres les plus prioritaires, dans la limite du budget du jour"
          >
            {starting ? <LoaderCircle size={11} className="spin" /> : <Play size={11} />}
            <span>Lancer un passage maintenant</span>
          </button>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12.5 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span>Budget quotidien :</span>
            <select
              value={prefs.fundamentals_budget_pct}
              disabled={disabled}
              onChange={e => onChangePrefs({ ...prefs, fundamentals_budget_pct: Number(e.target.value) })}
              aria-label="Budget quotidien des fondamentaux"
            >
              {[5, 10, 20, 30, 50].map(p => (
                <option key={p} value={p}>
                  {p} % de la limite
                </option>
              ))}
            </select>
          </label>
          {b && (
            <span>
              ≈ <strong>{fmt(b.budget_calls)}</strong> calls/jour soit <strong>{fmt(b.titles_per_day)}</strong> titres
              {b.daily_limit_known ? "" : " (limite du compte inconnue : 100 000 supposée)"} · utilisé aujourd&apos;hui :{" "}
              {fmt(b.spent_today)}
            </span>
          )}
          <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span>Arrêt si le quota restant passe sous</span>
            <select
              value={prefs.fundamentals_quota_safety_pct}
              disabled={disabled}
              onChange={e => onChangePrefs({ ...prefs, fundamentals_quota_safety_pct: Number(e.target.value) })}
              aria-label="Marge de sécurité du quota"
            >
              {[10, 15, 25, 40].map(p => (
                <option key={p} value={p}>
                  {p} %
                </option>
              ))}
            </select>
          </label>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <span>Priorités :</span>
          {prefs.fundamentals_priority_order.map((src, idx) => (
            <span key={src} className="finance-sync-pill is-checked" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
              <strong>{idx + 1}.</strong> {SOURCE_LABELS[src]}
              <button
                type="button"
                className="finance-tf-btn"
                disabled={disabled || idx === 0}
                onClick={() => moveSource(idx, -1)}
                aria-label={`Monter ${SOURCE_LABELS[src]}`}
              >
                <ArrowUp size={10} />
              </button>
              <button
                type="button"
                className="finance-tf-btn"
                disabled={disabled || idx === prefs.fundamentals_priority_order.length - 1}
                onClick={() => moveSource(idx, 1)}
                aria-label={`Descendre ${SOURCE_LABELS[src]}`}
              >
                <ArrowDown size={10} />
              </button>
            </span>
          ))}
          <small style={{ opacity: 0.7 }}>Les coups de pouce (bouton « Compléter » du Screener) passent toujours devant.</small>
        </div>

        {s && (
          <div>
            <strong>
              {fmt(s.tracked)} titres suivis · {fmt(s.up_to_date)} à jour · {fmt(s.to_process)} à traiter
              {state && state.estimated_days > 0 ? ` (≈ ${state.estimated_days} jour${state.estimated_days > 1 ? "s" : ""})` : ""}
            </strong>
            <div style={{ opacity: 0.8 }}>
              {fmt(s.never_loaded)} jamais chargés · {fmt(s.reported)} résultats publiés à recharger · {fmt(s.due)} rafraîchissements
              échus · {fmt(s.errors)} en erreur{s.boosted ? ` · ${fmt(s.boosted)} coups de pouce` : ""}
            </div>
          </div>
        )}

        <small style={{ opacity: 0.75 }}>
          Chargement léger : fondamentaux (10 calls) + historique des cours s&apos;il manque (1 call). Un titre est rechargé après
          la publication de ses résultats (calendrier EODHD), sinon selon sa saison de publication habituelle (trimestrielle ou
          semestrielle), et au plus tard 120 ou 200 jours après le dernier chargement.
        </small>

        {state && state.next_items.length > 0 && (
          <div>
            <button type="button" className="finance-tf-btn" onClick={() => setShowNext(v => !v)}>
              {showNext ? "Masquer" : "Voir"} les {state.next_items.length} prochains titres
            </button>
            {showNext && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18, columns: 2 }}>
                {state.next_items.map(it => (
                  <li key={it.symbol}>
                    <code>{it.symbol}</code> · {it.why}
                    {it.reason ? ` (${it.reason})` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {message && <small>{message}</small>}
        {error && <small style={{ color: "#be123c" }}>⚠️ {error}</small>}
      </div>
    </div>
  );
}
