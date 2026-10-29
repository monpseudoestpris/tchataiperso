"""
LearnMode — Architecture itérative de conception de cours approfondis et structurés (StateGraph Agent).

Inspiré de l'architecture par graphe d'états (StateGraph) :
1. Planification pédagogique & Décomposition en 5 axes (Plan Node)
2. Génération de requêtes didactiques et supports de cours (Query Generation)
3. Extraction, lecture ciblée et carnet de notes pédagogique (Web Retrieval & Reranking)
4. Audit pédagogique et réévaluation de complétude (Evaluation Node)
5. Traduction multilingue et organisation des supports didactiques (Synthesize Node)
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
from .source_filter import (
    PRIMARY_DOMAINS,
    curate_sources,
    enrich_top_sources_content,
    extract_primary_source_citations,
    filter_findings_by_sources,
    is_junk_source,
    prefilter_sources,
)

_logger = logging.getLogger("clair.learn_mode")

START = "__start__"
END = "__end__"

# Garde-fous étendus pour permettre une exploration longue, multilingue et exhaustive du cours
HARD_MAX_ITERATIONS = 12
HARD_MAX_TOTAL_QUERIES = 40
HARD_MAX_SOURCES = 160

_DEFAULT_PLAN_LEARN_FOLLOWUP = providers.plan_learn_followup


class LearnState(TypedDict, total=False):
    question: str
    iteration: int
    max_iterations: int
    max_sources: int | None
    findings: Annotated[List[str], operator.add]  # Carnet de notes didactique
    queries: List[str]
    executed_queries: List[str]
    sources: List[dict[str, str]]
    aspect_checklist: List[dict[str, str]]
    intermediate_questions: List[str]
    validation_log: List[str]
    searched_languages: List[str]
    is_sufficient: bool
    critique: str
    final_answer: str


class EvaluationOutput(BaseModel):
    is_sufficient: bool = Field(
        default=False,
        description="True si les supports réunis suffisent pour rédiger un cours complet, False sinon.",
    )
    critique: str = Field(
        default="",
        description="Analyse des éléments didactiques acquis ou lacunes restantes.",
    )
    extracted_findings: List[str] = Field(
        default_factory=list,
        description="Faits saillants, définitions et exemples clés extraits des supports.",
    )
    next_queries: List[str] = Field(
        default_factory=list,
        description="1 à 3 requêtes très précises pour combler les manques du cours.",
    )


class StateGraph:
    """Moteur de graphe d'états orienté agent pour le Mode Apprendre."""

    def __init__(self, state_schema: type):
        self.state_schema = state_schema
        self.nodes: dict[str, Callable[[LearnState], Awaitable[dict[str, Any]]]] = {}
        self.edges: dict[str, str] = {}
        self.conditional_edges: dict[str, tuple[Callable[[LearnState], str], dict[str, str]]] = {}

    def add_node(self, name: str, fn: Callable[[LearnState], Awaitable[dict[str, Any]]]) -> None:
        self.nodes[name] = fn

    def add_edge(self, from_node: str, to_node: str) -> None:
        self.edges[from_node] = to_node

    def add_conditional_edges(
        self,
        from_node: str,
        router: Callable[[LearnState], str],
        mapping: dict[str, str],
    ) -> None:
        self.conditional_edges[from_node] = (router, mapping)

    def compile(self) -> CompiledStateGraph:
        return CompiledStateGraph(self)


class CompiledStateGraph:
    def __init__(self, graph: StateGraph):
        self.graph = graph

    async def stream(self, initial_state: LearnState) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
        current_state: LearnState = dict(initial_state)
        current_node = self.graph.edges.get(START)

        while current_node and current_node != END:
            node_fn = self.graph.nodes.get(current_node)
            if not node_fn:
                break

            output = await node_fn(current_state)
            for k, v in output.items():
                if k == "findings" and "findings" in current_state:
                    current_state["findings"] = list(dict.fromkeys(current_state["findings"] + v))
                elif k == "sources" and "sources" in current_state:
                    current_state["sources"] = v
                else:
                    current_state[k] = v

            yield current_node, output

            if current_node in self.graph.conditional_edges:
                router, mapping = self.graph.conditional_edges[current_node]
                route = router(current_state)
                current_node = mapping.get(route, END)
            else:
                current_node = self.graph.edges.get(current_node, END)


