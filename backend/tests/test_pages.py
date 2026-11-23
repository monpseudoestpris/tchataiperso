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
    assert "themeBtn" not in fallback

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

    # Theme toggle buttons are stripped out to avoid visual glitches
    html_with_theme_btn = '<html><body><button id="themeBtn">Thème</button><p>Contenu</p></body></html>'
    cleaned = sanitize_and_enhance_html(html_with_theme_btn)
    assert 'id="themeBtn"' not in cleaned
    assert 'Contenu' in cleaned


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

    # 6. Public endpoint when published -> 200 with raw HTML, sandboxed CSP and storage shim
    res = client.get(f"/p/{token}")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    csp = res.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "sandbox allow-scripts" in csp
    assert "allow-same-origin" not in csp
    assert "form-action 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "__clair_storage_shim__" in res.text
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
    assert len(topics) >= 14

    titles_and_desc = " ".join([t["title"] + " " + t["description"] for t in topics]).lower()
    # Check for inclusion of essential literary subtopics requested by user
    assert "figure" in titles_and_desc
    assert "ponctuation" in titles_and_desc or "rythme" in titles_and_desc
    assert "champs lexicaux" in titles_and_desc or "lexique" in titles_and_desc
    assert "plan" in titles_and_desc or "axes" in titles_and_desc


def test_create_page_with_author_persona_visual_desc_and_formats(client):
    # Verify creation with author_persona, visual_description, and per-topic output_format
    res = client.post(
        "/api/pages",
        json={
            "prompt": "Analyse de Germinal de Zola",
            "title": "Germinal - Étude stylistique",
            "author_persona": "Émile Zola",
            "visual_description": "Très coloré rouge mine et noir charbon",
            "selected_topics": [
                {
                    "id": "figures",
                    "title": "Figures de style de la mine",
                    "description": "Métaphores animales et anthropomorphiques du Voreux.",
                    "category": "Stylistique",
                    "output_format": "table",
                    "detail_level": 8,
                },
                {
                    "id": "rythme",
                    "title": "Rythme de la descente",
                    "description": "Phrases courtes et suffocation.",
                    "category": "Syntaxe",
                    "output_format": "list",
                    "detail_level": 6,
                },
            ],
        },
    )
    assert res.status_code == 201
    created = res.json()
    assert created["title"] == "Germinal - Étude stylistique"
    detail = client.get(f"/api/pages/{created['id']}").json()
    html_content = detail["versions"][0]["html_content"]
    assert "Figures de style de la mine" in html_content
    assert "Rythme de la descente" in html_content
    # Table layout for figures
    assert "<table" in html_content or "format : table" in html_content.lower()



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


def test_a4_strict_presets_and_enforcer(client):
    from app.page_runtime import inject_a4_sheet_enforcer, sanitize_and_enhance_html

    # 1. inject_a4_sheet_enforcer injects A4 CSS geometry and data attributes
    raw = "<!DOCTYPE html><html><head><title>Fiche</title></head><body><h1>Synthèse</h1><p>Contenu court</p></body></html>"
    enforced_1p = inject_a4_sheet_enforcer(raw, layout_style="a4_1p", orientation="portrait")
    assert 'data-a4-mode="1p"' in enforced_1p
    assert 'data-a4-orientation="portrait"' in enforced_1p
    assert ".a4-sheet {" in enforced_1p
    assert ".a4-sheet-inner {" in enforced_1p
    assert "size: A4 portrait" in enforced_1p
    assert "clair-a4-enforcer-css" in enforced_1p

    # 2. Cheat sheet enforces 1p landscape dimensions (297mm x 210mm) via sanitize_and_enhance_html
    enforced_cs = sanitize_and_enhance_html(raw, title="Antisèche", layout_style="cheat_sheet", orientation="portrait")
    assert 'data-a4-mode="1p"' in enforced_cs
    assert 'data-a4-orientation="landscape"' in enforced_cs
    assert "size: A4 landscape" in enforced_cs
    assert "fitA4Sheets" in enforced_cs

    # 3. API propose-topics with a4_1p caps recommended topics to <= 5 with detail_level <= 2
    res_topics = client.post(
        "/api/pages/propose-topics",
        json={
            "prompt": "La thermodynamique : principes, entropie et machines thermiques",
            "page_type": "a4_revision_1p",
            "layout_style": "a4_1p",
            "target_audience": "academic",
        },
    )
    assert res_topics.status_code == 200, res_topics.text
    topics = res_topics.json()["topics"]
    recommended = [t for t in topics if t["recommended"]]
    assert 1 <= len(recommended) <= 5
    assert all(t["detail_level"] <= 2 for t in recommended)

    # 4. API create page in a4_1p produces strict single-sheet output + auto-fit runtime
    res_page = client.post(
        "/api/pages",
        json={
            "prompt": "Fiche mémo sur la thermodynamique",
            "title": "Thermodynamique A4",
            "page_type": "a4_revision_1p",
            "layout_style": "a4_1p",
            "orientation": "portrait",
            "text_density": 2,
            "interactivity": "none",
            "animation_engine": "none",
            "selected_topics": recommended,
        },
    )
    assert res_page.status_code == 201, res_page.text
    created = res_page.json()
    html_out = created["latest_html"]
    assert 'data-a4-mode="1p"' in html_out
    assert ".a4-sheet {" in html_out
    assert "fitA4Sheets" in html_out


