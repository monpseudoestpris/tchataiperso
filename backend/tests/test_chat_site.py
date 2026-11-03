"""Chat-to-Pages generation, fallback, scope, ownership and script isolation."""

import asyncio
import json
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
import httpx
from pydantic import SecretStr

from app import chat_site, providers
from app.config import Settings
from app.models import Conversation, Message, User
from app.page_generator import generate_page_html
from test_api import authenticated_client


class Frames(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.frames = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            self.frames.append(dict(attrs))


def test_site_uses_pages_and_isolates_html(monkeypatch):
    calls = []

    async def generate(**kwargs):
        calls.append(kwargs)
        return "Titre", '<html><body><svg></svg><script>parent.attack()</script></body></html>'

    monkeypatch.setattr(chat_site, "generate_page_html", generate)
    messages = [{"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Réponse [1]", "sources": [{"url": "https://example.org"}]}]
    document = asyncio.run(chat_site.generate_chat_site(
        SimpleNamespace(demo_mode=False), '<Titre>', messages,
    ))
    call = calls[0]
    assert json.loads(call["chat_transcript"]) == [
        {"role": m["role"], "content": m["content"], "sources": m.get("sources", [])} for m in messages
    ]
    assert call["include_svg"] and not call["include_quiz"]
    assert call["page_type"] == "article" and call["raise_on_failure"]
    assert '<script>parent.attack()' not in document
    frames = Frames(document).frames
    assert len(frames) == 1
    assert frames[0]["sandbox"] == ""
    assert "script-src &#x27;none&#x27;" in frames[0]["srcdoc"]
    assert call["interactivity"] == "none"
    assert 'connect-src &#x27;none&#x27;' in frames[0]["srcdoc"]
    assert "Content-Security-Policy" in frames[0]["srcdoc"]
    assert "Original" not in document
    assert "Question" not in document
    assert "Réponse [1]" not in document
    assert '&lt;Titre&gt;' in document
    assert "Échanges originaux" not in document
    assert "?pdf=1" not in document


@pytest.mark.parametrize("demo", [True, False])
def test_unavailable_generation_never_embeds_actual_chat(monkeypatch, demo):
    async def unavailable(**kwargs):
        raise providers.ProviderError("unavailable")

    monkeypatch.setattr(chat_site, "generate_page_html", unavailable)
    result = asyncio.run(chat_site.generate_chat_site(
        SimpleNamespace(demo_mode=demo), "Titre", [{"role": "assistant", "content": "Fait réel"}],
    ))
    assert "synthèse IA est indisponible" in result
    assert "Fait réel" not in result
    assert len(Frames(result).frames) == 1


def test_empty_chat_shows_only_empty_state():
    result = asyncio.run(chat_site.generate_chat_site(
        SimpleNamespace(demo_mode=True), "Titre", [],
    ))
    assert "Aucune information à synthétiser" in result
    assert len(Frames(result).frames) == 1


def test_long_chat_includes_last_messages_and_compresses(monkeypatch):
    seen = []

    async def summarize(settings, model, previous, transcript):
        seen.append(transcript)
        return "Résumé " + ("DÉCISION FINALE" if "DÉCISION FINALE" in transcript else "du début")

    monkeypatch.setattr(providers, "summarize", summarize)
    settings = SimpleNamespace(summary_model="summary", default_model="default")
    result = asyncio.run(chat_site._transcript(settings, [
        {"role": "assistant", "content": "texte " * 5000},
        {"role": "user", "content": "DÉCISION FINALE"},
    ]))
    assert len(seen) > 1 and len(result) < 23000
    assert "DÉCISION FINALE" in result


def test_withdrawn_report_never_reaches_pages(monkeypatch):
    async def generate(**kwargs):
        assert "CHIFFRE NON VALIDÉ" not in kwargs["chat_transcript"]
        assert "révision documentaire requise" in kwargs["chat_transcript"]
        return "Titre", '<html><body>Révision requise</body></html>'

    monkeypatch.setattr(chat_site, "generate_page_html", generate)
    asyncio.run(chat_site.generate_chat_site(SimpleNamespace(demo_mode=False), "Titre", [
        {"role": "assistant", "content": "🔴 Révision requise CHIFFRE NON VALIDÉ"},
    ]))


def test_strict_pages_demo_refuses_generic_fallback(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    with pytest.raises(providers.ProviderError):
        asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))


@pytest.mark.parametrize("content,finish,valid", [
    ('<!doctype html><html><body><svg></svg>Synthèse</body></html>', 'stop', True),
    ('<!doctype html><html><body>Inachevé', 'stop', False),
    ('<!doctype html><html><body>Inachevé</body></html>', 'length', False),
])
def test_strict_pages_provider_result(tmp_path, monkeypatch, content, finish, valid):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False,
                        llm_api_key=SecretStr("test-only-placeholder"))

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            assert kwargs["json"]["model"] == settings.page_model
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "choices": [{"message": {"content": content}, "finish_reason": finish}],
            })

    monkeypatch.setattr("app.page_generator.httpx.AsyncClient", Client)
    if valid:
        _, result = asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))
        assert "Synthèse" in result and "<svg" in result
    else:
        with pytest.raises(providers.ProviderError):
            asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))


