import asyncio
import pytest
from app.config import Settings
from app.deep_search import (
    END,
    START,
    CompiledStateGraph,
    EvaluationOutput,
    SearchState,
    StateGraph,
    create_deep_search_graph,
    execute_deep_search,
    should_continue,
)
from app.providers import ProviderError


def test_search_state_and_evaluation_output_schemas():
    output = EvaluationOutput(
        is_sufficient=False,
        critique="Manque d'analyses sur le coût du kWh",
        extracted_findings=["L'électrolyseur PEM atteint 65% de rendement"],
        next_queries=["coût kWh électrolyse PEM 2026"],
    )
    assert output.is_sufficient is False
    assert len(output.extracted_findings) == 1
    assert len(output.next_queries) == 1
    dump = output.model_dump()
    assert dump["critique"] == "Manque d'analyses sur le coût du kWh"

    state: SearchState = {
        "question": "Quel avenir pour le silicium ?",
        "iteration": 1,
        "max_iterations": 3,
        "findings": ["Faits initiaux"],
        "queries": ["silicium 2nm"],
        "executed_queries": [],
        "sources": [],
        "is_sufficient": False,
        "critique": "",
        "final_answer": "",
    }
    assert state["question"] == "Quel avenir pour le silicium ?"


def test_should_continue_routing():
    # 1. Suffisant -> Synthèse
    assert should_continue({"is_sufficient": True, "iteration": 1, "max_iterations": 3, "queries": ["test"]}) == "synthesize"

    # 2. Max iterations atteint -> Synthèse
    assert should_continue({"is_sufficient": False, "iteration": 4, "max_iterations": 3, "queries": ["test"]}) == "synthesize"

    # 3. Quota de sources (si configuré) atteint -> Synthèse
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "max_sources": 100, "sources": [{}] * 100, "queries": ["test"]}) == "synthesize"

    # 3b. Sans quota (max_sources=None), continue tant que non suffisant même avec > 100 sources (sous la limite de sécurité 120)
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "max_sources": None, "sources": [{}] * 105, "queries": ["test"]}) == "search"

    # 3c. Garde-fous durs contre les emballements : sources >= 120 ou requêtes exécutées >= 24 -> Synthèse
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "max_sources": None, "sources": [{}] * 125, "queries": ["test"]}) == "synthesize"
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "executed_queries": ["q"] * 24, "queries": ["test"]}) == "synthesize"

    # 4. Aucune requête restante -> Synthèse
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "queries": []}) == "synthesize"

    # 5. Non suffisant avec requêtes -> Recherche
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "queries": ["query A"]}) == "search"


@pytest.mark.asyncio
async def test_stategraph_execution_and_accumulation():
    builder = StateGraph(SearchState)

    async def node_a(state: SearchState):
        return {"iteration": 1, "findings": ["Découverte 1"]}

    async def node_b(state: SearchState):
        return {"iteration": 2, "findings": ["Découverte 2", "Découverte 1"]}  # Découverte 1 ne doit pas être dupliquée

    builder.add_node("a", node_a)
    builder.add_node("b", node_b)
    builder.add_edge(START, "a")
    builder.add_edge("a", "b")
    builder.add_edge("b", END)

    graph = builder.compile()
    outputs = []
    async for name, payload in graph.stream({"question": "Test", "findings": []}):
        outputs.append((name, payload))

    assert len(outputs) == 2
    assert outputs[0][0] == "a"
    assert outputs[1][0] == "b"


