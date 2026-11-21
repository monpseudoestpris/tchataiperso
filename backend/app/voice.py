"""Services de synthèse vocale (Google Gemini TTS) et de dictée vocale (Mistral Voxtral / Google Gemini STT)."""

from __future__ import annotations

import base64
import io
import re
import wave
from typing import Any

import httpx

from .google_cloud import (
    ProviderError,
    _GEMINI_NATIVE_BASE_URL,
    _extract_safe_error_detail,
    check_response,
    clean_secret,
    get_google_cloud_access_token,
    json_body,
    normalize_google_model_id,
    resolve_google_cloud_mode,
    vertex_api_host,
)
from .voice_sanitize import prepare_text_for_speech, split_speech_chunks


MISTRAL_TRANSCRIPTIONS_URL = "https://api.mistral.ai/v1/audio/transcriptions"
MAX_STT_AUDIO_BYTES = 15 * 1024 * 1024  # 15 Mo
_DEFAULT_SAMPLE_RATE = 24000
_RATE_RE = re.compile(r"rate=(\d+)", flags=re.IGNORECASE)

GOOGLE_TTS_VOICES: list[dict[str, str]] = [
    {"id": "Aoede", "name": "Aoede", "tone": "Légère & naturelle"},
    {"id": "Kore", "name": "Kore", "tone": "Ferme & claire"},
    {"id": "Zephyr", "name": "Zephyr", "tone": "Lumineuse & enjouée"},
    {"id": "Puck", "name": "Puck", "tone": "Vive & dynamique"},
    {"id": "Charon", "name": "Charon", "tone": "Grave & informative"},
    {"id": "Fenrir", "name": "Fenrir", "tone": "Expressive & intense"},
    {"id": "Leda", "name": "Leda", "tone": "Jeune & fluide"},
    {"id": "Orus", "name": "Orus", "tone": "Posée & professionnelle"},
    {"id": "Sulafat", "name": "Sulafat", "tone": "Chaleureuse & douce"},
    {"id": "Callirrhoe", "name": "Callirrhoe", "tone": "Décontractée & aisée"},
    {"id": "Autonoe", "name": "Autonoe", "tone": "Claire & lumineuse"},
    {"id": "Enceladus", "name": "Enceladus", "tone": "Soufflée & apaisante"},
    {"id": "Iapetus", "name": "Iapetus", "tone": "Nette & articulée"},
    {"id": "Umbriel", "name": "Umbriel", "tone": "Détendue & naturelle"},
    {"id": "Algieba", "name": "Algieba", "tone": "Veloutée & fluide"},
    {"id": "Despina", "name": "Despina", "tone": "Douce & harmonieuse"},
    {"id": "Erinome", "name": "Erinome", "tone": "Précise & cristalline"},
    {"id": "Algenib", "name": "Algenib", "tone": "Rauque & profonde"},
    {"id": "Rasalgethi", "name": "Rasalgethi", "tone": "Posée & didactique"},
    {"id": "Laomedeia", "name": "Laomedeia", "tone": "Rythmée & enthousiaste"},
    {"id": "Achernar", "name": "Achernar", "tone": "Tendre & délicate"},
    {"id": "Alnilam", "name": "Alnilam", "tone": "Assurée & directe"},
    {"id": "Schedar", "name": "Schedar", "tone": "Régulière & équilibrée"},
    {"id": "Gacrux", "name": "Gacrux", "tone": "Mature & posée"},
    {"id": "Pulcherrima", "name": "Pulcherrima", "tone": "Franche & engagée"},
    {"id": "Achird", "name": "Achird", "tone": "Amicale & chaleureuse"},
    {"id": "Zubenelgenubi", "name": "Zubenelgenubi", "tone": "Simple & familière"},
    {"id": "Vindemiatrix", "name": "Vindemiatrix", "tone": "Bienveillante & calme"},
    {"id": "Sadachbia", "name": "Sadachbia", "tone": "Alerte & vivante"},
    {"id": "Sadaltager", "name": "Sadaltager", "tone": "Érudite & structurée"},
]