@pytest.mark.parametrize("partial,finish", [
    ('<html><body>RÉPONSE TRONQUÉE', 'stop'),
    ('<html><body>RÉPONSE TRONQUÉE</body></html>', 'length'),
])
def test_incomplete_page_retries_compact_document_without_partial_content(tmp_path, monkeypatch, partial, finish):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False,
                        llm_api_key=SecretStr("test-only-placeholder"))
    requests = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            requests.append(kwargs["json"])
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "choices": [{"message": {"content": partial if len(requests) == 1 else
                            '<html><body><svg></svg>SYNTHÈSE COMPLÈTE</body></html>'},
                             "finish_reason": finish if len(requests) == 1 else "stop"}],
            })

    monkeypatch.setattr("app.page_generator.httpx.AsyncClient", Client)
    _, result = asyncio.run(generate_page_html(
        settings, "Instructions originales", chat_transcript="Informations du tchat",
        raise_on_failure=True,
    ))
    assert "SYNTHÈSE COMPLÈTE" in result and "RÉPONSE TRONQUÉE" not in result
    assert len(requests) == 2
    assert requests[1]["messages"][:2] == requests[0]["messages"]
    assert "Informations du tchat" in requests[1]["messages"][1]["content"]
    assert "RÉPONSE TRONQUÉE" not in str(requests[1])
    assert "600 mots maximum" in requests[1]["messages"][-1]["content"]
    assert requests[1]["temperature"] == 0.2


def test_repeated_incomplete_page_has_bounded_retry(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False,
                        llm_api_key=SecretStr("test-only-placeholder"))
    requests = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            requests.append(kwargs["json"])
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "choices": [{"message": {"content": '<html><body>Tronqué'}, "finish_reason": "length"}],
            })

    monkeypatch.setattr("app.page_generator.httpx.AsyncClient", Client)
    with pytest.raises(providers.ProviderError, match="seconde tentative compacte"):
        asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))
    assert len(requests) == 2


@pytest.mark.parametrize("status", [400, 404, 422, 401, 402, 429])
def test_pages_fallback_only_for_unsupported_model(tmp_path, monkeypatch, status):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False,
                        llm_api_key=SecretStr("test-only-placeholder"))
    models = []

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            models.append(kwargs["json"]["model"])
            if len(models) == 1:
                return httpx.Response(status, request=httpx.Request("POST", url),
                                      text="PRIVATE PROVIDER DETAILS")
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "choices": [{"message": {"content": '<html><body>Synthèse</body></html>'}}],
            })

    monkeypatch.setattr("app.page_generator.httpx.AsyncClient", Client)
    if status in (400, 404, 422):
        _, page = asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))
        assert "Synthèse" in page
        assert models == [settings.page_model, settings.default_model]
    else:
        with pytest.raises(providers.ProviderError, match=f"HTTP {status}") as error:
            asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))
        assert "PRIVATE PROVIDER DETAILS" not in str(error.value)
        assert models == [settings.page_model]


@pytest.mark.parametrize("exception,expected", [
    (httpx.ReadTimeout("PRIVATE DETAILS"), "délai autorisé"),
    (httpx.ConnectError("PRIVATE DETAILS"), "Impossible de joindre"),
])
def test_pages_network_error_is_actionable_and_safe(tmp_path, monkeypatch, exception, expected):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False,
                        llm_api_key=SecretStr("test-only-placeholder"))

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            raise exception

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("app.page_generator.httpx.AsyncClient", Client)
    with pytest.raises(providers.ProviderError, match=expected) as error:
        asyncio.run(generate_page_html(settings, "Sujet", raise_on_failure=True))
    assert "PRIVATE DETAILS" not in str(error.value)


def test_chat_site_displays_sanitized_failure_reason(monkeypatch):
    async def unavailable(**kwargs):
        raise providers.ProviderError("Fournisseur IA : crédit insuffisant (HTTP 402).")

    monkeypatch.setattr(chat_site, "generate_page_html", unavailable)
    result = asyncio.run(chat_site.generate_chat_site(
        SimpleNamespace(demo_mode=False), "Titre", [{"role": "user", "content": "Question privée"}],
    ))
    assert "crédit insuffisant (HTTP 402)" in Frames(result).frames[0]["srcdoc"]
    assert "Question privée" not in result


def test_export_routes_scope_pdf_download_and_ownership(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    calls = []

    async def site(settings, title, messages, **kwargs):
        calls.append(messages)
        return "<!doctype html><html><body>PAGE SYNTHÉTISÉE</body></html>"

    monkeypatch.setattr("app.chat_site_store.generate_chat_site", site)
    with authenticated_client(settings) as client:
        with client.app.state.sessions() as db:
            user = db.query(User).filter_by(username="tester").one()
            conv = Conversation(user_id=user.id, title="Sujet", model="demo")
            db.add(conv)
            db.flush()
            messages = [Message(conversation_id=conv.id, role=role, content=content)
                        for role, content in [("user", "Première question"), ("assistant", "Première réponse"),
                                              ("user", "Dernière question"), ("assistant", "Dernière réponse")]]
            db.add_all(messages)
            db.commit()
            conv_id, msg_id = conv.id, messages[-1].id
            other = User(username="other", password_hash="unused")
            db.add(other)
            db.flush()
            private = Conversation(user_id=other.id, title="Privé", model="demo")
            db.add(private)
            db.commit()
            private_id = private.id
        url = f"/api/messages/{msg_id}/html"
        response = client.get(url)
        assert response.status_code == 200 and "PAGE SYNTHÉTISÉE" in response.text
        assert [m["content"] for m in calls[-1]] == ["Dernière question", "Dernière réponse"]
        assert client.get(url + "?scope=conversation").status_code == 200
        assert len(calls[-1]) == 4
        response = client.get(f"/api/conversations/{conv_id}/html?download=1")
        assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
        assert len(calls[-1]) == 4
        count = len(calls)
        for pdf_url in [url + "?pdf=1", url + "?print=1", f"/api/conversations/{conv_id}/html?pdf=1"]:
            response = client.get(pdf_url)
            assert response.status_code == 200 and "PAGE SYNTHÉTISÉE" not in response.text
        assert len(calls) == count
        assert client.get(f"/api/conversations/{private_id}/html").status_code == 404
        assert len(calls) == count
