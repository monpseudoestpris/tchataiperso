"use client";

import { useEffect, useState } from "react";
import {
  Brain,
  Check,
  CircleAlert,
  Copy,
  GraduationCap,
  HelpCircle,
  Layers,
  LoaderCircle,
  MessageSquareQuote,
  RotateCcw,
  Sliders,
  Sparkles,
  Trophy,
  WandSparkles,
  X,
} from "lucide-react";
import {
  errorMessage,
  generateStudyMaterial,
  type Conversation,
  type Flashcard,
  type QuizQuestion,
  type StudyMaterialResponse,
} from "@/lib/api";
import { LearnFlashcards } from "@/components/learn-flashcards";
import { LearnQuiz } from "@/components/learn-quiz";

type StudyModalProps = {
  isOpen: boolean;
  conversation: Conversation | null;
  initialKind?: "flashcards" | "quiz";
  onClose: () => void;
  onSendToChat?: (content: string) => void;
};

type Difficulty = "easy" | "medium" | "hard";

const COUNT_PRESETS = [
  { count: 5, label: "5 cartes", hint: "Express (~3 min)" },
  { count: 10, label: "10 cartes", hint: "Standard (~6 min)" },
  { count: 15, label: "15 cartes", hint: "Approfondi (~10 min)" },
  { count: 20, label: "20 cartes", hint: "Examen (~15 min)" },
];

const DIFFICULTY_OPTIONS: { id: Difficulty; label: string; icon: string; desc: string; tone: string }[] = [
  {
    id: "easy",
    label: "Facile / Débutant",
    icon: "🟢",
    desc: "Notions de base, définitions immédiates et concepts clés sans piège.",
    tone: "is-easy",
  },
  {
    id: "medium",
    label: "Moyen / Intermédiaire",
    icon: "🟡",
    desc: "Compréhension, mise en situation, applications concrètes et pièges classiques.",
    tone: "is-medium",
  },
  {
    id: "hard",
    label: "Difficile / Avancé",
    icon: "🔴",
    desc: "Cas limites, subtilités méthodologiques, diagnostic d'erreurs et analyse critique.",
    tone: "is-hard",
  },
];

