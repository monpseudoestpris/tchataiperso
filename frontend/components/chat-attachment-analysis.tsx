"use client";

import {
  BookOpen,
  Brain,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Globe2,
  GraduationCap,
  Languages,
  LineChart,
  ListOrdered,
  LoaderCircle,
  Maximize2,
  RefreshCw,
  Sparkles,
  SquarePlay,
  TrendingUp,
  X,
} from "lucide-react";
import { useEffect, useState, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { api, errorMessage, type Attachment, type DocumentExtraction } from "@/lib/api";
import {
  YOUTUBE_TRANSCRIPT_ACTIONS,
  type YoutubeTranscriptAction,
} from "@/lib/youtube-actions";
export { ChatUrlAttachModal } from "./chat-url-attach-modal";
export type { YoutubeTranscriptAction } from "@/lib/youtube-actions";

const CODE_SEGMENT_RE =
  /((?:^|\n)(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n(?:`{3,}|~{3,})(?=\n|$)|$)|`+[^`]*?`+)/g;

export const markdownRemarkPlugins = [remarkGfm, remarkMath];
export const markdownRehypePlugins: NonNullable<ComponentProps<typeof ReactMarkdown>["rehypePlugins"]> = [
  [rehypeKatex, { throwOnError: false, strict: "ignore", errorColor: "#64748b" }],
];

function formatDisplayMathBlock(indent: string, math: string) {
  const body = math
    .trim()
    .split("\n")
    .map((line) => (line.trim() ? `${indent}${line.trim()}` : ""))
    .join("\n");
  return `${indent}$$\n${body}\n${indent}$$`;
}

function normalizeMathSegment(segment: string) {
  return segment
    .replace(
      /(^|\n)([ \t]*)\\\[([\s\S]*?)\\\](?=[ \t]*(?:\n|$))/g,
      (_, prefix: string, indent: string, math: string) =>
        `${prefix}${formatDisplayMathBlock(indent, math)}`
    )
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, math: string) => `\n$$\n${math.trim()}\n$$\n`)
    .replace(
      /(^|\n)([ \t]*)\$\$([^\n$]+?)\$\$(?=[ \t]*(?:\n|$))/g,
      (_, prefix: string, indent: string, math: string) =>
        `${prefix}${formatDisplayMathBlock(indent, math)}`
    )
    .replace(
      /(^|\n)([ \t]*)\[[ \t]*\n([\s\S]*?\\[a-zA-Z]+[\s\S]*?)\n[ \t]*\](?=[ \t]*(?:\n|$))/g,
      (_, prefix: string, indent: string, math: string) =>
        `${prefix}${formatDisplayMathBlock(indent, math)}`
    )
    .replace(
      /\\\(([\s\S]*?)\\\)/g,
      (_, math: string) => `$${math.trim().replace(/\s*\n\s*/g, " ")}$`
    );
}

export function normalizeMathMarkdown(content: string) {
  return content
    .split(CODE_SEGMENT_RE)
    .map((part, index) => (index % 2 === 1 ? part : normalizeMathSegment(part)))
    .join("");
}

function YoutubeActionIcon({ id, size = 13 }: { id: YoutubeTranscriptAction; size?: number }) {
  switch (id) {
    case "analyze":
      return <Brain size={size} />;
    case "key_points":
      return <ListOrdered size={size} />;
    case "study":
      return <GraduationCap size={size} />;
    case "translate_fr":
      return <Languages size={size} />;
    case "summarize":
    default:
      return <Sparkles size={size} />;
  }
}

export function AttachmentAnalysis({
  attachment,
  isFinance,
  onYoutubeAction,
  actionDisabled,
  autoOpenModal,
  onAutoOpened,
}: {
  attachment: Attachment;
  isFinance?: boolean;
  onYoutubeAction?: (attachment: Attachment, action: YoutubeTranscriptAction) => void;
  actionDisabled?: boolean;
  autoOpenModal?: boolean;
  onAutoOpened?: () => void;
}) {
  const [extraction, setExtraction] = useState<DocumentExtraction | null>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [rawText, setRawText] = useState(!isFinance);
  const [modalOpen, setModalOpen] = useState(false);
  const [copiedTranscript, setCopiedTranscript] = useState(false);

  const isYoutube =
    attachment.filename.startsWith("🎬") ||
    attachment.mime_type.includes("youtube") ||
    extraction?.model === "youtube-transcript";

  useEffect(() => {
    if (!autoOpenModal) return;
    let cancelled = false;
    async function openAndLoad() {
      if (extraction === undefined && !loading) {
        setLoading(true);
        setError("");
        try {
          const result = await api<{ extraction: DocumentExtraction | null }>(
            `/attachments/${attachment.id}/extraction`,
          );
          if (!cancelled) setExtraction(result.extraction);
        } catch (err) {
          if (!cancelled) setError(errorMessage(err));
        } finally {
          if (!cancelled) setLoading(false);
        }
      }
      if (!cancelled) {
        setModalOpen(true);
        onAutoOpened?.();
      }
    }
    void openAndLoad();
    return () => {
      cancelled = true;
    };
  }, [autoOpenModal, attachment.id, extraction, loading, onAutoOpened]);

  useEffect(() => {
    if (!modalOpen) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setModalOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [modalOpen]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const result = await api<{ extraction: DocumentExtraction | null }>(
        `/attachments/${attachment.id}/extraction`
      );
      setExtraction(result.extraction);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function triggerYoutubeAction(action: YoutubeTranscriptAction) {
    if (!onYoutubeAction || actionDisabled) return;
    setModalOpen(false);
    onYoutubeAction(attachment, action);
  }

  async function copyTranscript(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedTranscript(true);
      window.setTimeout(() => setCopiedTranscript(false), 1800);
    } catch {
      /* ignore clipboard error */
    }
  }

  function downloadTranscript(text: string) {
    const cleanBase = attachment.filename
      .replace(/^🎬\s*/, "")
      .replace(/[^a-zA-Z0-9\u00C0-\u017F_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "transcript-youtube";
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${cleanBase}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const page = extraction?.pages[pageIndex];
  const isVision = attachment.analysis_mode === "vision" || page?.method === "vision";
  const charCount = page?.markdown ? page.markdown.length : attachment.extracted_chars || 0;

  return (
    <>
      <details
        className={`attachment-analysis ${isFinance ? "finance-analysis" : ""} ${isYoutube ? "youtube-analysis" : ""}`}
        onToggle={(event) => {
          if (event.currentTarget.open && extraction === undefined && !loading && !error) void load();
        }}
      >
        <summary>
          {isFinance ? (
            <TrendingUp size={14} />
          ) : isYoutube ? (
            <SquarePlay size={14} />
          ) : isVision ? (
            <Eye size={14} />
          ) : (
            <BookOpen size={14} />
          )}
          {isFinance ? (
            "Données financières détaillées Yahoo Finance (valorisation, bilan, historique des cours)"
          ) : isYoutube ? (
            <>
              Transcription de la vidéo
              {charCount ? <span>{charCount.toLocaleString("fr-FR")} car.</span> : null}
            </>
          ) : isVision ? (
            "Analyse visuelle détaillée (Modèle Vision)"
          ) : (
            <>
              Contenu extrait
              {attachment.page_count ? <span>{attachment.page_count} p.</span> : null}
            </>
          )}
        </summary>
        {loading && (
          <p className="analysis-status" role="status">
            <LoaderCircle size={14} className="spin" />
            Chargement de l’analyse…
          </p>
        )}
        {error && (
          <div className="analysis-status" role="alert">
            <p>{error}</p>
            <button
              type="button"
              className="icon-button"
              aria-label="Réessayer le chargement"
              title="Réessayer le chargement"
              onClick={() => void load()}
            >
              <RefreshCw size={15} />
            </button>
          </div>
        )}
        {extraction === null && (
          <p className="analysis-status">
            Analyse indisponible pour cette pièce jointe. Joignez à nouveau le fichier pour l’analyser.
          </p>
        )}
        {extraction && page && (
          <>
            <div className="analysis-toolbar">
              {!isYoutube && (
                <>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Page précédente"
                    title="Page précédente"
                    disabled={pageIndex === 0}
                    onClick={() => setPageIndex((index) => index - 1)}
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <label>
                    Page{" "}
                    <select
                      value={pageIndex}
                      onChange={(event) => setPageIndex(Number(event.target.value))}
                    >
                      {extraction.pages.map((item, index) => (
                        <option key={item.index} value={index}>
                          {item.index + 1}
                        </option>
                      ))}
                    </select>{" "}
                    / {extraction.pages.length}
                  </label>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Page suivante"
                    title="Page suivante"
                    disabled={pageIndex === extraction.pages.length - 1}
                    onClick={() => setPageIndex((index) => index + 1)}
                  >
                    <ChevronRight size={16} />
                  </button>
                </>
              )}
              <span>
                {isYoutube
                  ? `YouTube · ${charCount.toLocaleString("fr-FR")} caractères`
                  : page.method === "vision"
                    ? "Vision IA détaillée"
                    : page.method === "local"
                      ? isFinance
                        ? "Yahoo Finance API"
                        : "Extraction locale"
                      : "Mistral OCR"}
              </span>
              {isYoutube && (
                <button
                  type="button"
                  className="analysis-expand-btn"
                  onClick={() => setModalOpen(true)}
                  title="Ouvrir la transcription complète dans une modale"
                >
                  <Maximize2 size={13} />
                  <span>Agrandir</span>
                </button>
              )}
            </div>
            {isYoutube && onYoutubeAction && (
              <div className="analysis-quick-actions" role="group" aria-label="Actions sur la transcription">
                {YOUTUBE_TRANSCRIPT_ACTIONS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`analysis-action-btn ${item.toneClass}`}
                    disabled={actionDisabled}
                    onClick={() => triggerYoutubeAction(item.id)}
                    title={item.description}
                  >
                    <YoutubeActionIcon id={item.id} size={13} />
                    <span>{item.shortLabel}</span>
                  </button>
                ))}
              </div>
            )}
            {isYoutube && attachment.youtube_meta?.has_transcript === false && (
              <p className="analysis-warning" role="status">
                <CircleAlert size={13} style={{ display: "inline", marginRight: 5 }} />
                Aucun sous-titre n’est disponible sur YouTube pour cette vidéo ; seules les métadonnées et la description ont pu être récupérées.
              </p>
            )}
            <div className="analysis-format" role="group" aria-label="Format de lecture">
              <button type="button" aria-pressed={rawText} onClick={() => setRawText(true)}>
                <FileText size={13} />
                Texte brut
              </button>
              <button type="button" aria-pressed={!rawText} onClick={() => setRawText(false)}>
                <BookOpen size={13} />
                Mise en forme
              </button>
            </div>
            <div className="analysis-content" aria-live="polite">
              {extraction.warnings.map((warning, index) => (
                <p className="analysis-warning" key={index}>
                  {warning}
                </p>
              ))}
              <section className="analysis-section">
                <h4>
                  {isFinance
                    ? "Tableaux et indicateurs financiers Yahoo Finance"
                    : isYoutube
                      ? "Transcription intégrale de la vidéo"
                      : isVision
                        ? `Description visuelle détaillée · page ${page.index + 1}`
                        : `Transcription OCR · page ${page.index + 1}`}
                </h4>
                {page.markdown.trim() ? (
                  rawText ? (
                    <pre className="analysis-transcript">{page.markdown}</pre>
                  ) : (
                    <div className="markdown">
                      <ReactMarkdown
                        skipHtml
                        remarkPlugins={markdownRemarkPlugins}
                        rehypePlugins={markdownRehypePlugins}
                        components={{
                          img: ({ alt }) => (
                            <span className="analysis-image-label">[{alt || "Illustration"}]</span>
                          ),
                          a: ({ children, href }) => (
                            <a href={href} target="_blank" rel="noreferrer">
                              {children}
                            </a>
                          ),
                          table: ({ children }) => (
                            <div className="table-scroll">
                              <table>{children}</table>
                            </div>
                          ),
                        }}
                      >
                        {normalizeMathMarkdown(page.markdown)}
                      </ReactMarkdown>
                    </div>
                  )
                ) : page.vision_description ? (
                  <p>{page.vision_description}</p>
                ) : (
                  <p>Aucun texte détecté.</p>
                )}
              </section>
              {page.images.map(
                (image) =>
                  image.annotation && (
                    <section className="analysis-section" key={image.id}>
                      <h4>
                        {image.id} · {image.annotation.image_type}
                      </h4>
                      <p>{image.annotation.description}</p>
                      {image.annotation.visible_text && (
                        <pre className="analysis-transcript analysis-visible-text">
                          {image.annotation.visible_text}
                        </pre>
                      )}
                    </section>
                  )
              )}
              {page.vision_description && (
                <section className="analysis-section">
                  <h4>Description visuelle · page {page.index + 1}</h4>
                  <p>{page.vision_description}</p>
                </section>
              )}
              {pageIndex === 0 && extraction.annotations.length > 0 && (
                <details className="analysis-annotations">
                  <summary>Analyse documentaire complémentaire</summary>
                  {extraction.annotations.map((annotation, index) => (
                    <section className="analysis-section" key={index}>
                      <h4>{annotation.title || "Relevé documentaire"}</h4>
                      <p>{annotation.summary}</p>
                    </section>
                  ))}
                </details>
              )}
            </div>
          </>
        )}
      </details>
      {modalOpen && extraction && page && (
        <div
          className="modal-backdrop transcript-modal-backdrop"
          onClick={(event) => {
            if (event.target === event.currentTarget) setModalOpen(false);
          }}
        >
          <section
            className="modal transcript-modal"
            role="dialog"
            aria-modal="true"
            aria-label={`Transcription — ${attachment.filename}`}
          >
            <div className="transcript-modal-header">
              <div className="transcript-modal-title">
                <span className="modal-icon" style={{ background: "#fef2f2", color: "#dc2626" }}>
                  <SquarePlay size={18} />
                </span>
                <div>
                  <h2>{attachment.filename.replace(/^🎬\s*/, "")}</h2>
                  <small>
                    {charCount.toLocaleString("fr-FR")} caractères · Transcription intégrale
                    {attachment.youtube_meta?.duration ? ` · ${attachment.youtube_meta.duration}` : ""}
                    {attachment.youtube_meta?.lang_label ? ` · ${attachment.youtube_meta.lang_label}` : ""}
                  </small>
                </div>
              </div>
              <div className="transcript-modal-header-actions">
                {onYoutubeAction && (
                  <>
                    {YOUTUBE_TRANSCRIPT_ACTIONS.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`analysis-action-btn ${item.toneClass}`}
                        disabled={actionDisabled}
                        onClick={() => triggerYoutubeAction(item.id)}
                        title={item.description}
                      >
                        <YoutubeActionIcon id={item.id} size={13} />
                        <span>{item.shortLabel}</span>
                      </button>
                    ))}
                  </>
                )}
                <button
                  type="button"
                  className="secondary-button transcript-copy-btn"
                  onClick={() => void copyTranscript(page.markdown)}
                  title="Copier toute la transcription"
                >
                  {copiedTranscript ? <Check size={14} /> : <Copy size={14} />}
                  <span>{copiedTranscript ? "Copié" : "Copier"}</span>
                </button>
                <button
                  type="button"
                  className="secondary-button transcript-copy-btn"
                  onClick={() => downloadTranscript(page.markdown)}
                  title="Télécharger toute la transcription en fichier Markdown (.md)"
                >
                  <Download size={14} />
                  <span>.md</span>
                </button>
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Fermer la transcription"
                  title="Fermer la transcription"
                  onClick={() => setModalOpen(false)}
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="transcript-modal-toolbar">
              <div className="analysis-format" role="group" aria-label="Format de lecture">
                <button type="button" aria-pressed={rawText} onClick={() => setRawText(true)}>
                  <FileText size={13} />
                  Texte brut
                </button>
                <button type="button" aria-pressed={!rawText} onClick={() => setRawText(false)}>
                  <BookOpen size={13} />
                  Mise en forme
                </button>
              </div>
              {attachment.source_url && (
                <a
                  className="document-link document-youtube-link"
                  href={attachment.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <SquarePlay size={14} />
                  <span>Ouvrir sur YouTube</span>
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
            <div className="transcript-modal-body">
              {page.markdown.trim() ? (
                rawText ? (
                  <pre className="analysis-transcript">{page.markdown}</pre>
                ) : (
                  <div className="markdown">
                    <ReactMarkdown
                      skipHtml
                      remarkPlugins={markdownRemarkPlugins}
                      rehypePlugins={markdownRehypePlugins}
                      components={{
                        img: ({ alt }) => (
                          <span className="analysis-image-label">[{alt || "Illustration"}]</span>
                        ),
                        a: ({ children, href }) => (
                          <a href={href} target="_blank" rel="noreferrer">
                            {children}
                          </a>
                        ),
                        table: ({ children }) => (
                          <div className="table-scroll">
                            <table>{children}</table>
                          </div>
                        ),
                      }}
                    >
                      {normalizeMathMarkdown(page.markdown)}
                    </ReactMarkdown>
                  </div>
                )
              ) : (
                <p>Aucun texte détecté.</p>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}

export function AttachmentView({
  attachment,
  onOpenFinanceModal,
  onYoutubeAction,
  actionDisabled,
}: {
  attachment: Attachment;
  onOpenFinanceModal?: (queryOrSymbol?: string) => void;
  onYoutubeAction?: (attachment: Attachment, action: YoutubeTranscriptAction) => void;
  actionDisabled?: boolean;
}) {
  const isYoutube = attachment.filename.startsWith("🎬") || attachment.mime_type.includes("youtube");
  const isFinance = attachment.filename.startsWith("📈") || attachment.mime_type.includes("finance");
  const isWeb =
    attachment.mime_type.startsWith("text/html") ||
    !!attachment.source_url ||
    attachment.filename.startsWith("🌐");

  if (isFinance) {
    const meta = attachment.finance_meta;
    const isEOD =
      meta?.provider === "eodhd" ||
      attachment.mime_type.includes("source=eod") ||
      attachment.filename.includes("EOD Historical Data");
    const symbol = meta?.symbol || attachment.filename.match(/\(([A-Za-z0-9\.\^=_-]+)\)/)?.[1] || "";
    const shortName =
      meta?.short_name ||
      meta?.long_name ||
      attachment.filename.replace(/^📈\s*/, "").replace(/\s*·.*$/, "");
    const price = meta?.price;
    const currency = meta?.currency || (symbol.endsWith(".US") ? "USD" : "EUR");
    const changePct = meta?.change_percent;
    const sourceLabel = meta?.source_label || (isEOD ? "EOD Historical Data API" : "Yahoo Finance API");
    const externalLabel = isEOD ? "EODHD" : "Yahoo Finance";
    const externalUrl =
      meta?.url ||
      attachment.source_url ||
      (isEOD
        ? `https://eodhd.com/financial-summary/${symbol}`
        : symbol
          ? `https://finance.yahoo.com/quote/${symbol}`
          : "https://finance.yahoo.com");

    return (
      <div className="finance-attachment-card" role="region" aria-label={`Données financières pour ${shortName}`}>
        <div className="finance-card-header">
          <div className="finance-card-identity">
            <span className="finance-card-icon">
              <TrendingUp size={16} />
            </span>
            <div>
              <div className="finance-card-title-row">
                <strong className="finance-card-name">{shortName}</strong>
                {symbol && <span className="finance-symbol-badge">{symbol}</span>}
                <span className="finance-source-tag">
                  <TrendingUp size={11} /> {sourceLabel}
                </span>
              </div>
              <p className="finance-card-sub">
                {isEOD
                  ? "Cotations en direct et historique des séances EOD"
                  : "Données financières, valorisation et consensus d'analystes"}
              </p>
            </div>
          </div>
          <div className="finance-card-side">
            {price != null && (
              <div className="finance-card-quote">
                <span className="finance-quote-price">
                  {price} <small>{currency}</small>
                </span>
                {changePct != null && (
                  <span className={`finance-quote-change ${changePct >= 0 ? "is-up" : "is-down"}`}>
                    {changePct >= 0 ? "+" : ""}
                    {changePct.toFixed(2)}%
                  </span>
                )}
              </div>
            )}
            <div className="finance-card-actions-group">
              {onOpenFinanceModal && (
                <button
                  type="button"
                  className="finance-card-modal-btn"
                  onClick={() => onOpenFinanceModal(symbol || shortName)}
                  title="Ouvrir la courbe de cours EOD et les tableaux financiers Yahoo Finance"
                >
                  <LineChart size={13} />
                  <span>Courbe & Stats</span>
                </button>
              )}
              <a
                className="finance-card-external-btn"
                href={externalUrl}
                target="_blank"
                rel="noreferrer"
                title={`Ouvrir la cotation en direct sur ${externalLabel}`}
              >
                <span>{externalLabel}</span>
                <ExternalLink size={12} />
              </a>
            </div>
          </div>
        </div>
        <AttachmentAnalysis attachment={attachment} isFinance={true} />
      </div>
    );
  }

  return (
    <div className="attachment-entry">
      {attachment.mime_type.startsWith("image/") ? (
        <div className="message-image-wrap">
          <a className="message-image" href={attachment.url} target="_blank" rel="noreferrer">
            <img src={attachment.url} alt={attachment.filename} loading="lazy" />
            <span>
              {attachment.filename}
              <ExternalLink size={13} />
            </span>
          </a>
          {attachment.analysis_mode === "vision" ? (
            <span className="attachment-mode-tag mode-vision">
              <Eye size={10} /> Vision IA
            </span>
          ) : attachment.analysis_mode === "ocr" ? (
            <span className="attachment-mode-tag mode-ocr">
              <FileText size={10} /> Mistral OCR
            </span>
          ) : null}
        </div>
      ) : isYoutube ? (
        <a
          className="document-link document-youtube-link"
          href={attachment.source_url || attachment.url}
          target="_blank"
          rel="noreferrer"
          title="Ouvrir la vidéo sur YouTube"
        >
          <SquarePlay size={18} />
          <span>{attachment.filename}</span>
          <ExternalLink size={13} />
        </a>
      ) : isWeb ? (
        <a
          className="document-link document-web-link"
          href={attachment.source_url || attachment.url}
          target="_blank"
          rel="noreferrer"
          title="Consulter la page d'origine"
        >
          <Globe2 size={18} />
          <span>{attachment.filename}</span>
          <ExternalLink size={13} />
        </a>
      ) : (
        <a className="document-link" href={attachment.url} target="_blank" rel="noreferrer">
          <FileText size={18} />
          <span>{attachment.filename}</span>
          {attachment.analysis_mode === "ocr" ? (
            <span className="attachment-mode-tag mode-ocr">
              <FileText size={10} /> Mistral OCR
            </span>
          ) : null}
          <ExternalLink size={13} />
        </a>
      )}
      <AttachmentAnalysis
        attachment={attachment}
        onYoutubeAction={onYoutubeAction}
        actionDisabled={actionDisabled}
      />
    </div>
  );
}
