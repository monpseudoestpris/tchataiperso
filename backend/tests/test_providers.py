"""Provider contracts exercised through local transports, without paid API calls."""

import asyncio
import base64
import json
import socket
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app import providers
from app.config import Settings
from app.schemas import DocumentExtraction


def test_extraction_accepts_empty_page_for_vision_fallback():
    extraction = DocumentExtraction.model_validate({
        "model": "mistral-ocr-4-1", "pages": [{"index": 0, "markdown": ""}],
    })
    assert extraction.pages[0].markdown == ""
    assert extraction.pages[0].method == "ocr"
    with pytest.raises(ValueError):
        DocumentExtraction.model_validate({"model": "mistral-ocr-4-1", "pages": []})


@pytest.fixture
def settings():
    return SimpleNamespace(
        llm_base_url="https://llm.example/v1/",
        llm_api_key=SecretStr("fake-llm-secret"),
        llm_temperature=0.35,
        llm_max_tokens=3072,
        summary_temperature=0.15,
        summary_max_tokens=1200,
        demo_mode=False,
        duckduckgo_enabled=False,
        brave_api_key=SecretStr("fake-brave-secret"),
        mistral_api_key=SecretStr("fake-mistral-secret"),
        ocr_model="mistral-ocr-4-1",
        vision_model="example/vision",
        ideogram_api_key=SecretStr("fake-ideogram-secret"),
        ideogram_image_hosts="ideogram.ai,images.example",
    )


@pytest.fixture(autouse=True)
def prohibit_dns(monkeypatch):
    def unavailable_dns(*args, **kwargs):
        raise AssertionError("Provider adapters must not resolve DNS outside the HTTPS proxy")

    monkeypatch.setattr(socket, "getaddrinfo", unavailable_dns)


@pytest.fixture
def transport(monkeypatch):
    """Keep real HTTPX serialization/streaming, replacing only network I/O."""
    client_class = httpx.AsyncClient

    def install(handler):
        def make_client(**kwargs):
            assert kwargs["follow_redirects"] is False
            return client_class(transport=httpx.MockTransport(handler), trust_env=False, **kwargs)

        monkeypatch.setattr(providers.httpx, "AsyncClient", make_client)

    return install


class Chunks(httpx.AsyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


async def collect_chat(settings):
    return [chunk async for chunk in providers.stream_chat(
        settings, [{"role": "user", "content": "Bonjour"}], "example/model"
    )]


def test_chat_stream_reads_chunked_sse_and_sends_provider_contract(settings, transport):
    def handler(request):
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer fake-llm-secret"
        assert request.headers["accept"] == "text/event-stream"
        assert json.loads(request.content) == {
            "model": "example/model", "messages": [{"role": "user", "content": "Bonjour"}],
            "stream": True, "temperature": 0.35, "max_tokens": 3072,
        }
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Chunks(
            b': keepalive\r\nevent: message\r\ndata: {"choices":[{"delta":{"content":"Bon',
            b'jour"},"finish_reason":null}]}\r\n\r\n',
            b'data: {"choices":\ndata: [{"delta":{"content":" !"},"finish_reason":"stop"}]}\n\n',
            b'data: {"choices":[],"usage":{"total_tokens":4}}\n\ndata: [DONE]\n\n',
        ))

    transport(handler)
    assert asyncio.run(collect_chat(settings)) == ["Bonjour", " !"]


def test_chat_returns_at_done_without_waiting_for_connection_to_close(settings, transport):
    class CompleteThenTimeout(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"Complete"},"finish_reason":"stop"}]}\n\n'
            yield b'data: [DONE]\n\n'
            raise httpx.ReadTimeout("The provider left the connection open after completion")

    transport(lambda request: httpx.Response(
        200, headers={"content-type": "text/event-stream"}, stream=CompleteThenTimeout()
    ))
    assert asyncio.run(collect_chat(settings)) == ["Complete"]


@pytest.mark.parametrize("status", [401, 429, 500])
def test_chat_provider_errors_do_not_expose_body_or_secret(settings, transport, status):
    unsafe = "fake-llm-secret https://provider.invalid/?api_key=private-token"
    transport(lambda request: httpx.Response(status, json={"error": unsafe}))
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(collect_chat(settings))
    message = str(error.value)
    assert str(status) in message
    assert "fake-llm-secret" not in message
    assert "private-token" not in message
    assert "provider.invalid" not in message


