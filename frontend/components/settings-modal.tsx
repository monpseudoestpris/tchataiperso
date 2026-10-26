"use client";

import { useEffect, useState } from "react";
import {
  AlertCircle,
  Brain,
  Check,
  CheckCircle2,
  Coins,
  Cpu,
  Info,
  LoaderCircle,
  RotateCcw,
  Save,
  Settings,
  Sparkles,
  Trash2,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { api, errorMessage, type AuthUser, type PromptPreset, type UserSettings } from "@/lib/api";

type SettingsModalProps = {
  currentUser: AuthUser;
  isOpen: boolean;
  onClose: () => void;
  onSettingsUpdated?: (updated: { system_prompt: string; prompt_cache_enabled: boolean; auto_memory_enabled: boolean }) => void;
};

export function SettingsModal({
  currentUser,
  isOpen,
  onClose,
  onSettingsUpdated,
}: SettingsModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [systemPrompt, setSystemPrompt] = useState("");
  const [promptCacheEnabled, setPromptCacheEnabled] = useState(true);
  const [autoMemoryEnabled, setAutoMemoryEnabled] = useState(true);
  const [defaultSystemPrompt, setDefaultSystemPrompt] = useState("");
  const [presets, setPresets] = useState<PromptPreset[]>([]);

  useEffect(() => {
    if (!isOpen) return;

    let active = true;
    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    api<UserSettings>("/settings")
      .then((data) => {
        if (!active) return;
        setSystemPrompt(data.system_prompt || "");
        setPromptCacheEnabled(data.prompt_cache_enabled ?? true);
        setAutoMemoryEnabled(data.auto_memory_enabled ?? true);
        setDefaultSystemPrompt(data.default_system_prompt || "");
        setPresets(data.prompt_presets || []);
      })
      .catch((err) => {
        if (!active) return;
        // Fallback to current user data if endpoint fails
        setSystemPrompt(currentUser.system_prompt || "");
        setPromptCacheEnabled(currentUser.prompt_cache_enabled ?? true);
        setAutoMemoryEnabled(currentUser.auto_memory_enabled ?? true);
        setError(`Impossible de charger les paramètres : ${errorMessage(err)}`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, currentUser]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen && !saving) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, saving, onClose]);

  if (!isOpen) return null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const res = await api<UserSettings>("/settings", {
        method: "PATCH",
        body: JSON.stringify({
          system_prompt: systemPrompt,
          prompt_cache_enabled: promptCacheEnabled,
          auto_memory_enabled: autoMemoryEnabled,
        }),
      });

      setSystemPrompt(res.system_prompt || "");
      setPromptCacheEnabled(res.prompt_cache_enabled ?? true);
      setAutoMemoryEnabled(res.auto_memory_enabled ?? true);
      setSuccessMessage("Paramètres enregistrés avec succès !");

      if (onSettingsUpdated) {
        onSettingsUpdated({
          system_prompt: res.system_prompt || "",
          prompt_cache_enabled: res.prompt_cache_enabled ?? true,
          auto_memory_enabled: res.auto_memory_enabled ?? true,
        });
      }

      setTimeout(() => {
        setSuccessMessage(null);
      }, 3500);
    } catch (err) {
      setError(`Échec de l'enregistrement : ${errorMessage(err)}`);
    } finally {
      setSaving(false);
    }
  }

  function applyPreset(preset: PromptPreset) {
    setSystemPrompt(preset.prompt);
    setSuccessMessage(`Preset « ${preset.title} » appliqué.`);
    setTimeout(() => setSuccessMessage(null), 2500);
  }

  function handleResetToDefault() {
    setSystemPrompt(defaultSystemPrompt || "");
    setSuccessMessage("Prompt général réinitialisé aux valeurs standard de l'application.");
    setTimeout(() => setSuccessMessage(null), 2500);
  }

  const approxTokens = Math.max(0, Math.round(systemPrompt.length / 4));

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
      <div className="settings-modal-container" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <header className="settings-modal-header">
          <div className="settings-modal-header-left">
            <div className="settings-modal-badge-icon">
              <Settings size={22} />
            </div>
            <div>
              <div className="settings-modal-title-row">
                <h2 id="settings-modal-title">Paramètres & Personnalisation</h2>
                <span className="settings-user-pill">Compte : {currentUser.username}</span>
              </div>
              <p>Configurez votre prompt général permanent et l’optimisation de coût par cache de prompt.</p>
            </div>
          </div>
          <button
            type="button"
            className="settings-modal-close"
            onClick={onClose}
            aria-label="Fermer la modale"
            disabled={saving}
          >
            <X size={19} />
          </button>
        </header>

        {/* Content body */}
        <div className="settings-modal-body">
          {loading ? (
            <div className="settings-loading-state">
              <LoaderCircle size={28} className="spin" />
              <span>Chargement de vos préférences…</span>
            </div>
          ) : (
            <>
              {error && (
                <div className="settings-alert-banner error" role="alert">
                  <AlertCircle size={18} />
                  <span>{error}</span>
                </div>
              )}

              {successMessage && (
                <div className="settings-alert-banner success" role="status">
                  <CheckCircle2 size={18} />
                  <span>{successMessage}</span>
                </div>
              )}

              {/* SECTION 1 : Prompt Général Modifiable */}
              <section className="settings-section">
                <div className="settings-section-header">
                  <div className="settings-section-title-wrap">
                    <span className="settings-section-icon"><Wand2 size={18} /></span>
                    <div>
                      <h3>Prompt Général Personnalisé (Instructions Système)</h3>
                      <p>
                        Ces directives permanentes sont transmises au modèle au début de <strong>tous vos messages et conversations</strong>.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Presets rapides */}
                {presets.length > 0 && (
                  <div className="settings-presets-container">
                    <div className="settings-presets-label">
                      <Sparkles size={13} />
                      <span>Modèles de prompts rapides :</span>
                    </div>
                    <div className="settings-presets-grid">
                      {presets.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          className="settings-preset-chip"
                          onClick={() => applyPreset(preset)}
                          title={preset.description}
                        >
                          <strong>{preset.title}</strong>
                          <span className="preset-snippet">{preset.prompt.slice(0, 48)}…</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Zone de saisie du prompt */}
                <div className="settings-prompt-editor-wrap">
                  <textarea
                    id="user-system-prompt"
                    className="settings-prompt-textarea"
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    placeholder="Exemple : Sois direct et concis. Réponds sans formules superflues. Quand tu donnes du code, commente les points clés et privilégie TypeScript et Python..."
                    rows={6}
                    maxLength={12000}
                  />

                  <div className="settings-prompt-footer">
                    <div className="settings-prompt-stats">
                      <span>{systemPrompt.length} / 12 000 caractères</span>
                      <span className="stat-separator">•</span>
                      <span>~{approxTokens} tokens</span>
                    </div>

                    <div className="settings-prompt-actions">
                      {systemPrompt.trim() && (
                        <button
                          type="button"
                          className="settings-link-btn danger"
                          onClick={() => setSystemPrompt("")}
                          title="Effacer tout le prompt personnalisé"
                        >
                          <Trash2 size={13} />
                          <span>Effacer</span>
                        </button>
                      )}
                      <button
                        type="button"
                        className="settings-link-btn"
                        onClick={handleResetToDefault}
                        title="Réinitialiser pour utiliser uniquement les règles de base cLAIr"
                      >
                        <RotateCcw size={13} />
                        <span>Prompt par défaut</span>
                      </button>
                    </div>
                  </div>
                </div>
              </section>

              {/* SECTION 2 : Gestion du Cache de Prompt (Prompt Caching) */}
              <section className="settings-section">
                <div className="settings-section-header">
                  <div className="settings-section-title-wrap">
                    <span className="settings-section-icon cache-accent"><Zap size={18} /></span>
                    <div>
                      <div className="settings-title-with-badge">
                        <h3>Optimisation du Cache de Prompt (Prompt Caching)</h3>
                        <span className={`settings-cache-badge ${promptCacheEnabled ? "is-active" : "is-disabled"}`}>
                          {promptCacheEnabled ? "✨ Actif · Économies 50% à 90%" : "⏸️ Désactivé"}
                        </span>
                      </div>
                      <p>
                        Évite de repayer plusieurs fois pour les mêmes instructions de début de message sur les modèles compatibles.
                      </p>
                    </div>
                  </div>

                  {/* Toggle Switch */}
                  <label className="settings-switch" title={promptCacheEnabled ? "Désactiver le cache de prompt" : "Activer le cache de prompt"}>
                    <input
                      type="checkbox"
                      checked={promptCacheEnabled}
                      onChange={(e) => setPromptCacheEnabled(e.target.checked)}
                    />
                    <span className="settings-slider" />
                  </label>
                </div>

                {/* Encart explicatif haute valeur pédagogique */}
                <div className="settings-cache-explainer">
                  <div className="cache-explainer-badge">
                    <Coins size={15} />
                    <span>Fonctionnement & Économies Réelles</span>
                  </div>
                  <div className="cache-explainer-grid">
                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Cpu size={14} />
                        <strong>Modèles compatibles</strong>
                      </div>
                      <p>
                        <strong>Anthropic Claude</strong> (Claude 3.5 Sonnet, Haiku, Opus), <strong>OpenAI</strong> (GPT-4o, o-series), <strong>DeepSeek</strong> (V3, R1) et <strong>Gemini</strong> mettent en cache les préfixes identiques.
                      </p>
                    </div>

                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Coins size={14} />
                        <strong>Jusqu&apos;à 90% d&apos;économies</strong>
                      </div>
                      <p>
                        Lorsque le prompt général et l&apos;historique récent restent fixes, le fournisseur IA réutilise les tokens déjà encodés au lieu de les recalculer. La facturation des tokens en cache est réduite de <strong>50% à 90%</strong>.
                      </p>
                    </div>

                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Zap size={14} />
                        <strong>Accélération des réponses</strong>
                      </div>
                      <p>
                        Le temps de premier token (TTFT) est diminué car le modèle saute le traitement initial des instructions et démarre immédiatement la génération.
                      </p>
                    </div>

                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Info size={14} />
                        <strong>Gestion automatique par cLAIr</strong>
                      </div>
                      <p>
                        cLAIr structure automatiquement le préfixe immuable et injecte les balises de cache éphémère (<code>cache_control: ephemeral</code>) pour garantir la persistance du cache sur OpenRouter et Anthropic.
                      </p>
                    </div>
                  </div>
                </div>
              </section>

              {/* SECTION 3 : Mémoire Long Terme & Agent de Souvenirs */}
              <section className="settings-section">
                <div className="settings-section-header">
                  <div className="settings-section-title-wrap">
                    <div className="settings-icon-badge" style={{ background: "rgba(16, 185, 129, 0.12)", color: "#10b981" }}>
                      <Brain size={18} />
                    </div>
                    <div>
                      <h3 className="settings-section-title">Mémoire Long Terme & Agent de Souvenirs</h3>
                      <p className="settings-section-desc">
                        L&apos;agent retient automatiquement vos préférences durables au fil des échanges ou sur demande explicite (<em>« note en mémoire que... »</em>).
                      </p>
                    </div>
                  </div>

                  {/* Badge d'état */}
                  <span className={`settings-status-badge ${autoMemoryEnabled ? "badge-active" : "badge-inactive"}`}>
                    {autoMemoryEnabled ? (
                      <>
                        <Sparkles size={13} />
                        <span>✨ Actif · Capture autonome &amp; explicite</span>
                      </>
                    ) : (
                      <>
                        <Info size={13} />
                        <span>✋ Manuel · Sur demande uniquement</span>
                      </>
                    )}
                  </span>
                </div>

                <div className="settings-toggle-card">
                  <div className="toggle-card-info">
                    <strong>Détection autonome des souvenirs par l&apos;IA</strong>
                    <p>
                      Quand cette option est active, l&apos;agent décide quoi retenir automatiquement (identité, stack, habitudes, contraintes).
                      Même désactivée, vos demandes explicites (<em>« note en mémoire que... »</em>, <em>« retiens que... »</em>) sont toujours prises en compte.
                    </p>
                  </div>

                  {/* Toggle Switch */}
                  <label className="settings-switch" title={autoMemoryEnabled ? "Désactiver la capture autonome" : "Activer la capture autonome"}>
                    <input
                      type="checkbox"
                      checked={autoMemoryEnabled}
                      onChange={(e) => setAutoMemoryEnabled(e.target.checked)}
                    />
                    <span className="settings-slider" />
                  </label>
                </div>

                <div className="settings-cache-explainer">
                  <div className="cache-explainer-badge" style={{ background: "rgba(16, 185, 129, 0.15)", color: "#059669" }}>
                    <Brain size={15} />
                    <span>Comment fonctionne la mémoire ?</span>
                  </div>
                  <div className="cache-explainer-grid">
                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Sparkles size={14} />
                        <strong>En tâche de fond (Autonome)</strong>
                      </div>
                      <p>
                        L&apos;agent extrait les faits clés durables (votre métier, vos langages de prédilection, votre ville, vos objectifs de long terme) sans jamais polluer avec du bruit passager.
                      </p>
                    </div>

                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Check size={14} />
                        <strong>Sur commande (Explicite)</strong>
                      </div>
                      <p>
                        Dites simplement <em>« note en mémoire que j&apos;habite à Lyon »</em> ou <em>« souviens-toi que je code en Rust »</em>. L&apos;IA enregistre le fait instantanément.
                      </p>
                    </div>

                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Trash2 size={14} />
                        <strong>Oublier ou supprimer</strong>
                      </div>
                      <p>
                        Vous gardez le contrôle total : vous pouvez supprimer n&apos;importe quel souvenir dans le panneau <strong>Mémoire</strong> ou dire <em>« oublie que... »</em> directement dans le tchat.
                      </p>
                    </div>

                    <div className="cache-explainer-item">
                      <div className="explainer-item-header">
                        <Info size={14} />
                        <strong>Injection contextuelle</strong>
                      </div>
                      <p>
                        Vos souvenirs sont injectés de manière concise dans le contexte de toutes vos futures conversations pour des réponses parfaitement personnalisées.
                      </p>
                    </div>
                  </div>
                </div>
              </section>
            </>
          )}
        </div>

        {/* Footer actions */}
        <footer className="settings-modal-footer">
          <button
            type="button"
            className="settings-cancel-btn"
            onClick={onClose}
            disabled={saving}
          >
            Fermer
          </button>

          <button
            type="button"
            className="settings-save-btn"
            onClick={() => void handleSave()}
            disabled={loading || saving}
          >
            {saving ? (
              <>
                <LoaderCircle size={15} className="spin" />
                <span>Enregistrement…</span>
              </>
            ) : (
              <>
                <Save size={15} />
                <span>Enregistrer les modifications</span>
              </>
            )}
          </button>
        </footer>
      </div>
    </div>
  );
}
