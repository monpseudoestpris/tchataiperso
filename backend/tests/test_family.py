from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Base, FamilyGroup, User


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)


@contextmanager
def setup_app_and_client(settings):
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)
    with app.state.sessions() as db:
        admin_user = User(username="parent_admin", password_hash=hash_password("admin_password_123"), is_admin=True)
        db.add(admin_user)
        db.commit()
    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        res = client.post("/api/auth/login", json={"username": "parent_admin", "password": "admin_password_123"})
        assert res.status_code == 200
        yield client, app


def test_family_group_lifecycle_and_fast_switch(settings):
    with setup_app_and_client(settings) as (client, app):
        # 1. Initialement, aucun groupe familial
        res = client.get("/api/family")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] is None
        assert data["name"] is None
        assert data["members"] == []

        # 2. Création d'un groupe familial
        res = client.post("/api/family", json={"name": "Famille Martin"})
        assert res.status_code == 200
        data = res.json()
        assert data["id"] is not None
        assert data["name"] == "Famille Martin"
        assert len(data["members"]) == 1
        assert data["members"][0]["username"] == "parent_admin"
        assert data["members"][0]["is_current"] is True

        # 3. Création directe du 2e compte dans la famille (ex: enfant1) sans avoir besoin d'invitation
        res = client.post(
            "/api/family/members",
            json={"username": "lucas_martin", "password": "password_lucas_123"},
        )
        assert res.status_code == 201
        data = res.json()
        assert len(data["members"]) == 2
        usernames = [m["username"] for m in data["members"]]
        assert "parent_admin" in usernames
        assert "lucas_martin" in usernames

        # 4. Création directe du 3e compte (ex: enfant2 / maman)
        res = client.post(
            "/api/family/members",
            json={"username": "emma_martin", "password": "password_emma_123"},
        )
        assert res.status_code == 201
        data = res.json()
        assert len(data["members"]) == 3
        lucas_info = next(m for m in data["members"] if m["username"] == "lucas_martin")
        emma_info = next(m for m in data["members"] if m["username"] == "emma_martin")
        parent_info = next(m for m in data["members"] if m["username"] == "parent_admin")

        # 5. Switch de compte instantané sans retaper login ni mdp vers Lucas
        switch_res = client.post(f"/api/family/switch/{lucas_info['id']}")
        assert switch_res.status_code == 200
        switched_user = switch_res.json()
        assert switched_user["username"] == "lucas_martin"

        # Vérifier que la session courante est bien devenue Lucas
        session_res = client.get("/api/auth/session")
        assert session_res.status_code == 200
        assert session_res.json()["username"] == "lucas_martin"

        # 6. Depuis le compte de Lucas, switch instantané vers Emma
        switch_res2 = client.post(f"/api/family/switch/{emma_info['id']}")
        assert switch_res2.status_code == 200
        assert switch_res2.json()["username"] == "emma_martin"

        session_res2 = client.get("/api/auth/session")
        assert session_res2.status_code == 200
        assert session_res2.json()["username"] == "emma_martin"

        # 7. Depuis Emma, switch de retour vers le parent_admin
        switch_res3 = client.post(f"/api/family/switch/{parent_info['id']}")
        assert switch_res3.status_code == 200
        assert switch_res3.json()["username"] == "parent_admin"

        # 8. Tentative de switch vers un compte externe non membre de la famille -> 403
        with app.state.sessions() as db:
            outsider = User(username="outsider_user", password_hash=hash_password("outsider_pass_123"), is_admin=False)
            db.add(outsider)
            db.commit()
            outsider_id = outsider.id

        forbidden_switch = client.post(f"/api/family/switch/{outsider_id}")
        assert forbidden_switch.status_code == 403

        # 9. Renommage du groupe familial
        patch_res = client.patch("/api/family", json={"name": "Famille Martin & Co"})
        assert patch_res.status_code == 200
        assert patch_res.json()["name"] == "Famille Martin & Co"

        # 10. Rattachement d'un compte existant avec mot de passe
        link_res = client.post(
            "/api/family/link",
            json={"username": "outsider_user", "password": "outsider_pass_123"},
        )
        assert link_res.status_code == 200
        data_after_link = link_res.json()
        assert len(data_after_link["members"]) == 4

        # Maintenant le switch vers cet outsider devenu membre est autorisé
        allowed_now = client.post(f"/api/family/switch/{outsider_id}")
        assert allowed_now.status_code == 200
        assert allowed_now.json()["username"] == "outsider_user"

        # 11. Déconnexion via le bouton déconnexion -> retour login
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 204

        # Vérification que la session est invalidée
        post_logout = client.get("/api/auth/session")
        assert post_logout.status_code == 401

