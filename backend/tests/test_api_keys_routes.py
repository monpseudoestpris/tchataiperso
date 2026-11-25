import httpx
import pytest
from pydantic import SecretStr
from starlette.testclient import TestClient

from app import api_key_tester
from app.auth import hash_password
from app.config import Settings
from app.main import create_app
from app.models import Base, FamilyGroup, User


def _setup_app_with_family(tmp_path, *, demo_mode: bool = True, env_mistral_key: str = ""):
    database_url = f"sqlite:///{tmp_path / 'api_keys_test.db'}"
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        database_url=database_url,
        demo_mode=demo_mode,
        mistral_api_key=env_mistral_key,
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)

    with app.state.sessions() as db:
        family = FamilyGroup(name="Famille Test")
        db.add(family)
        db.flush()
        admin = User(
            username="admin_chef",
            password_hash=hash_password("AdminStrongPass!99"),
            is_admin=True,
            active=True,
            family_group_id=family.id,
        )
        member = User(
            username="membre_enfant",
            password_hash=hash_password("MemberPass!1234"),
            is_admin=False,
            active=True,
            family_group_id=family.id,
        )
        db.add_all([admin, member])
        db.commit()
        admin_id = admin.id

    return app, settings, admin_id


def test_non_admin_forbidden_and_family_switch_blocked_without_admin_password(tmp_path):
    app, settings, admin_id = _setup_app_with_family(tmp_path, env_mistral_key="env-mistral-secret-xyz")
    origin = settings.origins[0]

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        # 1. Connexion en tant que membre non-admin : accès 403 strict sur toutes les routes clés API
        res_login = client.post("/api/auth/login", json={"username": "membre_enfant", "password": "MemberPass!1234"})
        assert res_login.status_code == 200
        assert client.get("/api/settings/api-keys").status_code == 403
        assert (
            client.patch(
                "/api/settings/api-keys",
                json={"current_password": "MemberPass!1234", "keys": {"llm_api_key": "sk-hijack"}},
            ).status_code
            == 403
        )
        assert client.post("/api/settings/api-keys/test", json={"key_name": "mistral_api_key"}).status_code == 403

        # 2. Le membre bascule sur le compte Admin via le groupe familial (sans mot de passe Admin)
        switch_res = client.post(f"/api/family/switch/{admin_id}")
        assert switch_res.status_code == 200
        assert switch_res.json()["is_admin"] is True

        # 3. GET ne renvoie AUCUN caractère de la clé .env
        status_res = client.get("/api/settings/api-keys")
        assert status_res.status_code == 200
        raw_text = status_res.text
        assert "env-mistral-secret-xyz" not in raw_text
        assert "xyz" not in raw_text

        # 4. Tenter d'écraser ou d'effacer une clé sans le vrai mot de passe Admin échoue en 401
        bad_patch = client.patch(
            "/api/settings/api-keys",
            json={"current_password": "MemberPass!1234", "keys": {"llm_api_key": "sk-hijack"}},
        )
        assert bad_patch.status_code == 401
        bad_clear = client.patch(
            "/api/settings/api-keys",
            json={"current_password": "wrong", "clear_keys": ["mistral_api_key"]},
        )
        assert bad_clear.status_code == 401
        assert settings.mistral_api_key.get_secret_value() == "env-mistral-secret-xyz"


def test_vault_override_priority_zero_leak_demo_mode_auto_exit_and_restore(tmp_path):
    env_mistral = "env-mistral-987654321"
    vault_llm = "sk-or-v1-vault-secret-abcdef123456"
    vault_mistral = "vault-mistral-override-555555"

    app, settings, _ = _setup_app_with_family(tmp_path, demo_mode=True, env_mistral_key=env_mistral)
    origin = settings.origins[0]

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        login_res = client.post("/api/auth/login", json={"username": "admin_chef", "password": "AdminStrongPass!99"})
        assert login_res.status_code == 200

        # État initial : DEMO_MODE=true, mistral en active_env, llm en missing
        init_res = client.get("/api/settings/api-keys")
        assert init_res.status_code == 200
        init_body = init_res.json()
        assert init_body["demo_mode"] is True
        assert init_body["baseline_demo_mode"] is True
        by_name = {item["key_name"]: item for item in init_body["items"]}
        assert by_name["llm_api_key"]["status"] == "missing"
        assert by_name["mistral_api_key"]["status"] == "active_env"
        assert by_name["mistral_api_key"]["has_env_fallback"] is True

        # Enregistrement dans le coffre-fort : sortie auto de DEMO_MODE + surcharge prioritaire sur .env
        save_res = client.patch(
            "/api/settings/api-keys",
            json={
                "current_password": "AdminStrongPass!99",
                "keys": {
                    "llm_api_key": f"Bearer {vault_llm}",
                    "mistral_api_key": vault_mistral,
                },
            },
        )
        assert save_res.status_code == 200
        save_text = save_res.text
        for secret_fragment in (env_mistral, vault_llm, vault_mistral, "123456", "555555", "987654"):
            assert secret_fragment not in save_text

        saved_body = save_res.json()
        assert saved_body["demo_mode"] is False
        assert saved_body["baseline_demo_mode"] is True
        by_name = {item["key_name"]: item for item in saved_body["items"]}
        assert by_name["llm_api_key"]["status"] == "active_vault"
        assert by_name["llm_api_key"]["updated_at"] is not None
        assert by_name["mistral_api_key"]["status"] == "active_vault"
        assert by_name["mistral_api_key"]["has_env_fallback"] is True

        # Vérification effective côté Settings et /api/config
        assert settings.demo_mode is False
        assert settings.llm_api_key.get_secret_value() == vault_llm
        assert settings.mistral_api_key.get_secret_value() == vault_mistral
        cfg_res = client.get("/api/config")
        assert cfg_res.status_code == 200
        assert vault_llm not in cfg_res.text
        assert cfg_res.json()["demo_mode"] is False
        assert cfg_res.json()["features"]["ocr"] is True

        # Suppression de mistral_api_key -> retour immédiat à la clé du .env
        clear_mistral = client.patch(
            "/api/settings/api-keys",
            json={"current_password": "AdminStrongPass!99", "clear_keys": ["mistral_api_key"]},
        )
        assert clear_mistral.status_code == 200
        assert settings.mistral_api_key.get_secret_value() == env_mistral
        by_name = {item["key_name"]: item for item in clear_mistral.json()["items"]}
        assert by_name["mistral_api_key"]["status"] == "active_env"

        # Suppression de llm_api_key -> retour au comportement DEMO_MODE=true du .env
        clear_llm = client.patch(
            "/api/settings/api-keys",
            json={"current_password": "AdminStrongPass!99", "clear_keys": ["llm_api_key"]},
        )
        assert clear_llm.status_code == 200
        assert clear_llm.json()["demo_mode"] is True
        assert settings.demo_mode is True
        assert settings.llm_api_key.get_secret_value() == ""


