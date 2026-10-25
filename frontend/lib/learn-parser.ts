import type { Flashcard, QuizQuestion } from "./api";

/**
 * Extrait ou synthétise scrupuleusement 20 flashcards à partir du contenu Markdown du cours.
 */
export function parseFlashcardsFromMarkdown(mdText: string, topic: string = ""): Flashcard[] {
  const cards: Flashcard[] = [];

  // 1. Détection des blocs formalisés "### Flashcard X"
  const flashcardBlockRegex = /###\s*Flashcard\s*(\d+)[:\s\-*]*\n+(?:[-*]\s*)?\*\*Recto\s*:\*\*\s*([\s\S]+?)\n+(?:[-*]\s*)?\*\*Verso\s*:\*\*\s*([\s\S]+?)(?=\n+###|\n+##|\n*---|\Z)/gi;
  let match: RegExpExecArray | null;
  while ((match = flashcardBlockRegex.exec(mdText)) !== null) {
    const recto = match[2].trim().replace(/^\[|\]$/g, "");
    const verso = match[3].trim().replace(/^\[|\]$/g, "");
    if (recto && verso) {
      cards.push({
        id: cards.length + 1,
        category: "Point Clé",
        recto,
        verso,
      });
      if (cards.length >= 20) break;
    }
  }

  // 2. Extraction des définitions (- **Terme :** Définition)
  if (cards.length < 20) {
    const existingRectos = new Set(cards.map((c) => c.recto.toLowerCase()));
    const defRegex = /[-*]\s+\*\*([^*\n]+?)(?:\s*:)?\*\*\s*:?\s*(.+)/g;
    while ((match = defRegex.exec(mdText)) !== null) {
      const term = match[1].trim();
      const def = match[2].trim();
      const lowerTerm = term.toLowerCase();
      if (
        lowerTerm.startsWith("recto") ||
        lowerTerm.startsWith("verso") ||
        lowerTerm.startsWith("énoncé") ||
        lowerTerm.startsWith("bonne réponse") ||
        lowerTerm.startsWith("explication")
      ) {
        continue;
      }
      const recto = `Qu'est-ce que « ${term} » et quel est son rôle ?`;
      if (!existingRectos.has(recto.toLowerCase()) && def.length > 15) {
        existingRectos.add(recto.toLowerCase());
        cards.push({
          id: cards.length + 1,
          category: "Définition & Rôle",
          recto,
          verso: def,
        });
        if (cards.length >= 20) break;
      }
    }
  }

  // 3. Extraction des sous-parties de cours (### Titre)
  if (cards.length < 20) {
    const existingRectos = new Set(cards.map((c) => c.recto.toLowerCase()));
    const hRegex = /###?\s+([^\n#]+)\n+([^\n#]+)/g;
    while ((match = hRegex.exec(mdText)) !== null) {
      const title = match[1].trim();
      const body = match[2].trim();
      const lower = title.toLowerCase();
      if (
        lower.includes("flashcard") ||
        lower.includes("quiz") ||
        lower.includes("quizz") ||
        lower.includes("sommaire") ||
        lower.includes("table des")
      ) {
        continue;
      }
      const recto = `Expliquez le principe fondamental de : « ${title} »`;
      if (!existingRectos.has(recto.toLowerCase()) && body.length > 25) {
        existingRectos.add(recto.toLowerCase());
        cards.push({
          id: cards.length + 1,
          category: "Mécanisme",
          recto,
          verso: body,
        });
        if (cards.length >= 20) break;
      }
    }
  }

  // 4. Modèles de secours pour garantir 20 flashcards
  const cleanTopic = topic.trim() || "le sujet étudié";
  const fallbackTemplates = [
    ["Fondations", `Quelle est la finalité première de : ${cleanTopic} ?`, "Résoudre les limitations des approches naïves en structurant une démarche rigoureuse, reproductible et méthodique."],
    ["Méthodologie", `Quelle est la première étape indispensable lors de l'étude de : ${cleanTopic} ?`, "Analyser attentivement le cadre, identifier les prérequis et délimiter précisément le périmètre d'action."],
    ["Règle d'or", `Quelle est la règle cardinale pour maîtriser : ${cleanTopic} ?`, "Ne jamais se fier aux impressions subjectives : toujours appuyer ses affirmations sur des éléments tangibles et vérifiables."],
    ["Architecture", `Quels sont les piliers fondamentaux qui composent : ${cleanTopic} ?`, "Une solide compréhension théorique, une méthode de décomposition systématique et une mise en pratique rigoureuse."],
    ["Auto-contrôle", `Comment vérifier l'exactitude de sa démarche sur : ${cleanTopic} ?`, "Utiliser une grille critériée d'auto-évaluation et confronter ses résultats aux cas limites et contre-exemples."],
    ["Approfondissement", `Quelle est la compétence avancée à développer sur : ${cleanTopic} ?`, "Savoir anticiper les cas atypiques, maîtriser les subtilités d'analyse et adapter la stratégie aux contraintes réelles."],
    ["Anti-pattern", `Quelle est l'erreur la plus courante commise par les débutants sur : ${cleanTopic} ?`, "La précipitation et l'omission des étapes d'analyse préliminaire au profit d'une exécution directe non cadrée."],
    ["Synthèse", `Quel est le lien entre théorie et pratique dans : ${cleanTopic} ?`, "La théorie éclaire la structure des décisions, tandis que la pratique affine l'intuition et éprouve la solidité des modèles."],
    ["Vocabulaire", `Pourquoi employer un vocabulaire technique précis dans : ${cleanTopic} ?`, "Nommer rigoureusement les concepts permet de penser clairement et d'éliminer toute ambiguïté intellectuelle."],
    ["Excellence", `Qu'est-ce qui distingue un praticien expert d'un novice dans : ${cleanTopic} ?`, "La capacité à diagnostiquer rapidement les dysfonctionnements et à justifier chaque choix avec méthode."],
  ];

  let fbIdx = 0;
  while (cards.length < 20) {
    const [cat, r, v] = fallbackTemplates[fbIdx % fallbackTemplates.length];
    cards.push({
      id: cards.length + 1,
      category: cat,
      recto: `${r} (Point clé #${cards.length + 1})`,
      verso: v,
    });
    fbIdx++;
  }

  return cards.slice(0, 20);
}

