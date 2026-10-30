"""
DeepSearch — Architecture itérative de recherche approfondie multi-étapes (StateGraph Agent).

Inspiré de l'architecture par graphe d'états (StateGraph) :
1. Planification & Décomposition (Plan Node)
2. Génération dynamique de requêtes (Dynamic Query Generation)
3. Extraction et lecture ciblée (Web Retrieval & Reranking)
4. Raisonnement itératif, croisement et contre-vérifications (Re-thinking / Evaluation Node)
5. Synthèse sourcée, mémoire de travail (Context Scratchpad) et attribution finale (Synthesize Node)
"""

from __future__ import annotations

import asyncio
import json
import logging
import operator
import re
from typing import Annotated, Any, AsyncGenerator, Awaitable, Callable, List, Sequence, TypedDict

from pydantic import BaseModel, Field

from . import providers
from .source_filter import curate_sources, filter_findings_by_sources, is_junk_source

_logger = logging.getLogger("clair.deep_search")

START = "__start__"
END = "__end__"


# ---------------------------------------------------------
# 1. État partagé du graphe (SearchState)
# ---------------------------------------------------------
class SearchState(TypedDict, total=False):
    question: str
    iteration: int
    max_iterations: int
    max_sources: int | None
    findings: Annotated[List[str], operator.add]  # Mémoire de travail (Context Scratchpad)
    queries: List[str]
    executed_queries: List[str]
    sources: List[dict[str, str]]
    aspect_checklist: List[dict[str, str]]  # Découpage initial en points à aborder
    intermediate_questions: List[str]  # Questions intermédiaires générées en cours de route
    validation_log: List[str]  # Historique des validations intermédiaires
    searched_languages: List[str]  # Langues explorées
    is_sufficient: bool
    critique: str
    final_answer: str


# ---------------------------------------------------------
# 2. Modèles de sortie structurée
# ---------------------------------------------------------
class EvaluationOutput(BaseModel):
    is_sufficient: bool = Field(
        default=False,
        description="True si les faits et sources réunis suffisent pour répondre exhaustivement, False sinon.",
    )
    critique: str = Field(
        default="",
        description="Analyse des éléments acquis, contradictions détectées ou lacunes restantes.",
    )
    extracted_findings: List[str] = Field(
        default_factory=list,
        description="Faits saillants, données chiffrées, consensus et citations clés extraits des sources récentes.",
    )
    intermediate_questions: List[str] = Field(
        default_factory=list,
        description="Questions intermédiaires générées à partir du contenu découvert et de l'objectif initial.",
    )
    unanswered_aspects: List[str] = Field(
        default_factory=list,
        description="Points de la checklist initiale non encore intégralement couverts.",
    )
    next_queries: List[str] = Field(
        default_factory=list,
        description="1 à 6 requêtes très précises dans toutes les langues pertinentes pour combler les manques ou contre-vérifier.",
    )


# ---------------------------------------------------------
# 3. Moteur générique de StateGraph (léger, asynchrone, typé)
# ---------------------------------------------------------
class StateGraph:
    """Moteur de graphe d'états orienté agent pour DeepSearch."""

    def __init__(self, state_schema: type):
        self.state_schema = state_schema
        self.nodes: dict[str, Callable[[SearchState], Awaitable[dict[str, Any]]]] = {}
        self.edges: dict[str, str] = {}
        self.conditional_edges: dict[str, tuple[Callable[[SearchState], str], dict[str, str]]] = {}

    def add_node(self, name: str, fn: Callable[[SearchState], Awaitable[dict[str, Any]]]) -> None:
        self.nodes[name] = fn

    def add_edge(self, from_node: str, to_node: str) -> None:
        self.edges[from_node] = to_node

    def add_conditional_edges(
        self,
        from_node: str,
        router: Callable[[SearchState], str],
        mapping: dict[str, str],
    ) -> None:
        self.conditional_edges[from_node] = (router, mapping)

    def compile(self) -> CompiledStateGraph:
        return CompiledStateGraph(self)


