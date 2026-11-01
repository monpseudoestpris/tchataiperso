"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  BookOpen,
  Brain,
  Calendar,
  Check,
  CheckSquare,
  ChevronRight,
  CircleAlert,
  Compass,
  Copy,
  Download,
  ExternalLink,
  FileText,
  FolderArchive,
  Globe,
  GraduationCap,
  History,
  Layers,
  Lightbulb,
  ListTodo,
  LoaderCircle,
  MessageCircle,
  MessageSquarePlus,
  Pencil,
  Plus,
  Sparkles,
  Square,
  StickyNote,
  Target,
  Trash2,
  Unlink,
  X,
} from "lucide-react";
import {
  createTopic,
  createTopicMemory,
  createTopicResource,
  deleteTopic,
  deleteTopicMemory,
  deleteTopicResource,
  fetchTopic,
  fetchTopics,
  unlinkConversationFromTopic,
  updateTopic,
  updateTopicMemory,
  type Conversation,
  type TopicMemory,
  type TopicMemoryStatus,
  type TopicResource,
  type TopicResourceType,
  type TopicSpace,
  type TopicType,
} from "@/lib/api";
import styles from "./topic-modal.module.css";

const TOPIC_TYPE_LABELS: Record<TopicType, { label: string; icon: string; desc: string }> = {
  learning: {
    label: "Apprentissage",
    icon: "🎓",
    desc: "Suivi des notions, niveau, exercices et acquis didactiques",
  },
  project: {
    label: "Projet",
    icon: "💻",
    desc: "Objectifs, décisions d'architecture, tâches et avancée",
  },
  interest: {
    label: "Centre d'intérêt",
    icon: "🎯",
    desc: "Sujets explorés, curation de ressources et recommandations",
  },
  personal: {
    label: "Dossier personnel",
    icon: "📂",
    desc: "Démarches, échéances, notes et décisions clés",
  },
};

const STATUS_CONFIG: Record<TopicMemoryStatus, { label: string; next: TopicMemoryStatus }> = {
  discussed: { label: "Abordé", next: "in_progress" },
  in_progress: { label: "En cours", next: "provisional_mastery" },
  needs_review: { label: "À renforcer", next: "provisional_mastery" },
  provisional_mastery: { label: "Acquis provisoire", next: "validated" },
  validated: { label: "Validé", next: "needs_review" },
};

export type TopicModalProps = {
  open: boolean;
  topicId: string | null;
  onClose: () => void;
  onOpenConversation: (conversationId: string) => void;
  onStartNewConversation: (topicId: string) => void;
  onStartCustomChat?: (topicId: string, prompt: string) => void;
  onOpenStudyModal?: (topicId: string, initialKind: "flashcards" | "quiz" | "cloze" | "all", courseText: string) => void;
  onTopicsChanged?: () => void;
};