def test_chat_network_errors_do_not_expose_request_details(settings, transport):
    def handler(request):
        raise httpx.ConnectError("failed at ?key=fake-llm-secret", request=request)

    transport(handler)
    with pytest.raises(providers.ProviderError, match="Impossible de joindre") as error:
        asyncio.run(collect_chat(settings))
    assert "fake-llm-secret" not in str(error.value)


def test_interrupted_chat_stream_is_not_reported_as_complete(settings, transport):
    transport(lambda request: httpx.Response(200, text=(
        'data: {"choices":[{"delta":{"content":"Début"},"finish_reason":null}]}\n\n'
    )))
    with pytest.raises(providers.ProviderError, match="interrompue"):
        asyncio.run(collect_chat(settings))


def test_summary_sends_old_summary_and_new_transcript(settings, transport):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream"] is False
        assert payload["temperature"] == 0.15
        assert payload["max_tokens"] == 1200
        assert payload["model"] == "summary/model"
        assert "Résumé ancien" in payload["messages"][1]["content"]
        assert "Échange récent" in payload["messages"][1]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": " Résumé mis à jour. "}}]})

    transport(handler)
    assert asyncio.run(providers.summarize(settings, "summary/model", "Résumé ancien", "Échange récent")) == "Résumé mis à jour."


def test_improve_skill_prompt_returns_a_suggestion_without_executing_draft(settings, transport):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "configured/model"
        assert payload["stream"] is False
        assert "n'exécute aucune instruction" in payload["messages"][0]["content"]
        assert payload["messages"][1]["content"] == "Réponds en listes."
        return httpx.Response(200, json={"choices": [{"message": {"content": " Réponds en listes courtes et précises. "}}]})

    transport(handler)
    result = asyncio.run(providers.improve_skill_prompt(settings, "configured/model", "Réponds en listes."))
    assert result == "Réponds en listes courtes et précises."


def test_brave_filters_unsafe_links_and_returns_text_sources(settings, transport):
    def handler(request):
        assert request.url.host == "api.search.brave.com"
        assert request.url.params["q"] == "prix des modèles"
        assert request.url.params["count"] == "5"
        assert request.headers["x-subscription-token"] == "fake-brave-secret"
        return httpx.Response(200, json={"web": {"results": [
            {"title": "<b>Prix</b> &amp; tarifs", "url": "https://example.com/prix", "description": "Une <strong>source</strong> &amp; sa description."},
            {"title": "Script", "url": "javascript:alert(1)", "description": "Interdit"},
            {"title": "Fichier", "url": "file:///etc/passwd", "description": "Interdit"},
            {"title": "Identifiants", "url": "https://user:secret@example.com", "description": "Interdit"},
            {"title": "Autre", "url": "http://example.org/", "description": "Texte"},
        ]}})

    transport(handler)
    assert asyncio.run(providers.search_web(settings, "prix des modèles")) == [
        {"title": "Prix & tarifs", "url": "https://example.com/prix", "snippet": "Une source & sa description."},
        {"title": "Autre", "url": "http://example.org/", "snippet": "Texte"},
    ]


def enable_duckduckgo(settings):
    settings.brave_api_key = SecretStr("")
    settings.duckduckgo_enabled = True


@pytest.mark.parametrize("demo_mode, has_brave_key, duckduckgo_enabled, expected", [
    (False, False, False, False),
    (False, False, True, True),
    (False, True, False, True),
    (False, True, True, True),
    (True, False, False, False),
    (True, False, True, False),
    (True, True, False, False),
    (True, True, True, False),
])
def test_config_web_search_enabled_respects_provider_flags_and_demo_mode(
    demo_mode, has_brave_key, duckduckgo_enabled, expected
):
    config = Settings(
        _env_file=None, demo_mode=demo_mode, duckduckgo_enabled=duckduckgo_enabled,
        brave_api_key=SecretStr("fake-brave-secret" if has_brave_key else ""),
    )
    assert config.web_search_enabled is expected


