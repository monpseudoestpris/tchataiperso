"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Bookmark,
  Bot,
  Brain,
  Check,
  ChevronDown,
  Coins,
  Cpu,
  Eye,
  Layers,
  LoaderCircle,
  MessageSquare,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Users,
  X,
  Zap,
} from "lucide-react";
import type { AgentPersonaConfig, AgentTeam, AgentTeamsResponse, Model, MultiAgentConfig } from "@/lib/api";
import { api, generateAiPersona } from "@/lib/api";

type MultiAgentModalProps = {
  isOpen: boolean;
  onClose: () => void;
  models: Model[];
  defaultModel: string;
  activeConfig: MultiAgentConfig | null;
  onApplyConfig: (config: MultiAgentConfig | null) => void;
};

const DEFAULT_AGENTS_INITIAL: AgentPersonaConfig[] = [
  {
    id: "agent_lawyer",
    name: "Maître Legrand",
    role: "Avocat & Juriste",
    model: "anthropic/claude-3.5-sonnet",
    prompt:
      "Tu es un avocat d'affaires chevronné et juriste exigeant. Ton rôle est d'analyser chaque situation sous l'angle du droit, des obligations contractuelles, des responsabilités civiles et pénales, des clauses ambiguës et de la conformité réglementaire. Tu traques sans complaisance les failles juridiques et signales les risques contentieux.",
    avatar: "⚖️",
    color: "#d97706",
  },
  {
    id: "agent_math",
    name: "Professeur Gauss",
    role: "Mathématiques & Logique",
    model: "deepseek/deepseek-r1",
    prompt:
      "Tu es un professeur de mathématiques et chercheur en logique formelle. Ton approche repose sur la rigueur absolue, l'exactitude des calculs, la traque des failles logiques, la décomposition pas à pas et le raisonnement déductif. Tu démontres méthodiquement chaque assertion.",
    avatar: "📐",
    color: "#2563eb",
  },
  {
    id: "agent_critic",
    name: "Socrate",
    role: "Avocat du Diable & Critique",
    model: "openai/gpt-4o",
    prompt:
      "Tu es un philosophe dialecticien et l'avocat du diable en chef. Ton rôle est de détruire les faux consensus, de questionner les postulats évidents acceptés sans preuve, de souligner les angles morts et de tester la robustesse des idées contre le pire cas.",
    avatar: "🧠",
    color: "#7c3aed",
  },
];

function formatPrice(val?: number): string {
  if (val === undefined || val === null) return "—";
  if (val === 0) return "Gratuit";
  if (val < 0.01) return "<$0.01";
  return `$${val.toFixed(2)}`;
}

function formatTokens(tokens?: number): string {
  if (!tokens || tokens <= 0) return "—";
  if (tokens >= 1_000_000) {
    const val = tokens / 1_000_000;
    return `${val % 1 === 0 ? val.toFixed(0) : val.toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${Math.round(tokens / 1_000)}k`;
  }
  return `${tokens}`;
}

const AVATAR_OPTIONS = [
  "⚖️",
  "📐",
  "💻",
  "🛡️",
  "📊",
  "🩺",
  "🧠",
  "🎨",
  "⚡",
  "🦾",
  "🎖️",
  "🚀",
  "🌌",
  "🎬",
  "🐉",
  "🌊",
  "🔬",
  "🤖",
  "👔",
  "🎓",
  "💡",
  "📜",
  "🥊",
  "⚔️",
];
const COLOR_OPTIONS = [
  "#d97706",
  "#2563eb",
  "#7c3aed",
  "#0284c7",
  "#dc2626",
  "#059669",
  "#ec4899",
  "#f59e0b",
  "#4f46e5",
  "#0ea5e9",
  "#e11d48",
  "#1e3a8a",
  "#8b5cf6",
  "#f97316",
  "#0d9488",
  "#475569",
];

