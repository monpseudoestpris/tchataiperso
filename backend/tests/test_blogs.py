import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.blog import (
    _enrich_sources_with_content,
    _extract_complete_article,
    generate_blog_edition,
    is_landing_or_index_url,
    looks_like_article_url,
    parse_cards_from_content,
    parse_trends_from_content,
    search_blog_news,
)
from app.config import Settings
from app.main import create_app
from app.models import Base, Blog, BlogPost, User


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/test_blogs_app.db",
        demo_mode=True,
        searxng_url="http://clair-searxng:8080",
    )


@contextmanager
def auth_client_for_user(app, settings, username: str, is_admin: bool = False):
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        admin_user = db.scalar(Base.metadata.tables["users"].select().where(Base.metadata.tables["users"].c.is_admin == True))
        if not admin_user:
            db.add(User(username="admin", password_hash=hash_password("securepassword123"), is_admin=True))
        existing = db.scalar(Base.metadata.tables["users"].select().where(Base.metadata.tables["users"].c.username == username))
        if not existing:
            db.add(User(username=username, password_hash=hash_password("securepassword123"), is_admin=is_admin))
        db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as c:
        resp = c.post("/api/auth/login", json={"username": username, "password": "securepassword123"})
        assert resp.status_code == 200
        yield c


def test_parse_cards_from_content_json():
    json_content = json.dumps({
        "title": "Titre",
        "summary": "Chapeau",
        "trends": ["Tendance 1 : Montée des agents", "Tendance 2 : Efficacité énergétique"],
        "cards": [
            {
                "title": "Avancée majeure sur les puces IA",
                "text": "Nouvelle architecture 2nm dévoilée avec 40% de gains énergétiques.",
                "url": "https://example.com/puces",
                "source_name": "TechCrunch",
                "tag": "Hardware",
                "color": "emerald",
            }
        ]
    })
    cards = parse_cards_from_content(json_content)
    assert len(cards) == 1
    assert cards[0]["title"] == "Avancée majeure sur les puces IA"
    assert cards[0]["color"] == "emerald"
    assert cards[0]["source_name"] == "TechCrunch"
    trends = parse_trends_from_content(json_content)
    assert len(trends) == 2
    assert "Montée des agents" in trends[0]


def test_parse_cards_from_content_markdown_fallback():
    markdown = """# Mon Titre

## [Premier fait](https://lemonde.fr/article)
Des chercheurs ont publié de nouveaux résultats.

## [Deuxième fait](https://wired.com/post)
Une entreprise lève 50 millions.
"""
    cards = parse_cards_from_content(markdown)
    assert len(cards) == 2
    assert "Premier fait" in cards[0]["title"]
    assert cards[0]["url"] == "https://lemonde.fr/article"
    assert cards[0]["source_name"] == "lemonde.fr"


def test_generate_blog_edition_demo_mode(settings):
    title, summary, content, sources = asyncio.run(
        generate_blog_edition(settings, "les news IA", blog_title="Les News IA")
    )
    assert "Les News IA" in title
    assert "news IA" in summary
    cards = parse_cards_from_content(content)
    assert len(cards) >= 10
    assert cards[0]["color"] in ["blue", "emerald", "purple", "amber", "rose", "cyan"]
    trends = parse_trends_from_content(content)
    assert len(trends) >= 1
    assert any("news IA" in t.lower() or "accélération" in t.lower() for t in trends)


