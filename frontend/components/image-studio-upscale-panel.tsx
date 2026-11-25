"use client";

import { useState, type FormEvent } from "react";
import {
  Check,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Eye,
  LoaderCircle,
  Maximize2,
  SlidersHorizontal,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  errorMessage,
  type GeneratedImage,
  type UpscaleFactor,
  type UpscaleImagePayload,
  type UpscaleModelId,
  type UpscaleModelSpec,
  type UpscaleResolutionTier,
} from "@/lib/api";
import styles from "./image-studio-ext.module.css";

export type StudioSourceImage = {
  kind: "upload" | "gallery";
  name: string;
  previewUrl: string;
  dataUrl?: string;
  sourceImageId?: string;
  mimeType?: string;
  sizeBytes?: number;
  width?: number;
  height?: number;
};

export const FALLBACK_UPSCALE_MODELS: UpscaleModelSpec[] = [
  {
    id: "auto",
    name: "Ideogram Auto",
    kind: "automatic",
    kind_label: "Automatique",
    description: "Sélectionne automatiquement le modèle d'agrandissement optimal selon l'image.",
    supported_factors: ["x2", "x4", "x8"],
    supported_tiers: [],
    max_side_px: 8192,
    max_megapixels: null,
    supports_prompt: false,
    supports_autoprompt: false,
    supports_creativity: false,
    supports_color_preservation: false,
    supports_enhancement_strength: false,
    supports_topaz_controls: false,
    supports_redefine_controls: false,
    supports_seed: true,
  },
  {
    id: "topaz-standard-2",
    name: "Topaz Standard V2",
    kind: "faithful",
    kind_label: "Fidèle",
    description: "Agrandit et accentue la netteté globale en restant strictement fidèle à l'image source.",
    supported_factors: ["x2", "x4", "x8"],
    supported_tiers: [],
    max_side_px: 8192,
    max_megapixels: null,
    supports_prompt: false,
    supports_autoprompt: false,
    supports_creativity: false,
    supports_color_preservation: false,
    supports_enhancement_strength: false,
    supports_topaz_controls: true,
    supports_redefine_controls: false,
    supports_seed: false,
  },
  {
    id: "topaz-text-refine",
    name: "Topaz Text Refine",
    kind: "faithful",
    kind_label: "Fidèle · Typographie",
    description: "Préserve la netteté des grands titres comme des petits caractères, étiquettes et logos.",
    supported_factors: ["x2", "x4", "x8"],
    supported_tiers: [],
    max_side_px: 8192,
    max_megapixels: null,
    supports_prompt: false,
    supports_autoprompt: false,
    supports_creativity: false,
    supports_color_preservation: false,
    supports_enhancement_strength: false,
    supports_topaz_controls: true,
    supports_redefine_controls: false,
    supports_seed: false,
  },
  {
    id: "topaz-wonder-4",
    name: "Topaz Wonder 4",
    kind: "detail",
    kind_label: "Détails & Visages · 100 MP",
    description: "Supprime bruit, flou et artefacts JPEG tout en restaurant les visages en une passe (x2 ou x4, max 100 MP).",
    supported_factors: ["x2", "x4"],
    supported_tiers: [],
    max_side_px: null,
    max_megapixels: 100,
    supports_prompt: false,
    supports_autoprompt: false,
    supports_creativity: false,
    supports_color_preservation: false,
    supports_enhancement_strength: false,
    supports_topaz_controls: false,
    supports_redefine_controls: false,
    supports_seed: false,
  },
  {
    id: "topaz-wonder-3-5",
    name: "Topaz Wonder 3.5",
    kind: "detail",
    kind_label: "Reconstruction de détails",
    description: "Reconstruit la matière et les micro-détails avec dosage d'intensité (faible, moyenne, élevée).",
    supported_factors: ["x2", "x4", "x8"],
    supported_tiers: [],
    max_side_px: 8192,
    max_megapixels: null,
    supports_prompt: false,
    supports_autoprompt: false,
    supports_creativity: false,
    supports_color_preservation: false,
    supports_enhancement_strength: true,
    supports_topaz_controls: false,
    supports_redefine_controls: false,
    supports_seed: true,
  },
  {
    id: "topaz-bloom-2",
    name: "Topaz Bloom 2",
    kind: "creative",
    kind_label: "Créatif",
    description: "Enrichit les textures fines avec créativité réglable (1–9), conservation des couleurs et prompt optionnel.",
    supported_factors: ["x2", "x4", "x8"],
    supported_tiers: [],
    max_side_px: 8192,
    max_megapixels: null,
    supports_prompt: true,
    supports_autoprompt: false,
    supports_creativity: true,
    supports_color_preservation: true,
    supports_enhancement_strength: false,
    supports_topaz_controls: false,
    supports_redefine_controls: false,
    supports_seed: true,
  },
  {
    id: "topaz-redefine",
    name: "Topaz Redefine",
    kind: "creative",
    kind_label: "Créatif avancé",
    description: "Réinterprétation générative poussée guidée par prompt ou autoprompt, texture, détail et visages.",
    supported_factors: ["x2", "x4", "x8"],
    supported_tiers: [],
    max_side_px: 8192,
    max_megapixels: null,
    supports_prompt: true,
    supports_autoprompt: true,
    supports_creativity: true,
    supports_color_preservation: false,
    supports_enhancement_strength: false,
    supports_topaz_controls: false,
    supports_redefine_controls: true,
    supports_seed: true,
  },
  {
    id: "nano-banana-pro",
    name: "Nano Banana Pro",
    kind: "regenerate",
    kind_label: "Régénération 1K / 2K / 4K",
    description: "Régénère l'image au palier 1K, 2K ou 4K en préservant sa composition et son style.",
    supported_factors: [],
    supported_tiers: ["1K", "2K", "4K"],
    max_side_px: null,
    max_megapixels: null,
    supports_prompt: true,
    supports_autoprompt: false,
    supports_creativity: false,
    supports_color_preservation: false,
    supports_enhancement_strength: false,
    supports_topaz_controls: false,
    supports_redefine_controls: false,
    supports_seed: false,
  },
];

