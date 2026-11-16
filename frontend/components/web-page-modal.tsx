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
  Image as ImageIcon,
  Laptop,
  LoaderCircle,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Printer,
  Puzzle,
  RefreshCw,
  Send,
  Settings2,
  Share2,
  Sliders,
  Smartphone,
  Sparkles,
  Star,
  Trash2,
  X,
} from "lucide-react";
import {
  createWebPage,
  deleteWebPage,
  errorMessage,
  executePageBrick,
  fetchWebPage,
  fetchWebPages,
  proposeWebPageTopics,
  refineWebPage,
  restoreWebPageVersion,
  updateWebPage,
  type Model,
  type PageBrick,
  type PageTopicItem,
  type WebPage,
  type WebPageVersion,
} from "@/lib/api";
import { buildBrickWiringPrompt, injectBrickIntoCanvasHtml } from "@/lib/canvas-bricks";
import type { CanvasFile } from "@/lib/code-canvas";
import { CanvasBricksModal } from "./canvas-bricks-modal";
import { ModelModal } from "./model-modal";
import { useModelFavorites } from "@/lib/model-favorites";
import { toJpeg, toPng } from "html-to-image";
import styles from "./web-page-modal.module.css";

export type WebPageModalProps = {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: string | null;
  conversationTitle?: string | null;
  initialPrompt?: string;
  initialTab?: "pages" | "apps";
  initialPageId?: string | null;
  models?: Model[];
  currentModel?: string;
  onRefreshModels?: () => Promise<void>;
  onOpenInCanvas?: (files: CanvasFile[], title: string, bricks: PageBrick[], pageId: string) => void;
};

export type PagePresetDef = {
  id: string;
  icon: string;
  label: string;
  badge?: string;
  hint: string;
};

export const PAGE_PRESETS: PagePresetDef[] = [
  {
    id: "auto",
    icon: "✨",
    label: "Mode Automatique",
    hint: "Adaptation libre au sujet",
  },
  {
    id: "a4_sheet_1p",
    icon: "📄",
    label: "Fiche A4 · 1 Page",
    badge: "Strict",
    hint: "1 seule feuille A4 portrait (210×297 mm) auto-calibrée, zéro débordement",
  },
  {
    id: "a4_sheet_2p",
    icon: "📑",
    label: "Fiche A4 · 2 Pages",
    badge: "Recto-Verso",
    hint: "Exactement 2 feuilles A4 complémentaires : théorie au recto, méthode & exemples au verso",
  },
  {
    id: "cheat_sheet",
    icon: "⚡",
    label: "Cheat Sheet A4",
    badge: "Paysage 1p",
    hint: "Antisèche 3 colonnes sur 1 page A4 paysage (297×210 mm) pour formules & commandes",
  },
  {
    id: "revision",
    icon: "🎯",
    label: "Révision Interactive",
    hint: "Exploration détaillée par onglets + style cahier d'écolier",
  },
  {
    id: "comparison",
    icon: "⚖️",
    label: "Comparatif & Benchmark",
    hint: "Tableau comparatif structuré, avantages/limites et matrice de choix",
  },
  {
    id: "timeline",
    icon: "⏳",
    label: "Frise & Processus",
    hint: "Chronologie ou méthodologie étape par étape avec diagramme SVG",
  },
  {
    id: "article",
    icon: "📰",
    label: "Article Éditorial",
    hint: "Mise en page magazine serif, lecture longue immersive",
  },
  {
    id: "dashboard",
    icon: "📊",
    label: "Tableau de Bord",
    hint: "KPI, graphiques SVG et grille large écran",
  },
];

const SUGGESTIONS = [
  "Guide interactif sur le système solaire avec diagramme SVG et fiches didactiques",
  "Synthèse visuelle sur la photosynthèse avec schéma des étapes et accordéons",
  "Fiche récapitulative cybersécurité : mots de passe, phishing et bonnes pratiques",
  "Tableau de bord interactif d'analyse avec graphiques SVG et sélecteur d'onglets",
];

