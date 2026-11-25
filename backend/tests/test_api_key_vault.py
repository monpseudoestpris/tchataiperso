import base64
import os
import secrets

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api_key_vault import (
    ALLOWED_VAULT_KEY_NAMES,
    ApiKeyVault,
    VaultConfigurationError,
    VaultIntegrityError,
    decrypt_api_key,
    encrypt_api_key,
    load_or_create_master_key,
    normalize_secret_input,
    validate_vault_key_name,
)
from app.models import ApiKeyOverride, Base


def test_allowed_vault_keys_strictly_limited_to_8_external_providers():
    assert len(ALLOWED_VAULT_KEY_NAMES) == 8
    for forbidden in ("hermes_api_key", "postgres_password", "searxng_secret", "session_cookie_name"):
        with pytest.raises(ValueError, match="non autorisée"):
            validate_vault_key_name(forbidden)


def test_normalize_secret_input_strips_bearer_quotes_and_comments_and_rejects_control_chars():
    assert normalize_secret_input("  'Bearer sk-or-v1-test12345'  # prod key ") == "sk-or-v1-test12345"
    assert normalize_secret_input('"AIzaSyTestKey9876"') == "AIzaSyTestKey9876"
    with pytest.raises(ValueError, match="vide"):
        normalize_secret_input("   # only comment")
    with pytest.raises(ValueError, match="contrôle"):
        normalize_secret_input("sk-test\ninjected")
    with pytest.raises(ValueError, match="longueur maximale"):
        normalize_secret_input("x" * 513)


def test_aes_256_gcm_roundtrip_unique_nonces_and_aad_row_swap_protection():
    master_key = secrets.token_bytes(32)
    plaintext = "sk-or-v1-super-secret-value"

    tok1 = encrypt_api_key(master_key, "llm_api_key", plaintext)
    tok2 = encrypt_api_key(master_key, "llm_api_key", plaintext)
    assert tok1 != tok2
    assert plaintext not in tok1
    assert decrypt_api_key(master_key, "llm_api_key", tok1) == plaintext
    assert decrypt_api_key(master_key, "llm_api_key", tok2) == plaintext

    # Un attaquant échangeant le ciphertext vers une autre colonne/clé échoue grâce à l'AAD
    with pytest.raises(VaultIntegrityError, match="Authentification AES-GCM refusée"):
        decrypt_api_key(master_key, "mistral_api_key", tok1)

    # Toute altération d'un octet du ciphertext est détectée
    wrong_key = secrets.token_bytes(32)
    with pytest.raises(VaultIntegrityError):
        decrypt_api_key(wrong_key, "llm_api_key", tok1)


def test_master_key_file_created_with_0600_permissions_and_env_override(tmp_path, monkeypatch):
    key_path = tmp_path / "vault" / ".vault.key"
    k1 = load_or_create_master_key(tmp_path, vault_key_path=key_path)
    k2 = load_or_create_master_key(tmp_path, vault_key_path=key_path)
    assert len(k1) == 32
    assert k1 == k2
    if os.name == "posix":
        assert (key_path.stat().st_mode & 0o777) == 0o600

    # Priorité à CLAIR_VAULT_KEY si définie dans l'environnement
    env_raw = secrets.token_bytes(32)
    monkeypatch.setenv("CLAIR_VAULT_KEY", base64.urlsafe_b64encode(env_raw).decode("ascii"))
    assert load_or_create_master_key(tmp_path, vault_key_path=key_path) == env_raw

    # Format CLAIR_VAULT_KEY invalide rejeté explicitement
    monkeypatch.setenv("CLAIR_VAULT_KEY", "short-invalid-key")
    with pytest.raises(VaultConfigurationError):
        load_or_create_master_key(tmp_path, vault_key_path=key_path)


def test_api_key_vault_sql_upsert_delete_and_zero_plaintext_in_db(tmp_path):
    db_file = tmp_path / "vault_test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    vault = ApiKeyVault(sessions=sessions, app_data_dir=tmp_path)
    assert vault.get_decrypted_overrides() == {}

    saved = vault.upsert_overrides(
        {
            "llm_api_key": "Bearer sk-or-live-secret-999",
            "eod_historical_data_key": "eodhd-secret-token-777",
        },
        updated_by_user_id=None,
    )
    assert set(saved) == {"llm_api_key", "eod_historical_data_key"}

    # Vérification directe en base SQL : aucun secret en clair n'est stocké
    with sessions() as db:
        rows = list(db.scalars(select(ApiKeyOverride)))
        assert len(rows) == 2
        for row in rows:
            assert row.ciphertext.startswith("v1:")
            assert "sk-or-live-secret-999" not in row.ciphertext
            assert "eodhd-secret-token-777" not in row.ciphertext

    decrypted = vault.get_decrypted_overrides()
    assert decrypted == {
        "llm_api_key": "sk-or-live-secret-999",
        "eod_historical_data_key": "eodhd-secret-token-777",
    }

    stamps = vault.list_override_timestamps()
    assert set(stamps.keys()) == {"llm_api_key", "eod_historical_data_key"}

    assert vault.delete_override("llm_api_key") is True
    assert vault.delete_override("llm_api_key") is False
    assert vault.get_decrypted_overrides() == {"eod_historical_data_key": "eodhd-secret-token-777"}
    engine.dispose()
