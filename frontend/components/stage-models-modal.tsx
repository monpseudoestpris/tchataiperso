"use client";

import { useMemo, useState } from "react";
import {
  Brain,
  Check,
  Cpu,
  Eye,
  Layers,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import type { Model, StageModelsConfig } from "@/lib/api";
import { ModelModal } from "@/components/model-modal";

export type StageId = "plan_model" | "search_model" | "expert_model" | "synthesis_model" | "audit_model";

export interface StageDefinition {
  id: StageId;
  name: string;
  badge: string;
  icon: typeof Brain;
  color: string;
  description: string;
  defaultModel: string;
}

export const STAGES_DEFINITIONS: StageDefinition[] = [
  {
    id: "plan_model",
    name: "Étape 1 · Planification & Décomposition",
    badge: "Architecte",
    icon: Brain,
    color: "#6366f1",
    description: "Analyse panoramique à 360°, identification des angles contradictoires et découpage en modules stratégiques d'enquête.",
    defaultModel: "google/gemini-4-argon",
  },
  {
    id: "search_model",
    name: "Étape 2 · Recherche & Approfondissement",
    badge: "Retriever",
    icon: Search,
    color: "#06b6d4",
    description: "Validation itérative en cours de route, génération de sous-requêtes multilingues et évaluation des manques documentaires.",
    defaultModel: "google/gemini-3.8-flash",
  },
  {
    id: "expert_model",
    name: "Étape 3 · Collège des 3 Experts Indépendants",
    badge: "Comité Aveugle",
    icon: Cpu,
    color: "#a855f7",
    description: "Trois analyses spécialisées exécutées en parallèle et à l'aveugle (confrontation d'hypothèses et détection des failles).",
    defaultModel: "google/gemini-3.8-flash",
  },
  {
    id: "synthesis_model",
    name: "Étape 4 · Rédaction & Synthèse Finale",
    badge: "Écrivain",
    icon: Sparkles,
    color: "#10b981",
    description: "Arbitrage des avis divergents, intégration fluide des preuves sourcées, graphiques et rédaction structurée.",
    defaultModel: "google/gemini-3.8-flash",
  },
  {
    id: "audit_model",
    name: "Étape 5 · Relecture Critique Astra & Validation",
    badge: "GPT-6 Astra",
    icon: ShieldCheck,
    color: "#f59e0b",
    description: "Relecture critique exhaustive par GPT-6 Astra : validation/invalidation du texte et des sources, arbitrage factuel et remédiation directe des passages problématiques.",
    defaultModel: "openai/gpt-6-astra",
  },
];

export const PRESET_CONFIGS: {
  id: string;
  name: string;
  icon: string;
  desc: string;
  config: StageModelsConfig;
}[] = [
  {
    id: "balanced",
    name: "⚖️ Équilibré (Recommandé)",
    icon: "⚖️",
    desc: "Planification par Gemini Argon (forte vision), exécution & rédaction par Gemini Flash, et relecture critique par GPT-6 Astra.",
    config: {
      plan_model: "google/gemini-4-argon",
      search_model: "google/gemini-3.8-flash",
      expert_model: "google/gemini-3.8-flash",
      synthesis_model: "google/gemini-3.8-flash",
      audit_model: "openai/gpt-6-astra",
    },
  },
  {
    id: "speed",
    name: "⚡ Économique & Véloce",
    icon: "⚡",
    desc: "100 % Gemini Flash pour une latence minimale et une consommation de tokens très réduite.",
    config: {
      plan_model: "google/gemini-3.8-flash",
      search_model: "google/gemini-3.8-flash",
      expert_model: "google/gemini-3.8-flash",
      synthesis_model: "google/gemini-3.8-flash",
      audit_model: "google/gemini-3.8-flash",
    },
  },
  {
    id: "max_reasoning",
    name: "🧠 Raisonnement & Rigueur Max",
    icon: "🧠",
    desc: "Argon pour le plan, DeepSeek R1 pour les 3 experts aveugles, Claude 3.5 Sonnet pour la rédaction, et GPT-6 Astra pour l'audit critique.",
    config: {
      plan_model: "google/gemini-4-argon",
      search_model: "google/gemini-3.8-flash",
      expert_model: "deepseek/deepseek-r1",
      synthesis_model: "anthropic/claude-3.5-sonnet",
      audit_model: "openai/gpt-6-astra",
    },
  },
];

type StageModelsModalProps = {
  isOpen: boolean;
  modeTitle: "DeepSearch" | "Mode Apprendre";
  config: StageModelsConfig;
  models: Model[];
  onChangeConfig: (newConfig: StageModelsConfig) => void;
  onClose: () => void;
  onRefreshModels?: () => Promise<void>;
};

function formatTokens(tokens?: number): string {
  if (!tokens || tokens <= 0) return "—";
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 === 0 ? 0 : 1)}M`;
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}k`;
  return `${tokens}`;
}

function formatPrice(val?: number | null): string {
  if (val === null || val === undefined) return "—";
  if (val === 0) return "Gratuit";
  if (val < 0.01) return `$${val.toFixed(4)}`;
  return `$${val.toFixed(2)}`;
}