def _authority_score(item: dict[str, Any]) -> int:
    """Priorise les publications primaires, statistiques officielles, institutions académiques et documentations de référence."""
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    score = 0

    if any(p in url for p in PRIMARY_DOMAINS):
        score += 10
    if any(ext in url for ext in [".edu", ".gov", "arxiv.org", "wikipedia.org", "github.com", "docs.", "mdn.", "developer.mozilla"]):
        score += 8
    if any(k in url for k in ["coursera", "edx", "mit.edu", "stanford.edu", "inria.fr", "cnrs.fr", "college-de-france.fr", "openclassrooms"]):
        score += 7
    if any(k in title for k in ["cours", "tutoriel", "guide", "introduction", "tutorial", "course", "handbook", "manual", "exercices"]):
        score += 5
    if any(k in snippet for k in ["définition", "principe", "exemple", "fonctionnement", "architecture", "code", "exercices", "méthode"]):
        score += 3
    # Seuls les traqueurs publicitaires avérés ou faux liens sont pénalisés négativement
    if any(bad in url for bad in ["doubleclick.net", "googleadservices.com", "utm_medium=cpc", "sponsored-content", "ad-tracker"]):
        score -= 10
    return score


def _clean_source_snippet(raw_text: str) -> str:
    """Nettoie le texte des balises, navigation et bannières."""
    if not raw_text:
        return ""
    text = re.sub(r"<!--.*?-->", "", raw_text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(
        r"(accepter tous les cookies|politique de confidentialité|tous droits réservés|nous utilisons des cookies|cookie policy|privacy policy|terms of service)",
        "", text, flags=re.IGNORECASE
    )
    text = " ".join(text.split())
    return text.strip()


def _extract_date_hint(item: dict[str, str]) -> str:
    """Extrait une date de publication approximative."""
    text = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('url', '')}"
    m = re.search(r"\b(202[0-6])\b", text)
    return m.group(1) if m else "Récent"


def should_continue(state: LearnState) -> str:
    """Détermine si le graphe doit collecter d'autres supports ou passer à la synthèse."""
    iteration = state.get("iteration", 1)
    max_iterations = min(state.get("max_iterations", HARD_MAX_ITERATIONS), HARD_MAX_ITERATIONS)
    max_sources = state.get("max_sources", None)
    sources_count = len(state.get("sources", []))
    executed_queries_count = len(state.get("executed_queries", []))

    if iteration >= max_iterations:
        return "synthesize"
    if executed_queries_count >= HARD_MAX_TOTAL_QUERIES or sources_count >= HARD_MAX_SOURCES:
        return "synthesize"
    if state.get("is_sufficient", False):
        return "synthesize"
    if max_sources is not None and sources_count >= max_sources:
        return "synthesize"
    if not state.get("queries"):
        return "synthesize"
    return "search"


