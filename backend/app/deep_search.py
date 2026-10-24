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
    next_queries: List[str] = Field(
        default_factory=list,
        description="1 à 3 requêtes très précises pour combler les manques ou contre-vérifier.",
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
_PRIMARY_DOMAINS = (
    "github.com",
    "arxiv.org",
    "huggingface.co",
    "docs.",
    "developer.",
    "ietf.org",
    "w3.org",
    "ieee.org",
    "acm.org",
    "nature.com",
    "science.org",
    ".gov",
    ".edu",
)
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
    """PHASE 2.2 : Prioriser documentation officielle, GitHub, arXiv et audits indépendants."""
    url = (item.get("url") or "").lower()
    if any(pat in url for pat in _AD_OR_SPAM_PATTERNS):
        return -10
    score = 0
    if any(dom in url for dom in _PRIMARY_DOMAINS):
        score += 5
    snippet = item.get("snippet") or ""
    # Bonus pour présence de données chiffrées / métriques techniques
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:%|ms|s|GB|Go|MB|Mo|TB|W|kW|MHz|GHz|fps|tok/s|tokens/s|\$|€)\b", snippet, re.IGNORECASE):
        score += 3
    return score


# Garde-fous stricts en dur (protection contre les boucles infinies et explosion de tokens)
HARD_MAX_ITERATIONS: int = 5
HARD_MAX_TOTAL_QUERIES: int = 24
HARD_MAX_SOURCES: int = 120


# ---------------------------------------------------------
# 5. Nœuds spécialisés DeepSearch (Protocole en 5 Phases)
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
) -> CompiledStateGraph:
    """Construit et assemble le graphe d'agent DeepSearch complet."""

    builder = StateGraph(SearchState)

    async def plan_node(state: SearchState) -> dict[str, Any]:
        """Étape 1 & 2 : Planification et décomposition initiale."""
        iteration = state.get("iteration", 0) + 1
        raw_query = state.get("question", "")

        # Si le plan initial a été validé ou personnalisé par l'utilisateur
        user_queries = [q for q in state.get("queries", []) if isinstance(q, str) and q.strip()]
        if user_queries:
            if on_status:
                on_status(f"DeepSearch · Plan validé par l'utilisateur ({len(user_queries)} requêtes)…")
            return {
                "iteration": iteration,
                "queries": list(user_queries),
                "is_sufficient": False,
            }

        if on_status:
            on_status("DeepSearch · Planification des pistes multilingues…")

        try:
            try:
                queries = await providers.plan_deep_search_queries(
                    settings, raw_query, summary, recent_turns, max_queries=8,
                )
            except TypeError:
                queries = await providers.plan_deep_search_queries(
                    settings, raw_query, summary, recent_turns,
                )
        except providers.ProviderError as exc:
            _logger.warning("Planification DeepSearch indisponible; repli sur question directe: %s", exc)
            queries = [raw_query]

        return {
            "iteration": iteration,
            "queries": queries,
            "is_sufficient": False,
        }

    async def search_node(state: SearchState) -> dict[str, Any]:
        """Étape 3 : Web Retrieval, extraction et déduplication ciblée."""
        queries = state.get("queries", [])
        existing_sources = list(state.get("sources", []))
        executed_queries = list(state.get("executed_queries", []))
        max_sources = state.get("max_sources", None)
        iteration = state.get("iteration", 1)

        last_error: providers.ProviderError | None = None
        successful_searches = 0
        new_findings: list[str] = []

        is_followup = bool(executed_queries)
        sem = asyncio.Semaphore(3)
        completed_count = 0
        total_queries = len(queries)

        async def fetch_one(sub_query: str) -> tuple[str, list[dict[str, str]], providers.ProviderError | None]:
            nonlocal completed_count
            async with sem:
                try:
                    res = await search_fn(sub_query, 10)
                    completed_count += 1
                    if on_status:
                        label = "Approfondissement" if is_followup else "Exploration"
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
                # PHASE 3.2 & 3.3 : Extraction factuelle sélective dans le carnet de notes (`findings`)
                # Associer systématiquement : URL source exacte, date de publication/modification et contexte technique
                for item in (cleaned_batch or batch)[:4]:
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
            "findings": new_findings[:25],
        }

    async def evaluate_node(state: SearchState) -> dict[str, Any]:
        """Étape 4 : Raisonnement itératif, croisement et détection de contradictions (Re-thinking)."""
        sources = state.get("sources", [])
        executed_queries = state.get("executed_queries", [])
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
            return {"is_sufficient": True, "queries": []}

        if on_status and sources:
            on_status(f"DeepSearch · Analyse de {len(sources)} sources et vérification de complétude…")

        try:
            try:
                followup_queries = await providers.plan_deep_search_followup(
                    settings, raw_query, executed_queries, sources, max_queries=4,
                )
            except TypeError:
                followup_queries = await providers.plan_deep_search_followup(
                    settings, raw_query, executed_queries, sources,
                )
        except providers.ProviderError as exc:
            _logger.warning("Approfondissement DeepSearch ignoré: %s", exc)
            followup_queries = []

        is_sufficient = len(followup_queries) == 0 or (max_sources is not None and len(sources) >= max_sources)

        return {
            "iteration": iteration + 1,
            "is_sufficient": is_sufficient,
            "queries": followup_queries,
            "critique": f"Itération {iteration}: {len(sources)} sources accumulées, {len(followup_queries)} pistes complémentaires identifiées.",
        }

    async def synthesize_node(state: SearchState) -> dict[str, Any]:
        """Étape 5 : Traduction multilingue et préparation du matériau documentaire sourcé."""
        sources = list(state.get("sources", []))
        raw_query = state.get("question", "")
        demo_mode = getattr(settings, "demo_mode", False)

        if sources and not demo_mode:
            if on_status:
                on_status(f"DeepSearch · Traduction et préparation des {len(sources)} sources…")
            try:
                sources = await providers.translate_deep_search_sources(settings, sources, raw_query)
            except Exception as exc:
                _logger.warning("Traduction des sources DeepSearch partielle ou ignorée: %s", exc)

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
    max_iterations: int = 5,
    max_sources: int | None = None,
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
        "is_sufficient": False,
        "critique": "",
        "final_answer": "",
    }

    final_sources: list[dict[str, str]] = []
    final_findings: list[str] = []

    # Tâche d'exécution du graphe en tâche de fond avec vidage de la file d'attente de statut
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

    # Vider les messages restants dans la file
    while not status_queue.empty():
        status_msg = status_queue.get_nowait()
        yield {"type": "status", "message": status_msg}

    # Lever les erreurs éventuelles survenues dans le graphe
    await graph_task

    yield {
        "type": "done",
        "sources": final_sources,
        "findings": list(dict.fromkeys(final_findings)),
    }
