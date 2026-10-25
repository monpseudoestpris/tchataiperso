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

_logger = logging.getLogger("clair.learn_mode")

START = "__start__"
END = "__end__"

# Garde-fous stricts
HARD_MAX_ITERATIONS = 5
HARD_MAX_TOTAL_QUERIES = 24
HARD_MAX_SOURCES = 120


class LearnState(TypedDict, total=False):
    question: str
    iteration: int
    max_iterations: int
    max_sources: int | None
    findings: Annotated[List[str], operator.add]  # Carnet de notes didactique
    queries: List[str]
    executed_queries: List[str]
    sources: List[dict[str, str]]
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
    """Priorise les domaines pédagogiques, de référence, universitaires et documentations officielles."""
    url = (item.get("url") or "").lower()
    title = (item.get("title") or "").lower()
    snippet = (item.get("snippet") or "").lower()
    score = 0

    if any(ext in url for ext in [".edu", ".gov", "arxiv.org", "wikipedia.org", "github.com", "docs.", "mdn.", "developer.mozilla"]):
        score += 8
    if any(k in url for k in ["coursera", "edx", "mit.edu", "stanford.edu", "inria.fr", "cnrs.fr", "college-de-france.fr", "openclassrooms"]):
        score += 7
    if any(k in title for k in ["cours", "tutoriel", "guide", "introduction", "tutorial", "course", "handbook", "manual", "exercices"]):
        score += 5
    if any(k in snippet for k in ["définition", "principe", "exemple", "fonctionnement", "architecture", "code", "exercices", "méthode"]):
        score += 3
    if any(bad in url for bad in ["pinterest", "quora", "facebook", "tiktok", "instagram", "ad.", "sponsor"]):
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
) -> CompiledStateGraph:
    """Construit et assemble le graphe complet du Mode Apprendre."""

    builder = StateGraph(LearnState)

    async def plan_node(state: LearnState) -> dict[str, Any]:
        """Étape 1 & 2 : Planification du cours et axes pédagogiques."""
        iteration = state.get("iteration", 0) + 1
        raw_query = state.get("question", "")

        user_queries = [q for q in state.get("queries", []) if isinstance(q, str) and q.strip()]
        if user_queries:
            if on_status:
                on_status(f"Mode Apprendre · Plan validé ({len(user_queries)} modules de recherche)…")
            return {
                "iteration": iteration,
                "queries": list(user_queries),
                "is_sufficient": False,
            }

        if on_status:
            on_status("Mode Apprendre · Conception du plan de cours et des axes pédagogiques…")

        try:
            try:
                queries = await providers.plan_learn_queries(
                    settings, raw_query, summary, recent_turns, max_queries=8,
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
                    if not isinstance(raw_item, dict) or _authority_score(raw_item) < 0:
                        continue
                    item_copy = dict(raw_item)
                    item_copy["snippet"] = _clean_source_snippet(item_copy.get("snippet", ""))
                    cleaned_batch.append(item_copy)
                cleaned_batch.sort(key=_authority_score, reverse=True)

                existing_sources = providers.merge_web_sources(
                    existing_sources, cleaned_batch or batch, query=sub_query, max_total=max_sources,
                )
                executed_queries.append(sub_query)

                for item in (cleaned_batch or batch)[:4]:
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
        """Étape 4 : Audit pédagogique des supports et complétude du contenu."""
        sources = state.get("sources", [])
        executed_queries = state.get("executed_queries", [])
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
            return {"is_sufficient": True, "queries": []}

        if on_status and sources:
            on_status(f"Mode Apprendre · Audit pédagogique de {len(sources)} supports et vérification de complétude…")

        try:
            try:
                followup_queries = await providers.plan_learn_followup(
                    settings, raw_query, executed_queries, sources, max_queries=4,
                )
            except TypeError:
                followup_queries = await providers.plan_learn_followup(
                    settings, raw_query, executed_queries, sources,
                )
        except providers.ProviderError as exc:
            _logger.warning("Approfondissement Mode Apprendre ignoré: %s", exc)
            followup_queries = []

        is_sufficient = len(followup_queries) == 0 or (max_sources is not None and len(sources) >= max_sources)

        return {
            "iteration": iteration + 1,
            "is_sufficient": is_sufficient,
            "queries": followup_queries,
            "critique": f"Itération {iteration}: {len(sources)} supports accumulés, {len(followup_queries)} compléments didactiques demandés.",
        }

    async def synthesize_node(state: LearnState) -> dict[str, Any]:
        """Étape 5 : Traduction multilingue et structuration pédagogique finale."""
        sources = list(state.get("sources", []))
        raw_query = state.get("question", "")
        demo_mode = getattr(settings, "demo_mode", False)

        if sources and not demo_mode:
            if on_status:
                on_status(f"Mode Apprendre · Traduction et organisation des {len(sources)} supports pédagogiques…")
            try:
                sources = await providers.translate_deep_search_sources(settings, sources, raw_query)
            except Exception as exc:
                _logger.warning("Traduction des supports de cours partielle ou ignorée: %s", exc)

        return {"sources": sources}

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
    max_iterations: int = 5,
    max_sources: int | None = None,
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
        "is_sufficient": False,
        "critique": "",
        "final_answer": "",
    }

    final_sources: list[dict[str, str]] = []
    final_findings: list[str] = []

    async def run_graph() -> None:
        nonlocal final_sources, final_findings
        last_state: dict[str, Any] = {}
        async for node_name, output in graph.stream(initial_input):
            last_state.update(output)
            if "sources" in output:
                final_sources = output["sources"]
            if "findings" in output:
                final_findings.extend(output["findings"])
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

    yield {
        "type": "done",
        "sources": final_sources,
        "findings": list(dict.fromkeys(final_findings)),
    }