def create_learn_graph(
    settings: Any,
    summary: str,
    recent_turns: list[dict[str, str]],
    search_fn: Callable[[str, int], Awaitable[list[dict[str, str]]]],
    on_status: Callable[[str], None] | None = None,
    plan_model: str | None = None,
    search_model: str | None = None,
) -> CompiledStateGraph:
    """Construit et assemble le graphe complet du Mode Apprendre."""

    builder = StateGraph(LearnState)

    async def plan_node(state: LearnState) -> dict[str, Any]:
        """Étape 1 & 2 : Découpage initial en points pédagogiques obligatoires et planification multilingue du cours."""
        iteration = state.get("iteration", 0) + 1
        raw_query = state.get("question", "")

        aspect_checklist = list(state.get("aspect_checklist", []))
        if not aspect_checklist:
            if on_status:
                on_status("Mode Apprendre · Découpage du sujet en points pédagogiques obligatoires à valider…")
            try:
                aspect_checklist = await providers.decompose_learn_objective(
                    settings, raw_query, summary, recent_turns, model=plan_model,
                )
            except Exception as exc:
                _logger.warning("Découpage initial Mode Apprendre en repli par défaut: %s", exc)
                aspect_checklist = providers.default_learn_aspect_checklist(raw_query)

        user_queries = [q for q in state.get("queries", []) if isinstance(q, str) and q.strip()]
        if user_queries:
            if on_status:
                on_status(
                    f"Mode Apprendre · Plan validé ({len(user_queries)} modules, {len(aspect_checklist)} points de contrôle)…"
                )
            return {
                "iteration": iteration,
                "queries": list(user_queries),
                "aspect_checklist": aspect_checklist,
                "is_sufficient": False,
            }

        if on_status:
            on_status(
                f"Mode Apprendre · Conception du plan de cours multilingue ({len(aspect_checklist)} points découpés)…"
            )

        try:
            try:
                queries = await providers.plan_learn_queries(
                    settings, raw_query, summary, recent_turns, model=plan_model,
                )
            except TypeError:
                queries = await providers.plan_learn_queries(
                    settings, raw_query, summary, recent_turns,
                )
        except providers.ProviderError as exc:
            _logger.warning("Planification Mode Apprendre indisponible; repli sur les modules par défaut: %s", exc)
            queries = providers.default_learn_themes(raw_query)

        return {
            "iteration": iteration,
            "queries": queries,
            "aspect_checklist": aspect_checklist,
            "is_sufficient": False,
        }

    async def search_node(state: LearnState) -> dict[str, Any]:
        """Étape 3 : Collecte des supports de cours et extraction des points clés."""
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
                        label = "Approfondissement pédagogique" if is_followup else "Collecte des supports"
                        on_status(f"Mode Apprendre · {label} ({completed_count}/{total_queries}) : « {sub_query[:60]} »…")
                    return sub_query, res, None
                except providers.ProviderError as exc:
                    completed_count += 1
                    _logger.warning("Requête cours en échec (%r): %s", sub_query, exc)
                    return sub_query, [], exc

        tasks = [fetch_one(q) for q in queries]
        results = await asyncio.gather(*tasks)

        for sub_query, batch, exc in results:
            if exc:
                last_error = exc
            if batch:
                successful_searches += 1
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

                for item in (cleaned_batch)[:4]:
                    snippet = item.get("snippet", "").strip()
                    title = item.get("title", "").strip()
                    url = item.get("url", "").strip()
                    date_hint = _extract_date_hint(item)
                    if snippet and len(snippet) > 45:
                        new_findings.append(
                            f"[{title} | URL: {url} | Date: {date_hint} | Module: {sub_query[:80]}] {snippet[:320]}"
                        )

        if successful_searches == 0 and last_error is not None and not existing_sources:
            raise last_error

        return {
            "sources": existing_sources,
            "executed_queries": executed_queries,
            "findings": new_findings[:25],
        }

    async def evaluate_node(state: LearnState) -> dict[str, Any]:
        """Étape 4 : Validation pédagogique en cours de route, questions intermédiaires et relance multilingue."""
        sources = state.get("sources", [])
        executed_queries = state.get("executed_queries", [])
        findings = state.get("findings", [])
        aspect_checklist = list(state.get("aspect_checklist", [])) or providers.default_learn_aspect_checklist(
            state.get("question", ""),
        )
        prev_inter_questions = list(state.get("intermediate_questions", []))
        validation_log = list(state.get("validation_log", []))
        searched_languages = list(state.get("searched_languages", ["fr", "en"]))
        max_sources = state.get("max_sources", None)
        iteration = state.get("iteration", 1)
        max_iterations = min(state.get("max_iterations", HARD_MAX_ITERATIONS), HARD_MAX_ITERATIONS)
        raw_query = state.get("question", "")

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
                f"Mode Apprendre · Validation intermédiaire (vague {iteration}/{max_iterations}, {len(sources)} supports) & questions de contrôle…"
            )

        followup_queries: list[str] = []
        new_inter_questions: list[str] = []
        val_summary = ""
        validation_findings: list[str] = []

        custom_followup_override = providers.plan_learn_followup is not _DEFAULT_PLAN_LEARN_FOLLOWUP

        try:
            if custom_followup_override:
                try:
                    followup_queries = await providers.plan_learn_followup(
                        settings, raw_query, executed_queries, sources, max_queries=4,
                    )
                except TypeError:
                    followup_queries = await providers.plan_learn_followup(
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
                    f"{len(followup_queries)} compléments didactiques identifiés."
                )
            else:
                try:
                    eval_res = await providers.validate_and_followup_learn(
                        settings=settings,
                        query=raw_query,
                        aspect_checklist=aspect_checklist,
                        executed_queries=executed_queries,
                        sources=sources,
                        findings=[{"sub_query": "", "summary": f} if isinstance(f, str) else f for f in findings],
                        previous_intermediate_questions=prev_inter_questions,
                        max_queries=6,
                        model=search_model,
                    )
                except TypeError:
                    eval_res = await providers.validate_and_followup_learn(
                        settings=settings,
                        query=raw_query,
                        aspect_checklist=aspect_checklist,
                        executed_queries=executed_queries,
                        sources=sources,
                        findings=[{"sub_query": "", "summary": f} if isinstance(f, str) else f for f in findings],
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
            _logger.warning("Validation / Approfondissement Mode Apprendre ignoré: %s", exc)
            followup_queries = []
            is_sufficient = True

        covered_count = sum(1 for c in aspect_checklist if c.get("status") == "covered")
        total_points = len(aspect_checklist)

        # Primary Source Resolution : si des citations d'organismes officiels/scientifiques sont mentionnées
        # dans les notes de supports secondaires, injecter une requête ciblée vers la publication originale
        primary_citations = extract_primary_source_citations(findings)
        if primary_citations and not is_sufficient:
            for org in primary_citations[:2]:
                resolution_query = f"{raw_query[:55]} {org} cours étude officiel"
                if resolution_query not in executed_queries and resolution_query not in followup_queries:
                    followup_queries.insert(0, resolution_query)
                    if on_status:
                        on_status(f"Mode Apprendre · Primary Source Resolution : remontée vers les travaux originaux de « {org} »…")

        # Evidence Auditor (Architecture Evidence-First V2) : ciblage des aspects encore non couverts
        if not custom_followup_override and not followup_queries and not is_sufficient:
            from .evidence_ledger import extract_deterministic_evidence_from_sources
            ledger = extract_deterministic_evidence_from_sources(sources)
            uncovered = [c for c in aspect_checklist if c.get("status") in ("pending", "partial", "NOT_STARTED")]
            if uncovered:
                target_aspect = uncovered[0].get("aspect") or uncovered[0].get("question", "")
                if target_aspect:
                    target_query = f"{raw_query[:50]} {target_aspect[:40]} cours définitions exemples"
                    if target_query not in executed_queries:
                        followup_queries.append(target_query)

        if new_inter_questions:
            for q_txt in new_inter_questions:
                if q_txt not in prev_inter_questions:
                    prev_inter_questions.append(q_txt)
            if on_status:
                on_status(
                    f"Mode Apprendre · Questions intermédiaires ({covered_count}/{total_points} points validés) : « {new_inter_questions[0][:75]} »…"
                )
            validation_findings.append(
                f"[VALIDATION PÉDAGOGIQUE VAGUE {iteration} ({covered_count}/{total_points} points validés) | Questions intermédiaires générées] "
                + " ; ".join(new_inter_questions[:3])
            )
        elif on_status and sources:
            status_detail = (
                f"Mode Apprendre · Validation vague {iteration} : {covered_count}/{total_points} points couverts"
                + (
                    f" · Relance de {len(followup_queries)} recherches ({', '.join(searched_languages[:5])})…"
                    if followup_queries
                    else " · Tous les aspects du cours sont validés !"
                )
            )
            on_status(status_detail)

        if val_summary:
            validation_log.append(f"Vague {iteration}: {val_summary}")
            validation_findings.append(f"[AUDIT PÉDAGOGIQUE VAGUE {iteration}] {val_summary}")

        return {
            "iteration": iteration + 1,
            "is_sufficient": is_sufficient,
            "queries": followup_queries,
            "aspect_checklist": aspect_checklist,
            "intermediate_questions": prev_inter_questions,
            "validation_log": validation_log,
            "searched_languages": searched_languages,
            "findings": validation_findings,
            "critique": val_summary or f"Itération {iteration}: {len(sources)} supports accumulés, {len(followup_queries)} compléments didactiques demandés.",
        }

    async def synthesize_node(state: LearnState) -> dict[str, Any]:
        """Étape 5 : Validation finale de la checklist pédagogique, traduction multilingue et organisation des supports."""
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
            final_audit_notes.append(f"[BILAN FINAL DES POINTS PÉDAGOGIQUES À ABORDER] {summary_points}")
        if inter_questions:
            final_audit_notes.append(
                "[QUESTIONS INTERMÉDIAIRES PÉDAGOGIQUES VÉRIFIÉES EN COURS DE ROUTE] " + " | ".join(inter_questions[:8])
            )

        if sources and not demo_mode:
            if on_status:
                on_status(f"Mode Apprendre · Traduction et organisation des {len(sources)} supports pédagogiques…")
            try:
                sources = await providers.translate_deep_search_sources(settings, sources, raw_query)
            except Exception as exc:
                _logger.warning("Traduction des supports de cours partielle ou ignorée: %s", exc)

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


async def execute_learn_mode(
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
    """Exécute l'agent de cours complet en émettant des événements SSE de statut."""
    status_queue: asyncio.Queue[str] = asyncio.Queue()

    def on_status(message: str) -> None:
        status_queue.put_nowait(message)

    graph = create_learn_graph(
        settings=settings,
        summary=summary,
        recent_turns=recent_turns,
        search_fn=search_fn,
        on_status=on_status,
        plan_model=plan_model,
        search_model=search_model,
    )

    safe_max_iterations = min(max(1, max_iterations), HARD_MAX_ITERATIONS)

    initial_input: LearnState = {
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

    while not status_queue.empty():
        status_msg = status_queue.get_nowait()
        yield {"type": "status", "message": status_msg}

    await graph_task

    # Filtrage de pertinence : écarte les sources hors sujet avant toute synthèse ou citation
    final_findings = list(dict.fromkeys(final_findings))
    if final_sources:
        yield {"type": "status", "message": f"Filtrage de pertinence des {len(final_sources)} sources collectées…"}
        final_sources, filter_stats = await curate_sources(
            settings, query, final_sources, use_llm_judge=providers.plan_learn_followup is _DEFAULT_PLAN_LEARN_FOLLOWUP, learn_mode=True,
        )
        final_findings = filter_findings_by_sources(final_findings, final_sources)
        yield {
            "type": "status",
            "message": (
                f"Filtrage de pertinence : {filter_stats['kept']} sources conservées sur {filter_stats['initial']} "
                f"({filter_stats['junk']} hors sujet évidentes, {filter_stats['irrelevant']} jugées non pertinentes)."
            ),
        }
        yield {"type": "status", "message": "Mode Apprendre · Lecture approfondie des supports didactiques de référence…"}
        await enrich_top_sources_content(settings, final_sources, limit=10)

    yield {
        "type": "done",
        "sources": final_sources,
        "findings": final_findings,
        "aspect_checklist": final_checklist,
        "intermediate_questions": final_inter_questions,
    }

