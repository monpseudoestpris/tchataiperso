"""OpenRouter dynamic model directory adapter with filtering, caching, and pricing computation."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

_logger = logging.getLogger("uvicorn.error")

_CACHE: dict[str, Any] = {
    "timestamp": 0.0,
    "models": [],
}
_CACHE_TTL = 900.0  # 15 minutes


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