function formatBytesCompact(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function factorMultiplier(f: UpscaleFactor): number {
  if (f === "x4") return 4;
  if (f === "x8") return 8;
  return 2;
}

type ImageStudioUpscalePanelProps = {
  models: UpscaleModelSpec[];
  loadingModels: boolean;
  sourceImage: StudioSourceImage | null;
  previewingSource: boolean;
  busy: boolean;
  canUseIdeogram: boolean;
  onPickFile: () => void;
  onTogglePreviewSource: () => void;
  onClearSource: () => void;
  onUpscaleCreated: (created: GeneratedImage) => void;
  onError: (message: string) => void;
  onBusyChange: (nextBusy: "generate" | null, statusLabel?: string) => void;
};

export function ImageStudioUpscalePanel({
  models,
  loadingModels,
  sourceImage,
  previewingSource,
  busy,
  canUseIdeogram,
  onPickFile,
  onTogglePreviewSource,
  onClearSource,
  onUpscaleCreated,
  onError,
  onBusyChange,
}: ImageStudioUpscalePanelProps) {
  const catalog = models.length > 0 ? models : FALLBACK_UPSCALE_MODELS;
  const [modelId, setModelId] = useState<UpscaleModelId>("auto");
  const [factor, setFactor] = useState<UpscaleFactor>("x2");
  const [tier, setTier] = useState<UpscaleResolutionTier>("2K");
  const [prompt, setPrompt] = useState("");
  const [autoprompt, setAutoprompt] = useState(false);
  const [creativity, setCreativity] = useState(3);
  const [colorPreservation, setColorPreservation] = useState(true);
  const [enhancementStrength, setEnhancementStrength] = useState<"low" | "medium" | "high">("high");
  const [texture, setTexture] = useState(1);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [useCustomFineControls, setUseCustomFineControls] = useState(false);
  const [strength, setStrength] = useState(0.5);
  const [sharpen, setSharpen] = useState(0.35);
  const [denoise, setDenoise] = useState(0.25);
  const [fixCompression, setFixCompression] = useState(0.3);
  const [detailEnabled, setDetailEnabled] = useState(false);
  const [detailStrength, setDetailStrength] = useState(4);
  const [faceEnhancement, setFaceEnhancement] = useState(false);
  const [subjectDetection, setSubjectDetection] = useState<"all" | "foreground" | "background">("all");
  const [seedInput, setSeedInput] = useState("");

  const activeSpec = catalog.find(m => m.id === modelId) ?? catalog[0];
  const effectiveFactor: UpscaleFactor =
    activeSpec.supported_factors.length > 0 && !activeSpec.supported_factors.includes(factor)
      ? activeSpec.supported_factors[0]
      : factor;

  const isUnsupportedSourceFormat =
    !!sourceImage?.mimeType && !["image/png", "image/jpeg", "image/webp"].includes(sourceImage.mimeType);

  function evaluateFactor(f: UpscaleFactor) {
    if (!sourceImage?.width || !sourceImage?.height) {
      return { outW: null, outH: null, mp: null, blockedReason: null };
    }
    const mult = factorMultiplier(f);
    const outW = sourceImage.width * mult;
    const outH = sourceImage.height * mult;
    const mp = (outW * outH) / 1_000_000;
    if (activeSpec.max_side_px && (outW > activeSpec.max_side_px || outH > activeSpec.max_side_px)) {
      return {
        outW,
        outH,
        mp,
        blockedReason: `Dépasse la limite de ${activeSpec.max_side_px} px par côté (${outW}×${outH} px).`,
      };
    }
    if (activeSpec.max_megapixels && mp > activeSpec.max_megapixels) {
      return {
        outW,
        outH,
        mp,
        blockedReason: `Dépasse la limite de ${activeSpec.max_megapixels} MP (${mp.toFixed(1)} MP).`,
      };
    }
    return { outW, outH, mp, blockedReason: null };
  }

  const activeProjection =
    activeSpec.supported_factors.length > 0 ? evaluateFactor(effectiveFactor) : null;

  const canSubmit =
    canUseIdeogram &&
    !!sourceImage &&
    !isUnsupportedSourceFormat &&
    !activeProjection?.blockedReason &&
    !busy;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit || !sourceImage) return;
    onError("");

    const parsedSeed = seedInput.trim() ? Number.parseInt(seedInput.trim(), 10) : undefined;
    if (parsedSeed !== undefined && (Number.isNaN(parsedSeed) || parsedSeed < 0 || parsedSeed > 2147483647)) {
      onError("La graine (seed) doit être un entier compris entre 0 et 2 147 483 647.");
      return;
    }

    const payload: UpscaleImagePayload = {
      model: activeSpec.id,
      reference_image_data: sourceImage.dataUrl,
      source_image_id: sourceImage.sourceImageId,
    };

    if (activeSpec.supported_tiers.length > 0) {
      payload.resolution_tier = tier;
    } else {
      payload.upscale_factor = effectiveFactor;
    }

    if (activeSpec.supports_seed && parsedSeed !== undefined) {
      payload.seed = parsedSeed;
    }

    if (activeSpec.supports_enhancement_strength) {
      payload.enhancement_strength = enhancementStrength;
    }

    if (activeSpec.supports_autoprompt && autoprompt) {
      payload.autoprompt = true;
    } else if (activeSpec.supports_prompt && prompt.trim()) {
      payload.prompt = prompt.trim();
    }

    if (activeSpec.supports_creativity) {
      payload.creativity = creativity;
    }

    if (activeSpec.supports_color_preservation) {
      payload.color_preservation = colorPreservation;
    }

    if (activeSpec.supports_redefine_controls) {
      payload.texture = texture;
      if (useCustomFineControls) {
        payload.detail = detailEnabled;
        if (detailEnabled) payload.detail_strength = detailStrength;
        payload.sharpen = sharpen;
        payload.denoise = denoise;
        payload.face_enhancement = faceEnhancement;
        payload.subject_detection = subjectDetection;
      }
    } else if (activeSpec.supports_topaz_controls && useCustomFineControls) {
      payload.strength = strength;
      payload.sharpen = sharpen;
      payload.denoise = denoise;
      payload.fix_compression = fixCompression;
      payload.face_enhancement = faceEnhancement;
      payload.subject_detection = subjectDetection;
    }

    const badge = activeSpec.supported_tiers.length > 0 ? tier : effectiveFactor.toUpperCase();
    onBusyChange("generate", `Upscale ${badge} avec ${activeSpec.name}`);
    try {
      const created = await api<GeneratedImage>("/images/upscale", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onUpscaleCreated(created);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      onBusyChange(null);
    }
  }

  return (
    <form className={styles.panelForm} onSubmit={event => void handleSubmit(event)}>
      {/* 1. Image source */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.sectionTitle}>Image source à agrandir</span>
          <span className={styles.pillNeutral}>PNG · JPEG · WEBP</span>
        </div>

        {sourceImage ? (
          <div className={styles.sourceRow}>
            <button
              type="button"
              className={styles.sourceThumb}
              onClick={onTogglePreviewSource}
              title="Afficher / masquer l'image source dans le visualiseur"
            >
              <img src={sourceImage.previewUrl} alt={sourceImage.name} />
            </button>
            <div className={styles.sourceMeta}>
              <strong className={styles.sourceName} title={sourceImage.name}>
                {sourceImage.name}
              </strong>
              <span className={styles.sourceDims}>
                {sourceImage.width && sourceImage.height
                  ? `${sourceImage.width}×${sourceImage.height} px`
                  : "Dimensions détectées à l’envoi"}
                {sourceImage.sizeBytes ? ` · ${formatBytesCompact(sourceImage.sizeBytes)}` : ""}
              </span>
              <div className={styles.sourceActions}>
                <button
                  type="button"
                  className={`${styles.miniBtn} ${previewingSource ? styles.miniBtnActive : ""}`}
                  onClick={onTogglePreviewSource}
                  disabled={busy}
                >
                  <Eye size={11} />
                  <span>{previewingSource ? "Affichée" : "Voir"}</span>
                </button>
                <button type="button" className={styles.miniBtn} onClick={onPickFile} disabled={busy}>
                  <Upload size={11} />
                  <span>Remplacer</span>
                </button>
                <button
                  type="button"
                  className={`${styles.miniBtn} ${styles.miniBtnDanger}`}
                  onClick={onClearSource}
                  disabled={busy}
                >
                  <X size={11} />
                  <span>Retirer</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <button type="button" className={styles.dropzone} onClick={onPickFile} disabled={busy}>
            <Upload size={16} className={styles.dropzoneIcon} />
            <div className={styles.dropzoneText}>
              <strong>Importer une image à agrandir</strong>
              <small>PNG, JPEG ou WEBP · ou cliquez sur « Upscaler » sous une image de la galerie</small>
            </div>
          </button>
        )}

        {isUnsupportedSourceFormat && (
          <div className={styles.warningBox} role="alert">
            <CircleAlert size={14} />
            <span>
              L’upscale Ideogram v2 accepte uniquement les images matricielles <strong>PNG, JPEG ou WEBP</strong>.
            </span>
          </div>
        )}
      </div>

      {/* 2. Choix parmi les 8 modèles d'upscale */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.sectionTitle}>Modèle d’upscale Ideogram v2</span>
          <span className={styles.pillAccent}>
            {loadingModels ? "Chargement…" : `${catalog.length} modèles`}
          </span>
        </div>

        <div className={styles.modelList} role="radiogroup" aria-label="Modèles d'upscale">
          {catalog.map(item => {
            const selected = item.id === activeSpec.id;
            return (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={`${styles.modelOption} ${selected ? styles.modelOptionSelected : ""}`}
                onClick={() => setModelId(item.id)}
                disabled={busy}
              >
                <div className={styles.modelOptionTop}>
                  <span className={styles.modelOptionName} title={item.name}>
                    {item.name}
                  </span>
                  {selected && <Check size={12} />}
                </div>
                <span className={styles.modelOptionKind}>{item.kind_label}</span>
              </button>
            );
          })}
        </div>

        <p className={styles.modelDesc}>{activeSpec.description}</p>
      </div>

      {/* 3. Facteur d'agrandissement ou Palier de résolution */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.sectionTitle}>
            {activeSpec.supported_tiers.length > 0
              ? "Palier de résolution cible"
              : "Facteur d’agrandissement"}
          </span>
          <span className={styles.pillNeutral}>
            {activeSpec.max_side_px
              ? `Max ${activeSpec.max_side_px} px`
              : activeSpec.max_megapixels
                ? `Max ${activeSpec.max_megapixels} MP`
                : "Ratio préservé"}
          </span>
        </div>

        {activeSpec.supported_tiers.length > 0 ? (
          <div className={styles.segmentedRow} role="radiogroup" aria-label="Palier de résolution">
            {activeSpec.supported_tiers.map(t => (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={tier === t}
                className={`${styles.segmentBtn} ${tier === t ? styles.segmentBtnSelected : ""}`}
                onClick={() => setTier(t)}
                disabled={busy}
              >
                <strong>{t}</strong>
                <small>{t === "1K" ? "Standard" : t === "2K" ? "Haute déf." : "Ultra HD"}</small>
              </button>
            ))}
          </div>
        ) : (
          <div className={styles.segmentedRow} role="radiogroup" aria-label="Facteur d'agrandissement">
            {activeSpec.supported_factors.map(f => {
              const proj = evaluateFactor(f);
              const isSelected = effectiveFactor === f;
              return (
                <button
                  key={f}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  className={`${styles.segmentBtn} ${isSelected ? styles.segmentBtnSelected : ""}`}
                  onClick={() => setFactor(f)}
                  disabled={busy || !!proj.blockedReason}
                  title={proj.blockedReason ?? `Agrandir en ${f.toUpperCase()}`}
                >
                  <strong>{f.toUpperCase()}</strong>
                  <small>
                    {proj.outW && proj.outH ? `${proj.outW}×${proj.outH}` : f === "x2" ? "×2" : f === "x4" ? "×4" : "×8"}
                  </small>
                </button>
              );
            })}
          </div>
        )}

        {activeProjection?.outW && activeProjection.outH && activeProjection.mp !== null && (
          <div className={styles.outputReadout}>
            <span>Sortie estimée</span>
            <strong>
              {activeProjection.outW}×{activeProjection.outH} px · {activeProjection.mp.toFixed(1)} MP
            </strong>
          </div>
        )}

        {activeProjection?.blockedReason && (
          <div className={styles.warningBox} role="alert">
            <CircleAlert size={14} />
            <span>{activeProjection.blockedReason} Choisissez un facteur inférieur ou Topaz Wonder 4 (100 MP).</span>
          </div>
        )}
      </div>

      {/* 4. Contrôles spécifiques au modèle choisi */}
      {(activeSpec.supports_enhancement_strength ||
        activeSpec.supports_prompt ||
        activeSpec.supports_autoprompt ||
        activeSpec.supports_creativity ||
        activeSpec.supports_color_preservation ||
        activeSpec.supports_redefine_controls ||
        activeSpec.supports_topaz_controls ||
        activeSpec.supports_seed) && (
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={styles.sectionTitle}>Paramètres du modèle</span>
            <span className={styles.pillNeutral}>{activeSpec.name}</span>
          </div>

          {activeSpec.supports_enhancement_strength && (
            <div className={styles.segmentedRow} role="radiogroup" aria-label="Intensité de reconstruction">
              {(
                [
                  { id: "low", label: "Faible", hint: "Fidèle" },
                  { id: "medium", label: "Moyenne", hint: "Équilibrée" },
                  { id: "high", label: "Élevée", hint: "Détaillée" },
                ] as const
              ).map(opt => (
                <button
                  key={opt.id}
                  type="button"
                  role="radio"
                  aria-checked={enhancementStrength === opt.id}
                  className={`${styles.segmentBtn} ${enhancementStrength === opt.id ? styles.segmentBtnSelected : ""}`}
                  onClick={() => setEnhancementStrength(opt.id)}
                  disabled={busy}
                >
                  <strong>{opt.label}</strong>
                  <small>{opt.hint}</small>
                </button>
              ))}
            </div>
          )}

          {activeSpec.supports_autoprompt && (
            <button
              type="button"
              role="switch"
              aria-checked={autoprompt}
              className={`${styles.switchRow} ${autoprompt ? styles.switchRowActive : ""}`}
              onClick={() => setAutoprompt(prev => !prev)}
              disabled={busy}
            >
              <div className={styles.switchLabelGroup}>
                <strong>Autoprompt automatique</strong>
                <small>Le modèle décrit lui-même la scène pour guider la reconstruction</small>
              </div>
              <span className={styles.switchBadge}>{autoprompt ? "Activé" : "Manuel"}</span>
            </button>
          )}

          {activeSpec.supports_prompt && !(activeSpec.supports_autoprompt && autoprompt) && (
            <>
              <div className={styles.inlineFieldRow}>
                <label htmlFor="upscale-prompt-input">Guidage textuel (optionnel)</label>
                <span className={styles.pillNeutral}>{prompt.length}/1024</span>
              </div>
              <textarea
                id="upscale-prompt-input"
                className={styles.textarea}
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                placeholder="Optionnel : précisez les matières, l’éclairage ou les détails fins à accentuer…"
                maxLength={1024}
                rows={2}
                disabled={busy}
              />
            </>
          )}

          {activeSpec.supports_creativity && (
            <div className={styles.sliderField}>
              <div className={styles.sliderHeader}>
                <label htmlFor="upscale-creativity-slider">Créativité générative (1 = fidèle, 9 = inventif)</label>
                <strong>{creativity}/9</strong>
              </div>
              <input
                id="upscale-creativity-slider"
                type="range"
                className={styles.sliderInput}
                min={1}
                max={9}
                step={1}
                value={creativity}
                disabled={busy}
                onChange={e => setCreativity(Number(e.target.value))}
              />
            </div>
          )}

          {activeSpec.supports_redefine_controls && (
            <div className={styles.sliderField}>
              <div className={styles.sliderHeader}>
                <label htmlFor="upscale-texture-slider">Grain & micro-textures (1 à 5)</label>
                <strong>{texture}/5</strong>
              </div>
              <input
                id="upscale-texture-slider"
                type="range"
                className={styles.sliderInput}
                min={1}
                max={5}
                step={1}
                value={texture}
                disabled={busy}
                onChange={e => setTexture(Number(e.target.value))}
              />
            </div>
          )}

          {activeSpec.supports_color_preservation && (
            <button
              type="button"
              role="switch"
              aria-checked={colorPreservation}
              className={`${styles.switchRow} ${colorPreservation ? styles.switchRowActive : ""}`}
              onClick={() => setColorPreservation(prev => !prev)}
              disabled={busy}
            >
              <div className={styles.switchLabelGroup}>
                <strong>Préserver la palette d’origine</strong>
                <small>Maintient fidèlement les teintes et la colorimétrie source</small>
              </div>
              <span className={styles.switchBadge}>{colorPreservation ? "Oui" : "Libre"}</span>
            </button>
          )}

          {(activeSpec.supports_topaz_controls || activeSpec.supports_redefine_controls) && (
            <>
              <button
                type="button"
                className={styles.accordionToggle}
                onClick={() => setShowAdvanced(prev => !prev)}
                disabled={busy}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                  <SlidersHorizontal size={12} />
                  Réglages experts Topaz (netteté, bruit, visages)
                </span>
                {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>

              {showAdvanced && (
                <div className={styles.accordionBody}>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={useCustomFineControls}
                    className={`${styles.switchRow} ${useCustomFineControls ? styles.switchRowActive : ""}`}
                    onClick={() => setUseCustomFineControls(prev => !prev)}
                    disabled={busy}
                  >
                    <div className={styles.switchLabelGroup}>
                      <strong>Surcharger les réglages automatiques</strong>
                      <small>Par défaut, Topaz calibre chaque curseur selon l’image</small>
                    </div>
                    <span className={styles.switchBadge}>{useCustomFineControls ? "Personnalisé" : "Auto"}</span>
                  </button>

                  {useCustomFineControls && (
                    <>
                      {activeSpec.supports_topaz_controls && (
                        <div className={styles.sliderField}>
                          <div className={styles.sliderHeader}>
                            <label htmlFor="topaz-strength">Intensité globale</label>
                            <strong>{Math.round(strength * 100)}%</strong>
                          </div>
                          <input
                            id="topaz-strength"
                            type="range"
                            className={styles.sliderInput}
                            min={0.05}
                            max={1}
                            step={0.05}
                            value={strength}
                            onChange={e => setStrength(Number(e.target.value))}
                          />
                        </div>
                      )}

                      {activeSpec.supports_redefine_controls && (
                        <>
                          <button
                            type="button"
                            role="switch"
                            aria-checked={detailEnabled}
                            className={`${styles.switchRow} ${detailEnabled ? styles.switchRowActive : ""}`}
                            onClick={() => setDetailEnabled(prev => !prev)}
                          >
                            <div className={styles.switchLabelGroup}>
                              <strong>Accentuation de détail post-rendu</strong>
                            </div>
                            <span className={styles.switchBadge}>{detailEnabled ? "Oui" : "Non"}</span>
                          </button>
                          {detailEnabled && (
                            <div className={styles.sliderField}>
                              <div className={styles.sliderHeader}>
                                <label htmlFor="redefine-detail-strength">Force du détail (0–10)</label>
                                <strong>{detailStrength}</strong>
                              </div>
                              <input
                                id="redefine-detail-strength"
                                type="range"
                                className={styles.sliderInput}
                                min={0}
                                max={10}
                                step={0.5}
                                value={detailStrength}
                                onChange={e => setDetailStrength(Number(e.target.value))}
                              />
                            </div>
                          )}
                        </>
                      )}

                      <div className={styles.sliderField}>
                        <div className={styles.sliderHeader}>
                          <label htmlFor="topaz-sharpen">Netteté des contours</label>
                          <strong>{Math.round(sharpen * 100)}%</strong>
                        </div>
                        <input
                          id="topaz-sharpen"
                          type="range"
                          className={styles.sliderInput}
                          min={0}
                          max={1}
                          step={0.05}
                          value={sharpen}
                          onChange={e => setSharpen(Number(e.target.value))}
                        />
                      </div>

                      <div className={styles.sliderField}>
                        <div className={styles.sliderHeader}>
                          <label htmlFor="topaz-denoise">Réduction du bruit</label>
                          <strong>{Math.round(denoise * 100)}%</strong>
                        </div>
                        <input
                          id="topaz-denoise"
                          type="range"
                          className={styles.sliderInput}
                          min={0}
                          max={1}
                          step={0.05}
                          value={denoise}
                          onChange={e => setDenoise(Number(e.target.value))}
                        />
                      </div>

                      {activeSpec.supports_topaz_controls && (
                        <div className={styles.sliderField}>
                          <div className={styles.sliderHeader}>
                            <label htmlFor="topaz-compression">Correction artefacts JPEG</label>
                            <strong>{Math.round(fixCompression * 100)}%</strong>
                          </div>
                          <input
                            id="topaz-compression"
                            type="range"
                            className={styles.sliderInput}
                            min={0}
                            max={1}
                            step={0.05}
                            value={fixCompression}
                            onChange={e => setFixCompression(Number(e.target.value))}
                          />
                        </div>
                      )}

                      <button
                        type="button"
                        role="switch"
                        aria-checked={faceEnhancement}
                        className={`${styles.switchRow} ${faceEnhancement ? styles.switchRowActive : ""}`}
                        onClick={() => setFaceEnhancement(prev => !prev)}
                      >
                        <div className={styles.switchLabelGroup}>
                          <strong>Restauration des visages</strong>
                          <small>Récupère les traits faciaux avec fidélité</small>
                        </div>
                        <span className={styles.switchBadge}>{faceEnhancement ? "Activée" : "Off"}</span>
                      </button>

                      <div className={styles.inlineFieldRow}>
                        <label htmlFor="topaz-subject-select">Zone d’application</label>
                        <select
                          id="topaz-subject-select"
                          className={styles.selectInput}
                          value={subjectDetection}
                          onChange={e => setSubjectDetection(e.target.value as "all" | "foreground" | "background")}
                        >
                          <option value="all">Image entière</option>
                          <option value="foreground">Sujet (1er plan)</option>
                          <option value="background">Arrière-plan</option>
                        </select>
                      </div>
                    </>
                  )}
                </div>
              )}
            </>
          )}

          {activeSpec.supports_seed && (
            <div className={styles.inlineFieldRow}>
              <label htmlFor="upscale-seed-input">Graine aléatoire (Seed, optionnel)</label>
              <input
                id="upscale-seed-input"
                type="number"
                min={0}
                max={2147483647}
                placeholder="Aléatoire"
                className={styles.numberInput}
                value={seedInput}
                disabled={busy}
                onChange={e => setSeedInput(e.target.value)}
              />
            </div>
          )}
        </div>
      )}

      <button type="submit" className={styles.submitBtn} disabled={!canSubmit}>
        {busy ? (
          <>
            <LoaderCircle className="spin" size={17} />
            <span>Agrandissement avec {activeSpec.name}…</span>
          </>
        ) : (
          <>
            <Maximize2 size={17} />
            <span>
              Upscaler en{" "}
              {activeSpec.supported_tiers.length > 0 ? tier : effectiveFactor.toUpperCase()} ({activeSpec.name})
            </span>
          </>
        )}
      </button>
    </form>
  );
}
