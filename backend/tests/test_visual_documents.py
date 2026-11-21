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


def test_finance_report_bridge_to_visual_doc_and_conversation(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    app = _create_app_with_users(settings)
    from app.models import FinanceQuarterlyReport

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "finrep-test.pdf").write_bytes(_make_pdf_bytes(2))

    with app.state.sessions() as db:
        owner = db.scalar(select(User).where(User.username == "alice"))
        assert owner is not None
        report = FinanceQuarterlyReport(
            user_id=owner.id,
            symbol="MC.PA",
            company_name="LVMH",
            title="Résultats S1 2026",
            period_label="S1 2026",
            source_type="pdf-ocr",
            filename="lvmh-s1-2026.pdf",
            storage_name="finrep-test.pdf",
            extracted_text=(
                "[Page 1]\nChiffre d'affaires S1 2026 : 42,5 Md€ (+6%).\n\n"
                "[Page 2]\n| Division | CA (Md€) |\n| --- | --- |\n| Mode & Maroquinerie | 21,2 |"
            ),
            extracted_tables=[
                {
                    "index": 1,
                    "page": 2,
                    "title": "CA par division",
                    "rows_count": 2,
                    "cols_count": 2,
                    "markdown": "| Division | CA (Md€) |\n| --- | --- |\n| Mode & Maroquinerie | 21,2 |",
                }
            ],
            summary_markdown="Croissance organique solide portée par la Mode & Maroquinerie.",
            key_metrics={"revenue": "42,5 Md€", "operating_margin": "25,8 %"},
        )
        db.add(report)
        db.commit()
        report_id = report.id

    with _login(app, settings, "alice") as client:
        resp1 = client.post(f"/api/finance/reports/{report_id}/visual-doc")
        assert resp1.status_code == 200
        vdoc1 = resp1.json()
        assert vdoc1["page_count"] == 2
        assert "LVMH" in vdoc1["title"]
        assert "42,5 Md€" in vdoc1["compiled_markdown"]
        assert "Mode & Maroquinerie" in vdoc1["compiled_markdown"]
        assert f"/api/docs/{vdoc1['slug']}/page_1.webp" in vdoc1["compiled_markdown"]

        # Vérifie que la page WebP rendue est bien servie de manière sécurisée
        page_img = client.get(f"/api/docs/{vdoc1['slug']}/page_1.webp")
        assert page_img.status_code == 200
        assert page_img.headers["content-type"] == "image/webp"

        # Idempotence : un second appel retourne exactement le même VisualDocument
        resp2 = client.post(f"/api/finance/reports/{report_id}/visual-doc")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == vdoc1["id"]

        # Liaison à une conversation comme tout Document Illustré
        conv = client.post("/api/conversations", json={"title": "Analyse LVMH"}).json()
        attached = client.post(f"/api/conversations/{conv['id']}/visual-docs/{vdoc1['id']}")
        assert attached.status_code == 200
        assert any(d["id"] == vdoc1["id"] for d in attached.json()["visual_docs"])


def test_build_context_keeps_all_pages_for_71k_rulebook_and_plural_matching():
    """Vérifie qu'une règle de 12 pages (~71k car., type Res Arcana) est envoyée intégralement (dont p. 7)."""
    pages = []
    for p in range(1, 13):
        text = f"## [p. {p}]\n\n" + ("Explication détaillée des artefacts et essences. " * 115)
        if p == 7:
            text += "\n\n## Perte de Vie\nCertains pouvoirs infligeant de la perte de Vie (ex : les dragons) offrent une réaction."
        pages.append({
            "page": p,
            "page_image": f"page_{p}.webp",
            "page_image_url": f"/api/docs/res-arcana/page_{p}.webp",
            "compiled_markdown": text,
            "figures": [],
        })
    compiled_full = "\n\n".join(p["compiled_markdown"] for p in pages)
    assert len(compiled_full) > 65000

    settings = Settings(_env_file=None, demo_mode=True)
    ctx = build_context(
        settings=settings,
        summary="",
        memories=[],
        messages=[{"role": "user", "content": "Quand on se fait virer une carte par un dragon, qu'est-ce qu'on en fait ?", "attachments": []}],
        sources=[],
        vision=False,
        max_context_tokens=12000,
        visual_docs=[{
            "title": "Res Arcana",
            "slug": "res-arcana",
            "page_count": 12,
            "figure_count": 53,
            "compiled_markdown": compiled_full,
            "pages_meta": pages,
        }],
    )
    joined_ctx = "\n".join(str(m.get("content", "")) for m in ctx)
    assert "## [p. 7]" in joined_ctx
    assert "## [p. 12]" in joined_ctx

    # Même sous budget contraint, le singulier "dragon" matche le pluriel "dragons" de la page 7
    tight_selected = visual_documents.build_visual_docs_context(
        [{
            "title": "Res Arcana",
            "slug": "res-arcana",
            "page_count": 12,
            "figure_count": 53,
            "compiled_markdown": compiled_full,
            "pages_meta": pages,
        }],
        query_text="attaque d'un dragon ou voir page 7",
        max_chars=25000,
    )
    assert "## [p. 7]" in tight_selected


