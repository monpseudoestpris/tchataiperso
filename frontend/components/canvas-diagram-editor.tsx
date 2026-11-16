"use client";

import {
  Bot,
  Check,
  Link2,
  LoaderCircle,
  Monitor,
  Plus,
  Rocket,
  Sparkles,
  Trash2,
  WandSparkles,
  X,
} from "lucide-react";
import { useRef, useState } from "react";
import {
  errorMessage,
  interviewAppDiagram,
  type DiagramInterviewQuestion,
  type Model,
  type PageBrick,
} from "@/lib/api";
import {
  createBrickFromTemplate,
  PREMADE_BRICK_TEMPLATES,
  slugifyBrickId,
  type BrickInputType,
  type BrickOutputFieldType,
  type BrickOutputFormat,
} from "@/lib/canvas-bricks";
import {
  DIAGRAM_PRESETS,
  extractBricksFromDiagram,
  type AppDiagram,
  type DiagramEdge,
  type DiagramNode,
  type DiagramNodeKind,
} from "@/lib/canvas-diagram";
import styles from "./canvas-diagram-editor.module.css";

export type CanvasDiagramEditorProps = {
  diagram: AppDiagram;
  models?: Model[];
  currentModel?: string;
  hasExistingFiles: boolean;
  onDiagramChange: (nextDiagram: AppDiagram, syncBricks: PageBrick[]) => void;
  onGenerateFromDiagram: (diagram: AppDiagram, bricks: PageBrick[]) => void;
};

const NODE_WIDTH = 230;
const NODE_HEIGHT = 112;

