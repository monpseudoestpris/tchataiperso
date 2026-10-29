"""Isole la suite de tests de l'environnement du développeur.

Toute variable d'environnement correspondant à un champ de `Settings` (DATABASE_URL, APP_DATA_DIR,
clés d'API...) est retirée : sinon les tests écrivent dans la vraie base de développement et
utilisent de vraies clés au lieu de la configuration explicite qu'ils construisent.
"""
import os

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch):
    names = {name.upper() for name in Settings.model_fields}
    for key in list(os.environ):
        if key.upper() in names:
            monkeypatch.delenv(key, raising=False)
