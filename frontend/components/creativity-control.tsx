"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Info, RotateCcw, Sliders, Sparkles } from "lucide-react";
import { api, type Model, type ModelParametersResponse, type SamplingParameters } from "@/lib/api";

export type ParameterMeta = {
  name: keyof SamplingParameters;
  label: string;
  role: string;
  description: string;
  hint: string;
  unavailableLabel: string;
  min?: number;
  max?: number;
  step?: number;
  defaultVal: number | string | null;
  type: "float" | "int" | "select" | "json";
  options?: { value: string; label: string }[];
};

export const CREATIVITY_PARAMETER_DEFS: ParameterMeta[] = [
  {
    name: "temperature",
    label: "temperature",
    role: "Aléatoire et originalité",
    description: "Contrôle l'audace du modèle. Plus elle monte, plus il ose choisir des mots improbables.",
    hint: "Basse : réponses classiques. Haute : réponses originales, parfois absurdes.",
    unavailableLabel: "Pas de contrôle direct de l'aléatoire",
    min: 0,
    max: 2,
    step: 0.05,
    defaultVal: 0.2,
    type: "float",
  },
  {
    name: "top_p",
    label: "top_p",
    role: "Diversité des tokens possibles",
    description: "Élimine les mots les moins probables.",
    hint: "À 0.9, le modèle ne choisit que parmi les mots représentant ensemble 90 % de la probabilité.",
    unavailableLabel: "Pas de réglage",
    min: 0.05,
    max: 1,
    step: 0.05,
    defaultVal: 1.0,
    type: "float",
  },
  {
    name: "top_k",
    label: "top_k",
    role: "Nombre de tokens candidats",
    description: "Limite le nombre de mots possibles à chaque étape.",
    hint: "À 20, le modèle choisit parmi les 20 mots les plus probables.",
    unavailableLabel: "Pas de réglage",
    min: 1,
    max: 500,
    step: 1,
    defaultVal: 40,
    type: "int",
  },
  {
    name: "min_p",
    label: "min_p",
    role: "Élimination des tokens trop improbables",
    description: "Élimine les tokens dont la probabilité est trop faible par rapport au token le plus probable.",
    hint: "À 0.05, tout token ayant moins de 5 % de la probabilité du meilleur choix est écarté.",
    unavailableLabel: "Pas de réglage",
    min: 0,
    max: 1,
    step: 0.01,
    defaultVal: 0,
    type: "float",
  },
  {
    name: "top_a",
    label: "top_a",
    role: "Filtrage dynamique des tokens",
    description: "Ajuste dynamiquement le seuil de filtrage selon la confiance du modèle dans son premier choix.",
    hint: "Quand le modèle est très sûr de lui, la sélection se resserre automatiquement.",
    unavailableLabel: "Pas de réglage",
    min: 0,
    max: 1,
    step: 0.05,
    defaultVal: 0,
    type: "float",
  },
  {
    name: "presence_penalty",
    label: "presence_penalty",
    role: "Introduction de nouvelles idées",
    description: "Encourage le modèle à introduire de nouvelles idées plutôt qu'à revenir sur les mêmes.",
    hint: "Utile pour un brainstorming qui tourne en rond.",
    unavailableLabel: "Pas de réglage",
    min: -2,
    max: 2,
    step: 0.1,
    defaultVal: 0,
    type: "float",
  },
  {
    name: "frequency_penalty",
    label: "frequency_penalty",
    role: "Réduction des répétitions",
    description: "Décourage les mots utilisés trop souvent dans la réponse.",
    hint: "Évite de répéter constamment les mêmes expressions.",
    unavailableLabel: "Pas de réglage",
    min: -2,
    max: 2,
    step: 0.1,
    defaultVal: 0,
    type: "float",
  },
  {
    name: "repetition_penalty",
    label: "repetition_penalty",
    role: "Pénalisation des tokens déjà utilisés",
    description: "Pénalise les répétitions, avec un mécanisme différent de frequency_penalty.",
    hint: "Limite les phrases et formulations répétitives.",
    unavailableLabel: "Pas de réglage",
    min: 0.1,
    max: 2,
    step: 0.05,
    defaultVal: 1.0,
    type: "float",
  },
  {
    name: "logit_bias",
    label: "logit_bias",
    role: "Favoriser ou défavoriser certains tokens",
    description: "Modifie manuellement la probabilité d'apparition de certains tokens (identifiants numériques).",
    hint: 'Objet JSON {"token_id": bias} entre -100 (interdit) et +100 (forcé).',
    unavailableLabel: "Pas de réglage",
    defaultVal: null,
    type: "json",
  },
  {
    name: "seed",
    label: "seed",
    role: "Variation ou reproductibilité entre générations",
    description: "Permet de tenter de reproduire les mêmes choix aléatoires.",
    hint: "Même question + même seed = résultats potentiellement similaires, sans garantie absolue.",
    unavailableLabel: "Pas de réglage",
    min: 0,
    max: 2147483647,
    step: 1,
    defaultVal: null,
    type: "int",
  },
  {
    name: "reasoning",
    label: "reasoning",
    role: "Influence indirecte par la profondeur de réflexion",
    description: "Contrôle le niveau de réflexion interne du modèle avant de formuler sa réponse.",
    hint: "Utile sur les modèles sans température (ex. Sonnet 5.5) pour approfondir l'exploration conceptuelle.",
    unavailableLabel: "Pas de réglage",
    defaultVal: null,
    type: "select",
    options: [
      { value: "none", label: "Désactivé (none)" },
      { value: "low", label: "Faible (low)" },
      { value: "medium", label: "Moyen (medium)" },
      { value: "high", label: "Élevé (high)" },
    ],
  },
  {
    name: "reasoning_effort",
    label: "reasoning_effort",
    role: "Variante de configuration de l'effort de réflexion",
    description: "Ajuste l'effort de raisonnement alloué aux modèles compatibles OpenAI / OpenRouter.",
    hint: "Permet de choisir entre rapidité (low) et réflexion approfondie (high).",
    unavailableLabel: "Pas de réglage",
    defaultVal: null,
    type: "select",
    options: [
      { value: "minimal", label: "Minimal (minimal)" },
      { value: "low", label: "Faible (low)" },
      { value: "medium", label: "Moyen (medium)" },
      { value: "high", label: "Élevé (high)" },
    ],
  },
  {
    name: "verbosity",
    label: "verbosity",
    role: "Influence indirecte par le niveau de développement",
    description: "Contrôle la longueur et le degré de développement des réponses.",
    hint: "Permet d'obtenir des réponses très synthétiques (low) ou richement développées (high).",
    unavailableLabel: "Pas de réglage",
    defaultVal: null,
    type: "select",
    options: [
      { value: "low", label: "Concis (low)" },
      { value: "medium", label: "Équilibré (medium)" },
      { value: "high", label: "Développé (high)" },
    ],
  },
];

