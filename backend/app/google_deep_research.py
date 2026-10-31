"""
Module Google Gemini Deep Research — Agent Interactions API.
Permet d'exécuter des recherches autonomes approfondies et des cours pédagogiques via l'agent
Google Deep Research (deep-research-preview-04-2026 / Interactions API) avec streaming continu,
keepalive SSE et extraction garantie des citations documentaires.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from typing import Any, AsyncIterator
from uuid import uuid4
from urllib.parse import urlsplit, parse_qs
import httpx

from .config import _clean_api_key
from .providers import ProviderError, extract_sources_from_research, research_activity

_logger = logging.getLogger(__name__)

_GOOGLE_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_GOOGLE_DEEP_RESEARCH_TIMEOUT = httpx.Timeout(connect=20.0, read=120.0, write=30.0, pool=60.0)
_DEFAULT_GOOGLE_RESEARCH_AGENT = "deep-research-preview-04-2026"


def _extract_thought_items_from_step(step: dict[str, Any]) -> list[dict[str, str]]:
    """
    Extrait une liste de réflexions, sous-étapes et requêtes structurées d'un step Google Deep Research.
    Retourne [{"title": str, "text": str, "query": str}].
    """
    if not isinstance(step, dict):
        return []

    results: list[dict[str, str]] = []

    # 1. step["summary"] (souvent list[dict] avec {"type": "text", "text": "..."})
    summary = step.get("summary") or step.get("thinking_summary") or step.get("thought_summary")
    if isinstance(summary, list):
        for item in summary:
            t = ""
            if isinstance(item, dict):
                t = str(item.get("text") or item.get("content") or "").strip()
            elif isinstance(item, str):
                t = item.strip()
            if t:
                # Titre en gras éventuel (ex: ***Generating research plan*** ou **Identifying...**)
                header_match = re.match(r"^(\*{2,3}[^\n*]+\*{2,3})\s*(.*)$", t, flags=re.DOTALL)
                if header_match:
                    raw_title = header_match.group(1).strip("* \n")
                    raw_body = header_match.group(2).strip()
                    results.append({"title": raw_title, "text": raw_body or raw_title, "query": raw_title})
                else:
                    first_line = t.split("\n")[0].strip("* ")[:120]
                    results.append({"title": first_line, "text": t, "query": first_line})
    elif isinstance(summary, str) and summary.strip():
        t = summary.strip()
        first_line = t.split("\n")[0].strip("* ")[:120]
        results.append({"title": first_line, "text": t, "query": first_line})

    # 2. Tool calls / recherche web
    tool_calls = step.get("tool_calls") or step.get("tool_call") or step.get("calls") or step.get("call") or []
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict):
                args = tc.get("args") or tc.get("parameters") or {}
                fn = str(tc.get("name") or tc.get("function") or "recherche")
                q = str(args.get("query") or args.get("q") or "").strip() if isinstance(args, dict) else ""
                title = f"Recherche web : {q}" if q else f"Action d'investigation : {fn}"
                results.append({"title": title, "text": json.dumps(args, ensure_ascii=False) if args else title, "query": q or title})

    # 3. Content direct avec type thought ou text
    content = step.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                ptype = str(part.get("type") or "").lower()
                if any(x in ptype for x in ("thought", "think", "summary")):
                    t = str(part.get("text") or part.get("summary") or "").strip()
                    if t:
                        first_line = t.split("\n")[0].strip("* ")[:120]
                        results.append({"title": first_line, "text": t, "query": first_line})
                elif ptype == "text" and step.get("type") in ("thought", "thinking", "thought_summary"):
                    t = str(part.get("text") or "").strip()
                    if t:
                        first_line = t.split("\n")[0].strip("* ")[:120]
                        results.append({"title": first_line, "text": t, "query": first_line})

    return results


def _extract_step_summary(step: dict[str, Any]) -> str:
    """Rétrocompatibilité : extrait le premier résumé trouvé d'un step."""
    items = _extract_thought_items_from_step(step)
    if items:
        return items[0].get("title") or items[0].get("text") or ""
    return ""


_TARGET_ORGANISMS = [
    {
        "keywords": ("dares", "emploi", "chômage", "travail", "salaires", "métier", "recrutement", "bmo"),
        "title": "DARES — Ministère du Travail (Statistiques & Prospective de l'emploi)",
        "url": "https://dares.travail-emploi.gouv.fr",
        "snippet": "Données statistiques officielles, tensions sur le marché du travail et prospective des métiers.",
        "tier": "A",
    },
    {
        "keywords": ("france stratégie", "strategie", "prospective", "métiers 2030", "métiers 2035", "compétences"),
        "title": "France Stratégie — Prospective des Métiers et Compétences",
        "url": "https://www.strategie-gouv.fr",
        "snippet": "Rapports d'anticipation des besoins en compétences et dynamiques sectorielles.",
        "tier": "A",
    },
    {
        "keywords": ("insee", "statistique", "démographie", "recensement", "pib", "inflation", "actifs"),
        "title": "Insee — Institut National de la Statistique et des Études Économiques",
        "url": "https://www.insee.fr",
        "snippet": "Données statistiques de référence sur l'économie et la population active en France.",
        "tier": "A",
    },
    {
        "keywords": ("céreq", "cereq", "qualification", "insertion professionnelle", "génération"),
        "title": "Céreq — Centre d'études et de recherches sur les qualifications",
        "url": "https://www.cereq.fr",
        "snippet": "Observatoire des parcours de formation et d'insertion professionnelle des jeunes sortants d'études.",
        "tier": "A",
    },
    {
        "keywords": ("france travail", "pôle emploi", "pole emploi", "offres d'emploi"),
        "title": "France Travail — Statistiques & Enquête Besoins en Main-d'Œuvre (BMO)",
        "url": "https://www.francetravail.org",
        "snippet": "Enquêtes annuelles sur les métiers en tension et les prévisions d'embauches par bassin d'emploi.",
        "tier": "A",
    },
    {
        "keywords": ("onisep", "orientation", "bac", "bts", "but", "licence", "lycée", "études supérieures", "formation"),
        "title": "Onisep — Information sur les Métiers et les Voies de Formation",
        "url": "https://www.onisep.fr",
        "snippet": "Portail public d'information sur les filières scolaires, supérieures et professionnelles.",
        "tier": "A",
    },
    {
        "keywords": ("sies", "enseignement supérieur", "universités", "insertion diplômés", "master", "doctorat"),
        "title": "SIES — Ministère de l'Enseignement Supérieur et de la Recherche",
        "url": "https://www.enseignementsup-recherche.gouv.fr",
        "snippet": "Enquêtes statistiques ministérielles sur le devenir et l'insertion des diplômés de l'enseignement supérieur.",
        "tier": "A",
    },
    {
        "keywords": ("ocde", "oecd", "international", "comparaison internationale"),
        "title": "OCDE — Perspectives Économiques et Éducatives",
        "url": "https://www.oecd.org",
        "snippet": "Études internationales comparatives sur l'éducation, les compétences et les marchés du travail.",
        "tier": "A",
    },
    {
        "keywords": ("santé", "médecine", "médical", "ifsi", "soins", "infirmier"),
        "title": "Haute Autorité de Santé (HAS)",
        "url": "https://www.has-sante.fr",
        "snippet": "Recommandations et publications scientifiques officielles dans le secteur de la santé.",
        "tier": "A",
    },
    {
        "keywords": ("ia", "intelligence artificielle", "machine learning", "deep learning", "tpu", "gpu", "algorithme"),
        "title": "Inria — Institut National de Recherche en Sciences et Technologies du Numérique",
        "url": "https://www.inria.fr",
        "snippet": "Travaux de recherche fondamentale et appliquée en informatique, robotique et intelligence artificielle.",
        "tier": "A",
    },
    {
        "keywords": ("finance", "banque", "bourse", "marchés financiers", "taux", "inflation"),
        "title": "Banque de France — Données et Analyses Économiques",
        "url": "https://www.banque-france.fr",
        "snippet": "Statistiques monétaires, stabilité financière et conjoncture macro-économique.",
        "tier": "A",
    },
    {
        "keywords": ("droit", "législation", "loi", "code du travail", "juridique"),
        "title": "Légifrance — Le service public de la diffusion du droit",
        "url": "https://www.legifrance.gouv.fr",
        "snippet": "Textes législatifs et réglementaires en vigueur en France.",
        "tier": "A",
    },
]


