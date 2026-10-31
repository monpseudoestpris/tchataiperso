import asyncio
import json
import pytest
import httpx
from app import google_deep_research
from app.config import Settings


def test_stream_google_deep_research_demo_mode():
    settings = Settings(demo_mode=True)
    events = []

    async def run():
        async for ev in google_deep_research.stream_google_deep_research(
            settings=settings,
            query="Impact de l'IA sur l'emploi",
            model="google/deep-research-preview-04-2026",
            learn_mode=False,
        ):
            events.append(ev)

    asyncio.run(run())
    assert any(e["type"] == "status" for e in events)
    assert any(e["type"] == "research_activity" for e in events)
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "Google Deep Research" in deltas
    done = next(e for e in events if e["type"] == "done")
    assert len(done["sources"]) >= 2
    assert done["sources"][0]["doc_id"] == "source-1"


def test_stream_google_deep_research_learn_mode_demo():
    settings = Settings(demo_mode=True)
    events = []

    async def run():
        async for ev in google_deep_research.stream_google_deep_research(
            settings=settings,
            query="Fondements du Machine Learning",
            model="google/deep-research-preview-04-2026",
            learn_mode=True,
        ):
            events.append(ev)

    asyncio.run(run())
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "Cours magistral" in deltas
    assert "Auto-évaluation" in deltas


def test_stream_google_deep_research_polling_flow(monkeypatch):
    settings = Settings(demo_mode=False, google_api_key="test-google-key")
    events = []

    poll_calls = 0

    def mock_post(url, headers, json):
        assert "interactions" in str(url)
        assert headers["x-goog-api-key"] == "test-google-key"
        assert json["agent"] == "deep-research-preview-04-2026"
        return httpx.Response(200, json={"id": "interactions/int-12345", "status": "in_progress"})

    def mock_get(url, headers):
        nonlocal poll_calls
        poll_calls += 1
        assert "interactions/int-12345" in str(url)
        if poll_calls == 1:
            return httpx.Response(200, json={"id": "interactions/int-12345", "status": "in_progress"})
        return httpx.Response(200, json={
            "id": "interactions/int-12345",
            "status": "completed",
            "outputs": [
                {
                    "text": (
                        "# Rapport Google Deep Research\n\n"
                        "Constats vérifiés [1] et perspectives [2].\n\n"
                        "### Sources documentaires\n"
                        "1. [Étude Statistique](https://example.org/etude)\n"
                        "2. [Rapport Emploi](https://example.org/emploi)\n"
                    )
                }
            ],
        })

    real_async_client = httpx.AsyncClient

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers=None, json=None):
            return mock_post(url, headers, json)

        async def get(self, url, headers=None):
            return mock_get(url, headers)

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)
    real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda d: real_sleep(0.001))

    async def run():
        async for ev in google_deep_research.stream_google_deep_research(
            settings=settings,
            query="Test investigation Google",
            model="google/deep-research-preview-04-2026",
        ):
            events.append(ev)

    asyncio.run(run())
    deltas = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "Rapport Google Deep Research" in deltas
    done = next(e for e in events if e["type"] == "done")
    assert len(done["sources"]) == 2
    assert done["sources"][0]["url"] == "https://example.org/etude"


def test_stream_google_deep_research_max_agent_selection(monkeypatch):
    settings = Settings(demo_mode=False, google_api_key="test-google-key")
    posted_agent = None

    def mock_post(url, headers, json):
        nonlocal posted_agent
        posted_agent = json.get("agent")
        return httpx.Response(200, json={"id": "interactions/int-max-999", "status": "completed", "outputs": [{"text": "# Rapport Max"}]})

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, headers=None, json=None):
            return mock_post(url, headers, json)
        async def get(self, url, headers=None):
            return httpx.Response(200, json={"status": "completed", "outputs": [{"text": "# Rapport Max"}]})

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    async def run():
        async for _ in google_deep_research.stream_google_deep_research(
            settings=settings,
            query="Investigation Max",
            model="google/deep-research-max-preview-04-2026",
        ):
            pass

    asyncio.run(run())
    assert posted_agent == "deep-research-max-preview-04-2026"


