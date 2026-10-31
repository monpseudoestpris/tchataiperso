"""Regression coverage for evidence -> citations -> persistence -> HTML."""
from html.parser import HTMLParser

import pytest

from app.chat_export_html import generate_chat_export_html
from app.deep_search_html import generate_report_html, markdown_to_html
from app.evidence_ledger import EvidenceLedger
from app.fact_verifier import format_verification_markdown, run_repair_loop, verify_report_figures
from app.report_publication import finalize_report
from app.source_registry import SourceRegistry


SOURCES = [
    {"title": "Enquête A", "url": "https://example.org/a", "snippet": "L'insertion de la promotion 2024 atteint 94 % à 12 mois."},
    {"title": "Enquête B", "url": "https://example.net/b", "snippet": "L'insertion de la promotion 2024 atteint 94 % à 12 mois."},
]


class Links(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.targets = set()
        self.citations = []
        self.external = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.targets.add(attrs["id"])
        if tag == "a":
            href = attrs.get("href", "")
            if href.startswith("#source-"):
                self.citations.append(href[1:])
            if href.startswith("https://"):
                self.external.append(href)


def test_registry_survives_storage_and_resolves_only_known_evidence():
    registry = SourceRegistry(SOURCES)
    saved = registry.export_sources()
    assert saved[0]["source_id"].startswith("SRC_")
    assert saved[0]["evidence"][0]["source_url"] == SOURCES[0]["url"]
    restored = SourceRegistry(saved)
    assert restored.ledger.to_dict_list() == registry.ledger.to_dict_list()
    text = restored.resolve_evidence_citations("Constat [EV_0001], inconnu [EV_9999].")
    assert text == "Constat [1], inconnu [EV_9999]."
    assert restored.invalid_citations(text) == ["EV_9999"]
    saved[0]["url"] = "https://other.example"
    assert registry.export_sources()[0]["url"] == SOURCES[0]["url"]


def test_sparse_reordered_evidence_ids_are_preserved():
    registry = SourceRegistry(SOURCES)
    items = registry.ledger.to_dict_list()[::-1]
    items[0]["evidence_id"] = "EV_0042"
    ledger = EvidenceLedger.from_dict_list(items)
    assert ledger.get("EV_0042").source_url == SOURCES[1]["url"]
    assert ledger.get("EV_0001").source_url == SOURCES[0]["url"]
    assert ledger.add_evidence("other", "https://other.example", "Autre", "Autre preuve suffisamment longue.").evidence_id == "EV_0043"


def test_report_export_preserves_duplicate_snippet_source_numbers():
    document = generate_report_html("Test", "Test", "L'insertion atteint 94 % [1-2].", SOURCES)
    links = Links(document)
    assert links.citations == ["source-1", "source-2"]
    assert set(links.citations) <= links.targets
    assert SOURCES[1]["url"] in links.external


def test_missing_citations_never_produce_orphan_html_links():
    document, _ = markdown_to_html("Références [1, 3] et [2–4].", SOURCES)
    links = Links(document)
    assert links.citations == ["source-1", "source-2"]
    assert "référence indisponible" in document


def test_conversation_export_maps_local_source_numbers_to_global_bibliography():
    messages = [
        {"role": "assistant", "content": "Premier constat [1].", "sources": [SOURCES[0]]},
        {"role": "assistant", "content": "Second constat [1].", "sources": [SOURCES[1]]},
    ]
    links = Links(generate_chat_export_html("Discussion", messages, scope="conversation"))
    assert links.citations == ["source-1", "source-2"]
    assert set(links.citations) <= links.targets
    assert messages[1]["content"] == "Second constat [1]."


@pytest.mark.parametrize("value,source_value", [("7,6 millions", "7,4 millions"), ("95 %", "94 %"), ("94 %", "194 %"), ("800 000 emplois", "760 000 emplois")])
def test_nearby_values_and_substrings_cannot_validate_a_number(value, source_value):
    sources = [{"url": "https://example.org/a", "snippet": f"Prévision : {source_value}."}]
    result = verify_report_figures(f"La prévision atteint {value} [1].", sources)
    assert result["stats"]["non retrouvé"] == 1


def test_repair_removes_all_repeated_unsupported_benchmarks_and_keeps_table_labels():
    text = "Salaire 999 000 € [9]. Salaire 999 000 € [9].\n| Filière | Salaire |\n|---|---|\n| Cyber | 999 000 € indicatifs [9] |"
    fixed, result = run_repair_loop(text, SOURCES)
    assert "999 000" not in fixed
    assert "Cyber" in fixed and "Donnée non établie" in fixed
    assert result["stats"]["source inexistante"] == 0
    assert result["stats"]["removed"] > 0


def test_same_figure_in_distinct_claims_is_not_collapsed():
    result = verify_report_figures("L'insertion atteint 94 % [1]. La satisfaction atteint 94 % [1].", SOURCES)
    assert result["stats"]["total"] == 2
    assert len({r["claim_id"] for r in result["rows"]}) == 2


def test_indicative_caveat_does_not_validate_an_unsupported_benchmark():
    result = verify_report_figures("Salaire de 999 000 € à titre indicatif [1].", SOURCES)
    assert result["rows"][0]["action"] == "rewrite_or_research"


def test_gate_blocks_non_numeric_orphan_citations_and_empty_corpus():
    for sources in (SOURCES, []):
        result = finalize_report("Affirmation inventée [99].", SourceRegistry(sources), {"decision": "validé"})
        assert "n'a pas été publié" in result
        assert "Affirmation inventée" not in result


def test_gate_resolves_evidence_and_does_not_trust_auditor_summary():
    result = finalize_report(
        "L'insertion atteint 94 % à 12 mois [EV_0001].", SourceRegistry(SOURCES),
        {"decision": "validé", "verified_facts": ["Salaire de 999 000 € [99]."], "critique": "99 % [99]", "warnings": ["Cohorte restreinte, comparaison à contextualiser."]},
    )
    assert "94 %" in result and "[1]" in result
    assert "999 000" not in result and "[99]" not in result
    assert "Cohorte restreinte" in result


def test_table_verifies_each_cell_against_its_own_reference():
    sources = [SOURCES[0], {"url": "https://example.net/salary", "snippet": "Le salaire médian atteint 38 000 € bruts."}]
    text = "| Parcours | Insertion | Salaire |\n|---|---|---|\n| Exemple | 94 % [1] | 38 000 € [2] |"
    fixed, result = run_repair_loop(text, sources)
    assert fixed == text
    assert result["stats"]["retrouvé"] == 2


def test_translation_cannot_become_a_new_numeric_proof():
    source = dict(SOURCES[0], original_snippet=SOURCES[0]["snippet"], snippet="L'insertion atteint 99 % selon une traduction erronée.")
    result = verify_report_figures("L'insertion atteint 99 % [1].", [source])
    assert result["stats"]["non retrouvé"] == 1
    registry = SourceRegistry([source])
    assert "94 %" in registry.ledger.get("EV_0001").exact_passage


def test_failed_historical_report_does_not_export_the_unvalidated_body():
    text = "Comparatif douteux : 999 000 € [1].\n🔴 Révision requise"
    report = generate_report_html("Test", "Test", text, SOURCES)
    chat = generate_chat_export_html("Test", [{"role": "assistant", "content": text, "sources": SOURCES}])
    assert "999 000" not in report and "999 000" not in chat


def test_verification_table_cleans_claim_artifacts_without_splitting_escaped_pipes():
    result = {
        "rows": [{"claim": r"\| Cybersécurité ██████████ : A | B |", "occurrences": 1,
                  "sources": [1], "status": "mention indicative nuancée", "confidence": "indicative",
                  "action": "retained_with_caveat"}],
        "stats": {"total": 1, "mention indicative nuancée": 1},
    }
    markdown = format_verification_markdown(result)
    assert "████" not in markdown
    assert r"A \| B" in markdown
    rendered, _ = markdown_to_html(markdown, SOURCES)
    assert rendered.count("<td") == 6
    assert '<td>Cybersécurité : A | B</td>' in rendered
    assert '<td class="report-metadata-cell">indicative</td>' in rendered
    assert '<td class="report-metadata-cell">retained_with_caveat</td>' in rendered
    # Historical Markdown is cleaned at render time as well.
    legacy = markdown.replace(r"Cybersécurité : A \| B", r"\| Santé & Soins ██████████ \| A \| B")
    rendered_legacy, _ = markdown_to_html(legacy, SOURCES)
    assert '<td>Santé &amp; Soins | A | B</td>' in rendered_legacy
    assert rendered_legacy.count("<td") == 6
    for export in (
        generate_report_html("Test", "Test", legacy, SOURCES),
        generate_chat_export_html("Test", [{"role": "assistant", "content": legacy, "sources": SOURCES}]),
    ):
        assert "white-space: nowrap;" in export
        assert "table.report-verification-table" in export


def test_regular_table_keeps_literal_pipes_and_meaningful_block_graphs():
    rendered, _ = markdown_to_html("| Expression | Graphique |\n|---|---|\n| A \\| B | █████ |")
    assert '<table class="report-table">' in rendered
    assert '<td>A | B</td>' in rendered
    assert '<td>█████</td>' in rendered
