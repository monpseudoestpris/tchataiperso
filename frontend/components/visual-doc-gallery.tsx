"use client";

import { useMemo, useRef, useState } from "react";
import {
  AudioLines,
  BookOpen,
  Camera,
  Globe,
  LoaderCircle,
  MessageSquare,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import {
  errorMessage,
  resetVisualDocCover,
  uploadVisualDocCover,
  VISUAL_DOC_CATEGORIES,
  type VisualDocDetail,
  type VisualDocSummary,
} from "@/lib/api";
import styles from "./visual-doc-gallery.module.css";

export interface VisualDocGalleryProps {
  docs: VisualDocSummary[];
  loading: boolean;
  attachedDocIds: string[];
  onSelectDoc: (docId: string) => void;
  onStartChatWithDoc: (doc: VisualDocSummary) => Promise<void> | void;
  onStartVoiceWithDoc?: (doc: VisualDocSummary) => Promise<void> | void;
  onDeleteDoc: (docId: string) => Promise<void> | void;
  onDocCoverUpdated: (updated: VisualDocDetail) => void;
  onOpenIngest: () => void;
  onError: (msg: string) => void;
}

function getCategoryMeta(catId?: string) {
  return (
    VISUAL_DOC_CATEGORIES.find((c) => c.id === catId) ||
    VISUAL_DOC_CATEGORIES[VISUAL_DOC_CATEGORIES.length - 1]
  );
}

export function VisualDocGallery({
  docs,
  loading,
  attachedDocIds,
  onSelectDoc,
  onStartChatWithDoc,
  onStartVoiceWithDoc,
  onDeleteDoc,
  onDocCoverUpdated,
  onOpenIngest,
  onError,
}: VisualDocGalleryProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [uploadingCoverDocId, setUploadingCoverDocId] = useState<string | null>(null);
  const [busyDocId, setBusyDocId] = useState<string | null>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);
  const pendingCoverTargetRef = useRef<string | null>(null);

  const presentCategories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of docs) {
      const cid = d.doc_category || "general";
      counts.set(cid, (counts.get(cid) || 0) + 1);
    }
    return VISUAL_DOC_CATEGORIES.filter((c) => counts.has(c.id)).map((c) => ({
      ...c,
      count: counts.get(c.id) || 0,
    }));
  }, [docs]);

  const filteredDocs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return docs.filter((doc) => {
      if (selectedCategory !== "all" && (doc.doc_category || "general") !== selectedCategory) {
        return false;
      }
      if (!q) return true;
      return (
        doc.title.toLowerCase().includes(q) ||
        (doc.doc_category_label || "").toLowerCase().includes(q) ||
        (doc.forum_label || "").toLowerCase().includes(q)
      );
    });
  }, [docs, searchQuery, selectedCategory]);

  function triggerCoverPicker(docId: string, e: React.MouseEvent) {
    e.stopPropagation();
    pendingCoverTargetRef.current = docId;
    coverInputRef.current?.click();
  }

  async function handleCoverFileSelected(fileList: FileList | null) {
    const targetId = pendingCoverTargetRef.current;
    if (!targetId || !fileList || fileList.length === 0) return;
    const file = fileList[0];
    setUploadingCoverDocId(targetId);
    onError("");
    try {
      const updated = await uploadVisualDocCover(targetId, file);
      onDocCoverUpdated(updated);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setUploadingCoverDocId(null);
      pendingCoverTargetRef.current = null;
      if (coverInputRef.current) coverInputRef.current.value = "";
    }
  }

  async function handleResetCover(docId: string, e: React.MouseEvent) {
    e.stopPropagation();
    setUploadingCoverDocId(docId);
    onError("");
    try {
      const updated = await resetVisualDocCover(docId);
      onDocCoverUpdated(updated);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setUploadingCoverDocId(null);
    }
  }

  if (loading) {
    return (
      <div className={styles.centerState}>
        <LoaderCircle size={26} className="spin" />
        <span>Ouverture de votre bibliothèque illustrée…</span>
      </div>
    );
  }

  if (docs.length === 0) {
    return (
      <div className={styles.centerState}>
        <div className={styles.emptyHeroIcon}>
          <BookOpen size={34} />
        </div>
        <h3>Votre bibliothèque illustrée est prête</h3>
        <p>
          Importez un livret de règles de jeu, un rapport financier, un article scientifique ou un manuel technique pour le feuilleter en Livre 3D et interroger l&apos;IA avec schémas et citations cliquables.
        </p>
        <button type="button" className={styles.heroAddBtn} onClick={onOpenIngest}>
          <Plus size={16} />
          <span>Ingérer un premier document</span>
        </button>
      </div>
    );
  }

  return (
    <div className={styles.galleryRoot}>
      <input
        ref={coverInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
        style={{ display: "none" }}
        onChange={(e) => void handleCoverFileSelected(e.target.files)}
      />

      {/* Barre supérieure de recherche & filtres */}
      <div className={styles.galleryTopBar}>
        <div className={styles.searchBox}>
          <Search size={15} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Rechercher un document, une règle de jeu, un rapport…"
            aria-label="Rechercher dans la bibliothèque"
          />
        </div>

        <div className={styles.filterPills} role="tablist" aria-label="Filtrer par catégorie">
          <button
            type="button"
            role="tab"
            aria-selected={selectedCategory === "all"}
            className={`${styles.filterPill} ${selectedCategory === "all" ? styles.filterPillActive : ""}`}
            onClick={() => setSelectedCategory("all")}
          >
            <span>Tous</span>
            <small>{docs.length}</small>
          </button>
          {presentCategories.map((cat) => (
            <button
              key={cat.id}
              type="button"
              role="tab"
              aria-selected={selectedCategory === cat.id}
              className={`${styles.filterPill} ${selectedCategory === cat.id ? styles.filterPillActive : ""}`}
              onClick={() => setSelectedCategory(cat.id)}
            >
              <span>{cat.emoji} {cat.shortLabel}</span>
              <small>{cat.count}</small>
            </button>
          ))}
        </div>
      </div>

      {/* Grille de cartes premium */}
      <div className={styles.cardsGrid}>
        {filteredDocs.map((doc) => {
          const catMeta = getCategoryMeta(doc.doc_category);
          const isLinked = attachedDocIds.includes(doc.id);
          const isUploadingCover = uploadingCoverDocId === doc.id;
          const isBusy = busyDocId === doc.id;

          return (
            <article
              key={doc.id}
              className={`${styles.bookCard} ${isLinked ? styles.bookCardLinked : ""}`}
              onClick={() => onSelectDoc(doc.id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelectDoc(doc.id);
                }
              }}
            >
              {/* Couverture visuelle immersive */}
              <div className={styles.cardCoverStage}>
                {doc.cover_url ? (
                  <img
                    src={doc.cover_url}
                    alt={doc.title}
                    className={styles.cardCoverImg}
                    loading="lazy"
                  />
                ) : (
                  <div className={styles.cardCoverPlaceholder}>
                    <BookOpen size={36} />
                  </div>
                )}

                <div className={styles.cardCoverGradient} />

                {/* Badges flottants en haut */}
                <div className={styles.cardTopBadges}>
                  <span className={styles.categoryGlassBadge}>
                    <span>{catMeta.emoji}</span>
                    <span>{doc.doc_category_label || catMeta.shortLabel}</span>
                  </span>
                  {isLinked && (
                    <span className={styles.linkedGlassBadge}>
                      <Sparkles size={11} />
                      <span>Actif ici</span>
                    </span>
                  )}
                </div>

                {/* Boutons d'édition d'image de couverture */}
                <div className={styles.coverOverlayTools}>
                  <button
                    type="button"
                    className={styles.coverEditBtn}
                    disabled={isUploadingCover}
                    onClick={(e) => triggerCoverPicker(doc.id, e)}
                    title="Choisir une image de couverture personnalisée (boîte de jeu, visuel HD…)"
                  >
                    {isUploadingCover ? <LoaderCircle size={13} className="spin" /> : <Camera size={13} />}
                    <span>{doc.has_custom_cover ? "Changer l'image" : "Ajouter une image"}</span>
                  </button>
                  {doc.has_custom_cover && (
                    <button
                      type="button"
                      className={styles.coverResetBtn}
                      disabled={isUploadingCover}
                      onClick={(e) => void handleResetCover(doc.id, e)}
                      title="Revenir à la page 1 du document"
                    >
                      <RotateCcw size={12} />
                    </button>
                  )}
                </div>

                {/* Titre en bas de la couverture */}
                <div className={styles.cardCoverTitleOverlay}>
                  <h3 className={styles.cardTitle} title={doc.title}>
                    {doc.title}
                  </h3>
                </div>
              </div>

              {/* Métadonnées et actions */}
              <div className={styles.cardBody}>
                <div className={styles.cardStatsRow}>
                  <span className={styles.statChip}>
                    {doc.page_count} page{doc.page_count > 1 ? "s" : ""}
                  </span>
                  <span className={styles.statChip}>
                    {doc.figure_count} schéma{doc.figure_count > 1 ? "s" : ""}
                  </span>
                  {(doc.link_count ?? 0) > 0 && (
                    <span className={`${styles.statChip} ${styles.statChipAccent}`}>
                      +{doc.link_count} doc/lien{(doc.link_count ?? 0) > 1 ? "s" : ""}
                    </span>
                  )}
                </div>

                <div className={styles.cardForumLine} title={doc.forum_label || catMeta.forumLabel}>
                  <Globe size={12} />
                  <span>{doc.forum_label || catMeta.forumLabel}</span>
                </div>

                <div className={styles.cardActionsRow}>
                  <button
                    type="button"
                    className={styles.openBookBtn}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectDoc(doc.id);
                    }}
                  >
                    <BookOpen size={14} />
                    <span>Ouvrir le livre</span>
                  </button>
                  <button
                    type="button"
                    className={styles.quickActionBtn}
                    disabled={isBusy}
                    title="Poser des questions dans le tchat sur ce document"
                    onClick={async (e) => {
                      e.stopPropagation();
                      setBusyDocId(doc.id);
                      try {
                        await onStartChatWithDoc(doc);
                      } finally {
                        setBusyDocId(null);
                      }
                    }}
                  >
                    <MessageSquare size={14} />
                  </button>
                  {onStartVoiceWithDoc && (
                    <button
                      type="button"
                      className={styles.quickActionBtn}
                      disabled={isBusy}
                      title="Ouvrir en Mode Vocal Plein Écran"
                      onClick={async (e) => {
                        e.stopPropagation();
                        setBusyDocId(doc.id);
                        try {
                          await onStartVoiceWithDoc(doc);
                        } finally {
                          setBusyDocId(null);
                        }
                      }}
                    >
                      <AudioLines size={14} />
                    </button>
                  )}
                  <button
                    type="button"
                    className={`${styles.quickActionBtn} ${styles.quickDeleteBtn}`}
                    disabled={isBusy}
                    title="Supprimer ce document"
                    onClick={async (e) => {
                      e.stopPropagation();
                      setBusyDocId(doc.id);
                      try {
                        await onDeleteDoc(doc.id);
                      } finally {
                        setBusyDocId(null);
                      }
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </article>
          );
        })}

        {/* Carte d'ajout rapide */}
        <button
          type="button"
          className={styles.addNewCard}
          onClick={onOpenIngest}
        >
          <div className={styles.addNewCardIcon}>
            <Plus size={26} />
          </div>
          <strong>Nouveau document</strong>
          <span>Importer un PDF, des photos, une FAQ ou un rapport</span>
        </button>
      </div>
    </div>
  );
}
