"""Génération de matériel d'étude (flashcards, QCM, textes à trous) et repli heuristique ancré dans le cours."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .google_cloud import (
    ProviderError,
    can_fallback_to_model,
    check_response as _check_response,
    has_llm_access,
    json_body as _json,
    post_chat_completion,
)

_STUDY_TIMEOUT = httpx.Timeout(60.0, connect=10.0, pool=10.0)
_logger = logging.getLogger("uvicorn.error")


def _is_methodology_study_item(text: str) -> bool:
    """Détecte les questions et assertions méta ou de méthodologie générale à proscrire."""
    t = text.lower()
    meta_phrases = (
        "piège ou l'erreur courante à éviter avec",
        "piège fréquent",
        "première démarche recommandée pour aborder",
        "règle cardinale à respecter concernant",
        "objectif premier recherché lorsqu'on étudie",
        "comment met-on concrètement en œuvre :",
        "comment s'assurer de la validité d'une démarche",
        "distinction importante faut-il opérer dans",
        "maîtrise avancée de :",
        "apport majeur de la discussion sur",
        "quelle est la finalité principale abordée au sujet de",
        "face à une difficulté dans la mise en œuvre de",
        "l'objectif prioritaire dans l'étude de",
        "pour garantir la fiabilité d'une démarche sur",
        "documenter les choix méthodologiques pour assurer la traçabilité",
        "confondre la cause initiale d'un problème avec ses symptômes",
        "remise en question des résultats renforcent",
        "procéder de manière progressive et itérative",
        "se précipiter sur une solution superficielle",
        "analyser le cadre d'intervention",
        "quelle démarche",
        "comment s'organiser pour réviser",
    )
    return any(p in t for p in meta_phrases)


def fallback_study_material(
    transcript: str,
    kind: str = "flashcards",
    count: int = 10,
    difficulty: str = "medium",
    topic: str = "",
    course_text: str = "",
) -> dict[str, Any]:
    """Génération heuristique de secours ancrée rigoureusement dans le cours (sans questions méta-méthodologiques)."""
    count = max(1, min(count, 30))
    source_content = course_text.strip() if course_text and course_text.strip() else transcript

    clean_topic = topic.strip()
    if not clean_topic or clean_topic in ("le sujet abordé", "cette discussion", "le cours à réviser"):
        if course_text.strip():
            first_line = course_text.strip().splitlines()[0].strip("# ").strip()
            clean_topic = first_line[:120] if first_line else "le cours à réviser"
        else:
            clean_topic = "le sujet abordé"

    lines = [line.strip() for line in source_content.splitlines() if line.strip()]

    # Unités de cours extraites : (catégorie, recto/question, verso/réponse, concept_clé)
    extracted_units: list[dict[str, str]] = []
    seen_texts: set[tuple[str, str]] = set()

    def _add_unit(cat: str, r: str, v: str, concept: str = "") -> None:
        norm = (r.strip().lower(), v.strip().lower())
        if norm not in seen_texts and len(v.strip()) > 5:
            seen_texts.add(norm)
            extracted_units.append({
                "category": cat[:35],
                "recto": r.strip(),
                "verso": v.strip(),
                "concept": (concept or cat).strip()[:50],
            })

    # 1. Définitions numérotées ou à puces avec du gras : "1. **Direction** (la droite...)" ou "- **Image** : définition"
    for line in lines:
        match = re.match(r"^(?:[-*•]|\d+[\.)])\s*\*\*([^*]+?)\*\*\s*[:\-]?\s*(.+)", line)
        if match:
            k = match.group(1).strip().rstrip(":")
            v = match.group(2).strip()
            lower_k = k.lower()
            if len(v) > 6 and not any(lower_k.startswith(x) for x in ("bonne réponse", "recto", "verso", "explication", "option", "question", "attention", "remarque", "rappel")):
                _add_unit("Définition", f"Que désigne ou définit précisément « {k} » dans le cours ?", v, concept=k)

    # 2. Termes clés en gras au sein des phrases (ex: "Deux vecteurs sont **égaux** si...", "la **relation de Chasles**")
    for line in lines:
        if line.startswith("#") or line.startswith("---"):
            continue
        for b in re.findall(r"\*\*([^*]+?)\*\*", line):
            b_clean = b.strip().rstrip(":")
            if 3 <= len(b_clean) <= 40:
                lower_b = b_clean.lower()
                if not any(lower_b.startswith(x) for x in ("bonne réponse", "recto", "verso", "explication", "option", "question", "attention", "remarque", "une direction", "un sens", "une norme")):
                    clean_line = re.sub(r"[*_#]", "", line).strip()
                    if len(clean_line) > 15:
                        _add_unit("Point Clé", f"Concernant « {b_clean} », qu'énonce ou démontre le cours ?", clean_line, concept=b_clean)

    # 3. Titres de sections avec leur synthèse de contenu
    current_sec = ""
    sec_content: list[str] = []
    for line in lines:
        if line.startswith("#"):
            if current_sec and sec_content:
                summary = " ".join(sec_content[:3])
                _add_unit("Chapitre & Synthèse", f"Quels sont les points et résultats essentiels de la section « {current_sec} » ?", summary, concept=current_sec)
            current_sec = line.lstrip("#").strip()
            sec_content = []
        elif current_sec and not line.startswith("---") and not line.startswith("Où est-ce") and len(line) > 15:
            sec_content.append(line)
    if current_sec and sec_content:
        summary = " ".join(sec_content[:3])
        _add_unit("Chapitre & Synthèse", f"Quels sont les points et résultats essentiels de la section « {current_sec} » ?", summary, concept=current_sec)

    # 4. Formules mathématiques isolées ($$...$$ ou \[...\]) ou puces d'opérations
    for line in lines:
        if line.startswith("$$") or line.startswith(r"\["):
            _add_unit("Formule", f"À quoi correspond l'égalité ou la formule suivante : {line} ?", f"Formule et égalité fondamentale vue dans le cours : {line}", concept="Formule mathématique")
        elif re.match(r"^[-*•]\s+", line):
            cleaned = re.sub(r"^[-*•]\s+", "", line).strip()
            if len(cleaned) > 20:
                words = cleaned.split()
                snippet = " ".join(words[:5])
                _add_unit("Propriété & Règle", f"Énoncer la règle ou propriété du cours débutant par : « {snippet}... »", cleaned, concept=snippet)

    # 5. Décomposition en phrases substantielles si le contenu nécessite plus de matière
    if len(extracted_units) < count:
        for line in lines:
            if line.startswith("#") or line.startswith("---") or len(line) < 25:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", line)
            for s in sentences:
                s_clean = s.strip()
                if len(s_clean) > 25 and not s_clean.startswith("Où est-ce") and not s_clean.startswith("Tu veux") and not _is_methodology_study_item(s_clean):
                    words = s_clean.split()
                    lead = " ".join(words[:4])
                    _add_unit("Notion du cours", f"Dans le cours sur « {clean_topic} », que précise l'énoncé : « {lead}... » ?", s_clean, concept=lead)

    # 6. Variantes disciplinaires ciblées si le texte d'origine est très concis (aucun énoncé méta-méthodologique)
    course_aspects = [
        ("Définition clé", f"Quelle est la définition ou la notion fondamentale de : {clean_topic} ?", f"La définition formelle et les concepts structurants exposés dans le cadre de {clean_topic}."),
        ("Propriété majeure", f"Quelle propriété essentielle ou théorème caractérise : {clean_topic} ?", f"Les théorèmes, propriétés mathématiques ou lois régissant {clean_topic}."),
        ("Formule & Calcul", f"Comment s'exprime la relation ou la formule de calcul associée à : {clean_topic} ?", f"L'expression formelle, les relations d'égalité et les démarches de calcul vues pour {clean_topic}."),
        ("Règle d'application", f"Quelle règle d'application concrète doit-on mobiliser pour : {clean_topic} ?", f"La règle technique et les conditions d'application enseignées pour {clean_topic}."),
        ("Théorème associé", f"Quel résultat théorique majeur est établi au sujet de : {clean_topic} ?", f"L'énoncé théorique formel, ses hypothèses et sa conclusion pour {clean_topic}."),
        ("Cas d'application", f"Sur quel cas type ou calcul met-on en œuvre : {clean_topic} ?", f"L'application directe aux résolutions d'exercices et aux calculs du cours sur {clean_topic}."),
        ("Hypothèse requise", f"Sous quelles conditions ou hypothèses de validité utilise-t-on les résultats de : {clean_topic} ?", f"Le domaine de validité et les hypothèses préalables définies dans le cours pour {clean_topic}."),
        ("Synthèse de cours", f"Quels sont les acquis indispensables du cours sur : {clean_topic} ?", f"L'ensemble des définitions, formules et propriétés indispensables présentées sur {clean_topic}."),
    ]
    idx = 0
    while len(extracted_units) < count:
        asp = course_aspects[idx % len(course_aspects)]
        _add_unit(asp[0], asp[1] + (f" (Point {idx+1})" if idx >= len(course_aspects) else ""), asp[2], concept=clean_topic)
        idx += 1

    # --- 1. Flashcards ---
    cards: list[dict[str, Any]] = []
    for i, u in enumerate(extracted_units[:count]):
        cards.append({
            "id": i + 1,
            "category": u["category"],
            "recto": u["recto"],
            "verso": u["verso"],
        })

    # --- 2. Questions Quizz QCM ---
    questions: list[dict[str, Any]] = []
    for i, u in enumerate(extracted_units[:count]):
        concept_title = u["concept"]
        verso_clean = u["verso"]
        question_text = f"Concernant « {concept_title} », quelle affirmation issue du cours est exacte ?"
        correct_option = verso_clean[:140]

        distractors: list[str] = []
        for other_u in extracted_units:
            other_v = other_u["verso"][:140]
            if other_u != u and other_v != correct_option and other_v not in distractors:
                distractors.append(other_v)
                if len(distractors) == 3:
                    break

        fallback_distractors = [
            f"Cette propriété n'est pas applicable dans le cadre de {clean_topic}.",
            "C'est une affirmation contradictoire avec les définitions établies dans le cours.",
            "Cette relation ne concerne que des cas particuliers non traités dans le cours.",
            "Cette notion s'annule lorsque les grandeurs considérées sont non nulles.",
        ]
        fb_idx = 0
        while len(distractors) < 3:
            distractors.append(fallback_distractors[fb_idx % len(fallback_distractors)])
            fb_idx += 1

        options = [correct_option, distractors[0], distractors[1], distractors[2]]
        questions.append({
            "id": i + 1,
            "question": question_text,
            "options": options,
            "answer": 0,
            "explanation": f"Le cours indique précisément : {verso_clean[:220]}.",
        })

    # --- 3. Phrases à trous (Cloze test) ---
    cloze_items: list[dict[str, Any]] = []
    for i, u in enumerate(extracted_units[:count]):
        sentence = u["verso"]
        target_concept = u["concept"]

        # Identifier le mot clé à masquer
        missing_word = target_concept if (target_concept and target_concept in sentence) else ""
        if not missing_word:
            words = re.findall(r"[a-zA-ZÀ-ÿ\d_\\${}]+", sentence)
            candidates = [
                w for w in words
                if len(w) >= 4 and w.lower() not in (
                    "cette", "notre", "votre", "leurs", "comme", "faire", "avoir", "selon",
                    "entre", "aussi", "alors", "apres", "avant", "cours", "point", "droite", "dans"
                )
            ]
            missing_word = candidates[0] if candidates else (words[0] if words else "notion")

        text_with_blanks = sentence.replace(missing_word, "[...]", 1) if missing_word in sentence else f"{sentence} ([...])"

        options = [missing_word]
        for other_u in extracted_units:
            other_c = other_u["concept"]
            if other_c and other_c != missing_word and other_c not in options and len(other_c) <= 30:
                options.append(other_c)
                if len(options) == 4:
                    break

        defaults = ["direction", "norme", "colinéaires", "Chasles", "coordonnées", "abscisse", "ordonnée", "vecteur"]
        for d in defaults:
            if len(options) < 4 and d not in options and d.lower() != missing_word.lower():
                options.append(d)

        cloze_items.append({
            "id": i + 1,
            "sentence": sentence,
            "text_with_blanks": text_with_blanks,
            "missing_words": [missing_word],
            "hints": [f"Terme clé lié à la notion : {u['category']}"],
            "options": options[:4],
            "explanation": f"Dans le cours : {sentence[:200]}.",
        })

    if kind == "flashcards":
        return {
            "kind": "flashcards",
            "count": count,
            "difficulty": difficulty,
            "topic": clean_topic,
            "flashcards": cards[:count],
            "questions": [],
            "cloze_items": [],
        }
    elif kind == "quiz":
        return {
            "kind": "quiz",
            "count": count,
            "difficulty": difficulty,
            "topic": clean_topic,
            "flashcards": [],
            "questions": questions[:count],
            "cloze_items": [],
        }
    elif kind == "cloze":
        return {
            "kind": "cloze",
            "count": count,
            "difficulty": difficulty,
            "topic": clean_topic,
            "flashcards": [],
            "questions": [],
            "cloze_items": cloze_items[:count],
        }
    else:  # kind == "all"
        return {
            "kind": "all",
            "count": count,
            "difficulty": difficulty,
            "topic": clean_topic,
            "flashcards": cards[:count],
            "questions": questions[:count],
            "cloze_items": cloze_items[:count],
        }


async def generate_study_material(
    settings: Any,
    transcript: str = "",
    kind: str = "flashcards",
    count: int = 10,
    difficulty: str = "medium",
    topic: str = "",
    model: str = "",
    course_text: str = "",
) -> dict[str, Any]:
    """Génère des flashcards, des questions de quizz ou des phrases à trous sur mesure."""
    count = max(1, min(count, 30))
    clean_topic = topic.strip()
    if not clean_topic or clean_topic in ("cette discussion", "le sujet abordé", "le cours à réviser"):
        if course_text.strip():
            first_line = course_text.strip().splitlines()[0].strip("# ").strip()
            clean_topic = first_line[:120] if first_line else "le cours à réviser"
        else:
            clean_topic = "cette discussion"

    chosen_model = model or getattr(settings, "default_model", "mistralai/mistral-small-3.2-24b-instruct")
    if getattr(settings, "demo_mode", False) or not has_llm_access(settings, chosen_model):
        return fallback_study_material(transcript, kind, count, difficulty, clean_topic, course_text=course_text)

    diff_desc = {
        "easy": "Niveau FACILE / DÉBUTANT : notions fondamentales, définitions directes, vocabulaire accessible, concepts clés immédiats sans piège.",
        "medium": "Niveau MOYEN / INTERMÉDIAIRE : compréhension des mécanismes, cas pratiques d'application, distinctions entre concepts proches, pièges classiques.",
        "hard": "Niveau DIFFICILE / EXPERT : cas limites, pièges subtils, analyse critique approfondie, diagnostic d'erreurs fréquentes, synthèse méthodologique exigeante.",
    }.get(difficulty, "Niveau MOYEN / INTERMÉDIAIRE")

    if kind == "flashcards":
        prompt_instruction = (
            f"Tu es un formateur pédagogique d'excellence. À partir du contenu fourni, génère exactement {count} flashcards de révision active (recto/verso) sur le cours « {clean_topic} ».\n"
            f"Difficulté demandée : {diff_desc}\n\n"
            "RÈGLES PÉDAGOGIQUES STRICTES ET OBLIGATOIRES :\n"
            "1. INTERDICTION FORMELLE DE TOUTE QUESTION DE MÉTHODOLOGIE OU MÉTA :\n"
            "   - Ne JAMAIS poser de questions du type : 'Quelle est la démarche pour aborder...', 'Quel est le piège ou l'erreur courante à éviter avec [sujet] ?', 'Quel est l'objectif premier quand on étudie...', 'Comment s'organiser pour réviser...'.\n"
            "   - AUCUNE question sur l'organisation du travail, la méthodologie générale ou l'attitude de l'élève.\n"
            "2. 100% DES QUESTIONS DOIVENT PORTER DIRECTEMENT ET CONCRÈTEMENT SUR LE CONTENU DU COURS FOURNI :\n"
            "   - Interroge l'élève sur les DÉFINITIONS exactes, FORMULES mathématiques/scientifiques, THÉORÈMES, PROPRIÉTÉS, RÈGLES DE CALCUL, ÉGALITÉS et APPLICATIONS du cours.\n"
            "   - Chaque question ('recto') doit tester une notion précise du cours (ex: 'Quelle est la formule des coordonnées du vecteur $\\vec{AB}$ à partir de $A(x_A; y_A)$ et $B(x_B; y_B)$ ?', 'Énoncer la relation de Chasles.', 'À quelle condition deux vecteurs sont-ils colinéaires ?').\n"
            "   - Verso : La réponse directe, rigoureuse, didactique et complète avec les formules associées.\n"
            "3. NOTATION MATHÉMATIQUE LATEX / KATEX OBLIGATOIRE :\n"
            "   - Pour toutes les mathématiques et sciences, écris TOUTES les formules, variables, coordonnées et symboles en LaTeX entre dollars simples : $...$ (ex: $\\vec{u}$, $\\vec{AB}$, $(x_B - x_A)$, $k \\in \\mathbb{R}$, $\\sqrt{x}$).\n"
            "4. CATÉGORIES DISCIPLINAIRES LIÉES AU COURS :\n"
            "   - Utilise UNIQUEMENT des catégories disciplinaires : 'Définition', 'Formule', 'Théorème', 'Propriété', 'Calcul', 'Règle', 'Application'.\n"
            "   - Ne JAMAIS utiliser 'Méthodologie', 'Méthode générale' ou 'Piège fréquent'.\n"
            f"5. NOMBRE D'ÉLÉMENTS STRICT : Tu DOIS obligatoirement générer TRÈS EXACTEMENT {count} flashcards complètes.\n\n"
            "Retourne EXCLUSIVEMENT un objet JSON valide avec cette structure stricte :\n"
            "{\n"
            f'  "topic": "{clean_topic}",\n'
            '  "flashcards": [\n'
            '    {\n'
            '      "id": 1,\n'
            '      "category": "Définition",\n'
            '      "recto": "...",\n'
            '      "verso": "..."\n'
            '    }\n'
            '  ]\n'
            "}"
        )
    elif kind == "quiz":
        prompt_instruction = (
            f"Tu es un formateur pédagogique d'excellence. À partir du contenu fourni, conçois un quizz interactif d'exactement {count} questions à choix multiples (QCM) sur le cours « {clean_topic} ».\n"
            f"Difficulté demandée : {diff_desc}\n\n"
            "RÈGLES PÉDAGOGIQUES STRICTES ET OBLIGATOIRES :\n"
            "1. INTERDICTION ABSOLUE de poser des questions de méthodologie générale, d'organisation ou méta ('Quel est le piège avec...', 'Quelle démarche adopter...').\n"
            "2. 100% des questions doivent être des questions de connaissances CONCRÈTES ou d'applications directes du cours : formules, calculs, définitions exactes, théorèmes, identification de propriétés.\n"
            "3. Pour chaque question :\n"
            f"   - 'id' : entier de 1 à {count}\n"
            "   - 'question' : énoncé clair et précis portant sur une notion du cours\n"
            "   - 'options' : tableau d'exactement 4 options techniques distinctes et plausibles\n"
            "   - 'answer' : entier (0, 1, 2 ou 3) désignant l'unique bonne réponse\n"
            "   - 'explanation' : explication didactique et factuelle basée sur le cours\n"
            "4. Notations mathématiques OBLIGATOIREMENT entre dollars simples $...$ (KaTeX).\n"
            f"5. Génère IMPÉRATIVEMENT et TRÈS EXACTEMENT {count} questions.\n\n"
            "Retourne EXCLUSIVEMENT un objet JSON valide avec cette structure stricte :\n"
            "{\n"
            f'  "topic": "{clean_topic}",\n'
            '  "questions": [\n'
            '    {\n'
            '      "id": 1,\n'
            '      "question": "...",\n'
            '      "options": ["...", "...", "...", "..."],\n'
            '      "answer": 0,\n'
            '      "explanation": "..."\n'
            '    }\n'
            '  ]\n'
            "}"
        )
    elif kind == "cloze":
        prompt_instruction = (
            f"Tu es un formateur pédagogique d'excellence. À partir du contenu fourni, conçois un atelier interactif d'exactement {count} phrases ou textes à trous (cloze test) sur le cours « {clean_topic} ».\n"
            f"Difficulté demandée : {diff_desc}\n\n"
            "RÈGLES PÉDAGOGIQUES STRICTES ET OBLIGATOIRES :\n"
            "1. INTERDICTION ABSOLUE de phrases de méthodologie générale ou méta ('L'objectif prioritaire est de...', 'Il faut vérifier chaque étape...').\n"
            "2. 100% des phrases doivent être des énoncés de cours CONCRETS : définitions, formules, théorèmes, règles ou propriétés extraites ou fidèles au cours fourni.\n"
            "3. Le terme masqué par '[...]' doit être un mot technique décisif, une formule, un nom de théorème ou un concept clé du cours.\n"
            "4. Pour chaque élément :\n"
            f"   - 'id' : entier de 1 à {count}\n"
            "   - 'sentence' : la phrase complète et exacte du cours\n"
            "   - 'text_with_blanks' : la même phrase où le mot clé décisif est remplacé par '[...]'\n"
            "   - 'missing_words' : tableau contenant le mot ou les mots exacts masqués (ex: ['colinéaires'])\n"
            "   - 'hints' : tableau avec un indice précis sur la notion du cours\n"
            "   - 'options' : tableau d'au moins 4 termes du même domaine disciplinaire (dont le mot correct)\n"
            "   - 'explanation' : explication didactique rappelant le point précis du cours\n"
            "5. Notations mathématiques OBLIGATOIREMENT entre dollars simples $...$ (KaTeX).\n"
            f"6. Génère IMPÉRATIVEMENT et TRÈS EXACTEMENT {count} éléments complets.\n\n"
            "Retourne EXCLUSIVEMENT un objet JSON valide avec cette structure stricte :\n"
            "{\n"
            f'  "topic": "{clean_topic}",\n'
            '  "cloze_items": [\n'
            '    {\n'
            '      "id": 1,\n'
            '      "sentence": "...",\n'
            '      "text_with_blanks": "...",\n'
            '      "missing_words": ["..."],\n'
            '      "hints": ["..."],\n'
            '      "options": ["...", "...", "...", "..."],\n'
            '      "explanation": "..."\n'
            '    }\n'
            '  ]\n'
            "}"
        )
    else:  # kind == "all"
        prompt_instruction = (
            f"Tu es un formateur pédagogique d'excellence. À partir du contenu fourni, conçois un pack complet de révision sur le cours « {clean_topic} » contenant :\n"
            f"- Exactement {count} flashcards de révision active (recto/verso)\n"
            f"- Exactement {count} questions de quizz QCM (4 options avec indice 'answer' 0-3 et 'explanation')\n"
            f"- Exactement {count} phrases à trous 'cloze_items' ('sentence', 'text_with_blanks' avec '[...]', 'missing_words', 'hints', 'options', 'explanation')\n"
            f"Difficulté demandée : {diff_desc}\n\n"
            "RÈGLES PÉDAGOGIQUES STRICTES ET OBLIGATOIRES :\n"
            "1. INTERDICTION FORMELLE DE TOUTE QUESTION MÉTA OU DE MÉTHODOLOGIE GÉNÉRALE.\n"
            "2. 100% des cartes, questions et phrases à trous doivent porter EXCLUSIVEMENT sur les définitions, formules, théorèmes, règles et exercices du cours.\n"
            "3. Notations mathématiques en LaTeX avec dollars simples $...$.\n"
            f"4. Génère très exactement {count} éléments pour chacune des trois activités.\n\n"
            "Retourne EXCLUSIVEMENT un objet JSON valide avec cette structure stricte :\n"
            "{\n"
            f'  "topic": "{clean_topic}",\n'
            '  "flashcards": [...],\n'
            '  "questions": [...],\n'
            '  "cloze_items": [...]\n'
            "}"
        )

    if course_text and course_text.strip():
        source_label = "Voici le texte intégral du cours / document à réviser :"
        context_text = course_text.strip()[:14000]
    else:
        source_label = "Voici les échanges de la discussion :"
        context_text = transcript[:8000] if transcript else f"Sujet : {clean_topic}"

    messages = [
        {"role": "system", "content": prompt_instruction},
        {"role": "user", "content": f"{source_label}\n\n{context_text}"},
    ]

    tokens_needed = min(max(count * (550 if kind == "all" else 260), 1600), 6000)
    try:
        async with httpx.AsyncClient(timeout=_STUDY_TIMEOUT, follow_redirects=False) as client:
            response = await post_chat_completion(
                settings,
                {
                    "model": chosen_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.1,
                    "max_tokens": tokens_needed,
                },
                client=client,
            )
            if response.status_code in (400, 404, 422):
                alt_model = getattr(settings, "default_model", "")
                if alt_model and can_fallback_to_model(settings, chosen_model, alt_model):
                    response = await post_chat_completion(
                        settings,
                        {
                            "model": alt_model,
                            "messages": messages,
                            "stream": False,
                            "temperature": 0.1,
                            "max_tokens": tokens_needed,
                        },
                        client=client,
                    )
        _check_response(response, "Fournisseur IA")
        payload = _json(response, "Fournisseur IA")
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Réponse IA non textuelle")

        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        candidate = match.group(0) if match else cleaned
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            # Réparation des antislashs LaTeX non échappés par le LLM (ex: \vec, \frac, \begin, \alpha)
            repaired = re.sub(r"(?<!\\)\\(?![\\\"/])", r"\\\\", candidate)
            data = json.loads(repaired)

        def _parse_flashcards(raw_list: Any) -> list[dict[str, Any]]:
            res = []
            if isinstance(raw_list, list):
                for c in raw_list:
                    if isinstance(c, dict) and c.get("recto") and c.get("verso"):
                        recto = str(c["recto"]).strip()
                        verso = str(c["verso"]).strip()
                        if not _is_methodology_study_item(recto) and not _is_methodology_study_item(verso):
                            res.append({
                                "id": len(res) + 1,
                                "category": str(c.get("category") or "Point Clé")[:40],
                                "recto": recto,
                                "verso": verso,
                            })
            return res

        def _parse_questions(raw_list: Any) -> list[dict[str, Any]]:
            res = []
            if isinstance(raw_list, list):
                for q in raw_list:
                    if isinstance(q, dict) and q.get("question") and isinstance(q.get("options"), list) and len(q["options"]) >= 2:
                        question = str(q["question"]).strip()
                        if not _is_methodology_study_item(question):
                            opts = [str(o).strip() for o in q["options"][:4]]
                            while len(opts) < 4:
                                opts.append(f"Option {len(opts) + 1}")
                            ans = q.get("answer", 0)
                            if not isinstance(ans, int) or ans < 0 or ans >= len(opts):
                                ans = 0
                            res.append({
                                "id": len(res) + 1,
                                "question": question,
                                "options": opts,
                                "answer": ans,
                                "explanation": str(q.get("explanation") or "Réponse exacte selon le cours.").strip(),
                            })
            return res

        def _parse_cloze(raw_list: Any) -> list[dict[str, Any]]:
            res = []
            if isinstance(raw_list, list):
                for item in raw_list:
                    if isinstance(item, dict) and (item.get("sentence") or item.get("text_with_blanks")):
                        sent = str(item.get("sentence") or "").strip()
                        twb = str(item.get("text_with_blanks") or "").strip()
                        if not _is_methodology_study_item(sent) and not _is_methodology_study_item(twb):
                            raw_missing = item.get("missing_words")
                            missing = [str(w).strip() for w in raw_missing if str(w).strip()] if isinstance(raw_missing, list) else []
                            raw_hints = item.get("hints")
                            hints = [str(h).strip() for h in raw_hints if str(h).strip()] if isinstance(raw_hints, list) else []
                            raw_opts = item.get("options")
                            opts = [str(o).strip() for o in raw_opts if str(o).strip()] if isinstance(raw_opts, list) else []

                            if not twb and sent and missing:
                                twb = sent
                                for w in missing:
                                    twb = re.sub(re.escape(w), "[...]", twb, count=1, flags=re.IGNORECASE)
                            elif not sent and twb and missing:
                                sent = twb
                                for w in missing:
                                    sent = sent.replace("[...]", w, 1)

                            for w in missing:
                                if w not in opts:
                                    opts.insert(0, w)

                            res.append({
                                "id": len(res) + 1,
                                "sentence": sent or twb,
                                "text_with_blanks": twb or sent,
                                "missing_words": missing or [opts[0] if opts else "notion"],
                                "hints": hints or ["Rappelez-vous le point précis du cours."],
                                "options": opts if len(opts) >= 2 else ["Terme A", "Terme B", "Terme C", "Terme D"],
                                "explanation": str(item.get("explanation") or "Élément clé du cours.").strip(),
                            })
            return res

        fb = fallback_study_material(transcript, kind, count, difficulty, clean_topic, course_text=course_text)

        if kind == "flashcards":
            valid_cards = _parse_flashcards(data.get("flashcards"))
            if len(valid_cards) < count:
                extra = fb["flashcards"][len(valid_cards):count]
                for extra_card in extra:
                    extra_card["id"] = len(valid_cards) + 1
                    valid_cards.append(extra_card)
            return {
                "kind": "flashcards",
                "count": len(valid_cards[:count]),
                "difficulty": difficulty,
                "topic": str(data.get("topic") or clean_topic),
                "flashcards": valid_cards[:count],
                "questions": [],
                "cloze_items": [],
            }
        elif kind == "quiz":
            valid_questions = _parse_questions(data.get("questions"))
            if len(valid_questions) < count:
                extra = fb["questions"][len(valid_questions):count]
                for extra_q in extra:
                    extra_q["id"] = len(valid_questions) + 1
                    valid_questions.append(extra_q)
            return {
                "kind": "quiz",
                "count": len(valid_questions[:count]),
                "difficulty": difficulty,
                "topic": str(data.get("topic") or clean_topic),
                "flashcards": [],
                "questions": valid_questions[:count],
                "cloze_items": [],
            }
        elif kind == "cloze":
            valid_cloze = _parse_cloze(data.get("cloze_items"))
            if len(valid_cloze) < count:
                extra = fb["cloze_items"][len(valid_cloze):count]
                for extra_c in extra:
                    extra_c["id"] = len(valid_cloze) + 1
                    valid_cloze.append(extra_c)
            return {
                "kind": "cloze",
                "count": len(valid_cloze[:count]),
                "difficulty": difficulty,
                "topic": str(data.get("topic") or clean_topic),
                "flashcards": [],
                "questions": [],
                "cloze_items": valid_cloze[:count],
            }
        else:  # kind == "all"
            valid_cards = _parse_flashcards(data.get("flashcards"))
            if len(valid_cards) < count:
                extra_c = fb["flashcards"][len(valid_cards):count]
                for c in extra_c:
                    c["id"] = len(valid_cards) + 1
                    valid_cards.append(c)

            valid_questions = _parse_questions(data.get("questions"))
            if len(valid_questions) < count:
                extra_q = fb["questions"][len(valid_questions):count]
                for q in extra_q:
                    q["id"] = len(valid_questions) + 1
                    valid_questions.append(q)

            valid_cloze = _parse_cloze(data.get("cloze_items"))
            if len(valid_cloze) < count:
                extra_cl = fb["cloze_items"][len(valid_cloze):count]
                for cl in extra_cl:
                    cl["id"] = len(valid_cloze) + 1
                    valid_cloze.append(cl)

            return {
                "kind": "all",
                "count": count,
                "difficulty": difficulty,
                "topic": str(data.get("topic") or clean_topic),
                "flashcards": valid_cards[:count],
                "questions": valid_questions[:count],
                "cloze_items": valid_cloze[:count],
            }

    except (httpx.HTTPError, ProviderError, ValueError, TypeError, KeyError, IndexError) as exc:
        _logger.warning("Échec de la génération IA de révision (%s): %s — repli sur l'extraction locale", chosen_model, exc)
        return fallback_study_material(transcript, kind, count, difficulty, clean_topic, course_text=course_text)
