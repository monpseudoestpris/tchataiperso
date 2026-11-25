"""Sondeur léger et sans facturation pour vérifier la validité d'une clé API fournisseur.

Garanties de sécurité :
- Timeout réseau strict de 5 s (`connect=3s`).
- Aucune journalisation ni retour d'URL brute, d'en-tête ou de fragment de clé.
- Les sondes interrogent uniquement des endpoints de métadonnées non facturés (`$0`).
"""

from __future__ import annotations

import httpx

from .api_key_vault import normalize_secret_input, validate_vault_key_name
from .config import Settings, _clean_api_key


_PROBE_TIMEOUT = httpx.Timeout(5.0, connect=3.0, pool=3.0)


def _status_verdict(status_code: int, *, accept_validation_4xx: bool = False) -> tuple[bool, str]:
    if 200 <= status_code < 300:
        return True, "Connexion vérifiée : clé acceptée par le fournisseur."
    if accept_validation_4xx and status_code in (400, 422):
        return True, "Connexion vérifiée : authentification acceptée par le fournisseur."
    if status_code in (401, 403):
        return False, f"Clé refusée par le fournisseur (HTTP {status_code})."
    if status_code == 402:
        return False, "Clé reconnue, mais crédit ou abonnement épuisé (HTTP 402)."
    if status_code == 429:
        return True, "Clé reconnue (limite de requêtes temporairement atteinte, HTTP 429)."
    if status_code >= 500:
        return False, f"Fournisseur temporairement indisponible (HTTP {status_code})."
    return False, f"Réponse inattendue du fournisseur (HTTP {status_code})."


async def probe_provider_api_key(
    settings: Settings,
    key_name: str,
    candidate_value: str | None = None,
) -> tuple[bool, str]:
    """Teste une clé candidate (en mémoire) ou la clé active actuelle sans jamais l'exposer."""
    norm_name = validate_vault_key_name(key_name)
    if candidate_value is not None and candidate_value.strip():
        secret = normalize_secret_input(candidate_value)
    else:
        settings.refresh_from_env_file()
        secret = _clean_api_key(getattr(settings, norm_name, None))
        if not secret:
            return False, "Aucune clé active configurée pour ce fournisseur."

    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT, follow_redirects=False) as client:
            if norm_name == "llm_api_key":
                base_url = (settings.llm_base_url or "https://openrouter.ai/api/v1").strip().rstrip("/")
                probe_url = f"{base_url}/auth/key" if "openrouter.ai" in base_url.lower() else f"{base_url}/models"
                resp = await client.get(probe_url, headers={"Authorization": f"Bearer {secret}"})
                return _status_verdict(resp.status_code)

            if norm_name == "google_api_key":
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"pageSize": "1"},
                    headers={"x-goog-api-key": secret},
                )
                return _status_verdict(resp.status_code)

            if norm_name == "vertex_api_key":
                resp = await client.post(
                    "https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash:countTokens",
                    headers={"x-goog-api-key": secret, "Content-Type": "application/json"},
                    json={"contents": [{"role": "user", "parts": [{"text": "ok"}]}]},
                )
                return _status_verdict(resp.status_code)

            if norm_name == "mistral_api_key":
                resp = await client.get(
                    "https://api.mistral.ai/v1/models",
                    headers={"Authorization": f"Bearer {secret}"},
                )
                return _status_verdict(resp.status_code)

            if norm_name == "ideogram_api_key":
                # Corps vide : l'authentification rejette une clé invalide en 401/403 avant toute génération,
                # et répond 400/422 sans aucun crédit débité lorsque la clé est valide.
                resp = await client.post(
                    "https://api.ideogram.ai/v1/ideogram-v3/generate",
                    headers={"Api-Key": secret, "Content-Type": "application/json"},
                    json={},
                )
                return _status_verdict(resp.status_code, accept_validation_4xx=True)

            if norm_name == "eleven_labs_key":
                resp = await client.get(
                    "https://api.elevenlabs.io/v1/user",
                    headers={"xi-api-key": secret},
                )
                return _status_verdict(resp.status_code)

            if norm_name == "eod_historical_data_key":
                resp = await client.get(
                    "https://eodhd.com/api/user",
                    params={"api_token": secret, "fmt": "json"},
                )
                return _status_verdict(resp.status_code)

            if norm_name == "brave_api_key":
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": "clair", "count": "1"},
                    headers={"X-Subscription-Token": secret, "Accept": "application/json"},
                )
                return _status_verdict(resp.status_code)
    except httpx.TimeoutException:
        return False, "Délai d'attente dépassé (5 s) en contactant le fournisseur."
    except httpx.HTTPError:
        return False, "Impossible de joindre le fournisseur distant (erreur réseau)."

    return False, "Fournisseur non pris en charge par le testeur."
