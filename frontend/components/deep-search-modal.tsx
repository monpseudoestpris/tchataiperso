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
  Presentation,
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
  type Model,
} from "@/lib/api";

type DeepSearchModalProps = {
  isOpen: boolean;
  question?: string;
  conversationId?: string | null;
  initialTab?: "plan" | "reports";
  initialReportId?: string | null;
  models?: Model[];
  onRefreshModels?: () => Promise<void>;
  onClose: () => void;
  onLaunch?: (
    queries: string[],
    detailLevel?: number,
    selectedModel?: string,
    interactionId?: string,
    planFeedback?: string,
  ) => void | Promise<void>;
};

export const DEEP_RESEARCH_ENGINES = [
  {
    id: "perplexity/sonar-deep-research",
    label: "Sonar Deep Research",
    providerBadge: "Perplexity · OpenRouter",
    badge: "Exhaustif · Multi-passes",
    desc: "Investigation web multi-passes approfondie, analyse d'expert et confrontation des sources primaires.",
  },
  {
    id: "perplexity/sonar-pro-search",
    label: "Sonar Pro Search",
    providerBadge: "Perplexity · OpenRouter",
    badge: "Pro · Rapide & Agile",
    desc: "Recherche proactive rapide, agile et sourcée avec citations directes pour synthèses ciblées.",
  },
  {
    id: "google/deep-research-preview-04-2026",
    label: "Google Gemini Deep Research",
    providerBadge: "Google Gemini API",
    badge: "Agent Google · Interactions API",
    desc: "Agent autonome d'investigation de Google Gemini (requiert GOOGLE_API_KEY).",
  },
  {
    id: "google/deep-research-max-preview-04-2026",
    label: "Google Gemini Deep Research Max",
    providerBadge: "Google Gemini API",
    badge: "Max · Exhaustivité Maximale",
    desc: "Version maximale ultra-exhaustive de Google Deep Research pour investigations complexes massives.",
  },
];

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
  models = [],
  onRefreshModels,
  onClose,
  onLaunch,
}: DeepSearchModalProps) {
  const [activeTab, setActiveTab] = useState<"plan" | "reports">(initialTab);
  const [outputFormat, setOutputFormat] = useState<"html" | "pdf">("html");
  const [selectedEngineModel, setSelectedEngineModel] = useState<string>("perplexity/sonar-deep-research");
  
  // Question state
  const [targetQuery, setTargetQuery] = useState(question.trim());
  const [isLaunching, setIsLaunching] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const overlayMouseDownRef = useRef<EventTarget | null>(null);

  // Google Deep Research Collaborative Planning state
  const isGoogleModel = selectedEngineModel.toLowerCase().includes("google");
  const [collaborativePlan, setCollaborativePlan] = useState<string>("");
  const [interactionId, setInteractionId] = useState<string | null>(null);
  const [loadingGooglePlan, setLoadingGooglePlan] = useState<boolean>(false);
  const [showPlanReview, setShowPlanReview] = useState<boolean>(false);

  // Reset plan review if user changes engine
  useEffect(() => {
    if (!isGoogleModel) {
      setShowPlanReview(false);
      setCollaborativePlan("");
      setInteractionId(null);
    }
  }, [isGoogleModel]);

  // Auto-fetch collaborative plan when Google engine is selected
  useEffect(() => {
    if (!isOpen || activeTab !== "plan" || !isGoogleModel) return;
    const cleanQ = targetQuery.trim() || question.trim();
    if (cleanQ && !collaborativePlan && !loadingGooglePlan && !planError) {
      void handleRequestGooglePlan();
    }
  }, [isOpen, activeTab, isGoogleModel, selectedEngineModel, targetQuery, question, collaborativePlan, loadingGooglePlan, planError]);

  // Reports state
  const [reports, setReports] = useState<DeepSearchReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [reportsSearch, setReportsSearch] = useState("");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(initialReportId);
  const [activeReport, setActiveReport] = useState<DeepSearchReport | null>(null);
  const [loadingActiveReport, setLoadingActiveReport] = useState(false);
  const [copiedReport, setCopiedReport] = useState(false);
  const [reportToDelete, setReportToDelete] = useState<DeepSearchReport | null>(null);

  // Sync question when prop changes
  useEffect(() => {
    setTargetQuery(question.trim());
  }, [question]);

  useEffect(() => {
    if (initialReportId) {
      setSelectedReportId(initialReportId);
      setActiveTab("reports");
    }
  }, [initialReportId]);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

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
  }, [isOpen, activeTab, targetQuery, activeReport, reportToDelete]);

  if (!isOpen) return null;

  async function handleRequestGooglePlan(refineWithPrevious = false) {
    const cleanQ = targetQuery.trim() || question.trim();
    if (!cleanQ || loadingGooglePlan) return;
    setLoadingGooglePlan(true);
    setPlanError(null);
    setShowPlanReview(true);
    try {
      const prevId = refineWithPrevious && interactionId ? interactionId : undefined;
      const res = await planDeepSearch(conversationId, cleanQ, undefined, selectedEngineModel, prevId);
      if (res.plan_text) {
        setCollaborativePlan(res.plan_text);
        if (res.interaction_id) setInteractionId(res.interaction_id);
      }
    } catch (err) {
      setPlanError(
        err instanceof Error ? err.message : "Impossible d'obtenir la proposition de plan de Google Deep Research.",
      );
    } finally {
      setLoadingGooglePlan(false);
    }
  }

  async function handleConfirmPlan() {
    if (!onLaunch || isLaunching) return;
    const cleanQ = targetQuery.trim() || question.trim();
    if (!cleanQ) return;

    // Si Google Deep Research est sélectionné et qu'aucun plan n'est encore généré, on le génère d'abord pour validation !
    if (isGoogleModel && (!showPlanReview || !collaborativePlan)) {
      await handleRequestGooglePlan();
      return;
    }

    setIsLaunching(true);
    setPlanError(null);
    try {
      const activeInteractionId = isGoogleModel && showPlanReview && interactionId ? interactionId : undefined;
      const activeFeedback = isGoogleModel && showPlanReview && collaborativePlan ? collaborativePlan : undefined;
      await onLaunch([cleanQ], undefined, selectedEngineModel, activeInteractionId, activeFeedback);
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
                    : "Perplexity Sonar Deep Research"}
                </span>
              </div>
              <p>
                {activeReport
                  ? `Question initiale : « ${activeReport.topic} »`
                  : activeTab === "reports"
                  ? "Consultez, lisez en mode blog et exportez vos grands rapports d'investigation sauvegardés."
                  : "Investigation autonome approfondie par Perplexity Sonar Deep Research avec recherche web multi-sources et citations vérifiées en temps réel."}
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
            {/* Plan Body */}
            <div className="deepsearch-modal-body">
              {/* Question principale */}
              <div className="output-format-card" role="group" aria-label="Question d'investigation">
                <span className="output-format-label">
                  <Sparkles size={14} />
                  <span>Question ou sujet de la recherche approfondie :</span>
                </span>
                <textarea
                  rows={3}
                  className="deepsearch-modal-query-input deepsearch-module-textarea"
                  style={{
                    width: "100%",
                    marginTop: "8px",
                    padding: "12px",
                    borderRadius: "10px",
                    resize: "vertical",
                    fontSize: "13px",
                    lineHeight: "1.5",
                  }}
                  value={targetQuery}
                  onChange={(e) => setTargetQuery(e.target.value)}
                  placeholder="Précisez votre question ou sujet d'investigation…"
                  disabled={isLaunching}
                />
              </div>

              {/* Sélecteur de moteur d'investigation */}
              <div className="output-format-card" role="group" aria-label="Moteur d'investigation">
                <span className="output-format-label">
                  <Compass size={14} />
                  <span>Moteur de recherche autonome :</span>
                </span>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "10px", marginTop: "8px" }}>
                  {DEEP_RESEARCH_ENGINES.map((engine) => {
                    const isSelected = selectedEngineModel === engine.id;
                    return (
                      <button
                        key={engine.id}
                        type="button"
                        onClick={() => setSelectedEngineModel(engine.id)}
                        className={`output-format-option ${isSelected ? "is-selected" : ""}`}
                        style={{
                          textAlign: "left",
                          padding: "12px 14px",
                          borderRadius: "10px",
                          border: isSelected ? "1.5px solid var(--accent-primary, #6366f1)" : "1px solid var(--border-color, #334155)",
                          background: isSelected ? "rgba(99, 102, 241, 0.12)" : "rgba(30, 41, 59, 0.4)",
                          cursor: "pointer",
                          display: "flex",
                          flexDirection: "column",
                          gap: "4px",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
                          <span style={{ fontWeight: 600, fontSize: "13px", color: isSelected ? "var(--accent-primary, #818cf8)" : "inherit" }}>
                            {engine.label}
                          </span>
                          <span style={{ fontSize: "10px", padding: "2px 6px", borderRadius: "6px", background: "rgba(148, 163, 184, 0.15)", color: "#94a3b8" }}>
                            {engine.badge}
                          </span>
                        </div>
                        <small style={{ fontSize: "11px", color: "var(--text-muted, #94a3b8)", lineHeight: "1.4" }}>
                          {engine.desc}
                        </small>
                      </button>
                    );
                  })}
                </div>

                {/* Option Google Deep Research : Collaborative Planning natif */}
                {isGoogleModel && (
                  <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
                    {loadingGooglePlan ? (
                      <div
                        style={{
                          padding: "14px 16px",
                          borderRadius: "10px",
                          border: "1px solid rgba(99, 102, 241, 0.4)",
                          background: "rgba(99, 102, 241, 0.08)",
                          display: "flex",
                          alignItems: "center",
                          gap: "10px",
                          fontSize: "12px",
                          color: "var(--accent-primary, #818cf8)",
                        }}
                      >
                        <LoaderCircle size={18} className="spin" />
                        <div>
                          <strong>Élaboration du plan en temps réel…</strong>
                          <p style={{ margin: "2px 0 0 0", fontSize: "11px", color: "var(--text-muted, #94a3b8)" }}>
                            Consultation de Google Gemini Deep Research pour établir les axes d'investigation.
                          </p>
                        </div>
                      </div>
                    ) : planError ? (
                      <div
                        style={{
                          padding: "12px 14px",
                          borderRadius: "10px",
                          border: "1px solid rgba(239, 68, 68, 0.4)",
                          background: "rgba(239, 68, 68, 0.1)",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "10px",
                          fontSize: "12px",
                          color: "#f87171",
                        }}
                      >
                        <span>{planError}</span>
                        <button
                          type="button"
                          onClick={() => void handleRequestGooglePlan()}
                          style={{
                            background: "rgba(239, 68, 68, 0.2)",
                            border: "1px solid rgba(239, 68, 68, 0.4)",
                            color: "#fca5a5",
                            borderRadius: "6px",
                            padding: "4px 8px",
                            fontSize: "11px",
                            cursor: "pointer",
                            whiteSpace: "nowrap",
                          }}
                        >
                          Réessayer
                        </button>
                      </div>
                    ) : collaborativePlan ? (
                      <div
                        style={{
                          padding: "12px",
                          borderRadius: "10px",
                          border: "1.5px solid rgba(99, 102, 241, 0.4)",
                          background: "rgba(15, 23, 42, 0.65)",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                          <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--accent-primary, #818cf8)", display: "flex", alignItems: "center", gap: "6px" }}>
                            <Sparkles size={13} />
                            <span>📋 Plan d'investigation Google Gemini — À valider :</span>
                          </span>
                          <button
                            type="button"
                            onClick={() => void handleRequestGooglePlan(true)}
                            disabled={loadingGooglePlan || isLaunching}
                            style={{
                              background: "none",
                              border: "none",
                              color: "var(--text-muted, #94a3b8)",
                              cursor: "pointer",
                              fontSize: "11px",
                              display: "flex",
                              alignItems: "center",
                              gap: "4px",
                            }}
                            title="Demander une nouvelle proposition de plan"
                          >
                            <RefreshCw size={11} />
                            <span>Régénérer</span>
                          </button>
                        </div>
                        <p style={{ fontSize: "11px", color: "var(--text-muted, #94a3b8)", margin: "0 0 8px 0" }}>
                          Vous pouvez affiner, réordonner ou compléter les axes ci-dessous. Le modèle suivra scrupuleusement ces directives.
                        </p>
                        <textarea
                          rows={6}
                          className="deepsearch-modal-query-input deepsearch-module-textarea"
                          style={{
                            width: "100%",
                            padding: "10px 12px",
                            borderRadius: "8px",
                            resize: "vertical",
                            fontSize: "12px",
                            lineHeight: "1.5",
                          }}
                          value={collaborativePlan}
                          onChange={(e) => setCollaborativePlan(e.target.value)}
                          disabled={isLaunching}
                        />
                      </div>
                    ) : (
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          onClick={() => void handleRequestGooglePlan()}
                          disabled={loadingGooglePlan || isLaunching || !targetQuery.trim()}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "6px",
                            padding: "7px 13px",
                            borderRadius: "8px",
                            fontSize: "12px",
                            background: "rgba(99, 102, 241, 0.12)",
                            border: "1px solid rgba(99, 102, 241, 0.35)",
                            color: "var(--accent-primary, #818cf8)",
                            cursor: "pointer",
                            fontWeight: 500,
                          }}
                        >
                          <Sparkles size={14} />
                          <span>📋 Générer le plan d'investigation (Collaborative Planning)</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Sélecteur de format de sortie (Beau site HTML ou Beau PDF) */}
              <div className="output-format-card output-format-card-compact" role="group" aria-label="Format de sortie">
                <span className="output-format-label">
                  <FileText size={13} />
                  <span>Format de sortie privilégié :</span>
                </span>
                <div className="output-format-toggle">
                  <button
                    type="button"
                    className={`output-format-option ${outputFormat === "html" ? "is-selected" : ""}`}
                    onClick={() => setOutputFormat("html")}
                    title="Générer et consulter sous forme de beau site web HTML interactif (sommaire, navigation, thème sombre/clair)"
                  >
                    <Globe2 size={13} />
                    <span>Beau site HTML</span>
                    <small>Interactif & responsive</small>
                  </button>
                  <button
                    type="button"
                    className={`output-format-option ${outputFormat === "pdf" ? "is-selected" : ""}`}
                    onClick={() => setOutputFormat("pdf")}
                    title="Mise en page éditoriale A4 haute fidélité prête pour impression, archivage ou partage PDF"
                  >
                    <FileText size={13} />
                    <span>Beau document PDF</span>
                    <small>Édition & impression A4</small>
                  </button>
                </div>
              </div>

              {planError && <div className="deepsearch-modal-error-banner">{planError}</div>}
            </div>

            {/* Footer */}
            <div className="deepsearch-modal-footer">
              <div className="deepsearch-modal-footer-hint">
                <CornerDownLeft size={13} />
                <span>Appuyez sur Entrée ou validez pour démarrer la recherche autonome</span>
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
                  disabled={isLaunching || !targetQuery.trim() || !onLaunch}
                >
                  {isLaunching || loadingGooglePlan ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Compass size={16} />
                  )}
                  <span>
                    {isLaunching
                      ? "Lancement en cours…"
                      : loadingGooglePlan
                      ? "Établissement du plan Google…"
                      : isGoogleModel && (!showPlanReview || !collaborativePlan)
                      ? "📋 Établir le plan d'investigation"
                      : isGoogleModel && showPlanReview
                      ? "Valider le plan & Lancer l'investigation"
                      : "Lancer l'investigation approfondie"}
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
                          title="Ouvrir le beau site HTML interactif en plein écran"
                        >
                          <Globe2 size={13} />
                        </a>
                        <a
                          href={`/api/deep-search/reports/${report.id}/html?pdf=1`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="deepsearch-report-action-icon-btn pdf-btn"
                          title="Ouvrir et imprimer / enregistrer en Beau PDF"
                        >
                          <FileText size={13} />
                        </a>
                        <a
                          href={`/api/deep-search/reports/${report.id}/slides`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="deepsearch-report-action-icon-btn slides-btn"
                          title="Présentation type PowerPoint (diaporama interactif 16:9)"
                          onClick={(e) => {
                            e.currentTarget.href = `/api/deep-search/reports/${report.id}/slides?t=${Date.now()}`;
                          }}
                        >
                          <Presentation size={13} />
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
                  title="Ouvrir le beau site HTML interactif dans un nouvel onglet"
                >
                  <Globe2 size={13} />
                  <span>Beau site HTML</span>
                </a>

                <a
                  href={`/api/deep-search/reports/${activeReport.id}/html?pdf=1`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="deepsearch-reader-tool-btn deepsearch-pdf-tool-btn"
                  title="Ouvrir et imprimer / enregistrer en Beau PDF (mise en page éditoriale A4)"
                >
                  <FileText size={13} />
                  <span>Beau PDF</span>
                </a>

                <a
                  href={`/api/deep-search/reports/${activeReport.id}/slides`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="deepsearch-reader-tool-btn deepsearch-slides-tool-btn"
                  title="Présentation type PowerPoint de ce rapport (diaporama 16:9)"
                  onClick={(e) => {
                    e.currentTarget.href = `/api/deep-search/reports/${activeReport.id}/slides?t=${Date.now()}`;
                  }}
                >
                  <Presentation size={13} />
                  <span>Présentation PPT</span>
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
                <article className="deepsearch-reader-prose markdown">
                  <ReactMarkdown
                    urlTransform={url => url}
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeKatex]}
                    components={{
                      img: ({ src, alt }) =>
                        typeof src === "string" && src.trim() ? (
                          <span className="markdown-inline-figure">
                            <span className="markdown-inline-img-wrap">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={src}
                                alt={alt || "Illustration"}
                                loading="lazy"
                                className="markdown-inline-img"
                                onError={e => {
                                  const fig = e.currentTarget.closest(".markdown-inline-figure") as HTMLElement | null;
                                  if (fig) fig.style.display = "none";
                                }}
                              />
                            </span>
                            {alt && (
                              <span className="markdown-inline-caption">
                                <span className="markdown-inline-caption-text">{alt}</span>
                              </span>
                            )}
                          </span>
                        ) : null,
                      pre: ({ children }) => (
                        <div className="code-block">
                          <div className="code-label">
                            <span>Encart technique / Données / Code</span>
                          </div>
                          <pre>{children}</pre>
                        </div>
                      ),
                      table: ({ children }) => (
                        <div className="table-scroll">
                          <table>{children}</table>
                        </div>
                      ),
                    }}
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
