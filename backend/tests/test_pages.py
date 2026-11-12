import pytest
from app.config import Settings
from app.page_generator import extract_html, extract_title_from_html, generate_fallback_page, slugify
from app.svg_assets import THEMATIC_ILLUSTRATIONS, inject_svg_placeholders, render_svg_asset
from app.text_fx import inject_text_fx_placeholders, render_curved_text

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

    # 5. extract_html with truncated markdown fence
    truncated_wrapped = "```html\n<!DOCTYPE html><html><body><h1>Titre</h1>"
    extracted_trunc = extract_html(truncated_wrapped)
    assert extracted_trunc.startswith("<!DOCTYPE html>")
    assert not extracted_trunc.startswith("```")


def test_sanitize_and_enhance_html():
    from app.page_runtime import sanitize_and_enhance_html

    # External links get target="_blank" and rel="noopener noreferrer"
    html_with_ext_link = '<html><body><a href="https://example.org">Lien externe</a></body></html>'
    enhanced = sanitize_and_enhance_html(html_with_ext_link)
    assert 'target="_blank"' in enhanced
    assert 'rel="noopener noreferrer"' in enhanced
    assert "__clair_runtime_installed__" in enhanced

    # Unclosed tags are properly closed
    truncated = '<html><body><section><h2>Partie 1</h2><script>console.log("ok");'
    closed = sanitize_and_enhance_html(truncated)
    assert "</script>" in closed
    assert "</body>" in closed
    assert "</html>" in closed

    # Hidden tabs container has hidden attribute removed
    with_hidden_tabs = '<nav class="tabs" hidden><button>Tab 1</button></nav>'
    unhidden = sanitize_and_enhance_html(with_hidden_tabs)
    assert 'hidden' not in unhidden or 'class="tabs"' in unhidden