const REFINE_CHIPS = [
  "Anime la page au scroll (AOS) et ajoute des transitions GSAP",
  "Change les couleurs en bleu nuit et cyan",
  "Détaille davantage chaque section avec des exemples concrets",
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
export const ANIMATION_ENGINES = [
  { id: "auto", icon: "✨", name: "Auto IA", desc: "L'IA choisit le dosage optimal" },
  { id: "both", icon: "🚀", name: "AOS + GSAP", desc: "Révélations au scroll + chorégraphies et compteurs" },
  { id: "aos", icon: "📜", name: "AOS Seul", desc: "Apparitions fluides et cascades au défilement" },
  { id: "gsap", icon: "⏱️", name: "GSAP Seul", desc: "Timelines, compteurs de chiffres et tracés SVG" },
  { id: "none", icon: "🛑", name: "Statique", desc: "Zéro animation (lecture sobre / impression)" },
];

export const FONT_FAMILIES_LIST = [
  { id: "auto", name: "Assortie au style", desc: "Police signature du style visuel" },
  { id: "outfit", name: "Outfit & Plus Jakarta", desc: "Géométrique, épuré & contemporain (SaaS)" },
  { id: "playfair", name: "Playfair & Lora (Serif)", desc: "Éditorial littéraire, lettrines prestigieuses" },
  { id: "space_grotesk", name: "Space Grotesk & Syne", desc: "Brutaliste, design affirmé & avant-garde" },
  { id: "fredoka", name: "Fredoka & Baloo 2", desc: "Ronde, douce, conviviale & ludique" },
  { id: "caveat", name: "Caveat & Patrick Hand", desc: "Manuscrite, carnet d'écolier & croquis" },
  { id: "jetbrains", name: "JetBrains Mono", desc: "Terminal informatique, console & code" },
  { id: "righteous", name: "Righteous & Orbitron", desc: "Rétro-futuriste, Synthwave & affichage" },
];

export const TEXT_EFFECTS_LIST = [
  { id: "charming_wave", icon: "🌊", name: "Ondulation cinétique", desc: "Vague animée lettre par lettre sur le titre" },
  { id: "charming_gradient", icon: "🌈", name: "Flux chromatique", desc: "Dégradé de couleur animé sur les mots-clés" },
  { id: "charming_bounce", icon: "🎈", name: "Rebond au survol", desc: "Lettres dynamiques et interactives à la souris" },
  { id: "pretext_fit", icon: "📐", name: "Titre monumental", desc: "Auto-ajustement plein cadre sans débordement" },
  { id: "curved_text", icon: "〰️", name: "Bandeau courbé SVG", desc: "Accroche sur courbe sinusoïdale organique" },
  { id: "gsap_counters", icon: "🔢", name: "Compteurs chiffrés", desc: "Défilement numérique animé des statistiques" },
];


export function WebPageModal({
  isOpen,
  onClose,
  conversationId,
  conversationTitle,
  initialPrompt,
  initialTab = "pages",
  initialPageId = null,
  models,
  currentModel,
  onRefreshModels,
  onOpenInCanvas,
}: WebPageModalProps) {
  const [pages, setPages] = useState<WebPage[]>([]);
  const [sidebarTab, setSidebarTab] = useState<"pages" | "apps">(initialTab);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<WebPage | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [bricksModalOpen, setBricksModalOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>(currentModel || "");
  const { isFavorite } = useModelFavorites("llm");

  useEffect(() => {
    if (currentModel) {
      setSelectedModel(currentModel);
    } else if (models && models.length > 0 && !selectedModel) {
      setSelectedModel(models[0].id);
    }
  }, [currentModel, models]);

  // Synchronize useConversation whenever conversationId changes or modal opens
  useEffect(() => {
    if (conversationId) {
      setUseConversation(true);
    }
  }, [conversationId, isOpen]);

  const [loading, setLoading] = useState(false);
  const [loadingPage, setLoadingPage] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Creation form state
  const [prompt, setPrompt] = useState(initialPrompt ?? "");
  const [title, setTitle] = useState("");
  const [useConversation, setUseConversation] = useState(Boolean(conversationId));
  const [pageType, setPageType] = useState<string>("auto");
  const [targetAudience, setTargetAudience] = useState<string>("general");
  const [authorPersona, setAuthorPersona] = useState<string>("");
  const [visualDescription, setVisualDescription] = useState<string>("");

  const [creativeFreedom, setCreativeFreedom] = useState<"low" | "medium" | "high">("medium");
  const [orientation, setOrientation] = useState<"portrait" | "landscape">("portrait");
  const [layoutStyle, setLayoutStyle] = useState<
    "tabs" | "single_page" | "print_sheet" | "a4_1p" | "a4_2p" | "cheat_sheet" | "auto"
  >("auto");
  const [textDensity, setTextDensity] = useState<number>(5);
  const [interactivity, setInteractivity] = useState<"auto" | "high" | "none">("auto");
  const [includeQuiz, setIncludeQuiz] = useState<boolean>(false);
  const [includeSvg, setIncludeSvg] = useState<boolean>(true);
  const [themePalette, setThemePalette] = useState<string>("ocean");
  const [visualStyle, setVisualStyle] = useState<string>("auto");
  const [activePreset, setActivePreset] = useState<string>("auto");
  const [animationEngine, setAnimationEngine] = useState<"auto" | "both" | "aos" | "gsap" | "none">("auto");
  const [fontFamily, setFontFamily] = useState<string>("auto");
  const [textEffects, setTextEffects] = useState<string[]>([]);

  const [isModelPickerOpen, setIsModelPickerOpen] = useState(false);

  const currentModelInfo = useMemo(
    () => (models || []).find((item) => item.id === selectedModel),
    [models, selectedModel]
  );

  const currentModelPriceTag = useMemo(() => {
    if (!currentModelInfo) return null;
    if (currentModelInfo.prompt_price_1m === 0) return "Gratuit";
    if (currentModelInfo.prompt_price_1m !== undefined) {
      const val = currentModelInfo.prompt_price_1m;
      return val < 0.01 ? "<$0.01/M" : val < 1 ? `$${val.toFixed(2)}/M` : `$${val.toFixed(1)}/M`;
    }
    return null;
  }, [currentModelInfo]);

  const isStrictA4Selected =
    layoutStyle === "a4_1p" ||
    layoutStyle === "print_sheet" ||
    layoutStyle === "a4_2p" ||
    layoutStyle === "cheat_sheet" ||
    pageType === "a4_revision_1p" ||
    pageType === "a4_revision_2p" ||
    pageType === "cheat_sheet";

  function renderUnifiedModelButton(variant: "header" | "full" | "compact" = "header") {
    const wrapVariantClass =
      variant === "full"
        ? styles.unifiedModelWrapFull
        : variant === "compact"
        ? styles.unifiedModelWrapCompact
        : styles.unifiedModelWrap;
    return (
      <div className={`model-select-wrap ${wrapVariantClass}`}>
        <button
          type="button"
          className="model-selector-btn"
          onClick={() => setIsModelPickerOpen(true)}
          disabled={working}
          title="Changer de modèle IA (voir tous les modèles, prix, contexte, vision)"
          aria-label="Changer de modèle IA"
        >
          <span className="model-indicator" />
          {selectedModel && isFavorite(selectedModel) && (
            <span className="model-topbar-pill favorite" title="Modèle favori">
              <Star size={11} fill="#f59e0b" color="#f59e0b" />
            </span>
          )}
          <span className="model-current-name">
            {currentModelInfo?.name || selectedModel || "Modèle IA"}
          </span>
          {currentModelInfo?.vision && (
            <span
              className="model-topbar-pill vision"
              title="Modèle multimodal avec vision (images acceptées)"
            >
              <Eye size={11} />
              <span>Vision</span>
            </span>
          )}
          {currentModelPriceTag && (
            <span
              className={`model-topbar-pill price ${
                currentModelPriceTag === "Gratuit" ? "is-free" : ""
              }`}
            >
              {currentModelPriceTag}
            </span>
          )}
          <ChevronDown size={14} className="model-chevron" />
        </button>
      </div>
    );
  }
  // Topics exploration modal state
  const [showTopicsModal, setShowTopicsModal] = useState(false);
  const [proposedTopics, setProposedTopics] = useState<PageTopicItem[]>([]);
  const [selectedTopicIds, setSelectedTopicIds] = useState<Set<string>>(new Set());
  const [proposedSummary, setProposedSummary] = useState("");
  const [loadingTopics, setLoadingTopics] = useState(false);
  const [customTopicInput, setCustomTopicInput] = useState("");
  const [topicCategoryFilter, setTopicCategoryFilter] = useState<string>("all");
  const [topicSearchQuery, setTopicSearchQuery] = useState<string>("");
  const [topicDetailLevels, setTopicDetailLevels] = useState<Record<string, number>>({});
  const [bulkDetailLevel, setBulkDetailLevel] = useState<number>(5);
  const [topicOutputFormats, setTopicOutputFormats] = useState<Record<string, "auto" | "text" | "list" | "table" | "cards" | "timeline">>({});
  const [bulkOutputFormat, setBulkOutputFormat] = useState<"auto" | "text" | "list" | "table" | "cards" | "timeline">("auto");


  // Categories derived from proposed topics
  const topicCategories = useMemo(() => {
    const cats = new Set<string>();
    proposedTopics.forEach((t) => {
      if (t.category) cats.add(t.category);
    });
    return Array.from(cats);
  }, [proposedTopics]);

  // Filtered topics according to category chip and search query
  const displayedTopics = useMemo(() => {
    return proposedTopics.filter((t) => {
      const matchCat = topicCategoryFilter === "all" || t.category === topicCategoryFilter;
      const matchSearch =
        !topicSearchQuery.trim() ||
        t.title.toLowerCase().includes(topicSearchQuery.toLowerCase()) ||
        t.description.toLowerCase().includes(topicSearchQuery.toLowerCase()) ||
        t.category.toLowerCase().includes(topicSearchQuery.toLowerCase());
      return matchCat && matchSearch;
    });
  }, [proposedTopics, topicCategoryFilter, topicSearchQuery]);


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
      setAnimationEngine("auto");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("auto");
      setBulkDetailLevel(5);
    } else if (presetId === "a4_sheet_1p") {
      setPageType("a4_revision_1p");
      setTargetAudience("academic");
      setCreativeFreedom("low");
      setOrientation("portrait");
      setLayoutStyle("a4_1p");
      setTextDensity(2);
      setInteractivity("none");
      setAnimationEngine("none");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("notebook");
      setBulkDetailLevel(2);
    } else if (presetId === "a4_sheet_2p") {
      setPageType("a4_revision_2p");
      setTargetAudience("academic");
      setCreativeFreedom("low");
      setOrientation("portrait");
      setLayoutStyle("a4_2p");
      setTextDensity(3);
      setInteractivity("none");
      setAnimationEngine("none");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("modern_clean");
      setBulkDetailLevel(3);
    } else if (presetId === "cheat_sheet") {
      setPageType("cheat_sheet");
      setTargetAudience("professional");
      setCreativeFreedom("low");
      setOrientation("landscape");
      setLayoutStyle("cheat_sheet");
      setTextDensity(2);
      setInteractivity("none");
      setAnimationEngine("none");
      setIncludeSvg(false);
      setIncludeQuiz(false);
      setVisualStyle("modern_clean");
      setBulkDetailLevel(2);
    } else if (presetId === "revision") {
      setPageType("revision");
      setTargetAudience("school");
      setCreativeFreedom("medium");
      setOrientation("portrait");
      setLayoutStyle("tabs");
      setTextDensity(5);
      setInteractivity("high");
      setAnimationEngine("auto");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("notebook");
      setBulkDetailLevel(5);
    } else if (presetId === "comparison") {
      setPageType("comparison");
      setTargetAudience("general");
      setCreativeFreedom("medium");
      setOrientation("landscape");
      setLayoutStyle("single_page");
      setTextDensity(5);
      setInteractivity("auto");
      setAnimationEngine("auto");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("modern_clean");
      setBulkDetailLevel(5);
    } else if (presetId === "timeline") {
      setPageType("timeline");
      setTargetAudience("general");
      setCreativeFreedom("medium");
      setOrientation("portrait");
      setLayoutStyle("single_page");
      setTextDensity(4);
      setInteractivity("auto");
      setAnimationEngine("aos");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("pastel_infographic");
      setBulkDetailLevel(4);
    } else if (presetId === "article") {
      setPageType("article");
      setTargetAudience("general");
      setCreativeFreedom("medium");
      setOrientation("portrait");
      setLayoutStyle("single_page");
      setTextDensity(6);
      setInteractivity("none");
      setAnimationEngine("none");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("editorial_newspaper");
      setBulkDetailLevel(6);
    } else if (presetId === "interactive") {
      setPageType("didactic_sheet");
      setTargetAudience("general");
      setCreativeFreedom("high");
      setOrientation("portrait");
      setLayoutStyle("tabs");
      setTextDensity(5);
      setInteractivity("high");
      setAnimationEngine("both");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("modern_clean");
      setBulkDetailLevel(5);
    } else if (presetId === "dashboard") {
      setPageType("dashboard");
      setTargetAudience("professional");
      setCreativeFreedom("medium");
      setOrientation("landscape");
      setLayoutStyle("single_page");
      setTextDensity(4);
      setInteractivity("high");
      setAnimationEngine("auto");
      setIncludeSvg(true);
      setIncludeQuiz(false);
      setVisualStyle("modern_clean");
      setBulkDetailLevel(4);
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
  const [isExportingImage, setIsExportingImage] = useState(false);
  const [showImageExportMenu, setShowImageExportMenu] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const imageExportMenuRef = useRef<HTMLDivElement>(null);

  // Click outside listener for image export menu
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        imageExportMenuRef.current &&
        !imageExportMenuRef.current.contains(event.target as Node)
      ) {
        setShowImageExportMenu(false);
      }
    }
    if (showImageExportMenu) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showImageExportMenu]);

  // Load pages list on open
  useEffect(() => {
    if (!isOpen) return;
    if (initialTab) setSidebarTab(initialTab);
    void loadPages(initialPageId);
  }, [isOpen, initialTab, initialPageId]);

  // Listen for CLAIR_BRICK_CALL postMessage from the app iframe
  useEffect(() => {
    if (!isOpen) return;
    function handleBrickMessage(event: MessageEvent) {
      const data = event.data as {
        type?: string;
        requestId?: string;
        brickId?: string;
        inputs?: Record<string, unknown>;
      } | null;
      if (!data || data.type !== "CLAIR_BRICK_CALL" || !data.requestId) return;
      const iframeWin = iframeRef.current?.contentWindow;
      if (!iframeWin || event.source !== iframeWin) return;
      if (!selectedPage) return;

      void executePageBrick({
        page_id: selectedPage.id,
        brick_id: data.brickId,
        inputs: data.inputs ?? {},
        model: selectedModel || undefined,
      })
        .then((result) => {
          iframeWin.postMessage(
            { type: "CLAIR_BRICK_RESULT", requestId: data.requestId, ok: true, result },
            "*",
          );
        })
        .catch((err) => {
          iframeWin.postMessage(
            { type: "CLAIR_BRICK_RESULT", requestId: data.requestId, ok: false, error: errorMessage(err) },
            "*",
          );
        });
    }

    window.addEventListener("message", handleBrickMessage);
    return () => window.removeEventListener("message", handleBrickMessage);
  }, [isOpen, selectedPage, selectedModel]);

  // When initialPrompt changes
  useEffect(() => {
    if (initialPrompt) {
      setPrompt(initialPrompt);
      setSelectedPageId(null);
    }
  }, [initialPrompt]);

  const pageItems = useMemo(
    () => pages.filter((p) => (p.kind || "page") !== "app"),
    [pages],
  );
  const appItems = useMemo(
    () => pages.filter((p) => p.kind === "app"),
    [pages],
  );
  const displayedSidebarItems = sidebarTab === "apps" ? appItems : pageItems;

  async function loadPages(targetPageId?: string | null) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWebPages();
      setPages(data);
      if (targetPageId) {
        const found = data.find((p) => p.id === targetPageId);
        if (found) {
          setSidebarTab(found.kind === "app" ? "apps" : "pages");
        }
        await selectPage(targetPageId);
        return;
      }
      // Only auto-select existing page if there is NO conversation context and NO initialPrompt
      if (data.length > 0 && !selectedPageId && !initialPrompt && !conversationId) {
        const preferred =
          (initialTab === "apps"
            ? data.find((p) => p.kind === "app")
            : data.find((p) => (p.kind || "page") !== "app")) ?? data[0];
        await selectPage(preferred.id);
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
    setLoadingPage(true);
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
      setLoadingPage(false);
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

  // Trigger topic exploration before generation
  async function handleExploreTopics(e?: FormEvent) {
    if (e) e.preventDefault();
    if (!prompt.trim() && !useConversation) return;

    setLoadingTopics(true);
    setError(null);
    try {
      const res = await proposeWebPageTopics({
        prompt: prompt.trim(),
        title: title.trim() || undefined,
        conversation_id: useConversation && conversationId ? conversationId : undefined,
        page_type: pageType,
        target_audience: targetAudience,
        author_persona: authorPersona.trim() || undefined,
        visual_description: visualDescription.trim() || undefined,
        layout_style: layoutStyle,
        model: selectedModel || undefined,
      });

      if (!title.trim() && res.suggested_title) {
        setTitle(res.suggested_title);
      }
      setProposedSummary(res.summary || "");
      setProposedTopics(res.topics || []);

      // Initialize default detail level and output format for each topic
      const fallbackLvl =
        layoutStyle === "a4_1p" || layoutStyle === "print_sheet" || layoutStyle === "cheat_sheet"
          ? 2
          : layoutStyle === "a4_2p"
          ? 3
          : 5;
      setBulkDetailLevel(fallbackLvl);
      const initialLevels: Record<string, number> = {};
      const initialFormats: Record<string, "auto" | "text" | "list" | "table" | "cards" | "timeline"> = {};
      (res.topics || []).forEach((t) => {
        initialLevels[t.id] = t.detail_level || fallbackLvl;
        initialFormats[t.id] = (t.output_format as any) || "auto";
      });
      setTopicDetailLevels(initialLevels);
      setTopicOutputFormats(initialFormats);

      // Auto-select recommended topics, or all if none recommended
      const rec = new Set<string>();
      (res.topics || []).forEach((t) => {
        if (t.recommended) rec.add(t.id);
      });
      if (rec.size === 0) {
        (res.topics || []).forEach((t) => rec.add(t.id));
      }
      setSelectedTopicIds(rec);
      setShowTopicsModal(true);
    } catch (err) {
      setError("Impossible d'explorer les thèmes : " + errorMessage(err));
    } finally {
      setLoadingTopics(false);
    }
  }

  // Handle page creation with optional selected topics
  async function handleCreate(topicsToInclude?: PageTopicItem[]) {
    if (!prompt.trim() && !useConversation) return;

    setShowTopicsModal(false);
    setWorking(true);
    setError(null);
    try {
      const created = await createWebPage({
        prompt: prompt.trim(),
        title: title.trim() || undefined,
        conversation_id: useConversation && conversationId ? conversationId : undefined,
        model: selectedModel || undefined,
        kind: sidebarTab === "apps" ? "app" : "page",
        page_type: pageType,
        target_audience: targetAudience,
        author_persona: authorPersona.trim() || undefined,
        visual_description: visualDescription.trim() || undefined,
        creative_freedom: creativeFreedom,
        orientation: orientation,
        layout_style: layoutStyle,
        text_density: textDensity,
        interactivity: interactivity,
        include_quiz: includeQuiz,
        include_svg: includeSvg,
        theme_palette: themePalette,
        visual_style: visualStyle,
        animation_engine: animationEngine,
        font_family: fontFamily,
        text_effects: textEffects,
        selected_topics: topicsToInclude && topicsToInclude.length > 0 ? topicsToInclude : undefined,
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

  // Helper to toggle a topic selection
  function toggleTopicSelection(topicId: string) {
    setSelectedTopicIds((prev) => {
      const next = new Set(prev);
      if (next.has(topicId)) {
        next.delete(topicId);
      } else {
        next.add(topicId);
      }
      return next;
    });
  }

  // Add custom user-defined topic to proposed topics list
  function handleAddCustomTopic() {
    const trimmed = customTopicInput.trim();
    if (!trimmed) return;
    const newId = `custom-${Date.now()}`;
    const newTopic: PageTopicItem = {
      id: newId,
      title: trimmed,
      description: "Thème sur-mesure ajouté par vos soins.",
      category: "Personnalisé",
      recommended: true,
      detail_level: bulkDetailLevel || 5,
    };
    setProposedTopics((prev) => [newTopic, ...prev]);
    setSelectedTopicIds((prev) => new Set(prev).add(newId));
    setTopicDetailLevels((prev) => ({ ...prev, [newId]: bulkDetailLevel || 5 }));
    setCustomTopicInput("");
  }

  // Adjust detail level for a specific topic
  function handleSetTopicDetail(topicId: string, level: number) {
    setTopicDetailLevels((prev) => ({
      ...prev,
      [topicId]: Math.max(1, Math.min(10, level)),
    }));
  }

  // Apply a bulk detail level to all proposed topics
  function handleApplyBulkDetailLevel(level: number) {
    const clamped = Math.max(1, Math.min(10, level));
    setBulkDetailLevel(clamped);
    setTopicDetailLevels((prev) => {
      const updated: Record<string, number> = {};
      proposedTopics.forEach((t) => {
        updated[t.id] = clamped;
      });
      return updated;
    });
  }

  // Adjust output format for a specific topic
  function handleSetTopicFormat(topicId: string, format: "auto" | "text" | "list" | "table" | "cards" | "timeline") {
    setTopicOutputFormats((prev) => ({
      ...prev,
      [topicId]: format,
    }));
  }

  // Apply a bulk output format to all proposed topics
  function handleApplyBulkFormat(format: "auto" | "text" | "list" | "table" | "cards" | "timeline") {
    setBulkOutputFormat(format);
    setTopicOutputFormats((prev) => {
      const updated: Record<string, "auto" | "text" | "list" | "table" | "cards" | "timeline"> = {};
      proposedTopics.forEach((t) => {
        updated[t.id] = format;
      });
      return updated;
    });
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
    const htmlToDownload = activeHtml || selectedPage?.latest_html || "";
    if (!htmlToDownload || !selectedPage) return;
    const blob = new Blob([htmlToDownload], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${selectedPage.slug || "page"}.html`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  // Print rendered page cleanly (preserves @page A4 rules)
  function handlePrintPage() {
    const win = iframeRef.current?.contentWindow;
    if (!win) {
      setError("L'aperçu de la page n'est pas encore prêt pour l'impression.");
      return;
    }
    win.focus();
    win.print();
  }

  // Export rendered page as PNG or JPEG image
  async function handleExportImage(format: "png" | "jpeg" = "png") {
    if (!selectedPage || !activeHtml) return;
    setIsExportingImage(true);
    setShowImageExportMenu(false);
    setError(null);

    try {
      const iframe = iframeRef.current;
      const doc = iframe?.contentDocument;
      if (!doc || !doc.body) {
        throw new Error("L'aperçu de la page n'est pas encore prêt pour l'export.");
      }

      // Extract accessible @font-face rules safely without triggering SecurityError on cross-origin stylesheets
      let safeFontEmbedCSS = "";
      try {
        const styleSheets = Array.from(doc.styleSheets || []);
        for (const sheet of styleSheets) {
          try {
            const rules = sheet.cssRules || sheet.rules;
            if (!rules) continue;
            for (let i = 0; i < rules.length; i++) {
              const rule = rules[i];
              if (rule && rule.type === CSSRule.FONT_FACE_RULE) {
                safeFontEmbedCSS += rule.cssText + "\n";
              }
            }
          } catch {
            // Ignore SecurityError on cross-origin / CDN stylesheets (Google Fonts, FontAwesome, etc.)
          }
        }
      } catch {
        // Ignore errors accessing doc.styleSheets
      }

      const a4Sheets = Array.from(doc.querySelectorAll(".a4-sheet")) as HTMLElement[];
      const captureTarget: HTMLElement = a4Sheets.length === 1 ? a4Sheets[0] : doc.body;

      const contentWidth =
        a4Sheets.length === 1
          ? Math.max(captureTarget.scrollWidth, captureTarget.offsetWidth)
          : Math.max(
              doc.body.scrollWidth,
              doc.documentElement.scrollWidth,
              doc.body.offsetWidth,
              deviceMode === "mobile" ? 390 : 1024
            );
      const contentHeight =
        a4Sheets.length === 1
          ? Math.max(captureTarget.scrollHeight, captureTarget.offsetHeight)
          : Math.max(
              doc.body.scrollHeight,
              doc.documentElement.scrollHeight,
              doc.body.offsetHeight,
              600
            );

      const maxDimension = 8192;
      const pixelRatio = (contentHeight * 2 > maxDimension || contentWidth * 2 > maxDimension) ? 1 : 2;

      const baseOptions = {
        pixelRatio,
        width: contentWidth,
        height: contentHeight,
        skipFonts: true,
        fontEmbedCSS: safeFontEmbedCSS.trim() ? safeFontEmbedCSS : undefined,
        imagePlaceholder: "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'/%3E",
        filter: (node: HTMLElement) => {
          if (node.classList && node.classList.contains("no-print")) {
            return false;
          }
          return true;
        },
      };

      let dataUrl: string;
      try {
        if (format === "jpeg") {
          dataUrl = await toJpeg(captureTarget, { ...baseOptions, quality: 0.92, backgroundColor: "#0f172a" });
        } else {
          dataUrl = await toPng(captureTarget, baseOptions);
        }
      } catch (firstErr) {
        console.warn("Primary image export failed, retrying with minimalist fallback options...", firstErr);
        const fallbackOptions = {
          ...baseOptions,
          fontEmbedCSS: undefined,
          pixelRatio: 1,
        };
        if (format === "jpeg") {
          dataUrl = await toJpeg(captureTarget, { ...fallbackOptions, quality: 0.88, backgroundColor: "#0f172a" });
        } else {
          dataUrl = await toPng(captureTarget, fallbackOptions);
        }
      }

      const filename = `${selectedPage.slug || "page"}.${format === "jpeg" ? "jpg" : "png"}`;
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      console.error("Export image error:", err);
      setError("Erreur lors de l'export d'image : " + errorMessage(err));
    } finally {
      setIsExportingImage(false);
    }
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
            {models && models.length > 0 && renderUnifiedModelButton("header")}

            {/* Create new page action available directly from top bar */}
            <button
              type="button"
              className={`${styles.btn} ${!selectedPage ? styles.btnPrimary : ""}`}
              onClick={() => {
                setSelectedPageId(null);
                setSelectedPage(null);
                setPrompt("");
                setTitle("");
                if (conversationId) setUseConversation(true);
              }}
              title="Créer une nouvelle page autonome"
            >
              <Plus size={14} />
              <span>Nouvelle page</span>
            </button>

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

                {/* Print / PDF button */}
                <button
                  type="button"
                  className={styles.btn}
                  onClick={handlePrintPage}
                  disabled={viewMode !== "preview"}
                  title="Imprimer ou enregistrer en PDF (respecte la mise en page A4)"
                >
                  <Printer size={14} />
                  <span>Imprimer / PDF</span>
                </button>

                {/* Download button */}
                <button
                  type="button"
                  className={styles.btn}
                  onClick={handleDownloadHtml}
                  disabled={!activeHtml && !selectedPage?.latest_html}
                  title="Télécharger le fichier .html autonome"
                >
                  <Download size={14} />
                  <span>Télécharger .html</span>
                </button>

                {/* Export Image button & dropdown */}
                <div style={{ position: "relative" }} ref={imageExportMenuRef}>
                  <button
                    type="button"
                    className={styles.btn}
                    onClick={() => setShowImageExportMenu((v) => !v)}
                    disabled={isExportingImage}
                    title="Exporter la page sous forme d'image (PNG Haute Définition ou JPEG)"
                  >
                    {isExportingImage ? (
                      <LoaderCircle size={13} className="spin" />
                    ) : (
                      <ImageIcon size={13} />
                    )}
                    <span>{isExportingImage ? "Export..." : "Image"}</span>
                    <ChevronDown size={11} />
                  </button>

                  {showImageExportMenu && (
                    <div
                      style={{
                        position: "absolute",
                        top: "calc(100% + 5px)",
                        right: 0,
                        zIndex: 60,
                        backgroundColor: "var(--bg-surface, #ffffff)",
                        border: "1px solid var(--border-color, #cbd5e1)",
                        borderRadius: "8px",
                        boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.25)",
                        minWidth: "210px",
                        padding: "0.35rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.2rem",
                      }}
                    >
                      <button
                        type="button"
                        className={styles.btn}
                        style={{ width: "100%", justifyContent: "flex-start", border: "none" }}
                        onClick={() => void handleExportImage("png")}
                      >
                        <ImageIcon size={13} color="#0284c7" />
                        <span>PNG Haute Définition (x2)</span>
                      </button>
                      <button
                        type="button"
                        className={styles.btn}
                        style={{ width: "100%", justifyContent: "flex-start", border: "none" }}
                        onClick={() => void handleExportImage("jpeg")}
                      >
                        <ImageIcon size={13} color="#ea580c" />
                        <span>JPEG Web compressé</span>
                      </button>
                    </div>
                  )}
                </div>

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
                  onClick={() => setBricksModalOpen(true)}
                  title="Configurer les briques préfaites et agents IA attachés à cette page/application"
                >
                  <Puzzle size={13} />
                  <span>
                    Briques IA
                    {(selectedPage.bricks?.length || 0) > 0
                      ? ` (${selectedPage.bricks?.length})`
                      : ""}
                  </span>
                </button>

                {onOpenInCanvas &&
                  ((selectedPage.latest_canvas_files?.length || 0) > 0 ||
                    selectedPage.kind === "app") && (
                    <button
                      type="button"
                      className={styles.btn}
                      onClick={() => {
                        const files: CanvasFile[] =
                          selectedPage.latest_canvas_files &&
                          selectedPage.latest_canvas_files.length > 0
                            ? selectedPage.latest_canvas_files.map((f) => ({
                                path: f.path,
                                language: f.language || "text",
                                content: f.content,
                              }))
                            : [
                                {
                                  path: "index.html",
                                  language: "html",
                                  content: activeHtml || selectedPage.latest_html || "",
                                },
                              ];
                        onOpenInCanvas(
                          files,
                          selectedPage.title,
                          selectedPage.bricks || [],
                          selectedPage.id,
                        );
                        onClose();
                      }}
                      title="Ouvrir le code source multi-fichiers dans le Code Canvas"
                    >
                      <Code2 size={13} />
                      <span>Ouvrir dans Canvas</span>
                    </button>
                  )}

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
              <div className={styles.sidebarTabs} role="tablist" aria-label="Filtrer par type">
                <button
                  type="button"
                  role="tab"
                  aria-selected={sidebarTab === "pages"}
                  className={`${styles.sidebarTabBtn} ${sidebarTab === "pages" ? styles.active : ""}`}
                  onClick={() => setSidebarTab("pages")}
                >
                  <span>📄 Mes Pages ({pageItems.length})</span>
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={sidebarTab === "apps"}
                  className={`${styles.sidebarTabBtn} ${sidebarTab === "apps" ? styles.active : ""}`}
                  onClick={() => setSidebarTab("apps")}
                >
                  <span>🧩 Mes Apps ({appItems.length})</span>
                </button>
              </div>
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
                <span>{sidebarTab === "apps" ? "Nouvelle Page / App" : "Nouvelle Page Web"}</span>
              </button>
            </div>

            <ul className={styles.pageList}>
              {loading && (
                <li style={{ padding: "1rem", textAlign: "center", color: "#64748b" }}>
                  <LoaderCircle size={18} className="spin" style={{ margin: "0 auto" }} />
                </li>
              )}
              {!loading && displayedSidebarItems.length === 0 && (
                <li className={styles.emptyState}>
                  {sidebarTab === "apps"
                    ? "Aucune application Canvas intégrée pour le moment. Ouvrez le Code Canvas puis cliquez sur « Intégrer à Mes Apps »."
                    : "Aucune page créée pour le moment."}
                </li>
              )}
              {displayedSidebarItems.map((p) => {
                const isSelected = selectedPageId === p.id;
                const bricksCount = p.bricks?.length || 0;
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
                        {bricksCount > 0 && (
                          <span className={styles.appBrickPill}>🧩 {bricksCount}</span>
                        )}
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
                    {PAGE_PRESETS.map((preset) => (
                      <button
                        key={preset.id}
                        type="button"
                        className={`${styles.presetBtn} ${preset.badge ? styles.presetBtnStrict : ""} ${
                          activePreset === preset.id ? styles.active : ""
                        }`}
                        onClick={() => applyPreset(preset.id)}
                        title={preset.hint}
                      >
                        <span>
                          {preset.icon} {preset.label}
                        </span>
                        {preset.badge && (
                          <span className={styles.presetBadgeStrict}>{preset.badge}</span>
                        )}
                      </button>
                    ))}
                  </div>

                  {isStrictA4Selected && (
                    <div className={styles.a4ConstraintBanner}>
                      <span style={{ fontSize: "1rem", lineHeight: 1.2 }}>📐</span>
                      <div>
                        <strong>
                          {layoutStyle === "a4_2p" || pageType === "a4_revision_2p"
                            ? "Gabarit A4 Recto-Verso strict (exactement 2 pages)"
                            : layoutStyle === "cheat_sheet" || pageType === "cheat_sheet"
                            ? "Gabarit Cheat Sheet A4 Paysage strict (1 seule page)"
                            : "Gabarit Fiche A4 strict (1 seule page garantie)"}
                        </strong>{" "}
                        — Budget de texte plafonné, grille multi-colonnes sans onglets cachés et calibrage géométrique
                        automatique pour empêcher tout débordement sur plusieurs pages.
                      </div>
                    </div>
                  )}

                  <form onSubmit={handleExploreTopics}>
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
                    {/* Author Persona / Plume & Style */}
                    <div className={styles.formGroup}>
                      <label className={styles.label} htmlFor="author-persona-input">
                        Qui rédige la page ? (Auteur, plume ou persona)
                      </label>
                      <input
                        id="author-persona-input"
                        type="text"
                        className={styles.input}
                        placeholder="Ex : Émile Zola, Un prof de français au lycée, Un vulgarisateur scientifique passionné..."
                        value={authorPersona}
                        onChange={(e) => setAuthorPersona(e.target.value)}
                        disabled={working}
                      />
                    </div>

                    {/* Visual Description & Custom Atmosphere */}
                    <div className={styles.formGroup}>
                      <label className={styles.label} htmlFor="visual-desc-input">
                        Décris la page (Ambiance visuelle & Couleurs libres)
                      </label>
                      <input
                        id="visual-desc-input"
                        type="text"
                        className={styles.input}
                        placeholder="Ex : Très coloré en rouge et vert, Noir et blanc minimaliste, Ambiance parchemin ancien..."
                        value={visualDescription}
                        onChange={(e) => setVisualDescription(e.target.value)}
                        disabled={working}
                      />
                    </div>

                    {models && models.length > 0 && (
                      <div className={styles.formGroup}>
                        <label className={styles.label}>Modèle IA de génération</label>
                        {renderUnifiedModelButton("full")}
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
                            <option value="a4_revision_1p">📄 Fiche de révision A4 · 1 Page stricte</option>
                            <option value="a4_revision_2p">📑 Fiche de révision A4 · Recto-Verso (2 pages)</option>
                            <option value="cheat_sheet">⚡ Cheat Sheet / Antisèche A4 Paysage</option>
                            <option value="revision">🎯 Fiche de révision interactive (multi-onglets)</option>
                            <option value="comparison">⚖️ Comparatif & Benchmark structuré</option>
                            <option value="timeline">⏳ Frise chronologique & Processus</option>
                            <option value="didactic_sheet">📘 Guide didactique structuré</option>
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
                              <option value="a4_1p">📄 Fiche A4 stricte (1 seule page)</option>
                              <option value="a4_2p">📑 Fiche A4 Recto-Verso (2 pages max)</option>
                              <option value="cheat_sheet">⚡ Cheat Sheet A4 Paysage (1 page)</option>
                              <option value="tabs">📑 Onglets interactifs par section</option>
                              <option value="single_page">📜 Défilement continu</option>
                              <option value="print_sheet">🖨️ Fiche imprimable (A4 1 page)</option>
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

                      {/* Row 7: Palette */}
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
                      {/* Row 8: Moteur d'Animation (AOS & GSAP) */}
                      <div style={{ marginTop: "0.85rem", marginBottom: "0.85rem" }}>
                        <label className={styles.label}>Chorégraphie & Moteur d&apos;animation</label>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.4rem" }}>
                          {ANIMATION_ENGINES.map((eng) => (
                            <button
                              key={eng.id}
                              type="button"
                              className={`${styles.creativeCard} ${animationEngine === eng.id ? styles.active : ""}`}
                              onClick={() => {
                                setAnimationEngine(eng.id as any);
                                setActivePreset("custom");
                              }}
                              style={{ padding: "0.45rem" }}
                            >
                              <div className={styles.creativeCardTitle}>
                                <span>{eng.icon}</span>
                                <span>{eng.name}</span>
                              </div>
                              <div className={styles.creativeCardDesc} style={{ fontSize: "0.62rem" }}>
                                {eng.desc}
                              </div>
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Row 9: Police d'écriture (Google Fonts) */}
                      <div style={{ marginBottom: "0.85rem" }}>
                        <label className={styles.label}>Police d&apos;écriture (Google Fonts)</label>
                        <select
                          className={styles.selectInput}
                          value={fontFamily}
                          onChange={(e) => {
                            setFontFamily(e.target.value);
                            setActivePreset("custom");
                          }}
                        >
                          {FONT_FAMILIES_LIST.map((f) => (
                            <option key={f.id} value={f.id}>
                              {f.name} — {f.desc}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Row 10: Effets typographiques et visuels (Charming, Pretext, xsvg, compteurs) */}
                      <div style={{ marginBottom: "0.85rem" }}>
                        <label className={styles.label}>Effets visuels & typographiques activés</label>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "0.35rem" }}>
                          {TEXT_EFFECTS_LIST.map((eff) => {
                            const isChecked = textEffects.includes(eff.id);
                            return (
                              <button
                                key={eff.id}
                                type="button"
                                className={`${styles.effectChip} ${isChecked ? styles.active : ""}`}
                                onClick={() => {
                                  setTextEffects((prev) =>
                                    isChecked ? prev.filter((id) => id !== eff.id) : [...prev, eff.id]
                                  );
                                  setActivePreset("custom");
                                }}
                              >
                                <span style={{ fontSize: "0.95rem" }}>{eff.icon}</span>
                                <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                                  <span style={{ fontWeight: 600, fontSize: "0.72rem" }}>{eff.name}</span>
                                  <span style={{ fontSize: "0.6rem", opacity: 0.75, lineHeight: 1.15 }}>{eff.desc}</span>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
                      <button
                        type="button"
                        className={styles.btn}
                        disabled={working || loadingTopics || (!prompt.trim() && !useConversation)}
                        onClick={() => void handleCreate()}
                        title="Générer directement la page sans passer par la sélection de thèmes"
                      >
                        <span>Génération directe</span>
                      </button>
                      <button
                        type="submit"
                        className={`${styles.btn} ${styles.btnPrimary}`}
                        disabled={working || loadingTopics || (!prompt.trim() && !useConversation)}
                      >
                        {loadingTopics ? (
                          <>
                            <LoaderCircle size={15} className="spin" />
                            <span>Exploration des thèmes...</span>
                          </>
                        ) : working ? (
                          <>
                            <LoaderCircle size={15} className="spin" />
                            <span>Génération en cours...</span>
                          </>
                        ) : (
                          <>
                            <Sparkles size={15} />
                            <span>Explorer les thèmes & Générer</span>
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
                  {(working || loadingPage) && (
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
                      <span>{loadingPage ? "Chargement de la page..." : "Actualisation par l'IA..."}</span>
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
                        ref={iframeRef}
                        key={`${selectedPage.id}-${selectedVersionId}-${previewNonce}`}
                        className={styles.iframe}
                        title={selectedPage.title}
                        sandbox="allow-scripts allow-forms allow-modals allow-same-origin"
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

                      {models && models.length > 0 && !refineBarCollapsed && renderUnifiedModelButton("compact")}
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

            {/* Topics Selection Modal */}
      {showTopicsModal && (
        <div
          className={styles.topicsOverlay}
          onClick={(e) => {
            if (e.target === e.currentTarget && !working) {
              setShowTopicsModal(false);
            }
          }}
        >
          <div className={styles.topicsModal} role="dialog" aria-modal="true" aria-labelledby="topics-modal-title">
            <div className={styles.topicsHeader}>
              <div className={styles.topicsTitleWrap}>
                <div className={styles.topicsIconBadge}>
                  <Sparkles size={20} />
                </div>
                <div>
                  <h3 id="topics-modal-title" className={styles.topicsMainTitle}>
                    Thèmes d&apos;exploration : {title || prompt.slice(0, 45)}
                  </h3>
                  <p className={styles.topicsSubtitle}>
                    {proposedSummary ||
                      "L'agent a balayé large pour identifier tous les angles possibles. Cochez les sujets à intégrer dans votre page."}
                  </p>
                </div>
              </div>
              <button
                type="button"
                className={styles.topicsCloseBtn}
                onClick={() => setShowTopicsModal(false)}
                disabled={working}
                aria-label="Fermer la modale"
              >
                <X size={18} />
              </button>
            </div>

            <div className={styles.topicsToolbar}>
              <div className={styles.topicsCounter}>
                <Check size={14} />
                <span>
                  {selectedTopicIds.size} / {proposedTopics.length} thème{selectedTopicIds.size > 1 ? "s" : ""} sélectionné{selectedTopicIds.size > 1 ? "s" : ""}
                </span>
              </div>
              {models && models.length > 0 && renderUnifiedModelButton("compact")}
              <div className={styles.topicsActionLinks}>
                <button
                  type="button"
                  className={styles.topicsLinkBtn}
                  onClick={() => {
                    const allIds = new Set(proposedTopics.map((t) => t.id));
                    setSelectedTopicIds(allIds);
                  }}
                  disabled={working}
                >
                  Tout cocher
                </button>
                <button
                  type="button"
                  className={styles.topicsLinkBtn}
                  onClick={() => {
                    const rec = new Set<string>();
                    proposedTopics.forEach((t) => {
                      if (t.recommended) rec.add(t.id);
                    });
                    setSelectedTopicIds(rec);
                  }}
                  disabled={working}
                >
                  Sélection recommandée
                </button>
                <button
                  type="button"
                  className={styles.topicsLinkBtn}
                  onClick={() => setSelectedTopicIds(new Set())}
                  disabled={working}
                >
                  Tout désélectionner
                </button>
                <button
                  type="button"
                  className={styles.topicsLinkBtn}
                  onClick={(e) => void handleExploreTopics(e)}
                  disabled={working || loadingTopics}
                  title="Demander à l'IA d'autres suggestions"
                >
                  {loadingTopics ? <LoaderCircle size={11} className="spin" /> : <RefreshCw size={11} />}
                  <span>Relancer</span>
                </button>
              </div>

              {/* Bulk Detail Level Slider */}
              <div className={styles.bulkDetailBar} title="Règle d'un coup le niveau de détail de base pour tous les thèmes">
                <span>Niveau global :</span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={bulkDetailLevel}
                  onChange={(e) => handleApplyBulkDetailLevel(Number(e.target.value))}
                  style={{ width: "90px", accentColor: "#0284c7" }}
                />
                <span style={{ fontWeight: 700, color: "#0284c7", minWidth: "32px" }}>{bulkDetailLevel}/10</span>
                <span style={{ fontSize: "0.66rem", opacity: 0.8 }}>
                  {bulkDetailLevel >= 7 ? "(35-50 lignes/thème)" : bulkDetailLevel >= 4 ? "(≥20 lignes/thème)" : "(15 lignes/thème)"}
                </span>
              </div>
            </div>
              {/* Bulk Output Format Selector */}
              <div className={styles.bulkDetailBar} title="Appliquer un formatage de sortie à tous les thèmes">
                <span>Format global :</span>
                <select
                  className={styles.bulkFormatSelect}
                  value={bulkOutputFormat}
                  onChange={(e) => handleApplyBulkFormat(e.target.value as any)}
                >
                  <option value="auto">✨ Auto IA</option>
                  <option value="text">📝 Texte rédigé</option>
                  <option value="list">📋 Liste / Checklist</option>
                  <option value="table">📊 Tableau comparatif</option>
                  <option value="cards">🗂️ Cartes modulaires</option>
                  <option value="timeline">⏳ Étapes / Timeline</option>
                </select>
              </div>


            <div className={styles.topicsBody}>
              {/* Source conversation rappel dans la modale */}
              {conversationId && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "0.5rem 0.85rem",
                    borderRadius: "8px",
                    background: "rgba(2, 132, 199, 0.08)",
                    border: "1px solid rgba(2, 132, 199, 0.25)",
                    fontSize: "0.78rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", minWidth: 0 }}>
                    <span style={{ color: "#0284c7", fontWeight: 700 }}>Conversation liée :</span>
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {conversationTitle || "Échange actif"}
              {/* Quick Persona & Visual Description inputs in Modal */}
              <div className={styles.topicsPersonaRow}>
                <div className={styles.topicsPersonaInputWrap}>
                  <label className={styles.topicsPersonaLabel} htmlFor="modal-author-persona">
                    ✍️ Qui rédige la page ? (Auteur / Persona)
                  </label>
                  <input
                    id="modal-author-persona"
                    type="text"
                    className={styles.topicsPersonaInput}
                    placeholder="Ex: Émile Zola, Un prof de français, Un vulgarisateur..."
                    value={authorPersona}
                    onChange={(e) => setAuthorPersona(e.target.value)}
                  />
                </div>
                <div className={styles.topicsPersonaInputWrap}>
                  <label className={styles.topicsPersonaLabel} htmlFor="modal-visual-desc">
                    🎨 Décris la page (Ambiance & Couleurs libres)
                  </label>
                  <input
                    id="modal-visual-desc"
                    type="text"
                    className={styles.topicsPersonaInput}
                    placeholder="Ex: Très coloré rouge et vert, Noir et blanc minimaliste..."
                    value={visualDescription}
                    onChange={(e) => setVisualDescription(e.target.value)}
                  />
                </div>
              </div>

                    </span>
                  </div>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer", fontWeight: 600, color: "#0284c7" }}>
                    <input
                      type="checkbox"
                      checked={useConversation}
                      onChange={(e) => setUseConversation(e.target.checked)}
                    />
                    <span>Inclure les échanges du tchat</span>
                  </label>
                </div>
              )}
              {/* Category Filter Chips & Search Bar */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", flexWrap: "wrap" }}>
                <div className={styles.categoryFilterRow}>
                  <button
                    type="button"
                    className={`${styles.categoryFilterChip} ${topicCategoryFilter === "all" ? styles.active : ""}`}
                    onClick={() => setTopicCategoryFilter("all")}
                  >
                    Toutes ({proposedTopics.length})
                  </button>
                  {topicCategories.map((cat) => {
                    const countInCat = proposedTopics.filter((t) => t.category === cat).length;
                    return (
                      <button
                        key={cat}
                        type="button"
                        className={`${styles.categoryFilterChip} ${topicCategoryFilter === cat ? styles.active : ""}`}
                        onClick={() => setTopicCategoryFilter(cat)}
                      >
                        {cat} ({countInCat})
                      </button>
                    );
                  })}
                </div>
                <input
                  type="text"
                  className={styles.topicSearchInput}
                  placeholder="Filtrer les thèmes..."
                  value={topicSearchQuery}
                  onChange={(e) => setTopicSearchQuery(e.target.value)}
                />
              </div>

              {/* Add custom topic on the fly */}
              <div className={styles.customTopicBar}>
                <Plus size={16} color="#0284c7" />
                <input
                  type="text"
                  className={styles.customTopicInput}
                  placeholder="Ajouter un thème personnalisé..."
                  value={customTopicInput}
                  onChange={(e) => setCustomTopicInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddCustomTopic();
                    }
                  }}
                  disabled={working}
                />
                <button
                  type="button"
                  className={styles.topicsLinkBtn}
                  onClick={handleAddCustomTopic}
                  disabled={!customTopicInput.trim() || working}
                  style={{ fontWeight: 600, color: "#0284c7" }}
                >
                  Ajouter
                </button>
              </div>

              {/* Topics Grid */}
              <div className={styles.topicsGrid}>
                {displayedTopics.map((top) => {
                  const isChecked = selectedTopicIds.has(top.id);
                  const detailLvl = topicDetailLevels[top.id] ?? 5;
                  return (
                    <div
                      key={top.id}
                      className={`${styles.topicCard} ${isChecked ? styles.selected : ""}`}
                      onClick={() => toggleTopicSelection(top.id)}
                      role="checkbox"
                      aria-checked={isChecked}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          toggleTopicSelection(top.id);
                        }
                      }}
                    >
                      <div className={styles.topicCardTop}>
                        <span className={styles.topicCatBadge}>{top.category}</span>
                        <div className={styles.topicCheckCircle}>
                          {isChecked && <Check size={12} strokeWidth={3} />}
                        </div>
                      </div>
                      <div className={styles.topicCardTitle}>{top.title}</div>
                      {top.description && <div className={styles.topicCardDesc}>{top.description}</div>}

                      {/* Detail Level Slider on each selected topic card */}
                      {isChecked && (
                        <div
                          className={styles.topicDetailSliderBox}
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <div className={styles.topicDetailSliderHeader}>
                            <span>Détail : {detailLvl}/10</span>
                            <span className={styles.topicDetailSliderBadge}>
                              {detailLvl >= 7
                                ? "≥ 35 lignes"
                                : detailLvl >= 4
                                ? "≥ 20 lignes (standard)"
                                : "~15 lignes"}
                            </span>
                          </div>
                          <input
                            type="range"
                            min={1}
                            max={10}
                            value={detailLvl}
                            className={styles.topicDetailSliderInput}
                            onChange={(e) => {
                              handleSetTopicDetail(top.id, Number(e.target.value));
                            }}
                          />

                          {/* Output Format Selector on each topic */}
                          <div style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.2rem", flexWrap: "wrap" }}>
                            <span style={{ fontSize: "0.66rem", fontWeight: 600, color: "#64748b" }}>Format :</span>
                            <div className={styles.topicFormatRow}>
                              {[
                                { id: "auto", label: "Auto", icon: "✨" },
                                { id: "text", label: "Texte", icon: "📝" },
                                { id: "list", label: "Liste", icon: "📋" },
                                { id: "table", label: "Tableau", icon: "📊" },
                                { id: "cards", label: "Cartes", icon: "🗂️" },
                                { id: "timeline", label: "Étapes", icon: "⏳" },
                              ].map((fmt) => {
                                const currentFmt = topicOutputFormats[top.id] || "auto";
                                const isActive = currentFmt === fmt.id;
                                return (
                                  <button
                                    key={fmt.id}
                                    type="button"
                                    className={`${styles.topicFormatBtn} ${isActive ? styles.active : ""}`}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleSetTopicFormat(top.id, fmt.id as any);
                                    }}
                                    title={`Formater ce thème en ${fmt.label}`}
                                  >
                                    <span>{fmt.icon}</span>
                                    <span>{fmt.label}</span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            <div className={styles.topicsFooter}>
              <button
                type="button"
                className={styles.btn}
                onClick={() => setShowTopicsModal(false)}
                disabled={working}
              >
                Annuler
              </button>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <button
                  type="button"
                  className={styles.btn}
                  onClick={() => void handleCreate()}
                  disabled={working}
                  title="Générer sans imposer la sélection de thèmes"
                >
                  Générer sans filtrer
                </button>
                <button
                  type="button"
                  className={`${styles.btn} ${styles.btnPrimary}`}
                  disabled={working || selectedTopicIds.size === 0}
                  onClick={() => {
                    const chosen = proposedTopics
                      .filter((t) => selectedTopicIds.has(t.id))
                      .map((t) => ({
                        ...t,
                        detail_level: topicDetailLevels[t.id] ?? 5,
                        output_format: topicOutputFormats[t.id] || "auto",
                      }));
                    void handleCreate(chosen);
                  }}
                >
                  {working ? (
                    <>
                      <LoaderCircle size={15} className="spin" />
                      <span>Génération de la page...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles size={15} />
                      <span>
                        Générer la page ({selectedTopicIds.size} thème{selectedTopicIds.size > 1 ? "s" : ""})
                      </span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}


      {/* Unified Model Selector Modal */}
      {isModelPickerOpen && (
        <ModelModal
          currentModel={selectedModel}
          models={models || []}
          onSelectModel={(id) => {
            setSelectedModel(id);
            setIsModelPickerOpen(false);
          }}
          onClose={() => setIsModelPickerOpen(false)}
          onRefreshModels={onRefreshModels}
        />
      )}

      {/* Premade Bricks / AI Agents Configurator for the selected App/Page */}
      {selectedPage && (
        <CanvasBricksModal
          isOpen={bricksModalOpen}
          bricks={selectedPage.bricks || []}
          models={models || []}
          currentModel={selectedModel}
          pageId={selectedPage.id}
          onSave={async (nextBricks) => {
            const updated = await updateWebPage(selectedPage.id, { bricks: nextBricks });
            setSelectedPage(updated);
            setPages((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
            if (updated.versions && updated.versions.length > 0) {
              setSelectedVersionId(updated.versions[0].id);
            }
            setPreviewNonce((n) => n + 1);
          }}
          onInsertTurnkeyWidget={(brick, nextBricks) => {
            const updatedHtml = injectBrickIntoCanvasHtml(activeHtml, brick, selectedPage.title);
            void updateWebPage(selectedPage.id, {
              bricks: nextBricks,
              html_content: updatedHtml,
              prompt_used: `Insertion widget ${brick.name}`,
            }).then((updated) => {
              setSelectedPage(updated);
              setPages((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
              if (updated.versions && updated.versions.length > 0) {
                setSelectedVersionId(updated.versions[0].id);
              }
              setViewMode("preview");
              setPreviewNonce((n) => n + 1);
            }).catch((err) => {
              setError(errorMessage(err));
            });
          }}
          onWireBrickWithAI={(brick) => {
            const wirePrompt = buildBrickWiringPrompt(brick, []);
            void handleRefine(wirePrompt);
          }}
          onClose={() => setBricksModalOpen(false)}
        />
      )}
    </div>
  );
}

