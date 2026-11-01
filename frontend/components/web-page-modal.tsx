"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronUp,
  Code2,
  Copy,
  Download,
  Eye,
  Globe,
  Globe2,
  History,
  Laptop,
  LoaderCircle,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  RefreshCw,
  Send,
  Settings2,
  Share2,
  Sliders,
  Smartphone,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import {
  createWebPage,
  deleteWebPage,
  errorMessage,
  fetchWebPage,
  fetchWebPages,
  refineWebPage,
  restoreWebPageVersion,
  updateWebPage,
  type Model,
  type WebPage,
  type WebPageVersion,
} from "@/lib/api";
import { ModelPickerModal } from "./model-picker-modal";
import styles from "./web-page-modal.module.css";

export type WebPageModalProps = {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: string | null;
  conversationTitle?: string | null;
  initialPrompt?: string;
  models?: Model[];
  currentModel?: string;
};

const SUGGESTIONS = [
  "Guide interactif sur le système solaire avec diagramme SVG et mini-quiz",
  "Synthèse visuelle sur la photosynthèse avec schéma des étapes et accordéons",
  "Fiche récapitulative cybersécurité : mots de passe, phishing et bonnes pratiques",
  "Tableau de bord interactif d'analyse avec graphiques SVG et sélecteur d'onglets",
];

const REFINE_CHIPS = [
  "Change les couleurs en bleu nuit et cyan",
  "Ajoute un quiz interactif de 3 questions",
  "Ajoute un schéma conceptuel en SVG",
  "Raccourcis l'introduction et résume en puces",
  "Ajoute une section Foire aux questions",
];

export const VISUAL_STYLES_LIST = [
  { id: "modern_clean", icon: "✨", name: "Moderne Épuré", desc: "Cartes SaaS contemporaines, ombres douces et bordures fines" },
  { id: "neobrutalism", icon: "⚡", name: "Néobrutalisme Pop", desc: "Bordures noires épaisses (2.5px), ombres franches sans flou" },
  { id: "glassmorphism", icon: "💎", name: "Glassmorphism", desc: "Effet verre dépoli, reflets lumineux et dégradés profonds" },
  { id: "notebook", icon: "📓", name: "Cahier d'écolier", desc: "Fond quadrillé, surlignage stabilo, post-it et fiches révision" },
  { id: "cyberpunk", icon: "🔮", name: "Cyberpunk & Terminal", desc: "Fond sombre OLED, néons cyan/magenta, police monospace" },
  { id: "editorial_newspaper", icon: "📰", name: "Presse & Journal", desc: "Typographie Serif prestigieuse (Georgia), lettrines et filets" },
  { id: "pastel_infographic", icon: "🎨", name: "Infographie Pastel", desc: "Teintes douces, formes très arrondies, chiffres géants didactiques" },
  { id: "minimal_mono", icon: "📐", name: "Minimaliste Suisse", desc: "Noir & blanc strict, géométrie pure et zéro distraction" },
  { id: "synthwave_retro", icon: "🌆", name: "Rétro 80s Synthwave", desc: "Coucher de soleil violet/rose, grille filaire et néons chauds" },
  { id: "nature_botanic", icon: "🌿", name: "Nature & Botanique", desc: "Vert sauge, lin naturel, teintes terreuses et esprit herbier" },
  { id: "playful_cartoon", icon: "🎈", name: "BD & Cartoon", desc: "Bulles de dialogue, contrastes joyeux et badges ludiques" },
];

