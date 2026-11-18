"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  MessageSquarePlus,
  Search,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";

import { FinanceMetricLabel } from "@/components/finance-info-tip";
import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  analyzeStockMoat,
  deleteStockMoat,
  fetchStockMoats,
  type FinancialStats,
  type MoatQuantitativeSignal,
  type StockMoatAnalysis,
} from "@/lib/api";

type FinanceMoatPanelProps = {
  symbol: string;
  companyName: string;
  financialStats: FinancialStats;
  onInsertIntoChat?: (text: string) => void;
};

const RATING_LABELS: Record<StockMoatAnalysis["moat_rating"], { label: string; cls: string }> = {
  wide: { label: "MOAT Large (Avantage durable)", cls: "is-wide" },
  narrow: { label: "MOAT Étroit (Avantage partiel)", cls: "is-narrow" },
  none: { label: "Pas de MOAT net", cls: "is-none" },
};

const PILLAR_STATUS_LABELS: Record<"strong" | "moderate" | "absent", { label: string; cls: string }> = {
  strong: { label: "Fort", cls: "is-strong" },
  moderate: { label: "Modéré", cls: "is-moderate" },
  absent: { label: "Absent", cls: "is-absent" },
};

function parsePctMetric(raw?: string): number | null {
  if (!raw) return null;
  const cleaned = raw.replace(/\s+/g, "").replace(",", ".").replace(/[%xX$€£]+$/, "");
  const match = cleaned.match(/-?\d+(?:\.\d+)?/);
  if (!match) return null;
  const num = Number(match[0]);
  return Number.isFinite(num) ? num : null;
}

function buildLocalQuantitativeSignals(stats: FinancialStats): MoatQuantitativeSignal[] {
  const signals: MoatQuantitativeSignal[] = [];
  const prof = stats?.profitability || {};
  const bs = stats?.balance_sheet || {};

  const pushPct = (
    label: string,
    raw: string | undefined,
    high: number,
    mid: number,
    highMsg: string,
    midMsg: string,
    lowMsg: string,
  ) => {
    const val = parsePctMetric(raw);
    if (val == null || !raw) return;
    const verdict: MoatQuantitativeSignal["verdict"] =
      val >= high ? "favorable" : val >= mid ? "neutral" : "weak";
    signals.push({
      label,
      value: raw,
      verdict,
      reason: verdict === "favorable" ? highMsg : verdict === "neutral" ? midMsg : lowMsg,
    });
  };

  pushPct(
    "Marge brute",
    prof.gross_margin,
    40,
    25,
    "Pricing power marqué",
    "Pricing power modéré",
    "Marge brute exposée à la concurrence",
  );
  pushPct(
    "Marge opérationnelle",
    prof.operating_margin,
    18,
    8,
    "Levier opérationnel élevé",
    "Rentabilité d'exploitation intermédiaire",
    "Marge opérationnelle faible ou comprimée",
  );
  pushPct(
    "ROE",
    prof.roe,
    16,
    9,
    "Rendement élevé sur capitaux propres",
    "Rendement dans la moyenne sectorielle",
    "Rendement des capitaux modeste",
  );
  pushPct(
    "ROA",
    prof.roa,
    8,
    4,
    "Forte productivité des actifs",
    "Productivité correcte des actifs",
    "Forte intensité capitalistique",
  );
  pushPct(
    "Croissance CA",
    prof.revenue_growth,
    8,
    0,
    "Traction commerciale soutenue",
    "Parts de marché stables",
    "Chiffre d'affaires en repli",
  );

  const de = parsePctMetric(bs.debt_to_equity);
  if (de != null && bs.debt_to_equity) {
    const verdict: MoatQuantitativeSignal["verdict"] =
      de <= 60 ? "favorable" : de <= 130 ? "neutral" : "weak";
    signals.push({
      label: "Dette / Capitaux propres",
      value: bs.debt_to_equity,
      verdict,
      reason:
        verdict === "favorable"
          ? "Bilan peu endetté"
          : verdict === "neutral"
            ? "Levier modéré"
            : "Endettement élevé à surveiller",
    });
  }

  return signals;
}

