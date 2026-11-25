"""Routage unifié des modèles Google vers Google Cloud (Vertex AI OAuth2/ADC, Vertex API Key, Gemini Developer API)."""

from __future__ import annotations

import asyncio
import base64
import datetime
import json
import logging
import re
import threading
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

import google.auth
import google.auth.exceptions
import google.auth.transport
import httpx

_logger = logging.getLogger("uvicorn.error")

_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,29}$")
_LOCATION_RE = re.compile(r"^[a-z0-9-]{2,40}$")
_MODEL_BARE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_ALLOWED_MODES = {"auto", "vertex_oauth", "vertex_api_key", "gemini_api", "disabled"}
_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
_GEMINI_NATIVE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_MAX_IMAGE_BYTES = 10 * 1024 * 1024

_OPENROUTER_ONLY_FIELDS = {
    "reasoning",
    "include_reasoning",
    "min_p",
    "top_a",
    "repetition_penalty",
    "verbosity",
    "top_k",
    "logit_bias",
    "transforms",
    "route",
    "provider",
    "models",
}

_AUTH_LOCK = threading.Lock()
_AUTH_CACHE: dict[tuple[str, str], tuple[Any, str]] = {}


class ProviderError(Exception):
    """A message suitable for displaying to the user, without provider details."""


def clean_secret(value: Any) -> str:
    if hasattr(value, "get_secret_value"):
        raw = value.get_secret_value()
    elif isinstance(value, str):
        raw = value
    else:
        return ""
    cleaned = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1].strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    return cleaned


def _extract_safe_error_detail(response: httpx.Response) -> str:
    """Extract a short, redacted error message from an HTTP error response if available."""
    try:
        data = response.json()
    except Exception:
        return ""
    msg = ""
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or "")
        elif isinstance(err, str):
            msg = err
        if not msg:
            msg = str(data.get("message") or "")
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        err = data[0].get("error")
        if isinstance(err, dict):
            msg = str(err.get("message") or "")
    msg = " ".join(msg.split()).strip()
    if not msg:
        return ""
    msg = re.sub(r"(Bearer\s+[A-Za-z0-9._-]+|ya29\.[A-Za-z0-9._-]+|AIza[0-9A-Za-z_-]+)", "[REDACTED]", msg)
    return msg[:220]


def check_response(response: httpx.Response, provider: str) -> None:
    if response.is_success:
        return
    if response.status_code in (401, 403):
        message = "clé API refusée ou accès non autorisé"
    elif response.status_code == 402:
        message = "crédit insuffisant"
    elif response.status_code == 429:
        message = "limite de requêtes atteinte ; réessayez plus tard"
    elif response.status_code in (400, 404, 422):
        message = "requête ou modèle non pris en charge ; vérifiez la configuration"
        detail = _extract_safe_error_detail(response)
        if detail:
            raise ProviderError(f"{provider} : {message} (HTTP {response.status_code} — {detail}).")
    elif response.status_code >= 500:
        message = "service temporairement indisponible"
    else:
        message = "requête refusée"
    raise ProviderError(f"{provider} : {message} (HTTP {response.status_code}).")


def json_body(response: httpx.Response, provider: str) -> dict[str, Any]:
    try:
        value = response.json()
    except (ValueError, UnicodeDecodeError):
        raise ProviderError(f"{provider} a renvoyé une réponse illisible.") from None
    if not isinstance(value, dict):
        raise ProviderError(f"{provider} a renvoyé une réponse inattendue.")
    return value


