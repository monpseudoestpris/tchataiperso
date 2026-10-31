"use client";

import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  HelpCircle,
  LayoutGrid,
  Maximize2,
  RotateCcw,
  RotateCw,
  Shuffle,
  Sparkles,
} from "lucide-react";
import type { Flashcard } from "@/lib/api";
import { MathMarkdown } from "@/components/math-markdown";

type LearnFlashcardsProps = {
  flashcards: Flashcard[];
  title?: string;
  subtitle?: string;
};

export function LearnFlashcards({ flashcards: initialFlashcards, title, subtitle }: LearnFlashcardsProps) {
  const [cards, setCards] = useState<Flashcard[]>(initialFlashcards);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [masteredIds, setMasteredIds] = useState<Set<number>>(new Set());
  const [reviewIds, setReviewIds] = useState<Set<number>>(new Set());
  const [viewMode, setViewMode] = useState<"single" | "grid">("single");
  const [gridFlipped, setGridFlipped] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setCards(initialFlashcards);
    setCurrentIndex(0);
    setIsFlipped(false);
    setMasteredIds(new Set());
    setReviewIds(new Set());
    setGridFlipped({});
  }, [initialFlashcards]);

  const currentCard = cards[currentIndex] || cards[0];
  const total = cards.length;

  // Raccourcis clavier (Espace, Flèche gauche, Flèche droite)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (viewMode !== "single") return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.code === "Space") {
        e.preventDefault();
        setIsFlipped((prev) => !prev);
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        handlePrev();
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        handleNext();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [viewMode, currentIndex, cards.length]);

  function handleFlip() {
    setIsFlipped((prev) => !prev);
  }

  function handlePrev() {
    setIsFlipped(false);
    setCurrentIndex((prev) => (prev > 0 ? prev - 1 : cards.length - 1));
  }

  function handleNext() {
    setIsFlipped(false);
    setCurrentIndex((prev) => (prev < cards.length - 1 ? prev + 1 : 0));
  }

  function handleMarkMastered(cardId: number, e?: React.MouseEvent) {
    e?.stopPropagation();
    setMasteredIds((prev) => {
      const next = new Set(prev);
      next.add(cardId);
      return next;
    });
    setReviewIds((prev) => {
      const next = new Set(prev);
      next.delete(cardId);
      return next;
    });
  }

  function handleMarkReview(cardId: number, e?: React.MouseEvent) {
    e?.stopPropagation();
    setReviewIds((prev) => {
      const next = new Set(prev);
      next.add(cardId);
      return next;
    });
    setMasteredIds((prev) => {
      const next = new Set(prev);
      next.delete(cardId);
      return next;
    });
  }

  function handleShuffle() {
    const shuffled = [...cards].sort(() => Math.random() - 0.5);
    setCards(shuffled);
    setCurrentIndex(0);
    setIsFlipped(false);
  }

  function handleResetProgress() {
    setMasteredIds(new Set());
    setReviewIds(new Set());
    setCurrentIndex(0);
    setIsFlipped(false);
    setGridFlipped({});
  }

  function toggleGridCard(id: number) {
    setGridFlipped((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  if (!cards || cards.length === 0) {
    return null;
  }

  const masteredCount = masteredIds.size;
  const reviewCount = reviewIds.size;
  const masteryPercent = Math.round((masteredCount / total) * 100);

  return (
    <section id="learn-section-flashcards" className="learn-widget-block learn-flashcards-widget">
      {/* En-tête avec métriques d'apprentissage */}
      <div className="learn-widget-header">
        <div className="learn-widget-title-wrap">
          <div className="learn-widget-badge">
            <Sparkles size={14} />
            <span>Rappel Actif Espacé</span>
          </div>
          <h2>📇 {title || `${total} Flashcards Interactives de Mémorisation Active`}</h2>
          <p>
            {subtitle || (
              <>
                Ancrez durablement les {total} concepts fondamentaux. Retournez chaque carte au clic ou avec la barre{" "}
                <strong>Espace</strong> pour révéler la réponse modèle.
              </>
            )}
          </p>
        </div>

        {/* Statistiques d'évaluation en direct */}
        <div className="learn-flashcards-stats-bar">
          <div className="learn-stat-pill is-mastered" title="Cartes maîtrisées">
            <CheckCircle2 size={13} />
            <span>{masteredCount} maîtrisée{masteredCount > 1 ? "s" : ""}</span>
          </div>
          <div className="learn-stat-pill is-review" title="Cartes à réviser">
            <RotateCcw size={13} />
            <span>{reviewCount} à revoir</span>
          </div>
          <div className="learn-stat-pill is-percent" title="Progression de maîtrise globale">
            <span>{masteryPercent}% maîtrise</span>
          </div>
        </div>
      </div>

      {/* Barre de progression globale */}
      <div className="learn-progress-track" role="progressbar" aria-valuenow={masteryPercent} aria-valuemin={0} aria-valuemax={100}>
        <div className="learn-progress-fill" style={{ width: `${masteryPercent}%` }} />
      </div>

      {/* Boutons d'action et mode d'affichage */}
      <div className="learn-flashcards-toolbar">
        <div className="learn-toolbar-left">
          <button
            type="button"
            className="learn-btn-secondary"
            onClick={handleShuffle}
            title="Mélanger l'ordre des cartes pour varier l'apprentissage"
          >
            <Shuffle size={14} />
            <span>Mélanger</span>
          </button>
          <button
            type="button"
            className="learn-btn-secondary"
            onClick={handleResetProgress}
            title="Réinitialiser l'auto-évaluation"
          >
            <RotateCw size={14} />
            <span>Réinitialiser</span>
          </button>
        </div>

        <div className="learn-toolbar-right">
          <button
            type="button"
            className={`learn-btn-secondary ${viewMode === "single" ? "is-active" : ""}`}
            onClick={() => setViewMode("single")}
            title="Mode immersion carte par carte"
          >
            <Maximize2 size={14} />
            <span>Carte par carte</span>
          </button>
          <button
            type="button"
            className={`learn-btn-secondary ${viewMode === "grid" ? "is-active" : ""}`}
            onClick={() => setViewMode("grid")}
            title="Afficher l'ensemble des 20 cartes en grille"
          >
            <LayoutGrid size={14} />
            <span>Grille ({total})</span>
          </button>
        </div>
      </div>

      {/* VUE 1 : CARTE PAR CARTE AVEC RETOURNEMENT 3D */}
      {viewMode === "single" && currentCard && (
        <div className="learn-flashcard-single-container">
          <div
            className={`learn-flashcard-3d-scene ${isFlipped ? "is-flipped" : ""}`}
            onClick={handleFlip}
            role="button"
            tabIndex={0}
            aria-label={`Flashcard ${currentIndex + 1} sur ${total}. Cliquez ou appuyez sur Espace pour retourner.`}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleFlip();
              }
            }}
          >
            <div className="learn-flashcard-3d-inner">
              {/* FACE RECTO (QUESTION / CONCEPT) */}
              <div className="learn-flashcard-face learn-flashcard-front">
                <div className="learn-flashcard-face-top">
                  <span className="learn-category-badge">{currentCard.category || "Point Clé"}</span>
                  <span className="learn-card-counter">
                    Carte {currentIndex + 1} / {total}
                  </span>
                </div>

                <div className="learn-flashcard-body">
                  <div className="learn-flashcard-icon">
                    <HelpCircle size={28} />
                  </div>
                  <div className="learn-flashcard-prompt">
                    <MathMarkdown content={currentCard.recto} />
                  </div>
                </div>

                <div className="learn-flashcard-face-bottom">
                  <span className="learn-flip-hint">
                    <RotateCw size={12} />
                    <span>Cliquez ou appuyez sur Espace pour voir la réponse</span>
                  </span>
                </div>
              </div>

              {/* FACE VERSO (RÉPONSE DÉTAILLÉE / EXPLICATION) */}
              <div className="learn-flashcard-face learn-flashcard-back">
                <div className="learn-flashcard-face-top">
                  <span className="learn-category-badge is-answer">Réponse modèle</span>
                  <span className="learn-card-counter">
                    Carte {currentIndex + 1} / {total}
                  </span>
                </div>

                <div className="learn-flashcard-body">
                  <div className="learn-flashcard-answer">
                    <MathMarkdown content={currentCard.verso} />
                  </div>
                </div>

                <div className="learn-flashcard-face-bottom">
                  <div className="learn-eval-buttons" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className={`learn-eval-btn is-mastered ${masteredIds.has(currentCard.id) ? "is-selected" : ""}`}
                      onClick={(e) => handleMarkMastered(currentCard.id, e)}
                    >
                      <CheckCircle2 size={14} />
                      <span>Maîtrisée</span>
                    </button>
                    <button
                      type="button"
                      className={`learn-eval-btn is-review ${reviewIds.has(currentCard.id) ? "is-selected" : ""}`}
                      onClick={(e) => handleMarkReview(currentCard.id, e)}
                    >
                      <RotateCcw size={14} />
                      <span>À revoir</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Navigation interactive sous la carte */}
          <div className="learn-flashcard-nav">
            <button
              type="button"
              className="learn-nav-btn"
              onClick={handlePrev}
              title="Carte précédente (Touche Flèche Gauche)"
            >
              <ArrowLeft size={16} />
              <span>Précédente</span>
            </button>

            <button
              type="button"
              className="learn-nav-flip-btn"
              onClick={handleFlip}
              title="Retourner la carte (Touche Espace)"
            >
              <RotateCw size={15} />
              <span>{isFlipped ? "Voir la question" : "Révéler la réponse (Espace)"}</span>
            </button>

            <button
              type="button"
              className="learn-nav-btn"
              onClick={handleNext}
              title="Carte suivante (Touche Flèche Droite)"
            >
              <span>Suivante</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* VUE 2 : GRILLE INTÉGRALE DES 20 CARTES */}
      {viewMode === "grid" && (
        <div className="learn-flashcards-grid">
          {cards.map((card, idx) => {
            const flipped = !!gridFlipped[card.id];
            const isMastered = masteredIds.has(card.id);
            const isReview = reviewIds.has(card.id);

            return (
              <div
                key={card.id || idx}
                className={`learn-grid-card ${flipped ? "is-flipped" : ""} ${
                  isMastered ? "is-mastered-card" : isReview ? "is-review-card" : ""
                }`}
                onClick={() => toggleGridCard(card.id)}
              >
                <div className="learn-grid-card-header">
                  <span className="learn-grid-card-num">#{idx + 1}</span>
                  <span className="learn-grid-category">{card.category || "Point Clé"}</span>
                  {isMastered && <span className="learn-grid-status is-ok">✅</span>}
                  {isReview && <span className="learn-grid-status is-review">🔄</span>}
                </div>

                <div className="learn-grid-card-content">
                  {flipped ? (
                    <div className="learn-grid-verso">
                      <strong>Réponse :</strong>
                      <div className="learn-grid-card-text">
                        <MathMarkdown content={card.verso} />
                      </div>
                    </div>
                  ) : (
                    <div className="learn-grid-recto">
                      <strong>Question :</strong>
                      <div className="learn-grid-card-text">
                        <MathMarkdown content={card.recto} />
                      </div>
                    </div>
                  )}
                </div>

                <div className="learn-grid-card-footer" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    className="learn-grid-flip-btn"
                    onClick={() => toggleGridCard(card.id)}
                  >
                    <RotateCw size={11} />
                    <span>{flipped ? "Recto" : "Verso"}</span>
                  </button>
                  <div className="learn-grid-actions">
                    <button
                      type="button"
                      className={`learn-tiny-eval ${isMastered ? "active" : ""}`}
                      onClick={(e) => handleMarkMastered(card.id, e)}
                      title="Marquer comme maîtrisée"
                    >
                      ✅
                    </button>
                    <button
                      type="button"
                      className={`learn-tiny-eval ${isReview ? "active" : ""}`}
                      onClick={(e) => handleMarkReview(card.id, e)}
                      title="Marquer à revoir"
                    >
                      🔄
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

