"""Coffre-fort chiffré AES-256-GCM (« Write-Only ») pour les surcharges de clés API externes.

Invariants de sécurité (ADR-0007) :
- Seules les 8 clés fournisseurs externes autorisées peuvent être lues, écrites ou supprimées.
- Chiffrement authentifié AES-256-GCM avec nonce aléatoire de 96 bits unique par écriture et
  données associées (`AAD`) liées à `key_name` pour empêcher toute permutation de lignes en base.
- La clé maîtresse 256 bits est résolue depuis `CLAIR_VAULT_KEY` ou stockée hors de la base SQL
  dans un fichier dédié en permissions strictes `0600` (`.vault.key`).
- Aucune méthode de ce module ne journalise ni n'expose une clé en clair dans ses exceptions.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import logging
import os
from pathlib import Path
import re
import secrets
import threading
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .models import ApiKeyOverride, now


_logger = logging.getLogger("uvicorn.error")

_TOKEN_PREFIX = "v1:"
_AAD_PREFIX = "clair.api_key_overrides.v1:"
_NONCE_BYTES = 12
_KEY_BYTES = 32
_MAX_SECRET_CHARS = 512
_CACHE_TTL_SECONDS = 5.0
_KEY_FILE_LOCK = threading.Lock()

# Désactivé automatiquement par `tests/conftest.py` pour isoler les tests du HOME développeur.
_ALLOW_USER_SECRETS_DIR = True


class VaultConfigurationError(RuntimeError):
    """Erreur de configuration de la clé maîtresse du coffre-fort (sans secret exposé)."""


class VaultIntegrityError(ValueError):
    """Échec d'authentification ou de format d'une entrée chiffrée dans `api_key_overrides`."""


@dataclass(frozen=True)
class ApiKeySpec:
    key_name: str
    env_name: str
    label: str
    description: str
    is_llm_key: bool = False


EXTERNAL_API_KEY_SPECS: tuple[ApiKeySpec, ...] = (
    ApiKeySpec(
        key_name="llm_api_key",
        env_name="LLM_API_KEY",
        label="OpenRouter / LLM Principal",
        description="Tchat principal, vision, DeepSearch Sonar et modèles d'images OpenRouter.",
        is_llm_key=True,
    ),
    ApiKeySpec(
        key_name="google_api_key",
        env_name="GOOGLE_API_KEY",
        label="Google Gemini API",
        description="Synthèse vocale TTS, dictée STT, Deep Research et Gemini Developer API.",
        is_llm_key=True,
    ),
    ApiKeySpec(
        key_name="vertex_api_key",
        env_name="VERTEX_API_KEY",
        label="Google Cloud Vertex AI",
        description="Routage des modèles Google via clé API Vertex AI Express.",
        is_llm_key=True,
    ),
    ApiKeySpec(
        key_name="mistral_api_key",
        env_name="MISTRAL_API_KEY",
        label="Mistral AI",
        description="OCR PDF & Documents Illustrés (Mistral OCR 4.1) et dictée vocale Voxtral.",
        is_llm_key=False,
    ),
    ApiKeySpec(
        key_name="ideogram_api_key",
        env_name="IDEOGRAM_API_KEY",
        label="Ideogram",
        description="Génération et retouche d'images dans le Studio Image (Ideogram 4.5 / 4.0 / 3.0).",
        is_llm_key=False,
    ),
    ApiKeySpec(
        key_name="eleven_labs_key",
        env_name="ELEVEN_LABS_KEY",
        label="ElevenLabs",
        description="Création d'effets sonores et composition musicale dans le Studio Son.",
        is_llm_key=False,
    ),
    ApiKeySpec(
        key_name="eod_historical_data_key",
        env_name="EOD_HISTORICAL_DATA_KEY",
        label="EOD Historical Data (EODHD)",
        description="Cotations boursières, fondamentaux, Screener et synchronisation quotidienne.",
        is_llm_key=False,
    ),
    ApiKeySpec(
        key_name="brave_api_key",
        env_name="BRAVE_API_KEY",
        label="Brave Search",
        description="Recherche web de secours derrière SearXNG.",
        is_llm_key=False,
    ),
)

API_KEY_SPECS_BY_NAME: dict[str, ApiKeySpec] = {spec.key_name: spec for spec in EXTERNAL_API_KEY_SPECS}
ALLOWED_VAULT_KEY_NAMES: frozenset[str] = frozenset(API_KEY_SPECS_BY_NAME)
LLM_VAULT_KEY_NAMES: frozenset[str] = frozenset(
    spec.key_name for spec in EXTERNAL_API_KEY_SPECS if spec.is_llm_key
)


def validate_vault_key_name(key_name: str) -> str:
    norm = (key_name or "").strip().lower()
    if norm not in ALLOWED_VAULT_KEY_NAMES:
        raise ValueError(f"Clé API non autorisée dans le coffre-fort : {norm or '<vide>'}")
    return norm


def normalize_secret_input(raw_value: str) -> str:
    """Nettoie une clé API entrante et rejette les caractères de contrôle ou tailles abusives."""
    if not isinstance(raw_value, str):
        raise ValueError("La clé API doit être une chaîne de caractères.")
    if any(ch in raw_value for ch in ("\r", "\n", "\x00")):
        raise ValueError("La clé API contient des caractères de contrôle interdits.")
    cleaned = re.split(r"\s+#", raw_value, maxsplit=1)[0].strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1].strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    if not cleaned:
        raise ValueError("La clé API ne peut pas être vide.")
    if len(cleaned) > _MAX_SECRET_CHARS:
        raise ValueError(f"La clé API dépasse la longueur maximale autorisée ({_MAX_SECRET_CHARS} caractères).")
    return cleaned


def _parse_master_key(raw: str) -> bytes:
    token = raw.strip()
    if not token:
        raise VaultConfigurationError("La clé maîtresse du coffre-fort est vide.")
    if len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token):
        return bytes.fromhex(token)
    padded = token + "=" * (-len(token) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise VaultConfigurationError(
            "CLAIR_VAULT_KEY invalide : fournissez 32 octets encodés en base64url ou 64 caractères hexadécimaux."
        ) from exc
    if len(decoded) != _KEY_BYTES:
        raise VaultConfigurationError(
            f"CLAIR_VAULT_KEY doit décoder exactement {_KEY_BYTES} octets (reçu : {len(decoded)} octets)."
        )
    return decoded


def _default_vault_key_path(app_data_dir: Path) -> Path:
    explicit_file = os.environ.get("CLAIR_VAULT_KEY_FILE", "").strip()
    if explicit_file:
        return Path(explicit_file).expanduser().resolve()
    if _ALLOW_USER_SECRETS_DIR:
        user_secrets_dir = (Path.home() / ".secrets").resolve()
        if user_secrets_dir.is_dir() and os.access(user_secrets_dir, os.W_OK | os.X_OK):
            return user_secrets_dir / "clair_vault.key"
    return app_data_dir.resolve() / ".vault.key"


def load_or_create_master_key(app_data_dir: Path, vault_key_path: Path | None = None) -> bytes:
    """Charge `CLAIR_VAULT_KEY` ou lit/génère de façon atomique (`0600`) le fichier `.vault.key`."""
    env_key = os.environ.get("CLAIR_VAULT_KEY", "").strip()
    if env_key:
        return _parse_master_key(env_key)

    target_path = (vault_key_path or _default_vault_key_path(app_data_dir)).resolve()
    with _KEY_FILE_LOCK:
        if target_path.is_file():
            try:
                if os.name == "posix":
                    mode = target_path.stat().st_mode & 0o777
                    if mode & 0o077:
                        os.chmod(target_path, 0o600)
                raw = target_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise VaultConfigurationError(
                    f"Impossible de lire le fichier de clé maîtresse ({target_path.name})."
                ) from exc
            return _parse_master_key(raw)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_bytes(_KEY_BYTES)
        encoded = base64.urlsafe_b64encode(generated).decode("ascii") + "\n"
        tmp_path = target_path.parent / f".{target_path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
        fd = -1
        try:
            fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if not target_path.exists():
                os.replace(tmp_path, target_path)
            else:
                tmp_path.unlink(missing_ok=True)
                return _parse_master_key(target_path.read_text(encoding="utf-8"))
            if os.name == "posix":
                os.chmod(target_path, 0o600)
        except OSError as exc:
            if fd != -1:
                os.close(fd)
            tmp_path.unlink(missing_ok=True)
            raise VaultConfigurationError(
                f"Impossible d'initialiser la clé maîtresse du coffre-fort ({target_path.name})."
            ) from exc
        return generated


def encrypt_api_key(master_key: bytes, key_name: str, plaintext: str) -> str:
    """Chiffre une clé API nettoyée avec AES-256-GCM et lie le jeton à `key_name` via `AAD`."""
    if len(master_key) != _KEY_BYTES:
        raise VaultConfigurationError("Taille de clé maîtresse AES-256-GCM invalide.")
    norm_name = validate_vault_key_name(key_name)
    cleaned = normalize_secret_input(plaintext)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    aad = f"{_AAD_PREFIX}{norm_name}".encode("utf-8")
    ciphertext = AESGCM(master_key).encrypt(nonce, cleaned.encode("utf-8"), aad)
    nonce_b64 = base64.urlsafe_b64encode(nonce).decode("ascii")
    ct_b64 = base64.urlsafe_b64encode(ciphertext).decode("ascii")
    return f"{_TOKEN_PREFIX}{nonce_b64}:{ct_b64}"


def decrypt_api_key(master_key: bytes, key_name: str, token: str) -> str:
    """Déchiffre et authentifie un jeton `v1:<nonce>:<ct+tag>` lié à `key_name`."""
    if len(master_key) != _KEY_BYTES:
        raise VaultConfigurationError("Taille de clé maîtresse AES-256-GCM invalide.")
    norm_name = validate_vault_key_name(key_name)
    if not isinstance(token, str) or not token.startswith(_TOKEN_PREFIX):
        raise VaultIntegrityError(f"Version de jeton chiffré non reconnue pour {norm_name}.")
    body = token[len(_TOKEN_PREFIX):]
    parts = body.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise VaultIntegrityError(f"Structure de jeton chiffré invalide pour {norm_name}.")
    try:
        nonce = base64.urlsafe_b64decode(parts[0].encode("ascii"))
        ciphertext = base64.urlsafe_b64decode(parts[1].encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise VaultIntegrityError(f"Encodage base64url corrompu pour {norm_name}.") from exc
    if len(nonce) != _NONCE_BYTES or len(ciphertext) < 17:
        raise VaultIntegrityError(f"Dimensions cryptographiques invalides pour {norm_name}.")
    aad = f"{_AAD_PREFIX}{norm_name}".encode("utf-8")
    try:
        plaintext_bytes = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
        plaintext = plaintext_bytes.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError) as exc:
        raise VaultIntegrityError(f"Authentification AES-GCM refusée pour {norm_name}.") from exc
    return normalize_secret_input(plaintext)


class ApiKeyVault:
    """Accès transactionnel et cache mémoire court aux surcharges `api_key_overrides`."""

    def __init__(
        self,
        sessions: sessionmaker,
        app_data_dir: Path,
        vault_key_path: Path | None = None,
    ) -> None:
        self._sessions = sessions
        self._app_data_dir = app_data_dir
        self._vault_key_path = vault_key_path
        self._lock = threading.Lock()
        self._cached_overrides: dict[str, str] | None = None
        self._cached_at: float = 0.0

    def _master_key(self) -> bytes:
        return load_or_create_master_key(self._app_data_dir, self._vault_key_path)

    def invalidate_cache(self) -> None:
        with self._lock:
            self._cached_overrides = None
            self._cached_at = 0.0

    def get_decrypted_overrides(self, force_reload: bool = False) -> dict[str, str]:
        """Retourne `{key_name: secret_clair}` pour l'exécution interne backend uniquement."""
        now_mono = time.monotonic()
        with self._lock:
            if (
                not force_reload
                and self._cached_overrides is not None
                and (now_mono - self._cached_at) < _CACHE_TTL_SECONDS
            ):
                return dict(self._cached_overrides)

        try:
            with self._sessions() as db:
                rows = list(db.scalars(select(ApiKeyOverride)))
        except Exception:
            # Table absente avant bootstrap initial (ex. Settings() nu en test unitaire)
            return {}

        if not rows:
            with self._lock:
                self._cached_overrides = {}
                self._cached_at = now_mono
            return {}

        master_key = self._master_key()
        resolved: dict[str, str] = {}
        for row in rows:
            if row.key_name not in ALLOWED_VAULT_KEY_NAMES:
                continue
            try:
                resolved[row.key_name] = decrypt_api_key(master_key, row.key_name, row.ciphertext)
            except (VaultIntegrityError, ValueError):
                _logger.warning(
                    "Surcharge chiffrée illisible ignorée dans api_key_overrides pour %s",
                    row.key_name,
                )
        with self._lock:
            self._cached_overrides = dict(resolved)
            self._cached_at = now_mono
        return resolved

    def list_override_timestamps(self) -> dict[str, datetime]:
        """Retourne `{key_name: updated_at}` sans déchiffrer aucun secret."""
        with self._sessions() as db:
            rows = list(db.scalars(select(ApiKeyOverride)))
        return {
            row.key_name: row.updated_at
            for row in rows
            if row.key_name in ALLOWED_VAULT_KEY_NAMES
        }

    def upsert_overrides(self, updates: dict[str, str], updated_by_user_id: str | None) -> list[str]:
        """Valide, chiffre et enregistre de façon atomique un lot de clés API externes."""
        if not updates:
            return []
        master_key = self._master_key()
        prepared: list[tuple[str, str]] = []
        for raw_name, raw_secret in updates.items():
            norm_name = validate_vault_key_name(raw_name)
            token = encrypt_api_key(master_key, norm_name, raw_secret)
            prepared.append((norm_name, token))

        stamp_now = now()
        with self._sessions() as db:
            for norm_name, token in prepared:
                existing = db.get(ApiKeyOverride, norm_name)
                if existing is not None:
                    existing.ciphertext = token
                    existing.updated_at = stamp_now
                    existing.updated_by_user_id = updated_by_user_id
                else:
                    db.add(
                        ApiKeyOverride(
                            key_name=norm_name,
                            ciphertext=token,
                            updated_at=stamp_now,
                            updated_by_user_id=updated_by_user_id,
                        )
                    )
            db.commit()

        self.invalidate_cache()
        return [name for name, _ in prepared]

    def delete_override(self, key_name: str) -> bool:
        """Supprime une surcharge du coffre-fort afin de retomber sur la valeur du `.env`."""
        norm_name = validate_vault_key_name(key_name)
        with self._sessions() as db:
            existing = db.get(ApiKeyOverride, norm_name)
            if existing is None:
                return False
            db.delete(existing)
            db.commit()
        self.invalidate_cache()
        return True