def test_duckduckgo_uses_official_instant_answers_and_extracts_all_source_types(settings, transport):
    enable_duckduckgo(settings)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.duckduckgo.com"
        assert request.url.path == "/"
        assert dict(request.url.params) == {
            "q": "Python & développement", "format": "json", "no_html": "1",
            "no_redirect": "1", "t": "clair",
        }
        assert "x-subscription-token" not in request.headers
        assert "authorization" not in request.headers
        assert "fake-brave-secret" not in str(request.url)
        return httpx.Response(200, json={
            "Heading": "<b>Python</b> &amp; code",
            "AbstractText": "Un <strong>langage</strong> &amp; ses outils.",
            "AbstractURL": "https://example.com/python",
            "Definition": "Une <em>définition</em> précise.",
            "DefinitionURL": "https://example.com/definition",
            "Results": [{"Text": "Résultat &amp; <b>source</b>", "FirstURL": "https://example.com/result"}],
            "RelatedTopics": [{"Name": "Groupe", "Topics": [
                {"Text": "Sujet <b>lié</b>", "FirstURL": "https://example.com/related"},
                {"Topics": [{"Text": "Sujet imbriqué", "FirstURL": "http://example.org/nested"}]},
            ]}],
            "Answer": "Réponse directe sans URL", "Redirect": "https://redirect.invalid/ignored",
        })

    transport(handler)
    sources = asyncio.run(providers.search_web(settings, "Python & développement"))
    assert [source["url"] for source in sources] == [
        "https://example.com/python", "https://example.com/definition", "https://example.com/result",
        "https://example.com/related", "http://example.org/nested",
    ]
    assert [source["snippet"] for source in sources] == [
        "Un langage & ses outils.", "Une définition précise.", "Résultat & source", "Sujet lié", "Sujet imbriqué",
    ]
    assert all(source["provider"] == "duckduckgo_instant_answers" for source in sources)
    assert all(isinstance(source["title"], str) and "<" not in source["title"] for source in sources)
    notice = sources[0]["search_notice"].lower()
    assert "brave" in notice and "configur" in notice
    assert "instantan" in notice and "sujets liés" in notice and "uniquement" in notice
    assert all("search_notice" not in source for source in sources[1:])
    assert len(calls) == 1


def test_brave_success_stays_primary_even_when_duckduckgo_is_enabled(settings, transport):
    settings.duckduckgo_enabled = True
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.search.brave.com"
        return httpx.Response(200, json={"web": {"results": [
            {"title": "Brave", "url": "https://example.com/brave", "description": "Source Brave"},
        ]}})

    transport(handler)
    assert asyncio.run(providers.search_web(settings, "query")) == [
        {"title": "Brave", "url": "https://example.com/brave", "snippet": "Source Brave"},
    ]
    assert len(calls) == 1


@pytest.mark.parametrize("outcome", ["no_key", "empty", "401", "429", "invalid_json", "timeout"])
def test_duckduckgo_fallback_runs_once_without_forwarding_brave_credentials(settings, transport, outcome):
    settings.duckduckgo_enabled = True
    if outcome == "no_key":
        settings.brave_api_key = SecretStr("")
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "api.search.brave.com":
            assert outcome != "no_key"
            assert request.headers["x-subscription-token"] == "fake-brave-secret"
            if outcome == "timeout":
                raise httpx.ReadTimeout("fake-brave-secret private provider URL", request=request)
            if outcome == "invalid_json":
                return httpx.Response(200, text="invalid fake-brave-secret")
            if outcome == "empty":
                return httpx.Response(200, json={"web": {"results": []}})
            return httpx.Response(int(outcome), json={"error": "fake-brave-secret"})
        assert request.url.host == "api.duckduckgo.com"
        assert "x-subscription-token" not in request.headers
        assert "authorization" not in request.headers
        assert "fake-brave-secret" not in str(request.url)
        return httpx.Response(200, json={
            "Heading": "Solution", "AbstractText": "Résultat de secours", "AbstractURL": "https://example.com/fallback",
        })

    transport(handler)
    sources = asyncio.run(providers.search_web(settings, "query"))
    assert len(sources) == 1
    assert sources[0]["url"] == "https://example.com/fallback"
    assert sources[0]["provider"] == "duckduckgo_instant_answers"
    notice = sources[0]["search_notice"]
    assert "instantan" in notice.lower() and "sujets liés" in notice.lower()
    assert "fake-brave-secret" not in notice
    assert "private provider URL" not in notice
    if outcome == "no_key":
        assert "configur" in notice.lower()
    elif outcome == "empty":
        assert "aucun résultat" in notice.lower()
    elif outcome in {"401", "429"}:
        assert outcome in notice and "Brave" in notice
    elif outcome == "invalid_json":
        assert "illisible" in notice.lower()
    else:
        assert "temps" in notice.lower()
    assert [request.url.host for request in calls] == (
        ["api.duckduckgo.com"] if outcome == "no_key" else ["api.search.brave.com", "api.duckduckgo.com"]
    )