export function TopicModal({
  open,
  topicId,
  onClose,
  onOpenConversation,
  onStartNewConversation,
  onStartCustomChat,
  onOpenStudyModal,
  onTopicsChanged,
}: TopicModalProps) {
  const [topic, setTopic] = useState<TopicSpace | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [activeTab, setActiveTab] = useState<"resume" | "conversations" | "memories" | "resources" | "events">("resume");
  const [isCreating, setIsCreating] = useState(!topicId);

  // Creation form state
  const titleInputRef = useRef<HTMLInputElement>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newIcon, setNewIcon] = useState("📌");
  const [newType, setNewType] = useState<TopicType>("learning");
  const [newObjective, setNewObjective] = useState("");

  // Edit space state
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editIcon, setEditIcon] = useState("📌");
  const [editType, setEditType] = useState<TopicType>("learning");
  const [editObjective, setEditObjective] = useState("");

  // Add memory state
  const [isAddingMemory, setIsAddingMemory] = useState(false);
  const [memFact, setMemFact] = useState("");
  const [memCategory, setMemCategory] = useState("general");
  const [memStatus, setMemStatus] = useState<TopicMemoryStatus>("discussed");

  // Memory filter
  const [memoryFilter, setMemoryFilter] = useState<"all" | TopicMemoryStatus>("all");

  // Resource state
  const [isAddingResource, setIsAddingResource] = useState(false);
  const [resTitle, setResTitle] = useState("");
  const [resType, setResType] = useState<TopicResourceType>("link");
  const [resUrl, setResUrl] = useState("");
  const [resContent, setResContent] = useState("");
  const [resourceFilter, setResourceFilter] = useState<"all" | TopicResourceType>("all");

  // Project tracker quick item
  const [quickItemText, setQuickItemText] = useState("");

  // Export menu
  const [exportMenuOpen, setExportMenuOpen] = useState(false);

  function notify(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3500);
  }

  // Load topic data
  useEffect(() => {
    if (!open) return;
    if (!topicId) {
      setIsCreating(true);
      setTopic(null);
      setLoading(false);
      setError("");
      setTimeout(() => {
        titleInputRef.current?.focus();
      }, 50);
      return;
    }
    setIsCreating(false);
    setLoading(true);
    setError("");

    fetchTopic(topicId)
      .then(data => {
        setTopic(data);
        setEditTitle(data.title);
        setEditIcon(data.icon || "📌");
        setEditType(data.topic_type);
        setEditObjective(data.objective);
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : "Erreur de chargement de l'espace");
      })
      .finally(() => setLoading(false));
  }, [open, topicId]);

  // Handle ESC key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && open) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  async function handleCreateTopic(e: FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) {
      setError("Veuillez renseigner un titre pour cet espace (ex : Apprendre l'espagnol).");
      titleInputRef.current?.focus();
      return;
    }
    setLoading(true);
    setError("");
    try {
      const created = await createTopic({
        title: newTitle.trim(),
        icon: newIcon.trim() || "📌",
        topic_type: newType,
        objective: newObjective.trim(),
      });
      setTopic(created);
      setIsCreating(false);
      setNewTitle("");
      setNewObjective("");
      onTopicsChanged?.();
      notify("Espace créé avec succès !");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de la création");
    } finally {
      setLoading(false);
    }
  }

  async function handleUpdateTopic(e: FormEvent) {
    e.preventDefault();
    if (!topic || !editTitle.trim()) return;
    setLoading(true);
    try {
      const updated = await updateTopic(topic.id, {
        title: editTitle.trim(),
        icon: editIcon.trim() || "📌",
        topic_type: editType,
        objective: editObjective.trim(),
      });
      setTopic(updated);
      setIsEditing(false);
      onTopicsChanged?.();
      notify("Espace mis à jour");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de la mise à jour");
    } finally {
      setLoading(false);
    }
  }

  async function handleDeleteTopic() {
    if (!topic) return;
    if (!confirm(`Supprimer l'espace « ${topic.title} » ? Les conversations resteront conservées hors-espace.`)) return;
    setLoading(true);
    try {
      await deleteTopic(topic.id);
      onTopicsChanged?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur lors de la suppression");
      setLoading(false);
    }
  }

  async function handleCycleStatus(mem: TopicMemory) {
    if (!topic) return;
    const nextStatus = STATUS_CONFIG[mem.status]?.next || "discussed";
    try {
      const updated = await updateTopicMemory(topic.id, mem.id, { status: nextStatus });
      setTopic(curr =>
        curr
          ? {
              ...curr,
              memories: curr.memories?.map(m => (m.id === mem.id ? updated : m)),
            }
          : null
      );
      notify(`Statut passé à : ${STATUS_CONFIG[nextStatus].label}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur mise à jour statut");
    }
  }

  async function handleDeleteMemory(memoryId: string) {
    if (!topic) return;
    try {
      await deleteTopicMemory(topic.id, memoryId);
      setTopic(curr =>
        curr
          ? {
              ...curr,
              memories: curr.memories?.filter(m => m.id !== memoryId),
              memories_count: Math.max(0, curr.memories_count - 1),
            }
          : null
      );
      notify("Souvenir supprimé");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur suppression souvenir");
    }
  }

  async function handleAddMemory(e: FormEvent) {
    e.preventDefault();
    if (!topic || !memFact.trim()) return;
    try {
      const created = await createTopicMemory(topic.id, {
        fact: memFact.trim(),
        category: memCategory.trim() || "general",
        status: memStatus,
      });
      setTopic(curr =>
        curr
          ? {
              ...curr,
              memories: [created, ...(curr.memories || [])],
              memories_count: curr.memories_count + 1,
            }
          : null
      );
      setMemFact("");
      setIsAddingMemory(false);
      notify("Souvenir ajouté à la mémoire du sujet");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur ajout souvenir");
    }
  }

  async function handleAddResource(e: FormEvent) {
    e.preventDefault();
    if (!topic || !resTitle.trim()) return;
    try {
      const created = await createTopicResource(topic.id, {
        title: resTitle.trim(),
        resource_type: resType,
        url: resUrl.trim() || undefined,
        content: resContent.trim(),
      });
      setTopic(curr =>
        curr
          ? {
              ...curr,
              resources: [created, ...(curr.resources || [])],
              resources_count: (curr.resources_count || 0) + 1,
            }
          : null
      );
      setResTitle("");
      setResUrl("");
      setResContent("");
      setIsAddingResource(false);
      notify("Ressource ajoutée à cet espace !");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur ajout ressource");
    }
  }

  async function handleDeleteResource(resourceId: string) {
    if (!topic) return;
    try {
      await deleteTopicResource(topic.id, resourceId);
      setTopic(curr =>
        curr
          ? {
              ...curr,
              resources: curr.resources?.filter(r => r.id !== resourceId),
              resources_count: Math.max(0, (curr.resources_count || 1) - 1),
            }
          : null
      );
      notify("Ressource supprimée");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur suppression ressource");
    }
  }

  async function handleUnlinkConv(conversationId: string) {
    if (!topic) return;
    try {
      const updated = await unlinkConversationFromTopic(topic.id, conversationId);
      setTopic(updated);
      onTopicsChanged?.();
      notify("Discussion détachée de cet espace");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur détachement discussion");
    }
  }

  async function handleToggleTaskDone(mem: TopicMemory) {
    if (!topic) return;
    const isDone = mem.status === "validated";
    const nextStatus: TopicMemoryStatus = isDone ? "in_progress" : "validated";
    try {
      const updated = await updateTopicMemory(topic.id, mem.id, { status: nextStatus });
      setTopic(curr =>
        curr
          ? {
              ...curr,
              memories: curr.memories?.map(m => (m.id === mem.id ? updated : m)),
            }
          : null
      );
      notify(isDone ? "Tâche marquée en cours" : "Tâche validée !");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur mise à jour tâche");
    }
  }

  async function handleQuickAddProjectItem(category: "task" | "decision") {
    if (!topic || !quickItemText.trim()) return;
    try {
      const created = await createTopicMemory(topic.id, {
        fact: quickItemText.trim(),
        category,
        status: category === "decision" ? "validated" : "in_progress",
      });
      setTopic(curr =>
        curr
          ? {
              ...curr,
              memories: [created, ...(curr.memories || [])],
              memories_count: curr.memories_count + 1,
            }
          : null
      );
      setQuickItemText("");
      notify(category === "task" ? "Tâche ajoutée au projet !" : "Décision enregistrée !");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur ajout élément");
    }
  }

  function generateMarkdownExport(t: TopicSpace): string {
    const lines: string[] = [];
    lines.push(`# ${t.icon || "📌"} ${t.title}`);
    lines.push("");
    lines.push(`**Type d'espace :** ${TOPIC_TYPE_LABELS[t.topic_type]?.label || t.topic_type}`);
    if (t.objective) {
      lines.push(`**Objectif :** ${t.objective}`);
    }
    lines.push(`**Date d'export :** ${new Date().toLocaleDateString("fr-FR", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" })}`);
    lines.push("");
    lines.push("---");
    lines.push("");
    lines.push("## 🧭 Point de reprise");
    lines.push(t.current_resume_context || "Aucun point de reprise pour le moment.");
    lines.push("");
    if (t.suggested_next_step) {
      lines.push(`> **Prochaine étape suggérée :** ${t.suggested_next_step}`);
      lines.push("");
    }

    const mems = (t.memories || []).filter(m => !m.is_archived);
    lines.push(`## 🧠 Mémoire & Savoirs (${mems.length})`);
    lines.push("");
    const validated = mems.filter(m => m.status === "validated");
    const provisional = mems.filter(m => m.status === "provisional_mastery");
    const inProgress = mems.filter(m => m.status === "in_progress");
    const needsReview = mems.filter(m => m.status === "needs_review");
    const discussed = mems.filter(m => m.status === "discussed");

    if (validated.length > 0) {
      lines.push("### ✅ Validés");
      validated.forEach(m => lines.push(`- ${m.fact}`));
      lines.push("");
    }
    if (provisional.length > 0) {
      lines.push("### 🔹 Acquis provisoires");
      provisional.forEach(m => lines.push(`- ${m.fact}`));
      lines.push("");
    }
    if (inProgress.length > 0) {
      lines.push("### ⏳ En cours");
      inProgress.forEach(m => lines.push(`- ${m.fact}`));
      lines.push("");
    }
    if (needsReview.length > 0) {
      lines.push("### ⚠️ À renforcer");
      needsReview.forEach(m => lines.push(`- ${m.fact}`));
      lines.push("");
    }
    if (discussed.length > 0) {
      lines.push("### 💬 Abordés");
      discussed.forEach(m => lines.push(`- ${m.fact}`));
      lines.push("");
    }

    if (t.topic_type === "project") {
      const tasks = mems.filter(m => m.category === "task");
      const decisions = mems.filter(m => m.category === "decision" || m.category === "arch");
      if (tasks.length > 0 || decisions.length > 0) {
        lines.push("## 🎯 Feuille de route & Tâches");
        tasks.forEach(m => {
          const checked = m.status === "validated" ? "[x]" : "[ ]";
          lines.push(`- ${checked} ${m.fact}`);
        });
        lines.push("");
        if (decisions.length > 0) {
          lines.push("## 💡 Décisions");
          decisions.forEach(m => lines.push(`- **${m.fact}**`));
          lines.push("");
        }
      }
    }

    const convs = t.conversations || [];
    lines.push(`## 💬 Discussions associées (${convs.length})`);
    if (convs.length === 0) {
      lines.push("_Aucune discussion rattachée pour le moment._");
    } else {
      convs.forEach(c => {
        const dateStr = new Date(c.updated_at).toLocaleDateString("fr-FR");
        lines.push(`- **${c.title}** (${dateStr})`);
      });
    }
    lines.push("");

    const resources = t.resources || [];
    if (resources.length > 0) {
      lines.push(`## 📚 Ressources & Documents (${resources.length})`);
      resources.forEach(r => {
        const link = r.url ? ` (${r.url})` : "";
        const desc = r.content ? ` — ${r.content}` : "";
        lines.push(`- **[${r.resource_type.toUpperCase()}]** ${r.title}${link}${desc}`);
      });
      lines.push("");
    }

    const events = t.events || [];
    if (events.length > 0) {
      lines.push(`## 📜 Journal d'activité (${events.length})`);
      events.forEach(e => {
        const dateStr = new Date(e.created_at).toLocaleDateString("fr-FR");
        lines.push(`- **${dateStr}** : ${e.title}`);
      });
      lines.push("");
    }

    return lines.join("\n");
  }

  async function handleCopyMarkdown() {
    if (!topic) return;
    try {
      const md = generateMarkdownExport(topic);
      await navigator.clipboard.writeText(md);
      setExportMenuOpen(false);
      notify("Synthèse Markdown copiée dans le presse-papiers !");
    } catch {
      setError("Impossible de copier dans le presse-papiers");
    }
  }

  function handleDownloadMarkdown() {
    if (!topic) return;
    try {
      const md = generateMarkdownExport(topic);
      const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const safeTitle = topic.title.toLowerCase().replace(/[^a-z0-9]/gi, "_").slice(0, 30);
      link.download = `espace_${safeTitle}_synthese.md`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setExportMenuOpen(false);
      notify("Dossier Markdown téléchargé !");
    } catch {
      setError("Erreur lors du téléchargement");
    }
  }

  function handleStartStudy(targetMemories?: TopicMemory[], forcedKind: "flashcards" | "quiz" | "cloze" | "all" = "all") {
    if (!topic || !onOpenStudyModal) return;
    const mems = targetMemories || (topic.memories || []).filter(m => !m.is_archived);
    const lines: string[] = [];
    lines.push(`Espace thématique : ${topic.title} (${TOPIC_TYPE_LABELS[topic.topic_type]?.label || topic.topic_type})`);
    if (topic.objective) {
      lines.push(`Objectif durable : ${topic.objective}`);
    }
    if (topic.current_resume_context) {
      lines.push(`Point de reprise : ${topic.current_resume_context}`);
    }
    lines.push("\nNotions et acquis à réviser et tester :");
    mems.forEach(m => {
      const statusLabel = STATUS_CONFIG[m.status]?.label || m.status;
      lines.push(`- [${statusLabel}] ${m.fact}`);
    });
    const res = (topic.resources || []).filter(r => r.content);
    if (res.length > 0) {
      lines.push("\nExtraits de documentation et fiches associées :");
      res.slice(0, 3).forEach(r => {
        lines.push(`- ${r.title} : ${r.content.slice(0, 200)}`);
      });
    }
    onClose();
    onOpenStudyModal(topic.id, forcedKind, lines.join("\n"));
  }

  const memoriesList = (topic?.memories || []).filter(m => {
    if (m.is_archived) return false;
    if (memoryFilter === "all") return true;
    return m.status === memoryFilter;
  });

  return (
    <div
      className={styles.backdrop}
      onClick={e => {
        if (e.target === e.currentTarget && !loading) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="topic-modal-title"
    >
      <div className={styles.modal}>
        {/* Header */}
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.topicIcon} aria-hidden="true">
              {isCreating ? newIcon : topic?.icon || "📌"}
            </span>
            <div className={styles.headerMeta}>
              <div className={styles.headerTitleRow}>
                <h2 id="topic-modal-title" className={styles.headerTitle}>
                  {isCreating ? "Nouvel espace thématique" : topic?.title}
                </h2>
                {!isCreating && topic && (
                  <span className={`${styles.typeBadge} ${styles[`badge_${topic.topic_type}`]}`}>
                    {TOPIC_TYPE_LABELS[topic.topic_type]?.label || topic.topic_type}
                  </span>
                )}
              </div>
              {!isCreating && topic?.objective && (
                <p className={styles.headerObjective} title={topic.objective}>
                  🎯 {topic.objective}
                </p>
              )}
            </div>
          </div>
          <div className={styles.headerActions}>
            {!isCreating && topic && (
              <>
                <div className={styles.exportDropdown}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() => setExportMenuOpen(!exportMenuOpen)}
                    title="Exporter la synthèse de cet espace"
                  >
                    <Download size={15} />
                    <span>Exporter</span>
                  </button>
                  {exportMenuOpen && (
                    <div className={styles.exportMenu}>
                      <button
                        type="button"
                        className={styles.exportMenuItem}
                        onClick={handleCopyMarkdown}
                      >
                        <Copy size={14} />
                        <span>Copier le Markdown</span>
                      </button>
                      <button
                        type="button"
                        className={styles.exportMenuItem}
                        onClick={handleDownloadMarkdown}
                      >
                        <Download size={14} />
                        <span>Télécharger le dossier (.md)</span>
                      </button>
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  onClick={() => setIsEditing(!isEditing)}
                  title="Modifier les paramètres de l'espace"
                >
                  <Pencil size={15} />
                  <span>{isEditing ? "Annuler" : "Modifier"}</span>
                </button>
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={handleDeleteTopic}
                  title="Supprimer cet espace"
                >
                  <Trash2 size={16} />
                </button>
              </>
            )}
            <button
              type="button"
              className={styles.iconBtn}
              onClick={onClose}
              aria-label="Fermer"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Global Notifications */}
        {toast && (
          <div style={{ background: "#dbeafe", color: "#1e40af", padding: "0.5rem 1.25rem", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Sparkles size={14} />
            <span>{toast}</span>
          </div>
        )}
        {error && (
          <div style={{ background: "#fee2e2", color: "#991b1b", padding: "0.5rem 1.25rem", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <CircleAlert size={14} />
            <span>{error}</span>
          </div>
        )}

        {/* Create Mode View */}
        {isCreating ? (
          <form onSubmit={handleCreateTopic} className={styles.content}>
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <p style={{ margin: 0, fontSize: "0.9rem", color: "var(--text-secondary, #64748b)" }}>
                Un espace persistant conserve le fil de vos apprentissages, projets ou centres d&apos;intérêt sur la durée, avec une mémoire active et un point de reprise à chaque retour.
              </p>

              <div style={{ display: "grid", gridTemplateColumns: "80px 1fr", gap: "0.75rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.25rem" }}>Icône</label>
                  <input
                    type="text"
                    value={newIcon}
                    onChange={e => setNewIcon(e.target.value)}
                    maxLength={4}
                    className={styles.formInput}
                    style={{ textAlign: "center", fontSize: "1.25rem", padding: "0.6rem" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                    Titre de l&apos;espace <span style={{ color: "#ef4444" }}>*</span>
                  </label>
                  <input
                    ref={titleInputRef}
                    type="text"
                    value={newTitle}
                    onChange={e => {
                      setNewTitle(e.target.value);
                      if (error) setError("");
                    }}
                    placeholder="Ex : Apprendre l'espagnol, Développement cLAIr, Production audio..."
                    className={styles.formInput}
                    autoFocus
                  />
                </div>
              </div>

              {/* Suggestions chips */}
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", marginTop: "-0.4rem" }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-secondary, #64748b)" }}>Exemples rapides :</span>
                {[
                  { icon: "🇪🇸", title: "Apprendre l'espagnol", type: "learning" as TopicType },
                  { icon: "🐍", title: "Apprendre Python", type: "learning" as TopicType },
                  { icon: "🚀", title: "Mon Projet Web", type: "project" as TopicType },
                  { icon: "🎵", title: "Production musicale", type: "interest" as TopicType },
                  { icon: "📁", title: "Notes & Dossier", type: "personal" as TopicType },
                ].map(sug => (
                  <button
                    key={sug.title}
                    type="button"
                    onClick={() => {
                      setNewTitle(sug.title);
                      setNewIcon(sug.icon);
                      setNewType(sug.type);
                      if (error) setError("");
                    }}
                    className={styles.suggestionChip}
                    title={`Remplir automatiquement avec « ${sug.title} »`}
                  >
                    <span>{sug.icon}</span>
                    <span>{sug.title}</span>
                  </button>
                ))}
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.4rem" }}>Type d&apos;espace</label>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "0.75rem" }}>
                  {(Object.keys(TOPIC_TYPE_LABELS) as TopicType[]).map(typeKey => {
                    const info = TOPIC_TYPE_LABELS[typeKey];
                    const selected = newType === typeKey;
                    return (
                      <button
                        key={typeKey}
                        type="button"
                        onClick={() => {
                          setNewType(typeKey);
                          if (newIcon === "📌" || ["🎓", "🚀", "💡", "📁"].includes(newIcon)) {
                            setNewIcon(info.icon);
                          }
                        }}
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "flex-start",
                          padding: "0.75rem 0.85rem",
                          borderRadius: "0.625rem",
                          border: selected ? "2px solid #2563eb" : "1px solid var(--border-color, #e2e8f0)",
                          background: selected ? "rgba(37, 99, 235, 0.08)" : "transparent",
                          cursor: "pointer",
                          textAlign: "left",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 600, fontSize: "0.875rem" }}>
                          <span>{info.icon}</span>
                          <span>{info.label}</span>
                        </div>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-secondary, #64748b)", marginTop: "0.25rem" }}>
                          {info.desc}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                  Objectif durable (optionnel)
                </label>
                <textarea
                  value={newObjective}
                  onChange={e => setNewObjective(e.target.value)}
                  placeholder="Ex : Atteindre un niveau B1 pour voyager en Espagne, livrer le MVP avant décembre..."
                  rows={2}
                  className={styles.formTextarea}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1rem" }}>
                <button type="button" className={styles.secondaryButton} onClick={onClose} disabled={loading}>
                  Annuler
                </button>
                <button type="submit" className={styles.primaryButton} disabled={loading}>
                  {loading ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}
                  <span>{loading ? "Création en cours…" : "Créer cet espace"}</span>
                </button>
              </div>
            </div>
          </form>
        ) : (
          <>
            {/* Edit Mode Inline Drawer */}
            {isEditing && (
              <form onSubmit={handleUpdateTopic} style={{ padding: "1rem 1.5rem", background: "var(--bg-surface-header, #f8fafc)", borderBottom: "1px solid var(--border-color, #e2e8f0)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "60px 1fr 180px", gap: "0.75rem", marginBottom: "0.75rem" }}>
                  <input
                    type="text"
                    value={editIcon}
                    onChange={e => setEditIcon(e.target.value)}
                    maxLength={4}
                    className={styles.formInput}
                    style={{ textAlign: "center", fontSize: "1.2rem", padding: "0.5rem" }}
                  />
                  <input
                    type="text"
                    value={editTitle}
                    onChange={e => setEditTitle(e.target.value)}
                    required
                    className={styles.formInput}
                    placeholder="Titre de l'espace..."
                  />
                  <select
                    value={editType}
                    onChange={e => setEditType(e.target.value as TopicType)}
                    className={styles.formSelect}
                  >
                    {(Object.keys(TOPIC_TYPE_LABELS) as TopicType[]).map(k => (
                      <option key={k} value={k}>
                        {TOPIC_TYPE_LABELS[k].label}
                      </option>
                    ))}
                  </select>
                </div>
                <input
                  type="text"
                  value={editObjective}
                  onChange={e => setEditObjective(e.target.value)}
                  placeholder="Objectif du sujet..."
                  className={styles.formInput}
                  style={{ marginBottom: "0.75rem" }}
                />
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                  <button type="button" className={styles.secondaryButton} onClick={() => setIsEditing(false)}>
                    Annuler
                  </button>
                  <button type="submit" className={styles.primaryButton}>
                    Enregistrer les modifications
                  </button>
                </div>
              </form>
            )}

            {/* Navigation Tabs */}
            <nav className={styles.tabsBar} aria-label="Sections de l'espace">
              <button
                type="button"
                className={`${styles.tabButton} ${activeTab === "resume" ? styles.activeTab : ""}`}
                onClick={() => setActiveTab("resume")}
              >
                <Compass size={16} />
                <span>Synthèse & Reprise</span>
              </button>
              <button
                type="button"
                className={`${styles.tabButton} ${activeTab === "conversations" ? styles.activeTab : ""}`}
                onClick={() => setActiveTab("conversations")}
              >
                <MessageCircle size={16} />
                <span>Discussions ({topic?.conversations_count ?? 0})</span>
              </button>
              <button
                type="button"
                className={`${styles.tabButton} ${activeTab === "memories" ? styles.activeTab : ""}`}
                onClick={() => setActiveTab("memories")}
              >
                <Brain size={16} />
                <span>Mémoire & Savoirs ({topic?.memories_count ?? 0})</span>
              </button>
              <button
                type="button"
                className={`${styles.tabButton} ${activeTab === "resources" ? styles.activeTab : ""}`}
                onClick={() => setActiveTab("resources")}
              >
                <FolderArchive size={16} />
                <span>Ressources & Docs ({topic?.resources?.length ?? 0})</span>
              </button>
              <button
                type="button"
                className={`${styles.tabButton} ${activeTab === "events" ? styles.activeTab : ""}`}
                onClick={() => setActiveTab("events")}
              >
                <History size={16} />
                <span>Journal d&apos;activité ({topic?.events?.length ?? 0})</span>
              </button>
            </nav>

            {/* Tab 1: Synthèse & Reprise */}
            {activeTab === "resume" && topic && (
              <div className={styles.content}>
                {/* Hero Card : Point de reprise */}
                <div className={styles.resumeHeroCard}>
                  <div className={styles.resumeHeroHeader}>
                    <span className={styles.resumeHeroTitle}>
                      <Compass size={18} />
                      <span>Ton point de reprise</span>
                    </span>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-secondary, #64748b)" }}>
                      Synchronisé avec la dernière session
                    </span>
                  </div>

                  <p className={styles.resumeHeroText}>
                    {topic.current_resume_context || "Cet espace est prêt. Lancez votre première discussion pour amorcer la mémorisation et le suivi."}
                  </p>

                  {topic.suggested_next_step && (
                    <div className={styles.resumeNextStepBox}>
                      <Target size={16} style={{ color: "#2563eb", flexShrink: 0, marginTop: "0.15rem" }} />
                      <div>
                        <strong style={{ display: "block", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "#2563eb" }}>
                          Prochaine étape suggérée
                        </strong>
                        <span>{topic.suggested_next_step}</span>
                      </div>
                    </div>
                  )}

                  <div className={styles.resumeActionRow}>
                    <button
                      type="button"
                      className={styles.primaryButton}
                      onClick={() => {
                        onClose();
                        if (topic.conversations && topic.conversations.length > 0) {
                          onOpenConversation(topic.conversations[0].id);
                        } else {
                          onStartNewConversation(topic.id);
                        }
                      }}
                    >
                      <MessageSquarePlus size={16} />
                      <span>
                        {topic.conversations && topic.conversations.length > 0
                          ? "Reprendre la discussion"
                          : "Commencer une discussion"}
                      </span>
                    </button>
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      onClick={() => {
                        onClose();
                        onStartNewConversation(topic.id);
                      }}
                    >
                      <Plus size={15} />
                      <span>Nouvelle discussion dans cet espace</span>
                    </button>
                    {onOpenStudyModal && (
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        onClick={() => handleStartStudy(undefined, "all")}
                        title="S'entraîner avec les Flashcards 3D, le Quizz interactif et les Phrases à trous sur cet espace"
                      >
                        <GraduationCap size={15} />
                        <span>S&apos;entraîner (Quiz & Flashcards)</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Quick stats grid */}
                <div className={styles.statsGrid}>
                  <div className={styles.statCard}>
                    <span className={styles.statLabel}>Discussions</span>
                    <span className={styles.statValue}>{topic.conversations_count ?? 0}</span>
                  </div>
                  <div className={styles.statCard}>
                    <span className={styles.statLabel}>Souvenirs & Acquis</span>
                    <span className={styles.statValue}>{topic.memories_count ?? 0}</span>
                  </div>
                  <div className={styles.statCard}>
                    <span className={styles.statLabel}>Notions validées</span>
                    <span className={styles.statValue}>
                      {topic.memories?.filter(m => m.status === "validated").length ?? 0}
                    </span>
                  </div>
                  <div className={styles.statCard}>
                    <span className={styles.statLabel}>À renforcer</span>
                    <span className={styles.statValue}>
                      {topic.memories?.filter(m => m.status === "needs_review").length ?? 0}
                    </span>
                  </div>
                </div>

                {/* Didactic Notion Progress Bar */}
                {(() => {
                  const allMems = topic.memories?.filter(m => !m.is_archived) || [];
                  const total = allMems.length;
                  if (total === 0) return null;
                  const validated = allMems.filter(m => m.status === "validated").length;
                  const provisional = allMems.filter(m => m.status === "provisional_mastery").length;
                  const inProgress = allMems.filter(m => m.status === "in_progress").length;
                  const needsReview = allMems.filter(m => m.status === "needs_review").length;
                  const discussed = allMems.filter(m => m.status === "discussed").length;
                  const pctValidated = Math.round(((validated + provisional) / total) * 100);

                  return (
                    <div className={styles.progressCard}>
                      <div className={styles.progressHeader}>
                        <span className={styles.progressTitle}>
                          <Layers size={14} />
                          <span>Progression & Maîtrise ({pctValidated}% assimilés)</span>
                        </span>
                        <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary, #64748b)" }}>
                          {validated + provisional} sur {total} notion(s) acquise(s)
                        </span>
                      </div>

                      <div className={styles.progressBar}>
                        {validated > 0 && <div className={`${styles.progressSegment} ${styles.seg_validated}`} style={{ width: `${(validated / total) * 100}%` }} title={`Validé : ${validated}`} />}
                        {provisional > 0 && <div className={`${styles.progressSegment} ${styles.seg_provisional}`} style={{ width: `${(provisional / total) * 100}%` }} title={`Acquis provisoire : ${provisional}`} />}
                        {inProgress > 0 && <div className={`${styles.progressSegment} ${styles.seg_in_progress}`} style={{ width: `${(inProgress / total) * 100}%` }} title={`En cours : ${inProgress}`} />}
                        {needsReview > 0 && <div className={`${styles.progressSegment} ${styles.seg_needs_review}`} style={{ width: `${(needsReview / total) * 100}%` }} title={`À renforcer : ${needsReview}`} />}
                        {discussed > 0 && <div className={`${styles.progressSegment} ${styles.seg_discussed}`} style={{ width: `${(discussed / total) * 100}%` }} title={`Abordé : ${discussed}`} />}
                      </div>

                      <div className={styles.progressLegend}>
                        <div className={styles.legendItem}><span className={styles.legendDot} style={{ background: "#22c55e" }} /><span>Validé ({validated})</span></div>
                        <div className={styles.legendItem}><span className={styles.legendDot} style={{ background: "#0284c7" }} /><span>Acquis provisoire ({provisional})</span></div>
                        <div className={styles.legendItem}><span className={styles.legendDot} style={{ background: "#eab308" }} /><span>En cours ({inProgress})</span></div>
                        <div className={styles.legendItem}><span className={styles.legendDot} style={{ background: "#ef4444" }} /><span>À renforcer ({needsReview})</span></div>
                      </div>
                    </div>
                  );
                })()}

                {/* Review Alert Card */}
                {(() => {
                  const needsReviewMems = topic.memories?.filter(m => !m.is_archived && m.status === "needs_review") || [];
                  if (needsReviewMems.length === 0) return null;

                  return (
                    <div className={styles.reviewAlertCard}>
                      <div className={styles.reviewAlertHeader}>
                        <span className={styles.reviewAlertTitle}>
                          <CircleAlert size={16} />
                          <span>Difficultés identifiées à consolider ({needsReviewMems.length})</span>
                        </span>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          {onOpenStudyModal && (
                            <button
                              type="button"
                              className={styles.secondaryButton}
                              style={{ borderColor: "#fca5a5", color: "#991b1b", background: "#ffffff", padding: "0.4rem 0.8rem", fontSize: "0.775rem" }}
                              onClick={() => handleStartStudy(needsReviewMems, "all")}
                              title="S'entraîner avec Flashcards 3D, Quizz interactif et Phrases à trous sur ces difficultés"
                            >
                              <Sparkles size={14} />
                              <span>Flashcards & Quiz</span>
                            </button>
                          )}
                          <button
                            type="button"
                            className={styles.secondaryButton}
                            style={{ borderColor: "#fca5a5", color: "#991b1b", background: "#ffffff", padding: "0.4rem 0.8rem", fontSize: "0.775rem" }}
                            onClick={() => {
                              onClose();
                              const factsList = needsReviewMems.slice(0, 3).map(m => m.fact).join(" ; ");
                              const prompt = `Je souhaite réviser et faire des exercices ciblés pour consolider ces difficultés : ${factsList}. Peux-tu me proposer un petit test progressif ?`;
                              if (onStartCustomChat) {
                                onStartCustomChat(topic.id, prompt);
                              } else {
                                onStartNewConversation(topic.id);
                              }
                            }}
                          >
                            <GraduationCap size={14} />
                            <span>Révision tchat</span>
                          </button>
                        </div>
                      </div>
                      <ul className={styles.reviewAlertList}>
                        {needsReviewMems.slice(0, 3).map(m => (
                          <li key={m.id}>{m.fact}</li>
                        ))}
                      </ul>
                    </div>
                  );
                })()}

                {/* Project Tasks & Roadmap (for Project spaces) */}
                {topic.topic_type === "project" && (() => {
                  const projectMems = topic.memories?.filter(m => !m.is_archived) || [];
                  const tasks = projectMems.filter(m => m.category === "task");
                  const decisions = projectMems.filter(m => m.category === "decision" || m.category === "arch");
                  const doneCount = tasks.filter(t => t.status === "validated").length;

                  return (
                    <div className={styles.projectTrackerCard}>
                      <div className={styles.projectTrackerHeader}>
                        <span className={styles.projectTrackerTitle}>
                          <ListTodo size={16} />
                          <span>Feuille de route & Tâches ({doneCount}/{tasks.length} achevées)</span>
                        </span>
                      </div>

                      {tasks.length > 0 ? (
                        <ul className={styles.projectTaskList}>
                          {tasks.map(t => {
                            const isDone = t.status === "validated";
                            return (
                              <li key={t.id} className={styles.projectTaskItem}>
                                <button
                                  type="button"
                                  className={`${styles.projectTaskCheckbox} ${isDone ? styles.checked : ""}`}
                                  onClick={() => void handleToggleTaskDone(t)}
                                  title={isDone ? "Marquer comme à faire" : "Valider la tâche"}
                                >
                                  {isDone ? <CheckSquare size={17} /> : <Square size={17} />}
                                </button>
                                <span className={`${styles.projectTaskText} ${isDone ? styles.projectTaskDone : ""}`}>
                                  {t.fact}
                                </span>
                                <button
                                  type="button"
                                  className={styles.projectTaskDeleteBtn}
                                  onClick={() => void handleDeleteMemory(t.id)}
                                  title="Supprimer la tâche"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      ) : (
                        <p style={{ margin: 0, fontSize: "0.8rem", color: "var(--text-secondary, #64748b)" }}>
                          Aucune tâche définie. Ajoutez des jalons ou laissez l&apos;IA extraire les tâches lors des discussions.
                        </p>
                      )}

                      {decisions.length > 0 && (
                        <div style={{ marginTop: "0.5rem" }}>
                          <span style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", fontWeight: 700, color: "#6b21a8", marginBottom: "0.35rem" }}>
                            <Lightbulb size={13} />
                            <span>Décisions d&apos;architecture enregistrées ({decisions.length})</span>
                          </span>
                          <ul className={styles.projectTaskList}>
                            {decisions.map(d => (
                              <li key={d.id} className={styles.projectTaskItem}>
                                <span className={styles.projectDecisionBadge}>Décision</span>
                                <span className={styles.projectTaskText}>{d.fact}</span>
                                <button
                                  type="button"
                                  className={styles.projectTaskDeleteBtn}
                                  onClick={() => void handleDeleteMemory(d.id)}
                                  title="Supprimer la décision"
                                >
                                  <Trash2 size={13} />
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      <div className={styles.projectQuickAddForm}>
                        <input
                          type="text"
                          value={quickItemText}
                          onChange={e => setQuickItemText(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void handleQuickAddProjectItem("task");
                            }
                          }}
                          placeholder="Ajouter une tâche ou une décision..."
                          className={styles.projectQuickAddInput}
                        />
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          style={{ padding: "0.45rem 0.75rem", fontSize: "0.78rem" }}
                          disabled={!quickItemText.trim()}
                          onClick={() => void handleQuickAddProjectItem("task")}
                        >
                          <Plus size={13} />
                          <span>Tâche</span>
                        </button>
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          style={{ padding: "0.45rem 0.75rem", fontSize: "0.78rem" }}
                          disabled={!quickItemText.trim()}
                          onClick={() => void handleQuickAddProjectItem("decision")}
                        >
                          <Lightbulb size={13} />
                          <span>Décision</span>
                        </button>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}

            {/* Tab 2: Discussions */}
            {activeTab === "conversations" && topic && (
              <div className={styles.content}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary, #64748b)" }}>
                    Toutes les conversations de cet espace partagent la même mémoire continue et alimentent le point de reprise.
                  </p>
                  <button
                    type="button"
                    className={styles.primaryButton}
                    onClick={() => {
                      onClose();
                      onStartNewConversation(topic.id);
                    }}
                  >
                    <Plus size={15} />
                    <span>Nouvelle discussion</span>
                  </button>
                </div>

                {topic.conversations && topic.conversations.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    {topic.conversations.map(conv => (
                      <div
                        key={conv.id}
                        className={styles.memoryCard}
                        style={{ cursor: "pointer" }}
                        onClick={() => {
                          onClose();
                          onOpenConversation(conv.id);
                        }}
                      >
                        <div className={styles.memoryMain}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <MessageCircle size={16} style={{ color: "#2563eb" }} />
                            <strong>{conv.title}</strong>
                            {conv.theme && (
                              <span style={{ fontSize: "0.725rem", padding: "0.1rem 0.4rem", borderRadius: "4px", background: "rgba(0,0,0,0.06)" }}>
                                {conv.theme}
                              </span>
                            )}
                          </div>
                          {conv.summary && (
                            <p style={{ margin: "0.25rem 0 0", fontSize: "0.8rem", color: "var(--text-secondary, #64748b)" }}>
                              {conv.summary.slice(0, 160)}...
                            </p>
                          )}
                        </div>
                        <div className={styles.memoryActions} onClick={e => e.stopPropagation()}>
                          <button
                            type="button"
                            className={styles.iconBtn}
                            onClick={() => handleUnlinkConv(conv.id)}
                            title="Détacher de cet espace"
                          >
                            <Unlink size={15} />
                          </button>
                          <ChevronRight size={16} style={{ color: "#94a3b8" }} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className={styles.emptyBox}>
                    <MessageCircle size={32} />
                    <p className={styles.emptyTitle}>Aucune discussion pour le moment</p>
                    <p className={styles.emptyDesc}>
                      Démarrez une discussion pour enrichir cet espace thématique.
                    </p>
                    <button
                      type="button"
                      className={styles.primaryButton}
                      onClick={() => {
                        onClose();
                        onStartNewConversation(topic.id);
                      }}
                    >
                      <Plus size={15} />
                      <span>Commencer la première discussion</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: Mémoire & Savoirs */}
            {activeTab === "memories" && topic && (
              <div className={styles.content}>
                <div className={styles.memoriesHeader}>
                  <div className={styles.memoryFilterBar}>
                    <button
                      type="button"
                      className={`${styles.filterChip} ${memoryFilter === "all" ? styles.activeChip : ""}`}
                      onClick={() => setMemoryFilter("all")}
                    >
                      Tous ({topic.memories?.length ?? 0})
                    </button>
                    {(Object.keys(STATUS_CONFIG) as TopicMemoryStatus[]).map(stKey => {
                      const count = topic.memories?.filter(m => m.status === stKey).length ?? 0;
                      return (
                        <button
                          key={stKey}
                          type="button"
                          className={`${styles.filterChip} ${memoryFilter === stKey ? styles.activeChip : ""}`}
                          onClick={() => setMemoryFilter(stKey)}
                        >
                          {STATUS_CONFIG[stKey].label} ({count})
                        </button>
                      );
                    })}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    {onOpenStudyModal && (topic.memories?.length ?? 0) > 0 && (
                      <button
                        type="button"
                        className={styles.secondaryButton}
                        onClick={() => handleStartStudy(memoriesList, "all")}
                        title="S'entraîner avec Flashcards 3D, Quizz interactif et Phrases à trous sur ces notions"
                      >
                        <GraduationCap size={15} />
                        <span>S&apos;entraîner sur ces acquis</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      onClick={() => setIsAddingMemory(!isAddingMemory)}
                    >
                      <Plus size={15} />
                      <span>Ajouter un fait</span>
                    </button>
                  </div>
                </div>

                {/* Form to add memory manually */}
                {isAddingMemory && (
                  <form onSubmit={handleAddMemory} style={{ padding: "0.85rem", borderRadius: "0.5rem", border: "1px solid var(--border-color, #e2e8f0)", background: "var(--bg-surface-header, #f8fafc)", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                    <input
                      type="text"
                      value={memFact}
                      onChange={e => setMemFact(e.target.value)}
                      placeholder="Fait ou notion à mémoriser (ex. : Maîtrise la conjugaison au subjonctif)..."
                      required
                      className={styles.formInput}
                    />
                    <div style={{ display: "flex", gap: "0.75rem" }}>
                      <select
                        value={memStatus}
                        onChange={e => setMemStatus(e.target.value as TopicMemoryStatus)}
                        className={styles.formSelect}
                        style={{ flex: "0 0 auto", width: "auto" }}
                      >
                        {(Object.keys(STATUS_CONFIG) as TopicMemoryStatus[]).map(k => (
                          <option key={k} value={k}>
                            Statut : {STATUS_CONFIG[k].label}
                          </option>
                        ))}
                      </select>
                      <input
                        type="text"
                        value={memCategory}
                        onChange={e => setMemCategory(e.target.value)}
                        placeholder="Catégorie (grammar, task, decision...)"
                        className={styles.formInput}
                        style={{ flex: 1 }}
                      />
                      <button type="submit" className={styles.primaryButton}>
                        Ajouter
                      </button>
                    </div>
                  </form>
                )}

                {/* Memories list */}
                {memoriesList.length > 0 ? (
                  <div className={styles.memoriesContainer}>
                    {memoriesList.map(mem => (
                      <div key={mem.id} className={styles.memoryCard}>
                        <div className={styles.memoryMain}>
                          <div className={styles.memoryStatusRow}>
                            <button
                              type="button"
                              className={`${styles.statusPill} ${styles[`status_${mem.status}`]}`}
                              onClick={() => handleCycleStatus(mem)}
                              title="Cliquer pour faire évoluer le statut didactique"
                            >
                              {STATUS_CONFIG[mem.status]?.label || mem.status} ↻
                            </button>
                            {mem.category && (
                              <span className={styles.memoryCategory}>• {mem.category}</span>
                            )}
                          </div>
                          <p className={styles.memoryFact}>{mem.fact}</p>
                        </div>
                        <div className={styles.memoryActions}>
                          <button
                            type="button"
                            className={styles.iconBtn}
                            onClick={() => handleDeleteMemory(mem.id)}
                            title="Supprimer ce souvenir"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className={styles.emptyBox}>
                    <Brain size={32} />
                    <p className={styles.emptyTitle}>Aucun souvenir enregistré dans cette vue</p>
                    <p className={styles.emptyDesc}>
                      L&apos;IA extrait automatiquement les acquis et difficultés au fil des échanges. Vous pouvez aussi ajouter des souvenirs manuellement.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Tab: Ressources & Documents */}
            {activeTab === "resources" && topic && (() => {
              const allResources = topic.resources || [];
              const filteredResources = allResources.filter(r => {
                if (resourceFilter === "all") return true;
                return r.resource_type === resourceFilter;
              });
              const linksCount = allResources.filter(r => r.resource_type === "link").length;
              const docsCount = allResources.filter(r => r.resource_type === "document").length;
              const notesCount = allResources.filter(r => r.resource_type === "note").length;

              return (
                <div className={styles.content}>
                  <div className={styles.resourcesContainer}>
                    <div className={styles.memoriesHeader}>
                      <div className={styles.memoryFilterBar}>
                        <button
                          type="button"
                          className={`${styles.filterChip} ${resourceFilter === "all" ? styles.activeChip : ""}`}
                          onClick={() => setResourceFilter("all")}
                        >
                          Tous ({allResources.length})
                        </button>
                        <button
                          type="button"
                          className={`${styles.filterChip} ${resourceFilter === "link" ? styles.activeChip : ""}`}
                          onClick={() => setResourceFilter("link")}
                        >
                          🌐 Liens Web ({linksCount})
                        </button>
                        <button
                          type="button"
                          className={`${styles.filterChip} ${resourceFilter === "document" ? styles.activeChip : ""}`}
                          onClick={() => setResourceFilter("document")}
                        >
                          📄 Documents ({docsCount})
                        </button>
                        <button
                          type="button"
                          className={`${styles.filterChip} ${resourceFilter === "note" ? styles.activeChip : ""}`}
                          onClick={() => setResourceFilter("note")}
                        >
                          📝 Notes & Mémos ({notesCount})
                        </button>
                      </div>

                      <button
                        type="button"
                        className={styles.primaryButton}
                        onClick={() => setIsAddingResource(!isAddingResource)}
                      >
                        <Plus size={15} />
                        <span>{isAddingResource ? "Fermer" : "Ajouter une ressource"}</span>
                      </button>
                    </div>

                    {/* Inline Creation Form */}
                    {isAddingResource && (
                      <form
                        onSubmit={handleAddResource}
                        style={{
                          background: "var(--bg-surface-header, #f8fafc)",
                          border: "1px solid var(--border-color, #e2e8f0)",
                          borderRadius: "0.625rem",
                          padding: "1rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.75rem",
                        }}
                      >
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          {(
                            [
                              { key: "link", label: "🌐 Lien Web" },
                              { key: "document", label: "📄 Document / Fichier" },
                              { key: "note", label: "📝 Note / Fiche" },
                            ] as const
                          ).map(opt => (
                            <button
                              key={opt.key}
                              type="button"
                              onClick={() => setResType(opt.key)}
                              style={{
                                padding: "0.35rem 0.65rem",
                                borderRadius: "0.375rem",
                                fontSize: "0.78rem",
                                fontWeight: 600,
                                border: resType === opt.key ? "2px solid #2563eb" : "1px solid var(--border-color, #cbd5e1)",
                                background: resType === opt.key ? "rgba(37, 99, 235, 0.08)" : "transparent",
                                cursor: "pointer",
                              }}
                            >
                              {opt.label}
                            </button>
                          ))}
                        </div>

                        <div>
                          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                            Titre de la ressource *
                          </label>
                          <input
                            type="text"
                            value={resTitle}
                            onChange={e => setResTitle(e.target.value)}
                            placeholder="Ex : Documentation officielle, Fiche de révision du subjonctif..."
                            required
                            className={styles.formInput}
                          />
                        </div>

                        {resType === "link" && (
                          <div>
                            <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                              URL web
                            </label>
                            <input
                              type="url"
                              value={resUrl}
                              onChange={e => setResUrl(e.target.value)}
                              placeholder="https://..."
                              className={styles.formInput}
                            />
                          </div>
                        )}

                        <div>
                          <label style={{ display: "block", fontSize: "0.75rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                            {resType === "note" ? "Contenu de la note / aide-mémoire" : "Description ou extrait de contenu"}
                          </label>
                          <textarea
                            value={resContent}
                            onChange={e => setResContent(e.target.value)}
                            placeholder={resType === "note" ? "Rédigez ou collez vos notes, règles, mémos importants..." : "Courte description pour aider l'IA à situer cette ressource..."}
                            rows={3}
                            className={styles.formTextarea}
                          />
                        </div>

                        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.5rem" }}>
                          <button type="button" className={styles.secondaryButton} onClick={() => setIsAddingResource(false)}>
                            Annuler
                          </button>
                          <button type="submit" className={styles.primaryButton} disabled={!resTitle.trim()}>
                            <Plus size={15} />
                            <span>Enregistrer la ressource</span>
                          </button>
                        </div>
                      </form>
                    )}

                    {/* Resources List */}
                    {filteredResources.length > 0 ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
                        {filteredResources.map(res => {
                          const icon = res.resource_type === "link" ? <Globe size={18} /> : res.resource_type === "document" ? <FileText size={18} /> : <StickyNote size={18} />;
                          const typeLabel = res.resource_type === "link" ? "Lien" : res.resource_type === "document" ? "Document" : "Note";

                          return (
                            <div key={res.id} className={styles.resourceCard}>
                              <div className={`${styles.resourceIconWrap} ${styles[`resourceType_${res.resource_type}`]}`}>
                                {icon}
                              </div>

                              <div className={styles.resourceMain}>
                                <div className={styles.resourceHeaderRow}>
                                  <h4 className={styles.resourceTitle}>{res.title}</h4>
                                  <span className={styles.resourceTypeTag} style={{ background: "rgba(100, 116, 139, 0.1)", color: "var(--text-secondary, #64748b)" }}>
                                    {typeLabel}
                                  </span>
                                  <span style={{ fontSize: "0.7rem", color: "var(--text-secondary, #94a3b8)", marginLeft: "auto" }}>
                                    {new Date(res.created_at).toLocaleDateString("fr-FR")}
                                  </span>
                                </div>

                                {res.url && (
                                  <a
                                    href={res.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    style={{ fontSize: "0.78rem", color: "#2563eb", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.3rem", width: "fit-content" }}
                                  >
                                    <span>{res.url}</span>
                                    <ExternalLink size={12} />
                                  </a>
                                )}

                                {res.content && (
                                  <p className={styles.resourceDesc}>{res.content}</p>
                                )}
                              </div>

                              <div className={styles.resourceActions}>
                                {res.url && (
                                  <a
                                    href={res.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className={styles.resourceLinkAction}
                                    title="Ouvrir le lien"
                                  >
                                    <ExternalLink size={13} />
                                    <span>Ouvrir</span>
                                  </a>
                                )}
                                <button
                                  type="button"
                                  className={styles.iconBtn}
                                  onClick={() => handleDeleteResource(res.id)}
                                  title="Supprimer cette ressource"
                                >
                                  <Trash2 size={15} />
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className={styles.emptyBox}>
                        <FolderArchive size={32} />
                        <p className={styles.emptyTitle}>
                          Aucune ressource pour cet espace
                        </p>
                        <p className={styles.emptyDesc}>
                          Associez des fiches de cours, liens de documentation ou mémos pour que l&apos;IA puisse s&apos;y référer.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Tab 4: Journal d'activité */}
            {activeTab === "events" && topic && (
              <div className={styles.content}>
                <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--text-secondary, #64748b)" }}>
                  Chronologie factuelle des étapes franchies, exercices passés et décisions prises.
                </p>

                {topic.events && topic.events.length > 0 ? (
                  <div style={{ marginTop: "1rem" }}>
                    {topic.events.map(ev => (
                      <div key={ev.id} className={styles.eventItem}>
                        <div className={styles.eventBullet}>
                          <Check size={11} />
                        </div>
                        <div className={styles.eventContent}>
                          <span className={styles.eventTitle}>{ev.title}</span>
                          <span className={styles.eventDate}>
                            {new Date(ev.created_at).toLocaleDateString("fr-FR", {
                              day: "numeric",
                              month: "long",
                              year: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          {ev.details && Object.keys(ev.details).length > 0 && (
                            <div style={{ fontSize: "0.8rem", color: "var(--text-secondary, #64748b)", background: "rgba(0,0,0,0.03)", padding: "0.35rem 0.6rem", borderRadius: "4px", marginTop: "0.2rem" }}>
                              {Object.entries(ev.details).map(([k, v]) => (
                                <span key={k} style={{ marginRight: "0.75rem" }}>
                                  <strong>{k} :</strong> {String(v)}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className={styles.emptyBox}>
                    <History size={32} />
                    <p className={styles.emptyTitle}>Journal encore vide</p>
                    <p className={styles.emptyDesc}>
                      Les événements clés (résultats de quiz, décisions de projet, jalons) apparaîtront ici automatiquement.
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