GOOGLE_TTS_TONES: list[dict[str, str]] = [
    {"id": "natural", "label": "Naturel", "prompt": ""},
    {"id": "warm", "label": "Chaleureux", "prompt": "Say warmly, smiling, and naturally in French"},
    {"id": "enthusiastic", "label": "Dynamique", "prompt": "Say with an energetic, enthusiastic, and lively tone in French"},
    {"id": "calm", "label": "Calme", "prompt": "Say in a calm, slow, soothing, and reassuring tone in French"},
    {"id": "teacher", "label": "Pédagogue", "prompt": "Explain clearly, patiently, and articulately like a friendly teacher in French"},
    {"id": "storyteller", "label": "Conteur", "prompt": "Narrate like an expressive, engaging storyteller in French"},
    {"id": "podcast", "label": "Podcast", "prompt": "Speak like a lively, charismatic French podcast host"},
    {"id": "whisper", "label": "Chuchoté", "prompt": "Say softly in a gentle whisper in French"},
]

_TONE_PROMPTS: dict[str, str] = {t["id"]: t["prompt"] for t in GOOGLE_TTS_TONES}

_VALID_VOICE_IDS = {v["id"] for v in GOOGLE_TTS_VOICES}

ALLOWED_AUDIO_MIME_TYPES: dict[str, str] = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/flac": ".flac",
}


def normalize_audio_mime(content_type: str | None, filename: str = "") -> str:
    """Normalise un Content-Type audio (retire codecs=...) et vérifie la liste blanche."""
    raw = (content_type or "").split(";", 1)[0].strip().lower()
    if raw in ALLOWED_AUDIO_MIME_TYPES:
        return "audio/mp4" if raw in ("audio/x-m4a", "audio/m4a") else ("audio/mpeg" if raw == "audio/mp3" else ("audio/wav" if raw in ("audio/x-wav", "audio/wave") else raw))

    ext = ""
    if "." in (filename or ""):
        ext = "." + filename.rsplit(".", 1)[-1].strip().lower()
    for mime, mapped_ext in ALLOWED_AUDIO_MIME_TYPES.items():
        if ext and ext == mapped_ext:
            return mime
    return ""