def test_search_without_keys_and_with_duckduckgo_disabled_does_not_call_any_api(settings, transport):
    settings.brave_api_key = SecretStr("")
    calls = []
    transport(lambda request: calls.append(request) or pytest.fail("Disabled web search must not make a request"))
    with pytest.raises(providers.ProviderError):
        asyncio.run(providers.search_web(settings, "query"))
    assert calls == []


@pytest.mark.parametrize("outcome", ["empty", "401", "429", "invalid_json", "timeout"])
def test_duckduckgo_disabled_never_falls_back_from_brave(settings, transport, outcome):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.search.brave.com"
        if outcome == "timeout":
            raise httpx.ReadTimeout("private provider details", request=request)
        if outcome == "invalid_json":
            return httpx.Response(200, text="invalid-json")
        if outcome == "empty":
            return httpx.Response(200, json={"web": {"results": []}})
        return httpx.Response(int(outcome), json={"error": "private provider details"})

    transport(handler)
    if outcome == "empty":
        assert asyncio.run(providers.search_web(settings, "query")) == []
    else:
        with pytest.raises(providers.ProviderError):
            asyncio.run(providers.search_web(settings, "query"))
    assert len(calls) == 1


@pytest.mark.parametrize("has_brave_key", [False, True])
def test_web_search_in_demo_mode_refuses_all_external_calls(settings, transport, has_brave_key):
    settings.demo_mode = True
    settings.duckduckgo_enabled = True
    if not has_brave_key:
        settings.brave_api_key = SecretStr("")
    transport(lambda request: pytest.fail("Demo mode must not call an external API"))
    with pytest.raises(providers.ProviderError):
        asyncio.run(providers.search_web(settings, "query"))


@pytest.mark.parametrize("payload", [
    {},
    {"Answer": "Une réponse directe sans source", "AnswerType": "calc", "Redirect": "https://example.com/redirect"},
    {"AbstractText": "Sans URL", "Definition": "Sans URL", "Results": [], "RelatedTopics": []},
    {"Heading": {}, "AbstractText": 12, "AbstractURL": [], "Definition": [], "DefinitionURL": {},
     "Results": "not-a-list", "RelatedTopics": None},
    {"Results": [None, 42, "texte", {}, {"Text": 12, "FirstURL": "https://example.com/wrong-text"}],
     "RelatedTopics": [False, {"Topics": "not-a-list"}, {"Text": ["wrong"], "FirstURL": "https://example.com/wrong"}]},
])
def test_duckduckgo_empty_or_malformed_optional_fields_return_no_sources(settings, transport, payload):
    enable_duckduckgo(settings)
    transport(lambda request: httpx.Response(200, json=payload))
    assert asyncio.run(providers.search_web(settings, "query")) == []


def test_duckduckgo_filters_unsafe_urls_and_deduplicates_sources(settings, transport):
    enable_duckduckgo(settings)
    transport(lambda request: httpx.Response(200, json={
        "Heading": "Titre", "AbstractText": "Première source", "AbstractURL": "https://example.com/duplicate",
        "Definition": "Copie", "DefinitionURL": "https://example.com/duplicate",
        "Results": [
            {"Text": "Copie", "FirstURL": "https://example.com/duplicate"},
            {"Text": "Script", "FirstURL": "javascript:alert(1)"},
            {"Text": "Fichier", "FirstURL": "file:///etc/passwd"},
            {"Text": "Utilisateur", "FirstURL": "https://user:secret@example.com/private"},
            {"Text": "URL vide", "FirstURL": "https://"},
        ],
        "RelatedTopics": [{"Topics": [
            {"Text": "Copie imbriquée", "FirstURL": "https://example.com/duplicate"},
            {"Text": "Valide", "FirstURL": "http://example.org/valid"},
        ]}],
    }))
    sources = asyncio.run(providers.search_web(settings, "query"))
    assert [source["url"] for source in sources] == ["https://example.com/duplicate", "http://example.org/valid"]
    assert all(source["provider"] == "duckduckgo_instant_answers" for source in sources)