def test_build_visual_docs_context_keeps_all_40_pages_in_hybrid_mode():
    """Sur un gros livret de 40 pages très illustré (~260k car.), même si max_chars est borné à 120k,
    le mode hybride conserve 100 % des 40 pages (texte + URLs WebP) en condensant seulement les
    descriptions de figures des pages non prioritaires.
    """
    pages = []
    for p in range(1, 41):
        long_alt = (
            f"Anatomie détaillée figure page {p} : "
            + ("description spatiale très détaillée des icônes, coûts et repères numérotés (1) (2) (3). " * 10)
        )
        page_md = (
            f"## [p. {p}]\n\n"
            f"Texte complet des règles de la page {p} sur les phases de jeu et combats.\n\n"
            f"![{long_alt}](/api/docs/big-rulebook/p{p}_fig1.webp)\n\n"
            f"_Page originale de secours [p. {p}] : `/api/docs/big-rulebook/page_{p}.webp`_"
        )
        pages.append({
            "page": p,
            "page_image": f"page_{p}.webp",
            "page_image_url": f"/api/docs/big-rulebook/page_{p}.webp",
            "compiled_markdown": page_md,
            "figures": [
                {
                    "id": f"p{p}_fig1",
                    "url": f"/api/docs/big-rulebook/p{p}_fig1.webp",
                    "short_title": f"Schéma p.{p}",
                    "alt": long_alt,
                }
            ],
        })
    compiled_full = "\n\n".join(p["compiled_markdown"] for p in pages)
    doc = {
        "title": "Grosse Règle 40 Pages",
        "slug": "big-rulebook",
        "page_count": 40,
        "figure_count": 40,
        "compiled_markdown": compiled_full,
        "pages_meta": pages,
    }

    # 1. Avec le budget par défaut (450 000 car.), les 40 pages passent à 100 % avec toutes les descriptions longues
    full_ctx = visual_documents.build_visual_docs_context([doc], query_text="combat page 27")
    for p in range(1, 41):
        assert f"## [p. {p}]" in full_ctx
        assert f"Anatomie détaillée figure page {p}" in full_ctx

    # 2. Même si on bride max_chars à 45 000 car. (< taille totale), les 40 pages restent TOUTES présentes !
    hybrid_ctx = visual_documents.build_visual_docs_context(
        [doc],
        query_text="Que dit la page 27 sur les combats ?",
        max_chars=45000,
    )
    for p in range(1, 41):
        assert f"## [p. {p}]" in hybrid_ctx
        assert f"Texte complet des règles de la page {p}" in hybrid_ctx
        assert f"/api/docs/big-rulebook/p{p}_fig1.webp" in hybrid_ctx
    # La page 27 (demandée) a conservé sa description anatomique longue intégrale
    assert "Anatomie détaillée figure page 27" in hybrid_ctx


