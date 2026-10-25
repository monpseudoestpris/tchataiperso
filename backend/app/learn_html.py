"""
learn_html — Générateur de page HTML autonome et stylisée pour les cours du Mode Apprendre.

Produit un document HTML complet, élégant, responsive, typographiquement soigné
(façon grand manuel universitaire / cours magistral interactif d'excellence),
avec navigation, sommaire dynamique, citations interactives, 20 flashcards 3D interactives,
un quizz de 20 questions avec feedback instantané, encarts didactiques et styles d'impression.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit


def slugify(text: str) -> str:
    """Produit un slug ASCII propre pour les ancres HTML."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[\s_]+", "-", cleaned)


def estimate_reading_time_minutes(text: str) -> int:
    """Estime le temps d'apprentissage en minutes (environ 180 mots/min pour un cours)."""
    words = len(re.findall(r"\w+", text))
    return max(1, round(words / 180))


def extract_domain(url: str) -> str:
    """Extrait le nom d'hôte propre d'une URL."""
    try:
        host = urlsplit(url).netloc
        return host.replace("www.", "") if host else url
    except Exception:
        return url


def parse_flashcards(md_text: str, topic: str) -> list[dict[str, Any]]:
    """
    Extrait ou synthétise exactement 20 flashcards de révision active à partir du markdown du cours.
    """
    cards: list[dict[str, Any]] = []

    # 1. Détection des blocs explicites de Flashcards (### Flashcard X ...)
    pattern1 = re.compile(
        r"(?:###|\*\*)\s*Flashcard\s*(\d+)[:\s\-*]*\n*(?:[-*]\s*)?\*\*Recto\s*:\*\*\s*(.+?)\n+(?:[-*]\s*)?\*\*Verso\s*:\*\*\s*(.+?)(?=\n*(?:###|\*\*)\s*Flashcard|\n*#{1,3}\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern1.finditer(md_text):
        recto = " ".join(m.group(2).strip().split())
        verso = " ".join(m.group(3).strip().split())
        if recto and verso:
            cards.append({
                "id": len(cards) + 1,
                "category": "Révision active",
                "recto": recto,
                "verso": verso,
            })

    # Détection simplifiée Recto : ... Verso : ...
    if len(cards) < 20:
        pattern2 = re.compile(
            r"[-*]?\s*\*\*Recto\s*:\*\*\s*(.+?)\n+[-*]?\s*\*\*Verso\s*:\*\*\s*(.+?)(?=\n+[-*]?\s*\*\*Recto|\n*#{1,3}\s|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        existing_rectos = {c["recto"].casefold() for c in cards}
        for m in pattern2.finditer(md_text):
            recto = " ".join(m.group(1).strip().split())
            verso = " ".join(m.group(2).strip().split())
            if recto and verso and recto.casefold() not in existing_rectos:
                existing_rectos.add(recto.casefold())
                cards.append({
                    "id": len(cards) + 1,
                    "category": "Concept clé",
                    "recto": recto,
                    "verso": verso,
                })
                if len(cards) >= 20:
                    break

    # 2. Extraction des définitions (- **Terme :** Définition)
    if len(cards) < 20:
        existing_rectos = {c["recto"].casefold() for c in cards}
        def_pattern = re.compile(r"[-*]\s+\*\*([^*\n]+?)(?:\s*:)?\*\*\s*:?\s*(.+)")
        for m in def_pattern.finditer(md_text):
            term = m.group(1).strip()
            definition = " ".join(m.group(2).strip().split())
            if any(term.lower().startswith(p) for p in ["recto", "verso", "énoncé", "bonne réponse", "explication"]):
                continue
            recto = f"Qu'est-ce que « {term} » et quel est son rôle ?"
            if recto.casefold() not in existing_rectos and len(definition) > 15:
                existing_rectos.add(recto.casefold())
                cards.append({
                    "id": len(cards) + 1,
                    "category": "Définition & Rôle",
                    "recto": recto,
                    "verso": definition,
                })
                if len(cards) >= 20:
                    break

    # 3. Extraction des pièges classiques
    if len(cards) < 20:
        existing_rectos = {c["recto"].casefold() for c in cards}
        pitfall_pattern = re.compile(r"(?:Piège|Erreur|Anti-pattern)\s*(?:n°\s*\d+|\d+)?\s*:\s*([^\n*]+)(.*?)(?=(?:Piège|Erreur|Anti-pattern)|#{1,3}\s|\Z)", re.IGNORECASE | re.DOTALL)
        for m in pitfall_pattern.finditer(md_text):
            name = m.group(1).strip().strip("*# ")
            desc = " ".join(m.group(2).strip().split())[:300]
            recto = f"Quel est le piège lié à : « {name} » et comment l'éviter ?"
            if recto.casefold() not in existing_rectos and len(desc) > 20:
                existing_rectos.add(recto.casefold())
                cards.append({
                    "id": len(cards) + 1,
                    "category": "Piège & Méthode",
                    "recto": recto,
                    "verso": desc,
                })
                if len(cards) >= 20:
                    break

    # 4. Extraction des sous-parties de cours (### Titre)
    if len(cards) < 20:
        existing_rectos = {c["recto"].casefold() for c in cards}
        h_pattern = re.compile(r"###?\s+([^\n#]+)\n+([^\n#]+)", re.MULTILINE)
        for m in h_pattern.finditer(md_text):
            title = m.group(1).strip()
            first_p = " ".join(m.group(2).strip().split())
            if any(w in title.lower() for w in ["flashcard", "quizz", "quiz", "sommaire", "table des"]):
                continue
            recto = f"Expliquez le principe fondamental de : « {title} »"
            if recto.casefold() not in existing_rectos and len(first_p) > 25:
                existing_rectos.add(recto.casefold())
                cards.append({
                    "id": len(cards) + 1,
                    "category": "Mécanisme",
                    "recto": recto,
                    "verso": first_p,
                })
                if len(cards) >= 20:
                    break

    # 5. Gabarits pédagogiques de secours pour garantir scrupuleusement 20 cartes
    clean_topic = topic.strip() or "le sujet étudié"
    fallback_templates = [
        ("Fondations", f"Quelle est la finalité première de : {clean_topic} ?", f"Résoudre les limitations des méthodes naïves en structurant une démarche rigoureuse, reproductible et optimisée."),
        ("Méthodologie", f"Quelle est la première étape indispensable lors de l'étude de : {clean_topic} ?", "Analyser attentivement le cadre, identifier les prérequis et délimiter précisément le périmètre."),
        ("Règle d'or", f"Quelle est la règle cardinale pour maîtriser : {clean_topic} ?", "Ne jamais se fier aux impressions subjectives : toujours appuyer ses affirmations sur des éléments tangibles et vérifiables."),
        ("Architecture", f"Quels sont les piliers fondamentaux qui composent : {clean_topic} ?", "Une solide compréhension théorique, une méthodologie de décomposition systématique et une mise en pratique rigoureuse."),
        ("Auto-contrôle", f"Comment vérifier l'exactitude de sa démarche sur : {clean_topic} ?", "Utiliser une grille critériée d'auto-évaluation et confronter ses résultats aux cas limites et contre-exemples."),
        ("Approfondissement", f"Quelle est la compétence avancée à développer sur : {clean_topic} ?", "Savoir anticiper les cas atypiques, maîtriser les subtilités avancées et adapter la stratégie aux contraintes réelles."),
        ("Anti-pattern", f"Quelle est l'erreur la plus courante commise par les débutants sur : {clean_topic} ?", "La précipitation et l'omission des étapes d'analyse préliminaire au profit d'une exécution directe non cadrée."),
        ("Synthèse", f"Quel est le lien entre théorie et pratique dans : {clean_topic} ?", "La théorie éclaire la structure des décisions, tandis que la pratique affine l'intuition et éprouve la solidité des modèles."),
        ("Vocabulaire", f"Pourquoi employer un vocabulaire technique précis dans : {clean_topic} ?", "Nommer rigoureusement les concepts permet de penser clairement et d'éliminer toute ambiguïté intellectuelle."),
        ("Excellence", f"Qu'est-ce qui distingue un praticien expert d'un novice dans : {clean_topic} ?", "La capacité à diagnostiquer rapidement les dysfonctionnements et à justifier chaque choix avec méthode."),
    ]
    fb_idx = 0
    while len(cards) < 20:
        cat, r, v = fallback_templates[fb_idx % len(fallback_templates)]
        cards.append({
            "id": len(cards) + 1,
            "category": cat,
            "recto": f"{r} (Point clé #{len(cards)+1})",
            "verso": v,
        })
        fb_idx += 1

    return cards[:20]


def parse_quiz(md_text: str, topic: str) -> list[dict[str, Any]]:
    """
    Extrait ou synthétise exactement 20 questions de quizz (QCM 4 options) avec explications.
    """
    questions: list[dict[str, Any]] = []

    # 1. Détection des blocs de questions formalisés
    q_pattern = re.compile(
        r"(?:###|\*\*)\s*Question\s*(\d+)[:\s\-*]*\n*(?:[-*]\s*)?(.*?)\n+"
        r"(?:[-*]\s*)?A\)\s*(.*?)\n+"
        r"(?:[-*]\s*)?B\)\s*(.*?)\n+"
        r"(?:[-*]\s*)?C\)\s*(.*?)\n+"
        r"(?:[-*]\s*)?D\)\s*(.*?)\n+"
        r"(?:[-*]\s*)?(?:\*\*Bonne réponse\s*:\*\*\s*|Bonne réponse\s*:\s*)([A-D])\b.*?\n+"
        r"(?:[-*]\s*)?(?:\*\*Explication\s*:\*\*\s*|Explication\s*:\s*)(.*?)(?=\n*(?:###|\*\*)\s*Question|\n*#{1,3}\s|\Z)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in q_pattern.finditer(md_text):
        q_raw = " ".join(m.group(2).strip().split())
        q_text = re.sub(r"^\*?\*?Énoncé\s*:\*?\*?\s*", "", q_raw, flags=re.IGNORECASE).strip()
        opt_a = " ".join(m.group(3).strip().split())
        opt_b = " ".join(m.group(4).strip().split())
        opt_c = " ".join(m.group(5).strip().split())
        opt_d = " ".join(m.group(6).strip().split())
        ans_letter = m.group(7).strip().upper()
        explanation = " ".join(m.group(8).strip().split())

        ans_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(ans_letter, 0)
        if q_text and opt_a and opt_b:
            questions.append({
                "id": len(questions) + 1,
                "question": q_text,
                "options": [opt_a, opt_b, opt_c, opt_d],
                "answer": ans_idx,
                "explanation": explanation or f"La bonne réponse est l'option {ans_letter}.",
            })

    # 2. Détection de QCM sans formatage strict
    if len(questions) < 20:
        simple_q_pattern = re.compile(
            r"(?:^|\n)(?:\d+[\.\)]|\*\*Question\s*\d+\*\*)\s*(.+?\?)\n+"
            r"(?:[-*]\s*)?[aA][\)\.]\s*(.+?)\n+"
            r"(?:[-*]\s*)?[bB][\)\.]\s*(.+?)\n+"
            r"(?:[-*]\s*)?[cC][\)\.]\s*(.+?)\n+"
            r"(?:[-*]\s*)?[dD][\)\.]\s*(.+?)\n+"
            r"(?:.*?Réponse\s*:\s*([A-D]))?",
            re.DOTALL | re.IGNORECASE,
        )
        existing_qs = {q["question"].casefold() for q in questions}
        for m in simple_q_pattern.finditer(md_text):
            q_text = " ".join(m.group(1).strip().split())
            opt_a = " ".join(m.group(2).strip().split())
            opt_b = " ".join(m.group(3).strip().split())
            opt_c = " ".join(m.group(4).strip().split())
            opt_d = " ".join(m.group(5).strip().split())
            ans_letter = (m.group(6) or "A").strip().upper()
            ans_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(ans_letter, 0)
            if q_text and q_text.casefold() not in existing_qs:
                existing_qs.add(q_text.casefold())
                questions.append({
                    "id": len(questions) + 1,
                    "question": q_text,
                    "options": [opt_a, opt_b, opt_c, opt_d],
                    "answer": ans_idx,
                    "explanation": f"L'option {ans_letter} est la réponse exacte validée par le cours.",
                })
                if len(questions) >= 20:
                    break

    # 3. Synthèse de questions à partir des définitions du cours
    if len(questions) < 20:
        clean_topic = topic.strip() or "le sujet étudié"
        def_pattern = re.compile(r"[-*]\s+\*\*([^*\n]+?)(?:\s*:)?\*\*\s*:?\s*(.+)")
        defs = def_pattern.findall(md_text)
        existing_qs = {q["question"].casefold() for q in questions}
        for term, definition in defs:
            clean_term = term.strip()
            clean_def = " ".join(definition.strip().split())
            if any(clean_term.lower().startswith(p) for p in ["recto", "verso", "énoncé", "bonne réponse", "explication"]):
                continue
            q_text = f"Dans le cadre de {clean_topic}, comment se définit exactement « {clean_term} » ?"
            if q_text.casefold() not in existing_qs and len(clean_def) > 15:
                existing_qs.add(q_text.casefold())
                correct = clean_def[:200]
                distractor1 = f"Un procédé consistant à ignorer {clean_term} au profit d'une intuition subjective."
                distractor2 = f"Une notion secondaire réservée uniquement aux débutants, sans impact sur le résultat final."
                distractor3 = f"Un outil purement théorique déconseillé par les spécialistes en raison de sa complexité."
                questions.append({
                    "id": len(questions) + 1,
                    "question": q_text,
                    "options": [correct, distractor1, distractor2, distractor3],
                    "answer": 0,
                    "explanation": f"« {clean_term} » désigne précisément : {correct}",
                })
                if len(questions) >= 20:
                    break

    # 4. Gabarits de contrôle méthodologique de secours pour garantir 20 questions
    clean_topic = topic.strip() or "ce domaine"
    fallback_quiz = [
        (f"Quel est le principe d'apprentissage fondamental mis en avant dans ce cours sur {clean_topic} ?",
         ["Lier systématiquement la théorie, le mécanisme interne et la pratique concrète",
          "Mémoriser uniquement par cœur sans chercher à comprendre le pourquoi",
          "Éviter toute confrontation avec des cas réels complexes",
          "Se limiter à une lecture rapide sans exercices d'application"],
         0,
         "L'ancrage durable du savoir repose sur la compréhension du mécanisme et la validation pratique immédiate."),
        (f"Lorsqu'on aborde une notion complexe dans {clean_topic}, que conseille la méthode d'excellence ?",
         ["L'apprentissage linéaire passif sans prise de notes",
          "La décomposition en sous-problèmes plus simples et l'analyse des composants",
          "Ignorer les prérequis pour passer directement au niveau expert",
          "Attendre l'évaluation finale avant de s'exercer"],
         1,
         "La décomposition méthodique (diviser pour régner) permet de dompter la complexité sans saturation cognitive."),
        (f"Quelle est la principale source d'erreur identifiée dans la pratique de {clean_topic} ?",
         ["L'excès de rigueur méthodologique",
          "La confusion entre description superficielle et analyse causale approfondie",
          "L'utilisation d'exemples concrets",
          "La consultation de documentations de référence"],
         1,
         "Le survol descriptif ne permet pas de démontrer les mécanismes sous-jacents, source de contre-sens fréquents."),
        (f"Quelle attitude est recommandée face à une contradiction apparente dans {clean_topic} ?",
         ["Choisir arbitrairement la première source consultée",
          "Remonter aux sources primaires et examiner les conditions d'application respectives",
          "Supprimer les deux éléments pour éviter les questions gênantes",
          "Considérer que les deux affirmations sont nécessairement fausses"],
         1,
         "L'esprit critique universitaire exige d'identifier le contexte et le périmètre de validité de chaque affirmation."),
        (f"Comment mesurer concrètement sa progression dans la maîtrise de {clean_topic} ?",
         ["En étant capable d'expliquer la notion simplement et de résoudre des cas réels en autonomie",
          "En ayant lu le cours une seule fois en diagonale",
          "En évitant de se tester pour ne pas douter",
          "En mémorisant uniquement les acronymes sans leur sens"],
         0,
         "La technique de Feynman (expliquer simplement) et la résolution de cas réels constituent les meilleurs tests de maîtrise."),
        (f"Quel est le rôle des pièges et anti-patterns présentés dans ce cours ?",
         ["Décourager l'apprenant face aux difficultés",
          "Développer des réflexes de diagnostic pour anticiper et corriger les erreurs courantes",
          "Remplacer les règles fondamentales par des exceptions",
          "Compliquer inutilement l'apprentissage"],
         1,
         "L'étude des anti-patterns permet d'acquérir les réflexes d'un praticien chevronné."),
        (f"Quelle est la fonction d'une grille critériée d'auto-évaluation ?",
         ["Fournir une checklist objective pour vérifier chaque point d'exigence avant de valider son travail",
          "Noter arbitrairement les étudiants",
          "Remplacer l'entraînement pratique",
          "Limiter la créativité"],
         0,
         "La grille d'auto-évaluation permet de s'auto-corriger avec la même rigueur qu'un correcteur officiel."),
        (f"Pourquoi est-il crucial de maîtriser le vocabulaire technique précis de {clean_topic} ?",
         ["Pour intimider les non-spécialistes",
          "Parce qu'un vocabulaire précis permet une pensée claire, sans ambiguïté conceptuelle",
          "Ce n'est pas nécessaire, les termes approximatifs suffisent",
          "Uniquement pour réussir les examens théoriques"],
         1,
         "Nommer précisément les choses est la condition d'un raisonnement rigoureux et d'une communication professionnelle."),
    ]
    fb_idx = 0
    while len(questions) < 20:
        q_text, opts, ans_idx, expl = fallback_quiz[fb_idx % len(fallback_quiz)]
        questions.append({
            "id": len(questions) + 1,
            "question": f"{q_text} (Question #{len(questions)+1})",
            "options": list(opts),
            "answer": ans_idx,
            "explanation": expl,
        })
        fb_idx += 1

    return questions[:20]


def strip_raw_modules_for_body(md_text: str) -> str:
    """Isole le corps didactique (Modules 1 à 7) pour éviter les doublons textuels avec les widgets interactifs."""
    split_match = re.search(
        r"(?:^|\n)#{1,4}\s*(?:📇|🎯)?\s*(?:Module\s*8\b|(?:20\s*)?Flashcards?\b|Module\s*9\b|(?:20\s*)?Quizz?\b|Questions?\s*de\s*Quizz\b)",
        md_text,
        flags=re.IGNORECASE,
    )
    if split_match:
        return md_text[:split_match.start()].strip()
    return md_text


def markdown_to_html(md_text: str, sources: list[dict[str, Any]] | None = None) -> tuple[str, list[dict[str, str]]]:
    """
    Convertit le texte Markdown du cours en HTML riche et sécurisé,
    en extrayant la table des matières (TOC) et en liant les citations [1], [2] aux sources.
    """
    sources = sources or []
    lines = md_text.split("\n")
    toc: list[dict[str, str]] = []
    html_lines: list[str] = []

    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []

    in_list: str | None = None  # "ul" ou "ol"
    in_table = False
    table_headers: list[str] = []
    table_rows: list[list[str]] = []

    def close_list():
        nonlocal in_list
        if in_list:
            html_lines.append(f"</{in_list}>")
            in_list = None

    def close_table():
        nonlocal in_table, table_headers, table_rows
        if in_table:
            t_html = ['<div class="report-table-wrapper"><table class="report-table">']
            if table_headers:
                t_html.append("<thead><tr>")
                for th in table_headers:
                    t_html.append(f"<th>{inline_formatting(th)}</th>")
                t_html.append("</tr></thead>")
            if table_rows:
                t_html.append("<tbody>")
                for row in table_rows:
                    t_html.append("<tr>")
                    for td in row:
                        t_html.append(f"<td>{inline_formatting(td)}</td>")
                    t_html.append("</tr>")
                t_html.append("</tbody>")
            t_html.append("</table></div>")
            html_lines.append("".join(t_html))
            in_table = False
            table_headers = []
            table_rows = []

    def inline_formatting(text: str) -> str:
        escaped = html.escape(text)

        # Gras **text**
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)

        # Italique *text* ou _text_
        escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
        escaped = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<em>\1</em>", escaped)

        # Code inline `code`
        escaped = re.sub(r"`([^`]+)`", r'<code class="report-inline-code">\1</code>', escaped)

        # Liens Markdown [text](url)
        escaped = re.sub(
            r"\[([^\]]+)\]\((https?://[^\s\)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener noreferrer" class="report-external-link">\1 '
            r'<svg class="external-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>',
            escaped,
        )

        # Citations de sources [1], [2], [1, 2]
        def cite_repl(match: re.Match) -> str:
            raw_nums = match.group(1)
            parts = re.split(r"[,;\s]+", raw_nums)
            pills = []
            for p in parts:
                p = p.strip()
                if p.isdigit():
                    num = int(p)
                    if 1 <= num <= len(sources):
                        pills.append(
                            f'<a href="#source-{num}" class="report-citation-pill" '
                            f'title="Voir le support didactique #{num}">[{num}]</a>'
                        )
                    else:
                        pills.append(f'<span class="report-citation-pill">[{num}]</span>')
            return " ".join(pills) if pills else match.group(0)

        escaped = re.sub(r"\[(\d+(?:[,\s;]+\d+)*)\]", cite_repl, escaped)
        return escaped

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Blocs de code ```
        if stripped.startswith("```"):
            if in_code_block:
                code_content = html.escape("\n".join(code_lines))
                lang_label = html.escape(code_lang or "code")
                html_lines.append(
                    f'<div class="code-block-container">'
                    f'<div class="code-block-header"><span>{lang_label}</span>'
                    f'<button type="button" class="code-copy-btn" onclick="copyCode(this)">Copier</button></div>'
                    f'<pre><code class="language-{lang_label}">{code_content}</code></pre></div>'
                )
                in_code_block = False
                code_lines = []
                code_lang = ""
            else:
                close_list()
                close_table()
                in_code_block = True
                code_lang = stripped[3:].strip()
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            close_list()
            close_table()
            i += 1
            continue

        # Séparateur horizontal ---
        if re.match(r"^(\-{3,}|\*{3,}|_{3,})$", stripped):
            close_list()
            close_table()
            html_lines.append('<hr class="report-divider" />')
            i += 1
            continue

        # Tableaux Markdown
        if stripped.startswith("|") and stripped.endswith("|"):
            close_list()
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cols if c):
                i += 1
                continue

            if not in_table:
                in_table = True
                table_headers = cols
            else:
                table_rows.append(cols)
            i += 1
            continue
        else:
            close_table()

        # Titres #, ##, ###, ####
        header_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if header_match:
            close_list()
            level = len(header_match.group(1))
            h_text = header_match.group(2).strip()
            anchor = slugify(h_text)

            if level in (2, 3):
                toc.append({
                    "anchor": anchor,
                    "text": h_text,
                    "level": level,
                })

            tag = f"h{level}"
            css_class = f"report-heading-{level}"
            html_lines.append(
                f'<{tag} id="{anchor}" class="{css_class}">'
                f'<a href="#{anchor}" class="heading-anchor" aria-hidden="true">#</a>'
                f'{inline_formatting(h_text)}'
                f'</{tag}>'
            )
            i += 1
            continue

        # Citations > blockquote
        if stripped.startswith(">"):
            close_list()
            quote_text = re.sub(r"^>\s?", "", stripped)
            html_lines.append(f'<blockquote class="report-blockquote"><p>{inline_formatting(quote_text)}</p></blockquote>')
            i += 1
            continue

        # Listes à puces - ou *
        ul_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if ul_match:
            close_table()
            if in_list != "ul":
                close_list()
                html_lines.append('<ul class="report-list">')
                in_list = "ul"
            html_lines.append(f"<li>{inline_formatting(ul_match.group(1))}</li>")
            i += 1
            continue

        # Listes ordonnées 1. ou 2.
        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            close_table()
            if in_list != "ol":
                close_list()
                html_lines.append('<ol class="report-ordered-list">')
                in_list = "ol"
            html_lines.append(f"<li>{inline_formatting(ol_match.group(1))}</li>")
            i += 1
            continue

        close_list()
        html_lines.append(f'<p class="report-paragraph">{inline_formatting(stripped)}</p>')
        i += 1

    close_list()
    close_table()

    if in_code_block:
        code_content = html.escape("\n".join(code_lines))
        lang_label = html.escape(code_lang or "code")
        html_lines.append(
            f'<div class="code-block-container">'
            f'<div class="code-block-header"><span>{lang_label}</span>'
            f'<button type="button" class="code-copy-btn" onclick="copyCode(this)">Copier</button></div>'
            f'<pre><code class="language-{lang_label}">{code_content}</code></pre></div>'
        )

    return "\n".join(html_lines), toc


def build_flashcards_html(flashcards: list[dict[str, Any]]) -> str:
    """Construit le balisage HTML de la section interactive des 20 Flashcards."""
    return f"""
    <section id="flashcards-section" class="interactive-tool-section">
      <div class="tool-section-header">
        <div class="tool-badge-pill">📇 Mémorisation Active</div>
        <h2>20 Flashcards de Révision</h2>
        <p>Testez vos réflexes, retournez la carte (<kbd>Espace</kbd> ou clic) et naviguez avec les flèches (<kbd>&larr;</kbd> / <kbd>&rarr;</kbd>).</p>
      </div>

      <div class="fc-container">
        <!-- Barre d'outils et statistiques -->
        <div class="fc-toolbar">
          <div class="fc-counter-box">
            <span class="fc-label">Carte</span>
            <span class="fc-current" id="fcCurrent">1</span>
            <span class="fc-total">/ 20</span>
          </div>
          <div class="fc-stats">
            <span class="fc-stat-pill known" id="fcKnownBadge">✅ Maîtrisées : <strong id="fcKnownCount">0</strong></span>
            <span class="fc-stat-pill review" id="fcReviewBadge">🔄 À revoir : <strong id="fcReviewCount">0</strong></span>
          </div>
          <div class="fc-mode-actions">
            <button type="button" class="fc-btn-secondary" onclick="shuffleFlashcards()" title="Mélanger l'ordre des cartes">🔀 Mélanger</button>
            <button type="button" class="fc-btn-secondary" onclick="toggleFlashcardView()" id="fcViewToggleBtn">👁️ Voir les 20 cartes</button>
          </div>
        </div>

        <!-- Jauge de progression -->
        <div class="fc-progress-track">
          <div class="fc-progress-bar" id="fcProgressBar" style="width: 5%;"></div>
        </div>

        <!-- Vue Carte par Carte (3D Flip Scene) -->
        <div id="fcSingleView" class="fc-single-view">
          <div class="fc-card-scene" onclick="flipCurrentCard()">
            <div class="fc-card" id="fcActiveCard">
              <!-- Recto -->
              <div class="fc-card-face fc-card-front">
                <div class="fc-card-top">
                  <span class="fc-category-tag" id="fcFrontCategory">Concept Clé</span>
                  <span class="fc-face-tag">Recto · Question</span>
                </div>
                <div class="fc-card-body">
                  <p class="fc-prompt-text" id="fcFrontText">Chargement de la question...</p>
                </div>
                <div class="fc-card-footer">
                  <span class="fc-hint">👆 Cliquer ou appuyer sur Espace pour retourner</span>
                </div>
              </div>
              <!-- Verso -->
              <div class="fc-card-face fc-card-back">
                <div class="fc-card-top">
                  <span class="fc-category-tag" id="fcBackCategory">Réponse & Clé</span>
                  <span class="fc-face-tag success">Verso · Solution</span>
                </div>
                <div class="fc-card-body">
                  <p class="fc-answer-text" id="fcBackText">Chargement de la réponse...</p>
                </div>
                <div class="fc-card-footer">
                  <span class="fc-hint">👆 Cliquer ou Espace pour revenir au recto</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Contrôles sous la carte -->
          <div class="fc-nav-controls">
            <button type="button" class="fc-nav-btn" onclick="prevFlashcard()" id="fcPrevBtn" title="Carte précédente (Flèche Gauche)">&larr; Précédente</button>
            <div class="fc-feedback-btns">
              <button type="button" class="fc-grade-btn review" onclick="markCard(false)" title="Marquer à réviser et passer à la suivante">🔄 À revoir</button>
              <button type="button" class="fc-grade-btn flip" onclick="flipCurrentCard()" title="Retourner la carte (Espace)">🔄 Retourner</button>
              <button type="button" class="fc-grade-btn known" onclick="markCard(true)" title="Marquer comme maîtrisée et passer à la suivante">✅ Maîtrisée</button>
            </div>
            <button type="button" class="fc-nav-btn" onclick="nextFlashcard()" id="fcNextBtn" title="Carte suivante (Flèche Droite)">Suivante &rarr;</button>
          </div>
        </div>

        <!-- Vue Grille Intégrale (20 cartes) -->
        <div id="fcGridView" class="fc-grid-view" style="display: none;">
          <div class="fc-grid-container" id="fcGridContainer"></div>
        </div>
      </div>
    </section>
    """


def build_quiz_html(quiz_questions: list[dict[str, Any]]) -> str:
    """Construit le balisage HTML de la section interactive du Quizz (20 questions)."""
    return f"""
    <section id="quiz-section" class="interactive-tool-section">
      <div class="tool-section-header">
        <div class="tool-badge-pill quiz-badge">🎯 Auto-Évaluation</div>
        <h2>Quizz de Maîtrise (20 Questions)</h2>
        <p>Validez votre compréhension sur les 20 points cardinaux du cours avec validation instantanée et explications détaillées.</p>
      </div>

      <div class="quiz-container">
        <!-- Barre de Score & Progression -->
        <div class="quiz-status-bar">
          <div class="quiz-score-box">
            <span class="quiz-score-label">Score :</span>
            <span class="quiz-score-val" id="quizScore">0</span>
            <span class="quiz-score-max">/ 20</span>
            <span class="quiz-percent-pill" id="quizPercent">0%</span>
          </div>
          <div class="quiz-progress-text">
            <span id="quizAnsweredCount">0</span> sur 20 répondues
          </div>
          <button type="button" class="quiz-reset-btn" onclick="resetQuiz()">🔄 Réinitialiser le Quizz</button>
        </div>

        <!-- Jauge de progression du quizz -->
        <div class="quiz-progress-track">
          <div class="quiz-progress-bar" id="quizProgressBar" style="width: 0%;"></div>
        </div>

        <!-- Liste des 20 questions -->
        <div class="quiz-questions-list" id="quizQuestionsList"></div>

        <!-- Carte récapitulative finale -->
        <div class="quiz-final-card" id="quizFinalCard" style="display: none;">
          <div class="quiz-trophy-icon">🏆</div>
          <h3 id="quizFinalTitle">Quizz Validé !</h3>
          <p id="quizFinalMsg">Félicitations pour votre apprentissage approfondi.</p>
          <div class="quiz-final-score-display" id="quizFinalScore">Score : 0 / 20</div>
          <button type="button" class="fc-grade-btn known" onclick="resetQuiz()">🔄 Recommencer pour viser 20/20</button>
        </div>
      </div>
    </section>
    """


def generate_learn_course_html(
    title: str,
    topic: str,
    markdown_content: str,
    sources: list[dict[str, Any]],
    created_at_str: str = "",
) -> str:
    """Génère un document HTML complet, autonome et haut de gamme pour le cours du Mode Apprendre."""
    sources = sources or []
    learning_time = estimate_reading_time_minutes(markdown_content)
    clean_title = title.strip() or "Cours complet · Mode Apprendre"
    clean_topic = topic.strip() or clean_title

    # Extraction des 20 Flashcards et 20 Questions de Quizz
    flashcards = parse_flashcards(markdown_content, clean_topic)
    quiz_questions = parse_quiz(markdown_content, clean_topic)

    # Nettoyage du Markdown pour isoler les modules de cours didactiques
    body_md = strip_raw_modules_for_body(markdown_content)
    body_html, toc = markdown_to_html(body_md, sources)

    # Blocs interactifs
    flashcards_html = build_flashcards_html(flashcards)
    quiz_html = build_quiz_html(quiz_questions)

    # Construction du Sommaire (TOC) enrichi avec Flashcards et Quizz
    toc_html_parts = []
    toc_html_parts.append('<div class="report-toc-card">')
    toc_html_parts.append('<div class="report-toc-header">')
    toc_html_parts.append('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>')
    toc_html_parts.append('<span>Sommaire du cours & Activités</span>')
    toc_html_parts.append('</div>')
    toc_html_parts.append('<nav class="report-toc-list">')
    for item in toc:
        indent_class = f"toc-level-{item['level']}"
        toc_html_parts.append(
            f'<a href="#{item["anchor"]}" class="report-toc-link {indent_class}">'
            f'<span>{html.escape(item["text"])}</span>'
            f'</a>'
        )
    # Liens interactifs dans le sommaire
    toc_html_parts.append('<div class="toc-interactive-divider"></div>')
    toc_html_parts.append('<a href="#flashcards-section" class="report-toc-link toc-interactive"><span class="toc-icon">📇</span><span>20 Flashcards de révision</span></a>')
    toc_html_parts.append('<a href="#quiz-section" class="report-toc-link toc-interactive"><span class="toc-icon">🎯</span><span>Quizz d\'auto-évaluation (20 questions)</span></a>')
    if sources:
        toc_html_parts.append('<a href="#bibliography-sources" class="report-toc-link toc-interactive"><span class="toc-icon">📚</span><span>Supports didactiques (' + str(len(sources)) + ')</span></a>')
    toc_html_parts.append('</nav></div>')
    toc_html = "".join(toc_html_parts)

    # Construction de la section des sources / supports didactiques
    sources_html_parts = []
    if sources:
        sources_html_parts.append('<section id="bibliography-sources" class="report-sources-section">')
        sources_html_parts.append('<div class="report-sources-header">')
        sources_html_parts.append('<h2>')
        sources_html_parts.append(f'<span class="sources-icon">📚</span> Supports didactiques et références du cours ({len(sources)})')
        sources_html_parts.append('</h2>')
        sources_html_parts.append(f'<p>Les concepts, exemples et bonnes pratiques de ce cours sont étayés par les documentations et publications recensées ci-dessous.</p>')
        sources_html_parts.append('</div>')
        sources_html_parts.append('<div class="report-sources-grid">')

        for idx, src in enumerate(sources, start=1):
            s_title = html.escape(src.get("title") or f"Support {idx}")
            s_url = html.escape(src.get("url") or "#")
            s_domain = html.escape(extract_domain(src.get("url") or ""))
            s_snippet = html.escape(src.get("snippet") or "")
            s_provider = html.escape(src.get("provider") or "web")
            extra_class = " source-card-extra source-card-hidden" if idx > 12 else ""

            sources_html_parts.append(
                f'<article id="source-{idx}" class="source-card{extra_class}">'
                f'<div class="source-card-top">'
                f'<span class="source-index">#{idx}</span>'
                f'<span class="source-domain">{s_domain}</span>'
                f'<span class="source-provider-badge">{s_provider}</span>'
                f'</div>'
                f'<h3 class="source-title">'
                f'<a href="{s_url}" target="_blank" rel="noopener noreferrer">{s_title} '
                f'<svg class="external-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>'
                f'</a>'
                f'</h3>'
            )
            if s_snippet:
                sources_html_parts.append(f'<p class="source-snippet">« {s_snippet} »</p>')
            sources_html_parts.append(
                f'<div class="source-card-bottom">'
                f'<a href="{s_url}" target="_blank" rel="noopener noreferrer" class="source-direct-link">Consulter la source pédagogique originale &rarr;</a>'
                f'</div>'
                f'</article>'
            )

        sources_html_parts.append('</div>')
        if len(sources) > 12:
            sources_html_parts.append(
                f'<div class="sources-toggle-container">'
                f'<button type="button" id="toggle-sources-btn" class="sources-toggle-btn" onclick="toggleAllSources()">'
                f'<span>Afficher l\'ensemble des {len(sources)} supports didactiques (+{len(sources)-12})</span>'
                f'</button>'
                f'</div>'
            )
        sources_html_parts.append('</section>')
    sources_html = "".join(sources_html_parts)

    escaped_title = html.escape(clean_title)
    escaped_topic = html.escape(clean_topic)
    date_display = html.escape(created_at_str or "Date récente")

    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escaped_title} — Cours Complet</title>
  <meta name="description" content="Cours pédagogique structuré avec 20 flashcards et 20 questions de quizz : {escaped_topic}" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Lora:ital,wght@0,400;0,600;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-serif: 'Lora', Georgia, serif;
      --font-mono: 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;

      --bg-page: #0d0f18;
      --bg-card: #151829;
      --bg-card-subtle: #1c2035;
      --bg-hero: linear-gradient(135deg, rgba(49, 46, 129, 0.45) 0%, rgba(17, 24, 39, 0.95) 100%);
      --border-color: rgba(255, 255, 255, 0.1);
      --border-accent: rgba(167, 139, 250, 0.4);

      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --text-dim: #6b7280;
      --text-heading: #ffffff;

      --primary: #a78bfa;
      --primary-hover: #c4b5fd;
      --primary-glow: rgba(167, 139, 250, 0.2);
      --accent: #8b5cf6;
      --accent-badge: rgba(139, 92, 246, 0.22);
      --accent-badge-border: rgba(167, 139, 250, 0.45);
      --success: #34d399;
      --danger: #f87171;

      --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.35);
      --shadow-md: 0 8px 30px rgba(0, 0, 0, 0.5);
    }}

    [data-theme="light"] {{
      --bg-page: #f8fafc;
      --bg-card: #ffffff;
      --bg-card-subtle: #f1f5f9;
      --bg-hero: linear-gradient(135deg, rgba(238, 242, 255, 0.9) 0%, rgba(243, 232, 255, 0.9) 100%);
      --border-color: rgba(0, 0, 0, 0.1);
      --border-accent: rgba(139, 92, 246, 0.35);

      --text-main: #1e293b;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      --text-heading: #0f172a;

      --primary: #7c3aed;
      --primary-hover: #6d28d9;
      --primary-glow: rgba(124, 58, 237, 0.12);
      --accent: #6d28d9;
      --accent-badge: rgba(124, 58, 237, 0.12);
      --accent-badge-border: rgba(124, 58, 237, 0.3);
      --success: #059669;
      --danger: #dc2626;

      --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.06);
      --shadow-md: 0 10px 25px rgba(0, 0, 0, 0.08);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      font-family: var(--font-sans);
      background-color: var(--bg-page);
      color: var(--text-main);
      line-height: 1.7;
      transition: background-color 0.2s ease, color 0.2s ease;
      -webkit-font-smoothing: antialiased;
    }}

    /* Barre supérieure d'outils */
    .top-reader-bar {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--bg-card);
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(12px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 24px;
      gap: 16px;
      flex-wrap: wrap;
    }}

    .top-reader-brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 800;
      font-size: 15px;
      color: var(--text-heading);
    }}

    .badge-pill {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      background: var(--accent-badge);
      color: var(--primary);
      border: 1px solid var(--accent-badge-border);
      padding: 2px 8px;
      border-radius: 9999px;
    }}

    .top-reader-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}

    .reader-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
      text-decoration: none;
    }}

    .reader-btn:hover {{
      background: var(--primary-glow);
      border-color: var(--primary);
      color: var(--primary);
    }}

    .reader-btn.jump-pill {{
      background: var(--accent-badge);
      border-color: var(--accent-badge-border);
      color: var(--primary);
    }}
    .reader-btn.jump-pill:hover {{
      background: var(--primary);
      color: #ffffff;
    }}

    /* Conteneur principal */
    .report-wrapper {{
      max-width: 920px;
      margin: 0 auto;
      padding: 40px 24px 100px;
    }}

    /* En-tête Héro */
    .report-hero {{
      background: var(--bg-hero);
      border: 1px solid var(--border-accent);
      border-radius: 20px;
      padding: 40px 36px;
      margin-bottom: 40px;
      box-shadow: var(--shadow-md);
      position: relative;
      overflow: hidden;
    }}

    .hero-meta-row {{
      display: flex;
      align-items: center;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 20px;
      font-size: 12.5px;
      color: var(--text-muted);
    }}

    .meta-tag {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--accent-badge);
      color: var(--primary);
      border: 1px solid var(--accent-badge-border);
      padding: 3px 10px;
      border-radius: 6px;
      font-weight: 700;
      text-transform: uppercase;
      font-size: 11px;
    }}

    .report-hero h1 {{
      font-size: 32px;
      font-weight: 800;
      color: var(--text-heading);
      line-height: 1.25;
      margin-bottom: 18px;
      letter-spacing: -0.5px;
    }}

    .hero-topic-box {{
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 12px 18px;
      font-size: 14px;
      color: var(--text-muted);
    }}

    /* Sommaire */
    .report-toc-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 24px 28px;
      margin-bottom: 48px;
      box-shadow: var(--shadow-sm);
    }}
    .report-toc-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--primary);
      margin-bottom: 16px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border-color);
    }}
    .report-toc-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .report-toc-link {{
      color: var(--text-main);
      text-decoration: none;
      font-size: 14px;
      line-height: 1.4;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .report-toc-link:hover {{
      color: var(--primary);
      transform: translateX(4px);
    }}
    .toc-level-3 {{
      margin-left: 20px;
      font-size: 13px;
      color: var(--text-muted);
    }}
    .toc-interactive-divider {{
      height: 1px;
      background: var(--border-color);
      margin: 8px 0;
    }}
    .toc-interactive {{
      font-weight: 700;
      color: var(--primary);
    }}

    /* Typographie et corps du cours */
    .report-content {{
      font-family: var(--font-serif);
      font-size: 17.5px;
      line-height: 1.85;
      color: var(--text-main);
    }}
    .report-heading-1, .report-heading-2, .report-heading-3, .report-heading-4 {{
      font-family: var(--font-sans);
      color: var(--text-heading);
      font-weight: 800;
      scroll-margin-top: 80px;
      position: relative;
    }}
    .report-heading-1 {{ font-size: 26px; margin: 48px 0 18px; border-bottom: 2px solid var(--border-color); padding-bottom: 10px; }}
    .report-heading-2 {{ font-size: 22px; margin: 42px 0 16px; color: var(--primary); }}
    .report-heading-3 {{ font-size: 18.5px; margin: 32px 0 12px; }}
    .report-heading-4 {{ font-size: 16px; margin: 24px 0 8px; }}

    .heading-anchor {{
      position: absolute;
      left: -24px;
      color: var(--text-dim);
      opacity: 0;
      text-decoration: none;
      transition: opacity 0.15s ease;
    }}
    .report-heading-2:hover .heading-anchor, .report-heading-3:hover .heading-anchor {{
      opacity: 1;
    }}

    .report-paragraph {{
      margin-bottom: 20px;
    }}

    .report-divider {{
      border: 0;
      height: 1px;
      background: var(--border-color);
      margin: 36px 0;
    }}

    .report-list, .report-ordered-list {{
      margin: 0 0 24px 28px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .report-blockquote {{
      margin: 28px 0;
      padding: 16px 22px;
      border-left: 4px solid var(--primary);
      background: var(--bg-card-subtle);
      border-radius: 0 10px 10px 0;
      font-style: italic;
      color: var(--text-muted);
    }}

    .report-inline-code {{
      font-family: var(--font-mono);
      font-size: 13.5px;
      padding: 2px 6px;
      border-radius: 5px;
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      color: var(--primary);
    }}

    .code-block-container {{
      margin: 28px 0;
      border-radius: 12px;
      border: 1px solid var(--border-color);
      background: #0f121d;
      overflow: hidden;
      box-shadow: var(--shadow-sm);
    }}
    .code-block-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 16px;
      background: rgba(255, 255, 255, 0.04);
      border-bottom: 1px solid var(--border-color);
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: var(--text-muted);
      text-transform: uppercase;
    }}
    .code-copy-btn {{
      padding: 3px 8px;
      border-radius: 5px;
      border: 1px solid var(--border-color);
      background: transparent;
      color: var(--text-muted);
      font-size: 11px;
      cursor: pointer;
    }}
    pre {{
      padding: 18px 20px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 13.5px;
      line-height: 1.6;
      background: #0f121d;
      color: #f1f5f9;
      border-radius: 10px;
      border: 1px solid var(--border-color);
      margin: 24px 0;
      box-shadow: var(--shadow-sm);
    }}
    pre code {{
      background: transparent !important;
      color: inherit;
      padding: 0;
      font-family: inherit;
    }}
    .code-block-container pre {{
      margin: 0;
      border: none;
      border-radius: 0;
      background: transparent;
      color: #f1f5f9;
      box-shadow: none;
    }}

    .report-table-wrapper {{
      margin: 30px 0;
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
    }}
    .report-table {{
      width: 100%;
      border-collapse: collapse;
      font-family: var(--font-sans);
      font-size: 14px;
      text-align: left;
    }}
    .report-table th {{
      padding: 12px 16px;
      background: var(--bg-card-subtle);
      color: var(--text-heading);
      font-weight: 700;
      border-bottom: 1px solid var(--border-color);
      white-space: nowrap;
    }}
    .report-table td {{
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-color);
      color: var(--text-main);
    }}

    .report-citation-pill {{
      display: inline-block;
      font-family: var(--font-sans);
      font-size: 11.5px;
      font-weight: 700;
      padding: 1px 6px;
      margin: 0 2px;
      border-radius: 5px;
      background: var(--accent-badge);
      border: 1px solid var(--accent-badge-border);
      color: var(--primary);
      text-decoration: none;
    }}

    .report-external-link {{
      color: var(--primary);
      text-decoration: underline;
      display: inline-flex;
      align-items: center;
      gap: 3px;
    }}

    /* ============================================================== */
    /* SECTIONS INTERACTIVES : FLASHCARDS & QUIZZ (20 DE CHAQUE)     */
    /* ============================================================== */

    .interactive-tool-section {{
      margin: 60px 0;
      padding: 36px 32px;
      background: var(--bg-card);
      border: 1px solid var(--border-accent);
      border-radius: 20px;
      box-shadow: var(--shadow-md);
      scroll-margin-top: 80px;
    }}

    .tool-section-header {{
      margin-bottom: 24px;
    }}
    .tool-badge-pill {{
      display: inline-block;
      font-size: 11.5px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 3px 10px;
      border-radius: 6px;
      background: var(--accent-badge);
      border: 1px solid var(--accent-badge-border);
      color: var(--primary);
      margin-bottom: 10px;
    }}
    .tool-badge-pill.quiz-badge {{
      background: rgba(52, 211, 153, 0.18);
      border-color: rgba(52, 211, 153, 0.4);
      color: var(--success);
    }}
    .tool-section-header h2 {{
      font-family: var(--font-sans);
      font-size: 24px;
      font-weight: 800;
      color: var(--text-heading);
      margin-bottom: 6px;
    }}
    .tool-section-header p {{
      font-size: 14px;
      color: var(--text-muted);
    }}

    /* --- FLASHCARDS STYLES --- */
    .fc-toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }}
    .fc-counter-box {{
      display: flex;
      align-items: baseline;
      gap: 6px;
      font-size: 14px;
      color: var(--text-muted);
    }}
    .fc-current {{
      font-size: 20px;
      font-weight: 800;
      color: var(--primary);
    }}
    .fc-stats {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .fc-stat-pill {{
      font-size: 12px;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 6px;
      border: 1px solid var(--border-color);
      background: var(--bg-card-subtle);
    }}
    .fc-stat-pill.known {{
      color: var(--success);
      border-color: rgba(52, 211, 153, 0.3);
    }}
    .fc-stat-pill.review {{
      color: #fbbf24;
      border-color: rgba(251, 191, 36, 0.3);
    }}
    .fc-mode-actions {{
      display: flex;
      gap: 8px;
    }}
    .fc-btn-secondary {{
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid var(--border-color);
      background: var(--bg-card-subtle);
      color: var(--text-main);
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .fc-btn-secondary:hover {{
      background: var(--primary-glow);
      border-color: var(--primary);
      color: var(--primary);
    }}

    .fc-progress-track {{
      width: 100%;
      height: 6px;
      background: var(--bg-card-subtle);
      border-radius: 9999px;
      overflow: hidden;
      margin-bottom: 24px;
    }}
    .fc-progress-bar {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--primary));
      border-radius: 9999px;
      transition: width 0.3s ease;
    }}

    /* 3D Flip Card Scene */
    .fc-card-scene {{
      perspective: 1000px;
      width: 100%;
      max-width: 720px;
      min-height: 290px;
      margin: 0 auto 24px;
      cursor: pointer;
      user-select: none;
    }}
    .fc-card {{
      width: 100%;
      height: 100%;
      min-height: 290px;
      position: relative;
      transform-style: preserve-3d;
      transition: transform 0.45s cubic-bezier(0.4, 0, 0.2, 1);
      border-radius: 16px;
    }}
    .fc-card.is-flipped {{
      transform: rotateY(180deg);
    }}
    .fc-card-face {{
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      min-height: 290px;
      backface-visibility: hidden;
      border-radius: 16px;
      padding: 28px 32px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: var(--shadow-sm);
    }}
    .fc-card-front {{
      background: linear-gradient(145deg, var(--bg-card), var(--bg-card-subtle));
      border: 2px solid var(--border-accent);
    }}
    .fc-card-back {{
      background: linear-gradient(145deg, #181c33, #1e223d);
      border: 2px solid var(--primary);
      transform: rotateY(180deg);
    }}
    [data-theme="light"] .fc-card-back {{
      background: linear-gradient(145deg, #f5f3ff, #ede9fe);
      border: 2px solid var(--primary);
    }}

    .fc-card-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      margin-bottom: 14px;
    }}
    .fc-category-tag {{
      font-weight: 700;
      color: var(--primary);
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
    }}
    .fc-face-tag {{
      font-size: 11px;
      font-weight: 700;
      color: var(--text-dim);
      background: rgba(255, 255, 255, 0.06);
      padding: 2px 8px;
      border-radius: 6px;
    }}
    .fc-face-tag.success {{
      color: var(--success);
      background: rgba(52, 211, 153, 0.12);
    }}

    .fc-card-body {{
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 10px 0;
    }}
    .fc-prompt-text {{
      font-size: 21px;
      font-weight: 700;
      color: var(--text-heading);
      line-height: 1.4;
    }}
    .fc-answer-text {{
      font-size: 17.5px;
      font-weight: 500;
      color: var(--text-main);
      line-height: 1.6;
    }}

    .fc-card-footer {{
      display: flex;
      justify-content: center;
      margin-top: 14px;
    }}
    .fc-hint {{
      font-size: 11.5px;
      color: var(--text-dim);
      font-style: italic;
    }}

    /* Contrôles de navigation flashcards */
    .fc-nav-controls {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      max-width: 720px;
      margin: 0 auto;
      flex-wrap: wrap;
    }}
    .fc-nav-btn {{
      padding: 8px 16px;
      border-radius: 10px;
      border: 1px solid var(--border-color);
      background: var(--bg-card-subtle);
      color: var(--text-main);
      font-weight: 600;
      font-size: 13.5px;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .fc-nav-btn:hover:not(:disabled) {{
      background: var(--primary-glow);
      border-color: var(--primary);
      color: var(--primary);
    }}
    .fc-nav-btn:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}
    .fc-feedback-btns {{
      display: flex;
      gap: 8px;
    }}
    .fc-grade-btn {{
      padding: 8px 14px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.15s ease;
    }}
    .fc-grade-btn.known {{
      background: rgba(52, 211, 153, 0.16);
      border-color: rgba(52, 211, 153, 0.4);
      color: var(--success);
    }}
    .fc-grade-btn.known:hover {{
      background: var(--success);
      color: #ffffff;
    }}
    .fc-grade-btn.review {{
      background: rgba(251, 191, 36, 0.16);
      border-color: rgba(251, 191, 36, 0.4);
      color: #fbbf24;
    }}
    .fc-grade-btn.review:hover {{
      background: #fbbf24;
      color: #111827;
    }}
    .fc-grade-btn.flip {{
      background: var(--accent-badge);
      border-color: var(--accent-badge-border);
      color: var(--primary);
    }}
    .fc-grade-btn.flip:hover {{
      background: var(--primary);
      color: #ffffff;
    }}

    /* Vue Grille Intégrale */
    .fc-grid-container {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
      margin-top: 20px;
    }}
    .fc-grid-item {{
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 18px;
      cursor: pointer;
      transition: all 0.2s ease;
      min-height: 180px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }}
    .fc-grid-item:hover {{
      border-color: var(--primary);
      transform: translateY(-2px);
    }}
    .fc-grid-header {{
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      color: var(--primary);
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .fc-grid-text {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text-heading);
      line-height: 1.5;
    }}
    .fc-grid-subtext {{
      font-size: 12.5px;
      color: var(--text-muted);
      margin-top: 10px;
      padding-top: 8px;
      border-top: 1px dashed var(--border-color);
    }}

    /* --- QUIZZ STYLES --- */
    .quiz-status-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }}
    .quiz-score-box {{
      display: flex;
      align-items: baseline;
      gap: 6px;
      font-size: 15px;
      color: var(--text-muted);
    }}
    .quiz-score-val {{
      font-size: 22px;
      font-weight: 800;
      color: var(--success);
    }}
    .quiz-percent-pill {{
      font-size: 12px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 9999px;
      background: rgba(52, 211, 153, 0.15);
      border: 1px solid rgba(52, 211, 153, 0.35);
      color: var(--success);
    }}
    .quiz-progress-text {{
      font-size: 13.5px;
      font-weight: 600;
      color: var(--text-dim);
    }}
    .quiz-reset-btn {{
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid var(--border-color);
      background: var(--bg-card-subtle);
      color: var(--text-main);
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
    }}
    .quiz-reset-btn:hover {{
      border-color: var(--danger);
      color: var(--danger);
    }}

    .quiz-progress-track {{
      width: 100%;
      height: 6px;
      background: var(--bg-card-subtle);
      border-radius: 9999px;
      overflow: hidden;
      margin-bottom: 28px;
    }}
    .quiz-progress-bar {{
      height: 100%;
      background: linear-gradient(90deg, #10b981, #34d399);
      border-radius: 9999px;
      transition: width 0.3s ease;
    }}

    .quiz-questions-list {{
      display: flex;
      flex-direction: column;
      gap: 24px;
    }}
    .quiz-card {{
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 22px 24px;
      transition: border-color 0.2s ease;
    }}
    .quiz-card:hover {{
      border-color: var(--border-accent);
    }}
    .quiz-card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }}
    .quiz-num-badge {{
      font-size: 11.5px;
      font-weight: 800;
      background: var(--accent-badge);
      border: 1px solid var(--accent-badge-border);
      color: var(--primary);
      padding: 2px 8px;
      border-radius: 6px;
    }}
    .quiz-status-indicator {{
      font-size: 12px;
      font-weight: 700;
    }}
    .quiz-question-title {{
      font-size: 16.5px;
      font-weight: 700;
      color: var(--text-heading);
      line-height: 1.45;
      margin-bottom: 16px;
    }}

    .quiz-options-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }}
    @media (min-width: 640px) {{
      .quiz-options-grid {{
        grid-template-columns: 1fr 1fr;
      }}
    }}

    .quiz-option-btn {{
      display: flex;
      align-items: flex-start;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid var(--border-color);
      background: var(--bg-card);
      color: var(--text-main);
      font-size: 13.5px;
      line-height: 1.4;
      text-align: left;
      cursor: pointer;
      transition: all 0.15s ease;
      width: 100%;
    }}
    .quiz-option-btn:hover:not(:disabled) {{
      background: var(--primary-glow);
      border-color: var(--primary);
      transform: translateY(-1px);
    }}
    .quiz-option-btn:disabled {{
      cursor: default;
    }}
    .quiz-letter {{
      font-weight: 800;
      font-size: 12px;
      background: rgba(255, 255, 255, 0.08);
      color: var(--text-heading);
      padding: 2px 7px;
      border-radius: 5px;
      flex-shrink: 0;
    }}
    .quiz-option-btn.correct {{
      background: rgba(52, 211, 153, 0.22) !important;
      border-color: var(--success) !important;
      color: #ffffff !important;
    }}
    .quiz-option-btn.correct .quiz-letter {{
      background: var(--success);
      color: #ffffff;
    }}
    .quiz-option-btn.incorrect {{
      background: rgba(248, 113, 113, 0.22) !important;
      border-color: var(--danger) !important;
      color: #ffffff !important;
    }}
    .quiz-option-btn.incorrect .quiz-letter {{
      background: var(--danger);
      color: #ffffff;
    }}

    .quiz-explanation-box {{
      margin-top: 14px;
      padding: 12px 16px;
      background: rgba(167, 139, 250, 0.1);
      border-left: 3px solid var(--primary);
      border-radius: 0 8px 8px 0;
      font-size: 13px;
      color: var(--text-main);
      display: none;
      animation: fadeIn 0.25s ease;
    }}
    .quiz-explanation-box strong {{
      color: var(--primary);
      display: block;
      margin-bottom: 4px;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(4px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    /* Carte finale quizz */
    .quiz-final-card {{
      background: linear-gradient(135deg, rgba(49, 46, 129, 0.5), rgba(17, 24, 39, 0.8));
      border: 2px solid var(--success);
      border-radius: 16px;
      padding: 32px;
      text-align: center;
      margin-top: 32px;
      animation: fadeIn 0.4s ease;
    }}
    .quiz-trophy-icon {{
      font-size: 40px;
      margin-bottom: 10px;
    }}
    .quiz-final-card h3 {{
      font-size: 22px;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 6px;
    }}
    .quiz-final-card p {{
      font-size: 14px;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}
    .quiz-final-score-display {{
      font-size: 24px;
      font-weight: 800;
      color: var(--success);
      margin-bottom: 20px;
    }}

    /* Section des sources bibliographiques */
    .report-sources-section {{
      margin-top: 60px;
      padding-top: 36px;
      border-top: 2px dashed var(--border-color);
    }}
    .report-sources-header {{
      margin-bottom: 24px;
    }}
    .report-sources-header h2 {{
      font-family: var(--font-sans);
      font-size: 22px;
      font-weight: 700;
      color: var(--text-heading);
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
    }}
    .report-sources-header p {{
      font-size: 13.5px;
      color: var(--text-muted);
    }}

    .report-sources-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
    }}

    .source-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: all 0.18s ease;
    }}
    .source-card:hover {{
      border-color: var(--border-accent);
      box-shadow: var(--shadow-sm);
      transform: translateY(-2px);
    }}

    .source-card-top {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
    }}
    .source-index {{
      font-weight: 800;
      color: var(--primary);
      background: var(--accent-badge);
      padding: 1px 6px;
      border-radius: 4px;
    }}
    .source-domain {{
      color: var(--text-muted);
      font-family: var(--font-mono);
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
    }}
    .source-provider-badge {{
      font-size: 10px;
      text-transform: uppercase;
      padding: 1px 5px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-dim);
    }}

    .source-title {{
      font-family: var(--font-sans);
      font-size: 14px;
      font-weight: 600;
      line-height: 1.4;
    }}
    .source-title a {{
      color: var(--text-heading);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .source-title a:hover {{
      color: var(--primary);
    }}

    .source-snippet {{
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.5;
      font-style: italic;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      flex: 1;
    }}

    .source-card-bottom {{
      margin-top: auto;
      padding-top: 8px;
      border-top: 1px solid var(--border-color);
    }}
    .source-direct-link {{
      font-size: 11.5px;
      font-weight: 600;
      color: var(--primary);
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .source-direct-link:hover {{
      text-decoration: underline;
    }}

    .source-card-hidden {{
      display: none !important;
    }}
    .sources-toggle-container {{
      margin-top: 24px;
      display: flex;
      justify-content: center;
    }}
    .sources-toggle-btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 11px 22px;
      border-radius: 10px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--primary);
      font-family: var(--font-sans);
      font-size: 13.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .sources-toggle-btn:hover {{
      background: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
      box-shadow: var(--shadow-sm);
      transform: translateY(-1px);
    }}

    /* Pied de page */
    .report-footer {{
      margin-top: 60px;
      padding-top: 24px;
      border-top: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12.5px;
      color: var(--text-dim);
      flex-wrap: wrap;
      gap: 12px;
    }}

    /* Bandeau mode aperçu PDF */
    .pdf-preview-banner {{
      display: none;
      background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%);
      color: #ffffff;
      padding: 10px 20px;
      font-size: 13px;
      font-weight: 500;
      position: sticky;
      top: 57px;
      z-index: 99;
      box-shadow: 0 4px 12px rgba(124, 58, 237, 0.25);
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .pdf-preview-banner.is-active {{
      display: flex;
    }}
    .pdf-preview-banner-text {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pdf-preview-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pdf-preview-btn {{
      background: rgba(255, 255, 255, 0.2);
      border: 1px solid rgba(255, 255, 255, 0.4);
      color: #ffffff;
      padding: 4px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.15s;
    }}
    .pdf-preview-btn:hover {{
      background: rgba(255, 255, 255, 0.35);
    }}
    .pdf-preview-btn.primary {{
      background: #ffffff;
      color: #7c3aed;
      border-color: #ffffff;
    }}
    .pdf-preview-btn.primary:hover {{
      background: #f1f5f9;
    }}

    /* Styles d'impression & Beau PDF */
    @page {{
      size: A4 portrait;
      margin: 16mm 14mm 16mm 14mm;
    }}
    @media print {{
      *, *::before, *::after {{
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }}
      .top-reader-bar, .pdf-preview-banner, .code-copy-btn, .heading-anchor, .fc-toolbar, .fc-nav-controls, .quiz-reset-btn, .source-card-link, .learn-sources-toggle-container {{
        display: none !important;
      }}
      body {{
        background: #ffffff !important;
        color: #0f172a !important;
        padding: 0 !important;
        font-size: 10.5pt !important;
        line-height: 1.6 !important;
      }}
      .report-wrapper {{
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
      }}
      .report-hero {{
        background: #f5f3ff !important;
        border: 1.5px solid #ddd6fe !important;
        border-radius: 8px !important;
        box-shadow: none !important;
        padding: 20px 24px !important;
        margin-bottom: 24px !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .meta-tag {{
        background: #ede9fe !important;
        color: #6d28d9 !important;
        border: 1px solid #c4b5fd !important;
        font-size: 8pt !important;
        padding: 3px 8px !important;
      }}
      .meta-date, .meta-time {{
        color: #64748b !important;
        font-size: 8.5pt !important;
      }}
      .report-hero h1 {{
        color: #0f172a !important;
        font-size: 19pt !important;
        line-height: 1.25 !important;
        margin: 12px 0 !important;
      }}
      .hero-topic-box {{
        background: #ffffff !important;
        color: #334155 !important;
        border: 1px solid #e2e8f0 !important;
        border-left: 4px solid #7c3aed !important;
        padding: 10px 14px !important;
        font-size: 9.5pt !important;
      }}
      h1, h2, h3, h4 {{
        color: #0f172a !important;
        break-after: avoid;
        page-break-after: avoid;
      }}
      h2 {{
        border-bottom: 1.5px solid #e2e8f0 !important;
        padding-bottom: 6px !important;
        margin-top: 26px !important;
      }}
      .interactive-tool-section {{
        border: 1px solid #e2e8f0 !important;
        background: #ffffff !important;
        box-shadow: none !important;
        break-inside: avoid;
        page-break-inside: avoid;
        margin-top: 30px !important;
      }}
      .fc-single-view {{
        display: none !important;
      }}
      .fc-grid-view {{
        display: grid !important;
        grid-template-columns: repeat(2, 1fr) !important;
        gap: 12px !important;
      }}
      .fc-grid-card {{
        background: #fdfdfd !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 6px !important;
        padding: 12px !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .quiz-explanation-box {{
        display: block !important;
        background: #f0fdf4 !important;
        border: 1px solid #bbf7d0 !important;
        border-radius: 6px !important;
        padding: 10px 12px !important;
        margin-top: 8px !important;
        font-size: 9pt !important;
      }}
      .source-card-hidden {{
        display: block !important;
      }}
      .learn-reader-source-card {{
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 6px !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .code-block {{
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 6px !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .code-block pre, .code-block code {{
        color: #f8fafc !important;
        background: transparent !important;
      }}
    }}
  </style>
</head>
<body>

  <!-- Barre supérieure d'outils -->
  <header class="top-reader-bar">
    <div class="top-reader-brand">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"></path><path d="M6 12v5c3 3 9 3 12 0v-5"></path></svg>
      <span>cLAIr</span>
      <span class="badge-pill">Mode Apprendre</span>
    </div>
    <div class="top-reader-actions">
      <a href="#flashcards-section" class="reader-btn jump-pill" title="Accéder aux 20 flashcards de révision">
        <span>📇 Flashcards (20)</span>
      </a>
      <a href="#quiz-section" class="reader-btn jump-pill" title="Accéder au quizz de 20 questions">
        <span>🎯 Quizz (20)</span>
      </a>
      <button type="button" class="reader-btn" onclick="toggleTheme()" id="themeBtn" title="Basculer thème sombre / clair">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
        <span>Thème</span>
      </button>
      <a href="?download=1" class="reader-btn" download title="Télécharger le fichier .html complet">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
        <span>Télécharger .html</span>
      </a>
      <button type="button" class="reader-btn primary-print-btn" onclick="printPdf()" title="Imprimer ou enregistrer en Beau PDF">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"></polyline><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path><rect x="6" y="14" width="12" height="8"></rect></svg>
        <span>📕 Beau PDF</span>
      </button>
      <button type="button" class="reader-btn" onclick="copyFullMarkdown()" id="copyMdBtn" title="Copier le Markdown intégral">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        <span>Copier Markdown</span>
      </button>
    </div>
  </header>

  <!-- Notice bandeau mode aperçu PDF -->
  <aside id="pdf-banner" class="pdf-preview-banner" role="region" aria-label="Mode Aperçu & Impression PDF">
    <div class="pdf-preview-banner-text">
      <span>📕</span>
      <span><strong>Mode Beau Polycopié PDF (A4) :</strong> La boîte d'impression s'ouvre pour enregistrer le cours magistral et ses grilles de révision en PDF.</span>
    </div>
    <div class="pdf-preview-actions">
      <button type="button" class="pdf-preview-btn primary" onclick="printPdf()">
        🖨️ Réouvrir impression PDF
      </button>
      <a href="?" class="pdf-preview-btn">
        🌐 Revenir au site HTML interactif
      </a>
    </div>
  </aside>

  <main class="report-wrapper">
    <!-- En-tête Héro -->
    <header class="report-hero">
      <div class="hero-meta-row">
        <span class="meta-tag">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 10v6M2 10l10-5 10 5-10 5z"></path><path d="M6 12v5c3 3 9 3 12 0v-5"></path></svg>
          Cours Magistral Structuré
        </span>
        <span class="meta-date">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
          {date_display}
        </span>
        <span class="meta-time">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
          ~{learning_time} min d'apprentissage
        </span>
      </div>

      <h1>{escaped_title}</h1>

      <div class="hero-topic-box">
        <strong>Sujet d'apprentissage :</strong>
        <span>« {escaped_topic} »</span>
      </div>
    </header>

    <!-- Table des matières dynamique -->
    {toc_html}

    <!-- Corps du cours -->
    <article class="report-content">
      {body_html}
    </article>

    <!-- 20 Flashcards interactives -->
    {flashcards_html}

    <!-- Quizz interactif 20 questions -->
    {quiz_html}

    <!-- Grille des sources didactiques -->
    {sources_html}

    <!-- Pied de page -->
    <footer class="report-footer">
      <span>Généré par cLAIr · Mode Apprendre (20 Flashcards & 20 Questions de Quizz)</span>
      <span>{len(sources)} supports didactiques croisés</span>
    </footer>
  </main>

  <!-- Script utilitaire intégré -->
  <script>
    // Données interactives injectées
    const flashcardsData = {json.dumps(flashcards, ensure_ascii=False)};
    const quizData = {json.dumps(quiz_questions, ensure_ascii=False)};

    // Bascule de thème sombre / clair
    function toggleTheme() {{
      const htmlEl = document.documentElement;
      const current = htmlEl.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      htmlEl.setAttribute('data-theme', next);
      localStorage.setItem('clair_theme', next);
    }}

    (function() {{
      const saved = localStorage.getItem('clair_theme');
      if (saved) {{
        document.documentElement.setAttribute('data-theme', saved);
      }}
    }})();

    // Copie de bloc de code
    function copyCode(btn) {{
      const code = btn.closest('.code-block-container').querySelector('code').innerText;
      navigator.clipboard.writeText(code).then(() => {{
        const oldText = btn.innerText;
        btn.innerText = 'Copié !';
        btn.style.color = '#34d399';
        setTimeout(() => {{
          btn.innerText = oldText;
          btn.style.color = '';
        }}, 2000);
      }});
    }}

    // Données Markdown brutes pour copie intégrale
    const rawMarkdownContent = {json.dumps(markdown_content, ensure_ascii=False)};

    function copyFullMarkdown() {{
      navigator.clipboard.writeText(rawMarkdownContent).then(() => {{
        const btn = document.getElementById('copyMdBtn');
        const span = btn.querySelector('span');
        const oldText = span.innerText;
        span.innerText = 'Markdown Copié !';
        btn.style.borderColor = '#34d399';
        setTimeout(() => {{
          span.innerText = oldText;
          btn.style.borderColor = '';
        }}, 2000);
      }});
    }}

    // ==========================================
    // MOTEUR INTERACTIF FLASHCARDS (20 CARTES)
    // ==========================================
    let fcIndex = 0;
    let fcFlipped = false;
    let fcKnownSet = new Set();
    let fcReviewSet = new Set();
    let fcIsGridView = false;

    function renderCurrentFlashcard() {{
      if (!flashcardsData || flashcardsData.length === 0) return;
      const card = flashcardsData[fcIndex];
      const cardEl = document.getElementById('fcActiveCard');
      cardEl.classList.remove('is-flipped');
      fcFlipped = false;

      document.getElementById('fcCurrent').innerText = (fcIndex + 1);
      document.getElementById('fcFrontCategory').innerText = card.category || 'Concept';
      document.getElementById('fcBackCategory').innerText = card.category || 'Solution';
      document.getElementById('fcFrontText').innerText = card.recto;
      document.getElementById('fcBackText').innerText = card.verso;

      const progress = ((fcIndex + 1) / flashcardsData.length) * 100;
      document.getElementById('fcProgressBar').style.width = progress + '%';

      document.getElementById('fcPrevBtn').disabled = (fcIndex === 0);
      document.getElementById('fcNextBtn').disabled = (fcIndex === flashcardsData.length - 1);
    }}

    function flipCurrentCard() {{
      const cardEl = document.getElementById('fcActiveCard');
      fcFlipped = !fcFlipped;
      if (fcFlipped) {{
        cardEl.classList.add('is-flipped');
      }} else {{
        cardEl.classList.remove('is-flipped');
      }}
    }}

    function nextFlashcard() {{
      if (fcIndex < flashcardsData.length - 1) {{
        fcIndex++;
        renderCurrentFlashcard();
      }}
    }}

    function prevFlashcard() {{
      if (fcIndex > 0) {{
        fcIndex--;
        renderCurrentFlashcard();
      }}
    }}

    function markCard(known) {{
      const cardId = flashcardsData[fcIndex].id;
      if (known) {{
        fcKnownSet.add(cardId);
        fcReviewSet.delete(cardId);
      }} else {{
        fcReviewSet.add(cardId);
        fcKnownSet.delete(cardId);
      }}
      document.getElementById('fcKnownCount').innerText = fcKnownSet.size;
      document.getElementById('fcReviewCount').innerText = fcReviewSet.size;
      nextFlashcard();
    }}

    function shuffleFlashcards() {{
      for (let i = flashcardsData.length - 1; i > 0; i--) {{
        const j = Math.floor(Math.random() * (i + 1));
        [flashcardsData[i], flashcardsData[j]] = [flashcardsData[j], flashcardsData[i]];
      }}
      fcIndex = 0;
      renderCurrentFlashcard();
      if (fcIsGridView) renderGridFlashcards();
    }}

    function toggleFlashcardView() {{
      fcIsGridView = !fcIsGridView;
      const singleEl = document.getElementById('fcSingleView');
      const gridEl = document.getElementById('fcGridView');
      const btn = document.getElementById('fcViewToggleBtn');
      if (fcIsGridView) {{
        singleEl.style.display = 'none';
        gridEl.style.display = 'block';
        btn.innerText = '🃏 Mode Carte par Carte';
        renderGridFlashcards();
      }} else {{
        singleEl.style.display = 'block';
        gridEl.style.display = 'none';
        btn.innerText = '👁️ Voir les 20 cartes';
        renderCurrentFlashcard();
      }}
    }}

    function renderGridFlashcards() {{
      const container = document.getElementById('fcGridContainer');
      container.innerHTML = '';
      flashcardsData.forEach((c, idx) => {{
        const item = document.createElement('div');
        item.className = 'fc-grid-item';
        item.innerHTML = `
          <div class="fc-grid-header">
            <span>#${{idx + 1}} · ${{c.category || 'Concept'}}</span>
            <span>Recto / Verso</span>
          </div>
          <div class="fc-grid-text"><strong>Q :</strong> ${{c.recto}}</div>
          <div class="fc-grid-subtext"><strong>R :</strong> ${{c.verso}}</div>
        `;
        container.appendChild(item);
      }});
    }}

    // Raccourcis clavier pour les flashcards
    window.addEventListener('keydown', (e) => {{
      if (['input', 'textarea'].includes(document.activeElement.tagName.toLowerCase())) return;
      if (e.code === 'Space') {{
        e.preventDefault();
        flipCurrentCard();
      }} else if (e.code === 'ArrowRight') {{
        nextFlashcard();
      }} else if (e.code === 'ArrowLeft') {{
        prevFlashcard();
      }}
    }});

    // ==========================================
    // MOTEUR INTERACTIF QUIZZ (20 QUESTIONS)
    // ==========================================
    let userQuizAnswers = {{}};
    let quizScore = 0;

    function renderQuizQuestions() {{
      const listEl = document.getElementById('quizQuestionsList');
      listEl.innerHTML = '';

      quizData.forEach((q, qIdx) => {{
        const card = document.createElement('div');
        card.className = 'quiz-card';
        card.id = 'quizCard_' + qIdx;

        let optionsHtml = '';
        const letters = ['A', 'B', 'C', 'D'];
        q.options.forEach((optText, optIdx) => {{
          optionsHtml += `
            <button type="button" class="quiz-option-btn" id="optBtn_${{qIdx}}_${{optIdx}}" onclick="selectQuizOption(${{qIdx}}, ${{optIdx}})">
              <span class="quiz-letter">${{letters[optIdx]}}</span>
              <span class="quiz-opt-text">${{optText}}</span>
            </button>
          `;
        }});

        card.innerHTML = `
          <div class="quiz-card-header">
            <span class="quiz-num-badge">Question ${{qIdx + 1}} / 20</span>
            <span class="quiz-status-indicator" id="quizStatus_${{qIdx}}">⚪ En attente</span>
          </div>
          <div class="quiz-question-title">${{q.question}}</div>
          <div class="quiz-options-grid">${{optionsHtml}}</div>
          <div class="quiz-explanation-box" id="quizExpl_${{qIdx}}">
            <strong>💡 Explication pédagogique :</strong>
            <span>${{q.explanation || 'Analyse validée par le cours.'}}</span>
          </div>
        `;
        listEl.appendChild(card);
      }});
    }}

    function selectQuizOption(qIdx, selectedOptIdx) {{
      if (userQuizAnswers.hasOwnProperty(qIdx)) return; // déjà répondu
      userQuizAnswers[qIdx] = selectedOptIdx;

      const q = quizData[qIdx];
      const isCorrect = (selectedOptIdx === q.answer);
      const statusEl = document.getElementById('quizStatus_' + qIdx);
      const explBox = document.getElementById('quizExpl_' + qIdx);

      // Désactiver tous les boutons de cette question
      q.options.forEach((_, optIdx) => {{
        const btn = document.getElementById(`optBtn_${{qIdx}}_${{optIdx}}`);
        btn.disabled = true;
        if (optIdx === q.answer) {{
          btn.classList.add('correct');
        }}
        if (optIdx === selectedOptIdx && !isCorrect) {{
          btn.classList.add('incorrect');
        }}
      }});

      if (isCorrect) {{
        quizScore++;
        statusEl.innerText = '✅ Correct (+1)';
        statusEl.style.color = 'var(--success)';
      }} else {{
        statusEl.innerText = '❌ Incorrect';
        statusEl.style.color = 'var(--danger)';
      }}

      explBox.style.display = 'block';
      updateQuizProgress();
    }}

    function updateQuizProgress() {{
      const answeredCount = Object.keys(userQuizAnswers).length;
      document.getElementById('quizScore').innerText = quizScore;
      document.getElementById('quizAnsweredCount').innerText = answeredCount;

      const percent = Math.round((quizScore / quizData.length) * 100);
      document.getElementById('quizPercent').innerText = percent + '%';

      const progressPercent = (answeredCount / quizData.length) * 100;
      document.getElementById('quizProgressBar').style.width = progressPercent + '%';

      // Vérification fin du quizz
      if (answeredCount === quizData.length) {{
        const finalCard = document.getElementById('quizFinalCard');
        finalCard.style.display = 'block';
        document.getElementById('quizFinalScore').innerText = `Score Final : ${{quizScore}} / 20 (${{percent}}%)`;
        if (quizScore >= 18) {{
          document.getElementById('quizFinalTitle').innerText = '🎉 Maîtrise Exceptionnelle !';
          document.getElementById('quizFinalMsg').innerText = 'Vous avez parfaitement assimilé l\'ensemble des 20 points cardinaux du cours.';
        }} else if (quizScore >= 14) {{
          document.getElementById('quizFinalTitle').innerText = '👏 Très Bon Niveau !';
          document.getElementById('quizFinalMsg').innerText = 'Solide compréhension globale. Révisez les quelques questions manquées grâce aux flashcards.';
        }} else {{
          document.getElementById('quizFinalTitle').innerText = '💪 Bon Début d\'Apprentissage !';
          document.getElementById('quizFinalMsg').innerText = 'Prenez le temps de revoir les flashcards interactives ci-dessus avant de retenter le quizz.';
        }}
        finalCard.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      }}
    }}

    function resetQuiz() {{
      userQuizAnswers = {{}};
      quizScore = 0;
      document.getElementById('quizFinalCard').style.display = 'none';
      renderQuizQuestions();
      updateQuizProgress();
    }}

    let allSourcesExpanded = false;
    function toggleAllSources() {{
      allSourcesExpanded = !allSourcesExpanded;
      const extraCards = document.querySelectorAll('.source-card-extra');
      extraCards.forEach(c => {{
        c.classList.toggle('source-card-hidden', !allSourcesExpanded);
      }});
      const btn = document.getElementById('toggle-sources-btn');
      if (btn) {{
        btn.querySelector('span').textContent = allSourcesExpanded
          ? '▲ Réduire l\'affichage des supports didactiques'
          : `▼ Afficher l'ensemble des ${{extraCards.length + 12}} supports didactiques (+${{extraCards.length}})`;
      }}
    }}

    function printPdf() {{
      window.print();
    }}

    // Initialisation au chargement de la page
    document.addEventListener('DOMContentLoaded', () => {{
      renderCurrentFlashcard();
      renderQuizQuestions();

      const params = new URLSearchParams(window.location.search);
      if (params.get('pdf') === '1' || params.get('print') === '1') {{
        const banner = document.getElementById('pdf-banner');
        if (banner) banner.classList.add('is-active');
        setTimeout(() => {{
          window.print();
        }}, 500);
      }}
    }});
  </script>
</body>
</html>"""
