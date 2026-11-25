"""Adaptateurs Ideogram v2 pour l'Upscale d'images (8 modèles) et les Vecteurs SVG (Generate SVG & Image-to-SVG)."""

from __future__ import annotations

import sys
from typing import Any

import httpx

from .google_cloud import (
    ProviderError,
    check_response as _check_response,
    detect_image_mime as _detect_image_mime,
    image_signature_matches as _image_signature_matches,
    json_body as _json,
)
from .svg_sanitize import sanitize_svg_bytes

_MAX_UPSCALE_IMAGE_BYTES = 60 * 1024 * 1024
_UPSCALE_TIMEOUT = httpx.Timeout(300.0, connect=10.0, pool=10.0)
_DOWNLOAD_TIMEOUT = httpx.Timeout(120.0, connect=10.0, pool=10.0)
_SVG_MAX_POLLS = 120
_UPSCALE_MAX_POLLS = 120

_RASTER_EXT_MAP = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}
_ALLOWED_RASTER_MIMES = frozenset(_RASTER_EXT_MAP)

_SVG_GENERATE_RATIOS: frozenset[str] = frozenset({
    "auto",
    "1x4",
    "1x3",
    "1x2",
    "9x16",
    "10x16",
    "2x3",
    "3x4",
    "4x5",
    "1x1",
    "5x4",
    "4x3",
    "3x2",
    "16x10",
    "16x9",
    "2x1",
    "3x1",
    "4x1",
})

