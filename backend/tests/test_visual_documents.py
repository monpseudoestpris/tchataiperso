"""Tests unitaires et d'intégration pour l'ingestion et la consultation de documents illustrés."""

from __future__ import annotations

import base64
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from pypdf import PdfWriter
from sqlalchemy import select

from app import providers, visual_documents
from app.auth import hash_password
from app.config import Settings
from app.context import VISUAL_DOC_SYSTEM_PROMPT, build_context
from app.main import create_app
from app.models import Base, User


def _make_png_bytes(color: tuple[int, int, int] = (40, 120, 210), size: tuple[int, int] = (240, 160)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_pdf_bytes(page_count: int = 2) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=400, height=600)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _create_app_with_users(settings: Settings):
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        for username, is_admin in (("alice", True), ("bob", False)):
            if not db.scalar(select(User).where(User.username == username)):
                db.add(User(username=username, password_hash=hash_password("correct horse battery"), is_admin=is_admin))
        db.commit()
    return app


def _login(app, settings: Settings, username: str) -> TestClient:
    origin = settings.origins[0]
    client = TestClient(app, base_url=origin, headers={"Origin": origin})
    resp = client.post("/api/auth/login", json={"username": username, "password": "correct horse battery"})
    assert resp.status_code == 200
    return client


def test_ingest_pdf_with_mistral_ocr_saves_webp_figures_pages_and_compiles_markdown(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        mistral_api_key=SecretStr("test-mistral-key"),
    )
    app = _create_app_with_users(settings)

    fig_b64 = base64.b64encode(_make_png_bytes((220, 80, 50), (120, 90))).decode("ascii")

    async def fake_extract_visual_ocr_pages(_settings, *, pdf_bytes=None, page_count=1, image_pages=None):
        assert pdf_bytes is not None
        assert page_count == 2
        return [
            {
                "index": 0,
                "markdown": "### Carte Bâtiment\n\nVoici le détail d'une carte :\n\n![img-0.jpeg](img-0.jpeg)",
                "images": [
                    {
                        "id": "img-0.jpeg",
                        "top_left_x": 10,
                        "top_left_y": 20,
                        "bottom_right_x": 200,
                        "bottom_right_y": 180,
                        "image_base64": f"data:image/png;base64,{fig_b64}",
                        "image_annotation": json.dumps({
                            "image_type": "Anatomie de carte",
                            "short_title": "Anatomie d'une carte Bâtiment",
                            "detailed_description": "Coût en bois à gauche (1), points de victoire en haut à droite (2), effet permanent en bas (3).",
                            "visible_text": "1 Bois | 2 PV | Effet : +1 blé",
                        }),
                    }
                ],
                "dimensions": {"width": 400, "height": 600},
            },
            {
                "index": 1,
                "markdown": "### Fin de partie\n\nLes points ne comptent que si le bâtiment est construit avant le dernier tour.",
                "images": [],
                "dimensions": {"width": 400, "height": 600},
            },
        ]

    monkeypatch.setattr(visual_documents, "extract_visual_ocr_pages", fake_extract_visual_ocr_pages)

    with _login(app, settings, "alice") as alice:
        pdf_bytes = _make_pdf_bytes(2)
        resp = alice.post(
            "/api/visual-docs",
            data={"title": "Catan — Règles de base", "enrich_vision": "false"},
            files=[("files", ("catan_rules.pdf", pdf_bytes, "application/pdf"))],
        )
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        slug = doc["slug"]

        assert doc["source_type"] == "pdf"
        assert doc["page_count"] == 2
        assert doc["figure_count"] == 1
        assert f"/api/docs/{slug}/p1_fig1.webp" in doc["compiled_markdown"]
        assert "points de victoire en haut à droite (2)" in doc["compiled_markdown"]
        assert "## [p. 1]" in doc["compiled_markdown"]
        assert f"/api/docs/{slug}/page_1.webp" in doc["compiled_markdown"]
        assert f"/api/docs/{slug}/page_2.webp" in doc["compiled_markdown"]

        # Vérification des fichiers WebP servis au propriétaire
        fig_resp = alice.get(f"/api/docs/{slug}/p1_fig1.webp")
        assert fig_resp.status_code == 200
        assert fig_resp.headers["content-type"] == "image/webp"
        assert fig_resp.headers["x-content-type-options"] == "nosniff"
        assert fig_resp.content[:4] == b"RIFF"

        page2_resp = alice.get(f"/api/docs/{slug}/page_2.webp")
        assert page2_resp.status_code == 200
        assert page2_resp.headers["content-type"] == "image/webp"

        # Path traversal et extensions invalides refusées
        assert alice.get(f"/api/docs/{slug}/../secret.webp").status_code == 404
        assert alice.get(f"/api/docs/{slug}/p1_fig1.png").status_code == 404

        # Isolation multi-utilisateurs : Bob ne peut pas lire les assets d'Alice
        with _login(app, settings, "bob") as bob:
            assert bob.get(f"/api/docs/{slug}/p1_fig1.webp").status_code == 404
            assert bob.get(f"/api/visual-docs/{doc['id']}").status_code == 404

        # Non authentifié -> 401
        with TestClient(app, base_url=settings.origins[0]) as anon:
            assert anon.get(f"/api/docs/{slug}/p1_fig1.webp").status_code == 401

        # Suppression nettoie la base et le dossier sur disque
        doc_dir = tmp_path / "visual_docs" / doc["id"]
        assert doc_dir.is_dir()
        assert alice.delete(f"/api/visual-docs/{doc['id']}").status_code == 204
        assert not doc_dir.exists()


