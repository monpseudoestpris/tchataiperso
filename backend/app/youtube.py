import html
import json
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from fastapi import HTTPException

from .config import Settings
from .documents import MAX_EXTRACTED_CHARS
from .schemas import DocumentAnnotation, DocumentExtraction, ExtractedPage

_logger = logging.getLogger("uvicorn.error")

DEFAULT_INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player?key={api_key}"
INNERTUBE_CONTEXT = {
    "client": {
        "clientName": "ANDROID",
        "clientVersion": "20.10.38",
    }
}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_cached_innertube_api_key: str | None = None


def extract_innertube_key_from_html(html_text: str) -> str | None:
    """Extracts INNERTUBE_API_KEY from YouTube HTML using regex patterns."""
    if not html_text:
        return None
    patterns = [
        r'"INNERTUBE_API_KEY":\s*"([^"]+)"',
        r'"innertubeApiKey":\s*"([^"]+)"',
        r'INNERTUBE_API_KEY\s*[:=]\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


async def get_innertube_api_key(
    client: httpx.AsyncClient,
    video_id: str | None = None,
) -> str:
    """
    Dynamically retrieves YouTube's InnerTube API key by inspecting YouTube pages
    (watch page -> embed page -> homepage fallback -> default key).
    """
    global _cached_innertube_api_key

    urls: list[str] = []
    if video_id:
        urls.append(f"https://www.youtube.com/watch?v={video_id}")
        urls.append(f"https://www.youtube.com/embed/{video_id}")
    urls.append("https://www.youtube.com/")

    for url in urls:
        try:
            res = await client.get(url)
            if res.status_code == 200 and res.text:
                extracted = extract_innertube_key_from_html(res.text)
                if extracted:
                    _logger.debug("Clé InnerTube extraite dynamiquement depuis %s: %s***", url, extracted[:10])
                    _cached_innertube_api_key = extracted
                    return extracted
        except Exception as exc:
            _logger.debug("Échec de récupération de la clé InnerTube depuis %s: %s", url, exc)

    if _cached_innertube_api_key:
        return _cached_innertube_api_key
    return DEFAULT_INNERTUBE_API_KEY


def extract_youtube_video_id(url: str) -> str | None:
    """Extract 11-char YouTube video ID from various URL formats (watch, youtu.be, shorts, embed, live)."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        if host not in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
        }:
            return None

        if host == "youtu.be":
            path_id = parsed.path.strip("/")
            return path_id[:11] if len(path_id) >= 11 else None

        query = urllib.parse.parse_qs(parsed.query)
        if "v" in query and len(query["v"][0]) >= 11:
            return query["v"][0][:11]

        match = re.search(r"/(?:shorts|embed|live|v)/([a-zA-Z0-9_-]{11})", parsed.path)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None


def format_duration(seconds: int) -> str:
    """Format duration seconds into HH:MM:SS or MM:SS."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_transcript_paragraphs(nodes: list[tuple[float, str]]) -> str:
    """Groups consecutive subtitle segments into coherent timestamped paragraphs."""
    paragraphs: list[str] = []
    current_time: float = 0.0
    current_texts: list[str] = []

    for start, text in nodes:
        clean = text.strip()
        if not clean:
            continue
        if not current_texts:
            current_time = start
        current_texts.append(clean)

        # Flush paragraph if time span >= 20 seconds or end of sentence
        if (start - current_time >= 20.0) or clean.endswith((".", "!", "?")):
            time_tag = format_duration(int(current_time))
            combined = " ".join(current_texts).strip()
            paragraphs.append(f"[{time_tag}] {combined}")
            current_texts = []

    if current_texts:
        time_tag = format_duration(int(current_time))
        combined = " ".join(current_texts).strip()
        paragraphs.append(f"[{time_tag}] {combined}")

    return "\n\n".join(paragraphs)


def select_best_caption_track(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the most relevant caption track (prioritizing French, then English, manual over ASR)."""
    if not tracks:
        return None

    # Priority 1: French manual captions
    for t in tracks:
        code = t.get("languageCode", "").lower()
        if (code == "fr" or code.startswith("fr-")) and t.get("kind") != "asr":
            return t

    # Priority 2: French auto-generated (ASR)
    for t in tracks:
        code = t.get("languageCode", "").lower()
        if code == "fr" or code.startswith("fr-"):
            return t

    # Priority 3: English manual captions
    for t in tracks:
        code = t.get("languageCode", "").lower()
        if (code == "en" or code.startswith("en-")) and t.get("kind") != "asr":
            return t

    # Priority 4: English auto-generated (ASR)
    for t in tracks:
        code = t.get("languageCode", "").lower()
        if code == "en" or code.startswith("en-"):
            return t

    # Priority 5: Any manual captions
    for t in tracks:
        if t.get("kind") != "asr":
            return t

    # Fallback: First available track
    return tracks[0]


async def fetch_and_parse_youtube_video(
    settings: Settings,
    video_url: str,
    video_id: str,
) -> tuple[str, bytes, str, str, dict[str, Any]]:
    """
    Fetches YouTube video metadata and parses subtitles/transcript via the unofficial InnerTube API.
    Returns: (filename, content_bytes, mime_type, full_markdown, extraction_dict)
    """
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cookie": "CONSENT=YES+cb.20210328-17-p0.fr+FX+478; SOCS=CAESEwgDEgk0ODEzNzk0MjEaAmZyIAEaBgiA_LyaBg;",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            # 1. Dynamically retrieve InnerTube API key from YouTube page HTML
            api_key = await get_innertube_api_key(client, video_id=video_id)

            # 2. Query InnerTube API player endpoint with Android client
            inner_url = INNERTUBE_URL.format(api_key=api_key)
            inner_payload = {
                "context": INNERTUBE_CONTEXT,
                "videoId": video_id,
            }
            inner_res = await client.post(inner_url, json=inner_payload)
            inner_data = inner_res.json()

            video_details = inner_data.get("videoDetails", {})
            title = video_details.get("title") or f"Vidéo YouTube ({video_id})"
            author = video_details.get("author") or "YouTube"
            length_sec = int(video_details.get("lengthSeconds") or 0)
            duration_str = format_duration(length_sec) if length_sec > 0 else "Inconnue"
            description = (video_details.get("shortDescription") or "").strip()

            captions_json = (
                inner_data.get("captions", {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks", [])
            )

            # 3. Fetch and parse subtitles if available
            chosen_track = select_best_caption_track(captions_json)
            transcript_text = ""
            lang_label = "Aucun sous-titre disponible"

            if chosen_track and chosen_track.get("baseUrl"):
                base_url = chosen_track["baseUrl"].replace("&fmt=srv3", "")
                track_name = chosen_track.get("name", {}).get("runs", [{}])[0].get("text") or chosen_track.get("languageCode", "Langue originale")
                is_asr = chosen_track.get("kind") == "asr"
                lang_label = f"{track_name} (généré automatiquement)" if is_asr else track_name

                sub_res = await client.get(base_url)
                if sub_res.status_code == 200 and sub_res.content:
                    try:
                        root = ET.fromstring(sub_res.text)
                        segments: list[tuple[float, str]] = []
                        for node in list(root):
                            start = float(node.attrib.get("start", 0))
                            text_content = html.unescape(node.text or "").strip()
                            if text_content:
                                segments.append((start, text_content))
                        if segments:
                            transcript_text = format_transcript_paragraphs(segments)
                    except Exception as parse_err:
                        _logger.warning("Échec de parsing XML des sous-titres YouTube (%s): %s", video_id, parse_err)

    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "YouTube a mis trop de temps à répondre (délai dépassé).") from exc
    except Exception as exc:
        raise HTTPException(
            422, f"Impossible d'accéder à la vidéo YouTube ({type(exc).__name__}). Vérifiez l'adresse ou la disponibilité."
        ) from exc

    # 4. Construct rich markdown
    header_parts = [
        f"# 🎬 {title}",
        f"**Chaîne :** [{author}]({watch_url}) · **Durée :** `{duration_str}` · **Sous-titres :** {lang_label}",
        f"**Lien vidéo :** {watch_url}",
    ]
    if description:
        short_desc = description[:800].replace("\n", " ")
        header_parts.append(f"\n> **Description :** {short_desc}{'…' if len(description) > 800 else ''}")

    header_parts.append("\n---\n")

    if transcript_text:
        header_parts.append(f"### 🎙️ Transcription / Paroles de la vidéo ({lang_label})\n\n{transcript_text}")
    else:
        header_parts.append(
            "*(ℹ️ Aucun sous-titre ni transcription textuelle n'a pu être extrait pour cette vidéo. "
            "Les métadonnées et la description ci-dessus sont fournies pour l'analyse).*"
        )

    full_markdown = "\n\n".join(header_parts)
    if len(full_markdown) > MAX_EXTRACTED_CHARS:
        full_markdown = full_markdown[:MAX_EXTRACTED_CHARS] + "\n\n[... transcription tronquée à 40 000 caractères ...]"

    short_title = title[:65].strip()
    filename = f"🎬 {short_title} ({author})"[:255]
    mime_type = "text/html; video=youtube"

    extraction = DocumentExtraction(
        model="youtube-transcript",
        pages=[
            ExtractedPage(
                index=0,
                markdown=full_markdown,
                method="local",
                images=[],
            )
        ],
        annotations=[
            DocumentAnnotation(
                title=title,
                summary=f"Vidéo YouTube : {title} par {author} ({duration_str}). Sous-titres : {lang_label}.",
            )
        ],
        warnings=[],
    ).model_dump()
    extraction["url"] = watch_url
    extraction["video_id"] = video_id
    extraction["author"] = author
    extraction["duration"] = duration_str

    content_bytes = full_markdown.encode("utf-8")
    return filename, content_bytes, mime_type, full_markdown, extraction

