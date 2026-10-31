import asyncio
from types import SimpleNamespace

from app.config import Settings
from app.deep_search import execute_deep_search
from app.research_activity import research_activity
from app.source_filter import enrich_top_sources_content


def test_public_activity_whitelists_fields_and_safe_document_links():
    event = research_activity("results", "Résultats", query="insertion", sources=[
        {"title": "Rapport", "url": "https://example.org/rapport", "snippet": "PRIVATE_CONTENT", "content": "PRIVATE_CONTENT", "reasoning": "PRIVATE_REASONING"},
        {"title": "Unsafe", "url": "javascript:alert(1)"},
        {"title": "Credentials", "url": "https://user:password@example.org"},
        {"title": "Image", "url": "https://example.org/i", "media_type": "image"},
    ])
    payload = event["activity"]
    assert payload["query"] == "insertion"
    assert payload["sources"] == [{"title": "Rapport", "url": "https://example.org/rapport", "state": "found"}]
    assert "PRIVATE_" not in str(event)
    assert payload["timestamp"]


def test_deep_search_emits_queries_results_and_selection_without_claiming_pages_were_read():
    async def search(query, limit):
        return [{"title": "Insertion", "url": "https://example.org/insertion", "snippet": "Enquête sur l'insertion des diplômés avec des résultats documentaires."}]

    async def run():
        return [event async for event in execute_deep_search(
            Settings(_env_file=None, demo_mode=True), "insertion", "", [], search,
            initial_queries=["insertion diplômés"], max_iterations=1,
        )]
    events = asyncio.run(run())
    activities = [event["activity"] for event in events if event["type"] == "research_activity"]
    assert [event["kind"] for event in activities] == ["query", "results", "selection"]
    assert activities[0]["query"]
    assert activities[1]["sources"][0]["state"] == "found"
    assert activities[2]["sources"][0]["state"] == "selected"
    assert events[-1]["type"] == "done"


def test_source_authority_is_available_before_midcourse_evidence_audit():
    from app.deep_search import create_deep_search_graph

    async def search(query, limit):
        return [{"title": "Les métiers en 2030", "url": "https://dares.travail-emploi.gouv.fr/etude",
                 "snippet": "Près de 760 000 recrutements annuels sont projetés d'ici 2030."}]

    graph = create_deep_search_graph(Settings(_env_file=None, demo_mode=True), "", [], search)
    result = asyncio.run(graph.nodes["search"]({"question": "Recrutements", "queries": ["métiers 2030"]}))
    assert result["sources"][0]["tier"] == "A"


def test_page_read_activity_distinguishes_full_text_from_failed_fetch(monkeypatch):
    from app import web

    async def fetch(settings, url):
        if url.endswith("/ok"):
            return {"text": "Contenu documentaire effectivement récupéré. " * 10}
        raise RuntimeError("Page indisponible")

    monkeypatch.setattr(web, "fetch_and_parse_web_url", fetch)
    sources = [{"url": "https://example.org/ok"}, {"url": "https://example.org/unavailable"}]
    notifications = []
    asyncio.run(enrich_top_sources_content(
        SimpleNamespace(demo_mode=False), sources,
        on_source_read=lambda source, success: notifications.append((source["url"], success)),
    ))
    assert (sources[0]["url"], True) in notifications
    assert (sources[1]["url"], False) in notifications
    assert sources[0]["content"]
    assert "content" not in sources[1]
