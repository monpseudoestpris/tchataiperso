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
  type Model,
  type StageModelsConfig,
} from "@/lib/api";
import { StageModelsModal, STAGES_DEFINITIONS } from "@/components/stage-models-modal";

type DeepSearchModalProps = {
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

const DEEPSEARCH_DETAIL_LEVELS: Record<
  number,
  { label: string; badge: string; desc: string }
> = {
  1: {
    label: "Synthèse flash très courte",
    badge: "Flash · 2 parties",
    desc: "1 paragraphe court par expert · ~400 mots au total · 2 vagues de recherche",
  },
  2: {
    label: "Synthèse exécutive concise",
    badge: "Concis · 3 parties",
    desc: "1 paragraphe synthétique par expert · ~800 mots au total · 2 vagues de recherche",
  },
  3: {
    label: "Résumé structuré",
    badge: "Résumé · 3 parties",
    desc: "1 à 2 paragraphes par expert · ~1 200 mots au total · 3 vagues de recherche",
  },
  4: {
    label: "Aperçu analytique",
    badge: "Analytique · 4 parties",
    desc: "2 paragraphes par expert · ~2 000 mots au total · 4 vagues de recherche",
  },
  5: {
    label: "Dossier standard équilibré",
    badge: "Standard · 4 parties",
    desc: "2 à 3 paragraphes par expert · ~2 800 mots au total · 5 vagues de recherche",
  },
  6: {
    label: "Analyse détaillée",
    badge: "Détaillé · 5 parties",
    desc: "3 paragraphes denses par expert · ~4 200 mots au total · 6 vagues de recherche",
  },
  7: {
    label: "Étude approfondie",
    badge: "Approfondi · 5 parties",
    desc: "3 à 4 paragraphes denses par expert · ~5 200 mots au total · 7 vagues de recherche",
  },
  8: {
    label: "Grand rapport complet (Recommandé)",
    badge: "Complet · 5 parties",
    desc: "4 à 5 paragraphes denses par expert · ~6 500 mots au total · 8 vagues de recherche",
  },
  9: {
    label: "Traité exhaustif très détaillé",
    badge: "Exhaustif · 6 parties",
    desc: "5 à 6 paragraphes très développés par expert · ~9 500 mots · 9 vagues de recherche",
  },
  10: {
    label: "Encyclopédique & Ultra-détaillé",
    badge: "Maximum · 7 parties",
    desc: "6 à 8 paragraphes exhaustifs par expert (x5+) · ~14 000+ mots · 10 vagues de recherche",
  },
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
  models = [],
  stageModels: initialStageModels,
  onChangeStageModels,
  onRefreshModels,
  onClose,
  onLaunch,
}: DeepSearchModalProps) {
  const [activeTab, setActiveTab] = useState<"plan" | "reports">(initialTab);
  const [outputFormat, setOutputFormat] = useState<"html" | "pdf">("html");
  const [detailLevel, setDetailLevel] = useState<number>(8);
  const [stageModels, setStageModels] = useState<StageModelsConfig>(() => {
    if (initialStageModels) return initialStageModels;
    try {
      const stored = localStorage.getItem("clair_stage_models_deep_search");
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
      localStorage.setItem("clair_stage_models_deep_search", JSON.stringify(newCfg));
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
        const generated = await planDeepSearch(conversationId, question, stageModels);
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

  // Auto-resize all theme textareas so the full text is always visible without internal scrollbar truncation
  useEffect(() => {
    inputRefs.current.forEach((el) => {
      if (el instanceof HTMLTextAreaElement) {
        el.style.height = "auto";
        el.style.height = `${Math.max(44, el.scrollHeight)}px`;
      }
    });
  }, [queries, loadingPlan, activeTab, isOpen]);

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
      await onLaunch(finalQueries, detailLevel, stageModels);
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
                    : "3 Experts par partie · Rédaction en 2 étapes"}
                </span>
              </div>
              <p>
                {activeReport
                  ? `Question initiale : « ${activeReport.topic} »`
                  : activeTab === "reports"
                  ? "Consultez, lisez en mode blog et exportez vos grands rapports d'investigation sauvegardés."
                  : "Découpage initial sans limite par Gemini Argon, validations multilingues, puis sortie en 2 temps : Planificateur + Écrivain développant chaque partie sous la perspective de 3 experts du domaine."}
              </p>
            </div>
          </div>

          <div className="deepsearch-modal-header-right">
            {/* Configure Stage Models Button */}
            {!activeReport && (
              <button
                type="button"
                onClick={() => setStageModelsModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-colors shadow-sm"
                title="Configurer les modèles IA utilisés pour chacune des 5 étapes du pipeline DeepSearch"
              >
                <Sparkles size={13} />
                <span>Modèles des étapes</span>
              </button>
            )}

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
            {/* Plan Body (Scrollable area containing target summary, format selector and full themes list) */}
            <div className="deepsearch-modal-body">
              {/* Question prompt summary */}
              <div className="deepsearch-modal-target-box deepsearch-modal-target-box-inline">
                <div className="deepsearch-modal-target-label">
                  <Sparkles size={13} />
                  <span>Découpage initial en points à aborder & Validations intermédiaires</span>
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
                  <span className="deepsearch-modal-pill" title="Exploration à 360° (ex. filières bouchées vs en tension), toutes langues & questions de contrôle">6. Vision 360° & Toutes langues</span>
                </div>
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

              {/* Curseur de niveau de détail (1 à 10 : de Synthèse courte à Ultra détaillé) */}
              <div className="detail-level-slider-card" role="group" aria-label="Niveau de détail de la réponse">
                <div className="detail-level-slider-header">
                  <div className="detail-level-slider-title">
                    <Sparkles size={13} />
                    <span>Niveau de détail souhaité :</span>
                    <strong className="detail-level-active-name">
                      Niveau {detailLevel}/10 — {DEEPSEARCH_DETAIL_LEVELS[detailLevel]?.label}
                    </strong>
                  </div>
                  <span className="detail-level-badge">
                    {DEEPSEARCH_DETAIL_LEVELS[detailLevel]?.badge}
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
                      className="detail-level-range-input"
                      aria-label="Curseur du niveau de détail de 1 à 10"
                    />
                    <div className="detail-level-ticks" aria-hidden="true">
                      {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((lvl) => (
                        <button
                          key={lvl}
                          type="button"
                          disabled={isLaunching}
                          className={`detail-level-tick ${detailLevel === lvl ? "is-active" : ""} ${detailLevel >= lvl ? "is-filled" : ""}`}
                          onClick={() => setDetailLevel(lvl)}
                          title={`Niveau ${lvl}/10 — ${DEEPSEARCH_DETAIL_LEVELS[lvl]?.label}`}
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
                  {DEEPSEARCH_DETAIL_LEVELS[detailLevel]?.desc}
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
                  <div className="deepsearch-modal-plan-title">
                    <ListFilter size={15} />
                    <span>Thèmes & angles planifiés (Gemini Argon · sans limite)</span>
                    <span className="deepsearch-modal-count-badge">{validQueriesCount}</span>
                  </div>
                  <span className="deepsearch-modal-plan-subtitle">
                    Vision 360° (ex. filières en tension ET filières bouchées) · Sortie en 2 temps (Agent Planificateur puis Agent Écrivain partie par partie)
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
                    <div key={index} className="deepsearch-modal-query-row deepsearch-theme-card">
                      <span className="deepsearch-modal-query-num" aria-hidden="true">
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
                        className="deepsearch-modal-query-input deepsearch-module-textarea deepsearch-theme-full-textarea"
                        value={query}
                        placeholder="Ex: 1. Définition et délimitation conceptuelle : analyser les principes clés et enjeux..."
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
                        title="Supprimer cette thématique"
                        aria-label={`Supprimer la thématique ${index + 1}`}
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
                    <span>Ajouter un angle ou une thématique de recherche</span>
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

      {stageModelsModalOpen && (
        <StageModelsModal
          isOpen={stageModelsModalOpen}
          modeTitle="DeepSearch"
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