def test_duckduckgo_html_result_fallback_is_text_and_uses_only_explicit_source_url(settings, transport):
    enable_duckduckgo(settings)
    transport(lambda request: httpx.Response(200, json={"Results": [{
        "Result": '<a href="https://other.invalid/">&lt;b&gt;Source&lt;/b&gt; &amp; texte</a>',
        "FirstURL": "https://example.com/explicit-source",
    }]}))
    sources = asyncio.run(providers.search_web(settings, "query"))
    assert len(sources) == 1
    assert sources[0]["snippet"] == "Source & texte"
    assert sources[0]["url"] == "https://example.com/explicit-source"
    assert "<" not in sources[0]["title"]


def test_duckduckgo_limits_results_to_five(settings, transport):
    enable_duckduckgo(settings)
    transport(lambda request: httpx.Response(200, json={"RelatedTopics": [
        {"Text": f"Source {index}", "FirstURL": f"https://example.com/{index}"} for index in range(20)
    ]}))
    sources = asyncio.run(providers.search_web(settings, "query"))
    assert len(sources) == 5
    assert len({source["url"] for source in sources}) == 5


def test_duckduckgo_ignores_topics_nested_beyond_depth_limit(settings, transport):
    enable_duckduckgo(settings)
    topic = {"Text": "Trop profond", "FirstURL": "https://example.com/deep"}
    for _ in range(8):
        topic = {"Topics": [topic]}
    transport(lambda request: httpx.Response(200, json={"RelatedTopics": [topic]}))
    assert asyncio.run(providers.search_web(settings, "query")) == []


def test_duckduckgo_bounds_number_of_visited_topic_nodes(settings, transport):
    enable_duckduckgo(settings)
    topics = [{"Text": "Sans URL"} for _ in range(220)]
    topics.append({"Text": "Après la limite", "FirstURL": "https://example.com/too-late"})
    transport(lambda request: httpx.Response(200, json={"RelatedTopics": topics}))
    assert asyncio.run(providers.search_web(settings, "query")) == []


@pytest.mark.parametrize("outcome", ["401", "429", "500", "302", "invalid_json", "json_array", "timeout"])
def test_duckduckgo_errors_are_safe_and_do_not_retry(settings, transport, outcome):
    enable_duckduckgo(settings)
    unsafe = "private-provider-token https://private.invalid/?api_key=private-secret"
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "api.duckduckgo.com"
        if outcome == "timeout":
            raise httpx.ReadTimeout(unsafe, request=request)
        if outcome == "invalid_json":
            return httpx.Response(200, text=unsafe)
        if outcome == "json_array":
            return httpx.Response(200, json=[unsafe])
        return httpx.Response(int(outcome), json={"error": unsafe}, headers={"location": "https://private.invalid/redirect"})

    transport(handler)
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(providers.search_web(settings, "query"))
    message = str(error.value)
    assert "private-provider-token" not in message
    assert "private-secret" not in message
    assert "private.invalid" not in message
    assert len(calls) == 1


@pytest.mark.parametrize("duckduckgo_outcome", ["429", "invalid_json", "timeout"])
def test_failed_duckduckgo_fallback_preserves_the_brave_error(settings, transport, duckduckgo_outcome):
    settings.duckduckgo_enabled = True
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "api.search.brave.com":
            return httpx.Response(401, json={"error": "fake-brave-secret"})
        assert request.url.host == "api.duckduckgo.com"
        if duckduckgo_outcome == "timeout":
            raise httpx.ReadTimeout("private-ddg-details", request=request)
        if duckduckgo_outcome == "invalid_json":
            return httpx.Response(200, text="private-ddg-details")
        return httpx.Response(int(duckduckgo_outcome), json={"error": "private-ddg-details"})

    transport(handler)
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(providers.search_web(settings, "query"))
    assert "Brave" in str(error.value)
    assert "401" in str(error.value)
    assert "fake-brave-secret" not in str(error.value)
    assert "private-ddg-details" not in str(error.value)
    assert [request.url.host for request in calls] == ["api.search.brave.com", "api.duckduckgo.com"]


