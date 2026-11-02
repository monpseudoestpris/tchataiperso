"use client";

import { useEffect, useState } from "react";

import {
  fetchFinanceStatements,
  type FinancialStatements,
  type StatementPeriod,
  type StatementRow,
} from "@/lib/api";

type Granularity = "annual" | "quarterly";

function formatAmount(v: number | null): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)} Md`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)} M`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(1)} k`;
  return v.toFixed(2);
}

function StatementTable({
  title,
  rows,
  dates,
  format,
}: {
  title: string;
  rows: StatementRow[];
  dates: string[];
  format: (row: StatementRow, v: number | null) => string;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="finance-statement-block">
      <h4>{title}</h4>
      <div className="finance-table-wrapper">
        <table className="finance-data-table">
          <thead>
            <tr>
              <th>Poste</th>
              {dates.map(d => (
                <th key={d}>{d}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.key}>
                <td>
                  <strong>{row.label}</strong>
                </td>
                {row.values.map((v, i) => (
                  <td key={dates[i]} className={v != null && v < 0 ? "text-rose" : undefined}>
                    {format(row, v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Compte de résultat, bilan, flux de trésorerie et ratios dérivés (chargés à la demande). */
export function FinanceStatements({ symbol, currency }: { symbol: string; currency: string }) {
  const [statements, setStatements] = useState<FinancialStatements | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [granularity, setGranularity] = useState<Granularity>("annual");

  useEffect(() => {
    let cancelled = false;
    setStatements(null);
    setError(null);
    fetchFinanceStatements(symbol)
      .then(res => !cancelled && setStatements(res))
      .catch(err => !cancelled && setError(err?.message || "Impossible de charger les états financiers."));
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (error) return <p className="text-rose">{error}</p>;
  if (!statements) return <p>Chargement des états financiers…</p>;

  const period: StatementPeriod = statements[granularity];
  const amount = (_: StatementRow, v: number | null) => formatAmount(v);

  return (
    <div className="finance-statements">
      <div className="finance-statements-head">
        <strong>États financiers ({currency})</strong>
        <div className="finance-timeframe-selector">
          {(["annual", "quarterly"] as const).map(g => (
            <button
              key={g}
              type="button"
              className={`finance-tf-btn ${granularity === g ? "active" : ""}`}
              onClick={() => setGranularity(g)}
            >
              {g === "annual" ? "Annuel" : "Trimestriel"}
            </button>
          ))}
        </div>
      </div>
      {period.dates.length === 0 ? (
        <p>Aucune donnée {granularity === "annual" ? "annuelle" : "trimestrielle"} disponible.</p>
      ) : (
        <>
          <StatementTable
            title="Indicateurs & ratios clés"
            rows={period.ratios}
            dates={period.dates}
            format={(row, v) => {
              if (v == null) return "—";
              const fmt = period.ratios.find(r => r.key === row.key)?.format;
              return fmt === "pct" ? `${v.toFixed(1)} %` : `${v.toFixed(2)}×`;
            }}
          />
          <StatementTable title="Compte de résultat" rows={period.income} dates={period.dates} format={(r, v) => (r.key === "DilutedEPS" && v != null ? v.toFixed(2) : amount(r, v))} />
          <StatementTable title="Bilan" rows={period.balance} dates={period.dates} format={amount} />
          <StatementTable title="Flux de trésorerie" rows={period.cashflow} dates={period.dates} format={amount} />
        </>
      )}
    </div>
  );
}
