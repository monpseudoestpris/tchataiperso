import json
import re
import unicodedata
from datetime import timezone

from .blog import parse_cards_from_content
from .models import Attachment, Blog, BlogPost, Conversation, DeepSearchReport, GeneratedImage, GeneratedSound, LearnReport, Message, Skill, User


MAX_SKILL_COUNT = 100
MAX_SKILL_CONTEXT_CHARS = 12000
MAX_GENERATED_IMAGES = 200
IMAGE_ASPECT_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3"}
MAX_GENERATED_SOUNDS = 200
SOUND_OUTPUT_FORMATS = [
    {"id": "mp3_44100_128", "name": "MP3 44.1 kHz (128 kbps — Recommandé)", "mime": "audio/mpeg", "ext": "mp3"},
    {"id": "mp3_44100_192", "name": "MP3 44.1 kHz (192 kbps — Haute fidélité)", "mime": "audio/mpeg", "ext": "mp3"},
    {"id": "mp3_44100_96", "name": "MP3 44.1 kHz (96 kbps — Léger)", "mime": "audio/mpeg", "ext": "mp3"},
    {"id": "mp3_44100_64", "name": "MP3 44.1 kHz (64 kbps — Ultra léger)", "mime": "audio/mpeg", "ext": "mp3"},
    {"id": "pcm_44100", "name": "WAV / PCM 44.1 kHz (Non compressé)", "mime": "audio/wav", "ext": "wav"},
]


def stamp(value) -> str:
    return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


def user_json(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "family_group_id": user.family_group_id,
        "family_group_name": user.family_group.name if user.family_group else None,
    }


def attachment_json(item: Attachment) -> dict:
    url_source = item.extraction.get("url") if isinstance(item.extraction, dict) else None
    finance_meta = None
    if isinstance(item.extraction, dict) and item.extraction.get("model") in ("yahoo-finance", "eod-historical-data"):
        finance_meta = {
            k: item.extraction.get(k)
            for k in ("symbol", "short_name", "long_name", "price", "currency", "change_percent", "exchange", "url",
                      "provider", "source_label")
            if item.extraction.get(k) is not None
        }
    return {
        "id": item.id,
        "filename": item.filename,
        "mime_type": item.mime_type,
        "size": item.size,
        "url": f"/api/attachments/{item.id}/file",
        "created_at": stamp(item.created_at),
        "extracted_chars": len(item.extracted_text),
        "has_extraction": bool(item.extraction),
        "page_count": len(item.extraction["pages"]) if item.extraction and "pages" in item.extraction else 0,
        "source_url": url_source,
        "finance_meta": finance_meta,
    }


def generated_image_json(item: GeneratedImage) -> dict:
    return {
        "id": item.id,
        "prompt": item.prompt,
        "aspect_ratio": item.aspect_ratio,
        "filename": item.filename,
        "mime_type": item.mime_type,
        "size": item.size,
        "url": f"/api/images/{item.id}/file",
        "download_url": f"/api/images/{item.id}/file?download=1",
        "created_at": stamp(item.created_at),
    }


def generated_sound_json(item: GeneratedSound) -> dict:
    return {
        "id": item.id,
        "prompt": item.prompt,
        "duration_seconds": item.duration_seconds,
        "prompt_influence": item.prompt_influence,
        "output_format": item.output_format,
        "loop": bool(item.loop),
        "filename": item.filename,
        "mime_type": item.mime_type,
        "size": item.size,
        "url": f"/api/sounds/{item.id}/file",
        "download_url": f"/api/sounds/{item.id}/file?download=1",
        "created_at": stamp(item.created_at),
    }


def message_json(item: Message) -> dict:
    reports = getattr(item, "deep_search_reports", None)
    report_id = reports[0].id if reports else None
    learn_reports = getattr(item, "learn_reports", None)
    learn_report_id = learn_reports[0].id if learn_reports else None
    return {
        "id": item.id,
        "role": item.role,
        "content": item.content,
        "created_at": stamp(item.created_at),
        "attachments": [attachment_json(value) for value in item.attachments],
        "sources": item.sources,
        "deep_search_report_id": report_id,
        "learn_report_id": learn_report_id,
    }


def deep_search_report_json(item: DeepSearchReport, include_html: bool = False) -> dict:
    data = {
        "id": item.id,
        "user_id": item.user_id,
        "conversation_id": item.conversation_id,
        "message_id": item.message_id,
        "title": item.title,
        "topic": item.topic,
        "markdown_content": item.markdown_content,
        "sources": item.sources or [],
        "sources_count": len(item.sources or []),
        "created_at": stamp(item.created_at),
        "html_url": f"/api/deep-search/reports/{item.id}/html",
        "pdf_url": f"/api/deep-search/reports/{item.id}/html?pdf=1",
        "download_url": f"/api/deep-search/reports/{item.id}/html?download=1",
    }
    if include_html:
        data["html_content"] = item.html_content
    return data