export function FinanceMoatPanel({
  symbol,
  companyName,
  financialStats,
  onInsertIntoChat,
}: FinanceMoatPanelProps) {
  const [items, setItems] = useState<StockMoatAnalysis[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [customFocus, setCustomFocus] = useState("");
  const [error, setError] = useState<string | null>(null);

  const localSignals = useMemo(
    () => buildLocalQuantitativeSignals(financialStats),
    [financialStats],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadMoats() {
      setLoading(true);
      setError(null);
      try {
        const list = await fetchStockMoats(symbol);
        if (!cancelled) setItems(list);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Impossible de charger l'historique des analyses MOAT.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadMoats();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function handleAnalyze(e: React.FormEvent) {
    e.preventDefault();
    if (analyzing) return;
    setAnalyzing(true);
    setError(null);
    try {
      const created = await analyzeStockMoat({
        symbol,
        company_name: companyName,
        custom_focus: customFocus.trim(),
        financial_stats: financialStats,
      });
      setItems(prev => [created, ...prev]);
      setCustomFocus("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "L'analyse MOAT a échoué.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function handleDelete(moatId: string) {
    try {
      await deleteStockMoat(moatId);
      setItems(prev => prev.filter(item => item.id !== moatId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  function sendMoatToChat(entry: StockMoatAnalysis) {
    if (!onInsertIntoChat) return;
    const ratingInfo = RATING_LABELS[entry.moat_rating] || RATING_LABELS.narrow;
    const lines = [
      `Analyse MOAT de **${entry.company_name} (${entry.symbol})** — Verdict : **${ratingInfo.label}** (${entry.moat_score}/100)`,
      "",
      "**Facteurs favorables (MOAT) :**",
      ...entry.strengths.map(s => `- ${s}`),
      "",
      "**Facteurs défavorables / Risques d'érosion :**",
      ...entry.weaknesses.map(w => `- ${w}`),
      "",
      entry.summary_markdown,
    ];
    onInsertIntoChat(lines.join("\n"));
  }

  function triggerSectorScanInChat() {
    if (!onInsertIntoChat) return;
    const sector = financialStats?.profile?.sector || financialStats?.profile?.industry || companyName || symbol;
    onInsertIntoChat(
      `Fonction "Scan de Moats" (Analyste en Investissement Stratégique — Buffett/Dalio/McKinsey) : ` +
        `Scanne le secteur "${sector}" (incluant ${companyName} / ${symbol}) et identifie jusqu'à 10 entreprises ` +
        `qui possèdent un moat durable, sous forme de tableau | Entreprise | Type de Moat | Justification Courte |.`,
    );
  }

  function triggerCompareInChat() {
    if (!onInsertIntoChat) return;
    const sector = financialStats?.profile?.industry || financialStats?.profile?.sector || "";
    onInsertIntoChat(
      `Fonction "Analyse Comparative Stratégique" (3 entreprises max, cadre Buffett/Dalio/McKinsey) : ` +
        `Compare le MOAT de ${companyName} (${symbol})${sector ? ` avec ses 2 principaux concurrents du secteur "${sector}"` : " avec 2 concurrents majeurs"}, ` +
        `incluant Analyse Externe (PESTEL), Analyse Interne (Fonctions), les deux tableaux Risques & FCS (priorité Élevée/Moyenne) et la Valorisation du moat.`,
    );
  }

  return (
    <div className="finance-tab-content finance-moat-panel">
      {/* Signaux quantitatifs instantanés */}
      {localSignals.length > 0 && (
        <div className="finance-moat-signals-box">
          <div className="finance-moat-signals-head">
            <Shield size={14} />
            <strong>Signaux financiers objectifs du MOAT ({symbol})</strong>
          </div>
          <div className="finance-moat-signals-grid">
            {localSignals.map(sig => (
              <div key={sig.label} className={`finance-moat-signal-chip is-${sig.verdict}`}>
                <div className="finance-moat-signal-top">
                  <FinanceMetricLabel label={sig.label} />
                  <strong>{sig.value}</strong>
                </div>
                <small>{sig.reason}</small>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Barre de lancement d'une analyse MOAT */}
      <form className="finance-panel-toolbar" onSubmit={handleAnalyze}>
        <div className="finance-panel-input-wrap">
          <Search size={14} className="finance-panel-input-icon" />
          <input
            type="text"
            value={customFocus}
            onChange={e => setCustomFocus(e.target.value)}
            placeholder={`Angle optionnel pour ${companyName || symbol} (ex. concurrence IA, brevets, pouvoir de prix)...`}
            disabled={analyzing}
          />
        </div>
        <button type="submit" className="finance-insert-btn" disabled={analyzing}>
          {analyzing ? <LoaderCircle size={14} className="spin" /> : <ShieldCheck size={14} />}
          <span>{analyzing ? "Analyse du MOAT…" : "Analyser le MOAT"}</span>
        </button>
      </form>

      {onInsertIntoChat && (
        <div className="finance-presets-bar">
          <span>Actions chat associées :</span>
          <button type="button" className="finance-chip" onClick={triggerSectorScanInChat}>
            Scanner le secteur{financialStats?.profile?.sector ? ` (${financialStats.profile.sector})` : ""}
          </button>
          <button type="button" className="finance-chip" onClick={triggerCompareInChat}>
            Comparer {symbol} vs concurrents (max 3)
          </button>
        </div>
      )}

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {loading && items.length === 0 ? (
        <div className="finance-panel-empty">
          <LoaderCircle size={22} className="spin text-emerald" />
          <p>Chargement des analyses MOAT…</p>
        </div>
      ) : items.length === 0 ? (
        <div className="finance-panel-empty">
          <ShieldAlert size={24} />
          <p>Aucune analyse MOAT enregistrée pour {symbol}.</p>
          <small>
            Cliquez sur « Analyser le MOAT » pour générer l&apos;étude stratégique complète sur les 7 sources de MOAT
            (avantage coûts, coûts de changement, effets de réseau, marque, réglementation, IP/actifs incorporels,
            échelle efficiente), la cartographie PESTEL &amp; interne (Risques vs Facteurs Clés de Succès) et la
            valorisation du moat.
          </small>
        </div>
      ) : (
        <div className="finance-archive-list">
          {items.map(entry => {
            const ratingInfo = RATING_LABELS[entry.moat_rating] || RATING_LABELS.narrow;
            return (
              <article key={entry.id} className="finance-archive-card finance-moat-card">
                <div className="finance-archive-card-head">
                  <div className="finance-archive-meta">
                    <span className={`finance-moat-rating-badge ${ratingInfo.cls}`}>
                      {ratingInfo.label}
                    </span>
                    <span className="finance-moat-score-pill">
                      Score : <strong>{entry.moat_score}/100</strong>
                    </span>
                    <span>
                      {new Date(entry.created_at).toLocaleString("fr-FR", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </span>
                  </div>
                  <div className="finance-archive-actions">
                    {onInsertIntoChat && (
                      <button
                        type="button"
                        className="finance-copy-btn"
                        onClick={() => sendMoatToChat(entry)}
                        title="Discuter de ce MOAT avec l'IA"
                      >
                        <MessageSquarePlus size={13} />
                        <span>Discuter</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="finance-wl-remove-btn"
                      onClick={() => void handleDelete(entry.id)}
                      title="Supprimer cette analyse MOAT"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {/* Facteurs POUR vs CONTRE un MOAT */}
                <div className="finance-moat-versus">
                  <div className="finance-moat-box is-pro">
                    <h4>
                      <CheckCircle2 size={14} />
                      <span>Facteurs qui FONT de l&apos;action un MOAT</span>
                    </h4>
                    <ul>
                      {entry.strengths.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div className="finance-moat-box is-con">
                    <h4>
                      <AlertTriangle size={14} />
                      <span>Facteurs qui N&apos;EN FONT PAS un MOAT / Risques</span>
                    </h4>
                    <ul>
                      {entry.weaknesses.map((w, idx) => (
                        <li key={idx}>{w}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Grille des 5 piliers */}
                {entry.pillars.length > 0 && (
                  <div className="finance-moat-pillars">
                    {entry.pillars.map((pillar, idx) => {
                      const pInfo = PILLAR_STATUS_LABELS[pillar.status] || PILLAR_STATUS_LABELS.moderate;
                      return (
                        <div key={idx} className="finance-moat-pillar-card">
                          <div className="finance-moat-pillar-head">
                            <strong>{pillar.name}</strong>
                            <span className={`finance-moat-pillar-pill ${pInfo.cls}`}>
                              {pInfo.label}
                            </span>
                          </div>
                          <p>{pillar.explanation}</p>
                        </div>
                      );
                    })}
                  </div>
                )}

                <FinanceRichReport
                  markdown={entry.summary_markdown}
                  meta={{
                    title: `Analyse MOAT — ${entry.company_name || entry.symbol}`,
                    subtitle: `Score MOAT : ${entry.moat_score}/100 (${entry.moat_rating})`,
                    symbol: entry.symbol,
                    model: "Analyse MOAT",
                    createdAt: entry.created_at,
                    accent: "#0ea5e9",
                    badgeLabel: "MOAT",
                  }}
                />
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