def test_canvas_app_integration_and_ai_bricks(client):
    sample_brick = {
        "id": "agent_analyse",
        "name": "Analyste Synthèse",
        "type": "ai_agent",
        "description": "Analyse un texte et renvoie un JSON structuré.",
        "model": "openai/gpt-4o-mini",
        "system_prompt": "Analyse le texte fourni avec rigueur.",
        "web_search_enabled": False,
        "show_widget": True,
        "inputs": [
            {
                "key": "texte",
                "label": "Texte source",
                "type": "textarea",
                "required": True,
                "placeholder": "Collez un texte...",
                "default_value": "",
                "options": [],
            }
        ],
        "output_spec": {
            "format": "json",
            "description": "Objet JSON avec résumé et score",
            "fields": [
                {"key": "resume", "type": "string", "description": "Synthèse"},
                {"key": "score", "type": "number", "description": "Score sur 100"},
                {"key": "valide", "type": "boolean", "description": "Est conforme"},
                {"key": "points", "type": "string[]", "description": "Liste de points"},
            ],
        },
    }

    canvas_files = [
        {
            "path": "index.html",
            "language": "html",
            "content": "<!DOCTYPE html><html><body><h1>Mon App Kanban</h1><div id='root'></div></body></html>",
        },
        {
            "path": "app.js",
            "language": "javascript",
            "content": "console.log('ready');",
        },
    ]

    # 1. Create a Canvas app inside cLAIr Pages ("Mes Apps")
    res = client.post(
        "/api/pages",
        json={
            "prompt": "Import Canvas App",
            "title": "Mon App Kanban",
            "kind": "app",
            "html_content": "<!DOCTYPE html><html><head><title>Mon App Kanban</title></head><body><h1>Mon App Kanban</h1></body></html>",
            "canvas_files": canvas_files,
            "bricks": [sample_brick],
        },
    )
    assert res.status_code == 201, res.text
    app_data = res.json()
    assert app_data["kind"] == "app"
    assert app_data["title"] == "Mon App Kanban"
    assert len(app_data["bricks"]) == 1
    assert app_data["bricks"][0]["id"] == "agent_analyse"
    assert len(app_data["latest_canvas_files"]) == 2
    assert "clair-bricks-runtime-script" in app_data["latest_html"]
    assert "window.clair.runBrick" in app_data["latest_html"]
    page_id = app_data["id"]

    # 2. Validation: missing required input returns 422
    res_missing = client.post(
        "/api/pages/bricks/execute",
        json={"page_id": page_id, "brick_id": "agent_analyse", "inputs": {}},
    )
    assert res_missing.status_code == 422

    # 3. Execute brick attached to the saved app (demo mode returns structured schema)
    res_exec = client.post(
        "/api/pages/bricks/execute",
        json={
            "page_id": page_id,
            "brick_id": "agent_analyse",
            "inputs": {"texte": "Architecture modulaire FastAPI + Next.js"},
        },
    )
    assert res_exec.status_code == 200, res_exec.text
    exec_json = res_exec.json()
    assert exec_json["brick_id"] == "agent_analyse"
    assert exec_json["format"] == "json"
    assert isinstance(exec_json["output"], dict)
    assert set(exec_json["output"].keys()) >= {"resume", "score", "valide", "points"}
    assert isinstance(exec_json["output"]["score"], (int, float))
    assert isinstance(exec_json["output"]["valide"], bool)
    assert isinstance(exec_json["output"]["points"], list)

    # 4. Update bricks via PATCH and verify latest_html runtime updates
    updated_brick = {**sample_brick, "id": "agent_coach", "name": "Coach V2"}
    res_patch = client.patch(
        f"/api/pages/{page_id}",
        json={"bricks": [updated_brick]},
    )
    assert res_patch.status_code == 200, res_patch.text
    patched = res_patch.json()
    assert patched["bricks"][0]["id"] == "agent_coach"
    assert "agent_coach" in patched["latest_html"]