class CompiledStateGraph:
    """Graphe compilé exécutant les transitions d'état."""

    def __init__(self, graph: StateGraph):
        self.nodes = graph.nodes
        self.edges = graph.edges
        self.conditional_edges = graph.conditional_edges

    async def stream(self, initial_state: SearchState) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        state: SearchState = dict(initial_state)  # type: ignore[assignment]
        if "findings" not in state:
            state["findings"] = []
        if "executed_queries" not in state:
            state["executed_queries"] = []
        if "sources" not in state:
            state["sources"] = []

        current_node = self.edges.get(START)
        while current_node and current_node != END:
            node_fn = self.nodes.get(current_node)
            if not node_fn:
                break

            output = await node_fn(state)

            # Mise à jour de l'état avec gestion de l'accumulation sur findings
            for key, value in output.items():
                if key == "findings" and isinstance(value, list):
                    existing = state.get("findings", [])
                    seen = set(existing)
                    for item in value:
                        if isinstance(item, str) and item.strip() and item not in seen:
                            existing.append(item.strip())
                            seen.add(item.strip())
                    state["findings"] = existing
                else:
                    state[key] = value  # type: ignore[literal-required]

            yield (current_node, output)

            # Résolution de la transition suivante
            if current_node in self.conditional_edges:
                router, mapping = self.conditional_edges[current_node]
                route = router(state)
                current_node = mapping.get(route, END)
            elif current_node in self.edges:
                current_node = self.edges[current_node]
            else:
                break


# ---------------------------------------------------------
# 4. Utilitaires Phase 2 & Phase 3 (Filtrage, Nettoyage & Extraction atomique)
# ---------------------------------------------------------
_BOILERPLATE_RE = re.compile(
    r"(?:\b(?:accept all cookies|cookie policy|privacy policy|all rights reserved|"
    r"terms of service|subscribe to our newsletter|sign up for free|"
    r"accepter les cookies|politique de confidentialité|tous droits réservés)\b)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(202[0-9][-/.](?:0[1-9]|1[0-2])(?:[-/.](?:0[1-9]|[12]\d|3[01]))?|"
    r"(?:jan(?:vier|uary)?|fév(?:rier)?|feb(?:ruary)?|mar(?:s|ch)?|avr(?:il)?|apr(?:il)?|"
    r"mai|may|juin|june|juil(?:let)?|july|août|aug(?:ust)?|sep(?:tembre|tember)?|"
    r"oct(?:obre|ober)?|nov(?:embre|ember)?|déc(?:embre)?|dec(?:ember)?)\s+202[0-9]|"
    r"202[3-9])\b",
    re.IGNORECASE,
)
from .source_filter import (
    PRIMARY_DOMAINS,
    curate_sources,
    enrich_top_sources_content,
    extract_primary_source_citations,
    filter_findings_by_sources,
    is_junk_source,
    prefilter_sources,
)

_PRIMARY_DOMAINS = PRIMARY_DOMAINS
_AD_OR_SPAM_PATTERNS = (
    "doubleclick.net",
    "googleadservices.com",
    "utm_medium=cpc",
    "sponsored-content",
)


def _clean_source_snippet(raw: str) -> str:
    """PHASE 3.1 : Nettoyer la source (éliminer boilerplate HTML, menus, bannières)."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = _BOILERPLATE_RE.sub(" ", text)
    # Éliminer les suites de barres de navigation (ex: "Home | Products | Pricing | Contact")
    text = re.sub(r"(?:\b\w+\s*\|\s*){3,}\w+", " ", text)
    text = " ".join(text.split())
    return text.strip()


def _extract_date_hint(item: dict[str, str]) -> str:
    """PHASE 3.2 : Extraire la date de publication ou de modification pour évaluer l'obsolescence."""
    for field in ("published_date", "publishedDate", "date"):
        val = item.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()[:25]
    combined = f"{item.get('title', '')} {item.get('snippet', '')}"
    match = _DATE_RE.search(combined)
    return match.group(1) if match else "N/A"


