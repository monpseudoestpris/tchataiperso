"use client";

import {
  Bot,
  Check,
  Code2,
  Copy,
  Globe2,
  LoaderCircle,
  Play,
  Plus,
  Puzzle,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { executePageBrick, errorMessage, type Model } from "@/lib/api";
import {
  createBrickFromTemplate,
  generateBrickUsageSnippet,
  PREMADE_BRICK_TEMPLATES,
  slugifyBrickId,
  type BrickInputField,
  type BrickInputType,
  type BrickOutputField,
  type BrickOutputFieldType,
  type BrickOutputFormat,
  type BrickWidgetStyle,
  type PageBrick,
} from "@/lib/canvas-bricks";
import styles from "./canvas-bricks-modal.module.css";

export type CanvasBricksModalProps = {
  isOpen: boolean;
  bricks: PageBrick[];
  models?: Model[];
  currentModel?: string;
  pageId?: string | null;
  onSave: (nextBricks: PageBrick[]) => Promise<void> | void;
  onWireBrickWithAI?: (brick: PageBrick, currentBricks: PageBrick[]) => void;
  onInsertTurnkeyWidget?: (brick: PageBrick, currentBricks: PageBrick[]) => void;
  onClose: () => void;
};

export function CanvasBricksModal(props: CanvasBricksModalProps) {
  if (!props.isOpen) return null;
  return <CanvasBricksModalContent {...props} />;
}

function CanvasBricksModalContent({
  bricks,
  models = [],
  currentModel,
  pageId,
  onSave,
  onWireBrickWithAI,
  onInsertTurnkeyWidget,
  onClose,
}: CanvasBricksModalProps) {
  const [draftBricks, setDraftBricks] = useState<PageBrick[]>(
    () => JSON.parse(JSON.stringify(bricks || [])) as PageBrick[],
  );
  const [selectedId, setSelectedId] = useState<string | null>(
    () => (bricks && bricks[0]?.id) ?? null,
  );
  const [templateCat, setTemplateCat] = useState<string>("Toutes");
  const [saving, setSaving] = useState(false);
  const [copiedSnippet, setCopiedSnippet] = useState(false);

  // Live sandbox testing state keyed by brickId
  const [testInputsByBrick, setTestInputsByBrick] = useState<Record<string, Record<string, string>>>({});
  const [testing, setTesting] = useState(false);
  const [testOutput, setTestOutput] = useState<string | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const activeBrick = useMemo(
    () => draftBricks.find(b => b.id === selectedId) ?? draftBricks[0] ?? null,
    [draftBricks, selectedId],
  );

  const testInputs = useMemo(() => {
    if (!activeBrick) return {};
    const existing = testInputsByBrick[activeBrick.id] ?? {};
    const merged: Record<string, string> = {};
    for (const inp of activeBrick.inputs) {
      merged[inp.key] = existing[inp.key] ?? inp.default_value ?? "";
    }
    return merged;
  }, [activeBrick, testInputsByBrick]);

  function selectBrick(id: string) {
    setSelectedId(id);
    setTestOutput(null);
    setTestError(null);
  }

  function addFromTemplate(templateId: string) {
    const tpl = PREMADE_BRICK_TEMPLATES.find(t => t.templateId === templateId);
    if (!tpl) return;
    const next = createBrickFromTemplate(tpl, draftBricks);
    setDraftBricks(old => [...old, next]);
    selectBrick(next.id);
  }

  const templateCategories = useMemo(
    () => ["Toutes", ...Array.from(new Set(PREMADE_BRICK_TEMPLATES.map(t => t.category)))],
    [],
  );

  const visibleTemplates = useMemo(
    () =>
      templateCat === "Toutes"
        ? PREMADE_BRICK_TEMPLATES
        : PREMADE_BRICK_TEMPLATES.filter(t => t.category === templateCat),
    [templateCat],
  );

  function updateActiveBrick(updater: (brick: PageBrick) => PageBrick) {
    if (!activeBrick) return;
    setDraftBricks(old => old.map(b => (b.id === activeBrick.id ? updater(b) : b)));
  }

  function removeBrick(id: string) {
    setDraftBricks(old => {
      const remaining = old.filter(b => b.id !== id);
      if (selectedId === id) {
        setSelectedId(remaining[0]?.id ?? null);
      }
      return remaining;
    });
  }

  function addInputField() {
    updateActiveBrick(b => {
      const idx = b.inputs.length + 1;
      const newField: BrickInputField = {
        key: `entree_${idx}`,
        label: `Entrée ${idx}`,
        type: "text",
        required: true,
        placeholder: "",
        default_value: "",
        options: [],
      };
      return { ...b, inputs: [...b.inputs, newField] };
    });
  }

  function updateInputField(idx: number, patch: Partial<BrickInputField>) {
    updateActiveBrick(b => ({
      ...b,
      inputs: b.inputs.map((inp, i) => (i === idx ? { ...inp, ...patch } : inp)),
    }));
  }

  function removeInputField(idx: number) {
    updateActiveBrick(b => ({
      ...b,
      inputs: b.inputs.filter((_, i) => i !== idx),
    }));
  }

  function addOutputField() {
    updateActiveBrick(b => {
      const idx = b.output_spec.fields.length + 1;
      const nextField: BrickOutputField = {
        key: `champ_${idx}`,
        type: "string",
        description: "",
      };
      return {
        ...b,
        output_spec: {
          ...b.output_spec,
          fields: [...b.output_spec.fields, nextField],
        },
      };
    });
  }

  function updateOutputField(idx: number, patch: Partial<BrickOutputField>) {
    updateActiveBrick(b => ({
      ...b,
      output_spec: {
        ...b.output_spec,
        fields: b.output_spec.fields.map((f, i) => (i === idx ? { ...f, ...patch } : f)),
      },
    }));
  }

  function removeOutputField(idx: number) {
    updateActiveBrick(b => ({
      ...b,
      output_spec: {
        ...b.output_spec,
        fields: b.output_spec.fields.filter((_, i) => i !== idx),
      },
    }));
  }

  async function handleCopySnippet() {
    if (!activeBrick) return;
    try {
      await navigator.clipboard.writeText(generateBrickUsageSnippet(activeBrick));
      setCopiedSnippet(true);
      setTimeout(() => setCopiedSnippet(false), 1800);
    } catch {
      setCopiedSnippet(false);
    }
  }

  async function handleRunTest() {
    if (!activeBrick) return;
    setTesting(true);
    setTestError(null);
    setTestOutput(null);
    try {
      const res = await executePageBrick({
        brick: activeBrick,
        page_id: pageId ?? undefined,
        inputs: testInputs,
        model: activeBrick.model === "auto" ? currentModel : activeBrick.model,
      });
      const formatted =
        typeof res.output === "string"
          ? res.output
          : JSON.stringify(res.output, null, 2);
      setTestOutput(`[Modèle : ${res.model_used} · Format : ${res.format}]\n\n${formatted}`);
    } catch (err) {
      setTestError(errorMessage(err));
    } finally {
      setTesting(false);
    }
  }

  async function handleConfirmSave() {
    setSaving(true);
    try {
      await onSave(draftBricks);
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className={styles.backdrop}
      onClick={e => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="canvas-bricks-title"
    >
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <Puzzle size={19} />
            </div>
            <div>
              <h2 id="canvas-bricks-title" className={styles.headerTitle}>
                Briques Préfaites & Agents IA connectés
              </h2>
              <p className={styles.headerSub}>
                Configurez un agent IA (modèle, prompt, entrées, sorties attendues) utilisable sans clé API dans votre application.
              </p>
            </div>
          </div>
          <div className={styles.headerActions}>
            <button type="button" className={styles.btn} onClick={onClose} aria-label="Fermer">
              <X size={16} />
            </button>
          </div>
        </header>

        <div className={styles.body}>
          {/* Left Sidebar: Attached bricks + Premade templates */}
          <aside className={styles.sidebar}>
            <div>
              <h3 className={styles.sideTitle}>
                Briques de l&apos;app ({draftBricks.length})
              </h3>
              {draftBricks.length === 0 ? (
                <p style={{ fontSize: "0.76rem", color: "#64748b", margin: "0 0 0.5rem" }}>
                  Aucune brique attachée. Ajoutez un modèle ci-dessous.
                </p>
              ) : (
                <div className={styles.brickList}>
                  {draftBricks.map(b => {
                    const isSelected = activeBrick?.id === b.id;
                    return (
                      <div
                        key={b.id}
                        className={`${styles.brickCard} ${isSelected ? styles.active : ""}`}
                        onClick={() => selectBrick(b.id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={e => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            selectBrick(b.id);
                          }
                        }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: "0.82rem", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            🤖 {b.name}
                          </div>
                          <div className={styles.brickCardMeta}>
                            <code>{b.id}</code>
                            <span>·</span>
                            <span>{b.output_spec.format}</span>
                          </div>
                        </div>
                        <button
                          type="button"
                          className={`${styles.btn} ${styles.btnDanger}`}
                          style={{ padding: "0.25rem 0.4rem" }}
                          title="Retirer cette brique"
                          onClick={e => {
                            e.stopPropagation();
                            removeBrick(b.id);
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div>
              <h3 className={styles.sideTitle}>
                Catalogue prêt à l&apos;emploi ({PREMADE_BRICK_TEMPLATES.length})
              </h3>
              <div className={styles.catFilterRow}>
                {templateCategories.map(cat => (
                  <button
                    key={cat}
                    type="button"
                    className={`${styles.catChip} ${templateCat === cat ? styles.catChipActive : ""}`}
                    onClick={() => setTemplateCat(cat)}
                  >
                    {cat}
                  </button>
                ))}
              </div>
              <div className={styles.templateGrid}>
                {visibleTemplates.map(tpl => (
                  <button
                    key={tpl.templateId}
                    type="button"
                    className={styles.templateBtn}
                    onClick={() => addFromTemplate(tpl.templateId)}
                  >
                    <span style={{ fontSize: "1.1rem", lineHeight: 1.2 }}>{tpl.icon}</span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: "0.78rem", fontWeight: 700 }}>
                        + {tpl.brick.name}
                      </div>
                      <div style={{ fontSize: "0.69rem", color: "#64748b", lineHeight: 1.25 }}>
                        {tpl.tagline}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {/* Right Editor */}
          <section className={styles.editor}>
            {!activeBrick ? (
              <div className={styles.emptyEditor}>
                <Bot size={36} strokeWidth={1.5} color="#0284c7" />
                <strong style={{ fontSize: "1rem", color: "inherit" }}>
                  Adjoignez une brique prête à l&apos;emploi à votre application
                </strong>
                <p style={{ maxWidth: 480, fontSize: "0.84rem", margin: 0 }}>
                  Choisissez parmi les {PREMADE_BRICK_TEMPLATES.length} briques toutes faites à gauche :{" "}
                  <strong>Bot IA Conversationnel</strong>, <strong>Quiz QCM</strong>,{" "}
                  <strong>Réécriture</strong>, <strong>Traducteur</strong>, <strong>Coach /20</strong>,{" "}
                  <strong>Extracteur JSON</strong>, <strong>Veille Web</strong>…
                </p>
                <div style={{ display: "flex", gap: "0.55rem", flexWrap: "wrap", justifyContent: "center" }}>
                  <button
                    type="button"
                    className={`${styles.btn} ${styles.btnPrimary}`}
                    onClick={() => addFromTemplate("bot_ia_chat")}
                  >
                    <Plus size={15} />
                    <span>+ Bot IA Conversationnel</span>
                  </button>
                  <button
                    type="button"
                    className={styles.btn}
                    onClick={() => addFromTemplate("generateur_quiz")}
                  >
                    <Plus size={15} />
                    <span>+ Quiz QCM Interactif</span>
                  </button>
                  <button
                    type="button"
                    className={styles.btn}
                    onClick={() => addFromTemplate("extracteur_json")}
                  >
                    <Plus size={15} />
                    <span>+ Extracteur JSON</span>
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* 1. Identity & Model */}
                <div className={styles.sectionBox}>
                  <div className={styles.sectionHeader}>
                    <h3 className={styles.sectionHeading}>
                      <Bot size={15} color="#0284c7" />
                      1. Identité & Modèle IA
                    </h3>
                    <div style={{ display: "flex", gap: "0.75rem", fontSize: "0.76rem", alignItems: "center", flexWrap: "wrap" }}>
                      <label style={{ display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer" }}>
                        <input
                          type="checkbox"
                          checked={activeBrick.web_search_enabled}
                          onChange={e =>
                            updateActiveBrick(b => ({
                              ...b,
                              type: b.finance_data_enabled
                                ? "finance_eod_agent"
                                : e.target.checked
                                  ? "web_search_agent"
                                  : "ai_agent",
                              web_search_enabled: e.target.checked,
                            }))
                          }
                        />
                        <Globe2 size={13} />
                        <span>Recherche Web SearXNG</span>
                      </label>
                      <label
                        style={{ display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer" }}
                        title="Injecte automatiquement les cotations EODHD, Yahoo Finance, RSI/SMA/MACD et signaux MOAT réels"
                      >
                        <input
                          type="checkbox"
                          checked={Boolean(activeBrick.finance_data_enabled)}
                          onChange={e =>
                            updateActiveBrick(b => ({
                              ...b,
                              type: e.target.checked
                                ? "finance_eod_agent"
                                : b.web_search_enabled
                                  ? "web_search_agent"
                                  : "ai_agent",
                              finance_data_enabled: e.target.checked,
                            }))
                          }
                        />
                        <span>Données Bourse EOD / Yahoo</span>
                      </label>
                      <label
                        style={{ display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer" }}
                        title="Désactivé par défaut : la brique propulse directement l'interface de l'app via window.clair.runBrick(). Cochez uniquement pour ajouter un tiroir flottant en bas à droite."
                      >
                        <input
                          type="checkbox"
                          checked={activeBrick.show_widget}
                          onChange={e =>
                            updateActiveBrick(b => ({ ...b, show_widget: e.target.checked }))
                          }
                        />
                        <span>Bulle flottante de test</span>
                      </label>
                    </div>
                  </div>

                  <div className={styles.grid2}>
                    <div className={styles.field}>
                      <label className={styles.label}>Nom de la brique</label>
                      <input
                        className={styles.input}
                        value={activeBrick.name}
                        onChange={e =>
                          updateActiveBrick(b => ({ ...b, name: e.target.value }))
                        }
                        placeholder="Ex: Coach de rédaction"
                      />
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Identifiant JS (`brickId`)</label>
                      <input
                        className={styles.input}
                        value={activeBrick.id}
                        onChange={e => {
                          const nextId = slugifyBrickId(e.target.value, activeBrick.id);
                          setSelectedId(nextId);
                          updateActiveBrick(b => ({ ...b, id: nextId }));
                        }}
                        placeholder="agent_coach"
                      />
                    </div>
                  </div>

                  <div className={styles.grid2}>
                    <div className={styles.field}>
                      <label className={styles.label}>Modèle IA utilisé</label>
                      <select
                        className={styles.select}
                        value={activeBrick.model || "auto"}
                        onChange={e =>
                          updateActiveBrick(b => ({ ...b, model: e.target.value }))
                        }
                      >
                        <option value="auto">
                          Modèle actif par défaut ({currentModel || "auto"})
                        </option>
                        {models.map(m => (
                          <option key={m.id} value={m.id}>
                            {m.name || m.id}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Description courte</label>
                      <input
                        className={styles.input}
                        value={activeBrick.description}
                        onChange={e =>
                          updateActiveBrick(b => ({ ...b, description: e.target.value }))
                        }
                        placeholder="Ce que fait cette brique dans l'app..."
                      />
                    </div>
                  </div>

                  <div className={styles.grid2}>
                    <div className={styles.field}>
                      <label className={styles.label}>Interface clé-en-main du widget</label>
                      <select
                        className={styles.select}
                        value={activeBrick.widget_style || "auto"}
                        onChange={e =>
                          updateActiveBrick(b => ({
                            ...b,
                            widget_style: e.target.value as BrickWidgetStyle,
                          }))
                        }
                      >
                        <option value="auto">Automatique (selon le schéma)</option>
                        <option value="chatbot">💬 Bot IA Conversationnel (bulles + mémoire)</option>
                        <option value="quiz">🎯 Quiz QCM Interactif (cliquable + score)</option>
                        <option value="rewriter">✍️ Studio Texte (résultat + copie 1 clic)</option>
                        <option value="scorecard">🏆 Carte de Score (note + validation)</option>
                        <option value="cards">🗂️ Cartes & Listes structurées</option>
                      </select>
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>
                        Message d&apos;accueil (pour Bot IA)
                      </label>
                      <input
                        className={styles.input}
                        value={activeBrick.welcome_message || ""}
                        onChange={e =>
                          updateActiveBrick(b => ({ ...b, welcome_message: e.target.value }))
                        }
                        placeholder="Ex: Bonjour ! Posez-moi vos questions."
                      />
                    </div>
                  </div>

                  <div className={styles.field}>
                    <label className={styles.label}>Prompt / Instructions système de l&apos;Agent IA</label>
                    <textarea
                      className={styles.textarea}
                      rows={3}
                      value={activeBrick.system_prompt}
                      onChange={e =>
                        updateActiveBrick(b => ({ ...b, system_prompt: e.target.value }))
                      }
                      placeholder="Décrivez précisément le rôle de l'agent, sa méthode d'analyse et ses contraintes..."
                    />
                  </div>
                </div>

                {/* 2. Inputs */}
                <div className={styles.sectionBox}>
                  <div className={styles.sectionHeader}>
                    <h3 className={styles.sectionHeading}>
                      2. Entrées attendues ({activeBrick.inputs.length})
                    </h3>
                    <button type="button" className={styles.btn} onClick={addInputField}>
                      <Plus size={13} />
                      <span>Ajouter une entrée</span>
                    </button>
                  </div>

                  {activeBrick.inputs.map((inp, idx) => (
                    <div key={idx} className={styles.rowItem}>
                      <input
                        className={styles.input}
                        value={inp.key}
                        onChange={e =>
                          updateInputField(idx, { key: slugifyBrickId(e.target.value, inp.key) })
                        }
                        placeholder="cle_entree"
                        title="Clé JS transmise dans inputs"
                      />
                      <input
                        className={styles.input}
                        value={inp.label}
                        onChange={e => updateInputField(idx, { label: e.target.value })}
                        placeholder="Libellé affiché"
                      />
                      <select
                        className={styles.select}
                        value={inp.type}
                        onChange={e =>
                          updateInputField(idx, { type: e.target.value as BrickInputType })
                        }
                      >
                        <option value="text">Texte court</option>
                        <option value="textarea">Texte long</option>
                        <option value="number">Nombre</option>
                        <option value="select">Liste de choix</option>
                        <option value="json">JSON</option>
                      </select>
                      <button
                        type="button"
                        className={`${styles.btn} ${styles.btnDanger}`}
                        style={{ padding: "0.35rem" }}
                        onClick={() => removeInputField(idx)}
                        title="Supprimer cette entrée"
                      >
                        <Trash2 size={13} />
                      </button>
                      {inp.type === "select" && (
                        <input
                          className={styles.input}
                          style={{ gridColumn: "1 / -1" }}
                          value={inp.options.join(", ")}
                          onChange={e =>
                            updateInputField(idx, {
                              options: e.target.value
                                .split(",")
                                .map(s => s.trim())
                                .filter(Boolean),
                            })
                          }
                          placeholder="Options séparées par des virgules (ex: Débutant, Intermédiaire, Expert)"
                        />
                      )}
                    </div>
                  ))}
                </div>

                {/* 3. Expected Outputs */}
                <div className={styles.sectionBox}>
                  <div className={styles.sectionHeader}>
                    <h3 className={styles.sectionHeading}>
                      3. Sorties attendues
                    </h3>
                    {activeBrick.output_spec.format === "json" && (
                      <button type="button" className={styles.btn} onClick={addOutputField}>
                        <Plus size={13} />
                        <span>Ajouter une clé JSON</span>
                      </button>
                    )}
                  </div>

                  <div className={styles.grid2}>
                    <div className={styles.field}>
                      <label className={styles.label}>Format de sortie</label>
                      <select
                        className={styles.select}
                        value={activeBrick.output_spec.format}
                        onChange={e =>
                          updateActiveBrick(b => ({
                            ...b,
                            output_spec: {
                              ...b.output_spec,
                              format: e.target.value as BrickOutputFormat,
                            },
                          }))
                        }
                      >
                        <option value="markdown">Markdown structuré</option>
                        <option value="json">JSON typé (champs structurés)</option>
                        <option value="list">Liste d&apos;éléments (tableau)</option>
                        <option value="text">Texte brut</option>
                      </select>
                    </div>
                    <div className={styles.field}>
                      <label className={styles.label}>Description de la sortie attendue</label>
                      <input
                        className={styles.input}
                        value={activeBrick.output_spec.description}
                        onChange={e =>
                          updateActiveBrick(b => ({
                            ...b,
                            output_spec: {
                              ...b.output_spec,
                              description: e.target.value,
                            },
                          }))
                        }
                        placeholder="Ex: Diagnostic synthétique + score et plan d'action"
                      />
                    </div>
                  </div>

                  {activeBrick.output_spec.format === "json" &&
                    activeBrick.output_spec.fields.map((field, idx) => (
                      <div key={idx} className={styles.rowItem}>
                        <input
                          className={styles.input}
                          value={field.key}
                          onChange={e =>
                            updateOutputField(idx, { key: slugifyBrickId(e.target.value, field.key) })
                          }
                          placeholder="cle_sortie"
                        />
                        <input
                          className={styles.input}
                          value={field.description}
                          onChange={e => updateOutputField(idx, { description: e.target.value })}
                          placeholder="Description de la valeur attendue"
                        />
                        <select
                          className={styles.select}
                          value={field.type}
                          onChange={e =>
                            updateOutputField(idx, { type: e.target.value as BrickOutputFieldType })
                          }
                        >
                          <option value="string">string</option>
                          <option value="number">number</option>
                          <option value="boolean">boolean</option>
                          <option value="string[]">string[] (liste)</option>
                        </select>
                        <button
                          type="button"
                          className={`${styles.btn} ${styles.btnDanger}`}
                          style={{ padding: "0.35rem" }}
                          onClick={() => removeOutputField(idx)}
                          title="Supprimer cette clé"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))}
                </div>

                {/* 4. SDK Integration & Live Sandbox Test */}
                <div className={styles.sectionBox}>
                  <div className={styles.sectionHeader}>
                    <h3 className={styles.sectionHeading}>
                      <Code2 size={15} color="#0284c7" />
                      4. Intégration dans l&apos;application & Test en direct
                    </h3>
                    <div style={{ display: "flex", gap: "0.45rem", flexWrap: "wrap" }}>
                      <button type="button" className={styles.btn} onClick={() => void handleCopySnippet()}>
                        {copiedSnippet ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                        <span>{copiedSnippet ? "Copié" : "Copier le JS"}</span>
                      </button>
                      {onInsertTurnkeyWidget && (
                        <button
                          type="button"
                          className={`${styles.btn} ${styles.btnSuccess}`}
                          onClick={() => {
                            onInsertTurnkeyWidget(activeBrick, draftBricks);
                            onClose();
                          }}
                          title="Insère directement ce widget prêt à l'emploi dans l'application et ouvre l'Aperçu"
                        >
                          <Puzzle size={13} />
                          <span>Insérer le widget prêt à l&apos;emploi</span>
                        </button>
                      )}
                      {onWireBrickWithAI && (
                        <button
                          type="button"
                          className={`${styles.btn} ${styles.btnPrimary}`}
                          onClick={() => {
                            void onSave(draftBricks);
                            onWireBrickWithAI(activeBrick, draftBricks);
                            onClose();
                          }}
                        >
                          <Sparkles size={13} />
                          <span>Câbler dans le code via l&apos;IA</span>
                        </button>
                      )}
                    </div>
                  </div>

                  <pre className={styles.codeBox}>{generateBrickUsageSnippet(activeBrick)}</pre>

                  <div style={{ borderTop: "1px dashed #cbd5e1", paddingTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
                    <strong style={{ fontSize: "0.78rem" }}>Tester cette brique maintenant :</strong>
                    {activeBrick.inputs.map(inp => (
                      <div key={inp.key} className={styles.field}>
                        <label className={styles.label}>
                          {inp.label} (<code>{inp.key}</code>)
                        </label>
                        {inp.type === "textarea" || inp.type === "json" ? (
                          <textarea
                            className={styles.textarea}
                            rows={2}
                            value={testInputs[inp.key] ?? ""}
                            onChange={e =>
                              setTestInputsByBrick(old => ({
                                ...old,
                                [activeBrick.id]: {
                                  ...(old[activeBrick.id] ?? {}),
                                  [inp.key]: e.target.value,
                                },
                              }))
                            }
                            placeholder={inp.placeholder}
                          />
                        ) : (
                          <input
                            className={styles.input}
                            type={inp.type === "number" ? "number" : "text"}
                            value={testInputs[inp.key] ?? ""}
                            onChange={e =>
                              setTestInputsByBrick(old => ({
                                ...old,
                                [activeBrick.id]: {
                                  ...(old[activeBrick.id] ?? {}),
                                  [inp.key]: e.target.value,
                                },
                              }))
                            }
                            placeholder={inp.placeholder}
                          />
                        )}
                      </div>
                    ))}

                    <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                      <button
                        type="button"
                        className={`${styles.btn} ${styles.btnSuccess}`}
                        disabled={testing}
                        onClick={() => void handleRunTest()}
                      >
                        {testing ? <LoaderCircle size={14} className="spin" /> : <Play size={14} />}
                        <span>{testing ? "Exécution en cours..." : "Tester la brique IA"}</span>
                      </button>
                    </div>

                    {testError && (
                      <div style={{ color: "#ef4444", fontSize: "0.78rem" }}>{testError}</div>
                    )}
                    {testOutput && <div className={styles.testResult}>{testOutput}</div>}
                  </div>
                </div>
              </>
            )}
          </section>
        </div>

        <footer className={styles.footer}>
          <span style={{ fontSize: "0.76rem", color: "#64748b" }}>
            Les briques activent automatiquement <code>window.clair.runBrick(...)</code> et un widget interactif sécurisé (sans clé API côté client).
          </span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button type="button" className={styles.btn} onClick={onClose} disabled={saving}>
              Annuler
            </button>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnPrimary}`}
              onClick={() => void handleConfirmSave()}
              disabled={saving}
            >
              {saving ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}
              <span>Enregistrer les briques ({draftBricks.length})</span>
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
