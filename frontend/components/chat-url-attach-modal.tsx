"use client";

import {
  BookOpen,
  Brain,
  CircleAlert,
  FileText,
  Film,
  Globe2,
  GraduationCap,
  Languages,
  ListOrdered,
  LoaderCircle,
  MessageSquarePlus,
  Paperclip,
  Sparkles,
  SquarePlay,
  X,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  YOUTUBE_TRANSCRIPT_ACTIONS,
  getUrlSubmitLabel,
  isYoutubeUrl,
  type UrlImportAction,
  type UrlImportSubmitPayload,
  type YoutubeTranscriptAction,
} from "@/lib/youtube-actions";

function ActionIcon({ id }: { id: UrlImportAction }) {
  switch (id) {
    case "summarize":
      return <Sparkles size={14} />;
    case "analyze":
      return <Brain size={14} />;
    case "key_points":
      return <ListOrdered size={14} />;
    case "study":
      return <GraduationCap size={14} />;
    case "translate_fr":
      return <Languages size={14} />;
    case "custom":
      return <MessageSquarePlus size={14} />;
    case "attach_only":
    default:
      return <Paperclip size={14} />;
  }
}

export function ChatUrlAttachModal({
  open,
  loading,
  urlValue,
  error,
  savedVideosCount = 0,
  onChangeUrl,
  onClose,
  onSubmit,
  onOpenVideoLibrary,
}: {
  open: boolean;
  loading: boolean;
  urlValue: string;
  error: string;
  savedVideosCount?: number;
  onChangeUrl: (value: string) => void;
  onClose: () => void;
  onSubmit: (payload: UrlImportSubmitPayload) => void;
  onOpenVideoLibrary?: () => void;
}) {
  const [selectedAction, setSelectedAction] = useState<UrlImportAction>("summarize");
  const [userPickedAction, setUserPickedAction] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");
  const [openTranscriptAfterImport, setOpenTranscriptAfterImport] = useState(false);
  const [saveToLibrary, setSaveToLibrary] = useState(true);

  if (!open) return null;

  const detectedYoutube = isYoutubeUrl(urlValue);
  const effectiveAction: UrlImportAction = userPickedAction
    ? selectedAction
    : detectedYoutube
      ? "summarize"
      : urlValue.trim()
        ? "attach_only"
        : "summarize";

  function handleSelectAction(action: UrlImportAction) {
    setSelectedAction(action);
    setUserPickedAction(true);
  }

  function handleFormSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const clean = urlValue.trim();
    if (!clean || loading) return;
    if (effectiveAction === "custom" && !customPrompt.trim()) return;
    onSubmit({
      url: clean,
      action: effectiveAction,
      customPrompt: customPrompt.trim(),
      openTranscriptAfterImport: effectiveAction === "attach_only" && openTranscriptAfterImport,
      saveToLibrary,
    });
  }

  function handleClose() {
    if (loading) return;
    setUserPickedAction(false);
    setCustomPrompt("");
    setOpenTranscriptAfterImport(false);
    onClose();
  }

  const submitDisabled =
    loading ||
    !urlValue.trim() ||
    (effectiveAction === "custom" && !customPrompt.trim());

  return (
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget && !loading) handleClose();
      }}
    >
      <section
        className="modal url-attach-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="url-dialog-title"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !loading) handleClose();
        }}
      >
        <form onSubmit={handleFormSubmit}>
          <div className="modal-header">
            <span className="modal-icon" style={{ background: "#fef2f2", color: "#dc2626" }}>
              <SquarePlay size={20} />
            </span>
            <div className="url-modal-header-right">
              {onOpenVideoLibrary && (
                <button
                  type="button"
                  className="url-library-shortcut-btn"
                  disabled={loading}
                  onClick={() => {
                    handleClose();
                    onOpenVideoLibrary();
                  }}
                  title="Ouvrir votre bibliothèque « Mes Vidéos » (liens, transcripts et résumés)"
                >
                  <Film size={14} />
                  <span>Mes Vidéos{savedVideosCount > 0 ? ` (${savedVideosCount})` : ""}</span>
                </button>
              )}
              <button
                type="button"
                className="icon-button"
                aria-label="Fermer"
                title="Fermer"
                disabled={loading}
                onClick={handleClose}
              >
                <X size={18} />
              </button>
            </div>
          </div>

          <h2 id="url-dialog-title">Importer une vidéo YouTube ou un lien web</h2>
          <p>
            Récupérez l’intégralité du transcript d’une vidéo YouTube (ou le contenu d’une page web) et choisissez
            directement quoi en faire.
          </p>

          <div className="modal-fields">
            <div className="url-field-label-row">
              <label htmlFor="url-input">Adresse URL</label>
              {urlValue.trim() && (
                <span className={`url-detected-pill ${detectedYoutube ? "is-youtube" : "is-web"}`}>
                  {detectedYoutube ? <SquarePlay size={12} /> : <Globe2 size={12} />}
                  <span>
                    {detectedYoutube
                      ? "Vidéo YouTube · Transcript intégral"
                      : "Lien web / article"}
                  </span>
                </span>
              )}
            </div>
            <input
              id="url-input"
              type="url"
              value={urlValue}
              onChange={(event) => onChangeUrl(event.target.value)}
              placeholder="https://www.youtube.com/watch?v=... ou https://youtu.be/..."
              autoFocus
              disabled={loading}
              required
            />
          </div>

          <div className="url-action-section">
            <span className="url-action-section-label">
              {detectedYoutube || !urlValue.trim()
                ? "Que faire avec le transcript ?"
                : "Action après extraction"}
            </span>
            <div
              className="url-action-grid"
              role="radiogroup"
              aria-label="Action à appliquer au transcript"
            >
              {YOUTUBE_TRANSCRIPT_ACTIONS.map((item) => {
                const isSelected = effectiveAction === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    disabled={loading}
                    className={`url-action-card ${isSelected ? "is-selected" : ""}`}
                    onClick={() => handleSelectAction(item.id as YoutubeTranscriptAction)}
                  >
                    <span className={`url-action-card-icon ${item.toneClass}`}>
                      <ActionIcon id={item.id} />
                    </span>
                    <span className="url-action-card-body">
                      <strong>{item.label}</strong>
                      <small>{item.description}</small>
                    </span>
                  </button>
                );
              })}

              <button
                type="button"
                role="radio"
                aria-checked={effectiveAction === "custom"}
                disabled={loading}
                className={`url-action-card ${effectiveAction === "custom" ? "is-selected" : ""}`}
                onClick={() => handleSelectAction("custom")}
              >
                <span className="url-action-card-icon is-custom">
                  <ActionIcon id="custom" />
                </span>
                <span className="url-action-card-body">
                  <strong>Consigne libre</strong>
                  <small>Posez directement votre propre question sur la vidéo.</small>
                </span>
              </button>

              <button
                type="button"
                role="radio"
                aria-checked={effectiveAction === "attach_only"}
                disabled={loading}
                className={`url-action-card ${effectiveAction === "attach_only" ? "is-selected" : ""}`}
                onClick={() => handleSelectAction("attach_only")}
              >
                <span className="url-action-card-icon is-attach">
                  <ActionIcon id="attach_only" />
                </span>
                <span className="url-action-card-body">
                  <strong>Joindre uniquement</strong>
                  <small>Ajoute le transcript complet sans envoyer de message.</small>
                </span>
              </button>
            </div>

            {effectiveAction === "custom" && (
              <div className="url-custom-prompt-wrap">
                <label htmlFor="url-custom-prompt">Votre consigne sur le transcript</label>
                <textarea
                  id="url-custom-prompt"
                  className="url-custom-prompt"
                  rows={2}
                  value={customPrompt}
                  onChange={(event) => setCustomPrompt(event.target.value)}
                  placeholder="Ex. Extrais tous les chiffres, outils et recommandations cités dans la vidéo…"
                  disabled={loading}
                  required
                />
              </div>
            )}

            <div className="url-options-checks">
              {effectiveAction === "attach_only" && (
                <label className="url-checkbox-row">
                  <input
                    type="checkbox"
                    checked={openTranscriptAfterImport}
                    onChange={(event) => setOpenTranscriptAfterImport(event.target.checked)}
                    disabled={loading}
                  />
                  <BookOpen size={13} />
                  <span>Ouvrir directement le transcript complet (lecture, copie, téléchargement)</span>
                </label>
              )}
              {(detectedYoutube || !urlValue.trim()) && (
                <label className="url-checkbox-row">
                  <input
                    type="checkbox"
                    checked={saveToLibrary}
                    onChange={(event) => setSaveToLibrary(event.target.checked)}
                    disabled={loading}
                  />
                  <FileText size={13} />
                  <span>Conserver cette vidéo, son transcript et son résumé dans « Mes Vidéos »</span>
                </label>
              )}
            </div>
          </div>

          {error && (
            <div className="url-error-msg" role="alert">
              <CircleAlert size={14} />
              <span>{error}</span>
            </div>
          )}

          <div className="modal-actions">
            <button type="button" className="secondary-button" disabled={loading} onClick={handleClose}>
              Annuler
            </button>
            <button
              type="submit"
              className="primary-button"
              disabled={submitDisabled}
              style={{ background: "linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)" }}
            >
              {loading ? <LoaderCircle className="spin" size={15} /> : null}
              {loading
                ? detectedYoutube
                  ? "Récupération du transcript intégral…"
                  : "Extraction en cours…"
                : getUrlSubmitLabel(effectiveAction, detectedYoutube)}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