def test_sudo_rate_limiting_and_forbidden_internal_keys(tmp_path):
    app, settings, _ = _setup_app_with_family(tmp_path)
    origin = settings.origins[0]

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        client.post("/api/auth/login", json={"username": "admin_chef", "password": "AdminStrongPass!99"})

        # Clé interne HERMES_API_KEY refusée en 400 avant même de toucher au coffre
        bad_key = client.patch(
            "/api/settings/api-keys",
            json={"current_password": "AdminStrongPass!99", "keys": {"hermes_api_key": "internal"}},
        )
        assert bad_key.status_code == 400

        # 8 échecs de mot de passe -> 401, puis la 9e tentative est bloquée en 429
        for _ in range(8):
            r = client.patch(
                "/api/settings/api-keys",
                json={"current_password": "bad-password", "keys": {"brave_api_key": "bsa-123"}},
            )
            assert r.status_code == 401

        throttled = client.patch(
            "/api/settings/api-keys",
            json={"current_password": "AdminStrongPass!99", "keys": {"brave_api_key": "bsa-123"}},
        )
        assert throttled.status_code == 429


def test_provider_probe_endpoint_never_leaks_candidate_secret(tmp_path, monkeypatch):
    app, settings, _ = _setup_app_with_family(tmp_path)
    origin = settings.origins[0]

    class FakeResponse:
        def __init__(self, status_code: int):
            self.status_code = status_code

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, **kwargs):
            headers = kwargs.get("headers") or {}
            if headers.get("Authorization") == "Bearer valid-key-secret-token":
                return FakeResponse(200)
            if "timeout" in str(headers.get("Authorization", "")):
                raise httpx.ReadTimeout("simulated timeout with secret valid-key-secret-token")
            return FakeResponse(401)

    monkeypatch.setattr(api_key_tester.httpx, "AsyncClient", FakeAsyncClient)

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        client.post("/api/auth/login", json={"username": "admin_chef", "password": "AdminStrongPass!99"})

        ok_res = client.post(
            "/api/settings/api-keys/test",
            json={"key_name": "mistral_api_key", "candidate_value": "valid-key-secret-token"},
        )
        assert ok_res.status_code == 200
        assert ok_res.json()["valid"] is True
        assert "valid-key-secret-token" not in ok_res.text

        ko_res = client.post(
            "/api/settings/api-keys/test",
            json={"key_name": "mistral_api_key", "candidate_value": "bad-secret-token"},
        )
        assert ko_res.status_code == 200
        assert ko_res.json()["valid"] is False
        assert "401" in ko_res.json()["detail"]
        assert "bad-secret-token" not in ko_res.text

        to_res = client.post(
            "/api/settings/api-keys/test",
            json={"key_name": "mistral_api_key", "candidate_value": "timeout-secret-token"},
        )
        assert to_res.status_code == 200
        assert to_res.json()["valid"] is False
        assert "timeout-secret-token" not in to_res.text
        assert "valid-key-secret-token" not in to_res.text


def test_direct_runtime_settings_mutations_preserved_when_vault_has_no_override(tmp_path):
    app, settings, _ = _setup_app_with_family(tmp_path, demo_mode=True)
    origin = settings.origins[0]

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        settings.demo_mode = False
        settings.brave_api_key = SecretStr("runtime-brave-key")
        cfg = client.get("/api/config").json()
        assert cfg["demo_mode"] is False
        assert "brave" in cfg["search_providers"]

