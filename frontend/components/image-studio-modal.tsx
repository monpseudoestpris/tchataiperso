"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  Ban, Check, CircleAlert, Coins, Copy, Download, Expand, ExternalLink, ImagePlus,
  LoaderCircle, Minimize2, RefreshCw, RotateCcw, SlidersHorizontal, Sparkles, Trash2, WandSparkles, X,
} from "lucide-react";
import { api, errorMessage, type Config, type GeneratedImage, type ImageModel } from "@/lib/api";
import { ImageModelModal } from "@/components/image-model-modal";

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

type ImageStudioModalProps = {
  config: Config | null;
  initialPrompt?: string;
  onClose: () => void;
};

export function ImageStudioModal({ config, initialPrompt = "", onClose }: ImageStudioModalProps) {
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
  const promptRef = useRef<HTMLTextAreaElement>(null);

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
    (config?.models?.some(m => m.id === "openai/gpt-6-luna") ? "openai/gpt-6-luna" : config?.default_model || "openai/gpt-6-luna");
  const [improveModel, setImproveModel] = useState<string>(preferredModel);

  const [dynamicImageModels, setDynamicImageModels] = useState<ImageModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  const availableImageModels =
    dynamicImageModels.length > 0
      ? dynamicImageModels
      : (config?.image_models && config.image_models.length > 0
          ? config.image_models
          : [{ id: "ideogram", name: "Ideogram v2 (Sélection auto)", provider: "ideogram" as const }]);

  const initialGenModel = config?.default_image_model || availableImageModels[0]?.id || "ideogram";
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
  const topModels = availableImageModels.filter(m => m.is_top);
  const otherModels = availableImageModels.filter(m => !m.is_top);

  useEffect(() => {
    if (config?.image_prompt_model) {
      setImproveModel(config.image_prompt_model);
    } else if (config?.models?.some(m => m.id === "openai/gpt-6-luna")) {
      setImproveModel("openai/gpt-6-luna");
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
    promptRef.current?.focus();
  }, []);

  const selected = images.find(item => item.id === selectedId) ?? images[0] ?? null;
  const canGenerate =
    !!config?.features.image_generation &&
    !config.demo_mode &&
    availableImageModels.length > 0 &&
    !!prompt.trim() &&
    prompt.length <= 4000 &&
    !busy;
  const canImprove = !!config?.features.chat && !config.demo_mode && !!prompt.trim() && prompt.length <= 4000 && !busy;

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
    setBusy("generate");
    setError("");
    try {
      const created = await api<GeneratedImage>("/images", {
        method: "POST",
        body: JSON.stringify({
          prompt: prompt.trim(),
          aspect_ratio: aspectRatio,
          negative_prompt: negativePrompt.trim() || undefined,
          model: generationModel,
        }),
      });
      setImages(current => [created, ...current]);
      setSelectedId(created.id);
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

  function reuseImageSettings(target: GeneratedImage) {
    if (busy) return;
    setPrompt(target.prompt);
    setAspectRatio(target.aspect_ratio);
    setPreviousPrompt(null);
    promptRef.current?.focus();
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
              La génération d’images nécessite une clé <code>IDEOGRAM_API_KEY</code> ou <code>LLM_API_KEY</code> (OpenRouter) active côté serveur. Vous pouvez toujours consulter et télécharger vos images sauvegardées.
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
          <div className="image-studio-controls">
            <form className="image-studio-form" onSubmit={event => void generate(event)}>
              <div className="image-studio-field-header">
                <label htmlFor="image-studio-prompt">Description de l’image</label>
                <span>{prompt.length}/4000</span>
              </div>
              <textarea
                id="image-studio-prompt"
                ref={promptRef}
                value={prompt}
                onChange={event => setPrompt(event.target.value)}
                placeholder="Décrivez votre scène, le sujet, la lumière, les couleurs, le cadrage ou le texte à intégrer entre guillemets…"
                rows={4}
                maxLength={4000}
                disabled={!!busy}
                onKeyDown={event => {
                  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault();
                    void generate();
                  }
                }}
              />

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

              <div className="image-studio-prompt-tools">
                <button
                  type="button"
                  className="image-improve-button"
                  disabled={!canImprove}
                  onClick={() => void improvePrompt()}
                  title={
                    config?.features.chat && !config.demo_mode
                      ? `Enrichir les détails visuels, la lumière et la composition avec ${config?.models?.find(m => m.id === improveModel)?.name || "l'IA"}`
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
                    <div className="image-model-meta-pill" title="Fournisseur API">
                      <span>{selectedGenModel?.provider === "ideogram" ? "Ideogram v2" : "OpenRouter API"}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="image-ratio-section">
                <span className="image-section-label">Format de l’image</span>
                <div className="image-ratio-grid" role="radiogroup" aria-label="Format d’image">
                  {ASPECT_RATIOS.map(item => (
                    <button
                      key={item.value}
                      type="button"
                      role="radio"
                      aria-checked={aspectRatio === item.value}
                      className={`image-ratio-option ${aspectRatio === item.value ? "is-selected" : ""}`}
                      disabled={!!busy}
                      onClick={() => setAspectRatio(item.value)}
                    >
                      <strong>{item.label}</strong>
                      <small>{item.hint}</small>
                    </button>
                  ))}
                </div>
              </div>

              <button type="submit" className="image-generate-button" disabled={!canGenerate}>
                {busy === "generate" ? (
                  <>
                    <LoaderCircle className="spin" size={17} />
                    <span>Création avec {selectedGenModel?.name?.split("(")[0]?.trim() || "l'IA"}…</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={17} />
                    <span>Générer avec {selectedGenModel?.name?.split("(")[0]?.trim() || "l'IA"}</span>
                  </>
                )}
              </button>
            </form>

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
                        onClick={() => setSelectedId(item.id)}
                        aria-label={`Afficher l’image : ${item.prompt.slice(0, 60)}`}
                      >
                        <img src={item.url} alt={item.prompt} loading="lazy" />
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
                <h3>Ideogram compose votre image…</h3>
                <p>« {prompt.trim()} »</p>
                <span className="image-generating-badge">Format {aspectRatio} · Sauvegarde automatique</span>
              </div>
            ) : selected ? (
              <>
                <div className="image-viewer-stage">
                  <img
                    src={selected.url}
                    alt={selected.prompt}
                    className={zoomed ? "is-zoomed" : ""}
                    onClick={() => setZoomed(old => !old)}
                  />
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
                    <a
                      className="image-stage-pill"
                      href={selected.url}
                      target="_blank"
                      rel="noreferrer"
                      title="Ouvrir dans un nouvel onglet"
                    >
                      <ExternalLink size={14} />
                      <span>Plein écran</span>
                    </a>
                  </div>
                </div>

                <footer className="image-viewer-details">
                  <div className="image-viewer-meta">
                    <div className="image-viewer-badges">
                      <span className="image-saved-pill">
                        <Check size={12} /> Sauvegardée
                      </span>
                      <span>Format {selected.aspect_ratio}</span>
                      <span>{formatBytes(selected.size)}</span>
                      <span>{formatDate(selected.created_at)}</span>
                    </div>
                    <p className="image-viewer-prompt">{selected.prompt}</p>
                  </div>

                  <div className="image-viewer-actions">
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

