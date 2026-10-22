import asyncio
import io
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx

from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Attachment, Base, Conversation, User
from app.web import WebPageContentExtractor, is_private_or_local_host, validate_web_url, fetch_and_parse_web_url


class TestWebParsing(unittest.TestCase):
    def test_url_validation_safe(self):
        parsed = validate_web_url("https://example.com/article?ref=1")
        self.assertEqual(parsed.hostname, "example.com")
        self.assertEqual(parsed.scheme, "https")

        parsed2 = validate_web_url("http://sub.domain.org:8080/path")
        self.assertEqual(parsed2.hostname, "sub.domain.org")

    def test_url_validation_rejection(self):
        # Invalid scheme
        with self.assertRaises(HTTPException) as ctx:
            validate_web_url("ftp://example.com/file")
        self.assertEqual(ctx.exception.status_code, 422)

        with self.assertRaises(HTTPException) as ctx:
            validate_web_url("file:///etc/passwd")
        self.assertEqual(ctx.exception.status_code, 422)

        # Localhost and private IPs
        with self.assertRaises(HTTPException) as ctx:
            validate_web_url("http://localhost:8001/api")
        self.assertEqual(ctx.exception.status_code, 422)

        with self.assertRaises(HTTPException) as ctx:
            validate_web_url("http://127.0.0.1/test")
        self.assertEqual(ctx.exception.status_code, 422)

        with self.assertRaises(HTTPException) as ctx:
            validate_web_url("http://192.168.1.50/dashboard")
        self.assertEqual(ctx.exception.status_code, 422)

        with self.assertRaises(HTTPException) as ctx:
            validate_web_url("http://169.254.169.254/latest/meta-data")
        self.assertEqual(ctx.exception.status_code, 422)

    def test_html_content_extractor(self):
        sample_html = """<!DOCTYPE html>
<html lang="fr">
<head>
    <title>Comprendre les réseaux de neurones</title>
    <meta name="description" content="Introduction pédagogique au deep learning et rétropropagation." />
    <meta property="og:site_name" content="IA Mag" />
    <meta name="author" content="Dr. Jean Dupont" />
    <style>body { background: #000; }</style>
    <script>evil_tracker();</script>
</head>
<body>
    <nav><a href="/">Accueil</a> <a href="/categories">Catégories</a></nav>
    <article>
        <h1>Les fondamentaux des réseaux de neurones</h1>
        <p>Un réseau de neurones artificiels est un modèle de calcul inspiré du cerveau.</p>
        <h2>Fonctionnement d'une couche</h2>
        <p>Chaque neurone applique une somme pondérée suivie d'une fonction d'activation non-linéaire.</p>
        <p>Voir <a href="/docs/activation">les fonctions d'activation courantes</a> pour plus de détails.</p>
        <ul>
            <li>ReLU (Rectified Linear Unit)</li>
            <li>Sigmoïde</li>
            <li>GELU</li>
        </ul>
    </article>
    <aside>Publicité et articles recommandés</aside>
    <footer>Mentions légales © 2026</footer>
</body>
</html>"""
        extractor = WebPageContentExtractor(base_url="https://iamag.example.com/article")
        extractor.feed(sample_html)
        data = extractor.extract()

        self.assertEqual(data["title"], "Comprendre les réseaux de neurones")
        self.assertEqual(data["description"], "Introduction pédagogique au deep learning et rétropropagation.")
        self.assertEqual(data["site_name"], "IA Mag")
        self.assertEqual(data["author"], "Dr. Jean Dupont")

        md = data["markdown"]
        # Navigation and footer should be excluded
        self.assertNotIn("Accueil", md)
        self.assertNotIn("Mentions légales", md)
        self.assertNotIn("Publicité", md)
        self.assertNotIn("evil_tracker", md)

        # Article content and structure should be present
        self.assertIn("# Les fondamentaux des réseaux de neurones", md)
        self.assertIn("## Fonctionnement d'une couche", md)
        self.assertIn("- ReLU (Rectified Linear Unit)", md)
        # Link should be resolved against base_url
        self.assertIn("[les fonctions d'activation courantes](https://iamag.example.com/docs/activation)", md)


class TestWebEndpoints(unittest.TestCase):
    def setUp(self):
        import tempfile
        from uuid import uuid4
        self.tmp = tempfile.TemporaryDirectory()
        self.username = f"user_{uuid4().hex[:8]}"
        self.settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{self.tmp.name}/test.db",
            app_data_dir=self.tmp.name,
            demo_mode=True,
        )
        self.app = create_app(self.settings)
        origin = self.settings.origins[0]
        Base.metadata.create_all(self.app.state.engine)
        with self.app.state.sessions() as db:
            db.add(User(username=self.username, password_hash=hash_password("my-password-123"), is_admin=True))
            db.commit()

        self.client = TestClient(self.app, base_url=origin, headers={"Origin": origin})
        login_res = self.client.post("/api/auth/login", json={"username": self.username, "password": "my-password-123"})
        self.assertEqual(login_res.status_code, 200)

    def tearDown(self):
        self.tmp.cleanup()

    def test_post_attachments_url_mocked(self):
        mock_html = b"""<!DOCTYPE html>
<html><head><title>Page Test Antigravity</title><meta name="description" content="Une page de test." /></head>
<body><article><h1>Titre Test</h1><p>Contenu extrait avec succ\xc3\xa8s.</p></article></body></html>"""

        mock_resp = httpx.Response(
            200,
            content=mock_html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", "https://example.com/article"),
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            res = self.client.post("/api/attachments/url", json={"url": "https://example.com/article"})
            self.assertEqual(res.status_code, 201)
            data = res.json()
            self.assertIn("id", data)
            self.assertTrue(data["filename"].startswith("🌐 Page Test Antigravity"))
            self.assertEqual(data["mime_type"], "text/html")
            self.assertEqual(data["source_url"], "https://example.com/article")
            self.assertTrue(data["has_extraction"])
            self.assertGreater(data["extracted_chars"], 0)

            # Test extraction endpoint
            att_id = data["id"]
            extr_res = self.client.get(f"/api/attachments/{att_id}/extraction")
            self.assertEqual(extr_res.status_code, 200)
            extr_data = extr_res.json()["extraction"]
            self.assertEqual(extr_data["model"], "web-parser")
            self.assertIn("Contenu extrait avec succès", extr_data["pages"][0]["markdown"])

    def test_post_message_with_url_in_content(self):
        # Create conversation
        conv_res = self.client.post("/api/conversations", json={"title": "Test Web Link"})
        self.assertEqual(conv_res.status_code, 201)
        conv_id = conv_res.json()["id"]

        mock_html = b"""<!DOCTYPE html>
<html><head><title>Analyse Automatique</title></head>
<body><article><p>D\xc3\xa9couverte du contenu web automatique.</p></article></body></html>"""

        mock_resp = httpx.Response(
            200,
            content=mock_html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", "https://news.example.org/ia"),
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            msg_res = self.client.post(
                f"/api/conversations/{conv_id}/messages",
                json={
                    "content": "Que dis-tu de https://news.example.org/ia ?",
                    "attachment_ids": [],
                    "web_search": False,
                },
            )
            self.assertEqual(msg_res.status_code, 200)
            self.assertIn("event: meta", msg_res.text)
            self.assertIn("Analyse Automatique", msg_res.text)
            self.assertIn("event: status", msg_res.text)


if __name__ == "__main__":
    unittest.main()