def test_plan_google_deep_research_and_collaborative_execution(monkeypatch):
    settings = Settings(demo_mode=False, google_api_key="test-google-key")
    captured_planning_payload = None
    captured_execution_payload = None

    def mock_post(url, headers, json):
        nonlocal captured_planning_payload, captured_execution_payload
        if json.get("agent_config", {}).get("collaborative_planning") is True:
            captured_planning_payload = json
            return httpx.Response(200, json={
                "id": "interactions/int-plan-777",
                "status": "completed",
                "outputs": [{"text": "1. Axe A\n2. Axe B"}],
            })
        else:
            captured_execution_payload = json
            return httpx.Response(200, json={"id": "interactions/int-exec-888", "status": "completed", "outputs": [{"text": "# Rapport finalisé"}]})

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, headers=None, json=None):
            return mock_post(url, headers, json)
        async def get(self, url, headers=None):
            return httpx.Response(200, json={"status": "completed", "outputs": [{"text": "# Rapport finalisé"}]})

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    # 1. Test de la planification
    plan_res = asyncio.run(google_deep_research.plan_google_deep_research(
        settings=settings,
        query="Orientation 2030",
        model="google/deep-research-preview-04-2026",
    ))
    assert plan_res["interaction_id"] == "interactions/int-plan-777"
    assert "Axe A" in plan_res["plan_text"]
    assert captured_planning_payload["agent_config"]["collaborative_planning"] is True

    # 2. Test du lancement avec l'ID d'interaction et le plan validé
    events = []
    async def run():
        async for ev in google_deep_research.stream_google_deep_research(
            settings=settings,
            query="Orientation 2030",
            model="google/deep-research-preview-04-2026",
            interaction_id=plan_res["interaction_id"],
            plan_feedback="Plan ajusté : insérer Axe C",
        ):
            events.append(ev)

    asyncio.run(run())
    assert captured_execution_payload["previous_interaction_id"] == "interactions/int-plan-777"
    assert "Plan ajusté : insérer Axe C" in captured_execution_payload["input"]
    assert "EXCLUSIVEMENT EN FRANÇAIS" in captured_execution_payload["input"]
    assert captured_execution_payload["agent_config"]["collaborative_planning"] is False
    assert captured_execution_payload["agent_config"]["visualization"] == "auto"
    assert captured_execution_payload["agent_config"]["thinking_summaries"] == "auto"
    assert any(e["type"] == "done" for e in events)


def test_plan_google_deep_research_refinement_step_2(monkeypatch):
    """Vérifie l'Étape 2 d'affinement du plan multitours avec previous_interaction_id."""
    settings = Settings(demo_mode=False, google_api_key="test-google-key")
    captured_payload = None

    def mock_post(url, headers, json):
        nonlocal captured_payload
        captured_payload = json
        return httpx.Response(200, json={
            "id": "interactions/int-plan-refined-999",
            "status": "completed",
            "outputs": [{"text": "1. Axe A raffiné\n2. Axe B raffiné"}],
        })

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, headers=None, json=None):
            return mock_post(url, headers, json)
        async def get(self, url, headers=None):
            return httpx.Response(200, json={"status": "completed"})

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    plan_res = asyncio.run(google_deep_research.plan_google_deep_research(
        settings=settings,
        query="Préciser l'axe 2 sur les semi-conducteurs",
        model="google/deep-research-preview-04-2026",
        previous_interaction_id="interactions/int-plan-777",
    ))

    assert plan_res["interaction_id"] == "interactions/int-plan-refined-999"
    assert captured_payload["previous_interaction_id"] == "interactions/int-plan-777"
    assert captured_payload["agent_config"]["collaborative_planning"] is True
    assert captured_payload["agent_config"]["thinking_summaries"] == "auto"


def test_clean_plan_text_french_normalization():
    """Vérifie le nettoyage et la francisation des en-têtes usuels générés par Google Deep Research."""
    raw = (
        "**Title:** Investigation IA 2030\n\n"
        "**Research Plan:**\n\n"
        "**Overview:** Cadrage des dynamiques de formation.\n"
        "**Research Areas:**\n"
        "1. Analyse prospective\n"
        "2. Données statistiques"
    )
    cleaned = google_deep_research._clean_plan_text(raw)
    assert "**Overview:**" not in cleaned
    assert "**Vue d'ensemble :**" in cleaned
    assert "**Axes d'investigation :**" in cleaned
    assert "1. Analyse prospective" in cleaned

    """Vérifie la conversion des éléments images base64 (visualization: 'auto') en Markdown."""
    data = {
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {"type": "text", "text": "## Analyse de marché"},
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
                    },
                    {"type": "text", "text": "Tendances observées ci-dessus."},
                ],
            }
        ]
    }
    result = google_deep_research._extract_interaction_text(data)
    assert "## Analyse de marché" in result
    assert "![Graphique Google Deep Research](data:image/png;base64,iVBORw0K" in result
    assert "Tendances observées ci-dessus." in result


