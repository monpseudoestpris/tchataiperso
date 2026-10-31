"""
presentation_html — Générateur de présentation type PowerPoint par IA (diaporama interactif 16:9).

Règle d'or : MOINS DE TEXTE PAR SLIDE, MAIS PLUS DE SLIDES.
- Généré par IA via LLM (avec fallback algorithmique découpé en micro-slides percutantes).
- 1 seule idée forte par diapositive.
- Titres d'action orientés résultat.
- Puces courtes (6 à 12 mots maximum).
- Chiffres clés (KPIs), mini-cartes comparatives, citations et takeaways percutants.
- Format 16:9 autonome, navigation clavier/tactile, mode plein écran (F),
  vue mosaïque (G), bascule sombre/clair (T) et impression PDF A4 paysage.
"""

from __future__ import annotations

import html
import json
import logging
import re
import unicodedata
from copy import deepcopy
from typing import Any

import httpx

from .source_registry import CITATION_RE, citation_numbers, is_document
from .deep_search_html import extract_domain, slugify

_logger = logging.getLogger("uvicorn.error")


def _escape(text: Any) -> str:
    """Échappe les caractères HTML de manière sûre."""
    return html.escape(str(text or ""))


def _detect_kpis(text: str) -> list[dict[str, str]]:
    """Détecte les indicateurs et chiffres clés remarquables dans un texte."""
    kpis = []
    kpi_pattern = re.compile(
        r"(?:(?<=\s)|^)([-+]?\d+(?:[.,]\d+)?\s*(?:%|€|\$|k€|M€|Md€|milliards?|millions?|ans?|heures?|jours?))(?=\s|[.,;:!?)]|$)",
        re.IGNORECASE,
    )
    for line in text.split("\n"):
        line_clean = line.strip(" -*#•\t")
        if not line_clean:
            continue
        matches = list(kpi_pattern.finditer(line_clean))
        if matches:
            for m in matches[:2]:
                val = m.group(1).strip()
                label = line_clean.replace(m.group(0), "").strip(" :,;-()")
                if len(label) > 42:
                    label = label[:39] + "…"
                if label and len(kpis) < 4:
                    kpis.append({"value": val, "label": label})
    return kpis


def _inline_format(text: str) -> str:
    """Met en forme le Markdown en ligne (gras, italique, code)."""
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code class=\"inline-code\">\1</code>", text)
    text = re.sub(r"\[cite:\s*([^\]]+)\]", r"[\1]", text, flags=re.IGNORECASE)
    return text