IDEOGRAM_UPSCALE_MODELS: list[dict[str, Any]] = [
    {
        "id": "auto",
        "name": "Ideogram Auto",
        "kind": "automatic",
        "kind_label": "Automatique",
        "description": "Sélectionne automatiquement le modèle d'agrandissement optimal selon l'image.",
        "supported_factors": ["x2", "x4", "x8"],
        "supported_tiers": [],
        "max_side_px": 8192,
        "max_megapixels": None,
        "supports_prompt": False,
        "supports_autoprompt": False,
        "supports_creativity": False,
        "supports_color_preservation": False,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": False,
        "supports_redefine_controls": False,
        "supports_seed": True,
    },
    {
        "id": "topaz-standard-2",
        "name": "Topaz Standard V2",
        "kind": "faithful",
        "kind_label": "Fidèle",
        "description": "Agrandit et accentue la netteté globale en restant strictement fidèle à la photo ou illustration source.",
        "supported_factors": ["x2", "x4", "x8"],
        "supported_tiers": [],
        "max_side_px": 8192,
        "max_megapixels": None,
        "supports_prompt": False,
        "supports_autoprompt": False,
        "supports_creativity": False,
        "supports_color_preservation": False,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": True,
        "supports_redefine_controls": False,
        "supports_seed": False,
    },
    {
        "id": "topaz-text-refine",
        "name": "Topaz Text Refine",
        "kind": "faithful",
        "kind_label": "Fidèle · Typographie",
        "description": "Préserve la netteté des grands titres comme des petits caractères, étiquettes et logos.",
        "supported_factors": ["x2", "x4", "x8"],
        "supported_tiers": [],
        "max_side_px": 8192,
        "max_megapixels": None,
        "supports_prompt": False,
        "supports_autoprompt": False,
        "supports_creativity": False,
        "supports_color_preservation": False,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": True,
        "supports_redefine_controls": False,
        "supports_seed": False,
    },
    {
        "id": "topaz-wonder-4",
        "name": "Topaz Wonder 4",
        "kind": "detail",
        "kind_label": "Détails & Visages · 100 MP",
        "description": "Supprime bruit, flou et artefacts JPEG tout en restaurant les visages en une seule passe (x2 ou x4, jusqu'à 100 MP).",
        "supported_factors": ["x2", "x4"],
        "supported_tiers": [],
        "max_side_px": None,
        "max_megapixels": 100,
        "supports_prompt": False,
        "supports_autoprompt": False,
        "supports_creativity": False,
        "supports_color_preservation": False,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": False,
        "supports_redefine_controls": False,
        "supports_seed": False,
    },
    {
        "id": "topaz-wonder-3-5",
        "name": "Topaz Wonder 3.5",
        "kind": "detail",
        "kind_label": "Reconstruction de détails",
        "description": "Reconstruit la matière et les micro-détails avec dosage d'intensité (faible, moyenne, élevée).",
        "supported_factors": ["x2", "x4", "x8"],
        "supported_tiers": [],
        "max_side_px": 8192,
        "max_megapixels": None,
        "supports_prompt": False,
        "supports_autoprompt": False,
        "supports_creativity": False,
        "supports_color_preservation": False,
        "supports_enhancement_strength": True,
        "supports_topaz_controls": False,
        "supports_redefine_controls": False,
        "supports_seed": True,
    },
    {
        "id": "topaz-bloom-2",
        "name": "Topaz Bloom 2",
        "kind": "creative",
        "kind_label": "Créatif",
        "description": "Enrichit les textures fines avec créativité réglable (1–9), conservation des couleurs et prompt optionnel.",
        "supported_factors": ["x2", "x4", "x8"],
        "supported_tiers": [],
        "max_side_px": 8192,
        "max_megapixels": None,
        "supports_prompt": True,
        "supports_autoprompt": False,
        "supports_creativity": True,
        "supports_color_preservation": True,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": False,
        "supports_redefine_controls": False,
        "supports_seed": True,
    },
    {
        "id": "topaz-redefine",
        "name": "Topaz Redefine",
        "kind": "creative",
        "kind_label": "Créatif avancé",
        "description": "Réinterprétation générative poussée guidée par prompt ou autoprompt, texture, détail et restauration visages.",
        "supported_factors": ["x2", "x4", "x8"],
        "supported_tiers": [],
        "max_side_px": 8192,
        "max_megapixels": None,
        "supports_prompt": True,
        "supports_autoprompt": True,
        "supports_creativity": True,
        "supports_color_preservation": False,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": False,
        "supports_redefine_controls": True,
        "supports_seed": True,
    },
    {
        "id": "nano-banana-pro",
        "name": "Nano Banana Pro Upscale",
        "kind": "regenerate",
        "kind_label": "Régénération 1K / 2K / 4K",
        "description": "Régénère l'image au palier 1K, 2K ou 4K en préservant sa composition et son style, avec consigne optionnelle.",
        "supported_factors": [],
        "supported_tiers": ["1K", "2K", "4K"],
        "max_side_px": None,
        "max_megapixels": None,
        "supports_prompt": True,
        "supports_autoprompt": False,
        "supports_creativity": False,
        "supports_color_preservation": False,
        "supports_enhancement_strength": False,
        "supports_topaz_controls": False,
        "supports_redefine_controls": False,
        "supports_seed": False,
    },
]

UPSCALE_MODELS_BY_ID: dict[str, dict[str, Any]] = {m["id"]: m for m in IDEOGRAM_UPSCALE_MODELS}


def _resolve_async_client_cls() -> type[httpx.AsyncClient]:
    """Use providers.httpx.AsyncClient when monkeypatched in unit tests."""
    providers_mod = sys.modules.get(f"{__package__}.providers")
    if providers_mod is not None and hasattr(providers_mod, "httpx"):
        return providers_mod.httpx.AsyncClient
    return httpx.AsyncClient


def _validate_raster_source(reference_image: tuple[bytes, str] | None, context_label: str) -> tuple[bytes, str, str]:
    if reference_image is None:
        raise ProviderError(f"Une image source (PNG, JPEG ou WEBP) est requise pour {context_label}.")
    ref_bytes, ref_mime = reference_image
    norm_mime = (ref_mime or "").strip().lower()
    if norm_mime not in _ALLOWED_RASTER_MIMES:
        raise ProviderError(f"Format source non pris en charge pour {context_label} (utilisez PNG, JPEG ou WEBP).")
    return ref_bytes, norm_mime, _RASTER_EXT_MAP[norm_mime]