@pytest.mark.asyncio
async def test_execute_deep_search_pipeline(monkeypatch):
    settings = Settings(_env_file=None, demo_mode=False, llm_api_key="secret")
    searched_queries = []
    status_events = []

    async def fake_search(query: str, limit: int = 10):
        searched_queries.append(query)
        return [
            {"title": f"Titre {query}", "url": f"https://example.org/{len(searched_queries)}", "snippet": f"Extrait long et détaillé pour {query} avec des faits techniques probants."},
        ]

    async def fake_plan(_settings, query, summary, recent_turns, max_queries=8):
        return ["piste initiale 1", "piste initiale 2"]

    async def fake_followup(_settings, query, executed_queries, sources, max_queries=4):
        if len(executed_queries) <= 2:
            return ["piste approfondie 3"]
        return []

    async def fake_translate(_settings, sources, query):
        return [{**s, "title": f"{s['title']} (FR)"} for s in sources]

    from app import providers
    monkeypatch.setattr(providers, "plan_deep_search_queries", fake_plan)
    monkeypatch.setattr(providers, "plan_deep_search_followup", fake_followup)
    monkeypatch.setattr(providers, "translate_deep_search_sources", fake_translate)

    final_result = None
    async for event in execute_deep_search(
        settings=settings,
        query="Comment fonctionne la fusion nucléaire par confinement magnétique ?",
        summary="",
        recent_turns=[],
        search_fn=fake_search,
        max_iterations=3,
        max_sources=100,
    ):
        if event["type"] == "status":
            status_events.append(event["message"])
        elif event["type"] == "done":
            final_result = event

    assert final_result is not None
    assert len(final_result["sources"]) == 3
    assert final_result["sources"][0]["title"].endswith("(FR)")
    assert len(searched_queries) == 3
    assert "piste initiale" in searched_queries[0]
    assert len(final_result["findings"]) > 0
    assert "URL: https://example.org/1" in final_result["findings"][0]
    assert "Date:" in final_result["findings"][0]
    assert "Contexte: piste initiale 1" in final_result["findings"][0]
    assert any("Planification" in s for s in status_events)
    assert any("Exploration" in s for s in status_events)
    assert any("Approfondissement" in s for s in status_events)
    assert any("Traduction" in s for s in status_events)


@pytest.mark.asyncio
async def test_execute_deep_search_with_user_custom_queries():
    settings = Settings(_env_file=None, demo_mode=True)
    searched_queries = []

    async def fake_search(query: str, limit: int = 10):
        searched_queries.append(query)
        return [
            {"title": f"Titre {query}", "url": f"https://example.org/{len(searched_queries)}", "snippet": "Extrait pertinent."},
        ]

    user_plan = ["requête utilisateur A", "requête utilisateur B"]
    final_result = None
    async for event in execute_deep_search(
        settings=settings,
        query="Question générale",
        summary="",
        recent_turns=[],
        search_fn=fake_search,
        initial_queries=user_plan,
        max_iterations=1,
        max_sources=10,
    ):
        if event["type"] == "done":
            final_result = event

    assert final_result is not None
    assert len(searched_queries) == 2
    assert "utilisateur" in searched_queries[0]


def test_deep_search_html_generator():
    from app.deep_search_html import generate_report_html, markdown_to_html, estimate_reading_time_minutes

    md = """# Introduction
Voici une analyse approfondie sur les architectures d'inférence locale [1].

## Points Clés
- L'utilisation de puces NPU dédiées permet de réduire la latence [2].
- Tableau des performances :

| Architecture | Bande passante | Consommation |
| --- | --- | --- |
| Apple M4 Max | 546 GB/s | 65W |
| Nvidia DGX | 1000 GB/s | 350W |

### Code d'exemple
```python
def infer(prompt):
    return "result"
```

> Conclusion préliminaire : le rapport puissance/consommation favorise l'Apple Silicon.
"""
    sources = [
        {"title": "Étude Benchmarks 2026", "url": "https://techbenchmarks.org/local-llm", "snippet": "Analyse comparative des GPU et NPU.", "provider": "SearXNG"},
        {"title": "Livre blanc SemiAnalysis", "url": "https://semianalysis.com/report", "snippet": "Les architectures matérielles pour l'inférence.", "provider": "SearXNG"},
    ]

    html_content, toc = markdown_to_html(md, sources)
    assert '<h1 id="introduction"' in html_content
    assert '<h2 id="points-cles"' in html_content
    assert 'href="#source-1"' in html_content
    assert 'href="#source-2"' in html_content
    assert '<table class="report-table">' in html_content
    assert '<blockquote class="report-blockquote">' in html_content
    assert '<code class="language-python">' in html_content
    assert len(toc) >= 3

    full_page = generate_report_html(
        title="Rapport Inférence 2026",
        topic="Quelles architectures pour LLM local ?",
        markdown_content=md,
        sources=sources,
        created_at_str="24/10/2026 à 10:00",
    )
    assert "<!DOCTYPE html>" in full_page
    assert "Rapport Inférence 2026" in full_page
    assert "Quelles architectures pour LLM local ?" in full_page
    assert "24/10/2026 à 10:00" in full_page
    assert 'id="bibliography-sources"' in full_page
    assert "techbenchmarks.org" in full_page
    assert "semianalysis.com" in full_page
    assert "@media print" in full_page
    assert "printPdf()" in full_page
    assert "Beau PDF" in full_page
    assert estimate_reading_time_minutes(md) >= 1