def pcm_to_wav(
    pcm_data: bytes,
    *,
    sample_rate: int = _DEFAULT_SAMPLE_RATE,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Encapsule un flux PCM linéaire 16-bit mono dans un fichier WAV standard."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _demo_wav_bytes() -> bytes:
    # 0.3 seconde de silence valide à 24 kHz 16-bit mono
    return pcm_to_wav(b"\x00\x00" * int(_DEFAULT_SAMPLE_RATE * 0.3), sample_rate=_DEFAULT_SAMPLE_RATE)


def has_tts_access(settings: Any) -> bool:
    """Indique si la synthèse vocale Google est utilisable."""
    if settings is None:
        return False
    refresh = getattr(settings, "refresh_from_env_file", None)
    if callable(refresh):
        refresh()
    if getattr(settings, "demo_mode", False):
        return True
    if clean_secret(getattr(settings, "google_api_key", None)):
        return True
    return resolve_google_cloud_mode(settings) is not None


def resolve_stt_provider(settings: Any, requested: str | None = None) -> str | None:
    """Détermine le fournisseur STT actif ('mistral', 'google' ou 'demo')."""
    if settings is None:
        return None
    refresh = getattr(settings, "refresh_from_env_file", None)
    if callable(refresh):
        refresh()
    if getattr(settings, "demo_mode", False):
        return "demo"

    has_mistral = bool(clean_secret(getattr(settings, "mistral_api_key", None)))
    has_google = bool(clean_secret(getattr(settings, "google_api_key", None))) or (
        resolve_google_cloud_mode(settings) is not None
    )

    pref = (requested or getattr(settings, "stt_provider", "auto") or "auto").strip().lower()
    if pref == "mistral":
        return "mistral" if has_mistral else ("google" if has_google else None)
    if pref == "google":
        return "google" if has_google else ("mistral" if has_mistral else None)

    # Mode auto : priorité Mistral Voxtral (spécialisé transcription rapide), repli Google Gemini
    if has_mistral:
        return "mistral"
    if has_google:
        return "google"
    return None


def has_stt_access(settings: Any) -> bool:
    return resolve_stt_provider(settings) is not None


def is_valid_voice_id(voice_id: str | None) -> bool:
    """Vérifie qu'un identifiant de voix TTS appartient au catalogue supporté."""
    return bool(voice_id and voice_id.strip() in _VALID_VOICE_IDS)


def resolve_voice_name(settings: Any, requested: str | None = None) -> str:
    candidate = (requested or "").strip()
    if candidate in _VALID_VOICE_IDS:
        return candidate
    default_voice = str(getattr(settings, "tts_default_voice", "Aoede") or "Aoede").strip()
    if default_voice in _VALID_VOICE_IDS:
        return default_voice
    return "Aoede"


def _usable_api_key(value: Any) -> str:
    cleaned = clean_secret(value)
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower.startswith("replace-with-") or lower in ("your-api-key", "changeme", "todo"):
        return ""
    return cleaned


async def _resolve_google_native_endpoints(
    settings: Any,
    model: str,
    *,
    is_tts: bool = False,
) -> list[tuple[str, dict[str, str], str]]:
    """Construit la liste ordonnée des cibles `(url, headers, kind)` pour Google.

    `kind` vaut `'gemini'` (`:generateContent`) ou `'cloud_tts'` (`texttospeech.googleapis.com`).
    Respecte `GOOGLE_CLOUD_MODE` : si `vertex_oauth` est actif, essaie Vertex AI en priorité
    (`us-central1` stable `v1` -> `global` -> preview `v1beta1` -> Cloud TTS Chirp3-HD),
    puis `GOOGLE_API_KEY` en secours.
    """
    bare_model = normalize_google_model_id(model, settings=settings, for_vertex_openapi=False)
    if is_tts:
        # Toujours tester le modèle GA stable `gemini-2.5-flash-tts` en tête, puis la variante preview
        ordered_models: list[tuple[str, str]] = []
        ga_model = bare_model.replace("-preview-tts", "-tts") if bare_model.endswith("-preview-tts") else bare_model
        preview_model = (
            bare_model
            if bare_model.endswith("-preview-tts")
            else (bare_model.replace("-tts", "-preview-tts") if bare_model.endswith("-tts") else "")
        )
        ordered_models.append((ga_model, "v1"))
        if preview_model and preview_model != ga_model:
            ordered_models.append((preview_model, "v1beta1"))
    else:
        ordered_models = [(bare_model, "v1")]

    google_key = _usable_api_key(getattr(settings, "google_api_key", None))
    gemini_api_targets: list[tuple[str, dict[str, str], str]] = []
    if google_key:
        seen_m: set[str] = set()
        for cand_model, _ver in ordered_models:
            if cand_model in seen_m:
                continue
            seen_m.add(cand_model)
            gemini_api_targets.append(
                (
                    f"{_GEMINI_NATIVE_BASE_URL}/models/{cand_model}:generateContent",
                    {
                        "x-goog-api-key": google_key,
                        "Content-Type": "application/json",
                    },
                    "gemini",
                )
            )

    mode = resolve_google_cloud_mode(settings)
    vertex_targets: list[tuple[str, dict[str, str], str]] = []
    if mode == "vertex_oauth":
        token, project = await get_google_cloud_access_token(settings)
        loc = str(getattr(settings, "google_cloud_location", "global") or "global").strip().lower() or "global"
        if is_tts:
            # Les modèles Gemini TTS sur Vertex AI sont prioritairement stables en us-central1
            locations = ["us-central1", loc] if loc != "us-central1" else ["us-central1", "global"]
        else:
            locations = [loc]

        for cand_model, api_ver in ordered_models:
            for candidate_loc in locations:
                host = vertex_api_host(candidate_loc)
                vertex_targets.append(
                    (
                        f"{host}/{api_ver}/projects/{project}/locations/{candidate_loc}/publishers/google/models/{cand_model}:generateContent",
                        {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        "gemini",
                    )
                )
        if is_tts:
            # Repli Google Cloud Text-to-Speech Chirp 3 HD (mêmes voix Aoede/Kore/Leda/Puck/Charon/Fenrir/Orus)
            vertex_targets.append(
                (
                    "https://texttospeech.googleapis.com/v1/text:synthesize",
                    {
                        "Authorization": f"Bearer {token}",
                        "x-goog-user-project": project,
                        "Content-Type": "application/json",
                    },
                    "cloud_tts",
                )
            )
    elif mode == "vertex_api_key":
        vkey = _usable_api_key(getattr(settings, "vertex_api_key", None))
        if vkey:
            for cand_model, api_ver in ordered_models:
                vertex_targets.append(
                    (
                        f"https://aiplatform.googleapis.com/{api_ver}/publishers/google/models/{cand_model}:generateContent",
                        {
                            "x-goog-api-key": vkey,
                            "Content-Type": "application/json",
                        },
                        "gemini",
                    )
                )

    if mode in ("vertex_oauth", "vertex_api_key"):
        targets = [*vertex_targets, *gemini_api_targets]
    else:
        targets = [*gemini_api_targets, *vertex_targets]

    if not targets:
        raise ProviderError(
            "La synthèse vocale Google nécessite GOOGLE_API_KEY (ou une configuration Google Cloud Vertex AI active)."
        )
    return targets


async def _resolve_google_native_endpoint(settings: Any, model: str) -> tuple[str, dict[str, str]]:
    targets = await _resolve_google_native_endpoints(settings, model, is_tts=False)
    url, headers, _kind = targets[0]
    return url, headers


def _extract_audio_part(data: dict[str, Any]) -> tuple[bytes, str]:
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise ProviderError("Google TTS n'a renvoyé aucune piste audio.")
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                mime = str(inline.get("mimeType") or inline.get("mime_type") or "audio/L16;codec=pcm;rate=24000")
                try:
                    raw = base64.b64decode(inline["data"])
                except Exception as exc:
                    raise ProviderError("Google TTS a renvoyé des données audio base64 invalides.") from exc
                if raw:
                    return raw, mime
    raise ProviderError("Google TTS n'a renvoyé aucun contenu audio exploitable.")


def _parse_sample_rate(mime_type: str) -> int:
    match = _RATE_RE.search(mime_type or "")
    if match:
        try:
            rate = int(match.group(1))
            if 8000 <= rate <= 96000:
                return rate
        except ValueError:
            pass
    return _DEFAULT_SAMPLE_RATE


def _build_tone_prefix(tone: str | None) -> str:
    """Construit le préfixe d'intention vocale pour Gemini TTS (vide si naturel)."""
    raw = " ".join((tone or "").replace("\n", " ").replace("\r", " ").split()).strip()
    if not raw or raw.lower() == "natural":
        return ""
    preset = _TONE_PROMPTS.get(raw.lower())
    if preset is not None:
        return f"{preset}: " if preset else ""
    # Ton libre utilisateur : nettoyer les caractères de contrôle / ponctuation excessive
    safe_custom = re.sub(r"[`\"<>\{\}\[\]]", "", raw)[:120].strip()
    if not safe_custom:
        return ""
    return f"Speak in French with this tone ({safe_custom}): "


async def synthesize_speech_google(
    settings: Any,
    text: str,
    *,
    voice: str | None = None,
    tone: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str]:
    """Filtre le texte Markdown et génère un audio WAV via Google Gemini TTS."""
    clean_text = prepare_text_for_speech(text)
    if not clean_text:
        raise ValueError("Aucun texte lisible à synthétiser après filtrage des éléments non parlés.")

    if getattr(settings, "demo_mode", False):
        return _demo_wav_bytes(), "audio/wav"

    voice_name = resolve_voice_name(settings, voice)
    tone_prefix = _build_tone_prefix(tone)
    tts_model = str(getattr(settings, "tts_model", "gemini-2.5-flash-tts") or "gemini-2.5-flash-tts").strip()
    targets = await _resolve_google_native_endpoints(settings, tts_model, is_tts=True)
    chunks = split_speech_chunks(clean_text, max_chunk_chars=1600)

    pcm_segments: list[bytes] = []
    detected_rate = _DEFAULT_SAMPLE_RATE
    active_target: tuple[str, dict[str, str], str] | None = None

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=120.0, write=30.0, pool=30.0))
    try:
        for chunk in chunks:
            gemini_text = f"{tone_prefix}{chunk}" if tone_prefix else chunk
            gemini_ga_body = {
                "contents": [{"role": "user", "parts": [{"text": gemini_text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "languageCode": "fr-FR",
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": voice_name,
                            }
                        },
                    },
                },
            }
            gemini_preview_body = {
                "contents": [{"role": "user", "parts": [{"text": gemini_text}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": voice_name,
                            }
                        }
                    },
                },
            }
            cloud_tts_body = {
                "input": {"text": chunk},
                "voice": {
                    "languageCode": "fr-FR",
                    "name": f"fr-FR-Chirp3-HD-{voice_name}",
                },
                "audioConfig": {
                    "audioEncoding": "LINEAR16",
                    "sampleRateHertz": _DEFAULT_SAMPLE_RATE,
                },
            }

            candidates_to_try = [active_target] if active_target is not None else targets
            response: httpx.Response | None = None
            chosen_kind = "gemini"
            attempt_errors: list[str] = []

            for url, headers, kind in candidates_to_try:
                is_preview_url = "-preview-tts" in url
                req_body = (
                    cloud_tts_body
                    if kind == "cloud_tts"
                    else (gemini_preview_body if is_preview_url else gemini_ga_body)
                )
                short_target = "cloud-tts" if kind == "cloud_tts" else url.split("//", 1)[-1].split("/projects/", 1)[0] + ":" + url.rsplit("/models/", 1)[-1]
                try:
                    resp = await http_client.post(url, headers=headers, json=req_body)
                except httpx.HTTPError as exc:
                    attempt_errors.append(f"{short_target} -> {type(exc).__name__}")
                    continue

                if resp.is_success:
                    response = resp
                    chosen_kind = kind
                    active_target = (url, headers, kind)
                    break

                detail = _extract_safe_error_detail(resp)
                attempt_errors.append(
                    f"{short_target} -> HTTP {resp.status_code}" + (f" ({detail})" if detail else "")
                )
                # Continuer vers le prochain candidat sur toute erreur (y compris 500/502/503 preview)
                continue

            if response is None:
                summary = " | ".join(attempt_errors[:4])
                raise ProviderError(f"Google TTS indisponible ({summary}).")

            data = json_body(response, "Google TTS")
            if chosen_kind == "cloud_tts":
                b64_audio = data.get("audioContent")
                if not isinstance(b64_audio, str) or not b64_audio:
                    raise ProviderError("Google Cloud TTS n'a renvoyé aucun flux audio.")
                raw_audio = base64.b64decode(b64_audio)
                mime = "audio/wav" if raw_audio.startswith(b"RIFF") else f"audio/L16;codec=pcm;rate={_DEFAULT_SAMPLE_RATE}"
            else:
                raw_audio, mime = _extract_audio_part(data)

            # Si Google renvoie déjà un WAV complet sur un seul segment, le retourner tel quel
            if mime.lower().startswith("audio/wav") and len(chunks) == 1:
                return raw_audio, "audio/wav"
            if mime.lower().startswith("audio/wav") and raw_audio.startswith(b"RIFF"):
                # Extraire les frames PCM pour concaténer proprement plusieurs segments WAV
                with wave.open(io.BytesIO(raw_audio), "rb") as wf:
                    detected_rate = wf.getframerate()
                    pcm_segments.append(wf.readframes(wf.getnframes()))
            else:
                detected_rate = _parse_sample_rate(mime)
                pcm_segments.append(raw_audio)
    finally:
        if owns_client:
            await http_client.aclose()

    wav_bytes = pcm_to_wav(b"".join(pcm_segments), sample_rate=detected_rate)
    return wav_bytes, "audio/wav"


