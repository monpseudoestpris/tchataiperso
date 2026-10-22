import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Base, User
from app.youtube import (
    DEFAULT_INNERTUBE_API_KEY,
    extract_innertube_key_from_html,
    extract_youtube_video_id,
    fetch_and_parse_youtube_video,
    format_duration,
    format_transcript_paragraphs,
    get_innertube_api_key,
    select_best_caption_track,
)


class TestYouTubeHelpers(unittest.TestCase):
    def test_extract_video_id(self):
        cases = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtube.com/watch?feature=shared&v=dQw4w9WgXcQ&t=10s", "dQw4w9WgXcQ"),
            ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?si=abc123xyz", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
            ("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share", "dQw4w9WgXcQ"),
            ("https://example.com/watch?v=dQw4w9WgXcQ", None),
            ("https://youtube.com/about", None),
        ]
        for url, expected in cases:
            self.assertEqual(extract_youtube_video_id(url), expected, f"Failed for {url}")

    def test_format_duration(self):
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(45), "00:45")
        self.assertEqual(format_duration(125), "02:05")
        self.assertEqual(format_duration(3665), "01:01:05")

    def test_format_transcript_paragraphs(self):
        nodes = [
            (1.5, "Bonjour à tous"),
            (4.0, "et bienvenue dans cette vidéo."),
            (8.0, "Aujourd'hui nous allons parler d'un sujet passionnant :"),
            (15.0, "les réseaux de neurones."),
            (21.0, "Commençons dès maintenant."),
        ]
        res = format_transcript_paragraphs(nodes)
        self.assertIn("[00:01] Bonjour à tous et bienvenue dans cette vidéo.", res)
        self.assertIn("Aujourd'hui nous allons parler", res)
        self.assertIn("[00:21] Commençons dès maintenant.", res)

    def test_select_best_caption_track(self):
        tracks = [
            {"languageCode": "en", "kind": "asr", "baseUrl": "http://en-asr"},
            {"languageCode": "en", "baseUrl": "http://en-manual"},
            {"languageCode": "fr", "kind": "asr", "baseUrl": "http://fr-asr"},
            {"languageCode": "es", "baseUrl": "http://es-manual"},
        ]
        # French auto should be chosen over English manual because French is preferred
        chosen = select_best_caption_track(tracks)
        self.assertEqual(chosen["languageCode"], "fr")

        # If French manual is present, it takes top priority
        tracks.append({"languageCode": "fr", "baseUrl": "http://fr-manual"})
        chosen2 = select_best_caption_track(tracks)
        self.assertEqual(chosen2["baseUrl"], "http://fr-manual")

    def test_extract_innertube_key_from_html(self):
        # Standard UPPERCASE key in JSON
        html1 = '<html><script>var ytcfg = {"INNERTUBE_API_KEY": "AIzaSyDynamicKey123", "INNERTUBE_CONTEXT": {}}</script></html>'
        self.assertEqual(extract_innertube_key_from_html(html1), "AIzaSyDynamicKey123")

        # CamelCase innertubeApiKey
        html2 = '<html><script>window.yt = {"innertubeApiKey": "AIzaSyCamelKey456"};</script></html>'
        self.assertEqual(extract_innertube_key_from_html(html2), "AIzaSyCamelKey456")

        # Key not present
        html3 = '<html><script>var empty = 1;</script></html>'
        self.assertIsNone(extract_innertube_key_from_html(html3))
        self.assertIsNone(extract_innertube_key_from_html(""))


