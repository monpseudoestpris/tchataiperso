"""Extract explicit user questions without imposing a subject-specific outline."""
import re


def explicit_questions(query: str) -> list[str]:
    numbered = re.split(r"(?:^|\n)\s*(?:[-*]|\d+[.)])\s+", query)
    if len(numbered) > 2:
        return [q.strip() for q in numbered[1:] if q.strip()]
    questions = [q.strip() + " ?" for q in query.split("?")[:-1] if q.strip()]
    return questions if len(questions) > 1 else []


def has_generic_headings(parts: list[dict]) -> bool:
    patterns = (
        "cadre général", "fondations structurelles", "analyse approfondie des voies porteuses",
        "analyse critique & vision 360", "grands tableaux comparatifs", "genèse, mécanismes",
    )
    return any(any(p in str(part.get("heading", "")).lower() for p in patterns) for part in parts)
