"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Bot,
  Brain,
  Check,
  ChevronDown,
  Code2,
  Copy,
  Cpu,
  ExternalLink,
  Eye,
  FileText,
  Globe2,
  History,
  LoaderCircle,
  MessageSquarePlus,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
  Star,
  Trash2,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  api,
  errorMessage,
  fetchHermesStatus,
  streamHermesRun,
  type HermesCreatedPage,
  type HermesEnginePreference,
  type HermesPreset,
  type HermesRunMetrics,
  type HermesStatusResponse,
  type HermesStepEvent,
  type HermesSuggestedSkill,
  type HermesToolName,
  type Memory,
  type Model,
  type Skill,
  type Source,
} from "@/lib/api";
import { ModelModal } from "@/components/model-modal";
import { ThoughtAccordion } from "@/components/thought-accordion";
import { useModelFavorites } from "@/lib/model-favorites";
import styles from "./hermes-agent-modal.module.css";

export interface HermesAgentModalProps {
  isOpen: boolean;
  onClose: () => void;
  models: Model[];
  currentModel: string;
  initialPrompt?: string;
  onInsertIntoChat: (text: string) => void;
  onSkillCreated?: (skill: Skill) => void;
  onMemoryCreated?: (memory: Memory) => void;
  onRefreshModels?: () => Promise<void>;
}

function formatContextTokens(tokens?: number): string {
  if (!tokens || tokens <= 0) return "";
  if (tokens >= 1_000_000) {
    const val = tokens / 1_000_000;
    return `${val % 1 === 0 ? val.toFixed(0) : val.toFixed(1)}M ctx`;
  }
  if (tokens >= 1_000) {
    return `${Math.round(tokens / 1_000)}k ctx`;
  }
  return `${tokens} ctx`;
}

function formatModelPriceTag(model?: Model): string | null {
  if (!model) return null;
  if (model.prompt_price_1m === 0 && (model.completion_price_1m === undefined || model.completion_price_1m === 0)) {
    return "Gratuit";
  }
  if (model.completion_price_1m !== undefined && model.completion_price_1m !== null) {
    const p = model.completion_price_1m;
    return p < 0.01 ? "<$0.01/1M" : `$${p.toFixed(2)}/1M`;
  }
  if (model.prompt_price_1m !== undefined && model.prompt_price_1m !== null) {
    const p = model.prompt_price_1m;
    return p < 0.01 ? "<$0.01/1M" : `$${p.toFixed(2)}/1M`;
  }
  return null;
}

const DEFAULT_TOOLS: HermesToolName[] = ["web_search", "memory", "skills", "code_execution"];
const HERMES_HISTORY_STORAGE_KEY = "clair_hermes_prompt_history_v1";
const MAX_HERMES_HISTORY = 10;

type HermesHistoryItem = {
  id: string;
  prompt: string;
  model?: string;
  executionMode?: HermesEnginePreference;
  tools?: HermesToolName[];
  createdAt: number;
};

function loadHermesHistory(): HermesHistoryItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HERMES_HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is HermesHistoryItem =>
          Boolean(item) &&
          typeof item.id === "string" &&
          typeof item.prompt === "string" &&
          item.prompt.trim().length > 0 &&
          typeof item.createdAt === "number",
      )
      .slice(0, MAX_HERMES_HISTORY);
  } catch {
    return [];
  }
}

function saveHermesHistory(items: HermesHistoryItem[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      HERMES_HISTORY_STORAGE_KEY,
      JSON.stringify(items.slice(0, MAX_HERMES_HISTORY)),
    );
  } catch {
    // Ignore storage quota or private mode errors
  }
}