def build_ideogram_upscale_request(
    model_id: str,
    reference_image: tuple[bytes, str],
    *,
    upscale_factor: str = "x2",
    resolution_tier: str = "2K",
    prompt: str | None = None,
    autoprompt: bool | None = None,
    creativity: int | None = None,
    color_preservation: bool | None = None,
    enhancement_strength: str | None = None,
    strength: float | None = None,
    sharpen: float | None = None,
    denoise: float | None = None,
    fix_compression: float | None = None,
    texture: int | None = None,
    detail: bool | None = None,
    detail_strength: float | None = None,
    face_enhancement: bool | None = None,
    face_enhancement_strength: float | None = None,
    face_enhancement_creativity: float | None = None,
    subject_detection: str | None = None,
    seed: int | None = None,
) -> tuple[str, dict[str, tuple[Any, ...]]]:
    """Build exact multipart/form-data request for POST /v2/image/upscale/{model}."""
    spec = UPSCALE_MODELS_BY_ID.get((model_id or "").strip())
    if spec is None:
        raise ProviderError("Modèle d'upscale Ideogram inconnu.")

    ref_bytes, ref_mime, ref_ext = _validate_raster_source(reference_image, "l'upscale Ideogram")
    mid = spec["id"]
    endpoint = f"https://api.ideogram.ai/v2/image/upscale/{mid}"
    files: dict[str, tuple[Any, ...]] = {
        "image": (f"source.{ref_ext}", ref_bytes, ref_mime),
    }

    if mid == "nano-banana-pro":
        tier = (resolution_tier or "2K").strip().upper()
        if tier not in {"1K", "2K", "4K"}:
            raise ProviderError("Le palier de résolution Nano Banana Pro doit être 1K, 2K ou 4K.")
        files["resolution_tier"] = (None, tier)
        if prompt and prompt.strip():
            files["prompt"] = (None, prompt.strip()[:1024])
        return endpoint, files

    factor = (upscale_factor or "x2").strip().lower()
    if factor not in spec["supported_factors"]:
        allowed_str = ", ".join(spec["supported_factors"])
        raise ProviderError(f"Le facteur d'upscale {factor} n'est pas pris en charge par {spec['name']} ({allowed_str}).")
    files["upscale_factor"] = (None, factor)

    if spec["supports_seed"] and seed is not None:
        files["seed"] = (None, str(int(seed)))

    if mid == "topaz-wonder-3-5":
        if enhancement_strength is not None:
            enh = enhancement_strength.strip().lower()
            if enh not in {"low", "medium", "high"}:
                raise ProviderError("enhancement_strength doit valoir low, medium ou high.")
            files["enhancement_strength"] = (None, enh)
        return endpoint, files

    if mid == "topaz-bloom-2":
        if prompt and prompt.strip():
            files["prompt"] = (None, prompt.strip()[:1024])
        if creativity is not None:
            files["creativity"] = (None, str(max(1, min(9, int(creativity)))))
        if color_preservation is not None:
            files["color_preservation"] = (None, "true" if color_preservation else "false")
        return endpoint, files

    if mid == "topaz-redefine":
        if autoprompt is True:
            files["autoprompt"] = (None, "true")
        elif prompt and prompt.strip():
            files["prompt"] = (None, prompt.strip()[:1024])
        if creativity is not None:
            files["creativity"] = (None, str(max(1, min(9, int(creativity)))))
        if texture is not None:
            files["texture"] = (None, str(max(1, min(5, int(texture)))))
        if detail is not None:
            files["detail"] = (None, "true" if detail else "false")
            if detail and detail_strength is not None:
                files["detail_strength"] = (None, f"{max(0.0, min(10.0, float(detail_strength))):g}")
        if sharpen is not None:
            files["sharpen"] = (None, f"{max(0.0, min(1.0, float(sharpen))):g}")
        if denoise is not None:
            files["denoise"] = (None, f"{max(0.0, min(1.0, float(denoise))):g}")
        if face_enhancement is not None:
            files["face_enhancement"] = (None, "true" if face_enhancement else "false")
            if face_enhancement:
                fe_s = 0.8 if face_enhancement_strength is None else max(0.0, min(1.0, float(face_enhancement_strength)))
                fe_c = 0.2 if face_enhancement_creativity is None else max(0.0, min(1.0, float(face_enhancement_creativity)))
                files["face_enhancement_strength"] = (None, f"{fe_s:g}")
                files["face_enhancement_creativity"] = (None, f"{fe_c:g}")
        if subject_detection in {"all", "foreground", "background"}:
            files["subject_detection"] = (None, subject_detection)
        return endpoint, files

    if mid in {"topaz-standard-2", "topaz-text-refine"}:
        if strength is not None:
            files["strength"] = (None, f"{max(0.01, min(1.0, float(strength))):g}")
        if sharpen is not None:
            files["sharpen"] = (None, f"{max(0.0, min(1.0, float(sharpen))):g}")
        if denoise is not None:
            files["denoise"] = (None, f"{max(0.0, min(1.0, float(denoise))):g}")
        if fix_compression is not None:
            files["fix_compression"] = (None, f"{max(0.0, min(1.0, float(fix_compression))):g}")
        if face_enhancement is not None:
            files["face_enhancement"] = (None, "true" if face_enhancement else "false")
            if face_enhancement:
                fe_s = 0.8 if face_enhancement_strength is None else max(0.0, min(1.0, float(face_enhancement_strength)))
                fe_c = 0.2 if face_enhancement_creativity is None else max(0.0, min(1.0, float(face_enhancement_creativity)))
                files["face_enhancement_strength"] = (None, f"{fe_s:g}")
                files["face_enhancement_creativity"] = (None, f"{fe_c:g}")
        if subject_detection in {"all", "foreground", "background"}:
            files["subject_detection"] = (None, subject_detection)
        return endpoint, files

    return endpoint, files


