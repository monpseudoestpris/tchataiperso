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

    # 3c. Garde-fous durs contre les emballements : sources >= 120 ou requêtes exécutées >= 40 -> Synthèse
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "max_sources": None, "sources": [{}] * 125, "queries": ["test"]}) == "synthesize"
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "executed_queries": ["q"] * 40, "queries": ["test"]}) == "synthesize"

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


def test_theme_to_search_query_multilingual_and_non_latin():
    from app import providers

    # 1. Préservation des requêtes multilingues en écritures non-latines (japonais, chinois, cyrillique, arabe)
    q_ja = providers.theme_to_search_query("全固体電池 トヨタ 2026 量産 課題", topic="Batteries solides")
    assert "全固体電池" in q_ja
    assert "トヨタ" in q_ja

    q_zh = providers.theme_to_search_query("固态电池 能量密度 2026 宁德时代", topic="Batteries solides")
    assert "固态电池" in q_zh

    q_ru = providers.theme_to_search_query("твердотельные аккумуляторы плотность энергии", topic="Batteries")
    assert "твердотельные" in q_ru

    # 2. Préservation des requêtes courtes multilingues directes (allemand, anglais, espagnol)
    q_de = providers.theme_to_search_query('"Festkörperbatterie" Energiedichte Produktionskosten 2026', topic="Batteries")
    assert '"Festkörperbatterie"' in q_de
    assert "Energiedichte" in q_de


@pytest.mark.asyncio
async def test_deep_search_mid_course_validation_and_intermediate_questions(monkeypatch):
    from app import providers

    settings = Settings(_env_file=None, demo_mode=False, llm_api_key="secret")
    searched_queries = []
    status_events = []
    validation_calls = 0

    async def fake_decompose(_settings, query, summary="", recent_turns=None, max_points=6):
        return [
            {"id": "P1", "aspect": "Architecture & Chimie", "question": "Quelle est la chimie exacte des électrolytes ?", "status": "pending"},
            {"id": "P2", "aspect": "Industrialisation & Coûts", "question": "Quels sont les coûts au kWh et délais de production ?", "status": "pending"},
            {"id": "P3", "aspect": "Contradictions & Limites", "question": "Quels sont les problèmes de dendrites et de pression mécanique ?", "status": "pending"},
        ]

    async def fake_validate(
        settings,
        query,
        aspect_checklist,
        executed_queries,
        sources,
        findings=None,
        previous_intermediate_questions=None,
        max_queries=6,
    ):
        nonlocal validation_calls
        validation_calls += 1
        updated_checklist = [dict(c) for c in aspect_checklist]
        if validation_calls == 1:
            updated_checklist[0]["status"] = "covered"
            updated_checklist[1]["status"] = "partial"
            updated_checklist[2]["status"] = "missing"
            return {
                "is_sufficient": False,
                "aspect_checklist": updated_checklist,
                "intermediate_questions": [
                    "Quelle pression mécanique (MPa) est requise pour maintenir le contact de l'électrolyte solide ?",
                    "Pourquoi les annonces japonaises et allemandes divergent-elles sur le coût 2027 ?",
                ],
                "unanswered_aspects": ["Industrialisation & Coûts", "Contradictions & Limites"],
                "validation_summary": "1/3 points couverts · Lacunes sur la pression mécanique et les coûts.",
                "followup_queries": [
                    '"solid-state battery" stack pressure MPa dendrites',
                    "全固体電池 拘束圧 デンドライト 課題",
                    "Festkörperbatterie Produktionskosten kWh 2026",
                ],
                "searched_languages": ["fr", "en", "ja", "de"],
            }
        else:
            for item in updated_checklist:
                item["status"] = "covered"
            return {
                "is_sufficient": True,
                "aspect_checklist": updated_checklist,
                "intermediate_questions": [
                    "Les tests de cyclage à basse température (-20°C) confirment-ils la stabilité ?"
                ],
                "unanswered_aspects": [],
                "validation_summary": "3/3 points intégralement couverts et validés dans 4 langues.",
                "followup_queries": [],
                "searched_languages": ["fr", "en", "ja", "de"],
            }

    async def fake_search(query: str, limit: int = 10):
        searched_queries.append(query)
        return [
            {
                "title": f"Publication {query[:25]}",
                "url": f"https://arxiv.org/abs/2026.{len(searched_queries)}",
                "snippet": f"Données expérimentales détaillées (50 MPa, 120 $/kWh) pour {query} validées en 2026.",
            }
        ]

    async def fake_translate(_settings, sources, query):
        return sources

    monkeypatch.setattr(providers, "decompose_deep_search_objective", fake_decompose)
    monkeypatch.setattr(providers, "validate_and_followup_deep_search", fake_validate)
    monkeypatch.setattr(providers, "translate_deep_search_sources", fake_translate)

    final_result = None
    async for event in execute_deep_search(
        settings=settings,
        query="Quel est l'état réel des batteries tout-solide en 2026 ?",
        summary="",
        recent_turns=[],
        search_fn=fake_search,
        initial_queries=["1. Chimie des électrolytes solides : sulfures vs oxydes"],
        max_iterations=6,
    ):
        if event["type"] == "status":
            status_events.append(event["message"])
        elif event["type"] == "done":
            final_result = event

    assert final_result is not None
    assert validation_calls == 2
    # 1 initial query + 3 multilingual followup queries (EN, JA, DE)
    assert len(searched_queries) == 4
    assert any("全固体電池" in q for q in searched_queries)
    assert any("Festkörperbatterie" in q for q in searched_queries)
    # A model-only verdict without mapped proof cannot survive final curation.
    assert all(c["status"] != "covered" for c in final_result["aspect_checklist"])
    # Intermediate questions tracked and returned
    assert len(final_result["intermediate_questions"]) >= 2
    assert any("MPa" in q for q in final_result["intermediate_questions"])
    # Findings include validation audit notes and final checklist summary
    assert any("VALIDATION VAGUE 1" in f for f in final_result["findings"])
    assert any("BILAN FINAL DES POINTS À ABORDER" in f for f in final_result["findings"])
    assert any("Questions intermédiaires" in s for s in status_events)


