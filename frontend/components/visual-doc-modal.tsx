"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowDown,
  ArrowUp,
  AudioLines,
  BookOpen,
  Check,
  CircleAlert,
  Code2,
  Copy,
  Eye,
  FileImage,
  FileText,
  Globe,
  Image as ImageIcon,
  Layers,
  Link2,
  LoaderCircle,
  MessageSquare,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Unlink,
  Upload,
  X,
} from "lucide-react";
import {
  deleteVisualDoc,
  errorMessage,
  getVisualDoc,
  ingestVisualDoc,
  listVisualDocs,
  updateVisualDoc,
  VISUAL_DOC_CATEGORIES,
  type VisualDocCategoryId,
  type VisualDocDetail,
  type VisualDocSummary,
} from "@/lib/api";
import { VisualDocBookReader } from "./visual-doc-book-reader";
import { VisualDocLinksPanel } from "./visual-doc-links-panel";
import styles from "./visual-doc-modal.module.css";

export interface VisualDocModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeConversationId?: string | null;
  attachedDocIds: string[];
  onAttachToConversation?: (doc: VisualDocSummary) => Promise<void> | void;
  onDetachFromConversation?: (docId: string) => Promise<void> | void;
  onStartChatWithDoc: (doc: VisualDocSummary) => Promise<void> | void;
  onStartVoiceWithDoc?: (doc: VisualDocSummary) => Promise<void> | void;
  initialDocId?: string | null;
  initialTab?: "library" | "ingest";
  ocrEnabled?: boolean;
  demoMode?: boolean;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function guessCategoryFromName(name: string): VisualDocCategoryId | null {
  const low = name.toLowerCase();
  if (/\b(regles?|règles?|rulebook|rules|plateau|cartes|extension|bgg)\b/.test(low)) return "boardgame";
  if (/\b(jdr|ttrpg|donjons?|campagne|bestiaire|pathfinder|cthulhu)\b/.test(low)) return "rpg_lore";
  if (/\b(semestriel|trimestriel|annuel|urd|10-k|10-q|earnings|financier|bilan)\b/.test(low)) return "financial";
  if (/\b(arxiv|étude|etude|study|thesis|thèse|pubmed|preprint|scientifique)\b/.test(low)) return "scientific";
  if (/\b(contrat|bail|cgv|cgu|juridique|décret|decret|assurance)\b/.test(low)) return "legal";
  if (/\b(posologie|clinique|protocole|médical|medical|notice|patient)\b/.test(low)) return "medical";
  if (/\b(cours|chapitre|exercice|examen|corrigé|corrige|td|tp)\b/.test(low)) return "educational";
  if (/\b(datasheet|installation|câblage|cablage|firmware|api|manuel)\b/.test(low)) return "technical";
  return null;
}

function findCategorySpec(catId?: string) {
  return VISUAL_DOC_CATEGORIES.find((c) => c.id === catId) || VISUAL_DOC_CATEGORIES[VISUAL_DOC_CATEGORIES.length - 1];
}