def test_ingest_image_list_and_bbox_crop_fallback(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        mistral_api_key=SecretStr("test-mistral-key"),
    )
    app = _create_app_with_users(settings)

    async def fake_extract_visual_ocr_pages(_settings, *, pdf_bytes=None, page_count=1, image_pages=None):
        assert pdf_bytes is None
        assert image_pages is not None and len(image_pages) == 2
        return [
            {
                "index": 0,
                "markdown": "Mise en place du plateau\n\n![img-0.jpeg](img-0.jpeg)",
                "images": [
                    {
                        "id": "img-0.jpeg",
                        # Pas d'image_base64 -> le moteur doit découper depuis page_1.webp via bbox !
                        "top_left_x": 20,
                        "top_left_y": 20,
                        "bottom_right_x": 180,
                        "bottom_right_y": 140,
                        "image_annotation": {
                            "image_type": "Mise en place",
                            "short_title": "Schéma de mise en place",
                            "detailed_description": "Tuiles hexagones au centre entourées par les ports.",
                            "visible_text": "Port 2:1",
                        },
                    }
                ],
                "dimensions": {"width": 240, "height": 160},
            },
            {
                "index": 1,
                "markdown": "Tour de jeu et échanges commerciaux.",
                "images": [],
                "dimensions": {"width": 240, "height": 160},
            },
        ]

    monkeypatch.setattr(visual_documents, "extract_visual_ocr_pages", fake_extract_visual_ocr_pages)

    with _login(app, settings, "alice") as alice:
        img1 = _make_png_bytes((30, 160, 90), (240, 160))
        img2 = _make_png_bytes((90, 60, 180), (240, 160))
        resp = alice.post(
            "/api/visual-docs",
            data={"title": "Photos Livret", "enrich_vision": "false"},
            files=[
                ("files", ("p1.png", img1, "image/png")),
                ("files", ("p2.png", img2, "image/png")),
            ],
        )
        assert resp.status_code == 201, resp.text
        doc = resp.json()
        assert doc["source_type"] == "images"
        assert doc["page_count"] == 2
        assert doc["figure_count"] == 1
        assert alice.get(f"/api/docs/{doc['slug']}/p1_fig1.webp").status_code == 200
        assert alice.get(f"/api/docs/{doc['slug']}/page_1.webp").status_code == 200
        assert alice.get(f"/api/docs/{doc['slug']}/page_2.webp").status_code == 200


