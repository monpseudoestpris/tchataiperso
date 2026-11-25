import re
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .. import providers
from ..config import Settings
from ..deps import claim, current_user, get_conversation, get_sessions, get_settings, get_upload_dir
from ..google_cloud import has_llm_access, is_google_model
from ..models import Attachment, GeneratedImage, Message, User, now
from ..schemas import CreateImage, CreateSvgRequest, ImproveImagePrompt, UpscaleImageRequest
from ..serializers import (IMAGE_ASPECT_RATIOS, MAX_GENERATED_IMAGES,
                          generated_image_json, message_json)

_SVG_SAFE_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


router = APIRouter(tags=["images"])


@router.get("/api/images/models")
def list_image_models(
    force_refresh: bool = False,
    settings: Settings = Depends(get_settings),
):
    if settings.demo_mode:
        return []
    return settings.get_image_models(force_refresh=force_refresh)


@router.get("/api/images/upscale-models")
def list_upscale_models(
    settings: Settings = Depends(get_settings),
):
    if settings.demo_mode:
        return []
    return list(providers.IDEOGRAM_UPSCALE_MODELS)


@router.get("/api/images")
def list_generated_images(
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    with sessions() as db:
        return [
            generated_image_json(item)
            for item in db.scalars(
                select(GeneratedImage)
                .where(GeneratedImage.user_id == user.id)
                .order_by(GeneratedImage.created_at.desc(), GeneratedImage.id.desc())
            )
        ]


def _resolve_reference_image(
    reference_image_data: str | None,
    source_image_id: str | None,
    upload_dir,
    user: User,
    sessions: sessionmaker,
) -> tuple[bytes, str] | None:
    if reference_image_data:
        try:
            return providers.decode_reference_image(reference_image_data)
        except providers.ProviderError as exc:
            raise HTTPException(422, str(exc)) from exc
    if source_image_id:
        with sessions() as db:
            item = db.scalar(
                select(GeneratedImage).where(
                    GeneratedImage.id == source_image_id,
                    GeneratedImage.user_id == user.id,
                )
            )
            if not item or not (upload_dir / item.storage_name).is_file():
                raise HTTPException(404, "Image source introuvable")
            if item.mime_type == "image/svg+xml":
                raise HTTPException(
                    400,
                    "Un fichier vectoriel SVG ne peut pas être utilisé directement comme image source matricielle (PNG, JPEG ou WEBP requis).",
                )
            raw_bytes = (upload_dir / item.storage_name).read_bytes()
        detected_mime = providers._detect_image_mime(raw_bytes) or item.mime_type
        if not providers._image_signature_matches(raw_bytes, detected_mime):
            raise HTTPException(422, "L'image source sélectionnée n'est pas valide.")
        return raw_bytes, detected_mime
    return None


def _resolve_mask_image(
    mask_image_data: str | None,
    reference_image: tuple[bytes, str] | None,
) -> tuple[bytes, str] | None:
    if not mask_image_data:
        return None
    if reference_image is None:
        raise HTTPException(400, "An input reference image is required when using an inpaint mask.")
    try:
        return providers.decode_reference_image(mask_image_data)
    except providers.ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc


def _build_generate_kwargs(
    reference_image: tuple[bytes, str] | None,
    mask_image: tuple[bytes, str] | None,
    image_weight: int | None,
    edit_action: str | None = None,
    transparent_background: bool = False,
    out_metadata: dict[str, Any] | None = None,
) -> dict:
    gen_kwargs: dict = {}
    if reference_image is not None:
        gen_kwargs["reference_image"] = reference_image
        if mask_image is not None:
            gen_kwargs["mask_image"] = mask_image
        elif image_weight is not None:
            gen_kwargs["image_weight"] = image_weight
    if edit_action is not None:
        gen_kwargs["edit_action"] = edit_action
    if transparent_background:
        gen_kwargs["transparent_background"] = True
    if out_metadata is not None:
        gen_kwargs["out_metadata"] = out_metadata
    return gen_kwargs


def _validate_edit_request(
    body: CreateImage,
    is_ideogram: bool,
    reference_image: tuple[bytes, str] | None,
    mask_image: tuple[bytes, str] | None,
) -> None:
    if (
        reference_image is not None
        or mask_image is not None
        or body.edit_action is not None
        or body.transparent_background
    ) and not is_ideogram:
        raise HTTPException(
            400,
            "La retouche d’image et ces outils spécialisés sont uniquement disponibles avec les modèles Ideogram.",
        )
    if (
        body.edit_action in {"remix", "inpaint", "remove_background", "replace_background", "remove_object", "layerize"}
        and reference_image is None
    ):
        raise HTTPException(400, "Une image source est requise pour ce mode d’édition.")
    if body.edit_action in {"inpaint", "remove_object"} and mask_image is None:
        raise HTTPException(400, "Un masque est requis pour ce mode d’édition.")


def _fallback_prompt_for_action(prompt: str, edit_action: str | None) -> str:
    cleaned = (prompt or "").strip()
    if cleaned:
        return cleaned
    return {
        "remove_background": "Suppression de l’arrière-plan (Ideogram 1.0)",
        "remove_object": "Suppression d’objet (Ideogram 1.0)",
        "layerize": "Extraction de calques texte — Layerize (Ideogram 3.0)",
    }.get(edit_action or "", "Image générée")


@router.post("/api/images/improve")
async def improve_image(
    body: ImproveImagePrompt,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    model = (
        (body.model.strip() if body.model and body.model.strip() else None)
        or settings.image_prompt_model
        or "google/gemini-4-argon"
        or settings.default_model
    )
    if settings.demo_mode or not has_llm_access(settings, model):
        raise HTTPException(503, "L'amélioration du prompt nécessite une clé LLM_API_KEY ou Google Cloud et le mode IA réel")
    upload_dir = get_upload_dir(request)
    reference_image = _resolve_reference_image(
        body.reference_image_data, body.source_image_id, upload_dir, user, sessions
    )
    improve_kwargs: dict = {}
    if reference_image is not None:
        improve_kwargs["reference_image"] = reference_image
    if body.is_svg:
        improve_kwargs["is_svg"] = True
    elif body.is_edit or reference_image is not None:
        improve_kwargs["is_edit"] = True
    try:
        prompt = await providers.improve_image_prompt(
            settings, model, body.prompt, body.style_keywords, body.negative_prompt, **improve_kwargs
        )
    except providers.ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"prompt": prompt}


def _image_model_label(model_id: str) -> str:
    return {
        "ideogram-4-5": "Ideogram 4.5",
        "ideogram-4": "Ideogram 4.0",
        "ideogram-3": "Ideogram 3.0",
        "ideogram-3-transparent": "Ideogram 3.0 Transparent",
        "ideogram": "Ideogram Auto",
        "ideogram-auto": "Ideogram Auto",
    }.get(model_id, model_id)


@router.post("/api/images", status_code=201)
async def create_studio_image(
    body: CreateImage,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    is_ideogram = providers.is_ideogram_model(body.model)
    is_google = is_google_model(body.model)
    if is_ideogram and not settings.enabled(settings.ideogram_api_key):
        raise HTTPException(503, "La génération d'image avec Ideogram nécessite IDEOGRAM_API_KEY et un mode IA réel")
    if is_google and (settings.demo_mode or not settings.google_cloud_enabled):
        raise HTTPException(
            503,
            "Les modèles d'image Gemini passent exclusivement par Google Cloud (Vertex AI) ; vérifiez GOOGLE_CLOUD_MODE et GOOGLE_CLOUD_PROJECT.",
        )
    if not is_ideogram and not is_google and not has_llm_access(settings, body.model):
        raise HTTPException(503, "La génération d'image avec ce modèle nécessite LLM_API_KEY et un mode IA réel")
    if body.aspect_ratio not in IMAGE_ASPECT_RATIOS:
        raise HTTPException(422, "Ratio d'image non pris en charge")
    reference_image = _resolve_reference_image(
        body.reference_image_data, body.source_image_id, upload_dir, user, sessions
    )
    mask_image = _resolve_mask_image(body.mask_image_data, reference_image)
    _validate_edit_request(body, is_ideogram, reference_image, mask_image)
    with sessions() as db:
        count = db.scalar(select(func.count()).select_from(GeneratedImage).where(GeneratedImage.user_id == user.id))
        if count >= MAX_GENERATED_IMAGES:
            raise HTTPException(422, f"Limite de {MAX_GENERATED_IMAGES} images sauvegardées atteinte ; supprimez d'anciennes images")
    lock = claim(request, user.id, "image-studio")
    await lock.acquire()
    path = None
    try:
        out_metadata: dict[str, Any] | None = {} if body.edit_action == "layerize" else None
        gen_kwargs = _build_generate_kwargs(
            reference_image,
            mask_image,
            body.image_weight,
            edit_action=body.edit_action,
            transparent_background=body.transparent_background,
            out_metadata=out_metadata,
        )
        content, mime = await providers.generate_image(
            settings, body.prompt, body.aspect_ratio, body.negative_prompt, model=body.model, **gen_kwargs
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
        model_prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", body.model if is_ideogram else body.model.split("/")[-1])[:24]
        effective_prompt = _fallback_prompt_for_action(body.prompt, body.edit_action)
        with sessions() as db:
            image_id = str(uuid4())
            item = GeneratedImage(
                id=image_id,
                user_id=user.id,
                prompt=effective_prompt,
                aspect_ratio=body.aspect_ratio,
                filename=f"{model_prefix}-{image_id[:8]}.{extension}",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            result = generated_image_json(item)
            if body.edit_action is not None:
                result["edit_action"] = body.edit_action
            if out_metadata and "text_blocks" in out_metadata:
                result["text_blocks"] = out_metadata["text_blocks"]
            return result
    except providers.ProviderError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.release()


@router.post("/api/images/upscale", status_code=201)
async def create_upscaled_image(
    body: UpscaleImageRequest,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if settings.demo_mode or not settings.enabled(settings.ideogram_api_key):
        raise HTTPException(503, "L'upscale d'image nécessite IDEOGRAM_API_KEY et un mode IA réel")
    upload_dir = get_upload_dir(request)
    reference_image = _resolve_reference_image(
        body.reference_image_data, body.source_image_id, upload_dir, user, sessions
    )
    if reference_image is None:
        raise HTTPException(400, "Une image source est requise pour l'agrandissement.")

    source_ratio = "1:1"
    source_prompt = ""
    if body.source_image_id:
        with sessions() as db:
            src_row = db.scalar(
                select(GeneratedImage).where(
                    GeneratedImage.id == body.source_image_id,
                    GeneratedImage.user_id == user.id,
                )
            )
            if src_row:
                source_ratio = src_row.aspect_ratio or "1:1"
                source_prompt = src_row.prompt or ""

    with sessions() as db:
        count = db.scalar(select(func.count()).select_from(GeneratedImage).where(GeneratedImage.user_id == user.id))
        if count >= MAX_GENERATED_IMAGES:
            raise HTTPException(422, f"Limite de {MAX_GENERATED_IMAGES} images sauvegardées atteinte ; supprimez d'anciennes images")

    spec = providers.UPSCALE_MODELS_BY_ID.get(body.model, {})
    model_name = spec.get("name", body.model)
    scale_badge = body.resolution_tier if body.model == "nano-banana-pro" else body.upscale_factor.upper()
    upscale_kwargs = {
        k: v
        for k, v in body.model_dump(
            exclude={"model", "reference_image_data", "source_image_id"},
            exclude_none=True,
        ).items()
    }

    lock = claim(request, user.id, "image-studio")
    await lock.acquire()
    path = None
    try:
        out_meta: dict[str, Any] = {}
        content, mime = await providers.upscale_image(
            settings,
            body.model,
            reference_image,
            out_metadata=out_meta,
            **upscale_kwargs,
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        extension = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", f"upscale-{body.model}")[:28]
        dim_suffix = (
            f" ({out_meta['width']}×{out_meta['height']} px)"
            if "width" in out_meta and "height" in out_meta
            else ""
        )
        effective_prompt = (
            body.prompt
            or (f"Upscale {scale_badge} ({model_name}){dim_suffix} — {source_prompt}" if source_prompt else f"Upscale {scale_badge} ({model_name}){dim_suffix}")
        )[:4000]
        with sessions() as db:
            image_id = str(uuid4())
            item = GeneratedImage(
                id=image_id,
                user_id=user.id,
                prompt=effective_prompt,
                aspect_ratio=source_ratio[:16],
                filename=f"{safe_prefix}-{image_id[:8]}.{extension}",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            result = generated_image_json(item)
            result["edit_action"] = "upscale"
            if "width" in out_meta and "height" in out_meta:
                result["output_width"] = out_meta["width"]
                result["output_height"] = out_meta["height"]
            return result
    except providers.ProviderError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.release()


@router.post("/api/images/svg", status_code=201)
async def create_svg_studio_image(
    body: CreateSvgRequest,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    if settings.demo_mode or not settings.enabled(settings.ideogram_api_key):
        raise HTTPException(503, "Les outils vectoriels SVG nécessitent IDEOGRAM_API_KEY et un mode IA réel")
    upload_dir = get_upload_dir(request)
    reference_image = _resolve_reference_image(
        body.reference_image_data, body.source_image_id, upload_dir, user, sessions
    )
    if body.operation == "vectorize" and reference_image is None:
        raise HTTPException(400, "Une image source est requise pour convertir une image en SVG.")

    source_ratio = "auto"
    source_prompt = ""
    if body.source_image_id:
        with sessions() as db:
            src_row = db.scalar(
                select(GeneratedImage).where(
                    GeneratedImage.id == body.source_image_id,
                    GeneratedImage.user_id == user.id,
                )
            )
            if src_row:
                source_ratio = src_row.aspect_ratio or "auto"
                source_prompt = src_row.prompt or ""

    with sessions() as db:
        count = db.scalar(select(func.count()).select_from(GeneratedImage).where(GeneratedImage.user_id == user.id))
        if count >= MAX_GENERATED_IMAGES:
            raise HTTPException(422, f"Limite de {MAX_GENERATED_IMAGES} images sauvegardées atteinte ; supprimez d'anciennes images")

    lock = claim(request, user.id, "image-studio")
    await lock.acquire()
    path = None
    try:
        out_meta: dict[str, Any] = {}
        content, mime = await providers.generate_svg_image(
            settings,
            body.operation,
            prompt=body.prompt,
            reference_image=reference_image,
            aspect_ratio=body.aspect_ratio,
            quality=body.quality,
            mode=body.mode,
            shape_density=body.shape_density,
            color_variety=body.color_variety,
            use_gradient=body.use_gradient,
            seed=body.seed,
            out_metadata=out_meta,
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        mode_labels = {"auto": "Auto", "simple": "Simple", "detailed": "Détaillé"}
        if body.operation == "generate":
            effective_prompt = body.prompt
            stored_ratio = body.aspect_ratio[:16]
            prefix = "ideogram-svg"
        else:
            m_lbl = mode_labels.get(body.mode, body.mode)
            effective_prompt = (
                f"Vectorisation SVG ({m_lbl}) — {source_prompt}"
                if source_prompt
                else f"Vectorisation Image → SVG ({m_lbl}, Ideogram Vector 1.0)"
            )[:4000]
            stored_ratio = source_ratio[:16]
            prefix = "ideogram-vectorize"

        with sessions() as db:
            image_id = str(uuid4())
            item = GeneratedImage(
                id=image_id,
                user_id=user.id,
                prompt=effective_prompt,
                aspect_ratio=stored_ratio,
                filename=f"{prefix}-{image_id[:8]}.svg",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
            )
            db.add(item)
            db.commit()
            db.refresh(item)
            result = generated_image_json(item)
            result["edit_action"] = "generate_svg" if body.operation == "generate" else "image_to_svg"
            return result
    except providers.ProviderError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.release()


@router.get("/api/images/{image_id}/file")
def generated_image_file(
    image_id: str,
    download: bool = False,
    request: Request = None,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(select(GeneratedImage).where(GeneratedImage.id == image_id, GeneratedImage.user_id == user.id))
        if not item or not (upload_dir / item.storage_name).is_file():
            raise HTTPException(404, "Image introuvable")
        resp_headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
        if item.mime_type == "image/svg+xml":
            resp_headers["Content-Security-Policy"] = _SVG_SAFE_CSP
        return FileResponse(
            upload_dir / item.storage_name,
            media_type=item.mime_type,
            filename=item.filename,
            content_disposition_type="attachment" if download else "inline",
            headers=resp_headers,
        )


@router.delete("/api/images/{image_id}", status_code=204)
def delete_generated_image(
    image_id: str,
    request: Request,
    user: User = Depends(current_user),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    with sessions() as db:
        item = db.scalar(
            select(GeneratedImage)
            .where(GeneratedImage.id == image_id, GeneratedImage.user_id == user.id)
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "Image introuvable")
        storage_name = item.storage_name
        db.delete(item)
        db.commit()
    (upload_dir / storage_name).unlink(missing_ok=True)
    return Response(status_code=204)


@router.post("/api/conversations/{conversation_id}/images", status_code=201)
async def create_image(
    conversation_id: str,
    body: CreateImage,
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    sessions: sessionmaker = Depends(get_sessions),
):
    upload_dir = get_upload_dir(request)
    is_ideogram = providers.is_ideogram_model(body.model)
    is_google = is_google_model(body.model)
    if is_ideogram and not settings.enabled(settings.ideogram_api_key):
        raise HTTPException(503, "La génération d'image avec Ideogram nécessite IDEOGRAM_API_KEY et un mode IA réel")
    if is_google and (settings.demo_mode or not settings.google_cloud_enabled):
        raise HTTPException(
            503,
            "Les modèles d'image Gemini passent exclusivement par Google Cloud (Vertex AI) ; vérifiez GOOGLE_CLOUD_MODE et GOOGLE_CLOUD_PROJECT.",
        )
    if not is_ideogram and not is_google and not has_llm_access(settings, body.model):
        raise HTTPException(503, "La génération d'image avec ce modèle nécessite LLM_API_KEY et un mode IA réel")
    if body.aspect_ratio not in IMAGE_ASPECT_RATIOS:
        raise HTTPException(422, "Ratio d'image non pris en charge")
    reference_image = _resolve_reference_image(
        body.reference_image_data, body.source_image_id, upload_dir, user, sessions
    )
    mask_image = _resolve_mask_image(body.mask_image_data, reference_image)
    _validate_edit_request(body, is_ideogram, reference_image, mask_image)
    lock = claim(request, user.id, conversation_id)
    await lock.acquire()
    path = None
    try:
        with sessions() as db:
            get_conversation(db, conversation_id, user.id)
        gen_kwargs = _build_generate_kwargs(
            reference_image,
            mask_image,
            body.image_weight,
            edit_action=body.edit_action,
            transparent_background=body.transparent_background,
        )
        content, mime = await providers.generate_image(
            settings, body.prompt, body.aspect_ratio, body.negative_prompt, model=body.model, **gen_kwargs
        )
        storage_name = str(uuid4())
        path = upload_dir / storage_name
        path.write_bytes(content)
        model_label = _image_model_label(body.model) if is_ideogram else body.model
        model_prefix = re.sub(r"[^a-zA-Z0-9_-]", "-", body.model if is_ideogram else body.model.split("/")[-1])[:24]
        effective_prompt = _fallback_prompt_for_action(body.prompt, body.edit_action)
        with sessions() as db:
            conversation = get_conversation(db, conversation_id, user.id)
            prompt_prefix = "Modifie l'image :" if reference_image is not None else "Génère une image :"
            answer_prefix = "Image modifiée avec" if reference_image is not None else "Image générée avec"
            prompt = Message(conversation_id=conversation_id, role="user", content=f"{prompt_prefix} {effective_prompt}")
            answer = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=f"{answer_prefix} {model_label} : {effective_prompt}",
            )
            db.add_all([prompt, answer])
            db.flush()
            extension = {"image/png": "png", "image/webp": "webp", "image/gif": "gif"}.get(mime, "jpg")
            attachment = Attachment(
                user_id=user.id,
                filename=f"{model_prefix}.{extension}",
                mime_type=mime,
                size=len(content),
                storage_name=storage_name,
                message_id=answer.id,
            )
            db.add(attachment)
            conversation.updated_at = now()
            db.commit()
            db.refresh(answer)
            return message_json(answer)
    except providers.ProviderError as exc:
        if path:
            path.unlink(missing_ok=True)
        raise HTTPException(502, str(exc)) from exc
    except Exception:
        if path:
            path.unlink(missing_ok=True)
        raise
    finally:
        lock.release()

