"use client";

import { useCallback, useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type FormEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  Ban, Brush, Check, CircleAlert, Coins, Copy, Download, Eraser, Expand, ExternalLink, Eye, FileCode2, Grid2x2, ImagePlus,
  Layers, LoaderCircle, Maximize2, Minimize2, Paintbrush, RefreshCw, Replace, RotateCcw, Scissors, SlidersHorizontal, Sparkles, Star, Trash2, Type, Undo2, Upload, WandSparkles, X,
} from "lucide-react";
import {
  api,
  errorMessage,
  type Config,
  type GeneratedImage,
  type ImageModel,
  type LayerizeTextBlock,
  type UpscaleModelSpec,
} from "@/lib/api";
import { ImageModelModal } from "@/components/image-model-modal";
import {
  FALLBACK_UPSCALE_MODELS,
  ImageStudioUpscalePanel,
  type StudioSourceImage,
} from "@/components/image-studio-upscale-panel";
import { ImageStudioSvgPanel } from "@/components/image-studio-svg-panel";
import { useModelFavorites } from "@/lib/model-favorites";
import extStyles from "./image-studio-ext.module.css";

const ASPECT_RATIOS = [
  { value: "1:1", label: "1:1", hint: "Carré" },
  { value: "16:9", label: "16:9", hint: "Paysage" },
  { value: "9:16", label: "9:16", hint: "Portrait" },
  { value: "4:3", label: "4:3", hint: "Classique" },
  { value: "3:4", label: "3:4", hint: "Affiche" },
  { value: "3:2", label: "3:2", hint: "Photo" },
  { value: "2:3", label: "2:3", hint: "Vertical" },
];

type StyleCategory = "all" | "supports" | "photo" | "art" | "digital";

type StylePreset = {
  label: string;
  prompt: string;
  category: Exclude<StyleCategory, "all">;
};

const STYLE_CATEGORIES: { id: StyleCategory; label: string }[] = [
  { id: "all", label: "Tous" },
  { id: "supports", label: "Supports (Affiche, Livre, T-shirt…)" },
  { id: "photo", label: "Photo & Cinéma" },
  { id: "art", label: "Illustration & Art" },
  { id: "digital", label: "3D, Pop & Rétro" },
];

const SUGGESTED_STYLE_KEYWORDS = [
  "familial (pour une affiche)",
  "vaporeux",
  "terrifiant",
  "rouge",
  "cinématique",
  "sombre & dramatique",
  "lumineux & solaire",
  "rétrofuturiste",
  "cyberpunk",
  "aquarelle",
  "pastel doux",
  "minimaliste",
  "vintage 70s",
  "noir et blanc",
  "vue du ciel"
];

const SUGGESTED_NEGATIVE_PROMPTS = [
  "flou & basse qualité",
  "texte & filigrane",
  "mauvaise anatomie",
  "membres déformés",
  "visage asymétrique",
  "bruit excessif",
  "grain lourd",
  "couleurs ternes",
];

const STYLE_PRESETS: StylePreset[] = [
  // Styles fondamentaux
  {
    label: "Photographie cinématographique",
    prompt: "Photographie cinématographique, lumière naturelle douce, profondeur de champ, grain pellicule 35mm",
    category: "photo",
  },
  {
    label: "Illustration numérique détaillée",
    prompt: "Illustration numérique détaillée, couleurs vibrantes, éclairage dramatique, composition soignée",
    category: "art",
  },
  {
    label: "Rendu 3D studio minimaliste",
    prompt: "Rendu 3D studio minimaliste, éclairage doux, matériaux mats et textures fines",
    category: "digital",
  },
  {
    label: "Aquarelle poétique et texturée",
    prompt: "Aquarelle poétique et texturée sur papier grain torchon, pigments fluides et nuances délicates",
    category: "art",
  },
  {
    label: "Design graphique moderne",
    prompt: "Design graphique moderne, lignes épurées, formes géométriques audacieuses, palette harmonieuse",
    category: "supports",
  },
  // Supports & créations (Affiche, Livre, T-shirt, Logo, Sticker…)
  {
    label: "Affiche / Poster artistique",
    prompt: "Affiche artistique grand format, composition graphique percutante, mise en page éditoriale, fort contraste visuel",
    category: "supports",
  },
  {
    label: "Affiche de film cinéma",
    prompt: "Affiche de film cinématographique, cadrage dramatique, éclairage atmosphérique, composition d'affiche officielle",
    category: "supports",
  },
  {
    label: "Couverture de livre / roman",
    prompt: "Couverture de livre illustrée, composition verticale équilibrée, atmosphère captivante, design d'édition professionnel",
    category: "supports",
  },
  {
    label: "Design T-shirt",
    prompt: "Visuel graphique pour T-shirt, composition centrée isolée sur fond uni propre, contours nets, style sérigraphie prêt à imprimer",
    category: "supports",
  },
  {
    label: "Logo & emblème minimaliste",
    prompt: "Logo vectoriel minimaliste et mémorable, formes géométriques nettes, contraste fort sur fond neutre, identité visuelle professionnelle",
    category: "supports",
  },
  {
    label: "Sticker / Autocollant die-cut",
    prompt: "Sticker die-cut illustré avec contour blanc épais découpé, couleurs pop éclatantes, ombrage léger sur fond neutre",
    category: "supports",
  },
  {
    label: "Pochette d’album vinyle",
    prompt: "Pochette d'album musicale iconique, direction artistique audacieuse, esthétique visuelle forte",
    category: "supports",
  },
  {
    label: "Miniature YouTube / Web",
    prompt: "Miniature web ultra-accrocheuse, sujet expressif au premier plan, couleurs saturées et contrastées, composition dynamique",
    category: "supports",
  },
  {
    label: "Packaging & mockup produit",
    prompt: "Photographie studio de packaging produit haut de gamme, éclairage commercial maîtrisé, matériaux réalistes, mise en scène épurée",
    category: "supports",
  },
  {
    label: "Carte de tarot / collection",
    prompt: "Carte illustrée ornementale style tarot, bordure dorée finement gravée, symbolisme mystique et symétrie travaillée",
    category: "supports",
  },
  {
    label: "Écusson brodé / Patch textile",
    prompt: "Écusson brodé en fil textile avec relief de couture réaliste, bordure bourdon américaine épaisse, couleurs franches sur fond neutre",
    category: "supports",
  },
  {
    label: "Motif textile / Papier peint",
    prompt: "Motif répétitif harmonieux (seamless pattern) pour textile ou papier peint, éléments finement illustrés et équilibrés",
    category: "supports",
  },
  // Illustration & Beaux-Arts
  {
    label: "Bande dessinée franco-belge",
    prompt: "Style bande dessinée franco-belge ligne claire, encrage précis au trait noir, aplats de couleurs lumineux et détaillés",
    category: "art",
  },
  {
    label: "Manga / Anime japonais",
    prompt: "Esthétique anime japonais haut de gamme, éclairage cinématographique d'animation japonaise, ciel détaillé et couleurs vibrantes",
    category: "art",
  },
  {
    label: "Peinture à l’huile classique",
    prompt: "Peinture à l'huile sur toile, coups de pinceau visibles en empâtement, clair-obscur chaleureux et texture picturale riche",
    category: "art",
  },
  {
    label: "Gravure & linogravure",
    prompt: "Gravure sur bois et linogravure artisanale, hachures fines à l'encre, esthétique d'estampe traditionnelle",
    category: "art",
  },
  {
    label: "Art déco & affiche rétro",
    prompt: "Style Art déco années 1920, géométrie élégante, ornements dorés et couleurs profondes, charme rétro intemporel",
    category: "art",
  },
  {
    label: "Papier découpé / Origami",
    prompt: "Art en papier découpé multicouche, reliefs délicats, ombres portées douces et textures de papier coloré",
    category: "art",
  },
  {
    label: "Vitrail lumineux",
    prompt: "Art du vitrail en verre coloré translucide, sertissage au plomb noir net, lumière traversante chatoyante",
    category: "art",
  },
  {
    label: "Coloriage / Line art épuré",
    prompt: "Dessin au trait noir pur sur fond blanc immaculé (line art), contours nets et réguliers, sans ombrage gris, prêt à colorier",
    category: "art",
  },
  // 3D, Digital, Pop & Photo spécialisée
  {
    label: "Animation 3D style Pixar",
    prompt: "Scène en animation 3D expressive style grand studio d'animation, textures douces, éclairage chaleureux et rendu vivant",
    category: "digital",
  },
  {
    label: "Diorama 3D isométrique",
    prompt: "Diorama 3D miniature en vue isométrique, détails minutieux, éclairage doux en boîte lumineuse, rendu maquette soigné",
    category: "digital",
  },
  {
    label: "Cyberpunk & Néon Synthwave",
    prompt: "Esthétique cyberpunk futuriste, néons magenta et cyan, reflets sur sol mouillé, brume urbaine nocturne",
    category: "digital",
  },
  {
    label: "Pixel Art 16-bit",
    prompt: "Pixel art 16-bit détaillé, palette de couleurs rétro maîtrisée, ambiance jeu vidéo nostalgique",
    category: "digital",
  },
  {
    label: "Pop Art & sérigraphie",
    prompt: "Style Pop Art audacieux, trames demi-teintes, couleurs vives saturées, contours noirs marqués et contraste graphique",
    category: "digital",
  },
  {
    label: "Polaroid & photo argentique",
    prompt: "Photographie argentique instantanée type Polaroid vintage, couleurs chaudes légèrement délavées, grain authentique et lumière nostalgique",
    category: "photo",
  },
  {
    label: "Photo studio & éditoriale",
    prompt: "Photographie éditoriale de magazine haute définition, éclairage studio sculpté, piqué exceptionnel, faible profondeur de champ",
    category: "photo",
  },
  {
    label: "Architecture & design intérieur",
    prompt: "Photographie d'architecture et design d'intérieur contemporain, lignes géométriques pures, lumière naturelle dorée, matériaux nobles",
    category: "photo",
  },
];

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

type SourceImage = StudioSourceImage;

type StudioTab = "create" | "upscale" | "svg";

type EditMode =
  | "remix"
  | "inpaint"
  | "remove_background"
  | "replace_background"
  | "remove_object"
  | "layerize";

function isMaskEditMode(mode: EditMode): boolean {
  return mode === "inpaint" || mode === "remove_object";
}