/**
 * Extrait ou synthétise scrupuleusement 20 questions de quiz (QCM 4 options) avec explications.
 */
export function parseQuizFromMarkdown(mdText: string, topic: string = ""): QuizQuestion[] {
  const questions: QuizQuestion[] = [];

  // 1. Détection des blocs formalisés
  const qRegex = /(?:###|\*\*)\s*Question\s*(\d+)[:\s\-*]*\n*(?:[-*]\s*)?([\s\S]*?)\n+(?:[-*]\s*)?A\)\s*([\s\S]*?)\n+(?:[-*]\s*)?B\)\s*([\s\S]*?)\n+(?:[-*]\s*)?C\)\s*([\s\S]*?)\n+(?:[-*]\s*)?D\)\s*([\s\S]*?)\n+(?:[-*]\s*)?(?:\*\*Bonne réponse\s*:\*\*\s*|Bonne réponse\s*:\s*)([A-D])\b[\s\S]*?\n+(?:[-*]\s*)?(?:\*\*Explication\s*:\*\*\s*|Explication\s*:\s*)([\s\S]*?)(?=\n*(?:###|\*\*)\s*Question|\n*#{1,3}\s|\Z)/gi;
  let match: RegExpExecArray | null;
  const letterMap: Record<string, number> = { A: 0, B: 1, C: 2, D: 3 };

  while ((match = qRegex.exec(mdText)) !== null) {
    const rawQ = match[2].trim().replace(/^\*?\*?Énoncé\s*:\*?\*?\s*/i, "");
    const optA = match[3].trim();
    const optB = match[4].trim();
    const optC = match[5].trim();
    const optD = match[6].trim();
    const letter = match[7].trim().toUpperCase();
    const explanation = match[8].trim();

    if (rawQ && optA && optB && optC && optD && letter in letterMap) {
      questions.push({
        id: questions.length + 1,
        question: rawQ,
        options: [optA, optB, optC, optD],
        answer: letterMap[letter],
        explanation: explanation || "Explication validée conforme aux règles méthodologiques du cours.",
      });
      if (questions.length >= 20) break;
    }
  }

  // 2. Modèles de secours pour garantir 20 questions
  const cleanTopic = topic.trim() || "le domaine étudié";
  const fallbackTemplates = [
    {
      q: `Quelle est la finalité principale de la méthode présentée dans ce cours sur ${cleanTopic} ?`,
      options: [
        "Fournir un cadre rigoureux, reproductible et méthodique pour réussir ses analyses et projets",
        "Remplacer l'apprentissage par de la simple mémorisation passive sans réflexion",
        "Éviter toute confrontation avec des cas réels complexes",
        "Se limiter à une lecture rapide sans exercices d'application",
      ],
      ans: 0,
      expl: "L'ancrage durable du savoir repose sur la compréhension du mécanisme et la validation pratique immédiate.",
    },
    {
      q: `Lorsqu'on aborde une notion complexe dans ${cleanTopic}, que conseille la méthode d'excellence ?`,
      options: [
        "L'apprentissage linéaire passif sans prise de notes",
        "La décomposition en sous-problèmes plus simples et l'analyse méthodique des composants",
        "Ignorer les prérequis pour passer directement au niveau expert",
        "Attendre l'évaluation finale avant de s'exercer",
      ],
      ans: 1,
      expl: "La décomposition méthodique (diviser pour régner) permet de dompter la complexité sans saturation cognitive.",
    },
    {
      q: `Quelle est la principale source d'erreur identifiée dans la pratique de ${cleanTopic} ?`,
      options: [
        "L'excès de rigueur méthodologique",
        "La confusion entre description superficielle et analyse causale approfondie",
        "L'utilisation d'exemples concrets",
        "La consultation de documentations de référence",
      ],
      ans: 1,
      expl: "Le survol descriptif ne permet pas de démontrer les mécanismes sous-jacents, source de contre-sens fréquents.",
    },
    {
      q: `Quelle attitude est recommandée face à une contradiction apparente dans ${cleanTopic} ?`,
      options: [
        "Choisir arbitrairement la première source consultée",
        "Remonter aux sources primaires et examiner les conditions d'application respectives",
        "Supprimer les deux éléments pour éviter les questions gênantes",
        "Considérer que les deux affirmations sont nécessairement fausses",
      ],
      ans: 1,
      expl: "L'esprit critique universitaire exige d'identifier le contexte et le périmètre de validité de chaque affirmation.",
    },
    {
      q: `Comment mesurer concrètement sa progression dans la maîtrise de ${cleanTopic} ?`,
      options: [
        "En étant capable d'expliquer la notion simplement et de résoudre des cas réels en autonomie",
        "En ayant lu le cours une seule fois en diagonale",
        "En évitant de se tester pour ne pas douter",
        "En mémorisant uniquement les acronymes sans leur sens",
      ],
      ans: 0,
      expl: "La technique de Feynman (expliquer simplement) et la résolution de cas réels constituent les meilleurs tests de maîtrise.",
    },
    {
      q: `Quel est le rôle des pièges et anti-patterns présentés dans ce cours ?`,
      options: [
        "Décourager l'apprenant face aux difficultés",
        "Développer des réflexes de diagnostic pour anticiper et corriger les erreurs courantes",
        "Remplacer les règles fondamentales par des exceptions",
        "Compliquer inutilement l'apprentissage",
      ],
      ans: 1,
      expl: "L'étude des anti-patterns permet d'acquérir les réflexes d'un praticien chevronné.",
    },
    {
      q: `Quelle est la fonction d'une grille critériée d'auto-évaluation ?`,
      options: [
        "Fournir une checklist objective pour vérifier chaque point d'exigence avant de valider son travail",
        "Attribuer une note arbitraire sans justification",
        "Remplacer la rédaction par des cases à cocher",
        "Ignorer les critères de rigueur académique",
      ],
      ans: 0,
      expl: "L'auto-évaluation critériée responsabilise l'apprenant et sécurise la conformité aux exigences formelles.",
    },
    {
      q: `Pourquoi est-il primordial de s'exercer activement avec des flashcards ?`,
      options: [
        "Parce que la répétition espacée et le rappel actif renforcent durablement les connexions synaptiques",
        "Parce que c'est un simple passe-temps sans effet prouvé",
        "Pour éviter de devoir lire le cours",
        "Uniquement pour réviser la veille d'un examen sans suivi",
      ],
      ans: 0,
      expl: "Les sciences cognitives ont démontré que l'effort de récupération active consolide les traces mnésiques à long terme.",
    },
  ];

  let fbIdx = 0;
  while (questions.length < 20) {
    const item = fallbackTemplates[fbIdx % fallbackTemplates.length];
    questions.push({
      id: questions.length + 1,
      question: `${item.q} (Question de synthèse #${questions.length + 1})`,
      options: item.options,
      answer: item.ans,
      explanation: item.expl,
    });
    fbIdx++;
  }

  return questions.slice(0, 20);
}

/**
 * Détecte si un texte contient les modules interactifs (Module 8 Flashcards ou Module 9 Quizz).
 */
export function hasInteractiveLearnModules(mdText: string): boolean {
  if (!mdText) return false;
  return (
    /(?:^|\n)#{1,4}\s*(?:📇|🎯)?\s*(?:Module\s*8\b|(?:20\s*)?Flashcards?\b|Module\s*9\b|(?:20\s*)?Quizz?\b|Questions?\s*de\s*Quizz\b)/i.test(mdText) ||
    /###\s*Flashcard\s*\d+/i.test(mdText) ||
    /###\s*Question\s*\d+/i.test(mdText)
  );
}

/**
 * Retire les modules bruts 8 et 9 du Markdown pour éviter les doublons textuels avant les composants interactifs,
 * et empêcher la divulgation des réponses (spoils) dans le fil de discussion tchat.
 */
export function stripInteractiveModulesForBody(mdText: string): string {
  if (!mdText) return "";
  const match = mdText.search(
    /(?:^|\n)#{1,4}\s*(?:📇|🎯)?\s*(?:Module\s*8\b|(?:20\s*)?Flashcards?\b|Module\s*9\b|(?:20\s*)?Quizz?\b|Questions?\s*de\s*Quizz\b)/i
  );
  if (match !== -1) {
    return mdText.substring(0, match).trim();
  }
  return mdText;
}