def test_empty_duckduckgo_fallback_preserves_a_prior_brave_error(settings, transport):
    settings.duckduckgo_enabled = True
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "api.search.brave.com":
            return httpx.Response(401, json={"error": "fake-brave-secret private-error"})
        assert request.url.host == "api.duckduckgo.com"
        return httpx.Response(200, json={"RelatedTopics": [], "Results": []})

    transport(handler)
    with pytest.raises(providers.ProviderError) as error:
        asyncio.run(providers.search_web(settings, "query"))
    assert "Brave" in str(error.value) and "401" in str(error.value)
    assert "fake-brave-secret" not in str(error.value)
    assert "private-error" not in str(error.value)
    assert [request.url.host for request in calls] == ["api.search.brave.com", "api.duckduckgo.com"]


def test_empty_brave_and_duckduckgo_responses_stay_a_normal_empty_result(settings, transport):
    settings.duckduckgo_enabled = True
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "api.search.brave.com":
            return httpx.Response(200, json={"web": {"results": []}})
        assert request.url.host == "api.duckduckgo.com"
        return httpx.Response(200, json={"RelatedTopics": [], "Results": []})

    transport(handler)
    assert asyncio.run(providers.search_web(settings, "query")) == []
    assert [request.url.host for request in calls] == ["api.search.brave.com", "api.duckduckgo.com"]


