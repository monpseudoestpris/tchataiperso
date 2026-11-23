"use client";

import {
  BookOpen,
  Brain,
  Check,
  CircleAlert,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Film,
  GraduationCap,
  Languages,
  ListOrdered,
  LoaderCircle,
  MessageSquare,
  Pencil,
  Play,
  Plus,
  Search,
  Sparkles,
  SquarePlay,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  attachSavedVideoToChat,
  deleteSavedVideo,
  errorMessage,
  fetchSavedVideo,
  fetchSavedVideos,
  generateSavedVideoAnalysis,
  importSavedVideo,
  updateSavedVideo,
  type Attachment,
  type SavedVideoDetail,
  type SavedVideoSummary,
} from "@/lib/api";
import {
  YOUTUBE_TRANSCRIPT_ACTIONS,
  type YoutubeTranscriptAction,
} from "@/lib/youtube-actions";
import styles from "./video-library-modal.module.css";

type ImportActionOption = "none" | YoutubeTranscriptAction | "custom";

function formatShortDate(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("fr-FR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

function ActionMiniIcon({ id }: { id: YoutubeTranscriptAction }) {
  switch (id) {
    case "analyze":
      return <Brain size={13} />;
    case "key_points":
      return <ListOrdered size={13} />;
    case "study":
      return <GraduationCap size={13} />;
    case "translate_fr":
      return <Languages size={13} />;
    case "summarize":
    default:
      return <Sparkles size={13} />;
  }
}

export function VideoLibraryModal({
  open,
  defaultModel,
  onClose,
  onAttachToChat,
  onCountChange,
}: {
  open: boolean;
  defaultModel?: string;
  onClose: () => void;
  onAttachToChat: (attachment: Attachment) => void;
  onCountChange?: (count: number) => void;
}) {
  const [videos, setVideos] = useState<SavedVideoSummary[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SavedVideoDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const [activeTab, setActiveTab] = useState<"summary" | "transcript">("summary");
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [rawTranscript, setRawTranscript] = useState(true);
  const [transcriptFilter, setTranscriptFilter] = useState("");
  const [showEmbed, setShowEmbed] = useState(false);

  const [showImportBar, setShowImportBar] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [importAction, setImportAction] = useState<ImportActionOption>("summarize");
  const [importCustomPrompt, setImportCustomPrompt] = useState("");
  const [importing, setImporting] = useState(false);

  const [generatingAction, setGeneratingAction] = useState<string | null>(null);
  const [customActionDraft, setCustomActionDraft] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  const [renaming, setRenaming] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const [attaching, setAttaching] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const loadList = useCallback(
    async (keepSelectionId?: string | null) => {
      setListLoading(true);
      setError("");
      try {
        const items = await fetchSavedVideos();
        setVideos(items);
        onCountChange?.(items.length);
        const preferred = keepSelectionId !== undefined ? keepSelectionId : selectedId;
        if (preferred && items.some((v) => v.id === preferred)) {
          setSelectedId(preferred);
        } else {
          setSelectedId(items[0]?.id ?? null);
        }
      } catch (err) {
        setError(errorMessage(err));
      } finally {
        setListLoading(false);
      }
    },
    [onCountChange, selectedId],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetchSavedVideos()
      .then((items) => {
        if (cancelled) return;
        setVideos(items);
        setError("");
        onCountChange?.(items.length);
        setSelectedId((prev) =>
          prev && items.some((v) => v.id === prev) ? prev : (items[0]?.id ?? null),
        );
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, onCountChange]);

  useEffect(() => {
    if (!open || !selectedId) return;
    let cancelled = false;
    void fetchSavedVideo(selectedId)
      .then((loaded) => {
        if (cancelled) return;
        setDetail(loaded);
        setError("");
        setShowEmbed(false);
        setRenaming(false);
        setSelectedAnalysisId(null);
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, selectedId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && !importing && !generatingAction) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, importing, generatingAction, onClose]);

  const filteredVideos = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return videos;
    return videos.filter(
      (v) =>
        v.title.toLowerCase().includes(q) ||
        v.author.toLowerCase().includes(q) ||
        v.url.toLowerCase().includes(q),
    );
  }, [videos, searchQuery]);

  const filteredTranscriptInfo = useMemo(() => {
    const full = detail?.transcript_markdown || "";
    const q = transcriptFilter.trim();
    if (!q) return { text: full, matchCount: 0 };
    const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const matches = full.match(new RegExp(escaped, "gi"));
    const lines = full
      .split("\n")
      .filter((line) => line.toLowerCase().includes(q.toLowerCase()));
    return {
      text: lines.length > 0 ? lines.join("\n\n") : `Aucune occurrence trouvée pour « ${q} ».`,
      matchCount: matches ? matches.length : 0,
    };
  }, [detail?.transcript_markdown, transcriptFilter]);

  if (!open) return null;

  async function handleCopy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey((old) => (old === key ? null : old)), 1800);
    } catch {
      /* ignore clipboard error */
    }
  }

  function handleDownloadTranscript(video: SavedVideoDetail) {
    const slug =
      video.title
        .replace(/[^a-zA-Z0-9\u00C0-\u017F_-]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 80) || "transcript-youtube";
    const blob = new Blob([video.transcript_markdown || ""], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${slug}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function handleImportSubmit(event: FormEvent) {
    event.preventDefault();
    const clean = importUrl.trim();
    if (!clean || importing) return;
    if (importAction === "custom" && !importCustomPrompt.trim()) return;
    setImporting(true);
    setError("");
    try {
      const created = await importSavedVideo({
        url: clean,
        action: importAction,
        custom_prompt: importCustomPrompt.trim(),
        model: defaultModel || undefined,
      });
      setImportUrl("");
      setImportCustomPrompt("");
      setShowImportBar(false);
      setDetail(created);
      setSelectedId(created.id);
      setActiveTab(created.has_summary ? "summary" : "transcript");
      await loadList(created.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setImporting(false);
    }
  }

  async function handleGenerateAnalysis(action: YoutubeTranscriptAction | "custom", customPromptText = "") {
    if (!detail || generatingAction) return;
    if (action === "custom" && !customPromptText.trim()) return;
    setGeneratingAction(action);
    setError("");
    try {
      const updated = await generateSavedVideoAnalysis(detail.id, {
        action,
        custom_prompt: customPromptText.trim(),
        model: defaultModel || undefined,
      });
      setDetail(updated);
      setSelectedAnalysisId(updated.analyses[0]?.id ?? null);
      setActiveTab("summary");
      setShowCustomInput(false);
      setCustomActionDraft("");
      setVideos((old) =>
        old.map((v) =>
          v.id === updated.id
            ? {
                ...v,
                has_summary: updated.has_summary,
                summary_action: updated.summary_action,
                summary_preview: updated.summary_preview,
                analyses_count: updated.analyses_count,
                updated_at: updated.updated_at,
              }
            : v,
        ),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGeneratingAction(null);
    }
  }

  async function handleCommitRename(event: FormEvent) {
    event.preventDefault();
    if (!detail || !renameDraft.trim()) return;
    setError("");
    try {
      const updated = await updateSavedVideo(detail.id, { title: renameDraft.trim() });
      setDetail(updated);
      setRenaming(false);
      setVideos((old) => old.map((v) => (v.id === updated.id ? { ...v, title: updated.title } : v)));
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleAttachToChat() {
    if (!detail || attaching) return;
    setAttaching(true);
    setError("");
    try {
      const att = await attachSavedVideoToChat(detail.id);
      onAttachToChat(att);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAttaching(false);
    }
  }

  async function handleDeleteVideo() {
    if (!detail || deleting) return;
    if (!window.confirm(`Supprimer « ${detail.title} » de votre espace Mes Vidéos ?`)) return;
    setDeleting(true);
    setError("");
    try {
      await deleteSavedVideo(detail.id);
      const remaining = videos.filter((v) => v.id !== detail.id);
      setVideos(remaining);
      onCountChange?.(remaining.length);
      setSelectedId(remaining[0]?.id ?? null);
      if (remaining.length === 0) setDetail(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  const activeDetail = selectedId && detail?.id === selectedId ? detail : null;
  const activeAnalysis =
    activeDetail?.analyses?.find((a) => a.id === selectedAnalysisId) ||
    activeDetail?.analyses?.[0] ||
    null;
  const displayedSummary = activeAnalysis?.markdown || activeDetail?.summary_markdown || "";

  return (
    <div
      className={styles.backdrop}
      onClick={(event) => {
        if (event.target === event.currentTarget && !importing && !generatingAction) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="video-library-title"
    >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>
              <Film size={20} />
            </span>
            <div>
              <h2 id="video-library-title" className={styles.headerTitle}>
                Mes Vidéos
                <span className={styles.countBadge}>{videos.length}</span>
              </h2>
              <p className={styles.headerSubtitle}>
                Vos vidéos YouTube sauvegardées : liens, transcriptions intégrales et résumés IA.
              </p>
            </div>
          </div>
          <div className={styles.headerRight}>
            <button
              type="button"
              className={styles.importToggleBtn}
              onClick={() => setShowImportBar((old) => !old)}
              disabled={importing}
            >
              <Plus size={15} />
              <span>Importer une vidéo</span>
            </button>
            <button
              type="button"
              className={styles.closeBtn}
              onClick={onClose}
              disabled={importing || Boolean(generatingAction)}
              aria-label="Fermer Mes Vidéos"
              title="Fermer"
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {showImportBar && (
          <form className={styles.importBar} onSubmit={(e) => void handleImportSubmit(e)}>
            <div className={styles.importRow}>
              <input
                type="url"
                className={styles.importInput}
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=... ou https://youtu.be/..."
                disabled={importing}
                required
                autoFocus
              />
              <select
                className={styles.importSelect}
                value={importAction}
                onChange={(e) => setImportAction(e.target.value as ImportActionOption)}
                disabled={importing}
                aria-label="Action après import"
              >
                <option value="summarize">Importer + Résumer</option>
                <option value="analyze">Importer + Analyser</option>
                <option value="key_points">Importer + Points clés &amp; Chapitres</option>
                <option value="study">Importer + Fiche &amp; Quiz</option>
                <option value="translate_fr">Importer + Traduire en français</option>
                <option value="custom">Importer + Consigne libre…</option>
                <option value="none">Transcript intégral uniquement</option>
              </select>
              <button
                type="submit"
                className={styles.importSubmitBtn}
                disabled={importing || !importUrl.trim() || (importAction === "custom" && !importCustomPrompt.trim())}
              >
                {importing ? <LoaderCircle size={14} className="spin" /> : <SquarePlay size={14} />}
                <span>{importing ? "Extraction…" : "Importer"}</span>
              </button>
            </div>
            {importAction === "custom" && (
              <input
                type="text"
                className={styles.importInput}
                value={importCustomPrompt}
                onChange={(e) => setImportCustomPrompt(e.target.value)}
                placeholder="Votre consigne sur la vidéo (ex. Extrais toutes les recommandations)…"
                disabled={importing}
                required
              />
            )}
          </form>
        )}

        {error && (
          <div className={styles.errorBanner} role="alert">
            <CircleAlert size={15} />
            <span>{error}</span>
          </div>
        )}

        <div className={styles.body}>
          {/* Colonne gauche : Liste des vidéos */}
          <aside className={styles.sidebar} aria-label="Liste de mes vidéos">
            <div className={styles.searchWrap}>
              <Search size={14} />
              <input
                type="search"
                className={styles.searchInput}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filtrer par titre ou chaîne…"
                aria-label="Rechercher dans mes vidéos"
              />
            </div>

            {listLoading && videos.length === 0 ? (
              <div className={styles.emptyState}>
                <LoaderCircle size={18} className="spin" />
                <span>Chargement de vos vidéos…</span>
              </div>
            ) : filteredVideos.length === 0 ? (
              <div className={styles.emptyState}>
                <SquarePlay size={24} />
                <strong>{videos.length === 0 ? "Aucune vidéo enregistrée" : "Aucun résultat"}</strong>
                <p>
                  {videos.length === 0
                    ? "Importez une vidéo YouTube depuis ici ou depuis le tchat : son titre, son lien, son transcript intégral et son résumé seront conservés."
                    : "Essayez un autre mot-clé."}
                </p>
              </div>
            ) : (
              <ul className={styles.videoList}>
                {filteredVideos.map((vid) => {
                  const isActive = vid.id === selectedId;
                  return (
                    <li key={vid.id}>
                      <button
                        type="button"
                        className={`${styles.videoItem} ${isActive ? styles.videoItemActive : ""}`}
                        onClick={() => {
                          if (vid.id !== selectedId) {
                            setDetailLoading(true);
                            setSelectedId(vid.id);
                          }
                        }}
                        title={vid.title}
                      >
                        <div className={styles.videoItemTitle}>{vid.title}</div>
                        <div className={styles.videoItemMeta}>
                          <span>{vid.author || "YouTube"}</span>
                          {vid.duration && <span>· {vid.duration}</span>}
                          <span>· {formatShortDate(vid.updated_at)}</span>
                        </div>
                        <div className={styles.videoItemBadges}>
                          {vid.has_summary ? (
                            <span className={`${styles.badge} ${styles.badgeSummary}`}>Résumé prêt</span>
                          ) : (
                            <span className={`${styles.badge} ${styles.badgePending}`}>Sans résumé</span>
                          )}
                          <span className={styles.badge}>
                            {vid.transcript_chars.toLocaleString("fr-FR")} car.
                          </span>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </aside>

          {/* Volet droit : Détail de la vidéo sélectionnée */}
          <section className={styles.detailPane} aria-label="Détails de la vidéo">
            {detailLoading ? (
              <div className={styles.emptyState}>
                <LoaderCircle size={20} className="spin" />
                <span>Chargement du transcript et du résumé…</span>
              </div>
            ) : !detail ? (
              <div className={styles.emptyState}>
                <Film size={28} />
                <strong>Sélectionnez une vidéo</strong>
                <p>Consultez son lien YouTube, son résumé structuré et l’intégralité de son transcript.</p>
              </div>
            ) : (
              <>
                <div className={styles.detailHeader}>
                  <div className={styles.detailTitleBlock}>
                    {renaming ? (
                      <form className={styles.renameForm} onSubmit={(e) => void handleCommitRename(e)}>
                        <input
                          type="text"
                          className={styles.renameInput}
                          value={renameDraft}
                          onChange={(e) => setRenameDraft(e.target.value)}
                          maxLength={255}
                          autoFocus
                        />
                        <button type="submit" className={styles.miniBtn} title="Enregistrer">
                          <Check size={14} />
                        </button>
                        <button
                          type="button"
                          className={styles.miniBtn}
                          onClick={() => setRenaming(false)}
                          title="Annuler"
                        >
                          <X size={14} />
                        </button>
                      </form>
                    ) : (
                      <div className={styles.detailTitleRow}>
                        <h3>{detail.title}</h3>
                        <button
                          type="button"
                          className={styles.miniBtn}
                          onClick={() => {
                            setRenameDraft(detail.title);
                            setRenaming(true);
                          }}
                          title="Renommer cette vidéo"
                          aria-label="Renommer cette vidéo"
                        >
                          <Pencil size={13} />
                        </button>
                      </div>
                    )}
                    <div className={styles.detailMetaLine}>
                      <span>{detail.author || "YouTube"}</span>
                      {detail.duration && <span>· ⏱ {detail.duration}</span>}
                      {detail.lang_label && <span>· {detail.lang_label}</span>}
                      <span>· {detail.transcript_chars.toLocaleString("fr-FR")} car.</span>
                    </div>
                  </div>

                  <div className={styles.detailActions}>
                    <a
                      href={detail.url}
                      target="_blank"
                      rel="noreferrer"
                      className={styles.ytLinkBtn}
                      title="Ouvrir la vidéo sur YouTube"
                    >
                      <SquarePlay size={14} />
                      <span>YouTube</span>
                      <ExternalLink size={12} />
                    </a>
                    {detail.video_id && (
                      <button
                        type="button"
                        className={styles.miniBtn}
                        onClick={() => setShowEmbed((old) => !old)}
                        title="Afficher ou masquer le lecteur vidéo intégré"
                      >
                        <Play size={13} />
                        <span>{showEmbed ? "Masquer" : "Lecteur"}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      className={styles.chatBtn}
                      disabled={attaching}
                      onClick={() => void handleAttachToChat()}
                      title="Joindre immédiatement ce transcript au tchat pour en discuter"
                    >
                      {attaching ? <LoaderCircle size={13} className="spin" /> : <MessageSquare size={13} />}
                      <span>Discuter</span>
                    </button>
                    <button
                      type="button"
                      className={`${styles.miniBtn} ${styles.dangerBtn}`}
                      disabled={deleting}
                      onClick={() => void handleDeleteVideo()}
                      title="Supprimer cette vidéo de Mes Vidéos"
                      aria-label="Supprimer cette vidéo"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                {showEmbed && detail.video_id && (
                  <div className={styles.embedBox}>
                    <iframe
                      src={`https://www.youtube-nocookie.com/embed/${detail.video_id}`}
                      title={detail.title}
                      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                )}

                <div className={styles.tabsBar} role="tablist">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === "summary"}
                    className={`${styles.tabBtn} ${activeTab === "summary" ? styles.tabBtnActive : ""}`}
                    onClick={() => setActiveTab("summary")}
                  >
                    <Sparkles size={14} />
                    <span>Résumé &amp; Analyses</span>
                    {detail.analyses.length > 0 && (
                      <span className={styles.tabCount}>{detail.analyses.length}</span>
                    )}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === "transcript"}
                    className={`${styles.tabBtn} ${activeTab === "transcript" ? styles.tabBtnActive : ""}`}
                    onClick={() => setActiveTab("transcript")}
                  >
                    <FileText size={14} />
                    <span>Transcript intégral</span>
                  </button>
                </div>

                {activeTab === "summary" ? (
                  <div className={styles.tabContent}>
                    <div className={styles.actionToolbar}>
                      {YOUTUBE_TRANSCRIPT_ACTIONS.map((act) => (
                        <button
                          key={act.id}
                          type="button"
                          className={styles.genActionBtn}
                          disabled={Boolean(generatingAction)}
                          onClick={() => void handleGenerateAnalysis(act.id)}
                          title={act.description}
                        >
                          {generatingAction === act.id ? (
                            <LoaderCircle size={13} className="spin" />
                          ) : (
                            <ActionMiniIcon id={act.id} />
                          )}
                          <span>{act.shortLabel}</span>
                        </button>
                      ))}
                      <button
                        type="button"
                        className={styles.genActionBtn}
                        disabled={Boolean(generatingAction)}
                        onClick={() => setShowCustomInput((old) => !old)}
                      >
                        <Pencil size={13} />
                        <span>Consigne libre</span>
                      </button>
                      {displayedSummary && (
                        <button
                          type="button"
                          className={styles.miniBtn}
                          onClick={() => void handleCopy("summary", displayedSummary)}
                          style={{ marginLeft: "auto" }}
                        >
                          {copiedKey === "summary" ? <Check size={13} /> : <Copy size={13} />}
                          <span>{copiedKey === "summary" ? "Copié" : "Copier"}</span>
                        </button>
                      )}
                    </div>

                    {showCustomInput && (
                      <form
                        className={styles.customActionForm}
                        onSubmit={(e) => {
                          e.preventDefault();
                          void handleGenerateAnalysis("custom", customActionDraft);
                        }}
                      >
                        <input
                          type="text"
                          className={styles.importInput}
                          value={customActionDraft}
                          onChange={(e) => setCustomActionDraft(e.target.value)}
                          placeholder="Votre question ou consigne sur l'intégralité de la vidéo…"
                          disabled={Boolean(generatingAction)}
                          autoFocus
                        />
                        <button
                          type="submit"
                          className={styles.importSubmitBtn}
                          disabled={Boolean(generatingAction) || !customActionDraft.trim()}
                        >
                          {generatingAction === "custom" ? <LoaderCircle size={13} className="spin" /> : <Sparkles size={13} />}
                          <span>Lancer</span>
                        </button>
                      </form>
                    )}

                    {detail.analyses.length > 1 && (
                      <div className={styles.analysesSwitcher}>
                        {detail.analyses.map((entry) => {
                          const isCurrent = (activeAnalysis?.id || "") === entry.id;
                          return (
                            <button
                              key={entry.id}
                              type="button"
                              className={`${styles.analysisChip} ${isCurrent ? styles.analysisChipActive : ""}`}
                              onClick={() => setSelectedAnalysisId(entry.id)}
                            >
                              <span>{entry.label}</span>
                              <small>{formatShortDate(entry.created_at)}</small>
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {displayedSummary ? (
                      <div className={`${styles.markdownBody} markdown`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayedSummary}</ReactMarkdown>
                      </div>
                    ) : (
                      <div className={styles.emptySummaryBox}>
                        <Sparkles size={20} />
                        <p>
                          Aucun résumé enregistré pour le moment. Cliquez sur <strong>Résumer</strong> ou{" "}
                          <strong>Analyser</strong> ci-dessus pour générer une synthèse complète à partir du
                          transcript intégral.
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className={styles.tabContent}>
                    <div className={styles.transcriptToolbar}>
                      <div className={styles.transcriptSearchWrap}>
                        <Search size={13} />
                        <input
                          type="search"
                          className={styles.transcriptSearchInput}
                          value={transcriptFilter}
                          onChange={(e) => setTranscriptFilter(e.target.value)}
                          placeholder="Rechercher dans le transcript…"
                        />
                        {transcriptFilter.trim() && (
                          <span className={styles.matchBadge}>
                            {filteredTranscriptInfo.matchCount} occ.
                          </span>
                        )}
                      </div>
                      <div className={styles.transcriptToolbarBtns}>
                        <button
                          type="button"
                          className={`${styles.miniBtn} ${rawTranscript ? styles.miniBtnActive : ""}`}
                          onClick={() => setRawTranscript(true)}
                        >
                          <FileText size={13} />
                          <span>Brut</span>
                        </button>
                        <button
                          type="button"
                          className={`${styles.miniBtn} ${!rawTranscript ? styles.miniBtnActive : ""}`}
                          onClick={() => setRawTranscript(false)}
                        >
                          <BookOpen size={13} />
                          <span>Formaté</span>
                        </button>
                        <button
                          type="button"
                          className={styles.miniBtn}
                          onClick={() => void handleCopy("transcript", detail.transcript_markdown || "")}
                        >
                          {copiedKey === "transcript" ? <Check size={13} /> : <Copy size={13} />}
                          <span>{copiedKey === "transcript" ? "Copié" : "Copier"}</span>
                        </button>
                        <button
                          type="button"
                          className={styles.miniBtn}
                          onClick={() => handleDownloadTranscript(detail)}
                          title="Télécharger toute la transcription en Markdown"
                        >
                          <Download size={13} />
                          <span>.md</span>
                        </button>
                      </div>
                    </div>

                    {rawTranscript ? (
                      <pre className={styles.transcriptPre}>{filteredTranscriptInfo.text}</pre>
                    ) : (
                      <div className={`${styles.markdownBody} markdown`}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {filteredTranscriptInfo.text}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
