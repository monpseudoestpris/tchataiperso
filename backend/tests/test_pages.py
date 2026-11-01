import pytest
from app.config import Settings
from app.page_generator import extract_html, extract_title_from_html, generate_fallback_page, slugify
from app.svg_assets import THEMATIC_ILLUSTRATIONS, inject_svg_placeholders, render_svg_asset

try:
    from test_api import authenticated_client
except ImportError:
    from .test_api import authenticated_client


@pytest.fixture
def client(tmp_path):
    st = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    with authenticated_client(st) as value:
        yield value


def test_page_generator_helpers():
    # 1. slugify
    assert slugify("Ma Super Page Web !") == "ma-super-page-web"
    assert slugify("L'effet de serre & climat") == "l-effet-de-serre-climat"
    assert slugify("") == "page-web"

    # 2. extract_title_from_html
    sample_html = "<html><head><title>Système Solaire - cLAIr</title></head><body><h1>Le Système Solaire</h1></body></html>"
    assert extract_title_from_html(sample_html) == "Système Solaire"

    sample_no_title = "<html><body><h1>Guide de Securite</h1></body></html>"
    assert extract_title_from_html(sample_no_title) == "Guide de Securite"

    # 3. extract_html from markdown code fence
    markdown_wrapped = "Voici la page :\n```html\n<!DOCTYPE html><html lang=\"fr\"><head><title>Test</title></head><body><p>Hello</p></body></html>\n```\nBonne lecture !"
    extracted = extract_html(markdown_wrapped)
    assert extracted.startswith("<!DOCTYPE html>")
    assert "</html>" in extracted

    # 4. generate_fallback_page
    fallback = generate_fallback_page("Système Solaire", "Guide complet")
    assert "<!DOCTYPE html>" in fallback
    assert "Système Solaire" in fallback
    assert "<svg" in fallback
    assert "themeBtn" in fallback


def test_web_page_crud_and_lifecycle(client):
    # 1. Create a Web Page
    res = client.post(
        "/api/pages",
        json={
            "prompt": "Guide interactif sur l'astronomie",
            "title": "Astronomie Interactive",
        },
    )
    assert res.status_code == 201, res.text
    page = res.json()
    assert page["title"] == "Astronomie Interactive"
    assert page["slug"] == "astronomie-interactive"
    assert page["is_published"] is False
    assert page["versions_count"] == 1
    assert page["latest_version_number"] == 1
    assert "<!DOCTYPE html>" in page["latest_html"]
    page_id = page["id"]
    token = page["public_token"]

    # 2. List Web Pages
    res = client.get("/api/pages")
    assert res.status_code == 200
    pages = res.json()
    assert any(p["id"] == page_id for p in pages)

    # 3. Get Web Page detail with versions
    res = client.get(f"/api/pages/{page_id}")
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == page_id
    assert len(detail["versions"]) == 1
    v1_id = detail["versions"][0]["id"]

    # 4. Public endpoint when NOT published -> 404
    res = client.get(f"/p/{token}")
    assert res.status_code == 404

    # 5. Publish page
    res = client.patch(
        f"/api/pages/{page_id}",
        json={"is_published": True},
    )
    assert res.status_code == 200
    assert res.json()["is_published"] is True

    # 6. Public endpoint when published -> 200 with raw HTML and CSP
    res = client.get(f"/p/{token}")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "default-src 'none'" in res.headers["content-security-policy"]
    assert "<!DOCTYPE html>" in res.text

    # Also test /api/pages/public/{token}
    res = client.get(f"/api/pages/public/{token}")
    assert res.status_code == 200
    assert "<!DOCTYPE html>" in res.text

    # 7. Refine page (add instruction, creates v2)
    res = client.post(
        f"/api/pages/{page_id}/refine",
        json={"instruction": "Ajoute un quiz de validation et change les couleurs"},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["versions_count"] == 2
    assert updated["latest_version_number"] == 2
    v2_id = updated["versions"][0]["id"]

    # 8. Restore v1 (creates v3 based on v1)
    res = client.post(f"/api/pages/{page_id}/versions/{v1_id}/restore")
    assert res.status_code == 200
    restored = res.json()
    assert restored["versions_count"] == 3
    assert restored["latest_version_number"] == 3
    assert "Restauration de la version 1" in restored["latest_prompt"]

    # 9. Delete page
    res = client.delete(f"/api/pages/{page_id}")
    assert res.status_code == 204

    # Verification: page is gone
    res = client.get(f"/api/pages/{page_id}")
    assert res.status_code == 404


def test_web_page_creation_from_conversation(client):
    # 1. Create a conversation with messages
    conv_res = client.post("/api/conversations", json={})
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]

    # Post message
    client.post(f"/api/conversations/{conv_id}/messages", json={"content": "Explique-moi les exoplanètes"})

    # 2. Create web page linked to conversation
    res = client.post(
        "/api/pages",
        json={
            "prompt": "Synthétise cet échange sous forme de fiche web pédagogique",
            "conversation_id": conv_id,
        },
    )
    assert res.status_code == 201
    page = res.json()
    assert page["versions_count"] == 1
    assert "<!DOCTYPE html>" in page["latest_html"]


