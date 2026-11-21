"""Endpoints API pour la synthèse vocale (TTS Google) et la dictée vocale (STT Mistral Voxtral / Google)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..config import Settings
from ..deps import current_user, get_settings
from ..google_cloud import ProviderError
from ..models import User
from ..voice import (
    MAX_STT_AUDIO_BYTES,
    has_stt_access,
    has_tts_access,
    synthesize_speech_google,
    transcribe_audio,
)


router = APIRouter(tags=["voice"])
_logger = logging.getLogger("uvicorn.error")


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=25000)
    voice: str | None = Field(default=None, max_length=40)
    tone: str | None = Field(default=None, max_length=160)


@router.post("/api/voice/tts")
async def tts_endpoint(
    body: TTSRequest,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    if not has_tts_access(settings):
        raise HTTPException(
            503,
            "La synthèse vocale nécessite GOOGLE_API_KEY (ou Google Cloud Vertex AI) configurée côté serveur.",
        )
    effective_voice = (body.voice or "").strip() or getattr(user, "default_voice", None)
    try:
        audio_bytes, media_type = await synthesize_speech_google(
            settings,
            body.text,
            voice=effective_voice,
            tone=body.tone,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        _logger.warning("Voice TTS failed: %s", exc)
        raise HTTPException(502, str(exc)) from exc

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/api/voice/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...),
    language: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    _user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    if not has_stt_access(settings):
        raise HTTPException(
            503,
            "La dictée vocale nécessite MISTRAL_API_KEY (Voxtral) ou GOOGLE_API_KEY (Gemini Audio).",
        )
    audio_bytes = await file.read(MAX_STT_AUDIO_BYTES + 1)
    if len(audio_bytes) > MAX_STT_AUDIO_BYTES:
        raise HTTPException(413, "L'enregistrement audio dépasse la limite autorisée de 15 Mo.")

    try:
        result = await transcribe_audio(
            settings,
            audio_bytes,
            filename=file.filename or "dictation.webm",
            content_type=file.content_type,
            language=language,
            provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        _logger.warning("Voice STT failed: %s", exc)
        raise HTTPException(502, str(exc)) from exc

    return result
