"use client";

import {
  ArrowDown, ArrowRightLeft, ArrowUp, BookOpen, Brain, Check, ChevronDown, ChevronLeft, ChevronRight,
  CircleAlert, Code2, Compass, Copy, Download, ExternalLink, Eye, FileCode2, FileText, FolderArchive,
  Globe2, GraduationCap, ImagePlus, LineChart, Link2, LoaderCircle, LogOut, Menu, MessageCircle, Newspaper, PanelLeftClose, Paperclip,
  Pencil, Plus, Presentation, Search, RefreshCw, Settings, Share2, Shield, Sparkles, Square, SquarePlay, Trash2, TrendingUp, Users, UsersRound, Volume2, WandSparkles, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { AdminPanel } from "@/components/admin-panel";
import { AuthPanel } from "@/components/auth-panel";
import { BlogModal } from "@/components/blog-modal";
import { CodeCanvas } from "@/components/code-canvas";
import { DeepSearchModal } from "@/components/deep-search-modal";
import { ResearchActivityModal } from "@/components/research-activity-modal";
import type { ResearchActivity, ResearchRun } from "@/lib/research-activity";
import { FamilyModal } from "@/components/family-modal";
import { ImageStudioModal } from "@/components/image-studio-modal";
import { SoundStudioModal } from "@/components/sound-studio-modal";
import { FinanceModal } from "@/components/finance-modal";
import { MultiAgentModal } from "@/components/multi-agent-modal";
import { LearnModal } from "@/components/learn-modal";
import { ModelModal } from "@/components/model-modal";
import { SettingsModal } from "@/components/settings-modal";
import { SkillsPanel } from "@/components/skills-panel";
import { StudyModal } from "@/components/study-modal";
import { StageModelsModal } from "@/components/stage-models-modal";
import { ThoughtAccordion } from "@/components/thought-accordion";
import { ApiError, api, attachUrl, createLearnReportFromMessage, createReportFromMessage, errorMessage, skillToSlug, streamMessage, type Attachment, type AuthUser, type Config, type Conversation, type DocumentExtraction, type FamilyGroupInfo, type FinancialDashboardData, type GeneratedSound, type Memory, type Message, type Model, type MultiAgentConfig, type Skill, type Source, type StageModelsConfig } from "@/lib/api";
import { collectConversationCanvasFiles, createZipBlob, extractCanvasFiles, hasExplicitCanvasFiles, triggerBlobDownload } from "@/lib/code-canvas";
import { hasInteractiveLearnModules, stripInteractiveModulesForBody } from "@/lib/learn-parser";

function extractThoughtAndContent(text: string): { thought: string; cleanContent: string } {
  if (!text) return { thought: "", cleanContent: "" };
  const thinkMatch = text.match(/^<think>([\s\S]*?)<\/think>\s*/);
  if (thinkMatch) {
    return {
      thought: thinkMatch[1].trim(),
      cleanContent: text.slice(thinkMatch[0].length),
    };
  }
  return { thought: "", cleanContent: text };
}

const DEFAULT_THEMES = [
  "Codage",
  "Santé",
  "Travail & Projets",
  "Sciences & Tech",
  "Apprentissage",
  "Finance & Droit",
  "Création & Design",
  "Vie quotidienne",
  "Culture & Loisirs",
  "Général",
];

function themeTone(theme?: string) {
  const key = (theme || "Général").toLocaleLowerCase("fr");
  if (key.includes("codage") || key.includes("code") || key.includes("dev")) return "code";
  if (key.includes("santé") || key.includes("sante") || key.includes("médecin")) return "health";
  if (key.includes("travail") || key.includes("projet")) return "work";
  if (key.includes("science") || key.includes("tech")) return "science";
  if (key.includes("apprenti") || key.includes("cours")) return "learn";
  if (key.includes("finance") || key.includes("droit")) return "finance";
  if (key.includes("création") || key.includes("design") || key.includes("art")) return "creative";
  if (key.includes("quotidien") || key.includes("cuisine") || key.includes("maison")) return "daily";
  if (key.includes("culture") || key.includes("loisir")) return "culture";
  return "general";
}

const suggestions = [
  { icon: WandSparkles, title: "Faire émerger une idée", description: "Explorer une piste et lui donner forme", prompt: "Aide-moi à explorer une idée. Pose-moi quelques questions pour comprendre ce que je veux créer." },
  { icon: Newspaper, title: "Créer un blog d’actualités", description: "Veille auto sur les news IA via SearXNG", prompt: "Les dernières actualités et avancées en intelligence artificielle" },
  { icon: FileText, title: "Travailler un document", description: "Résumer, analyser, prendre du recul", prompt: "Je vais joindre un document. Peux-tu m’en proposer une synthèse et en faire ressortir les points essentiels ?" },
  { icon: ImagePlus, title: "Imaginer une image", description: "Du premier mot à une création visuelle", prompt: "Une petite maison d’architecte au milieu d’une forêt brumeuse, lumière du matin, photographie cinématographique." },
];

function subscribeToLocation(callback: () => void) {
  window.addEventListener("popstate", callback);
  window.addEventListener("hashchange", callback);
  return () => {
    window.removeEventListener("popstate", callback);
    window.removeEventListener("hashchange", callback);
  };
}

function getInvitationToken() {
  return new URLSearchParams(window.location.hash.slice(1)).get("invite") ?? "";
}

function shortDate(value: string) {
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(new Date(value));
}

function dateGroup(value: string) {
  const day = new Date(value);
  const today = new Date();
  if (day.toDateString() === today.toDateString()) return "Aujourd’hui";
  if (today.getTime() - day.getTime() < 7 * 86400000) return "Ces 7 derniers jours";
  return "Plus tôt";
}

function BrandMark({ small = false }: { small?: boolean }) {
  return <span className={`brand-mark ${small ? "small" : ""}`} aria-hidden="true"><Sparkles strokeWidth={1.5} /></span>;
}

const CODE_SEGMENT_RE = /((?:^|\n)(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n(?:`{3,}|~{3,})(?=\n|$)|$)|`+[^`]*?`+)/g;
const markdownRemarkPlugins = [remarkGfm, remarkMath];
const markdownRehypePlugins: NonNullable<React.ComponentProps<typeof ReactMarkdown>["rehypePlugins"]> = [
  [rehypeKatex, { throwOnError: false, strict: "ignore", errorColor: "#64748b" }],
];

function formatDisplayMathBlock(indent: string, math: string) {
  const body = math
    .trim()
    .split("\n")
    .map(line => (line.trim() ? `${indent}${line.trim()}` : ""))
    .join("\n");
  return `${indent}$$\n${body}\n${indent}$$`;
}

function normalizeMathSegment(segment: string) {
  return segment
    .replace(/(^|\n)([ \t]*)\\\[([\s\S]*?)\\\](?=[ \t]*(?:\n|$))/g, (_, prefix: string, indent: string, math: string) =>
      `${prefix}${formatDisplayMathBlock(indent, math)}`
    )
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, math: string) => `\n$$\n${math.trim()}\n$$\n`)
    .replace(/(^|\n)([ \t]*)\$\$([^\n$]+?)\$\$(?=[ \t]*(?:\n|$))/g, (_, prefix: string, indent: string, math: string) =>
      `${prefix}${formatDisplayMathBlock(indent, math)}`
    )
    .replace(/(^|\n)([ \t]*)\[[ \t]*\n([\s\S]*?\\[a-zA-Z]+[\s\S]*?)\n[ \t]*\](?=[ \t]*(?:\n|$))/g, (_, prefix: string, indent: string, math: string) =>
      `${prefix}${formatDisplayMathBlock(indent, math)}`
    )
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, math: string) => `$${math.trim().replace(/\s*\n\s*/g, " ")}$`);
}

function normalizeMathMarkdown(content: string) {
  return content
    .split(CODE_SEGMENT_RE)
    .map((part, index) => (index % 2 === 1 ? part : normalizeMathSegment(part)))
    .join("");
}

function IconButton({ label, children, className = "", ...props }: { label: string; children: ReactNode; className?: string } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={`icon-button ${className}`} aria-label={label} title={label} {...props}>{children}</button>;
}

function AttachmentAnalysis({ attachment, isFinance }: { attachment: Attachment; isFinance?: boolean }) {
  const [extraction, setExtraction] = useState<DocumentExtraction | null>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [rawText, setRawText] = useState(!isFinance);
  async function load() {
    setLoading(true); setError("");
    try {
      const result = await api<{ extraction: DocumentExtraction | null }>(`/attachments/${attachment.id}/extraction`);
      setExtraction(result.extraction);
    } catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }
  const page = extraction?.pages[pageIndex];
  const isVision = attachment.analysis_mode === "vision" || page?.method === "vision";
  return <details className={`attachment-analysis ${isFinance ? "finance-analysis" : ""}`} onToggle={event => {
    if (event.currentTarget.open && extraction === undefined && !loading && !error) void load();
  }}>
    <summary>
      {isFinance ? <TrendingUp size={14} /> : isVision ? <Eye size={14} /> : <BookOpen size={14} />}
      {isFinance ? "Données financières détaillées Yahoo Finance (valorisation, bilan, historique des cours)" : isVision ? "Analyse visuelle détaillée (Modèle Vision)" : <>Contenu extrait{attachment.page_count ? <span>{attachment.page_count} p.</span> : null}</>}
    </summary>
    {loading && <p className="analysis-status" role="status"><LoaderCircle size={14} className="spin" />Chargement de l’analyse…</p>}
    {error && <div className="analysis-status" role="alert"><p>{error}</p><IconButton label="Réessayer le chargement" onClick={() => void load()}><RefreshCw size={15} /></IconButton></div>}
    {extraction === null && <p className="analysis-status">Analyse indisponible pour cette pièce jointe. Joignez à nouveau le fichier pour l’analyser.</p>}
    {extraction && page && <>
      <div className="analysis-toolbar">
        <IconButton label="Page précédente" disabled={pageIndex === 0} onClick={() => setPageIndex(index => index - 1)}><ChevronLeft size={16} /></IconButton>
        <label>Page <select value={pageIndex} onChange={event => setPageIndex(Number(event.target.value))}>{extraction.pages.map((item, index) => <option key={item.index} value={index}>{item.index + 1}</option>)}</select> / {extraction.pages.length}</label>
        <IconButton label="Page suivante" disabled={pageIndex === extraction.pages.length - 1} onClick={() => setPageIndex(index => index + 1)}><ChevronRight size={16} /></IconButton>
        <span>{page.method === "vision" ? "Vision IA détaillée" : page.method === "local" ? (isFinance ? "Yahoo Finance API" : "Extraction locale") : "Mistral OCR"}</span>
      </div>
      <div className="analysis-format" role="group" aria-label="Format de lecture">
        <button type="button" aria-pressed={rawText} onClick={() => setRawText(true)}><FileText size={13} />Texte brut</button>
        <button type="button" aria-pressed={!rawText} onClick={() => setRawText(false)}><BookOpen size={13} />Mise en forme</button>
      </div>
      <div className="analysis-content" aria-live="polite">
        {extraction.warnings.map((warning, index) => <p className="analysis-warning" key={index}>{warning}</p>)}
        <section className="analysis-section"><h4>{isFinance ? "Tableaux et indicateurs financiers Yahoo Finance" : isVision ? `Description visuelle détaillée · page ${page.index + 1}` : `Transcription OCR · page ${page.index + 1}`}</h4>
          {page.markdown.trim() ? rawText ? <pre className="analysis-transcript">{page.markdown}</pre> : <div className="markdown"><ReactMarkdown skipHtml remarkPlugins={markdownRemarkPlugins} rehypePlugins={markdownRehypePlugins} components={{
            img: ({ alt }) => <span className="analysis-image-label">[{alt || "Illustration"}]</span>,
            a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
            table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
          }}>{normalizeMathMarkdown(page.markdown)}</ReactMarkdown></div> : (page.vision_description ? <p>{page.vision_description}</p> : <p>Aucun texte détecté.</p>)}
        </section>
        {page.images.map(image => image.annotation && <section className="analysis-section" key={image.id}>
          <h4>{image.id} · {image.annotation.image_type}</h4><p>{image.annotation.description}</p>
          {image.annotation.visible_text && <pre className="analysis-transcript analysis-visible-text">{image.annotation.visible_text}</pre>}
        </section>)}
        {page.vision_description && <section className="analysis-section"><h4>Description visuelle · page {page.index + 1}</h4><p>{page.vision_description}</p></section>}
        {pageIndex === 0 && extraction.annotations.length > 0 && <details className="analysis-annotations"><summary>Analyse documentaire complémentaire</summary>
          {extraction.annotations.map((annotation, index) => <section className="analysis-section" key={index}><h4>{annotation.title || "Relevé documentaire"}</h4><p>{annotation.summary}</p></section>)}
        </details>}
      </div>
    </>}
  </details>;
}

