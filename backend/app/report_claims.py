"""Locate prose claims and table cells without touching Markdown structure."""
import re
from hashlib import sha256
from typing import Any, Iterator


def iter_claim_spans(markdown: str) -> Iterator[dict[str, Any]]:
    offset = 0
    fence = ""
    for raw_line in markdown.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        marker = re.match(r"^(`{3,}|~{3,})", stripped)
        if marker:
            token = marker[1]
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
        elif stripped and not fence and not re.match(r"^#{1,6}\s", stripped) and not set(stripped) <= set("-|: "):
            table = stripped.startswith("|") and stripped.endswith("|")
            if table:
                delimiters = [m.start() for m in re.finditer(r"(?<!\\)\|", line)]
                bounds = [(a + 1, b) for a, b in zip(delimiters, delimiters[1:])]
            else:
                # Structural numbering is never a quantitative claim.
                prefix = re.match(r"\s*(?:>\s*)*(?:(?:[-*+] |\d+[.)]\s+))?", line)
                start = prefix.end() if prefix else 0
                stops = [m for m in re.finditer(r"(?<=[.!?])\s+", line[start:])]
                bounds = []
                for stop in stops:
                    end = start + stop.start()
                    bounds.append(end)
                origin = start
                bounds = [(a, b) for a, b in zip([origin] + [origin + m.end() for m in stops], bounds + [len(line)])]
            for start, end in bounds:
                segment = line[start:end]
                left = len(segment) - len(segment.lstrip())
                text = segment.strip()
                if not text:
                    continue
                begin = offset + start + left
                yield {
                    "full_sentence": text, "span_start": begin, "span_end": begin + len(text),
                    "claim_id": "CL_" + sha256(text.encode()).hexdigest()[:16],
                    "table_cell": table, "table_row": stripped if table else "",
                }
        offset += len(raw_line)


def apply_claim_edits(markdown: str, edits: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Apply verified, non-overlapping offsets from this exact draft, back to front."""
    applied = []
    boundary = len(markdown)
    for edit in sorted(edits, key=lambda value: value["span_start"], reverse=True):
        start, end = edit["span_start"], edit["span_end"]
        if start < 0 or end > boundary or markdown[start:end] != edit["full_sentence"]:
            continue
        replacement = edit.get("replacement", "")
        if replacement != markdown[start:end]:
            markdown = markdown[:start] + replacement + markdown[end:]
            applied.append(edit)
            if not replacement:
                line_start = markdown.rfind("\n", 0, start) + 1
                line_end = markdown.find("\n", start)
                line_end = len(markdown) if line_end < 0 else line_end
                if re.fullmatch(r"[ \t]*(?:>[ \t]*)*(?:[-*+]|\d+[.)])?[ \t]*", markdown[line_start:line_end]):
                    # Only the emptied line is cleaned; code blocks and untouched
                    # paragraphs retain their exact whitespace and indentation.
                    markdown = markdown[:line_start] + markdown[line_end:]
                    start = line_start
        boundary = start
    return markdown, applied