def learn_report_json(item: LearnReport, include_html: bool = False) -> dict:
    from app.learn_html import parse_flashcards, parse_quiz
    data = {
        "id": item.id,
        "user_id": item.user_id,
        "conversation_id": item.conversation_id,
        "message_id": item.message_id,
        "title": item.title,
        "topic": item.topic,
        "markdown_content": item.markdown_content,
        "sources": item.sources or [],
        "sources_count": len(item.sources or []),
        "created_at": stamp(item.created_at),
        "html_url": f"/api/learn/reports/{item.id}/html",
        "pdf_url": f"/api/learn/reports/{item.id}/html?pdf=1",
        "download_url": f"/api/learn/reports/{item.id}/html?download=1",
        "flashcards": parse_flashcards(item.markdown_content, item.topic),
        "quiz": parse_quiz(item.markdown_content, item.topic),
    }
    if include_html:
        data["html_content"] = item.html_content
    return data


def skill_json(item: Skill) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "prompt": item.prompt,
        "created_at": stamp(item.created_at),
        "updated_at": stamp(item.updated_at),
    }


def blog_post_json(item: BlogPost) -> dict:
    cards = parse_cards_from_content(item.content)
    return {
        "id": item.id,
        "blog_id": item.blog_id,
        "title": item.title,
        "summary": item.summary,
        "content": item.content,
        "cards": cards,
        "sources": item.sources or [],
        "created_at": stamp(item.created_at),
    }


def blog_json(item: Blog, include_posts: bool = False) -> dict:
    posts = item.posts or []
    latest = posts[0] if posts else None
    result = {
        "id": item.id,
        "title": item.title,
        "prompt": item.prompt,
        "auto_refresh": item.auto_refresh,
        "theme": getattr(item, "theme", None) or "sunset",
        "created_at": stamp(item.created_at),
        "updated_at": stamp(item.updated_at),
        "posts_count": len(posts),
        "latest_post": {
            "id": latest.id,
            "title": latest.title,
            "summary": latest.summary,
            "created_at": stamp(latest.created_at),
        } if latest else None,
    }
    if include_posts:
        result["posts"] = [blog_post_json(p) for p in posts]
    return result


def conversation_json(item: Conversation, detail: bool = False) -> dict:
    raw_keywords = item.keywords if isinstance(item.keywords, list) else []
    keywords = [str(k).strip() for k in raw_keywords if isinstance(k, str) and str(k).strip()][:5]
    result = {
        "id": item.id,
        "title": item.title,
        "model": item.model,
        "theme": (item.theme or "").strip(),
        "keywords": keywords,
        "created_at": stamp(item.created_at),
        "updated_at": stamp(item.updated_at),
        "summary": item.summary,
    }
    if detail:
        result["messages"] = [message_json(message) for message in item.messages]
        result["skills"] = [skill_json(link.skill) for link in item.skill_links]
    return result


def sse(name: str, value: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"


def extract_mentioned_skills(content: str, user_skills: list[Skill]) -> list[Skill]:
    """Finds user skills mentioned in the content via @slug or @name (e.g. @prof, @feynman)."""
    raw_tags = re.findall(r"@([a-zA-Z0-9_\u00C0-\u017F-]+)", content)
    if not raw_tags or not user_skills:
        return []
    resolved: list[Skill] = []
    for tag in raw_tags:
        tag_norm = unicodedata.normalize("NFKD", tag).encode("ascii", "ignore").decode("ascii").lower().strip("-_")
        if not tag_norm:
            continue
        for skill in user_skills:
            if skill in resolved:
                continue
            skill_norm = unicodedata.normalize("NFKD", skill.name).encode("ascii", "ignore").decode("ascii").lower().strip()
            skill_slug = re.sub(r"[^a-z0-9]+", "-", skill_norm).strip("-")
            skill_words = [w for w in re.split(r"[^a-z0-9]+", skill_norm) if w]
            matches = (
                tag_norm == skill_slug
                or tag_norm in skill_words
                or skill_slug.startswith(tag_norm)
                or any(w.startswith(tag_norm) for w in skill_words)
                or (len(skill_slug) >= 3 and tag_norm.startswith(skill_slug))
                or (len(tag_norm) >= 3 and tag_norm in skill_slug)
            )
            if matches:
                resolved.append(skill)
    return resolved