def test_web_page_options(client):
    # Test creation with print_sheet, density 2, no quiz, no svg, emerald palette, neobrutalism
    res = client.post(
        "/api/pages",
        json={
            "prompt": "Fiche de révision chimie",
            "title": "Chimie Organique A4",
            "layout_style": "print_sheet",
            "text_density": 2,
            "include_quiz": False,
            "include_svg": False,
            "theme_palette": "emerald",
            "visual_style": "neobrutalism",
        },
    )
    assert res.status_code == 201, res.text
    page = res.json()
    assert page["title"] == "Chimie Organique A4"
    html = page["latest_html"]
    assert "@media print" in html
    assert "Imprimer" in html
    assert "4px 4px 0px" in html or "2.5px solid" in html
    # SVG must be excluded
    assert "Schéma conceptuel interactif" not in html


def test_svg_assets_and_placeholders():
    # 1. Direct render of existing assets
    science_svg = render_svg_asset("science_biology")
    assert science_svg is not None
    assert "<svg" in science_svg
    assert "var(--primary)" in science_svg or "#" in science_svg

    icon_bulb = render_svg_asset("bulb")
    assert icon_bulb is not None
    assert 'class="clair-icon"' in icon_bulb

    wave = render_svg_asset("wave_smooth")
    assert wave is not None
    assert "clair-divider" in wave

    # Unknown returns None
    assert render_svg_asset("non_existent_asset") is None

    # 2. Tag substitution <clair-svg name="..." />
    sample = '<section><h2>Sciences</h2><clair-svg name="science_biology" /><p>Texte</p><clair-svg name="bulb"/></section>'
    substituted = inject_svg_placeholders(sample)
    assert '<clair-svg name="science_biology"' not in substituted
    assert '<clair-svg name="bulb"' not in substituted
    assert "<svg" in substituted
    assert 'class="clair-illustration"' in substituted
    assert 'class="clair-icon"' in substituted

    # 3. HTML comment substitution <!-- clair-svg: ... -->
    sample_comment = '<div class="header"><!-- clair-svg: wave_layered --></div>'
    sub_comment = inject_svg_placeholders(sample_comment)
    assert "<!-- clair-svg:" not in sub_comment
    assert "clair-divider" in sub_comment

    # 4. On-disk Tabler Icons library resolution (+5000 icons)
    tabler_cpu = render_svg_asset("tabler/cpu")
    assert tabler_cpu is not None
    assert "<svg" in tabler_cpu
    assert "icon-tabler-cpu" in tabler_cpu

    # 5. On-disk unDraw illustrations resolution (+1700 scenes)
    undraw_science = render_svg_asset("undraw/science")
    assert undraw_science is not None
    assert "<svg" in undraw_science
    assert "clair-illustration" in undraw_science

    # 6. Tag substitution with prefixes
    sample_prefixed = '<header><clair-svg name="tabler/database" /></header><main><clair-svg name="undraw/science" /></main>'
    sub_prefixed = inject_svg_placeholders(sample_prefixed)
    assert '<clair-svg' not in sub_prefixed
    assert 'icon-tabler-database' in sub_prefixed
    assert 'clair-illustration' in sub_prefixed

    # 7. Path traversal security
    assert render_svg_asset("../../etc/passwd") is None
    assert render_svg_asset("tabler/../../config") is None



