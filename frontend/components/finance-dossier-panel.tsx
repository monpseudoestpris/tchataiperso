"use client";

import {
  Award,
  BarChart2,
  BookOpen,
  ExternalLink,
  FileSpreadsheet,
  History,
  Layers,
  Newspaper,
  RefreshCw,
  Scale,
  Sparkles,
  Trash2,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { type FinanceHelpGuideId } from "@/components/finance-help-modal";
import { FinanceMetricLabel } from "@/components/finance-info-tip";
import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  buildAnnualRatioCalc,
  buildCapitalMetricCalc,
  buildCostOfCapitalCalc,
  buildIntrinsicMethodCalc,
  buildIntrinsicSummaryCalc,
  buildQualitativeScoreCalc,
  buildRiskMetricCalc,
  buildUncleStockScoreCalc,
} from "@/lib/finance-calc-details";
import {
  analyzeFinanceDossier,
  deleteFinanceAiHistoryItem,
  fetchFinanceDossier,
  type DossierMetricRow,
  type FinanceAiAnalysisRecord,
  type FinancialDossier,
  type IntrinsicValuationPayload,
  type StatementPeriod,
  type StatementRow,
  type UncleStockScoreItem,
  type UncleStockScoresPayload,
} from "@/lib/api";

type DepthMode = "5" | "10" | "all";
type DossierSubTab = "synthese" | "scores" | "intrinsic" | "ratios" | "stakeholders" | "statements" | "news" | "all";

const MONTHS_FR = ["Jan.", "Fév.", "Mar.", "Avr.", "Mai", "Juin", "Jui.", "Août", "Sept.", "Oct.", "Nov.", "Déc."];

function fmtMln(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const mln = v / 1e6;
  return Math.round(mln).toLocaleString("fr-FR");
}

function fmtCell(v: number | null | undefined, fmt: string): string {
  if (v == null || !Number.isFinite(v)) return "—";
  switch (fmt) {
    case "amount":
      return fmtMln(v);
    case "shares":
      return (v / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
    case "pct":
      return `${v.toFixed(1)}%`;
    case "x":
      return v.toFixed(1);
    case "days":
      return `${Math.round(v)}`;
    default:
      return v.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
  }
}

function fmtNum(v: number | null | undefined, digits = 1, suffix = ""): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v.toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })}${suffix}`;
}

function fmtBigCap(v: number | null | undefined, currency: string): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const m = Math.round(v / 1e6).toLocaleString("fr-FR");
  return `${m} M${currency}`;
}

function fmtInt(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return Math.round(v).toLocaleString("fr-FR");
}

function PerformanceSvgChart({
  series,
}: {
  series: { date: string; price: number; adj_price: number; index_100: number }[];
}) {
  if (series.length < 2) return null;
  const w = 780;
  const h = 190;
  const padX = 46;
  const padY = 18;
  const vals = series.map(s => s.index_100);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const pts = series.map((s, i) => {
    const x = padX + (i / Math.max(1, series.length - 1)) * (w - padX * 2);
    const y = h - padY - ((s.index_100 - min) / span) * (h - padY * 2);
    return { x, y, s };
  });
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const area = `${d} L${pts[pts.length - 1].x.toFixed(1)},${h - padY} L${pts[0].x.toFixed(1)},${h - padY} Z`;
  const isUp = vals[vals.length - 1] >= vals[0];
  const stroke = isUp ? "#10b981" : "#f43f5e";
  const firstPct = ((vals[vals.length - 1] / 100 - 1) * 100).toFixed(1);

  return (
    <div className="finance-dossier-perf-chart">
      <div className="finance-dossier-perf-chart-head">
        <span>Évolution base 100 (ajustée des dividendes · {series[0].date} → {series[series.length - 1].date})</span>
        <strong className={isUp ? "text-emerald" : "text-rose"}>
          {Number(firstPct) >= 0 ? "+" : ""}
          {firstPct}% sur la période
        </strong>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="finance-dossier-perf-svg" role="img" aria-label="Performance ajustée des dividendes">
        <defs>
          <linearGradient id="dossierPerfFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#dossierPerfFill)" />
        <path d={d} fill="none" stroke={stroke} strokeWidth={2.2} strokeLinejoin="round" />
        <text x={8} y={padY + 4} className="finance-dossier-svg-label">
          {Math.round(max)}
        </text>
        <text x={8} y={h - padY} className="finance-dossier-svg-label">
          {Math.round(min)}
        </text>
      </svg>
    </div>
  );
}

function AnnualMatrixTable({
  id,
  title,
  years,
  rows,
  unitNote,
  dossier,
}: {
  id?: string;
  title: string;
  years: string[];
  rows: DossierMetricRow[];
  unitNote?: string;
  dossier?: FinancialDossier;
}) {
  if (years.length === 0 || rows.length === 0) return null;
  const visibleRows = rows.filter(r => r.values.some(v => v != null));
  if (visibleRows.length === 0) return null;

  return (
    <section id={id} className="finance-dossier-section">
      <div className="finance-dossier-sec-head">
        <h4>{title}</h4>
        {unitNote && <small className="finance-dossier-unit">{unitNote}</small>}
      </div>
      <div className="finance-table-wrapper finance-stmt-scroll">
        <table className="finance-data-table finance-stmt-table">
          <thead>
            <tr>
              <th className="finance-stmt-sticky-col">Indicateur</th>
              {years.map((y, idx) => (
                <th key={`v-${idx}-${y}`}>{y}</th>
              ))}
              {years.slice(1).map((y, idx) => (
                <th key={`yoy-${idx}-${y}`} className="finance-dossier-yoy-head">
                  {years[idx].slice(-2)}-{y.slice(-2)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map(row => (
              <tr key={row.key}>
                <td className="finance-stmt-sticky-col">
                  <FinanceMetricLabel
                    termKey={row.key}
                    label={row.label}
                    calcDetail={dossier ? buildAnnualRatioCalc(row, dossier) : undefined}
                    strong
                  />
                </td>
                {row.values.map((v, i) => (
                  <td key={`${row.key}-v-${i}-${years[i]}`} className={v != null && v < 0 ? "text-rose" : undefined}>
                    {fmtCell(v, row.format)}
                  </td>
                ))}
                {row.yoy.slice(1).map((pct, i) => (
                  <td
                    key={`${row.key}-y-${i}-${years[i + 1]}`}
                    className={
                      pct == null
                        ? "finance-stmt-muted"
                        : pct >= 0
                          ? "text-emerald finance-dossier-yoy-cell"
                          : "text-rose finance-dossier-yoy-cell"
                    }
                  >
                    {pct == null ? "—" : `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Fiche complète de type institutionnel (Synthèse, Capital, Risque, Scores, Parties prenantes, Dividendes, Comptes). */
