"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  Calendar,
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
  LineChart,
  LoaderCircle,
  MessageSquarePlus,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react";
import {
  fetchFinanceDetails,
  type EodBar,
  type FinancialDashboardData,
  type FinancialStats,
} from "@/lib/api";

type FinanceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  initialQuery?: string | null;
  initialData?: FinancialDashboardData | null;
  onInsertIntoChat?: (text: string) => void;
};

type ActiveTab = "valuation" | "profitability" | "balance_sheet" | "analysts" | "history" | "profile";

const QUICK_SUGGESTIONS = [
  "Air Liquide",
  "LVMH",
  "TotalEnergies",
  "Apple",
  "Tesla",
  "Nvidia",
  "Stellantis",
  "Microsoft",
];

export function FinanceModal({
  isOpen,
  onClose,
  initialQuery,
  initialData,
  onInsertIntoChat,
}: FinanceModalProps) {
  const [query, setQuery] = useState("");
  const [data, setData] = useState<FinancialDashboardData | null>(initialData || null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("valuation");
  const [timeframe, setTimeframe] = useState<"1S" | "2S" | "1M" | "ALL">("1M");
  const [hoveredBarIndex, setHoveredBarIndex] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);

  // Synchronize when opening modal
  useEffect(() => {
    if (!isOpen) return;

    if (initialData) {
      setData(initialData);
      setQuery(initialData.short_name || initialData.symbol);
      setError(null);
      return;
    }

    const targetQuery = (initialQuery || "").trim();
    if (targetQuery) {
      setQuery(targetQuery);
      void loadDetails(targetQuery);
    } else if (!data) {
      // Default to Air Liquide if no initial query
      setQuery("Air Liquide");
      void loadDetails("Air Liquide");
    }
  }, [isOpen, initialQuery, initialData]);

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  async function loadDetails(searchTarget: string) {
    const q = searchTarget.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchFinanceDetails(q);
      setData(res);
    } catch (err: any) {
      setError(err?.message || "Impossible de charger les données financières pour cette action.");
    } finally {
      setLoading(false);
    }
  }

  function handleSearchSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (query.trim()) {
      void loadDetails(query.trim());
    }
  }

  // Filter bars according to selected timeframe
  const filteredBars = useMemo(() => {
    if (!data?.eod_bars || data.eod_bars.length === 0) return [];
    const all = data.eod_bars;
    if (timeframe === "1S") return all.slice(-5);
    if (timeframe === "2S") return all.slice(-10);
    if (timeframe === "1M") return all.slice(-22);
    return all;
  }, [data?.eod_bars, timeframe]);

  // Timeframe stats calculation
  const timeframeStats = useMemo(() => {
    if (filteredBars.length < 2) return null;
    const firstClose = filteredBars[0].close ?? 0;
    const lastClose = filteredBars[filteredBars.length - 1].close ?? 0;
    const diff = lastClose - firstClose;
    const diffPct = firstClose > 0 ? (diff / firstClose) * 100 : 0;
    const high = Math.max(...filteredBars.map(b => b.high ?? b.close ?? 0));
    const low = Math.min(...filteredBars.map(b => b.low ?? b.close ?? 9999999));
    return {
      diff,
      diffPct,
      high,
      low,
      isPositive: diff >= 0,
    };
  }, [filteredBars]);

  const activeBar = hoveredBarIndex != null ? filteredBars[hoveredBarIndex] : null;

  function copyMarkdownSummary() {
    if (!data) return;
    const stats = data.financial_stats;
    const text = [
      `# 📈 ${data.long_name} (${data.symbol})`,
      `> Cotation en direct EOD : **${data.price} ${data.currency}** (${data.change_percent ? (data.change_percent >= 0 ? "+" : "") + data.change_percent.toFixed(2) + "%" : "N/A"})`,
      "",
      `### 📊 Valorisation & Multiples (Yahoo Finance)`,
      `- Capitalisation : ${stats.valuation.market_cap || "N/A"}`,
      `- Ratio P/E actuel : ${stats.valuation.pe_trailing || "N/A"} (Forward : ${stats.valuation.pe_forward || "N/A"})`,
      `- Ratio PEG : ${stats.valuation.peg_ratio || "N/A"} · P/B : ${stats.valuation.price_to_book || "N/A"}`,
      `- EV/EBITDA : ${stats.valuation.ev_to_ebitda || "N/A"} · Bêta : ${stats.valuation.beta || "N/A"}`,
      `- Dividende : ${stats.valuation.dividend_yield || "N/A"} (annuel : ${stats.valuation.dividend_rate || "N/A"})`,
      "",
      `### 💰 Rentabilité & Résultats`,
      `- Chiffre d'affaires : ${stats.profitability.total_revenue || "N/A"} (${stats.profitability.revenue_growth || "N/A"})`,
      `- Marge brute : ${stats.profitability.gross_margin || "N/A"} · Marge nette : ${stats.profitability.profit_margin || "N/A"}`,
      `- EBITDA : ${stats.profitability.ebitda || "N/A"}`,
      `- Free Cash Flow : ${stats.profitability.free_cashflow || "N/A"}`,
      "",
      `### 🎯 Consensus des Analystes`,
      `- Recommandation : ${stats.analysts.recommendation || "N/A"}`,
      `- Objectif moyen : ${stats.analysts.target_mean || "N/A"} (Haut : ${stats.analysts.target_high || "N/A"} / Bas : ${stats.analysts.target_low || "N/A"})`,
      `- Potentiel estimé : ${stats.analysts.upside_potential_pct != null ? (stats.analysts.upside_potential_pct >= 0 ? "+" : "") + stats.analysts.upside_potential_pct.toFixed(2) + "%" : "N/A"}`,
    ].join("\n");

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  }

  function insertIntoChat() {
    if (!data || !onInsertIntoChat) return;
    const summary = `Donne-moi une analyse détaillée de l'action **${data.long_name}** (${data.symbol}) avec son cours actuel (${data.price} ${data.currency}) et ses données financières clés.`;
    onInsertIntoChat(summary);
    onClose();
  }

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop finance-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-container finance-modal-container"
        onClick={e => e.stopPropagation()}
        aria-label="Tableau de bord financier & Courbe de cours"
      >
        {/* Header */}
        <div className="finance-modal-header">
          <div className="finance-modal-title-wrap">
            <span className="finance-modal-badge-icon">
              <LineChart size={20} />
            </span>
            <div>
              <div className="finance-modal-title-row">
                <h2>{data?.short_name || "Analyse Boursière"}</h2>
                {data?.symbol && <span className="finance-symbol-tag">{data.symbol}</span>}
                <div className="finance-source-pills">
                  <span className="finance-live-pill is-eod" title="Cotations en direct et historique de marché">
                    EOD Historical Data
                  </span>
                  <span className="finance-live-pill is-yahoo" title="États financiers, valorisation et consensus">
                    Yahoo Finance
                  </span>
                </div>
              </div>
              <p className="finance-modal-sub">
                {data?.long_name
                  ? `${data.long_name} · Marché : ${data.exchange}${data.isin ? ` · ISIN : ${data.isin}` : ""}`
                  : "Cours de bourse en temps réel & données financières complètes"}
              </p>
            </div>
          </div>

          <div className="finance-modal-header-actions">
            <button
              type="button"
              className="modal-close-btn"
              onClick={onClose}
              aria-label="Fermer la modale"
              title="Fermer (Échap)"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Search & Suggestions Bar */}
        <div className="finance-modal-search-bar">
          <form className="finance-search-form" onSubmit={handleSearchSubmit}>
            <Search size={16} className="finance-search-icon" />
            <input
              type="text"
              className="finance-search-input"
              placeholder="Rechercher une action ou ticker (ex. Air Liquide, LVMH, AAPL, Tesla, NVDA)..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              disabled={loading}
            />
            <button type="submit" className="finance-search-submit" disabled={loading || !query.trim()}>
              {loading ? <LoaderCircle size={15} className="spin" /> : "Rechercher"}
            </button>
          </form>

          <div className="finance-quick-chips">
            <span className="finance-chips-label">Suggestions :</span>
            {QUICK_SUGGESTIONS.map(name => (
              <button
                key={name}
                type="button"
                className={`finance-chip ${data?.short_name?.toLowerCase().includes(name.toLowerCase()) ? "active" : ""}`}
                onClick={() => {
                  setQuery(name);
                  void loadDetails(name);
                }}
                disabled={loading}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        {/* Modal Body */}
        <div className="finance-modal-body">
          {error && (
            <div className="finance-modal-error" role="alert">
              <span>⚠️ {error}</span>
              <button type="button" onClick={() => void loadDetails(query)}>
                <RefreshCw size={14} /> Réessayer
              </button>
            </div>
          )}

          {loading && !data && (
            <div className="finance-modal-loading">
              <LoaderCircle size={36} className="spin text-emerald" />
              <p>Téléchargement des cours live (EOD) et des états financiers (Yahoo Finance)…</p>
            </div>
          )}

          {data && (
            <>
              {/* Live Quote Hero Banner */}
              <div className="finance-hero-banner">
                <div className="finance-hero-left">
                  <div className="finance-price-row">
                    <span className="finance-hero-price">
                      {data.price != null ? data.price.toFixed(2) : "N/A"}{" "}
                      <small className="finance-hero-curr">{data.currency}</small>
                    </span>
                    {data.change_percent != null && (
                      <span
                        className={`finance-hero-change ${data.change_percent >= 0 ? "is-up" : "is-down"}`}
                      >
                        {data.change_percent >= 0 ? (
                          <ArrowUpRight size={18} />
                        ) : (
                          <ArrowDownRight size={18} />
                        )}
                        <span>
                          {data.change ? `${data.change >= 0 ? "+" : ""}${data.change.toFixed(2)} ` : ""}
                          ({data.change_percent >= 0 ? "+" : ""}
                          {data.change_percent.toFixed(2)}%)
                        </span>
                      </span>
                    )}
                  </div>
                  <div className="finance-hero-sub-stats">
                    <span>
                      Ouv. : <strong>{data.open != null ? data.open.toFixed(2) : "-"}</strong>
                    </span>
                    <span>·</span>
                    <span>
                      Haut : <strong>{data.high != null ? data.high.toFixed(2) : "-"}</strong>
                    </span>
                    <span>·</span>
                    <span>
                      Bas : <strong>{data.low != null ? data.low.toFixed(2) : "-"}</strong>
                    </span>
                    <span>·</span>
                    <span>
                      Volume :{" "}
                      <strong>
                        {data.volume != null ? data.volume.toLocaleString("fr-FR") : "-"}
                      </strong>
                    </span>
                    <span>·</span>
                    <span>
                      Clôt. veille :{" "}
                      <strong>
                        {data.previous_close != null ? data.previous_close.toFixed(2) : "-"}
                      </strong>
                    </span>
                  </div>
                </div>

                <div className="finance-hero-right">
                  <div className="finance-analyst-badge-hero">
                    <span className="finance-analyst-hero-label">Consensus Analystes</span>
                    <strong className="finance-analyst-hero-rec">
                      {data.financial_stats.analysts.recommendation || "N/A"}
                    </strong>
                    {data.financial_stats.analysts.target_mean && (
                      <span className="finance-analyst-hero-target">
                        Obj. : {data.financial_stats.analysts.target_mean} {data.currency}
                        {data.financial_stats.analysts.upside_potential_pct != null && (
                          <small
                            className={
                              data.financial_stats.analysts.upside_potential_pct >= 0
                                ? "text-emerald"
                                : "text-rose"
                            }
                          >
                            {" "}
                            (
                            {data.financial_stats.analysts.upside_potential_pct >= 0 ? "+" : ""}
                            {data.financial_stats.analysts.upside_potential_pct.toFixed(1)}%)
                          </small>
                        )}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Section 1: Courbe interactive du cours via EOD */}
              <div className="finance-chart-section">
                <div className="finance-chart-header">
                  <div className="finance-chart-title">
                    <span className="chart-icon-wrap">
                      <TrendingUp size={16} />
                    </span>
                    <div>
                      <strong>Courbe du cours (EOD Historical Data)</strong>
                      <small>
                        {filteredBars.length} séances journalières ·{" "}
                        {timeframeStats ? (
                          <span className={timeframeStats.isPositive ? "text-emerald" : "text-rose"}>
                            {timeframeStats.diff >= 0 ? "+" : ""}
                            {timeframeStats.diff.toFixed(2)} {data.currency} (
                            {timeframeStats.diffPct >= 0 ? "+" : ""}
                            {timeframeStats.diffPct.toFixed(2)}%)
                          </span>
                        ) : (
                          "Données historiques de cotation"
                        )}
                      </small>
                    </div>
                  </div>

                  <div className="finance-timeframe-selector">
                    {(["1S", "2S", "1M", "ALL"] as const).map(tf => (
                      <button
                        key={tf}
                        type="button"
                        className={`finance-tf-btn ${timeframe === tf ? "active" : ""}`}
                        onClick={() => {
                          setTimeframe(tf);
                          setHoveredBarIndex(null);
                        }}
                      >
                        {tf === "1S"
                          ? "1 Sem."
                          : tf === "2S"
                          ? "2 Sem."
                          : tf === "1M"
                          ? "1 Mois"
                          : "Max"}
                      </button>
                    ))}
                  </div>
                </div>

                {/* SVG Price Chart */}
                <div className="finance-svg-chart-container">
                  {filteredBars.length >= 2 ? (
                    <InteractivePriceChart
                      bars={filteredBars}
                      currency={data.currency}
                      hoveredIndex={hoveredBarIndex}
                      onHover={setHoveredBarIndex}
                    />
                  ) : (
                    <div className="finance-chart-empty">
                      <span>Données de courbe insuffisantes pour cette sélection</span>
                    </div>
                  )}

                  {/* Active Bar Hover Details Card */}
                  {activeBar && (
                    <div className="finance-chart-hover-pill">
                      <span>📅 {activeBar.date}</span>
                      <span>·</span>
                      <span>
                        Clôture : <strong>{activeBar.close?.toFixed(2)} {data.currency}</strong>
                      </span>
                      <span>·</span>
                      <span>Ouv. : {activeBar.open?.toFixed(2)}</span>
                      <span>·</span>
                      <span>Haut : {activeBar.high?.toFixed(2)}</span>
                      <span>·</span>
                      <span>Bas : {activeBar.low?.toFixed(2)}</span>
                      {activeBar.volume && (
                        <>
                          <span>·</span>
                          <span>Vol. : {activeBar.volume.toLocaleString("fr-FR")}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Section 2: Navigation par onglets des statistiques financières complètes */}
              <div className="finance-stats-section">
                <div className="finance-tabs-nav">
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "valuation" ? "active" : ""}`}
                    onClick={() => setActiveTab("valuation")}
                  >
                    <Target size={15} />
                    <span>Valorisation & Multiples</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "profitability" ? "active" : ""}`}
                    onClick={() => setActiveTab("profitability")}
                  >
                    <TrendingUp size={15} />
                    <span>Rentabilité & CA</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "balance_sheet" ? "active" : ""}`}
                    onClick={() => setActiveTab("balance_sheet")}
                  >
                    <Wallet size={15} />
                    <span>Bilan & Trésorerie</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "analysts" ? "active" : ""}`}
                    onClick={() => setActiveTab("analysts")}
                  >
                    <Sparkles size={15} />
                    <span>Consensus Analystes</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "history" ? "active" : ""}`}
                    onClick={() => setActiveTab("history")}
                  >
                    <Calendar size={15} />
                    <span>Séances EOD ({data.eod_bars.length})</span>
                  </button>
                  <button
                    type="button"
                    className={`finance-tab-btn ${activeTab === "profile" ? "active" : ""}`}
                    onClick={() => setActiveTab("profile")}
                  >
                    <Building2 size={15} />
                    <span>Profil Entreprise</span>
                  </button>
                </div>

                {/* Tab 1: Valorisation & Multiples */}
                {activeTab === "valuation" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table">
                        <thead>
                          <tr>
                            <th>Indicateur boursier</th>
                            <th>Valeur déclarée</th>
                            <th>Explication / Rôle</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><strong>Capitalisation boursière</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.market_cap || "N/A"}</span></td>
                            <td className="finance-metric-desc">Valeur totale de l'entreprise sur les marchés d'actions</td>
                          </tr>
                          <tr>
                            <td><strong>Ratio C/B actuel (Trailing P/E)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.pe_trailing || "N/A"}</span></td>
                            <td className="finance-metric-desc">Cours rapporté au bénéfice net par action des 12 derniers mois</td>
                          </tr>
                          <tr>
                            <td><strong>Ratio C/B prévisionnel (Forward P/E)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.pe_forward || "N/A"}</span></td>
                            <td className="finance-metric-desc">Cours rapporté aux bénéfices futurs estimés par le consensus</td>
                          </tr>
                          <tr>
                            <td><strong>Ratio PEG (Price/Earnings-to-Growth)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.peg_ratio || "N/A"}</span></td>
                            <td className="finance-metric-desc">P/E pondéré par la croissance attendue (&lt; 1 indique une sous-évaluation)</td>
                          </tr>
                          <tr>
                            <td><strong>Price-to-Book (P/B)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.price_to_book || "N/A"}</span></td>
                            <td className="finance-metric-desc">Rapport entre le cours et la valeur comptable nette par action</td>
                          </tr>
                          <tr>
                            <td><strong>Valeur d'Entreprise / EBITDA (EV/EBITDA)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.ev_to_ebitda || "N/A"}</span></td>
                            <td className="finance-metric-desc">Multiple d'acquisition opérationnel, indépendant de la structure de dette</td>
                          </tr>
                          <tr>
                            <td><strong>Bêta (volatilité)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.beta || "N/A"}</span></td>
                            <td className="finance-metric-desc">Sensibilité aux mouvements du marché (1.0 = identique à l'indice)</td>
                          </tr>
                          <tr>
                            <td><strong>Bénéfice par action (BPA Trailing / Forward)</strong></td>
                            <td>
                              <span className="finance-metric-val">
                                {data.financial_stats.valuation.trailing_eps || "N/A"}{" "}
                                <small>({data.financial_stats.valuation.forward_eps ? `futur : ${data.financial_stats.valuation.forward_eps}` : ""})</small>
                              </span>
                            </td>
                            <td className="finance-metric-desc">Quote-part de bénéfice net revenant à chaque action ordinaire</td>
                          </tr>
                          <tr>
                            <td><strong>Rendement du dividende</strong></td>
                            <td>
                              <span className="finance-metric-val text-emerald">
                                {data.financial_stats.valuation.dividend_yield || "N/A"}{" "}
                                {data.financial_stats.valuation.dividend_rate ? `(${data.financial_stats.valuation.dividend_rate} ${data.currency})` : ""}
                              </span>
                            </td>
                            <td className="finance-metric-desc">Rémunération annuelle de l'actionnaire en dividende</td>
                          </tr>
                          <tr>
                            <td><strong>Taux de distribution (Payout Ratio)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.valuation.payout_ratio || "N/A"}</span></td>
                            <td className="finance-metric-desc">Part des bénéfices nets redistribuée aux actionnaires</td>
                          </tr>
                          <tr>
                            <td><strong>Fourchette 52 semaines</strong></td>
                            <td>
                              <span className="finance-metric-val">
                                {data.financial_stats.valuation.w52_low || "N/A"} - {data.financial_stats.valuation.w52_high || "N/A"} {data.currency}
                              </span>
                            </td>
                            <td className="finance-metric-desc">Plus bas et plus haut cours enregistrés sur un an glissant</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Tab 2: Rentabilité & CA */}
                {activeTab === "profitability" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table">
                        <thead>
                          <tr>
                            <th>Indicateur financier</th>
                            <th>Montant / Ratio déclaré</th>
                            <th>Signification</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><strong>Chiffre d'affaires (Total Revenue)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.total_revenue || "N/A"}</span></td>
                            <td className="finance-metric-desc">Revenus globaux déclarés sur l'exercice</td>
                          </tr>
                          <tr>
                            <td><strong>Croissance du chiffre d'affaires</strong></td>
                            <td>
                              <span className={`finance-metric-val ${data.financial_stats.profitability.revenue_growth?.startsWith("+") ? "text-emerald" : ""}`}>
                                {data.financial_stats.profitability.revenue_growth || "N/A"}
                              </span>
                            </td>
                            <td className="finance-metric-desc">Progression annuelle des ventes en rythme annuel</td>
                          </tr>
                          <tr>
                            <td><strong>Marge brute (Gross Margin)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.gross_margin || "N/A"}</span></td>
                            <td className="finance-metric-desc">Revenus déduits du coût direct des ventes</td>
                          </tr>
                          <tr>
                            <td><strong>Marge opérationnelle (Operating Margin)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.operating_margin || "N/A"}</span></td>
                            <td className="finance-metric-desc">Résultat d'exploitation rapporté au chiffre d'affaires</td>
                          </tr>
                          <tr>
                            <td><strong>Marge nette (Profit Margin)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.profit_margin || "N/A"}</span></td>
                            <td className="finance-metric-desc">Rentabilité finale après impôts, intérêts et charges</td>
                          </tr>
                          <tr>
                            <td><strong>EBITDA (Résultat opérationnel brut)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.ebitda || "N/A"}</span></td>
                            <td className="finance-metric-desc">Bénéfice avant intérêts, impôts, dépréciations et amortissements</td>
                          </tr>
                          <tr>
                            <td><strong>Bénéfice net attribuable (Net Income)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.net_income || "N/A"}</span></td>
                            <td className="finance-metric-desc">Bénéfice net consolidé part du groupe</td>
                          </tr>
                          <tr>
                            <td><strong>Rentabilité des capitaux propres (ROE)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.roe || "N/A"}</span></td>
                            <td className="finance-metric-desc">Efficacité avec laquelle la société réinvestit les capitaux actionnaires</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Tab 3: Bilan & Trésorerie */}
                {activeTab === "balance_sheet" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table">
                        <thead>
                          <tr>
                            <th>Poste de Bilan / Flux</th>
                            <th>Montant</th>
                            <th>Analyse</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><strong>Flux de trésorerie disponible (Free Cash Flow)</strong></td>
                            <td><span className="finance-metric-val text-emerald">{data.financial_stats.balance_sheet.total_cash || data.financial_stats.profitability.free_cashflow || "N/A"}</span></td>
                            <td className="finance-metric-desc">Trésorerie nette générée après investissements matériels (CAPEX)</td>
                          </tr>
                          <tr>
                            <td><strong>Flux de trésorerie d'exploitation</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.profitability.operating_cashflow || "N/A"}</span></td>
                            <td className="finance-metric-desc">Trésorerie opérationnelle tirée de l'activité courante</td>
                          </tr>
                          <tr>
                            <td><strong>Trésorerie totale disponible (Cash)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.total_cash || "N/A"}</span></td>
                            <td className="finance-metric-desc">Liquidités et équivalents de trésorerie au bilan</td>
                          </tr>
                          <tr>
                            <td><strong>Dette totale déclarée</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.total_debt || "N/A"}</span></td>
                            <td className="finance-metric-desc">Ensemble des dettes financières à court et long terme</td>
                          </tr>
                          <tr>
                            <td><strong>Ratio Dette / Fonds propres (Debt-to-Equity)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.debt_to_equity || "N/A"}</span></td>
                            <td className="finance-metric-desc">Niveau d'endettement par rapport aux capitaux propres de la société</td>
                          </tr>
                          <tr>
                            <td><strong>Ratio de liquidité générale (Current Ratio)</strong></td>
                            <td><span className="finance-metric-val">{data.financial_stats.balance_sheet.current_ratio || "N/A"}</span></td>
                            <td className="finance-metric-desc">Capacité à rembourser les dettes à court terme (&gt; 1.0 est sain)</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Tab 4: Consensus Analystes */}
                {activeTab === "analysts" && (
                  <div className="finance-tab-content">
                    <div className="finance-analyst-cards-grid">
                      <div className="finance-analyst-card-highlight">
                        <span className="card-kpi-label">Recommandation du Marché</span>
                        <div className="card-kpi-badge-row">
                          <span className="recommendation-badge">{data.financial_stats.analysts.recommendation || "N/A"}</span>
                          {data.financial_stats.analysts.opinions_count && (
                            <small className="analysts-count-tag">{data.financial_stats.analysts.opinions_count} analystes suivis</small>
                          )}
                        </div>
                      </div>

                      <div className="finance-analyst-card">
                        <span className="card-kpi-label">Objectif Moyen</span>
                        <strong className="card-kpi-value text-emerald">
                          {data.financial_stats.analysts.target_mean ? `${data.financial_stats.analysts.target_mean} ${data.currency}` : "N/A"}
                        </strong>
                        {data.financial_stats.analysts.upside_potential_pct != null && (
                          <span className={`kpi-upside-badge ${data.financial_stats.analysts.upside_potential_pct >= 0 ? "is-up" : "is-down"}`}>
                            Potentiel : {data.financial_stats.analysts.upside_potential_pct >= 0 ? "+" : ""}{data.financial_stats.analysts.upside_potential_pct.toFixed(2)}%
                          </span>
                        )}
                      </div>

                      <div className="finance-analyst-card">
                        <span className="card-kpi-label">Objectif le plus haut</span>
                        <strong className="card-kpi-value">
                          {data.financial_stats.analysts.target_high ? `${data.financial_stats.analysts.target_high} ${data.currency}` : "N/A"}
                        </strong>
                        <small className="card-kpi-hint">Hypothèse haussière maximale</small>
                      </div>

                      <div className="finance-analyst-card">
                        <span className="card-kpi-label">Objectif le plus bas</span>
                        <strong className="card-kpi-value">
                          {data.financial_stats.analysts.target_low ? `${data.financial_stats.analysts.target_low} ${data.currency}` : "N/A"}
                        </strong>
                        <small className="card-kpi-hint">Hypothèse baissière minimale</small>
                      </div>
                    </div>
                  </div>
                )}

                {/* Tab 5: Historique des séances EOD */}
                {activeTab === "history" && (
                  <div className="finance-tab-content">
                    <div className="finance-table-wrapper">
                      <table className="finance-data-table finance-history-table">
                        <thead>
                          <tr>
                            <th>Date séance</th>
                            <th>Clôture</th>
                            <th>Variation</th>
                            <th>Ouverture</th>
                            <th>Plus haut</th>
                            <th>Plus bas</th>
                            <th>Volume d'échanges</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.eod_bars.length === 0 ? (
                            <tr>
                              <td colSpan={7} className="text-center">Aucun historique disponible</td>
                            </tr>
                          ) : (
                            [...data.eod_bars].reverse().map((bar, idx, arr) => {
                              const prevClose = idx + 1 < arr.length ? arr[idx + 1].close : null;
                              const diff = bar.close != null && prevClose != null ? bar.close - prevClose : null;
                              const diffPct = diff != null && prevClose ? (diff / prevClose) * 100 : null;
                              return (
                                <tr key={bar.date}>
                                  <td><strong>{bar.date}</strong></td>
                                  <td><strong>{bar.close?.toFixed(2)} {data.currency}</strong></td>
                                  <td>
                                    {diffPct != null ? (
                                      <span className={diffPct >= 0 ? "text-emerald" : "text-rose"}>
                                        {diffPct >= 0 ? "+" : ""}{diffPct.toFixed(2)}%
                                      </span>
                                    ) : (
                                      "—"
                                    )}
                                  </td>
                                  <td>{bar.open?.toFixed(2) || "-"}</td>
                                  <td>{bar.high?.toFixed(2) || "-"}</td>
                                  <td>{bar.low?.toFixed(2) || "-"}</td>
                                  <td>{bar.volume != null ? bar.volume.toLocaleString("fr-FR") : "-"}</td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Tab 6: Profil de l'entreprise */}
                {activeTab === "profile" && (
                  <div className="finance-tab-content">
                    <div className="finance-profile-card">
                      <div className="finance-profile-grid">
                        <div>
                          <span className="profile-label">Secteur d'activité</span>
                          <strong>{data.financial_stats.profile.sector || "N/A"}</strong>
                        </div>
                        <div>
                          <span className="profile-label">Industrie</span>
                          <strong>{data.financial_stats.profile.industry || "N/A"}</strong>
                        </div>
                        <div>
                          <span className="profile-label">Siège social / Pays</span>
                          <strong>{data.financial_stats.profile.country || "N/A"}</strong>
                        </div>
                        <div>
                          <span className="profile-label">Effectif déclaré</span>
                          <strong>{data.financial_stats.profile.employees || "Non communiqué"}</strong>
                        </div>
                      </div>

                      {data.financial_stats.profile.website && (
                        <div className="finance-profile-site">
                          <span className="profile-label">Site officiel :</span>
                          <a
                            href={data.financial_stats.profile.website}
                            target="_blank"
                            rel="noreferrer"
                            className="site-link"
                          >
                            <span>{data.financial_stats.profile.website}</span>
                            <ExternalLink size={12} />
                          </a>
                        </div>
                      )}

                      {data.financial_stats.profile.summary && (
                        <div className="finance-profile-desc">
                          <span className="profile-label">Activité & Positionnement stratégique :</span>
                          <p>{data.financial_stats.profile.summary}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer actions */}
        <div className="finance-modal-footer">
          <div className="finance-footer-left">
            {data?.url_eod && (
              <a
                href={data.url_eod}
                target="_blank"
                rel="noreferrer"
                className="finance-external-link is-eod"
                title="Consulter la fiche officielle sur EOD Historical Data"
              >
                <span>Fiche EODHD</span>
                <ExternalLink size={12} />
              </a>
            )}
            {data?.url_yahoo && (
              <a
                href={data.url_yahoo}
                target="_blank"
                rel="noreferrer"
                className="finance-external-link is-yahoo"
                title="Consulter la fiche officielle sur Yahoo Finance"
              >
                <span>Fiche Yahoo Finance</span>
                <ExternalLink size={12} />
              </a>
            )}
          </div>

          <div className="finance-footer-right">
            <button
              type="button"
              className="finance-copy-btn"
              onClick={copyMarkdownSummary}
              disabled={!data}
              title="Copier la synthèse financière au format Markdown"
            >
              {copied ? <Check size={14} className="text-emerald" /> : <Copy size={14} />}
              <span>{copied ? "Rapport copié !" : "Copier le rapport"}</span>
            </button>

            {onInsertIntoChat && (
              <button
                type="button"
                className="finance-insert-btn"
                onClick={insertIntoChat}
                disabled={!data}
                title="Poser une question sur cette action dans la discussion courante"
              >
                <MessageSquarePlus size={14} />
                <span>Poser une question à l'IA</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Interactive SVG Line & Area Chart for Stock Price history
 */
function InteractivePriceChart({
  bars,
  currency,
  hoveredIndex,
  onHover,
}: {
  bars: EodBar[];
  currency: string;
  hoveredIndex: number | null;
  onHover: (idx: number | null) => void;
}) {
  const width = 800;
  const height = 220;
  const paddingX = 40;
  const paddingY = 24;

  const validPoints = useMemo(() => {
    return bars
      .map((b, i) => ({
        index: i,
        date: b.date,
        price: b.close ?? 0,
        high: b.high ?? b.close ?? 0,
        low: b.low ?? b.close ?? 0,
        volume: b.volume ?? 0,
      }))
      .filter(p => p.price > 0);
  }, [bars]);

  if (validPoints.length < 2) return null;

  const minPrice = Math.min(...validPoints.map(p => p.price));
  const maxPrice = Math.max(...validPoints.map(p => p.price));
  const priceRange = maxPrice - minPrice || 1;

  const chartW = width - paddingX * 2;
  const chartH = height - paddingY * 2;

  const isUp = validPoints[validPoints.length - 1].price >= validPoints[0].price;
  const strokeColor = isUp ? "#10b981" : "#f43f5e";
  const gradientId = isUp ? "emeraldGradient" : "roseGradient";

  // Coordinates mapping
  const points = validPoints.map((p, i) => {
    const x = paddingX + (i / (validPoints.length - 1)) * chartW;
    const y = height - paddingY - ((p.price - minPrice) / priceRange) * chartH;
    return { ...p, x, y };
  });

  const pathD = points.reduce((acc, pt, i) => {
    return i === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`;
  }, "");

  const areaD = `${pathD} L ${points[points.length - 1].x} ${height - paddingY} L ${points[0].x} ${height - paddingY} Z`;

  // Grid levels (3 horizontal lines)
  const gridLevels = [
    { label: maxPrice.toFixed(2), y: paddingY },
    { label: ((maxPrice + minPrice) / 2).toFixed(2), y: height / 2 },
    { label: minPrice.toFixed(2), y: height - paddingY },
  ];

  return (
    <div className="finance-svg-wrapper">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="finance-chart-svg"
        onMouseLeave={() => onHover(null)}
      >
        <defs>
          <linearGradient id="emeraldGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
          </linearGradient>
          <linearGradient id="roseGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Grid Lines */}
        {gridLevels.map((g, i) => (
          <g key={i}>
            <line
              x1={paddingX}
              y1={g.y}
              x2={width - paddingX}
              y2={g.y}
              stroke="var(--line, rgba(148, 163, 184, 0.2))"
              strokeDasharray="4 4"
            />
            <text
              x={width - paddingX + 6}
              y={g.y + 4}
              fontSize="10"
              fill="var(--muted, #94a3b8)"
              fontFamily="sans-serif"
            >
              {g.label}
            </text>
          </g>
        ))}

        {/* Area fill */}
        <path d={areaD} fill={`url(#${gradientId})`} />

        {/* Main Price Line */}
        <path
          d={pathD}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Interactive hover crosshair and dots */}
        {points.map((pt, i) => {
          const isHovered = hoveredIndex === i;
          return (
            <g
              key={i}
              className="chart-point-group"
              onMouseEnter={() => onHover(i)}
              style={{ cursor: "pointer" }}
            >
              {/* Invisible wide hit area */}
              <rect
                x={pt.x - chartW / points.length / 2}
                y={0}
                width={chartW / points.length}
                height={height}
                fill="transparent"
              />

              {isHovered && (
                <>
                  <line
                    x1={pt.x}
                    y1={paddingY}
                    x2={pt.x}
                    y2={height - paddingY}
                    stroke="var(--text, #334155)"
                    strokeWidth="1.5"
                    strokeDasharray="3 3"
                    opacity="0.6"
                  />
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="5"
                    fill={strokeColor}
                    stroke="#ffffff"
                    strokeWidth="2.5"
                  />
                </>
              )}
            </g>
          );
        })}

        {/* Start and end points */}
        <circle cx={points[0].x} cy={points[0].y} r="3.5" fill={strokeColor} opacity="0.8" />
        <circle
          cx={points[points.length - 1].x}
          cy={points[points.length - 1].y}
          r="4.5"
          fill={strokeColor}
        />
      </svg>
    </div>
  );
}

