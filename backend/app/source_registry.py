"""Report-local source order and evidence references shared by writers and exports.

Create the snapshot after curation. Never sort or deduplicate it after citations
have been assigned: legacy numeric references address this exact document order.
"""
from __future__ import annotations

import re
from copy import deepcopy
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from .evidence_ledger import EvidenceLedger, extract_deterministic_evidence_from_sources

CITATION_RE = re.compile(r"\[(?:cite:\s*)?(\d{1,3}(?:\s*[,;–-]\s*\d{1,3})*)\](?!\()", re.IGNORECASE)
EVIDENCE_RE = re.compile(r"\[(EV_\d+)\]")


def is_document(source: dict[str, Any]) -> bool:
    return not (source.get("media_type") == "image" or source.get("img_src") or source.get("provider") == "searxng_images")


def has_source_url(source: dict[str, Any]) -> bool:
    try:
        url = urlsplit(str(source.get("url") or ""))
        return url.scheme in ("http", "https") and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def citation_numbers(value: str) -> list[int]:
    value = re.sub(r"^cite:\s*", "", value.strip(), flags=re.IGNORECASE)
    numbers: list[int] = []
    for part in re.split(r"\s*[,;]\s*", value):
        bounds = re.split(r"\s*[–-]\s*", part.strip())
        if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
            start, end = map(int, bounds)
            numbers.extend(range(start, end + 1))
        elif bounds and bounds[0].isdigit():
            numbers.append(int(bounds[0]))
    return list(dict.fromkeys(numbers))


class SourceRegistry:
    """Own an isolated snapshot; serialize evidence alongside its source in JSON."""

    def __init__(self, sources: list[dict[str, Any]]) -> None:
        self._sources = deepcopy(sources)
        self.documents = [s for s in self._sources if is_document(s)]
        for index, source in enumerate(self.documents, 1):
            source["source_id"] = "SRC_" + sha256(str(source.get("url") or index).encode()).hexdigest()[:16]
        stored = list({ev["evidence_id"]: ev for s in self.documents for ev in s.get("evidence", [])}.values())
        self.ledger = EvidenceLedger.from_dict_list(stored) if stored else extract_deterministic_evidence_from_sources(self.documents)
        self._source_numbers = {s["source_id"]: i for i, s in enumerate(self.documents, 1)}
        for source in self.documents:
            source["evidence"] = [ev.to_dict() for ev in self.ledger.list_all() if ev.source_id == source["source_id"]]

    def export_sources(self) -> list[dict[str, Any]]:
        return deepcopy(self._sources)

    def resolve_evidence_citations(self, text: str) -> str:
        """Only registered evidence may produce a numeric citation; leave unknown IDs for the gate."""
        def replace(match: re.Match) -> str:
            evidence = self.ledger.get(match[1])
            number = self._source_numbers.get(evidence.source_id) if evidence else None
            if number and self.documents[number - 1].get("url") == evidence.source_url:
                return f"[{number}]"
            return match[0]
        return EVIDENCE_RE.sub(replace, text)

    def invalid_citations(self, text: str) -> list[str]:
        invalid = set(EVIDENCE_RE.findall(text))
        for match in CITATION_RE.finditer(text):
            numbers = citation_numbers(match[1])
            if not numbers:
                invalid.add(match[0])
            for number in numbers:
                if not (1 <= number <= len(self.documents)) or not has_source_url(self.documents[number - 1]):
                    invalid.add(str(number))
        return sorted(invalid)