export function WebPageModal({
  isOpen,
  onClose,
  conversationId,
  conversationTitle,
  initialPrompt,
  models,
  currentModel,
}: WebPageModalProps) {
  const [pages, setPages] = useState<WebPage[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<WebPage | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>(currentModel || "");

  useEffect(() => {
    if (currentModel) {
      setSelectedModel(currentModel);
    } else if (models && models.length > 0 && !selectedModel) {
      setSelectedModel(models[0].id);
    }
  }, [currentModel, models]);

  const [loading, setLoading] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Creation form state
  const [prompt, setPrompt] = useState(initialPrompt ?? "");
  const [title, setTitle] = useState("");
  const [useConversation, setUseConversation] = useState(Boolean(conversationId));
  const [pageType, setPageType] = useState<string>("auto");
  const [targetAudience, setTargetAudience] = useState<string>("general");
  const [creativeFreedom, setCreativeFreedom] = useState<"low" | "medium" | "high">("medium");
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [layoutStyle, setLayoutStyle] = useState<"tabs" | "single_page" | "print_sheet" | "auto">("auto");
  const [textDensity, setTextDensity] = useState<number>(5);
  const [interactivity, setInteractivity] = useState<"auto" | "high" | "none">("auto");
  const [includeQuiz, setIncludeQuiz] = useState<boolean>(true);
  const [includeSvg, setIncludeSvg] = useState<boolean>(true);
  const [themePalette, setThemePalette] = useState<string>("ocean");
  const [visualStyle, setVisualStyle] = useState<string>("auto");
  const [activePreset, setActivePreset] = useState<string>("auto");
  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);

  function applyPreset(presetId: string) {
    setActivePreset(presetId);
    if (presetId === "auto") {
      setPageType("auto");
      setTargetAudience("general");
      setCreativeFreedom("medium");
      setOrientation("portrait");
      setLayoutStyle("auto");
      setTextDensity(5);
      setInteractivity("auto");
      setIncludeSvg(true);
      setIncludeQuiz(true);
      setVisualStyle("auto");
    } else if (presetId === "revision") {
      setPageType("revision");
      setTargetAudience("school");
      setCreativeFreedom("medium");
      setOrientation("portrait");
      setLayoutStyle("tabs");
      setTextDensity(4);
      setInteractivity("high");
      setIncludeSvg(true);
      setIncludeQuiz(true);
      setVisualStyle("notebook");
    } else if (presetId === "article") {
      setPageType("article");
      setTargetAudience("general");
      setCreativeFreedom("medium");
      setOrientation("portrait");
      setLayoutStyle("single_page");
      setTextDensity(6);
      setInteractivity("none");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("editorial_newspaper");
    } else if (presetId === "interactive") {
      setPageType("didactic_sheet");
      setTargetAudience("general");
      setCreativeFreedom("high");
      setOrientation("portrait");
      setLayoutStyle("tabs");
      setTextDensity(5);
      setInteractivity("high");
      setIncludeSvg(true);
      setIncludeQuiz(true);
      setVisualStyle("modern_clean");
    } else if (presetId === "dashboard") {
      setPageType("dashboard");
      setTargetAudience("professional");
      setCreativeFreedom("medium");
      setOrientation("landscape");
      setLayoutStyle("single_page");
      setTextDensity(4);
      setInteractivity("high");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("modern_clean");
    }
  }

  // Workspace display controls
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [refineBarCollapsed, setRefineBarCollapsed] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [deviceMode, setDeviceMode] = useState<"desktop" | "mobile">("desktop");
  const [viewMode, setViewMode] = useState<"preview" | "code">("preview");
  const [copiedLink, setCopiedLink] = useState(false);
  const [copiedCode, setCopiedCode] = useState(false);
  const [refineInstruction, setRefineInstruction] = useState("");
  const [previewNonce, setPreviewNonce] = useState(0);

  // Load pages list on open
  useEffect(() => {
    if (!isOpen) return;
    void loadPages();
  }, [isOpen]);

  // When initialPrompt changes
  useEffect(() => {
    if (initialPrompt) {
      setPrompt(initialPrompt);
      setSelectedPageId(null);
    }
  }, [initialPrompt]);

  async function loadPages() {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWebPages();
      setPages(data);
      if (data.length > 0 && !selectedPageId && !initialPrompt) {
        await selectPage(data[0].id);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function selectPage(id: string) {
    setSelectedPageId(id);
    setSelectedVersionId(null);
    setWorking(true);
    setError(null);
    try {
      const full = await fetchWebPage(id);
      setSelectedPage(full);
      if (full.versions && full.versions.length > 0) {
        setSelectedVersionId(full.versions[0].id);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setWorking(false);
    }
  }

  // Active HTML document
  const activeHtml = useMemo(() => {
    if (!selectedPage) return "";
    if (selectedVersionId && selectedPage.versions) {
      const found = selectedPage.versions.find((v) => v.id === selectedVersionId);
      if (found?.html_content) return found.html_content;
    }
    return selectedPage.latest_html ?? "";
  }, [selectedPage, selectedVersionId]);

  // Handle page creation
  async function handleCreate(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!prompt.trim() && !useConversation) return;

    setWorking(true);
    setError(null);
    try {
      const created = await createWebPage({
        prompt: prompt.trim(),
        title: title.trim() || undefined,
        conversation_id: useConversation && conversationId ? conversationId : undefined,
        model: selectedModel || undefined,
        page_type: pageType,
        target_audience: targetAudience,
        creative_freedom: creativeFreedom,
        orientation: orientation,
        layout_style: layoutStyle,
        text_density: textDensity,
        interactivity: interactivity,
        include_quiz: includeQuiz,
        include_svg: includeSvg,
        theme_palette: themePalette,
        visual_style: visualStyle,
      });
      setPages((prev) => [created, ...prev]);
      setSelectedPageId(created.id);
      setSelectedPage(created);
      if (created.versions && created.versions.length > 0) {
        setSelectedVersionId(created.versions[0].id);
      }
      setPrompt("");
      setTitle("");
      setPreviewNonce((n) => n + 1);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setWorking(false);
    }
  }

  // Handle iterative refinement
  async function handleRefine(instructionText?: string) {
    const text = (instructionText || refineInstruction).trim();
    if (!text || !selectedPage) return;

    setWorking(true);
    setError(null);
    try {
      const updated = await refineWebPage(selectedPage.id, {
        instruction: text,
        model: selectedModel || undefined,
      });
      setSelectedPage(updated);
      if (updated.versions && updated.versions.length > 0) {
        setSelectedVersionId(updated.versions[0].id);
      }
      setPages((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setRefineInstruction("");
      setPreviewNonce((n) => n + 1);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setWorking(false);
    }
  }

  // Download standalone HTML file
  function handleDownloadHtml() {
    if (!activeHtml || !selectedPage) return;
    const blob = new Blob([activeHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedPage.slug || "page"}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  // Toggle publication
  async function handleTogglePublish() {
    if (!selectedPage) return;
    setWorking(true);
    setError(null);
    try {
      const nextStatus = !selectedPage.is_published;
      const updated = await updateWebPage(selectedPage.id, { is_published: nextStatus });
      setSelectedPage(updated);
      setPages((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setWorking(false);
    }
  }

  // Copy public link
  function handleCopyPublicUrl() {
    if (!selectedPage?.public_token) return;
    const url = `${window.location.origin}/p/${selectedPage.public_token}`;
    void navigator.clipboard.writeText(url);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2000);
  }

  // Copy HTML source
  function handleCopySourceCode() {
    if (!activeHtml) return;
    void navigator.clipboard.writeText(activeHtml);
    setCopiedCode(true);
    setTimeout(() => setCopiedCode(false), 2000);
  }

  // Delete page
  async function handleDeletePage() {
    if (!selectedPage) return;
    if (!window.confirm(`Supprimer définitivement la page « ${selectedPage.title} » ?`)) return;

    setWorking(true);
    try {
      await deleteWebPage(selectedPage.id);
      const remaining = pages.filter((p) => p.id !== selectedPage.id);
      setPages(remaining);
      if (remaining.length > 0) {
        void selectPage(remaining[0].id);
      } else {
        setSelectedPageId(null);
        setSelectedPage(null);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setWorking(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className={styles.backdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="web-pages-modal-title"
    >
      <div className={`${styles.modal} ${isMaximized ? styles.maximized : ""}`} onClick={(e) => e.stopPropagation()}>
        {/* Top Header */}
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <button
              type="button"
              className={styles.sidebarToggleBtn}
              onClick={() => setSidebarOpen((s) => !s)}
              title={sidebarOpen ? "Masquer la liste des pages" : "Afficher la liste des pages"}
              aria-label={sidebarOpen ? "Masquer la liste des pages" : "Afficher la liste des pages"}
            >
              {sidebarOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
            </button>
            <div className={styles.headerIcon}>
              <Globe size={18} />
            </div>
            <div className={styles.titleArea}>
              <h2 id="web-pages-modal-title" className={styles.headerTitle}>
                {selectedPage ? selectedPage.title : "cLAIr Pages"}
              </h2>
              <span className={styles.headerSubtitle}>
                <span>HTML5 + CSS3 + SVG + Vanilla JS</span>
                <span>·</span>
                <span style={{ color: "#10b981" }}>100% Autonome & Hors-ligne</span>
              </span>
            </div>
          </div>

          <div className={styles.headerControls}>
            {selectedPage && (
              <>
                {/* Device preview switcher */}
                <div className={styles.segmented} role="group" aria-label="Mode d'affichage">
                  <button
                    type="button"
                    className={`${styles.segmentedBtn} ${deviceMode === "desktop" ? styles.active : ""}`}
                    onClick={() => setDeviceMode("desktop")}
                    title="Vue Ordinateur (Responsive large)"
                  >
                    <Laptop size={13} />
                    <span>PC</span>
                  </button>
                  <button
                    type="button"
                    className={`${styles.segmentedBtn} ${deviceMode === "mobile" ? styles.active : ""}`}
                    onClick={() => setDeviceMode("mobile")}
                    title="Vue Smartphone (390px)"
                  >
                    <Smartphone size={13} />
                    <span>Mobile</span>
                  </button>
                </div>

                {/* View switcher (Preview vs Code) */}
                <div className={styles.segmented} role="group" aria-label="Aperçu ou Code">
                  <button
                    type="button"
                    className={`${styles.segmentedBtn} ${viewMode === "preview" ? styles.active : ""}`}
                    onClick={() => setViewMode("preview")}
                    title="Prévisualisation isolée"
                  >
                    <Eye size={13} />
                    <span>Aperçu</span>
                  </button>
                  <button
                    type="button"
                    className={`${styles.segmentedBtn} ${viewMode === "code" ? styles.active : ""}`}
                    onClick={() => setViewMode("code")}
                    title="Voir le code HTML source"
                  >
                    <Code2 size={13} />
                    <span>Code</span>
                  </button>
                </div>

                {/* Download button */}
                <button
                  type="button"
                  className={styles.btn}
                  onClick={handleDownloadHtml}
                  title="Télécharger le fichier .html autonome"
                >
                  <Download size={14} />
                  <span>Télécharger .html</span>
                </button>

                {/* Publish toggle & URL */}
                <button
                  type="button"
                  className={`${styles.btn} ${selectedPage.is_published ? styles.btnPublished : ""}`}
                  onClick={handleTogglePublish}
                  title={
                    selectedPage.is_published
                      ? "Page publiée en ligne (cliquez pour dépublier)"
                      : "Publier cette page pour lui attribuer une URL publique"
                  }
                >
                  <Globe2 size={14} />
                  <span>{selectedPage.is_published ? "Publiée" : "Publier"}</span>
                </button>

                {selectedPage.is_published && (
                  <button
                    type="button"
                    className={styles.btn}
                    onClick={handleCopyPublicUrl}
                    title="Copier le lien public"
                  >
                    {copiedLink ? <Check size={14} color="#10b981" /> : <Share2 size={14} />}
                    <span>{copiedLink ? "Lien copié !" : "Partager"}</span>
                  </button>
                )}

                {/* Reopen settings to regenerate */}
                <button
                  type="button"
                  className={styles.btn}
                  onClick={() => {
                    setPrompt(selectedPage.title);
                    setTitle(selectedPage.title);
                    setSelectedPageId(null);
                    setSelectedPage(null);
                  }}
                  title="Changer les paramètres ou régénérer une nouvelle version"
                >
                  <Settings2 size={13} />
                  <span>Réglages</span>
                </button>

                {/* Delete page */}
                <button
                  type="button"
                  className={styles.btn}
                  onClick={handleDeletePage}
                  title="Supprimer cette page"
                  style={{ color: "#ef4444" }}
                >
                  <Trash2 size={14} />
                </button>
              </>
            )}

            <button
              type="button"
              className={styles.iconBtn}
              onClick={() => setIsMaximized((m) => !m)}
              title={isMaximized ? "Réduire la fenêtre" : "Agrandir en plein écran"}
              aria-label={isMaximized ? "Réduire" : "Plein écran"}
            >
              {isMaximized ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
            </button>

            <button
              type="button"
              className={styles.iconBtn}
              onClick={onClose}
              aria-label="Fermer"
              title="Fermer"
            >
              <X size={17} />
            </button>
          </div>
        </header>

        {/* Modal Body */}
        <div className={styles.body}>
          {/* Sidebar */}
          <aside className={`${styles.sidebar} ${!sidebarOpen ? styles.collapsed : ""}`}>
            <div className={styles.sidebarHeader}>
              <button
                type="button"
                className={styles.newBtn}
                onClick={() => {
                  setSelectedPageId(null);
                  setSelectedPage(null);
                  setPrompt("");
                }}
              >
                <Plus size={16} />
                <span>Nouvelle Page Web</span>
              </button>
            </div>

            <ul className={styles.pageList}>
              {loading && (
                <li style={{ padding: "1rem", textAlign: "center", color: "#64748b" }}>
                  <LoaderCircle size={18} className="spin" style={{ margin: "0 auto" }} />
                </li>
              )}
              {!loading && pages.length === 0 && (
                <li className={styles.emptyState}>Aucune page créée pour le moment.</li>
              )}
              {pages.map((p) => {
                const isSelected = selectedPageId === p.id;
                return (
                  <li key={p.id} className={styles.pageItem}>
                    <button
                      type="button"
                      className={`${styles.pageItemBtn} ${isSelected ? styles.active : ""}`}
                      onClick={() => void selectPage(p.id)}
                    >
                      <div className={styles.pageItemTitle}>{p.title}</div>
                      <div className={styles.pageItemMeta}>
                        <span>v{p.latest_version_number || 1}</span>
                        {p.is_published && <span className={styles.pubPill}>Publiée</span>}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>

          {/* Main Area */}
          <section className={styles.workspace}>
            {error && (
              <div
                style={{
                  background: "rgba(239, 68, 68, 0.15)",
                  color: "#ef4444",
                  padding: "0.6rem 1rem",
                  fontSize: "0.85rem",
                  borderBottom: "1px solid rgba(239, 68, 68, 0.3)",
                }}
              >
                {error}
              </div>
            )}

            {!selectedPage ? (
              /* Creation View */
              <div className={styles.createView}>
                <div className={styles.createBox}>
                  <h3 className={styles.createTitle}>Concevoir une Page Web Autonome</h3>
                  <p className={styles.createDesc}>
                    Générez instantanément un document HTML5 moderne, sans compilation, avec illustrations
                    SVG inline, polices système et composants interactifs légers.
                  </p>

                  {/* UX Presets */}
                  <div className={styles.presetsRow}>
                    <button
                      type="button"
                      className={`${styles.presetBtn} ${activePreset === "auto" ? styles.active : ""}`}
                      onClick={() => applyPreset("auto")}
                    >
                      <span>⚡ Mode Automatique</span>
                    </button>
                    <button
                      type="button"
                      className={`${styles.presetBtn} ${activePreset === "revision" ? styles.active : ""}`}
                      onClick={() => applyPreset("revision")}
                    >
                      <span>🎯 Fiche de Révision</span>
                    </button>
                    <button
                      type="button"
                      className={`${styles.presetBtn} ${activePreset === "article" ? styles.active : ""}`}
                      onClick={() => applyPreset("article")}
                    >
                      <span>📰 Article Éditorial</span>
                    </button>
                    <button
                      type="button"
                      className={`${styles.presetBtn} ${activePreset === "interactive" ? styles.active : ""}`}
                      onClick={() => applyPreset("interactive")}
                    >
                      <span>🔬 Exploration Interactive</span>
                    </button>
                    <button
                      type="button"
                      className={`${styles.presetBtn} ${activePreset === "dashboard" ? styles.active : ""}`}
                      onClick={() => applyPreset("dashboard")}
                    >
                      <span>📊 Tableau de Bord</span>
                    </button>
                  </div>

                  <form onSubmit={handleCreate}>
                    {conversationId && (
                      <div className={styles.convSourceBanner}>
                        <div>
                          <strong>Conversation active :</strong> {conversationTitle || "Échange en cours"}
                        </div>
                        <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={useConversation}
                            onChange={(e) => setUseConversation(e.target.checked)}
                          />
                          <span>Inclure la synthèse du tchat</span>
                        </label>
                      </div>
                    )}

                    <div className={styles.formGroup}>
                      <label className={styles.label} htmlFor="page-topic-input">
                        Sujet, consigne ou question
                      </label>
                      <textarea
                        id="page-topic-input"
                        className={styles.textarea}
                        placeholder="Ex : Concevoir une page pédagogique et dynamique sur l'effet de serre, avec schéma SVG explicatif, bilan chiffré et quiz de validation..."
                        value={prompt}
                        onChange={(e) => setPrompt(e.target.value)}
                        disabled={working}
                      />
                      <div className={styles.suggestions}>
                        {SUGGESTIONS.map((sug, i) => (
                          <button
                            key={i}
                            type="button"
                            className={styles.suggestionChip}
                            onClick={() => setPrompt(sug)}
                          >
                            {sug}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className={styles.formGroup}>
                      <label className={styles.label} htmlFor="page-title-input">
                        Titre personnalisé (optionnel)
                      </label>
                      <input
                        id="page-title-input"
                        type="text"
                        className={styles.input}
                        placeholder="Laisser vide pour une attribution automatique par l'IA"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        disabled={working}
                      />
                    </div>

                    {/* Model Selector Trigger */}
                    {models && models.length > 0 && (
                      <div className={styles.formGroup}>
                        <label className={styles.label}>Modèle IA de génération</label>
                        <button
                          type="button"
                          className={styles.modelTriggerBtn}
                          onClick={() => setIsModelPickerOpen(true)}
                          disabled={working}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <Sparkles size={14} color="#0284c7" />
                            <span style={{ fontWeight: 600 }}>
                              {models.find((m) => m.id === selectedModel)?.name || selectedModel || "Sélectionner un modèle"}
                            </span>
                          </div>
                          <span className={styles.modelTriggerBadge}>Changer de modèle...</span>
                        </button>
                      </div>
                    )}

                    {/* Conception Options */}
                    <div className={styles.optionsBox}>
                      <div className={styles.optionsTitle}>
                        <Sliders size={14} />
                        <span>Réglages de conception</span>
                      </div>

                      {/* Row 1: Type de page & Public cible */}
                      <div className={styles.optionsColumns}>
                        <div>
                          <label className={styles.label}>Type de page</label>
                          <select
                            className={styles.selectInput}
                            value={pageType}
                            onChange={(e) => {
                              setPageType(e.target.value);
                              setActivePreset("custom");
                            }}
                          >
                            <option value="auto">✨ Détection automatique selon le sujet</option>
                            <option value="revision">🎯 Fiche de révision & mémos</option>
                            <option value="didactic_sheet">📑 Guide didactique structuré</option>
                            <option value="article">📰 Article de fond & format magazine</option>
                            <option value="dashboard">📊 Tableau de bord visuel & métriques</option>
                            <option value="report">📋 Rapport formel d'analyse</option>
                          </select>
                        </div>
                        <div>
                          <label className={styles.label}>Public cible</label>
                          <select
                            className={styles.selectInput}
                            value={targetAudience}
                            onChange={(e) => {
                              setTargetAudience(e.target.value);
                              setActivePreset("custom");
                            }}
                          >
                            <option value="general">🌍 Grand public curieux (accessible & captivant)</option>
                            <option value="school">🎒 Débutant & Scolaire (pédagogique, clair)</option>
                            <option value="academic">🎓 Étudiant & Académique (rigoureux, approfondi)</option>
                            <option value="professional">💼 Professionnel & Expert (concis, stratégique)</option>
                          </select>
                        </div>
                      </div>

                      {/* Row 2: Liberté créative (3 cartes) */}
                      <div style={{ marginBottom: "0.85rem" }}>
                        <div className={styles.sectionSubTitle}>
                          <span>Liberté créative :</span>
                          <span style={{ fontSize: "0.7rem", color: "#0284c7", fontWeight: 600 }}>
                            {creativeFreedom === "low"
                              ? "Faible (Sobre & prévisible)"
                              : creativeFreedom === "high"
                              ? "Élevée (Design expérimental & SVG)"
                              : "Moyenne (Compositions équilibrées)"}
                          </span>
                        </div>
                        <div className={styles.creativeGrid}>
                          <button
                            type="button"
                            className={`${styles.creativeCard} ${creativeFreedom === "low" ? styles.active : ""}`}
                            onClick={() => {
                              setCreativeFreedom("low");
                              setActivePreset("custom");
                            }}
                          >
                            <div className={styles.creativeCardTitle}>
                              <span>🛡️</span>
                              <span>Faible</span>
                            </div>
                            <div className={styles.creativeCardDesc}>
                              Sections classiques, sobre, disposition prévisible. Idéal rapports techniques.
                            </div>
                          </button>
                          <button
                            type="button"
                            className={`${styles.creativeCard} ${creativeFreedom === "medium" ? styles.active : ""}`}
                            onClick={() => {
                              setCreativeFreedom("medium");
                              setActivePreset("custom");
                            }}
                          >
                            <div className={styles.creativeCardTitle}>
                              <span>⚖️</span>
                              <span>Moyenne</span>
                            </div>
                            <div className={styles.creativeCardDesc}>
                              Compositions travaillées, schémas harmonieux et variations élégantes.
                            </div>
                          </button>
                          <button
                            type="button"
                            className={`${styles.creativeCard} ${creativeFreedom === "high" ? styles.active : ""}`}
                            onClick={() => {
                              setCreativeFreedom("high");
                              setActivePreset("custom");
                            }}
                          >
                            <div className={styles.creativeCardTitle}>
                              <span>🚀</span>
                              <span>Élevée</span>
                            </div>
                            <div className={styles.creativeCardDesc}>
                              Formes organiques, SVG immersifs, asymétrie et animations expressives.
                            </div>
                          </button>
                        </div>
                      </div>

                      {/* Row 3: Orientation & Interactivité */}
                      <div className={styles.optionsColumns}>
                        <div>
                          <label className={styles.label}>Orientation</label>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.4rem" }}>
                            <button
                              type="button"
                              className={`${styles.layoutCard} ${orientation === "portrait" ? styles.active : ""}`}
                              onClick={() => {
                                setOrientation("portrait");
                                setActivePreset("custom");
                              }}
                            >
                              <span className={styles.layoutCardTitle}>📱 Portrait</span>
                              <span className={styles.layoutCardDesc}>Lecture verticale (960px)</span>
                            </button>
                            <button
                              type="button"
                              className={`${styles.layoutCard} ${orientation === "landscape" ? styles.active : ""}`}
                              onClick={() => {
                                setOrientation("landscape");
                                setActivePreset("custom");
                              }}
                            >
                              <span className={styles.layoutCardTitle}>🖥️ Paysage</span>
                              <span className={styles.layoutCardDesc}>Écran large (1300px)</span>
                            </button>
                          </div>
                        </div>

                        <div>
                          <label className={styles.label}>Interactivité locale</label>
                          <select
                            className={styles.selectInput}
                            value={interactivity}
                            onChange={(e) => {
                              setInteractivity(e.target.value as any);
                              setActivePreset("custom");
                            }}
                          >
                            <option value="auto">⚡ Auto (JavaScript léger où pertinent)</option>
                            <option value="high">🎮 Forte (simulateurs, quiz, onglets)</option>
                            <option value="none">📄 Statique pure (zéro JS, lisible au repos)</option>
                          </select>

                          <div style={{ marginTop: "0.45rem" }}>
                            <label className={styles.label}>Mise en page</label>
                            <select
                              className={styles.selectInput}
                              value={layoutStyle}
                              onChange={(e) => {
                                setLayoutStyle(e.target.value as any);
                                setActivePreset("custom");
                              }}
                            >
                              <option value="auto">✨ Libre & optimisée pour le sujet</option>
                              <option value="tabs">📑 Onglets interactifs par section</option>
                              <option value="single_page">📜 Défilement continu</option>
                              <option value="print_sheet">🖨️ Fiche A4 (optimisée impression)</option>
                            </select>
                          </div>
                        </div>
                      </div>

                      {/* Row 4: Style Visuel */}
                      <div style={{ marginBottom: "0.85rem" }}>
                        <div className={styles.sectionSubTitle}>
                          <span>Style visuel & esthétique :</span>
                          <span style={{ fontSize: "0.7rem", color: "#0284c7", fontWeight: 600 }}>
                            {visualStyle === "auto" ? "✨ Auto-adapté" : VISUAL_STYLES_LIST.find((s) => s.id === visualStyle)?.name}
                          </span>
                        </div>
                        <select
                          className={styles.selectInput}
                          value={visualStyle}
                          onChange={(e) => {
                            setVisualStyle(e.target.value);
                            setActivePreset("custom");
                          }}
                          style={{ marginBottom: "0.45rem" }}
                        >
                          <option value="auto">✨ Auto-adapté à la tonalité du sujet</option>
                          {VISUAL_STYLES_LIST.map((st) => (
                            <option key={st.id} value={st.id}>
                              {st.icon} {st.name} — {st.desc}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Row 5: SVG Choice (Avec ou Sans SVG) */}
                      <div className={styles.styleSection}>
                        <div className={styles.sectionSubTitle}>
                          <span>Illustrations & Schémas SVG :</span>
                        </div>
                        <div className={styles.svgChoiceGrid}>
                          <button
                            type="button"
                            className={`${styles.svgChoiceCard} ${includeSvg ? styles.active : ""}`}
                            onClick={() => {
                              setIncludeSvg(true);
                              setActivePreset("custom");
                            }}
                          >
                            <span style={{ fontSize: "1.2rem" }}>🎨</span>
                            <div className={styles.svgChoiceText}>
                              <span className={styles.svgChoiceTitle}>Avec schémas SVG</span>
                              <span className={styles.svgChoiceSubtitle}>Frises, diagrammes ou graphiques selon le sujet</span>
                            </div>
                          </button>
                          <button
                            type="button"
                            className={`${styles.svgChoiceCard} ${!includeSvg ? styles.active : ""}`}
                            onClick={() => {
                              setIncludeSvg(false);
                              setActivePreset("custom");
                            }}
                          >
                            <span style={{ fontSize: "1.2rem" }}>📄</span>
                            <div className={styles.svgChoiceText}>
                              <span className={styles.svgChoiceTitle}>Sans SVG</span>
                              <span className={styles.svgChoiceSubtitle}>Pur texte, grilles denses et tableaux</span>
                            </div>
                          </button>
                        </div>
                      </div>

                      {/* Row 6: Densité du texte */}
                      <div className={styles.densityRow}>
                        <div className={styles.densityHeader}>
                          <span>Niveau de détail (Densité) :</span>
                          <span className={styles.densityBadge}>
                            {textDensity}/10 ·{" "}
                            {textDensity <= 3
                              ? "Synthétique & aéré (mots-clés, puces)"
                              : textDensity <= 7
                              ? "Équilibré & didactique"
                              : "Dense & approfondi (exhaustif)"}
                          </span>
                        </div>
                        <input
                          type="range"
                          min="1"
                          max="10"
                          step="1"
                          className={styles.rangeInput}
                          value={textDensity}
                          onChange={(e) => {
                            setTextDensity(Number(e.target.value));
                            setActivePreset("custom");
                          }}
                        />
                      </div>

                      {/* Row 7: Toggles Quiz & Palette */}
                      <div className={styles.togglesRow}>
                        <label className={styles.checkboxLabel}>
                          <input
                            type="checkbox"
                            checked={includeQuiz}
                            onChange={(e) => {
                              setIncludeQuiz(e.target.checked);
                              setActivePreset("custom");
                            }}
                          />
                          <span>Mini-quiz interactif de validation</span>
                        </label>
                      </div>

                      <div className={styles.paletteRow}>
                        <span>Palette de teintes :</span>
                        <div className={styles.paletteList}>
                          {[
                            { id: "ocean", label: "Océan", color: "#0284c7" },
                            { id: "emerald", label: "Émeraude", color: "#059669" },
                            { id: "sunset", label: "Sunset", color: "#ea580c" },
                            { id: "violet", label: "Violet", color: "#7c3aed" },
                            { id: "slate", label: "Ardoise", color: "#475569" },
                          ].map((pal) => (
                            <button
                              key={pal.id}
                              type="button"
                              className={`${styles.paletteBtn} ${themePalette === pal.id ? styles.active : ""}`}
                              style={{ backgroundColor: pal.color }}
                              onClick={() => setThemePalette(pal.id)}
                              title={pal.label}
                              aria-label={pal.label}
                            />
                          ))}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <button
                        type="submit"
                        className={`${styles.btn} ${styles.btnPrimary}`}
                        disabled={working || (!prompt.trim() && !useConversation)}
                      >
                        {working ? (
                          <>
                            <LoaderCircle size={15} className="spin" />
                            <span>Génération en cours...</span>
                          </>
                        ) : (
                          <>
                            <Sparkles size={15} />
                            <span>Générer la Page Web</span>
                          </>
                        )}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            ) : (
              /* Viewer & Workspace */
              <>
                <div className={styles.stage}>
                  {working && (
                    <div
                      style={{
                        position: "absolute",
                        top: "1rem",
                        right: "1.5rem",
                        zIndex: 20,
                        background: "rgba(15, 23, 42, 0.8)",
                        color: "#38bdf8",
                        padding: "0.4rem 0.8rem",
                        borderRadius: "8px",
                        fontSize: "0.8rem",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <LoaderCircle size={14} className="spin" />
                      <span>Actualisation par l'IA...</span>
                    </div>
                  )}

                  {viewMode === "preview" ? (
                    <div
                      className={
                        deviceMode === "desktop"
                          ? styles.stageFrameDesktop
                          : styles.stageFrameMobile
                      }
                    >
                      <iframe
                        key={`${selectedPage.id}-${selectedVersionId}-${previewNonce}`}
                        className={styles.iframe}
                        title={selectedPage.title}
                        sandbox="allow-scripts allow-forms allow-modals"
                        srcDoc={activeHtml}
                      />
                    </div>
                  ) : (
                    <div style={{ width: "100%", height: "100%", position: "relative" }}>
                      <div
                        style={{
                          position: "absolute",
                          top: "0.75rem",
                          right: "0.75rem",
                          zIndex: 10,
                        }}
                      >
                        <button
                          type="button"
                          className={styles.btn}
                          onClick={handleCopySourceCode}
                        >
                          {copiedCode ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                          <span>{copiedCode ? "Copié !" : "Copier le code"}</span>
                        </button>
                      </div>
                      <textarea
                        className={styles.codeArea}
                        value={activeHtml}
                        readOnly
                        spellCheck={false}
                      />
                    </div>
                  )}
                </div>

                {/* Bottom Refine & Version bar */}
                <div className={`${styles.refineBar} ${refineBarCollapsed ? styles.isCollapsed : ""}`}>
                  <div className={styles.refineMetaRow}>
                    <div className={styles.selectorsGroup}>
                      <button
                        type="button"
                        className={styles.collapseBarBtn}
                        onClick={() => setRefineBarCollapsed((c) => !c)}
                        title={
                          refineBarCollapsed
                            ? "Déplier les outils de modification IA"
                            : "Réduire pour maximiser la hauteur de l'aperçu"
                        }
                      >
                        {refineBarCollapsed ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                        <span>{refineBarCollapsed ? "Améliorer la page" : "Masquer la saisie"}</span>
                      </button>

                      <div className={styles.selectorItem}>
                        <History size={13} color="#64748b" />
                        <span>v:</span>
                        <select
                          id="version-picker"
                          className={styles.versionSelect}
                          value={selectedVersionId || ""}
                          onChange={(e) => setSelectedVersionId(e.target.value)}
                          title="Changer de version"
                        >
                          {(selectedPage.versions || []).map((v) => (
                            <option key={v.id} value={v.id}>
                              v{v.version_number} · {v.prompt_used.slice(0, 30)}
                            </option>
                          ))}
                        </select>
                      </div>

                      {models && models.length > 0 && !refineBarCollapsed && (
                        <div className={styles.selectorItem}>
                          <Sparkles size={13} color="#0284c7" />
                          <button
                            type="button"
                            className={styles.versionSelect}
                            onClick={() => setIsModelPickerOpen(true)}
                            disabled={working}
                            title="Changer de modèle IA"
                            style={{ textAlign: "left", cursor: "pointer" }}
                          >
                            {models.find((m) => m.id === selectedModel)?.name || selectedModel}
                          </button>
                        </div>
                      )}
                    </div>

                    {!refineBarCollapsed && (
                      <div className={styles.suggestionsScroll}>
                        {REFINE_CHIPS.map((chip, idx) => (
                          <button
                            key={idx}
                            type="button"
                            className={styles.suggestionChip}
                            onClick={() => void handleRefine(chip)}
                            disabled={working}
                          >
                            {chip}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {!refineBarCollapsed && (
                    <form
                      className={styles.refineForm}
                      onSubmit={(e) => {
                        e.preventDefault();
                        void handleRefine();
                      }}
                    >
                      <input
                        type="text"
                        className={styles.refineInput}
                        placeholder="Demandez une modification (ex: « Change les couleurs, ajoute un schéma SVG et raccourcis l'introduction »)..."
                        value={refineInstruction}
                        onChange={(e) => setRefineInstruction(e.target.value)}
                        disabled={working}
                      />
                      <button
                        type="submit"
                        className={`${styles.btn} ${styles.btnPrimary}`}
                        disabled={working || !refineInstruction.trim()}
                      >
                        {working ? <LoaderCircle size={14} className="spin" /> : <Send size={14} />}
                        <span>Améliorer</span>
                      </button>
                    </form>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      </div>

      {/* Dedicated Model Picker Modal */}
      {isModelPickerOpen && models && (
        <ModelPickerModal
          isOpen={isModelPickerOpen}
          onClose={() => setIsModelPickerOpen(false)}
          models={models}
          selectedModelId={selectedModel}
          onSelectModel={(id) => setSelectedModel(id)}
        />
      )}
    </div>
  );
}

