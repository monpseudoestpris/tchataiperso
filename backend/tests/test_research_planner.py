from app.evidence_ledger import EvidenceItem
from app.research_planner import ResearchPlan, SubQuestion, audit_sub_question_coverage


def test_research_plan_coverage_audit():
    sq1 = SubQuestion(
        id="SQ_1",
        title="Bacs et formations",
        question="Quelles formations et spécialités de baccalauréat choisir ?",
        expected_evidence=["Attendus Parcoursup", "Conditions d'accès"],
    )
    sq2 = SubQuestion(
        id="SQ_2",
        title="Tensions et recrutements",
        question="Quels secteurs recruteront le plus d'ici 2030 ?",
        expected_evidence=["Projections d'embauche", "Taux d'insertion"],
    )
    plan = ResearchPlan(main_topic="Orientation et métiers 2030", sub_questions=[sq1, sq2])

    # 1. Avant preuves : NOT_STARTED
    audit_sub_question_coverage(plan, [])
    assert sq1.status == "NOT_STARTED"
    assert sq2.status == "NOT_STARTED"
    assert not plan.all_covered()

    # 2. Ajout d'une preuve Tier A pour SQ_2
    ev1 = EvidenceItem(
        evidence_id="EV_0001",
        source_id="1",
        source_url="https://dares.travail-emploi.gouv.fr/metiers2030",
        source_title="Les métiers en 2030",
        exact_passage="Près de 760 000 recrutements annuels attendus d'ici 2030.",
        claim_type="statistic",
        source_tier="A",
        source_family_id="dares_travail_emploi_gouv_fr",
        sub_question_id="SQ_2",
    )
    audit_sub_question_coverage(plan, [ev1])
    assert sq2.status == "COVERED"
    assert sq1.status == "NOT_STARTED"

    # 3. Ajout d'une preuve Tier C pour SQ_1
    ev2 = EvidenceItem(
        evidence_id="EV_0002",
        source_id="2",
        source_url="https://blog.example/bacs",
        source_title="Blog orientation",
        exact_passage="Les bacs généraux et technologiques préparent à l'université.",
        claim_type="factual_statement",
        source_tier="C",
        source_family_id="blog_example",
        sub_question_id="SQ_1",
    )
    audit_sub_question_coverage(plan, [ev1, ev2])
    assert sq1.status == "PARTIAL"
    assert not plan.all_covered()

    # 4. Ajout d'une 2e preuve d'une famille différente pour SQ_1
    ev3 = EvidenceItem(
        evidence_id="EV_0003",
        source_id="3",
        source_url="https://onisep.fr/bacs",
        source_title="Onisep Fiches",
        exact_passage="Le baccalauréat général ou technologique offre des parcours variés.",
        claim_type="factual_statement",
        source_tier="B",
        source_family_id="onisep_fr",
        sub_question_id="SQ_1",
    )
    audit_sub_question_coverage(plan, [ev1, ev2, ev3])
    assert sq1.status == "COVERED"
    assert plan.all_covered()