def test_extract_step_summary_thinking_summaries():
    """Vérifie l'extraction des thinking summaries et tool calls."""
    step_with_summary = {"summary": "Exploration des sources statistiques de l'INSEE"}
    assert google_deep_research._extract_step_summary(step_with_summary) == "Exploration des sources statistiques de l'INSEE"

    step_with_thought_content = {
        "content": [{"type": "thought", "text": "Recoupement des projections d'effectifs avec Dares"}]
    }
    assert google_deep_research._extract_step_summary(step_with_thought_content) == "Recoupement des projections d'effectifs avec Dares"

    step_with_tool_call = {
        "tool_call": {"name": "google_search", "args": {"query": "Dares metiers 2030 synthese"}}
    }
    assert "Dares metiers 2030" in google_deep_research._extract_step_summary(step_with_tool_call)


def test_markdown_to_html_base64_image_and_citations():
    """Vérifie le rendu propre d'une image base64 scindée et des citations Google [cite: ...]."""
    from app.deep_search_html import markdown_to_html

    sample_md = (
        "## Dynamique de l'emploi\n\n"
        "Les besoins sont confirmés [cite: 1, 2] et évalués [cite: 2].\n\n"
        "![Graphique Google Deep Research]\n"
        "(data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==)\n\n"
        "Texte suivant la visualisation."
    )
    sources = [
        {"title": "Dares Emploi 2030", "url": "https://dares.travail-emploi.gouv.fr/metiers2030"},
        {"title": "France Stratégie", "url": "https://strategie.gouv.fr/publications"},
    ]
    html_output, toc = markdown_to_html(sample_md, sources)

    # 1. L'image doit être rendue dans une balise <figure> avec <img src="data:image/png;base64,..."
    assert '<figure class="report-inline-figure"' in html_output
    assert '<img src="data:image/png;base64,iVBORw0K' in html_output
    # Ne doit PAS rester en markdown brut dans un paragraphe
    assert "![Graphique Google Deep Research]" not in html_output
    assert "(data:image/png;base64," not in html_output

    # 2. Les citations doivent être converties en chips de sources
    assert 'href="#source-1"' in html_output
    assert 'href="#source-2"' in html_output
    assert "[cite:" not in html_output


def test_clean_grounding_url_and_sources_extraction():
    """Vérifie l'extraction d'URL propre depuis une redirection Google Vertex AI grounding."""
    from app.google_deep_research import _clean_grounding_url, _extract_interaction_sources

    redirect_url = (
        "https://vertexaisearch.cloud.google.com/grounding-api-redirect/ABC123XYZ?"
        "url=https%3A%2F%2Fdares.travail-emploi.gouv.fr%2Fmetiers2030&hl=fr"
    )
    cleaned = _clean_grounding_url(redirect_url)
    assert cleaned == "https://dares.travail-emploi.gouv.fr/metiers2030"

    data = {
        "steps": [
            {
                "grounding_chunks": [
                    {"web": {"uri": redirect_url}},
                    {"web": {"uri": "https://insee.fr/fr/statistiques"}},
                ]
            }
        ]
    }
    extracted = _extract_interaction_sources(data)
    assert "https://dares.travail-emploi.gouv.fr/metiers2030" in extracted
    assert "https://insee.fr/fr/statistiques" in extracted


