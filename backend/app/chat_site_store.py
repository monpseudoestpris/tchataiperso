"""Persist successful chat sites and reuse snapshots for unchanged source content."""

import html
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import providers
from .chat_site import _site_document, generate_chat_site
from .models import ChatSite


async def get_or_create_chat_site(
    db: Session, settings: Any, conversation_id: str, title: str,
    messages: list[dict[str, Any]], scope: str, message_id: str = "",
) -> str:
    """Cache by source content and scope; failed generations never become attachments."""
    normalized = [{"role": m.get("role"), "content": m.get("content", ""),
                   "sources": m.get("sources") or []} for m in messages]
    digest = hashlib.sha256(json.dumps(
        [title, scope, message_id, normalized], sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()
    query = select(ChatSite).where(ChatSite.conversation_id == conversation_id, ChatSite.input_hash == digest)
    existing = db.scalar(query)
    if existing:
        return existing.html_content
    try:
        document = await generate_chat_site(settings, title, messages, raise_on_failure=True)
    except providers.ProviderError as exc:
        return _site_document(title, '<p role="status">La synthèse IA est indisponible. '
                              + html.escape(str(exc)) + '</p>')
    site = ChatSite(conversation_id=conversation_id, input_hash=digest, scope=scope,
                    title=title[:200], html_content=document)
    db.add(site)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent identical requests may finish together; retain one snapshot.
        db.rollback()
        existing = db.scalar(query)
        if existing is None:
            raise
        return existing.html_content
    return document
