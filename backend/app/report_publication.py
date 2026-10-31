"""Final deterministic gate shared by both report generation paths."""
from __future__ import annotations

import logging
from typing import Any

from .fact_verifier import compute_validation_status, format_verification_markdown, run_repair_loop, verify_report_figures
from .source_registry import SourceRegistry
from .research_planner import format_coverage_limits

_logger = logging.getLogger(__name__)


def finalize_report(text: str, registry: SourceRegistry, audit: dict[str, Any], *, prefix: str = "") -> str:
    text = registry.resolve_evidence_citations(text)
    text, check = run_repair_loop(text, registry.export_sources(), semantic_reviews=audit.get("claim_reviews"))
    check["stats"]["coverage_missing"] = sum(item.get("status") != "covered" for item in audit.get("coverage", []))
    invalid = registry.invalid_citations(prefix + text)
    code, _ = compute_validation_status(check["stats"], audit)
    _logger.info(
        "Report gate sources=%d evidence=%d claims=%d invalid_citations=%d status=%s",
        len(registry.documents), registry.ledger.count(), len(check["rows"]), len(invalid), code,
    )
    if invalid or not text.strip() or not registry.documents or code == "REQUIRES_REVISION":
        # Never save/export the failed draft as an ordinary completed report.
        return (
            "## Révision documentaire requise\n\n"
            "Le rapport n'a pas été publié : les preuves disponibles ne permettent pas de valider "
            "ses affirmations ou ses références. Une nouvelle recherche ciblée est nécessaire.\n\n"
            "Les documents effectivement collectés restent consultables dans les sources.\n"
        )
    # The auditor's prose is also generated text. Do not reintroduce unchecked
    # numbers or references through its summary or its 'verified_facts' list.
    safe_audit = {
        "auditor_model": audit.get("auditor_model", "Auditeur"),
        "decision": audit.get("decision", ""),
        "performed": audit.get("performed", audit.get("decision") not in ("non_effectué", "indisponible")),
        "applied_count": audit.get("applied_count", 0),
        "critique": (
            "Relecture par le modèle indisponible ; contrôle déterministe uniquement."
            if audit.get("decision") == "non_effectué"
            else "Relecture effectuée ; résultat déterministe ci-dessous."
        ),
    }
    def checked_audit_text(value: Any) -> str:
        candidate = registry.resolve_evidence_citations(str(value or ""))
        if registry.invalid_citations(candidate):
            return ""
        result = verify_report_figures(candidate, registry.export_sources())
        if any(row.get("action") == "rewrite_or_research" for row in result["rows"]):
            return ""
        return candidate

    # Keep useful criticism and scope warnings when their own references and
    # quantities pass the same checks as the body of the report.
    for field in ("critique", "sources_assessment"):
        checked = checked_audit_text(audit.get(field))
        if checked:
            safe_audit[field] = checked
    for field in ("warnings", "verified_facts"):
        safe_audit[field] = [checked for value in (audit.get(field) or []) if (checked := checked_audit_text(value))]
    safe_audit["verified_facts"] = [row["full_sentence"] for row in check["rows"] if row.get("semantic_status") == "SUPPORTED"][:4]
    if check["stats"].get("semantic_pending") and safe_audit["performed"]:
        safe_audit["critique"] = "Examen sémantique incomplet ; seules les affirmations étayées sur un passage exact sont comptées comme vérifiées."
    removed = check["stats"].get("removed", 0)
    removal_note = f"\n> Données non étayées retirées avant publication : {removed}.\n" if removed else ""
    return prefix + text + removal_note + "\n" + format_coverage_limits(audit.get("coverage", [])) + "\n" + format_verification_markdown(check, safe_audit)
