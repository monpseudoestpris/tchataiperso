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


@pytest.fixture
def settings():
    return SimpleNamespace(
        llm_base_url="https://llm.example/v1/",
        llm_api_key=SecretStr("fake-llm-secret"),
        llm_temperature=0.35,
        llm_max_tokens=3072,
        summary_temperature=0.15,
        summary_max_tokens=1200,
        brave_api_key=SecretStr("fake-brave-secret"),
        mistral_api_key=SecretStr("fake-mistral-secret"),
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
        assert payload == {
            "model": "mistral-ocr-latest", "include_image_base64": False,
            "document": {"type": kind, url_field: f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"},
        }
        return httpx.Response(200, json={"pages": [{"markdown": "# Page 1"}, {"markdown": "Page 2"}]})

    transport(handler)
    assert asyncio.run(providers.extract_ocr(settings, content, mime_type)) == "# Page 1\n\nPage 2"


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
