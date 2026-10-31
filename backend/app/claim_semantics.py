"""Validate the provenance of per-claim semantic judgments from the auditor."""
import re
from typing import Any


def source_text(source: dict[str, Any]) -> str:
    parts = [source.get("original_title", source.get("title")), source.get("original_snippet", source.get("snippet"))]
    parts.extend(source.get(key) for key in ("content", "extract", "text"))
    return " ".join(str(part) for part in parts if part)


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def specific_topics_match(claim: str, passage: str) -> bool:
    """A named technical population cannot be supported by an unrelated acronym."""
    acronyms = set(re.findall(r"\b[A-Z]{2,6}\b", claim)) - {"FR", "EN"}
    for acronym in acronyms:
        if re.search(r"\b" + re.escape(acronym) + r"\b", passage, re.IGNORECASE):
            continue
        if acronym in ("IA", "AI") and re.search(r"intelligence artificielle|artificial intelligence|\b(?:IA|AI)\b", passage, re.IGNORECASE):
            continue
        return False
    return True


def apply_semantic_reviews(result: dict[str, Any], sources: list[dict[str, Any]], reviews: list[dict[str, Any]]) -> None:
    """A model label alone cannot validate a claim: require its cited exact passage."""
    by_id = {review.get("claim_id"): review for review in reviews if isinstance(review, dict)}
    for row in result["rows"] + result.get("raw_rows", []):
        row["semantic_status"] = "NOT_CHECKED"
        review = by_id.get(row.get("claim_id"))
        if not review:
            continue
        index = review.get("source_index")
        if type(index) is not int or index not in row.get("sources", []) or not 1 <= index <= len(sources):
            continue
        verdict = review.get("verdict")
        quote = normalized(str(review.get("exact_passage") or ""))
        if verdict == "SUPPORTED":
            if len(quote) < 20 or quote not in normalized(source_text(sources[index - 1])):
                continue
            if not specific_topics_match(row["full_sentence"], quote):
                continue
            numbers = {re.sub(r"[ \u00a0\u202f]", "", number).replace(",", ".") for number in re.findall(r"\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?", quote)}
            if not set(row.get("figures", [])) <= numbers:
                continue
            if row.get("status") in ("non retrouvé", "non sourcé", "source inexistante", "portée divergente", "formulation catégorique"):
                continue
            row.update(semantic_status="SUPPORTED", action="retain", normalized_status="SUPPORTED",
                       exact_passage=quote, evidence_url=sources[index - 1].get("url"),
                       note="Affirmation et périmètre examinés par le modèle sur un passage exact retrouvé.")
            if not row.get("figures"):
                row["status"] = "étayé"
        elif verdict in ("UNSUPPORTED", "CONTRADICTED"):
            row.update(semantic_status=verdict, action="rewrite_or_research", status="non étayé",
                       normalized_status=verdict, note=str(review.get("note") or "Le passage cité ne soutient pas l'affirmation."))
        elif verdict == "PARTIAL":
            row.update(semantic_status="PARTIAL", action="semantic_review",
                       note="Nuance nécessaire ; validation complète et modification effective non établies.")
    result["stats"]["semantic_supported"] = sum(row.get("semantic_status") == "SUPPORTED" for row in result["rows"])
    result["stats"]["semantic_pending"] = sum(row.get("semantic_status") != "SUPPORTED" for row in result["rows"])
    result["stats"]["non étayé"] = sum(row.get("status") == "non étayé" for row in result["rows"])