def fallback_ai_slides(
    markdown_text: str,
    default_title: str = "Présentation",
    topic: str = "",
    model: str = "",
    created_at_str: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Découpage algorithmique respectant strictement la règle :
    MOINS DE TEXTE, PLUS DE SLIDES (10 à 18 diapositives digestes et rythmées).
    """
    sources = sources or []
    slides: list[dict[str, Any]] = []

    clean_title = (default_title or "").strip() or "Présentation cLAIr"

    # 1. Slide de couverture
    slides.append({
        "slide_type": "cover",
        "title": clean_title,
        "subtitle": topic or "Synthèse Exécutive & Perspectives Stratégiques",
        "category": "cLAIr Diaporama",
        "model": model,
        "created_at_str": created_at_str,
    })

    # Nettoyage et segmentation par titres ##
    text = re.sub(r"\[cite:\s*([^\]]+)\]", r"[\1]", markdown_text, flags=re.IGNORECASE)
    sections = re.split(r"\n(?=##\s+)", text)

    # Extraire titre H1 si présent
    first_sec = sections[0].strip()
    if first_sec.startswith("# "):
        lines = first_sec.split("\n", 1)
        h1_title = lines[0][2:].strip()
        if h1_title:
            slides[0]["title"] = h1_title
            clean_title = h1_title
        first_sec = lines[1].strip() if len(lines) > 1 else ""
        sections[0] = first_sec

    # Collecter les grandes sections
    agenda_items = []
    section_data = []

    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        if sec.startswith("## "):
            lines = sec.split("\n", 1)
            title = lines[0][3:].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            agenda_items.append(title)
            section_data.append((title, body))
        elif len(sec) > 30:
            section_data.append(("Cadrage & Contexte", sec))
            agenda_items.append("Cadrage & Contexte")

    # 2. Slide d'agenda / sommaire
    if len(agenda_items) >= 2:
        slides.append({
            "slide_type": "agenda",
            "title": "Ordre du jour & Enjeux clés",
            "subtitle": f"{len(agenda_items)} axes d'investigation majeurs",
            "category": "Vue d'ensemble",
            "agenda_items": agenda_items[:8],
        })

    # 3. Découpage fin en micro-slides (1 idée par slide)
    for sec_title, sec_body in section_data:
        # Extraire KPIs
        kpis = _detect_kpis(sec_body)
        if kpis:
            slides.append({
                "slide_type": "kpi",
                "title": f"Chiffres clés : {sec_title}",
                "subtitle": "Indicateurs majeurs observés",
                "category": sec_title,
                "kpis": kpis[:3],
                "takeaway": f"Données quantitatives de référence pour l'analyse de {sec_title.lower()}.",
            })

        # Découper par sous-parties ### ou par blocs de 2-3 puces
        sub_blocks = re.split(r"\n(?=###\s+)", sec_body)
        for sub in sub_blocks:
            sub = sub.strip()
            if not sub:
                continue

            sub_title = sec_title
            sub_content = sub
            if sub.startswith("### "):
                parts = sub.split("\n", 1)
                sub_title = parts[0][4:].strip()
                sub_content = parts[1].strip() if len(parts) > 1 else ""

            # Extraire les puces
            bullet_matches = re.findall(r"^(?:[-*•]|\d+\.)\s+(.+)$", sub_content, re.MULTILINE)
            if bullet_matches:
                # Regrouper par 2 ou 3 puces par slide maximum !
                chunk_size = 2 if len(bullet_matches) <= 4 else 3
                for b_idx in range(0, len(bullet_matches), chunk_size):
                    chunk = bullet_matches[b_idx : b_idx + chunk_size]
                    bullets_data = []
                    for b in chunk:
                        bold_match = re.match(r"^\*\*(.+?)\*\*\s*(?::|-)?\s*(.*)$", b)
                        if bold_match:
                            bullets_data.append({"bold": bold_match.group(1), "text": bold_match.group(2) or bold_match.group(1)})
                        else:
                            words = b.split(" ", 2)
                            bold_prefix = " ".join(words[:2]) if len(words) >= 2 else b
                            rest = words[2] if len(words) >= 3 else ""
                            bullets_data.append({"bold": bold_prefix, "text": rest})
                    
                    slide_num_suffix = f" (Volet {b_idx // chunk_size + 1})" if len(bullet_matches) > chunk_size else ""
                    slides.append({
                        "slide_type": "bullets",
                        "title": f"{sub_title}{slide_num_suffix}",
                        "subtitle": sec_title if sub_title != sec_title else "",
                        "category": sec_title,
                        "bullets": bullets_data,
                    })
            else:
                # Texte en paragraphes : découper par paragraphe court
                paragraphs = [p.strip() for p in sub_content.split("\n\n") if p.strip() and not p.strip().startswith("|")]
                for p_idx, p in enumerate(paragraphs[:3]):
                    if p.startswith(">"):
                        slides.append({
                            "slide_type": "quote",
                            "title": sub_title,
                            "category": sec_title,
                            "quote": p.lstrip("> ").strip(),
                            "author": sec_title,
                        })
                    else:
                        sentences = re.split(r"(?<=[.!?])\s+", p)
                        lead = sentences[0] if sentences else p
                        body = " ".join(sentences[1:3]) if len(sentences) > 1 else ""
                        slides.append({
                            "slide_type": "cards",
                            "title": sub_title,
                            "subtitle": sec_title if sub_title != sec_title else "",
                            "category": sec_title,
                            "cards": [
                                {
                                    "title": "Constat majeur",
                                    "badge": "Prioritaire",
                                    "text": lead,
                                },
                                {
                                    "title": "Implication",
                                    "badge": "Analyse",
                                    "text": body or "Approfondissement recommandé pour la prise de décision.",
                                },
                            ],
                        })

    # 4. Slide de conclusion finale
    slides.append({
        "slide_type": "conclusion",
        "title": "Synthèse & Décisions clés",
        "subtitle": "Enseignements majeurs à retenir",
        "category": "Conclusion",
        "takeaways": [
            f"Consolidation des orientations stratégiques sur « {clean_title} ».",
            "Priorisation des actions à fort impact identifiées au fil de l'investigation.",
            "Accompagnement continu et suivi des indicateurs clés de performance.",
        ],
    })

    # 5. Slide des sources vérifiées
    valid_sources = [s for s in sources if is_document(s)]
    if valid_sources:
        slides.append({
            "slide_type": "sources",
            "title": "Sources vérifiées & Références",
            "subtitle": f"{len(valid_sources)} documents documentaires certifiés",
            "category": "Grounding cLAIr",
            "sources": valid_sources[:12],
        })

    return slides


# Alias pour rétrocompatibilité
markdown_to_slides = fallback_ai_slides


async def generate_ai_presentation_slides(
    settings: Any = None,
    content: str = "",
    title: str = "",
    topic: str = "",
    model: str = "",
    created_at_str: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Génère un jeu de diapositives exécutives par IA via un LLM.
    Enforce la consigne utilisateur : MOINS DE TEXTE PAR SLIDE, MAIS PLUS DE SLIDES (10 à 18 slides).
    """
    sources = sources or []
    clean_title = (title or "").strip() or "Présentation cLAIr"
    clean_topic = (topic or "").strip() or clean_title

    raw_key = getattr(settings, "llm_api_key", None)
    key = ""
    if hasattr(raw_key, "get_secret_value"):
        key = raw_key.get_secret_value().strip()
    elif isinstance(raw_key, str):
        key = raw_key.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
        key = key[1:-1].strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()

    if getattr(settings, "demo_mode", False) or not key:
        return fallback_ai_slides(content, clean_title, clean_topic, model, created_at_str, sources)

    configured_pres_model = getattr(settings, "presentation_model", "").strip() if settings else ""
    default_model = getattr(settings, "default_model", "openai/gpt-4o-mini") if settings else "openai/gpt-4o-mini"
    is_virtual_label = model in ("DeepSearch", "cLAIr Apprendre", "Sonar Deep Research", "")

    if configured_pres_model:
        chosen_model = configured_pres_model
    elif model and not is_virtual_label:
        chosen_model = model
    else:
        chosen_model = default_model

    system_prompt = (
        "Tu es un expert mondial en conception de présentations exécutives (style Apple Keynote / McKinsey).\n"
        "Ta mission : transformer le contenu fourni en un diaporama de présentation percutant, aéré et mémorable.\n\n"
        "RÈGLES ABSOLUES DE CONCEPTION (TRÈS STRICT) :\n"
        "1. MOINS DE TEXTE, PLUS DE SLIDES :\n"
        "   - Interdiction formelle de longs paragraphes ou de blocs de texte indigestes.\n"
        "   - 1 seule idée forte par diapositive, lisible en 5 secondes chrono.\n"
        "   - Génère impérativement entre 10 et 16 diapositives bien découpées.\n"
        "2. TITRES D'ACTION :\n"
        "   - Chaque titre doit exprimer une conclusion ou un message fort (ex: '+35% de croissance d'ici 2030' plutôt que 'Contexte').\n"
        "3. FORMATS VARIÉS ET DYNAMIQUES :\n"
        "   Alterne les types de slides :\n"
        "   - 'kpi' : 1 à 3 chiffres chocs avec libellé court.\n"
        "   - 'bullets' : 2 à 4 puces très courtes (maximum 8 à 12 mots par puce, avec un mot-clé fort au début).\n"
        "   - 'cards' : 2 ou 3 cartes côte à côte (ex: piliers, comparaisons, étapes).\n"
        "   - 'quote' : une citation ou une phrase clé marquante.\n"
        "   - 'conclusion' : 3 points clés à retenir.\n\n"
        "Retourne EXCLUSIVEMENT un objet JSON valide avec cette structure stricte :\n"
        "{\n"
        f'  "title": "{clean_title}",\n'
        f'  "subtitle": "{clean_topic}",\n'
        '  "slides": [\n'
        '    {\n'
        '      "slide_type": "cover",\n'
        f'      "title": "{clean_title}",\n'
        f'      "subtitle": "{clean_topic}",\n'
        '      "category": "Présentation Exécutive"\n'
        '    },\n'
        '    {\n'
        '      "slide_type": "agenda",\n'
        '      "title": "Ordre du jour & Enjeux clés",\n'
        '      "category": "Sommaire",\n'
        '      "agenda_items": ["Axe 1", "Axe 2", "Axe 3", "Axe 4"]\n'
        '    },\n'
        '    {\n'
        '      "slide_type": "kpi",\n'
        '      "title": "Titre orienté chiffre ou impact",\n'
        '      "category": "Indicateurs majeurs",\n'
        '      "kpis": [\n'
        '        {"value": "+35%", "label": "Croissance attendue"},\n'
        '        {"value": "94%", "label": "Taux d\'adoption"}\n'
        '      ],\n'
        '      "takeaway": "Phrase courte de mise en perspective."\n'
        '    },\n'
        '    {\n'
        '      "slide_type": "bullets",\n'
        '      "title": "Titre d\'action percutant",\n'
        '      "category": "Nom du volet",\n'
        '      "bullets": [\n'
        '        {"bold": "Mot-clé 1", "text": "Explication brève en 8 mots."},\n'
        '        {"bold": "Mot-clé 2", "text": "Autre point très concis."}\n'
        '      ]\n'
        '    },\n'
        '    {\n'
        '      "slide_type": "cards",\n'
        '      "title": "Piliers d\'action stratégiques",\n'
        '      "category": "Stratégie",\n'
        '      "cards": [\n'
        '        {"title": "Pilier 1", "badge": "Prioritaire", "text": "Court descriptif d\'action."},\n'
        '        {"title": "Pilier 2", "badge": "Horizon 2030", "text": "Court descriptif d\'action."}\n'
        '      ]\n'
        '    },\n'
        '    {\n'
        '      "slide_type": "quote",\n'
        '      "title": "Enseignement majeur",\n'
        '      "category": "Vision",\n'
        '      "quote": "Phrase directrice à retenir.",\n'
        '      "author": "Analyse cLAIr"\n'
        '    },\n'
        '    {\n'
        '      "slide_type": "conclusion",\n'
        '      "title": "Synthèse & Décisions à retenir",\n'
        '      "category": "Conclusion",\n'
        '      "takeaways": [\n'
        '        "Premier enseignement stratégique.",\n'
        '        "Deuxième enseignement stratégique.",\n'
        '        "Troisième enseignement stratégique."\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    sample_context = content[:9000] if content else f"Sujet : {clean_topic}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Voici le contenu à synthétiser en diaporama (beaucoup de slides courtes) :\n\n{sample_context}"},
    ]

    _logger.info("Lancement de la génération de présentation IA avec le modèle : %s", chosen_model)
    try:
        timeout = getattr(settings, "llm_timeout", 45.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            resp = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": chosen_model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.2,
                    "max_tokens": 3000,
                },
            )
            if resp.status_code in (400, 404, 422):
                alt_model = getattr(settings, "default_model", "")
                if alt_model and alt_model != chosen_model:
                    _logger.warning("Modèle %s non pris en charge (%d). Repli vers alt_model : %s", chosen_model, resp.status_code, alt_model)
                    resp = await client.post(
                        settings.llm_base_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={
                            "model": alt_model,
                            "messages": messages,
                            "stream": False,
                            "temperature": 0.2,
                            "max_tokens": 3000,
                        },
                    )

            if resp.status_code == 200:
                payload = resp.json()
                raw_text = payload["choices"][0]["message"]["content"]
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
                match = re.search(r"\{[\s\S]*\}", cleaned)
                data = json.loads(match.group(0) if match else cleaned)

                raw_slides = data.get("slides", [])
                if isinstance(raw_slides, list) and len(raw_slides) >= 5:
                    validated_slides: list[dict[str, Any]] = []
                    for s in raw_slides:
                        if not isinstance(s, dict):
                            continue
                        stype = s.get("slide_type", "bullets")
                        if stype == "cover":
                            s["model"] = chosen_model
                            s["created_at_str"] = created_at_str
                        validated_slides.append(s)

                    valid_sources = [src for src in sources if is_document(src)]
                    if valid_sources:
                        validated_slides.append({
                            "slide_type": "sources",
                            "title": "Sources vérifiées & Références",
                            "subtitle": f"{len(valid_sources)} documents documentaires certifiés",
                            "category": "Grounding cLAIr",
                            "sources": valid_sources[:12],
                        })
                    _logger.info("Présentation IA générée avec succès (%d slides reçues via %s)", len(validated_slides), chosen_model)
                    return validated_slides
            else:
                _logger.warning("Échec HTTP du modèle IA %s (statut %d) : %s", chosen_model, resp.status_code, resp.text[:200])

    except Exception as exc:
        _logger.warning("Exception lors de la génération de slides par IA (%s) : %s", chosen_model, exc)

    return fallback_ai_slides(content, clean_title, clean_topic, model, created_at_str, sources)