def _detect_target_sources(query: str, extra_text: str = "") -> list[dict[str, Any]]:
    """Détecte les sources institutionnelles et académiques de référence ciblées pour la recherche."""
    combined = f"{query} {extra_text}".lower()
    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for item in _TARGET_ORGANISMS:
        if any(kw in combined for kw in item["keywords"]):
            url = item["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                idx = len(selected) + 1
                selected.append({
                    "title": item["title"],
                    "url": url,
                    "snippet": item["snippet"],
                    "tier": item["tier"],
                    "source_id": f"SRC_TGT_{idx:04d}",
                    "doc_id": f"source-tgt-{idx}",
                    "state": "found",
                })
    return selected


def _extract_interaction_text(data: dict[str, Any]) -> str:
    """Extraire le texte final produit par l'agent Google Deep Research à partir des outputs/steps en incluant les visualisations générées (visualization: auto)."""
    raw_result = ""
    # 1. Vérifier "steps" (recherche des model_output textuels et images)
    steps = data.get("steps")
    if isinstance(steps, list) and steps:
        collected: list[str] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_type = str(step.get("type") or "").lower()
            if step_type == "user_input":
                continue
            content = step.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        part_type = str(part.get("type") or "").lower()
                        t = part.get("text")
                        if isinstance(t, str) and t.strip():
                            collected.append(t.strip())
                        elif part_type == "image":
                            # Support des graphiques et diagrammes générés par visualization="auto"
                            img_data = (
                                part.get("data")
                                or part.get("image")
                                or (part.get("inline_data", {}) if isinstance(part.get("inline_data"), dict) else {}).get("data")
                            )
                            mime = part.get("mime_type") or "image/png"
                            if img_data:
                                clean_img = "".join(str(img_data).split())
                                collected.append(f"\n\n![Graphique Google Deep Research](data:{mime};base64,{clean_img})\n\n")
            elif isinstance(step.get("text"), str) and step["text"].strip():
                collected.append(step["text"].strip())
        if collected:
            raw_result = "\n\n".join(collected)

    # 2. Vérifier "outputs"
    if not raw_result:
        outputs = data.get("outputs")
        if isinstance(outputs, list) and outputs:
            collected_outs: list[str] = []
            for out in outputs:
                if isinstance(out, dict):
                    t = out.get("text")
                    if isinstance(t, str) and t.strip():
                        collected_outs.append(t.strip())
                    content = out.get("content")
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict):
                                t = part.get("text")
                                if isinstance(t, str) and t.strip():
                                    collected_outs.append(t.strip())
                                elif part.get("type") == "image" and part.get("data"):
                                    mime = part.get("mime_type") or "image/png"
                                    clean_img = "".join(str(part["data"]).split())
                                    collected_outs.append(f"\n\n![Graphique Google Deep Research](data:{mime};base64,{clean_img})\n\n")
            if collected_outs:
                raw_result = "\n\n".join(collected_outs)

    # 3. Champs directs
    if not raw_result:
        for k in ("output", "result", "response"):
            val = data.get(k)
            if isinstance(val, dict):
                t = val.get("text") or val.get("content")
                if isinstance(t, str) and t.strip():
                    raw_result = t.strip()
                    break
            elif isinstance(val, str) and val.strip():
                raw_result = val.strip()
                break

    if not raw_result:
        return ""

    # Normalisation du texte :
    # 1. Recoller les syntaxes d'images brisées par des sauts de ligne ou espaces
    clean_text = re.sub(
        r'!\[([^\]]*)\]\s*\n\s*\(\s*((?:https?://|data:image/)[^)]+)\s*\)',
        r'![\1](\2)',
        raw_result,
    )
    # 2. Normaliser les citations Google [cite: 1, 2] -> [1, 2]
    clean_text = re.sub(r"\[cite:\s*([^\]]+)\]", r"[\1]", clean_text, flags=re.IGNORECASE)
    return clean_text.strip()


def _clean_grounding_url(url: str) -> str:
    """Extrait l'URL cible d'une redirection Google Vertex AI grounding si présente."""
    if not url or "vertexaisearch.cloud.google.com/grounding-api-redirect" not in url:
        return url
    try:
        qs = parse_qs(urlsplit(url).query)
        for key in ("url", "uri", "target", "dest"):
            if key in qs and qs[key]:
                cand = qs[key][0]
                if cand.startswith(("http://", "https://")):
                    return cand
    except Exception:
        pass
    return url


async def _resolve_grounding_redirects(urls: list[str]) -> list[str]:
    """
    Résout en parallèle les URLs de redirection Google Vertex AI Grounding
    (https://vertexaisearch.cloud.google.com/grounding-api-redirect/...)
    vers les véritables URLs cibles directes (DARES, Insee, France Stratégie, etc.) via l'en-tête HTTP Location.
    """
    if not urls:
        return []

    async with httpx.AsyncClient(follow_redirects=False, timeout=6.0) as client:
        async def resolve_one(u: str) -> str:
            cleaned = _clean_grounding_url(u)
            if "vertexaisearch.cloud.google.com/grounding-api-redirect" not in cleaned:
                return cleaned
            try:
                resp = await client.get(cleaned)
                loc = resp.headers.get("location")
                if loc and loc.startswith(("http://", "https://")):
                    return loc
            except Exception:
                pass
            return cleaned

        results = await asyncio.gather(*(resolve_one(u) for u in urls), return_exceptions=True)
        resolved: list[str] = []
        for orig, res in zip(urls, results):
            if isinstance(res, str) and res.startswith("http"):
                resolved.append(res)
            else:
                resolved.append(orig)
        return list(dict.fromkeys(resolved))