def test_generate_structured_fallback_plan_extracts_real_axes():
    """Vérifie que le plan de secours extrait les sous-questions en axes numérotés au lieu de copier la question brute."""
    from app.google_deep_research import _generate_structured_fallback_plan

    complex_query = (
        "Réalise une recherche approfondie sur : Dans quelles études se lancer en 2030 ?\n"
        "Je souhaite savoir :\n"
        "Quels baccalauréats privilégier au lycée ?\n"
        "Quelles études supérieures offrent les meilleurs débouchés ?\n"
        "Quelles filières risquent d'être affectées par l'IA ?\n"
        "Quels nouveaux métiers vont apparaître avec l'IA ?\n"
        "Quelles différences entre BTS, BUT, Licences et Écoles d'ingénieurs ?"
    )
    fallback = _generate_structured_fallback_plan(complex_query, learn_mode=False)

    # Doit contenir des axes numérotés propres
    assert "1. **Quels baccalauréats privilégier au lycée" in fallback
    assert "2. **Quelles études supérieures offrent les meilleurs débouchés" in fallback
    assert "3. **Quelles filières risquent d'être affectées par l'IA" in fallback
    # Ne doit PAS être la chaîne brute
    assert not fallback.startswith("Plan d'investigation Google Deep Research initié sur :")


def test_extract_thought_items_from_step_and_target_sources():
    """Vérifie l'extraction itérative des pensées structurées et la détection des sources institutionnelles."""
    from app.google_deep_research import _extract_thought_items_from_step, _detect_target_sources

    # 1. Step thought avec liste de résumés (format réel Google Interactions API)
    step_thought = {
        "type": "thought",
        "summary": [
            {
                "type": "text",
                "text": "***Generating research plan***\n\nTo best answer your request, I'm constructing a research plan.",
            },
            {
                "type": "text",
                "text": "**Identifying official statistical sources**\n\nI am querying Insee and Dares datasets.",
            },
        ],
    }
    items = _extract_thought_items_from_step(step_thought)
    assert len(items) == 2
    assert items[0]["title"] == "Generating research plan"
    assert "constructing a research plan" in items[0]["text"]
    assert items[1]["title"] == "Identifying official statistical sources"
    assert "querying Insee" in items[1]["text"]

    # 2. Détection ciblée des organismes officiels à partir de la demande
    user_query = "Recherche sur l'insertion professionnelle et les études avec DARES, France Stratégie, Insee, Onisep et l'impact de l'IA"
    target_sources = _detect_target_sources(user_query)
    urls = [s["url"] for s in target_sources]
    assert "https://dares.travail-emploi.gouv.fr" in urls
    assert "https://www.strategie-gouv.fr" in urls
    assert "https://www.insee.fr" in urls
    assert "https://www.onisep.fr" in urls
    assert "https://www.inria.fr" in urls
    assert all(s["state"] == "found" for s in target_sources)


def test_agent_mismatch_fallback_recovery(monkeypatch):
    """Vérifie la résilience face à l'erreur 400 'Previous interaction belongs to a different agent'."""
    from app.config import Settings
    from app.google_deep_research import stream_google_deep_research

    settings = Settings()
    settings.google_api_key = "fake-key"
    settings.demo_mode = False

    attempts = []

    def mock_httpx_get(url, *args, **kwargs):
        class MockResp:
            status_code = 200
            def json(self):
                # L'interaction précédente a été créée par l'agent standard
                return {"id": "v1_test_prev", "agent": "deep-research-preview-04-2026", "status": "completed"}
        return MockResp()

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *args, **kwargs):
            json_body = kwargs.get("json", {})
            attempts.append(json_body.get("agent"))
            class MockResp:
                status_code = 200
                def json(self):
                    return {"id": "v1_test_active", "status": "in_progress"}
            return MockResp()

        async def get(self, url, *args, **kwargs):
            class MockResp:
                status_code = 200
                def json(self):
                    return {
                        "id": "v1_test_active",
                        "status": "completed",
                        "outputs": [{"text": "# Rapport de recherche\n\nContenu vérifié."}],
                    }
            return MockResp()

    import httpx
    monkeypatch.setattr(httpx, "get", mock_httpx_get)
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    # Exécution avec modèle Max mais interaction préalable de type standard
    async def run():
        events = []
        async for ev in stream_google_deep_research(
            settings=settings,
            query="Test query",
            model="google/deep-research-max-preview-04-2026",
            interaction_id="v1_test_prev",
            plan_feedback="Plan approuvé",
        ):
            events.append(ev)
        return events

    events = asyncio.run(run())
    assert any(ev.get("type") == "done" for ev in events)
    # L'agent a été automatiquement aligné sur celui de l'interaction précédente
    assert attempts[0] == "deep-research-preview-04-2026"


