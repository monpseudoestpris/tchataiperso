"use client";

import { RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { FinanceMetricLabel } from "@/components/finance-info-tip";
import { buildStatementRatioCalc } from "@/lib/finance-calc-details";
import {
  fetchFinanceStatements,
  type EarningsHistoryRow,
  type FinancialStatements,
  type StatementPeriod,
  type StatementRow,
} from "@/lib/api";

type Granularity = "annual" | "quarterly";
type DepthOption = "5" | "10" | "all";
type SectionFilter = "all" | "ratios" | "income" | "balance" | "cashflow" | "earnings";

function formatAmount(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e12) return `${(v / 1e12).toFixed(2)} T`;
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)} Md`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(1)} M`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(1)} k`;
  return v.toFixed(2);
}

function formatDateHeader(dateStr: string, granularity: Granularity): string {
  if (granularity === "annual") {
    return dateStr.slice(0, 4);
  }
  const [y, m] = dateStr.split("-");
  const monthNum = Number(m);
  if (Number.isFinite(monthNum) && monthNum >= 1 && monthNum <= 12) {
    const q = Math.ceil(monthNum / 3);
    return `${y} T${q}`;
  }
  return dateStr;
}

function MiniSparkline({ values }: { values: (number | null)[] }) {
  const pts = values
    .map((v, i) => (v != null && Number.isFinite(v) ? { i, v } : null))
    .filter((p): p is { i: number; v: number } => p !== null);
  if (pts.length < 2) return <span className="finance-stmt-spark-empty">—</span>;

  const min = Math.min(...pts.map(p => p.v));
  const max = Math.max(...pts.map(p => p.v));
  const span = max - min || 1;
  const w = 64;
  const h = 20;
  const pad = 2;
  const first = pts[0].v;
  const last = pts[pts.length - 1].v;
  const stroke = last >= first ? "#10b981" : "#f43f5e";

  const d = pts
    .map((p, idx) => {
      const x = pad + (idx / Math.max(1, pts.length - 1)) * (w - pad * 2);
      const y = h - pad - ((p.v - min) / span) * (h - pad * 2);
      return `${idx === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="finance-stmt-sparkline" aria-hidden="true">
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function computeTotalEvolution(chronoValues: (number | null)[]): number | null {
  const valid = chronoValues.filter((v): v is number => v != null && Number.isFinite(v));
  if (valid.length < 2) return null;
  const first = valid[0];
  const last = valid[valid.length - 1];
  if (first === 0) return null;
  return ((last - first) / Math.abs(first)) * 100;
}

function StatementTable({
  title,
  rows,
  dates,
  granularity,
  newestFirst,
  showVarPct,
  isRatio,
  period,
  currency,
  format,
}: {
  title: string;
  rows: StatementRow[];
  dates: string[];
  granularity: Granularity;
  newestFirst: boolean;
  showVarPct: boolean;
  isRatio?: boolean;
  period?: StatementPeriod;
  currency?: string;
  format: (row: StatementRow, v: number | null) => string;
}) {
  if (rows.length === 0 || dates.length === 0) return null;

  const displayIndices = newestFirst
    ? dates.map((_, idx) => dates.length - 1 - idx)
    : dates.map((_, idx) => idx);

  return (
    <div className="finance-statement-block">
      <div className="finance-statement-block-head">
        <h4>{title}</h4>
        <span className="finance-statement-count">{rows.length} postes · {dates.length} périodes</span>
      </div>
      <div className="finance-table-wrapper finance-stmt-scroll">
        <table className="finance-data-table finance-stmt-table">
          <thead>
            <tr>
              <th className="finance-stmt-sticky-col">Poste</th>
              <th className="finance-stmt-trend-col">Tendance</th>
              <th className="finance-stmt-evol-col">Évol. période</th>
              {displayIndices.map(idx => (
                <th key={dates[idx]} title={dates[idx]}>
                  {formatDateHeader(dates[idx], granularity)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(row => {
              const evol = computeTotalEvolution(row.values);
              const latestVal = row.values[row.values.length - 1] ?? null;
              const calcDetail = period
                ? buildStatementRatioCalc(row.key, row.label, latestVal, period, currency || "USD")
                : undefined;
              return (
                <tr key={row.key}>
                  <td className="finance-stmt-sticky-col">
                    <FinanceMetricLabel termKey={row.key} label={row.label} calcDetail={calcDetail} strong />
                  </td>
                  <td className="finance-stmt-trend-col">
                    <MiniSparkline values={row.values} />
                  </td>
                  <td className="finance-stmt-evol-col">
                    {evol == null ? (
                      <span className="finance-stmt-muted">—</span>
                    ) : (
                      <span className={`finance-stmt-evol-badge ${evol >= 0 ? "is-pos" : "is-neg"}`}>
                        {evol >= 0 ? "+" : ""}{evol.toFixed(1)}%
                      </span>
                    )}
                  </td>
                  {displayIndices.map(idx => {
                    const v = row.values[idx] ?? null;
                    const prevIdx = granularity === "annual" ? idx - 1 : idx - 4;
                    const prev = prevIdx >= 0 ? (row.values[prevIdx] ?? null) : null;
                    let varPct: number | null = null;
                    if (showVarPct && !isRatio && v != null && prev != null && prev !== 0) {
                      varPct = ((v - prev) / Math.abs(prev)) * 100;
                    }
                    return (
                      <td key={dates[idx]} className={v != null && v < 0 ? "text-rose" : undefined}>
                        <div className="finance-stmt-cell-val">{format(row, v)}</div>
                        {varPct != null && (
                          <div className={`finance-stmt-cell-yoy ${varPct >= 0 ? "text-emerald" : "text-rose"}`}>
                            {varPct >= 0 ? "+" : ""}{varPct.toFixed(1)}%
                          </div>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function EarningsHistoryTable({ rows }: { rows: EarningsHistoryRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="finance-statement-block">
      <div className="finance-statement-block-head">
        <h4>Historique des résultats (BPA estimé vs publié)</h4>
        <span className="finance-statement-count">{rows.length} publications</span>
      </div>
      <div className="finance-table-wrapper finance-stmt-scroll">
        <table className="finance-data-table finance-stmt-table">
          <thead>
            <tr>
              <th className="finance-stmt-sticky-col">Clôture période</th>
              <th>Date publication</th>
              <th>BPA estimé</th>
              <th>BPA publié</th>
              <th>Écart</th>
              <th>Surprise (%)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={`${row.date}-${row.report_date ?? ""}`}>
                <td className="finance-stmt-sticky-col">
                  <strong>{row.date}</strong>
                </td>
                <td>{row.report_date || "—"}</td>
                <td>{row.eps_estimate != null ? row.eps_estimate.toFixed(2) : "—"}</td>
                <td>
                  <strong>{row.eps_actual != null ? row.eps_actual.toFixed(2) : "—"}</strong>
                  {row.currency ? ` ${row.currency}` : ""}
                </td>
                <td className={row.eps_difference != null ? (row.eps_difference >= 0 ? "text-emerald" : "text-rose") : undefined}>
                  {row.eps_difference != null ? `${row.eps_difference >= 0 ? "+" : ""}${row.eps_difference.toFixed(2)}` : "—"}
                </td>
                <td>
                  {row.surprise_pct == null ? (
                    "—"
                  ) : (
                    <span className={`finance-stmt-evol-badge ${row.surprise_pct >= 0 ? "is-pos" : "is-neg"}`}>
                      {row.surprise_pct >= 0 ? "+" : ""}{row.surprise_pct.toFixed(2)}%
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Explorateur historique des états financiers (EODHD prioritaire + cache BDD + backup Yahoo). */
export function FinanceStatements({ symbol, currency }: { symbol: string; currency: string }) {
  const [fetchState, setFetchState] = useState<{
    symbol: string;
    data: FinancialStatements | null;
    error: string | null;
  }>({ symbol: "", data: null, error: null });
  const [refreshing, setRefreshing] = useState(false);
  const [granularity, setGranularity] = useState<Granularity>("annual");
  const [depth, setDepth] = useState<DepthOption>("all");
  const [section, setSection] = useState<SectionFilter>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [newestFirst, setNewestFirst] = useState(true);
  const [showVarPct, setShowVarPct] = useState(true);
  const [showEmptyOverride, setShowEmptyOverride] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFinanceStatements(symbol, false)
      .then(res => {
        if (!cancelled) {
          setFetchState({ symbol, data: res, error: null });
        }
      })
      .catch(err => {
        if (!cancelled) {
          setFetchState({
            symbol,
            data: null,
            error: err?.message || "Impossible de charger les états financiers.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function handleRefresh() {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const res = await fetchFinanceStatements(symbol, true);
      setFetchState({ symbol, data: res, error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Impossible d'actualiser les états financiers.";
      setFetchState(prev => ({ ...prev, symbol, error: msg }));
    } finally {
      setRefreshing(false);
    }
  }

  const isLoading = fetchState.symbol !== symbol && !fetchState.error;
  const statements = fetchState.symbol === symbol ? fetchState.data : null;
  const error = fetchState.symbol === symbol ? fetchState.error : null;

  const period: StatementPeriod | null = useMemo(() => {
    if (!statements) return null;
    const raw = statements[granularity];
    if (depth === "all") return raw;
    const limit = Number(depth);
    if (!Number.isFinite(limit) || raw.dates.length <= limit) return raw;
    const startIdx = raw.dates.length - limit;
    return {
      dates: raw.dates.slice(startIdx),
      income: raw.income.map(r => ({ ...r, values: r.values.slice(startIdx) })),
      balance: raw.balance.map(r => ({ ...r, values: r.values.slice(startIdx) })),
      cashflow: raw.cashflow.map(r => ({ ...r, values: r.values.slice(startIdx) })),
      ratios: raw.ratios.map(r => ({ ...r, values: r.values.slice(startIdx) })),
    };
  }, [statements, granularity, depth]);

  const isYahooSource = statements?.source_provider === "yahoo_finance";
  const showEmptyRows = showEmptyOverride !== null ? showEmptyOverride : isYahooSource;

  const emptyRowsCount = useMemo(() => {
    if (!period) return 0;
    const all = [...period.income, ...period.balance, ...period.cashflow];
    return all.filter(r => r.values.every(v => v == null)).length;
  }, [period]);

  const filterRows = <T extends StatementRow>(rows: T[], respectEmptyFilter = true): T[] => {
    const q = searchTerm.trim().toLowerCase();
    return rows.filter(r => {
      if (respectEmptyFilter && !showEmptyRows && r.values.every(v => v == null)) return false;
      if (q && !r.label.toLowerCase().includes(q) && !r.key.toLowerCase().includes(q)) return false;
      return true;
    });
  };

  if (error) {
    return (
      <div className="finance-statements">
        <p className="text-rose">{error}</p>
        <button type="button" className="finance-tf-btn" onClick={() => void handleRefresh()}>
          Réessayer
        </button>
      </div>
    );
  }
  if (isLoading || !statements || !period) {
    return <p>Chargement de l’historique fondamental…</p>;
  }

  const displayCurrency = statements.currency || currency;
  const earningsHistory = statements.earnings_history || [];
  const amount = (_: StatementRow, v: number | null) => formatAmount(v);

  return (
    <div className="finance-statements">
      <div className="finance-statements-head">
        <div className="finance-statements-title-group">
          <strong>Historique fondamental ({displayCurrency})</strong>
          {statements.source_label && (
            <span className="finance-stmt-source-badge">
              {statements.source_label}
              {statements.cached ? " · Cache BDD" : " · Direct"}
            </span>
          )}
          {statements.updated_at && (
            <span className="finance-stmt-meta-date">
              Màj {new Date(statements.updated_at).toLocaleDateString("fr-FR")}
            </span>
          )}
        </div>

        <div className="finance-statements-controls">
          <div className="finance-timeframe-selector" role="group" aria-label="Périodicité">
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

          <div className="finance-timeframe-selector" role="group" aria-label="Profondeur historique">
            {(
              [
                ["5", "5 pér."],
                ["10", "10 pér."],
                ["all", "Tout l’historique"],
              ] as const
            ).map(([val, lbl]) => (
              <button
                key={val}
                type="button"
                className={`finance-tf-btn ${depth === val ? "active" : ""}`}
                onClick={() => setDepth(val)}
              >
                {lbl}
              </button>
            ))}
          </div>

          <button
            type="button"
            className={`finance-tf-btn ${showVarPct ? "active" : ""}`}
            onClick={() => setShowVarPct(prev => !prev)}
            title="Afficher la variation d'une période à l'autre (% YoY)"
          >
            % YoY
          </button>

          <button
            type="button"
            className="finance-tf-btn"
            onClick={() => setNewestFirst(prev => !prev)}
            title="Inverser l'ordre chronologique des colonnes"
          >
            {newestFirst ? "Récent → Ancien" : "Ancien → Récent"}
          </button>

          {emptyRowsCount > 0 && (
            <button
              type="button"
              className={`finance-tf-btn ${showEmptyRows ? "active" : ""}`}
              onClick={() => setShowEmptyOverride(!showEmptyRows)}
              title="Afficher ou masquer les postes sans valeur retournée par le fournisseur pour ce titre"
            >
              {showEmptyRows ? `Masquer vides (${emptyRowsCount})` : `+ Lignes vides (${emptyRowsCount})`}
            </button>
          )}

          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={refreshing}
            onClick={() => void handleRefresh()}
            title="Re-télécharger depuis EODHD / Yahoo Finance et mettre à jour la BDD"
          >
            <RefreshCw size={12} className={refreshing ? "spin" : ""} />
            <span>{refreshing ? "Sync…" : "Actualiser"}</span>
          </button>
        </div>
      </div>

      <div className="finance-stmt-filter-bar">
        <div className="finance-timeframe-selector">
          {(
            [
              ["all", "Tout"],
              ["ratios", "Ratios"],
              ["income", "Résultat"],
              ["balance", "Bilan"],
              ["cashflow", "Flux trésorerie"],
              ...(earningsHistory.length > 0 ? [["earnings", "BPA / Surprises"] as const] : []),
            ] as const
          ).map(([secKey, secLabel]) => (
            <button
              key={secKey}
              type="button"
              className={`finance-tf-btn ${section === secKey ? "active" : ""}`}
              onClick={() => setSection(secKey)}
            >
              {secLabel}
            </button>
          ))}
        </div>

        <label className="finance-stmt-search">
          <Search size={13} />
          <input
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Filtrer un poste (ex. marge, dette, FCF)…"
          />
        </label>
      </div>

      {period.dates.length === 0 && section !== "earnings" ? (
        <p>Aucune donnée {granularity === "annual" ? "annuelle" : "trimestrielle"} disponible.</p>
      ) : (
        <>
          {(section === "all" || section === "ratios") && (
            <StatementTable
              title="Indicateurs & ratios clés"
              rows={filterRows(period.ratios)}
              dates={period.dates}
              granularity={granularity}
              newestFirst={newestFirst}
              showVarPct={false}
              isRatio
              period={period}
              currency={currency}
              format={(row, v) => {
                if (v == null) return "—";
                const fmt = period.ratios.find(r => r.key === row.key)?.format;
                return fmt === "pct" ? `${v.toFixed(1)} %` : `${v.toFixed(2)}×`;
              }}
            />
          )}
          {(section === "all" || section === "income") && (
            <StatementTable
              title="Compte de résultat"
              rows={filterRows(period.income)}
              dates={period.dates}
              granularity={granularity}
              newestFirst={newestFirst}
              showVarPct={showVarPct}
              format={(r, v) =>
                (r.key === "DilutedEPS" || r.key === "BasicEPS") && v != null
                  ? v.toFixed(2)
                  : amount(r, v)
              }
            />
          )}
          {(section === "all" || section === "balance") && (
            <StatementTable
              title="Bilan"
              rows={filterRows(period.balance)}
              dates={period.dates}
              granularity={granularity}
              newestFirst={newestFirst}
              showVarPct={showVarPct}
              period={period}
              currency={currency}
              format={amount}
            />
          )}
          {(section === "all" || section === "cashflow") && (
            <StatementTable
              title="Flux de trésorerie"
              rows={filterRows(period.cashflow)}
              dates={period.dates}
              granularity={granularity}
              newestFirst={newestFirst}
              showVarPct={showVarPct}
              period={period}
              currency={currency}
              format={amount}
            />
          )}
          {(section === "all" || section === "earnings") && (
            <EarningsHistoryTable rows={earningsHistory} />
          )}
        </>
      )}
    </div>
  );
}