def detect_image_mime(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def image_signature_matches(content: bytes, mime_type: str) -> bool:
    return detect_image_mime(content) == mime_type


def clear_google_auth_cache() -> None:
    with _AUTH_LOCK:
        _AUTH_CACHE.clear()


class _HttpxAuthResponse(google.auth.transport.Response):
    def __init__(self, status: int, headers: httpx.Headers, data: bytes) -> None:
        self._status = int(status)
        self._headers = {k.lower(): v for k, v in headers.items()}
        self._data = data

    @property
    def status(self) -> int:
        return self._status

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def data(self) -> bytes:
        return self._data


class _HttpxAuthRequest(google.auth.transport.Request):
    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> _HttpxAuthResponse:
        effective_timeout = float(timeout) if timeout is not None else 15.0
        try:
            with httpx.Client(timeout=effective_timeout, follow_redirects=False) as client:
                resp = client.request(
                    method=method,
                    url=url,
                    content=body,
                    headers=headers,
                )
            return _HttpxAuthResponse(resp.status_code, resp.headers, resp.content)
        except httpx.HTTPError as exc:
            raise google.auth.exceptions.TransportError(
                f"Erreur réseau OAuth2 Google Cloud : {type(exc).__name__}"
            ) from None


def is_google_model(model: str | None) -> bool:
    if not isinstance(model, str):
        return False
    m = model.strip().lower()
    if not m:
        return False
    return (
        m.startswith("google/")
        or m.startswith("gemini-")
        or m.startswith("imagen-")
        or m.startswith("gemma-")
        or m.startswith("publishers/google/models/")
        or m.startswith("models/gemini-")
        or m.startswith("models/imagen-")
        or m.startswith("models/gemma-")
    )


def resolve_google_cloud_mode(settings: Any) -> str | None:
    if settings is None or getattr(settings, "demo_mode", False):
        return None
    refresh = getattr(settings, "refresh_from_env_file", None)
    if callable(refresh):
        refresh()
    if hasattr(settings, "active_google_cloud_mode"):
        val = getattr(settings, "active_google_cloud_mode")
        return val if val in {"vertex_oauth", "vertex_api_key", "gemini_api"} else None
    mode = str(getattr(settings, "google_cloud_mode", "auto") or "auto").strip().lower()
    if mode == "disabled":
        return None
    if mode in {"vertex_oauth", "vertex_api_key", "gemini_api"}:
        return mode
    if mode == "auto":
        if str(getattr(settings, "google_cloud_project", "") or "").strip():
            return "vertex_oauth"
        if clean_secret(getattr(settings, "vertex_api_key", None)):
            return "vertex_api_key"
    return None


def _has_google_cloud_credentials(settings: Any, mode: str | None) -> bool:
    if mode == "vertex_oauth":
        project = str(getattr(settings, "google_cloud_project", "") or "").strip()
        cred_path = str(getattr(settings, "google_application_credentials", "") or "").strip()
        return bool(project or cred_path or str(getattr(settings, "google_cloud_mode", "")).strip().lower() == "vertex_oauth")
    if mode == "vertex_api_key":
        return bool(clean_secret(getattr(settings, "vertex_api_key", None)))
    if mode == "gemini_api":
        return bool(
            clean_secret(getattr(settings, "google_api_key", None))
            or clean_secret(getattr(settings, "gemini_api_key", None))
        )
    return False


def should_route_to_google_cloud(settings: Any, model: str | None) -> bool:
    return bool(
        model
        and is_google_model(model)
        and not getattr(settings, "demo_mode", False)
        and resolve_google_cloud_mode(settings) is not None
    )


def has_llm_access(settings: Any, model: str | None = None) -> bool:
    if settings is None or getattr(settings, "demo_mode", False):
        return False
    refresh = getattr(settings, "refresh_from_env_file", None)
    if callable(refresh):
        refresh()
    has_openrouter = bool(clean_secret(getattr(settings, "llm_api_key", None)))
    gc_mode = resolve_google_cloud_mode(settings)
    has_gc = _has_google_cloud_credentials(settings, gc_mode)

    if model is None:
        return has_openrouter or has_gc
    if is_google_model(model):
        if has_gc:
            return True
        if gc_mode is None:
            return has_openrouter
        return has_openrouter and bool(getattr(settings, "google_cloud_fallback_openrouter", False))
    return has_openrouter


def can_fallback_to_model(settings: Any, primary_model: str, fallback_model: str) -> bool:
    fb = (fallback_model or "").strip()
    if not fb or fb == (primary_model or "").strip():
        return False
    if should_route_to_google_cloud(settings, primary_model):
        if not getattr(settings, "google_cloud_fallback_openrouter", False) and not is_google_model(fb):
            return False
    return True


def _load_model_map(settings: Any) -> dict[str, str]:
    raw = str(getattr(settings, "google_cloud_model_map", "") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, str] = {}
    for k, v in parsed.items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
            result[k.strip()] = v.strip()
    return result


def normalize_google_model_id(
    model: str,
    *,
    settings: Any = None,
    for_vertex_openapi: bool = False,
) -> str:
    candidate = (model or "").strip()
    if not candidate:
        raise ProviderError("Identifiant de modèle Google vide ou invalide.")

    model_map = _load_model_map(settings) if settings is not None else {}
    if candidate in model_map:
        candidate = model_map[candidate]
    else:
        lower_map = {k.lower(): v for k, v in model_map.items()}
        if candidate.lower() in lower_map:
            candidate = lower_map[candidate.lower()]

    if ":" in candidate:
        candidate = candidate.split(":", 1)[0]

    lower = candidate.lower()
    if lower.startswith("publishers/google/models/"):
        candidate = candidate[len("publishers/google/models/"):]
    elif lower.startswith("models/"):
        candidate = candidate[len("models/"):]
    elif lower.startswith("google/"):
        candidate = candidate[len("google/"):]

    bare = candidate.strip()
    if ".." in bare or "/" in bare or not _MODEL_BARE_RE.fullmatch(bare):
        raise ProviderError("Identifiant de modèle Google invalide.")

    return f"google/{bare}" if for_vertex_openapi else bare


def _validate_location(settings: Any) -> str:
    loc = str(getattr(settings, "google_cloud_location", "global") or "global").strip().lower()
    if not loc:
        loc = "global"
    if not _LOCATION_RE.fullmatch(loc):
        raise ProviderError("Région Google Cloud invalide.")
    return loc


def vertex_api_host(location: str) -> str:
    loc = (location or "global").strip().lower() or "global"
    if not _LOCATION_RE.fullmatch(loc):
        raise ProviderError("Région Google Cloud invalide.")
    if loc == "global":
        return "https://aiplatform.googleapis.com"
    return f"https://{loc}-aiplatform.googleapis.com"


def _get_oauth_token_and_project_sync(cred_path: str, project_setting: str) -> tuple[str, str]:
    clean_cred_path = (cred_path or "").strip()
    if any(ch in clean_cred_path for ch in ("\r", "\n", "\x00")):
        raise ProviderError("Chemin GOOGLE_APPLICATION_CREDENTIALS invalide.")

    clean_project = (project_setting or "").strip()
    if clean_project and not _PROJECT_ID_RE.fullmatch(clean_project):
        raise ProviderError("Identifiant GOOGLE_CLOUD_PROJECT invalide.")

    cache_key = (clean_cred_path, clean_project)
    with _AUTH_LOCK:
        cached = _AUTH_CACHE.get(cache_key)
        if cached is None:
            try:
                if clean_cred_path:
                    resolved_file = Path(clean_cred_path).expanduser()
                    if not resolved_file.is_file():
                        raise ProviderError(
                            "Le fichier GOOGLE_APPLICATION_CREDENTIALS est introuvable."
                        )
                    credentials, detected_project = google.auth.load_credentials_from_file(
                        str(resolved_file), scopes=[_CLOUD_SCOPE]
                    )
                else:
                    credentials, detected_project = google.auth.default(scopes=[_CLOUD_SCOPE])
            except ProviderError:
                raise
            except (google.auth.exceptions.GoogleAuthError, OSError, ValueError):
                raise ProviderError(
                    "Authentification Google Cloud impossible ; configurez GOOGLE_APPLICATION_CREDENTIALS "
                    "ou exécutez `gcloud auth application-default login`."
                ) from None

            resolved_project = clean_project or str(detected_project or "").strip()
            if not resolved_project or not _PROJECT_ID_RE.fullmatch(resolved_project):
                raise ProviderError(
                    "Configurez GOOGLE_CLOUD_PROJECT (ID de projet GCP valide) pour utiliser Vertex AI."
                )
            _AUTH_CACHE[cache_key] = (credentials, resolved_project)
        else:
            credentials, resolved_project = cached

        needs_refresh = not getattr(credentials, "token", None) or not getattr(credentials, "valid", False)
        expiry = getattr(credentials, "expiry", None)
        if not needs_refresh and expiry is not None:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            exp_utc = expiry if expiry.tzinfo is not None else expiry.replace(tzinfo=datetime.timezone.utc)
            if (exp_utc - now_utc).total_seconds() < 300:
                needs_refresh = True

        if needs_refresh:
            try:
                credentials.refresh(_HttpxAuthRequest())
            except google.auth.exceptions.GoogleAuthError:
                _AUTH_CACHE.pop(cache_key, None)
                raise ProviderError(
                    "Échec du rafraîchissement du jeton OAuth2 Google Cloud ; vérifiez vos identifiants GCP."
                ) from None

        token = str(getattr(credentials, "token", "") or "").strip()
        if not token:
            _AUTH_CACHE.pop(cache_key, None)
            raise ProviderError("Jeton OAuth2 Google Cloud vide ou indisponible.")
        return token, resolved_project


async def get_google_cloud_access_token(settings: Any) -> tuple[str, str]:
    cred_path = str(getattr(settings, "google_application_credentials", "") or "").strip()
    project_setting = str(getattr(settings, "google_cloud_project", "") or "").strip()
    return await asyncio.to_thread(_get_oauth_token_and_project_sync, cred_path, project_setting)


def _strip_cache_control(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            cleaned.append(msg)
            continue
        copied = dict(msg)
        content = copied.get("content")
        if isinstance(content, list):
            new_parts: list[Any] = []
            for part in content:
                if isinstance(part, dict) and "cache_control" in part:
                    new_parts.append({k: v for k, v in part.items() if k != "cache_control"})
                else:
                    new_parts.append(part)
            copied["content"] = new_parts
        cleaned.append(copied)
    return cleaned


def _is_mandatory_reasoning_gemini(bare_model: str) -> bool:
    low = bare_model.lower()
    return (
        "gemini-2.5-pro" in low
        or "gemini-3" in low
        or "gemini-4" in low
    )


def _max_output_tokens_for_google_model(bare_model: str) -> int:
    """Return the maximum output tokens accepted by Google Cloud / Vertex AI for the given model."""
    low = (bare_model or "").strip().lower()
    if low.startswith("gemini-1.5") or low.startswith("gemini-2.0"):
        return 8192
    return 65536


def adapt_openai_payload_for_google(
    payload: dict[str, Any],
    *,
    mode: str,
    settings: Any,
) -> dict[str, Any]:
    adapted = dict(payload)
    raw_model = str(adapted.get("model") or "")
    bare_model = normalize_google_model_id(raw_model, settings=settings, for_vertex_openapi=False)
    adapted["model"] = (
        f"google/{bare_model}" if mode == "vertex_oauth" else bare_model
    )

    max_cap = _max_output_tokens_for_google_model(bare_model)
    for tok_key in ("max_tokens", "max_completion_tokens"):
        tok_val = adapted.get(tok_key)
        if isinstance(tok_val, int) and not isinstance(tok_val, bool) and tok_val > max_cap:
            adapted[tok_key] = max_cap

    if isinstance(adapted.get("messages"), list):
        adapted["messages"] = _strip_cache_control(adapted["messages"])

    raw_reasoning = adapted.get("reasoning")
    if adapted.get("reasoning_effort") is None and isinstance(raw_reasoning, dict):
        if raw_reasoning.get("enabled") is False:
            adapted["reasoning_effort"] = "none"
        elif isinstance(raw_reasoning.get("effort"), str) and raw_reasoning["effort"].strip():
            adapted["reasoning_effort"] = raw_reasoning["effort"].strip().lower()

    effort = adapted.get("reasoning_effort")
    if isinstance(effort, str):
        eff_norm = effort.strip().lower()
        if eff_norm == "none" and _is_mandatory_reasoning_gemini(bare_model):
            adapted.pop("reasoning_effort", None)
        elif eff_norm in {"none", "minimal", "low", "medium", "high"}:
            adapted["reasoning_effort"] = eff_norm
        else:
            adapted.pop("reasoning_effort", None)

    for key in _OPENROUTER_ONLY_FIELDS:
        if key == "top_k" and mode == "vertex_api_key":
            continue
        adapted.pop(key, None)

    if not adapted.get("stream"):
        adapted.pop("stream_options", None)

    return adapted


def _sanitize_gemini_schema(schema: Any) -> Any:
    if isinstance(schema, list):
        return [_sanitize_gemini_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    cleaned: dict[str, Any] = {}
    for key, val in schema.items():
        if key in ("$schema", "additionalProperties", "$id"):
            continue
        cleaned[key] = _sanitize_gemini_schema(val)
    return cleaned


def _convert_openai_content_parts(content: Any) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    if isinstance(content, str):
        if content:
            parts.append({"text": content})
        return parts
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                if item:
                    parts.append({"text": item})
                continue
            if not isinstance(item, dict):
                continue
            itype = str(item.get("type") or "").lower()
            if itype == "text":
                text = str(item.get("text") or "")
                if text:
                    parts.append({"text": text})
            elif itype == "image_url":
                img_obj = item.get("image_url")
                url = img_obj.get("url", "") if isinstance(img_obj, dict) else str(img_obj or "")
                if url.startswith("data:"):
                    m = re.match(r"^data:([^;,]+);base64,(.+)$", url, re.DOTALL | re.IGNORECASE)
                    if m:
                        mime = m.group(1).strip()
                        b64_data = re.sub(r"\s+", "", m.group(2))
                        parts.append({"inlineData": {"mimeType": mime, "data": b64_data}})
                elif url:
                    parts.append({"fileData": {"fileUri": url, "mimeType": "image/jpeg"}})
    return parts


def openai_to_gemini_native_request(payload: dict[str, Any], *, bare_model: str = "") -> dict[str, Any]:
    messages = payload.get("messages") or []
    system_parts: list[dict[str, Any]] = []
    contents: list[dict[str, Any]] = []
    tool_id_to_name: dict[str, str] = {}

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "user").lower()
        parts = _convert_openai_content_parts(msg.get("content"))

        if role in ("system", "developer"):
            system_parts.extend(parts)
            continue

        if role == "assistant":
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    continue
                tc_id = str(tc.get("id") or "")
                fn = tc.get("function") or {}
                fn_name = str(fn.get("name") or "").strip()
                if tc_id and fn_name:
                    tool_id_to_name[tc_id] = fn_name
                raw_args = fn.get("arguments")
                if isinstance(raw_args, str):
                    try:
                        parsed_args = json.loads(raw_args) if raw_args.strip() else {}
                    except ValueError:
                        parsed_args = {}
                elif isinstance(raw_args, dict):
                    parsed_args = raw_args
                else:
                    parsed_args = {}
                if fn_name:
                    fc_part: dict[str, Any] = {
                        "functionCall": {
                            "name": fn_name,
                            "args": parsed_args if isinstance(parsed_args, dict) else {},
                        }
                    }
                    sig = tc.get("thought_signature") or (
                        (tc.get("extra_content") or {}).get("google") or {}
                    ).get("thought_signature")
                    if isinstance(sig, str) and sig:
                        fc_part["thoughtSignature"] = sig
                    parts.append(fc_part)
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        if role == "tool":
            tc_id = str(msg.get("tool_call_id") or "")
            fn_name = str(msg.get("name") or tool_id_to_name.get(tc_id) or "tool")
            raw_content = msg.get("content")
            if isinstance(raw_content, dict):
                resp_obj = raw_content
            else:
                text_val = raw_content if isinstance(raw_content, str) else json.dumps(raw_content, ensure_ascii=False)
                try:
                    decoded = json.loads(text_val)
                    resp_obj = decoded if isinstance(decoded, dict) else {"result": decoded}
                except ValueError:
                    resp_obj = {"result": text_val}
            fn_part = {"functionResponse": {"name": fn_name, "response": resp_obj}}
            if contents and contents[-1].get("role") == "user" and all(
                "functionResponse" in p for p in contents[-1].get("parts", [])
            ):
                contents[-1]["parts"].append(fn_part)
            else:
                contents.append({"role": "user", "parts": [fn_part]})
            continue

        contents.append({"role": "user", "parts": parts or [{"text": ""}]})

    native: dict[str, Any] = {"contents": contents}
    if system_parts:
        native["systemInstruction"] = {"parts": system_parts}

    gen_cfg: dict[str, Any] = {}
    if payload.get("temperature") is not None:
        gen_cfg["temperature"] = payload["temperature"]
    if payload.get("top_p") is not None:
        gen_cfg["topP"] = payload["top_p"]
    if payload.get("top_k") is not None:
        gen_cfg["topK"] = payload["top_k"]
    max_tok = payload.get("max_tokens") or payload.get("max_completion_tokens")
    if max_tok is not None:
        gen_cfg["maxOutputTokens"] = max_tok
    if payload.get("seed") is not None:
        gen_cfg["seed"] = payload["seed"]
    if payload.get("presence_penalty") is not None:
        gen_cfg["presencePenalty"] = payload["presence_penalty"]
    if payload.get("frequency_penalty") is not None:
        gen_cfg["frequencyPenalty"] = payload["frequency_penalty"]
    if payload.get("stop") is not None:
        stop_val = payload["stop"]
        gen_cfg["stopSequences"] = [stop_val] if isinstance(stop_val, str) else list(stop_val)

    resp_fmt = payload.get("response_format")
    if isinstance(resp_fmt, dict):
        fmt_type = str(resp_fmt.get("type") or "").lower()
        if fmt_type == "json_object":
            gen_cfg["responseMimeType"] = "application/json"
        elif fmt_type == "json_schema":
            gen_cfg["responseMimeType"] = "application/json"
            schema_obj = (resp_fmt.get("json_schema") or {}).get("schema")
            if isinstance(schema_obj, dict):
                gen_cfg["responseSchema"] = _sanitize_gemini_schema(schema_obj)

    effort = payload.get("reasoning_effort")
    if effort is None and isinstance(payload.get("reasoning"), dict):
        r = payload["reasoning"]
        if r.get("enabled") is False:
            effort = "none"
        elif isinstance(r.get("effort"), str):
            effort = r["effort"]

    if isinstance(effort, str) and effort.strip():
        eff = effort.strip().lower()
        model_low = bare_model.lower()
        if "gemini-2.5" in model_low:
            budget_map = {"none": 0, "minimal": 512, "low": 1024, "medium": 8192, "high": 24576}
            if eff == "none" and "pro" in model_low:
                pass
            elif eff in budget_map:
                gen_cfg["thinkingConfig"] = {"thinkingBudget": budget_map[eff]}
        elif ("gemini-3" in model_low or "gemini-4" in model_low) and eff in {"minimal", "low", "medium", "high"}:
            gen_cfg["thinkingConfig"] = {"thinkingLevel": eff.upper()}

    if gen_cfg:
        native["generationConfig"] = gen_cfg

    tools = payload.get("tools")
    if isinstance(tools, list) and tools:
        decls = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function") if tool.get("type") == "function" else tool
            if not isinstance(fn, dict) or not fn.get("name"):
                continue
            decl: dict[str, Any] = {
                "name": str(fn["name"]),
                "description": str(fn.get("description") or ""),
            }
            if isinstance(fn.get("parameters"), dict):
                decl["parameters"] = _sanitize_gemini_schema(fn["parameters"])
            decls.append(decl)
        if decls:
            native["tools"] = [{"functionDeclarations": decls}]

    tool_choice = payload.get("tool_choice")
    if tool_choice is not None and "tools" in native:
        if tool_choice == "auto":
            native["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        elif tool_choice == "none":
            native["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
        elif tool_choice == "required":
            native["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}
        elif isinstance(tool_choice, dict):
            fn_name = (tool_choice.get("function") or {}).get("name")
            if isinstance(fn_name, str) and fn_name.strip():
                native["toolConfig"] = {
                    "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [fn_name.strip()]}
                }

    return native


def _map_gemini_finish_reason(reason: str | None, *, has_tool_calls: bool = False) -> str | None:
    if not reason:
        return None
    norm = str(reason).upper()
    if norm == "STOP":
        return "tool_calls" if has_tool_calls else "stop"
    if norm == "MAX_TOKENS":
        return "length"
    if norm in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
        return "content_filter"
    return "stop"


def _extract_gemini_usage(native: dict[str, Any]) -> dict[str, int] | None:
    meta = native.get("usageMetadata")
    if not isinstance(meta, dict):
        return None
    prompt_t = int(meta.get("promptTokenCount") or 0)
    comp_t = int(meta.get("candidatesTokenCount") or 0)
    total_t = int(meta.get("totalTokenCount") or (prompt_t + comp_t))
    return {
        "prompt_tokens": prompt_t,
        "completion_tokens": comp_t,
        "total_tokens": total_t,
    }


def gemini_native_to_openai_dict(native: dict[str, Any], model: str) -> dict[str, Any]:
    candidates = native.get("candidates") or []
    cand = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    parts = ((cand.get("content") or {}).get("parts") or []) if isinstance(cand, dict) else []

    text_parts: list[str] = []
    thought_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("thought") is True and isinstance(part.get("text"), str):
            thought_parts.append(part["text"])
        elif isinstance(part.get("text"), str):
            text_parts.append(part["text"])
        if isinstance(part.get("functionCall"), dict):
            fc = part["functionCall"]
            idx = len(tool_calls)
            tc_entry: dict[str, Any] = {
                "id": f"call_{idx}",
                "type": "function",
                "function": {
                    "name": str(fc.get("name") or ""),
                    "arguments": json.dumps(fc.get("args") or {}, ensure_ascii=False),
                },
            }
            thought_sig = part.get("thoughtSignature")
            if isinstance(thought_sig, str) and thought_sig:
                tc_entry["thought_signature"] = thought_sig
                tc_entry["extra_content"] = {"google": {"thought_signature": thought_sig}}
            tool_calls.append(tc_entry)

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "".join(text_parts),
    }
    if thought_parts:
        message["reasoning_content"] = "".join(thought_parts)
    if tool_calls:
        message["tool_calls"] = tool_calls

    finish_reason = _map_gemini_finish_reason(
        cand.get("finishReason"), has_tool_calls=bool(tool_calls)
    ) or "stop"

    result: dict[str, Any] = {
        "id": native.get("responseId") or "gemini-native",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
    }
    usage = _extract_gemini_usage(native)
    if usage:
        result["usage"] = usage
    return result


async def iter_gemini_sse_as_openai_data(
    response: httpx.Response,
    model: str,
) -> AsyncIterator[str]:
    tool_idx = 0
    saw_tool_calls = False
    saw_finish = False
    event: list[str] = []

    def _convert_event(raw_json: str) -> str | None:
        nonlocal tool_idx, saw_tool_calls, saw_finish
        stripped = raw_json.strip()
        if not stripped:
            return None
        if stripped == "[DONE]":
            saw_finish = True
            return "[DONE]"
        try:
            native = json.loads(stripped)
        except ValueError:
            raise ProviderError("Google Cloud (Vertex AI) a renvoyé un flux invalide.") from None
        if not isinstance(native, dict):
            return None
        if isinstance(native.get("error"), dict):
            raise ProviderError("Google Cloud (Vertex AI) a interrompu la génération.")

        candidates = native.get("candidates") or []
        cand = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        parts = ((cand.get("content") or {}).get("parts") or []) if isinstance(cand, dict) else []

        text_parts: list[str] = []
        thought_parts: list[str] = []
        delta_tools: list[dict[str, Any]] = []

        for part in parts:
            if not isinstance(part, dict):
                continue
            if part.get("thought") is True and isinstance(part.get("text"), str):
                thought_parts.append(part["text"])
            elif isinstance(part.get("text"), str):
                text_parts.append(part["text"])
            if isinstance(part.get("functionCall"), dict):
                fc = part["functionCall"]
                saw_tool_calls = True
                delta_tc: dict[str, Any] = {
                    "index": tool_idx,
                    "id": f"call_{tool_idx}",
                    "type": "function",
                    "function": {
                        "name": str(fc.get("name") or ""),
                        "arguments": json.dumps(fc.get("args") or {}, ensure_ascii=False),
                    },
                }
                thought_sig = part.get("thoughtSignature")
                if isinstance(thought_sig, str) and thought_sig:
                    delta_tc["thought_signature"] = thought_sig
                    delta_tc["extra_content"] = {"google": {"thought_signature": thought_sig}}
                delta_tools.append(delta_tc)
                tool_idx += 1

        delta: dict[str, Any] = {}
        if text_parts:
            delta["content"] = "".join(text_parts)
        if thought_parts:
            delta["reasoning_content"] = "".join(thought_parts)
        if delta_tools:
            delta["tool_calls"] = delta_tools

        finish_reason = _map_gemini_finish_reason(
            cand.get("finishReason"), has_tool_calls=saw_tool_calls
        )
        if finish_reason is not None:
            saw_finish = True

        chunk: dict[str, Any] = {
            "id": native.get("responseId") or "gemini-native-stream",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason,
                }
            ],
        }
        usage = _extract_gemini_usage(native)
        if usage:
            chunk["usage"] = usage
        return json.dumps(chunk, ensure_ascii=False)

    async for line in response.aiter_lines():
        if line.startswith("data:"):
            event.append(line[5:].lstrip(" "))
        elif not line and event:
            converted = _convert_event("\n".join(event))
            event.clear()
            if converted is not None:
                yield converted
                if converted == "[DONE]":
                    return

    if event:
        converted = _convert_event("\n".join(event))
        if converted is not None:
            yield converted
            if converted == "[DONE]":
                return

    if saw_finish:
        yield "[DONE]"


async def _iter_openai_sse_data(response: httpx.Response) -> AsyncIterator[str]:
    event: list[str] = []
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            event.append(line[5:].lstrip(" "))
        elif not line and event:
            data = "\n".join(event)
            event.clear()
            yield data
            if data.strip() == "[DONE]":
                return
    if event:
        yield "\n".join(event)


async def _empty_sse_data() -> AsyncIterator[str]:
    if False:
        yield ""


def _openrouter_target(
    settings: Any,
    payload: dict[str, Any],
    extra_headers: dict[str, str] | None,
) -> tuple[str, dict[str, str], dict[str, Any], str]:
    api_key = clean_secret(getattr(settings, "llm_api_key", None))
    if not api_key:
        raise ProviderError("Configurez la clé API du fournisseur IA pour utiliser cette fonction.")
    base_url = str(getattr(settings, "llm_base_url", "https://openrouter.ai/api/v1") or "").strip().rstrip("/")
    if not base_url:
        raise ProviderError("Configurez LLM_BASE_URL pour utiliser le fournisseur IA.")
    url = f"{base_url}/chat/completions"
    headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"}
    if extra_headers:
        for k, v in extra_headers.items():
            headers[k] = v
    return url, headers, payload, "Fournisseur IA"


async def _google_cloud_target(
    settings: Any,
    payload: dict[str, Any],
    mode: str,
    *,
    stream: bool,
) -> tuple[str, dict[str, str], dict[str, Any], str, bool]:
    """Build (url, headers, body, route_label, is_native_gemini)."""
    adapted = adapt_openai_payload_for_google(payload, mode=mode, settings=settings)
    bare_model = normalize_google_model_id(
        str(payload.get("model") or ""), settings=settings, for_vertex_openapi=False
    )

    if mode == "vertex_oauth":
        token, project = await get_google_cloud_access_token(settings)
        loc = _validate_location(settings)
        host = vertex_api_host(loc)
        url = f"{host}/v1/projects/{project}/locations/{loc}/endpoints/openapi/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        return url, headers, adapted, "Google Cloud (Vertex AI)", False

    if mode == "gemini_api":
        api_key = clean_secret(getattr(settings, "google_api_key", None)) or clean_secret(
            getattr(settings, "gemini_api_key", None)
        )
        if not api_key:
            raise ProviderError(
                "Configurez GOOGLE_API_KEY pour utiliser Google Cloud en mode Gemini API."
            )
        url = f"{_GEMINI_OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        return url, headers, adapted, "Google Cloud (Gemini API)", False

    if mode == "vertex_api_key":
        api_key = clean_secret(getattr(settings, "vertex_api_key", None))
        if not api_key:
            raise ProviderError("Configurez VERTEX_API_KEY pour utiliser Vertex AI par clé API.")
        action = "streamGenerateContent?alt=sse" if stream else "generateContent"
        url = f"https://aiplatform.googleapis.com/v1/publishers/google/models/{bare_model}:{action}"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        native_body = openai_to_gemini_native_request(adapted, bare_model=bare_model)
        return url, headers, native_body, "Google Cloud (Vertex AI)", True

    raise ProviderError("Mode Google Cloud non pris en charge.")


async def post_chat_completion(
    settings: Any,
    payload: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float | httpx.Timeout = 120.0,
    extra_headers: dict[str, str] | None = None,
    provider_label: str = "Fournisseur IA",
) -> httpx.Response:
    """Route non-streaming chat completion calls to Google Cloud or OpenRouter."""
    model = str(payload.get("model") or "")
    use_gc = should_route_to_google_cloud(settings, model)
    fallback_or = bool(getattr(settings, "google_cloud_fallback_openrouter", False))
    has_or_key = bool(clean_secret(getattr(settings, "llm_api_key", None)))

    async def _do_post(
        target_client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> httpx.Response:
        return await target_client.post(url, headers=headers, json=body)

    async def _run_with_client(active_client: httpx.AsyncClient) -> httpx.Response:
        if not use_gc:
            url, headers, body, _ = _openrouter_target(settings, payload, extra_headers)
            return await _do_post(active_client, url, headers, body)

        mode = resolve_google_cloud_mode(settings) or ""
        try:
            url, headers, body, route_label, is_native = await _google_cloud_target(
                settings, payload, mode, stream=False
            )
            resp = await _do_post(active_client, url, headers, body)
            if not resp.is_success:
                if fallback_or and has_or_key:
                    _logger.warning(
                        "Échec %s HTTP %s pour %s ; bascule OpenRouter activée",
                        route_label,
                        resp.status_code,
                        model,
                    )
                    or_url, or_headers, or_body, _ = _openrouter_target(settings, payload, extra_headers)
                    return await _do_post(active_client, or_url, or_headers, or_body)
                return resp
            if is_native:
                native_json = json_body(resp, route_label)
                bare = normalize_google_model_id(model, settings=settings, for_vertex_openapi=False)
                converted = gemini_native_to_openai_dict(native_json, bare)
                return httpx.Response(200, json=converted, request=resp.request)
            return resp
        except (ProviderError, httpx.HTTPError) as exc:
            if fallback_or and has_or_key:
                _logger.warning(
                    "Échec Google Cloud (%s) pour %s ; bascule OpenRouter activée",
                    type(exc).__name__,
                    model,
                )
                or_url, or_headers, or_body, _ = _openrouter_target(settings, payload, extra_headers)
                return await _do_post(active_client, or_url, or_headers, or_body)
            raise

    if client is not None:
        return await _run_with_client(client)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as local_client:
        return await _run_with_client(local_client)


def _is_output_token_limit_error(err_text: str) -> bool:
    low = (err_text or "").lower()
    return any(
        tok in low
        for tok in ("max_tokens", "max_output_tokens", "max_completion_tokens", "maxoutputtokens", "output tokens")
    )


def _lower_max_tokens_in_body(body: dict[str, Any], is_native: bool) -> dict[str, Any] | None:
    """Return a copy of body with output token limit stepped down (65536 -> 32768 -> 8192), or None."""
    if is_native:
        gen_cfg = body.get("generationConfig")
        if not isinstance(gen_cfg, dict):
            return None
        cur = gen_cfg.get("maxOutputTokens")
        if not isinstance(cur, int) or cur <= 8192:
            return None
        nxt = 32768 if cur > 32768 else 8192
        return {**body, "generationConfig": {**gen_cfg, "maxOutputTokens": nxt}}
    for key in ("max_tokens", "max_completion_tokens"):
        cur = body.get(key)
        if isinstance(cur, int) and cur > 8192:
            nxt = 32768 if cur > 32768 else 8192
            return {**body, key: nxt}
    return None


@asynccontextmanager
async def open_chat_stream(
    settings: Any,
    payload: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float | httpx.Timeout = 480.0,
    extra_headers: dict[str, str] | None = None,
    provider_label: str = "Fournisseur IA",
    raise_on_error: bool = True,
) -> AsyncIterator[tuple[httpx.Response, AsyncIterator[str], str]]:
    """Open streaming chat completion against Google Cloud or OpenRouter, yielding normalized SSE data strings."""
    model = str(payload.get("model") or "")
    use_gc = should_route_to_google_cloud(settings, model)
    fallback_or = bool(getattr(settings, "google_cloud_fallback_openrouter", False))
    has_or_key = bool(clean_secret(getattr(settings, "llm_api_key", None)))

    async with AsyncExitStack() as stack:
        if client is not None:
            active_client = client
        else:
            active_client = await stack.enter_async_context(
                httpx.AsyncClient(timeout=timeout, follow_redirects=False)
            )

        if not use_gc:
            url, headers, body, _ = _openrouter_target(settings, payload, extra_headers)
            headers.setdefault("Accept", "text/event-stream")
            resp = await stack.enter_async_context(
                active_client.stream("POST", url, headers=headers, json=body)
            )
            if not resp.is_success:
                if raise_on_error:
                    check_response(resp, provider_label)
                yield resp, _empty_sse_data(), provider_label
            else:
                yield resp, _iter_openai_sse_data(resp), provider_label
            return

        mode = resolve_google_cloud_mode(settings) or ""
        try:
            url, headers, body, route_label, is_native = await _google_cloud_target(
                settings, payload, mode, stream=True
            )
            headers.setdefault("Accept", "text/event-stream")
            bare = normalize_google_model_id(model, settings=settings, for_vertex_openapi=False)
            active_body = body
            for _attempt in range(3):
                async with AsyncExitStack() as gc_stack:
                    resp = await gc_stack.enter_async_context(
                        active_client.stream("POST", url, headers=headers, json=active_body)
                    )
                    if resp.is_success:
                        sse_iter = (
                            iter_gemini_sse_as_openai_data(resp, bare)
                            if is_native
                            else _iter_openai_sse_data(resp)
                        )
                        yield resp, sse_iter, route_label
                        return
                    err_preview = ""
                    try:
                        await resp.aread()
                        err_preview = resp.text[:400].replace("\n", " ")
                    except Exception:
                        pass
                    if resp.status_code == 400 and _is_output_token_limit_error(err_preview):
                        stepped_body = _lower_max_tokens_in_body(active_body, is_native)
                        if stepped_body is not None:
                            _logger.warning(
                                "Google Cloud HTTP 400 sur max_tokens pour %s ; nouvelle tentative avec plafond réduit.",
                                bare,
                            )
                            active_body = stepped_body
                            continue
                    if not (fallback_or and has_or_key):
                        if raise_on_error:
                            if err_preview:
                                _logger.warning(
                                    "Échec %s HTTP %s pour %s : %s",
                                    route_label,
                                    resp.status_code,
                                    bare,
                                    err_preview,
                                )
                            check_response(resp, route_label)
                        yield resp, _empty_sse_data(), route_label
                        return
                    fallback_reason = f"HTTP {resp.status_code}"
                    break
            _logger.warning(
                "Échec stream Google Cloud (%s) pour %s ; bascule OpenRouter activée",
                fallback_reason,
                model,
            )
            or_url, or_headers, or_body, _ = _openrouter_target(settings, payload, extra_headers)
            or_headers.setdefault("Accept", "text/event-stream")
            or_resp = await stack.enter_async_context(
                active_client.stream("POST", or_url, headers=or_headers, json=or_body)
            )
            if not or_resp.is_success:
                if raise_on_error:
                    check_response(or_resp, provider_label)
                yield or_resp, _empty_sse_data(), provider_label
            else:
                yield or_resp, _iter_openai_sse_data(or_resp), provider_label
            return
        except (ProviderError, httpx.HTTPError) as exc:
            if not (fallback_or and has_or_key):
                raise
            _logger.warning(
                "Échec stream Google Cloud (%s) pour %s ; bascule OpenRouter activée",
                type(exc).__name__,
                model,
            )
            or_url, or_headers, or_body, _ = _openrouter_target(settings, payload, extra_headers)
            or_headers.setdefault("Accept", "text/event-stream")
            or_resp = await stack.enter_async_context(
                active_client.stream("POST", or_url, headers=or_headers, json=or_body)
            )
            if not or_resp.is_success:
                if raise_on_error:
                    check_response(or_resp, provider_label)
                yield or_resp, _empty_sse_data(), provider_label
            else:
                yield or_resp, _iter_openai_sse_data(or_resp), provider_label
            return


def _extract_image_from_gemini_payload(data: dict[str, Any]) -> tuple[bytes, str] | None:
    candidates = data.get("candidates") or []
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        parts = (cand.get("content") or {}).get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                raw_b64 = re.sub(r"\s+", "", str(inline["data"]))
                raw_bytes = base64.b64decode(raw_b64)
                mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/png").lower()
                return raw_bytes, mime
    return None


def _extract_image_from_imagen_payload(data: dict[str, Any]) -> tuple[bytes, str] | None:
    preds = data.get("predictions") or []
    for pred in preds:
        if not isinstance(pred, dict):
            continue
        b64 = pred.get("bytesBase64Encoded")
        if b64:
            raw_bytes = base64.b64decode(re.sub(r"\s+", "", str(b64)))
            mime = str(pred.get("mimeType") or "image/png").lower()
            return raw_bytes, mime
    return None


def _google_image_fallback_targets(
    bare: str,
    loc: str,
    mode: str,
) -> list[tuple[str, str]]:
    """Build ordered (location, model_id) pairs on Google Cloud so regional/preview 404s stay on Vertex AI."""
    candidates: list[tuple[str, str]] = [(loc, bare)]
    low = bare.lower()
    needs_preview_variant = (
        (low.startswith("gemini-3") or low.startswith("gemini-nano-banana"))
        and not low.endswith("-preview")
    )
    if mode == "vertex_oauth" and loc != "global":
        candidates.append(("global", bare))
        if needs_preview_variant:
            candidates.append(("global", f"{bare}-preview"))
    elif needs_preview_variant:
        candidates.append((loc, f"{bare}-preview"))
    return candidates


async def generate_google_cloud_image(
    settings: Any,
    model: str,
    prompt: str,
    *,
    aspect_ratio: str = "1:1",
    negative_prompt: str | None = None,
    reference_image: tuple[bytes, str] | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str]:
    """Generate an image via Google Cloud (Vertex AI / Gemini API) using Imagen `:predict` or Gemini `:generateContent`."""
    mode = resolve_google_cloud_mode(settings)
    if not mode:
        raise ProviderError(
            "Les modèles d'image Gemini passent exclusivement par Google Cloud (Vertex AI) ; "
            "configurez GOOGLE_CLOUD_MODE et GOOGLE_CLOUD_PROJECT."
        )

    bare = normalize_google_model_id(model, settings=settings, for_vertex_openapi=False)
    is_imagen = bare.lower().startswith("imagen-")

    final_prompt = prompt.strip()
    if negative_prompt and negative_prompt.strip() and not is_imagen:
        final_prompt = f"{final_prompt}\n\nAvoid / negative prompt: {negative_prompt.strip()}"

    if is_imagen:
        params: dict[str, Any] = {"sampleCount": 1}
        if aspect_ratio:
            params["aspectRatio"] = aspect_ratio
        if negative_prompt and negative_prompt.strip():
            params["negativePrompt"] = negative_prompt.strip()
        req_body: dict[str, Any] = {
            "instances": [{"prompt": final_prompt}],
            "parameters": params,
        }
        action = "predict"
    else:
        parts: list[dict[str, Any]] = [{"text": final_prompt}]
        if reference_image is not None:
            ref_bytes, ref_mime = reference_image
            parts.append({
                "inlineData": {
                    "mimeType": ref_mime,
                    "data": base64.b64encode(ref_bytes).decode("ascii"),
                }
            })
        image_cfg: dict[str, Any] = {}
        if aspect_ratio:
            image_cfg["aspectRatio"] = aspect_ratio
        gen_cfg: dict[str, Any] = {"responseModalities": ["IMAGE"]}
        if image_cfg:
            gen_cfg["imageConfig"] = image_cfg
        req_body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen_cfg,
        }
        action = "generateContent"

    loc = "global"
    token = ""
    project = ""
    if mode == "vertex_oauth":
        token, project = await get_google_cloud_access_token(settings)
        loc = _validate_location(settings)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        route_label = "Google Cloud (Vertex AI Images)"
    elif mode == "vertex_api_key":
        api_key = clean_secret(getattr(settings, "vertex_api_key", None))
        if not api_key:
            raise ProviderError("Configurez VERTEX_API_KEY pour générer des images via Vertex AI.")
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        route_label = "Google Cloud (Vertex AI Images)"
    elif mode == "gemini_api":
        api_key = clean_secret(getattr(settings, "google_api_key", None)) or clean_secret(
            getattr(settings, "gemini_api_key", None)
        )
        if not api_key:
            raise ProviderError("Configurez GOOGLE_API_KEY pour générer des images via Gemini API.")
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        route_label = "Google Cloud (Gemini Images)"
    else:
        raise ProviderError("Mode Google Cloud non pris en charge.")

    def _build_url(target_loc: str, target_bare: str) -> str:
        if mode == "vertex_oauth":
            host = vertex_api_host(target_loc)
            return f"{host}/v1/projects/{project}/locations/{target_loc}/publishers/google/models/{target_bare}:{action}"
        if mode == "vertex_api_key":
            return f"https://aiplatform.googleapis.com/v1/publishers/google/models/{target_bare}:{action}"
        return f"{_GEMINI_NATIVE_BASE_URL}/models/{target_bare}:{action}"

    targets = _google_image_fallback_targets(bare, loc, mode)

    async def _exec_with_fallbacks(active_client: httpx.AsyncClient) -> httpx.Response:
        last_resp: httpx.Response | None = None
        for idx, (cand_loc, cand_bare) in enumerate(targets):
            url = _build_url(cand_loc, cand_bare)
            resp = await active_client.post(url, headers=headers, json=req_body)
            last_resp = resp
            if resp.status_code == 404 and idx + 1 < len(targets):
                _logger.info(
                    "%s HTTP 404 sur %s (%s) ; nouvel essai sur %s (%s)",
                    route_label,
                    cand_bare,
                    cand_loc,
                    targets[idx + 1][1],
                    targets[idx + 1][0],
                )
                continue
            break
        assert last_resp is not None
        return last_resp

    try:
        if client is not None:
            response = await _exec_with_fallbacks(client)
        else:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0), follow_redirects=False) as local_client:
                response = await _exec_with_fallbacks(local_client)
        check_response(response, route_label)
        payload = json_body(response, route_label)
        extracted = (
            _extract_image_from_imagen_payload(payload)
            if is_imagen
            else _extract_image_from_gemini_payload(payload)
        )
        if not extracted:
            raise ProviderError(f"{route_label} n'a pas renvoyé d'image.")
        image_bytes, mime_type = extracted
        if len(image_bytes) > _MAX_IMAGE_BYTES:
            raise ProviderError("L'image dépasse la limite de 10 Mio.")
        detected_mime = detect_image_mime(image_bytes)
        if detected_mime:
            mime_type = detected_mime
        elif not image_signature_matches(image_bytes, mime_type):
            raise ProviderError("Le fichier renvoyé par Google Cloud n'est pas une image reconnue.")
        return image_bytes, mime_type
    except httpx.TimeoutException:
        raise ProviderError("La génération d'image Google Cloud a dépassé le délai autorisé.") from None
    except httpx.HTTPError:
        raise ProviderError("Impossible de joindre Google Cloud pour la génération d'image.") from None


