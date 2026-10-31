"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Award,
  BookOpen,
  Calendar,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  CornerDownLeft,
  Download,
  ExternalLink,
  FileText,
  Globe2,
  GraduationCap,
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
  deleteLearnReport,
  fetchLearnReport,
  fetchLearnReports,
  planLearnMode,
  type LearnReport,
  type Model,
  type StageModelsConfig,
} from "@/lib/api";
import { LearnFlashcards } from "@/components/learn-flashcards";
import { LearnQuiz } from "@/components/learn-quiz";
import {
  parseFlashcardsFromMarkdown,
  parseQuizFromMarkdown,
  stripInteractiveModulesForBody,
} from "@/lib/learn-parser";

type LearnModalProps = {
  isOpen: boolean;
  question?: string;
  conversationId?: string | null;
  initialTab?: "plan" | "reports";
  initialReportId?: string | null;
  models?: Model[];
  stageModels?: StageModelsConfig;
  onChangeStageModels?: (cfg: StageModelsConfig) => void;
  onRefreshModels?: () => Promise<void>;
  onClose: () => void;
  onLaunch?: (
    queries: string[],
    detailLevel?: number,
    stageModels?: StageModelsConfig,
    selectedModel?: string,
    interactionId?: string,
    planFeedback?: string,
  ) => void | Promise<void>;
};

export const LEARN_RESEARCH_ENGINES = [
  {
    id: "perplexity/sonar-deep-research",
    label: "Sonar Deep Research",
    providerBadge: "Perplexity · OpenRouter",
    badge: "Exhaustif · Académique",
    desc: "Cours magistral approfondi, exploration web exhaustive et recoupement des sources académiques.",
  },
  {
    id: "perplexity/sonar-pro-search",
    label: "Sonar Pro Search",
    providerBadge: "Perplexity · OpenRouter",
    badge: "Pro · Rapide & Didactique",
    desc: "Cours complet rapide, agile et sourcé avec cas pratiques et citations directes.",
  },
  {
    id: "google/deep-research-preview-04-2026",
    label: "Google Gemini Deep Research",
    providerBadge: "Google Gemini API",
    badge: "Agent Google · Interactions API",
    desc: "Agent autonome Google Gemini Deep Research pour analyse didactique en profondeur (requiert GOOGLE_API_KEY).",
  },
  {
    id: "google/deep-research-max-preview-04-2026",
    label: "Google Gemini Deep Research Max",
    providerBadge: "Google Gemini API",
    badge: "Max · Traité Encyclopédique",
    desc: "Version maximale de Google Deep Research pour concevoir un traité complet et exhaustif.",
  },
];