export function MultiAgentModal({
  isOpen,
  onClose,
  models,
  defaultModel,
  activeConfig,
  onApplyConfig,
}: MultiAgentModalProps) {
  const [mode, setMode] = useState<"synthesis" | "debate" | "dialectic" | "contradictory">(
    activeConfig?.mode || "synthesis"
  );
  const [agents, setAgents] = useState<AgentPersonaConfig[]>(
    activeConfig?.agents && activeConfig.agents.length >= 2
      ? activeConfig.agents
      : DEFAULT_AGENTS_INITIAL
  );
  const [rounds, setRounds] = useState<number>(activeConfig?.rounds || 1);
  const [activeTab, setActiveTab] = useState<"compose" | "presets" | "saved">("compose");

  // Server teams and templates data
  const [teamsData, setTeamsData] = useState<AgentTeamsResponse | null>(null);
  const [loadingTeams, setLoadingTeams] = useState(false);
  const [saveTeamName, setSaveTeamName] = useState("");
  const [isSavingTeam, setIsSavingTeam] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // AI Persona Generation state
  const [aiGeneratingIndex, setAiGeneratingIndex] = useState<number | null>(null);
  const [aiPromptInput, setAiPromptInput] = useState("");
  const [showAiCreator, setShowAiCreator] = useState(false);
  const [aiCreatingNew, setAiCreatingNew] = useState(false);

  // Map model id to model object
  const modelMap = useMemo(() => {
    const map = new Map<string, Model>();
    for (const m of models) {
      map.set(m.id, m);
    }
    return map;
  }, [models]);

  // Load server teams on mount or open
  useEffect(() => {
    if (!isOpen) return;
    let mounted = true;
    async function loadData() {
      setLoadingTeams(true);
      try {
        const res = await api<AgentTeamsResponse>("/agent-teams");
        if (mounted && res) {
          setTeamsData(res);
        }
      } catch (err) {
        console.warn("Échec du chargement des équipes:", err);
      } finally {
        if (mounted) setLoadingTeams(false);
      }
    }
    loadData();
    return () => {
      mounted = false;
    };
  }, [isOpen]);

  // Sync state if activeConfig changes
  useEffect(() => {
    if (activeConfig) {
      setMode(activeConfig.mode);
      setAgents(activeConfig.agents);
      setRounds(activeConfig.rounds || 1);
    }
  }, [activeConfig]);

  if (!isOpen) return null;

  function handleAddAgent() {
    if (agents.length >= 4) return;
    const availableTemplate = teamsData?.templates?.find(
      (t) => !agents.some((a) => a.name.includes(t.name.split(" ")[0]))
    );
    const newAgent: AgentPersonaConfig = {
      id: `agent_${Date.now()}`,
      name: availableTemplate?.name || `Expert #${agents.length + 1}`,
      role: availableTemplate?.role || "Consultant Spécialiste",
      model: defaultModel || models[0]?.id || "openai/gpt-4o",
      prompt: availableTemplate?.prompt || "Donne une analyse experte et rigoureuse de la question posée.",
      avatar: availableTemplate?.avatar || "🤖",
      color: availableTemplate?.color || COLOR_OPTIONS[agents.length % COLOR_OPTIONS.length],
    };
    setAgents([...agents, newAgent]);
  }

  function handleRemoveAgent(index: number) {
    if (agents.length <= 2) return;
    setAgents(agents.filter((_, i) => i !== index));
  }

  function handleUpdateAgent(index: number, updates: Partial<AgentPersonaConfig>) {
    setAgents(agents.map((a, i) => (i === index ? { ...a, ...updates } : a)));
  }

  function handleApplyTemplateToAgent(agentIndex: number, templateId: string) {
    const template = teamsData?.templates?.find((t) => t.id === templateId);
    if (!template) return;
    handleUpdateAgent(agentIndex, {
      name: template.name,
      role: template.role,
      avatar: template.avatar,
      color: template.color,
      prompt: template.prompt,
    });
  }

  async function handleGeneratePersonaWithAi(targetIndex?: number, customInput?: string) {
    const rawInput = (customInput || aiPromptInput).trim();
    if (!rawInput) return;
    setErrorMsg("");
    if (targetIndex !== undefined) {
      setAiGeneratingIndex(targetIndex);
    } else {
      setAiCreatingNew(true);
    }
    try {
      const generated = await generateAiPersona({
        name_or_concept: rawInput,
        model: defaultModel || models[0]?.id,
      });

      if (generated) {
        if (targetIndex !== undefined) {
          // Replace agent at targetIndex
          handleUpdateAgent(targetIndex, {
            name: generated.name,
            role: generated.role,
            avatar: generated.avatar,
            color: generated.color,
            prompt: generated.prompt,
            model:
              generated.suggested_model && modelMap.has(generated.suggested_model)
                ? generated.suggested_model
                : agents[targetIndex]?.model || defaultModel || models[0]?.id || "openai/gpt-4o",
          });
        } else {
          // Add as new agent (if < 4 agents)
          const newAgent: AgentPersonaConfig = {
            id: `agent_${Date.now()}`,
            name: generated.name,
            role: generated.role,
            avatar: generated.avatar,
            color: generated.color,
            prompt: generated.prompt,
            model:
              generated.suggested_model && modelMap.has(generated.suggested_model)
                ? generated.suggested_model
                : defaultModel || models[0]?.id || "openai/gpt-4o",
          };
          if (agents.length < 4) {
            setAgents([...agents, newAgent]);
          } else {
            // Replace the last agent if full
            setAgents([...agents.slice(0, 3), newAgent]);
          }
          setAiPromptInput("");
          setShowAiCreator(false);
        }
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Erreur lors de la génération IA de la personnalité.");
    } finally {
      setAiGeneratingIndex(null);
      setAiCreatingNew(false);
    }
  }

  function handleLoadPresetTeam(preset: { mode: "synthesis" | "debate" | "dialectic" | "contradictory"; agents: AgentPersonaConfig[] }) {
    setMode(preset.mode === "contradictory" ? "dialectic" : preset.mode);
    // Replace with matched models or default
    const resolvedAgents = preset.agents.map((ag) => {
      const exists = modelMap.has(ag.model);
      return {
        ...ag,
        model: exists ? ag.model : defaultModel || models[0]?.id || ag.model,
      };
    });
    setAgents(resolvedAgents);
    setActiveTab("compose");
  }

  async function handleSaveCurrentTeam() {
    if (!saveTeamName.trim()) {
      setErrorMsg("Veuillez donner un nom à votre équipe.");
      return;
    }
    setErrorMsg("");
    setIsSavingTeam(true);
    try {
      const created = await api<AgentTeam>("/agent-teams", {
        method: "POST",
        body: JSON.stringify({
          name: saveTeamName.trim(),
          mode,
          agents,
        }),
      });
      if (created) {
        setTeamsData((prev) =>
          prev ? { ...prev, teams: [created, ...(prev.teams || [])] } : null
        );
        setSaveTeamName("");
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Erreur lors de la sauvegarde de l'équipe.");
    } finally {
      setIsSavingTeam(false);
    }
  }

  async function handleDeleteSavedTeam(teamId: string) {
    try {
      await api(`/agent-teams/${teamId}`, { method: "DELETE" });
      setTeamsData((prev) =>
        prev ? { ...prev, teams: prev.teams.filter((t) => t.id !== teamId) } : null
      );
    } catch (err) {
      console.warn("Échec suppression équipe:", err);
    }
  }

  function handleConfirmApply() {
    if (agents.length < 2) {
      setErrorMsg("Le conseil doit comporter au moins 2 personnalités.");
      return;
    }
    onApplyConfig({
      mode,
      agents,
      rounds,
    });
    onClose();
  }

  function handleDeactivate() {
    onApplyConfig(null);
    onClose();
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal multi-agent-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="multi-agent-modal-title"
      >
        {/* Header */}
        <header className="multi-agent-modal-header">
          <div className="multi-agent-modal-title-wrap">
            <span className="multi-agent-brand-badge" aria-hidden="true">
              <Users size={20} />
            </span>
            <div>
              <div className="multi-agent-eyebrow">
                <span>CONSEIL MULTI-AGENTS</span>
                <span className="multi-agent-badge-pill">
                  {agents.length} experts · {mode === "synthesis" ? "🎯 Synthèse" : mode === "debate" ? "🎙️ Débat" : "⚔️ Contradictoire"}
                </span>
              </div>
              <h2 id="multi-agent-modal-title">Délibération collaborative & Mixture of Personas</h2>
            </div>
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Fermer la modale"
          >
            <X size={18} />
          </button>
        </header>

        {/* Mode Selector Card */}
        <div className="multi-agent-mode-selector">
          <button
            type="button"
            className={`multi-agent-mode-card ${mode === "synthesis" ? "is-active" : ""}`}
            onClick={() => setMode("synthesis")}
          >
            <div className="multi-agent-mode-card-header">
              <span className="multi-agent-mode-icon">🎯</span>
              <strong>Synthèse d'Experts (Consensus)</strong>
              {mode === "synthesis" && <Check size={16} className="mode-check-icon" />}
            </div>
            <p>
              Chaque modèle étudie la question en parallèle selon sa posture. Un arbitre impartial
              synthétise les <strong>points de consensus</strong>, les <strong>divergences</strong> et délivre une{" "}
              <strong>recommandation finale</strong>, avec accès aux avis complets dépliables.
            </p>
          </button>

          <button
            type="button"
            className={`multi-agent-mode-card ${mode === "debate" ? "is-active" : ""}`}
            onClick={() => setMode("debate")}
          >
            <div className="multi-agent-mode-card-header">
              <span className="multi-agent-mode-icon">🎙️</span>
              <strong>Table Ronde (Débat interactif)</strong>
              {mode === "debate" && <Check size={16} className="mode-check-icon" />}
            </div>
            <p>
              Les personnalités prennent la parole <strong>tour à tour</strong> dans la discussion en réagissant
              directement aux arguments déjà énoncés. Chaque intervention est affichée en direct avec son avatar et son modèle.
            </p>
          </button>

          <button
            type="button"
            className={`multi-agent-mode-card ${mode === "dialectic" ? "is-active" : ""}`}
            onClick={() => setMode("dialectic")}
          >
            <div className="multi-agent-mode-card-header">
              <span className="multi-agent-mode-icon">⚔️</span>
              <strong>Débat Contradictoire (Thèse · Antithèse · 3e Voie)</strong>
              {mode === "dialectic" && <Check size={16} className="mode-check-icon" />}
            </div>
            <p>
              Un premier orateur expose la <strong>Thèse</strong> (favorable), un second attaque avec l'<strong>Antithèse</strong> (réfutation frontale),
              puis un troisième arbitre apporte la <strong>Contradiction & 3e Voie</strong>. Échanges <strong>courts, vifs et acérés</strong>.
            </p>
          </button>
        </div>

        {/* Debate rounds setting if in debate mode */}
        {mode === "debate" && (
          <div className="multi-agent-rounds-bar">
            <span>Nombre de tours de table :</span>
            <div className="rounds-pill-group">
              <button
                type="button"
                className={`rounds-pill ${rounds === 1 ? "is-active" : ""}`}
                onClick={() => setRounds(1)}
              >
                1 tour (Chacun s'exprime une fois)
              </button>
              <button
                type="button"
                className={`rounds-pill ${rounds === 2 ? "is-active" : ""}`}
                onClick={() => setRounds(2)}
              >
                2 tours (Droit de réponse croisé)
              </button>
            </div>
          </div>
        )}

        {/* Modal Navigation Tabs */}
        <div className="multi-agent-tabs">
          <button
            type="button"
            className={`multi-agent-tab ${activeTab === "compose" ? "is-active" : ""}`}
            onClick={() => setActiveTab("compose")}
          >
            <Bot size={15} />
            <span>Composition de l'Équipe ({agents.length})</span>
          </button>
          <button
            type="button"
            className={`multi-agent-tab ${activeTab === "presets" ? "is-active" : ""}`}
            onClick={() => setActiveTab("presets")}
          >
            <Sparkles size={15} />
            <span>Équipes Clé en Main</span>
          </button>
          <button
            type="button"
            className={`multi-agent-tab ${activeTab === "saved" ? "is-active" : ""}`}
            onClick={() => setActiveTab("saved")}
          >
            <Bookmark size={15} />
            <span>Mes Équipes Enregistrées {teamsData?.teams?.length ? `(${teamsData.teams.length})` : ""}</span>
          </button>
        </div>

        {/* Tab 1: Compose Agents */}
        {activeTab === "compose" && (
          <div className="multi-agent-content-area">
            {/* AI Persona Quick Generator Banner */}
            <div className="ai-persona-generator-bar">
              <div className="ai-persona-bar-header">
                <div className="ai-persona-bar-title">
                  <Sparkles size={16} className="sparkle-icon" />
                  <span>Créer une personnalité avec l'IA</span>
                </div>
                <span className="ai-persona-bar-subtitle">
                  Tapez le nom d'une personnalité historique, politique, scientifique ou fictive (ex : <em>Poutine</em>, <em>Churchill</em>, <em>Ada Lovelace</em>)
                </span>
              </div>
              <div className="ai-persona-input-row">
                <input
                  type="text"
                  className="ai-persona-input"
                  value={aiPromptInput}
                  onChange={(e) => setAiPromptInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleGeneratePersonaWithAi();
                    }
                  }}
                  placeholder="Ex : Vladimir Poutine, Elon Musk, Marie Curie, Batman..."
                  maxLength={100}
                  disabled={aiCreatingNew}
                />
                <button
                  type="button"
                  className="ai-persona-generate-btn"
                  onClick={() => handleGeneratePersonaWithAi()}
                  disabled={aiCreatingNew || !aiPromptInput.trim()}
                >
                  {aiCreatingNew ? (
                    <>
                      <LoaderCircle size={15} className="spin" />
                      <span>Génération du profil IA…</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={15} />
                      <span>Générer le profil</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="multi-agent-cards-grid">
              {agents.map((agent, index) => {
                const modelObj = modelMap.get(agent.model);
                return (
                  <div
                    key={agent.id || index}
                    className="agent-card"
                    style={{ borderTopColor: agent.color || "#6366f1" }}
                  >
                    {mode === "dialectic" && (
                      <div className="agent-dialectic-role-badge">
                        {index === 0
                          ? "🥊 Acte 1 · La Thèse (Pour / Vision forte)"
                          : index === 1
                          ? "⚔️ Acte 2 · L'Antithèse (Réfutation frontale)"
                          : index === 2
                          ? "⚖️ Acte 3 · La Contradiction & 3e Voie"
                          : "⚡ Acte 4 · Réplique finale"}
                      </div>
                    )}
                    {/* Agent Card Header */}
                    <div className="agent-card-header">
                      <div className="agent-avatar-wrap">
                        <select
                          className="agent-avatar-select"
                          value={agent.avatar}
                          onChange={(e) => handleUpdateAgent(index, { avatar: e.target.value })}
                          title="Changer l'avatar emoji"
                        >
                          {AVATAR_OPTIONS.map((av) => (
                            <option key={av} value={av}>
                              {av}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="agent-info-inputs">
                        <input
                          type="text"
                          className="agent-name-input"
                          value={agent.name}
                          onChange={(e) => handleUpdateAgent(index, { name: e.target.value })}
                          placeholder="Nom de l'agent"
                          maxLength={60}
                        />
                        <input
                          type="text"
                          className="agent-role-input"
                          value={agent.role}
                          onChange={(e) => handleUpdateAgent(index, { role: e.target.value })}
                          placeholder="Rôle / Spécialité"
                          maxLength={60}
                        />
                      </div>

                      {agents.length > 2 && (
                        <button
                          type="button"
                          className="agent-delete-btn"
                          onClick={() => handleRemoveAgent(index)}
                          title="Supprimer cet agent"
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>

                    {/* Model Selector with Pricing Display */}
                    <div className="agent-model-select-section">
                      <label className="agent-field-label">
                        <Cpu size={13} />
                        <span>Modèle assigné & Tarifs</span>
                      </label>

                      <div className="agent-model-select-wrap">
                        <select
                          className="agent-model-select"
                          value={agent.model}
                          onChange={(e) => handleUpdateAgent(index, { model: e.target.value })}
                        >
                          {models.map((m) => {
                            const promptPriceStr =
                              m.prompt_price_1m === 0 ? "Gratuit" : formatPrice(m.prompt_price_1m);
                            const completionPriceStr =
                              m.completion_price_1m === 0 ? "Gratuit" : formatPrice(m.completion_price_1m);
                            return (
                              <option key={m.id} value={m.id}>
                                {m.name} — {promptPriceStr} / {completionPriceStr} per 1M (
                                {m.provider || "IA"})
                              </option>
                            );
                          })}
                        </select>
                        <ChevronDown size={14} className="agent-select-arrow" />
                      </div>

                      {/* Detailed Pricing & Capabilities Card for this Agent */}
                      {modelObj && (
                        <div className="agent-model-pricing-strip">
                          <div className="pricing-mini-item">
                            <span className="p-label">Entrée :</span>
                            <span className={`p-val ${modelObj.prompt_price_1m === 0 ? "is-free" : ""}`}>
                              {modelObj.prompt_price_1m === 0
                                ? "Gratuit"
                                : `${formatPrice(modelObj.prompt_price_1m)} / 1M`}
                            </span>
                          </div>
                          <div className="pricing-mini-divider" />
                          <div className="pricing-mini-item">
                            <span className="p-label">Sortie :</span>
                            <span className={`p-val ${modelObj.completion_price_1m === 0 ? "is-free" : ""}`}>
                              {modelObj.completion_price_1m === 0
                                ? "Gratuit"
                                : `${formatPrice(modelObj.completion_price_1m)} / 1M`}
                            </span>
                          </div>
                          <div className="pricing-mini-divider" />
                          <div className="pricing-mini-item">
                            <span className="p-label">Contexte :</span>
                            <span className="p-val">{formatTokens(modelObj.context_length)}</span>
                          </div>
                          {modelObj.reasoning && (
                            <span className="agent-badge-feat reasoning" title="Modèle à raisonnement">
                              🧠 Raisonnement
                            </span>
                          )}
                          {modelObj.vision && (
                            <span className="agent-badge-feat vision" title="Modèle multimodal avec vision">
                              👁️ Vision
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Persona Prompt Textarea */}
                    <div className="agent-prompt-section">
                      <div className="agent-prompt-header">
                        <label className="agent-field-label">
                          <MessageSquare size={13} />
                          <span>Posture / Prompt Persona</span>
                        </label>

                        <div className="agent-prompt-tools-group">
                          {/* AI Generator for this specific agent */}
                          <button
                            type="button"
                            className="agent-prompt-magic-btn"
                            title="Générer ou ajuster la posture de cet agent à partir de son nom"
                            onClick={() => handleGeneratePersonaWithAi(index, agent.name)}
                            disabled={aiGeneratingIndex === index || !agent.name.trim()}
                          >
                            {aiGeneratingIndex === index ? (
                              <LoaderCircle size={12} className="spin" />
                            ) : (
                              <Sparkles size={12} />
                            )}
                            <span>Inspirer par l'IA</span>
                          </button>

                          {/* Quick Template Picker */}
                          {teamsData?.templates && teamsData.templates.length > 0 && (
                            <div className="agent-template-quick-picker">
                              <select
                                className="quick-template-select"
                                value=""
                                onChange={(e) => {
                                  if (e.target.value) {
                                    handleApplyTemplateToAgent(index, e.target.value);
                                  }
                                }}
                              >
                                <option value="">Remplacer par un agent type…</option>
                                {teamsData.templates.map((tpl) => (
                                  <option key={tpl.id} value={tpl.id}>
                                    {tpl.avatar} {tpl.name}
                                  </option>
                                ))}
                              </select>
                              <ChevronDown size={11} className="template-picker-arrow" />
                            </div>
                          )}
                        </div>
                      </div>

                      <textarea
                        className="agent-prompt-textarea"
                        value={agent.prompt}
                        onChange={(e) => handleUpdateAgent(index, { prompt: e.target.value })}
                        placeholder="Définissez les consignes de posture, l'expertise et l'angle d'analyse de cet agent..."
                        rows={4}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Add Agent and Save Team Row */}
            <div className="agent-actions-bar">
              {agents.length < 4 && (
                <button type="button" className="agent-add-btn" onClick={handleAddAgent}>
                  <Plus size={16} />
                  <span>Ajouter un {agents.length === 2 ? "3e" : "4e"} expert</span>
                </button>
              )}

              <div className="save-team-inline">
                <input
                  type="text"
                  className="save-team-input"
                  value={saveTeamName}
                  onChange={(e) => setSaveTeamName(e.target.value)}
                  placeholder="Nom de l'équipe (ex: Mon Conseil Juridique & Tech)"
                  maxLength={60}
                />
                <button
                  type="button"
                  className="save-team-btn"
                  onClick={handleSaveCurrentTeam}
                  disabled={isSavingTeam || !saveTeamName.trim()}
                >
                  {isSavingTeam ? <LoaderCircle size={14} className="spin" /> : <Bookmark size={14} />}
                  <span>Sauvegarder l'équipe</span>
                </button>
              </div>
            </div>

            {saveSuccess && (
              <div className="team-success-notice">
                <Check size={15} />
                <span>Équipe enregistrée avec succès dans vos préférences !</span>
              </div>
            )}
            {errorMsg && (
              <div className="team-error-notice">
                <AlertCircle size={15} />
                <span>{errorMsg}</span>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Preset Teams */}
        {activeTab === "presets" && (
          <div className="multi-agent-content-area">
            <p className="presets-intro">
              Sélectionnez une équipe type optimisée pour appliquer instantanément les meilleurs profils et modèles :
            </p>
            <div className="preset-teams-grid">
              {teamsData?.preset_teams?.map((preset) => (
                <div key={preset.id} className="preset-team-card">
                  <div className="preset-team-header">
                    <div>
                      <span className="preset-mode-badge">
                        {preset.mode === "synthesis" ? "🎯 Synthèse" : "🎙️ Débat"}
                      </span>
                      <h3>{preset.name}</h3>
                    </div>
                    <button
                      type="button"
                      className="preset-load-btn"
                      onClick={() => handleLoadPresetTeam(preset)}
                    >
                      <span>Charger l'équipe</span>
                    </button>
                  </div>
                  <p className="preset-desc">{preset.description}</p>
                  <div className="preset-agents-list">
                    {preset.agents.map((ag, idx) => (
                      <div key={idx} className="preset-agent-pill">
                        <span className="pill-avatar">{ag.avatar}</span>
                        <span className="pill-name">{ag.name}</span>
                        <span className="pill-role">({ag.role})</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 3: Saved Teams */}
        {activeTab === "saved" && (
          <div className="multi-agent-content-area">
            {loadingTeams ? (
              <div className="teams-loading">
                <LoaderCircle size={20} className="spin" />
                <span>Chargement de vos équipes…</span>
              </div>
            ) : !teamsData?.teams || teamsData.teams.length === 0 ? (
              <div className="teams-empty-state">
                <Bookmark size={32} />
                <h3>Aucune équipe personnalisée enregistrée</h3>
                <p>
                  Composez vos agents dans l'onglet « Composition de l'Équipe » et cliquez sur « Sauvegarder l'équipe »
                  pour les retrouver ici en un clic.
                </p>
              </div>
            ) : (
              <div className="saved-teams-grid">
                {teamsData.teams.map((team) => (
                  <div key={team.id} className="saved-team-card">
                    <div className="saved-team-header">
                      <div>
                        <span className="preset-mode-badge">
                          {team.mode === "synthesis" ? "🎯 Synthèse" : "🎙️ Débat"}
                        </span>
                        <h3>{team.name}</h3>
                      </div>
                      <div className="saved-team-actions">
                        <button
                          type="button"
                          className="preset-load-btn"
                          onClick={() =>
                            handleLoadPresetTeam({
                              mode: team.mode,
                              agents: team.agents,
                            })
                          }
                        >
                          <span>Utiliser</span>
                        </button>
                        <button
                          type="button"
                          className="saved-team-del-btn"
                          onClick={() => handleDeleteSavedTeam(team.id)}
                          title="Supprimer cette équipe"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                    {team.description && <p className="preset-desc">{team.description}</p>}
                    <div className="preset-agents-list">
                      {team.agents.map((ag, idx) => (
                        <div key={idx} className="preset-agent-pill">
                          <span className="pill-avatar">{ag.avatar}</span>
                          <span className="pill-name">{ag.name}</span>
                          <span className="pill-role">({ag.role})</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Footer Actions */}
        <footer className="multi-agent-modal-footer">
          {activeConfig && (
            <button type="button" className="multi-agent-btn-deactivate" onClick={handleDeactivate}>
              <span>Désactiver le Conseil</span>
            </button>
          )}

          <div className="multi-agent-footer-right">
            <button type="button" className="multi-agent-btn-cancel" onClick={onClose}>
              Annuler
            </button>
            <button type="button" className="multi-agent-btn-apply" onClick={handleConfirmApply}>
              <Check size={16} />
              <span>
                Activer {mode === "synthesis" ? "la Synthèse d'Experts" : mode === "debate" ? "la Table Ronde" : "le Débat Contradictoire"} ({agents.length} agents)
              </span>
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}