def test_web_page_crud_and_lifecycle(client):
    # 1. Create a Web Page with custom font, animation engine and text effects
    res = client.post(
        "/api/pages",
        json={
            "prompt": "Guide interactif sur l'astronomie",
            "title": "Astronomie Interactive",
            "animation_engine": "both",
            "font_family": "space_grotesk",
            "text_effects": ["charming_wave", "gsap_counters"],
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
    assert "Space+Grotesk" in page["latest_html"] or "Space Grotesk" in page["latest_html"]
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


def test_propose_topics_and_creation_with_selected_topics(client):
    # 1. Test propose-topics endpoint
    res = client.post(
        "/api/pages/propose-topics",
        json={
            "prompt": "L'énergie nucléaire et les réacteurs SMR",
            "page_type": "didactic_sheet",
            "target_audience": "general",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "suggested_title" in data
    assert "topics" in data
    assert len(data["topics"]) >= 4
    # Check topic structure
    first_topic = data["topics"][0]
    assert "id" in first_topic
    assert "title" in first_topic
    assert "category" in first_topic
    assert "recommended" in first_topic

    # 2. Pick 3 topics
    chosen_topics = [
        data["topics"][0],
        data["topics"][1],
        {
            "id": "custom-safety",
            "title": "Protocoles de sûreté passive",
            "description": "Systèmes de refroidissement autonome sans alimentation électrique d'urgence.",
            "category": "Sécurité",
            "recommended": True,
        },
    ]

    # 3. Create Web Page with selected_topics
    res_page = client.post(
        "/api/pages",
        json={
            "prompt": "Guide complet sur les réacteurs nucléaires SMR",
            "title": "Nucléaire & SMR",
            "selected_topics": chosen_topics,
        },
    )
    assert res_page.status_code == 201
    created = res_page.json()
    assert created["title"] == "Nucléaire & SMR"
    page_id = created["id"]

    # Retrieve page HTML content
    detail = client.get(f"/api/pages/{page_id}").json()
    html_content = detail["versions"][0]["html_content"]

    # Verify that chosen topic titles and descriptions are integrated into the tabs/sections
    assert "Protocoles de sûreté passive" in html_content
    assert "Systèmes de refroidissement autonome" in html_content
    assert "Fonctionnement interne" in html_content
    assert created["versions_count"] == 1
    assert "<!DOCTYPE html>" in created["latest_html"]
    # Verify that detail_level is present and no quiz is forced by default
    assert "detail_level" in chosen_topics[0]
    assert "<div class=\"quiz-box" not in html_content



def test_propose_topics_literary_and_deep_subtopics(client):
    # Verify that literary subjects like "commentaire composé" return detailed subtopics:
    # figures of speech, punctuation, syntax, register, plan, etc.
    res = client.post(
        "/api/pages/propose-topics",
        json={
            "prompt": "Méthode du commentaire composé pour le bac de français",
            "page_type": "revision",
            "target_audience": "school",
        },
    )
    assert res.status_code == 200
    data = res.json()
    topics = data["topics"]
    # Check that we do not artificially limit the topics count
    assert len(topics) >= 14

    titles_and_desc = " ".join([t["title"] + " " + t["description"] for t in topics]).lower()
    # Check for inclusion of essential literary subtopics requested by user
    assert "figure" in titles_and_desc
    assert "ponctuation" in titles_and_desc or "rythme" in titles_and_desc
    assert "champs lexicaux" in titles_and_desc or "lexique" in titles_and_desc
    assert "plan" in titles_and_desc or "axes" in titles_and_desc



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


def test_text_fx_typography():
    # 1. Curved text generation (xsvg inspiration)
    wave_curved = render_curved_text("Comprendre la science", curve="wave")
    assert "<textPath" in wave_curved
    assert "Comprendre la science" in wave_curved
    assert "xsvg-curved-wrap" in wave_curved

    arc_curved = render_curved_text("Devise didactique", curve="arc")
    assert "<textPath" in arc_curved
    assert "Devise didactique" in arc_curved

    # 2. Tag substitution <clair-curved-text ... />
    html_sample = """<!DOCTYPE html><html><head><style>body { color: #fff; }</style></head>
<body><h1 class="charming" data-fx="wave">Titre</h1>
<clair-curved-text text="Exploration didactique" curve="wave" />
<h2 class="pretext-fit">TITRE LARGE</h2>
<script>console.log('ok');</script></body></html>"""

    processed = inject_text_fx_placeholders(html_sample)
    assert "<clair-curved-text" not in processed
    assert "xsvg-curved-wrap" in processed
    assert "<textPath" in processed
    # Ensures CSS and JS are injected when charming / pretext / xsvg are present
    assert "charWave" in processed
    assert "initCharmingTypography" in processed
    assert "initPretextAutoFit" in processed

    # 3. Fallback page includes typography enhancements
    fallback = generate_fallback_page("Physique Quantique", "Guide didactique")
    assert "charming" in fallback
    assert "charWave" in fallback
    assert "initCharmingTypography" in fallback
    assert "xsvg-curved-wrap" in fallback



def test_motion_fx_aos_and_gsap():
    from app.motion_fx import MOTION_FX_CSS, MOTION_FX_JS, inject_motion_fx

    # 1. Verification of inject_motion_fx on sample HTML
    sample_html = """<!DOCTYPE html><html><head><title>Test</title><style>body { margin: 0; }</style></head>
<body>
  <div class="card" data-aos="fade-up" data-aos-delay="100">Contenu</div>
  <script>console.log('init');</script>
</body></html>"""

    enhanced = inject_motion_fx(sample_html)
    assert "[data-aos]" in enhanced
    assert "data-aos=\"fade-up\"" in enhanced
    assert "window.AOS = AOS;" in enhanced
    assert "window.gsap = gsap;" in enhanced

    # 2. Verification that fallback page contains AOS and GSAP
    fallback = generate_fallback_page("Guide IA", "Sujet")
    assert "data-aos=\"fade-up\"" in fallback
    assert "[data-aos]" in fallback
    assert "window.AOS" in fallback
    assert "window.gsap" in fallback
    assert "AOS.refresh()" in fallback