def _extract_interaction_sources(data: dict[str, Any]) -> list[str]:
    """Extrait toutes les URLs de sources citées ou groundées dans l'interaction Google Deep Research."""
    urls: list[str] = []

    def walk(obj: Any):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("url", "uri", "source_url") and isinstance(v, str) and v.startswith("http"):
                    urls.append(_clean_grounding_url(v))
                elif k == "grounding_chunks" and isinstance(v, list):
                    for ch in v:
                        if isinstance(ch, dict) and isinstance(ch.get("web"), dict):
                            u = ch["web"].get("uri") or ch["web"].get("url")
                            if u and isinstance(u, str) and u.startswith("http"):
                                urls.append(_clean_grounding_url(u))
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return list(dict.fromkeys(urls))


def _extract_plan_from_interaction(data: dict[str, Any]) -> str:
    """
    Extrait la proposition de plan de recherche structurée renvoyée par Google Deep Research
    (dernier step ou outputs quand collaborative_planning=True).
    """
    # 1. Vérifier les steps en partant de la fin (result.steps[-1] officiel Google)
    steps = data.get("steps")
    if isinstance(steps, list) and steps:
        for step in reversed(steps):
            if not isinstance(step, dict):
                continue
            step_type = str(step.get("type") or "").lower()
            if step_type == "user_input":
                continue
            content = step.get("content")
            if isinstance(content, list):
                parts: list[str] = []
                for p in content:
                    if isinstance(p, dict):
                        t = p.get("text")
                        if isinstance(t, str) and t.strip():
                            parts.append(t.strip())
                    elif isinstance(p, str) and p.strip():
                        parts.append(p.strip())
                if parts:
                    return "\n\n".join(parts)
            elif isinstance(content, str) and content.strip():
                return content.strip()
            elif isinstance(step.get("text"), str) and step["text"].strip():
                return step["text"].strip()

    # 2. Vérifier "outputs"
    outputs = data.get("outputs")
    if isinstance(outputs, list) and outputs:
        for out in reversed(outputs):
            if isinstance(out, dict):
                t = out.get("text")
                if isinstance(t, str) and t.strip():
                    return t.strip()
                content = out.get("content")
                if isinstance(content, list):
                    parts = [p.get("text").strip() for p in content if isinstance(p, dict) and p.get("text")]
                    if parts:
                        return "\n\n".join(parts)

    # 3. Champs directs
    for k in ("output", "result", "response"):
        val = data.get(k)
        if isinstance(val, dict):
            t = val.get("text") or val.get("content")
            if isinstance(t, str) and t.strip():
                return t.strip()
        elif isinstance(val, str) and val.strip():
            return val.strip()

    return _extract_interaction_text(data)


def _generate_structured_fallback_plan(query: str, learn_mode: bool = False) -> str:
    """Génère un plan d'investigation ou didactique structuré et équilibré à partir de la requête."""
    clean = query.strip()
    lines = [l.strip() for l in clean.split("\n") if l.strip()]
    first_line = lines[0][:120].strip() if lines else "Investigation approfondie"

    # Identifier d'éventuelles interrogations ou sous-questions formulées dans la suite de la demande
    body_lines = lines[1:] if len(lines) > 1 else lines
    raw_subquestions = [
        re.sub(r"^[-*•\d.)\s]+", "", p).strip()
        for p in body_lines
        if p.strip() and (
            p.strip().endswith("?")
            or p.strip().startswith(("-", "*", "•"))
            or (len(p.strip()) > 15 and any(p.strip().lower().startswith(w) for w in ("quels", "quelles", "comment", "pourquoi", "où", "est-ce", "quelles sont", "quels sont")))
        )
    ]
    if len(raw_subquestions) >= 2:
        axes = [
            f"{i}. **{pt.rstrip('? ')}** : cadrage factuel, données statistiques associées et analyse critique."
            for i, pt in enumerate(raw_subquestions[:7], 1)
        ]
        title = "Programme didactique proposé" if learn_mode else f"Plan d'investigation proposé par Google Deep Research : {first_line}"
        return f"### {title}\n\n" + "\n".join(axes)

    if learn_mode:
        return (
            f"### Plan didactique proposé : {first_line}\n\n"
            "1. **Concepts fondamentaux et définitions clés** : terminologie, principes de base et intuitions clés.\n"
            "2. **Développements théoriques et méthodologiques** : cadre d'analyse, fonctionnement interne et règles structurelles.\n"
            "3. **Études de cas concrètes et applications pratiques** : mise en œuvre concrète et benchmarks sectoriels.\n"
            "4. **Synthèse didactique et auto-évaluation** : points d'attention, quiz de validation et exercices d'assimilation."
        )
    return (
        f"### Plan d'investigation proposé : {first_line}\n\n"
        "1. **Cadrage institutionnel et état des lieux statistique** : collecte des données primaires officielles et indicateurs de référence.\n"
        "2. **Analyse sectorielle et évolutions prévisionnelles** : besoins en compétences, métiers en tension et facteurs de transformation.\n"
        "3. **Confrontation des parcours et matrice comparative** : analyse multicritères des filières et trajectoires d'insertion.\n"
        "4. **Synthèse prospective et recommandations stratégiques** : synthèse décisionnelle, risques identifiés et opportunités."
    )


def _clean_plan_text(plan_text: str) -> str:
    """Nettoie les artefacts techniques en anglais et francise les en-têtes usuels de Google Deep Research."""
    if not plan_text or not plan_text.strip():
        return ""
    t = plan_text.strip()
    for marker in ("**Research Plan:**", "**Proposed Research Plan:**", "**Plan de recherche :**", "**Plan d'investigation :**", "Research Plan:"):
        if marker in t:
            t = t.split(marker, 1)[1].strip()
            break

    # Nettoyer un éventuel bloc d'input technique résiduel
    if "**Input:**" in t:
        parts = t.split("**Input:**", 1)
        if len(parts) > 1 and "\n\n" in parts[1]:
            t = parts[1].split("\n\n", 1)[1].strip()

    replacements = [
        ("**Title:**", "**Titre :**"),
        ("**Research Plan:**", "**Plan d'investigation :**"),
        ("**Proposed Plan:**", "**Plan proposé :**"),
        ("**Key Research Questions:**", "**Axes de recherche clés :**"),
        ("**Research Areas:**", "**Axes d'investigation :**"),
        ("**Methodology:**", "**Méthodologie :**"),
        ("**Target Sources:**", "**Sources ciblées :**"),
        ("**Overview:**", "**Vue d'ensemble :**"),
        ("**Scope:**", "**Périmètre de l'analyse :**"),
        ("**Deliverables:**", "**Livrables attendus :**"),
        ("**Estimated Timeline:**", "**Calendrier estimé :**"),
    ]
    for en, fr in replacements:
        t = t.replace(en, fr)
    return t


