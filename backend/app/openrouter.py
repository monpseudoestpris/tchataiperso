"""OpenRouter dynamic model directory adapter with filtering, caching, and pricing computation."""

from __future__ import annotations

import concurrent.futures
import logging
import time
from typing import Any

import httpx

_logger = logging.getLogger("uvicorn.error")

_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "models": [],
}
_IMAGE_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "models": [],
}
_CACHE_TTL = 900.0  # 15 minutes

# Top 12 ranked image generation models on OpenRouter
# (Source: https://openrouter.ai/collections/image-models)
TOP_IMAGE_MODELS: list[str] = [
    "google/gemini-3.1-flash-image",
    "openai/gpt-image-2.5-sunburst",
    "google/gemini-nano-banana-2.1",
    "bytedance-seed/seedream-5-0-flash",
    "meta/muse-image",
    "google/gemini-2.5-flash-image",
    "google/gemini-3.1-flash-lite-image",
    "openai/gpt-image-2.5-flare",
    "openai/gpt-image-2",
    "tencent/hy-image-v3.5-preview",
    "openai/gpt-5.4-image-2",
    "google/gemini-3-pro-image",
]


def is_chat_model(m: dict[str, Any]) -> bool:
    """Filter out non-chat models (sound/audio/music/video generation, batch queues, embeddings)."""
    mid = str(m.get("id") or "").strip()
    if not mid or ":batch" in mid:
        return False

    arch = m.get("architecture") or {}
    out_mods = [str(x).lower() for x in (arch.get("output_modalities") or [])]
    mod = str(arch.get("modality") or "").lower()

    # Must output text
    if out_mods and "text" not in out_mods:
        return False
    if mod and not (mod.endswith("->text") or "->text+" in mod or mod == "text->text"):
        return False

    # Exclude models producing sound, music, audio, or video
    if any(x in out_mods for x in ("audio", "video", "sound", "music")):
        return False
    if any(mod.endswith("->" + x) for x in ("audio", "video", "sound", "music")):
        return False

    # Exclude known audio/sound/tts/video/embedding model IDs
    mid_lower = mid.lower()
    audio_video_keywords = (
        "-audio",
        "/audio",
        "lyria",
        "suno",
        "elevenlabs",
        "whisper",
        "text-to-speech",
        "tts-",
        "/embed",
        "embedding",
        "/rerank",
    )
    if any(k in mid_lower for k in audio_video_keywords):
        return False

    return True


def format_openrouter_model(m: dict[str, Any]) -> dict[str, Any]:
    """Format raw OpenRouter model JSON into application model metadata."""
    mid = m["id"]
    arch = m.get("architecture") or {}
    pricing = m.get("pricing") or {}
    modality = str(arch.get("modality") or "").lower()
    in_mods = [str(x).lower() for x in (arch.get("input_modalities") or [])]

    # Vision check: does modality or input_modalities include image?
    has_vision = "image" in modality or "image" in in_mods

    try:
        raw_prompt = float(pricing.get("prompt") or 0)
    except (ValueError, TypeError):
        raw_prompt = 0.0

    try:
        raw_completion = float(pricing.get("completion") or 0)
    except (ValueError, TypeError):
        raw_completion = 0.0

    raw_cache = pricing.get("input_cache_read")
    try:
        cache_price = round(float(raw_cache) * 1_000_000, 4) if raw_cache is not None else None
    except (ValueError, TypeError):
        cache_price = None

    prompt_price_1m = round(raw_prompt * 1_000_000, 4)
    completion_price_1m = round(raw_completion * 1_000_000, 4)

    provider = mid.split("/")[0] if "/" in mid else "openrouter"
    reasoning_info = m.get("reasoning")
    has_reasoning = bool(reasoning_info and (reasoning_info.get("supported_efforts") or reasoning_info.get("mandatory")))

    return {
        "id": mid,
        "name": m.get("name") or mid,
        "vision": has_vision,
        "description": m.get("description") or "",
        "context_length": int(m.get("context_length") or 0),
        "pricing": {
            "prompt": pricing.get("prompt", "0"),
            "completion": pricing.get("completion", "0"),
            "input_cache_read": pricing.get("input_cache_read"),
        },
        "prompt_price_1m": prompt_price_1m,
        "completion_price_1m": completion_price_1m,
        "input_cache_read_price_1m": cache_price,
        "provider": provider,
        "reasoning": has_reasoning,
    }


def fetch_openrouter_models(
    api_key: str = "",
    base_url: str = "https://openrouter.ai/api/v1",
    force_refresh: bool = False,
    timeout: float = 6.0,
) -> list[dict[str, Any]]:
    """Fetch and filter chat models dynamically from OpenRouter with caching."""
    now = time.time()
    if not force_refresh and _CACHE["models"] and (now - _CACHE["timestamp"] < _CACHE_TTL):
        return list(_CACHE["models"])

    clean_base = base_url.rstrip("/") if base_url else "https://openrouter.ai/api/v1"
    url = f"{clean_base}/models" if not clean_base.endswith("/models") else clean_base
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers if headers else None)
            if resp.status_code != 200:
                _logger.warning("Échec récupération modèles OpenRouter (HTTP %s)", resp.status_code)
                return list(_CACHE["models"])
            data = resp.json().get("data", [])
            filtered = [format_openrouter_model(m) for m in data if is_chat_model(m)]
            if filtered:
                _CACHE["timestamp"] = now
                _CACHE["models"] = filtered
                return list(filtered)
    except Exception as exc:
        _logger.warning("Impossible de joindre OpenRouter pour la liste dynamique : %s", exc)

    return list(_CACHE["models"])