export function StudyModal({
  isOpen,
  conversation,
  initialKind = "flashcards",
  onClose,
  onSendToChat,
}: StudyModalProps) {
  const [kind, setKind] = useState<"flashcards" | "quiz">(initialKind);
  const [count, setCount] = useState<number>(10);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [topic, setTopic] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showConfig, setShowConfig] = useState(true);

  // Stockage des résultats par conversation
  const [result, setResult] = useState<StudyMaterialResponse | null>(null);

  // Initialisation à l'ouverture ou au changement de conversation
  useEffect(() => {
    if (isOpen && conversation) {
      const defaultTopic = conversation.title && conversation.title !== "Nouvelle conversation"
        ? conversation.title
        : conversation.theme || "Sujet abordé dans le tchat";
      setTopic(defaultTopic);
      setKind(initialKind);
      setError(null);
    }
  }, [isOpen, conversation, initialKind]);

  // Raccourci Échap pour fermer la modale
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!isOpen) return;
      if (e.key === "Escape" && !loading) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, loading, onClose]);

  if (!isOpen || !conversation) {
    return null;
  }

  async function handleGenerate(targetKind?: "flashcards" | "quiz") {
    if (!conversation) return;
    const activeKind = targetKind || kind;
    setKind(activeKind);
    setLoading(true);
    setError(null);

    try {
      const data = await generateStudyMaterial(conversation.id, {
        kind: activeKind,
        count,
        difficulty,
        topic: topic.trim() || conversation.title || "Discussion",
      });
      setResult(data);
      setShowConfig(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function handleCopyMarkdown() {
    if (!result) return;
    let md = "";
    if (result.kind === "flashcards" && result.flashcards) {
      md = `# 📇 Flashcards de révision : ${result.topic}\n\n`;
      md += `*Niveau : ${difficulty} · ${result.flashcards.length} cartes de mémorisation active*\n\n`;
      result.flashcards.forEach((card, idx) => {
        md += `### Flashcard ${idx + 1} (${card.category || "Point Clé"})\n`;
        md += `**Recto :** ${card.recto}\n`;
        md += `**Verso :** ${card.verso}\n\n`;
      });
    } else if (result.kind === "quiz" && result.questions) {
      md = `# 🎯 Quizz d'auto-évaluation : ${result.topic}\n\n`;
      md += `*Niveau : ${difficulty} · ${result.questions.length} questions QCM*\n\n`;
      result.questions.forEach((q, idx) => {
        md += `### Question ${idx + 1} : ${q.question}\n`;
        q.options.forEach((opt, optIdx) => {
          const letter = String.fromCharCode(65 + optIdx);
          md += `- **${letter}.** ${opt}\n`;
        });
        const correctLetter = String.fromCharCode(65 + q.answer);
        md += `\n*Bonne réponse : Option ${correctLetter}*\n`;
        md += `> **Explication :** ${q.explanation}\n\n`;
      });
    }

    if (navigator.clipboard) {
      navigator.clipboard.writeText(md).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  }

  function handleInsertInChat() {
    if (!result || !onSendToChat) return;
    let text = "";
    if (result.kind === "flashcards" && result.flashcards) {
      text = `### 📇 Flashcards générées sur « ${result.topic} »\n\n`;
      result.flashcards.forEach((c, idx) => {
        text += `**${idx + 1}. [${c.category || "Point Clé"}]** ${c.recto}\n*→ ${c.verso}*\n\n`;
      });
    } else if (result.kind === "quiz" && result.questions) {
      text = `### 🎯 Quizz d'entraînement sur « ${result.topic} »\n\n`;
      result.questions.forEach((q, idx) => {
        text += `**Question ${idx + 1} :** ${q.question}\n`;
        q.options.forEach((opt, optIdx) => {
          const letter = String.fromCharCode(65 + optIdx);
          text += `  - ${letter}. ${opt}\n`;
        });
        const correctLetter = String.fromCharCode(65 + q.answer);
        text += `*Bonne réponse : ${correctLetter}* (${q.explanation})\n\n`;
      });
    }
    onSendToChat(text);
    onClose();
  }

  const difficultyMeta = DIFFICULTY_OPTIONS.find((d) => d.id === difficulty) || DIFFICULTY_OPTIONS[1];

  return (
    <div
      className="deepsearch-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="study-modal-title"
    >
      <div className="deepsearch-modal deepsearch-modal-wide study-modal-container">
        {/* En-tête de la modale */}
        <div className="deepsearch-modal-header study-modal-header">
          <div className="deepsearch-modal-header-left">
            <span className="deepsearch-modal-badge-icon study-modal-badge-icon">
              <Brain size={20} />
            </span>
            <div className="deepsearch-modal-title-group">
              <div className="deepsearch-modal-eyebrow study-modal-eyebrow">
                <Sparkles size={12} />
                <span>RÉVISION ACTIVE & AUTO-ÉVALUATION</span>
              </div>
              <h2 id="study-modal-title">Flashcards 3D & Quizz Interactif</h2>
              <div className="study-modal-subheading">
                <span>Discussion : <strong>{conversation.title || "Tchat en cours"}</strong></span>
                {conversation.theme && (
                  <span className="study-modal-theme-pill">{conversation.theme}</span>
                )}
              </div>
            </div>
          </div>
          <button
            type="button"
            className="deepsearch-modal-close-btn"
            onClick={onClose}
            aria-label="Fermer la fenêtre de révision"
            disabled={loading}
          >
            <X size={18} />
          </button>
        </div>

        {/* Corps principal */}
        <div className="study-modal-body-scroll">
          {error && (
            <div className="study-modal-error-banner" role="alert">
              <CircleAlert size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* VUE 1 : CHARGEMENT EN COURS */}
          {loading && (
            <div className="study-modal-loading-screen">
              <div className="study-loading-orb">
                <LoaderCircle size={38} className="spin" />
              </div>
              <h3>Génération pédagogique en cours…</h3>
              <p>
                Analyse de la discussion et extraction des concepts clés pour concevoir vos{" "}
                <strong>{count} {kind === "flashcards" ? "Flashcards 3D" : "Questions de Quizz"}</strong> ({difficultyMeta.label}).
              </p>
              <div className="study-loading-steps">
                <span>✓ Analyse des échanges & du contexte</span>
                <span>⚡ Formulation des questions & explications didactiques</span>
                <span>✨ Finalisation de l'évaluation interactive</span>
              </div>
            </div>
          )}

          {/* VUE 2 : CONFIGURATION DES PARAMÈTRES (Avant génération ou lors d'un réajustement) */}
          {!loading && (showConfig || !result) && (
            <div className="study-config-panel">
              <div className="study-config-intro">
                <p>
                  Choisissez le format d’apprentissage souhaité, le nombre de cartes et le niveau d’exigence.
                  L’IA synthétise les points clés abordés dans cette conversation pour créer votre entraînement personnalisé.
                </p>
              </div>

              {/* 1. SÉLECTEUR DE MODE : Flashcards OU Quizz */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <Layers size={15} />
                  <span>1. Choisissez le format d'apprentissage</span>
                </label>
                <div className="study-format-cards-grid">
                  <button
                    type="button"
                    className={`study-format-card ${kind === "flashcards" ? "is-selected" : ""}`}
                    onClick={() => setKind("flashcards")}
                  >
                    <div className="study-format-card-header">
                      <span className="study-format-card-icon">📇</span>
                      <div className="study-format-card-name">
                        <strong>Flashcards 3D</strong>
                        <small>Cartes mémoire Recto / Verso</small>
                      </div>
                    </div>
                    <p>
                      Mémorisation active avec retournement animé 3D, touches clavier (Espace/Flèches) et auto-évaluation instantanée « Maîtrisée » ou « À revoir ».
                    </p>
                    <div className="study-format-card-footer">
                      <span className="study-format-badge">Flip 3D & Rappel Actif</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`study-format-card ${kind === "quiz" ? "is-selected" : ""}`}
                    onClick={() => setKind("quiz")}
                  >
                    <div className="study-format-card-header">
                      <span className="study-format-card-icon">🎯</span>
                      <div className="study-format-card-name">
                        <strong>Quizz QCM</strong>
                        <small>Questionnaire 4 options & explications</small>
                      </div>
                    </div>
                    <p>
                      Évaluation méthodique avec validation directe vert/rouge, explications expertes détaillées, calcul de score en temps réel et trophée final.
                    </p>
                    <div className="study-format-card-footer">
                      <span className="study-format-badge">Score en direct & Trophée</span>
                    </div>
                  </button>
                </div>
              </div>

              {/* 2. NOMBRE DE CARTES / QUESTIONS */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <Sliders size={15} />
                  <span>2. Nombre de {kind === "flashcards" ? "cartes" : "questions"} : <strong>{count}</strong></span>
                </label>
                <div className="study-count-chips-row">
                  {COUNT_PRESETS.map((preset) => (
                    <button
                      key={preset.count}
                      type="button"
                      className={`study-count-chip ${count === preset.count ? "is-active" : ""}`}
                      onClick={() => setCount(preset.count)}
                    >
                      <span className="study-count-chip-num">{preset.count}</span>
                      <span className="study-count-chip-label">{preset.hint}</span>
                    </button>
                  ))}
                  <div className="study-custom-count-input">
                    <label htmlFor="custom-count">Personnalisé :</label>
                    <input
                      id="custom-count"
                      type="number"
                      min={1}
                      max={30}
                      value={count}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        if (!isNaN(val) && val >= 1 && val <= 30) {
                          setCount(val);
                        }
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* 3. NIVEAU DE DIFFICULTÉ */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <GraduationCap size={15} />
                  <span>3. Niveau de difficulté</span>
                </label>
                <div className="study-difficulty-grid">
                  {DIFFICULTY_OPTIONS.map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      className={`study-difficulty-card ${opt.tone} ${difficulty === opt.id ? "is-active" : ""}`}
                      onClick={() => setDifficulty(opt.id)}
                    >
                      <div className="study-diff-header">
                        <span className="study-diff-icon">{opt.icon}</span>
                        <strong>{opt.label}</strong>
                      </div>
                      <p>{opt.desc}</p>
                    </button>
                  ))}
                </div>
              </div>

              {/* 4. SUJET / FOCUS OPTIONNEL */}
              <div className="study-section-block">
                <label htmlFor="study-topic-input" className="study-section-title">
                  <WandSparkles size={15} />
                  <span>4. Sujet ou axe ciblé (optionnel)</span>
                </label>
                <input
                  id="study-topic-input"
                  type="text"
                  className="study-topic-input"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="Ex: Le cycle de vie des composants, les erreurs de syntaxe, l'historique..."
                  maxLength={160}
                />
                <span className="study-topic-hint">
                  Pré-rempli avec le thème du tchat. Vous pouvez préciser un sous-thème spécifique pour cibler l'évaluation.
                </span>
              </div>

              {/* BOUTON D'ACTION PRINCIPALE */}
              <div className="study-config-actions">
                {result && (
                  <button
                    type="button"
                    className="study-btn-secondary"
                    onClick={() => setShowConfig(false)}
                  >
                    Retour aux résultats actuels
                  </button>
                )}
                <button
                  type="button"
                  className="study-btn-launch"
                  onClick={() => handleGenerate()}
                  disabled={loading}
                >
                  <Sparkles size={16} />
                  <span>
                    Générer {count} {kind === "flashcards" ? "Flashcards 3D" : "Questions de Quizz"}
                  </span>
                </button>
              </div>
            </div>
          )}

          {/* VUE 3 : RÉSULTATS INTERACTIFS */}
          {!loading && !showConfig && result && (
            <div className="study-results-view">
              {/* Barre d'outils du résultat */}
              <div className="study-results-toolbar">
                <div className="study-results-toolbar-left">
                  <div className="study-active-pill">
                    <span>{result.kind === "flashcards" ? "📇 Flashcards" : "🎯 Quizz QCM"}</span>
                    <small>({result.count} cartes · {difficultyMeta.label})</small>
                  </div>
                  <span className="study-results-topic-label" title={result.topic}>
                    Sujet : <strong>{result.topic}</strong>
                  </span>
                </div>

                <div className="study-results-toolbar-right">
                  <button
                    type="button"
                    className="study-toolbar-btn"
                    onClick={() => setShowConfig(true)}
                    title="Modifier le nombre, la difficulté ou régénérer"
                  >
                    <Sliders size={14} />
                    <span>Ajuster / Régénérer</span>
                  </button>

                  <button
                    type="button"
                    className="study-toolbar-btn"
                    onClick={() => handleGenerate(result.kind === "flashcards" ? "quiz" : "flashcards")}
                    title={`Générer directement ${result.kind === "flashcards" ? "un Quizz QCM" : "des Flashcards 3D"} sur ce même sujet`}
                  >
                    <RotateCcw size={14} />
                    <span>{result.kind === "flashcards" ? "Créer le Quizz" : "Créer les Flashcards"}</span>
                  </button>

                  <button
                    type="button"
                    className="study-toolbar-btn"
                    onClick={handleCopyMarkdown}
                    title="Copier l'ensemble des cartes ou questions au format texte Markdown"
                  >
                    {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                    <span>{copied ? "Copié !" : "Copier"}</span>
                  </button>

                  {onSendToChat && (
                    <button
                      type="button"
                      className="study-toolbar-btn is-highlight"
                      onClick={handleInsertInChat}
                      title="Insérer ces cartes de révision dans le fil de la discussion"
                    >
                      <MessageSquareQuote size={14} />
                      <span>Insérer dans le tchat</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Rendu interactif selon le format */}
              <div className="study-interactive-container">
                {result.kind === "flashcards" && result.flashcards && result.flashcards.length > 0 && (
                  <LearnFlashcards
                    flashcards={result.flashcards}
                    title={`${result.flashcards.length} Flashcards Interactives · ${result.topic}`}
                    subtitle={`Entraînez-vous activement sur « ${result.topic} ». Niveau : ${difficultyMeta.label}. Retournez les cartes au clic ou avec Espace.`}
                  />
                )}

                {result.kind === "quiz" && result.questions && result.questions.length > 0 && (
                  <LearnQuiz
                    questions={result.questions}
                    title={`Quizz d'Auto-évaluation (${result.questions.length} QCM) · ${result.topic}`}
                    subtitle={`Testez votre maîtrise sur « ${result.topic} » (Niveau ${difficultyMeta.label}). Choisissez l'option correcte pour afficher la justification experte.`}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