def render_slide_inner_html(slide: dict[str, Any], index: int, total_slides: int) -> str:
    """Rend le contenu HTML interne d'une diapositive aérée et sans surplus de texte."""
    stype = slide.get("slide_type", "bullets")
    stitle = _escape(slide.get("title") or f"Diapositive {index}")
    ssub = _escape(slide.get("subtitle") or "")
    scat = _escape(slide.get("category") or "cLAIr")

    if stype == "cover":
        model_display = _escape(slide.get("model") or "Assistant cLAIr")
        date_display = _escape(slide.get("created_at_str") or "Session récente")
        return f"""
        <div class="slide-cover-inner">
            <div class="cover-badge-row">
                <span class="cover-pill-brand">cLAIr · Présentation Exécutive</span>
                <span class="cover-pill-model">{model_display}</span>
                <span class="cover-pill-date">{date_display}</span>
            </div>
            <h1 class="cover-title">{stitle}</h1>
            {f'<p class="cover-subtitle">{ssub}</p>' if ssub else ''}
            <div class="cover-footer-action">
                <button type="button" class="btn-start-presentation" onclick="PresentationApp.nextSlide()">
                    <span>Lancer la présentation</span>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                </button>
                <div class="cover-shortcuts-hint">
                    <span><strong>[←] [→]</strong> ou <strong>[Espace]</strong></span>
                    <span>Plein écran : <strong>[F]</strong></span>
                    <span>Mosaïque : <strong>[G]</strong></span>
                </div>
            </div>
        </div>
        """

    header_html = f"""
    <header class="slide-header">
        <div class="slide-header-top">
            <span class="slide-category-tag">{scat}</span>
            <span class="slide-number-tag">{index} / {total_slides}</span>
        </div>
        <h2 class="slide-title">{stitle}</h2>
        {f'<p class="slide-subtitle">{ssub}</p>' if ssub else ''}
        <div class="slide-title-bar"></div>
    </header>
    """

    body_content = ""

    if stype == "agenda":
        items = slide.get("agenda_items") or []
        cards_html = []
        for a_idx, itm in enumerate(items[:8], 1):
            cards_html.append(
                f'<div class="agenda-card">'
                f'<span class="agenda-number">{a_idx:02d}</span>'
                f'<span class="agenda-text">{_escape(itm)}</span>'
                f'</div>'
            )
        body_content = f'<div class="slide-agenda-grid">{"".join(cards_html)}</div>'

    elif stype == "kpi":
        kpis = slide.get("kpis") or []
        takeaway = _escape(slide.get("takeaway") or "")
        kpis_html = []
        for k in kpis[:3]:
            kpis_html.append(
                f'<div class="kpi-card-hero">'
                f'<span class="kpi-hero-value">{_escape(k.get("value"))}</span>'
                f'<span class="kpi-hero-label">{_escape(k.get("label"))}</span>'
                f'</div>'
            )
        body_content = f"""
        <div class="kpi-hero-grid">{"".join(kpis_html)}</div>
        {f'<div class="kpi-takeaway-bar"><span class="takeaway-badge">Point Clé</span><p>{takeaway}</p></div>' if takeaway else ''}
        """

    elif stype == "cards":
        cards = slide.get("cards") or []
        card_items = []
        for c in cards[:3]:
            badge = _escape(c.get("badge") or "Priorité")
            ctitle = _escape(c.get("title") or "")
            ctext = _escape(c.get("text") or "")
            card_items.append(
                f'<div class="feature-card">'
                f'<div class="feature-card-header">'
                f'<strong>{ctitle}</strong>'
                f'<span class="feature-card-badge">{badge}</span>'
                f'</div>'
                f'<p class="feature-card-text">{ctext}</p>'
                f'</div>'
            )
        body_content = f'<div class="feature-cards-grid">{"".join(card_items)}</div>'

    elif stype == "quote":
        q_text = _escape(slide.get("quote") or "")
        author = _escape(slide.get("author") or "cLAIr Synthèse")
        body_content = f"""
        <div class="quote-slide-wrapper">
            <span class="quote-big-mark">“</span>
            <blockquote class="quote-slide-text">{q_text}</blockquote>
            <p class="quote-slide-author">— {author}</p>
        </div>
        """

    elif stype == "conclusion":
        takeaways = slide.get("takeaways") or []
        items_html = []
        for t in takeaways[:4]:
            items_html.append(
                f'<div class="conclusion-item">'
                f'<span class="conclusion-check">✓</span>'
                f'<p>{_escape(t)}</p>'
                f'</div>'
            )
        body_content = f'<div class="conclusion-list">{"".join(items_html)}</div>'

    elif stype == "sources":
        sources_list = slide.get("sources") or []
        cards_html = []
        for idx, src in enumerate(sources_list[:12], 1):
            domain = extract_domain(src.get("url", ""))
            st = src.get("title") or domain or f"Source {idx}"
            surl = src.get("url", "")
            escaped_url = _escape(surl)
            link_open = f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer" class="source-card-link">' if surl else '<div class="source-card-link">'
            link_close = "</a>" if surl else "</div>"
            cards_html.append(
                f'{link_open}'
                f'<span class="source-badge-num">[{idx}]</span>'
                f'<div class="source-card-info">'
                f'<strong>{_escape(st)}</strong>'
                f'<small>{_escape(domain)}</small>'
                f'</div>'
                f'{link_close}'
            )
        body_content = f'<div class="slide-sources-grid">{"".join(cards_html)}</div>'

    else:
        bullets = slide.get("bullets") or []
        if bullets and isinstance(bullets[0], dict):
            b_items = []
            for b in bullets[:4]:
                bold = _escape(b.get("bold") or "")
                txt = _escape(b.get("text") or "")
                b_items.append(
                    f'<li class="bullet-row-item">'
                    f'<span class="bullet-row-dot"></span>'
                    f'<div class="bullet-row-content">'
                    f'{f"<strong>{bold}</strong> · " if bold else ""}{txt}'
                    f'</div>'
                    f'</li>'
                )
            body_content = f'<ul class="bullet-row-list">{"".join(b_items)}</ul>'
        else:
            raw_text = slide.get("html_content") or ""
            body_content = f'<div class="slide-simple-content">{raw_text}</div>'

    footer_html = f"""
    <footer class="slide-footer">
        <span class="slide-footer-left">cLAIr · Diaporama Exécutif</span>
        <span class="slide-footer-center">{stitle}</span>
        <span class="slide-footer-right">{index} / {total_slides}</span>
    </footer>
    """

    return f"""
    {header_html}
    <main class="slide-body">
        {body_content}
    </main>
    {footer_html}
    """