def test_visual_doc_category_ingestion_patch_and_auto_forum_search_bgg(tmp_path, monkeypatch):
    """Vérifie :
    1. Le typage à l'ingestion (`doc_category`) + auto-inférence + modification via PATCH.
    2. Le prompt de raisonnement déductif par recoupement et la spécialisation métier.
    3. La recherche automatique sur les forums dédiés (ex. `site:boardgamegeek.com` pour un jeu de société)
       lorsqu'on pose une question sur le document dans le tchat.
    """
    from app.visual_doc_profiles import clean_doc_subject_for_search

    assert clean_doc_subject_for_search("c7 res arcana regle").lower() == "res arcana"
    assert clean_doc_subject_for_search("TOY FR01 Rules").lower() == "toy"

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        mistral_api_key="test-mistral-key",
        llm_api_key="test-llm-key",
        searxng_url="http://searx.local:8080",
    )
    app = _create_app_with_users(settings)

    async def fake_extract_visual_ocr_pages(s, *, pdf_bytes=None, page_count=1, image_pages=None):
        return [
            {
                "index": 0,
                "markdown": "## [p. 1]\nLes dragons infligent une perte de Vie. La défausse va sous la pioche.",
                "images": [],
                "dimensions": {"width": 600, "height": 800},
            }
        ]

    monkeypatch.setattr(visual_documents, "extract_visual_ocr_pages", fake_extract_visual_ocr_pages)

    searched_queries: list[str] = []
    captured_context: list[dict] = []

    async def fake_search_web(s, query: str, limit: int = 5, engines=None):
        searched_queries.append(query)
        return [
            {
                "title": "Res Arcana — Dragon life loss & discard ruling | BoardGameGeek",
                "url": "https://boardgamegeek.com/thread/225901/dragon-ruling-res-arcana",
                "snippet": "In Res Arcana, dragon attacks inflict life loss rather than discarding cards unless specified.",
                "provider": "searxng",
            }
        ]

    async def fake_stream_chat(_settings, context, _model, **_kwargs):
        captured_context.extend(context)
        yield "En recoupant la règle de Perte de Vie `[p. 1]` et le forum BoardGameGeek `[1]`, votre carte va sous la pioche."

    monkeypatch.setattr(providers, "search_web", fake_search_web)
    monkeypatch.setattr(providers, "stream_chat", fake_stream_chat)

    with _login(app, settings, "alice") as client:
        cats_resp = client.get("/api/visual-docs/categories")
        assert cats_resp.status_code == 200
        cat_ids = {c["id"] for c in cats_resp.json()}
        assert {"boardgame", "scientific", "financial", "technical", "legal", "medical", "educational", "rpg_lore", "general"}.issubset(cat_ids)

        # 1. Ingestion avec catégorie explicite "scientific" puis bascule PATCH vers "boardgame"
        created_resp = client.post(
            "/api/visual-docs",
            files=[("files", ("c7-res-arcana-regle.pdf", _make_pdf_bytes(1), "application/pdf"))],
            data={"title": "c7 res arcana regle", "doc_category": "scientific", "enrich_vision": "false"},
        )
        assert created_resp.status_code == 201
        doc = created_resp.json()
        assert doc["doc_category"] == "scientific"
        assert "PubMed" in doc["forum_label"]

        patched_resp = client.patch(f"/api/visual-docs/{doc['id']}", json={"doc_category": "boardgame"})
        assert patched_resp.status_code == 200
        patched_doc = patched_resp.json()
        assert patched_doc["doc_category"] == "boardgame"
        assert "BoardGameGeek" in patched_doc["forum_label"]

        # 2. Conversation liée au jeu de société : poser une question déclenche automatiquement la recherche BGG
        conv = client.post(
            "/api/conversations",
            json={"title": "Arbitrage Res Arcana", "visual_doc_ids": [doc["id"]]},
        ).json()

        msg_resp = client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={
                "content": "Quand on se fait virer une carte par un dragon, qu'est-ce qu'on en fait ?",
                "web_search": False,
                "auto_web_search": True,
                "web_search_mode": "auto",
            },
        )
        assert msg_resp.status_code == 200
        assert searched_queries, "La recherche sur les forums dédiés aurait dû être déclenchée automatiquement"
        assert any("boardgamegeek.com" in q.lower() for q in searched_queries)
        assert any("res arcana" in q.lower() for q in searched_queries)

        # 3. Vérifier le prompt système déductif + spécialisé jeu de société + injection de la source BGG
        system_msg = captured_context[0]["content"]
        assert "RAISONNEMENT DÉDUCTIF PAR RECOUPEMENT OBLIGATOIRE" in system_msg
        assert "Arbitre expert en Règles de Jeu de Société" in system_msg
        joined_all = "\n".join(str(m.get("content", "")) for m in captured_context)
        assert "https://boardgamegeek.com/thread/225901/dragon-ruling-res-arcana" in joined_all


