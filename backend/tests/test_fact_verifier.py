from app.fact_verifier import format_verification_markdown, remedy_unverified_claims, verify_report_figures

SOURCES = [
    {"title": "DARES", "url": "https://dares.example/a", "snippet": "Le taux d'insertion atteint 94 % en 2024, soit 38 000 € bruts."},
    {"title": "Cereq", "url": "https://cereq.example/b", "snippet": "Un taux d'insertion de 94 % est observé."},
    {"title": "Blog", "url": "https://blog.example/c", "snippet": "Les salaires augmentent."},
    {"title": "Image", "url": "https://img.example", "img_src": "https://img.example/i.jpg", "media_type": "image"},
]


def rows_by_status(report):
    result = verify_report_figures(report, SOURCES)
    return {r["status"]: r for r in result["rows"]}, result


def test_figure_found_in_two_sources_is_high_confidence():
    rows, _ = rows_by_status("L'insertion atteint 94 % [1][2].")
    assert rows["retrouvé"]["confidence"] == "élevée"


def test_figure_found_in_single_source_is_medium():
    rows, _ = rows_by_status("Le salaire est de 38 000 € bruts [1].")
    assert rows["retrouvé"]["confidence"] == "moyenne"


def test_uncited_figure_is_flagged():
    rows, _ = rows_by_status("Le taux atteint 77 % en 2030.")
    assert rows["non sourcé"]["confidence"] == "faible"


def test_figure_absent_from_cited_source_is_not_found():
    rows, _ = rows_by_status("Le taux atteint 94 % [3].")
    assert "non retrouvé" in rows


def test_nonexistent_source_and_years_and_headings_ignored():
    rows, result = rows_by_status("## 1.1 Titre 45 %\nEn 2024 la situation évolue [1].\nChiffre 12 % [9].")
    assert list(rows) == ["source inexistante"]
    assert result["stats"]["total"] == 1


def test_markdown_registry_lists_anomalies_first_and_states_rule():
    result = verify_report_figures("Taux 94 % [1][2]. Autre 77 %.", SOURCES)
    md = format_verification_markdown(result)
    assert md.startswith("## Registre de vérification factuelle")
    assert md.index("non sourcé") < md.index("retrouvé |")
    assert "périmètre" in md
    assert format_verification_markdown({"rows": [], "stats": {}}) == ""


def test_absolute_formulations_are_flagged():
    result = verify_report_figures(
        "Vulnérabilité IA : NULLE pour la santé. Le filtre automatisé binaire décide tout. Nuance prudente ici.", SOURCES,
    )
    statuses = [r["status"] for r in result["rows"]]
    assert statuses.count("formulation catégorique") == 2
    assert "formulations catégoriques" in format_verification_markdown(result)


def test_remedy_unverified_claims():
    text = "Vulnérabilité IA : NULLE dans ce secteur. Aucun risque à prévoir. Taux de 84 % pour les diplômés."
    result = verify_report_figures(text, SOURCES)
    remedied = remedy_unverified_claims(text, result)
    assert "NULLE" not in remedied
    assert "très faible" in remedied
    assert "Aucun risque" not in remedied
    assert "ordre de grandeur indicatif" in remedied


def test_claim_evidence_validator_scope_divergence():
    sources_with_foreign_workers = [
        {
            "title": "Arrêté métiers en tension",
            "url": "https://travail-emploi.gouv.fr/arrete",
            "snippet": "Publication de l'arrêté s'appuyant sur les critères de présence significative des travailleurs étrangers non communautaires.",
        }
    ]
    report = "La filière ST2S garantit un accès aux IFSI à 95 % selon le ministère [1]."
    result = verify_report_figures(report, sources_with_foreign_workers)
    rows = {r["status"]: r for r in result["rows"]}
    assert "portée divergente" in rows
    assert rows["portée divergente"]["entailment"] == "unsupported"
    assert rows["portée divergente"]["action"] == "rewrite_or_research"


def test_remedy_unverified_claims_nuances_categorical_terms():
    text = (
        "La filière ST2S garantit un accès privilégié aux IFSI. "
        "Ce sont les deux seuls leviers structurels. "
        "Les métiers de terrain sont par nature non automatisables. "
        "Une situation de plein emploi structurel est observée."
    )
    remedied = remedy_unverified_claims(text)
    assert "garantit un accès privilégié" not in remedied
    assert "offre une voie d'accès ciblée" in remedied
    assert "deux seuls leviers structurels" not in remedied
    assert "deux leviers structurels majeurs" in remedied
    assert "par nature non automatisables" not in remedied
    assert "résistance opérationnelle" in remedied
    assert "plein emploi structurel" not in remedied