def test_deep_search_two_step_planner_and_section_writer_sse(tmp_path, monkeypatch):
    from app.main import create_app
    from app.models import Base, User, Conversation
    from app.auth import hash_password
    from app import providers
    from fastapi.testclient import TestClient

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/data.db",
        demo_mode=False,
        llm_api_key="test-key",
        searxng_url="http://searxng.local",
        deep_search_engine="pipeline",
    )
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)

    with app.state.sessions() as db:
        user = User(username="ds_writer_user", password_hash=hash_password("correct horse battery"), is_admin=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        conv = Conversation(user_id=user.id, title="Orientation Post-Bac", model="mistral-small-latest")
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conv_id = conv.id

    async def fake_search_web(_settings, query: str, count: int | None = None):
        return [
            {
                "title": f"Étude Emploi & Filières ({query[:20]})",
                "url": "https://dares.travail-emploi.gouv.fr/etude-2026",
                "snippet": "Les filières ingénierie nucléaire, santé et électrotechnique affichent 94% d'insertion, contre une saturation en psycho/comm.",
                "provider": "SearXNG",
            }
        ]

    async def fake_validate(**kwargs):
        checklist = kwargs["aspect_checklist"]
        for c in checklist:
            c["status"] = "covered"
        return {
            "is_sufficient": True,
            "aspect_checklist": checklist,
            "intermediate_questions": ["Quels bacs technologiques offrent le meilleur rebond en BUT ?"],
            "unanswered_aspects": [],
            "validation_summary": "Tous les aspects sont validés.",
            "followup_queries": [],
            "searched_languages": ["fr", "en"],
        }

    outline_calls = []
    writer_calls = []

    async def fake_plan_report_outline(settings, query, sources, findings=None, aspect_checklist=None, intermediate_questions=None, learn_mode=False, detail_level=None):
        outline_calls.append({"query": query, "sources_count": len(sources), "learn_mode": learn_mode, "detail_level": detail_level})
        return {
            "title": "# Grand Dossier Orientation & Emploi d'Avenir",
            "executive_summary_guide": "Synthèse des choix de bac et filières porteuses vs saturées.",
            "parts": [
                {
                    "id": "S1",
                    "heading": "## 1. Choix des Spécialités de Baccalauréat (Général vs Technologique)",
                    "subparts": ["### 1.1 Mathématiques, Physique-Chimie et NSI", "### 1.2 Bacs Technologiques STI2D et STL"],
                    "focus": "Développer les combinaisons de spécialités et taux d'accès Parcoursup [1].",
                },
                {
                    "id": "S2",
                    "heading": "## 2. Filières en Forte Tension vs Filières Bouchées et Saturées",
                    "subparts": ["### 2.1 Industrie, Énergie, Santé et Cybersécurité", "### 2.2 Filières saturées et stratégies d'alternance"],
                    "focus": "Comparer les salaires, taux d'insertion et secteurs saturés [1].",
                },
            ],
        }

    async def fake_stream_chat(_settings, messages, model, enable_cache=True):
        last_user_msg = messages[-1]["content"]
        writer_calls.append({"model": model, "instruction": last_user_msg})
        if "PARTIE 1/2" in last_user_msg:
            yield "## Synthèse Exécutive & Conclusions Clés\nAnalyse complète [1].\n\n## 1. Choix des Spécialités de Baccalauréat (Général vs Technologique)\n### 1.1 Mathématiques, Physique-Chimie et NSI\nDéveloppement approfondi sur 5 paragraphes [1]."
        else:
            yield "## 2. Filières en Forte Tension vs Filières Bouchées et Saturées\n### 2.1 Industrie, Énergie, Santé et Cybersécurité\nDéveloppement approfondi de la partie 2 avec connaissance de la partie 1 [1]."

    monkeypatch.setattr(providers, "search_web", fake_search_web)
    monkeypatch.setattr(providers, "search_web_images", lambda *a, **kw: asyncio.sleep(0, result=[]))
    monkeypatch.setattr(providers, "decompose_deep_search_objective", lambda *a, **kw: asyncio.sleep(0, result=providers.default_deep_search_aspect_checklist("Orientation", 4)))
    monkeypatch.setattr(providers, "validate_and_followup_deep_search", fake_validate)
    monkeypatch.setattr(providers, "translate_deep_search_sources", lambda s, srcs, q: asyncio.sleep(0, result=srcs))
    monkeypatch.setattr(providers, "plan_report_outline", fake_plan_report_outline)
    monkeypatch.setattr(providers, "stream_chat", fake_stream_chat)

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login = client.post("/api/auth/login", json={"username": "ds_writer_user", "password": "correct horse battery"})
        assert login.status_code == 200

        resp = client.post(
            f"/api/conversations/{conv_id}/messages",
            json={
                "content": "Dans quelles études se lancer actuellement et quels bacs privilégier ?",
                "deep_search": True,
                "deep_search_queries": ["1. Choix du bac et filières en tension vs bouchées"],
            },
        )
        assert resp.status_code == 200
        body_text = resp.text

        # Vérifie que l'Étape 1 (Agent Planificateur) a bien été appelée une fois
        assert len(outline_calls) == 1
        assert outline_calls[0]["sources_count"] >= 1

        # Vérifie que l'Étape 2 (Agent Écrivain) a bien été appelée séquentiellement pour chaque partie (2 parties)
        expert_calls = [c for c in writer_calls if "MISSION DE L'EXPERT" in c["instruction"]]
        writer_calls = [c for c in writer_calls if "MISSION DE L'AGENT ÉCRIVAIN" in c["instruction"]]
        # 1 appel expert référent par partie (2 parties au total au lieu de 6 appels redondants)
        assert len(expert_calls) == 2
        assert len(writer_calls) == 2
        assert "ANALYSE STRATÉGIQUE DE L'EXPERT RÉFÉRENT" in writer_calls[0]["instruction"]
        assert writer_calls[0]["model"] == "google/gemini-3.8-flash"
        assert "PARTIE 1/2" in writer_calls[0]["instruction"]
        assert "PARTIE 2/2" in writer_calls[1]["instruction"]
        # La partie 2 a connaissance que la partie 1 a déjà été rédigée
        assert "## 1. Choix des Spécialités de Baccalauréat" in writer_calls[1]["instruction"]
        assert "PARTIES DÉJÀ RÉDIGÉES PRÉCÉDEMMENT" in writer_calls[1]["instruction"]

        # Vérifie que le flux SSE final contient le plan détaillé ET chacune des parties rédigées
        assert "Agent Planificateur" in body_text
        assert "Agent Écrivain" in body_text
        assert "Grand Dossier Orientation & Emploi d'Avenir" in body_text
        assert "Développement approfondi de la partie 2" in body_text






