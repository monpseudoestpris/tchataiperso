"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AudioLines,
  BookOpen,
  Check,
  Copy,
  Download,
  FileText,
  FileUp,
  LoaderCircle,
  MessageSquarePlus,
  Search,
  Table2,
  Trash2,
} from "lucide-react";

import { FinanceRichReport } from "@/components/finance-rich-report";
import {
  deleteQuarterlyReport,
  fetchQuarterlyReport,
  fetchQuarterlyReports,
  importQuarterlyReport,
  type QuarterlyReport,
  type QuarterlyReportTable,
} from "@/lib/api";

type FinanceReportsPanelProps = {
  symbol: string;
  companyName: string;
  onInsertIntoChat?: (text: string) => void;
  onOpenReportAsDoc?: (report: QuarterlyReport, openVoiceFullscreen?: boolean) => Promise<void> | void;
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

export function FinanceReportsPanel({
  symbol,
  companyName,
  onInsertIntoChat,
  onOpenReportAsDoc,
}: FinanceReportsPanelProps) {
  const [reports, setReports] = useState<QuarterlyReport[]>([]);
  const [openingReportId, setOpeningReportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [inputMode, setInputMode] = useState<"file" | "text">("file");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [periodLabel, setPeriodLabel] = useState("");
  const [rawText, setRawText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedTextId, setExpandedTextId] = useState<string | null>(null);
  const [expandedTablesId, setExpandedTablesId] = useState<string | null>(null);
  const [tablesLoadingId, setTablesLoadingId] = useState<string | null>(null);
  const [loadedTexts, setLoadedTexts] = useState<Record<string, string>>({});
  const [loadedTables, setLoadedTables] = useState<Record<string, QuarterlyReportTable[]>>({});
  const [tablesFilterByReport, setTablesFilterByReport] = useState<Record<string, string>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [copiedTableKey, setCopiedTableKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadReports() {
      await Promise.resolve();
      if (cancelled) return;
      setLoading(true);
      setError(null);
      try {
        const list = await fetchQuarterlyReports(symbol);
        if (!cancelled) setReports(list);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Impossible de charger les rapports enregistrés.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadReports();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function hydrateReportDetails(reportId: string): Promise<boolean> {
    if (loadedTexts[reportId] !== undefined && loadedTables[reportId] !== undefined) {
      return true;
    }
    setTablesLoadingId(reportId);
    try {
      const full = await fetchQuarterlyReport(reportId);
      setLoadedTexts(prev => ({ ...prev, [reportId]: full.extracted_text || "" }));
      setLoadedTables(prev => ({ ...prev, [reportId]: full.extracted_tables || [] }));
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Impossible de lire le contenu extrait.");
      return false;
    } finally {
      setTablesLoadingId(null);
    }
  }

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
      if (created.extracted_text !== undefined) {
        setLoadedTexts(prev => ({ ...prev, [created.id]: created.extracted_text || "" }));
      }
      if (created.extracted_tables !== undefined) {
        setLoadedTables(prev => ({ ...prev, [created.id]: created.extracted_tables || [] }));
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
    const ok = await hydrateReportDetails(reportId);
    if (ok) {
      setExpandedTextId(reportId);
    }
  }

  async function toggleExtractedTables(reportId: string) {
    if (expandedTablesId === reportId) {
      setExpandedTablesId(null);
      return;
    }
    const ok = await hydrateReportDetails(reportId);
    if (ok) {
      setExpandedTablesId(reportId);
    }
  }

  async function handleDelete(reportId: string) {
    try {
      await deleteQuarterlyReport(reportId);
      setReports(prev => prev.filter(r => r.id !== reportId));
      if (expandedTextId === reportId) setExpandedTextId(null);
      if (expandedTablesId === reportId) setExpandedTablesId(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Suppression impossible.");
    }
  }

  function copySummary(report: QuarterlyReport) {
    navigator.clipboard.writeText(report.summary_markdown);
    setCopiedId(report.id);
    setTimeout(() => setCopiedId(prev => (prev === report.id ? null : prev)), 2000);
  }

  function copyTableMarkdown(reportId: string, tbl: QuarterlyReportTable) {
    const key = `${reportId}:${tbl.index}`;
    navigator.clipboard.writeText(tbl.markdown);
    setCopiedTableKey(key);
    setTimeout(() => setCopiedTableKey(prev => (prev === key ? null : prev)), 2000);
  }

  return (
    <div className="finance-tab-content finance-reports-panel">
      <form className="finance-report-upload-card" onSubmit={handleImport}>
        <div className="finance-report-upload-head">
          <div>
            <strong>Importer un rapport trimestriel / financier ({companyName || symbol})</strong>
            <small>
              PDF (Mistral OCR page par page + tableaux), DOCX, TXT/MD ou texte collé — extraction intégrale, synthèse Map-Reduce &amp; archivage
            </small>
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
            <span>{importing ? "Extraction OCR page par page, tableaux & synthèse IA…" : "Importer, analyser & stocker"}</span>
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
            const tablesForReport = loadedTables[report.id];
            const tablesCount = report.tables_count ?? tablesForReport?.length ?? 0;
            const filterVal = (tablesFilterByReport[report.id] || "").trim().toLowerCase();
            const filteredTables = (tablesForReport || []).filter(tbl => {
              if (!filterVal) return true;
              return (
                tbl.title.toLowerCase().includes(filterVal) ||
                tbl.markdown.toLowerCase().includes(filterVal) ||
                `page ${tbl.page}`.includes(filterVal)
              );
            });

            return (
              <article key={report.id} className="finance-archive-card">
                <header className="finance-archive-card-head">
                  <div>
                    <div className="finance-report-title-row">
                      {report.period_label && <span className="finance-period-badge">{report.period_label}</span>}
                      <strong>{report.title}</strong>
                      <span
                        className={`finance-source-badge ${report.source_type === "pdf-ocr" ? "is-ocr" : ""}`}
                        title={
                          report.source_type === "pdf-ocr"
                            ? "Extrait page par page via Mistral OCR"
                            : "Extraction locale"
                        }
                      >
                        {report.source_type.toUpperCase()}
                      </span>
                    </div>
                    <div className="finance-archive-meta">
                      <span>{new Date(report.created_at).toLocaleString("fr-FR")}</span>
                      {report.filename && <span>{report.filename}</span>}
                      {report.page_count != null && report.page_count > 0 && (
                        <span>
                          {report.page_count} page{report.page_count > 1 ? "s" : ""}
                        </span>
                      )}
                      {tablesCount > 0 && (
                        <span>
                          {tablesCount} tableau{tablesCount > 1 ? "x" : ""}
                        </span>
                      )}
                      <span>{report.extracted_chars.toLocaleString("fr-FR")} caractères extraits</span>
                      {report.extracted_at && (
                        <span>Extrait le {new Date(report.extracted_at).toLocaleString("fr-FR")}</span>
                      )}
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
                    {onOpenReportAsDoc && (
                      <>
                        <button
                          type="button"
                          className="finance-copy-btn"
                          disabled={openingReportId === report.id}
                          onClick={async () => {
                            setOpeningReportId(report.id);
                            setError(null);
                            try {
                              await onOpenReportAsDoc(report, false);
                            } catch (err: unknown) {
                              setError(err instanceof Error ? err.message : "Impossible d'ouvrir ce rapport dans le tchat.");
                            } finally {
                              setOpeningReportId(null);
                            }
                          }}
                          title="Attacher tout le rapport (pages, tableaux & citations [p. X]) dans le tchat comme un Document Illustré"
                        >
                          {openingReportId === report.id ? <LoaderCircle size={13} className="spin" /> : <BookOpen size={13} />}
                          <span>Interagir (Doc)</span>
                        </button>
                        <button
                          type="button"
                          className="finance-copy-btn"
                          disabled={openingReportId === report.id}
                          onClick={async () => {
                            setOpeningReportId(report.id);
                            setError(null);
                            try {
                              await onOpenReportAsDoc(report, true);
                            } catch (err: unknown) {
                              setError(err instanceof Error ? err.message : "Impossible de lancer le mode vocal.");
                            } finally {
                              setOpeningReportId(null);
                            }
                          }}
                          title="Attacher tout le rapport et ouvrir le Mode Vocal Plein Écran (mains-libres + clavier)"
                        >
                          {openingReportId === report.id ? <LoaderCircle size={13} className="spin" /> : <AudioLines size={13} />}
                          <span>Vocal Plein Écran</span>
                        </button>
                      </>
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
                  <div className="finance-report-footer-actions">
                    <button
                      type="button"
                      className={`finance-inline-link-btn ${expandedTablesId === report.id ? "active" : ""}`}
                      onClick={() => void toggleExtractedTables(report.id)}
                      disabled={tablesLoadingId === report.id}
                    >
                      {tablesLoadingId === report.id && expandedTablesId !== report.id ? (
                        <LoaderCircle size={13} className="spin" />
                      ) : (
                        <Table2 size={13} />
                      )}
                      <span>
                        {expandedTablesId === report.id
                          ? `Masquer les tableaux (${tablesCount})`
                          : `Tableaux extraits (${tablesCount})`}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="finance-inline-link-btn"
                      onClick={() => void toggleRawText(report.id)}
                    >
                      {expandedTextId === report.id ? "Masquer le texte source extrait" : "Voir le texte source extrait"}
                    </button>
                  </div>
                </div>

                {expandedTablesId === report.id && (
                  <div className="finance-report-tables-drawer">
                    <div className="finance-report-tables-filter">
                      <Search size={13} />
                      <input
                        type="text"
                        value={tablesFilterByReport[report.id] || ""}
                        onChange={e =>
                          setTablesFilterByReport(prev => ({ ...prev, [report.id]: e.target.value }))
                        }
                        placeholder="Filtrer les tableaux extraits (titre, poste comptable, chiffre, page)..."
                      />
                      <span className="finance-report-tables-count">
                        {filteredTables.length} / {(tablesForReport || []).length}
                      </span>
                    </div>

                    {filteredTables.length === 0 ? (
                      <div className="finance-panel-empty">
                        {(tablesForReport || []).length === 0
                          ? "Aucun tableau Markdown détecté dans ce document."
                          : "Aucun tableau ne correspond à ce filtre."}
                      </div>
                    ) : (
                      <div className="finance-report-tables-list">
                        {filteredTables.map(tbl => {
                          const tblCopyKey = `${report.id}:${tbl.index}`;
                          const isCopied = copiedTableKey === tblCopyKey;
                          return (
                            <div key={tblCopyKey} className="finance-report-table-card">
                              <div className="finance-report-table-card-head">
                                <div className="finance-report-table-card-title">
                                  <span className="finance-period-badge">Page {tbl.page}</span>
                                  <strong>
                                    Tableau #{tbl.index} — {tbl.title}
                                  </strong>
                                  <small>
                                    {tbl.rows_count} × {tbl.cols_count}
                                  </small>
                                </div>
                                <div className="finance-archive-actions">
                                  <button
                                    type="button"
                                    className="finance-copy-btn"
                                    onClick={() => copyTableMarkdown(report.id, tbl)}
                                    title="Copier ce tableau au format Markdown"
                                  >
                                    {isCopied ? <Check size={12} className="text-emerald" /> : <Copy size={12} />}
                                    <span>{isCopied ? "Copié" : "Copier"}</span>
                                  </button>
                                  {onInsertIntoChat && (
                                    <button
                                      type="button"
                                      className="finance-copy-btn"
                                      onClick={() =>
                                        onInsertIntoChat(
                                          `Analyse ce tableau extrait de **${report.title}** (${report.company_name || report.symbol}, Page ${tbl.page} — ${tbl.title}) :\n\n${tbl.markdown}`,
                                        )
                                      }
                                      title="Envoyer ce tableau dans le tchat"
                                    >
                                      <MessageSquarePlus size={12} />
                                      <span>Discuter</span>
                                    </button>
                                  )}
                                </div>
                              </div>
                              <div className="finance-table-wrapper finance-report-table-md">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{tbl.markdown}</ReactMarkdown>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

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