export const CREATIVITY_PRESETS = [
  { label: "Auto", value: null, desc: "Par défaut" },
  { label: "Précis", value: 0.1, desc: "Factuel & rigoureux" },
  { label: "Équilibré", value: 0.4, desc: "Naturel & nuancé" },
  { label: "Créatif", value: 0.7, desc: "Riche & expressif" },
  { label: "Audacieux", value: 0.95, desc: "Brainstorming & hypothèses originales" },
];

export function computeAutoParamsFromCreativity(
  creativity: number | null | undefined,
  supported: Set<string>,
): SamplingParameters {
  if (creativity === null || creativity === undefined) {
    return supported.has("temperature") ? { temperature: 0.2 } : {};
  }
  const c = Math.max(0, Math.min(1, creativity));
  const out: SamplingParameters = {};
  if (supported.has("temperature")) {
    out.temperature = Number((c * 1.5).toFixed(2));
  }
  if (supported.has("top_p")) {
    const tp = c <= 0.7 ? 0.3 + (c / 0.7) * 0.65 : 0.95 + ((c - 0.7) / 0.3) * 0.05;
    out.top_p = Number(Math.max(0.1, Math.min(1, tp)).toFixed(2));
  }
  if (supported.has("top_k")) {
    out.top_k = Math.max(1, Math.round(10 + c * 90));
  }
  if (supported.has("min_p") && !supported.has("top_p")) {
    out.min_p = Number(Math.max(0.01, 0.15 - c * 0.13).toFixed(2));
  }
  if (supported.has("presence_penalty")) {
    out.presence_penalty = c > 0.4 ? Number((((c - 0.4) / 0.6) * 0.6).toFixed(2)) : 0;
  }
  if (supported.has("frequency_penalty")) {
    out.frequency_penalty = c > 0.3 ? Number((((c - 0.3) / 0.7) * 0.5).toFixed(2)) : 0;
  }
  if (supported.has("repetition_penalty") && !supported.has("frequency_penalty")) {
    out.repetition_penalty = c > 0.3 ? Number((1 + ((c - 0.3) / 0.7) * 0.15).toFixed(2)) : 1.0;
  }
  return out;
}