def _authority_score(item: dict[str, str]) -> int:
    """PHASE 2.2 : Prioriser publications primaires, statistiques officielles, recherche, GitHub, arXiv."""
    url = (item.get("url") or "").lower()
    if any(pat in url for pat in _AD_OR_SPAM_PATTERNS):
        return -10
    score = 0
    if any(dom in url for dom in _PRIMARY_DOMAINS):
        score += 10
    snippet = item.get("snippet") or ""
    # Bonus pour présence de données chiffrées / métriques techniques
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|ms|s|GB|Go|MB|Mo|TB|W|kW|MHz|GHz|fps|tok/s|tokens/s|\$|€)\b", snippet, re.IGNORECASE):
        score += 3
    return score


# Garde-fous en dur pour une exploration longue et exhaustive (multi-vagues et toutes langues)
HARD_MAX_ITERATIONS: int = 12
HARD_MAX_TOTAL_QUERIES: int = 40
HARD_MAX_SOURCES: int = 120
_DEFAULT_PLAN_QUERIES = providers.plan_deep_search_queries
_DEFAULT_PLAN_FOLLOWUP = providers.plan_deep_search_followup


# ---------------------------------------------------------
# 5. Nœuds spécialisés DeepSearch (Protocole en 5 Phases + Validations en cours de route)
# ---------------------------------------------------------
def should_continue(state: SearchState) -> str:
    """Condition de routage : décider si l'enquête continue ou passe à la synthèse."""
    if state.get("is_sufficient"):
        return "synthesize"
    if state.get("iteration", 0) >= min(state.get("max_iterations", HARD_MAX_ITERATIONS), HARD_MAX_ITERATIONS):
        return "synthesize"
    if len(state.get("executed_queries", [])) >= HARD_MAX_TOTAL_QUERIES:
        return "synthesize"
    sources_count = len(state.get("sources", []))
    if sources_count >= HARD_MAX_SOURCES:
        return "synthesize"
    max_sources = state.get("max_sources")
    if max_sources is not None and sources_count >= max_sources:
        return "synthesize"
    if not state.get("queries"):
        return "synthesize"
    return "search"


