"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Code2,
  Columns2,
  Copy,
  Eye,
  FileText,
  Image as ImageIcon,
  Maximize2,
  Minimize2,
  Palette,
  Sparkles,
  Volume2,
  VolumeX,
  ZoomIn,
} from "lucide-react";
import type { VisualDocDetail, VisualDocFigure, VisualDocPage } from "@/lib/api";
import styles from "./visual-doc-book-reader.module.css";

export type BookThemeId = "oldbook" | "report" | "parchment" | "nocturne" | "cyber";
export type BookDisplayMode = "original" | "hybrid" | "editorial" | "markdown";

export interface BookThemeOption {
  id: BookThemeId;
  label: string;
  subtitle: string;
  badge: string;
  swatchBg: string;
  swatchAccent: string;
}

export const BOOK_THEMES: BookThemeOption[] = [
  {
    id: "oldbook",
    label: "Grimoire & Règles",
    subtitle: "Vélin patiné, Cinzel & Garamond",
    badge: "Oldbook",
    swatchBg: "#f5ebd6",
    swatchAccent: "#8b261d",
  },
  {
    id: "report",
    label: "Rapport Éditorial",
    subtitle: "Papier financier ivoire & Playfair",
    badge: "Rapport",
    swatchBg: "#faf9f5",
    swatchAccent: "#1e3a8a",
  },
  {
    id: "parchment",
    label: "Manuscrit Royal",
    subtitle: "Parchemin ambré & enluminures",
    badge: "Parchemin",
    swatchBg: "#eddcb8",
    swatchAccent: "#92400e",
  },
  {
    id: "nocturne",
    label: "Cabinet Nocturne",
    subtitle: "Cuir sombre & lettres dorées",
    badge: "Nocturne",
    swatchBg: "#18161b",
    swatchAccent: "#d4af37",
  },
  {
    id: "cyber",
    label: "Manuel Holo-Tech",
    subtitle: "Ardoise futuriste & cyan",
    badge: "Tech",
    swatchBg: "#0d1526",
    swatchAccent: "#38bdf8",
  },
];

export interface VisualDocBookReaderProps {
  doc: VisualDocDetail;
  onZoomImage?: (asset: { src: string; caption: string }) => void;
  initialFullscreen?: boolean;
}

type FlipDirection = "next" | "prev" | null;

/**
 * Nettoie le markdown compilé d'une page pour un affichage éditorial fluide dans la liseuse :
 * - retire l'en-tête technique `## [p. X]` et la ligne `_Page originale de secours..._`
 */
function cleanEditorialPageMarkdown(raw: string | undefined): string {
  if (!raw) return "";
  return raw
    .replace(/^##\s*\[p\.\s*\d+\]\s*/im, "")
    .replace(/^_Page originale de secours\s*\[p\.\s*\d+\]\s*:.*_$/gim, "")
    .replace(/^>\s*Page originale complète\s*:.*$/gim, "")
    .trim();
}

/**
 * Synthétise un discret bruissement de page tournée via Web Audio API (zéro fichier audio externe).
 */
function playPageTurnRustle() {
  if (typeof window === "undefined") return;
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const duration = 0.14;
    const bufferSize = Math.floor(ctx.sampleRate * duration);
    const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < bufferSize; i++) {
      const env = Math.sin((i / bufferSize) * Math.PI);
      data[i] = (Math.random() * 2 - 1) * env * 0.045;
    }
    const noise = ctx.createBufferSource();
    noise.buffer = buffer;

    const filter = ctx.createBiquadFilter();
    filter.type = "bandpass";
    filter.frequency.setValueAtTime(1100, ctx.currentTime);
    filter.Q.setValueAtTime(1.4, ctx.currentTime);

    noise.connect(filter);
    filter.connect(ctx.destination);
    noise.start();
    noise.onended = () => {
      void ctx.close().catch(() => {});
    };
  } catch {
    // Ignorer si l'autoplay audio est restreint
  }
}