export function VisualDocModal({
  isOpen,
  onClose,
  activeConversationId,
  attachedDocIds,
  onAttachToConversation,
  onDetachFromConversation,
  onStartChatWithDoc,
  onStartVoiceWithDoc,
  initialDocId = null,
  initialTab = "library",
  ocrEnabled = true,
  demoMode = false,
}: VisualDocModalProps) {
  const [tab, setTab] = useState<"library" | "ingest">(initialTab);
  const [docs, setDocs] = useState<VisualDocSummary[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(initialDocId);
  const [detail, setDetail] = useState<VisualDocDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailSubTab, setDetailSubTab] = useState<"book" | "links" | "figures" | "pages" | "markdown">("book");
  const [activeVolumeId, setActiveVolumeId] = useState<string | null>(null);
  const [markdownDraft, setMarkdownDraft] = useState("");
  const [markdownEditMode, setMarkdownEditMode] = useState(false);
  const [savingMd, setSavingMd] = useState(false);
  const [copiedMd, setCopiedMd] = useState(false);
  const [error, setError] = useState("");
  const [busyAction, setBusyAction] = useState(false);

  // État d'ingestion
  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [queuedSuppFiles, setQueuedSuppFiles] = useState<File[]>([]);
  const [titleInput, setTitleInput] = useState("");
  const [categoryInput, setCategoryInput] = useState<VisualDocCategoryId>("boardgame");
  const [queuedLinks, setQueuedLinks] = useState<string[]>([]);
  const [linkDraftInput, setLinkDraftInput] = useState("");
  const [enrichVision, setEnrichVision] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [zoomedAsset, setZoomedAsset] = useState<{ src: string; caption: string } | null>(null);

  const pdfInputRef = useRef<HTMLInputElement>(null);
  const imgInputRef = useRef<HTMLInputElement>(null);
  const suppIngestInputRef = useRef<HTMLInputElement>(null);

  // Aperçus miniatures temporaires pour la file d'images à ingérer
  const previewUrls = useMemo(
    () => queuedFiles.map((file) => (file.type.startsWith("image/") ? URL.createObjectURL(file) : null)),
    [queuedFiles],
  );
  useEffect(() => {
    return () => {
      for (const u of previewUrls) {
        if (u) URL.revokeObjectURL(u);
      }
    };
  }, [previewUrls]);

  // Chargement de la bibliothèque à l'ouverture
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    (async () => {
      setError("");
      setTab(initialTab);
      setLoadingList(true);
      try {
        const items = await listVisualDocs();
        if (cancelled) return;
        setDocs(items);
        if (initialDocId && items.some((d) => d.id === initialDocId)) {
          setSelectedDocId(initialDocId);
        } else if (items.length > 0 && !selectedDocId) {
          setSelectedDocId(items[0].id);
        } else if (items.length === 0) {
          setTab("ingest");
        }
      } catch (err) {
        if (!cancelled) setError(errorMessage(err));
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, initialDocId, initialTab]); // eslint-disable-line react-hooks/exhaustive-deps

  // Chargement du détail du document sélectionné
  useEffect(() => {
    if (!isOpen || !selectedDocId) return;
    let cancelled = false;
    (async () => {
      setLoadingDetail(true);
      try {
        const loaded = await getVisualDoc(selectedDocId);
        if (cancelled) return;
        setDetail(loaded);
        setActiveVolumeId(null);
        setMarkdownDraft(loaded.compiled_markdown || "");
        setDetailSubTab("book");
      } catch (err) {
        if (!cancelled) setError(errorMessage(err));
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, selectedDocId]);

  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        if (zoomedAsset) setZoomedAsset(null);
        else if (!ingesting) onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, zoomedAsset, ingesting, onClose]);

  const activeDetail = selectedDocId && detail?.id === selectedDocId ? detail : null;

  const supplementaryDocs = useMemo(() => {
    if (!activeDetail?.external_links) return [];
    return activeDetail.external_links.filter((l) => l.link_type === "document");
  }, [activeDetail]);

  const activeSuppDoc = useMemo(() => {
    if (!activeVolumeId) return null;
    return supplementaryDocs.find((s) => s.id === activeVolumeId) || null;
  }, [activeVolumeId, supplementaryDocs]);

  const displayedDoc = useMemo<VisualDocDetail | null>(() => {
    if (!activeDetail) return null;
    if (!activeSuppDoc) return activeDetail;
    const suppMd = activeSuppDoc.compiled_markdown || activeSuppDoc.extracted_text || activeSuppDoc.summary_markdown || "";
    const suppPages =
      Array.isArray(activeSuppDoc.pages) && activeSuppDoc.pages.length > 0
        ? activeSuppDoc.pages
        : [
            {
              page: 1,
              page_image: "",
              page_image_url: "",
              compiled_markdown: `## [p. 1]\n\n${suppMd}`,
              figures: [],
            },
          ];
    return {
      ...activeDetail,
      id: `${activeDetail.id}:${activeSuppDoc.id}`,
      title: `${activeSuppDoc.title}${activeSuppDoc.doc_role_label ? ` — ${activeSuppDoc.doc_role_label}` : ""}`,
      page_count: activeSuppDoc.page_count || suppPages.length,
      figure_count: activeSuppDoc.figure_count || suppPages.reduce((acc, p) => acc + (p.figures?.length || 0), 0),
      compiled_markdown: suppMd,
      pages: suppPages,
    };
  }, [activeDetail, activeSuppDoc]);

  const allFigures = useMemo(() => {
    if (!displayedDoc?.pages) return [];
    return displayedDoc.pages.flatMap((p) => (p.figures || []).map((fig) => ({ ...fig, page: p.page })));
  }, [displayedDoc]);

  if (!isOpen) return null;

  function addFiles(fileList: FileList | File[] | null) {
    if (!fileList) return;
    const incoming = Array.from(fileList);
    if (!incoming.length) return;
    setError("");

    const pdf = incoming.find((f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf");
    if (pdf) {
      setQueuedFiles([pdf]);
      const cleanedTitle = pdf.name.replace(/\.pdf$/i, "").replace(/[_-]+/g, " ").trim();
      if (!titleInput.trim()) {
        setTitleInput(cleanedTitle);
      }
      const guessed = guessCategoryFromName(cleanedTitle);
      if (guessed) setCategoryInput(guessed);
      return;
    }

    const images = incoming.filter((f) => /\.(png|jpe?g|webp)$/i.test(f.name) || f.type.startsWith("image/"));
    if (!images.length) {
      setError("Formats acceptés : 1 fichier PDF ou une série d'images PNG, JPEG ou WebP.");
      return;
    }
    setQueuedFiles((prev) => {
      const base = prev.length === 1 && prev[0].name.toLowerCase().endsWith(".pdf") ? [] : prev;
      return [...base, ...images].slice(0, 100);
    });
    if (images[0]) {
      const cleanedImgTitle = images[0].name.replace(/\.(png|jpe?g|webp)$/i, "").replace(/[_-]+/g, " ").trim();
      if (!titleInput.trim()) {
        setTitleInput(cleanedImgTitle);
      }
      const guessed = guessCategoryFromName(cleanedImgTitle);
      if (guessed) setCategoryInput(guessed);
    }
  }

  function moveQueuedFile(index: number, delta: -1 | 1) {
    setQueuedFiles((prev) => {
      const target = index + delta;
      if (target < 0 || target >= prev.length) return prev;
      const copy = [...prev];
      const [item] = copy.splice(index, 1);
      copy.splice(target, 0, item);
      return copy;
    });
  }

  function removeQueuedFile(index: number) {
    setQueuedFiles((prev) => prev.filter((_, idx) => idx !== index));
  }

  function addQueuedLinksFromDraft() {
    const incoming = linkDraftInput
      .split(/[\r\n,\s]+/)
      .map((u) => u.trim())
      .filter((u) => /^https?:\/\//i.test(u));
    if (!incoming.length) return;
    setQueuedLinks((prev) => Array.from(new Set([...prev, ...incoming])).slice(0, 25));
    setLinkDraftInput("");
  }

  async function handleIngestSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!queuedFiles.length || ingesting) return;
    setIngesting(true);
    setError("");
    const pendingDraftUrls = linkDraftInput
      .split(/[\r\n,\s]+/)
      .map((u) => u.trim())
      .filter((u) => /^https?:\/\//i.test(u));
    const allInitialLinks = Array.from(new Set([...queuedLinks, ...pendingDraftUrls])).slice(0, 25);
    try {
      const created = await ingestVisualDoc({
        files: queuedFiles,
        supplementaryFiles: queuedSuppFiles.length > 0 ? queuedSuppFiles : undefined,
        title: titleInput.trim() || undefined,
        docCategory: categoryInput,
        links: allInitialLinks.length > 0 ? allInitialLinks : undefined,
        enrichVision,
      });
      setDocs((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      setSelectedDocId(created.id);
      setDetail(created);
      setMarkdownDraft(created.compiled_markdown || "");
      setDetailSubTab("book");
      setQueuedFiles([]);
      setQueuedSuppFiles([]);
      setQueuedLinks([]);
      setLinkDraftInput("");
      setTitleInput("");
      setTab("library");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIngesting(false);
    }
  }

  async function handleSaveMarkdown() {
    if (!detail || savingMd) return;
    setSavingMd(true);
    setError("");
    try {
      const updated = await updateVisualDoc(detail.id, { compiled_markdown: markdownDraft });
      setDetail(updated);
      setDocs((prev) => prev.map((d) => (d.id === updated.id ? { ...d, ...updated } : d)));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSavingMd(false);
    }
  }

  async function handleChangeCategory(docId: string, nextCategory: string) {
    setError("");
    try {
      const updated = await updateVisualDoc(docId, { doc_category: nextCategory });
      setDetail(updated);
      setDocs((prev) => prev.map((d) => (d.id === updated.id ? { ...d, ...updated } : d)));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleDeleteDoc(docId: string) {
    if (busyAction) return;
    setBusyAction(true);
    setError("");
    try {
      await deleteVisualDoc(docId);
      const remaining = docs.filter((d) => d.id !== docId);
      setDocs(remaining);
      if (selectedDocId === docId) {
        setSelectedDocId(remaining[0]?.id ?? null);
        setDetail(null);
      }
      if (attachedDocIds.includes(docId) && onDetachFromConversation) {
        await onDetachFromConversation(docId);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyAction(false);
    }
  }

  const isSelectedAttached = Boolean(activeDetail && attachedDocIds.includes(activeDetail.id));

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="visual-doc-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !ingesting) onClose();
      }}
    >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <div className={styles.headerIcon}>
              <BookOpen size={20} />
            </div>
            <div>
              <h2 id="visual-doc-modal-title" className={styles.headerTitle}>
                Documents Illustrés · Règles &amp; Manuels (Mistral OCR)
              </h2>
              <p className={styles.headerSubtitle}>
                Compile un PDF ou une liste d&apos;images en Markdown enrichi avec schémas WebP cliquables et pages de secours `[p. X]`.
              </p>
            </div>
          </div>
          <div className={styles.headerRight}>
            <div className={styles.modeTabs} role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={tab === "library"}
                className={`${styles.modeTab} ${tab === "library" ? styles.modeTabActive : ""}`}
                onClick={() => setTab("library")}
                disabled={ingesting}
              >
                <Layers size={14} />
                <span>Bibliothèque ({docs.length})</span>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={tab === "ingest"}
                className={`${styles.modeTab} ${tab === "ingest" ? styles.modeTabActive : ""}`}
                onClick={() => setTab("ingest")}
                disabled={ingesting}
              >
                <Plus size={14} />
                <span>Ingérer un document</span>
              </button>
            </div>
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onClose}
              disabled={ingesting}
              aria-label="Fermer les documents illustrés"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {error && (
          <div className={styles.errorBanner} role="alert">
            <CircleAlert size={16} />
            <span>{error}</span>
          </div>
        )}

        {!ocrEnabled && !demoMode && (
          <div className={styles.errorBanner} role="status">
            <CircleAlert size={16} />
            <span>
              <code>MISTRAL_API_KEY</code> n&apos;est pas configurée côté serveur : configurez-la dans <code>.env</code> pour lancer l&apos;ingestion Mistral OCR.
            </span>
          </div>
        )}

        <div className={styles.body}>
          {tab === "ingest" ? (
            <form className={styles.ingestWrap} onSubmit={(e) => void handleIngestSubmit(e)}>
              <input
                ref={pdfInputRef}
                type="file"
                accept=".pdf,application/pdf"
                style={{ display: "none" }}
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <input
                ref={imgInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
                multiple
                style={{ display: "none" }}
                onChange={(e) => {
                  addFiles(e.target.files);
                  e.target.value = "";
                }}
              />

              <div
                className={`${styles.dropzone} ${dragActive ? styles.dropzoneActive : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragActive(true);
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragActive(false);
                  addFiles(e.dataTransfer.files);
                }}
                onClick={() => pdfInputRef.current?.click()}
              >
                <div className={styles.dropzoneIcon}>
                  <Upload size={22} />
                </div>
                <h3>Glissez un livret PDF ou une série de photos de pages</h3>
                <p>
                  Mistral OCR extrait le texte + chaque schéma en <code>.webp</code> avec description anatomique détaillée, et sauvegarde chaque page entière en secours.
                </p>
                <div className={styles.dropzoneActions} onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    className={styles.secondaryBtn}
                    disabled={ingesting}
                    onClick={() => pdfInputRef.current?.click()}
                  >
                    <FileText size={14} />
                    <span>Choisir un PDF</span>
                  </button>
                  <button
                    type="button"
                    className={styles.secondaryBtn}
                    disabled={ingesting}
                    onClick={() => imgInputRef.current?.click()}
                  >
                    <FileImage size={14} />
                    <span>Choisir une liste d&apos;images</span>
                  </button>
                </div>
              </div>

              {queuedFiles.length > 0 && (
                <div className={styles.selectedFiles}>
                  <div className={styles.selectedFilesHeader}>
                    <span>
                      {queuedFiles.length === 1 && queuedFiles[0].name.toLowerCase().endsWith(".pdf")
                        ? "PDF prêt à être compilé"
                        : `${queuedFiles.length} page${queuedFiles.length > 1 ? "s" : ""} image${queuedFiles.length > 1 ? "s" : ""} (ordre de lecture respecté)`}
                    </span>
                    <button
                      type="button"
                      className={styles.secondaryBtn}
                      disabled={ingesting}
                      onClick={() => setQueuedFiles([])}
                    >
                      Tout effacer
                    </button>
                  </div>
                  <div className={styles.fileQueue}>
                    {queuedFiles.map((file, idx) => (
                      <div key={`${file.name}-${idx}`} className={styles.fileRow}>
                        <span className={styles.filePageNum}>
                          {file.name.toLowerCase().endsWith(".pdf") ? "PDF" : `Page ${idx + 1}`}
                        </span>
                        {previewUrls[idx] ? (
                          <img src={previewUrls[idx]!} alt={file.name} className={styles.fileThumb} />
                        ) : (
                          <FileText size={18} />
                        )}
                        <span className={styles.fileName} title={file.name}>
                          {file.name}
                        </span>
                        <span className={styles.fileSize}>{formatBytes(file.size)}</span>
                        {queuedFiles.length > 1 && (
                          <div className={styles.fileRowBtns}>
                            <button
                              type="button"
                              className={styles.miniIconBtn}
                              disabled={idx === 0 || ingesting}
                              onClick={() => moveQueuedFile(idx, -1)}
                              title="Monter cette page"
                            >
                              <ArrowUp size={13} />
                            </button>
                            <button
                              type="button"
                              className={styles.miniIconBtn}
                              disabled={idx === queuedFiles.length - 1 || ingesting}
                              onClick={() => moveQueuedFile(idx, 1)}
                              title="Descendre cette page"
                            >
                              <ArrowDown size={13} />
                            </button>
                          </div>
                        )}
                        <button
                          type="button"
                          className={styles.miniIconBtn}
                          disabled={ingesting}
                          onClick={() => removeQueuedFile(idx)}
                          title="Retirer"
                        >
                          <X size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className={styles.categoryPickerBlock}>
                <div className={styles.categoryPickerHeader}>
                  <label>Type de document &amp; Forums spécialisés associés</label>
                  <span className={styles.categoryForumHint}>
                    <Globe size={12} />
                    <span>
                      Sources interrogées en renfort :{" "}
                      <strong>{findCategorySpec(categoryInput).forumLabel}</strong>
                    </span>
                  </span>
                </div>
                <div className={styles.categoryGrid} role="radiogroup" aria-label="Type de document">
                  {VISUAL_DOC_CATEGORIES.map((cat) => {
                    const active = categoryInput === cat.id;
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        role="radio"
                        aria-checked={active}
                        disabled={ingesting}
                        className={`${styles.categoryChip} ${active ? styles.categoryChipActive : ""}`}
                        onClick={() => setCategoryInput(cat.id)}
                        title={`${cat.label} — Forums : ${cat.forumLabel}`}
                      >
                        <span className={styles.categoryEmoji}>{cat.emoji}</span>
                        <span className={styles.categoryChipText}>
                          <strong>{cat.shortLabel}</strong>
                          <small>{cat.forumLabel}</small>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className={styles.formGrid}>
                <div className={styles.field}>
                  <label htmlFor="vdoc-title">Nom du document / jeu / étude (recommandé pour cibler les forums)</label>
                  <input
                    id="vdoc-title"
                    type="text"
                    className={styles.textInput}
                    value={titleInput}
                    onChange={(e) => setTitleInput(e.target.value)}
                    placeholder="Ex : Res Arcana, Wingspan, Air Liquide S1 2026, Étude CRISPR…"
                    maxLength={200}
                    disabled={ingesting}
                  />
                </div>
                <button
                  type="submit"
                  className={styles.primaryBtn}
                  disabled={!queuedFiles.length || ingesting}
                >
                  {ingesting ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}
                  <span>{ingesting ? "Compilation Mistral OCR + WebP…" : "Ingérer & Compiler"}</span>
                </button>
              </div>

              <div className={styles.ingestLinksBox}>
                <input
                  ref={suppIngestInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp"
                  style={{ display: "none" }}
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      const incoming = Array.from(e.target.files);
                      setQueuedSuppFiles((prev) => [...prev, ...incoming].slice(0, 15));
                    }
                    e.target.value = "";
                  }}
                />
                <div className={styles.categoryPickerHeader}>
                  <label htmlFor="vdoc-initial-links">
                    Documents complémentaires (FAQ, Errata, Extension…) &amp; Liens (Forums, YouTube) — Optionnel, ajoutable aussi après coup
                  </label>
                  <button
                    type="button"
                    className={styles.secondaryBtn}
                    disabled={ingesting}
                    onClick={() => suppIngestInputRef.current?.click()}
                  >
                    <Plus size={13} />
                    <span>Joindre FAQ / Doc (PDF, Word, MD…)</span>
                  </button>
                </div>
                <div className={styles.ingestLinksInputRow}>
                  <input
                    id="vdoc-initial-links"
                    type="text"
                    className={styles.textInput}
                    value={linkDraftInput}
                    onChange={(e) => setLinkDraftInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addQueuedLinksFromDraft();
                      }
                    }}
                    placeholder="Ou collez un lien BoardGameGeek, site ou vidéo YouTube (https://…) puis Entrée"
                    disabled={ingesting}
                  />
                  <button
                    type="button"
                    className={styles.secondaryBtn}
                    disabled={!linkDraftInput.trim() || ingesting}
                    onClick={addQueuedLinksFromDraft}
                  >
                    <Plus size={14} />
                    <span>Ajouter le lien</span>
                  </button>
                </div>
                {(queuedSuppFiles.length > 0 || queuedLinks.length > 0) && (
                  <div className={styles.queuedLinksPills}>
                    {queuedSuppFiles.map((sf, idx) => (
                      <span key={`sf-${sf.name}-${idx}`} className={styles.queuedLinkChip} title={sf.name}>
                        <span>📜</span>
                        <span className={styles.queuedLinkUrl}>
                          {sf.name} ({formatBytes(sf.size)})
                        </span>
                        <button
                          type="button"
                          onClick={() => setQueuedSuppFiles((prev) => prev.filter((_, i) => i !== idx))}
                          disabled={ingesting}
                          aria-label="Retirer ce document complémentaire"
                        >
                          <X size={12} />
                        </button>
                      </span>
                    ))}
                    {queuedLinks.map((u, idx) => {
                      const isYt = /youtube\.com|youtu\.be/i.test(u);
                      const isForum = /boardgamegeek|reddit|trictrac|cwowd|stackoverflow|stackexchange|forum|thread/i.test(u);
                      return (
                        <span key={u} className={styles.queuedLinkChip} title={u}>
                          <span>{isYt ? "🎬" : isForum ? "💬" : "🌐"}</span>
                          <span className={styles.queuedLinkUrl}>{u}</span>
                          <button
                            type="button"
                            onClick={() => setQueuedLinks((prev) => prev.filter((_, i) => i !== idx))}
                            disabled={ingesting}
                            aria-label="Retirer ce lien"
                          >
                            <X size={12} />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>

              <label className={styles.checkboxCard}>
                <input
                  type="checkbox"
                  checked={enrichVision}
                  onChange={(e) => setEnrichVision(e.target.checked)}
                  disabled={ingesting}
                />
                <span>
                  <strong>Enrichir les descriptions de schémas par Vision IA contextuelle (Recommandé)</strong>
                  <small>
                    Croise chaque figure découpée avec le texte OCR de sa page pour décrire finement symboles, repères (1)(2)(3), coûts et positions spatiales.
                  </small>
                </span>
              </label>

              {ingesting && (
                <div className={styles.ingestingBox} role="status">
                  <LoaderCircle size={22} className="spin" />
                  <div>
                    <strong>Ingestion en cours…</strong>
                    <p>
                      Rendu des pages complètes en WebP (`pypdfium2`), appel Mistral OCR avec extraction des figures et compilation du Markdown enrichi.
                    </p>
                  </div>
                </div>
              )}
            </form>
          ) : (
            <div className={styles.libraryLayout}>
              <aside className={styles.sidebarList} aria-label="Mes documents compilés">
                {loadingList ? (
                  <div className={styles.emptyState}>
                    <LoaderCircle size={20} className="spin" />
                    <span>Chargement…</span>
                  </div>
                ) : docs.length === 0 ? (
                  <div className={styles.emptyState}>
                    <BookOpen size={24} />
                    <p>Aucun document illustré compilé.</p>
                    <button type="button" className={styles.primaryBtn} onClick={() => setTab("ingest")}>
                      <Plus size={14} />
                      <span>Ingérer un premier document</span>
                    </button>
                  </div>
                ) : (
                  docs.map((doc) => {
                    const isLinked = attachedDocIds.includes(doc.id);
                    return (
                      <button
                        key={doc.id}
                        type="button"
                        className={`${styles.docCard} ${selectedDocId === doc.id ? styles.docCardActive : ""}`}
                        onClick={() => setSelectedDocId(doc.id)}
                      >
                        {doc.cover_url ? (
                          <img src={doc.cover_url} alt={doc.title} className={styles.docCover} loading="lazy" />
                        ) : (
                          <div className={styles.docCover} />
                        )}
                        <div className={styles.docCardInfo}>
                          <span className={styles.docCardTitle} title={doc.title}>
                            {doc.title}
                          </span>
                          <div className={styles.docCardMeta}>
                            <span className={styles.badge}>
                              {doc.page_count} p. · {doc.figure_count} schéma{doc.figure_count > 1 ? "s" : ""}
                              {(doc.link_count ?? 0) > 0 ? ` · ${doc.link_count} lien${(doc.link_count ?? 0) > 1 ? "s" : ""}` : ""}
                            </span>
                            {isLinked && <span className={`${styles.badge} ${styles.badgeLinked}`}>Actif ici</span>}
                          </div>
                          <div className={styles.docCardMeta}>
                            <span>
                              {findCategorySpec(doc.doc_category).emoji}{" "}
                              {doc.doc_category_label || findCategorySpec(doc.doc_category).shortLabel}
                            </span>
                            {doc.vision_enriched && <span>· Vision IA</span>}
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </aside>

              <section className={styles.detailPane}>
                {loadingDetail ? (
                  <div className={styles.emptyState}>
                    <LoaderCircle size={22} className="spin" />
                    <span>Chargement du document compilé…</span>
                  </div>
                ) : !activeDetail ? (
                  <div className={styles.emptyState}>
                    <BookOpen size={28} />
                    <p>Sélectionnez un document dans la bibliothèque ou ingérez un nouveau PDF / jeu d&apos;images.</p>
                  </div>
                ) : (
                  <>
                    <div className={styles.detailHeader}>
                      <div className={styles.detailTitleBlock}>
                        <h3>{activeDetail.title}</h3>
                        <div className={styles.detailSubMetaRow}>
                          <select
                            className={styles.categorySelectInline}
                            value={activeDetail.doc_category || "general"}
                            onChange={(e) => void handleChangeCategory(activeDetail.id, e.target.value)}
                            aria-label="Type du document illustré"
                            title="Changer le type du document et les forums spécialisés interrogés"
                          >
                            {VISUAL_DOC_CATEGORIES.map((cat) => (
                              <option key={cat.id} value={cat.id}>
                                {cat.emoji} {cat.shortLabel}
                              </option>
                            ))}
                          </select>
                          <small>
                            {activeDetail.page_count} page{activeDetail.page_count > 1 ? "s" : ""} ·{" "}
                            {activeDetail.figure_count} schéma{activeDetail.figure_count > 1 ? "s" : ""} ·{" "}
                            <span className={styles.forumInlinePill}>
                              <Globe size={11} />
                              <span>{activeDetail.forum_label || findCategorySpec(activeDetail.doc_category).forumLabel}</span>
                            </span>
                          </small>
                        </div>
                      </div>
                      <div className={styles.detailActions}>
                        <button
                          type="button"
                          className={styles.primaryBtn}
                          disabled={busyAction}
                          onClick={async () => {
                            setBusyAction(true);
                            try {
                              await onStartChatWithDoc(activeDetail);
                              onClose();
                            } finally {
                              setBusyAction(false);
                            }
                          }}
                        >
                          <MessageSquare size={14} />
                          <span>Poser des questions</span>
                        </button>
                        {onStartVoiceWithDoc && (
                          <button
                            type="button"
                            className={styles.secondaryBtn}
                            disabled={busyAction}
                            title="Interagir avec ce document en Mode Vocal Plein Écran (mains-libres + clavier)"
                            onClick={async () => {
                              setBusyAction(true);
                              try {
                                await onStartVoiceWithDoc(activeDetail);
                                onClose();
                              } finally {
                                setBusyAction(false);
                              }
                            }}
                          >
                            <AudioLines size={14} />
                            <span>Vocal Plein Écran</span>
                          </button>
                        )}
                        {activeConversationId && onAttachToConversation && onDetachFromConversation && (
                          <button
                            type="button"
                            className={styles.secondaryBtn}
                            disabled={busyAction}
                            onClick={async () => {
                              setBusyAction(true);
                              try {
                                if (isSelectedAttached) {
                                  await onDetachFromConversation(activeDetail.id);
                                } else {
                                  await onAttachToConversation(activeDetail);
                                }
                              } finally {
                                setBusyAction(false);
                              }
                            }}
                          >
                            {isSelectedAttached ? <Unlink size={14} /> : <Link2 size={14} />}
                            <span>{isSelectedAttached ? "Détacher du tchat" : "Lier au tchat actif"}</span>
                          </button>
                        )}
                        <button
                          type="button"
                          className={styles.dangerBtn}
                          disabled={busyAction}
                          onClick={() => void handleDeleteDoc(activeDetail.id)}
                          title="Supprimer ce document compilé et ses images WebP"
                        >
                          <Trash2 size={13} />
                          <span>Supprimer</span>
                        </button>
                      </div>
                    </div>

                    <div className={styles.subTabs}>
                      <button
                        type="button"
                        className={`${styles.subTab} ${detailSubTab === "book" ? styles.subTabActive : ""}`}
                        onClick={() => setDetailSubTab("book")}
                      >
                        📖 Liseuse 3D ({displayedDoc?.pages.length ?? activeDetail.pages.length} p.)
                      </button>
                      <button
                        type="button"
                        className={`${styles.subTab} ${detailSubTab === "links" ? styles.subTabActive : ""}`}
                        onClick={() => setDetailSubTab("links")}
                      >
                        📎 Docs, FAQ &amp; Liens ({activeDetail.external_links?.length ?? activeDetail.link_count ?? 0})
                      </button>
                      <button
                        type="button"
                        className={`${styles.subTab} ${detailSubTab === "figures" ? styles.subTabActive : ""}`}
                        onClick={() => setDetailSubTab("figures")}
                      >
                        Schémas extraits ({allFigures.length})
                      </button>
                      <button
                        type="button"
                        className={`${styles.subTab} ${detailSubTab === "pages" ? styles.subTabActive : ""}`}
                        onClick={() => setDetailSubTab("pages")}
                      >
                        Pages originales ({displayedDoc?.pages.filter((p) => Boolean(p.page_image_url)).length ?? activeDetail.pages.length})
                      </button>
                      <button
                        type="button"
                        className={`${styles.subTab} ${detailSubTab === "markdown" ? styles.subTabActive : ""}`}
                        onClick={() => setDetailSubTab("markdown")}
                      >
                        Markdown compilé
                      </button>
                    </div>

                    {supplementaryDocs.length > 0 && detailSubTab !== "links" && (
                      <div className={styles.volumeBar} role="tablist" aria-label="Choisir le volume à consulter">
                        <span className={styles.volumeBarLabel}>Volume affiché :</span>
                        <button
                          type="button"
                          role="tab"
                          aria-selected={!activeSuppDoc}
                          className={`${styles.volumePill} ${!activeSuppDoc ? styles.volumePillActive : ""}`}
                          onClick={() => setActiveVolumeId(null)}
                        >
                          <span>📘 {activeDetail.title}</span>
                          <small>{activeDetail.page_count} p.</small>
                        </button>
                        {supplementaryDocs.map((sDoc) => {
                          const isCurrent = activeSuppDoc?.id === sDoc.id;
                          return (
                            <button
                              key={sDoc.id}
                              type="button"
                              role="tab"
                              aria-selected={isCurrent}
                              className={`${styles.volumePill} ${isCurrent ? styles.volumePillActive : ""}`}
                              onClick={() => setActiveVolumeId(sDoc.id)}
                              title={sDoc.doc_role_label || sDoc.filename}
                            >
                              <span>📜 {sDoc.title}</span>
                              {sDoc.page_count ? <small>{sDoc.page_count} p.</small> : null}
                            </button>
                          );
                        })}
                      </div>
                    )}

                    <div className={`${styles.detailContent} ${detailSubTab === "book" ? styles.detailContentBook : ""}`}>
                      {detailSubTab === "book" && displayedDoc && (
                        <VisualDocBookReader
                          key={displayedDoc.id}
                          doc={displayedDoc}
                          onZoomImage={(asset) => setZoomedAsset(asset)}
                        />
                      )}

                      {detailSubTab === "links" && (
                        <VisualDocLinksPanel
                          doc={activeDetail}
                          onDocUpdated={(updated) => {
                            setDetail(updated);
                            setDocs((prev) => prev.map((d) => (d.id === updated.id ? { ...d, ...updated } : d)));
                          }}
                          onError={setError}
                          onOpenInBookReader={(linkId) => {
                            setActiveVolumeId(linkId);
                            setDetailSubTab("book");
                          }}
                          onOpenInMarkdown={(linkId) => {
                            setActiveVolumeId(linkId);
                            setMarkdownEditMode(false);
                            setDetailSubTab("markdown");
                          }}
                        />
                      )}

                      {detailSubTab === "figures" && (
                        allFigures.length === 0 ? (
                          <div className={styles.emptyState}>
                            <ImageIcon size={24} />
                            <p>
                              Aucun schéma isolé n&apos;a été découpé sur ce document. Les pages originales complètes restent disponibles dans l&apos;onglet « Pages originales » et via les citations <code>[p. X]</code>.
                            </p>
                          </div>
                        ) : (
                          <div className={styles.figuresGrid}>
                            {allFigures.map((fig) => (
                              <article key={fig.id} className={styles.figureCard}>
                                <button
                                  type="button"
                                  className={styles.figureImgBtn}
                                  onClick={() => setZoomedAsset({ src: fig.url, caption: fig.alt })}
                                  title="Cliquer pour agrandir ce schéma"
                                >
                                  <img src={fig.url} alt={fig.short_title} className={styles.figureImg} loading="lazy" />
                                </button>
                                <div className={styles.figureMeta}>
                                  <div className={styles.figureMetaTop}>
                                    <span className={styles.badge}>p. {fig.page}</span>
                                    <code>{fig.filename}</code>
                                  </div>
                                  <p className={styles.figureAlt}>{fig.alt}</p>
                                </div>
                              </article>
                            ))}
                          </div>
                        )
                      )}

                      {detailSubTab === "pages" && displayedDoc && (
                        displayedDoc.pages.some((p) => Boolean(p.page_image_url)) ? (
                          <div className={styles.pagesGrid}>
                            {displayedDoc.pages
                              .filter((p) => Boolean(p.page_image_url))
                              .map((p) => (
                                <button
                                  key={p.page}
                                  type="button"
                                  className={styles.pageCard}
                                  onClick={() =>
                                    setZoomedAsset({
                                      src: p.page_image_url,
                                      caption: `${displayedDoc.title} — Page ${p.page} (original de secours)`,
                                    })
                                  }
                                >
                                  <img
                                    src={p.page_image_url}
                                    alt={`Page ${p.page}`}
                                    className={styles.pageThumb}
                                    loading="lazy"
                                  />
                                  <div className={styles.pageLabel}>
                                    <span>Page {p.page}</span>
                                    <span>{p.figures.length} fig.</span>
                                  </div>
                                </button>
                              ))}
                          </div>
                        ) : (
                          <div className={styles.emptyState}>
                            <FileText size={24} />
                            <p>
                              Ce document complémentaire est au format texte/Word (sans planches PDF scannées). Utilisez l&apos;onglet <strong>📖 Liseuse 3D</strong> pour le feuilleter en livre ou <strong>Markdown compilé</strong> pour le lire d&apos;un bloc.
                            </p>
                          </div>
                        )
                      )}

                      {detailSubTab === "markdown" && displayedDoc && (
                        <div>
                          <div className={styles.markdownToolbar}>
                            <small>
                              {activeSuppDoc
                                ? `Markdown compilé du document complémentaire « ${activeSuppDoc.title} » (${displayedDoc.page_count} p.).`
                                : markdownEditMode
                                  ? "Mode édition source : vous pouvez modifier une description puis enregistrer."
                                  : "Rendu stylisé du document compilé (titres, gras, tableaux et descriptions anatomiques des images)."}
                            </small>
                            <div style={{ display: "flex", gap: 8 }}>
                              {!activeSuppDoc && (
                                <button
                                  type="button"
                                  className={styles.secondaryBtn}
                                  onClick={() => setMarkdownEditMode((v) => !v)}
                                >
                                  {markdownEditMode ? <Eye size={13} /> : <Code2 size={13} />}
                                  <span>{markdownEditMode ? "Vue stylisée" : "Éditer le code source"}</span>
                                </button>
                              )}
                              <button
                                type="button"
                                className={styles.secondaryBtn}
                                onClick={() => {
                                  const toCopy = activeSuppDoc ? displayedDoc.compiled_markdown : markdownDraft;
                                  navigator.clipboard?.writeText(toCopy).then(() => {
                                    setCopiedMd(true);
                                    setTimeout(() => setCopiedMd(false), 1800);
                                  });
                                }}
                              >
                                {copiedMd ? <Check size={13} /> : <Copy size={13} />}
                                <span>{copiedMd ? "Copié" : "Copier"}</span>
                              </button>
                              {!activeSuppDoc && markdownEditMode && (
                                <button
                                  type="button"
                                  className={styles.primaryBtn}
                                  disabled={savingMd || markdownDraft === activeDetail.compiled_markdown}
                                  onClick={() => void handleSaveMarkdown()}
                                >
                                  {savingMd ? <LoaderCircle size={14} className="spin" /> : <Save size={14} />}
                                  <span>Enregistrer</span>
                                </button>
                              )}
                            </div>
                          </div>
                          {!activeSuppDoc && markdownEditMode ? (
                            <textarea
                              className={styles.markdownEditor}
                              value={markdownDraft}
                              onChange={(e) => setMarkdownDraft(e.target.value)}
                              spellCheck={false}
                            />
                          ) : (
                            <div className={styles.styledMarkdownDoc}>
                              <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                  img: ({ src, alt }) => {
                                    const imgSrc = typeof src === "string" ? src : "";
                                    const imgAlt = alt || "Illustration";
                                    if (!imgSrc) return null;
                                    const shortTitle =
                                      imgAlt.split(" : ")[0]?.split(" — ")[0]?.slice(0, 120) || "Illustration";
                                    return (
                                      <aside className={styles.styledDocFigureCard}>
                                        <button
                                          type="button"
                                          className={styles.styledDocFigureThumbBtn}
                                          onClick={() => setZoomedAsset({ src: imgSrc, caption: imgAlt })}
                                          title="Cliquer pour agrandir"
                                        >
                                          <img
                                            src={imgSrc}
                                            alt={shortTitle}
                                            className={styles.styledDocFigureThumb}
                                            loading="lazy"
                                          />
                                        </button>
                                        <div className={styles.styledDocFigureBody}>
                                          <strong className={styles.styledDocFigureTitle}>{shortTitle}</strong>
                                          <p className={styles.styledDocFigureDesc}>{imgAlt}</p>
                                        </div>
                                      </aside>
                                    );
                                  },
                                }}
                              >
                                {activeSuppDoc ? displayedDoc.compiled_markdown : markdownDraft}
                              </ReactMarkdown>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </section>
            </div>
          )}
        </div>
      </div>

      {zoomedAsset && (
        <div
          className={styles.zoomOverlay}
          role="dialog"
          aria-modal="true"
          onClick={() => setZoomedAsset(null)}
        >
          <img src={zoomedAsset.src} alt={zoomedAsset.caption} className={styles.zoomImg} />
          <p className={styles.zoomCaption}>{zoomedAsset.caption}</p>
        </div>
      )}
    </div>
  );
}
