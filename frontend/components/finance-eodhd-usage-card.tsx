"use client";

import { Gauge, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { fetchEodhdUsage, type EodhdUsageReport } from "@/lib/api";

function fmt(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("fr-FR");
}

/**
 * Carte « Consommation EODHD » : quota réel du compte (`/api/user`), appels émis aujourd'hui par
 * l'application (ventilés par endpoint avec leur coût), estimation de la synchro et barème officiel.
 */
export function FinanceEodhdUsageCard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [report, setReport] = useState<EodhdUsageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCosts, setShowCosts] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await fetchEodhdUsage());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Consommation EODHD indisponible.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchEodhdUsage()
      .then(res => {
        if (!cancelled) {
          setReport(res);
          setError(null);
        }
      })
      .catch(err => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Consommation EODHD indisponible.");
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

  return (
    <div className="finance-sync-card">
      <div className="finance-sync-card-head">
        <strong style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Gauge size={14} /> Consommation EODHD (quota journalier, remis à zéro à minuit UTC)
        </strong>
        <button type="button" className="finance-tf-btn" disabled={loading} onClick={() => void load()}>
          <RefreshCw size={11} className={loading ? "spin" : ""} />
          <span>Actualiser</span>
        </button>
      </div>

      {error && <small style={{ color: "#be123c" }}>⚠️ {error}</small>}

      {report && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 12.5 }}>
          {acc ? (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <span>
                  Compte {acc.subscription ? `« ${acc.subscription} »` : ""} :{" "}
                  <strong>{fmt(acc.api_requests_today)}</strong> / {fmt(acc.daily_limit)} calls utilisés aujourd&apos;hui
                </span>
                <span>
                  Reste : <strong>{fmt(acc.remaining_today)}</strong>
                  {acc.extra_limit ? ` (+ ${fmt(acc.extra_limit)} calls supplémentaires)` : ""}
                </span>
              </div>
              {usedPct != null && (
                <div className="finance-sync-progress-track" style={{ marginTop: 4 }}>
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
            <small style={{ opacity: 0.75 }}>
              Quota du compte indisponible (clé EODHD absente, mode démo ou API injoignable).
            </small>
          )}

          <div>
            <strong>
              Émis par l&apos;application aujourd&apos;hui : {fmt(report.local.total_requests)} requêtes ≈{" "}
              {fmt(report.local.total_calls)} calls
            </strong>
            <small style={{ opacity: 0.7 }}> (depuis minuit UTC ou le dernier redémarrage du serveur)</small>
            {report.local.by_endpoint.length > 0 && (
              <table style={{ width: "100%", marginTop: 4, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left", opacity: 0.7 }}>
                    <th>Endpoint</th>
                    <th style={{ textAlign: "right" }}>Requêtes</th>
                    <th style={{ textAlign: "right" }}>Coût unitaire</th>
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
          </div>

          <div>
            <strong>Estimation de la synchro quotidienne : ≤ {fmt(report.sync_estimate.max_daily_calls)} calls</strong>
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
              {report.sync_estimate.lines.map(line => (
                <li key={line.label}>
                  {line.label} : {fmt(line.calls)} calls{line.periodic ? " (les jours de rafraîchissement)" : ""}
                </li>
              ))}
            </ul>
            <small style={{ opacity: 0.7 }}>{report.sync_estimate.note}</small>
          </div>

          <div>
            <button type="button" className="finance-tf-btn" onClick={() => setShowCosts(v => !v)}>
              {showCosts ? "Masquer" : "Voir"} le barème EODHD
            </button>
            {showCosts && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {report.cost_table.map(c => (
                  <li key={c.endpoint}>
                    {c.label} (<code>{c.endpoint}</code>) : <strong>{c.unit_cost}</strong> call{c.unit_cost > 1 ? "s" : ""} / requête
                  </li>
                ))}
                <li>
                  Source :{" "}
                  <a href={report.source_url} target="_blank" rel="noreferrer noopener">
                    eodhd.com · API limits
                  </a>
                </li>
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