export function FinanceDossierPanel({
  symbol,
  onInsertIntoChat,
  onOpenHelp,
}: {
  symbol: string;
  onInsertIntoChat?: (text: string) => void;
  onOpenHelp?: (guide?: FinanceHelpGuideId) => void;
}) {
  const [state, setState] = useState<{ symbol: string; data: FinancialDossier | null; error: string | null }>({
    symbol: "",
    data: null,
    error: null,
  });
  const [refreshing, setRefreshing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [selectedAiId, setSelectedAiId] = useState<string | null>(null);
  const [depth, setDepth] = useState<DepthMode>("5");
  const [subTab, setSubTab] = useState<DossierSubTab>("synthese");
  const [holdersTab, setHoldersTab] = useState<"funds" | "institutions">("funds");

  useEffect(() => {
    let cancelled = false;
    fetchFinanceDossier(symbol, false)
      .then(res => {
        if (!cancelled) {
          setAiError(null);
          setSelectedAiId(null);
          setState({ symbol, data: res, error: null });
        }
      })
      .catch(err => {
        if (!cancelled) setState({ symbol, data: null, error: err?.message || "Impossible de charger la fiche complète." });
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function handleRefresh() {
    if (refreshing) return;
    setRefreshing(true);
    try {
      const res = await fetchFinanceDossier(symbol, true);
      setState({ symbol, data: res, error: null });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Erreur lors du rafraîchissement.";
      setState(prev => ({ ...prev, symbol, error: msg }));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleGenerateAi() {
    if (analyzing || !dossier) return;
    setAnalyzing(true);
    setAiError(null);
    try {
      const res = await analyzeFinanceDossier(dossier.symbol);
      setState(prev =>
        prev.data
          ? {
              ...prev,
              data: {
                ...prev.data,
                ai_analysis: res,
                ai_history: [res, ...(prev.data.ai_history || []).filter(h => h.id !== res.id)],
              },
            }
          : prev,
      );
      if (res.id) setSelectedAiId(res.id);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Impossible de générer l'analyse IA.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleDeleteDossierAi(entry: FinanceAiAnalysisRecord) {
    if (!entry.id) return;
    try {
      await deleteFinanceAiHistoryItem(entry.id);
      setState(prev => {
        if (!prev.data) return prev;
        const nextHist = (prev.data.ai_history || []).filter(h => h.id !== entry.id);
        return {
          ...prev,
          data: {
            ...prev.data,
            ai_history: nextHist,
            ai_analysis: nextHist[0] ?? null,
          },
        };
      });
      if (selectedAiId === entry.id) setSelectedAiId(null);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  const loading = state.symbol !== symbol && !state.error;
  const dossier = state.symbol === symbol ? state.data : null;
  const error = state.symbol === symbol ? state.error : null;

  const slicedAnnual = useMemo(() => {
    if (!dossier) return null;
    const tbl = dossier.annual_tables;
    const total = tbl.years.length;
    const limit = depth === "all" ? total : Math.min(total, Number(depth));
    const start = Math.max(0, total - limit);
    const sliceRows = (rows: DossierMetricRow[]) =>
      rows.map(r => ({
        ...r,
        values: r.values.slice(start),
        yoy: r.yoy.slice(start),
      }));
    return {
      years: tbl.years.slice(start),
      summary: sliceRows(tbl.summary),
      profitability: sliceRows(tbl.profitability),
      solvency: sliceRows(tbl.solvency),
      distribution: sliceRows(tbl.distribution),
      efficiency: sliceRows(tbl.efficiency),
      ih_score: {
        ...tbl.ih_score,
        years: tbl.ih_score.years.slice(start),
        criteria: tbl.ih_score.criteria.map(c => ({ ...c, values: c.values.slice(start) })),
        trend_criteria: tbl.ih_score.trend_criteria.map(c => ({ ...c, values: c.values.slice(start) })),
      },
      piotroski: {
        ...tbl.piotroski,
        years: tbl.piotroski.years.slice(start),
        criteria: tbl.piotroski.criteria.map(c => ({ ...c, values: c.values.slice(start) })),
        scores: tbl.piotroski.scores.slice(start),
      },
      altman: {
        ...tbl.altman,
        years: tbl.altman.years.slice(start),
        criteria: tbl.altman.criteria.map(c => ({ ...c, values: c.values.slice(start) })),
        scores: tbl.altman.scores.slice(start),
      },
    };
  }, [dossier, depth]);

  if (error) {
    return (
      <div className="finance-dossier">
        <p className="text-rose">{error}</p>
        <button type="button" className="finance-tf-btn" onClick={() => void handleRefresh()}>
          Réessayer
        </button>
      </div>
    );
  }
  if (loading || !dossier || !slicedAnnual) {
    return <p>Chargement et calcul du dossier complet (historique 10 ans, ratios, risques, scores)…</p>;
  }

  const hdr = dossier.header;
  const cap = dossier.capital_valuation;
  const stk = dossier.stakeholders;
  const an = stk.analysts;
  const unitLabel = `(en Mlns ${dossier.currency})`;
  const show = (tab: DossierSubTab) => subTab === "all" || subTab === tab;

  const usSummary = dossier.uncle_stock_scores?.summary;
  const usBadge =
    usSummary?.uncle_stock_score_verified != null
      ? `${usSummary.uncle_stock_score_verified.toFixed(0)}%`
      : null;
  const ivMos = dossier.intrinsic_valuation?.summary?.corrected?.margin_of_safety_pct;
  const ivBadge = ivMos != null ? `${ivMos >= 0 ? "+" : ""}${ivMos.toFixed(0)}%` : null;
  const newsCount = dossier.news?.items?.length ?? 0;

  return (
    <div className="finance-dossier">
      {/* Barre supérieure : source, profondeur & sommaire rapide */}
      <div className="finance-dossier-topbar">
        <div className="finance-dossier-topbar-left">
          {hdr.logo_url && /^https:\/\//i.test(hdr.logo_url) && (
            <img
              src={hdr.logo_url}
              alt={hdr.name}
              className="finance-dossier-logo"
              onError={e => {
                e.currentTarget.style.display = "none";
              }}
            />
          )}
          <span className="finance-stmt-source-badge">{dossier.source_label}</span>
          {dossier.warehouse_stats && (
            <span className="finance-stmt-meta-date">
              BDD : {dossier.warehouse_stats.eod_bars_count || 0} séances ·{" "}
              {dossier.warehouse_stats.annual_periods_count || 0} exercices
            </span>
          )}
        </div>
        <div className="finance-dossier-topbar-right">
          <div className="finance-timeframe-selector">
            {(
              [
                ["5", "5 ans"],
                ["10", "10 ans"],
                ["all", "Tout"],
              ] as const
            ).map(([k, lbl]) => (
              <button
                key={k}
                type="button"
                className={`finance-tf-btn ${depth === k ? "active" : ""}`}
                onClick={() => setDepth(k)}
              >
                {lbl}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="finance-tf-btn finance-stmt-refresh-btn"
            disabled={refreshing}
            onClick={() => void handleRefresh()}
          >
            <RefreshCw size={12} className={refreshing ? "spin" : ""} />
            <span>{refreshing ? "Sync…" : "Actualiser"}</span>
          </button>
        </div>
      </div>

      {/* Sommaire complet (visible en vue "Tout voir") */}
      {subTab === "all" && (
        <nav
          className="finance-dossier-toc-grid"
          aria-label="Sommaire du dossier"
          onClick={e => {
            const anchor = (e.target as HTMLElement).closest("a[href^='#']") as HTMLAnchorElement | null;
            const targetId = anchor?.getAttribute("href")?.slice(1);
            if (!targetId) return;
            const el = document.getElementById(targetId);
            if (el) {
              e.preventDefault();
              el.scrollIntoView({ behavior: "smooth", block: "start" });
            }
          }}
        >
          <div className="finance-dossier-toc-col">
            <strong>Synthèse boursière</strong>
            <a href="#dossier-analyse">Analyse IA (tous résultats)</a>
            <a href="#dossier-news">Actualités &amp; Sentiment</a>
            <a href="#dossier-capital">Capital &amp; Valorisation</a>
            <a href="#dossier-intrinsic">Valeurs intrinsèques</a>
            <a href="#dossier-macro">Macro &amp; Taux US</a>
            <a href="#dossier-perf">Performance boursière</a>
            <a href="#dossier-risque">Gestion du risque</a>
            <a href="#dossier-dividendes">Historique de dividendes</a>
            <a href="#dossier-fondamentaux">Fondamentaux synthèse</a>
          </div>
          <div className="finance-dossier-toc-col">
            <strong>Parties prenantes</strong>
            <a href="#dossier-analystes">Consensus des analystes</a>
            <a href="#dossier-direction">Équipe de direction</a>
            <a href="#dossier-inities">Opérations d’initiés</a>
            <a href="#dossier-fonds">Top fonds &amp; institutionnels</a>
          </div>
          <div className="finance-dossier-toc-col">
            <strong>Ratios financiers</strong>
            <a href="#dossier-profitabilite">Profitabilité</a>
            <a href="#dossier-solvabilite">Ratios de solvabilité</a>
            <a href="#dossier-distribution">Ratios de distribution</a>
            <a href="#dossier-efficacite">Ratios d’efficacité</a>
          </div>
          <div className="finance-dossier-toc-col">
            <strong>Scores qualitatifs</strong>
            <a href="#dossier-unclestock-scores">Scores Uncle Stock (31)</a>
            <a href="#dossier-ihscore">IH Score</a>
            <a href="#dossier-piotroski">F-Score Piotroski</a>
            <a href="#dossier-altman">Z-Score Altman</a>
          </div>
          <div className="finance-dossier-toc-col">
            <strong>Comptes détaillés</strong>
            <a href="#dossier-comptes-annuels">Comptes annuels</a>
            <a href="#dossier-comptes-trimestriels">Comptes trimestriels</a>
            <a href="#dossier-calendrier">Calendrier résultats</a>
            <a href="#dossier-bpa">Publications BPA</a>
          </div>
        </nav>
      )}

      {/* En-tête fiche valeur */}
      <div className="finance-dossier-header-grid">
        <div className="finance-dossier-kpi-chip">
          <FinanceMetricLabel termKey="market_cap" label={hdr.cap_category} />
          <strong>{fmtBigCap(hdr.market_cap, dossier.currency)}</strong>
        </div>
        <div className="finance-dossier-kpi-chip">
          <FinanceMetricLabel termKey="dividend_yield" label="Rendement" />
          <strong>{hdr.dividend_yield_pct != null ? `${hdr.dividend_yield_pct.toFixed(1)}%` : "—"}</strong>
        </div>
        <div className="finance-dossier-kpi-chip">
          <FinanceMetricLabel termKey="beta" label="Bêta" />
          <strong>{hdr.beta != null ? hdr.beta.toFixed(2) : "—"}</strong>
        </div>
        <div className="finance-dossier-kpi-chip is-score">
          <FinanceMetricLabel termKey="ih_score" label="IH Score" />
          <strong>
            {hdr.ih_score != null ? `${hdr.ih_quality || ""} (${hdr.ih_score.toFixed(1)}/9)` : "—"}{" "}
            <small>
              {hdr.ih_trend === "Haussière" ? "↗" : hdr.ih_trend === "Baissière" ? "↘" : "→"} {hdr.ih_trend}
            </small>
          </strong>
        </div>
        <div className="finance-dossier-kpi-chip">
          <FinanceMetricLabel termKey="price_dynamics" label="Dynamique du cours" />
          <strong className={hdr.price_dynamics.startsWith("Positif") ? "text-emerald" : hdr.price_dynamics.startsWith("Négatif") ? "text-rose" : undefined}>
            {hdr.price_dynamics}
          </strong>
        </div>
        <div className="finance-dossier-kpi-chip">
          <span>Secteur / Industrie</span>
          <strong>
            {hdr.sector || "N/A"} · {hdr.industry || "N/A"}
          </strong>
        </div>
        <div className="finance-dossier-kpi-chip">
          <span>Effectif</span>
          <strong>{fmtInt(hdr.employees)}</strong>
        </div>
        <div className="finance-dossier-kpi-chip">
          <span>Siège &amp; Site</span>
          <strong>
            {hdr.website ? (
              <a href={hdr.website} target="_blank" rel="noreferrer" className="site-link">
                Site officiel <ExternalLink size={11} />
              </a>
            ) : (
              "—"
            )}
          </strong>
          {hdr.address && <small>{hdr.address}</small>}
        </div>
      </div>

      {/* Navigation par sous-onglets de la fiche institutionnelle */}
      <div className="finance-dossier-subtabs" role="tablist" aria-label="Sections de la fiche complète">
        {(
          [
            { id: "synthese", label: "Synthèse & IA", icon: <Sparkles size={14} />, badge: null },
            { id: "scores", label: "Scores (31)", icon: <Award size={14} />, badge: usBadge },
            { id: "intrinsic", label: "Valeurs Intrinsèques", icon: <Scale size={14} />, badge: ivBadge },
            { id: "ratios", label: "Ratios", icon: <BarChart2 size={14} />, badge: null },
            { id: "stakeholders", label: "Parties & Divid.", icon: <Users size={14} />, badge: null },
            { id: "statements", label: "Comptes & BPA", icon: <FileSpreadsheet size={14} />, badge: null },
            { id: "news", label: "Actus & Macro", icon: <Newspaper size={14} />, badge: newsCount > 0 ? String(newsCount) : null },
            { id: "all", label: "Tout voir", icon: <Layers size={14} />, badge: null },
          ] as { id: DossierSubTab; label: string; icon: React.ReactNode; badge: string | null }[]
        ).map(item => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={subTab === item.id}
            className={`finance-dossier-subtab-btn ${subTab === item.id ? "active" : ""}`}
            onClick={() => setSubTab(item.id)}
          >
            {item.icon}
            <span>{item.label}</span>
            {item.badge && <span className="finance-dossier-subtab-badge">{item.badge}</span>}
          </button>
        ))}
      </div>

      {/* Profil & Composition dédiés aux fonds / OPCVM (EUFUND) */}
      {show("synthese") && dossier.fund_profile && (
        <section id="dossier-fund-profile" className="finance-dossier-section">
          <div className="finance-dossier-sec-head">
            <h4>Profil &amp; Composition du fonds ({dossier.fund_profile.exchange})</h4>
            {dossier.fund_profile.isin && (
              <small className="finance-dossier-unit">ISIN : {dossier.fund_profile.isin}</small>
            )}
          </div>
          <div className="finance-fund-profile-grid">
            <div className="finance-dossier-kpi-chip">
              <span>Société de gestion</span>
              <strong>{dossier.fund_profile.fund_family || "—"}</strong>
            </div>
            <div className="finance-dossier-kpi-chip">
              <span>Catégorie</span>
              <strong>{dossier.fund_profile.category || dossier.fund_profile.fund_type || "—"}</strong>
            </div>
            <div className="finance-dossier-kpi-chip">
              <span>Frais de gestion</span>
              <strong>
                {dossier.fund_profile.expense_ratio_pct != null
                  ? `${dossier.fund_profile.expense_ratio_pct.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
            <div className="finance-dossier-kpi-chip">
              <span>Encours / Actif net</span>
              <strong>
                {fmtBigCap(dossier.fund_profile.net_assets, dossier.fund_profile.currency || dossier.currency)}
              </strong>
            </div>
            <div className="finance-dossier-kpi-chip">
              <span>Création / Pays</span>
              <strong>
                {[dossier.fund_profile.inception_date, dossier.fund_profile.country].filter(Boolean).join(" · ") || "—"}
              </strong>
            </div>
            {dossier.fund_profile.morningstar_rating != null && (
              <div className="finance-dossier-kpi-chip">
                <span>Note Morningstar</span>
                <strong>{"★".repeat(Math.max(1, Math.min(5, Math.round(dossier.fund_profile.morningstar_rating))))}</strong>
              </div>
            )}
          </div>
          {(dossier.fund_profile.asset_allocation.length > 0 ||
            dossier.fund_profile.sector_weights.length > 0 ||
            dossier.fund_profile.world_regions.length > 0 ||
            dossier.fund_profile.top_holdings.length > 0) && (
            <div className="finance-fund-breakdowns">
              {dossier.fund_profile.asset_allocation.length > 0 && (
                <div className="finance-fund-breakdown-card">
                  <strong>Allocation d&apos;actifs</strong>
                  <ul>
                    {dossier.fund_profile.asset_allocation.map(a => (
                      <li key={a.name}>
                        <span>{a.name}</span>
                        <strong>{a.weight_pct != null ? `${a.weight_pct.toFixed(2)}%` : "—"}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {dossier.fund_profile.sector_weights.length > 0 && (
                <div className="finance-fund-breakdown-card">
                  <strong>Répartition sectorielle</strong>
                  <ul>
                    {dossier.fund_profile.sector_weights.map(s => (
                      <li key={s.name}>
                        <span>{s.name}</span>
                        <strong>{s.weight_pct != null ? `${s.weight_pct.toFixed(2)}%` : "—"}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {dossier.fund_profile.world_regions.length > 0 && (
                <div className="finance-fund-breakdown-card">
                  <strong>Zones géographiques</strong>
                  <ul>
                    {dossier.fund_profile.world_regions.map(w => (
                      <li key={w.name}>
                        <span>{w.name}</span>
                        <strong>{w.weight_pct != null ? `${w.weight_pct.toFixed(2)}%` : "—"}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {dossier.fund_profile.top_holdings.length > 0 && (
                <div className="finance-fund-breakdown-card">
                  <strong>Principales lignes</strong>
                  <ul>
                    {dossier.fund_profile.top_holdings.map(h => (
                      <li key={`${h.code || ""}-${h.name}`}>
                        <span>{h.name}</span>
                        <strong>{h.weight_pct != null ? `${h.weight_pct.toFixed(2)}%` : "—"}</strong>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Analyse fondamentale narrative (tous résultats via Gemini Hydrogen) */}
      {show("synthese") && (() => {
        const aiHistoryList: FinanceAiAnalysisRecord[] =
          dossier.ai_history && dossier.ai_history.length > 0
            ? dossier.ai_history
            : dossier.ai_analysis
              ? [dossier.ai_analysis]
              : [];
        const currentAi =
          (selectedAiId ? aiHistoryList.find(h => h.id === selectedAiId) : undefined) ??
          aiHistoryList[0] ??
          dossier.ai_analysis;
        return (
          <section id="dossier-analyse" className="finance-dossier-section finance-dossier-ai-box">
            <div className="finance-dossier-sec-head">
              <h4>Analyse fondamentale IA de {hdr.name} : synthèse complète</h4>
              <div className="finance-dossier-ai-actions">
                <button
                  type="button"
                  className="finance-tf-btn active finance-stmt-refresh-btn"
                  disabled={analyzing}
                  onClick={() => void handleGenerateAi()}
                >
                  <Sparkles size={12} />
                  <span>
                    {analyzing
                      ? "Analyse Gemini Hydrogen en cours…"
                      : currentAi
                        ? "Nouvelle analyse datée (Gemini Hydrogen)"
                        : "Analyser tous les résultats (Gemini Hydrogen)"}
                  </span>
                </button>
              </div>
            </div>

            {aiError && <p className="text-rose">{aiError}</p>}

            {aiHistoryList.length > 0 && (
              <div className="finance-ai-history-strip" aria-label="Historique des analyses IA du dossier">
                <span className="finance-ai-history-label">
                  <History size={12} />
                  <span>Historique daté ({aiHistoryList.length}) :</span>
                </span>
                <div className="finance-ai-history-pills">
                  {aiHistoryList.map((item, idx) => {
                    const isCurrent = currentAi?.id ? currentAi.id === item.id : idx === 0;
                    const dtIso = item.created_at || item.updated_at;
                    const dtLabel = dtIso
                      ? new Date(dtIso).toLocaleString("fr-FR", {
                          day: "2-digit",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : `Analyse #${idx + 1}`;
                    return (
                      <div key={item.id || `${idx}-${dtIso}`} className={`finance-ai-hist-chip ${isCurrent ? "active" : ""}`}>
                        <button
                          type="button"
                          className="finance-ai-hist-chip-btn"
                          onClick={() => setSelectedAiId(item.id || null)}
                        >
                          <strong>{dtLabel}</strong>
                          {item.verdict && <span className="finance-ai-hist-verdict">{item.verdict}</span>}
                          {item.model && <small>{item.model.split("/").pop()}</small>}
                        </button>
                        {item.id && (
                          <button
                            type="button"
                            className="finance-ai-hist-del"
                            onClick={() => void handleDeleteDossierAi(item)}
                            title="Supprimer cette analyse archivée"
                            aria-label="Supprimer cette analyse"
                          >
                            <Trash2 size={10} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {currentAi?.markdown ? (
              <FinanceRichReport
                contentHtml={currentAi.content_html}
                markdown={currentAi.markdown}
                onInsertIntoChat={onInsertIntoChat}
                meta={{
                  title: `Synthèse Fondamentale IA — ${hdr.name}`,
                  subtitle: "Analyse institutionnelle complète multi-exercices",
                  symbol: dossier.symbol,
                  model: currentAi.model,
                  createdAt: currentAi.created_at || currentAi.updated_at,
                  accent: "#4f46e5",
                  badgeLabel: "Analyse Dossier IA",
                }}
              />
            ) : (
              <p className="finance-dossier-ai-placeholder">
                {hdr.description ? `${hdr.description} — ` : ""}
                Cliquez sur « Analyser tous les résultats (Gemini Hydrogen) » pour obtenir une synthèse complète sauvegardée en HTML coloré couvrant valorisation, performances, risques, rentabilité, solidité, scores (IH, Piotroski, Altman) et gouvernance.
              </p>
            )}
          </section>
        );
      })()}

      {/* Actualités & sentiment */}
      {show("news") && (
      <section id="dossier-news" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>
            <Newspaper size={14} style={{ display: "inline", marginRight: 6, verticalAlign: "-2px" }} />
            Actualités &amp; Sentiment
          </h4>
          {dossier.news?.source && (
            <small className="finance-dossier-unit">Source : {dossier.news.source}</small>
          )}
        </div>
        {dossier.news?.sentiment_summary && (
          <div className="finance-dossier-sentiment-strip">
            <div>
              <FinanceMetricLabel termKey="sentiment_90j" label="Sentiment moyen (90j)" />
              <strong
                className={
                  dossier.news.sentiment_summary.avg_normalized >= 0.1
                    ? "text-emerald"
                    : dossier.news.sentiment_summary.avg_normalized <= -0.1
                      ? "text-rose"
                      : undefined
                }
              >
                {dossier.news.sentiment_summary.avg_normalized >= 0 ? "+" : ""}
                {dossier.news.sentiment_summary.avg_normalized.toFixed(3)}
              </strong>
            </div>
            <div>
              <span>Dernier score ({dossier.news.sentiment_summary.latest_date})</span>
              <strong>
                {dossier.news.sentiment_summary.latest_normalized >= 0 ? "+" : ""}
                {dossier.news.sentiment_summary.latest_normalized.toFixed(3)}
              </strong>
            </div>
            <div>
              <span>Volume médiatique</span>
              <strong>
                {dossier.news.sentiment_summary.article_count} articles ·{" "}
                {dossier.news.sentiment_summary.days_covered} jours
              </strong>
            </div>
          </div>
        )}
        {dossier.news && dossier.news.items.length > 0 ? (
          <div className="finance-dossier-news-list">
            {dossier.news.items.map((item, idx) => {
              const safeUrl = /^https?:\/\//i.test(item.url) ? item.url : "";
              const pol = item.sentiment?.polarity;
              const sentLabel =
                pol == null ? null : pol >= 0.15 ? "Positif" : pol <= -0.15 ? "Négatif" : "Neutre";
              const sentCls =
                pol == null ? "" : pol >= 0.15 ? "is-pos" : pol <= -0.15 ? "is-neg" : "is-neu";
              return (
                <article key={`${idx}-${item.url}`} className="finance-dossier-news-card">
                  <div className="finance-dossier-news-head">
                    {safeUrl ? (
                      <a href={safeUrl} target="_blank" rel="noopener noreferrer">
                        {item.title} <ExternalLink size={11} />
                      </a>
                    ) : (
                      <strong>{item.title}</strong>
                    )}
                    {sentLabel && (
                      <span className={`finance-dossier-sentiment-badge ${sentCls}`}>
                        {sentLabel} ({pol! >= 0 ? "+" : ""}{pol!.toFixed(2)})
                      </span>
                    )}
                  </div>
                  <div className="finance-dossier-news-meta">
                    <span>{item.source}</span>
                    {item.published_at && <span>· {item.published_at}</span>}
                    {item.tags && item.tags.length > 0 && (
                      <span className="finance-dossier-news-tags">
                        {item.tags.slice(0, 3).map(t => (
                          <code key={t}>{t}</code>
                        ))}
                      </span>
                    )}
                  </div>
                  {item.snippet && <p className="finance-dossier-news-snippet">{item.snippet}</p>}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="finance-dossier-ai-placeholder">
            Aucune actualité récente remontée pour {dossier.symbol}.
          </p>
        )}
      </section>
      )}

      {/* Capital, valorisation et momentum */}
      {show("synthese") && (
      <section id="dossier-capital" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>Capital, valorisation et momentum</h4>
        </div>
        <div className="finance-dossier-grids-stack">
          <div className="finance-dossier-6grid">
            <div><FinanceMetricLabel termKey="shares_outstanding" label="Nbr d’actions" calcDetail={buildCapitalMetricCalc("shares_outstanding", dossier)} /><strong>{fmtInt(cap.shares_outstanding)}</strong></div>
            <div><FinanceMetricLabel termKey="float_pct" label="Flottant" calcDetail={buildCapitalMetricCalc("float_pct", dossier)} /><strong>{fmtNum(cap.float_pct, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="insiders_pct" label="Initiés" /><strong>{fmtNum(cap.insiders_pct, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="institutions_pct" label="Institutionnels" /><strong>{fmtNum(cap.institutions_pct, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="short_ratio" label="Short Ratio" /><strong>{fmtNum(cap.short_ratio, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="short_pct_float" label="Flottant en VAD" /><strong>{fmtNum(cap.short_pct_float, 1, "%")}</strong></div>
          </div>
          <div className="finance-dossier-6grid">
            <div><FinanceMetricLabel termKey="pe_ttm" label="PER TTM" calcDetail={buildCapitalMetricCalc("pe_ttm", dossier)} /><strong>{fmtNum(cap.pe_ttm, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="pe_forward" label="PER prévi." calcDetail={buildCapitalMetricCalc("pe_forward", dossier)} /><strong>{fmtNum(cap.pe_forward, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="peg" label="PEG" calcDetail={buildCapitalMetricCalc("peg", dossier)} /><strong>{fmtNum(cap.peg, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="pb" label="P/B" calcDetail={buildCapitalMetricCalc("pb", dossier)} /><strong>{fmtNum(cap.pb, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="ev_ebitda" label="VE/EBITDA TTM" calcDetail={buildCapitalMetricCalc("ev_ebitda", dossier)} /><strong>{fmtNum(cap.ev_ebitda, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="ev_revenue" label="VE/CA TTM" calcDetail={buildCapitalMetricCalc("ev_revenue", dossier)} /><strong>{fmtNum(cap.ev_revenue, 1)}</strong></div>
          </div>
          <div className="finance-dossier-6grid">
            <div><FinanceMetricLabel termKey="op_m" label="Marge opé. TTM" calcDetail={buildCapitalMetricCalc("op_margin_ttm", dossier)} /><strong>{fmtNum(cap.op_margin_ttm, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="net_m" label="Marge nette TTM" calcDetail={buildCapitalMetricCalc("net_margin_ttm", dossier)} /><strong>{fmtNum(cap.net_margin_ttm, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="roe" label="ROE TTM" calcDetail={buildCapitalMetricCalc("roe_ttm", dossier)} /><strong>{fmtNum(cap.roe_ttm, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="roa" label="ROA TTM" calcDetail={buildCapitalMetricCalc("roa_ttm", dossier)} /><strong>{fmtNum(cap.roa_ttm, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="rev_growth" label="Δ CA trim. YoY" /><strong>{fmtNum(cap.rev_growth_q_yoy, 1, "%")}</strong></div>
            <div><FinanceMetricLabel termKey="eps" label="Δ RN trim. YoY" /><strong>{fmtNum(cap.eps_growth_q_yoy, 1, "%")}</strong></div>
          </div>
          <div className="finance-dossier-6grid">
            <div><span>Cours</span><strong>{fmtNum(cap.price, 2, ` ${dossier.currency}`)}</strong></div>
            <div><FinanceMetricLabel termKey="target_price" label="Cible" calcDetail={buildCapitalMetricCalc("target_price", dossier)} /><strong>{fmtNum(cap.target_price, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="mma50" label="MMA50" calcDetail={buildCapitalMetricCalc("mma50", dossier)} /><strong>{fmtNum(cap.mma50, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="mma200" label="MMA200" calcDetail={buildCapitalMetricCalc("mma200", dossier)} /><strong>{fmtNum(cap.mma200, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="w52_range" label="+ bas 52 s." /><strong>{fmtNum(cap.low_52w, 1)}</strong></div>
            <div><FinanceMetricLabel termKey="w52_range" label="+ haut 52 s." /><strong>{fmtNum(cap.high_52w, 1)}</strong></div>
          </div>
          {dossier.historical_market_cap && (
            <div className="finance-dossier-6grid">
              <div>
                <span>Cap. actuelle ({dossier.historical_market_cap.latest_date})</span>
                <strong>{fmtBigCap(dossier.historical_market_cap.latest_value, dossier.currency)}</strong>
              </div>
              <div>
                <span>Cap. min (hist.)</span>
                <strong>{fmtBigCap(dossier.historical_market_cap.min_value, dossier.currency)}</strong>
              </div>
              <div>
                <span>Cap. max (hist.)</span>
                <strong>{fmtBigCap(dossier.historical_market_cap.max_value, dossier.currency)}</strong>
              </div>
              <div>
                <span>Points hist.</span>
                <strong>{dossier.historical_market_cap.points.length}</strong>
              </div>
            </div>
          )}
        </div>
      </section>
      )}

      {show("news") && dossier.macro_context && (
        <section id="dossier-macro" className="finance-dossier-section">
          <div className="finance-dossier-sec-head">
            <h4>Contexte macroéconomique &amp; Taux ({dossier.macro_context.country_name})</h4>
            <small className="finance-dossier-unit">EODHD Macro &amp; US Treasury</small>
          </div>
          <div className="finance-dossier-6grid">
            <div>
              <FinanceMetricLabel termKey="gdp_growth" label={`Croissance PIB (${dossier.macro_context.gdp_growth_pct?.date?.slice(0, 4) || "—"})`} />
              <strong>
                {dossier.macro_context.gdp_growth_pct
                  ? `${dossier.macro_context.gdp_growth_pct.value.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
            <div>
              <FinanceMetricLabel termKey="inflation_cpi" label={`Inflation IPC (${dossier.macro_context.inflation_pct?.date?.slice(0, 4) || "—"})`} />
              <strong>
                {dossier.macro_context.inflation_pct
                  ? `${dossier.macro_context.inflation_pct.value.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
            <div>
              <FinanceMetricLabel termKey="unemployment" label={`Chômage (${dossier.macro_context.unemployment_pct?.date?.slice(0, 4) || "—"})`} />
              <strong>
                {dossier.macro_context.unemployment_pct
                  ? `${dossier.macro_context.unemployment_pct.value.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
            <div>
              <FinanceMetricLabel termKey="tbill_4w" label="US T-Bill 4 sem." />
              <strong>
                {dossier.macro_context.us_treasury?.rate_4wk_pct != null
                  ? `${dossier.macro_context.us_treasury.rate_4wk_pct.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
            <div>
              <FinanceMetricLabel termKey="tbill_13w" label="US T-Bill 13 sem." />
              <strong>
                {dossier.macro_context.us_treasury?.rate_13w_pct != null
                  ? `${dossier.macro_context.us_treasury.rate_13w_pct.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
            <div>
              <FinanceMetricLabel termKey="risk_free_rate" label="Taux sans risque 52 s." />
              <strong>
                {dossier.macro_context.us_treasury?.risk_free_pct != null
                  ? `${dossier.macro_context.us_treasury.risk_free_pct.toFixed(2)}%`
                  : "—"}
              </strong>
            </div>
          </div>
        </section>
      )}

      {show("intrinsic") && (dossier.intrinsic_valuation?.available ? (
        <IntrinsicValuationSection
          data={dossier.intrinsic_valuation}
          currency={dossier.currency}
          dossier={dossier}
          onOpenHelp={onOpenHelp ? () => onOpenHelp("intrinsic") : undefined}
        />
      ) : (
        <section id="dossier-intrinsic" className="finance-dossier-section">
          <div className="finance-dossier-sec-head">
            <h4>Valeurs intrinsèques (Uncle Stock &amp; Modèle Corrigé)</h4>
            <div className="finance-intrinsic-head-actions">
              {onOpenHelp && (
                <button
                  type="button"
                  className="finance-tf-btn finance-help-inline-btn"
                  onClick={() => onOpenHelp("intrinsic")}
                  title="Ouvrir le guide détaillé des formules (20 chapitres)"
                >
                  <BookOpen size={12} />
                  <span>Guide formules</span>
                </button>
              )}
              <button
                type="button"
                className="finance-tf-btn finance-stmt-refresh-btn"
                disabled={refreshing}
                onClick={() => void handleRefresh()}
              >
                <RefreshCw size={12} className={refreshing ? "spin" : ""} />
                <span>{refreshing ? "Sync…" : "Actualiser"}</span>
              </button>
            </div>
          </div>
          <p className="finance-dossier-ai-placeholder">
            {dossier.intrinsic_valuation?.reason ||
              "Les valeurs intrinsèques ne sont pas encore disponibles dans la réponse de l'API (redémarrez clair-api ou cliquez sur Actualiser)."}
          </p>
        </section>
      ))}

      {/* Performance boursière ajustée des dividendes */}
      {show("synthese") && (
      <>
      <section id="dossier-perf" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>Performance boursière ajustée des dividendes</h4>
        </div>
        <PerformanceSvgChart series={dossier.performance_chart} />
        <div className="finance-dossier-perf-grid">
          {dossier.performance.horizons.map(h => (
            <div key={h.key} className="finance-dossier-perf-cell">
              <span>{h.label}</span>
              <strong className={h.pct == null ? undefined : h.pct >= 0 ? "text-emerald" : "text-rose"}>
                {h.pct == null ? "—" : `${h.pct >= 0 ? "+" : ""}${h.pct.toFixed(1)}%`}
              </strong>
            </div>
          ))}
        </div>
      </section>

      {/* Gestion du risque */}
      <section id="dossier-risque" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>Gestion du risque et performance ajustée du risque</h4>
          {dossier.risk.rf_rates_pct && (
            <small className="finance-dossier-unit">
              Taux sans risque ({dossier.currency}) : {dossier.risk.rf_rates_pct.map(r => `${r}%`).join(" / ")}
            </small>
          )}
        </div>
        <div className="finance-table-wrapper finance-stmt-scroll">
          <table className="finance-data-table finance-stmt-table">
            <thead>
              <tr>
                <th className="finance-stmt-sticky-col">Indicateur de risque</th>
                {dossier.risk.horizons.map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dossier.risk.metrics.map(m => (
                <tr key={m.key}>
                  <td className="finance-stmt-sticky-col">
                    <FinanceMetricLabel
                      termKey={m.key}
                      label={m.label}
                      calcDetail={buildRiskMetricCalc(m, dossier)}
                      strong
                    />
                  </td>
                  {m.values.map((v, idx) => (
                    <td key={`${m.key}-${idx}`}>
                      {v == null
                        ? "—"
                        : m.format === "pct"
                          ? `${v.toFixed(1)}%`
                          : m.format === "days"
                            ? `${Math.round(v)} j`
                            : v.toFixed(2)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      </>
      )}

      {/* Consensus Analystes & Direction */}
      {show("stakeholders") && (
      <>
      <section id="dossier-analystes" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>Consensus des analystes &amp; Équipe de direction</h4>
        </div>
        <div className="finance-dossier-analysts-grid">
          <div><span>Nbr d’analystes</span><strong>{an.total}</strong></div>
          <div><span>Acheter</span><strong className="text-emerald">{an.strong_buy}</strong></div>
          <div><span>Accumuler</span><strong className="text-emerald">{an.buy}</strong></div>
          <div><span>Conserver</span><strong>{an.hold}</strong></div>
          <div><span>Alléger</span><strong className="text-rose">{an.sell}</strong></div>
          <div><span>Vendre</span><strong className="text-rose">{an.strong_sell}</strong></div>
          <div><span>Cible moyenne</span><strong>{fmtNum(an.target_price, 1, ` ${dossier.currency}`)}</strong></div>
        </div>
        {an.total > 0 && (
          <div className="finance-dossier-rec-bar" aria-label="Répartition Acheter à Vendre">
            <span style={{ width: `${(an.strong_buy / an.total) * 100}%`, background: "#059669" }} />
            <span style={{ width: `${(an.buy / an.total) * 100}%`, background: "#34d399" }} />
            <span style={{ width: `${(an.hold / an.total) * 100}%`, background: "#f59e0b" }} />
            <span style={{ width: `${(an.sell / an.total) * 100}%`, background: "#fb7185" }} />
            <span style={{ width: `${(an.strong_sell / an.total) * 100}%`, background: "#e11d48" }} />
          </div>
        )}

        {stk.officers.length > 0 && (
          <div id="dossier-direction" className="finance-table-wrapper finance-dossier-subtable">
            <table className="finance-data-table">
              <thead>
                <tr>
                  <th>Dirigeant</th>
                  <th>Fonction</th>
                  <th>Âge</th>
                </tr>
              </thead>
              <tbody>
                {stk.officers.map((o, idx) => (
                  <tr key={`${o.name}-${idx}`}>
                    <td><strong>{o.name}</strong></td>
                    <td>{o.title || "—"}</td>
                    <td>{o.age ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Opérations d'initiés & Top fonds */}
      <section id="dossier-inities" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>Opérations d’initiés &amp; Top actionnaires</h4>
          {stk.insiders_net_amount != null && (
            <strong className={stk.insiders_net_amount >= 0 ? "text-emerald" : "text-rose"}>
              Cumul initiés : {stk.insiders_net_amount >= 0 ? "+" : ""}
              {Math.round(stk.insiders_net_amount).toLocaleString("fr-FR")} {dossier.currency}
            </strong>
          )}
        </div>

        {stk.insiders.length > 0 && (
          <div className="finance-table-wrapper finance-dossier-subtable finance-dossier-scroll-y">
            <table className="finance-data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Nom</th>
                  <th>Fonction / Relation</th>
                  <th>Opération</th>
                  <th>Quantité</th>
                  <th>Cours</th>
                  <th>Montant</th>
                </tr>
              </thead>
              <tbody>
                {stk.insiders.map((tr, idx) => (
                  <tr key={`${tr.date}-${tr.name}-${idx}`}>
                    <td>{tr.date}</td>
                    <td><strong>{tr.name}</strong></td>
                    <td>{tr.relation || "—"}</td>
                    <td className={tr.action === "Achat" ? "text-emerald" : tr.action === "Vente" ? "text-rose" : undefined}>
                      {tr.action}
                    </td>
                    <td>{fmtInt(tr.shares)}</td>
                    <td>{tr.price != null ? `${tr.price.toFixed(2)}` : "—"}</td>
                    <td>{tr.amount != null ? `${Math.round(tr.amount).toLocaleString("fr-FR")}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {(stk.funds.length > 0 || stk.institutions.length > 0) && (
          <div id="dossier-fonds" className="finance-dossier-holders">
            <div className="finance-dossier-sec-head">
              <h5>Principaux actionnaires</h5>
              <div className="finance-timeframe-selector">
                <button
                  type="button"
                  className={`finance-tf-btn ${holdersTab === "funds" ? "active" : ""}`}
                  onClick={() => setHoldersTab("funds")}
                >
                  Fonds ({stk.funds.length})
                </button>
                <button
                  type="button"
                  className={`finance-tf-btn ${holdersTab === "institutions" ? "active" : ""}`}
                  onClick={() => setHoldersTab("institutions")}
                >
                  Institutionnels ({stk.institutions.length})
                </button>
              </div>
            </div>
            <div className="finance-table-wrapper">
              <table className="finance-data-table">
                <thead>
                  <tr>
                    <th>Fonds / Institution</th>
                    <th>Date</th>
                    <th>Titres détenus</th>
                    <th>Poids / Actif</th>
                    <th>Variation</th>
                  </tr>
                </thead>
                <tbody>
                  {(holdersTab === "funds" ? stk.funds : stk.institutions).map((h, idx) => (
                    <tr key={`${h.name}-${idx}`}>
                      <td><strong>{h.name}</strong></td>
                      <td>{h.date || "—"}</td>
                      <td>{fmtInt(h.shares)}</td>
                      <td>{h.weight_pct != null ? `${h.weight_pct.toFixed(2)}%` : "—"}</td>
                      <td className={h.change_pct == null ? undefined : h.change_pct >= 0 ? "text-emerald" : "text-rose"}>
                        {h.change_pct != null ? `${h.change_pct >= 0 ? "+" : ""}${h.change_pct.toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
      </>
      )}

      {/* Fondamentaux synthèse & Ratios */}
      {show("ratios") && (
      <>
      <AnnualMatrixTable
        id="dossier-fondamentaux"
        title="Fondamentaux synthèse"
        unitNote={unitLabel}
        years={slicedAnnual.years}
        rows={slicedAnnual.summary}
        dossier={dossier}
      />

      {/* Ratios */}
      <div id="dossier-ratios" className="finance-dossier-ratios-stack">
        <AnnualMatrixTable id="dossier-profitabilite" title="Ratios de profitabilité" years={slicedAnnual.years} rows={slicedAnnual.profitability} dossier={dossier} />
        <AnnualMatrixTable id="dossier-solvabilite" title="Ratios de solvabilité" years={slicedAnnual.years} rows={slicedAnnual.solvency} dossier={dossier} />
        <AnnualMatrixTable
          id="dossier-distribution"
          title="Ratios de distribution"
          unitNote={unitLabel}
          years={slicedAnnual.years}
          rows={slicedAnnual.distribution}
          dossier={dossier}
        />
        <AnnualMatrixTable
          id="dossier-efficacite"
          title="Ratios du cycle de conversion et d'efficacité"
          years={slicedAnnual.years}
          rows={slicedAnnual.efficiency}
          dossier={dossier}
        />
      </div>
      </>
      )}

      {show("scores") && dossier.uncle_stock_scores?.available && (
        <UncleStockScoresSection
          data={dossier.uncle_stock_scores}
          dossier={dossier}
          onOpenHelp={onOpenHelp ? () => onOpenHelp("scores") : undefined}
        />
      )}

      {/* Scores qualitatifs : IH Score, F-Score Piotroski, Z-Score Altman */}
      {show("scores") && (
      <section id="dossier-scores" className="finance-dossier-section">
        <div className="finance-dossier-sec-head">
          <h4>Scores qualitatifs (IH Score, Piotroski, Altman)</h4>
          {onOpenHelp && (
            <button
              type="button"
              className="finance-tf-btn finance-help-inline-btn"
              onClick={() => onOpenHelp("scores")}
              title="Ouvrir le guide détaillé des 31 scores Uncle Stock (36 chapitres)"
            >
              <BookOpen size={12} />
              <span>Guide scores</span>
            </button>
          )}
        </div>

        {slicedAnnual.ih_score.years.length > 0 && (
          <div id="dossier-ihscore" className="finance-dossier-score-block">
            <div className="finance-dossier-score-banner">
              <strong>
                <FinanceMetricLabel
                  termKey="ih_score"
                  label="IH Score"
                  calcDetail={buildQualitativeScoreCalc("ih_score", dossier.annual_tables, dossier)}
                  strong
                />{" "}
                : {slicedAnnual.ih_score.latest_score?.toFixed(1) ?? "—"}/9 (
                {slicedAnnual.ih_score.quality_label})
              </strong>
              <span className="finance-dossier-trend-pill">
                {slicedAnnual.ih_score.trend === "Haussière" ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                Tendance {slicedAnnual.ih_score.trend}
              </span>
            </div>
            <div className="finance-table-wrapper finance-stmt-scroll">
              <table className="finance-data-table finance-stmt-table">
                <thead>
                  <tr>
                    <th className="finance-stmt-sticky-col">Critère IH Score</th>
                    {slicedAnnual.ih_score.years.map((y, idx) => (
                      <th key={`ih-${idx}-${y}`}>{y}</th>
                    ))}
                    <th>Moy.</th>
                  </tr>
                </thead>
                <tbody>
                  {slicedAnnual.ih_score.criteria.map(c => (
                    <tr key={c.key}>
                      <td className="finance-stmt-sticky-col">{c.label}</td>
                      {c.values.map((v, i) => (
                        <td key={`${c.key}-${i}`}>{v != null ? v : "—"}</td>
                      ))}
                      <td><strong>{c.avg?.toFixed(2) ?? "—"}</strong></td>
                    </tr>
                  ))}
                  <tr className="finance-dossier-total-row">
                    <td className="finance-stmt-sticky-col"><strong>IH SCORE</strong></td>
                    <td colSpan={slicedAnnual.ih_score.years.length} />
                    <td><strong>{slicedAnnual.ih_score.latest_score?.toFixed(1) ?? "—"}</strong></td>
                  </tr>
                  {slicedAnnual.ih_score.trend_criteria.map(c => (
                    <tr key={c.key} className="finance-dossier-trend-row">
                      <td className="finance-stmt-sticky-col">{c.label}</td>
                      {c.values.map((v, i) => (
                        <td key={`${c.key}-${i}`}>{v != null ? v : "—"}</td>
                      ))}
                      <td><strong>{c.avg?.toFixed(2) ?? "—"}</strong></td>
                    </tr>
                  ))}
                  <tr className="finance-dossier-total-row">
                    <td className="finance-stmt-sticky-col"><strong>TENDANCE</strong></td>
                    <td colSpan={slicedAnnual.ih_score.years.length} />
                    <td><strong>{slicedAnnual.ih_score.trend}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {slicedAnnual.piotroski.years.length > 0 && (
          <div id="dossier-piotroski" className="finance-dossier-score-block">
            <h5>
              <FinanceMetricLabel
                termKey="piotroski"
                label="F-Score Piotroski"
                calcDetail={buildQualitativeScoreCalc("piotroski", dossier.annual_tables, dossier)}
                strong
              />{" "}
              — Dernier exercice : <strong>{slicedAnnual.piotroski.latest_score ?? "—"}/9</strong>
            </h5>
            <div className="finance-table-wrapper finance-stmt-scroll">
              <table className="finance-data-table finance-stmt-table">
                <thead>
                  <tr>
                    <th className="finance-stmt-sticky-col">Critère Piotroski</th>
                    {slicedAnnual.piotroski.years.map((y, idx) => (
                      <th key={`pio-${idx}-${y}`}>{y}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {slicedAnnual.piotroski.criteria.map(c => (
                    <tr key={c.key}>
                      <td className="finance-stmt-sticky-col">{c.label}</td>
                      {c.values.map((v, i) => (
                        <td key={`${c.key}-${i}`}>{v ?? "—"}</td>
                      ))}
                    </tr>
                  ))}
                  <tr className="finance-dossier-total-row">
                    <td className="finance-stmt-sticky-col"><strong>F_SCORE</strong></td>
                    {slicedAnnual.piotroski.scores.map((s, i) => (
                      <td key={`f-${i}`}><strong>{s}</strong></td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {slicedAnnual.altman.years.length > 0 && (
          <div id="dossier-altman" className="finance-dossier-score-block">
            <h5>
              <FinanceMetricLabel
                termKey="altman"
                label="Z-Score Altman"
                calcDetail={buildQualitativeScoreCalc("altman", dossier.annual_tables, dossier)}
                strong
              />{" "}
              — Dernier exercice : <strong>{slicedAnnual.altman.latest_score?.toFixed(1) ?? "—"}</strong>
            </h5>
            <div className="finance-table-wrapper finance-stmt-scroll">
              <table className="finance-data-table finance-stmt-table">
                <thead>
                  <tr>
                    <th className="finance-stmt-sticky-col">Critère Altman</th>
                    {slicedAnnual.altman.years.map((y, idx) => (
                      <th key={`alt-${idx}-${y}`}>{y}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {slicedAnnual.altman.criteria.map(c => (
                    <tr key={c.key}>
                      <td className="finance-stmt-sticky-col">
                        <FinanceMetricLabel termKey={`altman_${c.key}`} label={c.label} />
                      </td>
                      {c.values.map((v, i) => (
                        <td key={`${c.key}-${i}`}>{v != null ? v.toFixed(1) : "—"}</td>
                      ))}
                    </tr>
                  ))}
                  <tr className="finance-dossier-total-row">
                    <td className="finance-stmt-sticky-col"><strong>Z_SCORE</strong></td>
                    {slicedAnnual.altman.scores.map((s, i) => (
                      <td key={`z-${i}`}><strong>{s != null ? s.toFixed(1) : "—"}</strong></td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
      )}

      {/* Dividendes par action détachés */}
      {show("stakeholders") && dossier.dividends_matrix.rows.length > 0 && (
        <section id="dossier-dividendes" className="finance-dossier-section">
          <div className="finance-dossier-sec-head">
            <h4>Dividendes par action détachés</h4>
            <small className="finance-dossier-unit">({dossier.currency})</small>
          </div>
          <div className="finance-table-wrapper finance-stmt-scroll">
            <table className="finance-data-table finance-stmt-table">
              <thead>
                <tr>
                  <th className="finance-stmt-sticky-col">Année</th>
                  {MONTHS_FR.map(m => (
                    <th key={m}>{m}</th>
                  ))}
                  <th>Tot.</th>
                </tr>
              </thead>
              <tbody>
                {dossier.dividends_matrix.rows.map(r => (
                  <tr key={r.year}>
                    <td className="finance-stmt-sticky-col"><strong>{r.year}</strong></td>
                    {r.months.map((v, idx) => (
                      <td key={`${r.year}-${idx}`}>{v != null ? v.toFixed(3) : "—"}</td>
                    ))}
                    <td><strong>{r.total != null ? r.total.toFixed(3) : "—"}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Comptes annuels & trimestriels détaillés */}
      {show("statements") && (
      <>
      <SimplifiedPeriodSection
        id="dossier-comptes-annuels"
        title="Comptes annuels simplifiés"
        unitNote={unitLabel}
        period={dossier.statements.annual}
        limit={depth === "all" ? null : Number(depth)}
        annual
      />
      <SimplifiedPeriodSection
        id="dossier-comptes-trimestriels"
        title="Comptes trimestriels simplifiés"
        unitNote={unitLabel}
        period={dossier.statements.quarterly}
        limit={depth === "all" ? null : Number(depth)}
        annual={false}
      />

      {dossier.earnings_calendar && dossier.earnings_calendar.length > 0 && (
        <section id="dossier-calendrier" className="finance-dossier-section">
          <div className="finance-dossier-sec-head">
            <h4>Calendrier corporate des résultats</h4>
            <small className="finance-dossier-unit">EODHD Corporate Calendar</small>
          </div>
          <div className="finance-table-wrapper">
            <table className="finance-data-table">
              <thead>
                <tr>
                  <th>Date publication</th>
                  <th>Période fiscale</th>
                  <th>Moment</th>
                  <th>BPA estimé</th>
                  <th>BPA publié</th>
                  <th>Surprise</th>
                </tr>
              </thead>
              <tbody>
                {dossier.earnings_calendar.map((row, i) => (
                  <tr key={`${i}-${row.report_date}-${row.fiscal_date}`}>
                    <td><strong>{row.report_date || "—"}</strong></td>
                    <td>{row.fiscal_date || "—"}</td>
                    <td>{row.timing || "—"}</td>
                    <td>{row.estimate != null ? `${row.estimate.toFixed(2)} ${row.currency}`.trim() : "—"}</td>
                    <td><strong>{row.actual != null ? `${row.actual.toFixed(2)} ${row.currency}`.trim() : "À publier"}</strong></td>
                    <td className={row.surprise_pct == null ? undefined : row.surprise_pct >= 0 ? "text-emerald" : "text-rose"}>
                      {row.surprise_pct != null ? `${row.surprise_pct >= 0 ? "+" : ""}${row.surprise_pct.toFixed(2)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {dossier.statements.earnings_history.length > 0 && (
        <section id="dossier-bpa" className="finance-dossier-section">
          <div className="finance-dossier-sec-head">
            <h4>Publications BPA (estimé vs publié)</h4>
          </div>
          <div className="finance-table-wrapper finance-dossier-scroll-y">
            <table className="finance-data-table">
              <thead>
                <tr>
                  <th>Période</th>
                  <th>Publication</th>
                  <th>BPA estimé</th>
                  <th>BPA publié</th>
                  <th>Écart</th>
                  <th>Surprise</th>
                </tr>
              </thead>
              <tbody>
                {dossier.statements.earnings_history.slice(0, 24).map(row => (
                  <tr key={`${row.date}-${row.report_date ?? ""}`}>
                    <td><strong>{row.date}</strong></td>
                    <td>{row.report_date || "—"}</td>
                    <td>{row.eps_estimate != null ? row.eps_estimate.toFixed(2) : "—"}</td>
                    <td><strong>{row.eps_actual != null ? row.eps_actual.toFixed(2) : "—"}</strong></td>
                    <td className={row.eps_difference == null ? undefined : row.eps_difference >= 0 ? "text-emerald" : "text-rose"}>
                      {row.eps_difference != null ? `${row.eps_difference >= 0 ? "+" : ""}${row.eps_difference.toFixed(2)}` : "—"}
                    </td>
                    <td className={row.surprise_pct == null ? undefined : row.surprise_pct >= 0 ? "text-emerald" : "text-rose"}>
                      {row.surprise_pct != null ? `${row.surprise_pct >= 0 ? "+" : ""}${row.surprise_pct.toFixed(2)}%` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      </>
      )}
    </div>
  );
}

function IntrinsicValuationSection({
  data,
  currency,
  dossier,
  onOpenHelp,
}: {
  data: IntrinsicValuationPayload;
  currency: string;
  dossier: FinancialDossier;
  onOpenHelp?: () => void;
}) {
  const [mode, setMode] = useState<"corrected" | "unclestock">("corrected");
  const [expandedId, setExpandedId] = useState<string | null>("dcf_fcf");

  const activeAgg = mode === "corrected" ? data.summary.corrected : data.summary.unclestock;
  const coc = data.cost_of_capital || {};
  const owr = data.owner_returns || {};
  const weightedMethods = data.methods.filter(m => m.category === "weighted");
  const extraMethods = data.methods.filter(m => m.category === "complementary");

  const renderRows = (rows: typeof data.methods) =>
    rows.map(m => {
      const val = mode === "corrected" ? m.corrected_value : m.unclestock_value;
      const st = mode === "corrected" ? m.status_corrected : m.status_unclestock;
      const pIv = mode === "corrected" ? m.price_to_iv_corrected : m.price_to_iv_unclestock;
      const mos = mode === "corrected" ? m.margin_of_safety_corrected_pct : m.margin_of_safety_unclestock_pct;
      const isOpen = expandedId === m.id;
      const hasDetails = m.assumptions.length > 0 || Object.keys(m.intermediates).length > 0 || m.warnings.length > 0 || Boolean(m.exclusion_reason);

      return (
        <tr key={m.id} className={st !== "valid" ? "is-muted-row" : undefined}>
          <td>
            <div className="finance-intrinsic-method-name">
              <FinanceMetricLabel
                termKey={m.id}
                label={m.name}
                calcDetail={buildIntrinsicMethodCalc(m, mode, currency, dossier)}
                strong
              />
              {hasDetails && (
                <button
                  type="button"
                  className="finance-intrinsic-detail-btn"
                  onClick={() => setExpandedId(isOpen ? null : m.id)}
                >
                  {isOpen ? "Masquer" : "Détails"}
                </button>
              )}
            </div>
            {isOpen && (
              <div className="finance-intrinsic-details-box">
                {m.exclusion_reason && <div className="text-rose">Motif : {m.exclusion_reason}</div>}
                {m.assumptions.map((a, idx) => (
                  <div key={idx}>• {a}</div>
                ))}
                {Object.keys(m.intermediates).length > 0 && (
                  <div className="finance-intrinsic-interm-grid">
                    {Object.entries(m.intermediates).map(([k, v]) => (
                      <span key={k}>
                        <code>{k}</code> :{" "}
                        <strong>
                          {typeof v === "number"
                            ? Math.abs(v) >= 1e6
                              ? `${(v / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M`
                              : v.toLocaleString("fr-FR", { maximumFractionDigits: 3 })
                            : String(v ?? "—")}
                        </strong>
                      </span>
                    ))}
                  </div>
                )}
                {m.warnings.map((w, idx) => (
                  <div key={idx} className="finance-intrinsic-warn">⚠ {w}</div>
                ))}
              </div>
            )}
          </td>
          <td>{m.weight > 0 ? m.weight : "Compl."}</td>
          <td>
            <span className={`finance-intrinsic-status is-${st}`}>
              {st === "valid" ? "Valide" : st === "excluded" ? "Exclue" : "Indisp."}
            </span>
          </td>
          <td>
            <strong>{val != null ? `${val.toFixed(2)} ${currency}` : "—"}</strong>
          </td>
          <td>{pIv != null ? `${pIv.toFixed(2)}×` : "—"}</td>
          <td className={mos == null ? undefined : mos >= 0 ? "text-emerald" : "text-rose"}>
            {mos != null ? `${mos >= 0 ? "+" : ""}${mos.toFixed(1)}%` : "—"}
          </td>
        </tr>
      );
    });

  return (
    <section id="dossier-intrinsic" className="finance-dossier-section">
      <div className="finance-dossier-sec-head">
        <h4>Valeurs intrinsèques (Uncle Stock &amp; Modèle Corrigé)</h4>
        <div className="finance-intrinsic-head-actions">
          {onOpenHelp && (
            <button
              type="button"
              className="finance-tf-btn finance-help-inline-btn"
              onClick={onOpenHelp}
              title="Ouvrir le guide détaillé des formules (20 chapitres)"
            >
              <BookOpen size={12} />
              <span>Guide formules</span>
            </button>
          )}
          <div className="finance-timeframe-selector">
            <button
              type="button"
              className={`finance-tf-btn ${mode === "corrected" ? "active" : ""}`}
              onClick={() => setMode("corrected")}
            >
              Mode Corrigé (Indépendant)
            </button>
            <button
              type="button"
              className={`finance-tf-btn ${mode === "unclestock" ? "active" : ""}`}
              onClick={() => setMode("unclestock")}
            >
              Mode Fidèle Uncle Stock
            </button>
          </div>
        </div>
      </div>

      {/* Synthèse & Coût du capital */}
      <div className="finance-dossier-grids-stack">
        <div className="finance-dossier-6grid">
          <div>
            <FinanceMetricLabel
              termKey="intrinsic_value"
              label={`VI Globale (${activeAgg ? `${activeAgg.weight_used}/${activeAgg.weight_max} poids` : "—"})`}
              calcDetail={buildIntrinsicSummaryCalc("iv", data, mode, currency, dossier)}
            />
            <strong>{activeAgg ? `${activeAgg.intrinsic_value.toFixed(2)} ${currency}` : "—"}</strong>
          </div>
          <div>
            <span>Cours actuel</span>
            <strong>{data.current_price != null ? `${data.current_price.toFixed(2)} ${currency}` : "—"}</strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="margin_of_safety"
              label="Marge de sécurité"
              calcDetail={buildIntrinsicSummaryCalc("mos", data, mode, currency, dossier)}
            />
            <strong
              className={
                activeAgg?.margin_of_safety_pct == null
                  ? undefined
                  : activeAgg.margin_of_safety_pct >= 0
                    ? "text-emerald"
                    : "text-rose"
              }
            >
              {activeAgg?.margin_of_safety_pct != null
                ? `${activeAgg.margin_of_safety_pct >= 0 ? "+" : ""}${activeAgg.margin_of_safety_pct.toFixed(1)}%`
                : "—"}
            </strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="price_to_iv"
              label="Ratio Cours / VI"
              calcDetail={buildIntrinsicSummaryCalc("price_to_iv", data, mode, currency, dossier)}
            />
            <strong>{activeAgg?.price_to_iv != null ? `${activeAgg.price_to_iv.toFixed(2)}×` : "—"}</strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="wacc"
              label={`WACC (plancher ${fmtNum(coc.wacc_floor_pct, 1, "%")})`}
              calcDetail={buildCostOfCapitalCalc("wacc", data, currency, dossier)}
            />
            <strong>{fmtNum(coc.wacc_pct, 2, "%")}</strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="ke_capm"
              label="Ke (CAPM) / Kd net"
              calcDetail={buildCostOfCapitalCalc("ke_capm", data, currency, dossier)}
            />
            <strong>
              {fmtNum(coc.cost_of_equity_capm_pct, 2, "%")} / {fmtNum(coc.after_tax_cost_of_debt_pct, 2, "%")}
            </strong>
          </div>
        </div>

        <div className="finance-dossier-6grid">
          <div>
            <FinanceMetricLabel
              termKey="total_owner_return"
              label="Total Owner Return"
              calcDetail={buildCostOfCapitalCalc("total_owner_return", data, currency, dossier)}
            />
            <strong className={owr.total_owner_return_pct == null ? undefined : owr.total_owner_return_pct >= 0 ? "text-emerald" : "text-rose"}>
              {owr.total_owner_return_pct != null ? `${owr.total_owner_return_pct >= 0 ? "+" : ""}${owr.total_owner_return_pct.toFixed(1)}%` : "—"}
            </strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="net_owner_return"
              label="Net Owner Return"
              calcDetail={buildCostOfCapitalCalc("net_owner_return", data, currency, dossier)}
            />
            <strong className={owr.net_owner_return_pct == null ? undefined : owr.net_owner_return_pct >= 0 ? "text-emerald" : "text-rose"}>
              {owr.net_owner_return_pct != null ? `${owr.net_owner_return_pct >= 0 ? "+" : ""}${owr.net_owner_return_pct.toFixed(1)}%` : "—"}
            </strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="buffett_irr"
              label="TRI Buffett (implicite)"
              calcDetail={buildCostOfCapitalCalc("buffett_irr", data, currency, dossier)}
            />
            <strong>{fmtNum(owr.buffett_rate_of_return_pct, 2, "%")}</strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="forward_return_yacktman"
              label="Rdt Prospectif Yacktman"
              calcDetail={buildCostOfCapitalCalc("forward_return_yacktman", data, currency, dossier)}
            />
            <strong>{fmtNum(owr.forward_rate_of_return_pct, 2, "%")}</strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="payback_market"
              label="Payback marché estimé"
              calcDetail={buildCostOfCapitalCalc("payback_market", data, currency, dossier)}
            />
            <strong>{owr.payback_years_market != null ? `${owr.payback_years_market.toFixed(1)} ans` : "—"}</strong>
          </div>
          <div>
            <FinanceMetricLabel
              termKey="equity_charge"
              label="Charge d’équité / act."
              calcDetail={buildCostOfCapitalCalc("equity_charge", data, currency, dossier)}
            />
            <strong>{fmtNum(coc.equity_charge_ps, 2, ` ${currency}`)}</strong>
          </div>
        </div>
      </div>

      {/* Tableau des 13 composantes pondérées + méthodes complémentaires */}
      <div className="finance-table-wrapper">
        <table className="finance-data-table">
          <thead>
            <tr>
              <th>Méthode (cliquer sur Détails pour les étapes)</th>
              <th>Poids</th>
              <th>Statut</th>
              <th>Valeur / act.</th>
              <th><FinanceMetricLabel termKey="price_to_iv" label="Cours / VI" /></th>
              <th><FinanceMetricLabel termKey="margin_of_safety" label="Marge sécurité" /></th>
            </tr>
          </thead>
          <tbody>
            {renderRows(weightedMethods)}
            {extraMethods.length > 0 && (
              <tr className="finance-dossier-total-row">
                <td colSpan={6}><strong>Méthodes complémentaires (hors pondération globale)</strong></td>
              </tr>
            )}
            {renderRows(extraMethods)}
          </tbody>
        </table>
      </div>

      {/* 3 Scénarios DCF FCF & Sensibilité WACC × Croissance */}
      {(data.scenarios.length > 0 || data.sensitivity) && (
        <div className="finance-intrinsic-bottom-grid">
          {data.scenarios.length > 0 && (
            <div className="finance-dossier-score-block">
              <h5>Scénarios DCF FCF</h5>
              <div className="finance-table-wrapper">
                <table className="finance-data-table">
                  <thead>
                    <tr>
                      <th>Scénario</th>
                      <th>Croissance</th>
                      <th>WACC</th>
                      <th>VI / action</th>
                      <th>Marge séc.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.scenarios.map(sc => (
                      <tr key={sc.key}>
                        <td><strong>{sc.label}</strong></td>
                        <td>{sc.growth_pct.toFixed(1)}%</td>
                        <td>{sc.wacc_pct.toFixed(1)}%</td>
                        <td><strong>{sc.intrinsic_value != null ? `${sc.intrinsic_value.toFixed(2)} ${currency}` : "—"}</strong></td>
                        <td className={sc.margin_of_safety_pct == null ? undefined : sc.margin_of_safety_pct >= 0 ? "text-emerald" : "text-rose"}>
                          {sc.margin_of_safety_pct != null ? `${sc.margin_of_safety_pct >= 0 ? "+" : ""}${sc.margin_of_safety_pct.toFixed(1)}%` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {data.sensitivity && (
            <div className="finance-dossier-score-block">
              <h5>Sensibilité DCF FCF (WACC × Croissance)</h5>
              <div className="finance-table-wrapper">
                <table className="finance-data-table">
                  <thead>
                    <tr>
                      <th>WACC \ g</th>
                      {data.sensitivity.growth_headers_pct.map(g => (
                        <th key={g}>{g.toFixed(1)}%</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.sensitivity.rows.map(r => (
                      <tr key={r.wacc_pct}>
                        <td><strong>{r.wacc_pct.toFixed(1)}%</strong></td>
                        {r.cells.map(c => (
                          <td key={`${r.wacc_pct}-${c.growth_pct}`} className={c.undervalued ? "text-emerald" : "text-rose"}>
                            {c.value != null ? c.value.toFixed(1) : "—"}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

const SCORE_CATEGORY_ORDER = [
  "Tous",
  "Signal",
  "Scores Uncle Stock",
  "Qualité & Croissance",
  "Scores Factoriels",
  "Santé & Faillite",
  "Manipulation comptable",
  "ESG",
] as const;

function scoreToneClass(id: string, finalScore: number | string | null, available: boolean): string {
  if (!available || finalScore == null) return "";
  if (typeof finalScore === "string") {
    const low = finalScore.toLowerCase();
    if (low.includes("strong buy") || low === "buy" || low === "oui") return "text-emerald";
    if (low.includes("sell") || low === "non") return "text-rose";
    return "";
  }
  if (id === "trap_score") {
    return finalScore >= 60 ? "text-rose" : finalScore <= 30 ? "text-emerald" : "";
  }
  if (id === "montier_c_score") {
    return finalScore >= 4 ? "text-rose" : finalScore <= 1 ? "text-emerald" : "";
  }
  if (id === "beneish_m_score") {
    return finalScore > -1.78 ? "text-rose" : "text-emerald";
  }
  if (id === "dechow_f_score") {
    return finalScore > 1.85 ? "text-rose" : finalScore <= 1.2 ? "text-emerald" : "";
  }
  if (id === "ohlson_o_score") {
    return finalScore > 0.5 ? "text-rose" : finalScore < -0.5 ? "text-emerald" : "";
  }
  if (id === "altman_z_score") {
    return finalScore >= 3 ? "text-emerald" : finalScore < 1.81 ? "text-rose" : "";
  }
  if (id === "piotroski_f_score") {
    return finalScore >= 7 ? "text-emerald" : finalScore <= 3 ? "text-rose" : "";
  }
  if (id === "mohanram_g_score") {
    return finalScore >= 6 ? "text-emerald" : finalScore <= 2 ? "text-rose" : "";
  }
  if (id === "levermann_score") {
    return finalScore >= 4 ? "text-emerald" : finalScore <= 0 ? "text-rose" : "";
  }
  if (finalScore >= 70) return "text-emerald";
  if (finalScore < 40) return "text-rose";
  return "";
}

function fmtCompVal(v: number | string | boolean | null | undefined): string {
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "Oui" : "Non";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    if (Math.abs(v) >= 1e9) return `${(v / 1e9).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} Md`;
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} M`;
    return v.toLocaleString("fr-FR", { maximumFractionDigits: 3 });
  }
  return String(v);
}

function UncleStockScoresSection({
  data,
  dossier,
  onOpenHelp,
}: {
  data: UncleStockScoresPayload;
  dossier: FinancialDossier;
  onOpenHelp?: () => void;
}) {
  const [mode, setMode] = useState<"verified" | "documented">("verified");
  const [selectedCategory, setSelectedCategory] = useState<string>("Tous");
  const [expandedId, setExpandedId] = useState<string | null>("uncle_stock_score");

  const availableCategories = useMemo(() => {
    const present = new Set(data.items.map(i => i.category));
    return SCORE_CATEGORY_ORDER.filter(cat => cat === "Tous" || present.has(cat));
  }, [data.items]);

  const filteredItems = useMemo(
    () => (selectedCategory === "Tous" ? data.items : data.items.filter(i => i.category === selectedCategory)),
    [data.items, selectedCategory],
  );

  const summary = data.summary;
  const activeUncleScore = mode === "verified" ? summary.uncle_stock_score_verified : summary.uncle_stock_score_documented;
  const activeAdvice = mode === "verified" ? summary.advice_verified : summary.advice_documented;

  return (
    <section id="dossier-unclestock-scores" className="finance-dossier-section">
      <div className="finance-dossier-sec-head">
        <div>
          <h4>Scores &amp; Indicateurs Uncle Stock (31)</h4>
          <small className="finance-dossier-unit">
            Synthèse multifactorielle complète (mode vérifié/interprété vs formule littérale documentée)
          </small>
        </div>
        <div className="finance-intrinsic-head-actions">
          {onOpenHelp && (
            <button
              type="button"
              className="finance-tf-btn finance-help-inline-btn"
              onClick={onOpenHelp}
              title="Ouvrir le guide détaillé des 31 scores Uncle Stock (36 chapitres)"
            >
              <BookOpen size={12} />
              <span>Guide scores</span>
            </button>
          )}
          <div className="finance-timeframe-selector" role="group" aria-label="Mode de calcul des scores">
            <button
              type="button"
              className={`finance-tf-btn ${mode === "verified" ? "active" : ""}`}
              onClick={() => setMode("verified")}
              title="Dénominateurs alignés (1540, 2170, 1070, 3040), sigmoïde k=4, signe Dechow corrigé et branches cohérentes"
            >
              Vérifié / Interprété
            </button>
            <button
              type="button"
              className={`finance-tf-btn ${mode === "documented" ? "active" : ""}`}
              onClick={() => setMode("documented")}
              title="Formules littérales du guide (ex. /1420, /1810) avec alertes sur divergences connues"
            >
              Documenté
            </button>
          </div>
        </div>
      </div>

      {/* Cartes de synthèse */}
      {(() => {
        const byScoreId = Object.fromEntries(data.items.map(it => [it.id, it])) as Record<
          string,
          UncleStockScoreItem
        >;
        const kpiCalc = (id: string) =>
          byScoreId[id] ? buildUncleStockScoreCalc(byScoreId[id], mode, dossier) : undefined;
        return (
          <div className="finance-intrinsic-summary-grid finance-unclestock-summary-grid">
            <div className="finance-intrinsic-kpi">
              <span><FinanceMetricLabel termKey="advice" label="Verdict Advice" calcDetail={kpiCalc("advice")} /></span>
              <strong className={scoreToneClass("advice", activeAdvice, true)}>{activeAdvice || "—"}</strong>
              <small>{summary.categories || "Profil standard"}</small>
            </div>
            <div className="finance-intrinsic-kpi">
              <span><FinanceMetricLabel termKey="uncle_stock_score" label="Uncle Stock Score" calcDetail={kpiCalc("uncle_stock_score")} /></span>
              <strong className={scoreToneClass("uncle_stock_score", activeUncleScore, activeUncleScore != null)}>
                {activeUncleScore != null ? `${activeUncleScore.toFixed(1)} / 100` : "—"}
              </strong>
              <small>{mode === "verified" ? "Dénominateur aligné /1540" : "Littéral /1420 (clampé 1540)"}</small>
            </div>
            <div className="finance-intrinsic-kpi">
              <span><FinanceMetricLabel termKey="quality_score" label="Quality" calcDetail={kpiCalc("quality_score")} /></span>
              <strong className={scoreToneClass("quality_score", summary.quality_score, summary.quality_score != null)}>
                {summary.quality_score != null ? `${summary.quality_score.toFixed(1)} / 100` : "—"}
              </strong>
              <small>Rentabilité &amp; marges</small>
            </div>
            <div className="finance-intrinsic-kpi">
              <span><FinanceMetricLabel termKey="value_score" label="Value" calcDetail={kpiCalc("value_score")} /></span>
              <strong className={scoreToneClass("value_score", summary.value_score, summary.value_score != null)}>
                {summary.value_score != null ? `${summary.value_score.toFixed(1)} / 100` : "—"}
              </strong>
              <small>Multiples &amp; décote</small>
            </div>
            <div className="finance-intrinsic-kpi">
              <span><FinanceMetricLabel termKey="financial_health_score" label="Financial Health" calcDetail={kpiCalc("financial_health_score")} /></span>
              <strong className={scoreToneClass("financial_health_score", summary.financial_health_score, summary.financial_health_score != null)}>
                {summary.financial_health_score != null ? `${summary.financial_health_score.toFixed(1)} / 100` : "—"}
              </strong>
              <small>Solvabilité &amp; flux</small>
            </div>
            <div className="finance-intrinsic-kpi">
              <span><FinanceMetricLabel termKey="trap_score" label="Trap Score" calcDetail={kpiCalc("trap_score")} /></span>
              <strong className={scoreToneClass("trap_score", summary.trap_score, summary.trap_score != null)}>
                {summary.trap_score != null ? `${summary.trap_score.toFixed(1)} / 100` : "—"}
              </strong>
              <small>Plus bas = moins de risque</small>
            </div>
          </div>
        );
      })()}

      {/* Filtres par catégorie */}
      <div className="finance-unclestock-filters" role="group" aria-label="Filtrer les scores par catégorie">
        {availableCategories.map(cat => (
          <button
            key={cat}
            type="button"
            className={`finance-tf-btn ${selectedCategory === cat ? "active" : ""}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Tableau détaillé des 31 scores */}
      <div className="finance-table-wrapper">
        <table className="finance-data-table finance-intrinsic-table">
          <thead>
            <tr>
              <th>Indicateur / Score</th>
              <th>Catégorie</th>
              <th>Score ({mode === "verified" ? "Vérifié" : "Documenté"})</th>
              <th>Normalisé / 100</th>
              <th>Statut</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.map(item => {
              const res = mode === "verified" ? item.verified : item.documented;
              const isOpen = expandedId === item.id;
              const hasDetails = Boolean(res.summary) || res.components.length > 0 || res.warnings.length > 0;
              const tone = scoreToneClass(item.id, res.final_score, res.available);

              return (
                <tr key={item.id} className={!res.available ? "is-muted-row" : undefined}>
                  <td>
                    <div className="finance-intrinsic-method-name">
                      <FinanceMetricLabel
                        termKey={item.id}
                        label={item.name}
                        calcDetail={buildUncleStockScoreCalc(item, mode, dossier)}
                        strong
                      />
                      {hasDetails && (
                        <button
                          type="button"
                          className="finance-intrinsic-detail-btn"
                          onClick={() => setExpandedId(isOpen ? null : item.id)}
                        >
                          {isOpen ? "Masquer" : "Détails"}
                        </button>
                      )}
                    </div>
                    {isOpen && (
                      <div className="finance-intrinsic-details-box">
                        {res.summary && <div>{res.summary}</div>}
                        {res.components.length > 0 && (
                          <div className="finance-intrinsic-interm-grid">
                            {res.components.map((c, idx) => (
                              <span key={`${item.id}-c-${idx}`}>
                                <code>{c.name}</code> : <strong>{fmtCompVal(c.input)}</strong>
                                {c.weight != null && <> (poids {c.weight}</>}
                                {c.contribution != null && <>{c.weight != null ? ", " : " ("}contrib. {c.contribution.toFixed(1)}</>}
                                {(c.weight != null || c.contribution != null) && <>)</>}
                              </span>
                            ))}
                          </div>
                        )}
                        {res.warnings.map((w, idx) => (
                          <div key={idx} className="finance-intrinsic-warn">⚠ {w}</div>
                        ))}
                      </div>
                    )}
                  </td>
                  <td><small>{item.category}</small></td>
                  <td className={tone}><strong>{res.display_value || "—"}</strong></td>
                  <td>
                    {res.normalized_score != null ? (
                      <span>{res.normalized_score.toFixed(1)}</span>
                    ) : "—"}
                  </td>
                  <td>
                    <span className={`finance-intrinsic-status ${res.available ? "is-valid" : "is-unavailable"}`}>
                      {res.available ? (res.warnings.length > 0 ? "Partiel" : "Calculé") : "Indisp."}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SimplifiedPeriodSection({
  id,
  title,
  unitNote,
  period,
  limit,
  annual,
}: {
  id: string;
  title: string;
  unitNote: string;
  period: StatementPeriod;
  limit: number | null;
  annual: boolean;
}) {
  if (!period || period.dates.length === 0) return null;
  const start = limit != null && period.dates.length > limit ? period.dates.length - limit : 0;
  const dates = period.dates.slice(start);
  const subTables: [string, StatementRow[]][] = [
    ["Compte de résultat", period.income],
    ["Bilan", period.balance],
    ["Flux de trésorerie", period.cashflow],
  ];

  return (
    <section id={id} className="finance-dossier-section">
      <div className="finance-dossier-sec-head">
        <h4>{title}</h4>
        <small className="finance-dossier-unit">{unitNote}</small>
      </div>
      {subTables.map(([subTitle, rawRows]) => {
        const rows = rawRows.map(r => ({ ...r, values: r.values.slice(start) })).filter(r => r.values.some(v => v != null));
        if (rows.length === 0) return null;
        return (
          <div key={`${id}-${subTitle}`} className="finance-dossier-score-block">
            <h5>{subTitle}</h5>
            <div className="finance-table-wrapper finance-stmt-scroll">
              <table className="finance-data-table finance-stmt-table">
                <thead>
                  <tr>
                    <th className="finance-stmt-sticky-col">Poste</th>
                    {dates.map((d, i) => (
                      <th key={`${id}-d-${i}-${d}`}>{annual ? d.slice(0, 4) : d.slice(0, 7)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.key}>
                      <td className="finance-stmt-sticky-col"><strong>{r.label}</strong></td>
                      {r.values.map((v, i) => (
                        <td key={`${r.key}-${i}`} className={v != null && v < 0 ? "text-rose" : undefined}>
                          {r.key === "DilutedEPS" || r.key === "BasicEPS"
                            ? (v != null ? v.toFixed(2) : "—")
                            : fmtMln(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </section>
  );
}