export function formatCreativityBadge(
  creativity?: number | null,
  samplingParams?: SamplingParameters | null,
): string | null {
  const hasCustomParams =
    samplingParams &&
    Object.values(samplingParams).some(v => v !== null && v !== undefined && v !== "");
  if (creativity !== null && creativity !== undefined) {
    const pct = Math.round(creativity * 100);
    return hasCustomParams ? `Créativité ${pct}%+` : `Créativité ${pct}%`;
  }
  if (hasCustomParams) {
    if (samplingParams?.temperature !== null && samplingParams?.temperature !== undefined) {
      return `Temp. ${samplingParams.temperature}`;
    }
    if (samplingParams?.reasoning) {
      return `Réflexion ${samplingParams.reasoning}`;
    }
    if (samplingParams?.reasoning_effort) {
      return `Effort ${samplingParams.reasoning_effort}`;
    }
    if (samplingParams?.verbosity) {
      return `Verbosité ${samplingParams.verbosity}`;
    }
    return "Paramètres IA";
  }
  return null;
}

type CreativityControlProps = {
  creativity: number | null;
  samplingParams: SamplingParameters | null;
  onChange: (nextCreativity: number | null, nextParams: SamplingParameters | null) => void;
  model?: string;
  models?: Model[];
  disabled?: boolean;
  compact?: boolean;
  inheritedLabel?: string | null;
};

