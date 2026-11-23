import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Base, User


def _mock_youtube_http(title: str = "Conférence Architecture IA", author: str = "TechChannel"):
    watch_html = '<!DOCTYPE html><html><head><script>"INNERTUBE_API_KEY": "AIzaSySavedVidKey"</script></head><body></body></html>'
    innertube_json = {
        "videoDetails": {
            "title": title,
            "author": author,
            "lengthSeconds": "900",
            "shortDescription": "Description complète de test.",
        },
        "captions": {
            "playerCaptionsTracklistRenderer": {
                "captionTracks": [
                    {
                        "baseUrl": "https://www.youtube.com/api/timedtext?v=dQw4w9WgXcQ&lang=fr",
                        "languageCode": "fr",
                        "name": {"runs": [{"text": "Français"}]},
                    }
                ]
            }
        },
    }
    sub_xml = """<transcript>
        <text start="0.0" dur="3.0">Début du transcript intégral sauvegardé.</text>
        <text start="890.0" dur="4.0">Fin du transcript intégral sauvegardé.</text>
    </transcript>"""

    async def fake_get(url, **kwargs):
        url_str = str(url)
        if "watch" in url_str:
            return httpx.Response(200, text=watch_html, request=httpx.Request("GET", url_str))
        if "timedtext" in url_str:
            return httpx.Response(200, text=sub_xml, request=httpx.Request("GET", url_str))
        return httpx.Response(404, request=httpx.Request("GET", url_str))

    async def fake_post(url, **kwargs):
        return httpx.Response(200, json=innertube_json, request=httpx.Request("POST", str(url)))

    return fake_get, fake_post


class TestSavedVideosLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.user_a = f"vida_{uuid4().hex[:8]}"
        self.user_b = f"vidb_{uuid4().hex[:8]}"
        self.settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{self.tmp.name}/test_videos.db",
            app_data_dir=self.tmp.name,
            demo_mode=True,
        )
        self.app = create_app(self.settings)
        self.origin = self.settings.origins[0]
        Base.metadata.create_all(self.app.state.engine)
        with self.app.state.sessions() as db:
            db.add(User(username=self.user_a, password_hash=hash_password("password-vid-123"), is_admin=True))
            db.add(User(username=self.user_b, password_hash=hash_password("password-vid-456"), is_admin=False))
            db.commit()

        self.client_a = TestClient(self.app, base_url=self.origin, headers={"Origin": self.origin})
        self.client_b = TestClient(self.app, base_url=self.origin, headers={"Origin": self.origin})
        self.assertEqual(
            self.client_a.post("/api/auth/login", json={"username": self.user_a, "password": "password-vid-123"}).status_code,
            200,
        )
        self.assertEqual(
            self.client_b.post("/api/auth/login", json={"username": self.user_b, "password": "password-vid-456"}).status_code,
            200,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_attach_url_auto_saves_video_and_supports_full_crud_and_isolation(self):
        fake_get, fake_post = _mock_youtube_http()
        with patch("httpx.AsyncClient.get", side_effect=fake_get), \
             patch("httpx.AsyncClient.post", side_effect=fake_post):
            att_res = self.client_a.post(
                "/api/attachments/url",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "save_to_library": True},
            )
            self.assertEqual(att_res.status_code, 201)
            att = att_res.json()
            saved_id = att["youtube_meta"]["saved_video_id"]
            self.assertTrue(saved_id)

        # List shows title, link, transcript stats
        list_res = self.client_a.get("/api/videos")
        self.assertEqual(list_res.status_code, 200)
        items = list_res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Conférence Architecture IA")
        self.assertEqual(items[0]["url"], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertTrue(items[0]["has_transcript"])
        self.assertNotIn("transcript_markdown", items[0])

        # Detail includes full transcript
        detail_res = self.client_a.get(f"/api/videos/{saved_id}")
        self.assertEqual(detail_res.status_code, 200)
        detail = detail_res.json()
        self.assertIn("Début du transcript intégral sauvegardé.", detail["transcript_markdown"])
        self.assertIn("Fin du transcript intégral sauvegardé.", detail["transcript_markdown"])

        # Isolation: user B cannot see or edit user A's video
        self.assertEqual(self.client_b.get("/api/videos").json(), [])
        self.assertEqual(self.client_b.get(f"/api/videos/{saved_id}").status_code, 404)
        self.assertEqual(self.client_b.delete(f"/api/videos/{saved_id}").status_code, 404)

        # Generate summary on stored transcript (demo mode)
        gen_res = self.client_a.post(
            f"/api/videos/{saved_id}/generate",
            json={"action": "summarize"},
        )
        self.assertEqual(gen_res.status_code, 200)
        gen_data = gen_res.json()
        self.assertTrue(gen_data["has_summary"])
        self.assertIn("Conférence Architecture IA", gen_data["summary_markdown"])
        self.assertEqual(len(gen_data["analyses"]), 1)

        # Patch title & add chat analysis
        patch_res = self.client_a.patch(
            f"/api/videos/{saved_id}",
            json={
                "title": "Mon Titre Personnalisé",
                "summary_markdown": "### Analyse critique\n- Point clé 1",
                "summary_action": "analyze",
            },
        )
        self.assertEqual(patch_res.status_code, 200)
        patched = patch_res.json()
        self.assertEqual(patched["title"], "Mon Titre Personnalisé")
        self.assertEqual(len(patched["analyses"]), 2)

        # Instant re-attach to chat without touching YouTube
        reattach_res = self.client_a.post(f"/api/videos/{saved_id}/attach")
        self.assertEqual(reattach_res.status_code, 201)
        reattached = reattach_res.json()
        self.assertEqual(reattached["youtube_meta"]["saved_video_id"], saved_id)
        self.assertIn("Mon Titre Personnalisé", reattached["filename"])

        # Delete
        del_res = self.client_a.delete(f"/api/videos/{saved_id}")
        self.assertEqual(del_res.status_code, 204)
        self.assertEqual(self.client_a.get("/api/videos").json(), [])

    def test_post_videos_direct_import_and_dedupe_upsert(self):
        fake_get, fake_post = _mock_youtube_http(title="Cours FastAPI", author="DevFr")
        with patch("httpx.AsyncClient.get", side_effect=fake_get), \
             patch("httpx.AsyncClient.post", side_effect=fake_post):
            res1 = self.client_a.post(
                "/api/videos",
                json={"url": "https://youtu.be/dQw4w9WgXcQ", "action": "summarize"},
            )
            self.assertEqual(res1.status_code, 201)
            vid1 = res1.json()
            self.assertTrue(vid1["has_summary"])

            # Re-importing the same video updates instead of duplicating
            res2 = self.client_a.post(
                "/api/videos",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "action": "key_points"},
            )
            self.assertEqual(res2.status_code, 201)
            vid2 = res2.json()
            self.assertEqual(vid2["id"], vid1["id"])
            self.assertEqual(len(self.client_a.get("/api/videos").json()), 1)
            self.assertEqual(len(vid2["analyses"]), 2)


if __name__ == "__main__":
    unittest.main()