def resolve_interactions_config(settings: Any) -> dict[str, Any]:
    """Resolve Google Deep Research Interactions API endpoint configuration."""
    mode = resolve_google_cloud_mode(settings)
    raw_google_key = clean_secret(getattr(settings, "google_api_key", None)) or clean_secret(
        getattr(settings, "gemini_api_key", None)
    )

    if mode == "vertex_oauth":
        return {
            "mode": "vertex_oauth",
            "use_oauth": True,
            "api_key": "",
        }
    if mode == "gemini_api" or (raw_google_key and mode in (None, "auto")):
        if not raw_google_key:
            return {"mode": "demo", "use_oauth": False, "api_key": ""}
        return {
            "mode": "gemini_api",
            "use_oauth": False,
            "api_key": raw_google_key,
            "base_url": f"{_GEMINI_NATIVE_BASE_URL}/interactions",
        }
    if mode == "vertex_api_key":
        if raw_google_key:
            return {
                "mode": "gemini_api",
                "use_oauth": False,
                "api_key": raw_google_key,
                "base_url": f"{_GEMINI_NATIVE_BASE_URL}/interactions",
            }
        raise ProviderError(
            "Google Deep Research (Interactions API) nécessite soit Vertex AI OAuth2 "
            "(GOOGLE_CLOUD_PROJECT + ADC/Service Account), soit GOOGLE_API_KEY."
        )
    return {"mode": "demo", "use_oauth": False, "api_key": ""}


