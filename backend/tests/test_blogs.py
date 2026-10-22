import asyncio
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.blog import generate_blog_edition, parse_cards_from_content, search_blog_news
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