function formatCourseDate(dateStr: string): string {
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

function estimateLearningTime(text: string): number {
  const words = text.trim().split(/\s+/).length;
  return Math.max(1, Math.round(words / 180));
}

function extractDomain(rawUrl: string): string {
  try {
    const url = rawUrl.startsWith("http://") || rawUrl.startsWith("https://") ? rawUrl : `https://${rawUrl}`;
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return rawUrl;
  }
}

export function LearnModal({
  isOpen,
  question = "",
  conversationId,
  initialTab = "plan",
  initialReportId = null,
  models = [],
  stageModels: initialStageModels,
  onChangeStageModels,
  onRefreshModels,
  onClose,
  onLaunch,
}: LearnModalProps) {
  const [activeTab, setActiveTab] = useState<"plan" | "reports">(initialTab);
  const [outputFormat, setOutputFormat] = useState<"html" | "pdf">("html");
  const [selectedEngineModel, setSelectedEngineModel] = useState<string>("perplexity/sonar-pro-search");
  const [stageModels, setStageModels] = useState<StageModelsConfig>(() => {
    if (initialStageModels) return initialStageModels;
    try {
      const stored = localStorage.getItem("clair_stage_models_learn_mode");
      if (stored) return JSON.parse(stored);
    } catch {}
    return {
      plan_model: "google/gemini-4-argon",
      search_model: "google/gemini-3.8-flash",
      expert_model: "google/gemini-3.8-flash",
      synthesis_model: "google/gemini-3.8-flash",
      audit_model: "openai/gpt-6-astra",
    };
  });
  const [stageModelsModalOpen, setStageModelsModalOpen] = useState(false);

  const handleUpdateStageModels = (newCfg: StageModelsConfig) => {
    setStageModels(newCfg);
    try {
      localStorage.setItem("clair_stage_models_learn_mode", JSON.stringify(newCfg));
    } catch {}
    if (onChangeStageModels) onChangeStageModels(newCfg);
  };

  // Course subject state
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

  // Sync question when prop changes
  useEffect(() => {
    setTargetQuery(question.trim());
  }, [question]);

  // Courses state
  const [reports, setReports] = useState<LearnReport[]>([]);
  const [loadingReports, setLoadingReports] = useState(false);
  const [reportsSearch, setReportsSearch] = useState("");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(initialReportId);
  const [activeReport, setActiveReport] = useState<LearnReport | null>(null);
  const [loadingActiveReport, setLoadingActiveReport] = useState(false);
  const [copiedReport, setCopiedReport] = useState(false);
  const [reportToDelete, setReportToDelete] = useState<LearnReport | null>(null);
  const [showAllSources, setShowAllSources] = useState(false);

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

  useEffect(() => {
    if (!isOpen) return;

    if (activeTab === "reports") {
      setLoadingReports(true);
      fetchLearnReports()
        .then((data) => setReports(data))
        .catch((err) => console.error("Erreur chargement des cours:", err))
        .finally(() => setLoadingReports(false));
    }
  }, [isOpen, activeTab]);

  useEffect(() => {
    if (!isOpen || !selectedReportId) return;
    setShowAllSources(false);
    setLoadingActiveReport(true);
    fetchLearnReport(selectedReportId)
      .then((rep) => setActiveReport(rep))
      .catch((err) => console.error("Erreur chargement détail du cours:", err))
      .finally(() => setLoadingActiveReport(false));
  }, [isOpen, selectedReportId]);

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
        void handleConfirmPlan();
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
      const res = await planLearnMode(conversationId, cleanQ, undefined, selectedEngineModel, prevId);
      if (res.plan_text) {
        setCollaborativePlan(res.plan_text);
        if (res.interaction_id) setInteractionId(res.interaction_id);
      }
    } catch (err) {
      setPlanError(
        err instanceof Error ? err.message : "Impossible d'obtenir la proposition de plan pédagogique de Google Deep Research.",
      );
    } finally {
      setLoadingGooglePlan(false);
    }
  }

  async function handleConfirmPlan() {
    if (!onLaunch || isLaunching) return;
    const cleanQ = targetQuery.trim() || question.trim();
    if (!cleanQ) return;

    if (isGoogleModel && (!showPlanReview || !collaborativePlan)) {
      await handleRequestGooglePlan();
      return;
    }

    setIsLaunching(true);
    setPlanError(null);
    try {
      const activeInteractionId = isGoogleModel && showPlanReview && interactionId ? interactionId : undefined;
      const activeFeedback = isGoogleModel && showPlanReview && collaborativePlan ? collaborativePlan : undefined;
      await onLaunch([cleanQ], undefined, stageModels, selectedEngineModel, activeInteractionId, activeFeedback);
      onClose();
    } catch (err) {
      setPlanError(
        err instanceof Error ? err.message : "Erreur lors du lancement de la création du cours.",
      );
    } finally {
      setIsLaunching(false);
    }
  }

  async function handleDeleteReport(reportId: string) {
    try {
      await deleteLearnReport(reportId);
      setReports((prev) => prev.filter((r) => r.id !== reportId));
      if (selectedReportId === reportId) {
        setSelectedReportId(null);
        setActiveReport(null);
      }
      setReportToDelete(null);
    } catch (err) {
      console.error("Erreur suppression du cours:", err);
    }
  }

  function handleCopyReport(rep: LearnReport) {
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
      className="deepsearch-modal-overlay learn-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="learn-modal-title"
      onMouseDown={(e) => {
        overlayMouseDownRef.current = e.target;
      }}
      onClick={(e) => {
        if (overlayMouseDownRef.current === e.currentTarget && e.target === e.currentTarget && !isLaunching) {
          onClose();
        }
      }}
    >
      <div className={`deepsearch-modal-container learn-modal-container ${(activeReport || activeTab === "reports") ? "deepsearch-modal-wide" : ""}`}>
        {/* Top Header & Tabs */}
        <div className="deepsearch-modal-header learn-modal-header">
          <div className="deepsearch-modal-header-left">
            <div className="deepsearch-modal-badge-icon learn-modal-badge-icon" aria-hidden="true">
              <GraduationCap size={22} />
            </div>
            <div>
              <div className="deepsearch-modal-title-row">
                <h2 id="learn-modal-title">
                  {activeReport
                    ? activeReport.title
                    : activeTab === "reports"
                    ? "Mes Cours & Formations"
                    : "Conception du cours · Plan d'apprentissage"}
                </h2>
                <span className="deepsearch-modal-pill learn-modal-pill">
                  {activeReport
                    ? `Mode Cours Interactif · ${activeReport.sources_count} supports`
                    : "⚡ Perplexity Sonar & Google Deep Research"}
                </span>
              </div>
              <p>
                {activeReport
                  ? `Sujet enseigné : « ${activeReport.topic} »`
                  : activeTab === "reports"
                  ? "Consultez, révisez et exportez vos grands cours magistraux sauvegardés."
                  : "Cours magistral didactique, approfondi et sourcé conçu avec recherche web autonome en temps réel et auto-évaluation."}
              </p>
            </div>
          </div>

          <div className="deepsearch-modal-header-right">
            {!activeReport && (
              <div className="deepsearch-tabs-pills" role="tablist">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "plan"}
                  className={`deepsearch-tab-pill learn-tab-pill ${activeTab === "plan" ? "is-active" : ""}`}
                  onClick={() => setActiveTab("plan")}
                >
                  <WandSparkles size={13} />
                  <span>Plan du cours</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "reports"}
                  className={`deepsearch-tab-pill learn-tab-pill ${activeTab === "reports" ? "is-active" : ""}`}
                  onClick={() => setActiveTab("reports")}
                >
                  <BookOpen size={13} />
                  <span>Mes Cours</span>
                  {reports.length > 0 && (
                    <span className="deepsearch-tab-counter learn-tab-counter">{reports.length}</span>
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
            <div className="deepsearch-modal-body">
              {/* Sujet du cours */}
              <div className="output-format-card" role="group" aria-label="Sujet du cours">
                <span className="output-format-label">
                  <Sparkles size={14} />
                  <span>Sujet ou concept à apprendre :</span>
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
                  placeholder="Précisez le sujet, concept ou domaine que vous souhaitez maîtriser…"
                  disabled={isLaunching}
                />
              </div>

              {/* Sélecteur de moteur d'apprentissage */}
              <div className="output-format-card" role="group" aria-label="Moteur de cours approfondi">
                <span className="output-format-label">
                  <GraduationCap size={14} />
                  <span>Moteur de recherche & conception du cours :</span>
                </span>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "10px", marginTop: "8px" }}>
                  {LEARN_RESEARCH_ENGINES.map((engine) => {
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
                          <strong>Conception de la structure du cours…</strong>
                          <p style={{ margin: "2px 0 0 0", fontSize: "11px", color: "var(--text-muted, #94a3b8)" }}>
                            Consultation de Google Gemini Deep Research pour établir les modules didactiques.
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
                            <span>📋 Programme pédagogique Google Gemini — À valider :</span>
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
                            title="Demander une nouvelle proposition de programme didactique"
                          >
                            <RefreshCw size={11} />
                            <span>Régénérer</span>
                          </button>
                        </div>
                        <p style={{ fontSize: "11px", color: "var(--text-muted, #94a3b8)", margin: "0 0 8px 0" }}>
                          Vous pouvez ajuster les modules, notions clés ou exercices de révision. Le modèle appliquera ce programme.
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
                          <span>📋 Concevoir le plan du cours (Collaborative Planning)</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Sélecteur de format de sortie (Beau site HTML ou Beau PDF) */}
              <div className="output-format-card learn-output-format-card output-format-card-compact" role="group" aria-label="Format de sortie">
                <span className="output-format-label">
                  <FileText size={13} />
                  <span>Format de sortie privilégié :</span>
                </span>
                <div className="output-format-toggle">
                  <button
                    type="button"
                    className={`output-format-option ${outputFormat === "html" ? "is-selected" : ""}`}
                    onClick={() => setOutputFormat("html")}
                    title="Générer et consulter sous forme de cours interactif (avec flashcards et quizz interactif)"
                  >
                    <Globe2 size={13} />
                    <span>Beau site HTML</span>
                    <small>Cours & modules 3D interactifs</small>
                  </button>
                  <button
                    type="button"
                    className={`output-format-option ${outputFormat === "pdf" ? "is-selected" : ""}`}
                    onClick={() => setOutputFormat("pdf")}
                    title="Polycopié de formation haute fidélité A4 avec cours intégral et grilles de révision prêtes à imprimer"
                  >
                    <FileText size={13} />
                    <span>Beau polycopié PDF</span>
                    <small>Fiches de cours & révision A4</small>
                  </button>
                </div>
              </div>

              {planError && <div className="deepsearch-modal-error-banner">{planError}</div>}
            </div>

            <div className="deepsearch-modal-footer">
              <div className="deepsearch-modal-footer-hint">
                <CornerDownLeft size={13} />
                <span>Appuyez sur Entrée ou validez pour lancer la création du cours</span>
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
                  className="deepsearch-modal-launch-btn learn-modal-launch-btn"
                  onClick={() => void handleConfirmPlan()}
                  disabled={isLaunching || !targetQuery.trim() || !onLaunch}
                >
                  {isLaunching || loadingGooglePlan ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <GraduationCap size={16} />
                  )}
                  <span>
                    {isLaunching
                      ? "Création du cours en cours…"
                      : loadingGooglePlan
                      ? "Conception du plan didactique…"
                      : isGoogleModel && (!showPlanReview || !collaborativePlan)
                      ? "📋 Concevoir le plan du cours"
                      : isGoogleModel && showPlanReview
                      ? "Valider le plan & Concevoir le cours"
                      : "Créer le cours complet"}
                  </span>
                </button>
              </div>
            </div>
          </>
        )}

        {/* ===================== TAB 2: COURSES LIST ===================== */}
        {activeTab === "reports" && !activeReport && (
          <div className="learn-reports-container">
            {/* Toolbar */}
            <div className="learn-reports-toolbar">
              <div className="learn-reports-search-box">
                <Search size={15} className="learn-reports-search-icon" />
                <input
                  type="text"
                  placeholder="Rechercher parmi mes cours..."
                  value={reportsSearch}
                  onChange={(e) => setReportsSearch(e.target.value)}
                  className="learn-reports-search-input"
                />
                {reportsSearch && (
                  <button
                    type="button"
                    className="learn-reports-clear-search"
                    onClick={() => setReportsSearch("")}
                    title="Effacer la recherche"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>

              <div className="learn-reports-toolbar-actions">
                <div className="learn-reports-count-pill">
                  <GraduationCap size={13} />
                  <span>{filteredReports.length} cours</span>
                </div>
                <button
                  type="button"
                  className="learn-reports-refresh-btn"
                  onClick={() => {
                    setLoadingReports(true);
                    fetchLearnReports()
                      .then((data) => setReports(data))
                      .finally(() => setLoadingReports(false));
                  }}
                  disabled={loadingReports}
                  title="Actualiser la liste des cours"
                >
                  <RefreshCw size={13} className={loadingReports ? "spin" : ""} />
                  <span>Actualiser</span>
                </button>
              </div>
            </div>

            {loadingReports ? (
              <div className="learn-reports-loading-state">
                <LoaderCircle size={32} className="spin" />
                <p>Chargement de vos cours magistraux…</p>
              </div>
            ) : filteredReports.length === 0 ? (
              <div className="learn-reports-empty">
                <div className="learn-reports-empty-icon-box">
                  <GraduationCap size={38} strokeWidth={1.4} />
                </div>
                <h3>Aucun cours disponible</h3>
                <p>
                  {reportsSearch
                    ? "Aucun cours ne correspond à votre recherche. Essayez un autre mot-clé."
                    : "Activez le « Mode Apprendre » dans le compositeur de tchat pour concevoir votre premier cours magistral interactif avec 20 Flashcards et Quizz."}
                </p>
                {question.trim() && (
                  <button
                    type="button"
                    className="learn-reports-empty-btn"
                    onClick={() => setActiveTab("plan")}
                  >
                    <WandSparkles size={14} />
                    <span>Créer un cours sur ce sujet</span>
                  </button>
                )}
              </div>
            ) : (
              <div className="learn-reports-grid">
                {filteredReports.map((rep) => {
                  const readTime = estimateLearningTime(rep.markdown_content);
                  return (
                    <article key={rep.id} className="learn-course-card">
                      <div className="learn-course-card-accent" />

                      <div className="learn-course-card-body">
                        <div className="learn-course-card-header">
                          <span className="learn-course-badge">
                            <GraduationCap size={12} />
                            <span>Cours complet</span>
                          </span>
                          <span className="learn-course-date">
                            <Calendar size={11} />
                            <span>{formatCourseDate(rep.created_at)}</span>
                          </span>
                        </div>

                        <h3 className="learn-course-title">
                          <button
                            type="button"
                            onClick={() => setSelectedReportId(rep.id)}
                            title="Ouvrir dans le lecteur interactif"
                          >
                            {rep.title}
                          </button>
                        </h3>

                        <div className="learn-course-topic-box">
                          <span className="learn-course-topic-label">Sujet :</span>
                          <span className="learn-course-topic-text">{rep.topic}</span>
                        </div>

                        <div className="learn-course-meta-chips">
                          <span className="learn-course-chip">
                            <Clock size={11} />
                            <span>~{readTime} min d&apos;apprentissage</span>
                          </span>
                          <span className="learn-course-chip">
                            <Globe2 size={11} />
                            <span>{rep.sources_count} supports</span>
                          </span>
                          <span className="learn-course-chip highlight">
                            <Sparkles size={11} />
                            <span>20 Flashcards & Quizz</span>
                          </span>
                        </div>

                        <div className="learn-course-card-footer">
                          <button
                            type="button"
                            className="learn-course-open-btn"
                            onClick={() => setSelectedReportId(rep.id)}
                            title="Ouvrir le cours avec les Flashcards et le Quizz"
                          >
                            <BookOpen size={13} />
                            <span>Consulter</span>
                          </button>

                          <div className="learn-course-secondary-actions">
                            <a
                              href={rep.html_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="learn-course-icon-btn"
                              title="Consulter le beau site HTML interactif en plein écran"
                            >
                              <Globe2 size={13} />
                            </a>
                            <a
                              href={`${rep.html_url}?pdf=1`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="learn-course-icon-btn pdf-btn"
                              title="Ouvrir et imprimer / enregistrer en Beau polycopié PDF"
                            >
                              <FileText size={13} />
                            </a>
                            <a
                              href={`${rep.html_url}?download=1`}
                              className="learn-course-icon-btn"
                              title="Télécharger le fichier .html complet"
                              download
                            >
                              <Download size={13} />
                            </a>
                            <button
                              type="button"
                              className="learn-course-icon-btn danger"
                              onClick={() => setReportToDelete(rep)}
                              title="Supprimer ce cours"
                            >
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ===================== VIEWER: SINGLE COURSE ===================== */}
        {activeReport && (
          <div className="deepsearch-modal-body deepsearch-reader-body">
            <div className="deepsearch-reader-topbar">
              <button
                type="button"
                className="deepsearch-reader-back-btn"
                onClick={() => {
                  setSelectedReportId(null);
                  setActiveReport(null);
                }}
              >
                <ArrowLeft size={14} />
                <span>Retour aux cours</span>
              </button>

              <div className="deepsearch-reader-actions">
                <button
                  type="button"
                  className="deepsearch-reader-tool-btn"
                  onClick={() => handleCopyReport(activeReport)}
                  title="Copier le texte Markdown intégral"
                >
                  {copiedReport ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                  <span>{copiedReport ? "Copié !" : "Copier Markdown"}</span>
                </button>
                <a
                  href={activeReport.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="deepsearch-reader-tool-btn"
                  title="Ouvrir le beau site HTML interactif dans un nouvel onglet"
                >
                  <Globe2 size={14} />
                  <span>Beau site HTML</span>
                </a>
                <a
                  href={`${activeReport.html_url}?pdf=1`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="deepsearch-reader-tool-btn learn-pdf-tool-btn"
                  title="Ouvrir et imprimer / enregistrer en Beau polycopié PDF (format A4)"
                >
                  <FileText size={14} />
                  <span>Beau PDF</span>
                </a>
                <a
                  href={`${activeReport.html_url}?download=1`}
                  className="deepsearch-reader-tool-btn"
                  title="Télécharger le fichier .html complet"
                  download
                >
                  <Download size={14} />
                  <span>Exporter .html</span>
                </a>
                <button
                  type="button"
                  className="deepsearch-reader-tool-btn deepsearch-action-delete"
                  onClick={() => setReportToDelete(activeReport)}
                  title="Supprimer ce cours"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            {loadingActiveReport ? (
              <div className="deepsearch-modal-loading-state">
                <LoaderCircle size={28} className="spin" />
                <p>Chargement du cours…</p>
              </div>
            ) : (
              <div className="deepsearch-reader-content">
                <header className="deepsearch-reader-hero learn-reader-hero">
                  <div className="deepsearch-reader-hero-meta">
                    <span className="meta-tag learn-meta-tag">
                      <GraduationCap size={13} />
                      Grand Cours Magistral
                    </span>
                    <span>
                      <Calendar size={13} />
                      {formatCourseDate(activeReport.created_at)}
                    </span>
                    <span>
                      <Clock size={13} />
                      ~{estimateLearningTime(activeReport.markdown_content)} min d'apprentissage
                    </span>
                    <span>
                      <Globe2 size={13} />
                      {activeReport.sources_count} supports didactiques
                    </span>
                  </div>
                  <h1>{activeReport.title}</h1>
                  <div className="deepsearch-reader-topic-box learn-reader-topic-box">
                    <strong>Sujet :</strong>
                    <span>{activeReport.topic}</span>
                  </div>
                </header>

                {(() => {
                  const flashcards =
                    activeReport.flashcards && activeReport.flashcards.length > 0
                      ? activeReport.flashcards
                      : parseFlashcardsFromMarkdown(activeReport.markdown_content, activeReport.topic);

                  const quizQuestions =
                    activeReport.quiz && activeReport.quiz.length > 0
                      ? activeReport.quiz
                      : parseQuizFromMarkdown(activeReport.markdown_content, activeReport.topic);

                  const cleanMarkdown = stripInteractiveModulesForBody(activeReport.markdown_content);

                  return (
                    <>
                      {/* Barre de navigation rapide dans le cours */}
                      <div className="learn-reader-quick-nav">
                        <a href="#learn-section-course" className="learn-quick-nav-pill">
                          <BookOpen size={13} />
                          <span>📖 Cours Magistral</span>
                        </a>
                        <a href="#learn-section-flashcards" className="learn-quick-nav-pill">
                          <Sparkles size={13} />
                          <span>📇 20 Flashcards 3D</span>
                        </a>
                        <a href="#learn-section-quiz" className="learn-quick-nav-pill">
                          <Award size={13} />
                          <span>🎯 Quizz (20 QCM)</span>
                        </a>
                        {activeReport.sources && activeReport.sources.length > 0 && (
                          <a href="#learn-section-sources" className="learn-quick-nav-pill">
                            <Globe2 size={13} />
                            <span>📚 {activeReport.sources.length} Supports</span>
                          </a>
                        )}
                      </div>

                      <article id="learn-section-course" className="deepsearch-reader-markdown markdown">
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
                                  <span>Encart didactique / Schéma / Code</span>
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
                          {cleanMarkdown}
                        </ReactMarkdown>
                      </article>

                      {/* Composant Dédié : 20 Flashcards Interactives 3D */}
                      <LearnFlashcards flashcards={flashcards} />

                      {/* Composant Dédié : Quizz 20 Questions interactif */}
                      <LearnQuiz questions={quizQuestions} />

                      {activeReport.sources && activeReport.sources.length > 0 && (
                        <section id="learn-section-sources" className="learn-reader-sources-block">
                          <div className="learn-reader-sources-header">
                            <div className="learn-reader-sources-title">
                              <BookOpen size={18} />
                              <h3>Supports didactiques et références ({activeReport.sources.length})</h3>
                            </div>
                            <p className="learn-reader-sources-desc">
                              Ressources, documentations officielles et supports didactiques mobilisés pour ce cours.
                            </p>
                          </div>

                          <div className="learn-reader-sources-grid">
                            {(showAllSources
                              ? activeReport.sources
                              : activeReport.sources.slice(0, 12)
                            ).map((src, idx) => {
                              const domain = extractDomain(src.url);
                              return (
                                <div key={idx} className="learn-reader-source-card">
                                  <div className="learn-source-card-top">
                                    <span className="learn-source-index">#{idx + 1}</span>
                                    <span className="learn-source-domain" title={src.url}>
                                      {domain}
                                    </span>
                                    {src.provider && (
                                      <span className="learn-source-provider">{src.provider}</span>
                                    )}
                                  </div>
                                  <h4 className="learn-source-card-title">
                                    <a href={src.url} target="_blank" rel="noopener noreferrer">
                                      {src.title || domain}
                                      <ExternalLink size={12} />
                                    </a>
                                  </h4>
                                  {src.snippet && (
                                    <p className="learn-source-card-snippet">« {src.snippet} »</p>
                                  )}
                                  <a
                                    href={src.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="learn-source-card-link"
                                  >
                                    Consulter la ressource didactique &rarr;
                                  </a>
                                </div>
                              );
                            })}
                          </div>

                          {activeReport.sources.length > 12 && (
                            <div className="learn-sources-toggle-container">
                              <button
                                type="button"
                                onClick={() => setShowAllSources(!showAllSources)}
                                className="learn-sources-toggle-btn"
                              >
                                {showAllSources ? (
                                  <>
                                    <ChevronUp size={16} />
                                    <span>Réduire l&apos;affichage des supports didactiques</span>
                                  </>
                                ) : (
                                  <>
                                    <ChevronDown size={16} />
                                    <span>
                                      Afficher l&apos;ensemble des {activeReport.sources.length} supports didactiques (+{activeReport.sources.length - 12})
                                    </span>
                                  </>
                                )}
                              </button>
                            </div>
                          )}
                        </section>
                      )}
                    </>
                  );
                })()}
              </div>
            )}
          </div>
        )}

        {/* Modal confirm delete */}
        {reportToDelete && (
          <div className="deepsearch-delete-overlay">
            <div className="deepsearch-delete-dialog">
              <div className="deepsearch-delete-icon">
                <Trash2 size={24} />
              </div>
              <h3>Supprimer ce cours ?</h3>
              <p>
                Êtes-vous sûr de vouloir supprimer définitivement « {reportToDelete.title} » ?
                Cette action est irréversible.
              </p>
              <div className="deepsearch-delete-actions">
                <button
                  type="button"
                  className="deepsearch-modal-cancel-btn"
                  onClick={() => setReportToDelete(null)}
                >
                  Annuler
                </button>
                <button
                  type="button"
                  className="deepsearch-delete-confirm-btn"
                  onClick={() => handleDeleteReport(reportToDelete.id)}
                >
                  Confirmer la suppression
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

