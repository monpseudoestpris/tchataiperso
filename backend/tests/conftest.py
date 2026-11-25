"""Isole la suite de tests de l'environnement du développeur.

Toute variable d'environnement correspondant à un champ de `Settings` (DATABASE_URL, APP_DATA_DIR,
clés d'API...) est retirée : sinon les tests écrivent dans la vraie base de développement et
utilisent de vraies clés au lieu de la configuration explicite qu'ils construisent.
"""
import os
from pathlib import Path

import pytest

from app import api_key_vault as vault_module
from app import config as config_module
from app.config import Settings
from app.google_cloud import clear_google_auth_cache


_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REAL_ENV_PATHS = frozenset({
    (_BACKEND_DIR / ".env").resolve(),
    (_BACKEND_DIR.parent / ".env").resolve(),
})

_EXTRA_ISOLATED_ENV_VARS = {
    "VERTEX_PROJECT_ID",
    "VERTEX_LOCATION",
    "GOOGLE_CLOUD_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "CLAIR_VAULT_KEY",
    "CLAIR_VAULT_KEY_FILE",
}


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch, tmp_path):
    names = {name.upper() for name in Settings.model_fields} | _EXTRA_ISOLATED_ENV_VARS
    for key in list(os.environ):
        if key.upper() in names:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config_module, "_ISOLATED_ENV_PATHS", _REAL_ENV_PATHS)
    monkeypatch.setattr(config_module, "_REPO_ENV_FILE", tmp_path / ".isolated_nonexistent_env")
    monkeypatch.setattr(vault_module, "_ALLOW_USER_SECRETS_DIR", False)
    clear_google_auth_cache()
    yield
    clear_google_auth_cache()
