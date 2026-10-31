"use client";

import { useEffect, useState } from "react";
import {
  Award,
  Check,
  CheckCircle2,
  HelpCircle,
  Lightbulb,
  RotateCcw,
  Sparkles,
  Trophy,
  X,
  Eye,
  ArrowLeft,
  ArrowRight,
  LayoutGrid,
  Maximize2,
  Pencil,
} from "lucide-react";
import type { ClozeTestItem } from "@/lib/api";
import { MathMarkdown } from "@/components/math-markdown";

type LearnClozeProps = {
  clozeItems: ClozeTestItem[];
  title?: string;
  subtitle?: string;
};

// Nettoie une chaîne pour une comparaison tolérante (minuscules, sans accents, trim)
function normalizeString(str: string): string {
  return str
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function LearnCloze({ clozeItems, title, subtitle }: LearnClozeProps) {
  const [items, setItems] = useState<ClozeTestItem[]>(clozeItems);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [viewMode, setViewMode] = useState<"single" | "grid">("single");

  // Réponses saisies par l'utilisateur: [itemId][blankIndex] = valeur
  const [answers, setAnswers] = useState<Record<number, Record<number, string>>>({});
  // État de validation: [itemId] = boolean (validé ou non)
  const [checked, setChecked] = useState<Record<number, boolean>>({});
  // Indices révélés: [itemId] = boolean
  const [hintsRevealed, setHintsRevealed] = useState<Record<number, boolean>>({});
  // Solutions révélées: [itemId] = boolean
  const [solutionsRevealed, setSolutionsRevealed] = useState<Record<number, boolean>>({});

  useEffect(() => {
    setItems(clozeItems);
    setCurrentIndex(0);
    setAnswers({});
    setChecked({});
    setHintsRevealed({});
    setSolutionsRevealed({});
  }, [clozeItems]);

  if (!items || items.length === 0) {
    return null;
  }

  const total = items.length;
  const currentItem = items[currentIndex] || items[0];

  function handleReset() {
    setAnswers({});
    setChecked({});
    setHintsRevealed({});
    setSolutionsRevealed({});
  }

  function handleInputChange(itemId: number, blankIdx: number, value: string) {
    setAnswers((prev) => ({
      ...prev,
      [itemId]: {
        ...(prev[itemId] || {}),
        [blankIdx]: value,
      },
    }));
    // Si l'utilisateur modifie, on retire le statut "checked" pour lui permettre de retenter
    if (checked[itemId]) {
      setChecked((prev) => ({ ...prev, [itemId]: false }));
    }
  }

  function handleSelectWordBank(itemId: number, word: string) {
    const item = items.find((it) => it.id === itemId);
    if (!item) return;

    const currentItemAnswers = answers[itemId] || {};
    const missingCount = item.missing_words.length || 1;

    // Trouver le premier trou vide
    let targetBlank = 0;
    for (let i = 0; i < missingCount; i++) {
      if (!currentItemAnswers[i] || currentItemAnswers[i].trim() === "") {
        targetBlank = i;
        break;
      }
    }

    handleInputChange(itemId, targetBlank, word);
  }

  function handleCheck(itemId: number) {
    setChecked((prev) => ({ ...prev, [itemId]: true }));
  }

  function handleToggleHint(itemId: number) {
    setHintsRevealed((prev) => ({ ...prev, [itemId]: !prev[itemId] }));
  }

  function handleRevealSolution(itemId: number) {
    const item = items.find((it) => it.id === itemId);
    if (!item) return;

    // Remplir les réponses correctes
    const correctMap: Record<number, string> = {};
    item.missing_words.forEach((word, idx) => {
      correctMap[idx] = word;
    });

    setAnswers((prev) => ({
      ...prev,
      [itemId]: correctMap,
    }));
    setSolutionsRevealed((prev) => ({ ...prev, [itemId]: true }));
    setChecked((prev) => ({ ...prev, [itemId]: true }));
  }

  // Vérifier si un item particulier est entièrement correct
  function isItemCorrect(item: ClozeTestItem): boolean {
    const itemAnswers = answers[item.id] || {};
    if (item.missing_words.length === 0) return false;
    return item.missing_words.every((expected, idx) => {
      const given = itemAnswers[idx] || "";
      return normalizeString(given) === normalizeString(expected);
    });
  }

  // Calcul du score global
  let correctCount = 0;
  let evaluatedCount = 0;
  items.forEach((it) => {
    if (checked[it.id]) {
      evaluatedCount += 1;
      if (isItemCorrect(it)) {
        correctCount += 1;
      }
    }
  });

  const percent = total > 0 ? Math.round((correctCount / total) * 100) : 0;
  const progressPercent = total > 0 ? Math.round((evaluatedCount / total) * 100) : 0;
  const isComplete = evaluatedCount === total && total > 0;

  // Découpe un texte avec trous "[...]" en fragments textuels pour insérer les inputs
  function renderSentenceWithBlanks(item: ClozeTestItem) {
    const text = item.text_with_blanks || item.sentence;
    // Si la chaîne contient "[...]"
    const parts = text.split(/\[\.\.\.\]/);

    const isItemChecked = checked[item.id];
    const isRevealed = solutionsRevealed[item.id];

    return (
      <div className="learn-cloze-sentence-wrap">
        <p className="learn-cloze-sentence-text">
          {parts.map((part, idx) => {
            const isLast = idx === parts.length - 1;
            const blankIdx = idx;
            const expectedWord = item.missing_words[blankIdx] || "";
            const currentVal = answers[item.id]?.[blankIdx] || "";
            const isBlankCorrect =
              isItemChecked && normalizeString(currentVal) === normalizeString(expectedWord);
            const isBlankWrong =
              isItemChecked && normalizeString(currentVal) !== normalizeString(expectedWord);

            return (
              <span key={idx} className="learn-cloze-inline-fragment">
                <MathMarkdown content={part} inline />
                {!isLast && (
                  <span className="learn-cloze-input-container">
                    <input
                      type="text"
                      className={`learn-cloze-blank-input ${
                        isBlankCorrect ? "is-correct" : isBlankWrong ? "is-wrong" : ""
                      }`}
                      value={currentVal}
                      placeholder={isRevealed ? expectedWord : "…………"}
                      onChange={(e) => handleInputChange(item.id, blankIdx, e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          handleCheck(item.id);
                        }
                      }}
                      style={{
                        minWidth: `${Math.max(expectedWord.length * 11 + 24, 70)}px`,
                      }}
                      aria-label={`Trou numéro ${blankIdx + 1}`}
                    />
                    {isItemChecked && (
                      <span className="learn-cloze-blank-status">
                        {isBlankCorrect ? (
                          <Check size={14} className="text-emerald-500" />
                        ) : (
                          <X size={14} className="text-rose-500" />
                        )}
                      </span>
                    )}
                  </span>
                )}
              </span>
            );
          })}
        </p>
      </div>
    );
  }

  return (
    <section id="learn-section-cloze" className="learn-widget-block learn-cloze-widget">
      {/* En-tête */}
      <div className="learn-widget-header">
        <div className="learn-widget-title-wrap">
          <div className="learn-widget-badge">
            <Pencil size={14} />
            <span>Rappel Didactique · Cloze Test</span>
          </div>
          <h2>✍️ {title || `Phrases à Trous & Auto-complétion (${total} Exercices)`}</h2>
          <p>
            {subtitle || (
              "Complétez les mots clés manquants directement au clavier ou en cliquant sur les suggestions de la banque de mots. Validez ensuite pour afficher les explications."
            )}
          </p>
        </div>

        {/* Tableau de bord de score */}
        <div className="learn-quiz-score-board">
          <div className="learn-score-display">
            <span className="learn-score-num">
              {correctCount} / {total}
            </span>
            <span className="learn-score-label">Score ({percent}%)</span>
          </div>
          <button
            type="button"
            className="learn-btn-secondary"
            onClick={handleReset}
            title="Réinitialiser l'ensemble des réponses"
          >
            <RotateCcw size={14} />
            <span>Réinitialiser</span>
          </button>
        </div>
      </div>

      {/* Barre de progression */}
      <div
        className="learn-progress-track"
        role="progressbar"
        aria-valuenow={progressPercent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="learn-progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      {/* Barre d'outils et sélecteur de vue */}
      <div className="learn-flashcards-toolbar">
        <div className="learn-toolbar-left">
          <span className="learn-counter-text">
            {viewMode === "single"
              ? `Exercice ${currentIndex + 1} sur ${total}`
              : `Ensemble des ${total} phrases`}
          </span>
        </div>

        <div className="learn-toolbar-right">
          <button
            type="button"
            className={`learn-btn-secondary ${viewMode === "single" ? "is-active" : ""}`}
            onClick={() => setViewMode("single")}
            title="Afficher une phrase à la fois"
          >
            <Maximize2 size={14} />
            <span>Pas à pas</span>
          </button>
          <button
            type="button"
            className={`learn-btn-secondary ${viewMode === "grid" ? "is-active" : ""}`}
            onClick={() => setViewMode("grid")}
            title="Afficher toutes les phrases en liste"
          >
            <LayoutGrid size={14} />
            <span>Tout afficher</span>
          </button>
        </div>
      </div>

      {/* VUE 1 : SINGLE (PAS À PAS) */}
      {viewMode === "single" && currentItem && (
        <div className="learn-cloze-single-card">
          <div className="learn-cloze-card-header">
            <div className="learn-cloze-badge">
              <span>Exercice {currentIndex + 1}</span>
            </div>
            {checked[currentItem.id] && (
              <span
                className={`learn-cloze-result-pill ${
                  isItemCorrect(currentItem) ? "is-correct" : "is-wrong"
                }`}
              >
                {isItemCorrect(currentItem) ? (
                  <>
                    <CheckCircle2 size={14} />
                    <span>Exact !</span>
                  </>
                ) : (
                  <>
                    <X size={14} />
                    <span>À corriger</span>
                  </>
                )}
              </span>
            )}
          </div>

          {/* Rendu de la phrase à trous */}
          {renderSentenceWithBlanks(currentItem)}

          {/* Banque de mots clés cliquables */}
          {currentItem.options && currentItem.options.length > 0 && (
            <div className="learn-cloze-word-bank">
              <span className="learn-cloze-word-bank-label">Banque de mots :</span>
              <div className="learn-cloze-word-chips">
                {currentItem.options.map((word, optIdx) => (
                  <button
                    key={optIdx}
                    type="button"
                    className="learn-cloze-word-chip"
                    onClick={() => handleSelectWordBank(currentItem.id, word)}
                    title={`Insérer « ${word} » dans le trou`}
                  >
                    <MathMarkdown content={word} inline />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Indice contextuel si affiché */}
          {hintsRevealed[currentItem.id] && currentItem.hints && currentItem.hints.length > 0 && (
            <div className="learn-cloze-hint-box" role="status">
              <Lightbulb size={16} />
              <div>
                <strong>Indice :</strong>
                <MathMarkdown content={currentItem.hints.join(" · ")} />
                <small>
                  Première lettre du mot manquant :{" "}
                  <strong>{currentItem.missing_words[0]?.charAt(0).toUpperCase()}...</strong>
                </small>
              </div>
            </div>
          )}

          {/* Explication didactique si validé ou solution révélée */}
          {(checked[currentItem.id] || solutionsRevealed[currentItem.id]) && (
            <div className="learn-cloze-explanation-box">
              <div className="learn-cloze-explanation-header">
                <CheckCircle2 size={16} />
                <span>
                  Solution attendue :{" "}
                  <strong>
                    <MathMarkdown content={currentItem.missing_words.join(", ")} inline />
                  </strong>
                </span>
              </div>
              {currentItem.explanation && (
                <div className="learn-cloze-explanation-text">
                  <MathMarkdown content={currentItem.explanation} />
                </div>
              )}
            </div>
          )}

          {/* Barre d'action de la carte */}
          <div className="learn-cloze-actions-row">
            <div className="learn-cloze-actions-left">
              <button
                type="button"
                className="learn-btn-secondary"
                onClick={() => handleToggleHint(currentItem.id)}
                title="Afficher un indice didactique"
              >
                <Lightbulb size={14} />
                <span>{hintsRevealed[currentItem.id] ? "Masquer l'indice" : "Indice"}</span>
              </button>
              <button
                type="button"
                className="learn-btn-secondary"
                onClick={() => handleRevealSolution(currentItem.id)}
                title="Révéler la solution exacte"
              >
                <Eye size={14} />
                <span>Révéler la solution</span>
              </button>
            </div>

            <div className="learn-cloze-actions-right">
              <button
                type="button"
                className="learn-btn-primary"
                onClick={() => handleCheck(currentItem.id)}
              >
                <Check size={14} />
                <span>Vérifier</span>
              </button>

              <button
                type="button"
                className="learn-btn-secondary"
                onClick={() => setCurrentIndex((prev) => (prev > 0 ? prev - 1 : total - 1))}
                aria-label="Phrase précédente"
                title="Phrase précédente"
              >
                <ArrowLeft size={16} />
              </button>
              <button
                type="button"
                className="learn-btn-secondary"
                onClick={() => setCurrentIndex((prev) => (prev < total - 1 ? prev + 1 : 0))}
                aria-label="Phrase suivante"
                title="Phrase suivante"
              >
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* VUE 2 : GRILLE / LISTE COMPLÈTE */}
      {viewMode === "grid" && (
        <div className="learn-cloze-grid-list">
          {items.map((item, idx) => (
            <div key={item.id} className="learn-cloze-grid-item">
              <div className="learn-cloze-card-header">
                <span className="learn-cloze-badge">Phrase {idx + 1}</span>
                {checked[item.id] && (
                  <span
                    className={`learn-cloze-result-pill ${
                      isItemCorrect(item) ? "is-correct" : "is-wrong"
                    }`}
                  >
                    {isItemCorrect(item) ? "Exact" : "À corriger"}
                  </span>
                )}
              </div>

              {renderSentenceWithBlanks(item)}

              {item.options && item.options.length > 0 && (
                <div className="learn-cloze-word-bank">
                  <div className="learn-cloze-word-chips">
                    {item.options.map((word, optIdx) => (
                      <button
                        key={optIdx}
                        type="button"
                        className="learn-cloze-word-chip"
                        onClick={() => handleSelectWordBank(item.id, word)}
                      >
                        <MathMarkdown content={word} inline />
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {checked[item.id] && item.explanation && (
                <div className="learn-cloze-explanation-box">
                  <div className="learn-cloze-explanation-header">
                    <strong>Solution : <MathMarkdown content={item.missing_words.join(", ")} inline /></strong>
                  </div>
                  <MathMarkdown content={item.explanation} />
                </div>
              )}

              <div className="learn-cloze-grid-item-actions">
                <button
                  type="button"
                  className="learn-btn-secondary"
                  onClick={() => handleRevealSolution(item.id)}
                >
                  <Eye size={12} />
                  <span>Solution</span>
                </button>
                <button
                  type="button"
                  className="learn-btn-primary"
                  onClick={() => handleCheck(item.id)}
                >
                  <Check size={12} />
                  <span>Vérifier</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Trophée de fin */}
      {isComplete && (
        <div className="learn-quiz-trophy-banner">
          <Trophy size={28} className="trophy-bounce" />
          <div className="learn-trophy-text">
            <h3>Entraînement complet validé !</h3>
            <p>
              Vous avez complété l'ensemble des {total} phrases avec un score de {percent}%.
              {percent >= 80
                ? " Excellente assimilation des concepts clés du cours !"
                : " N'hésitez pas à réinitialiser pour ancrer les définitions manquantes."}
            </p>
          </div>
          <button type="button" className="learn-btn-secondary" onClick={handleReset}>
            <RotateCcw size={14} />
            <span>Recommencer l'exercice</span>
          </button>
        </div>
      )}
    </section>
  );
}