async def get_interactions_request_params(settings: Any) -> tuple[str, dict[str, str], str]:
    """Return (base_interactions_url, auth_headers, mode) with fresh OAuth2 token when applicable."""
    cfg = resolve_interactions_config(settings)
    if cfg.get("use_oauth"):
        token, project = await get_google_cloud_access_token(settings)
        base_url = f"https://aiplatform.googleapis.com/v1beta1/projects/{project}/locations/global/interactions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        return base_url, headers, "vertex_oauth"

    api_key = str(cfg.get("api_key") or "")
    base_url = str(cfg.get("base_url") or f"{_GEMINI_NATIVE_BASE_URL}/interactions")
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    return base_url, headers, str(cfg.get("mode") or "gemini_api")


def build_interaction_url(base_url: str, interaction_id: str) -> str:
    clean_id = str(interaction_id or "").strip()
    clean_base = base_url.rstrip("/")
    if not clean_id:
        return clean_base
    if clean_id.startswith("projects/"):
        return f"https://aiplatform.googleapis.com/v1beta1/{clean_id}"
    if clean_id.startswith("interactions/"):
        if "aiplatform.googleapis.com" in clean_base:
            suffix = clean_id[len("interactions/"):]
            return f"{clean_base}/{suffix}"
        return f"{_GEMINI_NATIVE_BASE_URL}/{clean_id}"
    return f"{clean_base}/{clean_id}"