export function CreativityControl({
  creativity,
  samplingParams,
  onChange,
  model,
  models = [],
  disabled = false,
  compact = false,
  inheritedLabel = null,
}: CreativityControlProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [fetchedSupported, setFetchedSupported] = useState<string[] | null>(null);
  const [logitBiasText, setLogitBiasText] = useState<string>(() => {
    const lb = samplingParams?.logit_bias;
    if (!lb) return "";
    return typeof lb === "string" ? lb : JSON.stringify(lb);
  });

  const modelObj = useMemo(() => models.find(m => m.id === model), [models, model]);

  useEffect(() => {
    const lb = samplingParams?.logit_bias;
    if (!lb) {
      setLogitBiasText("");
    } else if (typeof lb === "string") {
      setLogitBiasText(lb);
    } else {
      setLogitBiasText(JSON.stringify(lb));
    }
  }, [samplingParams?.logit_bias]);

  useEffect(() => {
    if (!model) {
      setFetchedSupported(null);
      return;
    }
    if (modelObj?.supported_parameters && modelObj.supported_parameters.length > 0) {
      setFetchedSupported(modelObj.supported_parameters);
      return;
    }
    const controller = new AbortController();
    api<ModelParametersResponse>(`/models/${encodeURIComponent(model)}/parameters`, {
      signal: controller.signal,
    })
      .then(res => {
        if (!controller.signal.aborted && Array.isArray(res.supported_parameters)) {
          setFetchedSupported(res.supported_parameters);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setFetchedSupported(null);
      });
    return () => controller.abort();
  }, [model, modelObj]);

  const supportedSet = useMemo(() => {
    const list =
      fetchedSupported ??
      modelObj?.supported_parameters ?? [
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "seed",
      ];
    return new Set(list);
  }, [fetchedSupported, modelObj]);

  const hasTemperatureSupport = supportedSet.has("temperature");

  const autoComputed = useMemo(
    () => computeAutoParamsFromCreativity(creativity, supportedSet),
    [creativity, supportedSet],
  );

  function handlePresetClick(val: number | null) {
    if (disabled) return;
    if (val === null) {
      onChange(null, null);
    } else {
      onChange(val, samplingParams);
    }
  }

  function handleSliderChange(val: number) {
    if (disabled) return;
    onChange(Number(val.toFixed(2)), samplingParams);
  }

  function handleParamChange(name: keyof SamplingParameters, rawValue: string) {
    if (disabled) return;
    const current: Record<string, unknown> = { ...(samplingParams || {}) };
    const def = CREATIVITY_PARAMETER_DEFS.find(d => d.name === name);
    if (rawValue.trim() === "") {
      delete current[name];
    } else if (def?.type === "select") {
      current[name] = rawValue.trim();
    } else if (def?.type === "json") {
      setLogitBiasText(rawValue);
      try {
        const parsed = JSON.parse(rawValue);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
          current[name] = parsed;
        } else {
          return;
        }
      } catch {
        return;
      }
    } else {
      const parsed = def?.type === "int" ? parseInt(rawValue, 10) : parseFloat(rawValue);
      if (!Number.isNaN(parsed)) {
        current[name] = parsed;
      }
    }
    const hasAny = Object.values(current).some(v => v !== null && v !== undefined && v !== "");
    onChange(creativity, hasAny ? (current as SamplingParameters) : null);
  }

  function handleResetAll() {
    if (disabled) return;
    setLogitBiasText("");
    onChange(null, null);
  }

  const hasCustom =
    creativity !== null ||
    Boolean(samplingParams && Object.values(samplingParams).some(v => v !== null && v !== undefined && v !== ""));

  return (
    <div
      className="creativity-control"
      style={{
        border: "1px solid var(--border, #e2e8f0)",
        borderRadius: "10px",
        padding: compact ? "10px 12px" : "12px 14px",
        background: "var(--surface-subtle, rgba(248, 250, 252, 0.7))",
        marginTop: "8px",
        marginBottom: "8px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", marginBottom: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
          <Sparkles size={14} style={{ color: "#6366f1" }} />
          <strong style={{ fontSize: "12.5px" }}>Créativité hybride des réponses</strong>
          {creativity !== null ? (
            <span
              style={{
                fontSize: "11px",
                fontWeight: 600,
                padding: "1px 7px",
                borderRadius: "999px",
                background: "rgba(99, 102, 241, 0.12)",
                color: "#4f46e5",
              }}
            >
              {Math.round(creativity * 100)} %
            </span>
          ) : (
            <span
              style={{
                fontSize: "11px",
                padding: "1px 7px",
                borderRadius: "999px",
                background: "rgba(100, 116, 139, 0.12)",
                color: "var(--text-secondary, #64748b)",
              }}
            >
              {inheritedLabel || "Par défaut"}
            </span>
          )}
          <span
            style={{
              fontSize: "10.5px",
              padding: "1px 7px",
              borderRadius: "999px",
              background: hasTemperatureSupport ? "rgba(16, 185, 129, 0.12)" : "rgba(245, 158, 11, 0.14)",
              color: hasTemperatureSupport ? "#059669" : "#b45309",
              fontWeight: 600,
            }}
          >
            {hasTemperatureSupport
              ? "Température + Consignes prompt"
              : "Consignes prompt (sans température)"}
          </span>
        </div>
        {hasCustom && (
          <button
            type="button"
            disabled={disabled}
            onClick={handleResetAll}
            title="Réinitialiser la créativité et les paramètres aux valeurs par défaut"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              fontSize: "11px",
              color: "var(--text-secondary, #64748b)",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: "2px 4px",
            }}
          >
            <RotateCcw size={12} />
            <span>Réinitialiser</span>
          </button>
        )}
      </div>

      {/* Presets */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "5px", marginBottom: "10px" }}>
        {CREATIVITY_PRESETS.map(preset => {
          const isSelected =
            preset.value === null
              ? creativity === null
              : creativity !== null && Math.abs(creativity - preset.value) < 0.06;
          return (
            <button
              key={preset.label}
              type="button"
              disabled={disabled}
              onClick={() => handlePresetClick(preset.value)}
              title={preset.desc}
              style={{
                fontSize: "11.5px",
                padding: "4px 9px",
                borderRadius: "7px",
                border: isSelected ? "1px solid #6366f1" : "1px solid var(--border, #cbd5e1)",
                background: isSelected ? "rgba(99, 102, 241, 0.1)" : "var(--surface, #fff)",
                color: isSelected ? "#4f46e5" : "var(--text-primary, #1e293b)",
                fontWeight: isSelected ? 600 : 500,
                cursor: disabled ? "not-allowed" : "pointer",
              }}
            >
              {preset.label}
            </button>
          );
        })}
      </div>

      {/* Slider */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
        <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", minWidth: "52px" }}>Classique</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          disabled={disabled}
          value={creativity ?? 0.2}
          onChange={e => handleSliderChange(parseFloat(e.target.value))}
          aria-label="Niveau de créativité"
          style={{ flex: 1, accentColor: "#6366f1", cursor: disabled ? "not-allowed" : "pointer" }}
        />
        <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)", minWidth: "52px", textAlign: "right" }}>
          Original
        </span>
      </div>

      {/* Hybrid behavior explanation */}
      <div
        style={{
          fontSize: "11px",
          color: "var(--text-secondary, #475569)",
          lineHeight: 1.35,
          marginTop: "4px",
        }}
      >
        {hasTemperatureSupport ? (
          <span>
            Quel que soit le modèle, la consigne écrite est injectée dans le prompt (en plus des paramètres supportés comme <code>temperature</code>), sans jamais inventer de faits.
          </span>
        ) : (
          <span>
            Ce modèle n&apos;expose pas de contrôle direct de l&apos;aléatoire (<code>temperature</code>) : le curseur injecte la consigne écrite dans le prompt (exploration d&apos;hypothèses originales sans jamais inventer de faits).
          </span>
        )}
      </div>

      {/* Summary of active parameters for the model */}
      <div
        style={{
          fontSize: "11px",
          color: "var(--text-secondary, #64748b)",
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
          marginTop: "6px",
        }}
      >
        {CREATIVITY_PARAMETER_DEFS.map(def => {
          const isAvail = supportedSet.has(def.name);
          if (!isAvail) return null;
          const explicitVal = samplingParams?.[def.name];
          const effectiveVal = explicitVal !== undefined && explicitVal !== null ? explicitVal : autoComputed[def.name];
          if (effectiveVal === undefined || effectiveVal === null || effectiveVal === "") return null;
          const formattedVal = typeof effectiveVal === "object" ? JSON.stringify(effectiveVal) : String(effectiveVal);
          return (
            <span key={def.name} style={{ fontFamily: "monospace" }}>
              {def.name}={formattedVal}
            </span>
          );
        })}
      </div>

      {/* Accordion toggle for the 13 parameters */}
      <div style={{ marginTop: "8px", borderTop: "1px dashed var(--border, #e2e8f0)", paddingTop: "8px" }}>
        <button
          type="button"
          onClick={() => setAdvancedOpen(prev => !prev)}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
            fontSize: "11.5px",
            fontWeight: 600,
            color: "var(--text-secondary, #475569)",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: "5px" }}>
            <Sliders size={12} />
            <span>Paramètres détaillés du modèle (aléatoire, pénalités, seed, reasoning, verbosity)</span>
          </span>
          {advancedOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>

        {advancedOpen && (
          <div
            style={{
              marginTop: "10px",
              display: "flex",
              flexDirection: "column",
              gap: "10px",
              maxHeight: compact ? "340px" : "420px",
              overflowY: "auto",
              paddingRight: "6px",
              paddingBottom: "8px",
              scrollbarWidth: "thin",
            }}
          >
            {modelObj && (
              <div
                style={{
                  fontSize: "11px",
                  padding: "6px 10px",
                  borderRadius: "6px",
                  background: "rgba(37, 99, 235, 0.06)",
                  color: "var(--text-secondary, #334155)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <Info size={13} style={{ color: "#2563eb", flexShrink: 0 }} />
                <span>
                  Disponibilité détectée pour <strong>{modelObj.name}</strong> ({supportedSet.size}/{CREATIVITY_PARAMETER_DEFS.length} paramètres pris en charge).
                </span>
              </div>
            )}

            {CREATIVITY_PARAMETER_DEFS.map(def => {
              const isAvailable = supportedSet.has(def.name);
              const explicitVal = samplingParams?.[def.name];
              const autoVal = autoComputed[def.name];
              return (
                <div
                  key={def.name}
                  style={{
                    padding: "8px 10px",
                    borderRadius: "8px",
                    border: "1px solid var(--border, #e2e8f0)",
                    background: isAvailable ? "var(--surface, #fff)" : "rgba(241, 245, 249, 0.6)",
                    opacity: isAvailable ? 1 : 0.65,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", flexWrap: "wrap" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
                      <code style={{ fontSize: "12px", fontWeight: 700, color: "#1e293b" }}>{def.label}</code>
                      <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-secondary, #475569)" }}>
                        — {def.role}
                      </span>
                      <span
                        style={{
                          fontSize: "10px",
                          padding: "1px 6px",
                          borderRadius: "999px",
                          fontWeight: 600,
                          background: isAvailable ? "rgba(16, 185, 129, 0.12)" : "rgba(148, 163, 184, 0.2)",
                          color: isAvailable ? "#059669" : "#64748b",
                        }}
                      >
                        {isAvailable ? "Disponible" : def.unavailableLabel}
                      </span>
                    </div>

                    {def.type === "select" && def.options ? (
                      <select
                        disabled={disabled || !isAvailable}
                        value={explicitVal !== undefined && explicitVal !== null ? String(explicitVal) : ""}
                        onChange={e => handleParamChange(def.name, e.target.value)}
                        aria-label={def.label}
                        style={{
                          fontSize: "12px",
                          padding: "3px 8px",
                          borderRadius: "6px",
                          border: "1px solid var(--border, #cbd5e1)",
                          background: "var(--surface, #fff)",
                        }}
                      >
                        <option value="">Auto (par défaut)</option>
                        {def.options.map(opt => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : def.type === "json" ? (
                      <input
                        type="text"
                        disabled={disabled || !isAvailable}
                        placeholder='ex: {"1234": -50}'
                        value={logitBiasText}
                        onChange={e => {
                          setLogitBiasText(e.target.value);
                          handleParamChange(def.name, e.target.value);
                        }}
                        aria-label={def.label}
                        style={{
                          width: "160px",
                          fontSize: "11.5px",
                          fontFamily: "monospace",
                          padding: "3px 6px",
                          borderRadius: "6px",
                          border: "1px solid var(--border, #cbd5e1)",
                        }}
                      />
                    ) : (
                      <input
                        type="number"
                        min={def.min}
                        max={def.max}
                        step={def.step}
                        disabled={disabled || !isAvailable}
                        placeholder={autoVal !== undefined && autoVal !== null ? `Auto (${autoVal})` : "Auto"}
                        value={explicitVal !== undefined && explicitVal !== null ? String(explicitVal) : ""}
                        onChange={e => handleParamChange(def.name, e.target.value)}
                        aria-label={def.label}
                        style={{
                          width: def.name === "seed" ? "115px" : "88px",
                          fontSize: "12px",
                          padding: "3px 6px",
                          borderRadius: "6px",
                          border: "1px solid var(--border, #cbd5e1)",
                          textAlign: "right",
                        }}
                      />
                    )}
                  </div>
                  <p style={{ margin: "4px 0 2px", fontSize: "11.5px", color: "var(--text-primary, #334155)", lineHeight: 1.35 }}>
                    {def.description}
                  </p>
                  <small style={{ display: "block", fontSize: "11px", color: "var(--text-secondary, #64748b)", lineHeight: 1.3 }}>
                    💡 {def.hint}
                  </small>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
