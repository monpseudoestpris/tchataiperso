"use client";

import { useEffect, useState } from "react";
import {
  BookOpen,
  Brain,
  Check,
  CircleAlert,
  Copy,
  FileText,
  GraduationCap,
  HelpCircle,
  Layers,
  LoaderCircle,
  MessageSquareQuote,
  Pencil,
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
  type ClozeTestItem,
  type StudyMaterialResponse,
} from "@/lib/api";
import { LearnFlashcards } from "@/components/learn-flashcards";
import { LearnQuiz } from "@/components/learn-quiz";
import { LearnCloze } from "@/components/learn-cloze";

type StudyModalProps = {
  isOpen: boolean;
  conversation?: Conversation | null;
  initialKind?: "flashcards" | "quiz" | "cloze" | "all";
  initialCourseText?: string;
  onClose: () => void;
  onSendToChat?: (content: string) => void;
};

type Difficulty = "easy" | "medium" | "hard";

const COUNT_PRESETS = [
  { count: 5, label: "5 éléments", hint: "Express (~3 min)" },
  { count: 10, label: "10 éléments", hint: "Standard (~6 min)" },
  { count: 15, label: "15 éléments", hint: "Approfondi (~10 min)" },
  { count: 20, label: "20 éléments", hint: "Examen (~15 min)" },
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
  initialCourseText = "",
  onClose,
  onSendToChat,
}: StudyModalProps) {
  const [kind, setKind] = useState<"flashcards" | "quiz" | "cloze" | "all">(initialKind);
  const [sourceMode, setSourceMode] = useState<"conversation" | "custom">("custom");
  const [courseText, setCourseText] = useState<string>("");
  const [count, setCount] = useState<number>(10);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [topic, setTopic] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showConfig, setShowConfig] = useState(true);

  // Pour naviguer entre les activités quand "Pack Complet" (all) est sélectionné
  const [activePackTab, setActivePackTab] = useState<"flashcards" | "quiz" | "cloze">("flashcards");

  // Stockage des résultats
  const [result, setResult] = useState<StudyMaterialResponse | null>(null);

  // Initialisation à l'ouverture
  useEffect(() => {
    if (isOpen) {
      if (initialCourseText && initialCourseText.trim()) {
        setCourseText(initialCourseText);
        setSourceMode("custom");
      } else if (conversation && conversation.title) {
        setSourceMode("conversation");
      } else {
        setSourceMode("custom");
      }

      const defaultTopic =
        conversation?.title && conversation.title !== "Nouvelle conversation"
          ? conversation.title
          : conversation?.theme ||
            (initialCourseText ? initialCourseText.split("\n")[0].replace(/^#+\s*/, "").slice(0, 60) : "Sujet de cours");

      setTopic(defaultTopic);
      setKind(initialKind);
      setError(null);
    }
  }, [isOpen, conversation, initialKind, initialCourseText]);

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

  if (!isOpen) {
    return null;
  }

  async function handleGenerate(targetKind?: "flashcards" | "quiz" | "cloze" | "all") {
    const activeKind = targetKind || kind;
    setKind(activeKind);
    setLoading(true);
    setError(null);

    const isUsingCustom = sourceMode === "custom" || !conversation;
    if (isUsingCustom && !courseText.trim()) {
      setError("Veuillez saisir ou coller le texte de votre cours pour générer les révisions.");
      setLoading(false);
      return;
    }

    try {
      const data = await generateStudyMaterial(isUsingCustom ? null : conversation?.id, {
        kind: activeKind,
        count,
        difficulty,
        topic:
          topic.trim() ||
          conversation?.title ||
          (courseText.trim() ? courseText.trim().split("\n")[0].replace(/^#+\s*/, "").slice(0, 60) : "Cours"),
        course_text: isUsingCustom ? courseText.trim() : undefined,
      });
      setResult(data);
      setShowConfig(false);
      if (activeKind === "all") {
        setActivePackTab("flashcards");
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  function handleCopyMarkdown() {
    if (!result) return;
    let md = "";

    if (result.flashcards && result.flashcards.length > 0) {
      md += `# 📇 Flashcards de révision : ${result.topic}\n\n`;
      md += `*Niveau : ${difficulty} · ${result.flashcards.length} cartes de mémorisation active*\n\n`;
      result.flashcards.forEach((card, idx) => {
        md += `### Flashcard ${idx + 1} (${card.category || "Point Clé"})\n`;
        md += `**Recto :** ${card.recto}\n`;
        md += `**Verso :** ${card.verso}\n\n`;
      });
    }

    if (result.questions && result.questions.length > 0) {
      md += `# 🎯 Quizz d'auto-évaluation : ${result.topic}\n\n`;
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

    if (result.cloze_items && result.cloze_items.length > 0) {
      md += `# ✍️ Phrases à trous de révision : ${result.topic}\n\n`;
      md += `*Niveau : ${difficulty} · ${result.cloze_items.length} exercices Cloze test*\n\n`;
      result.cloze_items.forEach((item, idx) => {
        md += `### Exercice ${idx + 1}\n`;
        md += `> ${item.text_with_blanks || item.sentence}\n\n`;
        md += `*Terme(s) manquant(s) :* **${item.missing_words.join(", ")}**\n`;
        if (item.explanation) {
          md += `*Justification :* ${item.explanation}\n\n`;
        }
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

    if (result.flashcards && result.flashcards.length > 0) {
      text += `### 📇 Flashcards sur « ${result.topic} »\n\n`;
      result.flashcards.forEach((c, idx) => {
        text += `**${idx + 1}. [${c.category || "Point Clé"}]** ${c.recto}\n*→ ${c.verso}*\n\n`;
      });
    }

    if (result.questions && result.questions.length > 0) {
      text += `### 🎯 Quizz QCM sur « ${result.topic} »\n\n`;
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

    if (result.cloze_items && result.cloze_items.length > 0) {
      text += `### ✍️ Phrases à trous sur « ${result.topic} »\n\n`;
      result.cloze_items.forEach((c, idx) => {
        text += `**Exercice ${idx + 1} :** ${c.text_with_blanks || c.sentence}\n`;
        text += `*Mots clés : ${c.missing_words.join(", ")}* (${c.explanation})\n\n`;
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
              <GraduationCap size={20} />
            </span>
            <div className="deepsearch-modal-title-group">
              <div className="deepsearch-modal-eyebrow study-modal-eyebrow">
                <Sparkles size={12} />
                <span>ESPACE RÉVISION & ENTRAÎNEMENT DIDACTIQUE</span>
              </div>
              <h2 id="study-modal-title">Mode Réviser · Flashcards, Quizz & Phrases à trous</h2>
              <div className="study-modal-subheading">
                {conversation?.title ? (
                  <span>
                    Discussion liée : <strong>{conversation.title}</strong>
                  </span>
                ) : (
                  <span>Cours personnalisé ou extrait libre</span>
                )}
                {conversation?.theme && (
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
              <h3>Conception pédagogique de vos révisions…</h3>
              <p>
                Analyse du cours et extraction des définitions et mécanismes clés pour concevoir vos{" "}
                <strong>
                  {count}{" "}
                  {kind === "flashcards"
                    ? "Flashcards 3D"
                    : kind === "quiz"
                    ? "Questions de Quizz"
                    : kind === "cloze"
                    ? "Phrases à trous"
                    : "Activités complètes (Flash, Quizz, Trous)"}
                </strong>{" "}
                ({difficultyMeta.label}).
              </p>
              <div className="study-loading-steps">
                <span>✓ Analyse didactique du cours & des notions clés</span>
                <span>⚡ Formulation des questions, réponses et pièges didactiques</span>
                <span>✨ Génération de vos supports de révision interactive</span>
              </div>
            </div>
          )}

          {/* VUE 2 : CONFIGURATION DES PARAMÈTRES */}
          {!loading && (showConfig || !result) && (
            <div className="study-config-panel">
              <div className="study-config-intro">
                <p>
                  Mettez votre cours ou vos notes de révision pour générer instantanément des flashcards 3D,
                  un quizz à choix multiples ou des phrases à trous interactives.
                </p>
              </div>

              {/* 1. SOURCE DU COURS : Discussion OU Saisie personnalisée */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <BookOpen size={15} />
                  <span>1. Source du cours à réviser</span>
                </label>
                <div className="study-source-tabs">
                  <button
                    type="button"
                    className={`study-source-tab ${sourceMode === "custom" ? "is-active" : ""}`}
                    onClick={() => setSourceMode("custom")}
                  >
                    <FileText size={13} />
                    <span>Coller / Écrire un cours</span>
                  </button>
                  {conversation && (
                    <button
                      type="button"
                      className={`study-source-tab ${sourceMode === "conversation" ? "is-active" : ""}`}
                      onClick={() => setSourceMode("conversation")}
                    >
                      <MessageSquareQuote size={13} />
                      <span>Utiliser les échanges du tchat</span>
                    </button>
                  )}
                </div>

                {sourceMode === "custom" && (
                  <div className="study-course-input-wrap">
                    <textarea
                      className="study-course-textarea"
                      placeholder="Collez ici votre cours, vos notes, un résumé ou les définitions à réviser (ex: architecture Docker, cours de SVT, histoire, programmation, droit...)"
                      value={courseText}
                      onChange={(e) => setCourseText(e.target.value)}
                      maxLength={40000}
                    />
                    <div className="study-course-meta">
                      <span>{courseText.length} caractères saisis</span>
                      {courseText && (
                        <button
                          type="button"
                          className="text-xs text-rose-500 hover:underline"
                          onClick={() => setCourseText("")}
                        >
                          Effacer le cours
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* 2. SÉLECTEUR DE FORMAT D'APPRENTISSAGE */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <Layers size={15} />
                  <span>2. Choisissez vos activités de révision</span>
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
                      Évaluation méthodique avec validation directe vert/rouge, explications expertes détaillées, calcul de score en direct et trophée.
                    </p>
                    <div className="study-format-card-footer">
                      <span className="study-format-badge">Score direct & Explications</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`study-format-card ${kind === "cloze" ? "is-selected" : ""}`}
                    onClick={() => setKind("cloze")}
                  >
                    <div className="study-format-card-header">
                      <span className="study-format-card-icon">✍️</span>
                      <div className="study-format-card-name">
                        <strong>Phrases à trous</strong>
                        <small>Cloze test interactif & auto-complétion</small>
                      </div>
                    </div>
                    <p>
                      Complétez les notions clés directement au clavier ou via la banque de mots cliquables. Vérification immédiate, indices et solutions.
                    </p>
                    <div className="study-format-card-footer">
                      <span className="study-format-badge">Banque de mots & Indices</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    className={`study-format-card ${kind === "all" ? "is-selected" : ""}`}
                    onClick={() => setKind("all")}
                  >
                    <div className="study-format-card-header">
                      <span className="study-format-card-icon">🌟</span>
                      <div className="study-format-card-name">
                        <strong>Pack Révision Complet</strong>
                        <small>Flashcards + Quizz + Phrases à trous</small>
                      </div>
                    </div>
                    <p>
                      Générez en une seule fois l'ensemble des 3 formats pour un entraînement exhaustif à 360° sur votre cours.
                    </p>
                    <div className="study-format-card-footer">
                      <span className="study-format-badge">Pack 3-en-1</span>
                    </div>
                  </button>
                </div>
              </div>

              {/* 3. NOMBRE DE CARTES / QUESTIONS */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <Sliders size={15} />
                  <span>
                    3. Nombre d'éléments par activité : <strong>{count}</strong>
                  </span>
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

              {/* 4. NIVEAU DE DIFFICULTÉ */}
              <div className="study-section-block">
                <label className="study-section-title">
                  <GraduationCap size={15} />
                  <span>4. Niveau d'exigence</span>
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

              {/* 5. SUJET / FOCUS OPTIONNEL */}
              <div className="study-section-block">
                <label htmlFor="study-topic-input" className="study-section-title">
                  <WandSparkles size={15} />
                  <span>5. Sujet ou titre du cours (optionnel)</span>
                </label>
                <input
                  id="study-topic-input"
                  type="text"
                  className="study-topic-input"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="Ex: Architecture des microservices, La Révolution française, Les pointeurs en C..."
                  maxLength={160}
                />
                <span className="study-topic-hint">
                  Permet de guider et contextualiser l'intitulé de vos fiches de révision.
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
                    Générer{" "}
                    {kind === "all"
                      ? "le Pack Complet de Révision"
                      : `${count} ${
                          kind === "flashcards"
                            ? "Flashcards 3D"
                            : kind === "quiz"
                            ? "Questions de Quizz"
                            : "Phrases à trous"
                        }`}
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
                    <span>
                      {result.kind === "flashcards"
                        ? "📇 Flashcards"
                        : result.kind === "quiz"
                        ? "🎯 Quizz QCM"
                        : result.kind === "cloze"
                        ? "✍️ Phrases à trous"
                        : "🌟 Pack Révision 3-en-1"}
                    </span>
                    <small>({difficultyMeta.label})</small>
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
                    title="Modifier le cours, le nombre ou régénérer"
                  >
                    <Sliders size={14} />
                    <span>Ajuster / Nouveau cours</span>
                  </button>

                  <button
                    type="button"
                    className="study-toolbar-btn"
                    onClick={handleCopyMarkdown}
                    title="Copier toutes les activités au format texte Markdown"
                  >
                    {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                    <span>{copied ? "Copié !" : "Copier Markdown"}</span>
                  </button>

                  {onSendToChat && (
                    <button
                      type="button"
                      className="study-toolbar-btn is-highlight"
                      onClick={handleInsertInChat}
                      title="Insérer ces supports de révision dans le fil de discussion"
                    >
                      <MessageSquareQuote size={14} />
                      <span>Insérer dans le tchat</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Si Pack Complet : Onglets pour basculer facilement entre les 3 activités */}
              {result.kind === "all" && (
                <div className="study-pack-tabs">
                  <button
                    type="button"
                    className={`study-pack-tab ${activePackTab === "flashcards" ? "is-active" : ""}`}
                    onClick={() => setActivePackTab("flashcards")}
                  >
                    <span>📇 Flashcards 3D ({result.flashcards?.length || 0})</span>
                  </button>
                  <button
                    type="button"
                    className={`study-pack-tab ${activePackTab === "quiz" ? "is-active" : ""}`}
                    onClick={() => setActivePackTab("quiz")}
                  >
                    <span>🎯 Quizz QCM ({result.questions?.length || 0})</span>
                  </button>
                  <button
                    type="button"
                    className={`study-pack-tab ${activePackTab === "cloze" ? "is-active" : ""}`}
                    onClick={() => setActivePackTab("cloze")}
                  >
                    <span>✍️ Phrases à trous ({result.cloze_items?.length || 0})</span>
                  </button>
                </div>
              )}

              {/* Rendu interactif selon le format sélectionné */}
              <div className="study-interactive-container">
                {/* 1. Flashcards */}
                {((result.kind === "flashcards") || (result.kind === "all" && activePackTab === "flashcards")) &&
                  result.flashcards &&
                  result.flashcards.length > 0 && (
                    <LearnFlashcards
                      flashcards={result.flashcards}
                      title={`${result.flashcards.length} Flashcards Interactives · ${result.topic}`}
                      subtitle={`Entraînez-vous activement sur « ${result.topic} » (Niveau : ${difficultyMeta.label}). Espace pour retourner, Flèches pour naviguer.`}
                    />
                  )}

                {/* 2. Quizz */}
                {((result.kind === "quiz") || (result.kind === "all" && activePackTab === "quiz")) &&
                  result.questions &&
                  result.questions.length > 0 && (
                    <LearnQuiz
                      questions={result.questions}
                      title={`Quizz d'Auto-évaluation (${result.questions.length} Questions) · ${result.topic}`}
                      subtitle={`Testez votre maîtrise sur « ${result.topic} ». Choisissez l'option correcte pour afficher immédiatement l'explication didactique.`}
                    />
                  )}

                {/* 3. Phrases à trous */}
                {((result.kind === "cloze") || (result.kind === "all" && activePackTab === "cloze")) &&
                  result.cloze_items &&
                  result.cloze_items.length > 0 && (
                    <LearnCloze
                      clozeItems={result.cloze_items}
                      title={`Phrases à Trous (${result.cloze_items.length} Exercices) · ${result.topic}`}
                      subtitle={`Complétez les mots clés manquants sur « ${result.topic} ». Saisissez au clavier ou cliquez sur la banque de mots.`}
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