def test_generate_blog_edition_real_mode(tmp_path):
    real_settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/test_real.db",
        demo_mode=False,
        llm_api_key="sk-test-key",
        llm_base_url="https://llm.example/v1",
        default_model="test-model",
        searxng_url="http://clair-searxng:8080",
    )

    llm_payload = {
        "title": "Révolution des agents autonomes : l'actualité IA",
        "summary": "Cette semaine marque un tournant avec des agents capables d'orchestrer des tâches complexes.",
        "cards": [
            {
                "title": "Déploiement massif des agents de recherche",
                "text": "Les entreprises adoptent à grande échelle des systèmes d'automatisation.",
                "url": "https://example.com/ia",
                "source_name": "TechNews",
                "tag": "Modèles",
                "color": "blue"
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "chat/completions" in str(request.url):
            payload = {
                "choices": [{"message": {"content": json.dumps(llm_payload), "role": "assistant"}}],
            }
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    mock_sources = [
        {"title": "TechNews IA", "url": "https://example.com/ia", "snippet": "Annonce majeure d'un modèle..."}
    ]

    real_async_client = httpx.AsyncClient

    with patch("app.blog.search_blog_news", AsyncMock(return_value=mock_sources)), \
         patch("httpx.AsyncClient", lambda *args, **kwargs: real_async_client(transport=httpx.MockTransport(handler))):
        title, summary, content, sources = asyncio.run(
            generate_blog_edition(real_settings, "actualités IA", blog_title="Mon Blog IA")
        )
        assert title == "Révolution des agents autonomes : l'actualité IA"
        assert "Cette semaine marque un tournant" in summary
        cards = parse_cards_from_content(content)
        assert len(cards) >= 10
        assert cards[0]["url"] == "https://example.com/ia"
        assert cards[0]["color"] == "blue"


def test_blog_api_crud_and_refresh(settings):
    app = create_app(settings)

    with auth_client_for_user(app, settings, "blogger") as client:
        # Initially empty
        list_resp = client.get("/api/blogs")
        assert list_resp.status_code == 200
        assert list_resp.json() == []

        # Create blog
        create_resp = client.post(
            "/api/blogs",
            json={"title": "Actus Intelligence Artificielle", "prompt": "les dernières news IA", "auto_refresh": True},
        )
        assert create_resp.status_code == 201
        blog = create_resp.json()
        blog_id = blog["id"]
        assert blog["title"] == "Actus Intelligence Artificielle"
        assert blog["prompt"] == "les dernières news IA"
        assert blog["auto_refresh"] is True
        assert blog["posts_count"] == 1
        assert len(blog["posts"]) == 1
        first_post = blog["posts"][0]
        assert "Actus Intelligence Artificielle" in first_post["title"] or "news IA" in first_post["title"]
        assert len(first_post["cards"]) >= 10

        # Get single blog
        get_resp = client.get(f"/api/blogs/{blog_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == blog_id
        assert len(get_resp.json()["posts"]) == 1
        assert len(get_resp.json()["posts"][0]["cards"]) >= 10

        # Update blog settings
        patch_resp = client.patch(
            f"/api/blogs/{blog_id}",
            json={"title": "Mon Super Blog IA", "auto_refresh": False},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["title"] == "Mon Super Blog IA"
        assert patch_resp.json()["auto_refresh"] is False

        # Refresh blog (generate a second edition)
        refresh_resp = client.post(f"/api/blogs/{blog_id}/refresh")
        assert refresh_resp.status_code == 200
        refreshed = refresh_resp.json()
        assert refreshed["blog"]["posts_count"] == 2
        assert len(refreshed["blog"]["posts"]) == 2
        new_post = refreshed["new_post"]
        assert new_post["id"] == refreshed["blog"]["posts"][0]["id"]
        assert len(new_post["cards"]) >= 10

        # Delete one edition
        delete_post_resp = client.delete(f"/api/blogs/{blog_id}/posts/{first_post['id']}")
        assert delete_post_resp.status_code == 204

        # Verify only 1 edition remains
        after_post_del = client.get(f"/api/blogs/{blog_id}")
        assert after_post_del.status_code == 200
        assert after_post_del.json()["posts_count"] == 1

        # Delete the entire blog
        delete_blog_resp = client.delete(f"/api/blogs/{blog_id}")
        assert delete_blog_resp.status_code == 204

        # Verify blog is gone
        assert client.get(f"/api/blogs/{blog_id}").status_code == 404
        assert client.get("/api/blogs").json() == []


def test_blog_multi_user_isolation(settings):
    app = create_app(settings)

    with auth_client_for_user(app, settings, "usera") as client_a:
        res = client_a.post("/api/blogs", json={"title": "Blog A", "prompt": "Topic A"})
        assert res.status_code == 201
        blog_a_id = res.json()["id"]

    with auth_client_for_user(app, settings, "userb") as client_b:
        # User B cannot see or manipulate User A's blog
        assert client_b.get("/api/blogs").json() == []
        assert client_b.get(f"/api/blogs/{blog_a_id}").status_code == 404
        assert client_b.patch(f"/api/blogs/{blog_a_id}", json={"title": "Hacked"}).status_code == 404
        assert client_b.post(f"/api/blogs/{blog_a_id}/refresh").status_code == 404
        assert client_b.delete(f"/api/blogs/{blog_a_id}").status_code == 404


def test_generate_blog_edition_categories(settings):
    # Test single category: facts
    title, summary, content, sources = asyncio.run(
        generate_blog_edition(settings, "culture générale", blog_title="Curiosités du Monde", categories=["facts"])
    )
    assert "Curiosités du Monde" in title
    cards = parse_cards_from_content(content)
    assert len(cards) >= 10
    assert any(c.get("category") == "facts" for c in cards)

    # Test mixed categories: news, facts, images, tips
    title_mix, summary_mix, content_mix, _ = asyncio.run(
        generate_blog_edition(
            settings,
            "sciences et espace",
            blog_title="Magazine Espace",
            categories=["news", "facts", "images", "tips"],
        )
    )
    assert "Magazine Espace" in title_mix
    cards_mix = parse_cards_from_content(content_mix)
    assert len(cards_mix) >= 10
    categories_present = {c.get("category") for c in cards_mix}
    assert "facts" in categories_present or "images" in categories_present or "news" in categories_present


def test_blog_api_categories_crud(settings):
    app = create_app(settings)

    with auth_client_for_user(app, settings, "cat_blogger") as client:
        # Create blog with specific categories
        create_resp = client.post(
            "/api/blogs",
            json={
                "title": "Culture G & Faits Insolites",
                "prompt": "faits insolites et culture générale",
                "categories": ["facts", "images", "tips"],
            },
        )
        assert create_resp.status_code == 201
        blog = create_resp.json()
        assert blog["categories"] == ["facts", "images", "tips"]
        first_post = blog["posts"][0]
        assert len(first_post["cards"]) >= 10

        # Patch categories
        patch_resp = client.patch(
            f"/api/blogs/{blog['id']}",
            json={"categories": ["facts", "quotes", "concepts"]},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["categories"] == ["facts", "quotes", "concepts"]

        # Refresh with updated categories
        refresh_resp = client.post(f"/api/blogs/{blog['id']}/refresh")
        assert refresh_resp.status_code == 200
        refreshed = refresh_resp.json()
        assert refreshed["blog"]["categories"] == ["facts", "quotes", "concepts"]
        assert len(refreshed["new_post"]["cards"]) >= 10


def test_generate_blog_edition_videos_category(settings):
    title, summary, content, sources = asyncio.run(
        generate_blog_edition(
            settings,
            "documentaires et conférences espace",
            blog_title="Vidéos Documentaires Espace",
            categories=["videos", "news"],
        )
    )
    assert "Vidéos Documentaires Espace" in title
    cards = parse_cards_from_content(content)
    assert len(cards) >= 10
    video_cards = [c for c in cards if c.get("category") == "videos" or c.get("video_embed_url")]
    assert len(video_cards) >= 1
    sample = video_cards[0]
    assert sample.get("video_url")
    assert sample.get("video_embed_url")
    assert sample.get("image_url")


def test_search_blog_videos_endpoint(settings):
    app = create_app(settings)

    mock_videos = [
        {
            "title": "Documentaire sur l'Univers",
            "url": "https://www.youtube.com/watch?v=mock123",
            "video_url": "https://www.youtube.com/watch?v=mock123",
            "video_embed_url": "https://www.youtube-nocookie.com/embed/mock123",
            "thumbnail_url": "https://i.ytimg.com/vi/mock123/hqdefault.jpg",
            "image_url": "https://i.ytimg.com/vi/mock123/hqdefault.jpg",
            "content": "Super documentaire sur les nébuleuses.",
            "source": "Astronomie France",
        }
    ]

    with patch("app.routers.blogs.search_web_videos", new=AsyncMock(return_value=mock_videos)):
        with auth_client_for_user(app, settings, "videouser") as client:
            resp = client.get("/api/blogs/search-videos?q=astronomie")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["title"] == "Documentaire sur l'Univers"
            assert "mock123" in data[0]["video_embed_url"]


def test_search_blog_images_endpoint(settings):
    app = create_app(settings)

    mock_images = [
        {
            "title": "Nébuleuse d'Orion",
            "img_src": "https://example.com/orion.jpg",
            "thumbnail_src": "https://example.com/orion_thumb.jpg",
            "url": "https://example.com/page",
            "image_source": "NASA",
        }
    ]

    with patch("app.routers.blogs.providers.search_web_images", new=AsyncMock(return_value=mock_images)):
        with auth_client_for_user(app, settings, "imguser") as client:
            resp = client.get("/api/blogs/search-images?q=orion")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["title"] == "Nébuleuse d'Orion"
            assert data[0]["img_src"] == "https://example.com/orion.jpg"


def test_landing_vs_article_url_detection():
    landing_urls = [
        "https://www.lesechos.fr/finance-marches",
        "https://www.investing.com/news/economy",
        "https://www.lemonde.fr/economie/",
        "https://example.com/tag/ia",
        "https://www.boursier.com/actualites/news-du-jour",
    ]
    for url in landing_urls:
        assert is_landing_or_index_url(url) is True, f"Expected landing URL: {url}"
        assert looks_like_article_url(url) is False, f"Expected non-article URL: {url}"

    article_urls = [
        "https://www.lesechos.fr/finance-marches/banques-assurances/la-fed-maintient-ses-taux-directeurs-en-novembre-2026-2134567",
        "https://www.boursier.com/actualites/economie/la-fed-maintient-ses-taux-directeurs-en-novembre-945678.html",
        "https://www.lemonde.fr/economie/article/2026/11/13/inflation-ralentit-en-zone-euro_6234567_3234.html",
    ]
    for article_url in article_urls:
        assert is_landing_or_index_url(article_url) is False, f"Expected article URL: {article_url}"
        assert looks_like_article_url(article_url) is True, f"Expected article markers: {article_url}"


def test_extract_complete_article_rejects_landing_page_and_accepts_full_article():
    landing_html = """
    <html>
      <head><title>Économie &amp; Marchés - Actualités</title></head>
      <body>
        <main>
          <p>L'analyse approfondie du marché du travail américain et des décisions de la Réserve fédérale dicte le rythme des marchés mondiaux.</p>
          <section>
            <h2><a href="/economie/la-fed-maintient-ses-taux-a-425-en-novembre-2026">La Fed maintient ses taux à 4,25 % en novembre 2026</a></h2>
            <h2><a href="/economie/inflation-zone-euro-recule-a-19-pourcent-octobre">L'inflation recule à 1,9 % en zone euro</a></h2>
            <p><a href="/economie/article-1">Lire la suite de l'article complet sur les taux américains et les marchés</a></p>
          </section>
        </main>
      </body>
    </html>
    """
    assert _extract_complete_article(landing_html) is None

    feed_html = """
    <html>
      <head><title>News du jour - Boursier.com</title></head>
      <body>
        <main>
          <h2><a href="/actualites/economie/article-un-taux-directeurs-945601.html">La BCE maintient ses taux directeurs en novembre</a></h2>
          <p>La Banque centrale europeenne a decide de laisser ses principaux taux inchanges lors de sa reunion mensuelle a Francfort.</p>
          <h2><a href="/actualites/societes/article-deux-resultats-trimestriels-945602.html">TotalEnergies publie ses resultats du troisieme trimestre</a></h2>
          <p>Le groupe energetique affiche un benefice ajuste en leger repli sur fond de baisse des marges de raffinage en Europe.</p>
          <h2><a href="/actualites/marches/article-trois-cac40-cloture-945603.html">Le CAC 40 cloture en hausse de 0,6 %</a></h2>
          <p>La Bourse de Paris a termine la seance dans le vert, soutenue par les valeurs technologiques et le secteur du luxe.</p>
          <h2><a href="/actualites/economie/article-quatre-inflation-usa-945604.html">L'inflation americaine conforme aux attentes</a></h2>
          <p>L'indice des prix a la consommation a progresse de 2,6 % sur un an aux Etats-Unis selon le departement du Travail.</p>
          <h2><a href="/actualites/societes/article-cinq-airbus-commandes-945605.html">Airbus enregistre une commande de 40 appareils</a></h2>
          <p>L'avionneur europeen renforce son carnet de commandes moyen-courrier avec un contrat signe au salon aeronautique.</p>
          <h2><a href="/actualites/marches/article-six-or-record-945606.html">L'once d'or se stabilise sous son record</a></h2>
          <p>Les investisseurs arbitrent entre les rendements obligataires americains et les valeurs refuges avant la fin de semaine.</p>
        </main>
      </body>
    </html>
    """
    assert _extract_complete_article(feed_html) is None

    article_html = """
    <html>
      <head>
        <title>La Fed maintient ses taux directeurs à 4,25 %</title>
        <meta property="og:type" content="article" />
      </head>
      <body>
        <nav><p>Menu principal du journal et liens vers toutes les rubriques économiques.</p></nav>
        <article>
          <h1>La Fed maintient ses taux directeurs entre 4,00 % et 4,25 %</h1>
          <p>Réunie mercredi à Washington, la Réserve fédérale américaine a décidé à 11 voix contre 1 de laisser son taux directeur inchangé dans la fourchette de 4,00 % à 4,25 %, invoquant une inflation sous-jacente encore supérieure à sa cible de 2 %.</p>
          <p>Selon le Bureau of Labor Statistics, les créations d'emplois non agricoles ont atteint 185 000 postes en octobre, tandis que le taux de chômage s'est stabilisé à 4,1 %, réduisant l'urgence d'un nouvel assouplissement monétaire immédiat.</p>
          <p>Jerome Powell a précisé lors de sa conférence de presse que le comité examinerait les données d'inflation PCE de décembre avant d'envisager une baisse de 25 points de base au premier trimestre 2027.</p>
        </article>
      </body>
    </html>
    """
    extracted = _extract_complete_article(article_html)
    assert extracted is not None
    title, body = extracted
    assert "Fed maintient ses taux" in title
    assert "185 000 postes" in body
    assert "Menu principal" not in body


def test_enrich_sources_follows_article_links_from_landing_page():
    landing_url = "https://news.example.com/finance-marches"
    article_url = "https://news.example.com/2026/11/la-fed-maintient-ses-taux-directeurs-en-novembre-2026-2134567"

    landing_html = f"""
    <html>
      <head><title>Finance &amp; Marchés</title></head>
      <body>
        <main>
          <p>Retrouvez toute l'actualité des marchés financiers et des banques centrales en temps réel.</p>
          <h2><a href="{article_url}">La Fed maintient ses taux directeurs en novembre 2026</a></h2>
        </main>
      </body>
    </html>
    """

    article_html = """
    <html>
      <head>
        <title>La Fed maintient ses taux directeurs à 4,25 %</title>
        <meta property="og:type" content="article" />
      </head>
      <body>
        <article>
          <p>La Réserve fédérale a maintenu son principal taux directeur entre 4,00 % et 4,25 % le 12 novembre 2026, confirmant une pause prudente face à la vigueur de la consommation des ménages américains.</p>
          <p>Les rendements des bons du Trésor à 10 ans ont progressé de 6 points de base à 4,38 % après la publication du communiqué, tandis que l'indice S&amp;P 500 clôturait en hausse de 0,45 % à New York.</p>
          <p>Les contrats à terme FedWatch n'accordent désormais plus que 38 % de probabilité à une baisse de taux dès janvier, contre 62 % une semaine plus tôt.</p>
        </article>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == landing_url:
            return httpx.Response(200, text=landing_html, headers={"content-type": "text/html; charset=utf-8"})
        if str(request.url) == article_url:
            return httpx.Response(200, text=article_html, headers={"content-type": "text/html; charset=utf-8"})
        return httpx.Response(404)

    real_async_client = httpx.AsyncClient
    initial_sources = [
        {"title": "Finance & Marchés", "url": landing_url, "snippet": "L'analyse approfondie des marchés mondiaux."}
    ]

    with patch("httpx.AsyncClient", lambda *args, **kwargs: real_async_client(transport=httpx.MockTransport(handler))):
        enriched = asyncio.run(_enrich_sources_with_content(initial_sources))

    assert len(enriched) == 1
    assert enriched[0]["url"] == article_url
    assert enriched[0].get("is_complete_article") == "true"
    assert "4,38 %" in enriched[0]["content"]



