#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

echo "[1/2] Tests unitaires et isolation multi-utilisateurs (pytest)..."
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_hermes.py -v

echo "[2/2] Test bout-en-bout réel : Hermes Gateway -> MCP params._meta -> clair_create_page -> PostgreSQL..."
docker exec -i tchataiperso-clair-api-1 python - <<'PY'
import sys
import uuid
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.auth import hash_password
from app.config import Settings
from app.models import AuthSession, User, WebPage

s = Settings()
engine = create_engine(s.db_url)
Sessions = sessionmaker(bind=engine, expire_on_commit=False)

uname = "e2e-user-" + uuid.uuid4().hex[:8]
uid = None

try:
    with Sessions() as db:
        u = User(
            username=uname,
            password_hash=hash_password("test-password-1234"),
            is_admin=False,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        uid = u.id

    with httpx.Client(base_url="http://127.0.0.1:8001", timeout=120.0) as client:
        login = client.post(
            "/api/auth/login",
            headers={"Origin": "http://localhost:3001"},
            json={"username": uname, "password": "test-password-1234"},
        )
        assert login.status_code == 200, f"Login failed: {login.status_code}"
        resp = client.post(
            "/api/hermes/run",
            headers={"Origin": "http://localhost:3001"},
            json={
                "prompt": (
                    'Appelle immédiatement l outil mcp__clair__clair_create_page avec '
                    'title="E2E Gateway Draft", '
                    'content="Contenu de validation bout en bout Hermes Gateway vers cLAIr Pages via MCP params._meta.", '
                    'page_type="educational".'
                ),
                "execution_mode": "gateway",
                "enabled_tools": ["create_page"],
            },
        )
        assert resp.status_code == 200, f"/api/hermes/run failed: {resp.status_code}"

    with Sessions() as db:
        pages = db.scalars(select(WebPage).where(WebPage.user_id == uid)).all()
        assert len(pages) == 1, f"Expected 1 draft page, got {len(pages)}"
        page = pages[0]
        assert page.is_published is False, "Draft must not be published"
        print(f"E2E OK: draft_id={page.id} title={page.title!r} is_published={page.is_published}")
finally:
    if uid:
        with Sessions() as db:
            for p in db.scalars(select(WebPage).where(WebPage.user_id == uid)).all():
                db.delete(p)
            for sess in db.scalars(select(AuthSession).where(AuthSession.user_id == uid)).all():
                db.delete(sess)
            u = db.get(User, uid)
            if u:
                db.delete(u)
            db.commit()
PY
