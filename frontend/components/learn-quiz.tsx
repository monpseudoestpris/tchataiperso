"use client";

import { useState } from "react";
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
} from "lucide-react";
import type { QuizQuestion } from "@/lib/api";

type LearnQuizProps = {
  questions: QuizQuestion[];
  title?: string;
  subtitle?: string;
};

export function LearnQuiz({ questions, title, subtitle }: LearnQuizProps) {
  const [selectedAnswers, setSelectedAnswers] = useState<Record<number, number>>({});
  const total = questions.length;

  function handleSelectOption(qIndex: number, optionIndex: number) {
    if (selectedAnswers[qIndex] !== undefined) {
      return; // Déjà répondu à cette question
    }
    setSelectedAnswers((prev) => ({
      ...prev,
      [qIndex]: optionIndex,
    }));
  }

  function handleResetQuiz() {
    setSelectedAnswers({});
  }

  if (!questions || questions.length === 0) {
    return null;
  }

  // Calcul du score en direct
  let score = 0;
  const answeredCount = Object.keys(selectedAnswers).length;
  questions.forEach((q, idx) => {
    if (selectedAnswers[idx] === q.answer) {
      score += 1;
    }
  });

  const percent = total > 0 ? Math.round((score / total) * 100) : 0;
  const progressPercent = total > 0 ? Math.round((answeredCount / total) * 100) : 0;
  const isComplete = answeredCount === total && total > 0;

  return (
    <section id="learn-section-quiz" className="learn-widget-block learn-quiz-widget">
      {/* En-tête du Quiz */}
      <div className="learn-widget-header">
        <div className="learn-widget-title-wrap">
          <div className="learn-widget-badge">
            <Award size={14} />
            <span>Évaluation Didactique</span>
          </div>
          <h2>🎯 {title || `Quizz d'Auto-évaluation & Entraînement (${total} Questions)`}</h2>
          <p>
            {subtitle || (
              "Validez votre assimilation des concepts et réflexes méthodologiques. Chaque question propose 4 options et affiche la justification experte immédiatement après votre choix."
            )}
          </p>
        </div>

        {/* Tableau de bord de score en temps réel */}
        <div className="learn-quiz-score-board">
          <div className="learn-score-display">
            <span className="learn-score-num">
              {score} / {total}
            </span>
            <span className="learn-score-label">Score ({percent}%)</span>
          </div>
          <button
            type="button"
            className="learn-btn-secondary"
            onClick={handleResetQuiz}
            title="Réinitialiser l'ensemble des réponses pour refaire le test"
          >
            <RotateCcw size={14} />
            <span>Réinitialiser</span>
          </button>
        </div>
      </div>

      {/* Barre de progression des questions répondues */}
      <div className="learn-progress-track" role="progressbar" aria-valuenow={progressPercent} aria-valuemin={0} aria-valuemax={100}>
        <div className="learn-progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      <div className="learn-quiz-counter-text">
        <span>
          {answeredCount} sur {total} question{total > 1 ? "s" : ""} répondue{answeredCount > 1 ? "s" : ""}
        </span>
      </div>

      {/* Liste des questions de Quizz */}
      <div className="learn-quiz-questions-list">
        {questions.map((q, qIdx) => {
          const userChoice = selectedAnswers[qIdx];
          const hasAnswered = userChoice !== undefined;
          const isCorrect = hasAnswered && userChoice === q.answer;

          return (
            <div
              key={q.id || qIdx}
              className={`learn-quiz-card ${hasAnswered ? (isCorrect ? "is-answered-correct" : "is-answered-wrong") : ""}`}
            >
              <div className="learn-quiz-card-header">
                <span className="learn-quiz-card-num">Question {qIdx + 1} / {total}</span>
                {hasAnswered && (
                  <span className={`learn-quiz-result-pill ${isCorrect ? "is-correct" : "is-wrong"}`}>
                    {isCorrect ? (
                      <>
                        <Check size={12} />
                        <span>Bonne réponse</span>
                      </>
                    ) : (
                      <>
                        <X size={12} />
                        <span>Erreur</span>
                      </>
                    )}
                  </span>
                )}
              </div>

              <h3 className="learn-quiz-statement">{q.question}</h3>

              {/* Options A, B, C, D */}
              <div className="learn-quiz-options-list">
                {q.options.map((optionText, optIdx) => {
                  const letter = String.fromCharCode(65 + optIdx); // A, B, C, D
                  const isThisSelected = userChoice === optIdx;
                  const isThisCorrect = optIdx === q.answer;

                  let optStateClass = "";
                  if (hasAnswered) {
                    if (isThisCorrect) {
                      optStateClass = "is-correct-option";
                    } else if (isThisSelected) {
                      optStateClass = "is-wrong-option";
                    } else {
                      optStateClass = "is-dimmed-option";
                    }
                  }

                  return (
                    <button
                      key={optIdx}
                      type="button"
                      className={`learn-quiz-option-btn ${optStateClass}`}
                      onClick={() => handleSelectOption(qIdx, optIdx)}
                      disabled={hasAnswered}
                    >
                      <span className="learn-quiz-option-letter">{letter}</span>
                      <span className="learn-quiz-option-text">{optionText}</span>
                      {hasAnswered && isThisCorrect && (
                        <CheckCircle2 size={16} className="learn-option-feedback-icon is-ok" />
                      )}
                      {hasAnswered && isThisSelected && !isThisCorrect && (
                        <X size={16} className="learn-option-feedback-icon is-err" />
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Boîte d'explication didactique */}
              {hasAnswered && (
                <div className="learn-quiz-explanation-box">
                  <div className="learn-explanation-header">
                    <Lightbulb size={16} />
                    <strong>Justification méthodologique :</strong>
                  </div>
                  <p>{q.explanation}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* BANNIÈRE DE FÉLICITATIONS FINALE */}
      {isComplete && (
        <div className="learn-quiz-final-card">
          <div className="learn-final-trophy">
            <Trophy size={48} />
          </div>
          <h3>
            {score >= 18
              ? "🎉 Maîtrise Exceptionnelle !"
              : score >= 14
              ? "👏 Très Bon Niveau Pédagogique !"
              : "💪 Bon Début d'Apprentissage !"}
          </h3>
          <p>
            {score >= 18
              ? "Félicitations ! Vous avez assimilé avec brio les 20 notions et réflexes clés du cours."
              : score >= 14
              ? "Solide compréhension d'ensemble. Revoyez les quelques questions manquées grâce aux flashcards ci-dessus."
              : "Prenez le temps de revoir les flashcards de mémorisation active et relisez les démonstrations modèles du cours avant de retenter le test."}
          </p>
          <div className="learn-final-score-badge">
            Score Final : {score} / {total} ({percent}%)
          </div>
          <button
            type="button"
            className="learn-btn-primary"
            onClick={handleResetQuiz}
          >
            <RotateCcw size={16} />
            <span>Retenter le Quizz pour viser 20 / 20</span>
          </button>
        </div>
      )}
    </section>
  );
}

