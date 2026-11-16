"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Code2, LoaderCircle, Plus, Sliders, Sparkles, X } from "lucide-react";

import type { CustomIndicator, CustomIndicatorGuideLine, EodBar } from "@/lib/api";
import { CUSTOM_INDICATOR_PRESETS, validateCustomFormula } from "@/lib/custom-indicators";

type FinanceCustomIndicatorModalProps = {
  isOpen: boolean;
  onClose: () => void;
  bars: EodBar[];
  initialIndicator?: CustomIndicator | null;
  onSave: (payload: {
    id?: string;
    name: string;
    formula: string;
    pane: "overlay" | "oscillator";
    series_type: "line" | "histogram" | "dots";
    color: string;
    guide_lines: CustomIndicatorGuideLine[];
    enabled_by_default: boolean;
  }) => Promise<void>;
};

const COLOR_SWATCHES = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#ec4899",
  "#0ea5e9",
  "#14b8a6",
  "#f97316",
];

const ASSISTANT_TYPES = [
  { id: "ema", label: "EMA (Moyenne Exponentielle)", pane: "overlay" as const, hasMult: false, defaultPeriod: 9 },
  { id: "sma", label: "SMA (Moyenne Simple)", pane: "overlay" as const, hasMult: false, defaultPeriod: 100 },
  { id: "wma", label: "WMA (Moyenne Pondérée)", pane: "overlay" as const, hasMult: false, defaultPeriod: 20 },
  { id: "rsi", label: "RSI personnalisé", pane: "oscillator" as const, hasMult: false, defaultPeriod: 7 },
  { id: "roc", label: "ROC (Rate of Change %)", pane: "oscillator" as const, hasMult: false, defaultPeriod: 10 },
  { id: "keltner_up", label: "Keltner Supérieur (EMA + k·ATR)", pane: "overlay" as const, hasMult: true, defaultPeriod: 20 },
  { id: "keltner_dn", label: "Keltner Inférieur (EMA - k·ATR)", pane: "overlay" as const, hasMult: true, defaultPeriod: 20 },
  { id: "dist_sma", label: "Écart à la SMA (%)", pane: "oscillator" as const, hasMult: false, defaultPeriod: 50 },
];

const FORMULA_SNIPPETS = [
  "close",
  "hlc3",
  "sma(close, 20)",
  "ema(close, 12)",
  "rsi(close, 14)",
  "atr(14)",
  "boll_upper(close, 20, 2)",
  "macd_hist(close, 12, 26, 9)",
  "iff(close > sma(close, 50), 1, -1)",
];

function parseGuideLinesInput(raw: string): CustomIndicatorGuideLine[] {
  if (!raw.trim()) return [];
  const parts = raw
    .split(/[,;\s]+/)
    .map(s => s.trim())
    .filter(Boolean)
    .slice(0, 6);
  const out: CustomIndicatorGuideLine[] = [];
  for (const part of parts) {
    const val = Number(part);
    if (Number.isFinite(val)) {
      const color = val > 50 ? "#f43f5e" : val < 0 || (val > 0 && val <= 35) ? "#10b981" : "#94a3b8";
      out.push({ value: val, color });
    }
  }
  return out;
}

