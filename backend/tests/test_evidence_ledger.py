from app.evidence_ledger import EvidenceLedger, extract_deterministic_evidence_from_sources


def test_evidence_ledger_add_and_deduplicate():
    ledger = EvidenceLedger()
    item1 = ledger.add_evidence(
        source_id="1",
        source_url="https://dares.travail-emploi.gouv.fr/metiers2030",
        source_title="Les métiers en 2030",
        exact_passage="Entre 2019 et 2030, près de 760 000 postes seraient à pourvoir chaque année en moyenne.",
        claim_type="statistic",
        source_tier="A",
        normalized_value=760000.0,
        nature="projection",
    )
    assert item1.evidence_id == "EV_0001"
    assert item1.source_family_id == "dares_travail_emploi_gouv_fr"
    assert ledger.count() == 1

    # Dédoublonnage d'un passage quasi-identique de la même source
    item2 = ledger.add_evidence(
        source_id="1",
        source_url="https://dares.travail-emploi.gouv.fr/metiers2030",
        source_title="Les métiers en 2030",
        exact_passage="760 000 postes seraient à pourvoir chaque année en moyenne.",
        claim_type="statistic",
        source_tier="A",
    )
    assert item2.evidence_id == "EV_0001"
    assert ledger.count() == 1


def test_extract_deterministic_evidence_from_sources():
    sources = [
        {
            "source_id": "1",
            "url": "https://dares.travail-emploi.gouv.fr/etude",
            "title": "DARES Rapport",
            "tier": "A",
            "snippet": "L'insertion professionnelle s'élève à 94 % à 12 mois. Ce résultat s'explique par un fort dynamisme.",
            "content": "Attention au biais de poursuite d'études qui modifie le dénominateur de la cohorte.",
        },
        {
            "source_id": "2",
            "url": "https://legifrance.gouv.fr/arrete",
            "title": "Arrêté ministériel",
            "tier": "A",
            "snippet": "En application de l'article L. 123-4 du code du travail, l'arrêté fixe les conditions.",
        },
    ]

    ledger = extract_deterministic_evidence_from_sources(sources, sub_question_id="SQ_1")
    items = ledger.list_all()

    # Doit avoir extrait le chiffre, la réserve méthodologique et le texte réglementaire
    types = [it.claim_type for it in items]
    assert "statistic" in types
    assert "methodological_caveat" in types
    assert "regulatory_norm" in types

    formatted = ledger.format_for_analysts()
    assert "GRAND LIVRE DES PREUVES" in formatted
    assert "EV_0001" in formatted
    assert "94" in formatted


def test_evidence_ledger_serialization():
    ledger = EvidenceLedger()
    ledger.add_evidence(
        source_id="1",
        source_url="https://test.example/doc",
        source_title="Test Doc",
        exact_passage="Une affirmation factuelle bien sourcée.",
        claim_type="factual_statement",
    )
    data = ledger.to_dict_list()
    assert len(data) == 1
    assert data[0]["evidence_id"] == "EV_0001"

    restored = EvidenceLedger.from_dict_list(data)
    assert restored.count() == 1
    assert restored.get("EV_0001").exact_passage == "Une affirmation factuelle bien sourcée."

