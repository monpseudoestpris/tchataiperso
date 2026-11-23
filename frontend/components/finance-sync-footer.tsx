"use client";

import { Database, Gauge, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  fetchEodhdUsage,
  type EodhdUsageReport,
  type FinanceSyncStateResponse,
  type FinanceWarehouseSourcesSummary,
} from "@/lib/api";

import styles from "./finance-sync-panel.module.css";

function fmt(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("fr-FR");
}

type FinanceSyncFooterProps = {
  refreshKey: number;
  disabled: boolean;
  isSyncActive: boolean;
  warehouseSources: FinanceWarehouseSourcesSummary | null;
  screenerSummary?: FinanceSyncStateResponse["screener_summary"] | null;
  onUpgradeWarehouse: (forceAllFundamentals: boolean) => void;
  onRebuildScreener: () => void;
};

/**
 * Bloc 3 (en bas de l'onglet 5) : synthèse des calls EODHD, état de la base synchronisée et maintenance/migration.
 */
export function FinanceSyncFooter({
  refreshKey,
  disabled,
  isSyncActive,
  warehouseSources,
  screenerSummary,
  onUpgradeWarehouse,
  onRebuildScreener,
}: FinanceSyncFooterProps) {
  const [report, setReport] = useState<EodhdUsageReport | null>(null);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [usageError, setUsageError] = useState<string | null>(null);

  const loadUsage = useCallback(async () => {
    setLoadingUsage(true);
    setUsageError(null);
    try {
      setReport(await fetchEodhdUsage());
    } catch (err) {
      setUsageError(err instanceof Error ? err.message : "Consommation EODHD indisponible.");
    } finally {
      setLoadingUsage(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchEodhdUsage()
      .then(res => {
        if (!cancelled) {
          setReport(res);
          setUsageError(null);
        }
      })
      .catch(err => {
        if (!cancelled) setUsageError(err instanceof Error ? err.message : "Consommation EODHD indisponible.");
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const acc = report?.account;
  const usedPct =
    acc?.daily_limit && acc.api_requests_today != null
      ? Math.min(100, Math.round((acc.api_requests_today / acc.daily_limit) * 100))
      : null;
  const yahooRemaining =
    (warehouseSources?.yahoo_only_fundamentals_count ?? 0) +
    (warehouseSources?.yahoo_only_bars_symbols_count ?? 0);

  return (
    <div className={styles.footerGrid}>
      {/* Carte Calls EODHD */}
      <section className={styles.card} aria-label="Consommation et quota API EODHD">
        <div className={styles.cardHead}>
          <div className={styles.titleRow}>
            <span className={styles.titleIcon}>
              <Gauge size={16} />
            </span>
            <div className={styles.titleText}>
              <h3>Calls API EODHD</h3>
              <p className={styles.subtitle}>Quota journalier (remis à zéro à minuit UTC)</p>
            </div>
          </div>
          <button
            type="button"
            className={styles.ghostBtn}
            disabled={loadingUsage}
            onClick={() => void loadUsage()}
          >
            <RefreshCw size={12} className={loadingUsage ? "spin" : ""} />
            <span>Actualiser</span>
          </button>
        </div>

        {usageError && <small style={{ color: "#be123c" }}>⚠️ {usageError}</small>}

        {report && (
          <>
            {acc ? (
              <div>
                <div className={styles.inlineControlRow} style={{ justifyContent: "space-between" }}>
                  <span>
                    Compte {acc.subscription ? `« ${acc.subscription} » ` : ""}:{" "}
                    <strong>{fmt(acc.api_requests_today)}</strong> / {fmt(acc.daily_limit)} calls
                  </span>
                  <span>
                    Reste : <strong>{fmt(acc.remaining_today)}</strong>
                    {acc.extra_limit ? ` (+${fmt(acc.extra_limit)})` : ""}
                  </span>
                </div>
                {usedPct != null && (
                  <div className="finance-sync-progress-track" style={{ marginTop: 6 }}>
                    <div
                      className="finance-sync-progress-fill"
                      style={{
                        width: `${Math.max(2, usedPct)}%`,
                        background: usedPct >= 90 ? "#f43f5e" : usedPct >= 70 ? "#f59e0b" : undefined,
                      }}
                    />
                  </div>
                )}
              </div>
            ) : (
              <p className={styles.subtitle}>
                Quota du compte indisponible (clé EODHD absente, mode démo ou API injoignable).
              </p>
            )}

            <div className={styles.inlineControlRow}>
              <span>
                Émis par l&apos;app aujourd&apos;hui : <strong>{fmt(report.local.total_calls)}</strong> calls (
                {fmt(report.local.total_requests)} req.)
              </span>
              <span>·</span>
              <span>
                Synchro auto estimée : <strong>≤ {fmt(report.sync_estimate.max_daily_calls)}</strong> calls/j
              </span>
            </div>

            <details className={styles.detailsBox}>
              <summary>Détail par endpoint, estimation &amp; barème EODHD</summary>
              {report.local.by_endpoint.length > 0 && (
                <table className={styles.usageTable}>
                  <thead>
                    <tr style={{ textAlign: "left" }}>
                      <th>Endpoint</th>
                      <th style={{ textAlign: "right" }}>Req.</th>
                      <th style={{ textAlign: "right" }}>Coût</th>
                      <th style={{ textAlign: "right" }}>Calls</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.local.by_endpoint.map(it => (
                      <tr key={it.endpoint}>
                        <td title={it.endpoint}>{it.label}</td>
                        <td style={{ textAlign: "right" }}>{fmt(it.requests)}</td>
                        <td style={{ textAlign: "right" }}>× {it.unit_cost}</td>
                        <td style={{ textAlign: "right" }}>
                          <strong>{fmt(it.calls)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {report.sync_estimate.lines.length > 0 && (
                <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                  {report.sync_estimate.lines.map(line => (
                    <li key={line.label}>
                      {line.label} : {fmt(line.calls)} calls
                    </li>
                  ))}
                </ul>
              )}
              <p style={{ margin: "6px 0 0", opacity: 0.85 }}>{report.sync_estimate.note}</p>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {report.cost_table.map(c => (
                  <li key={c.endpoint}>
                    {c.label} (<code>{c.endpoint}</code>) : <strong>{c.unit_cost}</strong> call
                    {c.unit_cost > 1 ? "s" : ""}
                  </li>
                ))}
              </ul>
            </details>
          </>
        )}
      </section>

      {/* Carte Données synchronisées & Maintenance */}
      <section className={styles.card} aria-label="Données synchronisées et maintenance de la base">
        <div className={styles.cardHead}>
          <div className={styles.titleRow}>
            <span className={styles.titleIcon}>
              <Database size={16} />
            </span>
            <div className={styles.titleText}>
              <h3>Données synchronisées &amp; Maintenance</h3>
              <p className={styles.subtitle}>État local de l&apos;entrepôt SQLite et migration EODHD</p>
            </div>
          </div>
        </div>

        <div className={styles.statsGrid}>
          <div className={styles.statTile}>
            <strong>{fmt(screenerSummary?.stock_count)}</strong>
            <span>Actions au Screener ({fmt(screenerSummary?.with_fundamentals)} avec fondamentaux)</span>
          </div>
          <div className={styles.statTile}>
            <strong>{fmt(screenerSummary?.etf_count)}</strong>
            <span>ETFs indexés au Screener</span>
          </div>
          <div className={styles.statTile}>
            <strong>
              {warehouseSources
                ? `${fmt(warehouseSources.eodhd_bars_symbols_count)} / ${fmt(warehouseSources.total_bars_symbols)}`
                : "—"}
            </strong>
            <span>Historiques cours EODHD ({fmt(warehouseSources?.eodhd_fundamentals_count)} bilans EODHD)</span>
          </div>
          <div className={styles.statTile}>
            <strong>{fmt(yahooRemaining)}</strong>
            <span>Données Yahoo restantes à migrer</span>
          </div>
        </div>

        <div className={styles.headActions}>
          {warehouseSources && (
            <>
              <button
                type="button"
                className={yahooRemaining > 0 ? styles.primaryBtn : styles.ghostBtn}
                disabled={disabled || !warehouseSources.eodhd_configured}
                onClick={() => onUpgradeWarehouse(false)}
                title="Remplace uniquement les cours et états financiers encore issus de Yahoo Finance par des données EODHD"
              >
                {isSyncActive ? <LoaderCircle size={12} className="spin" /> : <RefreshCw size={12} />}
                <span>Migrer Yahoo → EODHD ({yahooRemaining})</span>
              </button>
              <button
                type="button"
                className={styles.ghostBtn}
                disabled={disabled || !warehouseSources.eodhd_configured}
                onClick={() => onUpgradeWarehouse(true)}
                title="Re-télécharge tous les états financiers de l'entrepôt depuis EODHD et réindexe le Screener"
              >
                <Database size={12} />
                <span>Tout réactualiser (EODHD)</span>
              </button>
            </>
          )}
          <button
            type="button"
            className={styles.ghostBtn}
            disabled={disabled}
            onClick={onRebuildScreener}
            title="Recalcule immédiatement tous les indicateurs (Jour, Semaine, Mois, 3 Mois + IsoPressure) depuis SQLite sans appel réseau"
          >
            <RefreshCw size={12} />
            <span>Réindexer le Screener (0 call)</span>
          </button>
        </div>
      </section>
    </div>
  );
}