export function StageModelsModal({
  isOpen,
  modeTitle,
  config,
  models,
  onChangeConfig,
  onClose,
  onRefreshModels,
}: StageModelsModalProps) {
  const [activeStagePicker, setActiveStagePicker] = useState<StageId | null>(null);

  const modelMap = useMemo(() => {
    const map = new Map<string, Model>();
    for (const m of models) {
      map.set(m.id, m);
    }
    return map;
  }, [models]);

  if (!isOpen) return null;

  const handleApplyPreset = (presetConfig: StageModelsConfig) => {
    onChangeConfig({ ...presetConfig });
  };

  const handleResetDefaults = () => {
    const def: StageModelsConfig = {};
    for (const st of STAGES_DEFINITIONS) {
      def[st.id] = st.defaultModel;
    }
    onChangeConfig(def);
  };

  const handlePickModel = (modelId: string) => {
    if (!activeStagePicker) return;
    onChangeConfig({
      ...config,
      [activeStagePicker]: modelId,
    });
    setActiveStagePicker(null);
  };

  return (
    <>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/60 backdrop-blur-sm animate-fade-in">
        <div
          role="dialog"
          aria-modal="true"
          className="relative flex flex-col w-full max-w-3xl max-h-[90vh] bg-surface-base border border-surface-border rounded-2xl shadow-2xl overflow-hidden animate-scale-up"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border bg-surface-subtle/50">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-primary/10 text-primary border border-primary/20">
                <Workflow className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                  Configuration des modèles · {modeTitle}
                  <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium border border-primary/20">
                    5 Étapes
                  </span>
                </h2>
                <p className="text-xs text-text-muted mt-0.5">
                  Choisissez précisément le modèle IA alloué à chaque étape du pipeline pour équilibrer coût, vélocité et puissance cognitive.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-hover transition-colors"
              aria-label="Fermer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Presets Bar */}
          <div className="px-6 py-3 border-b border-surface-border/60 bg-surface-subtle/30 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-text-muted mr-1">Préréglages :</span>
              {PRESET_CONFIGS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleApplyPreset(preset.config)}
                  className="text-xs px-2.5 py-1 rounded-lg border border-surface-border bg-surface-base hover:border-primary/50 hover:bg-surface-hover text-text-secondary transition-colors flex items-center gap-1.5 shadow-sm"
                  title={preset.desc}
                >
                  <span>{preset.icon}</span>
                  <span>{preset.name.replace(/^[^\s]+\s*/, "")}</span>
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={handleResetDefaults}
              className="text-xs px-2 py-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-hover transition-colors flex items-center gap-1"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Rétablir défauts</span>
            </button>
          </div>

          {/* Stages List */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {STAGES_DEFINITIONS.map((stage, idx) => {
              const currentModelId = config[stage.id] || stage.defaultModel;
              const modelData = modelMap.get(currentModelId);
              const Icon = stage.icon;
              const isDefault = currentModelId === stage.defaultModel;

              return (
                <div
                  key={stage.id}
                  className="p-4 rounded-xl border border-surface-border bg-surface-base hover:border-surface-border-strong transition-all flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm"
                >
                  {/* Stage description & identity */}
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
                      style={{ backgroundColor: `${stage.color}15`, color: stage.color }}
                    >
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-text-primary">
                          {stage.name}
                        </span>
                        <span
                          className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full"
                          style={{
                            backgroundColor: `${stage.color}18`,
                            color: stage.color,
                            border: `1px solid ${stage.color}30`,
                          }}
                        >
                          {stage.badge}
                        </span>
                      </div>
                      <p className="text-xs text-text-muted mt-1 leading-relaxed">
                        {stage.description}
                      </p>
                    </div>
                  </div>

                  {/* Configured model chip & action */}
                  <div className="flex items-center gap-3 shrink-0 self-end md:self-center">
                    <div className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <span className="text-xs font-medium text-text-primary max-w-[200px] truncate" title={currentModelId}>
                          {modelData?.name || currentModelId.split("/").pop()}
                        </span>
                        {isDefault && (
                          <span className="text-[10px] text-text-muted bg-surface-hover px-1.5 py-0.2 rounded font-mono">
                            défaut
                          </span>
                        )}
                      </div>
                      <div className="flex items-center justify-end gap-2 text-[11px] text-text-muted mt-0.5 font-mono">
                        {modelData?.context_length ? (
                          <span>Ctx: {formatTokens(modelData.context_length)}</span>
                        ) : null}
                        {modelData && (
                          <span>
                            {modelData.prompt_price_1m === 0 ? "Gratuit" : `${formatPrice(modelData.completion_price_1m)}/1M`}
                          </span>
                        )}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => setActiveStagePicker(stage.id)}
                      className="px-3 py-1.5 text-xs font-medium rounded-lg border border-primary/30 bg-primary/10 text-primary hover:bg-primary/20 transition-all flex items-center gap-1.5 active:scale-95"
                    >
                      <span>Changer</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div className="px-6 py-3.5 border-t border-surface-border bg-surface-subtle/50 flex items-center justify-between">
            <span className="text-xs text-text-muted">
              Les configurations choisies sont automatiquement mémorisées localement.
            </span>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-sm active:scale-95"
            >
              Terminer & Valider
            </button>
          </div>
        </div>
      </div>

      {/* Model Picker Sub-Modal for Stage Selection */}
      {activeStagePicker && (
        <ModelModal
          currentModel={config[activeStagePicker] || STAGES_DEFINITIONS.find((s) => s.id === activeStagePicker)?.defaultModel || ""}
          models={models}
          onSelectModel={handlePickModel}
          onClose={() => setActiveStagePicker(null)}
          onRefreshModels={onRefreshModels}
        />
      )}
    </>
  );
}