def test_execute_brick_with_mocked_llm_json_schema(tmp_path, monkeypatch):
    import httpx
    from app import page_bricks

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
    )
    captured = {}

    class FakeResponse:
        status_code = 200
        is_success = True

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"note": "18", "ok": "true", "conseils": ["Aérer les titres", "Ajouter un exemple"]}\n```'
                        }
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(page_bricks.httpx, "AsyncClient", FakeAsyncClient)

    with authenticated_client(settings) as authed_client:
        res = authed_client.post(
            "/api/pages/bricks/execute",
            json={
                "brick": {
                    "id": "correcteur",
                    "name": "Correcteur",
                    "type": "ai_agent",
                    "model": "mistralai/mistral-small-3.2-24b-instruct",
                    "system_prompt": "Corrige la copie.",
                    "inputs": [{"key": "copie", "label": "Copie", "type": "textarea", "required": True}],
                    "output_spec": {
                        "format": "json",
                        "description": "Correction chiffrée",
                        "fields": [
                            {"key": "note", "type": "number", "description": "Note sur 20"},
                            {"key": "ok", "type": "boolean", "description": "Validé"},
                            {"key": "conseils", "type": "string[]", "description": "Conseils"},
                        ],
                    },
                },
                "inputs": {"copie": "La photosynthèse transforme la lumière en énergie chimique."},
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert captured["json"]["model"] == "mistralai/mistral-small-3.2-24b-instruct"
        assert data["output"]["note"] == 18
        assert data["output"]["ok"] is True
        assert data["output"]["conseils"] == ["Aérer les titres", "Ajouter un exemple"]


def test_chatbot_brick_with_history_and_widget_style(tmp_path, monkeypatch):
    from app import page_bricks

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
    )
    captured = {}

    class FakeResponse:
        status_code = 200
        is_success = True

        def json(self):
            return {"choices": [{"message": {"content": "Bien sûr, voici la suite de notre échange."}}]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(page_bricks.httpx, "AsyncClient", FakeAsyncClient)

    with authenticated_client(settings) as authed_client:
        res_app = authed_client.post(
            "/api/pages",
            json={
                "prompt": "App avec Bot IA",
                "title": "App Bot IA",
                "kind": "app",
                "html_content": "<!DOCTYPE html><html><body><div data-clair-brick='bot_ia_chat'></div></body></html>",
                "bricks": [
                    {
                        "id": "bot_ia_chat",
                        "name": "Bot IA Conversationnel",
                        "type": "ai_agent",
                        "model": "auto",
                        "widget_style": "chatbot",
                        "welcome_message": "Bienvenue sur le bot !",
                        "system_prompt": "Tu es un bot utile.",
                        "inputs": [{"key": "message", "label": "Message", "type": "textarea", "required": True}],
                        "output_spec": {"format": "markdown", "description": "Réponse", "fields": []},
                    }
                ],
            },
        )
        assert res_app.status_code == 201, res_app.text
        created = res_app.json()
        assert created["bricks"][0]["widget_style"] == "chatbot"
        assert created["bricks"][0]["welcome_message"] == "Bienvenue sur le bot !"
        assert "buildChatbotPanel" in created["latest_html"]

        res_chat = authed_client.post(
            "/api/pages/bricks/execute",
            json={
                "page_id": created["id"],
                "brick_id": "bot_ia_chat",
                "inputs": {
                    "message": "Peux-tu résumer ?",
                    "_history": [
                        {"role": "user", "content": "Bonjour"},
                        {"role": "assistant", "content": "Bonjour ! Comment aider ?"},
                    ],
                },
            },
        )
        assert res_chat.status_code == 200, res_chat.text
        sent_messages = captured["json"]["messages"]
        assert len(sent_messages) == 4  # system + 2 history turns + current user turn
        assert sent_messages[1] == {"role": "user", "content": "Bonjour"}
        assert sent_messages[2] == {"role": "assistant", "content": "Bonjour ! Comment aider ?"}
        assert "_history" not in sent_messages[3]["content"]


def test_propose_app_diagram_and_default_internal_brick(client):
    res = client.post(
        "/api/pages/diagram/propose",
        json={"prompt": "App Le NiaisBot où j'explique un sujet à un bot naïf qui fait évoluer sa jauge de compréhension et son score"},
    )
    assert res.status_code == 200, res.text
    diagram = res.json()
    assert diagram["title"]
    assert isinstance(diagram["nodes"], list) and len(diagram["nodes"]) >= 3
    assert isinstance(diagram["edges"], list) and len(diagram["edges"]) >= 2

    ai_nodes = [n for n in diagram["nodes"] if n.get("kind") == "ai_brick"]
    assert len(ai_nodes) >= 1
    brick = ai_nodes[0]["brick"]
    assert brick["show_widget"] is False
    assert len(brick["inputs"]) >= 1
    assert brick["output_spec"]["format"] == "json"
    assert len(brick["output_spec"]["fields"]) >= 2


def test_diagram_interview_selects_bricks_and_asks_questions(client):
    # Turn 1: agent analyzes request, selects bricks, and asks clarifying questions
    res1 = client.post(
        "/api/pages/diagram/interview",
        json={
            "messages": [
                {"role": "user", "content": "Je veux une app avec un bot qui me fait réviser et un quiz"},
            ],
            "available_templates": [
                {"templateId": "bot_ia_chat", "name": "Bot IA Conversationnel", "tagline": "Chatbot"},
                {"templateId": "generateur_quiz", "name": "Générateur de Quiz QCM", "tagline": "Quiz"},
            ],
        },
    )
    assert res1.status_code == 200, res1.text
    step1 = res1.json()
    assert step1["status"] == "questions"
    assert len(step1["questions"]) >= 2
    assert "bot_ia_chat" in step1["selected_brick_ids"]
    assert "generateur_quiz" in step1["selected_brick_ids"]
    assert step1["diagram"] is None

    # Turn 2: user answers questions -> agent builds the complete diagram with internal bricks
    res2 = client.post(
        "/api/pages/diagram/interview",
        json={
            "messages": [
                {"role": "user", "content": "Je veux une app avec un bot qui me fait réviser et un quiz"},
                {"role": "assistant", "content": step1["assistant_message"]},
                {"role": "user", "content": "Un bot naïf façon Feynman avec jauge de compréhension et score /100"},
            ],
        },
    )
    assert res2.status_code == 200, res2.text
    step2 = res2.json()
    assert step2["status"] == "ready"
    assert step2["diagram"] is not None
    ai_nodes = [n for n in step2["diagram"]["nodes"] if n.get("kind") == "ai_brick"]
    assert len(ai_nodes) >= 1
    assert ai_nodes[0]["brick"]["show_widget"] is False


def test_finance_eod_brick_execution_and_interview(tmp_path, monkeypatch):
    from app import finance, page_bricks

    bars = [
        {"date": f"2026-10-{i:02d}", "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 100 + i, "volume": 1000000}
        for i in range(1, 25)
    ]
    tech = page_bricks._compute_technical_indicators_summary(bars)
    assert tech["last_close"] == 124.0
    assert tech["sma_20"] is not None
    assert tech["rsi_14"] == 100.0

    # Mock get_financial_dashboard_data and LLM completion
    async def fake_dashboard(settings, query, limit_bars=30, chart_range="1m"):
        return {
            "symbol": "AAPL",
            "eod_ticker": "AAPL.US",
            "yahoo_symbol": "AAPL",
            "long_name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "price": 124.0,
            "change": 1.5,
            "change_percent": 1.22,
            "volume": 1000000,
            "eod_bars": bars,
            "financial_stats": {"valuation": {"pe_trailing": "28.5"}, "profitability": {"roe": "140%"}},
        }

    captured = {}

    class FakeResponse:
        status_code = 200
        is_success = True

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"ticker": "AAPL", "prix_actuel": 124.0, "rsi_14": 100.0, "tendance_technique": "Haussière"}'
                        }
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            captured["messages"] = json["messages"]
            return FakeResponse()

    monkeypatch.setattr(finance, "get_financial_dashboard_data", fake_dashboard)
    monkeypatch.setattr(page_bricks.httpx, "AsyncClient", FakeAsyncClient)

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
    )

    with authenticated_client(settings) as authed_client:
        res = authed_client.post(
            "/api/pages/bricks/execute",
            json={
                "brick": {
                    "id": "finance_eod_indicateurs",
                    "name": "Cotation EOD & Indicateurs",
                    "type": "finance_eod_agent",
                    "finance_data_enabled": True,
                    "system_prompt": "Analyse EOD",
                    "inputs": [{"key": "symbole", "label": "Symbole", "type": "text", "required": True}],
                    "output_spec": {
                        "format": "json",
                        "description": "Indicateurs EOD",
                        "fields": [
                            {"key": "ticker", "type": "string", "description": "Ticker"},
                            {"key": "prix_actuel", "type": "number", "description": "Prix"},
                            {"key": "rsi_14", "type": "number", "description": "RSI"},
                            {"key": "tendance_technique", "type": "string", "description": "Tendance"},
                        ],
                    },
                },
                "inputs": {"symbole": "AAPL"},
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["output"]["ticker"] == "AAPL"
        assert data["output"]["prix_actuel"] == 124.0
        assert "DONNÉES BOURSIÈRES RÉELLES" in captured["messages"][-1]["content"]
        assert "rsi_14" in captured["messages"][-1]["content"]

        # Interview picks finance bricks on finance prompt
        res_int = authed_client.post(
            "/api/pages/diagram/interview",
            json={
                "messages": [{"role": "user", "content": "Je veux une app bourse avec cours EOD et indicateurs RSI"}],
                "force_finalize": True,
            },
        )
        assert res_int.status_code == 200, res_int.text
        int_data = res_int.json()
        assert "finance_eod_indicateurs" in int_data["selected_brick_ids"]


def test_pages_searxng_web_search_enabled_by_default_and_non_silent_errors(tmp_path, monkeypatch):
    import httpx
    from app import page_generator, page_web_search
    from app.providers import ProviderError
    from app.schemas import CreateWebPage, ProposePageTopicsRequest, RefineWebPage

    # 1. Vérifier que web_search est activé par défaut dans les schémas cLAIr Pages
    assert CreateWebPage(prompt="Sujet test").web_search is True
    assert ProposePageTopicsRequest(prompt="Sujet test").web_search is True
    assert RefineWebPage(instruction="Ajoute une section").web_search is True

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
        page_model="openai/gpt-4o-mini",
        searxng_url="http://clair-searxng:8080",
    )

    search_calls: list[str] = []
    llm_prompts: list[str] = []
    reformulate_calls: list[dict] = []

    async def fake_reformulate_post(_settings, payload, client=None, **kwargs):
        reformulate_calls.append(payload)
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"queries": ["nuclear fusion plasma confinement record 2026", "ITER tokamak fusion progress"]}'
                        }
                    }
                ]
            },
        )

    async def fake_search_web(_settings, query: str, limit: int = 5, engines=None):
        search_calls.append(query)
        return [
            {
                "title": "Rapport Fusion Nucléaire 2026",
                "url": "https://example.org/fusion-2026",
                "snippet": "Record de confinement plasma maintenu pendant 1200 secondes en 2026.",
                "engine": "searxng",
            }
        ]

    async def fake_post_chat_completion(_settings, payload, client=None, **kwargs):
        llm_prompts.append(payload["messages"][-1]["content"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": "<!DOCTYPE html><html lang='fr'><head><title>Fusion 2026</title></head><body><h1>Fusion Nucléaire</h1><p>1200 secondes</p></body></html>"
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    monkeypatch.setattr(page_web_search, "post_chat_completion", fake_reformulate_post)
    monkeypatch.setattr(page_web_search, "search_web", fake_search_web)
    monkeypatch.setattr(page_generator, "post_chat_completion", fake_post_chat_completion)

    with authenticated_client(settings) as authed_client:
        # 2. Création par défaut : les requêtes sont reformulées avant d'interroger SearXNG
        res = authed_client.post(
            "/api/pages",
            json={"prompt": "Fais-moi une belle page web pédagogique avec schéma SVG et quiz sur les avancées récentes de la fusion nucléaire"},
        )
        assert res.status_code == 201, res.text
        assert len(reformulate_calls) == 1
        assert search_calls == [
            "nuclear fusion plasma confinement record 2026",
            "ITER tokamak fusion progress",
        ]
        assert "RECHERCHE WEB SEARXNG" in llm_prompts[-1]
        assert "https://example.org/fusion-2026" in llm_prompts[-1]
        assert "1200 secondes" in res.json()["latest_html"]

        # 2bis. Si la reformulation échoue, repli gracieux sur les requêtes directes sans bloquer SearXNG
        search_calls.clear()

        async def failing_reformulate(*args, **kwargs):
            raise httpx.ReadTimeout("timeout reformulation")

        monkeypatch.setattr(page_web_search, "post_chat_completion", failing_reformulate)
        res_fb = authed_client.post(
            "/api/pages",
            json={"prompt": "Batteries sodium-ion 2026"},
        )
        assert res_fb.status_code == 201, res_fb.text
        assert search_calls == ["Batteries sodium-ion 2026"]
        monkeypatch.setattr(page_web_search, "post_chat_completion", fake_reformulate_post)

        # 3. Opt-out explicite : web_search=False n'appelle pas SearXNG
        search_calls.clear()
        res_off = authed_client.post(
            "/api/pages",
            json={"prompt": "Cours sur la thermodynamique", "web_search": False},
        )
        assert res_off.status_code == 201, res_off.text
        assert search_calls == []
        assert "RECHERCHE WEB SEARXNG" not in llm_prompts[-1]

        # 4. Si SearXNG échoue, la génération continue gracieusement sans bloquer
        async def failing_search_web(*args, **kwargs):
            raise ProviderError("SearXNG temporairement indisponible")

        monkeypatch.setattr(page_web_search, "search_web", failing_search_web)
        res_degraded = authed_client.post(
            "/api/pages",
            json={"prompt": "Histoire de l'aviation"},
        )
        assert res_degraded.status_code == 201, res_degraded.text

        # 5. Si le fournisseur IA échoue en mode réel (demo_mode=False), HTTP 502 au lieu d'une page fallback CSS vide
        async def failing_llm(*args, **kwargs):
            raise ProviderError("Modèle indisponible sur le fournisseur")

        monkeypatch.setattr(page_generator, "post_chat_completion", failing_llm)
        res_err = authed_client.post(
            "/api/pages",
            json={"prompt": "Sujet qui ne doit pas renvoyer un faux fallback CSS"},
        )
        assert res_err.status_code == 502
        assert "Modèle indisponible" in res_err.json()["detail"]


def test_page_wizard_interview_and_exhaustive_criteria(tmp_path, monkeypatch):
    import json
    import httpx
    from app import page_wizard

    # 1. Mode démo : vérifie les deux phases (questions -> ready) et la détection des critères
    demo_settings = Settings(_env_file=None, app_data_dir=tmp_path / "demo", demo_mode=True)
    with authenticated_client(demo_settings) as demo_client:
        res_q = demo_client.post(
            "/api/pages/wizard/interview",
            json={"prompt": "Comparatif détaillé et exhaustif des batteries sodium-ion vs lithium-ion"},
        )
        assert res_q.status_code == 200, res_q.text
        data_q = res_q.json()
        assert data_q["status"] == "questions"
        assert len(data_q["questions"]) >= 3
        assert "tables_priority" in data_q["criteria"]["format_priorities"]

        res_ready = demo_client.post(
            "/api/pages/wizard/interview",
            json={
                "prompt": "Batteries sodium-ion vs lithium-ion",
                "messages": [
                    {"role": "user", "content": "Batteries sodium-ion vs lithium-ion"},
                    {"role": "assistant", "content": "Questions ?"},
                    {"role": "user", "content": "Priorité aux tableaux comparatifs, dossier complet et études de cas"},
                ],
                "force_finalize": True,
            },
        )
        assert res_ready.status_code == 200, res_ready.text
        data_ready = res_ready.json()
        assert data_ready["status"] == "ready"
        assert "tables_priority" in data_ready["criteria"]["format_priorities"]
        assert "comparison_matrix" in data_ready["criteria"]["mandatory_sections"]
        assert data_ready["criteria"]["text_density"] >= 8
        assert "sodium-ion" in data_ready["criteria"]["refined_prompt"].lower()

    # 2. Mode IA réelle (mocké) : vérifie l'appel LLM, le raffinage du prompt et le pré-remplissage complet
    ai_settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "ai",
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
        page_model="openai/gpt-4o-mini",
    )

    async def fake_wizard_llm(_settings, payload, client=None, **kwargs):
        is_second_turn = "FINALISER" in payload["messages"][0]["content"] or len(payload["messages"]) > 2
        if not is_second_turn:
            body = {
                "status": "questions",
                "assistant_message": "Précisons le format idéal.",
                "questions": [
                    {
                        "id": "q1",
                        "question": "Quels formats prioriser ?",
                        "options": ["Priorité aux tableaux", "Cartes Bento"],
                        "allow_multiple": True,
                        "recommended_option": "Priorité aux tableaux",
                    }
                ],
                "criteria": {
                    "suggested_title": "Benchmark IA",
                    "format_priorities": ["tables_priority"],
                    "text_density": 7,
                },
            }
        else:
            body = {
                "status": "ready",
                "assistant_message": "Prompt raffiné et critères prêts.",
                "questions": [],
                "criteria": {
                    "suggested_title": "Comparatif Complet GPU Cloud 2026",
                    "refined_prompt": "Dossier complet comparant H100, H200 et B200 avec tableaux de coûts, latence et VRAM.",
                    "page_type": "comparison",
                    "target_audience": "professional",
                    "editorial_tone": "analytical",
                    "format_priorities": ["tables_priority", "kpi_metrics"],
                    "mandatory_sections": ["executive_summary", "comparison_matrix", "common_pitfalls"],
                    "orientation": "landscape",
                    "layout_style": "single_page",
                    "text_density": 9,
                    "include_quiz": False,
                    "include_svg": True,
                    "web_search": True,
                },
            }
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            json={"choices": [{"message": {"content": json.dumps(body)}}]},
        )

    monkeypatch.setattr(page_wizard, "post_chat_completion", fake_wizard_llm)

    with authenticated_client(ai_settings) as ai_client:
        res1 = ai_client.post("/api/pages/wizard/interview", json={"prompt": "Comparatif GPU Cloud"})
        assert res1.status_code == 200
        assert res1.json()["status"] == "questions"
        assert res1.json()["questions"][0]["allow_multiple"] is True

        res2 = ai_client.post(
            "/api/pages/wizard/interview",
            json={
                "prompt": "Comparatif GPU Cloud",
                "messages": [
                    {"role": "user", "content": "Comparatif GPU Cloud"},
                    {"role": "assistant", "content": "Quels formats prioriser ?"},
                    {"role": "user", "content": "Priorité aux tableaux et KPI chiffrés"},
                ],
                "force_finalize": True,
            },
        )
        assert res2.status_code == 200
        ready = res2.json()
        assert ready["status"] == "ready"
        assert ready["criteria"]["suggested_title"] == "Comparatif Complet GPU Cloud 2026"
        assert ready["criteria"]["editorial_tone"] == "analytical"
        assert ready["criteria"]["orientation"] == "landscape"
        assert ready["criteria"]["text_density"] == 9
        assert "tables_priority" in ready["criteria"]["format_priorities"]
        assert "comparison_matrix" in ready["criteria"]["mandatory_sections"]


def test_long_complex_page_directives_and_truncation_recovery(tmp_path, monkeypatch):
    import httpx
    from app import page_generator

    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
        page_model="openai/gpt-4o-mini",
    )

    captured_payloads: list[dict] = []
    long_body_chunk = "<section><h2>Comparatif détaillé</h2><table><thead><tr><th>Critère</th><th>Valeur</th></tr></thead><tbody>" + ("<tr><td>Paramètre</td><td>Mesure détaillée exhaustive et vérifiée</td></tr>" * 100) + "</tbody></table></section>"
    truncated_long_html = f"<!DOCTYPE html><html lang='fr'><head><title>Dossier Long</title></head><body><main>{long_body_chunk}"
    assert len(truncated_long_html) >= 6000

    async def fake_post(_settings, payload, client=None, **kwargs):
        captured_payloads.append(payload)
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {"content": truncated_long_html},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    monkeypatch.setattr(page_generator, "post_chat_completion", fake_post)

    with authenticated_client(settings) as authed_client:
        res = authed_client.post(
            "/api/pages",
            json={
                "prompt": "Analyse exhaustive et complexe avec tableaux comparatifs",
                "editorial_tone": "analytical",
                "format_priorities": ["tables_priority", "kpi_metrics"],
                "mandatory_sections": ["executive_summary", "comparison_matrix"],
                "text_density": 9,
                "web_search": False,
            },
        )
        assert res.status_code == 201, res.text
        assert len(captured_payloads) == 2
        assert captured_payloads[0]["max_tokens"] == 65536
        user_msg = captured_payloads[0]["messages"][1]["content"]
        assert "PRIORITÉ ABSOLUE AUX TABLEAUX HTML" in user_msg
        assert "PRIORITÉ AUX KPI & CHIFFRES CLÉS" in user_msg
        assert "Ton analytique, factuel et rigoureux" in user_msg
        assert "Un bloc « L'essentiel en 30 secondes / Résumé exécutif »" in user_msg
        assert "ARCHITECTURE POUR PAGE LONGUE & COMPLEXE" in user_msg
        # Le retry d'une page complexe ne doit pas brider à 600 mots
        assert "600 mots maximum" not in captured_payloads[1]["messages"][-1]["content"]
        # La page longue tronquée en fin de 2e tentative est proprement refermée au lieu d'échouer
        html_out = res.json()["latest_html"]
        assert "</html>" in html_out.lower()
        assert "<table>" in html_out


def test_multipass_encyclopedic_page_generation_and_wizard_autodetect(tmp_path, monkeypatch):
    import json
    import httpx
    from app import page_multipass

    # 1. Le Wizard active automatiquement multipass_exhaustive sur une demande encyclopédique
    demo_settings = Settings(_env_file=None, app_data_dir=tmp_path / "wiz", demo_mode=True)
    with authenticated_client(demo_settings) as demo_client:
        res_wiz = demo_client.post(
            "/api/pages/wizard/interview",
            json={
                "prompt": "Toutes les races de Blood Bowl 2025 avec leur roster et le détail de toutes les compétences",
                "force_finalize": True,
            },
        )
        assert res_wiz.status_code == 200, res_wiz.text
        wiz_criteria = res_wiz.json()["criteria"]
        assert wiz_criteria["multipass_exhaustive"] is True
        assert wiz_criteria["text_density"] >= 9

    # 2. Génération multi-passes complète : Plan -> Recherches SearXNG par lot + Rédaction parallèle -> Assemblage
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path / "mp",
        demo_mode=False,
        llm_api_key="fake-test-key",
        default_model="openai/gpt-4o-mini",
        page_model="openai/gpt-4o-mini",
        searxng_url="http://clair-searxng:8080",
    )

    batch_queries_seen: list[str] = []
    llm_call_count = 0

    async def fake_global_search(*args, **kwargs):
        return "=== RECHERCHE WEB SEARXNG ===\n[1] Blood Bowl 2025 Teams List", []

    async def fake_batch_search_web(_settings, query: str, limit: int = 5, engines=None):
        batch_queries_seen.append(query)
        return [
            {
                "title": f"BB2025 Roster — {query}",
                "url": "https://example.org/bb2025",
                "snippet": "Stats officielles MA ST AG PA AV et compétences détaillées.",
                "engine": "searxng",
            }
        ]

    async def fake_mp_llm(_settings, payload, client=None, **kwargs):
        nonlocal llm_call_count
        llm_call_count += 1
        user_content = payload["messages"][-1]["content"]
        if payload.get("response_format"):
            blueprint = {
                "title": "Encyclopédie Blood Bowl 2025 — Toutes les Équipes",
                "subtitle": "Rosters complets et détail des compétences",
                "intro_html": "<p>Référentiel exhaustif des équipes Blood Bowl 2025.</p>",
                "batches": [
                    {
                        "batch_id": "lot_1",
                        "category": "Tier 1",
                        "search_queries": ["Blood Bowl 2025 Humans Orcs roster skills"],
                        "items": [
                            {"id": "humains", "title": "Humains", "subtitle": "Tier 1", "focus": "Roster + compétences"},
                            {"id": "orques", "title": "Orques", "subtitle": "Tier 1", "focus": "Roster + compétences"},
                        ],
                    },
                    {
                        "batch_id": "lot_2",
                        "category": "Tier 2",
                        "search_queries": ["Blood Bowl 2025 Skaven Dwarfs roster skills"],
                        "items": [
                            {"id": "skaven", "title": "Skaven", "subtitle": "Tier 2", "focus": "Roster + compétences"},
                        ],
                    },
                ],
            }
            content = json.dumps(blueprint)
        elif "lot_1" in user_content or "Humains" in user_content:
            content = (
                '<section class="mp-entry" id="humains" data-category="Tier 1" data-search="humains blocage esquive">'
                '<div class="mp-entry-head"><div><h2>Humains</h2></div></div>'
                '<div class="mp-table-wrap"><table class="mp-table"><thead><tr><th>Poste</th><th>Compétences</th></tr></thead>'
                '<tbody><tr><td>Blitzer</td><td>Blocage</td></tr></tbody></table></div>'
                '<div class="mp-skill-grid"><div class="mp-skill-card"><strong>Blocage</strong><p>Évite de tomber sur Les Deux Plaqués.</p></div></div>'
                "</section>"
                '<section class="mp-entry" id="orques" data-category="Tier 1" data-search="orques blocage">'
                '<div class="mp-entry-head"><div><h2>Orques</h2></div></div>'
                "</section>"
            )
        else:
            content = (
                '<section class="mp-entry" id="skaven" data-category="Tier 2" data-search="skaven esquive">'
                '<div class="mp-entry-head"><div><h2>Skaven</h2></div></div>'
                '<div class="mp-skill-grid"><div class="mp-skill-card"><strong>Esquive</strong><p>Relance un jet d\'esquive par tour.</p></div></div>'
                "</section>"
            )
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
        )

    monkeypatch.setattr(page_multipass, "gather_page_web_context", fake_global_search)
    monkeypatch.setattr(page_multipass, "search_web", fake_batch_search_web)
    monkeypatch.setattr(page_multipass, "post_chat_completion", fake_mp_llm)

    with authenticated_client(settings) as authed_client:
        res = authed_client.post(
            "/api/pages",
            json={
                "prompt": "Toutes les races de Blood Bowl 2025 avec leur roster et toutes les compétences",
                "format_priorities": ["tables_priority"],
                "multipass_exhaustive": True,
                "web_search": True,
            },
        )
        assert res.status_code == 201, res.text
        page = res.json()
        assert page["title"] == "Encyclopédie Blood Bowl 2025 — Toutes les Équipes"
        assert llm_call_count == 3  # 1 plan + 2 lots
        assert len(batch_queries_seen) == 2
        html_out = page["latest_html"]
        assert "mpSearch" in html_out
        assert 'id="humains"' in html_out
        assert 'id="orques"' in html_out
        assert 'id="skaven"' in html_out
        assert "Évite de tomber sur Les Deux Plaqués" in html_out
        assert "Relance un jet d'esquive par tour" in html_out