def test_get_message_html_endpoint(tmp_path):
    from app.main import create_app
    from app.models import Base, User, Conversation, Message
    from app.auth import hash_password
    from fastapi.testclient import TestClient

    settings = Settings(_env_file=None, app_data_dir=tmp_path, database_url=f"sqlite:///{tmp_path}/data.db", demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)

    with app.state.sessions() as db:
        user = User(username="user_msg", password_hash=hash_password("correct horse battery"), is_admin=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        conv = Conversation(user_id=user.id, title="Test HTML/PDF Export", model="mistral-small-latest")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        msg_user = Message(conversation_id=conv.id, role="user", content="Comment fabriquer du verre teinté ?")
        msg_ast = Message(conversation_id=conv.id, role="assistant", content="Pour fabriquer du verre teinté, on ajoute des oxydes métalliques...")
        db.add_all([msg_user, msg_ast])
        db.commit()
        db.refresh(msg_ast)
        msg_id = msg_ast.id

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login = client.post("/api/auth/login", json={"username": "user_msg", "password": "correct horse battery"})
        assert login.status_code == 200

        # Standard message HTML view
        resp = client.get(f"/api/messages/{msg_id}/html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<!DOCTYPE html>" in resp.text
        assert "verre teinté" in resp.text.lower()
        assert "Beau PDF" in resp.text

        # Standard message HTML download
        resp_dl = client.get(f"/api/messages/{msg_id}/html?download=1")
        assert resp_dl.status_code == 200
        assert "attachment" in resp_dl.headers.get("content-disposition", "")

        # Turn scope (Question & Réponse)
        resp_turn = client.get(f"/api/messages/{msg_id}/html?scope=turn")
        assert resp_turn.status_code == 200
        assert "Question de l'utilisateur" in resp_turn.text
        assert "Réponse de l'assistant cLAIr" in resp_turn.text
        assert "Comment fabriquer du verre teinté ?" in resp_turn.text

        # Conversation scope (Synthèse des messages)
        resp_conv = client.get(f"/api/messages/{msg_id}/html?scope=conversation")
        assert resp_conv.status_code == 200
        assert "Transcription & Synthèse de la discussion" in resp_conv.text
        assert "Test HTML/PDF Export" in resp_conv.text

        # Direct conversation HTML endpoint
        resp_c_endpoint = client.get(f"/api/conversations/{conv.id}/html")
        assert resp_c_endpoint.status_code == 200
        assert "<!DOCTYPE html>" in resp_c_endpoint.text
        assert "Test HTML/PDF Export" in resp_c_endpoint.text

        # Direct conversation download
        resp_c_dl = client.get(f"/api/conversations/{conv.id}/html?download=1")
        assert resp_c_dl.status_code == 200
        assert "attachment" in resp_c_dl.headers.get("content-disposition", "")




