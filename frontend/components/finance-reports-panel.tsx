"use client";

import { useEffect, useState } from "react";
import {
  Check,
  Copy,
  Download,
  FileText,
  FileUp,
  LoaderCircle,
  MessageSquarePlus,
  Trash2,
} from "lucide-react";

import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  deleteQuarterlyReport,
  fetchQuarterlyReport,
  fetchQuarterlyReports,
  importQuarterlyReport,
  type QuarterlyReport,
} from "@/lib/api";

type FinanceReportsPanelProps = {
  symbol: string;
  companyName: string;
  onInsertIntoChat?: (text: string) => void;
};

const METRIC_LABELS: Record<string, string> = {
  revenue: "Chiffre d'affaires",
  revenue_growth: "Croissance CA",
  operating_income: "Résultat opérationnel",
  ebitda: "EBITDA",
  operating_margin: "Marge opérationnelle",
  net_income: "Résultat net",
  eps: "BPA / EPS",
  free_cash_flow: "Free Cash Flow",
  net_debt: "Dette nette",
  guidance: "Guidance / Perspectives",
};

export function FinanceReportsPanel({ symbol, companyName, onInsertIntoChat }: FinanceReportsPanelProps) {
  const [reports, setReports] = useState<QuarterlyReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [inputMode, setInputMode] = useState<"file" | "text">("file");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [periodLabel, setPeriodLabel] = useState("");
  const [rawText, setRawText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedTextId, setExpandedTextId] = useState<string | null>(null);
  const [loadedTexts, setLoadedTexts] = useState<Record<string, string>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchQuarterlyReports(symbol)
      .then(list => {
        if (!cancelled) setReports(list);
      })
      .catch(err => {
        if (!cancelled) setError(err?.message || "Impossible de charger les rapports enregistrés.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function handleImport(e: React.FormEvent) {
    e.preventDefault();
    if (importing) return;
    if (inputMode === "file" && !file) {
      setError("Sélectionnez un fichier PDF, DOCX ou texte à importer.");
      return;
    }
    if (inputMode === "text" && !rawText.trim()) {
      setError("Collez le contenu du rapport trimestriel.");
      return;
    }

    setImporting(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("symbol", symbol);
      fd.append("company_name", companyName || symbol);
      fd.append("title", title.trim());
      fd.append("period_label", periodLabel.trim());
      if (inputMode === "file" && file) {
        fd.append("file", file);
      } else {
        fd.append("raw_text", rawText.trim());
      }
      const created = await importQuarterlyReport(fd);
      setReports(prev => [created, ...prev]);
      if (created.extracted_text) {
        setLoadedTexts(prev => ({ ...prev, [created.id]: created.extracted_text! }));
      }
      setFile(null);
      setTitle("");
      setPeriodLabel("");
      setRawText("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Échec de l'import ou de l'analyse du rapport.");
    } finally {
      setImporting(false);
    }
  }

  async function toggleRawText(reportId: string) {
    if (expandedTextId === reportId) {
      setExpandedTextId(null);
      return;
    }
    if (!loadedTexts[reportId]) {
      try {
        const full = await fetchQuarterlyReport(reportId);
        setLoadedTexts(prev => ({ ...prev, [reportId]: full.extracted_text || "" }));
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Impossible de lire le texte extrait.");
        return;
      }
    }
    setExpandedTextId(reportId);
  }

  async function handleDelete(reportId: string) {
    try {
      await deleteQuarterlyReport(reportId);
      setReports(prev => prev.filter(r => r.id !== reportId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  function copySummary(report: QuarterlyReport) {
    navigator.clipboard.writeText(report.summary_markdown);
    setCopiedId(report.id);
    setTimeout(() => setCopiedId(prev => (prev === report.id ? null : prev)), 2000);
  }

  return (
    <div className="finance-tab-content finance-reports-panel">
      <form className="finance-report-upload-card" onSubmit={handleImport}>
        <div className="finance-report-upload-head">
          <div>
            <strong>Importer un rapport trimestriel / financier ({companyName || symbol})</strong>
            <small>Formats PDF, DOCX, TXT/MD ou texte collé — analysé, résumé et archivé automatiquement</small>
          </div>
          <div className="finance-timeframe-selector">
            <button
              type="button"
              className={`finance-tf-btn ${inputMode === "file" ? "active" : ""}`}
              onClick={() => setInputMode("file")}
            >
              Fichier (PDF / TXT)
            </button>
            <button
              type="button"
              className={`finance-tf-btn ${inputMode === "text" ? "active" : ""}`}
              onClick={() => setInputMode("text")}
            >
              Coller le texte
            </button>
          </div>
        </div>

        <div className="finance-form-row-2">
          <label>
            <span>Période (ex. T3 2026, S1 2026, FY 2025)</span>
            <input
              type="text"
              value={periodLabel}
              onChange={e => setPeriodLabel(e.target.value)}
              placeholder="Ex. T3 2026"
              maxLength={60}
            />
          </label>
          <label>
            <span>Titre du rapport (optionnel)</span>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder={`Ex. Communiqué résultats T3 ${companyName || symbol}`}
              maxLength={200}
            />
          </label>
        </div>

        {inputMode === "file" ? (
          <label className="finance-file-dropzone">
            <FileUp size={18} />
            <span>
              {file ? `${file.name} (${(file.size / 1024).toFixed(1)} Ko)` : "Choisir un fichier PDF, DOCX, TXT ou MD…"}
            </span>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md,.csv"
              onChange={e => setFile(e.target.files?.[0] || null)}
              disabled={importing}
            />
          </label>
        ) : (
          <label className="finance-formula-field">
            <span>Contenu texte du rapport ou communiqué</span>
            <textarea
              rows={5}
              value={rawText}
              onChange={e => setRawText(e.target.value)}
              placeholder="Collez ici le communiqué de résultats trimestriels, chiffres clés et commentaires de la direction..."
              disabled={importing}
            />
          </label>
        )}

        <div className="finance-report-upload-actions">
          <button type="submit" className="finance-insert-btn" disabled={importing}>
            {importing ? <LoaderCircle size={14} className="spin" /> : <FileText size={14} />}
            <span>{importing ? "Extraction & analyse IA…" : "Importer, analyser & stocker"}</span>
          </button>
        </div>
      </form>

      {error && <div className="finance-modal-error">⚠️ {error}</div>}

      {loading && reports.length === 0 ? (
        <div className="finance-panel-empty">
          <LoaderCircle size={18} className="spin" /> Chargement des rapports archivés…
        </div>
      ) : reports.length === 0 ? (
        <div className="finance-panel-empty">
          Aucun rapport stocké pour <strong>{companyName || symbol}</strong>. Importez un PDF ou un texte ci-dessus.
        </div>
      ) : (
        <div className="finance-archive-list">
          {reports.map(report => {
            const metricEntries = Object.entries(report.key_metrics || {}).filter(([, val]) => Boolean(val));
            return (
              <article key={report.id} className="finance-archive-card">
                <header className="finance-archive-card-head">
                  <div>
                    <div className="finance-report-title-row">
                      {report.period_label && <span className="finance-period-badge">{report.period_label}</span>}
                      <strong>{report.title}</strong>
                      <span className="finance-source-badge">{report.source_type.toUpperCase()}</span>
                    </div>
                    <div className="finance-archive-meta">
                      <span>{new Date(report.created_at).toLocaleString("fr-FR")}</span>
                      {report.filename && <span>{report.filename}</span>}
                      <span>{report.extracted_chars.toLocaleString("fr-FR")} caractères extraits</span>
                    </div>
                  </div>
                  <div className="finance-archive-actions">
                    <button
                      type="button"
                      className="finance-copy-btn"
                      onClick={() => copySummary(report)}
                      title="Copier le résumé"
                    >
                      {copiedId === report.id ? <Check size={13} className="text-emerald" /> : <Copy size={13} />}
                      <span>{copiedId === report.id ? "Copié" : "Copier"}</span>
                    </button>
                    {report.has_file && (
                      <a
                        href={`/api/finance/reports/${report.id}/file`}
                        className="finance-copy-btn"
                        title="Télécharger le fichier d'origine"
                      >
                        <Download size={13} />
                        <span>Source</span>
                      </a>
                    )}
                    {onInsertIntoChat && (
                      <button
                        type="button"
                        className="finance-copy-btn"
                        onClick={() =>
                          onInsertIntoChat(
                            `Analyse ce résumé de rapport (${report.period_label || report.title}) pour **${report.company_name} (${report.symbol})** :\n\n${report.summary_markdown}`,
                          )
                        }
                        title="Approfondir dans le chat"
                      >
                        <MessageSquarePlus size={13} />
                        <span>Discuter</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="finance-wl-remove-btn"
                      onClick={() => void handleDelete(report.id)}
                      title="Supprimer ce rapport"
                      aria-label="Supprimer ce rapport"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </header>

                {metricEntries.length > 0 && (
                  <div className="finance-report-kpis">
                    {metricEntries.map(([key, val]) => (
                      <div key={key} className="finance-report-kpi-chip">
                        <span>{METRIC_LABELS[key] || key}</span>
                        <strong>{val}</strong>
                      </div>
                    ))}
                  </div>
                )}

                <FinanceRichReport
                  markdown={report.summary_markdown}
                  meta={{
                    title: `${report.title} — ${report.company_name || report.symbol}`,
                    subtitle: report.period_label || "Analyse de rapport financier",
                    symbol: report.symbol,
                    model: report.source_type || "Rapport",
                    createdAt: report.created_at,
                    accent: "#8b5cf6",
                    badgeLabel: "Rapport Trimestriel",
                  }}
                />

                <div className="finance-report-raw-toggle">
                  <button
                    type="button"
                    className="finance-inline-link-btn"
                    onClick={() => void toggleRawText(report.id)}
                  >
                    {expandedTextId === report.id ? "Masquer le texte source extrait" : "Voir le texte source extrait"}
                  </button>
                </div>

                {expandedTextId === report.id && (
                  <pre className="finance-report-raw-pre">{loadedTexts[report.id] || ""}</pre>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