def test_format_verification_markdown_with_astra_audit_review():
    result = verify_report_figures("L'insertion atteint 94 % [1][2].", SOURCES)
    audit_review = {
        "decision": "remanié",
        "auditor_model": "openai/gpt-6-astra",
        "critique": "Les affirmations sur l'insertion professionnelle sont validées à 94% par la DARES et le Céreq.",
        "verified_facts": [
            "Taux d'insertion de 94 % confirmé par deux sources distinctes [1][2].",
        ],
        "warnings": [
            "Périmètre limité aux diplômés de la promotion 2024.",
        ],
        "sources_assessment": "Excellente couverture institutionnelle primaire (DARES, Céreq).",
    }
    md = format_verification_markdown(result, audit_review=audit_review)
    assert "## Registre de vérification factuelle & Arbitrage critique" in md
    assert "Gpt 6 Astra" in md or "GPT-6 Astra" in md or "Astra" in md
    assert "Remanié & Sécurisé" in md
    assert "Arbitrage factuel" in md
    assert "Taux d'insertion de 94 % confirmé" in md
    assert "Périmètre limité aux diplômés" in md
    assert "Excellente couverture institutionnelle" in md
    assert "affirmations chiffrées retrouvées" in md


def test_validation_status_never_contradicts_unverified_claims():
    # Même si le LLM prétend "validé", 2 affirmations non retrouvées DOIVENT forcer un statut avec réserves
    result = verify_report_figures("Salaire 999 000 € [1]. Insertion 888 % [2].", SOURCES)
    audit_review = {
        "decision": "validé",  # LLM hallucinant ou trop optimiste
        "auditor_model": "openai/gpt-6-astra",
        "critique": "Analyse globale effectuée.",
    }
    md = format_verification_markdown(result, audit_review=audit_review)
    assert "Conformité documentaire intégrale" not in md
    assert "Validé avec réserves" in md or "Révision requise" in md


def test_universal_multi_domain_scope_divergence_and_categorical_nuances():
    # 1. Domaine médical : essai in vitro détourné pour affirmer une guérison clinique chez le patient
    medical_sources = [
        {
            "title": "Étude préclinique sur culture cellulaire",
            "url": "https://pubmed.example/study1",
            "snippet": "L'inhibition virale in vitro sur modèle murin atteint 85 % après 48 heures d'exposition.",
        }
    ]
    medical_report = "Ce protocole assure une guérison clinique chez le patient à 85 % [1]."
    med_res = verify_report_figures(medical_report, medical_sources)
    med_rows = {r["status"]: r for r in med_res["rows"]}
    assert "portée divergente" in med_rows

    # 2. Orthogonalité lexicale totale sur une affirmation causale forte
    unrelated_sources = [
        {
            "title": "Réglementation maritime internationale",
            "url": "https://maritime.example/doc",
            "snippet": "Les navires porte-conteneurs transocéaniques respectent un tirant d'eau maximal dans les détroits.",
        }
    ]
    unrelated_report = "L'architecture quantique supraconductrice garantit une réduction de 45 % de la latence énergétique [1]."
    unrel_res = verify_report_figures(unrelated_report, unrelated_sources)
    unrel_rows = {r["status"]: r for r in unrel_res["rows"]}
    assert "portée divergente" in unrel_rows

    # 3. Nuances universelles multi-domaines (santé, finance, cybersécurité)
    raw_multi = "Ce traitement est sans aucun effet secondaire, offre un rendement garanti et un chiffrement inviolable."
    remedied_multi = remedy_unverified_claims(raw_multi)
    assert "sans aucun effet secondaire" not in remedied_multi
    assert "rendement garanti" not in remedied_multi
    assert "inviolable" not in remedied_multi


def test_run_repair_loop_multi_cycles():
    from app.fact_verifier import run_repair_loop

    # Rapport contenant des chiffres non corroborés et des expressions catégoriques
    raw_draft = (
        "L'insertion professionnelle atteint 94 % à 12 mois [1]. "
        "Les débutants perçoivent 999 000 € bruts annuels [1]. "
        "Le taux de réussite est de 100 % garanti pour tous les candidats."
    )
    remedied_text, final_result = run_repair_loop(raw_draft, SOURCES, max_cycles=2)
    assert "100 % garanti" not in remedied_text
    assert "ordre de grandeur indicatif non consolidé" in remedied_text
    # Vérification que le badge de statut ne peut pas être PASSED avec des affirmations non consolidées
    stats = final_result.get("stats", {})
    from app.fact_verifier import compute_validation_status
    code, badge = compute_validation_status(stats)
    assert code != "PASSED"
    assert "PUBLISH_WITH_LIMITATIONS" in code or "REMEDIED" in code or "CAVEATS" in code