def test_visual_doc_attach_links_at_ingest_and_afterwards_with_summary_and_ssrf(tmp_path, monkeypatch):
    """Vérifie l'ajout de liens (forum, site, YouTube) à l'ingestion ET après coup, l'extraction + résumé IA,
    la protection anti-SSRF et l'injection dans le contexte de conversation.
    """
    from app import visual_doc_links

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        mistral_api_key="test-mistral-key",
        llm_api_key="test-llm-key",
    )
    app = _create_app_with_users(settings)

    async def fake_extract_visual_ocr_pages(s, *, pdf_bytes=None, page_count=1, image_pages=None):
        return [
            {
                "index": 0,
                "markdown": "## [p. 1]\nMise en place et tour de jeu.",
                "images": [],
                "dimensions": {"width": 600, "height": 800},
            }
        ]

    async def fake_fetch_and_parse_web_url(s, raw_url: str, allow_private: bool = False):
        # Valider SSRF réel via validate_web_url
        visual_doc_links.validate_web_url(raw_url, allow_private=allow_private)
        if "youtube.com" in raw_url or "youtu.be" in raw_url:
            return (
                "🎬 Ludochrono Res Arcana",
                b"yt",
                "text/html; video=youtube",
                "# 🎬 Ludochrono — Res Arcana\n[02:15] Lorsqu'un dragon attaque, les joueurs ayant passé sont immunisés.",
                {
                    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "video_id": "dQw4w9WgXcQ",
                    "author": "Ludochrono",
                    "duration": "05:12",
                    "annotations": [{"title": "Ludochrono — Res Arcana en 5 minutes"}],
                },
            )
        return (
            "💬 BGG FAQ",
            b"bgg",
            "text/html",
            "# FAQ Officielle Res Arcana\nLe Serpent de Mer compte à la fois comme Dragon et Créature.",
            {
                "url": raw_url,
                "domain": "boardgamegeek.com",
                "annotations": [{"title": "FAQ Officielle Res Arcana — BGG"}],
            },
        )

    async def fake_summarize_link(s, *, doc_title, doc_category, url, link_title, link_type, extracted_text):
        return f"### Synthèse IA ({link_type})\n- Point clé résumé pour **{link_title}**."

    captured_context: list[dict] = []

    async def fake_stream_chat(_settings, context, _model, **_kwargs):
        captured_context.extend(context)
        yield "Réponse enrichie avec la vidéo YouTube [02:15] et la FAQ BGG."

    monkeypatch.setattr(visual_documents, "extract_visual_ocr_pages", fake_extract_visual_ocr_pages)
    monkeypatch.setattr(visual_doc_links, "fetch_and_parse_web_url", fake_fetch_and_parse_web_url)
    monkeypatch.setattr(visual_doc_links, "summarize_extracted_link", fake_summarize_link)
    monkeypatch.setattr(providers, "stream_chat", fake_stream_chat)

    with _login(app, settings, "alice") as client:
        # 1. Ingestion initiale avec un lien de forum BGG joint dès la création
        created_resp = client.post(
            "/api/visual-docs",
            files=[("files", ("res-arcana.pdf", _make_pdf_bytes(1), "application/pdf"))],
            data={
                "title": "Res Arcana",
                "doc_category": "boardgame",
                "links": '["https://boardgamegeek.com/thread/111/faq-res-arcana"]',
                "enrich_vision": "false",
            },
        )
        assert created_resp.status_code == 201
        doc = created_resp.json()
        assert doc["link_count"] == 1
        assert len(doc["external_links"]) == 1
        assert doc["external_links"][0]["link_type"] == "forum"
        assert "Synthèse IA (forum)" in doc["external_links"][0]["summary_markdown"]

        # 2. Protection anti-SSRF sur l'ajout de lien local/privé
        ssrf_resp = client.post(
            f"/api/visual-docs/{doc['id']}/links",
            json={"urls": ["http://127.0.0.1:8001/api/health"]},
        )
        assert ssrf_resp.status_code == 422

        # 3. Ajout après coup d'une vidéo YouTube explicative
        add_yt_resp = client.post(
            f"/api/visual-docs/{doc['id']}/links",
            json={"urls": ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]},
        )
        assert add_yt_resp.status_code == 200
        updated_doc = add_yt_resp.json()
        assert updated_doc["link_count"] == 2
        yt_entry = next(l for l in updated_doc["external_links"] if l["link_type"] == "youtube")
        assert yt_entry["video_id"] == "dQw4w9WgXcQ"
        assert yt_entry["duration"] == "05:12"
        assert "Synthèse IA (youtube)" in yt_entry["summary_markdown"]

        # 4. Refresh d'un lien existant
        refreshed_resp = client.post(f"/api/visual-docs/{doc['id']}/links/{yt_entry['id']}/refresh")
        assert refreshed_resp.status_code == 200
        assert refreshed_resp.json()["link_count"] == 2

        # 5. Vérifier que les résumés et transcriptions des liens sont bien injectés dans le tchat
        conv = client.post(
            "/api/conversations",
            json={"title": "Test Liens Res Arcana", "visual_doc_ids": [doc["id"]]},
        ).json()
        msg_resp = client.post(
            f"/api/conversations/{conv['id']}/messages",
            json={"content": "Que disent la FAQ et la vidéo sur les dragons ?", "web_search": False, "auto_web_search": False},
        )
        assert msg_resp.status_code == 200
        full_ctx_str = "\n".join(str(m.get("content", "")) for m in captured_context)
        assert "RESSOURCES COMPLÉMENTAIRES ATTACHÉES AU DOCUMENT" in full_ctx_str
        assert "Ludochrono — Res Arcana en 5 minutes" in full_ctx_str
        assert "[02:15] Lorsqu'un dragon attaque" in full_ctx_str
        assert "Serpent de Mer compte à la fois comme Dragon et Créature" in full_ctx_str

        # 6. Suppression d'un lien
        del_resp = client.delete(f"/api/visual-docs/{doc['id']}/links/{yt_entry['id']}")
        assert del_resp.status_code == 200
        assert del_resp.json()["link_count"] == 1