@pytest.mark.parametrize("mime_type, kind, url_field", [
    ("application/pdf", "document_url", "document_url"),
    ("image/png", "image_url", "image_url"),
])
def test_mistral_ocr_encodes_pdf_and_images(settings, transport, mime_type, kind, url_field):
    content = b"example local document bytes"

    def handler(request):
        assert str(request.url) == "https://api.mistral.ai/v1/ocr"
        assert request.headers["authorization"] == "Bearer fake-mistral-secret"
        payload = json.loads(request.content)
        assert payload["model"] == "mistral-ocr-4-1"
        assert payload["include_image_base64"] is False
        assert payload["document"] == {"type": kind, url_field: f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"}
        assert payload["bbox_annotation_format"]["type"] == "json_schema"
        assert payload["document_annotation_format"]["json_schema"]["strict"] is True
        assert payload["include_blocks"] is True
        assert "pas un resume" in payload["document_annotation_prompt"]
        figure_fields = payload["bbox_annotation_format"]["json_schema"]["schema"]["properties"]
        assert "verbatim" in figure_fields["visible_text"]["description"]
        return httpx.Response(200, json={"pages": [{"index": 0, "markdown": ""}]})

    transport(handler)
    extraction = asyncio.run(providers.extract_ocr(settings, content, mime_type))
    assert extraction.pages[0].markdown == ""


def test_ocr_batches_all_pages_and_parses_figure_annotations(settings, transport):
    requested = []

    def handler(request):
        indices = json.loads(request.content)["pages"]
        requested.extend(indices)
        return httpx.Response(200, json={
            "pages": [{"index": index, "markdown": f"Page {index}", "images": [{
                "id": "img-0.jpeg", "image_base64": "not-stored",
                "image_annotation": json.dumps({"image_type": "graphique", "description": f"Figure page {index}", "visible_text": "20 %"}),
            }]} for index in indices],
            "document_annotation": '{"title":"Rapport","summary":"Synthese"}',
        })

    transport(handler)
    result = asyncio.run(providers.extract_ocr(settings, b"pdf", "application/pdf", page_count=10))
    assert requested == list(range(10))
    assert result.pages[9].images[0].annotation.description == "Figure page 9"
    assert len(result.annotations) == 2
    assert "not-stored" not in result.model_dump_json()


@pytest.mark.parametrize("pages", [[], [{"index": 1, "markdown": "wrong page"}], [{"index": 0}]])
def test_ocr_rejects_incomplete_response(settings, transport, pages):
    transport(lambda request: httpx.Response(200, json={"pages": pages}))
    with pytest.raises(providers.ProviderError, match="invalide ou incomplet"):
        asyncio.run(providers.extract_ocr(settings, b"pdf", "application/pdf"))


def test_dedicated_vision_description(settings, transport):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["model"] == "example/vision"
        assert payload["stream"] is False
        assert payload["max_tokens"] == 8000
        assert "pas un resume" in payload["messages"][0]["content"]
        assert payload["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(200, json={"choices": [{"message": {"content": "Une page blanche."}, "finish_reason": "stop"}]})

    transport(handler)
    assert asyncio.run(providers.describe_image(settings, b"image", "image/png")) == "Une page blanche."


def multipart_fields(request):
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + request.headers["content-type"].encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + request.content
    )
    return {part.get_param("name", header="content-disposition"): part.get_payload(decode=True).decode("utf-8")
            for part in message.iter_parts()}


def test_ideogram_uses_multipart_then_downloads_without_api_key_or_dns(settings, transport):
    requests = []
    png = b"\x89PNG\r\n\x1a\nlocal-image-content"

    def handler(request):
        requests.append(request)
        if request.url.host == "api.ideogram.ai":
            assert request.method == "POST"
            assert request.headers["api-key"] == "fake-ideogram-secret"
            assert multipart_fields(request) == {
                "prompt": "Un renard dans la neige", "aspect_ratio": "16x9", "rendering_speed": "TURBO",
            }
            return httpx.Response(200, json={"data": [{"url": "https://images.example/image.png?signature=example"}]})
        assert request.method == "GET"
        assert request.url.host == "images.example"
        assert "api-key" not in request.headers
        assert "authorization" not in request.headers
        return httpx.Response(200, headers={"content-type": "image/png"}, stream=Chunks(png[:10], png[10:]))

    transport(handler)
    assert asyncio.run(providers.generate_image(settings, "Un renard dans la neige", "16:9")) == (png, "image/png")
    assert len(requests) == 2


@pytest.mark.parametrize("url", [
    "https://localhost/image.png",
    "https://sub.localhost/image.png",
    "https://images.local/image.png",
    "https://images.internal/image.png",
    "https://127.0.0.1/image.png",
    "https://10.1.2.3/image.png",
    "https://169.254.169.254/image.png",
    "https://93.184.216.34/image.png",
    "https://[::1]/image.png",
    "https://*.images.example/image.png",
    "https://images.example./image.png",
    "https://2130706433/image.png",
    "https://images.example:444/image.png",
    "https://user:secret@images.example/image.png",
    "https://images.example/image.png#fragment",
    "http://images.example/image.png",
])
def test_ideogram_rejects_unsafe_download_urls_without_dns(settings, transport, url):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api.ideogram.ai"
        return httpx.Response(200, json={"data": [{"url": url}]})

    transport(handler)
    with pytest.raises(providers.ProviderError, match="interdite"):
        asyncio.run(providers.generate_image(settings, "Un paysage", "1:1"))
    assert len(requests) == 1


@pytest.mark.parametrize("host", ["unknown.example", "cdn.images.example", "images.example.attacker.com"])
def test_ideogram_requires_exact_configured_host_without_leaking_signed_url(settings, transport, host):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "api.ideogram.ai"
        return httpx.Response(200, json={"data": [{"url": f"https://{host}/signed-secret-path?signature=private-token"}]})

    transport(handler)
    with pytest.raises(providers.ProviderError, match="IDEOGRAM_IMAGE_HOSTS") as error:
        asyncio.run(providers.generate_image(settings, "Un paysage", "1:1"))
    assert host in str(error.value)
    assert "politique réseau" in str(error.value)
    assert "private-token" not in str(error.value)
    assert "signed-secret-path" not in str(error.value)
    assert len(requests) == 1


def test_ideogram_default_domain_is_allowed_without_dns(settings):
    settings.ideogram_image_hosts = "ideogram.ai"
    url = "https://ideogram.ai/image.png"
    assert asyncio.run(providers._check_download_url(settings, url)) == url


def test_ideogram_wildcard_setting_cannot_authorize_subdomains(settings):
    settings.ideogram_image_hosts = "*.images.example"
    with pytest.raises(providers.ProviderError, match="IDEOGRAM_IMAGE_HOSTS"):
        asyncio.run(providers._check_download_url(settings, "https://cdn.images.example/image.png"))


def test_ideogram_download_does_not_follow_redirects(settings, transport):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.host == "api.ideogram.ai":
            return httpx.Response(200, json={"data": [{"url": "https://images.example/image.png"}]})
        return httpx.Response(302, headers={"location": "https://127.0.0.1/private"})

    transport(handler)
    with pytest.raises(providers.ProviderError, match="HTTP 302"):
        asyncio.run(providers.generate_image(settings, "Un paysage", "1:1"))
    assert len(requests) == 2
