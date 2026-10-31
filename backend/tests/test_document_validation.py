"""Regressions from the orientation HTML: structure, semantics and coverage."""
from app.claim_semantics import apply_semantic_reviews
from app.evidence_ledger import extract_deterministic_evidence_from_sources
from app.fact_verifier import compute_validation_status, format_verification_markdown, run_repair_loop, verify_report_figures
from app.providers import default_report_outline, format_report_outline_markdown
from app.report_claims import apply_claim_edits, iter_claim_spans
from app.report_publication import finalize_report
from app.research_planner import coverage_query, verify_aspect_coverage
from app.source_registry import SourceRegistry


SOURCES = [{"title": "Enquête diplômés", "url": "https://example.org/enquete", "tier": "A",
            "snippet": "L'insertion des diplômés atteint 94 % à 12 mois en 2024."}]


def test_repair_preserves_outline_numbering_code_and_neighboring_prose():
    outline = format_report_outline_markdown(default_report_outline("Quels bacs ? Quelles études ?", detail_level=1))
    body = "## Résultats\n\nIntroduction utile. Salaire inventé de 999 000 € [1]. Conclusion utile.\n\n- Salaire de 888 000 € [1].\n\n```python\n# exemple 99 %\n```\n"
    repaired, check = run_repair_loop(body, SOURCES)
    assert "Introduction utile." in repaired and "Conclusion utile." in repaired
    assert "999 000" not in repaired and "888 000" not in repaired
    assert "Donnée chiffrée retirée" not in repaired
    assert "- \n" not in repaired
    assert "# exemple 99 %" in repaired
    final = finalize_report(body, SourceRegistry(SOURCES), {"decision": "non_effectué"}, prefix=outline)
    assert final.startswith(outline)
    assert "1.1" in final
    assert check["stats"]["removed"] == 2


def test_structural_numbers_do_not_become_figures_but_leading_percentages_do():
    report = "> - **1.1 Choix de spécialités**\n> - **1.2 Études**\n94 % des diplômés sont en emploi [1]."
    check = verify_report_figures(report, SOURCES)
    assert check["stats"]["total"] == 1
    assert check["rows"][0]["figures"] == ["94"]


def test_offset_edits_do_not_replace_equal_text_in_other_locations_or_accept_stale_offsets():
    text = "Même phrase.\n\nMême phrase."
    spans = list(iter_claim_spans(text))
    repaired, applied = apply_claim_edits(text, [{**spans[1], "replacement": "Phrase corrigée."}])
    assert repaired == "Même phrase.\n\nPhrase corrigée."
    assert len(applied) == 1
    unchanged, applied = apply_claim_edits("Autre texte.", [{**spans[0], "replacement": "Erreur."}])
    assert unchanged == "Autre texte." and not applied


def test_model_unavailable_is_not_a_verdict_from_the_requested_model():
    check = verify_report_figures("L'insertion atteint 94 % à 12 mois [1].", SOURCES)
    markdown = format_verification_markdown(check, {"decision": "non_effectué", "performed": False, "auditor_model": "openai/gpt-6-astra"})
    assert "Contrôle déterministe effectué" in markdown
    assert "Relecture LLM indisponible" in markdown
    assert "Validation complète non réalisée" in markdown
    assert "Astra" not in markdown and "Validé" not in markdown


def test_numeric_presence_is_not_semantic_support_and_fabricated_quote_cannot_validate():
    text = "L'insertion atteint 94 % à 12 mois [1]."
    check = verify_report_figures(text, SOURCES)
    assert check["stats"]["retrouvé"] == 1
    assert compute_validation_status(check["stats"], {"decision": "validé"})[0] != "PASSED"
    review = {"claim_id": check["rows"][0]["claim_id"], "source_index": 1, "verdict": "SUPPORTED", "exact_passage": "Passage inventé contenant le taux de 94 %."}
    apply_semantic_reviews(check, SOURCES, [review])
    assert check["stats"]["semantic_supported"] == 0
    review["exact_passage"] = SOURCES[0]["snippet"]
    apply_semantic_reviews(check, SOURCES, [review])
    assert check["stats"]["semantic_supported"] == 1
    assert check["stats"]["semantic_pending"] == 0


def test_wrong_scope_claim_is_removed_by_its_review_without_removing_neighbors():
    text = "Contexte utile. Ce bachelor garantit une insertion à 94 % [1]. Autre constat prudent."
    check = verify_report_figures(text, SOURCES)
    row = next(row for row in check["rows"] if row.get("figures"))
    reviews = [{"claim_id": row["claim_id"], "source_index": 1, "verdict": "UNSUPPORTED", "note": "Population du bachelor absente de l'enquête."}]
    fixed, _ = run_repair_loop(text, SOURCES, semantic_reviews=reviews)
    assert "94 %" not in fixed and "Contexte utile." in fixed and "Autre constat prudent." in fixed


def test_orientation_guides_do_not_cover_recruitment_projections():
    checklist = [{"id": "P1", "question": "Quels métiers recruteront d'ici 2030 ?", "aspect": "Recrutements", "status": "pending"}]
    guide = [{"url": "https://example.org/guide", "tier": "A", "snippet": "Le bachelor privé se prépare en 3 ans et propose plusieurs formations."}]
    ledger = extract_deterministic_evidence_from_sources(guide)
    result = verify_aspect_coverage(checklist, guide, [{"id": "P1", "status": "covered", "evidence_ids": [ev.evidence_id for ev in ledger.list_all()]}])
    assert result[0]["status"] != "covered"
    assert "emploi" in coverage_query(result[0]) and "projections" in coverage_query(result[0])
    primary = [{"url": "https://example.org/projection", "tier": "A", "snippet": "Près de 760 000 recrutements annuels sont projetés d'ici 2030."}]
    result = verify_aspect_coverage(checklist, primary, [{"id": "P1", "status": "covered", "evidence_ids": ["EV_0001"]}])
    assert result[0]["status"] == "covered"
    # Curation cannot preserve a coverage verdict after its proof disappears.
    assert verify_aspect_coverage(result, guide)[0]["status"] != "covered"


def test_bachelor_quote_cannot_validate_iut_claim_even_with_same_number_and_model_label():
    sources = [{"url": "https://example.org/bachelor", "snippet": "Le bachelor privé se prépare en 3 ans et propose une formation professionnalisante."}]
    check = verify_report_figures("Le cursus en IUT se prépare en 3 ans [1].", sources)
    review = {"claim_id": check["rows"][0]["claim_id"], "source_index": 1, "verdict": "SUPPORTED", "exact_passage": sources[0]["snippet"]}
    apply_semantic_reviews(check, sources, [review])
    assert check["stats"]["semantic_supported"] == 0