def generate_presentation_html(
    title: str,
    slides: list[dict[str, Any]],
    topic: str = "",
    model: str = "",
    created_at_str: str = "",
) -> str:
    """Assemble le document HTML complet et autonome avec styles et scripts PowerPoint."""
    clean_title = (title or "").strip() or "Présentation cLAIr"
    escaped_title = _escape(clean_title)
    total_slides = max(1, len(slides))

    slides_markup = []
    sorter_markup = []

    for index, slide in enumerate(slides, 1):
        stype = slide.get("slide_type", "bullets")
        stitle = _escape(slide.get("title") or f"Diapositive {index}")
        inner_content = render_slide_inner_html(slide, index, total_slides)

        active_class = " is-active" if index == 1 else ""
        slides_markup.append(
            f'<article class="slide slide-{stype}{active_class}" id="slide-{index}" data-slide-index="{index}">\n'
            f'{inner_content}\n'
            f'</article>'
        )

        sorter_markup.append(
            f'<div class="sorter-thumbnail{" is-active" if index == 1 else ""}" onclick="PresentationApp.goToSlide({index})" data-thumb-index="{index}">'
            f'<div class="thumb-header"><span class="thumb-number">{index:02d}</span><span class="thumb-type">{stype}</span></div>'
            f'<strong class="thumb-title">{stitle}</strong>'
            f'</div>'
        )

    slides_rendered = "\n".join(slides_markup)
    sorter_rendered = "\n".join(sorter_markup)

    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escaped_title} — Présentation PowerPoint cLAIr</title>
    <style>
        :root {{
            --bg-stage: #0a0f1d;
            --bg-slide: #111827;
            --bg-card: #1f2937;
            --border-slide: rgba(255, 255, 255, 0.08);
            --border-card: rgba(255, 255, 255, 0.12);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-faint: #64748b;
            --accent-primary: #ea580c; /* Orange PowerPoint */
            --accent-glow: rgba(234, 88, 12, 0.28);
            --accent-secondary: #6366f1;
            --kpi-bg: rgba(234, 88, 12, 0.12);
            --kpi-border: rgba(234, 88, 12, 0.35);
            --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            --shadow-slide: 0 25px 60px -15px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.08);
        }}

        [data-theme="light"] {{
            --bg-stage: #f1f5f9;
            --bg-slide: #ffffff;
            --bg-card: #f8fafc;
            --border-slide: #e2e8f0;
            --border-card: #e2e8f0;
            --text-main: #0f172a;
            --text-muted: #475569;
            --text-faint: #94a3b8;
            --accent-primary: #ea580c;
            --accent-glow: rgba(234, 88, 12, 0.18);
            --accent-secondary: #4f46e5;
            --kpi-bg: #fff7ed;
            --kpi-border: #fed7aa;
            --shadow-slide: 0 20px 45px -10px rgba(15, 23, 42, 0.15), 0 0 0 1px #e2e8f0;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        html, body {{
            width: 100%;
            height: 100%;
            overflow: hidden;
            background: var(--bg-stage);
            color: var(--text-main);
            font-family: var(--font-sans);
            user-select: none;
            -webkit-font-smoothing: antialiased;
        }}

        .presentation-progress-bar {{
            position: fixed;
            top: 0;
            left: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--accent-secondary), var(--accent-primary));
            transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            z-index: 1000;
        }}

        .presentation-stage {{
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 30px 40px 90px 40px;
        }}

        .slide {{
            display: none;
            position: relative;
            width: 100%;
            max-width: 1200px;
            aspect-ratio: 16 / 9;
            background: var(--bg-slide);
            border: 1px solid var(--border-slide);
            border-radius: 18px;
            box-shadow: var(--shadow-slide);
            padding: 44px 54px;
            flex-direction: column;
            justify-content: space-between;
            overflow: hidden;
            animation: slideFadeIn 0.2s ease-out;
        }}

        .slide.is-active {{
            display: flex;
        }}

        @keyframes slideFadeIn {{
            from {{
                opacity: 0;
                transform: scale(0.985) translateY(4px);
            }}
            to {{
                opacity: 1;
                transform: scale(1) translateY(0);
            }}
        }}

        .slide-cover {{
            background: radial-gradient(circle at 85% 15%, rgba(234, 88, 12, 0.18), transparent 50%),
                        radial-gradient(circle at 15% 85%, rgba(99, 102, 241, 0.18), transparent 50%),
                        var(--bg-slide);
            justify-content: center;
            align-items: flex-start;
        }}

        .slide-cover-inner {{
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}

        .cover-badge-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}

        .cover-pill-brand {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            padding: 4px 12px;
            border-radius: 9999px;
            background: var(--accent-primary);
            color: #ffffff;
        }}

        .cover-pill-model, .cover-pill-date {{
            font-size: 11.5px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 9999px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            color: var(--text-muted);
        }}

        .cover-title {{
            font-size: 42px;
            font-weight: 800;
            line-height: 1.15;
            letter-spacing: -0.025em;
            color: var(--text-main);
        }}

        .cover-subtitle {{
            font-size: 19px;
            line-height: 1.5;
            color: var(--text-muted);
        }}

        .cover-footer-action {{
            display: flex;
            align-items: center;
            gap: 24px;
            margin-top: 14px;
        }}

        .btn-start-presentation {{
            display: inline-flex;
            align-items: center;
            gap: 10px;
            background: var(--accent-primary);
            color: #ffffff;
            font-size: 14px;
            font-weight: 700;
            padding: 12px 22px;
            border-radius: 10px;
            border: none;
            cursor: pointer;
            box-shadow: 0 4px 14px var(--accent-glow);
            transition: all 0.15s ease;
        }}

        .btn-start-presentation:hover {{
            transform: translateY(-1px);
            filter: brightness(1.08);
            box-shadow: 0 6px 20px var(--accent-glow);
        }}

        .cover-shortcuts-hint {{
            display: flex;
            align-items: center;
            gap: 14px;
            font-size: 11.5px;
            color: var(--text-faint);
        }}

        .cover-shortcuts-hint strong {{
            color: var(--text-muted);
            font-family: var(--font-mono);
        }}

        .slide-header {{
            display: flex;
            flex-direction: column;
            gap: 4px;
            margin-bottom: 12px;
        }}

        .slide-header-top {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .slide-category-tag {{
            font-size: 10.5px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--accent-primary);
        }}

        .slide-number-tag {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-faint);
            font-family: var(--font-mono);
        }}

        .slide-title {{
            font-size: 28px;
            font-weight: 800;
            color: var(--text-main);
            letter-spacing: -0.015em;
            line-height: 1.25;
        }}

        .slide-subtitle {{
            font-size: 14px;
            color: var(--text-muted);
            line-height: 1.4;
        }}

        .slide-title-bar {{
            width: 44px;
            height: 3px;
            background: var(--accent-primary);
            border-radius: 2px;
            margin-top: 6px;
        }}

        .slide-body {{
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 16px;
        }}

        .bullet-row-list {{
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}

        .bullet-row-item {{
            display: flex;
            align-items: center;
            gap: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 16px 20px;
            transition: transform 0.15s ease;
        }}

        .bullet-row-item:hover {{
            transform: translateX(4px);
            border-color: var(--accent-primary);
        }}

        .bullet-row-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent-primary);
            box-shadow: 0 0 10px var(--accent-glow);
            flex-shrink: 0;
        }}

        .bullet-row-content {{
            font-size: 17px;
            line-height: 1.5;
            color: var(--text-main);
        }}

        .bullet-row-content strong {{
            color: var(--accent-primary);
        }}

        .kpi-hero-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 20px;
        }}

        .kpi-card-hero {{
            background: var(--kpi-bg);
            border: 2px solid var(--kpi-border);
            border-radius: 16px;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            text-align: center;
        }}

        .kpi-hero-value {{
            font-size: 46px;
            font-weight: 800;
            color: var(--accent-primary);
            letter-spacing: -0.03em;
            line-height: 1;
        }}

        .kpi-hero-label {{
            font-size: 15px;
            font-weight: 600;
            color: var(--text-muted);
            line-height: 1.4;
        }}

        .kpi-takeaway-bar {{
            display: flex;
            align-items: center;
            gap: 14px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 14px 18px;
            font-size: 15px;
        }}

        .takeaway-badge {{
            font-size: 10.5px;
            font-weight: 800;
            text-transform: uppercase;
            padding: 3px 8px;
            border-radius: 6px;
            background: var(--accent-secondary);
            color: #ffffff;
            flex-shrink: 0;
        }}

        .feature-cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 18px;
        }}

        .feature-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 14px;
            padding: 22px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}

        .feature-card:hover {{
            border-color: var(--accent-primary);
        }}

        .feature-card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .feature-card-header strong {{
            font-size: 17px;
            color: var(--text-main);
        }}

        .feature-card-badge {{
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 3px 8px;
            border-radius: 6px;
            background: var(--accent-primary);
            color: #ffffff;
        }}

        .feature-card-text {{
            font-size: 15px;
            line-height: 1.55;
            color: var(--text-muted);
        }}

        .quote-slide-wrapper {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 20px 40px;
            gap: 14px;
        }}

        .quote-big-mark {{
            font-size: 64px;
            line-height: 0;
            color: var(--accent-primary);
            opacity: 0.35;
        }}

        .quote-slide-text {{
            font-size: 24px;
            font-weight: 600;
            font-style: italic;
            line-height: 1.45;
            color: var(--text-main);
            max-width: 800px;
        }}

        .quote-slide-author {{
            font-size: 15px;
            color: var(--text-faint);
            font-weight: 600;
        }}

        .conclusion-list {{
            display: flex;
            flex-direction: column;
            gap: 14px;
        }}

        .conclusion-item {{
            display: flex;
            align-items: center;
            gap: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 18px 22px;
        }}

        .conclusion-check {{
            width: 28px;
            height: 28px;
            border-radius: 50%;
            background: #10b981;
            color: #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 15px;
            flex-shrink: 0;
        }}

        .conclusion-item p {{
            font-size: 16.5px;
            font-weight: 600;
            color: var(--text-main);
            line-height: 1.45;
        }}

        .slide-agenda-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 14px;
        }}

        .agenda-card {{
            display: flex;
            align-items: center;
            gap: 14px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 12px;
            padding: 16px 20px;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .agenda-card:hover {{
            border-color: var(--accent-primary);
            transform: translateX(4px);
        }}

        .agenda-number {{
            font-size: 20px;
            font-weight: 800;
            color: var(--accent-primary);
            font-family: var(--font-mono);
        }}

        .agenda-text {{
            font-size: 15px;
            font-weight: 600;
            color: var(--text-main);
        }}

        .slide-sources-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
            gap: 12px;
        }}

        .source-card-link {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 10px;
            padding: 12px 14px;
            text-decoration: none;
            color: inherit;
            transition: all 0.15s ease;
        }}

        .source-card-link:hover {{
            border-color: var(--accent-secondary);
            transform: translateY(-1px);
        }}

        .source-badge-num {{
            font-size: 11px;
            font-weight: 800;
            color: var(--accent-secondary);
            background: rgba(99, 102, 241, 0.15);
            padding: 2px 6px;
            border-radius: 4px;
        }}

        .source-card-info {{
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
        }}

        .source-card-info strong {{
            font-size: 12px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .source-card-info small {{
            font-size: 10.5px;
            color: var(--text-faint);
        }}

        .slide-footer {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-top: 14px;
            border-top: 1px solid var(--border-slide);
            font-size: 11px;
            color: var(--text-faint);
        }}

        .presentation-toolbar {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            border-radius: 9999px;
            background: rgba(17, 24, 39, 0.88);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
            z-index: 1000;
        }}

        [data-theme="light"] .presentation-toolbar {{
            background: rgba(255, 255, 255, 0.92);
            border-color: #cbd5e1;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
        }}

        .toolbar-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            background: transparent;
            color: var(--text-main);
            border: none;
            padding: 6px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }}

        .toolbar-btn:hover {{
            background: var(--bg-card);
            color: var(--accent-primary);
        }}

        .toolbar-counter {{
            font-size: 12px;
            font-weight: 700;
            font-family: var(--font-mono);
            padding: 4px 8px;
            border-radius: 6px;
            cursor: pointer;
            color: var(--accent-primary);
        }}

        .toolbar-counter:hover {{
            background: var(--kpi-bg);
        }}

        .toolbar-sep {{
            width: 1px;
            height: 18px;
            background: var(--border-card);
            margin: 0 2px;
        }}

        .sorter-overlay {{
            position: fixed;
            inset: 0;
            background: rgba(10, 15, 29, 0.94);
            backdrop-filter: blur(14px);
            z-index: 2000;
            padding: 40px;
            display: none;
            flex-direction: column;
            gap: 20px;
            overflow-y: auto;
        }}

        .sorter-overlay.is-open {{
            display: flex;
        }}

        .sorter-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .sorter-header h3 {{
            font-size: 20px;
            font-weight: 800;
        }}

        .sorter-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
            gap: 16px;
        }}

        .sorter-thumbnail {{
            aspect-ratio: 16 / 9;
            background: var(--bg-slide);
            border: 2px solid var(--border-card);
            border-radius: 10px;
            padding: 14px;
            cursor: pointer;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.15s ease;
        }}

        .sorter-thumbnail:hover, .sorter-thumbnail.is-active {{
            border-color: var(--accent-primary);
            box-shadow: 0 6px 20px var(--accent-glow);
            transform: translateY(-2px);
        }}

        .thumb-header {{
            display: flex;
            justify-content: space-between;
            font-size: 10.5px;
            color: var(--text-faint);
        }}

        .thumb-number {{
            font-weight: 800;
            color: var(--accent-primary);
            font-family: var(--font-mono);
        }}

        .thumb-title {{
            font-size: 13px;
            line-height: 1.35;
            color: var(--text-main);
        }}

        @media print {{
            @page {{
                size: landscape;
                margin: 0;
            }}

            html, body {{
                background: #ffffff !important;
                color: #0f172a !important;
                width: 100% !important;
                height: auto !important;
                overflow: visible !important;
            }}

            .presentation-progress-bar,
            .presentation-toolbar,
            .sorter-overlay {{
                display: none !important;
            }}

            .presentation-stage {{
                position: static !important;
                display: block !important;
                padding: 0 !important;
            }}

            .slide {{
                display: flex !important;
                width: 100vw !important;
                height: 100vh !important;
                max-width: none !important;
                aspect-ratio: auto !important;
                border-radius: 0 !important;
                border: none !important;
                box-shadow: none !important;
                page-break-after: always !important;
                break-after: page !important;
                padding: 48px 64px !important;
                background: #ffffff !important;
                color: #0f172a !important;
            }}

            .slide-cover {{
                background: #ffffff !important;
            }}

            .btn-start-presentation, .cover-shortcuts-hint {{
                display: none !important;
            }}
        }}

        @media (max-width: 800px) {{
            .presentation-stage {{
                padding: 10px 10px 80px 10px;
            }}

            .slide {{
                aspect-ratio: auto;
                height: calc(100vh - 100px);
                padding: 24px 20px;
                border-radius: 10px;
            }}

            .cover-title {{
                font-size: 26px;
            }}

            .slide-title {{
                font-size: 20px;
            }}

            .slide-agenda-grid {{
                grid-template-columns: 1fr;
            }}

            .toolbar-text-btn span {{
                display: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="presentation-progress-bar" id="progressBar" style="width: {(1 / total_slides) * 100}%;"></div>

    <div class="presentation-stage" id="presentationStage">
        {slides_rendered}
    </div>

    <nav class="presentation-toolbar" aria-label="Contrôles de présentation">
        <button type="button" class="toolbar-btn" onclick="PresentationApp.prevSlide()" title="Diapositive précédente (←)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <span class="toolbar-counter" id="slideCounter" onclick="PresentationApp.toggleSorter()" title="Afficher la mosaïque des diapositives (G)">1 / {total_slides}</span>
        <button type="button" class="toolbar-btn" onclick="PresentationApp.nextSlide()" title="Diapositive suivante (→)">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>

        <span class="toolbar-sep"></span>

        <button type="button" class="toolbar-btn toolbar-text-btn" onclick="PresentationApp.toggleSorter()" title="Vue Mosaïque de toutes les diapositives (G)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            <span>Mosaïque</span>
        </button>

        <button type="button" class="toolbar-btn toolbar-text-btn" onclick="PresentationApp.toggleTheme()" title="Basculer thème Sombre / Clair (T)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
        </button>

        <button type="button" class="toolbar-btn toolbar-text-btn" onclick="PresentationApp.regenerate()" title="Régénérer une nouvelle version par IA (Recharger)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
            <span>Régénérer</span>
        </button>

        <span class="toolbar-sep"></span>

        <button type="button" class="toolbar-btn toolbar-text-btn" onclick="window.print()" title="Imprimer ou enregistrer au format PDF 16:9 paysage (P)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            <span>Imprimer PDF</span>
        </button>

        <button type="button" class="toolbar-btn" onclick="PresentationApp.downloadSelf()" title="Télécharger le fichier de présentation HTML autonome">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>

        <button type="button" class="toolbar-btn" onclick="PresentationApp.toggleFullscreen()" title="Mode plein écran (F)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
        </button>
    </nav>

    <div class="sorter-overlay" id="sorterOverlay" role="dialog" aria-modal="true">
        <div class="sorter-header">
            <h3>Mosaïque des Diapositives ({total_slides})</h3>
            <button type="button" class="toolbar-btn" onclick="PresentationApp.toggleSorter()" title="Fermer la mosaïque (Échap)">✕ Fermer</button>
        </div>
        <div class="sorter-grid">
            {sorter_rendered}
        </div>
    </div>

    <script>
        const PresentationApp = (function() {{
            let current = 1;
            const total = {total_slides};

            function updateUI() {{
                document.querySelectorAll('.slide').forEach((el, idx) => {{
                    if (idx + 1 === current) {{
                        el.classList.add('is-active');
                    }} else {{
                        el.classList.remove('is-active');
                    }}
                }});

                document.querySelectorAll('.sorter-thumbnail').forEach((el, idx) => {{
                    if (idx + 1 === current) {{
                        el.classList.add('is-active');
                    }} else {{
                        el.classList.remove('is-active');
                    }}
                }});

                const counter = document.getElementById('slideCounter');
                if (counter) counter.textContent = current + ' / ' + total;

                const bar = document.getElementById('progressBar');
                if (bar) bar.style.width = ((current / total) * 100) + '%';

                try {{
                    window.location.hash = 'slide-' + current;
                }} catch (e) {{}}
            }}

            function goToSlide(n) {{
                if (n < 1) n = 1;
                if (n > total) n = total;
                current = n;
                updateUI();
                closeSorter();
            }}

            function nextSlide() {{
                if (current < total) {{
                    current++;
                    updateUI();
                }}
            }}

            function prevSlide() {{
                if (current > 1) {{
                    current--;
                    updateUI();
                }}
            }}

            function toggleSorter() {{
                const overlay = document.getElementById('sorterOverlay');
                if (overlay) overlay.classList.toggle('is-open');
            }}

            function closeSorter() {{
                const overlay = document.getElementById('sorterOverlay');
                if (overlay) overlay.classList.remove('is-open');
            }}

            function toggleTheme() {{
                const html = document.documentElement;
                const next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
                html.setAttribute('data-theme', next);
                try {{
                    localStorage.setItem('clair-presentation-theme', next);
                }} catch (e) {{}}
            }}

            function toggleFullscreen() {{
                if (!document.fullscreenElement) {{
                    document.documentElement.requestFullscreen().catch(() => {{}});
                }} else {{
                    if (document.exitFullscreen) document.exitFullscreen();
                }}
            }}

            function downloadSelf() {{
                const blob = new Blob([document.documentElement.outerHTML], {{ type: 'text/html;charset=utf-8' }});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = '{slugify(clean_title)[:40] or "presentation"}-slides.html';
                a.click();
                URL.revokeObjectURL(a.href);
            }}

            window.addEventListener('keydown', function(e) {{
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

                switch (e.key) {{
                    case 'ArrowRight':
                    case 'ArrowDown':
                    case 'PageDown':
                    case ' ':
                    case 'Enter':
                        e.preventDefault();
                        nextSlide();
                        break;
                    case 'ArrowLeft':
                    case 'ArrowUp':
                    case 'PageUp':
                    case 'Backspace':
                        e.preventDefault();
                        prevSlide();
                        break;
                    case 'Home':
                        e.preventDefault();
                        goToSlide(1);
                        break;
                    case 'End':
                        e.preventDefault();
                        goToSlide(total);
                        break;
                    case 'f':
                    case 'F':
                        e.preventDefault();
                        toggleFullscreen();
                        break;
                    case 'g':
                    case 'G':
                    case 'o':
                    case 'O':
                        e.preventDefault();
                        toggleSorter();
                        break;
                    case 't':
                    case 'T':
                        e.preventDefault();
                        toggleTheme();
                        break;
                    case 'p':
                    case 'P':
                        if (!e.ctrlKey && !e.metaKey) {{
                            e.preventDefault();
                            window.print();
                        }}
                        break;
                    case 'Escape':
                        closeSorter();
                        break;
                }}
            }});

            let touchStartX = 0;
            window.addEventListener('touchstart', e => {{
                touchStartX = e.changedTouches[0].screenX;
            }}, {{ passive: true }});

            window.addEventListener('touchend', e => {{
                const touchEndX = e.changedTouches[0].screenX;
                const diff = touchEndX - touchStartX;
                if (Math.abs(diff) > 50) {{
                    if (diff < 0) nextSlide();
                    else prevSlide();
                }}
            }}, {{ passive: true }});

            window.addEventListener('DOMContentLoaded', () => {{
                try {{
                    const savedTheme = localStorage.getItem('clair-presentation-theme');
                    if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
                }} catch (e) {{}}

                const m = window.location.hash.match(/slide-(\\d+)/);
                if (m && m[1]) {{
                    goToSlide(parseInt(m[1], 10));
                }} else {{
                    updateUI();
                }}
            }});

            function regenerate() {{
                const url = new URL(window.location.href);
                url.searchParams.set("r", Date.now().toString());
                window.location.href = url.toString();
            }}

            return {{
                nextSlide,
                prevSlide,
                goToSlide,
                toggleSorter,
                closeSorter,
                toggleTheme,
                toggleFullscreen,
                downloadSelf,
                regenerate,
            }};
        }})();
    </script>
</body>
</html>
"""


async def generate_chat_presentation_html(
    settings: Any = None,
    title: str = "",
    messages: list[dict[str, Any]] | None = None,
    scope: str = "turn",
    topic: str = "",
    model: str = "",
    created_at_str: str = "",
    summary: str = "",
) -> str:
    """Génère la présentation PowerPoint par IA pour un échange ciblé ou une discussion."""
    messages = messages or []
    clean_title = (title or "").strip() or "Présentation cLAIr"
    is_turn_scope = scope == "turn"

    all_sources: list[dict[str, Any]] = []
    for msg in messages:
        for s in (msg.get("sources") or []):
            if is_document(s) and s not in all_sources:
                all_sources.append(s)

    effective_model = model
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("model"):
            effective_model = msg["model"]
            break

    if is_turn_scope:
        user_msg = next((m for m in messages if m.get("role") == "user"), None)
        asst_msg = next((m for m in messages if m.get("role") == "assistant"), None)
        if not asst_msg and messages:
            asst_msg = messages[-1]

        user_content = user_msg.get("content", "").strip() if user_msg else (topic or clean_title)
        asst_content = asst_msg.get("content", "").strip() if asst_msg else ""

        full_prompt_content = f"Question posée :\n{user_content}\n\nRéponse complète :\n{asst_content}"
        slides = await generate_ai_presentation_slides(
            settings=settings,
            content=full_prompt_content,
            title=clean_title,
            topic=user_content[:140] if user_content else topic,
            model=effective_model,
            created_at_str=created_at_str,
            sources=all_sources,
        )
    else:
        conv_parts = []
        if summary:
            conv_parts.append(f"Synthèse de la discussion :\n{summary}")
        for idx, m in enumerate(messages, 1):
            role_label = "Utilisateur" if m.get("role") == "user" else "Assistant"
            c = m.get("content", "").strip()
            if c:
                conv_parts.append(f"Tour {idx:02d} ({role_label}) :\n{c}")

        compiled_md = "\n\n".join(conv_parts)
        slides = await generate_ai_presentation_slides(
            settings=settings,
            content=compiled_md,
            title=clean_title,
            topic=topic or "Synthèse de la discussion",
            model=effective_model,
            created_at_str=created_at_str,
            sources=all_sources,
        )

    return generate_presentation_html(
        title=clean_title,
        slides=slides,
        topic=topic,
        model=effective_model,
        created_at_str=created_at_str,
    )


async def generate_report_presentation_html(
    settings: Any = None,
    title: str = "",
    markdown_content: str = "",
    topic: str = "",
    model: str = "",
    created_at_str: str = "",
    sources: list[dict[str, Any]] | None = None,
) -> str:
    """Génère la présentation PowerPoint par IA pour un rapport DeepSearch ou Learn."""
    clean_title = (title or "").strip() or "Rapport d'analyse cLAIr"

    slides = await generate_ai_presentation_slides(
        settings=settings,
        content=markdown_content,
        title=clean_title,
        topic=topic or "Investigation approfondie",
        model=model,
        created_at_str=created_at_str,
        sources=sources or [],
    )

    return generate_presentation_html(
        title=clean_title,
        slides=slides,
        topic=topic,
        model=model,
        created_at_str=created_at_str,
    )