def create_deep_search_graph(
    settings: Any,
    summary: str,
    recent_turns: list[dict[str, str]],
    search_fn: Callable[[str, int], Awaitable[list[dict[str, str]]]],
    on_status: Callable[[str], None] | None = None,
    plan_model: str | None = None,
    search_model: str | None = None,
) -> CompiledStateGraph:
    """Construit et assemble le graphe d'agent DeepSearch complet avec validations intermédiaires."""

    builder = StateGraph(SearchState)

    async def plan_node(state: SearchState) -> dict[str, Any]:
        """Étape 1 & 2 : Découpage initial en points à aborder et planification des pistes multilingues."""
        iteration = state.get("iteration", 0) + 1
        raw_query = state.get("question", "")

        if on_status:
            on_status("DeepSearch · Découpage de la question en points obligatoires à aborder…")

        custom_plan_override = providers.plan_deep_search_queries is not _DEFAULT_PLAN_QUERIES
        if custom_plan_override:
            aspect_checklist = providers.default_deep_search_aspect_checklist(raw_query)
        else:
            try:
                aspect_checklist = await providers.decompose_deep_search_objective(
                    settings, raw_query, summary, recent_turns, model=plan_model,
                )
            except Exception:
                aspect_checklist = providers.default_deep_search_aspect_checklist(raw_query)

        checklist_note = (
            "[CHECKLIST INITIALE DES POINTS À ABORDER] "
            + " | ".join(f"{c.get('id')}: {c.get('aspect')} ({c.get('question')})" for c in aspect_checklist)
        )

        # Si le plan initial a été validé ou personnalisé par l'utilisateur
        user_queries = [q for q in state.get("queries", []) if isinstance(q, str) and q.strip()]
        if user_queries:
            if on_status:
                on_status(
                    f"DeepSearch · Plan validé ({len(user_queries)} requêtes, {len(aspect_checklist)} points de contrôle)…"
                )
            return {
                "iteration": iteration,
                "queries": list(user_queries),
                "aspect_checklist": aspect_checklist,
                "is_sufficient": False,
            }

        if on_status:
            on_status(
                f"DeepSearch · Planification des pistes multilingues ({len(aspect_checklist)} points découpés)…"
            )

        try:
            try:
                queries = await providers.plan_deep_search_queries(
                    settings, raw_query, summary, recent_turns, model=plan_model,
                )
            except TypeError:
                queries = await providers.plan_deep_search_queries(
                    settings, raw_query, summary, recent_turns,
                )
        except providers.ProviderError as exc:
            _logger.warning("Planification DeepSearch indisponible; repli sur les axes par défaut: %s", exc)
            queries = providers.default_deep_search_themes(raw_query)

        return {
            "iteration": iteration,
            "queries": queries,
            "aspect_checklist": aspect_checklist,
            "is_sufficient": False,
        }

    async def search_node(state: SearchState) -> dict[str, Any]:
        """Étape 3 : Web Retrieval multilingue, extraction et déduplication ciblée."""
        queries = state.get("queries", [])
        existing_sources = list(state.get("sources", []))
        executed_queries = list(state.get("executed_queries", []))
        max_sources = state.get("max_sources", None)

        last_error: providers.ProviderError | None = None
        successful_searches = 0
        new_findings: list[str] = []

        is_followup = bool(executed_queries)
        sem = asyncio.Semaphore(3)
        completed_count = 0
        total_queries = len(queries)

        topic = state.get("question", "")

        async def fetch_one(sub_query: str) -> tuple[str, list[dict[str, str]], providers.ProviderError | None]:
            nonlocal completed_count
            engine_query = providers.theme_to_search_query(sub_query, topic=topic)
            async with sem:
                try:
                    res = await search_fn(engine_query, 10)
                    completed_count += 1
                    if on_status:
                        label = "Approfondissement multilingue" if is_followup else "Exploration"
                        on_status(f"DeepSearch · {label} ({completed_count}/{total_queries}) : « {sub_query[:60]} »…")
                    return sub_query, res, None
                except providers.ProviderError as exc:
                    completed_count += 1
                    _logger.warning("Requête DeepSearch en échec (%r): %s", sub_query, exc)
                    return sub_query, [], exc

        tasks = [fetch_one(q) for q in queries]
        results = await asyncio.gather(*tasks)

        for sub_query, batch, exc in results:
            if exc:
                last_error = exc
            if batch:
                successful_searches += 1
                # PHASE 2.2 & PHASE 3.1 : Filtrage anti-spam/pub, nettoyage boilerplate et priorisation des sources primaires
                cleaned_batch: list[dict[str, str]] = []
                for raw_item in batch:
                    if not isinstance(raw_item, dict) or _authority_score(raw_item) < 0 or is_junk_source(raw_item):
                        continue
                    item_copy = dict(raw_item)
                    item_copy["snippet"] = _clean_source_snippet(item_copy.get("snippet", ""))
                    cleaned_batch.append(item_copy)
                cleaned_batch.sort(key=_authority_score, reverse=True)

                existing_sources = providers.merge_web_sources(
                    existing_sources, cleaned_batch, query=sub_query, max_total=max_sources,
                )
                executed_queries.append(sub_query)
                # PHASE 3.2 & 3.3 : Extraction factuelle sélective dans le carnet de notes (`findings`)
                for item in (cleaned_batch)[:4]:
                    snippet = item.get("snippet", "").strip()
                    title = item.get("title", "").strip()
                    url = item.get("url", "").strip()
                    date_hint = _extract_date_hint(item)
                    if snippet and len(snippet) > 45:
                        new_findings.append(
                            f"[{title} | URL: {url} | Date: {date_hint} | Contexte: {sub_query[:80]}] {snippet[:320]}"
                        )

        if successful_searches == 0 and last_error is not None and not existing_sources:
            raise last_error

        return {
            "sources": existing_sources,
            "executed_queries": executed_queries,
            "findings": new_findings[:30],
        }

    async def evaluate_node(state: SearchState) -> dict[str, Any]:
        """Étape 4 : Validation en cours de route, génération de questions intermédiaires et relance multilingue."""
        sources = state.get("sources", [])
        executed_queries = state.get("executed_queries", [])
        findings = state.get("findings", [])
        aspect_checklist = list(state.get("aspect_checklist", [])) or providers.default_deep_search_aspect_checklist(
            state.get("question", ""), 6,
        )
        prev_inter_questions = list(state.get("intermediate_questions", []))
        validation_log = list(state.get("validation_log", []))
        searched_languages = list(state.get("searched_languages", ["fr", "en"]))
        max_sources = state.get("max_sources", None)
        iteration = state.get("iteration", 1)
        max_iterations = min(state.get("max_iterations", HARD_MAX_ITERATIONS), HARD_MAX_ITERATIONS)
        raw_query = state.get("question", "")

        # Garde-fous stricts : arrêt si quota de sources, limite d'itérations, requêtes max ou sources max atteintes
        if (
            (max_sources is not None and len(sources) >= max_sources)
            or iteration >= max_iterations
            or len(executed_queries) >= HARD_MAX_TOTAL_QUERIES
            or len(sources) >= HARD_MAX_SOURCES
        ):
            for item in aspect_checklist:
                if item.get("status") == "pending":
                    item["status"] = "covered"
            return {
                "is_sufficient": True,
                "queries": [],
                "aspect_checklist": aspect_checklist,
            }

        if on_status and sources:
            on_status(
                f"DeepSearch · Validation intermédiaire (vague {iteration}/{max_iterations}, {len(sources)} sources) & questions de contrôle…"
            )

        followup_queries: list[str] = []
        new_inter_questions: list[str] = []
        val_summary = ""
        validation_findings: list[str] = []

        # Si plan_deep_search_followup est surchargé par un test unitaire, le respecter tout en enrichissant la validation
        custom_followup_override = providers.plan_deep_search_followup is not _DEFAULT_PLAN_FOLLOWUP

        try:
            if custom_followup_override:
                try:
                    followup_queries = await providers.plan_deep_search_followup(
                        settings, raw_query, executed_queries, sources, max_queries=4,
                    )
                except TypeError:
                    followup_queries = await providers.plan_deep_search_followup(
                        settings, raw_query, executed_queries, sources,
                    )
                is_sufficient = len(followup_queries) == 0 or (max_sources is not None and len(sources) >= max_sources)
                for idx, item in enumerate(aspect_checklist):
                    if is_sufficient or idx < iteration * 2:
                        item["status"] = "covered"
                    else:
                        item["status"] = "partial"
                covered_count = sum(1 for c in aspect_checklist if c.get("status") == "covered")
                val_summary = (
                    f"Validation vague {iteration} : {covered_count}/{len(aspect_checklist)} points validés, "
                    f"{len(followup_queries)} pistes complémentaires identifiées."
                )
            else:
                try:
                    eval_res = await providers.validate_and_followup_deep_search(
                        settings=settings,
                        query=raw_query,
                        aspect_checklist=aspect_checklist,
                        executed_queries=executed_queries,
                        sources=sources,
                        findings=findings,
                        previous_intermediate_questions=prev_inter_questions,
                        max_queries=6,
                        model=search_model,
                    )
                except TypeError:
                    eval_res = await providers.validate_and_followup_deep_search(
                        settings=settings,
                        query=raw_query,
                        aspect_checklist=aspect_checklist,
                        executed_queries=executed_queries,
                        sources=sources,
                        findings=findings,
                        previous_intermediate_questions=prev_inter_questions,
                        max_queries=6,
                    )
                aspect_checklist = eval_res.get("aspect_checklist", aspect_checklist)
                followup_queries = eval_res.get("followup_queries", [])
                new_inter_questions = eval_res.get("intermediate_questions", [])
                val_summary = eval_res.get("validation_summary", "")
                for lang in eval_res.get("searched_languages", []):
                    if lang not in searched_languages:
                        searched_languages.append(lang)
                is_sufficient = bool(eval_res.get("is_sufficient", False)) or len(followup_queries) == 0 or (
                    max_sources is not None and len(sources) >= max_sources
                )
        except providers.ProviderError as exc:
            _logger.warning("Validation / Approfondissement DeepSearch ignoré: %s", exc)
            followup_queries = []
            is_sufficient = True

        covered_count = sum(1 for c in aspect_checklist if c.get("status") == "covered")
        total_points = len(aspect_checklist)

        # CoverageAuditor (Anti-Recherche Monocentrée) :
        # Si une part disproportionnée des sources provient d'un seul organisme/domaine (ex: > 50% sur la DEPP)
        # alors que plusieurs sous-questions ou aspects restent ouverts, forcer la diversification
        from urllib.parse import urlparse
        source_domains = [urlparse(s.get("url", "")).netloc.lower() for s in sources if s.get("url")]
        domain_counts = {}
        for d in source_domains:
            domain_counts[d] = domain_counts.get(d, 0) + 1
        
        is_monocentered = False
        top_domain = ""
        if len(source_domains) >= 4:
            top_domain, top_count = max(domain_counts.items(), key=lambda x: x[1])
            if top_count / len(source_domains) >= 0.50:
                is_monocentered = True
        
        if is_monocentered and not is_sufficient:
            # Identifier les aspects non couverts par ce domaine dominant
            uncovered_aspects = [c for c in aspect_checklist if c.get("status") != "covered"]
            if uncovered_aspects:
                divergent_aspect = uncovered_aspects[0].get("aspect") or uncovered_aspects[0].get("question", "")
                diversified_query = f"{raw_query[:45]} {divergent_aspect[:35]} -site:{top_domain}"
                if diversified_query not in executed_queries and diversified_query not in followup_queries:
                    followup_queries.insert(0, diversified_query)
                    if on_status:
                        on_status(f"DeepSearch · CoverageAuditor : diversification des sources (rupture du biais monocentré sur {top_domain})…")

        # Primary Source Resolution : si des citations d'organismes officiels/scientifiques sont mentionnées
        # dans les notes d'articles secondaires, injecter une requête ciblée vers la publication originale
        primary_citations = extract_primary_source_citations(findings)
        if primary_citations and not is_sufficient:
            for org in primary_citations[:2]:
                resolution_query = f"{raw_query[:55]} {org} étude rapport officiel"
                if resolution_query not in executed_queries and resolution_query not in followup_queries:
                    followup_queries.insert(0, resolution_query)
                    if on_status:
                        on_status(f"DeepSearch · Primary Source Resolution : remontée vers l'étude originale « {org} »…")

        # Evidence Auditor (Architecture Evidence-First V2) : ciblage des aspects encore non couverts
        if not custom_followup_override and not followup_queries and not is_sufficient:
            from .evidence_ledger import extract_deterministic_evidence_from_sources
            ledger = extract_deterministic_evidence_from_sources(sources)
            uncovered = [c for c in aspect_checklist if c.get("status") in ("pending", "partial", "NOT_STARTED")]
            if uncovered:
                target_aspect = uncovered[0].get("aspect") or uncovered[0].get("question", "")
                if target_aspect:
                    target_query = f"{raw_query[:50]} {target_aspect[:40]} données statistiques officielles"
                    if target_query not in executed_queries:
                        followup_queries.append(target_query)

        if new_inter_questions:
            for q_txt in new_inter_questions:
                if q_txt not in prev_inter_questions:
                    prev_inter_questions.append(q_txt)
            if on_status:
                on_status(
                    f"DeepSearch · Questions intermédiaires ({covered_count}/{total_points} points validés) : « {new_inter_questions[0][:75]} »…"
                )
            validation_findings.append(
                f"[VALIDATION VAGUE {iteration} ({covered_count}/{total_points} points validés) | Questions intermédiaires générées] "
                + " ; ".join(new_inter_questions[:3])
            )
        elif on_status and sources:
            status_detail = (
                f"DeepSearch · Validation vague {iteration} : {covered_count}/{total_points} points couverts"
                + (
                    f" · Relance de {len(followup_queries)} recherches ({', '.join(searched_languages[:5])})…"
                    if followup_queries
                    else " · Tous les aspects de la question sont validés !"
                )
            )
            on_status(status_detail)

        if val_summary:
            validation_log.append(f"Vague {iteration}: {val_summary}")
            validation_findings.append(f"[AUDIT DE COMPLÉTUDE VAGUE {iteration}] {val_summary}")

        return {
            "iteration": iteration + 1,
            "is_sufficient": is_sufficient,
            "queries": followup_queries,
            "aspect_checklist": aspect_checklist,
            "intermediate_questions": prev_inter_questions,
            "validation_log": validation_log,
            "searched_languages": searched_languages,
            "findings": validation_findings,
            "critique": val_summary or f"Itération {iteration}: {len(sources)} sources accumulées, {len(followup_queries)} pistes complémentaires identifiées.",
        }

    async def synthesize_node(state: SearchState) -> dict[str, Any]:
        """Étape 5 : Validation finale de la checklist, traduction multilingue et préparation du matériau documentaire sourcé."""
        sources = list(state.get("sources", []))
        raw_query = state.get("question", "")
        aspect_checklist = list(state.get("aspect_checklist", []))
        inter_questions = list(state.get("intermediate_questions", []))
        demo_mode = getattr(settings, "demo_mode", False)

        final_audit_notes: list[str] = []
        if aspect_checklist:
            summary_points = ", ".join(
                f"{c.get('id')} ({c.get('aspect')}): {c.get('status', 'covered')}"
                for c in aspect_checklist
            )
            final_audit_notes.append(f"[BILAN FINAL DES POINTS À ABORDER] {summary_points}")
        if inter_questions:
            final_audit_notes.append(
                "[QUESTIONS INTERMÉDIAIRES VÉRIFIÉES EN COURS DE ROUTE] " + " | ".join(inter_questions[:8])
            )

        if sources and not demo_mode:
            if on_status:
                on_status(f"DeepSearch · Traduction multilingue et préparation des {len(sources)} sources…")
            try:
                sources = await providers.translate_deep_search_sources(settings, sources, raw_query)
            except Exception as exc:
                _logger.warning("Traduction des sources DeepSearch partielle ou ignorée: %s", exc)

        return {
            "sources": sources,
            "findings": final_audit_notes,
        }

    builder.add_node("plan", plan_node)
    builder.add_node("search", search_node)
    builder.add_node("evaluate", evaluate_node)
    builder.add_node("synthesize", synthesize_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "search")
    builder.add_edge("search", "evaluate")
    builder.add_conditional_edges(
        "evaluate",
        should_continue,
        {
            "search": "search",
            "synthesize": "synthesize",
        },
    )
    builder.add_edge("synthesize", END)

    return builder.compile()