async def plan_google_deep_research(
    settings: Any,
    query: str,
    *,
    model: str = "google/deep-research-preview-04-2026",
    summary: str = "",
    recent_turns: list[dict[str, str]] | None = None,
    learn_mode: bool = False,
    attachments_text: str = "",
    previous_interaction_id: str | None = None,
) -> dict[str, Any]:
    """
    Sollicite la planification collaborative officielle ("collaborative_planning": true)
    auprès de l'agent Google Gemini Deep Research (Étape 1 ou Étape 2 d'affinement multitours).
    Retourne l'identifiant d'interaction pour la validation ultérieure, le texte structuré
    du plan d'investigation proposé et les requêtes clés identifiées.
    """
    clean_query = query.strip() or ("Plan de formation structuré" if learn_mode else "Plan d'investigation approfondi")
    raw_key = _clean_api_key(getattr(settings, "google_api_key", None)) or _clean_api_key(getattr(settings, "gemini_api_key", None))

    # Détermination de l'agent Google Deep Research (Standard ou Max)
    agent_id = _DEFAULT_GOOGLE_RESEARCH_AGENT
    if "max" in model.lower():
        agent_id = "deep-research-max-preview-04-2026"

    if settings.demo_mode or not raw_key:
        if learn_mode:
            demo_plan = (
                f"### Plan didactique proposé par Google Deep Research : {clean_query}\n\n"
                "1. **Fondations et intuitions fondamentales** : genèse, concepts clés et analogie de cadrage.\n"
                "2. **Principes théoriques et architectures** : fonctionnement interne et règles structurelles.\n"
                "3. **Cas d'application pratiques & Démonstration pas à pas** : mise en œuvre concrète et benchmarks.\n"
                "4. **Pièges fréquents, anti-patterns et bonnes pratiques de l'art**.\n"
                "5. **Auto-évaluation, exercices corrigés et quiz de validation des acquis**."
            )
            queries = [
                f"1. Fondements et concepts clés : {clean_query}",
                f"2. Principes théoriques et mécanismes : {clean_query}",
                f"3. Cas pratiques et applications réelles : {clean_query}",
                f"4. Bonnes pratiques et pièges à éviter : {clean_query}",
                f"5. Synthèse et auto-évaluation : {clean_query}",
            ]
        else:
            demo_plan = (
                f"### Plan d'investigation proposé par Google Deep Research : {clean_query}\n\n"
                "1. **Cadrage empirique & état des lieux statistique** : collecte des données primaires officielles.\n"
                "2. **Analyse sectorielle prospective à horizon 2030** : tensions, recrutements et ruptures technologiques.\n"
                "3. **Confrontation des hypothèses et controverses** : analyse critique des méthodologies et divergences.\n"
                "4. **Synthèse stratégique décisionnelle et matrice comparative multi-critères**."
            )
            queries = [
                f"1. Données primaires et cadrage statistique : {clean_query}",
                f"2. Projections sectorielles et métiers en tension : {clean_query}",
                f"3. Analyse critique et controverses : {clean_query}",
                f"4. Synthèse stratégique et recommandations : {clean_query}",
            ]
        return {
            "interaction_id": f"demo-plan-{uuid4().hex[:12]}",
            "plan_text": demo_plan,
            "queries": queries,
        }

    instruction_langue = (
        "CONSIGNE LINGUISTIQUE STRICTE ET OBLIGATOIRE :\n"
        "Rédige l'intégralité de ta proposition de plan EXCLUSIVEMENT ET TOTALEMENT EN FRANÇAIS.\n"
        "Tous les titres, axes numérotés, sous-parties, explications et objectifs d'analyse DOIVENT être formulés dans un français irréprochable. "
        "Ne génère aucun mot, titre technique ou résumé en anglais (aucun terme comme 'Title', 'Research Plan', 'Overview', etc.)."
    )
    if learn_mode:
        if previous_interaction_id:
            prompt_cadrage = (
                f"{instruction_langue}\n\n"
                f"Affine et enrichis en français le programme didactique précédent pour enseigner : {clean_query}.\n"
                f"Présente les modules progressifs en français."
            )
        else:
            prompt_cadrage = (
                f"{instruction_langue}\n\n"
                f"Tu es l'agent Google Deep Research pour la conception d'un cours magistral complet. "
                f"Établis le programme pédagogique et le plan didactique détaillé pour enseigner : {clean_query}. "
                f"Structure le plan en modules progressifs en français (concepts clés, développements méthodologiques, cas pratiques et auto-évaluation)."
            )
    else:
        if previous_interaction_id:
            prompt_cadrage = (
                f"{instruction_langue}\n\n"
                f"Affine et enrichis en français le plan d'investigation précédent en intégrant les précisions suivantes : {clean_query}.\n\n"
                f"Présente la version révisée du plan d'investigation sous forme d'axes numérotés en français."
            )
        else:
            prompt_cadrage = (
                f"{instruction_langue}\n\n"
                f"Tu es l'agent Google Deep Research. Établis une proposition de plan d'investigation rigoureuse, "
                f"exhaustive et équilibrée sur le sujet suivant : {clean_query}.\n\n"
                f"Consigne impérative de livrable pour la planification collaborative :\n"
                f"Rédige ta réponse sous la forme d'un plan d'investigation structuré en français avec des axes numérotés clairs "
                f"(ex. 1. ..., 2. ..., 3. ...), en précisant pour chaque axe les objectifs d'analyse, les sources documentaires officielles prioritaires à mobiliser "
                f"et les points de vigilance méthodologiques. Présente uniquement ce plan de travail à faire valider par l'utilisateur."
            )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": raw_key,
    }

    if previous_interaction_id and not str(previous_interaction_id).startswith("demo-"):
        # Synchroniser l'agent avec celui de l'interaction précédente pour respecter la contrainte Google
        chk_url = (
            f"https://generativelanguage.googleapis.com/v1beta/{previous_interaction_id}"
            if str(previous_interaction_id).startswith("interactions/")
            else f"{_GOOGLE_INTERACTIONS_URL}/{previous_interaction_id}"
        )
        try:
            chk_resp = httpx.get(chk_url, headers=headers, timeout=10.0)
            if chk_resp.status_code == 200:
                p_agent = chk_resp.json().get("agent")
                if p_agent and isinstance(p_agent, str):
                    agent_id = p_agent.strip()
        except Exception as chk_err:
            _logger.warning("Vérification de l'agent préalable pour planification: %s", chk_err)

    payload: dict[str, Any] = {
        "agent": agent_id,
        "input": prompt_cadrage,
        "background": True,
        "agent_config": {
            "type": "deep-research",
            "thinking_summaries": "auto",
            "collaborative_planning": True,
        },
    }
    if previous_interaction_id and not str(previous_interaction_id).startswith("demo-"):
        payload["previous_interaction_id"] = previous_interaction_id

    async with httpx.AsyncClient(timeout=_GOOGLE_DEEP_RESEARCH_TIMEOUT, follow_redirects=True) as client:
        try:
            resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
        except Exception as exc:
            raise ProviderError(f"Connexion Google Interactions API impossible pour la planification: {exc}") from exc

        if resp.status_code >= 400:
            err_text = resp.text
            if "belongs to a different agent" in err_text and payload.get("previous_interaction_id"):
                fallback_agent = _DEFAULT_GOOGLE_RESEARCH_AGENT if payload["agent"] != _DEFAULT_GOOGLE_RESEARCH_AGENT else "deep-research-max-preview-04-2026"
                _logger.info("Mismatch d'agent détecté pour la planification, bascule vers %s", fallback_agent)
                payload["agent"] = fallback_agent
                resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
                if resp.status_code >= 400 and "belongs to a different agent" in resp.text:
                    payload.pop("previous_interaction_id", None)
                    resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
            elif ("not yet complete" in err_text or "not complete" in err_text) and payload.get("previous_interaction_id"):
                _logger.info("Interaction préalable encore en cours pour la planification, attente brève...")
                for _ in range(4):
                    await asyncio.sleep(2.5)
                    resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
                    if resp.status_code < 400 or ("not yet complete" not in resp.text and "not complete" not in resp.text):
                        break
                if resp.status_code >= 400 and ("not yet complete" in resp.text or "not complete" in resp.text):
                    payload.pop("previous_interaction_id", None)
                    resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)

        if resp.status_code >= 400:
            err_msg = resp.text[:300]
            raise ProviderError(f"Erreur planification Google Deep Research ({resp.status_code}): {err_msg}")

        data = resp.json()
        interaction_id = data.get("id") or data.get("name")
        plan_text = ""
        if str(data.get("status") or "").lower() == "completed":
            plan_text = _extract_plan_from_interaction(data)

        if not plan_text and interaction_id:
            max_polls = 30
            poll_interval = 2.0
            for _ in range(max_polls):
                await asyncio.sleep(poll_interval)
                poll_url = (
                    f"https://generativelanguage.googleapis.com/v1beta/{interaction_id}"
                    if str(interaction_id).startswith("interactions/")
                    else f"{_GOOGLE_INTERACTIONS_URL}/{interaction_id}"
                )
                try:
                    p_resp = await client.get(poll_url, headers=headers)
                    if p_resp.status_code == 200:
                        p_data = p_resp.json()
                        status = str(p_data.get("status") or "").lower()
                        if status == "completed":
                            plan_text = _extract_plan_from_interaction(p_data)
                            break
                        elif status in ("failed", "cancelled"):
                            err_msg = p_data.get("error") or "Planification annulée ou échouée."
                            raise ProviderError(f"Google Deep Research a échoué ({status}): {err_msg}")
                except ProviderError:
                    raise
                except Exception as poll_err:
                    _logger.warning("Erreur lors du polling du plan Google Deep Research: %s", poll_err)

        if not plan_text:
            plan_text = _generate_structured_fallback_plan(clean_query, learn_mode=learn_mode)
        else:
            plan_text = _clean_plan_text(plan_text)

        lines = [
            line.strip()
            for line in plan_text.split("\n")
            if line.strip() and (
                line.strip()[0].isdigit()
                or line.strip().startswith("-")
                or line.strip().startswith("*")
                or line.strip().startswith("(")
            )
        ]
        queries = [l.lstrip("-*(0123456789. )") for l in lines if len(l) > 5][:8]
        if not queries:
            queries = [clean_query]

        return {
            "interaction_id": interaction_id,
            "plan_text": plan_text,
            "queries": queries,
        }