async def transcribe_audio(
    settings: Any,
    audio_bytes: bytes,
    *,
    filename: str = "dictation.webm",
    content_type: str | None = None,
    language: str | None = None,
    provider: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, str]:
    """Transcrit un enregistrement audio via Mistral Voxtral (prioritaire) ou Google Gemini Audio."""
    if not audio_bytes:
        raise ValueError("L'enregistrement audio est vide.")
    if len(audio_bytes) > MAX_STT_AUDIO_BYTES:
        raise ValueError("L'enregistrement audio dépasse la limite autorisée de 15 Mo.")

    mime = normalize_audio_mime(content_type, filename)
    if not mime:
        raise ValueError("Format audio non pris en charge (utilisez WebM, Ogg, MP4/M4A, MP3 ou WAV).")

    resolved = resolve_stt_provider(settings, requested=provider)
    if not resolved:
        raise ProviderError(
            "La dictée vocale nécessite MISTRAL_API_KEY (Voxtral) ou GOOGLE_API_KEY (Gemini Audio)."
        )

    if resolved == "demo":
        return {
            "text": "Transcription de démonstration vocale.",
            "provider": "demo",
            "model": "demo",
        }

    safe_ext = ALLOWED_AUDIO_MIME_TYPES.get(mime, ".webm")
    safe_filename = f"dictation{safe_ext}"
    clean_lang = (language or "").strip().lower()[:10]
    if clean_lang and not re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", clean_lang):
        clean_lang = ""

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=httpx.Timeout(connect=20.0, read=90.0, write=60.0, pool=30.0))
    try:
        if resolved == "mistral":
            return await _transcribe_with_mistral(
                settings,
                http_client,
                audio_bytes=audio_bytes,
                filename=safe_filename,
                mime=mime,
                language=clean_lang,
            )
        return await _transcribe_with_google(
            settings,
            http_client,
            audio_bytes=audio_bytes,
            mime=mime,
            language=clean_lang,
        )
    finally:
        if owns_client:
            await http_client.aclose()


