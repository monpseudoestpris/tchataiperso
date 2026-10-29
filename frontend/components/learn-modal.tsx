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
import { StageModelsModal } from "@/components/stage-models-modal";

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
  onLaunch?: (queries: string[], detailLevel?: number, stageModels?: StageModelsConfig) => void | Promise<void>;
};

const LEARN_DETAIL_LEVELS: Record<
  number,
  { label: string; badge: string; desc: string }
> = {
  1: {
    label: "Fiche synthèse ultra-courte",
    badge: "Flash · 2 modules",
    desc: "1 paragraphe court par expert + 20 Flashcards & 20 QCM · 2 vagues de recherche",
  },
  2: {
    label: "Synthèse de révision concise",
    badge: "Concis · 3 modules",
    desc: "1 paragraphe synthétique par expert + 20 Flashcards & 20 QCM · 2 vagues de recherche",
  },
  3: {
    label: "Résumé de cours structuré",
    badge: "Résumé · 3 modules",
    desc: "1 à 2 paragraphes par expert + 20 Flashcards & 20 QCM · 3 vagues de recherche",
  },
  4: {
    label: "Cours synthétique & analytique",
    badge: "Analytique · 4 modules",
    desc: "2 paragraphes par expert + 20 Flashcards & 20 QCM · 4 vagues de recherche",
  },
  5: {
    label: "Cours standard équilibré",
    badge: "Standard · 5 modules",
    desc: "2 à 3 paragraphes par expert + 20 Flashcards & 20 QCM · 5 vagues de recherche",
  },
  6: {
    label: "Cours détaillé avec cas pratique",
    badge: "Détaillé · 5 modules",
    desc: "3 paragraphes denses par expert + 20 Flashcards & 20 QCM · 6 vagues de recherche",
  },
  7: {
    label: "Formation approfondie",
    badge: "Approfondi · 6 modules",
    desc: "3 à 4 paragraphes denses par expert + 20 Flashcards & 20 QCM · 7 vagues de recherche",
  },
  8: {
    label: "Grand cours magistral complet (Recommandé)",
    badge: "Complet · 7 modules",
    desc: "4 à 5 paragraphes denses par expert + exercices + 20 Flashcards & 20 QCM · 8 vagues",
  },
  9: {
    label: "Traité académique très détaillé",
    badge: "Exhaustif · 7 modules",
    desc: "5 à 6 paragraphes très développés par expert + exercices + 20 Flashcards & 20 QCM",
  },
  10: {
    label: "Manuel encyclopédique & Ultra-détaillé",
    badge: "Maximum · 7 modules",
    desc: "6 à 8 paragraphes exhaustifs par expert (x5+) + cas intégraux + 20 Flashcards & 20 QCM",
  },
};

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
  const [detailLevel, setDetailLevel] = useState<number>(8);
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

  // Plan state
  const [queries, setQueries] = useState<string[]>([]);
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const inputRefs = useRef<(HTMLTextAreaElement | HTMLInputElement | null)[]>([]);
  const overlayMouseDownRef = useRef<EventTarget | null>(null);

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

    if (activeTab === "plan" && question.trim() && queries.length === 0 && !loadingPlan) {
      setLoadingPlan(true);
      setPlanError(null);
      planLearnMode(conversationId, question, stageModels)
        .then((generated) => {
          setQueries(generated.length ? generated : [question.trim()]);
        })
        .catch((err) => {
          console.error("Erreur génération plan de cours:", err);
          setPlanError(
            err instanceof Error ? err.message : "Impossible de générer le plan pédagogique.",
          );
          setQueries([question.trim()]);
        })
        .finally(() => {
          setLoadingPlan(false);
        });
    }

    if (activeTab === "reports") {
      setLoadingReports(true);
      fetchLearnReports()
        .then((data) => setReports(data))
        .catch((err) => console.error("Erreur chargement des cours:", err))
        .finally(() => setLoadingReports(false));
    }
  }, [isOpen, activeTab, question, conversationId]);

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
    if (isOpen && activeTab === "plan" && !loadingPlan && queries.length > 0) {
      const timer = setTimeout(() => {
        inputRefs.current[0]?.focus();
      }, 80);
      return () => clearTimeout(timer);
    }
  }, [isOpen, activeTab, loadingPlan, queries.length]);

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
  }, [isOpen, activeTab, queries, activeReport, reportToDelete]);

  // Auto-resize all module textareas so the full text is always visible without internal scrollbar truncation
  useEffect(() => {
    inputRefs.current.forEach((el) => {
      if (el instanceof HTMLTextAreaElement) {
        el.style.height = "auto";
        el.style.height = `${Math.max(44, el.scrollHeight)}px`;
      }
    });
  }, [queries, loadingPlan, activeTab, isOpen]);

  if (!isOpen) return null;

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
      const generated = await planLearnMode(conversationId, question);
      setQueries(generated.length ? generated : [question.trim()]);
    } catch (err) {
      setPlanError(
        err instanceof Error ? err.message : "Erreur lors de la régénération du plan de cours.",
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
      await onLaunch(finalQueries, detailLevel, stageModels);
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

  const validQueriesCount = queries.filter((q) => q.trim().length > 0).length;
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
                    : "3 Experts par module · Rédaction en 2 étapes"}
                </span>
              </div>
              <p>
                {activeReport
                  ? `Sujet enseigné : « ${activeReport.topic} »`
                  : activeTab === "reports"
                  ? "Consultez, révisez et exportez vos grands cours magistraux sauvegardés."
                  : "Modules définis sans limite par Gemini Argon, validations multilingues, puis sortie en 2 temps : Planificateur + Écrivain développant chaque module avec la perspective de 3 experts du domaine."}
              </p>
            </div>
          </div>

          <div className="deepsearch-modal-header-right">
            {!activeReport && (
              <button
                type="button"
                onClick={() => setStageModelsModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors shadow-sm"
                title="Configurer les modèles IA utilisés pour chacune des 5 étapes du Mode Apprendre"
              >
                <Sparkles size={13} />
                <span>Modèles des étapes</span>
              </button>
            )}

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
              <div className="deepsearch-modal-target-box learn-modal-target-box deepsearch-modal-target-box-inline">
                <div className="deepsearch-modal-target-label learn-target-label">
                  <Sparkles size={13} />
                  <span>Planification pédagogique · Sujet à enseigner</span>
                </div>
                <div className="deepsearch-modal-target-text">
                  « {question.trim() || "Aucun sujet défini"} »
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px", fontSize: "11px" }}>
                  <span className="deepsearch-modal-pill learn-modal-pill" title="Intuitions premières, définitions et analogies">1. Prérequis & Fondations</span>
                  <span className="deepsearch-modal-pill learn-modal-pill" title="Fonctionnement interne, architectures et théories">2. Principes & Fonctionnement</span>
                  <span className="deepsearch-modal-pill learn-modal-pill" title="Tutoriels pas à pas, exemples de code ou exercices guidés">3. Cas pratiques & Applications</span>
                  <span className="deepsearch-modal-pill learn-modal-pill" title="Erreurs fréquentes, anti-patterns et règles de l'art">4. Pièges & Bonnes pratiques</span>
                  <span className="deepsearch-modal-pill learn-modal-pill" title="Usages/compétences en tension vs approches obsolètes ou filières bouchées">5. Vision Panoramique 360°</span>
                  <span className="deepsearch-modal-pill learn-modal-pill" title="Agent Planificateur puis Agent Écrivain partie par partie + 20 Flashcards & 20 QCM">6. Sortie 2 temps & Quiz</span>
                </div>
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
                    title="Générer et consulter sous forme de cours interactif (avec 20 flashcards 3D et quizz interactif)"
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

              {/* Curseur de niveau de détail (1 à 10 : de Synthèse courte à Ultra détaillé) */}
              <div className="detail-level-slider-card learn-detail-level-slider-card" role="group" aria-label="Niveau de détail du cours">
                <div className="detail-level-slider-header">
                  <div className="detail-level-slider-title">
                    <Sparkles size={13} />
                    <span>Niveau de détail souhaité :</span>
                    <strong className="detail-level-active-name">
                      Niveau {detailLevel}/10 — {LEARN_DETAIL_LEVELS[detailLevel]?.label}
                    </strong>
                  </div>
                  <span className="detail-level-badge learn-detail-level-badge">
                    {LEARN_DETAIL_LEVELS[detailLevel]?.badge}
                  </span>
                </div>
                <div className="detail-level-slider-control">
                  <span
                    className="detail-level-pole"
                    onClick={() => !isLaunching && setDetailLevel(1)}
                    title="Régler sur 1 : Synthèse très courte"
                  >
                    1 · Synthèse courte
                  </span>
                  <div className="detail-level-range-wrap">
                    <input
                      type="range"
                      min={1}
                      max={10}
                      step={1}
                      value={detailLevel}
                      disabled={isLaunching}
                      onChange={(e) => setDetailLevel(Number(e.target.value))}
                      className="detail-level-range-input learn-detail-level-range-input"
                      aria-label="Curseur du niveau de détail du cours de 1 à 10"
                    />
                    <div className="detail-level-ticks" aria-hidden="true">
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((lvl) => (
                        <button
                          key={lvl}
                          type="button"
                          disabled={isLaunching}
                          className={`detail-level-tick learn-detail-level-tick ${detailLevel === lvl ? "is-active" : ""} ${detailLevel >= lvl ? "is-filled" : ""}`}
                          onClick={() => setDetailLevel(lvl)}
                          title={`Niveau ${lvl}/10 — ${LEARN_DETAIL_LEVELS[lvl]?.label}`}
                        >
                          {lvl}
                        </button>
                      ))}
                    </div>
                  </div>
                  <span
                    className="detail-level-pole detail-level-pole-right"
                    onClick={() => !isLaunching && setDetailLevel(10)}
                    title="Régler sur 10 : Ultra détaillé"
                  >
                    10 · Ultra détaillé
                  </span>
                </div>
                <div className="detail-level-slider-desc">
                  {LEARN_DETAIL_LEVELS[detailLevel]?.desc}
                </div>

                {/* Pipeline Stages Mini-Summary Bar */}
                <div className="mt-2.5 pt-2 border-t border-surface-border/50 flex flex-wrap items-center justify-between gap-2 text-xs">
                  <div className="flex flex-wrap items-center gap-1.5 text-text-muted">
                    <span className="font-medium text-text-secondary">Pipeline IA :</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-subtle font-mono text-[11px] border border-surface-border" title="Étape 1 · Planification">
                      Plan: {stageModels.plan_model?.split("/").pop() || "Gemini Argon"}
                    </span>
                    <span className="text-text-muted/60">→</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-subtle font-mono text-[11px] border border-surface-border" title="Étape 2 · Recherche & Approfondissement">
                      Search: {stageModels.search_model?.split("/").pop() || "Gemini Flash"}
                    </span>
                    <span className="text-text-muted/60">→</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-subtle font-mono text-[11px] border border-surface-border" title="Étape 3 · Collège des 3 Experts">
                      3 Experts: {stageModels.expert_model?.split("/").pop() || "Gemini Flash"}
                    </span>
                    <span className="text-text-muted/60">→</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-subtle font-mono text-[11px] border border-surface-border" title="Étape 4 · Rédaction Finale">
                      Synthèse: {stageModels.synthesis_model?.split("/").pop() || "Gemini Flash"}
                    </span>
                    <span className="text-text-muted/60">→</span>
                    <span className="px-1.5 py-0.5 rounded bg-surface-subtle font-mono text-[11px] border border-surface-border" title="Étape 5 · Relecture Critique Astra & Validation">
                      Audit: {stageModels.audit_model?.split("/").pop() || "GPT-6 Astra"}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setStageModelsModalOpen(true)}
                    className="text-primary hover:underline font-medium text-[11px] shrink-0"
                  >
                    Personnaliser les 5 étapes →
                  </button>
                </div>
              </div>

              <div className="deepsearch-modal-body-top">
                <div className="deepsearch-modal-plan-header-block">
                  <div className="deepsearch-modal-plan-title learn-plan-title">
                    <ListFilter size={15} />
                    <span>Modules de recherche didactique (Gemini Argon · Sans limite)</span>
                    <span className="deepsearch-modal-count-badge learn-count-badge">{validQueriesCount}</span>
                  </div>
                  <span className="deepsearch-modal-plan-subtitle">
                    Vision 360° (usages en tension, pièges, filières saturées) · Sortie en 2 temps (Agent Planificateur puis Agent Écrivain partie par partie)
                  </span>
                </div>
                <button
                  type="button"
                  className="deepsearch-modal-regenerate-btn learn-regenerate-btn"
                  onClick={handleRegeneratePlan}
                  disabled={loadingPlan}
                  title="Demander à l'IA de recalculer de nouveaux angles pédagogiques"
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
                  <p>Élaboration du programme de formation et des modules de cours…</p>
                  <span>Recherche des meilleurs manuels, documentations officielles et cas pratiques</span>
                </div>
              ) : (
                <div className="deepsearch-modal-queries-list">
                  {queries.map((query, index) => (
                    <div key={index} className="deepsearch-modal-query-row learn-query-row deepsearch-theme-card">
                      <span className="deepsearch-modal-query-num learn-query-num" aria-hidden="true">
                        {index + 1}
                      </span>
                      <textarea
                        ref={(el) => {
                          inputRefs.current[index] = el;
                          if (el) {
                            el.style.height = "auto";
                            el.style.height = `${Math.max(44, el.scrollHeight)}px`;
                          }
                        }}
                        rows={1}
                        className="deepsearch-modal-query-input learn-module-textarea deepsearch-theme-full-textarea"
                        value={query}
                        placeholder="Ex: 1. Genèse, intuition et fondations conceptuelles : comprendre la finalité du sujet..."
                        onChange={(e) => {
                          handleQueryChange(index, e.target.value);
                          e.target.style.height = "auto";
                          e.target.style.height = `${Math.max(44, e.target.scrollHeight)}px`;
                        }}
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
                        title="Supprimer ce module"
                        aria-label={`Supprimer le module ${index + 1}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))}

                  <button
                    type="button"
                    className="deepsearch-modal-add-btn learn-add-btn"
                    onClick={handleAddQuery}
                    disabled={isLaunching}
                  >
                    <Plus size={15} />
                    <span>Ajouter un angle ou un module d'apprentissage</span>
                  </button>
                </div>
              )}
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
                  disabled={loadingPlan || isLaunching || validQueriesCount === 0 || !onLaunch}
                >
                  {isLaunching ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <GraduationCap size={16} />
                  )}
                  <span>
                    {isLaunching
                      ? "Création du cours en cours…"
                      : `Créer le cours complet (${validQueriesCount} modules)`}
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

      {stageModelsModalOpen && (
        <StageModelsModal
          isOpen={stageModelsModalOpen}
          modeTitle="Mode Apprendre"
          config={stageModels}
          models={models}
          onChangeConfig={handleUpdateStageModels}
          onClose={() => setStageModelsModalOpen(false)}
          onRefreshModels={onRefreshModels}
        />
      )}
    </div>
  );
}