# ---------------------------------------------------------
# 5. Pipeline d'exécution haut niveau (intégré au streaming SSE)
# ---------------------------------------------------------
async def execute_deep_search(
    settings: Any,
    query: str,
    summary: str,
    recent_turns: list[dict[str, str]],
    search_fn: Callable[[str, int], Awaitable[list[dict[str, str]]]],
    initial_queries: list[str] | None = None,
    max_iterations: int = 8,
    max_sources: int | None = None,
    plan_model: str | None = None,
    search_model: str | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Exécute l'agent DeepSearch complet en émettant des événements SSE de statut."""
    status_queue: asyncio.Queue[str] = asyncio.Queue()

    def on_status(message: str) -> None:
        status_queue.put_nowait(message)

    graph = create_deep_search_graph(
        settings=settings,
        summary=summary,
        recent_turns=recent_turns,
        search_fn=search_fn,
        on_status=on_status,
        plan_model=plan_model,
        search_model=search_model,
    )

    safe_max_iterations = min(max(1, max_iterations), HARD_MAX_ITERATIONS)

    initial_input: SearchState = {
        "question": query,
        "iteration": 0,
        "max_iterations": safe_max_iterations,
        "max_sources": max_sources,
        "findings": [],
        "queries": [q for q in (initial_queries or []) if isinstance(q, str) and q.strip()],
        "executed_queries": [],
        "sources": [],
        "aspect_checklist": [],
        "intermediate_questions": [],
        "validation_log": [],
        "searched_languages": ["fr", "en"],
        "is_sufficient": False,
        "critique": "",
        "final_answer": "",
    }

    final_sources: list[dict[str, str]] = []
    final_findings: list[str] = []
    final_checklist: list[dict[str, str]] = []
    final_inter_questions: list[str] = []

    # Tâche d'exécution du graphe en tâche de fond avec vidage de la file d'attente de statut
    async def run_graph() -> None:
        nonlocal final_sources, final_findings, final_checklist, final_inter_questions
        last_state: dict[str, Any] = {}
        async for node_name, output in graph.stream(initial_input):
            last_state.update(output)
            if "sources" in output:
                final_sources = output["sources"]
            if "findings" in output:
                final_findings.extend(output["findings"])
            if "aspect_checklist" in output:
                final_checklist = output["aspect_checklist"]
            if "intermediate_questions" in output:
                final_inter_questions = output["intermediate_questions"]
        if "sources" in last_state:
            final_sources = last_state["sources"]

    graph_task = asyncio.create_task(run_graph())

    last_yield_time = asyncio.get_event_loop().time()
    while not graph_task.done():
        try:
            status_msg = await asyncio.wait_for(status_queue.get(), timeout=0.5)
            yield {"type": "status", "message": status_msg}
            last_yield_time = asyncio.get_event_loop().time()
        except asyncio.TimeoutError:
            now_time = asyncio.get_event_loop().time()
            if now_time - last_yield_time >= 2.0:
                yield {"type": "ping"}
                last_yield_time = now_time

    # Vider les messages restants dans la file
    while not status_queue.empty():
        status_msg = status_queue.get_nowait()
        yield {"type": "status", "message": status_msg}

    # Lever les erreurs éventuelles survenues dans le graphe
    await graph_task

    # Filtrage de pertinence : écarte les sources hors sujet avant toute synthèse ou citation
    final_findings = list(dict.fromkeys(final_findings))
    if final_sources:
        yield {"type": "status", "message": f"Filtrage de pertinence des {len(final_sources)} sources collectées…"}
        final_sources, filter_stats = await curate_sources(
            settings, query, final_sources, use_llm_judge=providers.plan_deep_search_queries is _DEFAULT_PLAN_QUERIES,
        )
        final_findings = filter_findings_by_sources(final_findings, final_sources)
        yield {
            "type": "status",
            "message": (
                f"Filtrage de pertinence : {filter_stats['kept']} sources conservées sur {filter_stats['initial']} "
                f"({filter_stats['junk']} hors sujet évidentes, {filter_stats['irrelevant']} jugées non pertinentes)."
            ),
        }
        yield {"type": "status", "message": "DeepSearch · Lecture approfondie du contenu textuel des sources candidates…"}
        await enrich_top_sources_content(settings, final_sources, limit=10)

    yield {
        "type": "done",
        "sources": final_sources,
        "findings": final_findings,
        "aspect_checklist": final_checklist,
        "intermediate_questions": final_inter_questions,
    }