def test_visual_doc_supplementary_files_faq_ingest_and_afterwards(tmp_path):
    """Vérifie l'ajout de documents complémentaires (ex. FAQ, Errata, Extension) à l'ingestion
    et après coup, le téléchargement sécurisé isolé par utilisateur, l'injection dans le tchat et le nettoyage disque.
    """
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    app = _create_app_with_users(settings)

    faq_md_bytes = (
        "# FAQ Officielle Res Arcana v1.3\n\n"
        "- **Erratum Carte Crypte** : Vous ne pouvez pas cibler un artefact déjà en jeu.\n"
        "- **Précision Dragon** : Les joueurs ayant passé ignorent toute perte de Vie."
    ).encode("utf-8")
    ext_txt_bytes = "Règles de l'extension Lux & Tenebrae : ajout des Démons et Parchemins.".encode("utf-8")

    with _login(app, settings, "alice") as alice:
        # 1. Ingestion initiale avec un fichier FAQ joint dès le départ
        created_resp = alice.post(
            "/api/visual-docs",
            files=[
                ("files", ("res-arcana.pdf", _make_pdf_bytes(1), "application/pdf")),
                ("supplementary_files", ("Res_Arcana_FAQ_v1.3.md", faq_md_bytes, "text/markdown")),
            ],
            data={"title": "Res Arcana", "doc_category": "boardgame"},
        )
        assert created_resp.status_code == 201
        doc = created_resp.json()
        assert doc["link_count"] == 1
        faq_entry = doc["external_links"][0]
        assert faq_entry["link_type"] == "document"
        assert faq_entry["doc_role"] == "faq_errata"
        assert "FAQ / Errata officiel" in faq_entry["doc_role_label"]
        assert "Erratum Carte Crypte" in faq_entry["extracted_text"]

        # 2. Ajout après coup d'un second document complémentaire (Extension)
        add_supp_resp = alice.post(
            f"/api/visual-docs/{doc['id']}/supplementary-files",
            files=[("files", ("Extension_Lux_Tenebrae.txt", ext_txt_bytes, "text/plain"))],
            data={"doc_role": "extension", "title": "Extension Lux & Tenebrae"},
        )
        assert add_supp_resp.status_code == 200
        updated = add_supp_resp.json()
        assert updated["link_count"] == 2
        ext_entry = next(e for e in updated["external_links"] if e["doc_role"] == "extension")
        assert ext_entry["title"] == "Extension Lux & Tenebrae"

        # 3. Accès sécurisé au fichier complémentaire par sa propriétaire
        dl_resp = alice.get(faq_entry["url"])
        assert dl_resp.status_code == 200
        assert "Erratum Carte Crypte" in dl_resp.text

        # 4. Vérifier que build_visual_docs_context inclut bien la FAQ et l'Extension avec leurs badges
        ctx_text = visual_documents.build_visual_docs_context(
            [{
                "title": updated["title"],
                "slug": updated["slug"],
                "page_count": updated["page_count"],
                "figure_count": updated["figure_count"],
                "compiled_markdown": updated["compiled_markdown"],
                "pages_meta": updated["pages"],
                "external_links": updated["external_links"],
            }],
            query_text="Que dit la FAQ sur la Crypte ?",
        )
        assert "FAQ / Errata officiel" in ctx_text
        assert "Erratum Carte Crypte" in ctx_text
        assert "Extension Lux & Tenebrae" in ctx_text

        # 5. Suppression du fichier complémentaire -> nettoyé de la base et du disque
        supp_disk_path = tmp_path / "visual_docs" / doc["id"] / "supp" / ext_entry["storage_name"]
        assert supp_disk_path.is_file()
        del_resp = alice.delete(f"/api/visual-docs/{doc['id']}/links/{ext_entry['id']}")
        assert del_resp.status_code == 200
        assert del_resp.json()["link_count"] == 1
        assert not supp_disk_path.exists()

    # 6. Isolation inter-utilisateurs : Bob ne peut pas télécharger la FAQ d'Alice
    with _login(app, settings, "bob") as bob:
        forbidden = bob.get(faq_entry["url"])
        assert forbidden.status_code == 404