function formatHistoryTime(timestamp: number): string {
  const diffMin = Math.floor((Date.now() - timestamp) / 60_000);
  if (diffMin < 1) return "À l'instant";
  if (diffMin < 60) return `Il y a ${diffMin} min`;
  const date = new Date(timestamp);
  const now = new Date();
  const isToday =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();
  if (isToday) {
    return date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
}

const MODE_LABELS: Record<string, { label: string; className: string }> = {
  gateway: { label: "Gateway Hermes actif (8642)", className: styles.modeGateway },
  local_autonomous: { label: "Boucle Autonome cLAIr", className: styles.modeLocal },
  demo: { label: "Mode Démonstration", className: styles.modeDemo },
  offline: { label: "Hors-ligne (clé requise)", className: styles.modeOffline },
  disabled: { label: "Désactivé", className: styles.modeOffline },
};

function toolIcon(tool: string) {
  if (tool === "web_search") return <Globe2 size={14} color="#0284c7" />;
  if (tool === "memory") return <Brain size={14} color="#7c3aed" />;
  if (tool === "skills") return <Sparkles size={14} color="#d97706" />;
  if (tool === "code_execution") return <Code2 size={14} color="#059669" />;
  if (tool === "create_page") return <FileText size={14} color="#2563eb" />;
  return <Bot size={14} color="#4f46e5" />;
}

export function HermesAgentModal({
  isOpen,
  onClose,
  models,
  currentModel,
  initialPrompt = "",
  onInsertIntoChat,
  onSkillCreated,
  onMemoryCreated,
  onRefreshModels,
}: HermesAgentModalProps) {
  const { isFavorite } = useModelFavorites("llm");
  const [modelModalOpen, setModelModalOpen] = useState(false);
  const [statusData, setStatusData] = useState<HermesStatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [enginePreference, setEnginePreference] = useState<HermesEnginePreference>("auto");
  const [selectedModel, setSelectedModel] = useState(currentModel);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [soulPrompt, setSoulPrompt] = useState("");
  const [enabledTools, setEnabledTools] = useState<HermesToolName[]>(DEFAULT_TOOLS);
  const [autoLearnSkill, setAutoLearnSkill] = useState(true);
  const [sessionId, setSessionId] = useState("");
  const [history, setHistory] = useState<HermesHistoryItem[]>(() => loadHermesHistory());

  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<HermesStepEvent[]>([]);
  const [thought, setThought] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const [createdPages, setCreatedPages] = useState<HermesCreatedPage[]>([]);
  const [suggestedSkill, setSuggestedSkill] = useState<HermesSuggestedSkill | null>(null);
  const [suggestedMemory, setSuggestedMemory] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<HermesRunMetrics | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [savingSkill, setSavingSkill] = useState(false);
  const [skillSaved, setSkillSaved] = useState(false);
  const [savingMemory, setSavingMemory] = useState(false);
  const [memorySaved, setMemorySaved] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true);
    try {
      const res = await fetchHermesStatus();
      setStatusData(res);
      setSoulPrompt((prev) => prev || res.default_soul);
      setSelectedModel((prev) => prev || res.default_model || "");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    let active = true;
    fetchHermesStatus()
      .then((res) => {
        if (!active) return;
        setStatusData(res);
        setSoulPrompt((prev) => prev || res.default_soul);
        setSelectedModel((prev) => prev || res.default_model || "");
      })
      .catch((err) => {
        if (active) setError(errorMessage(err));
      });
    return () => {
      active = false;
      abortRef.current?.abort();
    };
  }, [isOpen]);

  const orderedModels = useMemo<Model[]>(() => {
    const modelMap = new Map(models.map((m) => [m.id, m]));
    const gatewayModels: Model[] = (statusData?.gateway_models ?? []).map((id) => {
      const existing = modelMap.get(id);
      if (existing) return existing;
      return {
        id,
        name: `Hermes Gateway · ${id}`,
        provider: "Hermes Gateway",
        description: "Modèle exposé directement par le conteneur Hermes Gateway.",
        vision: false,
      };
    });
    const defaultId = statusData?.default_model?.trim();
    const defaultHermesModel: Model[] = defaultId
      ? [
          modelMap.get(defaultId) ?? {
            id: defaultId,
            name: `OpenRouter · ${defaultId}`,
            provider: "OpenRouter",
            vision: false,
          },
        ]
      : [];
    const hermesPreferred = models.filter((m) => m.id.toLowerCase().includes("hermes"));
    const rest = models.filter((m) => !m.id.toLowerCase().includes("hermes"));
    const merged = [...gatewayModels, ...defaultHermesModel, ...hermesPreferred, ...rest];
    const seen = new Set<string>();
    return merged.filter((m) => {
      if (seen.has(m.id)) return false;
      seen.add(m.id);
      return true;
    });
  }, [models, statusData]);

  const selectedModelInfo = useMemo(
    () => orderedModels.find((m) => m.id === selectedModel),
    [orderedModels, selectedModel],
  );

  if (!isOpen) return null;

  const detectedMode = statusData?.mode || "local_autonomous";
  const effectiveMode =
    enginePreference !== "auto" && !["demo", "offline", "disabled"].includes(detectedMode)
      ? enginePreference
      : detectedMode;
  const modeInfo = MODE_LABELS[effectiveMode] || MODE_LABELS.local_autonomous;
  const providerLabel = statusData?.provider === "openai_compatible" ? "LLM Compatible" : "OpenRouter";
  const selectedPriceTag = formatModelPriceTag(selectedModelInfo);
  const selectedContextTag = formatContextTokens(selectedModelInfo?.context_length);

  function toggleTool(toolId: HermesToolName) {
    setEnabledTools((prev) =>
      prev.includes(toolId) ? prev.filter((item) => item !== toolId) : [...prev, toolId],
    );
  }

  function applyPreset(preset: HermesPreset) {
    setPrompt(preset.prompt);
    if (preset.tools?.length) {
      setEnabledTools(preset.tools);
    }
  }

  function recordHistory(trimmedPrompt: string) {
    const entry: HermesHistoryItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      prompt: trimmedPrompt,
      model: selectedModel || undefined,
      executionMode: enginePreference,
      tools: [...enabledTools],
      createdAt: Date.now(),
    };
    setHistory((prev) => {
      const deduplicated = prev.filter((item) => item.prompt.trim() !== trimmedPrompt);
      const next = [entry, ...deduplicated].slice(0, MAX_HERMES_HISTORY);
      saveHermesHistory(next);
      return next;
    });
  }

  function applyHistoryItem(item: HermesHistoryItem) {
    setPrompt(item.prompt);
    if (item.tools?.length) {
      setEnabledTools(item.tools);
    }
    if (item.executionMode) {
      setEnginePreference(item.executionMode);
    }
    if (item.model && orderedModels.some((m) => m.id === item.model)) {
      setSelectedModel(item.model);
    }
  }

  function removeHistoryItem(id: string) {
    setHistory((prev) => {
      const next = prev.filter((item) => item.id !== id);
      saveHermesHistory(next);
      return next;
    });
  }

  function clearHistory() {
    setHistory([]);
    saveHermesHistory([]);
  }

  async function handleRun(event?: FormEvent) {
    event?.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || running) return;

    recordHistory(trimmed);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setRunning(true);
    setError("");
    setSteps([]);
    setThought("");
    setAnswer("");
    setSources([]);
    setCreatedPages([]);
    setSuggestedSkill(null);
    setSuggestedMemory(null);
    setMetrics(null);
    setSkillSaved(false);
    setMemorySaved(false);

    try {
      await streamHermesRun(
        {
          prompt: trimmed,
          model: selectedModel || undefined,
          execution_mode: enginePreference,
          session_id: sessionId || undefined,
          soul_prompt: soulPrompt.trim() || undefined,
          enabled_tools: enabledTools,
          auto_learn_skill: autoLearnSkill,
        },
        controller.signal,
        (ev) => {
          if (ev.type === "meta") {
            setSessionId(ev.data.session_id);
          } else if (ev.type === "step") {
            setSteps((prev) => {
              const idx = prev.findIndex((s) => s.id === ev.data.id);
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = ev.data;
                return next;
              }
              return [...prev, ev.data];
            });
          } else if (ev.type === "thought") {
            setThought((prev) => prev + ev.data.text);
          } else if (ev.type === "delta") {
            setAnswer((prev) => prev + ev.data.text);
          } else if (ev.type === "artifacts") {
            setSources(ev.data.sources || []);
            setCreatedPages(ev.data.created_pages || []);
            setSuggestedSkill(ev.data.suggested_skill || null);
            setSuggestedMemory(ev.data.suggested_memory || null);
            if (ev.data.metrics) setMetrics(ev.data.metrics);
          } else if (ev.type === "done") {
            if (ev.data.content) setAnswer((prev) => prev || ev.data.content);
            if (ev.data.metrics) setMetrics(ev.data.metrics);
          }
        },
      );
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        setError(errorMessage(err));
      }
    } finally {
      setRunning(false);
    }
  }

  async function handleSaveSkill() {
    if (!suggestedSkill || savingSkill || skillSaved) return;
    setSavingSkill(true);
    setError("");
    try {
      const created = await api<Skill>("/skills", {
        method: "POST",
        body: JSON.stringify({
          name: suggestedSkill.name,
          prompt: suggestedSkill.prompt,
        }),
      });
      setSkillSaved(true);
      onSkillCreated?.(created);
      void loadStatus();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingSkill(false);
    }
  }

  async function handleSaveMemory() {
    if (!suggestedMemory || savingMemory || memorySaved) return;
    setSavingMemory(true);
    setError("");
    try {
      const created = await api<Memory>("/memories", {
        method: "POST",
        body: JSON.stringify({ content: suggestedMemory }),
      });
      setMemorySaved(true);
      onMemoryCreated?.(created);
      void loadStatus();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingMemory(false);
    }
  }

  async function handleCopy() {
    if (!answer.trim()) return;
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Copie dans le presse-papiers impossible.");
    }
  }

  return (
    <>
      <div
        className={styles.backdrop}
        role="dialog"
        aria-modal="true"
        aria-labelledby="hermes-modal-title"
        onClick={(e) => {
          if (e.target === e.currentTarget && !running) onClose();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !running && !modelModalOpen) onClose();
        }}
      >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <Bot size={22} />
            </div>
            <div>
              <div className={styles.headerTitleRow}>
                <h2 id="hermes-modal-title" className={styles.headerTitle}>
                  Hermes Agent · Nous Research
                </h2>
                <span className={`${styles.statusBadge} ${modeInfo.className}`}>
                  <span className={styles.statusDot} />
                  {modeInfo.label}
                </span>
                <span className={`${styles.statusBadge} ${styles.statusLocal}`}>
                  {providerLabel}
                </span>
              </div>
              <p className={styles.headerSubtitle}>
                Agent autonome à boucle d&apos;outils, mémoire persistante (USER.md) et création de compétences (@skills).
                {statusData && (
                  <>
                    {" "}
                    · {statusData.user_memories_count} souvenir(s) · {statusData.user_skills_count} compétence(s)
                  </>
                )}
              </p>
            </div>
          </div>

          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={() => void loadStatus()}
              disabled={loadingStatus || running}
              title="Actualiser le statut du Gateway Hermes"
              aria-label="Actualiser le statut"
            >
              <RefreshCw size={15} className={loadingStatus ? "spin" : ""} />
            </button>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={onClose}
              disabled={running}
              title="Fermer"
              aria-label="Fermer la fenêtre Hermes Agent"
            >
              <X size={17} />
            </button>
          </div>
        </header>

        <div className={styles.workspace}>
          <aside className={styles.sidebar}>
            <div>
              <div className={styles.sectionLabel}>
                <span>Moteur d&apos;exécution</span>
              </div>
              <select
                className={styles.select}
                value={enginePreference}
                onChange={(e) => setEnginePreference(e.target.value as HermesEnginePreference)}
                disabled={running}
                aria-label="Moteur Hermes"
              >
                <option value="auto">
                  Auto ({statusData?.gateway_reachable ? "Gateway Hermes" : "Local Autonomous"})
                </option>
                <option value="local_autonomous">
                  Local Autonomous (rapide &amp; économique · OpenRouter)
                </option>
                <option value="gateway" disabled={!statusData?.gateway_reachable && statusData?.mode !== "demo"}>
                  Gateway Hermes (mémoire native, skills &amp; terminal{statusData?.gateway_reachable ? "" : " — hors-ligne"})
                </option>
              </select>
            </div>

            <div>
              <div className={styles.sectionLabel}>
                <span>Modèle ({providerLabel})</span>
              </div>
              <button
                type="button"
                className={styles.modelTrigger}
                onClick={() => setModelModalOpen(true)}
                disabled={running}
                aria-label="Choisir le modèle Hermes (voir tous les modèles, prix, contexte, vision)"
                title="Changer de modèle IA (voir tous les modèles, prix, contexte, vision)"
              >
                <span className={styles.modelTriggerTop}>
                  <span className={styles.modelTriggerTitle}>
                    {selectedModel && isFavorite(selectedModel) && (
                      <Star size={12} fill="#f59e0b" color="#f59e0b" className={styles.modelStar} />
                    )}
                    <span className={styles.modelTriggerName}>
                      {selectedModelInfo?.name || selectedModel || "Choisir un modèle"}
                    </span>
                  </span>
                  <ChevronDown size={15} className={styles.modelTriggerChevron} />
                </span>
                {selectedModel && (
                  <code className={styles.modelTriggerId}>{selectedModel}</code>
                )}
                <span className={styles.modelTriggerMeta}>
                  {selectedModelInfo?.provider && (
                    <span className={`${styles.modelPill} ${styles.modelPillProvider}`}>
                      {selectedModelInfo.provider}
                    </span>
                  )}
                  {selectedModelInfo?.vision && (
                    <span className={`${styles.modelPill} ${styles.modelPillVision}`} title="Modèle multimodal avec vision">
                      <Eye size={11} />
                      <span>Vision</span>
                    </span>
                  )}
                  {selectedModelInfo?.reasoning && (
                    <span className={`${styles.modelPill} ${styles.modelPillReasoning}`} title="Modèle de raisonnement">
                      <Brain size={11} />
                      <span>Raisonnement</span>
                    </span>
                  )}
                  {selectedContextTag && (
                    <span className={`${styles.modelPill} ${styles.modelPillContext}`} title="Fenêtre de contexte">
                      <Cpu size={11} />
                      <span>{selectedContextTag}</span>
                    </span>
                  )}
                  {selectedPriceTag && (
                    <span
                      className={`${styles.modelPill} ${
                        selectedPriceTag === "Gratuit" ? styles.modelPillFree : styles.modelPillPrice
                      }`}
                      title="Tarif indicatif"
                    >
                      {selectedPriceTag}
                    </span>
                  )}
                </span>
              </button>
            </div>

            {statusData?.presets?.length ? (
              <div>
                <div className={styles.sectionLabel}>
                  <span>Missions types</span>
                </div>
                <div className={styles.presetList}>
                  {statusData.presets.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      className={styles.presetBtn}
                      disabled={running}
                      onClick={() => applyPreset(preset)}
                    >
                      <strong>{preset.title}</strong>
                      <span>{preset.description}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {history.length > 0 && (
              <div>
                <div className={styles.sectionLabel}>
                  <span className={styles.historyHeaderTitle}>
                    <History size={12} />
                    <span>Historique ({history.length}/{MAX_HERMES_HISTORY})</span>
                  </span>
                  <button
                    type="button"
                    className={styles.historyClearBtn}
                    onClick={clearHistory}
                    disabled={running}
                    title="Vider l'historique"
                  >
                    <Trash2 size={11} />
                    <span>Effacer</span>
                  </button>
                </div>
                <div className={styles.historyList}>
                  {history.map((item) => (
                    <div key={item.id} className={styles.historyItemWrap}>
                      <button
                        type="button"
                        className={styles.historyBtn}
                        disabled={running}
                        onClick={() => applyHistoryItem(item)}
                        title={item.prompt}
                      >
                        <span className={styles.historyPrompt}>{item.prompt}</span>
                        <span className={styles.historyMeta}>
                          <span>{formatHistoryTime(item.createdAt)}</span>
                          {item.model && (
                            <span className={styles.historyModel}>
                              {item.model.split("/").pop()}
                            </span>
                          )}
                        </span>
                      </button>
                      <button
                        type="button"
                        className={styles.historyDeleteBtn}
                        disabled={running}
                        onClick={() => removeHistoryItem(item.id)}
                        title="Supprimer de l'historique"
                        aria-label="Supprimer cette demande de l'historique"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className={styles.sectionLabel}>
                <span>Outils Hermes actifs</span>
              </div>
              <div className={styles.toolGrid}>
                {(statusData?.tools ?? []).map((tool) => {
                  const active = enabledTools.includes(tool.id);
                  return (
                    <button
                      key={tool.id}
                      type="button"
                      className={`${styles.toolToggle} ${active ? styles.isActive : ""}`}
                      onClick={() => toggleTool(tool.id)}
                      disabled={running}
                      aria-pressed={active}
                    >
                      <span className={styles.toolToggleCheck}>
                        {active && <Check size={11} strokeWidth={3} />}
                      </span>
                      <span className={styles.toolToggleText}>
                        <strong>{tool.name}</strong>
                        <small>{tool.description}</small>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            <details className={styles.soulBox}>
              <summary className={styles.soulSummary}>
                <span>Identité SOUL.md</span>
                <small>Personnaliser</small>
              </summary>
              <textarea
                className={styles.soulTextarea}
                rows={4}
                value={soulPrompt}
                onChange={(e) => setSoulPrompt(e.target.value)}
                disabled={running}
                maxLength={4000}
              />
              {statusData?.default_soul && (
                <button
                  type="button"
                  className={styles.resetLink}
                  disabled={running}
                  onClick={() => setSoulPrompt(statusData.default_soul)}
                >
                  Réinitialiser SOUL.md par défaut
                </button>
              )}
            </details>

            {!statusData?.gateway_reachable && (
              <div className={styles.gatewayTip}>
                <strong>Mode Gateway Docker (OpenRouter)</strong>
                <br />
                Pour exécuter le démon complet <code>nousresearch/hermes-agent</code> avec votre clé{" "}
                <code>OPENROUTER_API_KEY</code> (<code>LLM_API_KEY</code>) :{" "}
                <code>docker compose up -d clair-hermes</code> puis{" "}
                <code>docker compose exec clair-hermes hermes model</code>.
              </div>
            )}
          </aside>

          <section className={styles.main}>
            <form className={styles.promptForm} onSubmit={(e) => void handleRun(e)}>
              <textarea
                className={styles.promptTextarea}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Confiez une mission à Hermes Agent (ex. Audite cette architecture, synthétise l'actualité MCP, forge une @compétence)…"
                disabled={running}
                maxLength={16000}
              />
              <div className={styles.promptActions}>
                <label className={styles.autoLearnCheck}>
                  <input
                    type="checkbox"
                    checked={autoLearnSkill}
                    onChange={(e) => setAutoLearnSkill(e.target.checked)}
                    disabled={running}
                  />
                  <span>Extraire automatiquement une compétence @skill &amp; une note mémoire</span>
                </label>

                {running ? (
                  <button
                    type="button"
                    className={styles.stopBtn}
                    onClick={() => abortRef.current?.abort()}
                  >
                    <Square size={13} fill="currentColor" />
                    <span>Arrêter</span>
                  </button>
                ) : (
                  <button type="submit" className={styles.runBtn} disabled={!prompt.trim()}>
                    <Play size={14} />
                    <span>Lancer Hermes</span>
                  </button>
                )}
              </div>
            </form>

            <div className={styles.outputArea}>
              {error && (
                <div className={styles.errorBox} role="alert">
                  <AlertCircle size={15} />
                  <span>{error}</span>
                </div>
              )}

              {!steps.length && !answer && !thought && !running && (
                <div className={styles.emptyState}>
                  <Bot size={36} strokeWidth={1.3} color="#4f46e5" />
                  <h3>Prêt pour une mission autonome</h3>
                  <p>
                    Choisissez une mission type à gauche ou décrivez votre objectif ci-dessus. Hermes
                    chaîne ses outils en direct, consulte vos souvenirs et vous propose de capitaliser
                    le résultat en compétence réutilisable.
                  </p>
                </div>
              )}

              {steps.length > 0 && (
                <div className={styles.timeline}>
                  <div className={styles.timelineHeader}>
                    <span>Journal d&apos;exécution des outils</span>
                    <span>
                      {sessionId ? `Session ${sessionId}` : ""}
                      {metrics
                        ? `${sessionId ? " · " : ""}${metrics.llm_calls} appel(s) LLM · ${metrics.tool_calls} outil(s)${
                            metrics.total_tokens
                              ? ` · ${metrics.total_tokens} tok. (${metrics.prompt_tokens ?? 0} in / ${metrics.completion_tokens ?? 0} out)`
                              : ""
                          } · ${
                            typeof metrics.cost_usd === "number"
                              ? `$${metrics.cost_usd.toFixed(4)}`
                              : "Coût indisponible"
                          }${
                            metrics.duration_ms ? ` · ${(metrics.duration_ms / 1000).toFixed(1)} s` : ""
                          }${metrics.stop_reason && metrics.stop_reason !== "completed" ? ` · ${metrics.stop_reason}` : ""}`
                        : ""}
                    </span>
                  </div>
                  {steps.map((step) => (
                    <div key={step.id} className={styles.stepRow}>
                      {step.status === "running" ? (
                        <LoaderCircle size={14} className="spin" color="#4f46e5" />
                      ) : step.status === "error" ? (
                        <AlertCircle size={14} color="#dc2626" />
                      ) : (
                        toolIcon(step.tool)
                      )}
                      <strong>{step.title}</strong>
                      {step.detail && <span className={styles.stepDetail}>· {step.detail}</span>}
                    </div>
                  ))}
                </div>
              )}

              {thought && <ThoughtAccordion thought={thought} isStreaming={running && !answer} />}

              {answer && (
                <div className={`${styles.markdownBox} markdown`}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer}</ReactMarkdown>
                </div>
              )}

              {sources.length > 0 && (
                <div className={styles.sourcesBox}>
                  {sources.map((src, idx) => (
                    <a
                      key={`${src.url}-${idx}`}
                      href={src.url}
                      target="_blank"
                      rel="noreferrer"
                      className={styles.sourceChip}
                    >
                      <ExternalLink size={11} />
                      <span>
                        [{idx + 1}] {src.title || src.url}
                      </span>
                    </a>
                  ))}
                </div>
              )}

              {(createdPages.length > 0 || suggestedSkill || suggestedMemory) && (
                <div className={styles.artifactsGrid}>
                  {createdPages.map((page) => (
                    <div key={page.id} className={styles.artifactCard}>
                      <div className={styles.artifactTitle}>
                        <FileText size={14} color="#2563eb" />
                        <span>Brouillon cLAIr Page créé · {page.title}</span>
                      </div>
                      <p className={styles.artifactBody}>
                        Slug : <code>{page.slug}</code> · Statut :{" "}
                        {page.is_published ? "Publié" : "Brouillon (non publié)"}
                      </p>
                    </div>
                  ))}
                  {suggestedSkill && (
                    <div className={styles.artifactCard}>
                      <div className={styles.artifactTitle}>
                        <Sparkles size={14} color="#d97706" />
                        <span>Compétence apprise · @{suggestedSkill.name}</span>
                      </div>
                      <p className={styles.artifactBody}>{suggestedSkill.prompt}</p>
                      <button
                        type="button"
                        className={styles.artifactBtn}
                        onClick={() => void handleSaveSkill()}
                        disabled={savingSkill || skillSaved}
                      >
                        {skillSaved ? (
                          <>
                            <Check size={13} />
                            <span>Enregistrée dans @Compétences</span>
                          </>
                        ) : (
                          <>
                            <Plus size={13} />
                            <span>{savingSkill ? "Enregistrement…" : "Ajouter à mes @Compétences"}</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}

                  {suggestedMemory && (
                    <div className={styles.artifactCard}>
                      <div className={styles.artifactTitle}>
                        <Brain size={14} color="#7c3aed" />
                        <span>Mémoire extraite (USER.md)</span>
                      </div>
                      <p className={styles.artifactBody}>{suggestedMemory}</p>
                      <button
                        type="button"
                        className={styles.artifactBtn}
                        onClick={() => void handleSaveMemory()}
                        disabled={savingMemory || memorySaved}
                      >
                        {memorySaved ? (
                          <>
                            <Check size={13} />
                            <span>Mémorisé dans Souvenirs</span>
                          </>
                        ) : (
                          <>
                            <Plus size={13} />
                            <span>{savingMemory ? "Ajout…" : "Ajouter à mes Souvenirs"}</span>
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>

            <footer className={styles.footerBar}>
              <span className={styles.headerSubtitle}>
                {statusData?.gateway_reachable
                  ? `Connecté à ${statusData.gateway_url}`
                  : "Exécution sécurisée via cLAIr"}
              </span>
              <div className={styles.footerActions}>
                <button
                  type="button"
                  className={styles.secondaryBtn}
                  onClick={() => void handleCopy()}
                  disabled={!answer.trim()}
                >
                  {copied ? <Check size={13} /> : <Copy size={13} />}
                  <span>{copied ? "Copié" : "Copier"}</span>
                </button>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  disabled={!answer.trim()}
                  onClick={() => {
                    onInsertIntoChat(answer.trim());
                    onClose();
                  }}
                >
                  <MessageSquarePlus size={14} />
                  <span>Insérer dans le tchat</span>
                </button>
              </div>
            </footer>
          </section>
        </div>
      </div>
      </div>
      {modelModalOpen && (
        <ModelModal
          currentModel={selectedModel}
          models={orderedModels}
          onSelectModel={(modelId) => {
            setSelectedModel(modelId);
            setModelModalOpen(false);
          }}
          onClose={() => setModelModalOpen(false)}
          onRefreshModels={onRefreshModels}
        />
      )}
    </>
  );
}