class TestYouTubeDynamicApiKey(unittest.IsolatedAsyncioTestCase):
    async def test_get_innertube_api_key_from_watch_page(self):
        mock_watch = '<html><script>"INNERTUBE_API_KEY": "AIzaWatchDynamicKey"</script></html>'

        async def fake_get(url, **kwargs):
            return httpx.Response(200, text=mock_watch, request=httpx.Request("GET", str(url)))

        with patch("httpx.AsyncClient.get", side_effect=fake_get):
            async with httpx.AsyncClient() as client:
                key = await get_innertube_api_key(client, video_id="testvid123")
                self.assertEqual(key, "AIzaWatchDynamicKey")

    async def test_get_innertube_api_key_embed_fallback(self):
        # Watch page has no key (e.g. restricted), embed page has the key
        async def fake_get(url, **kwargs):
            url_str = str(url)
            if "/watch" in url_str:
                return httpx.Response(200, text="<html>No key here</html>", request=httpx.Request("GET", url_str))
            if "/embed" in url_str:
                return httpx.Response(
                    200,
                    text='<html><script>"innertubeApiKey": "AIzaEmbedDynamicKey"</script></html>',
                    request=httpx.Request("GET", url_str),
                )
            return httpx.Response(404, request=httpx.Request("GET", url_str))

        with patch("httpx.AsyncClient.get", side_effect=fake_get):
            async with httpx.AsyncClient() as client:
                key = await get_innertube_api_key(client, video_id="embedvid456")
                self.assertEqual(key, "AIzaEmbedDynamicKey")

    async def test_get_innertube_api_key_default_fallback(self):
        # All requests fail with 500/404 or empty
        import app.youtube as yt_mod
        yt_mod._cached_innertube_api_key = None

        async def fake_get(url, **kwargs):
            return httpx.Response(500, text="error", request=httpx.Request("GET", str(url)))

        with patch("httpx.AsyncClient.get", side_effect=fake_get):
            async with httpx.AsyncClient() as client:
                key = await get_innertube_api_key(client, video_id="failedvid")
                self.assertEqual(key, DEFAULT_INNERTUBE_API_KEY)


class TestYouTubeEndpointIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.username = f"ytuser_{uuid4().hex[:8]}"
        self.settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{self.tmp.name}/test_yt.db",
            app_data_dir=self.tmp.name,
            demo_mode=True,
        )
        self.app = create_app(self.settings)
        origin = self.settings.origins[0]
        Base.metadata.create_all(self.app.state.engine)
        with self.app.state.sessions() as db:
            db.add(User(username=self.username, password_hash=hash_password("password-yt-123"), is_admin=True))
            db.commit()

        self.client = TestClient(self.app, base_url=origin, headers={"Origin": origin})
        login_res = self.client.post("/api/auth/login", json={"username": self.username, "password": "password-yt-123"})
        self.assertEqual(login_res.status_code, 200)

    def tearDown(self):
        self.tmp.cleanup()

    def test_post_attachments_youtube_mocked(self):
        mock_watch_html = """<!DOCTYPE html><html><head>
        <script>"INNERTUBE_API_KEY": "AIzaSyFakeKey123"</script>
        </head><body></body></html>"""

        mock_innertube_json = {
            "videoDetails": {
                "title": "Introduction à l'IA Moderne",
                "author": "TechEdu France",
                "lengthSeconds": "300",
                "shortDescription": "Une leçon sur les transformers et l'attention.",
                "viewCount": "15000",
            },
            "captions": {
                "playerCaptionsTracklistRenderer": {
                    "captionTracks": [
                        {
                            "baseUrl": "https://www.youtube.com/api/timedtext?v=fake_vid&lang=fr",
                            "languageCode": "fr",
                            "name": {"runs": [{"text": "Français"}]},
                        }
                    ]
                }
            },
        }

        mock_sub_xml = """<transcript>
            <text start="0.0" dur="3.0">Bienvenue dans cette leçon sur les transformers.</text>
            <text start="3.5" dur="4.0">Le mécanisme d'attention permet de relier les mots entre eux.</text>
            <text start="8.0" dur="3.0">C'est la base des modèles actuels.</text>
        </transcript>"""

        async def fake_get(url, **kwargs):
            url_str = str(url)
            if "watch" in url_str:
                return httpx.Response(200, text=mock_watch_html, request=httpx.Request("GET", url_str))
            if "timedtext" in url_str:
                return httpx.Response(200, text=mock_sub_xml, request=httpx.Request("GET", url_str))
            return httpx.Response(404, request=httpx.Request("GET", url_str))

        async def fake_post(url, **kwargs):
            return httpx.Response(200, json=mock_innertube_json, request=httpx.Request("POST", str(url)))

        with patch("httpx.AsyncClient.get", side_effect=fake_get), \
             patch("httpx.AsyncClient.post", side_effect=fake_post):

            res = self.client.post("/api/attachments/url", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
            self.assertEqual(res.status_code, 201)
            data = res.json()
            self.assertIn("id", data)
            self.assertTrue(data["filename"].startswith("🎬 Introduction à l'IA"))
            self.assertIn("video=youtube", data["mime_type"])
            self.assertTrue(data["has_extraction"])
            self.assertGreater(data["extracted_chars"], 0)

            # Test extraction viewer
            att_id = data["id"]
            extr_res = self.client.get(f"/api/attachments/{att_id}/extraction")
            self.assertEqual(extr_res.status_code, 200)
            markdown = extr_res.json()["extraction"]["pages"][0]["markdown"]
            self.assertIn("Introduction à l'IA Moderne", markdown)
            self.assertIn("TechEdu France", markdown)
            self.assertIn("[00:00] Bienvenue dans cette leçon", markdown)
            self.assertIn("[00:03] Le mécanisme d'attention", markdown)

    def test_message_with_youtube_url_auto_parse(self):
        conv_res = self.client.post("/api/conversations", json={"title": "Test Chat YouTube"})
        self.assertEqual(conv_res.status_code, 201)
        conv_id = conv_res.json()["id"]

        mock_watch_html = """<!DOCTYPE html><html><head>
        <script>"INNERTUBE_API_KEY": "AIzaSyFakeKey456"</script>
        </head><body></body></html>"""

        mock_innertube_json = {
            "videoDetails": {
                "title": "Vidéo Résumé Test",
                "author": "Science Channel",
                "lengthSeconds": "180",
                "shortDescription": "Description de test",
            },
            "captions": {
                "playerCaptionsTracklistRenderer": {
                    "captionTracks": [
                        {
                            "baseUrl": "https://www.youtube.com/api/timedtext?v=fake2",
                            "languageCode": "fr",
                            "name": {"runs": [{"text": "Français"}]},
                        }
                    ]
                }
            },
        }

        mock_sub_xml = """<transcript>
            <text start="0.0" dur="4.0">Voici le résumé complet de la vidéo.</text>
        </transcript>"""

        async def fake_get(url, **kwargs):
            url_str = str(url)
            if "watch" in url_str:
                return httpx.Response(200, text=mock_watch_html, request=httpx.Request("GET", url_str))
            if "timedtext" in url_str:
                return httpx.Response(200, text=mock_sub_xml, request=httpx.Request("GET", url_str))
            return httpx.Response(404, request=httpx.Request("GET", url_str))

        async def fake_post(url, **kwargs):
            return httpx.Response(200, json=mock_innertube_json, request=httpx.Request("POST", str(url)))

        with patch("httpx.AsyncClient.get", side_effect=fake_get), \
             patch("httpx.AsyncClient.post", side_effect=fake_post):

            msg_res = self.client.post(
                f"/api/conversations/{conv_id}/messages",
                json={
                    "content": "Que dit cette vidéo https://youtu.be/dQw4w9WgXcQ ?",
                    "attachment_ids": [],
                    "web_search": False,
                },
            )
            self.assertEqual(msg_res.status_code, 200)
            self.assertIn("event: meta", msg_res.text)
            self.assertIn("Vidéo Résumé Test", msg_res.text)
            self.assertIn("Analyse de la vidéo YouTube", msg_res.text)


if __name__ == "__main__":
    unittest.main()