def _normalize_svg_aspect_ratio(aspect_ratio: str | None) -> str:
    raw = (aspect_ratio or "auto").strip().lower()
    if not raw or raw == "auto":
        return "auto"
    converted = raw.replace(":", "x")
    if converted not in _SVG_GENERATE_RATIOS:
        raise ProviderError("Format de vecteur SVG non pris en charge.")
    return converted


def build_ideogram_svg_request(
    operation: str,
    *,
    prompt: str = "",
    reference_image: tuple[bytes, str] | None = None,
    aspect_ratio: str = "auto",
    quality: str = "medium",
    mode: str = "auto",
    shape_density: float | None = None,
    color_variety: float | None = None,
    use_gradient: bool = True,
    seed: int | None = None,
) -> tuple[str, list[tuple[str, tuple[Any, ...]]]]:
    """Build multipart/form-data fields for Generate SVG or Vectorize (Image-to-SVG)."""
    op = (operation or "").strip().lower()
    if op == "generate":
        cleaned_prompt = (prompt or "").strip()
        if not cleaned_prompt:
            raise ProviderError("Un prompt est requis pour générer un vecteur SVG.")
        ratio = _normalize_svg_aspect_ratio(aspect_ratio)
        qual = (quality or "medium").strip().lower()
        if qual not in {"low", "medium", "high"}:
            raise ProviderError("La qualité SVG doit être low, medium ou high.")
        parts: list[tuple[str, tuple[Any, ...]]] = [
            ("prompt", (None, cleaned_prompt[:9500])),
            ("aspect_ratio", (None, ratio)),
            ("quality", (None, qual)),
            ("use_gradient", (None, "true" if use_gradient else "false")),
        ]
        if seed is not None:
            parts.append(("seed", (None, str(int(seed)))))
        if reference_image is not None:
            ref_bytes, ref_mime, ref_ext = _validate_raster_source(reference_image, "la génération SVG avec référence")
            parts.append(("images", (f"reference.{ref_ext}", ref_bytes, ref_mime)))
        return "https://api.ideogram.ai/v2/svg/generate/ideogram-vector-1", parts

    if op == "vectorize":
        ref_bytes, ref_mime, ref_ext = _validate_raster_source(reference_image, "la vectorisation Image vers SVG")
        vec_mode = (mode or "auto").strip().lower()
        if vec_mode not in {"auto", "simple", "detailed"}:
            raise ProviderError("Le mode de vectorisation SVG doit être auto, simple ou detailed.")
        parts = [
            ("image", (f"source.{ref_ext}", ref_bytes, ref_mime)),
            ("mode", (None, vec_mode)),
            ("use_gradient", (None, "true" if use_gradient else "false")),
        ]
        if shape_density is not None:
            parts.append(("shape_density", (None, f"{max(1.0, min(16.0, float(shape_density))):g}")))
        if color_variety is not None:
            parts.append(("color_variety", (None, f"{max(1.0, min(8.0, float(color_variety))):g}")))
        return "https://api.ideogram.ai/v2/svg/vectorize/ideogram-vector-1", parts

    raise ProviderError("Opération vectorielle SVG inconnue.")