function isPromptOptionalEditMode(mode: EditMode): boolean {
  return mode === "remove_background" || mode === "remove_object" || mode === "layerize";
}

function isBinaryPromptlessEditMode(mode: EditMode): boolean {
  return mode === "remove_background" || mode === "remove_object";
}

const EDIT_MODE_COPY: Record<
  EditMode,
  {
    label: string;
    title: string;
    promptLabel: string;
    promptPlaceholder: string;
    buttonLabel: string;
    busyLabel: string;
  }
> = {
  remix: {
    label: "Retouche (Remix)",
    title: "Modifier globalement l’image existante",
    promptLabel: "Modifications à apporter à l’image",
    promptPlaceholder:
      "Décrivez les modifications souhaitées : changer les couleurs, ajouter un objet, modifier le style ou l’éclairage…",
    buttonLabel: "Modifier l’image",
    busyLabel: "Modification",
  },
  inpaint: {
    label: "Inpaint (Pinceau)",
    title: "Remplacer ou régénérer une zone peinte au pinceau",
    promptLabel: "Contenu souhaité dans la zone peinte",
    promptPlaceholder:
      "Décrivez ce qui doit remplacer la zone peinte au pinceau (ex : des lunettes de soleil dorées, un bouquet de fleurs rouges…)",
    buttonLabel: "Appliquer l’inpaint",
    busyLabel: "Inpainting",
  },
  remove_background: {
    label: "Détourer le fond",
    title: "Ideogram 1.0 — Supprimer l’arrière-plan pour obtenir un PNG transparent",
    promptLabel: "",
    promptPlaceholder: "",
    buttonLabel: "Détourer l’arrière-plan",
    busyLabel: "Détourage",
  },
  replace_background: {
    label: "Remplacer le fond",
    title: "Ideogram 3.0 — Conserver le sujet et créer un nouvel arrière-plan",
    promptLabel: "Description du nouvel arrière-plan",
    promptPlaceholder:
      "Décrivez le nouvel arrière-plan souhaité derrière le sujet (ex : un studio minimaliste, une plage au coucher du soleil…)",
    buttonLabel: "Remplacer l’arrière-plan",
    busyLabel: "Remplacement du fond",
  },
  remove_object: {
    label: "Effacer un objet",
    title: "Ideogram 1.0 — Supprimer proprement l’objet peint au pinceau",
    promptLabel: "",
    promptPlaceholder: "",
    buttonLabel: "Effacer l’objet masqué",
    busyLabel: "Suppression d’objet",
  },
  layerize: {
    label: "Calques texte",
    title: "Ideogram 3.0 Layerize — Extraire le fond nettoyé et les blocs de texte structurés",
    promptLabel: "Contexte de l’image pour Layerize (optionnel)",
    promptPlaceholder:
      "Optionnel : décrivez brièvement l’affiche ou l’image pour aider la détection des calques de texte…",
    buttonLabel: "Extraire les calques texte",
    busyLabel: "Analyse Layerize",
  },
};

type MaskTool = "brush" | "erase";

type MaskPoint = { x: number; y: number };

type MaskStroke = {
  mode: MaskTool;
  sizeRatio: number;
  points: MaskPoint[];
};

const MAX_SOURCE_IMAGE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_SOURCE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

function renderStrokesToCanvas(
  canvas: HTMLCanvasElement,
  strokes: MaskStroke[],
  width: number,
  height: number,
  binaryMask: boolean,
  invertBinaryMask = false,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx || width <= 0 || height <= 0) return;
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  ctx.clearRect(0, 0, width, height);
  if (binaryMask) {
    ctx.globalCompositeOperation = "source-over";
    // Inpaint: white (#FFFFFF) keeps, black (#000000) paints.
    // Remove Object: black (#000000) keeps, white (#FFFFFF) removes.
    ctx.fillStyle = invertBinaryMask ? "#000000" : "#ffffff";
    ctx.fillRect(0, 0, width, height);
  }
  for (const stroke of strokes) {
    if (stroke.points.length === 0) continue;
    const radius = Math.max(1, (stroke.sizeRatio * width) / 2);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.lineWidth = radius * 2;
    if (binaryMask) {
      ctx.globalCompositeOperation = "source-over";
      const color = invertBinaryMask
        ? (stroke.mode === "brush" ? "#ffffff" : "#000000")
        : (stroke.mode === "brush" ? "#000000" : "#ffffff");
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
    } else if (stroke.mode === "brush") {
      ctx.globalCompositeOperation = "source-over";
      const overlayColor = invertBinaryMask ? "#ef4444" : "#9333ea";
      ctx.strokeStyle = overlayColor;
      ctx.fillStyle = overlayColor;
    } else {
      ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = "#000000";
      ctx.fillStyle = "#000000";
    }
    if (stroke.points.length === 1) {
      ctx.beginPath();
      ctx.arc(stroke.points[0].x * width, stroke.points[0].y * height, radius, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.beginPath();
      ctx.moveTo(stroke.points[0].x * width, stroke.points[0].y * height);
      for (let i = 1; i < stroke.points.length; i += 1) {
        ctx.lineTo(stroke.points[i].x * width, stroke.points[i].y * height);
      }
      ctx.stroke();
    }
  }
  ctx.globalCompositeOperation = "source-over";
}

function detectClosestAspectRatio(width: number, height: number): string {
  if (!width || !height) return "1:1";
  const target = width / height;
  let best = "1:1";
  let bestDiff = Infinity;
  for (const item of ASPECT_RATIOS) {
    const [w, h] = item.value.split(":").map(Number);
    if (!w || !h) continue;
    const diff = Math.abs(Math.log(target / (w / h)));
    if (diff < bestDiff) {
      bestDiff = diff;
      best = item.value;
    }
  }
  return best;
}

type ImageStudioModalProps = {
  config: Config | null;
  initialPrompt?: string;
  onClose: () => void;
};

