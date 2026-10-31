"""Public research telemetry: operation summaries and document links only."""
from datetime import datetime, timezone
from typing import Any

from .source_registry import has_source_url, is_document


def research_activity(kind: str, message: str, *, query: str = "", sources: list[dict[str, Any]] | None = None, state: str = "found") -> dict[str, Any]:
    """Whitelist public fields; never forward source content or model reasoning."""
    activity: dict[str, Any] = {
        "kind": kind, "message": message[:1000],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if query:
        activity["query"] = query[:1000]
    if sources is not None:
        activity["sources"] = [
            {"title": str(source.get("title") or "Document")[:300], "url": source["url"], "state": state}
            for source in sources if is_document(source) and has_source_url(source)
        ][:120]
    return {"type": "research_activity", "activity": activity}