def _extract_safe_result_url(payload: dict[str, Any], out_metadata: dict[str, Any] | None = None) -> str:
    data = payload.get("data") or []
    first_item = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
    if first_item.get("is_image_safe") is False:
        raise ProviderError("Ideogram a bloqué le résultat suite au contrôle de sécurité du contenu.")

    if out_metadata is not None:
        for dim_key in ("width", "height"):
            val = first_item.get(dim_key) if isinstance(first_item.get(dim_key), int) else payload.get(dim_key)
            if isinstance(val, int) and val > 0:
                out_metadata[dim_key] = val
        res_str = first_item.get("resolution") or payload.get("resolution")
        if isinstance(res_str, str) and "x" in res_str and ("width" not in out_metadata or "height" not in out_metadata):
            w_s, h_s = res_str.lower().split("x", 1)
            if w_s.isdigit() and h_s.isdigit():
                out_metadata["width"] = int(w_s)
                out_metadata["height"] = int(h_s)

    raw_url = first_item.get("url") or payload.get("url")
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ProviderError("Ideogram n'a pas renvoyé d'URL de résultat téléchargeable.")
    return raw_url.strip()


async def execute_ideogram_upscale(
    settings: Any,
    model_id: str,
    reference_image: tuple[bytes, str],
    *,
    require_key_fn: Any,
    resolve_payload_fn: Any,
    check_download_url_fn: Any,
    out_metadata: dict[str, Any] | None = None,
    **upscale_kwargs: Any,
) -> tuple[bytes, str]:
    """Run an Ideogram v2 upscale job, poll if needed, and download the high-res output safely."""
    key = require_key_fn(settings, "ideogram_api_key", "Ideogram")
    endpoint, files = build_ideogram_upscale_request(model_id, reference_image, **upscale_kwargs)
    client_cls = _resolve_async_client_cls()

    try:
        async with client_cls(timeout=_UPSCALE_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(endpoint, headers={"Api-Key": key}, files=files)
            _check_response(response, "Ideogram Upscale")
            payload = await resolve_payload_fn(
                client, _json(response, "Ideogram Upscale"), key, max_polls=_UPSCALE_MAX_POLLS
            )

        raw_url = _extract_safe_result_url(payload, out_metadata)
        url = await check_download_url_fn(settings, raw_url)

        async with client_cls(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=False) as dl_client:
            async with dl_client.stream("GET", url) as download:
                _check_response(download, "Téléchargement Ideogram Upscale")
                mime_type = download.headers.get("content-type", "").split(";")[0].strip().lower()
                if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
                    raise ProviderError("Ideogram Upscale a renvoyé un format d'image non pris en charge.")
                size_header = download.headers.get("content-length", "")
                if size_header.isdigit() and int(size_header) > _MAX_UPSCALE_IMAGE_BYTES:
                    raise ProviderError("L'image agrandie dépasse la limite de 60 Mio.")
                content = bytearray()
                async for chunk in download.aiter_bytes():
                    if len(content) + len(chunk) > _MAX_UPSCALE_IMAGE_BYTES:
                        raise ProviderError("L'image agrandie dépasse la limite de 60 Mio.")
                    content.extend(chunk)

        image = bytes(content)
        detected = _detect_image_mime(image)
        if detected:
            mime_type = detected
        if not _image_signature_matches(image, mime_type):
            raise ProviderError("Le fichier renvoyé par Ideogram Upscale n'est pas une image valide.")
        return image, mime_type
    except httpx.TimeoutException:
        raise ProviderError("L'agrandissement Ideogram a dépassé le délai autorisé.") from None
    except httpx.HTTPError:
        raise ProviderError("Impossible de joindre Ideogram pour l'agrandissement d'image.") from None


async def execute_ideogram_svg(
    settings: Any,
    operation: str,
    *,
    require_key_fn: Any,
    resolve_payload_fn: Any,
    check_download_url_fn: Any,
    out_metadata: dict[str, Any] | None = None,
    **svg_kwargs: Any,
) -> tuple[bytes, str]:
    """Run Ideogram Vector 1.0 (generate-svg or image-to-svg), poll async result, download and sanitize SVG."""
    key = require_key_fn(settings, "ideogram_api_key", "Ideogram")
    endpoint, multipart_parts = build_ideogram_svg_request(operation, **svg_kwargs)
    client_cls = _resolve_async_client_cls()

    try:
        async with client_cls(timeout=_UPSCALE_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(endpoint, headers={"Api-Key": key}, files=multipart_parts)
            _check_response(response, "Ideogram Vector")
            payload = await resolve_payload_fn(
                client, _json(response, "Ideogram Vector"), key, max_polls=_SVG_MAX_POLLS
            )

        raw_url = _extract_safe_result_url(payload, out_metadata)
        url = await check_download_url_fn(settings, raw_url)

        max_svg = 10 * 1024 * 1024
        async with client_cls(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=False) as dl_client:
            async with dl_client.stream("GET", url) as download:
                _check_response(download, "Téléchargement SVG Ideogram")
                mime_header = download.headers.get("content-type", "").split(";")[0].strip().lower()
                if mime_header and mime_header not in {
                    "image/svg+xml",
                    "text/xml",
                    "application/xml",
                    "text/plain",
                    "application/octet-stream",
                }:
                    raise ProviderError("Ideogram Vector a renvoyé un type MIME inattendu.")
                size_header = download.headers.get("content-length", "")
                if size_header.isdigit() and int(size_header) > max_svg:
                    raise ProviderError("Le fichier SVG dépasse la limite de 10 Mio.")
                raw_svg = bytearray()
                async for chunk in download.aiter_bytes():
                    if len(raw_svg) + len(chunk) > max_svg:
                        raise ProviderError("Le fichier SVG dépasse la limite de 10 Mio.")
                    raw_svg.extend(chunk)

        clean_svg = sanitize_svg_bytes(bytes(raw_svg))
        return clean_svg, "image/svg+xml"
    except httpx.TimeoutException:
        raise ProviderError("La génération vectorielle SVG Ideogram a dépassé le délai autorisé.") from None
    except httpx.HTTPError:
        raise ProviderError("Impossible de joindre Ideogram pour la génération vectorielle SVG.") from None
