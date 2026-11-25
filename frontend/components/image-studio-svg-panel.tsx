"use client";

import { useState, type FormEvent } from "react";
import {
  CircleAlert,
  Eye,
  FileCode2,
  Image as ImageIcon,
  LoaderCircle,
  RotateCcw,
  Sparkles,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import { api, errorMessage, type CreateSvgPayload, type GeneratedImage } from "@/lib/api";
import type { StudioSourceImage } from "./image-studio-upscale-panel";
import styles from "./image-studio-ext.module.css";

const SVG_ASPECT_RATIOS = [
  { value: "auto", label: "Auto", hint: "Adaptatif" },
  { value: "1:1", label: "1:1", hint: "Carré" },
  { value: "16:9", label: "16:9", hint: "Paysage" },
  { value: "9:16", label: "9:16", hint: "Portrait" },
  { value: "4:3", label: "4:3", hint: "Classique" },
  { value: "3:4", label: "3:4", hint: "Affiche" },
  { value: "3:2", label: "3:2", hint: "Large" },
  { value: "2:3", label: "2:3", hint: "Vertical" },
];

function formatBytesCompact(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

type ImageStudioSvgPanelProps = {
  operation: "generate" | "vectorize";
  onOperationChange: (op: "generate" | "vectorize") => void;
  sourceImage: StudioSourceImage | null;
  previewingSource: boolean;
  busy: "improve" | "generate" | "delete" | null;
  canUseIdeogram: boolean;
  canImproveChat: boolean;
  improveModel: string;
  onPickFile: () => void;
  onTogglePreviewSource: () => void;
  onClearSource: () => void;
  onSvgCreated: (created: GeneratedImage) => void;
  onError: (message: string) => void;
  onBusyChange: (nextBusy: "improve" | "generate" | null, statusLabel?: string) => void;
};

export function ImageStudioSvgPanel({
  operation,
  onOperationChange,
  sourceImage,
  previewingSource,
  busy,
  canUseIdeogram,
  canImproveChat,
  improveModel,
  onPickFile,
  onTogglePreviewSource,
  onClearSource,
  onSvgCreated,
  onError,
  onBusyChange,
}: ImageStudioSvgPanelProps) {
  const [prompt, setPrompt] = useState("");
  const [previousPrompt, setPreviousPrompt] = useState<string | null>(null);
  const [aspectRatio, setAspectRatio] = useState("auto");
  const [quality, setQuality] = useState<"low" | "medium" | "high">("medium");
  const [vectorizeMode, setVectorizeMode] = useState<"auto" | "simple" | "detailed">("auto");
  const [shapeDensity, setShapeDensity] = useState(14);
  const [colorVariety, setColorVariety] = useState(7);
  const [useGradient, setUseGradient] = useState(true);
  const [seedInput, setSeedInput] = useState("");

  const isBusy = busy !== null;
  const isUnsupportedRaster =
    !!sourceImage?.mimeType && !["image/png", "image/jpeg", "image/webp"].includes(sourceImage.mimeType);

  const canImprove =
    operation === "generate" &&
    canImproveChat &&
    !!prompt.trim() &&
    prompt.length <= 4000 &&
    !isBusy;

  const canSubmit =
    canUseIdeogram &&
    !isBusy &&
    !isUnsupportedRaster &&
    (operation === "generate" ? !!prompt.trim() && prompt.length <= 4000 : !!sourceImage);

  async function handleImprovePrompt() {
    if (!canImprove) return;
    const original = prompt.trim();
    onError("");
    onBusyChange("improve");
    try {
      const res = await api<{ prompt: string }>("/images/improve", {
        method: "POST",
        body: JSON.stringify({
          prompt: original,
          model: improveModel,
          reference_image_data: sourceImage?.dataUrl,
          source_image_id: sourceImage?.sourceImageId,
          is_svg: true,
        }),
      });
      setPreviousPrompt(original);
      setPrompt(res.prompt);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      onBusyChange(null);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    onError("");

    const parsedSeed = seedInput.trim() ? Number.parseInt(seedInput.trim(), 10) : undefined;
    if (parsedSeed !== undefined && (Number.isNaN(parsedSeed) || parsedSeed < 0 || parsedSeed > 2147483647)) {
      onError("La graine (seed) doit être un entier compris entre 0 et 2 147 483 647.");
      return;
    }

    const payload: CreateSvgPayload =
      operation === "generate"
        ? {
            operation: "generate",
            prompt: prompt.trim(),
            reference_image_data: sourceImage?.dataUrl,
            source_image_id: sourceImage?.sourceImageId,
            aspect_ratio: aspectRatio,
            quality,
            use_gradient: useGradient,
            seed: parsedSeed,
          }
        : {
            operation: "vectorize",
            reference_image_data: sourceImage?.dataUrl,
            source_image_id: sourceImage?.sourceImageId,
            mode: vectorizeMode,
            shape_density: shapeDensity,
            color_variety: colorVariety,
            use_gradient: useGradient,
          };

    onBusyChange(
      "generate",
      operation === "generate"
        ? "Génération du vecteur SVG (Ideogram Vector 1.0)"
        : "Vectorisation Image → SVG (Ideogram Vector 1.0)",
    );
    try {
      const created = await api<GeneratedImage>("/images/svg", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onSvgCreated(created);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      onBusyChange(null);
    }
  }

  return (
    <form className={styles.panelForm} onSubmit={event => void handleSubmit(event)}>
      {/* Sous-commutateur Generate SVG vs Image-to-SVG */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.sectionTitle}>Outil vectoriel Ideogram Vector 1.0</span>
          <span className={styles.pillAccent}>SVG éditable</span>
        </div>

        <div className={styles.segmentedRow} role="tablist" aria-label="Opération SVG">
          <button
            type="button"
            role="tab"
            aria-selected={operation === "generate"}
            className={`${styles.segmentBtn} ${operation === "generate" ? styles.segmentBtnSelected : ""}`}
            onClick={() => onOperationChange("generate")}
            disabled={isBusy}
          >
            <strong>Générer un SVG</strong>
            <small>Depuis un prompt</small>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={operation === "vectorize"}
            className={`${styles.segmentBtn} ${operation === "vectorize" ? styles.segmentBtnSelected : ""}`}
            onClick={() => onOperationChange("vectorize")}
            disabled={isBusy}
          >
            <strong>Image → SVG</strong>
            <small>Vectoriser une image</small>
          </button>
        </div>
      </div>

      {/* Image source (requise pour Image -> SVG, optionnelle comme référence pour Générer un SVG) */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <span className={styles.sectionTitle}>
            {operation === "vectorize"
              ? "Image matricielle à vectoriser"
              : "Image de référence (optionnel)"}
          </span>
          <span className={styles.pillNeutral}>PNG · JPEG · WEBP</span>
        </div>

        {sourceImage ? (
          <div className={styles.sourceRow}>
            <button
              type="button"
              className={styles.sourceThumb}
              onClick={onTogglePreviewSource}
              title="Afficher / masquer l'image source"
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
                  : "Image prête"}
                {sourceImage.sizeBytes ? ` · ${formatBytesCompact(sourceImage.sizeBytes)}` : ""}
              </span>
              <div className={styles.sourceActions}>
                <button
                  type="button"
                  className={`${styles.miniBtn} ${previewingSource ? styles.miniBtnActive : ""}`}
                  onClick={onTogglePreviewSource}
                  disabled={isBusy}
                >
                  <Eye size={11} />
                  <span>{previewingSource ? "Affichée" : "Voir"}</span>
                </button>
                <button type="button" className={styles.miniBtn} onClick={onPickFile} disabled={isBusy}>
                  <Upload size={11} />
                  <span>Remplacer</span>
                </button>
                <button
                  type="button"
                  className={`${styles.miniBtn} ${styles.miniBtnDanger}`}
                  onClick={onClearSource}
                  disabled={isBusy}
                >
                  <X size={11} />
                  <span>Retirer</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <button type="button" className={styles.dropzone} onClick={onPickFile} disabled={isBusy}>
            <Upload size={16} className={styles.dropzoneIcon} />
            <div className={styles.dropzoneText}>
              <strong>
                {operation === "vectorize"
                  ? "Importer une image à convertir en SVG"
                  : "Ajouter une image pour guider le SVG (optionnel)"}
              </strong>
              <small>
                {operation === "vectorize"
                  ? "Logos, icônes, stickers ou illustrations en PNG, JPEG ou WEBP"
                  : "Optionnel : inspire le style ou la composition du vecteur généré"}
              </small>
            </div>
          </button>
        )}

        {isUnsupportedRaster && (
          <div className={styles.warningBox} role="alert">
            <CircleAlert size={14} />
            <span>Ideogram Vector 1.0 accepte uniquement les images PNG, JPEG ou WEBP.</span>
          </div>
        )}
      </div>

      {operation === "generate" ? (
        <>
          {/* Prompt vectoriel */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <label htmlFor="svg-generate-prompt" className={styles.sectionTitle}>
                Description du vecteur SVG
              </label>
              <span className={styles.pillNeutral}>{prompt.length}/4000</span>
            </div>

            <textarea
              id="svg-generate-prompt"
              className={styles.textarea}
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="Ex : Logo minimaliste d’un renard géométrique en origami, formes franches, contours nets, fond isolé…"
              maxLength={4000}
              rows={4}
              disabled={isBusy}
              onKeyDown={e => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canSubmit) {
                  e.preventDefault();
                  void handleSubmit(e as unknown as FormEvent);
                }
              }}
            />

            <div className={styles.promptToolsRow}>
              <button
                type="button"
                className={styles.improveBtn}
                onClick={() => void handleImprovePrompt()}
                disabled={!canImprove}
              >
                {busy === "improve" ? <LoaderCircle className="spin" size={14} /> : <WandSparkles size={14} />}
                <span>
                  {busy === "improve" ? "Optimisation…" : "Améliorer le prompt vectoriel"}
                </span>
              </button>
              {previousPrompt !== null && (
                <button
                  type="button"
                  className={styles.miniBtn}
                  disabled={isBusy}
                  onClick={() => {
                    setPrompt(previousPrompt);
                    setPreviousPrompt(null);
                  }}
                >
                  <RotateCcw size={12} />
                  <span>Rétablir</span>
                </button>
              )}
            </div>
          </div>

          {/* Format, Qualité & Dégradés */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <span className={styles.sectionTitle}>Format & Qualité vectorielle</span>
              <span className={styles.pillNeutral}>Ideogram Vector 1.0</span>
            </div>

            <div className={styles.segmentedRow} role="radiogroup" aria-label="Format SVG">
              {SVG_ASPECT_RATIOS.map(r => (
                <button
                  key={r.value}
                  type="button"
                  role="radio"
                  aria-checked={aspectRatio === r.value}
                  className={`${styles.segmentBtn} ${aspectRatio === r.value ? styles.segmentBtnSelected : ""}`}
                  onClick={() => setAspectRatio(r.value)}
                  disabled={isBusy}
                >
                  <strong>{r.label}</strong>
                  <small>{r.hint}</small>
                </button>
              ))}
            </div>

            <div className={styles.segmentedRow} role="radiogroup" aria-label="Qualité de rendu SVG">
              {(
                [
                  { id: "low", label: "Rapide", hint: "Low" },
                  { id: "medium", label: "Équilibrée", hint: "Medium" },
                  { id: "high", label: "Haute précision", hint: "High" },
                ] as const
              ).map(q => (
                <button
                  key={q.id}
                  type="button"
                  role="radio"
                  aria-checked={quality === q.id}
                  className={`${styles.segmentBtn} ${quality === q.id ? styles.segmentBtnSelected : ""}`}
                  onClick={() => setQuality(q.id)}
                  disabled={isBusy}
                >
                  <strong>{q.label}</strong>
                  <small>{q.hint}</small>
                </button>
              ))}
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={useGradient}
              className={`${styles.switchRow} ${useGradient ? styles.switchRowActive : ""}`}
              onClick={() => setUseGradient(prev => !prev)}
              disabled={isBusy}
            >
              <div className={styles.switchLabelGroup}>
                <strong>Autoriser les dégradés SVG</strong>
                <small>
                  {useGradient
                    ? "Remplissages avec dégradés fluides autorisés"
                    : "Aplats de couleurs unies stricts (idéal découpe / sérigraphie)"}
                </small>
              </div>
              <span className={styles.switchBadge}>{useGradient ? "Dégradés" : "Aplats"}</span>
            </button>

            <div className={styles.inlineFieldRow}>
              <label htmlFor="svg-seed-input">Graine aléatoire (Seed, optionnel)</label>
              <input
                id="svg-seed-input"
                type="number"
                min={0}
                max={2147483647}
                placeholder="Aléatoire"
                className={styles.numberInput}
                value={seedInput}
                disabled={isBusy}
                onChange={e => setSeedInput(e.target.value)}
              />
            </div>
          </div>
        </>
      ) : (
        /* Réglages Image-to-SVG (Vectorizer) */
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <span className={styles.sectionTitle}>Paramètres de vectorisation</span>
            <span className={styles.pillNeutral}>Vectorizer v2</span>
          </div>

          <div className={styles.segmentedRow} role="radiogroup" aria-label="Mode de tracé SVG">
            {(
              [
                { id: "auto", label: "Auto", hint: "Optimal" },
                { id: "simple", label: "Simple", hint: "Logos épurés" },
                { id: "detailed", label: "Détaillé", hint: "Traits fins" },
              ] as const
            ).map(m => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={vectorizeMode === m.id}
                className={`${styles.segmentBtn} ${vectorizeMode === m.id ? styles.segmentBtnSelected : ""}`}
                onClick={() => setVectorizeMode(m.id)}
                disabled={isBusy}
              >
                <strong>{m.label}</strong>
                <small>{m.hint}</small>
              </button>
            ))}
          </div>

          <div className={styles.sliderField}>
            <div className={styles.sliderHeader}>
              <label htmlFor="svg-shape-density">Densité des formes (1 = minimal, 16 = très fin)</label>
              <strong>{shapeDensity}/16</strong>
            </div>
            <input
              id="svg-shape-density"
              type="range"
              className={styles.sliderInput}
              min={1}
              max={16}
              step={1}
              value={shapeDensity}
              disabled={isBusy}
              onChange={e => setShapeDensity(Number(e.target.value))}
            />
          </div>

          <div className={styles.sliderField}>
            <div className={styles.sliderHeader}>
              <label htmlFor="svg-color-variety">Variété de couleurs (1 = restreinte, 8 = riche)</label>
              <strong>{colorVariety}/8</strong>
            </div>
            <input
              id="svg-color-variety"
              type="range"
              className={styles.sliderInput}
              min={1}
              max={8}
              step={1}
              value={colorVariety}
              disabled={isBusy}
              onChange={e => setColorVariety(Number(e.target.value))}
            />
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={useGradient}
            className={`${styles.switchRow} ${useGradient ? styles.switchRowActive : ""}`}
            onClick={() => setUseGradient(prev => !prev)}
            disabled={isBusy}
          >
            <div className={styles.switchLabelGroup}>
              <strong>Autoriser les dégradés SVG</strong>
              <small>Désactivez pour forcer des aplats de couleurs unies</small>
            </div>
            <span className={styles.switchBadge}>{useGradient ? "Dégradés" : "Aplats"}</span>
          </button>
        </div>
      )}

      <button type="submit" className={styles.submitBtn} disabled={!canSubmit}>
        {busy === "generate" ? (
          <>
            <LoaderCircle className="spin" size={17} />
            <span>
              {operation === "generate"
                ? "Création du vecteur SVG…"
                : "Vectorisation en SVG…"}
            </span>
          </>
        ) : operation === "generate" ? (
          <>
            <Sparkles size={17} />
            <span>Générer le vecteur SVG</span>
          </>
        ) : (
          <>
            {sourceImage ? <FileCode2 size={17} /> : <ImageIcon size={17} />}
            <span>Convertir l’image en SVG</span>
          </>
        )}
      </button>
    </form>
  );
}