def test_owner_encrypted_publisher_pdf_succeeds_while_user_locked_pdf_returns_422(tmp_path):
    """Reproduit le bug 422 des PDF d'éditeurs (InDesign/Acrobat avec restrictions d'édition `user_password=""`) :
    - Un PDF avec mot de passe éditeur (`owner_password`) mais sans mot de passe d'ouverture (`user_password=""`)
      DOIT être accepté et déchiffré proprement (y compris dans `/supplementary-files`).
    - Un PDF exigeant un vrai mot de passe d'ouverture (`user_password="secret"`) DOIT renvoyer 422.
    """
    import io
    from pypdf import PdfWriter

    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    app = _create_app_with_users(settings)

    # PDF éditeur standard : mot de passe ouverture vide "", mot de passe propriétaire actif (AES-256)
    w_owner = PdfWriter()
    w_owner.add_blank_page(width=300, height=400)
    w_owner.encrypt(user_password="", owner_password="publisher-restrict-edit", algorithm="AES-256")
    buf_owner = io.BytesIO()
    w_owner.write(buf_owner)
    owner_encrypted_pdf = b"\n" + buf_owner.getvalue()  # avec octet d'en-tête avant %PDF-

    # PDF réellement verrouillé à l'ouverture
    w_locked = PdfWriter()
    w_locked.add_blank_page(width=300, height=400)
    w_locked.encrypt(user_password="user-secret", owner_password="owner-secret", algorithm="AES-256")
    buf_locked = io.BytesIO()
    w_locked.write(buf_locked)
    user_locked_pdf = buf_locked.getvalue()

    with _login(app, settings, "alice") as alice:
        # 1. L'ingestion d'un PDF protégé uniquement par permissions éditeur réussit
        doc_resp = alice.post(
            "/api/visual-docs",
            files=[("files", ("regle-editeur.pdf", owner_encrypted_pdf, "application/pdf"))],
            data={"title": "Règle Éditeur"},
        )
        assert doc_resp.status_code == 201
        doc = doc_resp.json()

        # 2. L'ajout d'un PDF FAQ protégé par permissions éditeur dans `/supplementary-files` réussit (200)
        #    et compile les pages WebP + Markdown compilé consultables dans la Liseuse 3D
        supp_resp = alice.post(
            f"/api/visual-docs/{doc['id']}/supplementary-files",
            files=[("files", ("FAQ_Officielle_Editeur.pdf", owner_encrypted_pdf, "application/pdf"))],
            data={"doc_role": "faq_errata"},
        )
        assert supp_resp.status_code == 200
        updated_doc = supp_resp.json()
        assert updated_doc["link_count"] == 1
        supp_entry = updated_doc["external_links"][0]
        assert supp_entry["page_count"] == 1
        assert supp_entry["compiled_markdown"]
        assert len(supp_entry["pages"]) == 1
        supp_page_url = supp_entry["pages"][0]["page_image_url"]
        assert supp_page_url.startswith(f"/api/docs/{doc['slug']}/supp_")
        assert supp_page_url.endswith("_page_1.webp")
        # L'image WebP de la page du document complémentaire est bien servie en 200
        webp_resp = alice.get(supp_page_url)
        assert webp_resp.status_code == 200
        assert webp_resp.headers["content-type"] == "image/webp"

        # 3. Un PDF réellement verrouillé par mot de passe utilisateur renvoie bien 422
        locked_resp = alice.post(
            f"/api/visual-docs/{doc['id']}/supplementary-files",
            files=[("files", ("Locked.pdf", user_locked_pdf, "application/pdf"))],
            data={"doc_role": "faq_errata"},
        )
        assert locked_resp.status_code == 422