async def _transcribe_with_mistral(
    settings: Any,
    http_client: httpx.AsyncClient,
    *,
    audio_bytes: bytes,
    filename: str,
    mime: str,
    language: str,
) -> dict[str, str]:
    mistral_key = clean_secret(getattr(settings, "mistral_api_key", None))
    if not mistral_key:
        raise ProviderError("MISTRAL_API_KEY non configurée pour la transcription Voxtral.")

    model = str(getattr(settings, "stt_mistral_model", "voxtral-mini-latest") or "voxtral-mini-latest").strip()
    form_data: dict[str, str] = {"model": model}
    if language:
        form_data["language"] = language.split("-", 1)[0]

    try:
        response = await http_client.post(
            MISTRAL_TRANSCRIPTIONS_URL,
            headers={"Authorization": f"Bearer {mistral_key}"},
            data=form_data,
            files={"file": (filename, audio_bytes, mime)},
        )
    except httpx.HTTPError as exc:
        raise ProviderError(f"Impossible de joindre Mistral Voxtral ({type(exc).__name__}).") from None

    check_response(response, "Mistral Voxtral")
    data = json_body(response, "Mistral Voxtral")
    transcript = str(data.get("text") or "").strip()
    return {"text": transcript, "provider": "mistral", "model": model}