export function ImageStudioModal({ config, initialPrompt = "", onClose }: ImageStudioModalProps) {
  const { isFavorite } = useModelFavorites("image");
  const [images, setImages] = useState<GeneratedImage[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingGallery, setLoadingGallery] = useState(true);
  const [prompt, setPrompt] = useState(initialPrompt);
  const [previousPrompt, setPreviousPrompt] = useState<string | null>(null);
  const [aspectRatio, setAspectRatio] = useState("1:1");
  const [styleCategory, setStyleCategory] = useState<StyleCategory>("all");
  const [busy, setBusy] = useState<"improve" | "generate" | "delete" | null>(null);
  const [error, setError] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [styleKeywords, setStyleKeywords] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [showModelModal, setShowModelModal] = useState(false);
  const [sourceImage, setSourceImage] = useState<SourceImage | null>(null);
  const [previewingSource, setPreviewingSource] = useState(false);
  const [isDraggingSource, setIsDraggingSource] = useState(false);
  const [imageWeight, setImageWeight] = useState(70);
  const [editMode, setEditMode] = useState<EditMode>("remix");
  const [transparentBg, setTransparentBg] = useState(false);
  const [showCheckerboard, setShowCheckerboard] = useState(false);
  const [layerizeBlocksByImageId, setLayerizeBlocksByImageId] = useState<Record<string, LayerizeTextBlock[]>>({});
  const [copiedBlockIndex, setCopiedBlockIndex] = useState<number | null>(null);
  const [copiedLayerizeJsonId, setCopiedLayerizeJsonId] = useState<string | null>(null);
  const [copiedSvgCodeId, setCopiedSvgCodeId] = useState<string | null>(null);
  const [studioTab, setStudioTab] = useState<StudioTab>("create");
  const [svgOperation, setSvgOperation] = useState<"generate" | "vectorize">("generate");
  const [upscaleModels, setUpscaleModels] = useState<UpscaleModelSpec[]>(FALLBACK_UPSCALE_MODELS);
  const [loadingUpscaleModels, setLoadingUpscaleModels] = useState(true);
  const [customBusyLabel, setCustomBusyLabel] = useState<string | null>(null);
  const [maskTool, setMaskTool] = useState<MaskTool>("brush");
  const [brushSize, setBrushSize] = useState(40);
  const [maskStrokes, setMaskStrokes] = useState<MaskStroke[]>([]);
  const [canvasBox, setCanvasBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const sourceImgRef = useRef<HTMLImageElement>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement>(null);
  const activeStrokeRef = useRef<MaskStroke | null>(null);
  const isDrawingMaskRef = useRef(false);

  function toggleNegativePrompt(tag: string) {
    if (busy) return;
    setNegativePrompt(current => {
      const items = current
        .split(",")
        .map(s => s.trim())
        .filter(Boolean);
      const existsIndex = items.findIndex(item => item.toLowerCase() === tag.toLowerCase());
      if (existsIndex >= 0) {
        items.splice(existsIndex, 1);
      } else {
        items.push(tag);
      }
      return items.join(", ");
    });
  }

  function toggleStyleKeyword(tag: string) {
    if (busy) return;
    setStyleKeywords(current => {
      const items = current
        .split(",")
        .map(s => s.trim())
        .filter(Boolean);
      const existsIndex = items.findIndex(item => item.toLowerCase() === tag.toLowerCase());
      if (existsIndex >= 0) {
        items.splice(existsIndex, 1);
      } else {
        items.push(tag);
      }
      return items.join(", ");
    });
  }

  const preferredModel =
    config?.image_prompt_model ||
    (config?.models?.some(m => m.id === "google/gemini-4-argon") ? "google/gemini-4-argon" : config?.default_model || "google/gemini-4-argon");
  const [improveModel, setImproveModel] = useState<string>(preferredModel);

  const [dynamicImageModels, setDynamicImageModels] = useState<ImageModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  const availableImageModels =
    dynamicImageModels.length > 0
      ? dynamicImageModels
      : (config?.image_models && config.image_models.length > 0
          ? config.image_models
          : [{ id: "ideogram-4-5", name: "Ideogram 4.5 (Dernière génération)", provider: "ideogram" as const }]);

  const initialGenModel = config?.default_image_model || availableImageModels[0]?.id || "ideogram-4-5";
  const [generationModel, setGenerationModel] = useState<string>(initialGenModel);

  async function loadModels(force = false) {
    setLoadingModels(true);
    try {
      const list = await api<ImageModel[]>(`/images/models${force ? "?force_refresh=true" : ""}`);
      if (Array.isArray(list) && list.length > 0) {
        setDynamicImageModels(list);
      }
    } catch {
      // Keep existing list
    } finally {
      setLoadingModels(false);
    }
  }

  useEffect(() => {
    void loadModels(false);
  }, []);

  useEffect(() => {
    if (config?.default_image_model && availableImageModels.some(m => m.id === config.default_image_model)) {
      if (!generationModel || !availableImageModels.some(m => m.id === generationModel)) {
        setGenerationModel(config.default_image_model);
      }
    } else if (availableImageModels.length > 0 && !availableImageModels.some(m => m.id === generationModel)) {
      setGenerationModel(availableImageModels[0].id);
    }
  }, [config?.default_image_model, availableImageModels, generationModel]);

  const selectedGenModel = availableImageModels.find(m => m.id === generationModel) || availableImageModels[0];
  const isIdeogramSelected =
    selectedGenModel?.provider === "ideogram" || generationModel === "ideogram" || generationModel.startsWith("ideogram-");
  const isGoogleCloudSelected =
    selectedGenModel?.routed_via === "google_cloud" || selectedGenModel?.provider === "google";
  const googleProviderBadgeLabel =
    config?.google_cloud_mode === "gemini_api" ? "Google Gemini API" : "Google Cloud (Vertex AI)";
  const supportsIdeogramWeight = isIdeogramSelected && generationModel !== "ideogram-4-5";
  const preferredIdeogramModel =
    availableImageModels.find(m => m.id === "ideogram-4-5")
    || availableImageModels.find(m => m.provider === "ideogram")
    || { id: "ideogram-4-5", name: "Ideogram 4.5", provider: "ideogram" as const };
  const topModels = availableImageModels.filter(m => m.is_top);
  const otherModels = availableImageModels.filter(m => !m.is_top);

  useEffect(() => {
    if (config?.image_prompt_model) {
      setImproveModel(config.image_prompt_model);
    } else if (config?.models?.some(m => m.id === "google/gemini-4-argon")) {
      setImproveModel("google/gemini-4-argon");
    } else if (config?.default_model) {
      setImproveModel(config.default_model);
    }
  }, [config?.image_prompt_model, config?.default_model, config?.models]);

  useEffect(() => {
    const controller = new AbortController();
    api<GeneratedImage[]>("/images", { signal: controller.signal })
      .then(list => {
        setImages(list);
        if (list.length > 0) setSelectedId(list[0].id);
      })
      .catch(err => {
        if (!controller.signal.aborted) setError(errorMessage(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingGallery(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api<UpscaleModelSpec[]>("/images/upscale-models", { signal: controller.signal })
      .then(list => {
        if (Array.isArray(list) && list.length > 0) {
          setUpscaleModels(list);
        }
      })
      .catch(() => {
        // Fallback statique déjà chargé
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingUpscaleModels(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    promptRef.current?.focus();
  }, []);

  const selected = images.find(item => item.id === selectedId) ?? images[0] ?? null;
  const canUseIdeogram = Boolean(
    config?.features.image_generation &&
      !config.demo_mode &&
      availableImageModels.some(m => m.provider === "ideogram" || m.id === "ideogram" || m.id.startsWith("ideogram-")),
  );
  const activeMaskEdit = studioTab === "create" && Boolean(sourceImage) && isMaskEditMode(editMode);
  const invertMaskPolarity = editMode === "remove_object";
  const isPromptRequired = !sourceImage || !isPromptOptionalEditMode(editMode);
  const effectiveTransparentBg =
    !sourceImage && isIdeogramSelected && (transparentBg || generationModel === "ideogram-3-transparent");
  const canGenerate =
    !!config?.features.image_generation &&
    !config.demo_mode &&
    availableImageModels.length > 0 &&
    (!sourceImage || isIdeogramSelected) &&
    (!isPromptRequired || !!prompt.trim()) &&
    prompt.length <= 4000 &&
    !busy;
  const canImprove =
    !!config?.features.chat &&
    !config.demo_mode &&
    (!sourceImage || !isPromptOptionalEditMode(editMode)) &&
    !!prompt.trim() &&
    prompt.length <= 4000 &&
    !busy;

  const syncCanvasBox = useCallback(() => {
    const img = sourceImgRef.current;
    if (!img || !img.clientWidth || !img.clientHeight) {
      setCanvasBox(null);
      return;
    }
    const next = {
      left: img.offsetLeft,
      top: img.offsetTop,
      width: img.clientWidth,
      height: img.clientHeight,
    };
    setCanvasBox(prev =>
      prev &&
      prev.left === next.left &&
      prev.top === next.top &&
      prev.width === next.width &&
      prev.height === next.height
        ? prev
        : next,
    );
  }, []);

  useEffect(() => {
    if (!sourceImage || !previewingSource || !isMaskEditMode(editMode) || busy === "generate") {
      return;
    }
    syncCanvasBox();
    const img = sourceImgRef.current;
    const stage = stageRef.current;
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => syncCanvasBox());
    if (img) observer.observe(img);
    if (stage) observer.observe(stage);
    return () => observer.disconnect();
  }, [sourceImage, previewingSource, editMode, zoomed, busy, syncCanvasBox]);

  useEffect(() => {
    const canvas = maskCanvasRef.current;
    if (!canvas || !canvasBox || !isMaskEditMode(editMode) || !previewingSource) return;
    renderStrokesToCanvas(canvas, maskStrokes, canvasBox.width, canvasBox.height, false, invertMaskPolarity);
  }, [maskStrokes, canvasBox, editMode, previewingSource, invertMaskPolarity]);

  function getNormalizedPoint(event: ReactPointerEvent<HTMLCanvasElement>): MaskPoint | null {
    const canvas = maskCanvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    };
  }

  function handleMaskPointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (busy || !isMaskEditMode(editMode)) return;
    const canvas = maskCanvasRef.current;
    const point = getNormalizedPoint(event);
    if (!canvas || !point) return;
    const rect = canvas.getBoundingClientRect();
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
    const stroke: MaskStroke = {
      mode: maskTool,
      sizeRatio: brushSize / Math.max(1, rect.width),
      points: [point],
    };
    activeStrokeRef.current = stroke;
    isDrawingMaskRef.current = true;
    renderStrokesToCanvas(canvas, [...maskStrokes, stroke], canvas.width, canvas.height, false, invertMaskPolarity);
  }

  function handleMaskPointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (!isDrawingMaskRef.current || !activeStrokeRef.current) return;
    const canvas = maskCanvasRef.current;
    const point = getNormalizedPoint(event);
    if (!canvas || !point) return;
    activeStrokeRef.current.points.push(point);
    renderStrokesToCanvas(
      canvas,
      [...maskStrokes, activeStrokeRef.current],
      canvas.width,
      canvas.height,
      false,
      invertMaskPolarity,
    );
  }

  function finishMaskStroke(event?: ReactPointerEvent<HTMLCanvasElement>) {
    if (!isDrawingMaskRef.current || !activeStrokeRef.current) return;
    const finished = activeStrokeRef.current;
    activeStrokeRef.current = null;
    isDrawingMaskRef.current = false;
    if (event && maskCanvasRef.current?.hasPointerCapture(event.pointerId)) {
      maskCanvasRef.current.releasePointerCapture(event.pointerId);
    }
    if (finished.points.length > 0) {
      setMaskStrokes(prev => [...prev, finished]);
    }
  }

  async function resolveSourceDimensions(src: SourceImage): Promise<{ width: number; height: number }> {
    if (src.width && src.height) return { width: src.width, height: src.height };
    const loadedImg = sourceImgRef.current;
    if (loadedImg?.naturalWidth && loadedImg?.naturalHeight) {
      return { width: loadedImg.naturalWidth, height: loadedImg.naturalHeight };
    }
    return new Promise((resolve, reject) => {
      const probe = new window.Image();
      probe.onload = () => resolve({ width: probe.naturalWidth || 1024, height: probe.naturalHeight || 1024 });
      probe.onerror = () => reject(new Error("Impossible de mesurer les dimensions de l’image source."));
      probe.src = src.previewUrl;
    });
  }

  async function buildInpaintMaskDataUrl(src: SourceImage, invertPolarity: boolean): Promise<string> {
    const { width, height } = await resolveSourceDimensions(src);
    const offscreen = document.createElement("canvas");
    renderStrokesToCanvas(offscreen, maskStrokes, width, height, true, invertPolarity);
    const ctx = offscreen.getContext("2d");
    if (ctx) {
      const pixels = ctx.getImageData(0, 0, width, height).data;
      let hasPaintedPixel = false;
      for (let i = 0; i < pixels.length; i += 16) {
        if (invertPolarity ? pixels[i] >= 128 : pixels[i] < 128) {
          hasPaintedPixel = true;
          break;
        }
      }
      if (!hasPaintedPixel) {
        throw new Error("EMPTY_MASK");
      }
    }
    return offscreen.toDataURL("image/png");
  }

  function clearSourceImage() {
    setSourceImage(null);
    setPreviewingSource(false);
    setEditMode("remix");
    setMaskStrokes([]);
    setCanvasBox(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function activateSourceImage(next: SourceImage, ratio?: string, targetTab?: StudioTab) {
    const activeTab = targetTab ?? studioTab;
    if (ratio) {
      setAspectRatio(ratio);
    }
    setSourceImage(next);
    setMaskStrokes([]);
    setEditMode("remix");
    setPreviewingSource(true);
    setZoomed(false);
    if (activeTab === "create") {
      if (!isIdeogramSelected) {
        setGenerationModel(preferredIdeogramModel.id);
      }
      promptRef.current?.focus();
    }
  }

  function inferMimeFromFilename(name: string): string | undefined {
    if (/\.png$/i.test(name)) return "image/png";
    if (/\.jpe?g$/i.test(name)) return "image/jpeg";
    if (/\.webp$/i.test(name)) return "image/webp";
    if (/\.gif$/i.test(name)) return "image/gif";
    return undefined;
  }

  function loadFileAsSourceImage(file: File) {
    if (busy) return;
    const extOk = /\.(png|jpe?g|webp|gif)$/i.test(file.name);
    if (file.type && !ACCEPTED_SOURCE_TYPES.has(file.type)) {
      setError("Format d'image non pris en charge. Utilisez PNG, JPEG, WEBP ou GIF.");
      return;
    }
    if (!file.type && !extOk) {
      setError("Format d'image non pris en charge. Utilisez PNG, JPEG, WEBP ou GIF.");
      return;
    }
    if (file.size > MAX_SOURCE_IMAGE_BYTES) {
      setError("L'image importée dépasse la limite de 10 Mo.");
      return;
    }
    const detectedMime = file.type || inferMimeFromFilename(file.name);
    setError("");
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : "";
      if (!dataUrl) {
        setError("Impossible de lire l'image sélectionnée.");
        return;
      }
      const probe = new window.Image();
      probe.onload = () => {
        const w = probe.naturalWidth || undefined;
        const h = probe.naturalHeight || undefined;
        activateSourceImage(
          {
            kind: "upload",
            name: file.name || "image-importee.png",
            previewUrl: dataUrl,
            dataUrl,
            mimeType: detectedMime,
            sizeBytes: file.size,
            width: w,
            height: h,
          },
          w && h ? detectClosestAspectRatio(w, h) : undefined,
        );
      };
      probe.onerror = () => {
        activateSourceImage({
          kind: "upload",
          name: file.name || "image-importee.png",
          previewUrl: dataUrl,
          dataUrl,
          mimeType: detectedMime,
          sizeBytes: file.size,
        });
      };
      probe.src = dataUrl;
    };
    reader.onerror = () => setError("Erreur lors de la lecture du fichier image.");
    reader.readAsDataURL(file);
  }

  function handleDropSource(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    setIsDraggingSource(false);
    if (busy) return;
    const file = event.dataTransfer?.files?.[0];
    if (file) loadFileAsSourceImage(file);
  }

  function handleModalPaste(event: ClipboardEvent) {
    if (busy) return;
    const items = event.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          event.preventDefault();
          loadFileAsSourceImage(file);
          return;
        }
      }
    }
  }

  function loadGalleryImageForEdit(target: GeneratedImage) {
    if (busy || target.mime_type === "image/svg+xml") return;
    setError("");
    setStudioTab("create");
    if (prompt.trim() === target.prompt.trim()) {
      setPrompt("");
    }
    activateSourceImage(
      {
        kind: "gallery",
        name: target.filename,
        previewUrl: target.url,
        sourceImageId: target.id,
        mimeType: target.mime_type,
        sizeBytes: target.size,
        width: target.output_width ?? undefined,
        height: target.output_height ?? undefined,
      },
      target.aspect_ratio,
      "create",
    );
  }

  function loadGalleryImageForTool(target: GeneratedImage, destination: "upscale" | "svg") {
    if (busy || target.mime_type === "image/svg+xml") return;
    setError("");
    setStudioTab(destination);
    if (destination === "svg") {
      setSvgOperation("vectorize");
    }
    activateSourceImage(
      {
        kind: "gallery",
        name: target.filename,
        previewUrl: target.url,
        sourceImageId: target.id,
        mimeType: target.mime_type,
        sizeBytes: target.size,
        width: target.output_width ?? undefined,
        height: target.output_height ?? undefined,
      },
      target.aspect_ratio,
      destination,
    );
  }

  async function copySvgSourceCode(target: GeneratedImage) {
    try {
      const response = await fetch(target.url, { credentials: "include" });
      if (!response.ok) return;
      const svgText = await response.text();
      await navigator.clipboard.writeText(svgText);
      setCopiedSvgCodeId(target.id);
      setTimeout(() => setCopiedSvgCodeId(current => (current === target.id ? null : current)), 2000);
    } catch {
      setCopiedSvgCodeId(null);
    }
  }

  async function improvePrompt() {
    if (!canImprove) return;
    const original = prompt.trim();
    setBusy("improve");
    setError("");
    try {
      const result = await api<{ prompt: string }>("/images/improve", {
        method: "POST",
        body: JSON.stringify({
          prompt: original,
          model: improveModel,
          style_keywords: styleKeywords.trim() || undefined,
          negative_prompt: negativePrompt.trim() || undefined,
          reference_image_data: sourceImage?.dataUrl,
          source_image_id: sourceImage?.sourceImageId,
          is_edit: !!sourceImage,
        }),
      });
      setPreviousPrompt(original);
      setPrompt(result.prompt);
      promptRef.current?.focus();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function applyStyleChip(styleText: string) {
    if (busy) return;
    setPrompt(current => {
      const trimmed = current.trim();
      if (!trimmed) return styleText;
      if (trimmed.toLocaleLowerCase("fr").includes(styleText.toLocaleLowerCase("fr"))) return current;
      const separator = /[.!?]$/.test(trimmed) ? " " : ", ";
      return `${trimmed}${separator}${styleText}`.slice(0, 4000);
    });
    promptRef.current?.focus();
  }

  async function generate(event?: FormEvent) {
    event?.preventDefault();
    if (!canGenerate) return;
    setError("");
    let maskImageData: string | undefined;
    if (sourceImage && isMaskEditMode(editMode)) {
      try {
        maskImageData = await buildInpaintMaskDataUrl(sourceImage, editMode === "remove_object");
      } catch (err) {
        if (err instanceof Error && err.message === "EMPTY_MASK") {
          setPreviewingSource(true);
          setError(
            editMode === "remove_object"
              ? "Peignez au pinceau l’objet à supprimer sur l’image, ou choisissez un autre outil."
              : "Peignez au pinceau la zone à modifier sur l’image, ou repassez en « Retouche globale ».",
          );
        } else {
          setError(errorMessage(err));
        }
        return;
      }
    }
    const payloadPrompt =
      sourceImage && (editMode === "remove_background" || editMode === "remove_object")
        ? ""
        : prompt.trim();
    const shouldUseNegativePrompt =
      (!sourceImage || editMode === "remix") && negativePrompt.trim() ? negativePrompt.trim() : undefined;
    setBusy("generate");
    try {
      const created = await api<GeneratedImage>("/images", {
        method: "POST",
        body: JSON.stringify({
          prompt: payloadPrompt,
          aspect_ratio: aspectRatio,
          negative_prompt: shouldUseNegativePrompt,
          model: generationModel,
          reference_image_data: sourceImage?.dataUrl,
          mask_image_data: maskImageData,
          source_image_id: sourceImage?.sourceImageId,
          image_weight:
            sourceImage && editMode === "remix" && supportsIdeogramWeight ? imageWeight : undefined,
          edit_action: sourceImage ? editMode : undefined,
          transparent_background: effectiveTransparentBg ? true : undefined,
        }),
      });
      setImages(current => [created, ...current]);
      setSelectedId(created.id);
      if (Array.isArray(created.text_blocks)) {
        setLayerizeBlocksByImageId(prev => ({
          ...prev,
          [created.id]: created.text_blocks ?? [],
        }));
      }
      if (effectiveTransparentBg || (sourceImage && editMode === "remove_background")) {
        setShowCheckerboard(true);
      } else {
        setShowCheckerboard(false);
      }
      setPreviewingSource(false);
      setPreviousPrompt(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function deleteImage(target: GeneratedImage) {
    if (busy) return;
    setBusy("delete");
    setError("");
    try {
      await api(`/images/${target.id}`, { method: "DELETE" });
      setImages(current => {
        const next = current.filter(item => item.id !== target.id);
        if (selectedId === target.id) {
          setSelectedId(next[0]?.id ?? null);
          setZoomed(false);
        }
        return next;
      });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function copyPrompt(target: GeneratedImage) {
    try {
      await navigator.clipboard.writeText(target.prompt);
      setCopiedId(target.id);
      setTimeout(() => setCopiedId(current => (current === target.id ? null : current)), 2000);
    } catch {
      setCopiedId(null);
    }
  }

  async function copyLayerizeText(text: string, index: number) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedBlockIndex(index);
      setTimeout(() => setCopiedBlockIndex(current => (current === index ? null : current)), 2000);
    } catch {
      setCopiedBlockIndex(null);
    }
  }

  async function copyLayerizeJson(imageId: string, blocks: LayerizeTextBlock[]) {
    try {
      await navigator.clipboard.writeText(JSON.stringify(blocks, null, 2));
      setCopiedLayerizeJsonId(imageId);
      setTimeout(() => setCopiedLayerizeJsonId(current => (current === imageId ? null : current)), 2000);
    } catch {
      setCopiedLayerizeJsonId(null);
    }
  }

  const editModeIcon = (mode: EditMode, size = 12) => {
    switch (mode) {
      case "remix":
        return <Paintbrush size={size} />;
      case "inpaint":
        return <Brush size={size} />;
      case "remove_background":
        return <Scissors size={size} />;
      case "replace_background":
        return <Replace size={size} />;
      case "remove_object":
        return <Eraser size={size} />;
      case "layerize":
        return <Layers size={size} />;
    }
  };

  function selectEditMode(nextMode: EditMode) {
    setEditMode(nextMode);
    setError("");
    if (isMaskEditMode(nextMode)) {
      setPreviewingSource(true);
      setZoomed(false);
    }
  }

  function reuseImageSettings(target: GeneratedImage) {
    if (busy) return;
    setStudioTab("create");
    setPrompt(target.prompt);
    if (target.aspect_ratio !== "auto") {
      setAspectRatio(target.aspect_ratio);
    }
    setPreviousPrompt(null);
    promptRef.current?.focus();
  }

  function handleSwitchStudioTab(nextTab: StudioTab) {
    if (busy) return;
    setError("");
    setStudioTab(nextTab);
    if (nextTab !== "create") {
      setCanvasBox(null);
    }
  }

  return (
    <div
      className="modal-backdrop image-studio-backdrop"
      onMouseDown={event => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        className={`image-studio-modal ${zoomed ? "is-zoomed" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="image-studio-title"
        onPaste={handleModalPaste}
        onKeyDown={event => {
          if (event.key === "Escape" && !busy) {
            if (zoomed) setZoomed(false);
            else onClose();
          }
        }}
      >
        <header className="image-studio-header">
          <div className="image-studio-brand">
            <span className="image-studio-badge">
              <ImagePlus size={18} />
            </span>
            <div>
              <span className="eyebrow">STUDIO CRÉATIF · MULTI-MODÈLES</span>
              <h2 id="image-studio-title">Studio Image</h2>
            </div>
          </div>
          <div className="image-studio-header-right">
            <span className="image-studio-count">
              {images.length} image{images.length > 1 ? "s" : ""} sauvegardée{images.length > 1 ? "s" : ""}
            </span>
            <button
              type="button"
              className="icon-button"
              onClick={onClose}
              disabled={!!busy}
              aria-label="Fermer le Studio Image"
              title="Fermer"
            >
              <X size={19} />
            </button>
          </div>
        </header>

        {!config?.features.image_generation && (
          <div className="image-studio-notice" role="status">
            <CircleAlert size={16} />
            <span>
              La génération d’images nécessite <code>IDEOGRAM_API_KEY</code>, <code>Google Cloud (Vertex AI)</code> ou <code>LLM_API_KEY</code> (OpenRouter) actif côté serveur. Vous pouvez toujours consulter et télécharger vos images sauvegardées.
            </span>
          </div>
        )}

        {error && (
          <div className="image-studio-error" role="alert">
            <CircleAlert size={16} />
            <p>{error}</p>
            <button type="button" className="icon-button" aria-label="Fermer l’erreur" onClick={() => setError("")}>
              <X size={14} />
            </button>
          </div>
        )}

        <div className="image-studio-body">
          <div
            className="image-studio-controls"
            onDragOver={event => {
              event.preventDefault();
              if (!busy) setIsDraggingSource(true);
            }}
            onDragLeave={event => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                setIsDraggingSource(false);
              }
            }}
            onDrop={handleDropSource}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept={
                studioTab === "create"
                  ? "image/png,image/jpeg,image/webp,image/gif"
                  : "image/png,image/jpeg,image/webp"
              }
              className="sr-only"
              style={{ display: "none" }}
              onChange={event => {
                const file = event.target.files?.[0];
                if (file) loadFileAsSourceImage(file);
              }}
            />

            <div className={extStyles.modeSwitcher} role="tablist" aria-label="Mode du Studio Image">
              <button
                type="button"
                role="tab"
                aria-selected={studioTab === "create"}
                className={`${extStyles.modeTab} ${studioTab === "create" ? extStyles.modeTabActive : ""}`}
                onClick={() => handleSwitchStudioTab("create")}
                disabled={!!busy}
              >
                <Sparkles size={13} />
                <span>Créer &amp; Retoucher</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={studioTab === "upscale"}
                className={`${extStyles.modeTab} ${studioTab === "upscale" ? extStyles.modeTabActive : ""}`}
                onClick={() => handleSwitchStudioTab("upscale")}
                disabled={!!busy}
              >
                <Maximize2 size={13} />
                <span>Upscale HD</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={studioTab === "svg"}
                className={`${extStyles.modeTab} ${studioTab === "svg" ? extStyles.modeTabActive : ""}`}
                onClick={() => handleSwitchStudioTab("svg")}
                disabled={!!busy}
              >
                <FileCode2 size={13} />
                <span>Vecteur SVG</span>
              </button>
            </div>

            {studioTab === "upscale" ? (
              <ImageStudioUpscalePanel
                models={upscaleModels}
                loadingModels={loadingUpscaleModels}
                sourceImage={sourceImage}
                previewingSource={previewingSource}
                busy={!!busy}
                canUseIdeogram={canUseIdeogram}
                onPickFile={() => fileInputRef.current?.click()}
                onTogglePreviewSource={() => setPreviewingSource(old => !old)}
                onClearSource={clearSourceImage}
                onUpscaleCreated={created => {
                  setImages(current => [created, ...current]);
                  setSelectedId(created.id);
                  setPreviewingSource(false);
                  setShowCheckerboard(false);
                }}
                onError={msg => setError(msg)}
                onBusyChange={(nextBusy, statusLabel) => {
                  setBusy(nextBusy);
                  setCustomBusyLabel(nextBusy ? (statusLabel ?? null) : null);
                }}
              />
            ) : studioTab === "svg" ? (
              <ImageStudioSvgPanel
                operation={svgOperation}
                onOperationChange={op => setSvgOperation(op)}
                sourceImage={sourceImage}
                previewingSource={previewingSource}
                busy={busy}
                canUseIdeogram={canUseIdeogram}
                canImproveChat={Boolean(config?.features.chat && !config.demo_mode)}
                improveModel={improveModel}
                onPickFile={() => fileInputRef.current?.click()}
                onTogglePreviewSource={() => setPreviewingSource(old => !old)}
                onClearSource={clearSourceImage}
                onSvgCreated={created => {
                  setImages(current => [created, ...current]);
                  setSelectedId(created.id);
                  setPreviewingSource(false);
                  setShowCheckerboard(true);
                }}
                onError={msg => setError(msg)}
                onBusyChange={(nextBusy, statusLabel) => {
                  setBusy(nextBusy);
                  setCustomBusyLabel(nextBusy ? (statusLabel ?? null) : null);
                }}
              />
            ) : (
            <form className="image-studio-form" onSubmit={event => void generate(event)}>
              <div className="image-source-section">
                <div className="image-source-header">
                  <span className="image-section-label">
                    {sourceImage ? "Image source à modifier" : "Image à modifier (optionnel)"}
                  </span>
                  {sourceImage ? (
                    <span className="image-source-mode-badge">
                      <Paintbrush size={10} />
                      <span>Mode retouche</span>
                    </span>
                  ) : (
                    <span className="image-source-hint-pill">Import · Glisser · Ctrl+V</span>
                  )}
                </div>

                {sourceImage ? (
                  <div className="image-source-card">
                    <button
                      type="button"
                      className="image-source-thumb"
                      onClick={() => setPreviewingSource(old => !old)}
                      title="Afficher / masquer l'image source dans le visualiseur"
                    >
                      <img src={sourceImage.previewUrl} alt={sourceImage.name} />
                    </button>
                    <div className="image-source-info">
                      <strong title={sourceImage.name}>{sourceImage.name}</strong>
                      <span>
                        {sourceImage.width && sourceImage.height ? `${sourceImage.width}×${sourceImage.height} px` : "Image prête"}
                        {sourceImage.sizeBytes ? ` · ${formatBytes(sourceImage.sizeBytes)}` : ""}
                      </span>
                      <div className="image-source-card-actions">
                        <button
                          type="button"
                          className={`image-source-mini-btn ${previewingSource ? "is-active" : ""}`}
                          onClick={() => setPreviewingSource(old => !old)}
                          disabled={!!busy}
                        >
                          <Eye size={11} />
                          <span>{previewingSource ? "Affichée" : "Voir"}</span>
                        </button>
                        <button
                          type="button"
                          className="image-source-mini-btn"
                          onClick={() => fileInputRef.current?.click()}
                          disabled={!!busy}
                        >
                          <Upload size={11} />
                          <span>Remplacer</span>
                        </button>
                        <button
                          type="button"
                          className="image-source-mini-btn is-danger"
                          onClick={clearSourceImage}
                          disabled={!!busy}
                          title="Retirer l'image source"
                        >
                          <X size={11} />
                          <span>Retirer</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    className={`image-source-dropzone ${isDraggingSource ? "is-dragging" : ""}`}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={!!busy}
                  >
                    <Upload size={16} />
                    <div>
                      <strong>Importer une image à modifier</strong>
                      <small>PNG, JPEG, WEBP, GIF (max 10 Mo) · ou cliquez sur « Modifier » dans la galerie</small>
                    </div>
                  </button>
                )}

                {sourceImage && (
                  <div className="image-edit-mode-toggle" role="tablist" aria-label="Mode d'édition d'image">
                    {(Object.keys(EDIT_MODE_COPY) as EditMode[]).map(mode => (
                      <button
                        key={mode}
                        type="button"
                        role="tab"
                        aria-selected={editMode === mode}
                        title={EDIT_MODE_COPY[mode].title}
                        className={`image-edit-mode-btn ${editMode === mode ? "is-active" : ""}`}
                        onClick={() => selectEditMode(mode)}
                        disabled={!!busy}
                      >
                        {editModeIcon(mode, 12)}
                        <span>{EDIT_MODE_COPY[mode].label}</span>
                      </button>
                    ))}
                  </div>
                )}

                {sourceImage && isMaskEditMode(editMode) && (
                  <div className="image-inpaint-hint">
                    <span>
                      {editMode === "remove_object"
                        ? maskStrokes.length > 0
                          ? `${maskStrokes.length} tracé${maskStrokes.length > 1 ? "s" : ""} sur l’objet à supprimer — aucun prompt nécessaire.`
                          : "Peignez directement au pinceau rouge sur l’objet à effacer à droite."
                        : maskStrokes.length > 0
                          ? `${maskStrokes.length} tracé${maskStrokes.length > 1 ? "s" : ""} sur le masque — seule la zone peinte sera régénérée.`
                          : "Peignez directement sur l’image à droite pour délimiter la zone à modifier."}
                    </span>
                  </div>
                )}

                {sourceImage && editMode === "remove_background" && (
                  <div className="image-inpaint-hint">
                    <span>Détourage automatique du sujet principal vers un PNG transparent (Ideogram 1.0). Aucun prompt requis.</span>
                  </div>
                )}

                {sourceImage && editMode === "replace_background" && (
                  <div className="image-inpaint-hint">
                    <span>Ideogram 3.0 conserve automatiquement le sujet au premier plan et génère le décor décrit ci-dessous.</span>
                  </div>
                )}

                {sourceImage && editMode === "layerize" && (
                  <div className="image-inpaint-hint">
                    <span>Layerize (Ideogram 3.0) extrait chaque bloc de texte (police, taille, couleur, position) et l’image de fond nettoyée.</span>
                  </div>
                )}

                {sourceImage && !isIdeogramSelected && (
                  <div className="image-source-warning" role="status">
                    <CircleAlert size={14} />
                    <div>
                      <span>
                        L’édition et les outils spécialisés (détourage, effacement d’objet, calques) sont uniquement pris en charge par <strong>Ideogram</strong>.
                      </span>
                      <button
                        type="button"
                        className="image-source-switch-btn"
                        onClick={() => setGenerationModel(preferredIdeogramModel.id)}
                      >
                        Basculer vers {preferredIdeogramModel.name.split("(")[0].trim()}
                      </button>
                    </div>
                  </div>
                )}

                {sourceImage && editMode === "remix" && supportsIdeogramWeight && (
                  <div className="image-weight-control">
                    <div className="image-weight-header">
                      <label htmlFor="image-weight-slider">Fidélité à l’image originale (Ideogram)</label>
                      <strong>{imageWeight}%</strong>
                    </div>
                    <input
                      id="image-weight-slider"
                      type="range"
                      min={10}
                      max={100}
                      step={5}
                      value={imageWeight}
                      disabled={!!busy}
                      onChange={e => setImageWeight(Number(e.target.value))}
                    />
                    <div className="image-weight-scale">
                      <span>Plus créatif</span>
                      <span>Plus fidèle</span>
                    </div>
                  </div>
                )}
              </div>

              {(!sourceImage || !isBinaryPromptlessEditMode(editMode)) && (
                <>
                  <div className="image-studio-field-header">
                    <label htmlFor="image-studio-prompt">
                      {sourceImage ? EDIT_MODE_COPY[editMode].promptLabel : "Description de l’image"}
                    </label>
                    <span>{prompt.length}/4000</span>
                  </div>
                  <textarea
                    id="image-studio-prompt"
                    ref={promptRef}
                    value={prompt}
                    onChange={event => setPrompt(event.target.value)}
                    placeholder={
                      sourceImage
                        ? EDIT_MODE_COPY[editMode].promptPlaceholder
                        : "Décrivez votre scène, le sujet, la lumière, les couleurs, le cadrage ou le texte à intégrer entre guillemets…"
                    }
                    rows={sourceImage && editMode === "layerize" ? 2 : 4}
                    maxLength={4000}
                    disabled={!!busy}
                    onKeyDown={event => {
                      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                        event.preventDefault();
                        void generate();
                      }
                    }}
                  />
                </>
              )}

              {(!sourceImage || !isPromptOptionalEditMode(editMode)) && (
                <>
                  <div className="image-keywords-section">
                    <div className="image-keywords-header">
                      <div className="image-keywords-title">
                        <SlidersHorizontal size={12} />
                        <span>Mots-clés de style & ambiance</span>
                        <span className="image-keywords-badge">guidage IA</span>
                      </div>
                      {styleKeywords.trim() && (
                        <button
                          type="button"
                          className="image-keywords-clear"
                          onClick={() => setStyleKeywords("")}
                          disabled={!!busy}
                        >
                          Effacer
                        </button>
                      )}
                    </div>
                    <input
                      type="text"
                      className="image-keywords-input"
                      value={styleKeywords}
                      onChange={e => setStyleKeywords(e.target.value)}
                      placeholder="Ex : familial (pour une affiche), vaporeux, terrifiant, rouge..."
                      disabled={!!busy}
                      maxLength={300}
                    />
                    <div className="image-keywords-chips" aria-label="Suggestions de style">
                      {SUGGESTED_STYLE_KEYWORDS.map(tag => {
                        const active = styleKeywords
                          .split(",")
                          .map(s => s.trim().toLowerCase())
                          .includes(tag.toLowerCase());
                        return (
                          <button
                            key={tag}
                            type="button"
                            className={`image-keyword-chip ${active ? "is-active" : ""}`}
                            onClick={() => toggleStyleKeyword(tag)}
                            disabled={!!busy}
                            title={active ? `Retirer « ${tag} »` : `Ajouter « ${tag} »`}
                          >
                            {active && <Check size={10} />}
                            <span>{tag}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {(!sourceImage || editMode === "remix") && (
                    <div className="image-negative-section">
                      <div className="image-negative-header">
                        <div className="image-negative-title">
                          <Ban size={12} />
                          <span>Prompt négatif (ce qu’on ne veut pas)</span>
                          <span className="image-negative-badge">exclusion</span>
                        </div>
                        {negativePrompt.trim() && (
                          <button
                            type="button"
                            className="image-negative-clear"
                            onClick={() => setNegativePrompt("")}
                            disabled={!!busy}
                          >
                            Effacer
                          </button>
                        )}
                      </div>
                      <input
                        type="text"
                        className="image-negative-input"
                        value={negativePrompt}
                        onChange={e => setNegativePrompt(e.target.value)}
                        placeholder="Ex : flou, texte, filigrane, membres déformés, basse qualité, mauvaise anatomie..."
                        disabled={!!busy}
                        maxLength={2000}
                      />
                      <div className="image-negative-chips" aria-label="Suggestions d'exclusions">
                        {SUGGESTED_NEGATIVE_PROMPTS.map(tag => {
                          const active = negativePrompt
                            .split(",")
                            .map(s => s.trim().toLowerCase())
                            .includes(tag.toLowerCase());
                          return (
                            <button
                              key={tag}
                              type="button"
                              className={`image-negative-chip ${active ? "is-active" : ""}`}
                              onClick={() => toggleNegativePrompt(tag)}
                              disabled={!!busy}
                              title={active ? `Retirer « ${tag} »` : `Exclure « ${tag} »`}
                            >
                              {active && <Check size={10} />}
                              <span>{tag}</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="image-studio-prompt-tools">
                    <button
                      type="button"
                      className="image-improve-button"
                      disabled={!canImprove}
                      onClick={() => void improvePrompt()}
                      title={
                        config?.features.chat && !config.demo_mode
                          ? `Enrichir les détails visuels, la lumière et la composition avec ${config?.models?.find(m => m.id === improveModel)?.name || "Gemini Argon"}`
                          : "Nécessite LLM_API_KEY et le mode IA réel"
                      }
                    >
                      {busy === "improve" ? <LoaderCircle className="spin" size={15} /> : <WandSparkles size={15} />}
                      <span>{busy === "improve" ? "Amélioration en cours…" : "Améliorer le prompt"}</span>
                    </button>
                    {previousPrompt !== null && (
                      <button
                        type="button"
                        className="image-revert-button"
                        disabled={!!busy}
                        onClick={() => {
                          setPrompt(previousPrompt);
                          setPreviousPrompt(null);
                        }}
                        title="Revenir au prompt précédent"
                      >
                        <RotateCcw size={13} />
                        <span>Rétablir</span>
                      </button>
                    )}
                  </div>

                  <div className="image-style-section">
                    <div className="image-style-header">
                      <span className="image-section-label">Styles & supports prédéfinis</span>
                      <span className="image-style-count">
                        {(styleCategory === "all" ? STYLE_PRESETS : STYLE_PRESETS.filter(item => item.category === styleCategory)).length} styles
                      </span>
                    </div>
                    <div className="image-style-categories" role="tablist" aria-label="Catégories de styles">
                      {STYLE_CATEGORIES.map(category => (
                        <button
                          key={category.id}
                          type="button"
                          role="tab"
                          aria-selected={styleCategory === category.id}
                          className={`image-style-category ${styleCategory === category.id ? "is-active" : ""}`}
                          disabled={!!busy}
                          onClick={() => setStyleCategory(category.id)}
                        >
                          {category.label}
                        </button>
                      ))}
                    </div>
                    <div className="image-style-chips" aria-label="Suggestions de style">
                      {(styleCategory === "all" ? STYLE_PRESETS : STYLE_PRESETS.filter(item => item.category === styleCategory)).map(preset => (
                        <button
                          key={preset.label}
                          type="button"
                          className="image-style-chip"
                          disabled={!!busy}
                          title={preset.prompt}
                          onClick={() => applyStyleChip(preset.prompt)}
                        >
                          + {preset.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}

              <div className="image-model-gen-section">
                <div className="image-model-gen-header">
                  <div className="image-model-gen-title-group">
                    <span className="image-section-label">Modèle de génération & vision</span>
                    <span className="image-model-count-badge">
                      {availableImageModels.length} modèle{availableImageModels.length > 1 ? "s" : ""}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="image-models-refresh-btn"
                    onClick={() => void loadModels(true)}
                    disabled={loadingModels || !!busy}
                    title="Actualiser en direct les modèles et tarifs depuis OpenRouter"
                  >
                    <RefreshCw size={11} className={loadingModels ? "spin" : ""} />
                    <span>{loadingModels ? "Actualisation…" : "Actualiser"}</span>
                  </button>
                </div>

                <div
                  className="image-model-trigger-card"
                  onClick={() => setShowModelModal(true)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setShowModelModal(true);
                    }
                  }}
                  title="Cliquer pour ouvrir la modale de sélection de modèle d'image et de vision"
                >
                  <div className="image-model-trigger-top">
                    <div className="image-model-trigger-ident">
                      <div className="image-model-trigger-icon">
                        <Sparkles size={16} />
                      </div>
                      <div className="image-model-trigger-title-group">
                        <strong className="image-model-trigger-name">{selectedGenModel?.name}</strong>
                        {selectedGenModel && isFavorite(selectedGenModel.id) && (
                          <span
                            className="image-model-top-badge"
                            style={{ background: "#fef3c7", color: "#b45309", borderColor: "#fde68a" }}
                            title="Modèle favori"
                          >
                            <Star size={10} fill="currentColor" />
                            <span>Favori</span>
                          </span>
                        )}
                        {selectedGenModel?.is_top && (
                          <span className="image-model-top-badge" title="Top Collection OpenRouter">
                            <Sparkles size={10} />
                            <span>Top Collection</span>
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      className="image-model-change-btn"
                      onClick={e => {
                        e.stopPropagation();
                        setShowModelModal(true);
                      }}
                    >
                      <span>Changer</span>
                      <SlidersHorizontal size={12} />
                    </button>
                  </div>

                  {selectedGenModel?.description && (
                    <p className="image-model-trigger-desc">{selectedGenModel.description}</p>
                  )}

                  <div className="image-model-trigger-pills">
                    {selectedGenModel?.supports_image_editing && (
                      <div className="image-model-edit-pill" title="Prend en charge l'import et la modification d'images">
                        <Paintbrush size={11} />
                        <span>Édition d’image</span>
                      </div>
                    )}
                    {selectedGenModel?.pricing_text && (
                      <div className="image-model-pricing-pill" title="Tarif du modèle">
                        <Coins size={12} />
                        <span>Tarif : <strong>{selectedGenModel.pricing_text}</strong></span>
                      </div>
                    )}
                    {selectedGenModel?.supported_resolutions && selectedGenModel.supported_resolutions.length > 0 && (
                      <div className="image-model-meta-pill" title="Résolutions maximales">
                        <span>Max : {selectedGenModel.supported_resolutions[selectedGenModel.supported_resolutions.length - 1]}</span>
                      </div>
                    )}
                    <div className="image-model-meta-pill" title="Fournisseur API d’exécution">
                      <span>
                        {isIdeogramSelected
                          ? "Ideogram API"
                          : isGoogleCloudSelected
                            ? googleProviderBadgeLabel
                            : "OpenRouter API"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="image-ratio-section">
                <div className="image-ratio-header">
                  <span className="image-section-label">Format de l’image</span>
                  {sourceImage && (activeMaskEdit || isIdeogramSelected) && (
                    <span className="image-ratio-locked-hint">Proportions source conservées</span>
                  )}
                </div>
                <div className="image-ratio-grid" role="radiogroup" aria-label="Format d’image">
                  {ASPECT_RATIOS.map(item => (
                    <button
                      key={item.value}
                      type="button"
                      role="radio"
                      aria-checked={aspectRatio === item.value}
                      className={`image-ratio-option ${aspectRatio === item.value ? "is-selected" : ""}`}
                      disabled={!!busy || (!!sourceImage && (activeMaskEdit || isIdeogramSelected))}
                      onClick={() => setAspectRatio(item.value)}
                    >
                      <strong>{item.label}</strong>
                      <small>{item.hint}</small>
                    </button>
                  ))}
                </div>
              </div>

              {!sourceImage && isIdeogramSelected && (
                <button
                  type="button"
                  role="switch"
                  aria-checked={effectiveTransparentBg}
                  className={`image-transparent-toggle ${effectiveTransparentBg ? "is-active" : ""}`}
                  disabled={!!busy || generationModel === "ideogram-3-transparent"}
                  onClick={() => setTransparentBg(prev => !prev)}
                  title="Générer directement un PNG détouré sur fond transparent via Ideogram 3.0 Transparent"
                >
                  <Grid2x2 size={15} />
                  <div>
                    <strong>Fond transparent (PNG détouré)</strong>
                    <small>
                      {generationModel === "ideogram-3-transparent"
                        ? "Activé automatiquement avec Ideogram 3.0 Transparent"
                        : "Canal alpha natif via Ideogram 3.0 Transparent"}
                    </small>
                  </div>
                  <span className="image-transparent-pill">
                    {effectiveTransparentBg ? "Activé" : "Désactivé"}
                  </span>
                </button>
              )}

              <button type="submit" className="image-generate-button" disabled={!canGenerate}>
                {busy === "generate" ? (
                  <>
                    <LoaderCircle className="spin" size={17} />
                    <span>
                      {sourceImage
                        ? EDIT_MODE_COPY[editMode].busyLabel
                        : effectiveTransparentBg
                          ? "Création PNG transparent"
                          : "Création"}{" "}
                      avec {selectedGenModel?.name?.split("(")[0]?.trim() || "l'IA"}…
                    </span>
                  </>
                ) : (
                  <>
                    {sourceImage ? editModeIcon(editMode, 17) : effectiveTransparentBg ? <Grid2x2 size={17} /> : <Sparkles size={17} />}
                    <span>
                      {sourceImage
                        ? EDIT_MODE_COPY[editMode].buttonLabel
                        : effectiveTransparentBg
                          ? "Générer en PNG transparent"
                          : `Générer avec ${selectedGenModel?.name?.split("(")[0]?.trim() || "l'IA"}`}
                    </span>
                  </>
                )}
              </button>
            </form>
            )}

            <section className="image-studio-gallery" aria-label="Galerie d’images sauvegardées">
              <div className="image-gallery-header">
                <h3>Galerie sauvegardée</h3>
                <span>{images.length}</span>
              </div>
              {loadingGallery ? (
                <div className="image-gallery-empty">
                  <LoaderCircle className="spin" size={18} />
                  <span>Chargement de vos créations…</span>
                </div>
              ) : images.length > 0 ? (
                <div className="image-gallery-grid">
                  {images.map(item => (
                    <div
                      key={item.id}
                      className={`image-gallery-item ${selected?.id === item.id ? "is-active" : ""}`}
                    >
                      <button
                        type="button"
                        className="image-gallery-thumb"
                        onClick={() => {
                          setSelectedId(item.id);
                          setPreviewingSource(false);
                        }}
                        aria-label={`Afficher l’image : ${item.prompt.slice(0, 60)}`}
                      >
                        <img src={item.url} alt={item.prompt} loading="lazy" />
                        {item.mime_type === "image/svg+xml" && (
                          <span className={extStyles.thumbFormatBadge}>SVG</span>
                        )}
                        <span className="image-thumb-ratio">{item.aspect_ratio}</span>
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="image-gallery-empty">
                  <ImagePlus size={22} strokeWidth={1.4} />
                  <p>Vos images générées seront automatiquement sauvegardées ici.</p>
                </div>
              )}
            </section>
          </div>

          <div className="image-studio-viewer" aria-label="Zone de visualisation">
            {busy === "generate" ? (
              <div className="image-viewer-generating" role="status">
                <div className="image-generating-orb">
                  <LoaderCircle className="spin" size={34} />
                </div>
                <h3>
                  {studioTab !== "create" && customBusyLabel
                    ? `${customBusyLabel}…`
                    : `${selectedGenModel?.name?.split("(")[0]?.trim() || "L'IA"} ${
                        sourceImage
                          ? `${EDIT_MODE_COPY[editMode].busyLabel.toLowerCase()} en cours…`
                          : "compose votre image…"
                      }`}
                </h3>
                {studioTab === "create" && prompt.trim() && <p>« {prompt.trim()} »</p>}
                <span className="image-generating-badge">
                  {studioTab === "upscale"
                    ? "Ideogram Upscale v2 · Sauvegarde automatique"
                    : studioTab === "svg"
                      ? "Ideogram Vector 1.0 · SVG sécurisé & sauvegardé"
                      : sourceImage
                        ? `${EDIT_MODE_COPY[editMode].label} · Proportions source conservées`
                        : effectiveTransparentBg
                          ? `Format ${aspectRatio} · PNG fond transparent (Ideogram 3.0)`
                          : `Format ${aspectRatio} · Sauvegarde automatique`}
                </span>
              </div>
            ) : sourceImage && previewingSource ? (
              <>
                <div ref={stageRef} className="image-viewer-stage">
                  <img
                    ref={sourceImgRef}
                    src={sourceImage.previewUrl}
                    alt={sourceImage.name}
                    className={`${zoomed ? "is-zoomed" : ""} ${activeMaskEdit ? "is-inpaint-target" : ""}`}
                    onClick={() => {
                      if (!activeMaskEdit) setZoomed(old => !old);
                    }}
                    onLoad={event => {
                      const imgEl = event.currentTarget;
                      const nw = imgEl.naturalWidth || undefined;
                      const nh = imgEl.naturalHeight || undefined;
                      if (nw && nh && (!sourceImage.width || !sourceImage.height)) {
                        setSourceImage(prev => (prev ? { ...prev, width: nw, height: nh } : prev));
                      }
                      syncCanvasBox();
                    }}
                  />
                  {activeMaskEdit && (
                    <canvas
                      ref={maskCanvasRef}
                      className={`image-inpaint-canvas ${maskTool === "erase" ? "is-erasing" : ""}`}
                      style={
                        canvasBox
                          ? {
                              left: `${canvasBox.left}px`,
                              top: `${canvasBox.top}px`,
                              width: `${canvasBox.width}px`,
                              height: `${canvasBox.height}px`,
                            }
                          : { display: "none" }
                      }
                      onPointerDown={handleMaskPointerDown}
                      onPointerMove={handleMaskPointerMove}
                      onPointerUp={finishMaskStroke}
                      onPointerCancel={finishMaskStroke}
                    />
                  )}
                  <div className="image-stage-floating-tools">
                    <button
                      type="button"
                      className="image-stage-pill"
                      onClick={() => setZoomed(old => !old)}
                      title={zoomed ? "Réduire l’aperçu" : "Agrandir l’aperçu"}
                    >
                      {zoomed ? <Minimize2 size={14} /> : <Expand size={14} />}
                      <span>{zoomed ? "Ajuster" : "Agrandir"}</span>
                    </button>
                  </div>
                  {activeMaskEdit && (
                    <div className="image-inpaint-toolbar" role="toolbar" aria-label="Outils de masquage">
                      <button
                        type="button"
                        className={`image-inpaint-tool-btn ${maskTool === "brush" ? "is-active" : ""}`}
                        onClick={() => setMaskTool("brush")}
                        disabled={!!busy}
                        title={
                          editMode === "remove_object"
                            ? "Pinceau : marquer l’objet à effacer"
                            : "Pinceau : marquer la zone à modifier"
                        }
                      >
                        <Brush size={14} />
                        <span>Pinceau</span>
                      </button>
                      <button
                        type="button"
                        className={`image-inpaint-tool-btn ${maskTool === "erase" ? "is-active" : ""}`}
                        onClick={() => setMaskTool("erase")}
                        disabled={!!busy}
                        title="Gomme : retirer du masque"
                      >
                        <Eraser size={14} />
                        <span>Gomme</span>
                      </button>
                      <label className="image-inpaint-size-control" title="Taille du pinceau">
                        <span>Taille</span>
                        <input
                          type="range"
                          min={10}
                          max={120}
                          step={2}
                          value={brushSize}
                          disabled={!!busy}
                          onChange={e => setBrushSize(Number(e.target.value))}
                        />
                        <strong>{brushSize}px</strong>
                      </label>
                      <button
                        type="button"
                        className="image-inpaint-tool-btn"
                        onClick={() => setMaskStrokes(prev => prev.slice(0, -1))}
                        disabled={maskStrokes.length === 0 || !!busy}
                        title="Annuler le dernier tracé"
                      >
                        <Undo2 size={14} />
                      </button>
                      <button
                        type="button"
                        className="image-inpaint-tool-btn is-danger"
                        onClick={() => setMaskStrokes([])}
                        disabled={maskStrokes.length === 0 || !!busy}
                        title="Effacer tout le masque"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  )}
                </div>

                <footer className="image-viewer-details">
                  <div className="image-viewer-meta">
                    <div className="image-viewer-badges">
                      <span className="image-source-viewer-pill">
                        {studioTab === "upscale" ? (
                          <>
                            <Maximize2 size={12} />
                            Upscale HD Ideogram
                          </>
                        ) : studioTab === "svg" ? (
                          <>
                            <FileCode2 size={12} />
                            {svgOperation === "vectorize"
                              ? "Image → SVG (Ideogram Vector 1.0)"
                              : "Référence SVG (Ideogram Vector 1.0)"}
                          </>
                        ) : (
                          <>
                            {editModeIcon(editMode, 12)}
                            {editMode === "remove_object"
                              ? "Masque Effacer un objet (Ideogram 1.0)"
                              : editMode === "inpaint"
                                ? generationModel === "ideogram-4-5"
                                  ? "Masque Precise Edit (Ideogram 4.5)"
                                  : "Masque Inpaint (Ideogram 3.0)"
                                : EDIT_MODE_COPY[editMode].label}
                          </>
                        )}
                      </span>
                      {sourceImage.width && sourceImage.height && (
                        <span>{sourceImage.width}×{sourceImage.height} px</span>
                      )}
                      {sourceImage.sizeBytes && <span>{formatBytes(sourceImage.sizeBytes)}</span>}
                    </div>
                    <p className="image-viewer-prompt">
                      {studioTab === "upscale"
                        ? `${sourceImage.name} — Choisissez un modèle d’upscale et un facteur d’échelle à gauche puis lancez l’agrandissement.`
                        : studioTab === "svg"
                          ? `${sourceImage.name} — Configurez la vectorisation ou la génération SVG à gauche.`
                          : editMode === "remove_object"
                            ? `${sourceImage.name} — Peignez en rouge l’objet à supprimer puis lancez l’effacement.`
                            : editMode === "inpaint"
                              ? `${sourceImage.name} — Peignez en violet la zone à remplacer puis décrivez le résultat à gauche.`
                              : `${sourceImage.name} — Configurez l’outil choisi à gauche puis lancez l’action.`}
                    </p>
                  </div>

                  <div className="image-viewer-actions">
                    {selected && (
                      <button
                        type="button"
                        className="image-secondary-action"
                        onClick={() => setPreviewingSource(false)}
                      >
                        <Eye size={15} />
                        <span>Voir la galerie</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="image-delete-action"
                      onClick={clearSourceImage}
                      disabled={!!busy}
                      aria-label="Retirer l’image source"
                      title="Retirer l’image source"
                    >
                      <X size={15} />
                    </button>
                  </div>
                </footer>
              </>
            ) : selected ? (
              <>
                <div
                  className={`image-viewer-stage ${
                    showCheckerboard &&
                    (selected.mime_type === "image/png" || selected.mime_type === "image/svg+xml")
                      ? "is-checkerboard"
                      : ""
                  }`}
                >
                  <img
                    src={selected.url}
                    alt={selected.prompt}
                    className={zoomed ? "is-zoomed" : ""}
                    onClick={() => setZoomed(old => !old)}
                  />
                  <div className="image-stage-floating-tools">
                    {(selected.mime_type === "image/png" || selected.mime_type === "image/svg+xml") && (
                      <button
                        type="button"
                        className={`image-stage-pill ${showCheckerboard ? "is-active" : ""}`}
                        onClick={() => setShowCheckerboard(old => !old)}
                        title="Afficher ou masquer le damier de transparence"
                      >
                        <Grid2x2 size={14} />
                        <span>Damier</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className="image-stage-pill"
                      onClick={() => setZoomed(old => !old)}
                      title={zoomed ? "Réduire l’aperçu" : "Agrandir l’aperçu"}
                    >
                      {zoomed ? <Minimize2 size={14} /> : <Expand size={14} />}
                      <span>{zoomed ? "Ajuster" : "Agrandir"}</span>
                    </button>
                    <a
                      className="image-stage-pill"
                      href={selected.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title="Ouvrir dans un nouvel onglet"
                    >
                      <ExternalLink size={14} />
                      <span>Plein écran</span>
                    </a>
                  </div>
                </div>

                {(layerizeBlocksByImageId[selected.id] || selected.text_blocks) && (() => {
                  const blocks = layerizeBlocksByImageId[selected.id] ?? selected.text_blocks ?? [];
                  return (
                    <section className="image-layerize-panel" aria-label="Calques de texte détectés par Layerize">
                      <div className="image-layerize-header">
                        <div className="image-layerize-title">
                          <Type size={14} />
                          <strong>Calques de texte détectés (Layerize)</strong>
                          <span className="image-layerize-count">{blocks.length} bloc{blocks.length > 1 ? "s" : ""}</span>
                        </div>
                        {blocks.length > 0 && (
                          <button
                            type="button"
                            className="image-layerize-copy-all"
                            onClick={() => void copyLayerizeJson(selected.id, blocks)}
                          >
                            {copiedLayerizeJsonId === selected.id ? <Check size={12} /> : <Copy size={12} />}
                            <span>{copiedLayerizeJsonId === selected.id ? "JSON copié" : "Copier JSON"}</span>
                          </button>
                        )}
                      </div>
                      {blocks.length === 0 ? (
                        <p className="image-layerize-empty">Aucun bloc de texte détecté dans cette image.</p>
                      ) : (
                        <div className="image-layerize-list">
                          {blocks.map((block, index) => {
                            const validColor =
                              block.color && /^#[0-9a-fA-F]{3,8}$/.test(block.color) ? block.color : null;
                            return (
                              <div key={`${block.text}-${index}`} className="image-layerize-item">
                                <div className="image-layerize-item-main">
                                  <div className="image-layerize-item-top">
                                    <span className="image-layerize-text">« {block.text} »</span>
                                    {block.role && <span className="image-layerize-role">{block.role}</span>}
                                  </div>
                                  <div className="image-layerize-meta">
                                    {block.font_name && <span>Police : {block.font_name}</span>}
                                    {typeof block.font_size === "number" && (
                                      <span>{Math.round(block.font_size)} px</span>
                                    )}
                                    {validColor && (
                                      <span className="image-layerize-color">
                                        <i className="image-layerize-swatch" style={{ backgroundColor: validColor }} />
                                        {validColor}
                                      </span>
                                    )}
                                    <span>
                                      Pos ({Math.round(block.x)}, {Math.round(block.y)}) · {Math.round(block.width)}×{Math.round(block.height)}
                                    </span>
                                  </div>
                                </div>
                                <button
                                  type="button"
                                  className="image-layerize-copy-btn"
                                  onClick={() => void copyLayerizeText(block.text, index)}
                                  title="Copier le texte de ce calque"
                                >
                                  {copiedBlockIndex === index ? <Check size={13} /> : <Copy size={13} />}
                                </button>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </section>
                  );
                })()}

                <footer className="image-viewer-details">
                  <div className="image-viewer-meta">
                    <div className="image-viewer-badges">
                      <span className="image-saved-pill">
                        <Check size={12} /> Sauvegardée
                      </span>
                      {selected.mime_type === "image/svg+xml" && <span>Vecteur SVG</span>}
                      <span>Format {selected.aspect_ratio}</span>
                      {selected.output_width && selected.output_height && (
                        <span>
                          {selected.output_width}×{selected.output_height} px
                        </span>
                      )}
                      <span>{formatBytes(selected.size)}</span>
                      <span>{formatDate(selected.created_at)}</span>
                    </div>
                    <p className="image-viewer-prompt">{selected.prompt}</p>
                  </div>

                  <div className="image-viewer-actions">
                    {selected.mime_type !== "image/svg+xml" ? (
                      <>
                        <button
                          type="button"
                          className="image-edit-source-button"
                          onClick={() => loadGalleryImageForEdit(selected)}
                          disabled={!!busy}
                          title="Charger cette image comme source pour lui apporter des modifications"
                        >
                          <Paintbrush size={15} />
                          <span>Modifier</span>
                        </button>
                        <button
                          type="button"
                          className="image-secondary-action"
                          onClick={() => loadGalleryImageForTool(selected, "upscale")}
                          disabled={!!busy}
                          title="Agrandir cette image avec l'un des 8 modèles Upscale Ideogram v2"
                        >
                          <Maximize2 size={15} />
                          <span>Upscaler</span>
                        </button>
                        <button
                          type="button"
                          className="image-secondary-action"
                          onClick={() => loadGalleryImageForTool(selected, "svg")}
                          disabled={!!busy}
                          title="Vectoriser cette image en fichier SVG éditable"
                        >
                          <FileCode2 size={15} />
                          <span>Image → SVG</span>
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="image-secondary-action"
                        onClick={() => void copySvgSourceCode(selected)}
                        disabled={!!busy}
                        title="Copier le code XML du fichier SVG dans le presse-papiers"
                      >
                        {copiedSvgCodeId === selected.id ? <Check size={15} /> : <FileCode2 size={15} />}
                        <span>{copiedSvgCodeId === selected.id ? "SVG copié" : "Copier le SVG"}</span>
                      </button>
                    )}
                    <a
                      className="image-download-button"
                      href={selected.download_url}
                      download={selected.filename}
                    >
                      <Download size={15} />
                      <span>Télécharger</span>
                    </a>
                    <button
                      type="button"
                      className="image-secondary-action"
                      onClick={() => reuseImageSettings(selected)}
                      disabled={!!busy}
                    >
                      <WandSparkles size={15} />
                      <span>Réutiliser le prompt</span>
                    </button>
                    <button
                      type="button"
                      className="image-secondary-action"
                      onClick={() => void copyPrompt(selected)}
                    >
                      {copiedId === selected.id ? <Check size={15} /> : <Copy size={15} />}
                      <span>{copiedId === selected.id ? "Copié" : "Copier"}</span>
                    </button>
                    <button
                      type="button"
                      className="image-delete-action"
                      onClick={() => void deleteImage(selected)}
                      disabled={!!busy}
                      aria-label="Supprimer cette image de la galerie"
                      title="Supprimer de la galerie"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </footer>
              </>
            ) : (
              <div className="image-viewer-empty">
                <div className="image-empty-illustration">
                  <ImagePlus size={36} strokeWidth={1.3} />
                </div>
                <h3>Votre zone de visualisation dédiée</h3>
                <p>
                  Rédigez une idée à gauche, enrichissez-la avec <strong>Améliorer le prompt</strong>, choisissez votre format et lancez la génération.
                </p>
              </div>
            )}
          </div>
        </div>
      </section>

      {showModelModal && (
        <ImageModelModal
          currentModel={generationModel}
          models={availableImageModels}
          onSelectModel={id => setGenerationModel(id)}
          onClose={() => setShowModelModal(false)}
          onRefreshModels={() => loadModels(true)}
        />
      )}
    </div>
  );
}