export function FinanceCustomIndicatorModal({
  isOpen,
  onClose,
  bars,
  initialIndicator,
  onSave,
}: FinanceCustomIndicatorModalProps) {
  const [mode, setMode] = useState<"formula" | "assistant">("formula");
  const [name, setName] = useState("EMA 9");
  const [formula, setFormula] = useState("ema(close, 9)");
  const [pane, setPane] = useState<"overlay" | "oscillator">("overlay");
  const [seriesType, setSeriesType] = useState<"line" | "histogram" | "dots">("line");
  const [color, setColor] = useState("#0ea5e9");
  const [guidesText, setGuidesText] = useState("");
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Assistant state
  const [asstType, setAsstType] = useState("ema");
  const [asstSource, setAsstSource] = useState("close");
  const [asstPeriod, setAsstPeriod] = useState(9);
  const [asstMult, setAsstMult] = useState(2);

  useEffect(() => {
    if (!isOpen) return;
    setSubmitError(null);
    if (initialIndicator) {
      setMode("formula");
      setName(initialIndicator.name);
      setFormula(initialIndicator.formula);
      setPane(initialIndicator.pane);
      setSeriesType(initialIndicator.series_type);
      setColor(initialIndicator.color);
      setGuidesText((initialIndicator.guide_lines || []).map(g => g.value).join(", "));
    } else {
      setMode("formula");
      setName("Momentum EMA 12/26");
      setFormula("ema(close, 12) - ema(close, 26)");
      setPane("oscillator");
      setSeriesType("histogram");
      setColor("#3b82f6");
      setGuidesText("0");
    }
  }, [isOpen, initialIndicator]);

  function applyAssistant(nextType = asstType, nextSrc = asstSource, nextPeriod = asstPeriod, nextMult = asstMult) {
    const p = Math.max(1, Math.min(500, Math.round(nextPeriod || 14)));
    const m = Number.isFinite(nextMult) ? nextMult : 2;
    const def = ASSISTANT_TYPES.find(t => t.id === nextType) || ASSISTANT_TYPES[0];
    let nextFormula = `ema(${nextSrc}, ${p})`;
    let nextName = `${def.id.toUpperCase()} ${p}`;
    let nextGuides = "";

    if (nextType === "sma") {
      nextFormula = `sma(${nextSrc}, ${p})`;
      nextName = `SMA ${p}`;
    } else if (nextType === "wma") {
      nextFormula = `wma(${nextSrc}, ${p})`;
      nextName = `WMA ${p}`;
    } else if (nextType === "rsi") {
      nextFormula = `rsi(${nextSrc}, ${p})`;
      nextName = `RSI ${p}`;
      nextGuides = "70, 30";
    } else if (nextType === "roc") {
      nextFormula = `roc(${nextSrc}, ${p})`;
      nextName = `ROC ${p}`;
      nextGuides = "0";
    } else if (nextType === "keltner_up") {
      nextFormula = `ema(${nextSrc}, ${p}) + ${m} * atr(14)`;
      nextName = `Keltner + (${p}, ${m})`;
    } else if (nextType === "keltner_dn") {
      nextFormula = `ema(${nextSrc}, ${p}) - ${m} * atr(14)`;
      nextName = `Keltner - (${p}, ${m})`;
    } else if (nextType === "dist_sma") {
      nextFormula = `((${nextSrc} - sma(${nextSrc}, ${p})) / sma(${nextSrc}, ${p})) * 100`;
      nextName = `Écart SMA ${p} (%)`;
      nextGuides = "0";
    }

    setFormula(nextFormula);
    setName(nextName);
    setPane(def.pane);
    setGuidesText(nextGuides);
  }

  const validation = useMemo(() => validateCustomFormula(formula, bars), [formula, bars]);
  const selectedAsstMeta = ASSISTANT_TYPES.find(t => t.id === asstType);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setSubmitError("Donnez un nom à votre indicateur.");
      return;
    }
    if (!validation.ok) {
      setSubmitError(validation.error);
      return;
    }
    setSaving(true);
    setSubmitError(null);
    try {
      await onSave({
        id: initialIndicator?.id,
        name: name.trim(),
        formula: formula.trim(),
        pane,
        series_type: seriesType,
        color,
        guide_lines: parseGuideLinesInput(guidesText),
        enabled_by_default: true,
      });
      onClose();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Erreur lors de l'enregistrement.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="finance-submodal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="finance-submodal-card" onClick={e => e.stopPropagation()}>
        <div className="finance-submodal-header">
          <div className="finance-submodal-title">
            <Sparkles size={17} className="text-emerald" />
            <div>
              <h3>{initialIndicator ? "Modifier l'indicateur personnalisé" : "Créer un indicateur TradingView"}</h3>
              <p>Formule Pine Express ou assistant paramétrique — sauvegardé dans votre profil</p>
            </div>
          </div>
          <button type="button" className="modal-close-btn" onClick={onClose} aria-label="Fermer">
            <X size={16} />
          </button>
        </div>

        <div className="finance-submodal-mode-tabs">
          <button
            type="button"
            className={`finance-tf-btn ${mode === "formula" ? "active" : ""}`}
            onClick={() => setMode("formula")}
          >
            <Code2 size={13} /> Éditeur de formule (TradingView)
          </button>
          <button
            type="button"
            className={`finance-tf-btn ${mode === "assistant" ? "active" : ""}`}
            onClick={() => {
              setMode("assistant");
              applyAssistant();
            }}
          >
            <Sliders size={13} /> Assistant rapide
          </button>
        </div>

        <form className="finance-submodal-form" onSubmit={handleSubmit}>
          {mode === "assistant" && (
            <div className="finance-assistant-grid">
              <label>
                <span>Indicateur de base</span>
                <select
                  value={asstType}
                  onChange={e => {
                    const nextType = e.target.value;
                    const meta = ASSISTANT_TYPES.find(t => t.id === nextType);
                    const nextPeriod = meta?.defaultPeriod ?? asstPeriod;
                    setAsstType(nextType);
                    setAsstPeriod(nextPeriod);
                    applyAssistant(nextType, asstSource, nextPeriod, asstMult);
                  }}
                >
                  {ASSISTANT_TYPES.map(t => (
                    <option key={t.id} value={t.id}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>

              <label>
                <span>Source de prix</span>
                <select
                  value={asstSource}
                  onChange={e => {
                    setAsstSource(e.target.value);
                    applyAssistant(asstType, e.target.value, asstPeriod, asstMult);
                  }}
                >
                  <option value="close">Close (Clôture)</option>
                  <option value="hlc3">HLC/3 (Prix typique)</option>
                  <option value="hl2">HL/2 (Médian)</option>
                  <option value="ohlc4">OHLC/4</option>
                  <option value="open">Open</option>
                </select>
              </label>

              <label>
                <span>Période</span>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={asstPeriod}
                  onChange={e => {
                    const val = Number(e.target.value) || 1;
                    setAsstPeriod(val);
                    applyAssistant(asstType, asstSource, val, asstMult);
                  }}
                />
              </label>

              {selectedAsstMeta?.hasMult && (
                <label>
                  <span>Multiplicateur ATR</span>
                  <input
                    type="number"
                    step="0.1"
                    min={0.1}
                    max={10}
                    value={asstMult}
                    onChange={e => {
                      const val = Number(e.target.value) || 1;
                      setAsstMult(val);
                      applyAssistant(asstType, asstSource, asstPeriod, val);
                    }}
                  />
                </label>
              )}
            </div>
          )}

          <div className="finance-presets-bar">
            <span>Modèles :</span>
            {CUSTOM_INDICATOR_PRESETS.map(p => (
              <button
                key={p.id}
                type="button"
                className="finance-chip"
                title={p.description}
                onClick={() => {
                  setName(p.name);
                  setFormula(p.formula);
                  setPane(p.pane);
                  setSeriesType(p.series_type);
                  setColor(p.color);
                  setGuidesText(p.guide_lines.map(g => g.value).join(", "));
                }}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="finance-form-row-2">
            <label>
              <span>Nom affiché sur le graphique</span>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Ex. Keltner Sup, Spread EMA 12/26..."
                maxLength={100}
                required
              />
            </label>

            <label>
              <span>Emplacement</span>
              <select value={pane} onChange={e => setPane(e.target.value as "overlay" | "oscillator")}>
                <option value="overlay">Sur la courbe du cours (Overlay)</option>
                <option value="oscillator">Sous-panneau dédié (Oscillateur)</option>
              </select>
            </label>
          </div>

          <label className="finance-formula-field">
            <span>Formule (syntaxe Pine Express — fonctions composables, insensible à la casse)</span>
            <textarea
              rows={3}
              value={formula}
              onChange={e => setFormula(e.target.value)}
              placeholder="Ex. ema(rsi(close, 14), 9) ou ema(close, 12) - ema(close, 26)"
              spellCheck={false}
              required
            />
          </label>

          <div className="finance-presets-bar">
            <span>Insérer :</span>
            {FORMULA_SNIPPETS.map(snippet => (
              <button
                key={snippet}
                type="button"
                className="finance-chip is-mono"
                onClick={() => setFormula(prev => (prev.trim() ? `${prev.trim()} ${snippet}` : snippet))}
              >
                + {snippet}
              </button>
            ))}
          </div>

          <div className={`finance-formula-status ${validation.ok ? "is-ok" : "is-err"}`}>
            {validation.ok ? (
              <span>
                <Check size={13} /> Formule valide · Dernières valeurs calculées :{" "}
                <strong>
                  {validation.lastValues.length > 0
                    ? validation.lastValues.map(v => v.toFixed(2)).join(" → ")
                    : "en attente de barres"}
                </strong>
              </span>
            ) : (
              <span>⚠️ {validation.error}</span>
            )}
          </div>

          <div className="finance-form-row-3">
            <label>
              <span>Style de tracé</span>
              <select
                value={seriesType}
                onChange={e => setSeriesType(e.target.value as "line" | "histogram" | "dots")}
              >
                <option value="line">Ligne continue</option>
                <option value="histogram">Histogramme (barres)</option>
                <option value="dots">Points (marqueurs)</option>
              </select>
            </label>

            <label>
              <span>Seuils horizontaux (optionnel)</span>
              <input
                type="text"
                value={guidesText}
                onChange={e => setGuidesText(e.target.value)}
                placeholder="Ex. 70, 30 ou 0"
              />
            </label>

            <label>
              <span>Couleur</span>
              <div className="finance-color-swatches">
                {COLOR_SWATCHES.map(c => (
                  <button
                    key={c}
                    type="button"
                    className={`finance-color-dot ${color.toLowerCase() === c ? "active" : ""}`}
                    style={{ background: c }}
                    onClick={() => setColor(c)}
                    aria-label={`Couleur ${c}`}
                  />
                ))}
                <input
                  type="color"
                  value={color}
                  onChange={e => setColor(e.target.value)}
                  aria-label="Couleur personnalisée"
                />
              </div>
            </label>
          </div>

          <div className="finance-formula-help">
            Séries : <code>open</code>, <code>high</code>, <code>low</code>, <code>close</code>, <code>volume</code>,{" "}
            <code>hl2</code>, <code>hlc3</code>, <code>ohlc4</code> · Fonctions : <code>sma</code>, <code>ema</code>,{" "}
            <code>wma</code>, <code>rsi</code>, <code>roc</code>, <code>atr</code>, <code>cci</code>, <code>willr</code>,{" "}
            <code>adx</code>, <code>obv</code>, <code>vwap</code>, <code>sar</code>, <code>boll_upper/mid/lower</code>,{" "}
            <code>macd_line/signal/hist</code>, <code>stoch_k/d</code>, <code>stdev</code>, <code>highest</code>,{" "}
            <code>lowest</code>, <code>shift</code> / <code>close[1]</code>, <code>iff(cond, a, b)</code>.
          </div>

          {submitError && <div className="finance-modal-error">⚠️ {submitError}</div>}

          <div className="finance-submodal-actions">
            <button type="button" className="finance-copy-btn" onClick={onClose} disabled={saving}>
              Annuler
            </button>
            <button type="submit" className="finance-insert-btn" disabled={saving || !validation.ok}>
              {saving ? <LoaderCircle size={14} className="spin" /> : <Plus size={14} />}
              <span>{initialIndicator ? "Mettre à jour" : "Ajouter au graphique"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