export function CanvasDiagramEditor({
  diagram,
  models = [],
  currentModel,
  hasExistingFiles,
  onDiagramChange,
  onGenerateFromDiagram,
}: CanvasDiagramEditorProps) {
  const [ideaPrompt, setIdeaPrompt] = useState("");
  const [proposing, setProposing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Interactive Architect Interview state
  const [interviewMessages, setInterviewMessages] = useState<
    { role: "user" | "assistant"; content: string }[]
  >([]);
  const [interviewStatus, setInterviewStatus] = useState<"idle" | "questions" | "ready">("idle");
  const [assistantMessage, setAssistantMessage] = useState("");
  const [selectedBrickIds, setSelectedBrickIds] = useState<string[]>([]);
  const [questions, setQuestions] = useState<DiagramInterviewQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    () => diagram.nodes.find(n => n.kind === "ai_brick")?.id ?? diagram.nodes[0]?.id ?? null,
  );
  const [connectingFromId, setConnectingFromId] = useState<string | null>(null);
  const [newEdgeLabel, setNewEdgeLabel] = useState("données");

  const dragRef = useRef<{
    nodeId: string;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);

  const selectedNode =
    diagram.nodes.find(n => n.id === selectedNodeId) ?? diagram.nodes[0] ?? null;

  function commitDiagram(next: AppDiagram) {
    const bricks = extractBricksFromDiagram(next);
    onDiagramChange(next, bricks);
  }

  function buildCatalogPayload() {
    return PREMADE_BRICK_TEMPLATES.map(t => ({
      templateId: t.templateId,
      name: t.brick.name,
      tagline: t.tagline,
    }));
  }

  async function runInterviewTurn(
    nextMessages: { role: "user" | "assistant"; content: string }[],
    forceFinalize = false,
  ) {
    setProposing(true);
    setError(null);
    try {
      const res = await interviewAppDiagram({
        messages: nextMessages,
        available_templates: buildCatalogPayload(),
        model: currentModel,
        force_finalize: forceFinalize,
      });

      setSelectedBrickIds(res.selected_brick_ids || []);
      setAssistantMessage(res.assistant_message || "");
      setQuestions(res.questions || []);
      setAnswers({});
      setInterviewStatus(res.status === "ready" ? "ready" : "questions");
      setInterviewMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: res.assistant_message || "Voici mes propositions.",
        },
      ]);

      if (res.diagram) {
        commitDiagram(res.diagram);
        const firstAi = res.diagram.nodes.find(n => n.kind === "ai_brick") ?? res.diagram.nodes[0];
        setSelectedNodeId(firstAi?.id ?? null);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setProposing(false);
    }
  }

  async function handleStartInterview() {
    if (!ideaPrompt.trim() || proposing) return;
    const initialHistory: { role: "user" | "assistant"; content: string }[] = [
      { role: "user", content: ideaPrompt.trim() },
    ];
    setInterviewMessages(initialHistory);
    await runInterviewTurn(initialHistory, false);
  }

  async function handleSubmitAnswers(forceFinalize = false) {
    if (proposing) return;
    const formattedAnswers = questions
      .map(q => {
        const ans = (answers[q.id] || "").trim();
        return ans ? `- ${q.question} -> ${ans}` : null;
      })
      .filter(Boolean)
      .join("\n");

    const replyContent =
      formattedAnswers ||
      (forceFinalize
        ? "Génère maintenant le diagramme complet avec les briques recommandées."
        : "Utilise tes recommandations et finalise le diagramme.");

    const nextMessages: { role: "user" | "assistant"; content: string }[] = [
      ...interviewMessages,
      { role: "user", content: replyContent },
    ];
    setInterviewMessages(nextMessages);
    await runInterviewTurn(nextMessages, forceFinalize || true);
  }

  function applyPreset(presetId: string) {
    const found = DIAGRAM_PRESETS.find(p => p.presetId === presetId);
    if (!found) return;
    const cloned = JSON.parse(JSON.stringify(found.diagram)) as AppDiagram;
    commitDiagram(cloned);
    setSelectedNodeId(cloned.nodes.find(n => n.kind === "ai_brick")?.id ?? cloned.nodes[0]?.id ?? null);
  }

  function addNode(kind: DiagramNodeKind, templateId?: string) {
    const idx = diagram.nodes.length + 1;
    let node: DiagramNode;

    if (kind === "ai_brick") {
      const tpl =
        PREMADE_BRICK_TEMPLATES.find(t => t.templateId === templateId) ??
        PREMADE_BRICK_TEMPLATES[0];
      const existingBricks = extractBricksFromDiagram(diagram);
      const brick = createBrickFromTemplate(tpl, existingBricks);
      brick.show_widget = false;
      node = {
        id: `ai_${brick.id}_${idx}`,
        kind: "ai_brick",
        label: brick.name,
        subtitle: "Agent IA interne de l'app",
        x: 344,
        y: 60 + (diagram.nodes.filter(n => n.kind === "ai_brick").length % 3) * 145,
        brick,
      };
    } else if (kind === "ui_input") {
      node = {
        id: `ui_in_${idx}`,
        kind: "ui_input",
        label: `Entrée UI ${idx}`,
        subtitle: "Champ, sélecteur ou bouton utilisateur",
        x: 36,
        y: 60 + (diagram.nodes.filter(n => n.kind === "ui_input").length % 3) * 145,
      };
    } else {
      node = {
        id: `ui_out_${idx}`,
        kind: "ui_output",
        label: `Affichage UI ${idx}`,
        subtitle: "Zone, jauge, bulle ou score mis à jour",
        x: 660,
        y: 60 + (diagram.nodes.filter(n => n.kind === "ui_output" || n.kind === "ui_state").length % 3) * 145,
      };
    }

    const next: AppDiagram = {
      ...diagram,
      nodes: [...diagram.nodes, node],
    };
    commitDiagram(next);
    setSelectedNodeId(node.id);
  }

  function removeNode(nodeId: string) {
    const next: AppDiagram = {
      ...diagram,
      nodes: diagram.nodes.filter(n => n.id !== nodeId),
      edges: diagram.edges.filter(e => e.from_node !== nodeId && e.to_node !== nodeId),
    };
    commitDiagram(next);
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(next.nodes[0]?.id ?? null);
    }
  }

  function updateNode(nodeId: string, updater: (node: DiagramNode) => DiagramNode) {
    const next: AppDiagram = {
      ...diagram,
      nodes: diagram.nodes.map(n => (n.id === nodeId ? updater(n) : n)),
    };
    commitDiagram(next);
  }

  function removeEdge(edgeId: string) {
    commitDiagram({
      ...diagram,
      edges: diagram.edges.filter(e => e.id !== edgeId),
    });
  }

  function handleNodeClick(node: DiagramNode) {
    if (connectingFromId && connectingFromId !== node.id) {
      const fromNode = diagram.nodes.find(n => n.id === connectingFromId);
      let autoLabel = newEdgeLabel.trim() || "données";
      if (fromNode?.kind === "ai_brick" && fromNode.brick?.output_spec.fields.length) {
        autoLabel = fromNode.brick.output_spec.fields[0].key;
      } else if (node.kind === "ai_brick" && node.brick?.inputs.length) {
        autoLabel = node.brick.inputs[0].key;
      }
      const usedIds = new Set(diagram.edges.map(e => e.id));
      let idx = diagram.edges.length + 1;
      while (usedIds.has(`e_${idx}`)) idx += 1;
      const newEdge: DiagramEdge = {
        id: `e_${idx}`,
        from_node: connectingFromId,
        to_node: node.id,
        label: autoLabel,
      };
      commitDiagram({
        ...diagram,
        edges: [...diagram.edges, newEdge],
      });
      setConnectingFromId(null);
      return;
    }
    setSelectedNodeId(node.id);
  }

  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>, node: DiagramNode) {
    if ((e.target as HTMLElement).closest("button")) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = {
      nodeId: node.id,
      startX: e.clientX,
      startY: e.clientY,
      origX: node.x,
      origY: node.y,
    };
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    const nextX = Math.max(12, Math.min(730, Math.round(drag.origX + dx)));
    const nextY = Math.max(12, Math.min(440, Math.round(drag.origY + dy)));
    updateNode(drag.nodeId, n => ({ ...n, x: nextX, y: nextY }));
  }

  function handlePointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (dragRef.current) {
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        // Ignore if pointer capture already released
      }
      dragRef.current = null;
    }
  }

  const nodeMap = new Map(diagram.nodes.map(n => [n.id, n]));

  return (
    <div className={styles.shell}>
      {/* Top Toolbar */}
      <div className={styles.topbar}>
        <div className={styles.promptRow}>
          <input
            className={styles.promptInput}
            value={ideaPrompt}
            onChange={e => setIdeaPrompt(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter") {
                e.preventDefault();
                void handleStartInterview();
              }
            }}
            placeholder="Décrivez l'app souhaitée (l'agent choisira les briques et vous posera 2-3 questions)…"
          />
          <button
            type="button"
            className={`${styles.btn} ${styles.btnPrimary}`}
            disabled={!ideaPrompt.trim() || proposing}
            onClick={() => void handleStartInterview()}
          >
            {proposing ? <LoaderCircle size={13} className="spin" /> : <WandSparkles size={13} />}
            <span>{proposing ? "Analyse…" : "Concevoir avec l'Agent"}</span>
          </button>
          <button
            type="button"
            className={`${styles.btn} ${styles.btnGenerate}`}
            onClick={() => onGenerateFromDiagram(diagram, extractBricksFromDiagram(diagram))}
            title="Génère ou met à jour le code de l'app en connectant chaque brique IA à l'intérieur de l'interface"
          >
            <Rocket size={13} />
            <span>
              {hasExistingFiles
                ? "Câbler ce diagramme dans l'App"
                : "Générer l'App depuis ce Diagramme"}
            </span>
          </button>
        </div>

        <div className={styles.toolbarRow}>
          <div className={styles.group}>
            <select
              className={styles.presetSelect}
              value=""
              onChange={e => {
                if (e.target.value) applyPreset(e.target.value);
              }}
              aria-label="Charger un modèle de diagramme"
            >
              <option value="">📐 Charger un modèle d&apos;architecture…</option>
              {DIAGRAM_PRESETS.map(p => (
                <option key={p.presetId} value={p.presetId}>
                  {p.icon} {p.label}
                </option>
              ))}
            </select>

            <button type="button" className={styles.btn} onClick={() => addNode("ui_input")}>
              <Plus size={12} />
              <span>Entrée UI</span>
            </button>
            <button type="button" className={styles.btn} onClick={() => addNode("ai_brick")}>
              <Bot size={12} />
              <span>Brique Agent IA</span>
            </button>
            <button type="button" className={styles.btn} onClick={() => addNode("ui_output")}>
              <Monitor size={12} />
              <span>Sortie / Jauge UI</span>
            </button>
          </div>

          <span style={{ fontSize: "0.72rem", color: "#94a3b8" }}>
            {diagram.nodes.length} blocs · {diagram.edges.length} liaisons
          </span>
        </div>

        {error && (
          <div style={{ fontSize: "0.75rem", color: "#fca5a5" }}>{error}</div>
        )}
      </div>

      {interviewStatus !== "idle" && (
        <div className={styles.interviewPanel}>
          <div className={styles.interviewHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
              <Bot size={15} color="#a78bfa" />
              <strong style={{ fontSize: "0.8rem", color: "#f8fafc" }}>
                Agent Architecte — Choix des briques & cadrage
              </strong>
            </div>
            <button
              type="button"
              className={styles.btn}
              style={{ padding: "2px 6px" }}
              onClick={() => setInterviewStatus("idle")}
              aria-label="Fermer l'assistant"
            >
              <X size={12} />
            </button>
          </div>

          {assistantMessage && <p className={styles.interviewMsg}>{assistantMessage}</p>}

          {selectedBrickIds.length > 0 && (
            <div className={styles.selectedBricksRow}>
              <span style={{ fontSize: "0.7rem", color: "#94a3b8", fontWeight: 600 }}>
                Briques choisies par l&apos;agent :
              </span>
              {selectedBrickIds.map(bid => {
                const tpl = PREMADE_BRICK_TEMPLATES.find(
                  t => t.templateId === bid || t.brick.id === bid,
                );
                return (
                  <span key={bid} className={styles.brickBadge}>
                    <span>{tpl?.icon || "🤖"}</span>
                    <span>{tpl?.brick.name || bid}</span>
                  </span>
                );
              })}
            </div>
          )}

          {interviewStatus === "questions" && questions.length > 0 && (
            <>
              <div className={styles.questionsList}>
                {questions.map(q => {
                  const currentAns = answers[q.id] || "";
                  return (
                    <div key={q.id} className={styles.questionCard}>
                      <div className={styles.questionText}>{q.question}</div>
                      {q.options.length > 0 && (
                        <div className={styles.optionsWrap}>
                          {q.options.map(opt => {
                            const active = currentAns === opt;
                            return (
                              <button
                                key={opt}
                                type="button"
                                className={`${styles.optionChip} ${active ? styles.optionChipActive : ""}`}
                                onClick={() =>
                                  setAnswers(old => ({ ...old, [q.id]: active ? "" : opt }))
                                }
                              >
                                {opt}
                              </button>
                            );
                          })}
                        </div>
                      )}
                      <input
                        className={styles.input}
                        value={currentAns}
                        onChange={e =>
                          setAnswers(old => ({ ...old, [q.id]: e.target.value }))
                        }
                        placeholder="Ou précisez votre réponse…"
                      />
                    </div>
                  );
                })}
              </div>

              <div className={styles.interviewActions}>
                <button
                  type="button"
                  className={styles.btn}
                  disabled={proposing}
                  onClick={() => void handleSubmitAnswers(true)}
                >
                  <span>Passer et générer le diagramme maintenant</span>
                </button>
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnPrimary}`}
                  disabled={proposing}
                  onClick={() => void handleSubmitAnswers(false)}
                >
                  {proposing ? <LoaderCircle size={13} className="spin" /> : <Check size={13} />}
                  <span>Valider mes réponses & construire le diagramme</span>
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {connectingFromId && (
        <div className={styles.connectBanner}>
          <span>
            🔗 Cliquez maintenant sur le bloc cible pour créer la flèche depuis «{" "}
            {nodeMap.get(connectingFromId)?.label} »
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <input
              className={styles.input}
              style={{ width: 150, padding: "0.2rem 0.45rem" }}
              value={newEdgeLabel}
              onChange={e => setNewEdgeLabel(e.target.value)}
              placeholder="Donnée (ex: reponse_bot)"
            />
            <button
              type="button"
              className={styles.btn}
              onClick={() => setConnectingFromId(null)}
            >
              Annuler
            </button>
          </div>
        </div>
      )}

      {/* Main Workspace: Interactive Graph + Right Node Inspector */}
      <div className={styles.workspace}>
        <div className={styles.canvasArea}>
          <div className={styles.board}>
            <svg className={styles.svgLayer}>
              <defs>
                <marker
                  id="diagram-arrow"
                  viewBox="0 0 10 10"
                  refX="8"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 1 L 10 5 L 0 9 z" fill="#60a5fa" />
                </marker>
              </defs>
              {diagram.edges.map(edge => {
                const src = nodeMap.get(edge.from_node);
                const dst = nodeMap.get(edge.to_node);
                if (!src || !dst) return null;
                const x1 = src.x + NODE_WIDTH;
                const y1 = src.y + NODE_HEIGHT / 2;
                const x2 = dst.x;
                const y2 = dst.y + NODE_HEIGHT / 2;
                const dx = Math.max(45, Math.abs(x2 - x1) * 0.45);
                const d = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
                return (
                  <path
                    key={edge.id}
                    d={d}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2.2"
                    strokeOpacity="0.8"
                    markerEnd="url(#diagram-arrow)"
                  />
                );
              })}
            </svg>

            {diagram.edges.map(edge => {
              const src = nodeMap.get(edge.from_node);
              const dst = nodeMap.get(edge.to_node);
              if (!src || !dst) return null;
              const midX = (src.x + NODE_WIDTH + dst.x) / 2;
              const midY = (src.y + dst.y + NODE_HEIGHT) / 2;
              return (
                <div
                  key={`${edge.id}_lbl`}
                  className={styles.edgeBadge}
                  style={{ left: midX, top: midY }}
                >
                  <span>{edge.label}</span>
                  <button
                    type="button"
                    title="Supprimer cette liaison"
                    onClick={() => removeEdge(edge.id)}
                  >
                    ×
                  </button>
                </div>
              );
            })}

            {diagram.nodes.map(node => {
              const isSelected = selectedNode?.id === node.id;
              const kindClass =
                node.kind === "ai_brick"
                  ? styles.node_ai_brick
                  : node.kind === "ui_input"
                    ? styles.node_ui_input
                    : styles.node_ui_output;
              const tagClass =
                node.kind === "ai_brick"
                  ? styles.tag_ai_brick
                  : node.kind === "ui_input"
                    ? styles.tag_ui_input
                    : styles.tag_ui_output;
              const kindLabel =
                node.kind === "ai_brick"
                  ? "🤖 Brique Agent IA"
                  : node.kind === "ui_input"
                    ? "🖥️ Entrée UI"
                    : "📊 Sortie UI";

              return (
                <div
                  key={node.id}
                  className={`${styles.nodeCard} ${kindClass} ${isSelected ? styles.selected : ""}`}
                  style={{ left: node.x, top: node.y }}
                  onClick={() => handleNodeClick(node)}
                  onPointerDown={e => handlePointerDown(e, node)}
                  onPointerMove={handlePointerMove}
                  onPointerUp={handlePointerUp}
                >
                  <div className={styles.nodeTop}>
                    <span className={`${styles.nodeKindTag} ${tagClass}`}>{kindLabel}</span>
                    <button
                      type="button"
                      className={styles.btn}
                      style={{ padding: "2px 6px", fontSize: "0.66rem" }}
                      title="Tracer une flèche depuis ce bloc vers un autre bloc"
                      onClick={e => {
                        e.stopPropagation();
                        setConnectingFromId(node.id);
                      }}
                    >
                      <Link2 size={11} />
                      <span>Relier</span>
                    </button>
                  </div>
                  <div className={styles.nodeTitle}>{node.label}</div>
                  <div className={styles.nodeSub}>{node.subtitle}</div>
                  {node.kind === "ai_brick" && node.brick && (
                    <div className={styles.nodeChips}>
                      <span className={styles.nodeChip}>
                        {node.brick.model && node.brick.model !== "auto"
                          ? node.brick.model.split("/").pop()
                          : "Modèle auto"}
                      </span>
                      <span className={styles.nodeChip}>
                        {node.brick.show_widget ? "Bulle test" : "Moteur interne"}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Inspector Panel */}
        <aside className={styles.inspector}>
          <div className={styles.field}>
            <label className={styles.label}>Titre de l&apos;Application</label>
            <input
              className={styles.input}
              value={diagram.title}
              onChange={e => commitDiagram({ ...diagram, title: e.target.value })}
            />
          </div>

          {selectedNode ? (
            <>
              <h3 className={styles.inspectorTitle}>
                <span>
                  {selectedNode.kind === "ai_brick" ? "🤖 Config Brique IA" : "🖥️ Bloc Interface"}
                </span>
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnDanger}`}
                  style={{ padding: "0.22rem 0.45rem" }}
                  onClick={() => removeNode(selectedNode.id)}
                  title="Supprimer ce bloc"
                >
                  <Trash2 size={12} />
                </button>
              </h3>

              <div className={styles.field}>
                <label className={styles.label}>Nom du bloc</label>
                <input
                  className={styles.input}
                  value={selectedNode.label}
                  onChange={e =>
                    updateNode(selectedNode.id, n => ({
                      ...n,
                      label: e.target.value,
                      brick: n.brick ? { ...n.brick, name: e.target.value } : undefined,
                    }))
                  }
                />
              </div>

              <div className={styles.field}>
                <label className={styles.label}>Rôle dans l&apos;interface</label>
                <input
                  className={styles.input}
                  value={selectedNode.subtitle}
                  onChange={e =>
                    updateNode(selectedNode.id, n => ({ ...n, subtitle: e.target.value }))
                  }
                />
              </div>

              {selectedNode.kind === "ai_brick" && selectedNode.brick && (
                <>
                  <div className={styles.field}>
                    <label className={styles.label}>ID JS (`window.clair.runBrick`)</label>
                    <input
                      className={styles.input}
                      value={selectedNode.brick.id}
                      onChange={e => {
                        const cleanId = slugifyBrickId(e.target.value, selectedNode.brick!.id);
                        updateNode(selectedNode.id, n =>
                          n.brick ? { ...n, brick: { ...n.brick, id: cleanId } } : n,
                        );
                      }}
                    />
                  </div>

                  <div className={styles.field}>
                    <label className={styles.label}>Modèle IA de cette brique</label>
                    <select
                      className={styles.select}
                      value={selectedNode.brick.model || "auto"}
                      onChange={e =>
                        updateNode(selectedNode.id, n =>
                          n.brick ? { ...n, brick: { ...n.brick, model: e.target.value } } : n,
                        )
                      }
                    >
                      <option value="auto">
                        Modèle actif ({currentModel || "auto"})
                      </option>
                      {models.map(m => (
                        <option key={m.id} value={m.id}>
                          {m.name || m.id}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className={styles.field}>
                    <label className={styles.label}>Prompt système / Personnage dans l&apos;app</label>
                    <textarea
                      className={styles.textarea}
                      rows={4}
                      value={selectedNode.brick.system_prompt}
                      onChange={e =>
                        updateNode(selectedNode.id, n =>
                          n.brick
                            ? { ...n, brick: { ...n.brick, system_prompt: e.target.value } }
                            : n,
                        )
                      }
                    />
                  </div>

                  {/* Inputs editor */}
                  <div className={styles.field}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <label className={styles.label}>Entrées ({selectedNode.brick.inputs.length})</label>
                      <button
                        type="button"
                        className={styles.btn}
                        style={{ padding: "2px 6px", fontSize: "0.68rem" }}
                        onClick={() =>
                          updateNode(selectedNode.id, n => {
                            if (!n.brick) return n;
                            const k = `entree_${n.brick.inputs.length + 1}`;
                            return {
                              ...n,
                              brick: {
                                ...n.brick,
                                inputs: [
                                  ...n.brick.inputs,
                                  {
                                    key: k,
                                    label: k,
                                    type: "text",
                                    required: true,
                                    placeholder: "",
                                    default_value: "",
                                    options: [],
                                  },
                                ],
                              },
                            };
                          })
                        }
                      >
                        + Entrée
                      </button>
                    </div>
                    {selectedNode.brick.inputs.map((inp, idx) => (
                      <div key={idx} className={styles.miniRow}>
                        <input
                          className={styles.input}
                          value={inp.key}
                          onChange={e =>
                            updateNode(selectedNode.id, n => {
                              if (!n.brick) return n;
                              const nextInputs = n.brick.inputs.map((item, i) =>
                                i === idx
                                  ? { ...item, key: slugifyBrickId(e.target.value, item.key), label: e.target.value }
                                  : item,
                              );
                              return { ...n, brick: { ...n.brick, inputs: nextInputs } };
                            })
                          }
                        />
                        <select
                          className={styles.select}
                          value={inp.type}
                          onChange={e =>
                            updateNode(selectedNode.id, n => {
                              if (!n.brick) return n;
                              const nextInputs = n.brick.inputs.map((item, i) =>
                                i === idx ? { ...item, type: e.target.value as BrickInputType } : item,
                              );
                              return { ...n, brick: { ...n.brick, inputs: nextInputs } };
                            })
                          }
                        >
                          <option value="text">text</option>
                          <option value="textarea">textarea</option>
                          <option value="number">number</option>
                          <option value="select">select</option>
                        </select>
                        <button
                          type="button"
                          className={styles.btn}
                          style={{ padding: "4px" }}
                          onClick={() =>
                            updateNode(selectedNode.id, n =>
                              n.brick
                                ? {
                                    ...n,
                                    brick: {
                                      ...n.brick,
                                      inputs: n.brick.inputs.filter((_, i) => i !== idx),
                                    },
                                  }
                                : n,
                            )
                          }
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    ))}
                  </div>

                  {/* Outputs editor */}
                  <div className={styles.field}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <label className={styles.label}>Sorties attendues</label>
                      {selectedNode.brick.output_spec.format === "json" && (
                        <button
                          type="button"
                          className={styles.btn}
                          style={{ padding: "2px 6px", fontSize: "0.68rem" }}
                          onClick={() =>
                            updateNode(selectedNode.id, n => {
                              if (!n.brick) return n;
                              const k = `sortie_${n.brick.output_spec.fields.length + 1}`;
                              return {
                                ...n,
                                brick: {
                                  ...n.brick,
                                  output_spec: {
                                    ...n.brick.output_spec,
                                    fields: [
                                      ...n.brick.output_spec.fields,
                                      { key: k, type: "string", description: "" },
                                    ],
                                  },
                                },
                              };
                            })
                          }
                        >
                          + Clé JSON
                        </button>
                      )}
                    </div>
                    <select
                      className={styles.select}
                      value={selectedNode.brick.output_spec.format}
                      onChange={e =>
                        updateNode(selectedNode.id, n =>
                          n.brick
                            ? {
                                ...n,
                                brick: {
                                  ...n.brick,
                                  output_spec: {
                                    ...n.brick.output_spec,
                                    format: e.target.value as BrickOutputFormat,
                                  },
                                },
                              }
                            : n,
                        )
                      }
                    >
                      <option value="json">JSON structuré (recommandé pour UI)</option>
                      <option value="markdown">Markdown</option>
                      <option value="list">Liste</option>
                      <option value="text">Texte brut</option>
                    </select>
                    {selectedNode.brick.output_spec.format === "json" &&
                      selectedNode.brick.output_spec.fields.map((f, idx) => (
                        <div key={idx} className={styles.miniRow}>
                          <input
                            className={styles.input}
                            value={f.key}
                            onChange={e =>
                              updateNode(selectedNode.id, n => {
                                if (!n.brick) return n;
                                const nextFields = n.brick.output_spec.fields.map((item, i) =>
                                  i === idx
                                    ? { ...item, key: slugifyBrickId(e.target.value, item.key) }
                                    : item,
                                );
                                return {
                                  ...n,
                                  brick: {
                                    ...n.brick,
                                    output_spec: { ...n.brick.output_spec, fields: nextFields },
                                  },
                                };
                              })
                            }
                          />
                          <select
                            className={styles.select}
                            value={f.type}
                            onChange={e =>
                              updateNode(selectedNode.id, n => {
                                if (!n.brick) return n;
                                const nextFields = n.brick.output_spec.fields.map((item, i) =>
                                  i === idx
                                    ? { ...item, type: e.target.value as BrickOutputFieldType }
                                    : item,
                                );
                                return {
                                  ...n,
                                  brick: {
                                    ...n.brick,
                                    output_spec: { ...n.brick.output_spec, fields: nextFields },
                                  },
                                };
                              })
                            }
                          >
                            <option value="string">string</option>
                            <option value="number">number</option>
                            <option value="boolean">boolean</option>
                            <option value="string[]">string[]</option>
                          </select>
                          <button
                            type="button"
                            className={styles.btn}
                            style={{ padding: "4px" }}
                            onClick={() =>
                              updateNode(selectedNode.id, n =>
                                n.brick
                                  ? {
                                      ...n,
                                      brick: {
                                        ...n.brick,
                                        output_spec: {
                                          ...n.brick.output_spec,
                                          fields: n.brick.output_spec.fields.filter((_, i) => i !== idx),
                                        },
                                      },
                                    }
                                  : n,
                              )
                            }
                          >
                            <Trash2 size={11} />
                          </button>
                        </div>
                      ))}
                  </div>

                  <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.72rem", color: "#cbd5e1", cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={selectedNode.brick.show_widget}
                      onChange={e =>
                        updateNode(selectedNode.id, n =>
                          n.brick
                            ? { ...n, brick: { ...n.brick, show_widget: e.target.checked } }
                            : n,
                        )
                      }
                    />
                    <span>Afficher aussi une bulle flottante de test (sinon 100 % intégré à l&apos;app)</span>
                  </label>
                </>
              )}
            </>
          ) : (
            <p style={{ fontSize: "0.78rem", color: "#94a3b8" }}>
              Sélectionnez un bloc sur le diagramme pour configurer son rôle, son modèle, son prompt, ses entrées et ses sorties.
            </p>
          )}
        </aside>
      </div>

      <div className={styles.hintStrip}>
        <span>
          <Sparkles size={12} style={{ verticalAlign: "middle", marginRight: 4 }} />
          Les briques configurées ici propulsent directement l&apos;interface de l&apos;app (sans bulle flottante superposée).
        </span>
        <span>Glissez les blocs pour organiser · Cliquez sur « Relier » pour tracer un flux</span>
      </div>
    </div>
  );
}