function AttachmentView({
  attachment,
  onOpenFinanceModal,
}: {
  attachment: Attachment;
  onOpenFinanceModal?: (queryOrSymbol?: string) => void;
}) {
  const isYoutube = attachment.filename.startsWith("🎬") || attachment.mime_type.includes("youtube");
  const isFinance = attachment.filename.startsWith("📈") || attachment.mime_type.includes("finance");
  const isWeb = attachment.mime_type.startsWith("text/html") || !!attachment.source_url || attachment.filename.startsWith("🌐");

  if (isFinance) {
    const meta = attachment.finance_meta;
    const isEOD = meta?.provider === "eodhd" || attachment.mime_type.includes("source=eod") || attachment.filename.includes("EOD Historical Data");
    const symbol = meta?.symbol || attachment.filename.match(/\(([A-Za-z0-9\.\^=_-]+)\)/)?.[1] || "";
    const shortName = meta?.short_name || meta?.long_name || attachment.filename.replace(/^📈\s*/, "").replace(/\s*·.*$/, "");
    const price = meta?.price;
    const currency = meta?.currency || (symbol.endsWith(".US") ? "USD" : "EUR");
    const changePct = meta?.change_percent;
    const sourceLabel = meta?.source_label || (isEOD ? "EOD Historical Data API" : "Yahoo Finance API");
    const externalLabel = isEOD ? "EODHD" : "Yahoo Finance";
    const externalUrl = meta?.url || attachment.source_url || (isEOD ? `https://eodhd.com/financial-summary/${symbol}` : (symbol ? `https://finance.yahoo.com/quote/${symbol}` : "https://finance.yahoo.com"));

    return (
      <div className="finance-attachment-card" role="region" aria-label={`Données financières pour ${shortName}`}>
        <div className="finance-card-header">
          <div className="finance-card-identity">
            <span className="finance-card-icon"><TrendingUp size={16} /></span>
            <div>
              <div className="finance-card-title-row">
                <strong className="finance-card-name">{shortName}</strong>
                {symbol && <span className="finance-symbol-badge">{symbol}</span>}
                <span className="finance-source-tag"><TrendingUp size={11} /> {sourceLabel}</span>
              </div>
              <p className="finance-card-sub">{isEOD ? "Cotations en direct et historique des séances EOD" : "Données financières, valorisation et consensus d'analystes"}</p>
            </div>
          </div>
          <div className="finance-card-side">
            {price != null && (
              <div className="finance-card-quote">
                <span className="finance-quote-price">{price} <small>{currency}</small></span>
                {changePct != null && (
                  <span className={`finance-quote-change ${changePct >= 0 ? "is-up" : "is-down"}`}>
                    {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
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

  return <div className="attachment-entry">
    {attachment.mime_type.startsWith("image/")
      ? <div className="message-image-wrap"><a className="message-image" href={attachment.url} target="_blank" rel="noreferrer"><img src={attachment.url} alt={attachment.filename} loading="lazy" /><span>{attachment.filename}<ExternalLink size={13} /></span></a>{attachment.analysis_mode === "vision" ? <span className="attachment-mode-tag mode-vision"><Eye size={10} /> Vision IA</span> : attachment.analysis_mode === "ocr" ? <span className="attachment-mode-tag mode-ocr"><FileText size={10} /> Mistral OCR</span> : null}</div>
      : isYoutube
      ? <a className="document-link document-youtube-link" href={attachment.source_url || attachment.url} target="_blank" rel="noreferrer" title="Ouvrir la vidéo sur YouTube"><SquarePlay size={18} /><span>{attachment.filename}</span><ExternalLink size={13} /></a>
      : isWeb
      ? <a className="document-link document-web-link" href={attachment.source_url || attachment.url} target="_blank" rel="noreferrer" title="Consulter la page d'origine"><Globe2 size={18} /><span>{attachment.filename}</span><ExternalLink size={13} /></a>
      : <a className="document-link" href={attachment.url} target="_blank" rel="noreferrer"><FileText size={18} /><span>{attachment.filename}</span>{attachment.analysis_mode === "ocr" ? <span className="attachment-mode-tag mode-ocr"><FileText size={10} /> Mistral OCR</span> : null}<ExternalLink size={13} /></a>}
    <AttachmentAnalysis attachment={attachment} />
  </div>;
}

type LightboxImageInfo = {
  src: string;
  fallbackSrc?: string;
  title: string;
  pageUrl?: string;
  domain?: string;
  resolution?: string;
};

function safeHostname(url?: string): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function MarkdownInlineImage({
  src,
  alt,
  imageSources,
  onOpenLightbox,
}: {
  src?: string;
  alt?: string;
  imageSources: Source[];
  onOpenLightbox: (info: LightboxImageInfo) => void;
}) {
  const rawSrc = typeof src === "string" ? src.trim() : "";
  const matched = useMemo(
    () =>
      imageSources.find(
        item =>
          item.img_src === rawSrc ||
          item.thumbnail_src === rawSrc ||
          item.url === rawSrc,
      ),
    [imageSources, rawSrc],
  );
  const primarySrc = matched?.img_src || rawSrc;
  const fallbackSrc =
    matched?.thumbnail_src && matched.thumbnail_src !== primarySrc
      ? matched.thumbnail_src
      : undefined;
  const [activeSrc, setActiveSrc] = useState(primarySrc);
  const [triedFallback, setTriedFallback] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setActiveSrc(primarySrc);
    setTriedFallback(false);
    setFailed(false);
  }, [primarySrc]);

  if (!activeSrc || failed) return null;

  const caption = (alt && alt.trim() && alt.trim() !== "Image" ? alt.trim() : matched?.title) || "";
  const pageUrl = matched?.url || primarySrc;
  const domain = matched?.image_source || safeHostname(pageUrl);

  return (
    <span className="markdown-inline-figure">
      <span
        className="markdown-inline-img-wrap"
        role="button"
        tabIndex={0}
        title="Cliquer pour agrandir l’image"
        onClick={() =>
          onOpenLightbox({
            src: activeSrc,
            fallbackSrc,
            title: caption || "Illustration Web",
            pageUrl,
            domain,
            resolution: matched?.resolution,
          })
        }
        onKeyDown={e => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpenLightbox({
              src: activeSrc,
              fallbackSrc,
              title: caption || "Illustration Web",
              pageUrl,
              domain,
              resolution: matched?.resolution,
            });
          }
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={activeSrc}
          alt={caption || "Illustration web"}
          loading="lazy"
          className="markdown-inline-img"
          onError={() => {
            if (!triedFallback && fallbackSrc) {
              setTriedFallback(true);
              setActiveSrc(fallbackSrc);
            } else {
              setFailed(true);
            }
          }}
        />
        <span className="markdown-inline-zoom-badge">
          <Eye size={12} />
          <span>Agrandir</span>
        </span>
      </span>
      {(caption || domain) && (
        <span className="markdown-inline-caption">
          {caption && <span className="markdown-inline-caption-text">{caption}</span>}
          {pageUrl && domain && (
            <a
              href={pageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="markdown-inline-source-pill"
              title={`Voir la page d’origine sur ${domain}`}
              onClick={e => e.stopPropagation()}
            >
              <Globe2 size={10} />
              <span>{domain}</span>
              <ExternalLink size={10} />
            </a>
          )}
        </span>
      )}
    </span>
  );
}

function SourceImageThumb({
  source,
  onOpenLightbox,
}: {
  source: Source;
  onOpenLightbox: (info: LightboxImageInfo) => void;
}) {
  const thumbSrc = source.thumbnail_src || source.img_src || "";
  const fullSrc = source.img_src || source.thumbnail_src || "";
  const [activeSrc, setActiveSrc] = useState(thumbSrc);
  const [triedFallback, setTriedFallback] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!activeSrc || failed) return null;
  const domain = source.image_source || safeHostname(source.url);

  return (
    <button
      type="button"
      className="source-image-card"
      onClick={() =>
        onOpenLightbox({
          src: fullSrc,
          fallbackSrc: thumbSrc !== fullSrc ? thumbSrc : undefined,
          title: source.title || "Illustration Web",
          pageUrl: source.url,
          domain,
          resolution: source.resolution,
        })
      }
      title={`${source.title || "Image Web"}${domain ? ` (${domain})` : ""}`}
    >
      <span className="source-image-thumb-wrap">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={activeSrc}
          alt={source.title || "Image web"}
          loading="lazy"
          onError={() => {
            if (!triedFallback && fullSrc && fullSrc !== activeSrc) {
              setTriedFallback(true);
              setActiveSrc(fullSrc);
            } else {
              setFailed(true);
            }
          }}
        />
      </span>
      <span className="source-image-meta">
        <span className="source-image-title">{source.title || domain || "Image"}</span>
        {domain && <small className="source-image-domain">{domain}</small>}
      </span>
    </button>
  );
}

function MessageView({
  message,
  streaming,
  onOpenCanvas,
  onOpenDeepSearchReport,
  onOpenLearnReport,
  onOpenFinanceModal,
  researchActivity,
  onOpenResearchActivity,
}: {
  message: Message;
  streaming?: boolean;
  onOpenCanvas?: (messageId: string, filePath?: string, forceUnnamed?: boolean) => void;
  onOpenDeepSearchReport?: (message: Message) => void;
  onOpenLearnReport?: (message: Message) => void;
  onOpenFinanceModal?: (queryOrSymbol?: string) => void;
  researchActivity?: ResearchRun;
  onOpenResearchActivity?: (messageId: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [zipDownloaded, setZipDownloaded] = useState(false);
  const [showAllSources, setShowAllSources] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [lightboxImage, setLightboxImage] = useState<LightboxImageInfo | null>(null);
  const exportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!exportOpen) return;
    function handleClickOutside(event: MouseEvent) {
      if (exportRef.current && !exportRef.current.contains(event.target as Node)) {
        setExportOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [exportOpen]);
  const isUser = message.role === "user";
  const sources = message.sources ?? [];
  const imageSources = useMemo(
    () => sources.filter(source => source.media_type === "image" || source.provider === "searxng_images" || Boolean(source.img_src)),
    [sources],
  );
  const textSources = useMemo(
    () => sources.filter(source => source.media_type !== "image" && source.provider !== "searxng_images" && !source.img_src),
    [sources],
  );
  const autoSearchReason = sources.find(source => source.auto_search_reason)?.auto_search_reason;
  const searchNotices = [...new Set(sources.flatMap(source => source.provider === "duckduckgo_instant_answers" && source.search_notice ? [source.search_notice] : []))];
  const exploredQueries = Array.from(new Set(textSources.map(item => item.query?.trim()).filter((item): item is string => Boolean(item))));
  const hasFinance = sources.some(source => source.provider === "yahoo_finance" || source.provider === "eodhd") ||
    message.attachments?.some(item => item.filename.startsWith("📈") || item.mime_type.includes("finance"));
  const financeSources = sources.filter(source => source.provider === "yahoo_finance" || source.provider === "eodhd");
  const financeProviders = [...new Set(financeSources.map(source => source.provider === "eodhd" ? "EOD Historical Data" : "Yahoo Finance"))];
  const financeSymbols = [...new Set(financeSources.map(source => /\(([^()]+)\)\s*$/.exec(source.title ?? "")?.[1]).filter((item): item is string => Boolean(item)))];
  const isLearnResult = Boolean(message.learn_report_id);
  const isDeepSearchResult = !isLearnResult && (exploredQueries.length > 0 || textSources.length > 5);
  const hasInteractiveModules = !isUser && (isLearnResult || hasInteractiveLearnModules(message.content));
  const rawDisplayContent = hasInteractiveModules ? stripInteractiveModulesForBody(message.content) : message.content;
  const parsed = useMemo(() => extractThoughtAndContent(rawDisplayContent), [rawDisplayContent]);
  const effectiveThought = message.thought || parsed.thought;
  const mainContent = parsed.cleanContent;
  const displayContent = streaming ? mainContent.replace(/!\[[^\]]*\]\([^)]*$/, "") : mainContent;
  const visibleSources = showAllSources ? textSources : textSources.slice(0, 8);
  const explicitCanvasFiles = useMemo(
    () => (isUser ? [] : extractCanvasFiles(displayContent, { isStreaming: streaming, includeUnnamed: false })),
    [isUser, displayContent, streaming],
  );
  const fallbackCanvasFiles = useMemo(
    () => (isUser || explicitCanvasFiles.length > 0 ? [] : extractCanvasFiles(displayContent, { isStreaming: streaming, includeUnnamed: true })),
    [isUser, explicitCanvasFiles.length, displayContent, streaming],
  );
  const canvasFiles = explicitCanvasFiles.length > 0 ? explicitCanvasFiles : fallbackCanvasFiles;
  const isExplicitCanvas = explicitCanvasFiles.length > 0;
  async function copy() {
    try {
      await navigator.clipboard.writeText(displayContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { setCopied(false); }
  }

  function downloadMessageZip() {
    if (!canvasFiles.length) return;
    const blob = createZipBlob(canvasFiles.map(file => ({ path: file.path, content: file.content })));
    triggerBlobDownload(blob, "projet-canvas.zip");
    setZipDownloaded(true);
    setTimeout(() => setZipDownloaded(false), 2000);
  }

  function renderNodeWithMentions(node: ReactNode): ReactNode {
    if (typeof node === "string") {
      const parts = node.split(/(@[a-zA-Z0-9_\u00C0-\u017F-]+)/g);
      if (parts.length <= 1) return node;
      return parts.map((part, index) => {
        if (part.startsWith("@") && part.length > 1) {
          return <span key={index} className="mention-pill">{part}</span>;
        }
        return part;
      });
    }
    if (Array.isArray(node)) {
      return node.map((child, i) => <span key={i}>{renderNodeWithMentions(child)}</span>);
    }
    return node;
  }

  return <article className={`message ${isUser ? "from-user" : "from-assistant"}`} aria-label={isUser ? "Votre message" : "Réponse de l’assistant"}>
    {!isUser && <div className="message-author"><BrandMark small /><span>cLAIr</span>{isDeepSearchResult && !streaming && <span className="deepsearch-badge"><Compass size={11} />DeepSearch</span>}{isExplicitCanvas && <span className="codecanvas-badge"><Code2 size={11} />Canvas Code</span>}{hasFinance && <span className="finance-badge" title="Cours et données financières téléchargés en direct"><TrendingUp size={11} />Finances & Bourse</span>}{streaming && <span className="streaming-label">en train d’écrire</span>}</div>}
    {!isUser && (researchActivity || message.deep_search_report_id) && <button type="button" className="tool-button" onClick={() => onOpenResearchActivity?.(message.id)}><Compass size={14} />{researchActivity?.state === "running" ? "Voir l’activité en direct" : "Voir l’activité DeepSearch"}</button>}
    {!isUser && financeSources.length > 0 && <div className="finance-live-banner" role="note" aria-label="Données financières téléchargées en direct">
      <span className="finance-live-icon"><TrendingUp size={18} /></span>
      <div className="finance-live-text">
        <strong>Données boursières en direct</strong>
        <small>{financeSymbols.length ? `${financeSymbols.join(" · ")} — ` : ""}téléchargées via l’API {financeProviders.join(" + ")}</small>
      </div>
      <div className="finance-live-providers">
        {financeProviders.map(name => <span key={name} className={`finance-live-pill ${name.startsWith("EOD") ? "is-eod" : "is-yahoo"}`}>{name}</span>)}
        {onOpenFinanceModal && (
          <button
            type="button"
            className="finance-live-modal-trigger"
            onClick={() => onOpenFinanceModal(financeSymbols[0] || "")}
            title="Ouvrir la modale interactive avec courbe de cours EOD et tableaux financiers Yahoo"
          >
            <LineChart size={13} />
            <span>Courbe & Tableaux</span>
          </button>
        )}
      </div>
    </div>}
    {!isUser && effectiveThought ? (
      <ThoughtAccordion thought={effectiveThought} isStreaming={streaming && !displayContent.trim()} />
    ) : null}
    {displayContent ? <div className={`markdown ${streaming ? "is-streaming" : ""}`}><ReactMarkdown urlTransform={url => url} remarkPlugins={markdownRemarkPlugins} rehypePlugins={markdownRehypePlugins} components={{
      p: ({ children }) => <p>{isUser ? renderNodeWithMentions(children) : children}</p>,
      a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
      img: ({ src, alt }) => (
        <MarkdownInlineImage
          src={typeof src === "string" ? src : undefined}
          alt={alt}
          imageSources={imageSources}
          onOpenLightbox={setLightboxImage}
        />
      ),
      pre: ({ children }) => <div className="code-block"><div className="code-label"><span>Code</span>{onOpenCanvas && canvasFiles.length > 0 && <button type="button" className="code-open-canvas" onClick={() => onOpenCanvas(message.id, canvasFiles[0]?.path, !isExplicitCanvas)}><Code2 size={11} />Ouvrir dans le Canvas</button>}</div><pre>{children}</pre></div>,
      table: ({ children }) => <div className="table-scroll"><table>{children}</table></div>,
    }}>{normalizeMathMarkdown(displayContent)}</ReactMarkdown></div> : streaming && !effectiveThought ? <div className="thinking-dots" aria-label="Réponse en cours"><i /><i /><i /></div> : null}
    {hasInteractiveModules && (
      <div className="chat-learn-interactive-banner" role="region" aria-label="Auto-évaluation et révision active">
        <div className="chat-learn-banner-icon">
          <GraduationCap size={20} />
        </div>
        <div className="chat-learn-banner-body">
          <strong>20 Flashcards 3D & Quizz (20 QCM) interactifs prêts</strong>
          <p>
            Les cartes de mémorisation active et les questions d&apos;auto-évaluation sont intégrées au cours interactif pour vous entraîner sans dévoiler les réponses dans le tchat.
          </p>
        </div>
        {onOpenLearnReport && (
          <button
            type="button"
            className="chat-learn-banner-btn"
            onClick={() => onOpenLearnReport(message)}
            title="Consulter le cours avec les Flashcards 3D et le Quizz interactif"
          >
            <Sparkles size={14} />
            <span>Tester mes connaissances</span>
          </button>
        )}
      </div>
    )}
    {!isUser && canvasFiles.length > 0 && <div className="message-canvas-card" role="region" aria-label="Projet Canvas généré">
      <div className="message-canvas-card-header">
        <div className="message-canvas-card-title">
          <span className="message-canvas-icon"><Code2 size={16} /></span>
          <div>
            <strong>{isExplicitCanvas ? "Projet Canvas multi-fichiers" : "Code prêt pour le Canvas"}</strong>
            <small>{canvasFiles.length} fichier{canvasFiles.length > 1 ? "s" : ""}{streaming ? " · Génération en direct…" : " · Éditable & exportable en .zip"}</small>
          </div>
        </div>
        <div className="message-canvas-card-actions">
          {onOpenCanvas && <button type="button" className="canvas-card-open-btn" onClick={() => onOpenCanvas(message.id, canvasFiles[0]?.path, !isExplicitCanvas)}><Code2 size={13} /><span>Ouvrir le Canvas</span></button>}
          <button type="button" className="canvas-card-zip-btn" onClick={downloadMessageZip}><FolderArchive size={13} /><span>{zipDownloaded ? "ZIP téléchargé" : "Télécharger .zip"}</span></button>
        </div>
      </div>
      <div className="message-canvas-files">
        {canvasFiles.map(file => <button key={file.path} type="button" className="message-canvas-file-pill" onClick={() => onOpenCanvas?.(message.id, file.path, !isExplicitCanvas)} title={`Ouvrir ${file.path} dans le Canvas`}><FileCode2 size={12} /><span>{file.path}</span>{file.streaming && <LoaderCircle size={11} className="spin" />}</button>)}
      </div>
    </div>}
    {!!message.attachments?.length && <div className="message-attachments">{message.attachments.map(item => <AttachmentView key={item.id} attachment={item} onOpenFinanceModal={onOpenFinanceModal} />)}</div>}
    {!!sources.length && <div className={`sources ${isLearnResult ? "sources-learn" : isDeepSearchResult ? "sources-deepsearch" : ""}`}>
      <div className="sources-header">
        <p>
          {isLearnResult ? (
            <><GraduationCap size={13} /> Cours structuré · {textSources.length || sources.length} supports didactiques{imageSources.length > 0 ? ` · ${imageSources.length} images web` : ""}</>
          ) : isDeepSearchResult ? (
            <><Compass size={13} /> Rapport DeepSearch · {textSources.length || sources.length} sources collectées{imageSources.length > 0 ? ` · ${imageSources.length} images web` : ""}</>
          ) : autoSearchReason ? (
            <><Globe2 size={13} /><span className="auto-badge">Auto</span> Recherche activée automatiquement ({textSources.length || sources.length}{imageSources.length > 0 ? ` + ${imageSources.length} images` : ""}) · <span className="auto-reason">{autoSearchReason}</span></>
          ) : (
            <><Globe2 size={13} /> Résultats de recherche & données ({textSources.length || sources.length}{imageSources.length > 0 ? ` · ${imageSources.length} images web` : ""})</>
          )}
        </p>
        <div className="sources-header-actions">
          {isLearnResult && (
            <div className="sources-report-buttons-group">
              <button
                type="button"
                className="sources-report-btn learn-sources-report-btn"
                onClick={() => onOpenLearnReport?.(message)}
                title="Consulter le cours complet dans le lecteur interactif ou en beau site HTML"
              >
                <GraduationCap size={12} />
                <span>Beau site HTML</span>
              </button>
              <a
                href={message.learn_report_id ? `/api/learn/reports/${message.learn_report_id}/html?pdf=1` : `/api/messages/${message.id}/html?pdf=1`}
                target="_blank"
                rel="noopener noreferrer"
                className="sources-report-btn sources-pdf-btn"
                title="Exporter ce cours au format Beau polycopié PDF (A4)"
              >
                <FileText size={12} />
                <span>Beau PDF</span>
              </a>
              <a
                href={message.learn_report_id ? `/api/learn/reports/${message.learn_report_id}/slides` : `/api/messages/${message.id}/slides?scope=turn`}
                target="_blank"
                rel="noopener noreferrer"
                className="sources-report-btn sources-slides-btn"
                title="Consulter ou présenter ce cours en diaporama type PowerPoint (16:9)"
                onClick={(e) => {
                  const base = message.learn_report_id ? `/api/learn/reports/${message.learn_report_id}/slides` : `/api/messages/${message.id}/slides?scope=turn`;
                  e.currentTarget.href = `${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`;
                }}
              >
                <Presentation size={12} />
                <span>Présentation PPT</span>
              </a>
              <a
                href={message.learn_report_id ? `/api/learn/reports/${message.learn_report_id}/html?download=1` : `/api/messages/${message.id}/html?download=1`}
                download
                className="sources-report-btn sources-download-btn"
                title="Télécharger directement le fichier HTML du cours"
              >
                <Download size={12} />
                <span>Télécharger HTML</span>
              </a>
            </div>
          )}
          {isDeepSearchResult && (
            <div className="sources-report-buttons-group">
              <button
                type="button"
                className="sources-report-btn"
                onClick={() => onOpenDeepSearchReport?.(message)}
                title="Consulter le grand rapport d'analyse dans le lecteur blog ou en beau site HTML"
              >
                <Globe2 size={12} />
                <span>Beau site HTML</span>
              </button>
              <a
                href={message.deep_search_report_id ? `/api/deep-search/reports/${message.deep_search_report_id}/html?pdf=1` : `/api/messages/${message.id}/html?pdf=1`}
                target="_blank"
                rel="noopener noreferrer"
                className="sources-report-btn sources-pdf-btn"
                title="Exporter ce grand rapport d'analyse au format Beau PDF (A4)"
              >
                <FileText size={12} />
                <span>Beau PDF</span>
              </a>
              <a
                href={message.deep_search_report_id ? `/api/deep-search/reports/${message.deep_search_report_id}/slides` : `/api/messages/${message.id}/slides?scope=turn`}
                target="_blank"
                rel="noopener noreferrer"
                className="sources-report-btn sources-slides-btn"
                title="Consulter ou présenter ce grand rapport en diaporama type PowerPoint (16:9)"
                onClick={(e) => {
                  const base = message.deep_search_report_id ? `/api/deep-search/reports/${message.deep_search_report_id}/slides` : `/api/messages/${message.id}/slides?scope=turn`;
                  e.currentTarget.href = `${base}${base.includes('?') ? '&' : '?'}t=${Date.now()}`;
                }}
              >
                <Presentation size={12} />
                <span>Présentation PPT</span>
              </a>
              <a
                href={message.deep_search_report_id ? `/api/deep-search/reports/${message.deep_search_report_id}/html?download=1` : `/api/messages/${message.id}/html?download=1`}
                download
                className="sources-report-btn sources-download-btn"
                title="Télécharger directement le fichier HTML du rapport"
              >
                <Download size={12} />
                <span>Télécharger HTML</span>
              </a>
            </div>
          )}
          {textSources.length > 8 && <button type="button" className="sources-toggle" onClick={() => setShowAllSources(old => !old)}>{showAllSources ? "Réduire" : `Voir les ${textSources.length} sources`}</button>}
        </div>
      </div>
      {imageSources.length > 0 && (
        <div className="sources-images-section" aria-label="Images web SearXNG associées">
          <div className="sources-images-label">
            <ImagePlus size={12} />
            <span>Images web trouvées via SearXNG ({imageSources.length})</span>
          </div>
          <div className="sources-images-strip">
            {imageSources.map((imgSource, idx) => (
              <SourceImageThumb
                key={`${imgSource.img_src || imgSource.url}-${idx}`}
                source={imgSource}
                onOpenLightbox={setLightboxImage}
              />
            ))}
          </div>
        </div>
      )}
      {exploredQueries.length > 0 && <div className="sources-queries" aria-label="Pistes explorées sur SearXNG">{exploredQueries.map(q => <span key={q} className="source-query-pill"><Search size={10} />{q}</span>)}</div>}
      {visibleSources.length > 0 && <div className="sources-links">{visibleSources.map((source, index) => <a key={`${source.url}-${index}`} href={source.url} target="_blank" rel="noreferrer" title={source.query ? `[Piste : ${source.query}]\n${source.snippet ?? ""}` : source.snippet}><span>{index + 1}</span><span>{source.title || safeHostname(source.url) || "Source"}</span>{source.provider === "yahoo_finance" ? <small className="source-provider source-provider-finance">Yahoo Finance</small> : source.provider === "eodhd" ? <small className="source-provider source-provider-finance">EOD Historical Data</small> : source.provider === "duckduckgo_instant_answers" ? <small className="source-provider">DuckDuckGo</small> : null}<ExternalLink size={12} /></a>)}</div>}
      {searchNotices.map(notice => <p className="source-notice" key={notice}><CircleAlert size={12} />{notice}</p>)}
      {sources.some(source => source.provider === "yahoo_finance") && <p className="source-attribution source-attribution-finance"><TrendingUp size={12} />Cours de bourse et états financiers téléchargés en direct sur <a href="https://finance.yahoo.com" target="_blank" rel="noreferrer">Yahoo Finance<ExternalLink size={10} /></a>.</p>}
      {sources.some(source => source.provider === "eodhd") && <p className="source-attribution source-attribution-finance"><TrendingUp size={12} />Cotations et historique téléchargés en direct via <a href="https://eodhd.com" target="_blank" rel="noreferrer">EOD Historical Data<ExternalLink size={10} /></a>.</p>}
      {sources.some(source => source.provider === "duckduckgo_instant_answers") && <p className="source-attribution">Réponses instantanées fournies par <a href="https://duckduckgo.com" target="_blank" rel="noreferrer">DuckDuckGo<ExternalLink size={10} /></a>.</p>}
    </div>}
    {lightboxImage && (
      <div
        className="web-image-lightbox-backdrop"
        role="dialog"
        aria-modal="true"
        aria-label={lightboxImage.title}
        onClick={() => setLightboxImage(null)}
      >
        <div className="web-image-lightbox-card" onClick={e => e.stopPropagation()}>
          <div className="web-image-lightbox-header">
            <div className="web-image-lightbox-title-wrap">
              <strong>{lightboxImage.title}</strong>
              <div className="web-image-lightbox-badges">
                {lightboxImage.domain && <span className="web-image-lightbox-domain">{lightboxImage.domain}</span>}
                {lightboxImage.resolution && <span className="web-image-lightbox-res">{lightboxImage.resolution}</span>}
              </div>
            </div>
            <div className="web-image-lightbox-actions">
              {lightboxImage.pageUrl && (
                <a
                  href={lightboxImage.pageUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="web-image-lightbox-source-btn"
                >
                  <Globe2 size={13} />
                  <span>Voir la page source</span>
                  <ExternalLink size={12} />
                </a>
              )}
              <button
                type="button"
                className="web-image-lightbox-close"
                onClick={() => setLightboxImage(null)}
                aria-label="Fermer l’aperçu"
              >
                <X size={18} />
              </button>
            </div>
          </div>
          <div className="web-image-lightbox-body">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={lightboxImage.src}
              alt={lightboxImage.title}
              onError={e => {
                const target = e.currentTarget;
                if (lightboxImage.fallbackSrc && target.src !== lightboxImage.fallbackSrc) {
                  target.src = lightboxImage.fallbackSrc;
                }
              }}
            />
          </div>
        </div>
      </div>
    )}
    {!isUser && message.content && !streaming && (
      <div className="message-actions">
        <button type="button" onClick={copy} aria-label={copied ? "Réponse copiée" : "Copier la réponse"}>
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Copié" : "Copier"}
        </button>
        <span className="message-action-separator" />
        <div className="message-export-wrapper" ref={exportRef}>
          <button
            type="button"
            className={`message-export-btn ${exportOpen ? "is-open" : ""}`}
            onClick={() => setExportOpen(prev => !prev)}
            aria-expanded={exportOpen}
            aria-label="Sortie du document : PDF ou HTML (Question & Réponse ou Synthèse des messages)"
            title="Sortie et export en HTML ou PDF"
          >
            <Share2 size={13} />
            <span>Sortie</span>
            <ChevronDown size={11} className={`export-chevron-icon ${exportOpen ? "is-rotated" : ""}`} />
          </button>

          {exportOpen && (
            <div className="message-export-popover" role="menu">
              <div className="message-export-popover-header">
                <span className="export-popover-title">
                  <Share2 size={13} />
                  <span>Sortie de document</span>
                </span>
                <span className="export-popover-tag">HTML · PDF · PPT</span>
              </div>

              {/* Option 1 : Question & Réponse */}
              <div className="message-export-item">
                <div className="export-item-desc">
                  <div className="export-item-title-row">
                    <span className="export-scope-tag scope-turn">Ce tour</span>
                    <strong>Question & Réponse</strong>
                  </div>
                  <p>Exporte la question posée et cette réponse détaillée.</p>
                </div>
                <div className="export-item-actions">
                  <a
                    href={`/api/messages/${message.id}/html?scope=turn`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="export-link-btn btn-html"
                    title="Consulter au format Beau site HTML interactif"
                    onClick={() => setExportOpen(false)}
                  >
                    <Globe2 size={12} />
                    <span>Site HTML</span>
                  </a>
                  <a
                    href={`/api/messages/${message.id}/html?scope=turn&pdf=1`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="export-link-btn btn-pdf"
                    title="Générer et imprimer le Beau document PDF d'édition (A4)"
                    onClick={() => setExportOpen(false)}
                  >
                    <FileText size={12} />
                    <span>Beau PDF</span>
                  </a>
                  <a
                    href={`/api/messages/${message.id}/slides?scope=turn`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="export-link-btn btn-slides"
                    title="Présentation type PowerPoint (diaporama interactif 16:9 et export PDF)"
                    onClick={(e) => {
                      e.currentTarget.href = `/api/messages/${message.id}/slides?scope=turn&t=${Date.now()}`;
                      setExportOpen(false);
                    }}
                  >
                    <Presentation size={12} />
                    <span>Présentation PPT</span>
                  </a>
                  <a
                    href={`/api/messages/${message.id}/html?scope=turn&download=1`}
                    download
                    className="export-link-btn btn-download-html"
                    title="Télécharger directement le fichier HTML de ce tour"
                    onClick={() => setExportOpen(false)}
                  >
                    <Download size={12} />
                    <span>Télécharger .html</span>
                  </a>
                </div>
              </div>

              <div className="export-popover-divider" />

              {/* Option 2 : Synthèse des messages */}
              <div className="message-export-item">
                <div className="export-item-desc">
                  <div className="export-item-title-row">
                    <span className="export-scope-tag scope-all">Discussion</span>
                    <strong>Synthèse des messages</strong>
                  </div>
                  <p>Exporte l’historique structuré et la synthèse de tous les échanges.</p>
                </div>
                <div className="export-item-actions">
                  <a
                    href={`/api/messages/${message.id}/html?scope=conversation`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="export-link-btn btn-html"
                    title="Consulter la synthèse complète en site HTML"
                    onClick={() => setExportOpen(false)}
                  >
                    <Globe2 size={12} />
                    <span>Site HTML</span>
                  </a>
                  <a
                    href={`/api/messages/${message.id}/html?scope=conversation&pdf=1`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="export-link-btn btn-pdf"
                    title="Générer et imprimer la synthèse au format PDF (A4)"
                    onClick={() => setExportOpen(false)}
                  >
                    <FileText size={12} />
                    <span>Beau PDF</span>
                  </a>
                  <a
                    href={`/api/messages/${message.id}/slides?scope=conversation`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="export-link-btn btn-slides"
                    title="Présentation type PowerPoint de l'ensemble de la discussion (diaporama 16:9)"
                    onClick={(e) => {
                      e.currentTarget.href = `/api/messages/${message.id}/slides?scope=conversation&t=${Date.now()}`;
                      setExportOpen(false);
                    }}
                  >
                    <Presentation size={12} />
                    <span>Présentation PPT</span>
                  </a>
                  <a
                    href={`/api/messages/${message.id}/html?scope=conversation&download=1`}
                    download
                    className="export-link-btn btn-download-html"
                    title="Télécharger directement la synthèse au format HTML"
                    onClick={() => setExportOpen(false)}
                  >
                    <Download size={12} />
                    <span>Télécharger .html</span>
                  </a>
                </div>
              </div>
            </div>
          )}
        </div>
        <span className="message-timestamp">
          {new Date(message.created_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    )}
  </article>;
}

export function ChatApp() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [authError, setAuthError] = useState("");
  const invitationToken = useSyncExternalStore(subscribeToLocation, getInvitationToken, () => "");
  const [adminOpen, setAdminOpen] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [streamingConversationIds, setStreamingConversationIds] = useState<string[]>([]);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [model, setModel] = useState("");
  const [modelModalOpen, setModelModalOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [webSearchMode, setWebSearchMode] = useState<"auto" | "always" | "off">("auto");
  const [deepSearch, setDeepSearch] = useState(false);
  const [deepSearchStageModels, setDeepSearchStageModels] = useState<StageModelsConfig>(() => {
    try {
      const stored = localStorage.getItem("clair_stage_models_deep_search");
      if (stored) return JSON.parse(stored);
    } catch {}
    return {
      plan_model: "google/gemini-4-argon",
      search_model: "google/gemini-3.8-flash",
      expert_model: "google/gemini-3.8-flash",
      synthesis_model: "google/gemini-3.8-flash",
      audit_model: "openai/gpt-6-astra",
    };
  });
  const [deepSearchModalOpen, setDeepSearchModalOpen] = useState(false);
  const [deepSearchModalQuestion, setDeepSearchModalQuestion] = useState("");
  const [deepSearchModalTab, setDeepSearchModalTab] = useState<"plan" | "reports">("plan");
  const [deepSearchModalReportId, setDeepSearchModalReportId] = useState<string | null>(null);
  const [learnMode, setLearnMode] = useState(false);
  const [learnModeStageModels, setLearnModeStageModels] = useState<StageModelsConfig>(() => {
    try {
      const stored = localStorage.getItem("clair_stage_models_learn_mode");
      if (stored) return JSON.parse(stored);
    } catch {}
    return {
      plan_model: "google/gemini-4-argon",
      search_model: "google/gemini-3.8-flash",
      expert_model: "google/gemini-3.8-flash",
      synthesis_model: "google/gemini-3.8-flash",
      audit_model: "openai/gpt-6-astra",
    };
  });
  const [learnModalOpen, setLearnModalOpen] = useState(false);
  const [learnModalQuestion, setLearnModalQuestion] = useState("");
  const [learnModalTab, setLearnModalTab] = useState<"plan" | "reports">("plan");
  const [learnModalReportId, setLearnModalReportId] = useState<string | null>(null);
  const [codeMode, setCodeMode] = useState(false);
  const [financeMode, setFinanceMode] = useState(false);
  const [financeModalOpen, setFinanceModalOpen] = useState(false);
  const [financeModalQuery, setFinanceModalQuery] = useState<string | null>(null);
  const [financeModalData, setFinanceModalData] = useState<FinancialDashboardData | null>(null);

  function openFinanceModal(queryOrSymbol?: string, directData?: FinancialDashboardData | null) {
    setFinanceModalQuery(queryOrSymbol || null);
    setFinanceModalData(directData || null);
    setFinanceModalOpen(true);
  }
  const [canvasOpen, setCanvasOpen] = useState(false);
  const [canvasMessageId, setCanvasMessageId] = useState<string | null>(null);
  const [canvasSelectedPath, setCanvasSelectedPath] = useState<string | null>(null);
  const [canvasIncludeUnnamed, setCanvasIncludeUnnamed] = useState(false);
  const [imageStudioOpen, setImageStudioOpen] = useState(false);
  const [imageStudioPrompt, setImageStudioPrompt] = useState("");
  const [soundStudioOpen, setSoundStudioOpen] = useState(false);
  const [soundStudioPrompt, setSoundStudioPrompt] = useState("");
  const [soundStudioInitialTab, setSoundStudioInitialTab] = useState<"effects" | "music" | "library">("effects");
  const [studyModalOpen, setStudyModalOpen] = useState(false);
  const [studyModalKind, setStudyModalKind] = useState<"flashcards" | "quiz">("flashcards");
  const [multiAgentActive, setMultiAgentActive] = useState(false);
  const [multiAgentConfig, setMultiAgentConfig] = useState<MultiAgentConfig | null>(null);
  const [showMultiAgentModal, setShowMultiAgentModal] = useState(false);
  const [blogModalOpen, setBlogModalOpen] = useState(false);
  const [blogModalSeedPrompt, setBlogModalSeedPrompt] = useState("");
  const [busy, setBusy] = useState<string | null>("init");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [researchRuns, setResearchRuns] = useState<Record<string, ResearchRun>>({});
  const [researchActivityMessageId, setResearchActivityMessageId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [groupMode, setGroupMode] = useState<"date" | "theme">("date");
  const [selectedKeyword, setSelectedKeyword] = useState("");
  const [selectedTheme, setSelectedTheme] = useState("");
  const [collapsedThemes, setCollapsedThemes] = useState<Record<string, boolean>>({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [contextTab, setContextTab] = useState<"summary" | "memories">("summary");
  const [memoryDraft, setMemoryDraft] = useState("");
  const [dialog, setDialog] = useState<{ type: "rename" | "delete"; conversation: Conversation } | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameTheme, setRenameTheme] = useState("");
  const [renameKeywords, setRenameKeywords] = useState("");
  const [showUrlModal, setShowUrlModal] = useState(false);
  const [urlInputValue, setUrlInputValue] = useState("");
  const [urlLoading, setUrlLoading] = useState(false);
  const [urlError, setUrlError] = useState("");
  const streamControllersRef = useRef<Map<string, AbortController>>(new Map());
  const streamingDeltasRef = useRef<Map<string, { assistantId: string; userMessage: Message; text: string; thought?: string; status: string }>>(new Map());
  const conversationIdRef = useRef<string | null>(null);
  conversationIdRef.current = conversation?.id ?? null;
  const docInputRef = useRef<HTMLInputElement>(null);
  const visionInputRef = useRef<HTMLInputElement>(null);
  const attachMenuRef = useRef<HTMLDivElement>(null);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [familyInfo, setFamilyInfo] = useState<FamilyGroupInfo | null>(null);
  const [familyModalOpen, setFamilyModalOpen] = useState(false);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement>(null);
  const [topbarExportOpen, setTopbarExportOpen] = useState(false);
  const topbarExportRef = useRef<HTMLDivElement>(null);
  const [memoryNotice, setMemoryNotice] = useState<string | null>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target as Node)) {
        setProfileMenuOpen(false);
      }
      if (topbarExportRef.current && !topbarExportRef.current.contains(event.target as Node)) {
        setTopbarExportOpen(false);
      }
      if (attachMenuRef.current && !attachMenuRef.current.contains(event.target as Node)) {
        setAttachMenuOpen(false);
      }
    }
    if (profileMenuOpen || topbarExportOpen || attachMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [profileMenuOpen, topbarExportOpen, attachMenuOpen]);

  async function loadFamily(signal?: AbortSignal) {
    try {
      const family = await api<FamilyGroupInfo>("/family", { signal });
      setFamilyInfo(family);
    } catch {
      // Ignorer si non disponible
    }
  }

  async function switchAccount(targetUserId: string) {
    setBusy("switch");
    setProfileMenuOpen(false);
    setError("");
    try {
      const newUser = await api<AuthUser>(`/family/switch/${targetUserId}`, { method: "POST" });
      setUser(newUser);
      setConversation(null);
      setConversations([]);
      setMemories([]);
      setSkills([]);
      setAttachments([]);
      setDraft("");
      await loadWorkspace();
      await loadFamily();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function loadWorkspace(signal?: AbortSignal) {
    const [settings, chats, savedMemories, userSkills] = await Promise.all([
      api<Config>("/config", { signal }),
      api<Conversation[]>("/conversations", { signal }),
      api<Memory[]>("/memories", { signal }),
      api<Skill[]>("/skills", { signal }).catch(() => [] as Skill[]),
    ]);
    setConfig(settings); setModel(settings.default_model); setConversations(chats); setMemories(savedMemories); setSkills(userSkills);
    void loadFamily(signal);
  }

  async function bootstrap(signal?: AbortSignal) {
    setBusy("init"); setError("");
    try {
      const current = await api<AuthUser>("/auth/session", { signal });
      setUser(current);
      await loadWorkspace(signal);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setUser(null);
      else setError(`Connexion au serveur impossible. ${errorMessage(err)}`);
    } finally { setBusy(null); setAuthReady(true); }
  }

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    api<AuthUser>("/auth/session", { signal: controller.signal })
      .then(async current => {
        if (!active) return;
        setUser(current);
        const [settings, chats, savedMemories, userSkills] = await Promise.all([
          api<Config>("/config", { signal: controller.signal }),
          api<Conversation[]>("/conversations", { signal: controller.signal }),
          api<Memory[]>("/memories", { signal: controller.signal }),
          api<Skill[]>("/skills", { signal: controller.signal }).catch(() => [] as Skill[]),
        ]);
        if (!active) return;
        setConfig(settings); setModel(settings.default_model); setConversations(chats); setMemories(savedMemories); setSkills(userSkills);
        void loadFamily(controller.signal);
      }).catch(err => {
        if (!active || (err instanceof ApiError && err.status === 401)) return;
        setAuthError(`Connexion au serveur impossible. ${errorMessage(err)}`);
      }).finally(() => { if (active) { setAuthReady(true); setBusy(null); } });
    return () => {
      active = false;
      controller.abort();
      streamControllersRef.current.forEach(c => c.abort());
    };
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) { textarea.style.height = "auto"; textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`; }
  }, [draft]);

  useEffect(() => {
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    const focusTarget = document.querySelector<HTMLElement>(dialog.type === "rename" ? "#rename-input" : ".modal .secondary-button");
    focusTarget?.focus();
    return () => previous?.focus();
  }, [dialog]);

  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ behavior: streamingId ? "instant" : "smooth", block: "end" });
  }, [conversation?.messages, atBottom, streamingId, status]);

  const messages = useMemo(() => conversation?.messages ?? [], [conversation?.messages]);
  const researchActivityMessage = messages.find(message => message.id === researchActivityMessageId);
  const isCurrentStreaming = Boolean(conversation?.id && streamingConversationIds.includes(conversation.id));
  const working = busy !== null && busy !== "send";
  const sending = isCurrentStreaming || busy === "send";
  const needsVision = attachments.some(file => file.mime_type.startsWith("image/") && !file.has_extraction) && !config?.demo_mode && !config?.models.find(item => item.id === model)?.vision;
  const canSend = !!config && !working && !isCurrentStreaming && config.features.chat && !needsVision && (!!draft.trim() || attachments.length > 0);

  const currentModelInfo = useMemo(() => config?.models.find(item => item.id === model), [config?.models, model]);
  const currentModelPriceTag = useMemo(() => {
    if (!currentModelInfo) return null;
    if (currentModelInfo.prompt_price_1m === 0) return "Gratuit";
    if (currentModelInfo.prompt_price_1m !== undefined) {
      const val = currentModelInfo.prompt_price_1m;
      return val < 0.01 ? "<$0.01/M" : val < 1 ? `$${val.toFixed(2)}/M` : `$${val.toFixed(1)}/M`;
    }
    return null;
  }, [currentModelInfo]);

  async function refreshModels() {
    try {
      const res = await api<{ models: Model[]; default_model: string }>("/models?refresh=true");
      if (res?.models) {
        setConfig(old => old ? { ...old, models: res.models } : old);
      }
    } catch {
      const newConfig = await api<Config>("/config");
      setConfig(newConfig);
    }
  }

  const filteredMentionSkills = useMemo(() => {
    if (mentionQuery === null) return [];
    const q = mentionQuery.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return skills.filter(skill => {
      if (!q) return true;
      const slug = skillToSlug(skill.name);
      const nameNorm = skill.name.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
      const words = nameNorm.split(/[^a-z0-9]+/).filter(Boolean);
      return (
        slug.includes(q) ||
        nameNorm.includes(q) ||
        words.some(w => w.startsWith(q))
      );
    }).slice(0, 8);
  }, [skills, mentionQuery]);

  function findMentionQuery(text: string, cursorPos: number): { query: string; start: number; end: number } | null {
    const before = text.slice(0, cursorPos);
    const match = before.match(/(?:^|\s)@([a-zA-Z0-9_\u00C0-\u017F-]*)$/);
    if (!match) return null;
    const query = match[1];
    const atPos = before.lastIndexOf("@");
    return { query, start: atPos, end: cursorPos };
  }

  function skillMatchesTag(skill: Skill, tag: string): boolean {
    const cleanTag = tag.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    const slug = skillToSlug(skill.name);
    const nameNorm = skill.name.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    const words = nameNorm.split(/[^a-z0-9]+/).filter(Boolean);
    return (
      slug === cleanTag ||
      slug.startsWith(cleanTag) ||
      words.some(w => w.startsWith(cleanTag) || cleanTag.startsWith(w)) ||
      (cleanTag.length >= 3 && slug.includes(cleanTag))
    );
  }

  function extractMentionedSkillIds(text: string, allSkills: Skill[]): string[] {
    const matches = Array.from(text.matchAll(/@([a-zA-Z0-9_\u00C0-\u017F-]+)/g));
    if (!matches.length || !allSkills.length) return [];
    const matchedIds = new Set<string>();
    for (const match of matches) {
      const tag = match[1];
      for (const skill of allSkills) {
        if (skillMatchesTag(skill, tag)) {
          matchedIds.add(skill.id);
        }
      }
    }
    return Array.from(matchedIds);
  }

  function insertMention(skill: Skill) {
    const textarea = textareaRef.current;
    const cursorPos = textarea?.selectionStart ?? draft.length;
    const mention = findMentionQuery(draft, cursorPos);
    const slug = skillToSlug(skill.name);
    const insertText = `@${slug} `;
    if (mention) {
      const before = draft.slice(0, mention.start);
      const after = draft.slice(mention.end);
      const nextVal = `${before}${insertText}${after}`;
      setDraft(nextVal);
      setMentionQuery(null);
      setTimeout(() => {
        if (textareaRef.current) {
          const newPos = before.length + insertText.length;
          textareaRef.current.focus();
          textareaRef.current.setSelectionRange(newPos, newPos);
        }
      }, 0);
    }
  }

  function stopCurrentStream() {
    if (conversation?.id) {
      const controller = streamControllersRef.current.get(conversation.id);
      controller?.abort();
    }
  }
  const isWebSearchAvailable = Boolean(config?.features.web_search);
  const effectiveWebMode = isWebSearchAvailable ? webSearchMode : "off";
  const searchProviders = config?.search_providers ?? (config?.features.web_search ? ["searxng", "brave"] : []);
  const hasPrimarySearch = searchProviders.includes("searxng") || searchProviders.includes("brave");
  const hasDuckDuckGo = searchProviders.includes("duckduckgo_instant_answers");
  const duckDuckGoOnly = hasDuckDuckGo && !hasPrimarySearch;
  const showDuckDuckGoNotice = duckDuckGoOnly && (effectiveWebMode !== "off" || deepSearch) && isWebSearchAvailable;
  const webSearchTooltip = !isWebSearchAvailable
    ? "Configurez SearXNG, une clé Brave ou activez DuckDuckGo côté serveur (DUCKDUCKGO_ENABLED=true) pour utiliser la recherche."
    : effectiveWebMode === "auto"
      ? "Mode Web Auto : un agent ultra-rapide (Mistral Small / Gemini Flash Lite) décide automatiquement si votre message nécessite une recherche web (actualités, prix, offres, santé/droit, versions...). Cliquez pour forcer."
      : effectiveWebMode === "always"
        ? "Mode Web Forcé : recherche web systématique à chaque message. Cliquez pour désactiver."
        : "Mode Web Désactivé : aucune recherche web. Cliquez pour réactiver le mode Auto.";

  const availableThemes = useMemo(() => {
    const base = config?.themes?.length ? config.themes : DEFAULT_THEMES;
    const extra = conversations
      .map(item => item.theme?.trim())
      .filter((t): t is string => typeof t === "string" && t.length > 0 && !base.includes(t));
    return Array.from(new Set([...base, ...extra]));
  }, [config?.themes, conversations]);

  const topKeywords = useMemo(() => {
    const counts = new Map<string, { label: string; count: number }>();
    for (const item of conversations) {
      for (const rawKw of item.keywords ?? []) {
        const clean = rawKw.trim().replace(/^#+/, "");
        if (!clean) continue;
        const key = clean.toLocaleLowerCase("fr");
        const existing = counts.get(key);
        if (existing) existing.count += 1;
        else counts.set(key, { label: clean, count: 1 });
      }
    }
    return Array.from(counts.values())
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "fr"))
      .slice(0, 14);
  }, [conversations]);

  const filteredConversations = useMemo(() => {
    const cleanQuery = query.trim().replace(/^#+/, "").toLocaleLowerCase("fr");
    const cleanKeyword = selectedKeyword.trim().replace(/^#+/, "").toLocaleLowerCase("fr");
    const cleanTheme = selectedTheme.trim().toLocaleLowerCase("fr");
    return conversations.filter(item => {
      const itemTheme = (item.theme?.trim() || "Général");
      const itemKeywords = item.keywords ?? [];
      if (cleanTheme && itemTheme.toLocaleLowerCase("fr") !== cleanTheme) return false;
      if (cleanKeyword && !itemKeywords.some(kw => kw.toLocaleLowerCase("fr") === cleanKeyword)) return false;
      if (!cleanQuery) return true;
      const inTitle = item.title.toLocaleLowerCase("fr").includes(cleanQuery);
      const inKeywords = itemKeywords.some(kw => kw.toLocaleLowerCase("fr").includes(cleanQuery));
      const inTheme = itemTheme.toLocaleLowerCase("fr").includes(cleanQuery);
      const inSummary = (item.summary ?? "").toLocaleLowerCase("fr").includes(cleanQuery);
      return inTitle || inKeywords || inTheme || inSummary;
    });
  }, [conversations, query, selectedKeyword, selectedTheme]);

  const groups = useMemo(() => {
    if (groupMode === "theme") {
      const byTheme = new Map<string, Conversation[]>();
      for (const item of filteredConversations) {
        const label = item.theme?.trim() || "Général";
        const list = byTheme.get(label) ?? [];
        list.push(item);
        byTheme.set(label, list);
      }
      const order = availableThemes;
      return Array.from(byTheme.entries())
        .map(([label, items]) => ({ label, items }))
        .sort((a, b) => {
          if (a.label === "Général" && b.label !== "Général") return 1;
          if (b.label === "Général" && a.label !== "Général") return -1;
          const idxA = order.indexOf(a.label);
          const idxB = order.indexOf(b.label);
          if (idxA !== -1 && idxB !== -1) return idxA - idxB;
          return b.items.length - a.items.length || a.label.localeCompare(b.label, "fr");
        });
    }
    return ["Aujourd’hui", "Ces 7 derniers jours", "Plus tôt"]
      .map(label => ({ label, items: filteredConversations.filter(item => dateGroup(item.updated_at) === label) }))
      .filter(group => group.items.length > 0);
  }, [groupMode, filteredConversations, availableThemes]);

  const hasActiveFilter = Boolean(query.trim() || selectedKeyword || selectedTheme);

  const canvasFiles = useMemo(
    () => collectConversationCanvasFiles(messages, canvasMessageId, streamingId, codeMode || canvasIncludeUnnamed),
    [messages, canvasMessageId, streamingId, codeMode, canvasIncludeUnnamed],
  );

  function openCanvasForMessage(messageId: string, filePath?: string, forceUnnamed = false) {
    setCanvasMessageId(messageId);
    setCanvasIncludeUnnamed(forceUnnamed);
    if (filePath) setCanvasSelectedPath(filePath);
    setContextOpen(false);
    setSkillsOpen(false);
    setCanvasOpen(true);
  }

  function toggleCodeMode() {
    setCodeMode(old => {
      const next = !old;
      if (next) {
        setCanvasMessageId(null);
        setContextOpen(false);
        setSkillsOpen(false);
        setCanvasOpen(true);
      }
      return next;
    });
  }

  function openImageStudio(seedPrompt = "") {
    setImageStudioPrompt(seedPrompt);
    setImageStudioOpen(true);
    setSidebarOpen(false);
  }

  function openSoundStudio(seedPrompt = "", tab: "effects" | "music" | "library" = "effects") {
    setSoundStudioPrompt(seedPrompt);
    setSoundStudioInitialTab(tab);
    setSoundStudioOpen(true);
    setSidebarOpen(false);
  }

  function openStudyModal(initialKind: "flashcards" | "quiz" = "flashcards") {
    setStudyModalKind(initialKind);
    setStudyModalOpen(true);
    setSidebarOpen(false);
  }

  function openBlogModal(seedPrompt = "") {
    setBlogModalSeedPrompt(seedPrompt);
    setBlogModalOpen(true);
    setSidebarOpen(false);
  }

  async function refreshConversations() { setConversations(await api<Conversation[]>("/conversations")); }

  async function discardUploads(files: Attachment[]) {
    const results = await Promise.allSettled(files.map(file => api(`/attachments/${file.id}`, { method: "DELETE" })));
    return results.some(result => result.status === "rejected") ? "Certains fichiers du brouillon n’ont pas pu être supprimés du serveur." : "";
  }

  async function removeAttachment(id: string) {
    if (working) return;
    setBusy("upload-delete"); setError("");
    try {
      await api(`/attachments/${id}`, { method: "DELETE" });
      setAttachments(old => old.filter(file => file.id !== id));
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function openConversation(id: string) {
    setResearchActivityMessageId(null);
    if (busy === "switch") return;
    setBusy("switch"); setError(""); setSidebarOpen(false);
    try {
      const loaded = await api<Conversation>(`/conversations/${id}`);
      const warning = await discardUploads(attachments);
      const inProgress = streamingDeltasRef.current.get(id);
      if (inProgress && inProgress.assistantId) {
        const empty: Message = { id: inProgress.assistantId, role: "assistant", content: inProgress.text, thought: inProgress.thought, created_at: new Date().toISOString(), attachments: [], sources: [] };
        loaded.messages = [...(loaded.messages ?? []), empty];
        setStreamingId(inProgress.assistantId);
        setStatus(inProgress.status);
      } else {
        setStreamingId(null);
        setStatus("");
      }
      const hasCanvas = (loaded.messages ?? []).some(msg => msg.role === "assistant" && hasExplicitCanvasFiles(msg.content));
      setConversation(loaded); setModel(loaded.model); setDraft(""); setAttachments([]); setAtBottom(true);
      setCanvasMessageId(null); setCanvasSelectedPath(null); setCanvasIncludeUnnamed(false);
      if (hasCanvas) { setContextOpen(false); setCanvasOpen(true); }
      if (warning) setError(warning);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function newConversation() {
    setResearchActivityMessageId(null);
    if (busy === "cleanup" || busy === "switch") return;
    setBusy("cleanup");
    const warning = await discardUploads(attachments);
    setConversation(null); setDraft(""); setAttachments([]); setModel(config?.default_model ?? ""); setError(""); setSidebarOpen(false); setAtBottom(true);
    setCanvasMessageId(null); setCanvasSelectedPath(null); setCanvasIncludeUnnamed(false);
    setStreamingId(null); setStatus("");
    if (!codeMode) setCanvasOpen(false);
    if (warning) setError(warning);
    setBusy(null);
    textareaRef.current?.focus();
  }

  async function changeModel(value: string) {
    if (working) return;
    const previous = model;
    setModel(value);
    if (!conversation) return;
    setBusy("model"); setError("");
    try {
      const updated = await api<Conversation>(`/conversations/${conversation.id}`, { method: "PATCH", body: JSON.stringify({ model: value }) });
      setConversation(old => old ? { ...old, ...updated, messages: updated.messages ?? old.messages } : updated);
      await refreshConversations();
    } catch (err) { setModel(previous); setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function uploadFiles(files: FileList | null, mode: "ocr" | "vision" = "ocr") {
    if (!files?.length || working) return;
    const incoming = Array.from(files);
    const imageCount = attachments.filter(file => file.mime_type.startsWith("image/")).length + incoming.filter(file => file.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(file.name)).length;
    if (incoming.length + attachments.length > 5 || imageCount > 4) {
      setError("Un message peut contenir au maximum 5 pièces jointes, dont 4 images. Retirez des fichiers avant d’en ajouter.");
      if (docInputRef.current) docInputRef.current.value = "";
      if (visionInputRef.current) visionInputRef.current.value = "";
      return;
    }
    setBusy("upload"); setError("");
    const uploaded: Attachment[] = [];
    try {
      for (const file of incoming) {
        if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} dépasse la limite de 20 Mo par fichier.`);
        if ((file.type.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(file.name)) && file.size > 8 * 1024 * 1024) throw new Error(`${file.name} dépasse la limite de 8 Mo par image.`);
        setStatus(`Importation et analyse ${mode === "vision" ? "visuelle (Vision IA)" : "documentaire (Mistral OCR)"} de ${file.name}…`);
        const body = new FormData();
        body.append("file", file);
        body.append("mode", mode);
        uploaded.push(await api<Attachment>("/attachments", { method: "POST", body }));
      }
    } catch (err) { setError(errorMessage(err)); }
    finally {
      setAttachments(old => [...old, ...uploaded]); setBusy(null); setStatus("");
      if (docInputRef.current) docInputRef.current.value = "";
      if (visionInputRef.current) visionInputRef.current.value = "";
    }
  }

  async function handleAttachUrl(event?: FormEvent) {
    event?.preventDefault();
    const clean = urlInputValue.trim();
    if (!clean) return;
    if (!/^https?:\/\//i.test(clean)) {
      setUrlError("Veuillez saisir une adresse web valide commençant par http:// ou https://");
      return;
    }
    if (attachments.length >= 5) {
      setUrlError("Un message peut contenir au maximum 5 pièces jointes. Retirez des fichiers avant d’en ajouter.");
      return;
    }
    setUrlLoading(true);
    setUrlError("");
    try {
      const attached = await attachUrl(clean);
      setAttachments(old => [...old, attached]);
      setUrlInputValue("");
      setShowUrlModal(false);
    } catch (err) {
      setUrlError(errorMessage(err));
    } finally {
      setUrlLoading(false);
    }
  }

  async function handleOpenDeepSearchReport(msg: Message) {
    if (msg.deep_search_report_id) {
      setDeepSearchModalQuestion("");
      setDeepSearchModalTab("reports");
      setDeepSearchModalReportId(msg.deep_search_report_id);
      setDeepSearchModalOpen(true);
      return;
    }
    try {
      const rep = await createReportFromMessage(msg.id);
      msg.deep_search_report_id = rep.id;
      setDeepSearchModalQuestion("");
      setDeepSearchModalTab("reports");
      setDeepSearchModalReportId(rep.id);
      setDeepSearchModalOpen(true);
    } catch (err) {
      console.error("Erreur génération rapport:", err);
      setDeepSearchModalQuestion("");
      setDeepSearchModalTab("reports");
      setDeepSearchModalReportId(null);
      setDeepSearchModalOpen(true);
    }
  }

  async function handleOpenLearnReport(msg: Message) {
    if (msg.learn_report_id) {
      setLearnModalQuestion("");
      setLearnModalTab("reports");
      setLearnModalReportId(msg.learn_report_id);
      setLearnModalOpen(true);
      return;
    }
    try {
      const rep = await createLearnReportFromMessage(msg.id);
      msg.learn_report_id = rep.id;
      setLearnModalQuestion("");
      setLearnModalTab("reports");
      setLearnModalReportId(rep.id);
      setLearnModalOpen(true);
    } catch (err) {
      console.error("Erreur génération cours:", err);
      setLearnModalQuestion("");
      setLearnModalTab("reports");
      setLearnModalReportId(null);
      setLearnModalOpen(true);
    }
  }

  function appendResearchActivity(messageId: string, event: ResearchActivity) {
    setResearchRuns(old => {
      const run = old[messageId];
      if (!run || run.state !== "running") return old;
      return { ...old, [messageId]: { ...run, events: [...run.events, event].slice(-600) } };
    });
  }

  async function send(
    event?: FormEvent,
    customDeepSearchQueries?: string[],
    customLearnQueries?: string[],
    customDetailLevel?: number,
    customStageModels?: StageModelsConfig,
    customModel?: string,
    interactionId?: string,
    planFeedback?: string,
  ) {
    event?.preventDefault();
    if (!config) return;

    let text = (
      draft.trim()
      || (customDeepSearchQueries ? deepSearchModalQuestion : "")
      || (customLearnQueries ? learnModalQuestion : "")
    ).trim();
    if (customDeepSearchQueries && !text && customDeepSearchQueries.length > 0) {
      text = customDeepSearchQueries[0].trim();
    }
    if (customLearnQueries && !text && customLearnQueries.length > 0) {
      text = customLearnQueries[0].trim();
    }
    if (isCurrentStreaming) {
      if (customDeepSearchQueries || customLearnQueries) {
        stopCurrentStream();
        await new Promise((r) => setTimeout(r, 120));
      } else {
        return;
      }
    }
    if (working) {
      if (customDeepSearchQueries || customLearnQueries) {
        throw new Error("Une opération est déjà en cours. Veuillez patienter un instant avant de lancer.");
      }
      return;
    }
    if (!config.features.chat) return;
    if (needsVision) {
      if (customDeepSearchQueries || customLearnQueries) {
        throw new Error("Le modèle sélectionné ne prend pas en charge les images jointes.");
      }
      return;
    }
    if (!text && attachments.length === 0) return;

    const useDeepSearch = deepSearch && config.features.web_search;
    if (useDeepSearch && !customDeepSearchQueries) {
      setDeepSearchModalQuestion(text);
      setDeepSearchModalTab("plan");
      setDeepSearchModalReportId(null);
      setDeepSearchModalOpen(true);
      return;
    }

    const useLearnMode = learnMode && config.features.web_search;
    if (useLearnMode && !customLearnQueries) {
      setLearnModalQuestion(text);
      setLearnModalTab("plan");
      setLearnModalReportId(null);
      setLearnModalOpen(true);
      return;
    }

    const files = attachments;
    const messageSkillIds = extractMentionedSkillIds(text, skills);
    const controller = new AbortController();
    setBusy("send"); setError(""); setStatus("Connexion au modèle…"); setDraft(""); setAttachments([]); setAtBottom(true);
    setMentionQuery(null);
    let activeId = conversation?.id;
    let persisted = false;
    let assistantId = "";
    try {
      if (!activeId) {
        const created = await api<Conversation>("/conversations", { method: "POST", body: JSON.stringify({ model }), signal: controller.signal });
        activeId = created.id;
        conversationIdRef.current = activeId;
        setConversation({ ...created, messages: created.messages ?? [] });
      }
      streamControllersRef.current.set(activeId, controller);
      setStreamingConversationIds(old => (old.includes(activeId!) ? old : [...old, activeId!]));

      const isAutoWeb = !useDeepSearch && !useLearnMode && effectiveWebMode === "auto";
      const isAlwaysWeb = !useDeepSearch && !useLearnMode && effectiveWebMode === "always";
      const useCodeMode = codeMode;
      if (useCodeMode) {
        setCanvasMessageId(null);
        setContextOpen(false);
        setSkillsOpen(false);
        setCanvasOpen(true);
      }
      let accumulatedText = "";
      await streamMessage(
        activeId,
        {
          content: text,
          model: customModel || model,
          web_search: isAlwaysWeb,
          auto_web_search: isAutoWeb,
          web_search_mode: effectiveWebMode,
          deep_search: useDeepSearch,
          deep_search_queries: customDeepSearchQueries,
          learn_mode: useLearnMode,
          learn_mode_queries: customLearnQueries,
          detail_level: customDetailLevel,
          stage_models: customStageModels || (useLearnMode ? learnModeStageModels : undefined),
          code_mode: useCodeMode,
          finance_mode: financeMode,
          multi_agent: multiAgentActive,
          multi_agent_config: multiAgentActive && multiAgentConfig ? multiAgentConfig : undefined,
          attachment_ids: files.map(item => item.id),
          skill_ids: messageSkillIds,
          interaction_id: interactionId,
          plan_feedback: planFeedback,
        },
        controller.signal,
        event => {
          if (event.type === "meta") {
            persisted = true; assistantId = event.data.assistant_message_id;
            if (useDeepSearch) setResearchRuns(old => ({ ...old, [assistantId]: { events: [], state: "running" } }));
            const empty: Message = { id: assistantId, role: "assistant", content: "", created_at: new Date().toISOString(), attachments: [], sources: [] };
            streamingDeltasRef.current.set(activeId!, {
              assistantId,
              userMessage: event.data.user_message,
              text: "",
              thought: "",
              status: useCodeMode ? "Canvas Code · Architecture du projet…" : "Le modèle réfléchit…",
            });
            if (conversationIdRef.current === activeId) {
              setStreamingId(assistantId);
              if (useCodeMode) setCanvasMessageId(assistantId);
              setConversation(old => (old && old.id === activeId ? { ...old, messages: [...(old.messages ?? []), event.data.user_message, empty] } : old));
              setStatus(useCodeMode ? "Canvas Code · Architecture du projet…" : "Le modèle réfléchit…");
            }
          } else if (event.type === "status") {
            if (useDeepSearch) appendResearchActivity(assistantId, { kind: "stage", timestamp: new Date().toISOString(), message: event.data.message });
            const inProgress = streamingDeltasRef.current.get(activeId!);
            if (inProgress) inProgress.status = event.data.message;
            if (conversationIdRef.current === activeId) setStatus(event.data.message);
          } else if (event.type === "thought") {
            const inProgress = streamingDeltasRef.current.get(activeId!);
            if (inProgress) {
              inProgress.thought = (inProgress.thought || "") + event.data.text;
            }
            if (conversationIdRef.current === activeId) {
              setConversation(old => (old && old.id === activeId ? {
                ...old,
                messages: (old.messages ?? []).map(item =>
                  item.id === assistantId ? { ...item, thought: (item.thought || "") + event.data.text } : item
                )
              } : old));
            }
            if (useDeepSearch) {
              const rawT = (event.data.text || "").trim();
              const cleanT = rawT.replace(/^[#*•\s]+/, "").trim();
              if (cleanT && cleanT.length > 5) {
                appendResearchActivity(assistantId, {
                  kind: "stage",
                  timestamp: new Date().toISOString(),
                  message: cleanT.length > 200 ? cleanT.slice(0, 197) + "…" : cleanT,
                });
              }
            }
          } else if (event.type === "research_activity") {
            if (useDeepSearch) appendResearchActivity(assistantId, event.data);
          } else if (event.type === "delta") {
            const inProgress = streamingDeltasRef.current.get(activeId!);
            if (inProgress) {
              inProgress.text += event.data.text;
              inProgress.status = "";
            }
            accumulatedText += event.data.text;
            if (conversationIdRef.current === activeId) {
              setStatus("");
              if (!canvasOpen && (useCodeMode || hasExplicitCanvasFiles(accumulatedText))) {
                setCanvasMessageId(assistantId);
                setContextOpen(false);
                setSkillsOpen(false);
                setCanvasOpen(true);
              }
              setConversation(old => (old && old.id === activeId ? {
                ...old,
                messages: (old.messages ?? []).map(item => item.id === assistantId ? { ...item, content: item.content + event.data.text } : item)
              } : old));
            }
          } else if (event.type === "done") {
            setResearchRuns(old => old[assistantId] ? { ...old, [assistantId]: { ...old[assistantId], state: "completed" } } : old);
            streamingDeltasRef.current.delete(activeId!);
            if (conversationIdRef.current === activeId) {
              setConversation(old => (old && old.id === activeId ? {
                ...event.data.conversation,
                skills: event.data.conversation.skills ?? old.skills ?? [],
                messages: event.data.conversation.messages ?? (old.messages ?? []).map(item => item.id === assistantId ? event.data.message : item)
              } : old));
            }
            if (event.data.memories) {
              setMemories(event.data.memories);
            }
            if (event.data.new_memories && event.data.new_memories.length > 0) {
              const count = event.data.new_memories.length;
              const notice = count === 1
                ? `Souvenir retenu : « ${event.data.new_memories[0]} »`
                : `${count} souvenirs retenus en mémoire`;
              setMemoryNotice(notice);
              setTimeout(() => setMemoryNotice(null), 7000);
            }
          }
        }
      );
      const loaded = await api<Conversation>(`/conversations/${activeId}`);
      if (conversationIdRef.current === activeId) setConversation(loaded);
      await refreshConversations();
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      setResearchRuns(old => old[assistantId]?.state === "running" ? { ...old, [assistantId]: { ...old[assistantId], state: aborted ? "interrupted" : "failed" } } : old);
      if (conversationIdRef.current === activeId) {
        setError(aborted ? "Génération interrompue. Les messages déjà enregistrés restent dans l’historique." : errorMessage(err));
        if (!persisted) { setDraft(text); setAttachments(files); }
      }
      if (activeId) {
        try {
          let fresh = await api<Conversation>(`/conversations/${activeId}`);
          if (persisted && (fresh.messages?.length ?? 0) <= 1) {
            await new Promise(r => setTimeout(r, 2000));
            fresh = await api<Conversation>(`/conversations/${activeId}`);
          }
          if (conversationIdRef.current === activeId) setConversation(fresh);
          await refreshConversations();
        } catch { /* Preserve history */ }
      }
    } finally {
      if (activeId) {
        streamControllersRef.current.delete(activeId);
        setStreamingConversationIds(old => old.filter(id => id !== activeId));
        streamingDeltasRef.current.delete(activeId);
      }
      if (conversationIdRef.current === activeId) {
        setStreamingId(null);
        setBusy(null);
        setStatus("");
        textareaRef.current?.focus();
      }
    }
  }

  async function saveMemory(event: FormEvent) {
    event.preventDefault();
    if (!memoryDraft.trim() || working) return;
    setBusy("memory"); setError("");
    try {
      const saved = await api<Memory>("/memories", { method: "POST", body: JSON.stringify({ content: memoryDraft.trim() }) });
      setMemories(old => [saved, ...old]); setMemoryDraft("");
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function deleteMemory(id: string) {
    if (working) return;
    setBusy("memory"); setError("");
    try { await api(`/memories/${id}`, { method: "DELETE" }); setMemories(old => old.filter(item => item.id !== id)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function authenticated(current: AuthUser) {
    setUser(current); setError(""); setBusy("init");
    try {
      await loadWorkspace();
      await loadFamily();
    }
    catch (err) { setError(`Connexion au serveur impossible. ${errorMessage(err)}`); }
    finally { setBusy(null); setAuthReady(true); }
  }

  function invitationAccepted() {
    setResearchRuns({}); setResearchActivityMessageId(null);
    setUser(null); setConfig(null); setConversations([]); setConversation(null); setMemories([]);
    setDraft(""); setAttachments([]); setMemoryDraft(""); setAdminOpen(false); setFamilyModalOpen(false); setSettingsModalOpen(false); setProfileMenuOpen(false);
    window.history.replaceState({}, "", window.location.pathname + window.location.search);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  async function logout() {
    setError("");
    try {
      await api<void>("/auth/logout", { method: "POST" });
    } catch (err) {
      console.error("Logout error", err);
    } finally {
      setUser(null); setConfig(null); setConversations([]); setConversation(null); setMemories([]);
      setResearchRuns({}); setResearchActivityMessageId(null);
      setSkills([]); setFamilyInfo(null); setAdminOpen(false); setFamilyModalOpen(false); setSettingsModalOpen(false); setProfileMenuOpen(false);
      setAuthReady(true);
    }
  }

  function openEditDialog(target: Conversation) {
    setDialog({ type: "rename", conversation: target });
    setRenameValue(target.title);
    setRenameTheme(target.theme?.trim() || "Général");
    setRenameKeywords((target.keywords ?? []).join(", "));
  }

  function toggleKeywordFilter(kw: string) {
    const clean = kw.trim().replace(/^#+/, "");
    setSelectedKeyword(old => (old.toLocaleLowerCase("fr") === clean.toLocaleLowerCase("fr") ? "" : clean));
  }

  function toggleThemeCollapse(label: string) {
    setCollapsedThemes(old => ({ ...old, [label]: !old[label] }));
  }

  async function classifyConversation(id: string, updateTitle = true) {
    if (working) return;
    setBusy("classify"); setError("");
    try {
      const updated = await api<Conversation>(`/conversations/${id}/classify`, {
        method: "POST",
        body: JSON.stringify({ update_title: updateTitle }),
      });
      if (conversation?.id === id) {
        setConversation(old => old ? { ...old, ...updated, messages: updated.messages ?? old.messages } : updated);
      }
      if (dialog?.conversation.id === id) {
        if (updateTitle) setRenameValue(updated.title);
        setRenameTheme(updated.theme?.trim() || "Général");
        setRenameKeywords((updated.keywords ?? []).join(", "));
      }
      await refreshConversations();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function classifyAllConversations() {
    if (working) return;
    setBusy("classify-all"); setError("");
    try {
      const updatedList = await api<Conversation[]>("/conversations/classify-all?force=true", { method: "POST" });
      setConversations(updatedList);
      if (conversation) {
        const match = updatedList.find(item => item.id === conversation.id);
        if (match) {
          setConversation(old => old ? { ...old, title: match.title, theme: match.theme, keywords: match.keywords } : old);
        }
      }
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function submitDialog(event: FormEvent) {
    event.preventDefault();
    if (!dialog || working || (dialog.type === "rename" && !renameValue.trim())) return;
    setBusy("edit"); setError("");
    try {
      const id = dialog.conversation.id;
      if (dialog.type === "delete") {
        await api(`/conversations/${id}`, { method: "DELETE" });
        if (conversation?.id === id) { setConversation(null); setDraft(""); setAttachments([]); }
      } else {
        const parsedKeywords = renameKeywords
          .split(/[,;]+/)
          .map(k => k.trim().replace(/^#+/, ""))
          .filter(Boolean)
          .slice(0, 5);
        const updated = await api<Conversation>(`/conversations/${id}`, {
          method: "PATCH",
          body: JSON.stringify({
            title: renameValue.trim(),
            theme: renameTheme.trim() || "Général",
            keywords: parsedKeywords,
          }),
        });
        if (conversation?.id === id) setConversation(old => old ? { ...old, ...updated, messages: updated.messages ?? old.messages } : updated);
      }
      await refreshConversations(); setDialog(null);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(null); }
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (mentionQuery !== null && filteredMentionSkills.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setMentionIndex(i => (i + 1) % filteredMentionSkills.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setMentionIndex(i => (i - 1 + filteredMentionSkills.length) % filteredMentionSkills.length);
        return;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        event.preventDefault();
        insertMention(filteredMentionSkills[mentionIndex]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setMentionQuery(null);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (isCurrentStreaming) {
        setStatus("Réponse en cours dans cette discussion… Cliquez sur Arrêter ou patientez avant d’envoyer.");
        return;
      }
      void send();
    }
  }

  if (!authReady) return <div className="auth-loading" role="status"><LoaderCircle className="spin" size={20} />Vérification de la session…</div>;
  if (invitationToken || !user) return <AuthPanel invitationToken={invitationToken} serviceError={authError} onAuthenticated={authenticated} onRegistration={invitationAccepted} />;

  return <div className="app-shell">
    <a className="skip-link" href="#composer">Aller au message</a>
    {sidebarOpen && <button className="sidebar-overlay" type="button" aria-label="Fermer le menu" onClick={() => setSidebarOpen(false)} />}
    <aside className={`sidebar ${sidebarOpen ? "is-open" : ""}`} aria-label="Conversations">
      <div className="brand"><BrandMark small /><span>cLAIr<span className="brand-dot">.</span></span><IconButton label="Fermer le menu" className="mobile-only" onClick={() => setSidebarOpen(false)}><PanelLeftClose size={18} /></IconButton></div>
      <button type="button" className="new-chat" onClick={() => void newConversation()} disabled={working}><Plus size={18} /><span>Nouvelle conversation</span><kbd>+</kbd></button>
      <label className="search-field">
        <Search size={16} />
        <input
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Titre, #mot-clé ou thème…"
          aria-label="Rechercher par titre, mot-clé ou thème"
        />
        {hasActiveFilter ? (
          <button
            type="button"
            className="search-clear"
            onClick={() => { setQuery(""); setSelectedKeyword(""); setSelectedTheme(""); }}
            aria-label="Effacer les filtres de recherche"
            title="Effacer les filtres"
          >
            <X size={13} />
          </button>
        ) : (
          <kbd>⌕</kbd>
        )}
      </label>

      {topKeywords.length > 0 && (
        <div className="sidebar-keywords-bar" aria-label="Filtrer par mot-clé">
          {selectedTheme && (
            <button
              type="button"
              className={`keyword-filter-chip is-theme is-active tone-${themeTone(selectedTheme)}`}
              onClick={() => setSelectedTheme("")}
              title="Retirer le filtre de thème"
            >
              <span>{selectedTheme}</span>
              <X size={11} />
            </button>
          )}
          {topKeywords.map(item => {
            const active = selectedKeyword.toLocaleLowerCase("fr") === item.label.toLocaleLowerCase("fr");
            return (
              <button
                key={item.label}
                type="button"
                className={`keyword-filter-chip ${active ? "is-active" : ""}`}
                onClick={() => toggleKeywordFilter(item.label)}
                title={`Filtrer par le mot-clé #${item.label} (${item.count})`}
              >
                <span>#{item.label}</span>
              </button>
            );
          })}
        </div>
      )}

      <div className="history-header">
        <span>VOTRE ESPACE · {filteredConversations.length}</span>
        <div className="history-header-controls">
          {conversations.length > 0 && (
            <button
              type="button"
              className="history-autoclassify-btn"
              disabled={working}
              onClick={() => void classifyAllConversations()}
              title="Générer automatiquement les titres, thèmes et mots-clés manquants (Mistral Small)"
              aria-label="Classer automatiquement les discussions"
            >
              {busy === "classify-all" ? <LoaderCircle size={12} className="spin" /> : <WandSparkles size={12} />}
            </button>
          )}
          <div className="history-view-toggle" role="group" aria-label="Mode de regroupement">
            <button
              type="button"
              className={groupMode === "date" ? "is-active" : ""}
              aria-pressed={groupMode === "date"}
              onClick={() => setGroupMode("date")}
            >
              Date
            </button>
            <button
              type="button"
              className={groupMode === "theme" ? "is-active" : ""}
              aria-pressed={groupMode === "theme"}
              onClick={() => setGroupMode("theme")}
            >
              Thèmes
            </button>
          </div>
        </div>
      </div>
      <nav className="history-list" aria-label="Historique des conversations">
        {busy === "init" ? <p className="history-empty"><LoaderCircle className="spin" size={16} /> Chargement de l’historique…</p> : groups.length ? groups.map(group => {
          const isCollapsed = groupMode === "theme" && Boolean(collapsedThemes[group.label]);
          const tone = groupMode === "theme" ? themeTone(group.label) : "general";
          return (
            <div key={group.label} className={`history-group ${groupMode === "theme" ? "is-theme-group" : ""}`}>
              {groupMode === "theme" ? (
                <button
                  type="button"
                  className={`history-theme-header tone-${tone}`}
                  onClick={() => toggleThemeCollapse(group.label)}
                  aria-expanded={!isCollapsed}
                >
                  <span className={`theme-dot tone-${tone}`} />
                  <span className="history-theme-title">{group.label}</span>
                  <span className="history-theme-count">{group.items.length}</span>
                  {isCollapsed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                </button>
              ) : (
                <h2>{group.label}</h2>
              )}
              {!isCollapsed && group.items.map(item => {
                const itemTheme = item.theme?.trim() || "";
                const itemKeywords = (item.keywords ?? []).slice(0, 3);
                return (
                  <div key={item.id} className={`history-item ${conversation?.id === item.id ? "is-active" : ""}`}>
                    <div className="history-item-main">
                      <button type="button" className="history-select" disabled={busy === "switch"} onClick={() => void openConversation(item.id)}>
                        <MessageCircle size={15} />
                        <span>{item.title}</span>
                        {streamingConversationIds.includes(item.id) && (
                          <span title="Réponse en cours…">
                            <LoaderCircle size={12} className="spin history-streaming-icon" />
                          </span>
                        )}
                      </button>
                      {(itemKeywords.length > 0 || (groupMode === "date" && itemTheme)) && (
                        <div className="history-item-meta">
                          {groupMode === "date" && itemTheme && (
                            <button
                              type="button"
                              className={`history-theme-badge tone-${themeTone(itemTheme)}`}
                              onClick={() => {
                                setGroupMode("theme");
                                setSelectedTheme(old => (old === itemTheme ? "" : itemTheme));
                              }}
                              title={`Regrouper ou filtrer par le thème « ${itemTheme} »`}
                            >
                              {itemTheme}
                            </button>
                          )}
                          {itemKeywords.map(kw => {
                            const kwActive = selectedKeyword.toLocaleLowerCase("fr") === kw.toLocaleLowerCase("fr");
                            return (
                              <button
                                key={kw}
                                type="button"
                                className={`history-keyword-pill ${kwActive ? "is-active" : ""}`}
                                onClick={() => toggleKeywordFilter(kw)}
                                title={`Chercher les discussions avec #${kw}`}
                              >
                                #{kw}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                    <div className="history-tools">
                      <IconButton label={`Modifier « ${item.title} »`} disabled={working} onClick={() => openEditDialog(item)}><Pencil size={13} /></IconButton>
                      <IconButton label={`Supprimer « ${item.title} »`} disabled={working} onClick={() => setDialog({ type: "delete", conversation: item })}><Trash2 size={13} /></IconButton>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        }) : <div className="history-empty"><MessageCircle size={20} /><p>{hasActiveFilter ? "Aucune discussion ne correspond à ce filtre." : "Une idée, une question…\nVotre historique commence ici."}</p></div>}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-quick-tools" aria-label="Accès rapides aux espaces et outils">
          <button
            type="button"
            className={`sidebar-quick-btn blog-quick ${blogModalOpen ? "is-active" : ""}`}
            onClick={() => { openBlogModal(""); setSidebarOpen(false); }}
            title="Mes Blogs d’actualités (Veille SearXNG & résumés auto)"
            aria-label="Mes Blogs d’actualités"
          >
            <Newspaper size={16} />
            <span className="sidebar-quick-label">Blogs</span>
          </button>
          <button
            type="button"
            className={`sidebar-quick-btn deepsearch-quick ${deepSearchModalOpen ? "is-active" : ""}`}
            onClick={() => {
              setDeepSearchModalQuestion(draft.trim());
              setDeepSearchModalTab("reports");
              setDeepSearchModalReportId(null);
              setDeepSearchModalOpen(true);
              setSidebarOpen(false);
            }}
            title="Rapports DeepSearch (Analyses HTML & recherche approfondie)"
            aria-label="Rapports DeepSearch"
          >
            <Compass size={16} />
            <span className="sidebar-quick-label">DeepSearch</span>
          </button>
          <button
            type="button"
            className={`sidebar-quick-btn learn-quick ${learnModalOpen ? "is-active" : ""}`}
            onClick={() => {
              setLearnModalQuestion(draft.trim());
              setLearnModalTab("reports");
              setLearnModalReportId(null);
              setLearnModalOpen(true);
              setSidebarOpen(false);
            }}
            title="Mes Cours & Formations (Cours magistraux, cas pratiques & HTML)"
            aria-label="Mes Cours & Formations"
          >
            <GraduationCap size={16} />
            <span className="sidebar-quick-label">Cours</span>
          </button>
          <button
            type="button"
            className={`sidebar-quick-btn memory-quick ${contextOpen && contextTab === "memories" ? "is-active" : ""}`}
            onClick={() => { setContextTab("memories"); setContextOpen(true); setSidebarOpen(false); }}
            title={`Votre mémoire (${memories.length ? `${memories.length} information${memories.length > 1 ? "s" : ""}` : "Les choses qui comptent"})`}
            aria-label="Votre mémoire"
          >
            <Brain size={16} />
            <span className="sidebar-quick-label">Mémoire</span>
          </button>
        </div>
        <div className="profile">
          <div className="profile-main" onClick={() => setFamilyModalOpen(true)} title="Gérer le groupe familial ou basculer" role="button" tabIndex={0}>
            <span className="avatar">{user.username[0].toLocaleUpperCase("fr")}</span>
            <span className="profile-user">
              <strong>{user.username}</strong>
              <small>
                {familyInfo?.name ? (
                  <span className="family-sub-link"><Users size={11} /> {familyInfo.name}</span>
                ) : (
                  <><span className="connection-dot" /> Compte sécurisé</>
                )}
              </small>
            </span>
          </div>
          {familyInfo?.members && familyInfo.members.filter(m => m.id !== user.id).length > 0 && (
            <div className="sidebar-family-avatars" title="Basculer vers un autre membre de la famille">
              {familyInfo.members.filter(m => m.id !== user.id).slice(0, 3).map(m => (
                <button
                  key={m.id}
                  type="button"
                  className="sidebar-avatar-pill"
                  onClick={() => void switchAccount(m.id)}
                  title={`Basculer immédiatement sur ${m.username}`}
                >
                  {m.username[0].toLocaleUpperCase("fr")}
                </button>
              ))}
              {familyInfo.members.filter(m => m.id !== user.id).length > 3 && (
                <button
                  type="button"
                  className="sidebar-avatar-more"
                  onClick={() => setFamilyModalOpen(true)}
                  title="Voir tous les membres"
                >
                  +{familyInfo.members.filter(m => m.id !== user.id).length - 3}
                </button>
              )}
            </div>
          )}
          <div className="profile-actions">
            <IconButton label="Paramètres & Prompt général" onClick={() => setSettingsModalOpen(true)}>
              <Settings size={16} />
            </IconButton>
            <IconButton label={familyInfo?.id ? "Groupe familial" : "Créer un groupe familial"} onClick={() => setFamilyModalOpen(true)}>
              <Users size={16} />
            </IconButton>
            {user.is_admin && <IconButton label="Gérer les utilisateurs" onClick={() => setAdminOpen(true)}><Shield size={16} /></IconButton>}
            <IconButton label="Se déconnecter (retour au login)" onClick={() => void logout()} className="profile-logout-btn"><LogOut size={16} /></IconButton>
          </div>
        </div>
      </div>
    </aside>

    <main className="main-panel">
      <header className="topbar">
        <div className="topbar-left">
          <IconButton label="Ouvrir le menu" className="mobile-only" onClick={() => setSidebarOpen(true)}><Menu size={21} /></IconButton>
          <div className="model-select-wrap"><button type="button" className="model-selector-btn" onClick={() => setModelModalOpen(true)} disabled={!config || working} title="Changer de modèle IA (voir tous les modèles, prix, contexte, vision)" aria-label="Changer de modèle IA"><span className="model-indicator" /><span className="model-current-name">{currentModelInfo?.name || model || "Modèle IA"}</span>{currentModelInfo?.vision && <span className="model-topbar-pill vision" title="Modèle multimodal avec vision (images acceptées)"><Eye size={11} /><span>Vision</span></span>}{currentModelPriceTag && <span className={`model-topbar-pill price ${currentModelPriceTag === "Gratuit" ? "is-free" : ""}`}>{currentModelPriceTag}</span>}<ChevronDown size={14} className="model-chevron" /></button></div>
          <span className="topbar-divider" />
          <span className="personal-label">Votre espace IA</span>
        </div>
        <div className="topbar-right">
          <button
            type="button"
            className={`deepsearch-topbar-button ${deepSearchModalOpen ? "is-selected" : ""}`}
            onClick={() => {
              setDeepSearchModalQuestion(draft.trim());
              setDeepSearchModalTab("reports");
              setDeepSearchModalReportId(null);
              setDeepSearchModalOpen(true);
            }}
            aria-label="Ouvrir mes rapports DeepSearch"
            title="Consulter mes rapports d’analyse approfondie DeepSearch"
          >
            <Compass size={17} />
            <span>DeepSearch</span>
          </button>
          <button
            type="button"
            className={`learn-topbar-button ${learnModalOpen ? "is-selected" : ""}`}
            onClick={() => {
              setLearnModalQuestion(draft.trim());
              setLearnModalTab("reports");
              setLearnModalReportId(null);
              setLearnModalOpen(true);
            }}
            aria-label="Ouvrir mes cours et formations"
            title="Consulter mes cours, parcours de formation et fiches de révision"
          >
            <GraduationCap size={17} />
            <span>Cours</span>
          </button>
          <button type="button" className={`blog-topbar-button ${blogModalOpen ? "is-selected" : ""}`} onClick={() => openBlogModal("")} aria-label="Ouvrir mes blogs" title="Consulter mes blogs d’actualités SearXNG"><Newspaper size={17} /><span>Blogs</span></button>
          <button type="button" className={`canvas-topbar-button ${canvasOpen ? "is-selected" : ""}`} onClick={() => { setCanvasOpen(old => { const next = !old; if (next) { setContextOpen(false); setSkillsOpen(false); } return next; }); }} aria-expanded={canvasOpen} aria-label="Ouvrir le Canvas Code" title="Ouvrir le Canvas Code interactif"><Code2 size={17} /><span>Canvas Code</span>{canvasFiles.length > 0 && <span className="canvas-topbar-count">{canvasFiles.length}</span>}</button>
          <button type="button" className="studio-topbar-button" onClick={() => openImageStudio(draft.trim())} aria-label="Ouvrir le Studio Image" title="Ouvrir le Studio Image"><ImagePlus size={17} /><span>Studio Image</span></button>
          <button type="button" className={`sound-topbar-button ${soundStudioOpen ? "is-selected" : ""}`} onClick={() => openSoundStudio(draft.trim())} aria-label="Ouvrir le Studio Son & Musique" title="Générer des effets sonores et morceaux de musique avec ElevenLabs"><Volume2 size={17} /><span>Sons & Musique</span></button>
          <button
            type="button"
            className={`multiagent-topbar-button ${multiAgentActive ? "is-selected" : ""}`}
            onClick={() => setShowMultiAgentModal(true)}
            aria-label="Ouvrir le Conseil Multi-Agents"
            title="Conseil Multi-Agents : délibération collaborative entre plusieurs modèles et personnalités (Synthèse d'experts ou Débat)"
          >
            <Users size={17} />
            <span>Conseil IA</span>
            {multiAgentActive && <span className="topbar-active-dot" />}
          </button>
          <button type="button" className={`context-toggle ${contextOpen ? "is-selected" : ""}`} onClick={() => { setContextOpen(old => { const next = !old; if (next) setCanvasOpen(false); return next; }); }} aria-expanded={contextOpen} aria-controls="context-panel" aria-label="Mémoire & contexte" title="Consulter la mémoire et le contexte"><Brain size={17} /><span>Mémoire</span><span className="memory-count">{memories.length}</span></button>

          {/* Sortie & Export de la discussion */}
          {conversation && (
            <button
              type="button"
              className={`topbar-study-btn ${studyModalOpen ? "is-active" : ""}`}
              onClick={() => openStudyModal("flashcards")}
              title="Générer des Flashcards 3D ou un Quizz QCM sur le sujet discuté"
              aria-label="Flashcards et Quizz d'auto-évaluation"
            >
              <Brain size={16} />
              <span>Flash / Quizz</span>
            </button>
          )}
          {conversation && (
            <div className="topbar-export-wrap" ref={topbarExportRef}>
              <button
                type="button"
                className={`topbar-export-btn ${topbarExportOpen ? "is-active" : ""}`}
                onClick={() => setTopbarExportOpen(prev => !prev)}
                title="Sortie et export de la conversation (PDF ou HTML)"
                aria-expanded={topbarExportOpen}
                aria-label="Sortie de la discussion"
              >
                <Share2 size={16} />
                <span>Sortie</span>
                <ChevronDown size={13} className={`topbar-chevron ${topbarExportOpen ? "is-open" : ""}`} />
              </button>
              {topbarExportOpen && (
                <div className="topbar-export-dropdown" role="menu">
                  <div className="topbar-export-dropdown-header">
                    <span className="dropdown-export-icon"><Share2 size={13} /></span>
                    <div>
                      <strong>Sortie de la discussion</strong>
                      <small>{conversation.title || "Discussion cLAIr"}</small>
                    </div>
                  </div>
                  <div className="topbar-export-options">
                    <a
                      href={`/api/conversations/${conversation.id}/html`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="topbar-export-link btn-html"
                      onClick={() => setTopbarExportOpen(false)}
                      title="Consulter la synthèse complète en site HTML"
                    >
                      <Globe2 size={14} />
                      <span>Site HTML</span>
                    </a>
                    <a
                      href={`/api/conversations/${conversation.id}/html?pdf=1`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="topbar-export-link btn-pdf"
                      onClick={() => setTopbarExportOpen(false)}
                      title="Imprimer ou enregistrer la discussion en Beau PDF (A4)"
                    >
                      <FileText size={14} />
                      <span>Beau PDF</span>
                    </a>
                    <a
                      href={`/api/conversations/${conversation.id}/slides`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="topbar-export-link btn-slides"
                      onClick={(e) => {
                        e.currentTarget.href = `/api/conversations/${conversation.id}/slides?t=${Date.now()}`;
                        setTopbarExportOpen(false);
                      }}
                      title="Consulter la présentation type PowerPoint (diaporama interactif 16:9)"
                    >
                      <Presentation size={14} />
                      <span>Présentation PPT</span>
                    </a>
                    <a
                      href={`/api/conversations/${conversation.id}/html?download=1`}
                      download
                      className="topbar-export-link btn-download-html"
                      onClick={() => setTopbarExportOpen(false)}
                      title="Télécharger la discussion au format fichier .html complet"
                    >
                      <Download size={14} />
                      <span>Télécharger .html</span>
                    </a>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Paramètres & Prompt Général */}
          <button
            type="button"
            className={`topbar-settings-btn ${settingsModalOpen ? "is-active" : ""}`}
            onClick={() => setSettingsModalOpen(true)}
            aria-label="Ouvrir les paramètres et le prompt général"
            title="Paramètres de l'assistant, prompt général permanent et cache de prompt"
          >
            <Settings size={16} />
            <span>Paramètres</span>
          </button>

          {/* Profil utilisateur & Bascule rapide de compte */}
          <div className="topbar-profile-wrap" ref={profileMenuRef}>
            <button
              type="button"
              className={`topbar-profile-btn ${profileMenuOpen ? "is-active" : ""}`}
              onClick={() => setProfileMenuOpen(prev => !prev)}
              aria-expanded={profileMenuOpen}
              aria-label="Mon compte et groupe familial"
            >
              <span className="topbar-profile-avatar">{user.username[0].toLocaleUpperCase("fr")}</span>
              <span className="topbar-profile-name">{user.username}</span>
              {familyInfo?.id && (
                <span className="topbar-family-pill" title={`Groupe familial : ${familyInfo.name}`}>
                  <Users size={12} />
                </span>
              )}
              <ChevronDown size={14} className={`topbar-chevron ${profileMenuOpen ? "is-open" : ""}`} />
            </button>

            {profileMenuOpen && (
              <div className="profile-dropdown-menu" role="menu">
                <div className="profile-dropdown-header">
                  <span className="dropdown-avatar">{user.username[0].toLocaleUpperCase("fr")}</span>
                  <div className="dropdown-user-details">
                    <strong>{user.username}</strong>
                    <small>{user.is_admin ? "Administrateur" : "Compte membre"} · <span className="status-dot-active" /> Connecté</small>
                  </div>
                </div>

                <div className="profile-dropdown-section">
                  <div className="profile-dropdown-section-header">
                    <span className="dropdown-section-title">
                      <Users size={13} /> {familyInfo?.name || "Groupe familial"}
                    </span>
                    <button
                      type="button"
                      className="dropdown-section-link"
                      onClick={() => {
                        setProfileMenuOpen(false);
                        setFamilyModalOpen(true);
                      }}
                    >
                      {familyInfo?.id ? "Gérer" : "+ Créer"}
                    </button>
                  </div>

                  {familyInfo?.members && familyInfo.members.filter(m => m.id !== user.id).length > 0 ? (
                    <div className="family-switch-list">
                      <span className="family-switch-hint">Basculer sur un compte sans mot de passe :</span>
                      {familyInfo.members
                        .filter(m => m.id !== user.id)
                        .map(member => (
                          <button
                            key={member.id}
                            type="button"
                            className="family-quick-switch-item"
                            onClick={() => void switchAccount(member.id)}
                            title={`Basculer immédiatement sur ${member.username}`}
                          >
                            <span className="quick-avatar">{member.username[0].toLocaleUpperCase("fr")}</span>
                            <span className="quick-name">{member.username}</span>
                            <span className="quick-badge"><ArrowRightLeft size={11} /> Basculer</span>
                          </button>
                        ))}
                    </div>
                  ) : familyInfo?.id ? (
                    <div className="dropdown-empty-family">
                      <span>Aucun autre compte dans la famille.</span>
                      <button
                        type="button"
                        className="dropdown-action-text"
                        onClick={() => {
                          setProfileMenuOpen(false);
                          setFamilyModalOpen(true);
                        }}
                      >
                        + Ajouter un membre
                      </button>
                    </div>
                  ) : (
                    <div className="dropdown-empty-family">
                      <span>Partagez l’app en famille avec bascule instantanée.</span>
                      <button
                        type="button"
                        className="dropdown-action-text"
                        onClick={() => {
                          setProfileMenuOpen(false);
                          setFamilyModalOpen(true);
                        }}
                      >
                        Créer un groupe familial
                      </button>
                    </div>
                  )}
                </div>

                <button
                  type="button"
                  className="profile-menu-item"
                  onClick={() => {
                    setProfileMenuOpen(false);
                    setSettingsModalOpen(true);
                  }}
                >
                  <Settings size={15} />
                  <span>Paramètres & Prompt général</span>
                </button>

                {user.is_admin && (
                  <button
                    type="button"
                    className="profile-menu-item"
                    onClick={() => {
                      setProfileMenuOpen(false);
                      setAdminOpen(true);
                    }}
                  >
                    <Shield size={15} />
                    <span>Gestion des utilisateurs</span>
                  </button>
                )}

                <div className="profile-dropdown-divider" />

                <button
                  type="button"
                  className="profile-menu-item is-logout"
                  onClick={() => void logout()}
                  title="Fermer la session et retourner à la page de connexion"
                >
                  <LogOut size={15} />
                  <span>Se déconnecter (retour au login)</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {config?.demo_mode && <div className="demo-banner" role="status"><CircleAlert size={17} /><span><strong>Mode démonstration.</strong> Les réponses sont simulées, aucun modèle IA n’est appelé. Configurez une clé côté serveur et désactivez <code>DEMO_MODE</code> pour activer l’IA.</span></div>}
      {config && !config.features.chat && !config.demo_mode && <div className="demo-banner" role="status"><CircleAlert size={17} /><span><strong>Le tchat attend sa configuration.</strong> Ajoutez une clé du fournisseur IA dans le fichier <code>.env</code> du serveur, puis redémarrez le backend.</span></div>}

      <div className="workspace">
        <section className="chat-panel" aria-label="Conversation">
          <div className="chat-skills-toolbar"><span>{conversation?.skills?.length ? conversation.skills.map(skill => skill.name).join(" · ") : "Aucune compétence active"}</span><button type="button" onClick={() => { setContextOpen(false); setSkillsOpen(true); }}><Sparkles size={15} />Compétences<small>{conversation?.skills?.length ?? 0}</small></button></div>
          {skillsOpen && <SkillsPanel conversation={conversation} model={model} config={config} onClose={() => setSkillsOpen(false)} onConversationChange={setConversation} onRefreshConversations={refreshConversations} onSkillsChange={setSkills} />}
          <div className="chat-scroll" ref={messagesRef} onScroll={() => { const el = messagesRef.current; if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 120); }}>
            {!messages.length && busy !== "switch" ? <div className="welcome"><div className="welcome-eyebrow"><span /> UN PEU DE CLARTÉ, BEAUCOUP DE POSSIBILITÉS</div><BrandMark /><h1>Qu’avez-vous en tête<span> aujourd’hui ?</span></h1><p>Un espace pour vos questions, vos idées et vos projets.<br />Commencez quelque part. On avance ensemble.</p><div className="suggestions">{suggestions.map((item, index) => <button type="button" className="suggestion" key={item.title} disabled={working} onClick={() => { if (index === 3) { openImageStudio(item.prompt); } else if (index === 1) { openBlogModal(item.prompt); } else { setDraft(item.prompt); textareaRef.current?.focus(); } }}><span className={`suggestion-icon suggestion-icon-${index}`}><item.icon size={19} strokeWidth={1.6} /></span><strong>{item.title}</strong><span>{item.description}</span><ChevronRight size={15} className="suggestion-arrow" /></button>)}</div><div className="welcome-note"><Brain size={14} /><span>Les souvenirs que vous choisissez gardent le fil d’une conversation à l’autre.</span></div></div> : busy === "switch" ? <div className="loading-conversation"><LoaderCircle size={23} className="spin" />Ouverture de votre conversation…</div> : <div className="messages"><div className="conversation-heading"><div className="conversation-heading-top"><span>CONVERSATION</span>{conversation?.theme && <button type="button" className={`conversation-theme-badge tone-${themeTone(conversation.theme)}`} onClick={() => { setGroupMode("theme"); setSelectedTheme(old => (old === conversation.theme ? "" : (conversation.theme ?? ""))); setSidebarOpen(true); }} title={`Voir toutes les discussions du thème « ${conversation.theme} »`}>{conversation.theme}</button>}<div className="conversation-heading-actions">{conversation && <button type="button" className="conversation-meta-btn conversation-study-btn" disabled={working} onClick={() => openStudyModal("flashcards")} title="Générer des Flashcards 3D ou un Quizz QCM sur le sujet discuté"><Brain size={12} /><span>Flash / Quizz</span></button>}{conversation && <button type="button" className="conversation-meta-btn" disabled={working} onClick={() => openEditDialog(conversation)} title="Modifier le titre, le thème et les mots-clés"><Pencil size={12} /><span>Éditer</span></button>}{conversation && <button type="button" className="conversation-meta-btn" disabled={working} onClick={() => void classifyConversation(conversation.id, true)} title="Régénérer le titre, le thème et les mots-clés automatiquement (Mistral Small)">{busy === "classify" ? <LoaderCircle size={12} className="spin" /> : <WandSparkles size={12} />}<span>Auto-tags IA</span></button>}</div></div><h1>{conversation?.title}</h1>{!!conversation?.keywords?.length && <div className="conversation-keywords-row" aria-label="Mots-clés de la discussion">{conversation.keywords.map(kw => <button key={kw} type="button" className={`conversation-keyword-chip ${selectedKeyword.toLocaleLowerCase("fr") === kw.toLocaleLowerCase("fr") ? "is-active" : ""}`} onClick={() => { toggleKeywordFilter(kw); setSidebarOpen(true); }} title={`Filtrer les discussions avec #${kw}`}>#{kw}</button>)}</div>}</div>{messages.map(message => <MessageView key={message.id} message={message} streaming={streamingId === message.id} onOpenCanvas={openCanvasForMessage} onOpenDeepSearchReport={handleOpenDeepSearchReport} researchActivity={researchRuns[message.id]} onOpenResearchActivity={setResearchActivityMessageId} onOpenLearnReport={handleOpenLearnReport} onOpenFinanceModal={openFinanceModal} />)}<div ref={bottomRef} /></div>}
          </div>
          {!atBottom && !!messages.length && <IconButton className="scroll-bottom" label="Aller aux derniers messages" onClick={() => { setAtBottom(true); bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }}><ArrowDown size={18} /></IconButton>}

          <div className="composer-area">
            {memoryNotice && (
              <div className="memory-toast" role="status">
                <Brain size={14} className="memory-toast-icon" />
                <span className="memory-toast-text">{memoryNotice}</span>
                <button
                  type="button"
                  className="memory-toast-action"
                  onClick={() => {
                    setContextTab("memories");
                    setContextOpen(true);
                    setMemoryNotice(null);
                  }}
                >
                  Voir mes souvenirs
                </button>
                <IconButton label="Fermer la notification mémoire" onClick={() => setMemoryNotice(null)}>
                  <X size={13} />
                </IconButton>
              </div>
            )}
            {error && <div className="error-banner" role="alert"><CircleAlert size={17} /><p>{error}</p>{!config && <button type="button" disabled={working} onClick={() => void bootstrap()}>Réessayer</button>}<IconButton label="Fermer le message d’erreur" onClick={() => setError("")}><X size={15} /></IconButton></div>}
            {showDuckDuckGoNotice && <div className="search-notice" id="web-search-hint" role="status"><Globe2 size={13} />DuckDuckGo fournit des réponses instantanées et des sujets associés ; couverture limitée.</div>}
            {needsVision && <div className="vision-notice" role="status"><CircleAlert size={13} />Pour analyser vos images, choisissez un modèle compatible avec la vision.</div>}
            {status && <div className="generation-status" role="status"><LoaderCircle size={13} className="spin" />{status}{streamingId && researchRuns[streamingId] && <button type="button" className="tool-button" onClick={() => setResearchActivityMessageId(streamingId)}>Voir l’activité</button>}</div>}

            {mentionQuery !== null && (
              <div className="mention-autocomplete-menu" role="listbox" aria-label="Compétences disponibles">
                <div className="mention-menu-header">
                  <Sparkles size={13} />
                  <span>Compétences ({filteredMentionSkills.length})</span>
                  <small>↑↓ pour naviguer, Entrée pour insérer</small>
                </div>
                {filteredMentionSkills.length > 0 ? (
                  <div className="mention-menu-list">
                    {filteredMentionSkills.map((skill, index) => {
                      const isSelected = index === mentionIndex;
                      const slug = skillToSlug(skill.name);
                      return (
                        <button
                          key={skill.id}
                          type="button"
                          role="option"
                          aria-selected={isSelected}
                          className={`mention-item ${isSelected ? "is-selected" : ""}`}
                          onMouseDown={event => {
                            event.preventDefault();
                            insertMention(skill);
                          }}
                          onMouseEnter={() => setMentionIndex(index)}
                        >
                          <span className="mention-item-handle">@{slug}</span>
                          <span className="mention-item-name">{skill.name}</span>
                          <span className="mention-item-prompt">{skill.prompt}</span>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mention-menu-empty">
                    <p>Aucune compétence ne correspond à <code>@{mentionQuery}</code>.</p>
                    <button
                      type="button"
                      className="mention-create-btn"
                      onMouseDown={event => {
                        event.preventDefault();
                        setMentionQuery(null);
                        setSkillsOpen(true);
                      }}
                    >
                      <Plus size={13} />
                      <span>Créer une compétence (@prof, @feynman…)</span>
                    </button>
                  </div>
                )}
              </div>
            )}

            <form className={`composer ${deepSearch ? "deepsearch-mode" : ""} ${learnMode ? "learn-mode" : ""} ${codeMode ? "codecanvas-mode" : ""} ${financeMode ? "finance-mode" : ""}`} onSubmit={event => void send(event)}>
              {deepSearch && (
                <div className="deepsearch-mode-label">
                  <Compass size={14} />
                  <span><strong>Mode DeepSearch</strong> · Exploration exhaustive sans limite de sources via SearXNG, recherche multi-vagues jusqu’à complétude, traduction et grand rapport d’analyse approfondi</span>
                  <button
                    type="button"
                    className="deepsearch-plan-btn"
                    onClick={() => {
                      if (!draft.trim()) {
                        setError("Saisissez d'abord votre question dans le champ pour préparer le plan de recherche.");
                        return;
                      }
                      setDeepSearchModalQuestion(draft.trim());
                      setDeepSearchModalTab("plan");
                      setDeepSearchModalReportId(null);
                      setDeepSearchModalOpen(true);
                    }}
                    title="Prévisualiser et modifier le plan de recherche avant de lancer"
                  >
                    <WandSparkles size={12} />
                    <span>Ajuster le plan</span>
                  </button>
                  <button
                    type="button"
                    className="deepsearch-plan-btn"
                    onClick={() => {
                      setDeepSearchModalQuestion(draft.trim());
                      setDeepSearchModalTab("reports");
                      setDeepSearchModalReportId(null);
                      setDeepSearchModalOpen(true);
                    }}
                    title="Consulter mes rapports DeepSearch et leurs pages HTML"
                  >
                    <BookOpen size={12} />
                    <span>Mes Rapports</span>
                  </button>
                  <button type="button" onClick={() => setDeepSearch(false)}>
                    <X size={12} />
                    Désactiver
                  </button>
                </div>
              )}
              {learnMode && (
                <div className="learn-mode-label">
                  <GraduationCap size={14} />
                  <span><strong>Mode Apprendre</strong> · Conception d’un cours complet et structuré multi-étapes avec plan pédagogique, cas pratiques et auto-évaluation</span>
                  <button
                    type="button"
                    className="learn-plan-btn"
                    onClick={() => {
                      if (!draft.trim()) {
                        setError("Saisissez d'abord votre sujet dans le champ pour préparer le plan du cours.");
                        return;
                      }
                      setLearnModalQuestion(draft.trim());
                      setLearnModalTab("plan");
                      setLearnModalReportId(null);
                      setLearnModalOpen(true);
                    }}
                    title="Prévisualiser et modifier le plan du cours avant de lancer"
                  >
                    <WandSparkles size={12} />
                    <span>Ajuster le plan</span>
                  </button>
                  <button
                    type="button"
                    className="learn-plan-btn"
                    onClick={() => {
                      setLearnModalQuestion(draft.trim());
                      setLearnModalTab("reports");
                      setLearnModalReportId(null);
                      setLearnModalOpen(true);
                    }}
                    title="Consulter mes cours et formations sauvegardés"
                  >
                    <BookOpen size={12} />
                    <span>Mes Cours</span>
                  </button>
                  <button type="button" onClick={() => setLearnMode(false)}>
                    <X size={12} />
                    Désactiver
                  </button>
                </div>
              )}
              {codeMode && <div className="codecanvas-mode-label"><Code2 size={14} /><span><strong>Mode Code · Canvas</strong> · L’éditeur multi-fichiers s’ouvre en direct avec aperçu web et téléchargement <code>.zip</code></span><button type="button" onClick={() => setCodeMode(false)}><X size={12} />Désactiver</button></div>}
              {financeMode && (
                <div className="finance-mode-label">
                  <TrendingUp size={14} />
                  <span><strong>Mode Finances & Bourse</strong> · Téléchargement automatique des cours et données financières (EOD Historical Data & Yahoo Finance) pour les entreprises ou tickers mentionnés</span>
                  <button type="button" className="finance-mode-modal-link" onClick={() => openFinanceModal()} title="Ouvrir le tableau de bord avec courbe de cours et tableaux financiers">
                    <LineChart size={12} />
                    <span>Tableau de bord</span>
                  </button>
                  <button type="button" onClick={() => setFinanceMode(false)}>
                    <X size={12} />
                    Désactiver
                  </button>
                </div>
              )}
              {multiAgentActive && multiAgentConfig && (
                <div className="multiagent-mode-label">
                  <Users size={14} />
                  <span>
                    <strong>Conseil Multi-Agents ({multiAgentConfig.mode === "synthesis" ? "🎯 Synthèse" : multiAgentConfig.mode === "debate" ? "🎙️ Table Ronde" : "⚔️ Débat Contradictoire"})</strong> ·{" "}
                    {multiAgentConfig.agents.map((ag) => `${ag.avatar} ${ag.name}`).join(" · ")}
                  </span>
                  <button type="button" className="config-link" onClick={() => setShowMultiAgentModal(true)}>
                    Modifier
                  </button>
                  <button type="button" onClick={() => setMultiAgentActive(false)}>
                    <X size={12} />
                    Désactiver
                  </button>
                </div>
              )}
              {!!attachments.length && <div className="pending-attachments">{attachments.map(item => {
                const isYoutube = item.filename.startsWith("🎬") || item.mime_type.includes("youtube");
                const isFinance = item.filename.startsWith("📈") || item.mime_type.includes("finance");
                const isWeb = item.mime_type.startsWith("text/html") || !!item.source_url || item.filename.startsWith("🌐");
                const isVision = item.analysis_mode === "vision";
                const isOcr = item.analysis_mode === "ocr";
                return <div className="pending-entry" key={item.id}><div className="pending-file">{isYoutube ? <SquarePlay size={15} color="#dc2626" /> : isFinance ? <TrendingUp size={15} color="#059669" /> : isWeb ? <Globe2 size={15} /> : isVision ? <Eye size={15} color="#7c3aed" /> : <FileText size={15} />}<span>{item.filename}</span>{isVision ? <span className="attachment-mode-tag mode-vision"><Eye size={10} /> Vision IA</span> : isOcr ? <span className="attachment-mode-tag mode-ocr"><FileText size={10} /> Mistral OCR</span> : null}<IconButton label={`Retirer ${item.filename}`} disabled={working} onClick={() => void removeAttachment(item.id)}><X size={13} /></IconButton></div><AttachmentAnalysis attachment={item} /></div>;
              })}</div>}
              <label className="sr-only" htmlFor="composer">Votre message</label>
              <textarea
                id="composer"
                ref={textareaRef}
                value={draft}
                onChange={event => {
                  const val = event.target.value;
                  setDraft(val);
                  const cursorPos = event.target.selectionStart ?? val.length;
                  const mention = findMentionQuery(val, cursorPos);
                  if (mention) {
                    setMentionQuery(mention.query);
                    setMentionIndex(0);
                  } else {
                    setMentionQuery(null);
                  }
                }}
                onKeyDown={composerKeyDown}
                placeholder={financeMode ? "Posez une question sur une entreprise, un ticker ou un indice (ex. Stellantis, Apple, LVMH, CAC 40)…" : codeMode ? "Décrivez l’application, le script ou le projet multi-fichiers à coder dans le Canvas…" : deepSearch ? "Quel sujet voulez-vous explorer en profondeur avec SearXNG ?" : learnMode ? "Sur quel sujet ou compétence souhaitez-vous concevoir un cours complet ?" : "Une question, une idée, ou tapez @ (ex. @prof, @feynman)…"}
                rows={2}
                maxLength={20000}
                disabled={working || !config}
                aria-describedby="composer-hint"
              />
              <div className="composer-toolbar"><div className="composer-tools"><div className="composer-attach-wrapper" ref={attachMenuRef}><input className="sr-only" type="file" ref={docInputRef} multiple accept=".txt,.md,.csv,.json,.pdf,.docx,image/png,image/jpeg,image/webp" onChange={event => void uploadFiles(event.target.files, "ocr")} tabIndex={-1} /><input className="sr-only" type="file" ref={visionInputRef} multiple accept="image/png,image/jpeg,image/webp" onChange={event => void uploadFiles(event.target.files, "vision")} tabIndex={-1} /><IconButton label="Joindre un document ou analyser une image" aria-expanded={attachMenuOpen} aria-haspopup="menu" disabled={working || !config} onMouseDown={e => e.stopPropagation()} onClick={e => { e.stopPropagation(); setAttachMenuOpen(prev => !prev); }}><Paperclip size={19} /></IconButton>{attachMenuOpen && <div className="composer-attach-popover" role="menu" onMouseDown={e => e.stopPropagation()}><div className="attach-popover-header"><span className="attach-popover-title">Joindre une pièce</span></div><button type="button" className="attach-popover-item" role="menuitem" onMouseDown={e => e.stopPropagation()} onClick={e => { e.stopPropagation(); docInputRef.current?.click(); setAttachMenuOpen(false); }}><span className="attach-popover-icon is-doc"><FileText size={17} /></span><div className="attach-popover-text"><span className="attach-item-title">Document (Mistral OCR)</span><span className="attach-item-desc">PDF, Word, scans, tableaux — extraction structurée & fidèle</span></div></button><button type="button" className="attach-popover-item" role="menuitem" onMouseDown={e => e.stopPropagation()} onClick={e => { e.stopPropagation(); visionInputRef.current?.click(); setAttachMenuOpen(false); }}><span className="attach-popover-icon is-vision"><Eye size={17} /></span><div className="attach-popover-text"><span className="attach-item-title">Image (Vision IA détaillée)</span><span className="attach-item-desc">Photos, infographies, schémas — analyse visuelle exhaustive</span></div></button></div>}</div><IconButton label="Analyser un lien web ou vidéo YouTube (URL)" disabled={working || !config} onClick={() => { setUrlError(""); setUrlInputValue(""); setShowUrlModal(true); }}><Link2 size={19} /></IconButton><span className="tool-divider" /><button type="button" className={`tool-button web-trigger ${effectiveWebMode !== "off" && !deepSearch && !learnMode ? "active" : ""} ${effectiveWebMode === "auto" && !deepSearch && !learnMode ? "web-auto" : ""} ${effectiveWebMode === "always" && !deepSearch && !learnMode ? "web-always" : ""} ${effectiveWebMode === "off" && !deepSearch && !learnMode ? "web-off" : ""}`} disabled={working || !isWebSearchAvailable} aria-pressed={effectiveWebMode !== "off" && !deepSearch && !learnMode} title={webSearchTooltip} aria-describedby={showDuckDuckGoNotice ? "web-search-hint" : undefined} onClick={() => { if (deepSearch || learnMode) { setDeepSearch(false); setLearnMode(false); setWebSearchMode("auto"); return; } setWebSearchMode(current => { if (current === "auto") return "always"; if (current === "always") return "off"; return "auto"; }); }}><Globe2 size={16} /><span>Web</span>{effectiveWebMode === "auto" && !deepSearch && !learnMode && <span className="auto-badge" title="Décision automatique par agent rapide">Auto</span>}{effectiveWebMode === "always" && !deepSearch && !learnMode && <Check size={12} />}</button><button type="button" className={`tool-button deepsearch-trigger ${deepSearch ? "active" : ""}`} disabled={working || !isWebSearchAvailable} aria-pressed={deepSearch} title={isWebSearchAvailable ? "DeepSearch : recherche large multi-requêtes via SearXNG et grand rapport d’analyse approfondi" : webSearchTooltip} onClick={() => { setDeepSearch(old => { if (!old) setLearnMode(false); return !old; }); }}><Compass size={16} /><span>DeepSearch</span>{deepSearch && <Check size={12} />}</button><button type="button" className={`tool-button learn-trigger ${learnMode ? "active" : ""}`} disabled={working || !isWebSearchAvailable} aria-pressed={learnMode} title={isWebSearchAvailable ? "Mode Apprendre : conception d'un cours complet et adapté au sujet avec plan pédagogique et supports" : webSearchTooltip} onClick={() => { setLearnMode(old => { if (!old) setDeepSearch(false); return !old; }); }}><GraduationCap size={16} /><span>Apprendre</span>{learnMode && <Check size={12} />}</button><button type="button" className={`tool-button codecanvas-trigger ${codeMode ? "active" : ""}`} disabled={working || !config} aria-pressed={codeMode} title="Mode Code Canvas : générer une application ou un projet multi-fichiers dans l’éditeur interactif avec téléchargement .zip" onClick={toggleCodeMode}><Code2 size={16} /><span>Code · Canvas</span>{codeMode && <Check size={12} />}</button><button type="button" className={`tool-button finance-trigger ${financeMode ? "active" : ""}`} disabled={working} aria-pressed={financeMode} title="Mode Finances & Bourse : télécharger automatiquement les cotations en direct (EOD) et les données financières (Yahoo Finance)" onClick={() => setFinanceMode(old => !old)}><TrendingUp size={16} /><span>Finances</span>{financeMode && <Check size={12} />}</button><button type="button" className="tool-button finance-chart-trigger" disabled={working} title="Ouvrir le tableau de bord boursier : courbe du cours EOD et statistiques financières complètes Yahoo" onClick={() => openFinanceModal()}><LineChart size={16} /><span>Courbe & Stats</span></button><button type="button" className={`tool-button multiagent-trigger ${multiAgentActive ? "active" : ""}`} disabled={working || !config} aria-pressed={multiAgentActive} title="Conseil Multi-Agents : orchestrer plusieurs modèles avec des personas dédiés (Synthèse d'experts ou Débat)" onClick={() => setShowMultiAgentModal(true)}><Users size={16} /><span>Conseil IA</span>{multiAgentActive && <Check size={12} />}</button><button type="button" className="tool-button studio-trigger" disabled={working} title="Ouvrir le Studio Image dédié (Ideogram, amélioration de prompt, visualisation et galerie)" onClick={() => openImageStudio(draft.trim())}><ImagePlus size={16} /><span>Studio Image</span></button><button type="button" className="tool-button sound-trigger" disabled={working} title="Ouvrir le Studio Son & Musique dédié (ElevenLabs Sound Effects & Eleven Music)" onClick={() => openSoundStudio(draft.trim())}><Volume2 size={16} /><span>Sons & Musique</span></button>{conversation && <button type="button" className={`tool-button study-trigger ${studyModalOpen ? "active" : ""}`} disabled={working} title="Générer des Flashcards ou un Quizz d'auto-évaluation sur les échanges du tchat" onClick={() => openStudyModal("flashcards")}><Brain size={16} /><span>Flash / Quizz</span></button>}</div><div className="composer-submit"><span className="enter-hint">↵ pour envoyer</span>{isCurrentStreaming ? <button className="send-button stop-button" type="button" onClick={stopCurrentStream} aria-label="Interrompre la génération" title="Interrompre la génération"><Square size={14} fill="currentColor" /></button> : <button className="send-button" type="submit" disabled={!canSend} aria-label="Envoyer le message">{busy === "upload" ? <LoaderCircle size={19} className="spin" /> : <ArrowUp size={20} />}</button>}</div></div>
            </form>
            <div className="composer-footnote" id="composer-hint"><span>cLAIr peut se tromper. Gardez un regard critique sur les réponses.</span><span>Maj + Entrée pour un saut de ligne</span></div>
          </div>
        </section>

        {canvasOpen && (
          <CodeCanvas
            title={conversation?.title || "Projet Canvas"}
            aiFiles={canvasFiles}
            streaming={Boolean(streamingId)}
            selectedPath={canvasSelectedPath}
            onSelectPath={setCanvasSelectedPath}
            onClose={() => setCanvasOpen(false)}
            onQuickPrompt={promptText => {
              setCodeMode(true);
              setDraft(promptText);
              textareaRef.current?.focus();
            }}
          />
        )}

        {contextOpen && <aside className="context-panel" id="context-panel" aria-label="Mémoire et contexte"><div className="context-heading"><div><span className="eyebrow">GARDER LE FIL</span><h2>Mémoire & contexte</h2></div><IconButton label="Fermer le panneau mémoire" onClick={() => setContextOpen(false)}><X size={18} /></IconButton></div><div className="context-tabs" role="tablist" aria-label="Contexte"><button id="summary-tab" type="button" role="tab" aria-selected={contextTab === "summary"} aria-controls="summary-panel" className={contextTab === "summary" ? "active" : ""} onClick={() => setContextTab("summary")}>Cette conversation</button><button id="memories-tab" type="button" role="tab" aria-selected={contextTab === "memories"} aria-controls="memories-panel" className={contextTab === "memories" ? "active" : ""} onClick={() => setContextTab("memories")}>Mes souvenirs <span>{memories.length}</span></button></div>
          {contextTab === "summary" ? <div className="context-content" role="tabpanel" id="summary-panel" aria-labelledby="summary-tab"><div className="context-info"><BookOpen size={19} /><h3>L’essentiel, au même endroit.</h3><p>Un résumé progressif aide l’IA à garder le contexte quand la conversation s’allonge.</p></div>{conversation?.summary ? <div className="summary-card markdown"><ReactMarkdown remarkPlugins={markdownRemarkPlugins} rehypePlugins={markdownRehypePlugins}>{normalizeMathMarkdown(conversation.summary)}</ReactMarkdown></div> : <div className="context-empty"><span className="empty-orbit"><BookOpen size={24} strokeWidth={1.2} /></span><strong>Chaque échange a son fil.</strong><p>{conversation ? "Le résumé apparaîtra ici lorsque cette conversation sera assez longue." : "Commencez une conversation pour retrouver son résumé ici."}</p></div>}<p className="context-explainer"><CircleAlert size={14} />Ce résumé est lié à cette conversation. Vos souvenirs, eux, peuvent enrichir tous vos échanges.</p></div> : <div className="context-content" role="tabpanel" id="memories-panel" aria-labelledby="memories-tab"><div className="context-info"><Brain size={20} /><h3>Les petites choses à retenir.</h3><p>Vos souvenirs s&apos;enrichissent soit automatiquement par l&apos;agent IA au fil des échanges, soit dès que vous lui dites <em>« note en mémoire que... »</em>. Vous gardez le contrôle total.</p></div><form className="memory-form" onSubmit={event => void saveMemory(event)}><label className="sr-only" htmlFor="memory-input">Nouvelle information à mémoriser</label><textarea id="memory-input" placeholder="Par exemple : je préfère des réponses courtes et concrètes." value={memoryDraft} onChange={event => setMemoryDraft(event.target.value)} disabled={working} maxLength={2000} rows={3} /><button type="submit" disabled={!memoryDraft.trim() || working}><Plus size={15} />Mémoriser</button></form>{memories.length ? <ul className="memory-list">{memories.map(memory => <li key={memory.id}><div><span className="memory-bullet" /><p>{memory.content}</p><IconButton label={`Oublier : ${memory.content.slice(0, 45)}`} disabled={working} onClick={() => void deleteMemory(memory.id)}><Trash2 size={14} /></IconButton></div><small>Ajouté le {shortDate(memory.created_at)}</small></li>)}</ul> : <div className="memory-empty"><Brain size={23} strokeWidth={1.3} /><p>Votre mémoire est encore une page blanche.</p></div>}<p className="context-explainer"><CircleAlert size={14} />Ces informations sont envoyées au modèle dans vos conversations. Vous pouvez les supprimer à tout moment.</p></div>}
        </aside>}
      </div>
    </main>

    {blogModalOpen && (
      <BlogModal
        initialPrompt={blogModalSeedPrompt}
        onClose={() => setBlogModalOpen(false)}
      />
    )}
    {modelModalOpen && (
      <ModelModal
        currentModel={model}
        models={config?.models ?? []}
        onSelectModel={async (selectedId) => {
          await changeModel(selectedId);
          setModelModalOpen(false);
        }}
        onClose={() => setModelModalOpen(false)}
        onRefreshModels={refreshModels}
      />
    )}
    {researchActivityMessage && <ResearchActivityModal
      run={researchRuns[researchActivityMessage.id]}
      sources={(researchActivityMessage.sources ?? []).filter(source => source.media_type !== "image" && !source.img_src && source.provider !== "searxng_images")}
      onClose={() => setResearchActivityMessageId(null)}
    />}
    {deepSearchModalOpen && (
      <DeepSearchModal
        isOpen={deepSearchModalOpen}
        question={deepSearchModalQuestion}
        conversationId={conversation?.id}
        initialTab={deepSearchModalTab}
        initialReportId={deepSearchModalReportId}
        models={config?.models ?? []}
        onRefreshModels={refreshModels}
        onClose={() => {
          setDeepSearchModalOpen(false);
          setDeepSearchModalReportId(null);
        }}
        onLaunch={async (finalQueries, _detailLevel, selectedModel, interactionId, planFeedback) => {
          await send(undefined, finalQueries, undefined, undefined, undefined, selectedModel, interactionId, planFeedback);
        }}
      />
    )}
    {learnModalOpen && (
      <LearnModal
        isOpen={learnModalOpen}
        question={learnModalQuestion}
        conversationId={conversation?.id}
        initialTab={learnModalTab}
        initialReportId={learnModalReportId}
        models={config?.models ?? []}
        stageModels={learnModeStageModels}
        onChangeStageModels={(cfg) => setLearnModeStageModels(cfg)}
        onRefreshModels={refreshModels}
        onClose={() => {
          setLearnModalOpen(false);
          setLearnModalReportId(null);
        }}
        onLaunch={async (finalQueries, _detailLevel, stageModels, selectedModel, interactionId, planFeedback) => {
          if (stageModels) setLearnModeStageModels(stageModels);
          await send(undefined, undefined, finalQueries, undefined, stageModels || learnModeStageModels, selectedModel, interactionId, planFeedback);
        }}
      />
    )}
    {imageStudioOpen && <ImageStudioModal config={config} initialPrompt={imageStudioPrompt} onClose={() => setImageStudioOpen(false)} />}
    {soundStudioOpen && (
      <SoundStudioModal
        config={config}
        initialPrompt={soundStudioPrompt}
        initialTab={soundStudioInitialTab}
        onClose={() => setSoundStudioOpen(false)}
        onSendToChat={(sound) => {
          const label = sound.sound_type === "music" ? "Musique" : "Effet sonore";
          const tag = `[${label} : ${sound.prompt}](${sound.url})`;
          setDraft(prev => prev ? `${prev}\n\n${tag}` : tag);
          setSoundStudioOpen(false);
          textareaRef.current?.focus();
        }}
      />
    )}
    {studyModalOpen && conversation && (
      <StudyModal
        isOpen={studyModalOpen}
        conversation={conversation}
        initialKind={studyModalKind}
        onClose={() => setStudyModalOpen(false)}
        onSendToChat={(content) => {
          setDraft((prev) => (prev ? `${prev}\n\n${content}` : content));
          textareaRef.current?.focus();
        }}
      />
    )}
    {adminOpen && user.is_admin && <AdminPanel currentUser={user} onClose={() => setAdminOpen(false)} />}
    {familyModalOpen && (
      <FamilyModal
        currentUser={user}
        familyInfo={familyInfo}
        onClose={() => setFamilyModalOpen(false)}
        onFamilyUpdated={setFamilyInfo}
        onSwitchAccount={switchAccount}
      />
    )}
    {settingsModalOpen && (
      <SettingsModal
        currentUser={user}
        isOpen={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        onSettingsUpdated={(updated) => {
          setUser(prev => prev ? { ...prev, ...updated } : prev);
        }}
      />
    )}
    <MultiAgentModal
      isOpen={showMultiAgentModal}
      onClose={() => setShowMultiAgentModal(false)}
      models={config?.models ?? []}
      defaultModel={model}
      activeConfig={multiAgentConfig}
      onApplyConfig={(cfg) => {
        if (cfg) {
          setMultiAgentConfig(cfg);
          setMultiAgentActive(true);
        } else {
          setMultiAgentActive(false);
        }
      }}
    />
    <FinanceModal
      isOpen={financeModalOpen}
      onClose={() => setFinanceModalOpen(false)}
      initialQuery={financeModalQuery}
      initialData={financeModalData}
      onInsertIntoChat={(promptText) => {
        setDraft(promptText);
        textareaRef.current?.focus();
      }}
    />
    {dialog && <div className="modal-backdrop" onClick={event => { if (event.target === event.currentTarget && !working) setDialog(null); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title" onKeyDown={event => { if (event.key === "Escape" && !working) setDialog(null); if (event.key === "Tab") { const elements = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)')); if (!elements.length) return; const first = elements[0]; const last = elements[elements.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } } }}><form onSubmit={event => void submitDialog(event)}><div className="modal-header"><span className="modal-icon">{dialog.type === "delete" ? <Trash2 size={20} /> : <Pencil size={20} />}</span><IconButton label="Fermer" disabled={working} onClick={() => setDialog(null)}><X size={18} /></IconButton></div><h2 id="dialog-title">{dialog.type === "delete" ? "Supprimer cette conversation ?" : "Organiser la discussion"}</h2>{dialog.type === "delete" ? <p>« {dialog.conversation.title} » et ses messages seront supprimés. Cette action est définitive.</p> : <div className="modal-fields"><div className="modal-field-header"><label htmlFor="rename-input">Titre de la conversation</label><button type="button" className="modal-ai-generate-btn" disabled={working} onClick={() => void classifyConversation(dialog.conversation.id, true)} title="Générer titre, thème et mots-clés avec Mistral Small">{busy === "classify" ? <LoaderCircle size={12} className="spin" /> : <WandSparkles size={12} />}<span>Générer en auto (IA)</span></button></div><input id="rename-input" value={renameValue} onChange={event => setRenameValue(event.target.value)} maxLength={200} autoFocus disabled={working} /><label htmlFor="theme-select">Thème</label><select id="theme-select" className="modal-select" value={renameTheme} onChange={event => setRenameTheme(event.target.value)} disabled={working}>{availableThemes.map(t => <option key={t} value={t}>{t}</option>)}</select><label htmlFor="keywords-input">Mots-clés (2 ou 3, séparés par des virgules)</label><input id="keywords-input" value={renameKeywords} onChange={event => setRenameKeywords(event.target.value)} placeholder="ex. santé, sommeil, récupération" maxLength={160} disabled={working} /></div>}<div className="modal-actions"><button type="button" className="secondary-button" disabled={working} onClick={() => setDialog(null)}>Annuler</button><button type="submit" className={dialog.type === "delete" ? "danger-button" : "primary-button"} disabled={working || (dialog.type === "rename" && !renameValue.trim())}>{working ? <LoaderCircle className="spin" size={15} /> : null}{dialog.type === "delete" ? "Supprimer" : "Enregistrer"}</button></div></form></section></div>}
    {showUrlModal && <div className="modal-backdrop" onClick={event => { if (event.target === event.currentTarget && !urlLoading) setShowUrlModal(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="url-dialog-title" onKeyDown={event => { if (event.key === "Escape" && !urlLoading) setShowUrlModal(false); }}><form onSubmit={event => void handleAttachUrl(event)}><div className="modal-header"><span className="modal-icon" style={{ background: "#fef2f2", color: "#dc2626" }}><SquarePlay size={20} /></span><IconButton label="Fermer" disabled={urlLoading} onClick={() => setShowUrlModal(false)}><X size={18} /></IconButton></div><h2 id="url-dialog-title">Analyser un lien web ou YouTube</h2><p>Entrez l’adresse d’un article, d’une page web ou d’une vidéo YouTube. Pour YouTube, les propos tenus dans la vidéo seront transcrits et analysés par l’assistant.</p><div className="modal-fields"><label htmlFor="url-input">Adresse URL</label><input id="url-input" type="url" value={urlInputValue} onChange={event => setUrlInputValue(event.target.value)} placeholder="https://exemple.fr/article ou https://youtu.be/..." autoFocus disabled={urlLoading} required /></div>{urlError && <div className="url-error-msg" role="alert"><CircleAlert size={14} /><span>{urlError}</span></div>}<div className="modal-actions"><button type="button" className="secondary-button" disabled={urlLoading} onClick={() => setShowUrlModal(false)}>Annuler</button><button type="submit" className="primary-button" disabled={urlLoading || !urlInputValue.trim()} style={{ background: "linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)" }}>{urlLoading ? <LoaderCircle className="spin" size={15} /> : null}{urlLoading ? "Extraction en cours…" : "Extraire et joindre"}</button></div></form></section></div>}

  </div>;
}