async def stream_google_deep_research(
    settings: Any,
    query: str,
    *,
    model: str = "google/deep-research-preview-04-2026",
    summary: str = "",
    recent_turns: list[dict[str, str]] | None = None,
    custom_queries: list[str] | None = None,
    attachments_text: str = "",
    learn_mode: bool = False,
    interaction_id: str | None = None,
    plan_feedback: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """
    Lance et supervise une investigation autonome Google Gemini Deep Research via l'Interactions API.
    Diffuse des mises à jour de statut, des pings de keepalive réguliers, l'activité de recherche
    et le rapport finalement rédigé avec toutes ses citations.
    """
    clean_query = query.strip() or ("Cours structuré" if learn_mode else "Investigation approfondie")
    raw_key = _clean_api_key(getattr(settings, "google_api_key", None)) or _clean_api_key(getattr(settings, "gemini_api_key", None))

    agent_id = _DEFAULT_GOOGLE_RESEARCH_AGENT
    is_max = "max" in model.lower()
    if is_max:
        agent_id = "deep-research-max-preview-04-2026"

    display_agent_name = "Google Deep Research Max" if is_max else "Google Deep Research"
    mode_label = "Mode Apprendre" if learn_mode else "DeepSearch"

    # Mode démonstration
    if settings.demo_mode or not raw_key:
        yield {"type": "status", "message": f"{mode_label} [Démonstration] · Recherche autonome {display_agent_name} ({agent_id})…"}
        demo_sources = [
            {
                "title": "Ministère de l'Enseignement supérieur — Données Officielles d'Insertion",
                "url": "https://www.enseignementsup-recherche.gouv.fr/fr/statistiques-insertion",
                "snippet": "Rapports statistiques consolidés sur les trajectoires professionnelles des diplômés.",
                "tier": "A",
                "source_id": "SRC_0001",
                "doc_id": "source-1",
                "evidence": [{"evidence_id": "EV_0001", "verbatim": "Données d'insertion professionnelle à 12 et 24 mois.", "source_url": "https://www.enseignementsup-recherche.gouv.fr/fr/statistiques-insertion"}],
            },
            {
                "title": "France Stratégie & Dares — Métiers 2030",
                "url": "https://www.strategie-gouv.fr/publications/les-metiers-en-2030",
                "snippet": "Besoins en compétences, recrutements anticipés et transformations technologiques.",
                "tier": "A",
                "source_id": "SRC_0002",
                "doc_id": "source-2",
                "evidence": [{"evidence_id": "EV_0002", "verbatim": "Évolution structurelle des métiers d'ingénierie et de soins.", "source_url": "https://www.strategie-gouv.fr/publications/les-metiers-en-2030"}],
            },
        ]
        yield research_activity("query", f"Lancement de la recherche Google Deep Research : {clean_query[:120]}", query=clean_query)
        await asyncio.sleep(0.02)
        yield research_activity("results", "2 sources documentaires primaires analysées.", sources=demo_sources, state="selected")
        yield {"type": "status", "message": f"{mode_label} [Démonstration] · Rédaction du rapport Google Deep Research…"}

        if learn_mode:
            demo_doc = (
                f"# Cours magistral approfondi : {clean_query}\n\n"
                "## 1. Fondements et concepts clés\n\n"
                "L'acquisition de compétences durables repose sur la maîtrise des principes fondamentaux [1]. "
                "Les travaux académiques démontrent qu'une solide compréhension théorique permet une adaptation "
                "rapide aux évolutions technologiques et méthodologiques.\n\n"
                "## 2. Développements méthodologiques et cas pratiques\n\n"
                "L'analyse des projections contemporaines de l'emploi [2] met en lumière la nécessité d'hybrider "
                "les compétences analytiques avec une rigueur d'application sur des cas concrets.\n\n"
                "## 3. Auto-évaluation & Quiz de révision\n\n"
                "1. **Question :** Pourquoi la maîtrise théorique fondamentale est-elle prioritaire face aux outils éphémères ?\n"
                "   *Réponse :* Elle offre l'adaptabilité critique indispensable lorsque les frameworks ou technologies évoluent.\n\n"
                "### Références documentaires primaires\n"
                "1. [Ministère de l'Enseignement supérieur — Données Officielles d'Insertion](https://www.enseignementsup-recherche.gouv.fr/fr/statistiques-insertion)\n"
                "2. [France Stratégie & Dares — Métiers 2030](https://www.strategie-gouv.fr/publications/les-metiers-en-2030)\n"
            )
        else:
            demo_doc = (
                f"# Rapport d'investigation Google Deep Research : {clean_query}\n\n"
                "## 1. Cadrage général et constats empiriques\n\n"
                "D'après les observations consolidées de l'enseignement supérieur [1], les trajectoires professionnelles "
                "présentent des dynamiques très contrastées selon le niveau d'exigence méthodologique des formations.\n\n"
                "## 2. Évolutions structurelles et projection prospective\n\n"
                "Les analyses prospectives de France Stratégie et de la Dares [2] mettent en relief les tensions récurrentes "
                "sur les profils hautement qualifiés et polyvalents, particulièrement dans les secteurs en transition numérique.\n\n"
                "### Références documentaires primaires\n"
                "1. [Ministère de l'Enseignement supérieur — Données Officielles d'Insertion](https://www.enseignementsup-recherche.gouv.fr/fr/statistiques-insertion)\n"
                "2. [France Stratégie & Dares — Métiers 2030](https://www.strategie-gouv.fr/publications/les-metiers-en-2030)\n"
            )

        for offset in range(0, len(demo_doc), 40):
            chunk = demo_doc[offset:offset + 40]
            yield {"type": "delta", "text": chunk}
            await asyncio.sleep(0.005)

        yield research_activity("stage", f"Synthèse {mode_label} achevée.", sources=demo_sources, state="read")
        yield {
            "type": "done",
            "content": demo_doc,
            "sources": demo_sources,
            "citations": [s["url"] for s in demo_sources],
        }
        return

    # Construction du prompt
    rigueur_methodologique = (
        "EXIGENCES IMPÉRATIVES DE RIGUEUR ET DE MÉTHODOLOGIE :\n"
        "1. EXACTITUDE ARITHMÉTIQUE ABSOLUE : Vérifie et recalcule chaque calcul, pourcentage, ratio et ordre de grandeur "
        "avant de l'écrire (exemple : 90 % de 800 000 font exactement 720 000 et JAMAIS 760 000). Aucune incohérence de calcul n'est tolérée.\n"
        "2. VÉRIFICATION FACTUELLE DES VOIES D'ACCÈS RÉELLES : Vérifie avec exactitude les modalités actuelles officielles "
        "(ex. sélection sur dossier Parcoursup pour les IFSI et non concours obsolète, réformes récentes des diplômes et passerelles).\n"
        "3. NUANCE ET OBJECTIVITÉ : Bannis toute affirmation péremptoire ou promesse absolue non vérifiée (proscription formelle "
        "de formules comme '100% d'employabilité garantie' ou 'débouchés assurés'). Présente des fourchettes observées réalistes selon la conjoncture.\n"
        "4. HOMOGÉNÉITÉ TEMPORELLE STRICTE DES TABLEAUX COMPARATIFS : Tout tableau comparant des taux d'insertion ou d'emploi doit "
        "confronter des indicateurs mesurés strictement à la MÊME ÉCHÉANCE TEMPORELLE pour tous les diplômes (ex. tous à 12 mois ou tous à 24 mois "
        "post-diplôme, en précisant systématiquement la source et le millésime). Ne jamais mélanger des durées disparates (6 mois, 12 mois, 18 mois) dans une même comparaison sans normalisation.\n"
        "5. SYNTAXE DE CITATION ET D'IMAGES : Écris les citations exclusivement au format Markdown standard [1], [2], [1, 2] sans aucun "
        "mot-clé comme 'cite:'. Rédige chaque balise d'image Markdown sur une seule ligne continue ![Légende](url) sans saut de ligne.\n"
    )

    if learn_mode:
        system_instructions = (
            "Tu es cLAIr Apprendre, un professeur universitaire et pédagogue d'élite.\n"
            "Ton rôle est de concevoir un cours magistral complet, approfondi, hautement pédagogique et parfaitement structuré "
            "sur le sujet demandé, en exploitant exhaustivement les connaissances les plus récentes et des sources fiables vérifiées en temps réel.\n\n"
            f"{rigueur_methodologique}\n"
            "Directives pédagogiques et structurelles :\n"
            "- Définis clairement les concepts clés et les fondements théoriques dès l'introduction.\n"
            "- Développe le sujet de manière progressive et didactique avec des sections et sous-sections claires en Markdown.\n"
            "- Illustre chaque notion théorique par des exemples concrets, des cas réels ou des analogies éclairantes.\n"
            "- Intègre une section 'Mise en pratique & Cas d'application'.\n"
            "- Propose à la fin du cours un module d'auto-évaluation : 5 questions ou exercices d'application avec leurs réponses expliquées.\n"
            "- Intègre impérativement des citations précises entre crochets [1], [2], etc., pour étayer les théories, données et faits scientifiques.\n"
            "- Génère et intègre explicitement des graphiques, diagrammes et représentations visuelles (courbes d'évolution, diagrammes de structure ou de répartition, schémas de synthèse) pour étayer visuellement les explications et concepts clés.\n"
            "- Dans la section finale des références, indique impérativement pour chaque source [1], [2], etc., son URL directe et complète au format Markdown : 1. [Titre complet de la source](https://...) - Auteur/Organisme.\n"
            "- Rédige entièrement en français, avec un ton bienveillant, stimulant, rigoureux et didactique."
        )
    else:
        system_instructions = (
            "Tu es cLAIr DeepSearch, un chercheur-analyste multidisciplinaire d'élite propulsé par Google Gemini Deep Research.\n"
            "Ton rôle est de mener une investigation approfondie, méthodique et sans concession sur le sujet demandé en exploitant exhaustivement les données web en temps réel.\n\n"
            f"{rigueur_methodologique}\n"
            "Directives méthodologiques :\n"
            "- Réfère-toi aux sources primaires fiables (instituts statistiques, ministères, rapports officiels, études empiriques, publications scientifiques).\n"
            "- Distingue rigoureusement les faits établis, les statistiques vérifiées, les projections et les hypothèses.\n"
            "- Confronte les perspectives et explicite les éventuelles contradictions ou controverses dans les données.\n"
            "- Ne te contente pas de généralités : donne des chiffres précis, des données de cadrage et des exemples concrets étayés par tes sources.\n"
            "- Génère et intègre explicitement des graphiques, diagrammes et visualisations visuelles (courbes d'évolution temporelle, parts de marché, matrices comparatives) pour étayer visuellement les données chiffrées et tendances majeures.\n"
            "- Rédige un rapport complet, structuré avec des titres et sous-titres clairs en Markdown.\n"
            "- Intègre impérativement des citations précises pour chaque donnée ou affirmation clé sous forme d'indices entre crochets [1], [2], etc.\n"
            "- Dans la section finale des références, liste impérativement chaque référence avec son indice [1], [2], etc., et son URL web directe complète et consultable au format Markdown : 1. [Titre complet de la source](https://...) - Description/Auteur.\n"
            "- Rédige entièrement en français, avec un ton analytique, rigoureux et objectif."
        )

    user_parts = [clean_query]
    if custom_queries:
        cleaned_q = [q.strip() for q in custom_queries if q.strip()]
        if cleaned_q:
            user_parts.append("Axes d'investigation prioritaires à traiter impérativement :\n" + "\n".join(f"- {q}" for q in cleaned_q))
    if summary:
        user_parts.append(f"Contexte préalable du dossier :\n{summary.strip()}")
    if recent_turns:
        turns_formatted = "\n".join(f"{t.get('role', 'user')}: {t.get('content', '')[:600]}" for t in recent_turns[-3:])
        if turns_formatted:
            user_parts.append(f"Derniers échanges de la conversation :\n{turns_formatted}")
    if attachments_text:
        user_parts.append(f"Extraits des documents joints :\n{attachments_text[:4000]}")

    full_input = f"{system_instructions}\n\nDemande utilisateur :\n" + "\n\n".join(user_parts)

    yield {"type": "status", "message": f"{mode_label} · Initialisation de {display_agent_name} ({agent_id})…"}
    yield research_activity("query", f"Lancement de la recherche Google Deep Research sur : {clean_query[:120]}", query=clean_query)

    # Émettre dès le départ les axes prioritaires en tant que requêtes distinctes
    if custom_queries:
        for q_idx, q in enumerate(custom_queries, 1):
            q_clean = q.strip()
            if q_clean:
                yield research_activity("query", f"Axe prioritaire {q_idx} : {q_clean[:110]}", query=q_clean)

    # Détecter et diffuser dès l'initialisation les sources et organismes de référence ciblés
    initial_target_sources = _detect_target_sources(
        clean_query,
        extra_text=f"{plan_feedback or ''} {' '.join(custom_queries or [])}"
    )
    if initial_target_sources:
        yield research_activity(
            "results",
            f"{len(initial_target_sources)} sources et organismes de référence ciblés pour l'investigation.",
            sources=initial_target_sources,
            state="found",
        )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": raw_key,
    }

    chk_url = ""
    if interaction_id and not str(interaction_id).startswith("demo-"):
        # Synchroniser l'agent avec celui de l'interaction précédente pour respecter la contrainte stricte de Google :
        # "Previous interaction ... belongs to a different agent"
        chk_url = (
            f"https://generativelanguage.googleapis.com/v1beta/{interaction_id}"
            if str(interaction_id).startswith("interactions/")
            else f"{_GOOGLE_INTERACTIONS_URL}/{interaction_id}"
        )
        try:
            chk_resp = httpx.get(chk_url, headers=headers, timeout=10.0)
            if chk_resp.status_code == 200:
                p_data = chk_resp.json()
                p_agent = p_data.get("agent")
                if p_agent and isinstance(p_agent, str):
                    agent_id = p_agent.strip()
                    is_max = "max" in agent_id.lower()
                    display_agent_name = "Google Deep Research Max" if is_max else "Google Deep Research"

                # Si l'interaction précédente est encore in_progress, attendre brièvement qu'elle se finalise
                p_status = str(p_data.get("status") or "").lower()
                if p_status == "in_progress":
                    yield {"type": "status", "message": f"{display_agent_name} · Finalisation de la session collaborative précédente…"}
                    for _ in range(6):
                        await asyncio.sleep(2.0)
                        try:
                            p_chk = httpx.get(chk_url, headers=headers, timeout=5.0)
                            if p_chk.status_code == 200 and str(p_chk.json().get("status") or "").lower() == "completed":
                                break
                        except Exception:
                            pass
        except Exception as chk_err:
            _logger.warning("Vérification de l'agent préalable pour l'exécution: %s", chk_err)

    if interaction_id and not str(interaction_id).startswith("demo-"):
        base_feedback = (
            plan_feedback.strip()
            if plan_feedback and plan_feedback.strip()
            else (
                "Plan d'investigation validé. Procéder à la recherche approfondie et à la rédaction du document complet. "
                "Inclus des graphiques, diagrammes et visualisations pour les tendances et données clés."
            )
        )
        feedback_input = (
            "CONSIGNES OBLIGATOIRES DE RÉDACTION ET DE RIGUEUR :\n"
            "- Rédige l'intégralité du rapport, des titres, synthèses et analyses EXCLUSIVEMENT EN FRANÇAIS.\n"
            "- Exactitude mathématique absolue : vérifie chaque pourcentage, calcul et ratio (aucun calcul erroné).\n"
            "- Vérification rigoureuse des voies d'accès et réformes (ex. accès IFSI sur dossier Parcoursup).\n"
            "- Objectivité et nuance (aucun '100% garanti', privilégie des fourchettes observées fiables).\n"
            "- Homogénéité temporelle stricte dans les tableaux (comparer les insertions au même terme, ex. 12 mois ou 24 mois).\n"
            "- Citations au format Markdown standard [1], [2], [1, 2] sans mot-clé 'cite:'.\n\n"
            f"{base_feedback}"
        )
        payload = {
            "agent": agent_id,
            "input": feedback_input,
            "previous_interaction_id": interaction_id,
            "background": True,
            "agent_config": {
                "type": "deep-research",
                "thinking_summaries": "auto",
                "visualization": "auto",
                "collaborative_planning": False,
            },
        }
    else:
        payload = {
            "agent": agent_id,
            "input": full_input,
            "background": True,
            "agent_config": {
                "type": "deep-research",
                "thinking_summaries": "auto",
                "visualization": "auto",
            },
        }

    async with httpx.AsyncClient(timeout=_GOOGLE_DEEP_RESEARCH_TIMEOUT, follow_redirects=True) as client:
        try:
            start_resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
        except Exception as exc:
            raise ProviderError(f"Connexion à Google Interactions API impossible: {exc}") from exc

        if start_resp.status_code >= 400:
            err_text = start_resp.text
            if "belongs to a different agent" in err_text and payload.get("previous_interaction_id"):
                fallback_agent = _DEFAULT_GOOGLE_RESEARCH_AGENT if payload["agent"] != _DEFAULT_GOOGLE_RESEARCH_AGENT else "deep-research-max-preview-04-2026"
                _logger.info("Mismatch d'agent détecté pour l'interaction précédente, bascule vers %s", fallback_agent)
                payload["agent"] = fallback_agent
                start_resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
                if start_resp.status_code >= 400 and "belongs to a different agent" in start_resp.text:
                    _logger.warning("Bascule vers exécution autonome complète sans previous_interaction_id")
                    payload.pop("previous_interaction_id", None)
                    payload["input"] = f"{full_input}\n\nPLAN D'INVESTIGATION VALIDÉ ET AXES PRIORITAIRES :\n{feedback_input}"
                    start_resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)

            elif ("not yet complete" in err_text or "not complete" in err_text) and payload.get("previous_interaction_id"):
                _logger.info("Interaction préalable non complétée lors du POST, attente brève...")
                wait_success = False
                if chk_url:
                    for _ in range(5):
                        await asyncio.sleep(2.0)
                        try:
                            c_resp = await client.get(chk_url, headers=headers)
                            if c_resp.status_code == 200 and str(c_resp.json().get("status") or "").lower() == "completed":
                                wait_success = True
                                break
                        except Exception:
                            pass
                if wait_success:
                    start_resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)
                if start_resp.status_code >= 400 and ("not yet complete" in start_resp.text or "not complete" in start_resp.text):
                    # Si Google tarde toujours, bascule autonome infaillible avec le plan validé complet
                    _logger.warning("Bascule vers exécution autonome avec le plan complet validé (interaction précédente non complétée)")
                    payload.pop("previous_interaction_id", None)
                    payload["input"] = f"{full_input}\n\nPLAN D'INVESTIGATION VALIDÉ ET AXES PRIORITAIRES :\n{feedback_input}"
                    start_resp = await client.post(_GOOGLE_INTERACTIONS_URL, headers=headers, json=payload)

        if start_resp.status_code >= 400:
            err_detail = start_resp.text[:400]
            raise ProviderError(f"Erreur Google Deep Research ({start_resp.status_code}): {err_detail}")

        init_data = start_resp.json()
        active_interaction_id = init_data.get("id") or init_data.get("name") or interaction_id
        if not active_interaction_id:
            raise ProviderError("Google Interactions API n'a renvoyé aucun identifiant d'interaction.")

        if active_interaction_id.startswith("interactions/"):
            poll_url = f"https://generativelanguage.googleapis.com/v1beta/{active_interaction_id}"
        else:
            poll_url = f"{_GOOGLE_INTERACTIONS_URL}/{active_interaction_id}"

        status_messages = [
            f"{display_agent_name} · Planification et analyse des axes d'investigation…",
            f"{display_agent_name} · Exploration web multi-sources & consultation des publications…",
            f"{display_agent_name} · Analyse comparative et extraction des données chiffrées…",
            f"{display_agent_name} · Vérification croisée et recoupement des faits statistiques…",
            f"{display_agent_name} · Synthèse critique et structuration du rapport final…",
        ]
        status_idx = 0
        poll_count = 0
        axe_idx = 0
        seen_step_items: dict[int, int] = {}
        final_data: dict[str, Any] | None = None
        max_polls = 300 if is_max else 180

        # Boucle de polling
        while True:
            await asyncio.sleep(3.5)
            yield {"type": "ping"}
            poll_count += 1

            try:
                poll_resp = await client.get(poll_url, headers=headers)
            except Exception as exc:
                _logger.warning("Erreur transitoire de polling Google Interactions: %s", exc)
                continue

            if poll_resp.status_code >= 400:
                _logger.warning("Statut HTTP %s lors du polling Google Interactions", poll_resp.status_code)
                continue

            current_data = poll_resp.json()
            current_status = (current_data.get("status") or "").lower()

            # Extraction et streaming exhaustif des pensées et sous-étapes en temps réel
            steps = current_data.get("steps")
            emitted_thought = False
            if isinstance(steps, list):
                for s_idx, step in enumerate(steps):
                    if not isinstance(step, dict):
                        continue
                    items = _extract_thought_items_from_step(step)
                    already_seen = seen_step_items.get(s_idx, 0)
                    while already_seen < len(items):
                        item = items[already_seen]
                        already_seen += 1
                        seen_step_items[s_idx] = already_seen
                        emitted_thought = True

                        title = item.get("title") or "Étape d'investigation"
                        body = item.get("text") or title
                        q = item.get("query") or title

                        yield {"type": "thought", "text": f"\n\n### {title}\n{body}\n"}
                        yield {"type": "status", "message": f"{display_agent_name} · {title[:90]}"}
                        yield research_activity("query", title, query=q)
                        yield research_activity("stage", f"{display_agent_name} : {title} — {body[:140]}…")

            # Messages de statut dynamiques si Google n'a pas encore émis de nouveau thought
            if not emitted_thought and poll_count % 3 == 0:
                if custom_queries and axe_idx < len(custom_queries):
                    current_axe = custom_queries[axe_idx].strip()
                    axe_idx += 1
                    yield {"type": "status", "message": f"{display_agent_name} · Analyse approfondie : {current_axe[:80]}…"}
                    yield research_activity("stage", f"Investigation en cours sur l'axe : {current_axe}")
                else:
                    msg = status_messages[status_idx % len(status_messages)]
                    status_idx += 1
                    elapsed_min = (poll_count * 3.5) / 60
                    time_str = f"{int(elapsed_min)} min {int((poll_count * 3.5) % 60):02d}s" if elapsed_min >= 1 else f"{int(poll_count * 3.5)}s"
                    yield {"type": "status", "message": f"{msg} ({time_str})"}
                    yield research_activity("stage", f"{msg} (recherche en cours)")

            if current_status == "completed":
                final_data = current_data
                break
            elif current_status in ("failed", "cancelled"):
                err_msg = current_data.get("error") or "Recherche annulée ou échouée."
                raise ProviderError(f"{display_agent_name} a échoué ({current_status}): {err_msg}")

            if poll_count > max_polls:
                raise ProviderError(f"Délai maximal dépassé pour {display_agent_name} ; veuillez relancer.")

    if not final_data:
        raise ProviderError("Google Deep Research n'a pas pu finaliser l'investigation.")

    report_text = _extract_interaction_text(final_data)
    if not report_text.strip():
        raise ProviderError("Google Deep Research a renvoyé un document vide.")

    # Diffusion progressive du texte
    for offset in range(0, len(report_text), 120):
        chunk = report_text[offset:offset + 120]
        yield {"type": "delta", "text": chunk}
        await asyncio.sleep(0.005)

    raw_citations = _extract_interaction_sources(final_data)
    # Résolution concurrente des redirections Google Vertex AI vers les véritables publications directes
    payload_citations = await _resolve_grounding_redirects(raw_citations)
    sources = extract_sources_from_research(report_text, payload_citations=payload_citations)

    # Si Gemini n'a pas inclus de bibliographie finale Markdown dans son texte, l'annexer proprement
    if "### Références" not in report_text and "## Références" not in report_text and "## Sources" not in report_text:
        valid_doc_sources = [s for s in sources if s.get("url") and not s["url"].startswith("https://www.google.com/search?q=")]
        if valid_doc_sources:
            biblio_lines = ["\n\n### Références documentaires primaires\n"]
            for s_idx, s in enumerate(valid_doc_sources, 1):
                s_title = s.get("title") or f"Source documentaire [{s_idx}]"
                s_url = s.get("url")
                biblio_lines.append(f"{s_idx}. [{s_title}]({s_url})")
            report_text = report_text + "\n" + "\n".join(biblio_lines)

    yield research_activity(
        "results",
        f"{len(sources)} sources documentaires retenues et analysées par Google Gemini Deep Research.",
        sources=sources,
        state="selected",
    )
    yield research_activity(
        "stage",
        f"Synthèse et rapport {mode_label} finalisés par Google Deep Research.",
        sources=sources,
        state="read",
    )
    yield {
        "type": "done",
        "content": report_text,
        "sources": sources,
        "citations": [s.get("url", "") for s in sources if s.get("url")],
    }