async def _transcribe_with_google(
    settings: Any,
    http_client: httpx.AsyncClient,
    *,
    audio_bytes: bytes,
    mime: str,
    language: str,
) -> dict[str, str]:
    model = str(getattr(settings, "stt_google_model", "gemini-2.5-flash") or "gemini-2.5-flash").strip()
    url, headers = await _resolve_google_native_endpoint(settings, model)
    lang_hint = f" (langue attendue : {language})" if language else ""
    instruction = (
        f"Transcris fidèlement et mot pour mot cet enregistrement audio dans sa langue parlée{lang_hint}, "
        "avec une ponctuation naturelle. Réponds uniquement par la transcription, sans aucun commentaire, "
        "ni guillemets, ni préfixe. Si l'audio est silencieux ou inaudible, réponds une chaîne vide."
    )
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": instruction},
                    {
                        "inlineData": {
                            "mimeType": mime,
                            "data": base64.b64encode(audio_bytes).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
        },
    }
    try:
        response = await http_client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError(f"Impossible de joindre Google Gemini Audio ({type(exc).__name__}).") from None

    check_response(response, "Google Gemini Audio")
    data = json_body(response, "Google Gemini Audio")
    parts_text: list[str] = []
    for cand in data.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content")
        for part in (content.get("parts") if isinstance(content, dict) else None) or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts_text.append(part["text"])
    transcript = " ".join(p.strip() for p in parts_text if p.strip()).strip()
    return {"text": transcript, "provider": "google", "model": model}
