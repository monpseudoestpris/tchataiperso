"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  AudioLines,
  BookOpen,
  Check,
  CircleAlert,
  Copy,
  FileImage,
  FileText,
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
  type VisualDocDetail,
  type VisualDocSummary,
} from "@/lib/api";
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
  const [detailSubTab, setDetailSubTab] = useState<"figures" | "pages" | "markdown">("figures");
  const [markdownDraft, setMarkdownDraft] = useState("");
  const [savingMd, setSavingMd] = useState(false);
  const [copiedMd, setCopiedMd] = useState(false);
  const [error, setError] = useState("");
  const [busyAction, setBusyAction] = useState(false);

  // État d'ingestion
  const [queuedFiles, setQueuedFiles] = useState<File[]>([]);
  const [titleInput, setTitleInput] = useState("");
  const [enrichVision, setEnrichVision] = useState(true);
  const [ingesting, setIngesting] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [zoomedAsset, setZoomedAsset] = useState<{ src: string; caption: string } | null>(null);

  const pdfInputRef = useRef<HTMLInputElement>(null);
  const imgInputRef = useRef<HTMLInputElement>(null);

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
        setMarkdownDraft(loaded.compiled_markdown || "");
        setDetailSubTab(loaded.figure_count > 0 ? "figures" : "pages");
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

  const allFigures = useMemo(() => {
    if (!activeDetail?.pages) return [];
    return activeDetail.pages.flatMap((p) => (p.figures || []).map((fig) => ({ ...fig, page: p.page })));
  }, [activeDetail]);

  if (!isOpen) return null;

  function addFiles(fileList: FileList | File[] | null) {
    if (!fileList) return;
    const incoming = Array.from(fileList);
    if (!incoming.length) return;
    setError("");

    const pdf = incoming.find((f) => f.name.toLowerCase().endsWith(".pdf") || f.type === "application/pdf");
    if (pdf) {
      setQueuedFiles([pdf]);
      if (!titleInput.trim()) {
        setTitleInput(pdf.name.replace(/\.pdf$/i, "").replace(/[_-]+/g, " ").trim());
      }
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
    if (!titleInput.trim() && images[0]) {
      setTitleInput(images[0].name.replace(/\.(png|jpe?g|webp)$/i, "").replace(/[_-]+/g, " ").trim());
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

  async function handleIngestSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!queuedFiles.length || ingesting) return;
    setIngesting(true);
    setError("");
    try {
      const created = await ingestVisualDoc({
        files: queuedFiles,
        title: titleInput.trim() || undefined,
        enrichVision,
      });
      setDocs((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      setSelectedDocId(created.id);
      setDetail(created);
      setMarkdownDraft(created.compiled_markdown || "");
      setDetailSubTab(created.figure_count > 0 ? "figures" : "pages");
      setQueuedFiles([]);
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

              <div className={styles.formGrid}>
                <div className={styles.field}>
                  <label htmlFor="vdoc-title">Nom du document / jeu (optionnel)</label>
                  <input
                    id="vdoc-title"
                    type="text"
                    className={styles.textInput}
                    value={titleInput}
                    onChange={(e) => setTitleInput(e.target.value)}
                    placeholder="Ex : Catan — Règles de base, Wingspan, Manuel chaudière…"
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
                            </span>
                            {isLinked && <span className={`${styles.badge} ${styles.badgeLinked}`}>Actif ici</span>}
                          </div>
                          <div className={styles.docCardMeta}>
                            <span>{doc.source_type === "images" ? "Liste d'images" : "PDF"}</span>
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
                        <small>
                          <code>/api/docs/{activeDetail.slug}/</code> · {activeDetail.page_count} page{activeDetail.page_count > 1 ? "s" : ""} ·{" "}
                          {activeDetail.figure_count} schéma{activeDetail.figure_count > 1 ? "s" : ""} WebP
                        </small>
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
                        Pages originales ({activeDetail.pages.length})
                      </button>
                      <button
                        type="button"
                        className={`${styles.subTab} ${detailSubTab === "markdown" ? styles.subTabActive : ""}`}
                        onClick={() => setDetailSubTab("markdown")}
                      >
                        Markdown compilé
                      </button>
                    </div>

                    <div className={styles.detailContent}>
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

                      {detailSubTab === "pages" && (
                        <div className={styles.pagesGrid}>
                          {activeDetail.pages.map((p) => (
                            <button
                              key={p.page}
                              type="button"
                              className={styles.pageCard}
                              onClick={() =>
                                setZoomedAsset({
                                  src: p.page_image_url,
                                  caption: `${activeDetail.title} — Page ${p.page} (original de secours)`,
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
                      )}

                      {detailSubTab === "markdown" && (
                        <div>
                          <div className={styles.markdownToolbar}>
                            <small>
                              Vous pouvez affiner manuellement une description <code>![...](...)</code> puis enregistrer.
                            </small>
                            <div style={{ display: "flex", gap: 8 }}>
                              <button
                                type="button"
                                className={styles.secondaryBtn}
                                onClick={() => {
                                  navigator.clipboard?.writeText(markdownDraft).then(() => {
                                    setCopiedMd(true);
                                    setTimeout(() => setCopiedMd(false), 1800);
                                  });
                                }}
                              >
                                {copiedMd ? <Check size={13} /> : <Copy size={13} />}
                                <span>{copiedMd ? "Copié" : "Copier"}</span>
                              </button>
                              <button
                                type="button"
                                className={styles.primaryBtn}
                                disabled={savingMd || markdownDraft === activeDetail.compiled_markdown}
                                onClick={() => void handleSaveMarkdown()}
                              >
                                {savingMd ? <LoaderCircle size={14} className="spin" /> : <Save size={14} />}
                                <span>Enregistrer</span>
                              </button>
                            </div>
                          </div>
                          <textarea
                            className={styles.markdownEditor}
                            value={markdownDraft}
                            onChange={(e) => setMarkdownDraft(e.target.value)}
                            spellCheck={false}
                          />
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
