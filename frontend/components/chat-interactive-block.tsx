"use client";

import { useState, type ReactNode } from "react";
import type { ClozeTestItem, Flashcard, QuizQuestion } from "@/lib/api";
import { LearnCloze } from "@/components/learn-cloze";
import { LearnFlashcards } from "@/components/learn-flashcards";
import { LearnQuiz } from "@/components/learn-quiz";

export type InteractiveKind = "quiz" | "flashcards" | "cloze";

const MAX_ITEMS = 50;
const MIN_COUNT = 3;
const MAX_COUNT = 30;
const DIFFICULTIES = ["facile", "moyenne", "difficile"] as const;
const KIND_LABEL: Record<InteractiveKind, string> = { quiz: "quizz (QCM)", flashcards: "flashcards", cloze: "textes à trous" };

/** Retourne le type d'exercice si le bloc de code Markdown est un bloc `clair-*`. */
export function interactiveKindFromClass(className?: string): InteractiveKind | null {
  const match = /(?:^|\s)language-clair-(quiz|flashcards|cloze)(?:\s|$)/.exec(className ?? "");
  return match ? (match[1] as InteractiveKind) : null;
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const str = (v: unknown) => (typeof v === "string" ? v : "");
const strList = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

function parseQuiz(data: unknown[]): QuizQuestion[] {
  return data.flatMap((raw, i) => {
    if (!isObj(raw)) return [];
    const options = strList(raw.options);
    const answer = Number(raw.answer);
    if (!str(raw.question) || options.length < 2 || !Number.isInteger(answer) || answer < 0 || answer >= options.length) return [];
    return [{ id: i + 1, question: str(raw.question), options, answer, explanation: str(raw.explanation) }];
  });
}

function parseFlashcards(data: unknown[]): Flashcard[] {
  return data.flatMap((raw, i) => {
    if (!isObj(raw) || !str(raw.recto) || !str(raw.verso)) return [];
    return [{ id: i + 1, category: str(raw.category) || "Général", recto: str(raw.recto), verso: str(raw.verso) }];
  });
}

function parseCloze(data: unknown[]): ClozeTestItem[] {
  return data.flatMap((raw, i) => {
    if (!isObj(raw)) return [];
    const missing = strList(raw.missing_words);
    const text = str(raw.text_with_blanks) || str(raw.sentence);
    if (!text || !missing.length) return [];
    const options = strList(raw.options);
    const hints = strList(raw.hints);
    return [{
      id: i + 1,
      sentence: str(raw.sentence) || text,
      text_with_blanks: text,
      missing_words: missing,
      hints: hints.length ? hints : undefined,
      options: options.length ? options : undefined,
      explanation: str(raw.explanation) || undefined,
    }];
  });
}

/** Réglage du nombre et de la difficulté ; envoie une demande de régénération dans le tchat. */
function ExerciseControls({ kind, count, onRegenerate }: { kind: InteractiveKind; count: number; onRegenerate: (prompt: string) => void }) {
  const [n, setN] = useState(Math.min(MAX_COUNT, Math.max(MIN_COUNT, count)));
  const [difficulty, setDifficulty] = useState<(typeof DIFFICULTIES)[number]>("moyenne");
  const safeN = Math.min(MAX_COUNT, Math.max(MIN_COUNT, Number.isFinite(n) ? Math.round(n) : count));
  return (
    <div className="chat-exercise-controls" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", margin: "8px 0", fontSize: 13 }}>
      <label>Nombre{" "}
        <input type="number" min={MIN_COUNT} max={MAX_COUNT} value={n} onChange={event => setN(Number(event.target.value))} style={{ width: 64 }} />
      </label>
      <label>Difficulté{" "}
        <select value={difficulty} onChange={event => setDifficulty(event.target.value as (typeof DIFFICULTIES)[number])}>
          {DIFFICULTIES.map(level => <option key={level} value={level}>{level}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => onRegenerate(`Génère un nouveau ${KIND_LABEL[kind]} sur le même sujet : ${safeN} éléments, difficulté ${difficulty}.`)}>
        Régénérer
      </button>
    </div>
  );
}

/**
 * Affiche un bloc ```clair-quiz|flashcards|cloze``` avec les composants Learn existants.
 * Le JSON est validé ; s'il est incomplet (streaming) ou invalide, un message d'attente/erreur est affiché.
 */
export function ChatInteractiveBlock({ kind, source, streaming, onRegenerate }: { kind: InteractiveKind; source: string; streaming: boolean; onRegenerate?: (prompt: string) => void }): ReactNode {
  let data: unknown;
  try {
    data = JSON.parse(source);
  } catch {
    return <div className="code-block"><div className="code-label"><span>{streaming ? "Préparation de l’exercice interactif…" : "Exercice illisible (JSON invalide)"}</span></div></div>;
  }
  const withControls = (node: ReactNode, count: number) => (
    <>{node}{onRegenerate && !streaming && <ExerciseControls kind={kind} count={count} onRegenerate={onRegenerate} />}</>
  );
  const list = (Array.isArray(data) ? data : []).slice(0, MAX_ITEMS);
  if (kind === "quiz") {
    const questions = parseQuiz(list);
    if (questions.length) return withControls(<LearnQuiz questions={questions} title={`Quizz · ${questions.length} questions`} />, questions.length);
  } else if (kind === "flashcards") {
    const flashcards = parseFlashcards(list);
    if (flashcards.length) return withControls(<LearnFlashcards flashcards={flashcards} title={`${flashcards.length} flashcards`} />, flashcards.length);
  } else {
    const clozeItems = parseCloze(list);
    if (clozeItems.length) return withControls(<LearnCloze clozeItems={clozeItems} title={`Textes à trous · ${clozeItems.length} exercices`} />, clozeItems.length);
  }
  return <div className="code-block"><div className="code-label"><span>Exercice vide ou mal formé</span></div></div>;
}
