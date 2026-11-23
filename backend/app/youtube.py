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
INNERTUBE_WEB_CONTEXT = {
    "client": {
        "clientName": "WEB",
        "clientVersion": "2.20250101.00.00",
    }
}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_CAPTION_RESPONSE_BYTES = 15 * 1024 * 1024
MAX_DESCRIPTION_CHARS = 2500

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


def extract_player_response_from_html(html_text: str) -> dict[str, Any] | None:
    """Extracts ytInitialPlayerResponse JSON object from YouTube watch/embed HTML."""
    if not html_text:
        return None
    markers = (
        "var ytInitialPlayerResponse =",
        "ytInitialPlayerResponse =",
        'window["ytInitialPlayerResponse"] =',
    )
    decoder = json.JSONDecoder()
    for marker in markers:
        pos = html_text.find(marker)
        if pos < 0:
            continue
        brace_start = html_text.find("{", pos + len(marker))
        if brace_start < 0:
            continue
        try:
            obj, _ = decoder.raw_decode(html_text, brace_start)
            if isinstance(obj, dict):
                return obj
        except (ValueError, json.JSONDecodeError):
            continue
    return None


async def get_innertube_api_key(
    client: httpx.AsyncClient,
    video_id: str | None = None,
    capture_html: list[str] | None = None,
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
                if capture_html is not None and video_id and f"/watch?v={video_id}" in url:
                    capture_html.append(res.text)
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


def _extract_track_label(track: dict[str, Any]) -> str:
    """Extracts a human-readable track label from InnerTube caption track metadata."""
    name_obj = track.get("name")
    if isinstance(name_obj, dict):
        simple = str(name_obj.get("simpleText") or "").strip()
        if simple:
            return simple
        runs = name_obj.get("runs")
        if isinstance(runs, list) and runs and isinstance(runs[0], dict):
            run_text = str(runs[0].get("text") or "").strip()
            if run_text:
                return run_text
    elif isinstance(name_obj, str) and name_obj.strip():
        return name_obj.strip()
    return str(track.get("languageCode") or "Langue originale")


def _with_query_param(url: str, key: str, value: str | None) -> str:
    """Replaces or removes a query parameter cleanly without breaking existing params."""
    parts = urllib.parse.urlsplit(url)
    params = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != key]
    if value is not None:
        params.append((key, value))
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params), parts.fragment)
    )


def _normalize_caption_text(raw: str) -> str:
    if not raw:
        return ""
    unescaped = html.unescape(raw)
    return " ".join(unescaped.split()).strip()