export function VisualDocBookReader({
  doc,
  onZoomImage,
  initialFullscreen = false,
}: VisualDocBookReaderProps) {
  const pages = useMemo<VisualDocPage[]>(() => {
    if (Array.isArray(doc.pages) && doc.pages.length > 0) {
      return [...doc.pages].sort((a, b) => a.page - b.page);
    }
    return [];
  }, [doc.pages]);

  const totalPages = pages.length;

  const [theme, setTheme] = useState<BookThemeId>(() => {
    const cat = doc.doc_category;
    if (cat === "financial" || cat === "scientific" || cat === "legal" || cat === "medical" || doc.ocr_model === "finance-report" || doc.source_type === "finance") {
      return "report";
    }
    if (cat === "technical") {
      return "cyber";
    }
    if (cat === "educational") {
      return "parchment";
    }
    return "oldbook";
  });
  const [displayMode, setDisplayMode] = useState<BookDisplayMode>(() => {
    const hasOriginalImages = pages.some((p) => Boolean(p.page_image_url));
    return hasOriginalImages ? "hybrid" : "editorial";
  });
  const [twoPageSpread, setTwoPageSpread] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      return window.innerWidth >= 960;
    }
    return true;
  });
  const [isFullscreen, setIsFullscreen] = useState<boolean>(initialFullscreen);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(true);
  const [copiedPageNum, setCopiedPageNum] = useState<number | null>(null);
  const [showRawMdCode, setShowRawMdCode] = useState<boolean>(false);
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [flipState, setFlipState] = useState<{
    direction: FlipDirection;
    fromIndex: number;
    toIndex: number;
  } | null>(null);

  const flipTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (flipTimeoutRef.current) clearTimeout(flipTimeoutRef.current);
    };
  }, []);

  const step = twoPageSpread && totalPages > 1 ? 2 : 1;

  // Normaliser l'index courant sur un début de double-page pair (0, 2, 4...) en mode 2 pages
  const normalizedIndex = useMemo(() => {
    if (totalPages === 0) return 0;
    const clamped = Math.max(0, Math.min(totalPages - 1, currentIndex));
    if (twoPageSpread && totalPages > 1) {
      return clamped % 2 === 0 ? clamped : clamped - 1;
    }
    return clamped;
  }, [currentIndex, totalPages, twoPageSpread]);

  const goToIndex = useCallback(
    (targetIdx: number, explicitDir?: "next" | "prev") => {
      if (totalPages === 0) return;
      const clamped = Math.max(0, Math.min(totalPages - 1, targetIdx));
      const dest =
        twoPageSpread && totalPages > 1
          ? clamped % 2 === 0
            ? clamped
            : clamped - 1
          : clamped;
      if (dest === normalizedIndex || flipState) return;

      const direction: "next" | "prev" = explicitDir || (dest > normalizedIndex ? "next" : "prev");
      if (soundEnabled) {
        playPageTurnRustle();
      }
      setFlipState({
        direction,
        fromIndex: normalizedIndex,
        toIndex: dest,
      });

      if (flipTimeoutRef.current) clearTimeout(flipTimeoutRef.current);
      flipTimeoutRef.current = setTimeout(() => {
        setCurrentIndex(dest);
        setFlipState(null);
      }, 640);
    },
    [totalPages, twoPageSpread, normalizedIndex, flipState, soundEnabled],
  );

  const canGoPrev = normalizedIndex > 0;
  const canGoNext = normalizedIndex + step < totalPages;

  const handlePrev = useCallback(() => {
    if (!canGoPrev) return;
    goToIndex(normalizedIndex - step, "prev");
  }, [canGoPrev, goToIndex, normalizedIndex, step]);

  const handleNext = useCallback(() => {
    if (!canGoNext) return;
    goToIndex(normalizedIndex + step, "next");
  }, [canGoNext, goToIndex, normalizedIndex, step]);

  // Navigation clavier (flèches gauche/droite, PageUp/PageDown, Échap en plein écran)
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        handlePrev();
      } else if (e.key === "ArrowRight" || e.key === "PageDown") {
        e.preventDefault();
        handleNext();
      } else if (e.key === "Escape" && isFullscreen) {
        e.preventDefault();
        e.stopPropagation();
        setIsFullscreen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handlePrev, handleNext, isFullscreen]);

  const leftPage = pages[normalizedIndex] || null;
  const rightPage = twoPageSpread && totalPages > 1 ? pages[normalizedIndex + 1] || null : null;

  // Pages utilisées pendant l'animation 3D de feuille qui se tourne
  const turningFrontPage = useMemo(() => {
    if (!flipState) return null;
    if (flipState.direction === "next") {
      return twoPageSpread ? pages[flipState.fromIndex + 1] || pages[flipState.fromIndex] : pages[flipState.fromIndex];
    }
    return pages[flipState.fromIndex];
  }, [flipState, pages, twoPageSpread]);

  const turningBackPage = useMemo(() => {
    if (!flipState) return null;
    if (flipState.direction === "next") {
      return pages[flipState.toIndex];
    }
    return twoPageSpread ? pages[flipState.toIndex + 1] || pages[flipState.toIndex] : pages[flipState.toIndex];
  }, [flipState, pages, twoPageSpread]);

  function renderPageSheetContent(page: VisualDocPage | null, side: "left" | "right" | "single") {
    if (!page) {
      return (
        <div className={styles.blankPageSheet}>
          <div className={styles.blankPageOrnament}>❦</div>
          <span>Fin de l&apos;ouvrage</span>
        </div>
      );
    }

    const cleanedMd = cleanEditorialPageMarkdown(page.compiled_markdown);
    const hasPageWebp = Boolean(page.page_image_url);
    const figures: VisualDocFigure[] = Array.isArray(page.figures) ? page.figures : [];
    const effectiveMode: BookDisplayMode = !hasPageWebp && displayMode === "original" ? "editorial" : displayMode;

    return (
      <div className={`${styles.pageSheetInner} ${styles[`side_${side}`]}`}>
        {/* En-tête courant de livre / rapport */}
        <header className={styles.runningHeader}>
          <span className={styles.runningTitle}>{doc.title}</span>
          <span className={styles.runningFolio}>
            {theme === "oldbook" || theme === "parchment" ? `Folio ${page.page}` : `Page ${page.page} / ${totalPages}`}
          </span>
        </header>

        <div className={styles.pageScrollBody}>
          {effectiveMode === "original" && hasPageWebp && (
            <div className={styles.originalPageWrap}>
              <button
                type="button"
                className={styles.originalImgBtn}
                onClick={() =>
                  onZoomImage?.({
                    src: page.page_image_url,
                    caption: `${doc.title} — Page ${page.page}`,
                  })
                }
                title="Cliquer pour inspecter la page en haute définition"
              >
                <img
                  src={page.page_image_url}
                  alt={`${doc.title} — Page ${page.page}`}
                  className={styles.originalPageImg}
                />
                <span className={styles.zoomHintPill}>
                  <ZoomIn size={13} />
                  <span>Loupe HD</span>
                </span>
              </button>
            </div>
          )}

          {effectiveMode === "hybrid" && (
            <div className={styles.hybridLayout}>
              {hasPageWebp && (
                <div className={styles.hybridVisualCol}>
                  <button
                    type="button"
                    className={styles.originalImgBtn}
                    onClick={() =>
                      onZoomImage?.({
                        src: page.page_image_url,
                        caption: `${doc.title} — Page ${page.page}`,
                      })
                    }
                    title="Agrandir la planche originale"
                  >
                    <img
                      src={page.page_image_url}
                      alt={`Page ${page.page}`}
                      className={styles.hybridOriginalImg}
                    />
                    <span className={styles.zoomHintPill}>
                      <ZoomIn size={12} />
                      <span>Planche p. {page.page}</span>
                    </span>
                  </button>
                </div>
              )}
              <div className={styles.hybridTextCol}>
                {cleanedMd ? (
                  <div className={styles.editorialProse}>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        img: ({ src, alt }) => {
                          const imgSrc = typeof src === "string" ? src : "";
                          const imgAlt = alt || `Illustration p. ${page.page}`;
                          if (!imgSrc) return null;
                          return (
                            <figure className={styles.inlineFigure}>
                              <button
                                type="button"
                                className={styles.inlineFigureBtn}
                                onClick={() => onZoomImage?.({ src: imgSrc, caption: imgAlt })}
                              >
                                <img src={imgSrc} alt={imgAlt} className={styles.inlineFigureImg} loading="lazy" />
                              </button>
                              <figcaption className={styles.inlineFigureCaption}>{imgAlt}</figcaption>
                            </figure>
                          );
                        },
                      }}
                    >
                      {cleanedMd}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p className={styles.emptyProseNote}>Planche visuelle sans texte additionnel.</p>
                )}
              </div>
            </div>
          )}

          {effectiveMode === "editorial" && (
            <div className={styles.editorialOnlyWrap}>
              {cleanedMd ? (
                <div className={styles.editorialProse}>
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      img: ({ src, alt }) => {
                        const imgSrc = typeof src === "string" ? src : "";
                        const imgAlt = alt || `Illustration p. ${page.page}`;
                        if (!imgSrc) return null;
                        return (
                          <figure className={styles.inlineFigure}>
                            <button
                              type="button"
                              className={styles.inlineFigureBtn}
                              onClick={() => onZoomImage?.({ src: imgSrc, caption: imgAlt })}
                            >
                              <img src={imgSrc} alt={imgAlt} className={styles.inlineFigureImg} loading="lazy" />
                            </button>
                            <figcaption className={styles.inlineFigureCaption}>{imgAlt}</figcaption>
                          </figure>
                        );
                      },
                    }}
                  >
                    {cleanedMd}
                  </ReactMarkdown>
                </div>
              ) : hasPageWebp ? (
                <div className={styles.originalPageWrap}>
                  <img
                    src={page.page_image_url}
                    alt={`Page ${page.page}`}
                    className={styles.originalPageImg}
                  />
                </div>
              ) : (
                <p className={styles.emptyProseNote}>Aucun contenu sur cette page.</p>
              )}

              {figures.length > 0 && !cleanedMd.includes("/api/docs/") && (
                <div className={styles.orphanFiguresStrip}>
                  {figures.map((fig) => (
                    <figure key={fig.id} className={styles.inlineFigure}>
                      <button
                        type="button"
                        className={styles.inlineFigureBtn}
                        onClick={() => onZoomImage?.({ src: fig.url, caption: fig.alt })}
                      >
                        <img src={fig.url} alt={fig.short_title} className={styles.inlineFigureImg} loading="lazy" />
                      </button>
                      <figcaption className={styles.inlineFigureCaption}>{fig.short_title || fig.alt}</figcaption>
                    </figure>
                  ))}
                </div>
              )}
            </div>
          )}

          {effectiveMode === "markdown" && (
            <div className={styles.markdownExtractWrap}>
              {/* Barre d'en-tête de l'extraction de la page */}
              <div className={styles.markdownExtractToolbar}>
                <span className={styles.markdownExtractStats}>
                  <FileText size={13} />
                  <span>
                    Page {page.page} · {(page.compiled_markdown || "").length.toLocaleString("fr-FR")} car. ·{" "}
                    {figures.length} description{figures.length > 1 ? "s" : ""} d&apos;image{figures.length > 1 ? "s" : ""}
                  </span>
                </span>
                <div className={styles.markdownExtractActions}>
                  <button
                    type="button"
                    className={`${styles.copyExtractBtn} ${showRawMdCode ? styles.copyExtractBtnActive : ""}`}
                    onClick={() => setShowRawMdCode((v) => !v)}
                    title="Basculer entre le rendu stylisé (sans # ni **) et le code source Markdown brut"
                  >
                    <Code2 size={12} />
                    <span>{showRawMdCode ? "Vue stylisée" : "Code brut"}</span>
                  </button>
                  <button
                    type="button"
                    className={styles.copyExtractBtn}
                    onClick={() => {
                      const rawToCopy = page.compiled_markdown || "";
                      navigator.clipboard?.writeText(rawToCopy).then(() => {
                        setCopiedPageNum(page.page);
                        setTimeout(() => setCopiedPageNum((curr) => (curr === page.page ? null : curr)), 1800);
                      });
                    }}
                  >
                    {copiedPageNum === page.page ? <Check size={12} /> : <Copy size={12} />}
                    <span>{copiedPageNum === page.page ? "Copié" : "Copier"}</span>
                  </button>
                </div>
              </div>

              {showRawMdCode ? (
                <div className={styles.extractedRawSection}>
                  <div className={styles.extractedSectionTitle}>
                    <span>Code source Markdown brut de la page {page.page}</span>
                  </div>
                  <pre className={styles.extractedMarkdownPre}>
                    {page.compiled_markdown || "Aucun texte Markdown extrait sur cette page."}
                  </pre>
                </div>
              ) : (
                <>
                  {/* 1. Texte extrait et descriptions d'images mis en page et stylisés au fil de la lecture (zéro # ni **) */}
                  <div className={styles.extractedRawSection}>
                    <div className={styles.extractedSectionTitle}>
                      <span>Texte extrait &amp; descriptions anatomiques des illustrations (Page {page.page})</span>
                    </div>
                    {cleanedMd ? (
                      <div className={`${styles.editorialProse} ${styles.styledExtractProse}`}>
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            img: ({ src, alt }) => {
                              const imgSrc = typeof src === "string" ? src : "";
                              const imgAlt = alt || `Illustration p. ${page.page}`;
                              if (!imgSrc) return null;
                              const matchingFig = figures.find((f) => f.url === imgSrc);
                              const shortTitle =
                                matchingFig?.short_title ||
                                imgAlt.split(" : ")[0]?.split(" — ")[0]?.slice(0, 120) ||
                                `Illustration p. ${page.page}`;
                              return (
                                <aside className={styles.styledExtractFigureBox}>
                                  <button
                                    type="button"
                                    className={styles.extractedFigureThumbBtn}
                                    onClick={() => onZoomImage?.({ src: imgSrc, caption: imgAlt })}
                                    title="Cliquer pour agrandir ce schéma"
                                  >
                                    <img
                                      src={imgSrc}
                                      alt={shortTitle}
                                      className={styles.extractedFigureThumb}
                                      loading="lazy"
                                    />
                                  </button>
                                  <div className={styles.extractedFigureBody}>
                                    <div className={styles.extractedFigureHeader}>
                                      <span className={styles.extractedFigureTitle}>{shortTitle}</span>
                                      {matchingFig?.image_type && (
                                        <span className={styles.extractedFigureBadge}>{matchingFig.image_type}</span>
                                      )}
                                      {matchingFig?.filename && (
                                        <span className={styles.extractedFigureFile}>{matchingFig.filename}</span>
                                      )}
                                    </div>
                                    <div className={styles.extractedFigureAltRich}>
                                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{imgAlt}</ReactMarkdown>
                                    </div>
                                    {matchingFig?.visible_text && (
                                      <div className={styles.extractedVisibleText}>
                                        <strong>Texte lu dans l&apos;image :</strong> {matchingFig.visible_text}
                                      </div>
                                    )}
                                  </div>
                                </aside>
                              );
                            },
                          }}
                        >
                          {cleanedMd}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className={styles.emptyProseNote}>Aucun texte extrait sur cette page.</p>
                    )}
                  </div>

                  {/* 2. Figures supplémentaires non citées dans le corps du texte */}
                  {figures.length > 0 && !cleanedMd.includes("/api/docs/") && (
                    <div className={styles.extractedFiguresSection}>
                      <div className={styles.extractedSectionTitle}>
                        <span>Descriptions des schémas de la page ({figures.length})</span>
                      </div>
                      <div className={styles.extractedFiguresList}>
                        {figures.map((fig, fIdx) => (
                          <article key={fig.id || fIdx} className={styles.styledExtractFigureBox}>
                            <button
                              type="button"
                              className={styles.extractedFigureThumbBtn}
                              onClick={() =>
                                onZoomImage?.({
                                  src: fig.url,
                                  caption: fig.alt || fig.short_title,
                                })
                              }
                            >
                              <img
                                src={fig.url}
                                alt={fig.short_title || `Figure ${fIdx + 1}`}
                                className={styles.extractedFigureThumb}
                                loading="lazy"
                              />
                            </button>
                            <div className={styles.extractedFigureBody}>
                              <div className={styles.extractedFigureHeader}>
                                <span className={styles.extractedFigureTitle}>
                                  {fig.short_title || `Schéma ${fIdx + 1}`}
                                </span>
                                {fig.image_type && (
                                  <span className={styles.extractedFigureBadge}>{fig.image_type}</span>
                                )}
                              </div>
                              <div className={styles.extractedFigureAltRich}>
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{fig.alt}</ReactMarkdown>
                              </div>
                              {fig.visible_text && (
                                <div className={styles.extractedVisibleText}>
                                  <strong>Texte lu dans l&apos;image :</strong> {fig.visible_text}
                                </div>
                              )}
                            </div>
                          </article>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Pied de page typographique avec numéro et ornement */}
        <footer className={styles.runningFooter}>
          <span className={styles.footerOrnament}>
            {theme === "oldbook" || theme === "parchment" ? "✦" : "—"}
          </span>
          <span className={styles.footerPageNumber}>{page.page}</span>
          <span className={styles.footerOrnament}>
            {theme === "oldbook" || theme === "parchment" ? "✦" : "—"}
          </span>
        </footer>
      </div>
    );
  }

  return (
    <div
      className={`${styles.readerRoot} ${styles[`theme_${theme}`]} ${
        isFullscreen ? styles.readerFullscreen : ""
      }`}
    >
      {/* Barre d'outils supérieure : Thèmes, Modes d'affichage, Double page, Plein écran */}
      <div className={styles.readerToolbar}>
        <div className={styles.toolbarGroup}>
          <span className={styles.toolbarLabel}>
            <Palette size={13} />
            <span>Thème :</span>
          </span>
          <div className={styles.themePills} role="radiogroup" aria-label="Thème visuel du livre">
            {BOOK_THEMES.map((t) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={theme === t.id}
                className={`${styles.themePill} ${theme === t.id ? styles.themePillActive : ""}`}
                onClick={() => setTheme(t.id)}
                title={`${t.label} — ${t.subtitle}`}
              >
                <span
                  className={styles.themeSwatch}
                  style={{
                    background: t.swatchBg,
                    borderColor: t.swatchAccent,
                  }}
                />
                <span>{t.badge}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.toolbarGroup}>
          <div className={styles.modeSegment} role="group" aria-label="Mode de lecture">
            <button
              type="button"
              className={`${styles.segmentBtn} ${displayMode === "original" ? styles.segmentBtnActive : ""}`}
              onClick={() => setDisplayMode("original")}
              title="Fac-similé : planches originales haute définition"
            >
              <ImageIcon size={13} />
              <span>Fac-similé</span>
            </button>
            <button
              type="button"
              className={`${styles.segmentBtn} ${displayMode === "hybrid" ? styles.segmentBtnActive : ""}`}
              onClick={() => setDisplayMode("hybrid")}
              title="Illustré : planche originale + texte composé et figures"
            >
              <Sparkles size={13} />
              <span>Illustré</span>
            </button>
            <button
              type="button"
              className={`${styles.segmentBtn} ${displayMode === "editorial" ? styles.segmentBtnActive : ""}`}
              onClick={() => setDisplayMode("editorial")}
              title="Typographie pure : mise en page livre avec lettrines et schémas intégrés"
            >
              <FileText size={13} />
              <span>Éditorial</span>
            </button>
            <button
              type="button"
              className={`${styles.segmentBtn} ${displayMode === "markdown" ? styles.segmentBtnActive : ""}`}
              onClick={() => setDisplayMode("markdown")}
              title="Markdown & Descriptions IA : texte OCR brut et descriptions anatomiques complètes des images page par page"
            >
              <Code2 size={13} />
              <span>Markdown &amp; Descriptions</span>
            </button>
          </div>

          {totalPages > 1 && (
            <button
              type="button"
              className={`${styles.iconToggleBtn} ${twoPageSpread ? styles.iconToggleBtnActive : ""}`}
              onClick={() => setTwoPageSpread((prev) => !prev)}
              title={twoPageSpread ? "Passer en vue 1 page" : "Passer en livre ouvert (2 pages côte à côte)"}
            >
              <Columns2 size={14} />
              <span>{twoPageSpread ? "2 pages" : "1 page"}</span>
            </button>
          )}

          <button
            type="button"
            className={`${styles.iconToggleBtn} ${soundEnabled ? styles.iconToggleBtnActive : ""}`}
            onClick={() => setSoundEnabled((s) => !s)}
            title={soundEnabled ? "Son de page tournée activé" : "Activer le bruissement de page"}
            aria-label="Bruissement de page"
          >
            {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </button>

          <button
            type="button"
            className={`${styles.fullscreenBtn} ${isFullscreen ? styles.fullscreenBtnActive : ""}`}
            onClick={() => setIsFullscreen((f) => !f)}
            title={isFullscreen ? "Quitter le plein écran (Échap)" : "Ouvrir la liseuse en plein écran immersif"}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            <span>{isFullscreen ? "Réduire" : "Plein écran"}</span>
          </button>
        </div>
      </div>

      {/* Scène 3D du livre ouvert */}
      <div className={styles.bookStage}>
        <button
          type="button"
          className={`${styles.navSideArrow} ${styles.navSideArrowLeft}`}
          disabled={!canGoPrev || Boolean(flipState)}
          onClick={handlePrev}
          aria-label="Tourner vers la page précédente"
          title="Page précédente (←)"
        >
          <ChevronLeft size={24} />
        </button>

        <div
          className={`${styles.bookViewport} ${
            twoPageSpread && totalPages > 1 ? styles.bookViewportSpread : styles.bookViewportSingle
          }`}
        >
          {/* Reliure et tranche de livre en 3D */}
          <div className={styles.bookHardcover}>
            <div className={styles.paperStackLeft} />
            <div className={styles.paperStackRight} />

            {twoPageSpread && totalPages > 1 ? (
              <div className={styles.spreadContainer}>
                {/* Page de gauche */}
                <div
                  className={`${styles.pageHalf} ${styles.pageHalfLeft}`}
                  onClick={() => {
                    if (canGoPrev && !flipState) handlePrev();
                  }}
                >
                  {renderPageSheetContent(leftPage, "left")}
                  <div className={styles.gutterShadowLeft} />
                  {canGoPrev && (
                    <div className={styles.cornerCurlLeft} title="Cliquer pour tourner la page">
                      <span />
                    </div>
                  )}
                </div>

                {/* Reliure centrale */}
                <div className={styles.centerSpine} />

                {/* Page de droite */}
                <div
                  className={`${styles.pageHalf} ${styles.pageHalfRight}`}
                  onClick={(e) => {
                    // Ne pas tourner la page si l'utilisateur clique sur une image ou un bouton de zoom
                    if ((e.target as HTMLElement).closest("button")) return;
                    if (canGoNext && !flipState) handleNext();
                  }}
                >
                  {renderPageSheetContent(rightPage, "right")}
                  <div className={styles.gutterShadowRight} />
                  {canGoNext && (
                    <div className={styles.cornerCurlRight} title="Cliquer pour tourner la page">
                      <span />
                    </div>
                  )}
                </div>

                {/* Feuille 3D animée pendant le retournement */}
                {flipState && (
                  <div
                    className={`${styles.turningLeaf} ${
                      flipState.direction === "next" ? styles.turningLeafNext : styles.turningLeafPrev
                    }`}
                  >
                    <div className={styles.leafFaceFront}>
                      {renderPageSheetContent(
                        turningFrontPage,
                        flipState.direction === "next" ? "right" : "left",
                      )}
                      <div className={styles.leafDynamicShade} />
                    </div>
                    <div className={styles.leafFaceBack}>
                      {renderPageSheetContent(
                        turningBackPage,
                        flipState.direction === "next" ? "left" : "right",
                      )}
                      <div className={styles.leafDynamicShade} />
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className={styles.singlePageContainer}>
                <div
                  className={`${styles.singlePageSheet} ${
                    flipState
                      ? flipState.direction === "next"
                        ? styles.singleFlipNext
                        : styles.singleFlipPrev
                      : ""
                  }`}
                >
                  {renderPageSheetContent(leftPage, "single")}
                </div>
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          className={`${styles.navSideArrow} ${styles.navSideArrowRight}`}
          disabled={!canGoNext || Boolean(flipState)}
          onClick={handleNext}
          aria-label="Tourner vers la page suivante"
          title="Page suivante (→)"
        >
          <ChevronRight size={24} />
        </button>
      </div>

      {/* Barre inférieure : ruban marque-page et vignettes rapides des pages */}
      <div className={styles.readerFooterBar}>
        <div className={styles.pageStatusInfo}>
          <BookOpen size={14} />
          <span>
            {twoPageSpread && rightPage
              ? `Pages ${leftPage?.page ?? 1}–${rightPage.page} sur ${totalPages}`
              : `Page ${leftPage?.page ?? 1} sur ${totalPages}`}
          </span>
        </div>

        <div className={styles.pageRibbon} role="navigation" aria-label="Accès rapide aux pages">
          {pages.map((p, idx) => {
            const isCurrent =
              idx === normalizedIndex || (twoPageSpread && totalPages > 1 && idx === normalizedIndex + 1);
            return (
              <button
                key={p.page}
                type="button"
                className={`${styles.pageDotBtn} ${isCurrent ? styles.pageDotBtnActive : ""}`}
                onClick={() => goToIndex(idx)}
                title={`Aller à la page ${p.page}`}
              >
                <span>{p.page}</span>
              </button>
            );
          })}
        </div>

        <div className={styles.keyboardHint}>
          <Eye size={13} />
          <span>Utilisez ← / → ou cliquez sur le coin de page pour feuilleter</span>
        </div>
      </div>
    </div>
  );
}
