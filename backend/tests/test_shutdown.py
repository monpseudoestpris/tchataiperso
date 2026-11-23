import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Base, User


class TestGracefulShutdown(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.admin_user = f"adm_{uuid4().hex[:8]}"
        self.normal_user = f"usr_{uuid4().hex[:8]}"
        self.settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{self.tmp.name}/test_shutdown.db",
            app_data_dir=self.tmp.name,
            demo_mode=True,
        )
        self.app = create_app(self.settings)
        self.origin = self.settings.origins[0]
        Base.metadata.create_all(self.app.state.engine)
        with self.app.state.sessions() as db:
            db.add(User(username=self.admin_user, password_hash=hash_password("password-adm-123"), is_admin=True))
            db.add(User(username=self.normal_user, password_hash=hash_password("password-usr-456"), is_admin=False))
            db.commit()

        self.admin_client = TestClient(self.app, base_url=self.origin, headers={"Origin": self.origin})
        self.user_client = TestClient(self.app, base_url=self.origin, headers={"Origin": self.origin})
        self.assertEqual(
            self.admin_client.post("/api/auth/login", json={"username": self.admin_user, "password": "password-adm-123"}).status_code,
            200,
        )
        self.assertEqual(
            self.user_client.post("/api/auth/login", json={"username": self.normal_user, "password": "password-usr-456"}).status_code,
            200,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_admin_cannot_access_shutdown_endpoints(self):
        self.assertEqual(self.user_client.get("/api/system/shutdown-status").status_code, 403)
        self.assertEqual(self.user_client.post("/api/system/prepare-shutdown", json={"stop_process": False}).status_code, 403)
        self.assertEqual(self.user_client.post("/api/system/resume").status_code, 403)

    def test_prepare_shutdown_freezes_writes_checkpoints_dbs_and_resumes(self):
        status_res = self.admin_client.get("/api/system/shutdown-status")
        self.assertEqual(status_res.status_code, 200)
        self.assertFalse(status_res.json()["shutting_down"])

        prep_res = self.admin_client.post("/api/system/prepare-shutdown", json={"stop_process": False})
        self.assertEqual(prep_res.status_code, 200)
        data = prep_res.json()
        self.assertEqual(data["status"], "ready_to_quit")
        self.assertTrue(data["shutting_down"])
        self.assertTrue(data["main_db_flushed"])
        self.assertTrue(data["warehouse_checkpoint"]["checkpointed"])

        # Writes are frozen while shutting down
        blocked_res = self.admin_client.post("/api/conversations", json={"title": "Blocked"})
        self.assertEqual(blocked_res.status_code, 503)

        # Health endpoint stays readable
        self.assertEqual(self.admin_client.get("/api/health").status_code, 200)

        # Resume unfreezes writes
        resume_res = self.admin_client.post("/api/system/resume")
        self.assertEqual(resume_res.status_code, 200)
        self.assertFalse(resume_res.json()["shutting_down"])

        ok_res = self.admin_client.post("/api/conversations", json={"title": "After Resume"})
        self.assertEqual(ok_res.status_code, 201)


if __name__ == "__main__":
    unittest.main()