def parse_youtube_captions(raw_text: str) -> list[tuple[float, str]]:
    """
    Parses YouTube subtitle payloads across all known formats:
    - JSON3 (`fmt=json3`): {"events": [{"tStartMs": ..., "segs": [{"utf8": "..."}]}]}
    - Timedtext XML v3 (`fmt=srv3`): <timedtext format="3"><body><p t="..." d="..."><s>...</s></p></body></timedtext>
    - Classic Timedtext XML: <transcript><text start="..." dur="...">...</text></transcript>
    Preserves text inside nested child tags (e.g., <i>, <b>, <s>) without truncation.
    """
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return []

    # 1. JSON3 format
    if cleaned.startswith("{"):
        try:
            payload = json.loads(cleaned)
        except (ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("events"), list):
            segments: list[tuple[float, str]] = []
            for ev in payload["events"]:
                if not isinstance(ev, dict):
                    continue
                segs = ev.get("segs")
                if not isinstance(segs, list):
                    continue
                raw_seg_text = "".join(
                    str(seg.get("utf8") or "")
                    for seg in segs
                    if isinstance(seg, dict)
                )
                text_content = _normalize_caption_text(raw_seg_text)
                if not text_content:
                    continue
                try:
                    start = float(ev.get("tStartMs", 0)) / 1000.0
                except (TypeError, ValueError):
                    start = 0.0
                segments.append((start, text_content))
            return segments

    # 2. XML formats (srv3 timedtext v3 OR classic transcript XML)
    root = ET.fromstring(cleaned)
    p_nodes = root.findall(".//p")
    if p_nodes:
        segments = []
        for node in p_nodes:
            raw_t = node.attrib.get("t")
            raw_start = node.attrib.get("start")
            try:
                if raw_t is not None:
                    start = float(raw_t) / 1000.0
                elif raw_start is not None:
                    start = float(raw_start)
                else:
                    start = 0.0
            except (TypeError, ValueError):
                start = 0.0
            text_content = _normalize_caption_text("".join(node.itertext()))
            if text_content:
                segments.append((start, text_content))
        if segments:
            return segments

    text_nodes = root.findall(".//text")
    iter_nodes = text_nodes if text_nodes else list(root)
    segments = []
    for node in iter_nodes:
        try:
            start = float(node.attrib.get("start", 0))
        except (TypeError, ValueError):
            start = 0.0
        text_content = _normalize_caption_text("".join(node.itertext()))
        if text_content:
            segments.append((start, text_content))
    return segments


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

    segments: list[tuple[float, str]] = []
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
            headers=headers,
        ) as client:
            # 1. Dynamically retrieve InnerTube API key from YouTube page HTML (and keep watch HTML for fallback)
            captured_watch_html: list[str] = []
            api_key = await get_innertube_api_key(client, video_id=video_id, capture_html=captured_watch_html)

            # 2. Query InnerTube API player endpoint with Android client
            inner_url = INNERTUBE_URL.format(api_key=api_key)
            inner_payload = {
                "context": INNERTUBE_CONTEXT,
                "videoId": video_id,
            }
            inner_res = await client.post(inner_url, json=inner_payload)
            inner_data = inner_res.json() if inner_res.content else {}
            if not isinstance(inner_data, dict):
                inner_data = {}

            video_details = inner_data.get("videoDetails") or {}
            captions_json = (
                (inner_data.get("captions") or {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks", [])
            )

            # 2b. Zero-cost fallback: inspect ytInitialPlayerResponse from the watch HTML already downloaded
            if (not captions_json or not video_details) and captured_watch_html:
                watch_player = extract_player_response_from_html(captured_watch_html[0])
                if watch_player:
                    if not video_details:
                        video_details = watch_player.get("videoDetails") or {}
                    if not captions_json:
                        captions_json = (
                            (watch_player.get("captions") or {})
                            .get("playerCaptionsTracklistRenderer", {})
                            .get("captionTracks", [])
                        )

            # 2c. Secondary InnerTube fallback with WEB client if ANDROID returned no caption tracks
            if not captions_json:
                try:
                    web_res = await client.post(
                        inner_url,
                        json={"context": INNERTUBE_WEB_CONTEXT, "videoId": video_id},
                    )
                    web_data = web_res.json() if web_res.content else {}
                    if isinstance(web_data, dict):
                        if not video_details:
                            video_details = web_data.get("videoDetails") or {}
                        captions_json = (
                            (web_data.get("captions") or {})
                            .get("playerCaptionsTracklistRenderer", {})
                            .get("captionTracks", [])
                        )
                except Exception as web_exc:
                    _logger.debug("Repli InnerTube WEB échoué pour %s: %s", video_id, web_exc)

            title = video_details.get("title") or f"Vidéo YouTube ({video_id})"
            author = video_details.get("author") or "YouTube"
            length_sec = int(video_details.get("lengthSeconds") or 0)
            duration_str = format_duration(length_sec) if length_sec > 0 else "Inconnue"
            description = (video_details.get("shortDescription") or "").strip()

            # 3. Fetch and parse subtitles across XML / JSON3 / SRV3 formats
            chosen_track = select_best_caption_track(captions_json)
            transcript_text = ""
            lang_label = "Aucun sous-titre disponible"

            if chosen_track and chosen_track.get("baseUrl"):
                raw_base_url = str(chosen_track["baseUrl"])
                track_name = _extract_track_label(chosen_track)
                is_asr = chosen_track.get("kind") == "asr"
                lang_label = f"{track_name} (généré automatiquement)" if is_asr else track_name

                candidate_urls: list[str] = []
                for candidate in (
                    _with_query_param(raw_base_url, "fmt", None),
                    _with_query_param(raw_base_url, "fmt", "json3"),
                    _with_query_param(raw_base_url, "fmt", "srv3"),
                ):
                    if candidate not in candidate_urls:
                        candidate_urls.append(candidate)

                for sub_url in candidate_urls:
                    try:
                        sub_res = await client.get(sub_url)
                        if sub_res.status_code != 200 or not sub_res.content:
                            continue
                        if len(sub_res.content) > MAX_CAPTION_RESPONSE_BYTES:
                            _logger.warning(
                                "Sous-titres YouTube (%s) dépassent la limite de %d octets",
                                video_id,
                                MAX_CAPTION_RESPONSE_BYTES,
                            )
                            continue
                        parsed_segments = parse_youtube_captions(sub_res.text)
                        if parsed_segments:
                            segments = parsed_segments
                            transcript_text = format_transcript_paragraphs(segments)
                            break
                    except Exception as parse_err:
                        _logger.warning("Échec de parsing des sous-titres YouTube (%s, %s): %s", video_id, sub_url[:80], parse_err)

    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "YouTube a mis trop de temps à répondre (délai dépassé).") from exc
    except Exception as exc:
        raise HTTPException(
            422, f"Impossible d'accéder à la vidéo YouTube ({type(exc).__name__}). Vérifiez l'adresse ou la disponibilité."
        ) from exc

    # 4. Construct rich markdown (never truncating transcript_text)
    header_parts = [
        f"# 🎬 {title}",
        f"**Chaîne :** [{author}]({watch_url}) · **Durée :** `{duration_str}` · **Sous-titres :** {lang_label}",
        f"**Lien vidéo :** {watch_url}",
    ]
    if description:
        short_desc = description[:MAX_DESCRIPTION_CHARS].replace("\n", " ")
        header_parts.append(f"\n> **Description :** {short_desc}{'…' if len(description) > MAX_DESCRIPTION_CHARS else ''}")

    header_parts.append("\n---\n")

    if transcript_text:
        header_parts.append(f"### 🎙️ Transcription / Paroles de la vidéo ({lang_label})\n\n{transcript_text}")
    else:
        header_parts.append(
            "*(ℹ️ Aucun sous-titre ni transcription textuelle n'a pu être extrait pour cette vidéo. "
            "Les métadonnées et la description ci-dessus sont fournies pour l'analyse).*"
        )

    full_markdown = "\n\n".join(header_parts)

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
    extraction["lang_label"] = lang_label
    extraction["has_transcript"] = bool(transcript_text)
    extraction["transcript_segments"] = len(segments)
    extraction["transcript_chars"] = len(transcript_text)

    content_bytes = full_markdown.encode("utf-8")
    return filename, content_bytes, mime_type, full_markdown, extraction

