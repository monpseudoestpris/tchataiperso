"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  AlertCircle,
  Bot,
  Brain,
  Check,
  Code2,
  Copy,
  ExternalLink,
  FileText,
  Globe2,
  LoaderCircle,
  MessageSquarePlus,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
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
import { ThoughtAccordion } from "@/components/thought-accordion";
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
}

const DEFAULT_TOOLS: HermesToolName[] = ["web_search", "memory", "skills", "code_execution"];

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
}: HermesAgentModalProps) {
  const [statusData, setStatusData] = useState<HermesStatusResponse | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [enginePreference, setEnginePreference] = useState<HermesEnginePreference>("auto");
  const [selectedModel, setSelectedModel] = useState(currentModel);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [soulPrompt, setSoulPrompt] = useState("");
  const [enabledTools, setEnabledTools] = useState<HermesToolName[]>(DEFAULT_TOOLS);
  const [autoLearnSkill, setAutoLearnSkill] = useState(true);
  const [sessionId, setSessionId] = useState("");

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

  const orderedModels = useMemo(() => {
    const gatewayModels = (statusData?.gateway_models ?? []).map((id) => ({
      id,
      name: `Hermes Gateway · ${id}`,
      vision: false,
    }));
    const defaultHermesModel = statusData?.default_model?.trim()
      ? [{ id: statusData.default_model.trim(), name: `OpenRouter · ${statusData.default_model.trim()}`, vision: false }]
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

  if (!isOpen) return null;

  const detectedMode = statusData?.mode || "local_autonomous";
  const effectiveMode =
    enginePreference !== "auto" && !["demo", "offline", "disabled"].includes(detectedMode)
      ? enginePreference
      : detectedMode;
  const modeInfo = MODE_LABELS[effectiveMode] || MODE_LABELS.local_autonomous;
  const providerLabel = statusData?.provider === "openai_compatible" ? "LLM Compatible" : "OpenRouter";

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

  async function handleRun(event?: FormEvent) {
    event?.preventDefault();
    const trimmed = prompt.trim();
    if (!trimmed || running) return;

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
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="hermes-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !running) onClose();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape" && !running) onClose();
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
              <select
                className={styles.select}
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                disabled={running}
                aria-label="Modèle Hermes"
              >
                {orderedModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
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
  );
}