def test_visual_doc_custom_cover_upload_serve_and_reset(tmp_path):
    """Vérifie l'ajout, la mise à jour, la lecture sécurisée et la réinitialisation
    d'une image de couverture personnalisée (`cover.webp`) sur un Document Illustré.
    """
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    app = _create_app_with_users(settings)

    page_png = _make_png_bytes((200, 180, 140))
    custom_cover_png = _make_png_bytes((30, 80, 160))

    with _login(app, settings, "alice") as alice:
        # 1. Ingestion standard : cover_url pointe sur page_1.webp, has_custom_cover == False
        create_resp = alice.post(
            "/api/visual-docs",
            files=[("files", ("page1.png", page_png, "image/png"))],
            data={"title": "Règle Viticulture", "doc_category": "boardgame"},
        )
        assert create_resp.status_code == 201
        doc = create_resp.json()
        assert doc["has_custom_cover"] is False
        assert doc["cover_url"] == f"/api/docs/{doc['slug']}/page_1.webp"

        # 2. Téléversement d'une couverture personnalisée
        cover_resp = alice.post(
            f"/api/visual-docs/{doc['id']}/cover",
            files={"file": ("boite-jeu.png", custom_cover_png, "image/png")},
        )
        assert cover_resp.status_code == 200
        updated = cover_resp.json()
        assert updated["has_custom_cover"] is True
        assert updated["cover_url"].startswith(f"/api/docs/{doc['slug']}/cover.webp?v=")

        # 3. La liste `GET /api/visual-docs` expose bien `has_custom_cover` et l'URL cover.webp
        list_resp = alice.get("/api/visual-docs")
        assert list_resp.status_code == 200
        listed = next(item for item in list_resp.json() if item["id"] == doc["id"])
        assert listed["has_custom_cover"] is True
        assert listed["cover_url"].startswith(f"/api/docs/{doc['slug']}/cover.webp?v=")

        # 4. L'asset `cover.webp` est servi en 200 `image/webp` à Alice
        img_resp = alice.get(updated["cover_url"])
        assert img_resp.status_code == 200
        assert img_resp.headers["content-type"] == "image/webp"

        # 5. Un fichier non-image est rejeté (422)
        bad_resp = alice.post(
            f"/api/visual-docs/{doc['id']}/cover",
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )
        assert bad_resp.status_code == 422

        # 6. Réinitialisation de la couverture : retour sur page_1.webp
        reset_resp = alice.delete(f"/api/visual-docs/{doc['id']}/cover")
        assert reset_resp.status_code == 200
        reverted = reset_resp.json()
        assert reverted["has_custom_cover"] is False
        assert reverted["cover_url"] == f"/api/docs/{doc['slug']}/page_1.webp"
        assert alice.get(f"/api/docs/{doc['slug']}/cover.webp").status_code == 404

    # 7. Isolation inter-utilisateurs : Bob ne peut pas modifier la couverture d'Alice
    with _login(app, settings, "bob") as bob:
        forbidden = bob.post(
            f"/api/visual-docs/{doc['id']}/cover",
            files={"file": ("hack.png", custom_cover_png, "image/png")},
        )
        assert forbidden.status_code == 404


