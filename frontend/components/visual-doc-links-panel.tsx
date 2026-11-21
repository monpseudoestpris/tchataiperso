"use client";

import { useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  ExternalLink,
  FilePlus2,
  FileText,
  Globe,
  Link2,
  LoaderCircle,
  MessageSquare,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import {
  addVisualDocLinks,
  deleteVisualDocLink,
  errorMessage,
  refreshVisualDocLink,
  SUPPLEMENTARY_DOC_ROLES,
  uploadVisualDocSupplementaryFiles,
  type SupplementaryDocRoleId,
  type VisualDocDetail,
  type VisualDocExternalLink,
} from "@/lib/api";
import styles from "./visual-doc-links-panel.module.css";

export interface VisualDocLinksPanelProps {
  doc: VisualDocDetail;
  onDocUpdated: (updated: VisualDocDetail) => void;
  onError: (message: string) => void;
  onOpenInBookReader?: (linkId: string) => void;
  onOpenInMarkdown?: (linkId: string) => void;
}

function formatFileSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function getLinkKindMeta(link: VisualDocExternalLink): { label: string; emoji: string; badgeClass: string } {
  if (link.link_type === "document") {
    const roleObj = SUPPLEMENTARY_DOC_ROLES.find((r) => r.id === link.doc_role);
    return {
      label: link.doc_role_label || roleObj?.label || "Document complémentaire",
      emoji: roleObj?.emoji || "📄",
      badgeClass: styles.badgeDocument,
    };
  }
  if (link.link_type === "youtube") {
    return { label: "Vidéo YouTube", emoji: "🎬", badgeClass: styles.badgeYoutube };
  }
  if (link.link_type === "forum") {
    return { label: "Forum", emoji: "💬", badgeClass: styles.badgeForum };
  }
  return { label: "Site / FAQ", emoji: "🌐", badgeClass: styles.badgeSite };
}

export function VisualDocLinksPanel({
  doc,
  onDocUpdated,
  onError,
  onOpenInBookReader,
  onOpenInMarkdown,
}: VisualDocLinksPanelProps) {
  const [urlInput, setUrlInput] = useState("");
  const [customTitle, setCustomTitle] = useState("");
  const [adding, setAdding] = useState(false);

  const [suppRole, setSuppRole] = useState<SupplementaryDocRoleId>("faq_errata");
  const [suppTitle, setSuppTitle] = useState("");
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const suppFileInputRef = useRef<HTMLInputElement>(null);

  const [busyLinkId, setBusyLinkId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string>("");
  const [expandedTextIds, setExpandedTextIds] = useState<Record<string, boolean>>({});
  const [playingVideoIds, setPlayingVideoIds] = useState<Record<string, boolean>>({});

  const links: VisualDocExternalLink[] = Array.isArray(doc.external_links) ? doc.external_links : [];

  async function handleAddSubmit(e: React.FormEvent) {
    e.preventDefault();
    const parsedUrls = urlInput
      .split(/[\r\n,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!parsedUrls.length || adding) return;

    setAdding(true);
    setLocalError("");
    onError("");
    try {
      const updated = await addVisualDocLinks(doc.id, parsedUrls, customTitle.trim() || undefined);
      onDocUpdated(updated);
      setUrlInput("");
      setCustomTitle("");
    } catch (err) {
      const msg = errorMessage(err);
      setLocalError(msg);
      onError(msg);
    } finally {
      setAdding(false);
    }
  }

  async function handleUploadSuppFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0 || uploadingFiles) return;
    const filesArr = Array.from(fileList);
    setUploadingFiles(true);
    setLocalError("");
    onError("");
    try {
      const updated = await uploadVisualDocSupplementaryFiles(doc.id, {
        files: filesArr,
        docRole: suppRole,
        title: suppTitle.trim() || undefined,
      });
      onDocUpdated(updated);
      setSuppTitle("");
    } catch (err) {
      const msg = errorMessage(err);
      setLocalError(msg);
      onError(msg);
    } finally {
      setUploadingFiles(false);
      if (suppFileInputRef.current) {
        suppFileInputRef.current.value = "";
      }
    }
  }

  async function handleRefresh(linkId: string) {
    if (busyLinkId) return;
    setBusyLinkId(linkId);
    onError("");
    try {
      const updated = await refreshVisualDocLink(doc.id, linkId);
      onDocUpdated(updated);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusyLinkId(null);
    }
  }

  async function handleDelete(linkId: string) {
    if (busyLinkId) return;
    setBusyLinkId(linkId);
    onError("");
    try {
      const updated = await deleteVisualDocLink(doc.id, linkId);
      onDocUpdated(updated);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusyLinkId(null);
    }
  }

  return (
    <div className={styles.panelWrap}>
      <input
        ref={suppFileInputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp"
        style={{ display: "none" }}
        onChange={(e) => {
          void handleUploadSuppFiles(e.target.files);
        }}
      />

      {localError && (
        <div className={styles.localErrorBox} role="alert">
          <CircleAlert size={15} />
          <span>{localError}</span>
        </div>
      )}

      {/* 1. Carte d'ajout de Documents complémentaires (FAQ, Errata, Extension, Aide de jeu, Annexe) */}
      <div className={styles.addCard}>
        <div className={styles.addCardHeader}>
          <div className={styles.addCardTitle}>
            <FilePlus2 size={15} />
            <strong>Ajouter un document complémentaire (FAQ, Errata, Aide de jeu, Extension, Annexe)</strong>
          </div>
          <span className={styles.addCardHint}>
            PDF, Word, Markdown, Texte ou Image — OCR &amp; résumé automatique (prioritaire en cas d&apos;erratum)
          </span>
        </div>

        <div className={styles.suppUploadRow}>
          <select
            className={styles.roleSelect}
            value={suppRole}
            onChange={(e) => setSuppRole(e.target.value as SupplementaryDocRoleId)}
            disabled={uploadingFiles}
            aria-label="Nature du document complémentaire"
          >
            {SUPPLEMENTARY_DOC_ROLES.map((r) => (
              <option key={r.id} value={r.id}>
                {r.emoji} {r.label}
              </option>
            ))}
          </select>
          <input
            type="text"
            className={styles.titleOptionalInput}
            value={suppTitle}
            onChange={(e) => setSuppTitle(e.target.value)}
            placeholder="Titre optionnel (ex : FAQ Officielle v1.3, Extension Perlas…)"
            maxLength={180}
            disabled={uploadingFiles}
          />
          <button
            type="button"
            className={styles.addSubmitBtn}
            disabled={uploadingFiles}
            onClick={() => suppFileInputRef.current?.click()}
          >
            {uploadingFiles ? <LoaderCircle size={15} className="spin" /> : <Upload size={15} />}
            <span>{uploadingFiles ? "Lecture OCR & Résumé…" : "Choisir fichier(s)…"}</span>
          </button>
        </div>
      </div>

      {/* 2. Formulaire d'ajout de liens externes (Forums, Sites, Vidéos YouTube) */}
      <form className={styles.addCard} onSubmit={(e) => void handleAddSubmit(e)}>
        <div className={styles.addCardHeader}>
          <div className={styles.addCardTitle}>
            <Link2 size={15} />
            <strong>Adjoindre un lien externe (Forum, Site web ou Vidéo YouTube)</strong>
          </div>
          <span className={styles.addCardHint}>
            Extraction automatique du fil / des sous-titres + résumé structuré
          </span>
        </div>

        <div className={styles.addInputsRow}>
          <input
            type="text"
            className={styles.urlInput}
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="https://boardgamegeek.com/thread/... ou https://www.youtube.com/watch?v=... (plusieurs URLs possibles)"
            disabled={adding}
          />
          <input
            type="text"
            className={styles.titleOptionalInput}
            value={customTitle}
            onChange={(e) => setCustomTitle(e.target.value)}
            placeholder="Titre personnalisé (optionnel)"
            maxLength={180}
            disabled={adding}
          />
          <button
            type="submit"
            className={styles.addSubmitBtn}
            disabled={!urlInput.trim() || adding}
          >
            {adding ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}
            <span>{adding ? "Extraction & Résumé…" : "Extraire & Résumer"}</span>
          </button>
        </div>
      </form>

      {/* Liste des documents complémentaires, forums, sites et vidéos rattachés */}
      {links.length === 0 ? (
        <div className={styles.emptyLinksState}>
          <div className={styles.emptyIconsRow}>
            <FileText size={22} />
            <MessageSquare size={22} />
            <Globe size={22} />
            <Play size={22} />
          </div>
          <h4>Aucun document complémentaire ni lien rattaché</h4>
          <p>
            Ajoutez à tout moment un PDF de <strong>FAQ / Errata</strong>, une <strong>aide de jeu</strong>, une règle d&apos;<strong>extension</strong>, un fil <strong>BoardGameGeek</strong> ou une <strong>vidéo YouTube</strong> explicative : tout est extrait, résumé et croisé automatiquement avec le document principal.
          </p>
        </div>
      ) : (
        <div className={styles.linksList}>
          {links.map((link) => {
            const meta = getLinkKindMeta(link);
            const isBusy = busyLinkId === link.id;
            const isExpanded = Boolean(expandedTextIds[link.id]);
            const isPlaying = Boolean(playingVideoIds[link.id]);
            const isDoc = link.link_type === "document";

            return (
              <article key={link.id} className={styles.linkCard}>
                <header className={styles.linkCardHeader}>
                  <div className={styles.linkCardMetaLeft}>
                    <span className={`${styles.kindBadge} ${meta.badgeClass}`}>
                      <span>{meta.emoji}</span>
                      <span>{meta.label}</span>
                    </span>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.linkCardTitle}
                      title={isDoc ? `Ouvrir ${link.filename || link.title}` : link.url}
                    >
                      <span>{link.title}</span>
                      <ExternalLink size={13} />
                    </a>
                    {link.author && <span className={styles.metaSubTag}>par {link.author}</span>}
                    {link.duration && <span className={styles.metaSubTag}>⏱ {link.duration}</span>}
                    {isDoc && link.page_count ? (
                      <span className={styles.metaSubTag}>
                        {link.page_count} p.{link.figure_count ? ` · ${link.figure_count} schéma${link.figure_count > 1 ? "s" : ""}` : ""}
                      </span>
                    ) : null}
                    {isDoc && link.file_size ? (
                      <span className={styles.metaSubTag}>{formatFileSize(link.file_size)}</span>
                    ) : null}
                    {(link.filename || link.domain) && (
                      <code className={styles.domainCode}>{link.filename || link.domain}</code>
                    )}
                  </div>

                  <div className={styles.linkCardActions}>
                    {isDoc && onOpenInBookReader && (
                      <button
                        type="button"
                        className={`${styles.miniActionBtn} ${styles.miniPrimaryBtn}`}
                        onClick={() => onOpenInBookReader(link.id)}
                        title="Ouvrir ce document complémentaire dans la Liseuse 3D (effet page qui se tourne)"
                      >
                        <BookOpen size={12} />
                        <span>Lire en Livre 3D</span>
                      </button>
                    )}
                    {isDoc && onOpenInMarkdown && (
                      <button
                        type="button"
                        className={styles.miniActionBtn}
                        onClick={() => onOpenInMarkdown(link.id)}
                        title="Afficher le Markdown compilé de ce document complémentaire"
                      >
                        <FileText size={12} />
                        <span>Markdown compilé</span>
                      </button>
                    )}
                    {link.video_id && (
                      <button
                        type="button"
                        className={styles.miniActionBtn}
                        onClick={() =>
                          setPlayingVideoIds((prev) => ({ ...prev, [link.id]: !prev[link.id] }))
                        }
                        title="Afficher ou masquer le lecteur YouTube intégré"
                      >
                        <Play size={12} />
                        <span>{isPlaying ? "Masquer vidéo" : "Voir la vidéo"}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className={styles.miniActionBtn}
                      disabled={isBusy}
                      onClick={() => void handleRefresh(link.id)}
                      title="Ré-analyser et actualiser le résumé"
                    >
                      <RefreshCw size={12} className={isBusy ? "spin" : ""} />
                      <span>Actualiser</span>
                    </button>
                    <button
                      type="button"
                      className={`${styles.miniActionBtn} ${styles.miniDangerBtn}`}
                      disabled={isBusy}
                      onClick={() => void handleDelete(link.id)}
                      title="Retirer cette ressource du document"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </header>

                {isPlaying && link.video_id && (
                  <div className={styles.youtubeEmbedBox}>
                    <iframe
                      src={`https://www.youtube-nocookie.com/embed/${link.video_id}`}
                      title={link.title}
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      className={styles.youtubeIframe}
                    />
                  </div>
                )}

                {/* Résumé IA stylisé */}
                <div className={styles.summarySection}>
                  <div className={styles.summaryProse}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {link.summary_markdown || "_Aucun résumé disponible._"}
                    </ReactMarkdown>
                  </div>
                </div>

                {/* Accordéon pour consulter la transcription ou le texte extrait complet */}
                {link.extracted_text && (
                  <div className={styles.rawExtractFooter}>
                    <button
                      type="button"
                      className={styles.expandToggleBtn}
                      onClick={() =>
                        setExpandedTextIds((prev) => ({ ...prev, [link.id]: !prev[link.id] }))
                      }
                    >
                      {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      <span>
                        {isExpanded
                          ? "Masquer le contenu source extrait"
                          : `Voir le texte / la transcription extraite (${(
                              link.extracted_chars ?? link.extracted_text.length
                            ).toLocaleString("fr-FR")} car.)`}
                      </span>
                    </button>
                    {isExpanded && (
                      <div className={styles.extractedSourceProse}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {link.extracted_text}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