def format_image_pricing(
    pricing_list: list[dict[str, Any]] | None,
    prompt_price_1m: float | None = None,
) -> str:
    """Format OpenRouter endpoint pricing list into a clear, concise pricing badge string."""
    if not pricing_list:
        return "Tarif standard"

    outputs = [p for p in pricing_list if p.get("billable") == "output_image"]
    inputs = [p for p in pricing_list if p.get("billable") in ("input_text", "input_image")]
    parts: list[str] = []

    # 1. Output per image
    img_outputs = [p for p in outputs if p.get("unit") == "image"]
    if img_outputs:
        costs = [float(p.get("cost_usd") or 0) for p in img_outputs if p.get("cost_usd") is not None]
        if costs:
            min_c = min(costs)
            max_c = max(costs)
            if min_c == max_c:
                parts.append(f"${min_c:g}/img")
            else:
                parts.append(f"${min_c:g}-${max_c:g}/img")

    # 2. Output per megapixel
    mp_outputs = [p for p in outputs if p.get("unit") == "megapixel"]
    if mp_outputs:
        cost = float(mp_outputs[0].get("cost_usd") or 0)
        parts.append(f"${cost:g}/MP")

    # 3. Output & input per token
    token_outputs = [p for p in outputs if p.get("unit") == "token"]
    token_inputs = [p for p in inputs if p.get("unit") == "token"]
    if token_outputs or token_inputs or prompt_price_1m:
        in_cost: float | None = None
        if token_inputs:
            in_cost = float(token_inputs[0].get("cost_usd") or 0) * 1_000_000
        elif prompt_price_1m is not None and prompt_price_1m > 0:
            in_cost = prompt_price_1m

        if in_cost is not None and in_cost > 0:
            parts.append(f"${in_cost:g}/M in")
        if token_outputs:
            out_cost = float(token_outputs[0].get("cost_usd") or 0) * 1_000_000
            parts.append(f"${out_cost:g}/M out")

    return " · ".join(parts) if parts else "Tarif spécifique"


def fetch_openrouter_image_models(
    api_key: str = "",
    base_url: str = "https://openrouter.ai/api/v1",
    force_refresh: bool = False,
    timeout: float = 6.0,
) -> list[dict[str, Any]]:
    """Fetch dedicated Image Generation models dynamically from OpenRouter Image API."""
    now = time.time()
    if not force_refresh and _IMAGE_CACHE["models"] and (now - _IMAGE_CACHE["timestamp"] < _CACHE_TTL):
        return list(_IMAGE_CACHE["models"])

    clean_base = base_url.rstrip("/") if base_url else "https://openrouter.ai/api/v1"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Also grab cached general models to cross-reference input token prices if available
    chat_models = {m["id"]: m for m in _CACHE["models"]}

    url = f"{clean_base}/images/models"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=headers if headers else None)
            if resp.status_code != 200:
                _logger.warning("Échec récupération modèles images OpenRouter (HTTP %s)", resp.status_code)
                return list(_IMAGE_CACHE["models"])
            raw_data = resp.json().get("data", [])
            if not raw_data:
                return list(_IMAGE_CACHE["models"])

            def _enrich_single(m: dict[str, Any]) -> dict[str, Any]:
                mid = str(m.get("id") or "").strip()
                ep_url = f"{clean_base}/images/models/{mid}/endpoints"
                pricing = None
                try:
                    with httpx.Client(timeout=2.5, follow_redirects=True) as ep_client:
                        ep_resp = ep_client.get(ep_url, headers=headers if headers else None)
                        if ep_resp.status_code == 200:
                            eps = ep_resp.json().get("endpoints", [])
                            if eps and isinstance(eps, list):
                                pricing = eps[0].get("pricing")
                except Exception:
                    pass

                chat_counterpart = chat_models.get(mid)
                prompt_price_1m = chat_counterpart.get("prompt_price_1m") if chat_counterpart else None
                pricing_text = format_image_pricing(pricing, prompt_price_1m)

                params = m.get("supported_parameters") or {}
                aspect_ratios = []
                if isinstance(params.get("aspect_ratio"), dict):
                    aspect_ratios = params["aspect_ratio"].get("values") or []
                resolutions = []
                if isinstance(params.get("resolution"), dict):
                    resolutions = params["resolution"].get("values") or []

                is_top = mid in TOP_IMAGE_MODELS
                rank = TOP_IMAGE_MODELS.index(mid) if is_top else 999

                return {
                    "id": mid,
                    "name": m.get("name") or mid,
                    "provider": "openrouter",
                    "description": m.get("description") or "",
                    "pricing_text": pricing_text,
                    "supported_aspect_ratios": [str(r) for r in aspect_ratios],
                    "supported_resolutions": [str(r) for r in resolutions],
                    "is_top": is_top,
                    "_rank": rank,
                }

            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                enriched = list(pool.map(_enrich_single, raw_data))

            enriched.sort(key=lambda x: (x["_rank"], x["name"].lower()))
            _IMAGE_CACHE["timestamp"] = now
            _IMAGE_CACHE["models"] = enriched
            return list(enriched)

    except Exception as exc:
        _logger.warning("Impossible de joindre OpenRouter Image API : %s", exc)

    return list(_IMAGE_CACHE["models"])