def test_conversation_visual_doc_context_injects_proactive_prompt_and_webp_urls(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key=SecretStr("test-llm-key"),
        mistral_api_key=SecretStr("test-mistral-key"),
    )
    app = _create_app_with_users(settings)

    async def fake_extract(_settings, *, pdf_bytes=None, page_count=1, image_pages=None):
        return [
            {
                "index": 0,
                "markdown": "Page 6 : ![img-0.jpeg](img-0.jpeg)",
                "images": [
                    {
                        "id": "img-0.jpeg",
                        "top_left_x": 10,
                        "top_left_y": 10,
                        "bottom_right_x": 150,
                        "bottom_right_y": 150,
                        "image_annotation": {
                            "image_type": "Carte",
                            "short_title": "Anatomie d'une carte Bâtiment",
                            "detailed_description": "Points de victoire en haut à droite (2).",
                            "visible_text": "2 PV",
                        },
                    }
                ],
                "dimensions": {"width": 400, "height": 600},
            }
        ]

    captured_context: list[dict] = []

    async def fake_stream_chat(_settings, context, _model, **_kwargs):
        captured_context.extend(context)
        yield "Le symbole en haut à droite **(2)** indique les Points de Victoire [p. 1]."

    monkeypatch.setattr(visual_documents, "extract_visual_ocr_pages", fake_extract)
    monkeypatch.setattr(providers, "stream_chat", fake_stream_chat)

    with _login(app, settings, "alice") as alice:
        doc_resp = alice.post(
            "/api/visual-docs",
            data={"title": "Catan", "enrich_vision": "false"},
            files=[("files", ("catan.pdf", _make_pdf_bytes(1), "application/pdf"))],
        )
        assert doc_resp.status_code == 201
        doc = doc_resp.json()

        conv_resp = alice.post("/api/conversations", json={"title": "Règles Catan", "visual_doc_ids": [doc["id"]]})
        assert conv_resp.status_code == 201
        conv = conv_resp.json()
        assert [d["id"] for d in conv["visual_docs"]] == [doc["id"]]

        msg_resp = alice.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "Ça veut dire quoi le symbole en haut à droite ?", "web_search": False, "auto_web_search": False},
        )
        assert msg_resp.status_code == 200
        assert captured_context
        system_msg = captured_context[0]["content"]
        assert "Sois visuellement proactif" in system_msg
        full_prompt_text = "\n".join(str(m.get("content", "")) for m in captured_context)
        assert f"/api/docs/{doc['slug']}/p1_fig1.webp" in full_prompt_text
        assert "Points de victoire en haut à droite (2)" in full_prompt_text


def test_build_visual_docs_context_keeps_intact_image_urls_on_large_manual():
    pages = []
    for p in range(1, 35):
        body = f"## [p. {p}]\n\n" + ("Règle détaillée sur le commerce et les ressources. " * 40)
        if p == 18:
            body += "\n\n![Anatomie d'une carte Bâtiment : symbole dragon en haut à droite](/api/docs/dragon-123456/p18_fig1.webp)"
        pages.append({
            "page": p,
            "page_image": f"page_{p}.webp",
            "page_image_url": f"/api/docs/dragon-123456/page_{p}.webp",
            "compiled_markdown": body,
            "figures": [
                {
                    "id": f"p{p}_fig1",
                    "url": f"/api/docs/dragon-123456/p{p}_fig1.webp",
                    "alt": "symbole dragon en haut à droite" if p == 18 else "illustration générique",
                }
            ] if p == 18 else [],
        })
    doc = {
        "title": "Gros Manuel",
        "slug": "dragon-123456",
        "page_count": len(pages),
        "figure_count": 1,
        "compiled_markdown": "\n\n".join(p["compiled_markdown"] for p in pages),
        "pages_meta": pages,
    }
    selected = visual_documents.build_visual_docs_context(
        [doc],
        query_text="Que signifie le symbole dragon en haut à droite ?",
        max_chars=12000,
    )
    assert "![Anatomie d'une carte Bâtiment : symbole dragon en haut à droite](/api/docs/dragon-123456/p18_fig1.webp)" in selected


def test_build_context_injects_visual_doc_system_prompt():
    settings = Settings(_env_file=None, demo_mode=True)
    ctx = build_context(
        settings=settings,
        summary="",
        memories=[],
        messages=[{"role": "user", "content": "Comment marche la carte Bâtiment ?", "attachments": []}],
        sources=[],
        vision=False,
        visual_docs=[{
            "title": "Catan",
            "slug": "catan-112233",
            "page_count": 6,
            "figure_count": 1,
            "compiled_markdown": "## [p. 6]\n\n![Carte Bâtiment](/api/docs/catan-112233/p6_fig1.webp)",
            "pages_meta": [],
        }],
    )
    assert VISUAL_DOC_SYSTEM_PROMPT in ctx[0]["content"]
    assert any("/api/docs/catan-112233/p6_fig1.webp" in str(m.get("content", "")) for m in ctx)
