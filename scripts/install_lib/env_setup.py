#!/usr/bin/env python3
"""
Préparation sécurisée du fichier .env pour cLAIr (tchataiperso).

- Crée .env depuis .env.example s'il n'existe pas (permissions 0600 dès la création).
- Génère des secrets cryptographiques aléatoires pour POSTGRES_PASSWORD, SEARXNG_SECRET et HERMES_API_KEY.
- Propose un assistant interactif facultatif (saisie masquée via getpass, aucun secret passé en argv).
- Préserve intégralement un .env existant et complète uniquement les placeholders replace-with-* manquants.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import sys
from pathlib import Path

PLACEHOLDERS = {
    "POSTGRES_PASSWORD": ("replace-with-random-local-password",),
    "SEARXNG_SECRET": ("replace-with-random-searxng-secret",),
    "HERMES_API_KEY": ("replace-with-hermes-gateway-key",),
}

SECRET_BYTES = {
    "POSTGRES_PASSWORD": 24,
    "SEARXNG_SECRET": 32,
    "HERMES_API_KEY": 24,
}

GCP_PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


def _strip_quotes(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value


def _format_env_value(value: str) -> str:
    if any(ch in value for ch in (" ", "#", "'", '"', "$", "\t")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _set_or_append_key(lines: list[str], key_name: str, value: str, newline: str) -> list[str]:
    formatted = f"{key_name}={_format_env_value(value)}"
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, _ = line.partition("=")
        if sep and key.strip() == key_name:
            ending = "\r\n" if line.endswith("\r\n") else "\n"
            lines[idx] = formatted + ending
            return lines
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += newline
    lines.append(formatted + newline)
    return lines


def _prompt_secret(label: str) -> str:
    try:
        return getpass.getpass(f"  {label} (masqué, Entrée pour ignorer) : ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _prompt_text(label: str) -> str:
    try:
        return input(f"  {label} (Entrée pour ignorer) : ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _prompt_yes_no(label: str, default: bool = False) -> bool:
    hint = "[O/n]" if default else "[o/N]"
    try:
        raw = input(f"  {label} {hint} : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if not raw:
        return default
    return raw in ("o", "oui", "y", "yes")


def _create_new_env(template_path: Path, target_path: Path, mode: str, interactive: bool) -> None:
    if not template_path.is_file():
        raise SystemExit(f"Fichier modèle introuvable : {template_path}")

    raw_text = template_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw_text else "\n"
    lines = raw_text.splitlines(keepends=True)

    # Secrets internes générés aléatoirement.
    for key_name, byte_len in SECRET_BYTES.items():
        lines = _set_or_append_key(lines, key_name, secrets.token_hex(byte_len), newline)

    updates: dict[str, str] = {}
    if interactive:
        print("\n  Configuration initiale des clés API (toutes sont facultatives — modifiables plus tard dans .env) :")
        if _prompt_yes_no("Souhaitez-vous saisir vos clés API maintenant ?", default=False):
            llm_key = _prompt_secret("Clé OpenRouter / LLM (LLM_API_KEY)")
            if llm_key:
                updates["LLM_API_KEY"] = llm_key

            mistral_key = _prompt_secret("Clé Mistral — OCR PDF/images & dictée Voxtral (MISTRAL_API_KEY)")
            if mistral_key:
                updates["MISTRAL_API_KEY"] = mistral_key

            google_key = _prompt_secret("Clé Google Gemini — Voix TTS & Deep Research (GOOGLE_API_KEY)")
            if google_key:
                updates["GOOGLE_API_KEY"] = google_key

            gcp_project = _prompt_text("ID de projet Google Cloud Vertex AI (GOOGLE_CLOUD_PROJECT)")
            if gcp_project:
                updates["GOOGLE_CLOUD_PROJECT"] = gcp_project

            if _prompt_yes_no("Configurer aussi les clés facultatives (Brave, Ideogram, EODHD Finance, ElevenLabs) ?", default=False):
                for key_name, label in (
                    ("BRAVE_API_KEY", "Clé Brave Search (BRAVE_API_KEY)"),
                    ("IDEOGRAM_API_KEY", "Clé Ideogram Images (IDEOGRAM_API_KEY)"),
                    ("EOD_HISTORICAL_DATA_KEY", "Clé EODHD Marchés Financiers (EOD_HISTORICAL_DATA_KEY)"),
                    ("ELEVEN_LABS_KEY", "Clé ElevenLabs Effets sonores (ELEVEN_LABS_KEY)"),
                ):
                    val = _prompt_secret(label)
                    if val:
                        updates[key_name] = val

    # Nettoyer le placeholder GOOGLE_API_KEY si l'utilisateur ne l'a pas saisie.
    if "GOOGLE_API_KEY" not in updates:
        updates["GOOGLE_API_KEY"] = ""

    has_real_ai = bool(updates.get("LLM_API_KEY") or updates.get("GOOGLE_CLOUD_PROJECT"))
    updates["DEMO_MODE"] = "false" if has_real_ai else "true"

    if updates.get("GOOGLE_CLOUD_PROJECT"):
        updates["GOOGLE_CLOUD_MODE"] = "vertex_oauth"
        updates["GOOGLE_APPLICATION_CREDENTIALS"] = "" if mode == "local" else "/run/secrets/gcp-adc.json"
    else:
        updates["GOOGLE_CLOUD_MODE"] = "auto"
        if mode == "local":
            updates["GOOGLE_APPLICATION_CREDENTIALS"] = ""

    for key_name, value in updates.items():
        lines = _set_or_append_key(lines, key_name, value, newline)

    target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))

    ai_status = "mode réel activé" if has_real_ai else "mode démo activé (aucune clé LLM saisie)"
    print(f"  ✓ {target_path} créé avec permissions 600 ({ai_status}, secrets locaux générés).")


def _ensure_existing_env(target_path: Path) -> None:
    raw = target_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.splitlines(keepends=True)
    changed = False

    for key_name, byte_len in SECRET_BYTES.items():
        placeholders = PLACEHOLDERS.get(key_name, ())
        found = False
        for idx, line in enumerate(lines):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            key, sep, val = line.partition("=")
            if sep and key.strip() == key_name:
                found = True
                clean = _strip_quotes(val)
                if not clean or clean in placeholders:
                    ending = "\r\n" if line.endswith("\r\n") else "\n"
                    lines[idx] = f"{key_name}={secrets.token_hex(byte_len)}{ending}"
                    changed = True
                break
        if not found:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            lines.append(f"{key_name}={secrets.token_hex(byte_len)}{newline}")
            changed = True

    if changed:
        target_path.write_text("".join(lines), encoding="utf-8")
        print(f"  ✓ {target_path} existant conservé (secrets internes manquants complétés).")
    else:
        print(f"  ✓ {target_path} existant conservé sans modification.")

    try:
        current_mode = target_path.stat().st_mode & 0o777
        if current_mode & 0o077:
            os.chmod(target_path, 0o600)
            print("  ✓ Permissions de .env restreintes à 600.")
    except OSError:
        pass


def _read_gcp_project(target_path: Path) -> str:
    if not target_path.is_file():
        return ""
    project = ""
    for line in target_path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep and key.strip() == "GOOGLE_CLOUD_PROJECT":
            candidate = _strip_quotes(val)
            if candidate and GCP_PROJECT_RE.match(candidate):
                project = candidate
    return project


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialise ou complète le fichier .env de cLAIr.")
    parser.add_argument("--repo-dir", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--env-file", type=Path, default=None, help="Chemin cible du fichier .env.")
    parser.add_argument("--mode", choices=("docker", "local", "all"), default="docker")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--get-gcp-project", action="store_true", help="Affiche uniquement GOOGLE_CLOUD_PROJECT s'il est valide.")
    args = parser.parse_args()

    template_path = args.repo_dir / ".env.example"
    if args.env_file is not None:
        target_path = args.env_file
    elif os.environ.get("CLAIR_ENV_FILE"):
        target_path = Path(os.environ["CLAIR_ENV_FILE"])
    else:
        target_path = Path.home() / ".secrets" / ".env"

    if args.get_gcp_project:
        print(_read_gcp_project(target_path))
        return 0

    if target_path.exists():
        _ensure_existing_env(target_path)
    else:
        _create_new_env(template_path, target_path, mode=args.mode, interactive=args.interactive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