def test_resolve_grounding_redirects_and_citations(monkeypatch):
    """Vérifie la résolution des redirections Vertex AI Grounding vers les publications réelles."""
    from app.google_deep_research import _resolve_grounding_redirects, _extract_interaction_sources
    from app.providers import extract_sources_from_research

    fake_redirect_1 = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/TOKEN_DARES"
    fake_redirect_2 = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/TOKEN_INSEE"

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, *args, **kwargs):
            class MockResp:
                def __init__(self, target):
                    self.headers = {"location": target}
            if "TOKEN_DARES" in url:
                return MockResp("https://dares.travail-emploi.gouv.fr/metiers2030")
            elif "TOKEN_INSEE" in url:
                return MockResp("https://www.insee.fr/fr/statistiques/emploi")
            return MockResp(url)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    resolved = asyncio.run(_resolve_grounding_redirects([fake_redirect_1, fake_redirect_2]))
    assert "https://dares.travail-emploi.gouv.fr/metiers2030" in resolved
    assert "https://www.insee.fr/fr/statistiques/emploi" in resolved

    # Vérification que extract_sources_from_research associe correctement les vraies sources
    report_text = "Les projections pour 2030 indiquent une forte tension [1] et un taux d'emploi stable [2]."
    sources = extract_sources_from_research(report_text, payload_citations=resolved)
    assert len(sources) == 2
    assert sources[0]["url"] == "https://dares.travail-emploi.gouv.fr/metiers2030"
    assert sources[1]["url"] == "https://www.insee.fr/fr/statistiques/emploi"
    # Aucune fausse URL générique
    assert not any("google.com/search?q=source+citation" in s["url"] for s in sources)


def test_previous_interaction_not_yet_complete_fallback(monkeypatch):
    """Vérifie la résilience face à l'erreur 400 'Previous interaction is not yet complete'."""
    from app.config import Settings
    from app.google_deep_research import stream_google_deep_research

    settings = Settings()
    settings.google_api_key = "fake-key"
    settings.demo_mode = False

    post_calls = []

    def mock_httpx_get(url, *args, **kwargs):
        class MockResp:
            status_code = 200
            def json(self):
                return {"id": "v1_test_prev", "agent": "deep-research-preview-04-2026", "status": "completed"}
        return MockResp()

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *args, **kwargs):
            body = kwargs.get("json", {})
            post_calls.append(dict(body))
            # Première tentative : simuler l'erreur 400 Google "is not yet complete"
            if len(post_calls) == 1:
                class MockErrResp:
                    status_code = 400
                    text = '{"error":{"message":"Previous interaction is not yet complete.","code":"invalid_request"}}'
                    def json(self):
                        return {"error": {"message": "Previous interaction is not yet complete."}}
                return MockErrResp()

            # Deuxième tentative (fallback sans previous_interaction_id) : succès
            class MockSuccessResp:
                status_code = 200
                text = '{"id":"v1_test_active","status":"in_progress"}'
                def json(self):
                    return {"id": "v1_test_active", "status": "in_progress"}
            return MockSuccessResp()

        async def get(self, url, *args, **kwargs):
            class MockResp:
                status_code = 200
                def json(self):
                    if "v1_test_prev" in url:
                        return {"id": "v1_test_prev", "status": "in_progress"}
                    return {
                        "id": "v1_test_active",
                        "status": "completed",
                        "outputs": [{"text": "# Rapport de recherche autonome\n\nContenu finalisé."}],
                    }
            return MockResp()

    import httpx
    monkeypatch.setattr(httpx, "get", mock_httpx_get)
    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    async def run():
        events = []
        async for ev in stream_google_deep_research(
            settings=settings,
            query="Test query",
            interaction_id="v1_test_prev",
            plan_feedback="Plan approuvé",
        ):
            events.append(ev)
        return events

    events = asyncio.run(run())
    assert any(ev.get("type") == "done" for ev in events)
    # Vérifier que le fallback a bien retiré previous_interaction_id lors du retry
    assert len(post_calls) >= 2
    assert "previous_interaction_id" not in post_calls[-1]
    assert "PLAN D'INVESTIGATION VALIDÉ" in post_calls[-1]["input"]








