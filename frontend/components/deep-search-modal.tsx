"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Calendar,
  Check,
  Clock,
  Compass,
  Copy,
  CornerDownLeft,
  Download,
  ExternalLink,
  FileText,
  Globe2,
  ListFilter,
  LoaderCircle,
  Maximize2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import {
  deleteDeepSearchReport,
  fetchDeepSearchReport,
  fetchDeepSearchReports,
  planDeepSearch,
  type DeepSearchReport,
} from "@/lib/api";

type DeepSearchModalProps = {
  isOpen: boolean;
  question?: string;
  conversationId?: string | null;
  initialTab?: "plan" | "reports";
  initialReportId?: string | null;
  onClose: () => void;
  onLaunch?: (queries: string[]) => void | Promise<void>;
};

function formatReportDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function estimateReadingTime(text: string): number {
  const words = text.trim().split(/\s+/).length;
  return Math.max(1, Math.round(words / 200));
}

export function DeepSearchModal({
  isOpen,
  question = "",
  conversationId,
  initialTab = "plan",
  initialReportId = null,
  onClose,
  onLaunch,
}: DeepSearchModalProps) {
  const [activeTab, setActiveTab] = useState<"plan" | "reports">(initialTab);
  
  // Plan state
  const [queries, setQueries] = useState<string[]>([]);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const overlayMouseDownRef = useRef<EventTarget | null>(null);

  // Reports state
  const [reports, setReports] = useState<DeepSearchReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [reportsSearch, setReportsSearch] = useState("");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(initialReportId);
  const [activeReport, setActiveReport] = useState<DeepSearchReport | null>(null);
  const [loadingActiveReport, setLoadingActiveReport] = useState(false);
  const [copiedReport, setCopiedReport] = useState(false);
  const [reportToDelete, setReportToDelete] = useState<DeepSearchReport | null>(null);

  // Sync tab and report id if props change
  useEffect(() => {
    if (initialReportId) {
      setActiveTab("reports");
      setSelectedReportId(initialReportId);
    } else if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab, initialReportId]);

  // Load plan when opening in plan mode
  useEffect(() => {
    if (!isOpen || activeTab !== "plan" || !question.trim()) return;

    let cancelled = false;
    async function loadPlan() {
      setLoadingPlan(true);
      setPlanError(null);
      try {
        const generated = await planDeepSearch(conversationId, question);
        if (!cancelled) {
          const list = generated.length ? generated : [question.trim()];
          setQueries(list);
          setTimeout(() => {
            inputRefs.current[0]?.focus();
          }, 80);
        }
      } catch (err) {
        if (!cancelled) {
          setPlanError(
            err instanceof Error
              ? err.message
              : "Impossible de générer le plan de recherche. Vous pouvez définir vos requêtes manuellement.",
          );
          setQueries([question.trim()]);
          setTimeout(() => {
            inputRefs.current[0]?.focus();
          }, 80);
        }
      } finally {
        if (!cancelled) {
          setLoadingPlan(false);
        }
      }
    }

    void loadPlan();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeTab, question, conversationId]);

  // Load reports list when switching to reports tab
  useEffect(() => {
    if (!isOpen || activeTab !== "reports") return;

    let cancelled = false;
    async function loadReports() {
      setLoadingReports(true);
      try {
        const list = await fetchDeepSearchReports();
        if (!cancelled) {
          setReports(list);
          if (selectedReportId && !activeReport) {
            void loadReportDetail(selectedReportId);
          }
        }
      } catch (err) {
        console.error("Erreur chargement des rapports:", err);
      } finally {
        if (!cancelled) setLoadingReports(false);
      }
    }

    void loadReports();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeTab]);

  // Load active report details when selectedReportId changes
  async function loadReportDetail(reportId: string) {
    setLoadingActiveReport(true);
    try {
      const rep = await fetchDeepSearchReport(reportId);
      setActiveReport(rep);
    } catch (err) {
      console.error("Erreur chargement rapport détaillé:", err);
    } finally {
      setLoadingActiveReport(false);
    }
  }

  useEffect(() => {
    if (selectedReportId) {
      void loadReportDetail(selectedReportId);
    } else {
      setActiveReport(null);
    }
  }, [selectedReportId]);

  // Handle ESC and Ctrl/Cmd+Enter keyboard shortcuts
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        if (reportToDelete) {
          setReportToDelete(null);
        } else if (activeReport) {
          setSelectedReportId(null);
          setActiveReport(null);
        } else {
          onClose();
        }
      } else if (activeTab === "plan" && (e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleConfirmPlan();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, activeTab, queries, activeReport, reportToDelete]);

  if (!isOpen) return null;

  // Plan actions
  function handleQueryChange(index: number, value: string) {
    setQueries((prev) => {
      const copy = [...prev];
      copy[index] = value;
      return copy;
    });
  }

  function handleRemoveQuery(index: number) {
    setQueries((prev) => prev.filter((_, i) => i !== index));
  }

  function handleAddQuery() {
    setQueries((prev) => [...prev, ""]);
    setTimeout(() => {
      const last = inputRefs.current[queries.length];
      last?.focus();
    }, 50);
  }

  async function handleRegeneratePlan() {
    if (loadingPlan || !question.trim()) return;
    setLoadingPlan(true);
    setPlanError(null);
    try {
      const generated = await planDeepSearch(conversationId, question);
      setQueries(generated.length ? generated : [question.trim()]);
    } catch (err) {
      setPlanError(
        err instanceof Error ? err.message : "Erreur lors de la régénération du plan.",
      );
    } finally {
      setLoadingPlan(false);
    }
  }

  async function handleConfirmPlan() {
    if (!onLaunch || isLaunching) return;
    const cleaned = queries.map((q) => q.trim()).filter(Boolean);
    const finalQueries = cleaned.length ? cleaned : [question.trim()];
    setIsLaunching(true);
    setPlanError(null);
    try {
      await onLaunch(finalQueries);
      onClose();
    } catch (err) {
      setPlanError(
        err instanceof Error ? err.message : "Erreur lors du lancement de la recherche approfondie.",
      );
    } finally {
      setIsLaunching(false);
    }
  }

  // Report actions
  async function handleDeleteReport(reportId: string) {
    try {
      await deleteDeepSearchReport(reportId);
      setReports((prev) => prev.filter((r) => r.id !== reportId));
      if (selectedReportId === reportId) {
        setSelectedReportId(null);
        setActiveReport(null);
      }
      setReportToDelete(null);
    } catch (err) {
      console.error("Erreur suppression rapport:", err);
    }
  }

  function handleCopyReport(rep: DeepSearchReport) {
    void navigator.clipboard.writeText(rep.markdown_content);
    setCopiedReport(true);
    setTimeout(() => setCopiedReport(false), 2000);
  }

  const validQueriesCount = queries.filter((q) => q.trim().length > 0).length;
  const filteredReports = reports.filter((r) => {
    if (!reportsSearch.trim()) return true;
    const s = reportsSearch.toLowerCase();
    return r.title.toLowerCase().includes(s) || r.topic.toLowerCase().includes(s);
  });

  return (
    <div
      className="deepsearch-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="deepsearch-modal-title"
      onMouseDown={(e) => {
        overlayMouseDownRef.current = e.target;
      }}
      onClick={(e) => {
        if (overlayMouseDownRef.current === e.currentTarget && e.target === e.currentTarget && !isLaunching) {
          onClose();
        }
      }}
    >
      <div className={`deepsearch-modal-container ${activeReport ? "deepsearch-modal-wide" : ""}`}>
        {/* Top Header & Tabs */}
        <div className="deepsearch-modal-header">
          <div className="deepsearch-modal-header-left">
            <div className="deepsearch-modal-badge-icon" aria-hidden="true">
              <Compass size={22} />
            </div>
            <div>
              <div className="deepsearch-modal-title-row">
                <h2 id="deepsearch-modal-title">
                  {activeReport
                    ? activeReport.title
                    : activeTab === "reports"
                    ? "Mes Rapports DeepSearch"
                    : "Plan de recherche DeepSearch"}
                </h2>
                <span className="deepsearch-modal-pill">
                  {activeReport
                    ? `Mode Lecture Blog · ${activeReport.sources_count} sources`
                    : "Exploration continue bornée (max 5 vagues)"}
                </span>
              </div>
              <p>
                {activeReport
                  ? `Question initiale : « ${activeReport.topic} »`
                  : activeTab === "reports"
                  ? "Consultez, lisez en mode blog et exportez vos grands rapports d'investigation sauvegardés."
                  : "L'agent décompose votre sujet et approfondit par vagues successives tant que l'analyse n'est pas complète (max 5 vagues sécurisées)."}
              </p>
            </div>
          </div>

          <div className="deepsearch-modal-header-right">
            {/* Tab switchers if not reading a specific report */}
            {!activeReport && (
              <div className="deepsearch-tabs-pills" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "plan"}
                  className={`deepsearch-tab-pill ${activeTab === "plan" ? "is-active" : ""}`}
                  onClick={() => setActiveTab("plan")}
                >
                  <WandSparkles size={13} />
                  <span>Nouveau plan</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "reports"}
                  className={`deepsearch-tab-pill ${activeTab === "reports" ? "is-active" : ""}`}
                  onClick={() => setActiveTab("reports")}
                >
                  <BookOpen size={13} />
                  <span>Mes Rapports</span>
                  {reports.length > 0 && (
                    <span className="deepsearch-tab-counter">{reports.length}</span>
                  )}
                </button>
              </div>
            )}

            <button
              type="button"
              className="deepsearch-modal-close"
              onClick={onClose}
              aria-label="Fermer la modale"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ===================== TAB 1: PLAN VIEW ===================== */}
        {activeTab === "plan" && !activeReport && (
          <>
            {/* Question prompt summary */}
            <div className="deepsearch-modal-target-box">
              <div className="deepsearch-modal-target-label">
                <Sparkles size={13} />
                <span>Protocole en 5 phases · Question cible de l'investigation</span>
              </div>
              <div className="deepsearch-modal-target-text">
                « {question.trim() || "Aucune question définie"} »
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px", fontSize: "11px" }}>
                <span className="deepsearch-modal-pill" title="Quels sont les composants, versions et standards impliqués ?">1. Axe Entités / Définitions</span>
                <span className="deepsearch-modal-pill" title="Quel est l'état de l'art actuel et les changements récents ?">2. Axe Temporel</span>
                <span className="deepsearch-modal-pill" title="Quels sont les mécanismes internes, architectures et métriques objectives ?">3. Axe Technique & Causal</span>
                <span className="deepsearch-modal-pill" title="Quels sont les goulots d'étranglement, limitations, failles ou avis opposés ?">4. Axe Contradictoire</span>
                <span className="deepsearch-modal-pill" title="Quelles sont les spécifications d'environnement ou conditions aux limites ?">5. Axe Périmètre & Contraintes</span>
              </div>
            </div>

            {/* Plan Queries list */}
            <div className="deepsearch-modal-body">
              <div className="deepsearch-modal-body-top">
                <div className="deepsearch-modal-plan-header-block">
                  <div className="deepsearch-modal-plan-title">
                    <ListFilter size={15} />
                    <span>Requêtes planifiées</span>
                    <span className="deepsearch-modal-count-badge">{validQueriesCount}</span>
                  </div>
                  <span className="deepsearch-modal-plan-subtitle">
                    4 à 6 mots-clés denses avec guillemets · Factuelles, critiques et internationales
                  </span>
                </div>
                <button
                  type="button"
                  className="deepsearch-modal-regenerate-btn"
                  onClick={handleRegeneratePlan}
                  disabled={loadingPlan}
                  title="Demander à l'IA de recalculer de nouveaux angles de recherche"
                >
                  {loadingPlan ? (
                    <LoaderCircle size={13} className="spin" />
                  ) : (
                    <WandSparkles size={13} />
                  )}
                  <span>Régénérer le plan</span>
                </button>
              </div>

              {planError && <div className="deepsearch-modal-error-banner">{planError}</div>}

              {loadingPlan ? (
                <div className="deepsearch-modal-loading-state">
                  <LoaderCircle size={28} className="spin" />
                  <p>Décomposition stratégique et formulation des pistes multilingues…</p>
                  <span>Identification des entités clés, points aveugles et documentation de référence</span>
                </div>
              ) : (
                <div className="deepsearch-modal-queries-list">
                  {queries.map((query, index) => (
                    <div key={index} className="deepsearch-modal-query-row">
                      <span className="deepsearch-modal-query-num" aria-hidden="true">
                        {index + 1}
                      </span>
                      <input
                        ref={(el) => {
                          inputRefs.current[index] = el;
                        }}
                        type="text"
                        className="deepsearch-modal-query-input"
                        value={query}
                        placeholder='Ex: "active recall" "spaced repetition" Dunlosky meta-analysis...'
                        onChange={(e) => handleQueryChange(index, e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            void handleConfirmPlan();
                          }
                        }}
                        disabled={isLaunching}
                      />
                      <button
                        type="button"
                        className="deepsearch-modal-query-delete-btn"
                        onClick={() => handleRemoveQuery(index)}
                        disabled={isLaunching}
                        title="Supprimer cette requête"
                        aria-label={`Supprimer la requête ${index + 1}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))}

                  <button
                    type="button"
                    className="deepsearch-modal-add-btn"
                    onClick={handleAddQuery}
                    disabled={isLaunching}
                  >
                    <Plus size={15} />
                    <span>Ajouter un angle ou une sous-requête de recherche</span>
                  </button>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="deepsearch-modal-footer">
              <div className="deepsearch-modal-footer-hint">
                <CornerDownLeft size={13} />
                <span>Appuyez sur Entrée ou validez pour démarrer la recherche</span>
              </div>
              <div className="deepsearch-modal-footer-actions">
                <button
                  type="button"
                  className="deepsearch-modal-cancel-btn"
                  onClick={onClose}
                  disabled={isLaunching}
                >
                  Annuler
                </button>
                <button
                  type="button"
                  className="deepsearch-modal-launch-btn"
                  onClick={() => void handleConfirmPlan()}
                  disabled={loadingPlan || isLaunching || validQueriesCount === 0 || !onLaunch}
                >
                  {isLaunching ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Compass size={16} />
                  )}
                  <span>
                    {isLaunching
                      ? "Lancement en cours…"
                      : `Lancer DeepSearch (${validQueriesCount} ${validQueriesCount > 1 ? "requêtes" : "requête"})`}
                  </span>
                </button>
              </div>
            </div>
          </>
        )}

        {/* ===================== TAB 2: REPORTS LIST ===================== */}
        {activeTab === "reports" && !activeReport && (
          <div className="deepsearch-reports-container">
            {/* Filter toolbar */}
            <div className="deepsearch-reports-toolbar">
              <div className="deepsearch-reports-search-box">
                <Search size={14} className="deepsearch-reports-search-icon" />
                <input
                  type="text"
                  placeholder="Rechercher parmi les rapports par titre ou question..."
                  value={reportsSearch}
                  onChange={(e) => setReportsSearch(e.target.value)}
                  className="deepsearch-reports-search-input"
                />
                {reportsSearch && (
                  <button
                    type="button"
                    className="deepsearch-reports-clear-search"
                    onClick={() => setReportsSearch("")}
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
              <div className="deepsearch-reports-count-pill">
                <span>{filteredReports.length} rapport{filteredReports.length > 1 ? "s" : ""}</span>
              </div>
            </div>

            {loadingReports ? (
              <div className="deepsearch-modal-loading-state">
                <LoaderCircle size={28} className="spin" />
                <p>Chargement des rapports d'analyse DeepSearch…</p>
              </div>
            ) : filteredReports.length === 0 ? (
              <div className="deepsearch-reports-empty">
                <Compass size={44} className="deepsearch-empty-icon" />
                <h3>Aucun rapport DeepSearch pour le moment</h3>
                <p>
                  Lorsque vous lancez une recherche en mode DeepSearch, le grand rapport d'analyse
                  et sa page HTML de publication sont automatiquement archivés ici.
                </p>
                {question.trim() && (
                  <button
                    type="button"
                    className="deepsearch-empty-cta-btn"
                    onClick={() => setActiveTab("plan")}
                  >
                    <WandSparkles size={14} />
                    <span>Préparer un plan pour « {question.slice(0, 40)}… »</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="deepsearch-reports-grid">
                {filteredReports.map((report) => (
                  <article key={report.id} className="deepsearch-report-card">
                    <div className="deepsearch-report-card-top">
                      <span className="deepsearch-report-date">
                        <Calendar size={12} />
                        <span>{formatReportDate(report.created_at)}</span>
                      </span>
                      <span className="deepsearch-report-sources-badge">
                        <Globe2 size={11} />
                        <span>{report.sources_count} sources</span>
                      </span>
                    </div>

                    <h3 className="deepsearch-report-card-title">{report.title}</h3>
                    <p className="deepsearch-report-card-topic">
                      « {report.topic} »
                    </p>

                    <div className="deepsearch-report-card-footer">
                      <button
                        type="button"
                        className="deepsearch-report-read-btn"
                        onClick={() => setSelectedReportId(report.id)}
                        title="Consulter le rapport dans le lecteur intégré"
                      >
                        <BookOpen size={13} />
                        <span>Lire le rapport</span>
                      </button>

                      <div className="deepsearch-report-actions-row">
                        <a
                          href={`/api/deep-search/reports/${report.id}/html`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="deepsearch-report-action-icon-btn"
                          title="Ouvrir la page HTML classe en plein écran (mode blog)"
                        >
                          <Maximize2 size={13} />
                        </a>
                        <a
                          href={`/api/deep-search/reports/${report.id}/html?download=1`}
                          className="deepsearch-report-action-icon-btn"
                          title="Télécharger le fichier .html autonome"
                          download
                        >
                          <Download size={13} />
                        </a>
                        <button
                          type="button"
                          className="deepsearch-report-action-icon-btn danger"
                          onClick={() => setReportToDelete(report)}
                          title="Supprimer définitivement ce rapport"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ===================== TAB 3: DEDICATED READER MODE ===================== */}
        {activeReport && (
          <div className="deepsearch-reader-wrapper">
            {/* Reader Sub-Header */}
            <div className="deepsearch-reader-top-bar">
              <button
                type="button"
                className="deepsearch-reader-back-btn"
                onClick={() => {
                  setActiveReport(null);
                  setSelectedReportId(null);
                }}
              >
                <ArrowLeft size={14} />
                <span>Tous les rapports</span>
              </button>

              <div className="deepsearch-reader-actions-bar">
                <button
                  type="button"
                  className="deepsearch-reader-tool-btn"
                  onClick={() => handleCopyReport(activeReport)}
                  title="Copier le texte en Markdown"
                >
                  {copiedReport ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                  <span>{copiedReport ? "Copié !" : "Copier Markdown"}</span>
                </button>

                <a
                  href={`/api/deep-search/reports/${activeReport.id}/html`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="deepsearch-reader-primary-tool-btn"
                  title="Ouvrir la page HTML autonome façon blog dans un nouvel onglet"
                >
                  <ExternalLink size={13} />
                  <span>Page HTML plein écran</span>
                </a>

                <a
                  href={`/api/deep-search/reports/${activeReport.id}/html?download=1`}
                  className="deepsearch-reader-tool-btn"
                  title="Télécharger le fichier .html complet"
                  download
                >
                  <Download size={13} />
                  <span>Exporter .html</span>
                </a>

                <button
                  type="button"
                  className="deepsearch-reader-tool-btn text-rose-500"
                  onClick={() => setReportToDelete(activeReport)}
                  title="Supprimer ce rapport"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>

            {loadingActiveReport ? (
              <div className="deepsearch-modal-loading-state">
                <LoaderCircle size={28} className="spin" />
                <p>Chargement du grand rapport d'analyse…</p>
              </div>
            ) : (
              <div className="deepsearch-reader-scrollable">
                {/* Article Header Card */}
                <header className="deepsearch-reader-hero">
                  <div className="deepsearch-reader-hero-badges">
                    <span className="reader-badge">Grand Rapport DeepSearch</span>
                    <span className="reader-badge success">
                      ✓ {activeReport.sources_count} sources analysées
                    </span>
                    <span className="reader-badge">Publication de synthèse</span>
                  </div>

                  <h1 className="deepsearch-reader-title">{activeReport.title}</h1>

                  <div className="deepsearch-reader-question-card">
                    <span className="reader-question-label">Question initiale posée</span>
                    <p className="reader-question-text">« {activeReport.topic} »</p>
                  </div>

                  <div className="deepsearch-reader-meta-row">
                    <span className="reader-meta-item">
                      <Calendar size={13} />
                      <span>{formatReportDate(activeReport.created_at)}</span>
                    </span>
                    <span className="reader-meta-item">
                      <Clock size={13} />
                      <span>Lecture ~ {estimateReadingTime(activeReport.markdown_content)} min</span>
                    </span>
                    <span className="reader-meta-item">
                      <Globe2 size={13} />
                      <span>Recherche SearXNG multi-étapes</span>
                    </span>
                  </div>
                </header>

                {/* Article Content Rendered */}
                <article className="deepsearch-reader-prose">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeKatex]}
                  >
                    {activeReport.markdown_content}
                  </ReactMarkdown>
                </article>

                {/* Sources Section */}
                {activeReport.sources && activeReport.sources.length > 0 && (
                  <section className="deepsearch-reader-sources-block">
                    <div className="deepsearch-reader-sources-title">
                      <Globe2 size={16} />
                      <h3>Sources et références web analysées ({activeReport.sources.length})</h3>
                    </div>
                    <p className="deepsearch-reader-sources-desc">
                      Chaque fait cité dans le rapport a été recoupé avec les extraits de ces domaines web.
                    </p>

                    <div className="deepsearch-reader-sources-grid">
                      {activeReport.sources.map((src, i) => (
                        <div key={i} className="deepsearch-reader-source-card">
                          <div className="reader-source-card-top">
                            <span className="reader-source-index">#{i + 1}</span>
                            <span className="reader-source-provider">{src.provider || "Web"}</span>
                          </div>
                          <h4 className="reader-source-card-title">
                            <a href={src.url} target="_blank" rel="noopener noreferrer">
                              {src.title || src.url}
                              <ExternalLink size={11} />
                            </a>
                          </h4>
                          {src.snippet && (
                            <p className="reader-source-card-snippet">« {src.snippet} »</p>
                          )}
                          <a
                            href={src.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="reader-source-card-link"
                          >
                            Consulter la source &rarr;
                          </a>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            )}
          </div>
        )}

        {/* Confirmation modal for report deletion */}
        {reportToDelete && (
          <div
            className="deepsearch-confirm-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-delete-report-title"
          >
            <div className="deepsearch-confirm-card">
              <div className="deepsearch-confirm-icon-box">
                <Trash2 size={24} className="text-rose-600" />
              </div>
              <h3 id="confirm-delete-report-title">Supprimer ce rapport ?</h3>
              <p>
                Êtes-vous sûr de vouloir supprimer définitivement le rapport{" "}
                <strong>« {reportToDelete.title} »</strong> ? Sa page HTML et ses sources associées
                seront effacées.
              </p>
              <div className="deepsearch-confirm-actions">
                <button
                  type="button"
                  className="deepsearch-confirm-cancel-btn"
                  onClick={() => setReportToDelete(null)}
                >
                  Annuler
                </button>
                <button
                  type="button"
                  className="deepsearch-confirm-delete-btn"
                  onClick={() => handleDeleteReport(reportToDelete.id)}
                >
                  Oui, supprimer le rapport
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