def test_filter_visual_doc_forum_sources_drops_offtopic_results():
    """Vérifie que les résultats web hors-sujet (ex. PPT 'Transmission de puissance' sur slideserve.com)
    sont écartés lorsque le document attaché est 'Regle res arcana'.
    """
    from app.visual_doc_profiles import filter_visual_doc_forum_sources

    docs = [{"title": "Regle res arcana", "doc_category": "boardgame"}]
    raw_sources = [
        {
            "title": "Res Arcana: Lux et Tenebrae FAQ",
            "snippet": "Scrolls, demons and 5-player rules on BoardGameGeek.",
            "url": "https://boardgamegeek.com/thread/234567/res-arcana-lux-et-tenebrae",
        },
        {
            "title": "PPT - Chapitre VIII Transmission de puissance",
            "snippet": "Cours de mécanique industrielle sur les engrenages.",
            "url": "https://www.slideserve.com/user/transmission-de-puissance",
        },
    ]
    filtered = filter_visual_doc_forum_sources(raw_sources, docs)
    assert len(filtered) == 1
    assert "boardgamegeek.com" in filtered[0]["url"]


def test_rename_visual_doc_and_supplementary_file(tmp_path):
    """Vérifie le renommage d'un document principal ET d'un document complémentaire (ex. dsfdsfds5454.pdf -> Perlae Imperii.pdf)."""
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    app = _create_app_with_users(settings)

    with _login(app, settings, "alice") as alice:
        create_resp = alice.post(
            "/api/visual-docs",
            files=[("files", ("dsfdsfds5454.pdf", _make_pdf_bytes(1), "application/pdf"))],
            data={"title": "dsfdsfds5454"},
        )
        assert create_resp.status_code == 201
        doc = create_resp.json()
        assert doc["filename"] == "dsfdsfds5454.pdf"

        # 1. Renommer le document principal
        rename_main = alice.patch(f"/api/visual-docs/{doc['id']}", json={"title": "Res Arcana"})
        assert rename_main.status_code == 200
        renamed = rename_main.json()
        assert renamed["title"] == "Res Arcana"
        assert renamed["filename"] == "Res Arcana.pdf"

        # 2. Ajouter un PDF complémentaire au nom cryptique puis le renommer
        supp_resp = alice.post(
            f"/api/visual-docs/{doc['id']}/supplementary-files",
            files=[("files", ("x9923_scan.pdf", _make_pdf_bytes(1), "application/pdf"))],
            data={"doc_role": "extension"},
        )
        assert supp_resp.status_code == 200
        link_id = supp_resp.json()["external_links"][0]["id"]

        rename_supp = alice.patch(
            f"/api/visual-docs/{doc['id']}/links/{link_id}",
            json={"title": "Perlae Imperii"},
        )
        assert rename_supp.status_code == 200
        supp_entry = rename_supp.json()["external_links"][0]
        assert supp_entry["title"] == "Perlae Imperii"
        assert supp_entry["filename"] == "Perlae Imperii.pdf"









