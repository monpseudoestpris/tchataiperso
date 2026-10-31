"""Planificateur de recherche par sous-questions et preuves attendues (ResearchPlanner).

Architecture cLAIr DeepSearch V2 — Evidence First.
Gère la décomposition d'un objectif de recherche en sous-questions ciblées,
le suivi de leur état de couverture (NOT_STARTED, SEARCHING, PARTIAL, COVERED)
et l'audit des preuves collectées dans l'Evidence Ledger.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
import unicodedata
from .claim_semantics import specific_topics_match


def expected_evidence_types(question: str) -> set[str]:
    text = unicodedata.normalize("NFKD", question.lower()).encode("ascii", "ignore").decode()
    types = set()
    if re.search(r"avenir|futur|emergen|prospect|project|prevision|recruter|20[3-9]\d", text):
        types.add("projection")
    if re.search(r"emploi|insertion|recrut|debouche|marche du travail|metiers|etudes.*avenir", text):
        types.add("employment_data")
    if re.search(r"reglement|jurid|grade|certification|conditions? d.acces|norme", text):
        types.add("regulatory_norm")
    return types


def evidence_answers_question(evidence: Any, question: str, expected: set[str]) -> bool:
    """Reject topical guides when the question requires measured outcomes or forecasts."""
    passage = getattr(evidence, "exact_passage", "")
    if not specific_topics_match(question, passage):
        return False
    flat = unicodedata.normalize("NFKD", passage.lower()).encode("ascii", "ignore").decode()
    if "projection" in expected and getattr(evidence, "nature", "") != "projection":
        return False
    if "employment_data" in expected and (
        getattr(evidence, "claim_type", "") not in ("statistic", "scientific_finding")
        or not re.search(r"emplo|insertion|recrut|offres|hiring|employment|vacanc|jobs", flat)
    ):
        return False
    if "regulatory_norm" in expected and getattr(evidence, "claim_type", "") != "regulatory_norm":
        return False
    def terms(text: str) -> set[str]:
        flat = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
        return {word[:6] for word in re.findall(r"[a-z]{5,}", flat)} - {
            "quelle", "quelles", "quels", "choisi", "donnee", "preuve", "source", "avenir", "etudes",
        }
    overlap = terms(question) & terms(passage)
    return bool(overlap) and (len(overlap) >= 2 or bool(expected))

SubQuestionStatus = Literal[
    "NOT_STARTED",      # Recherche non encore initiée
    "SEARCHING",        # Requêtes en cours d'exécution
    "PARTIAL",          # Preuves partielles ou tier C/D sans données consolidées
    "COVERED",          # Couverture robuste par au moins 2 sources indépendantes ou 1 source Tier A/B directe
    "CONFLICTING",      # Contradiction importante ou divergence entre sources identifiée
    "INSUFFICIENT",     # Preuves insuffisantes nécessitant recherche complémentaire ou signalement
    "BUDGET_EXHAUSTED", # Limite de requêtes/budget atteinte, continuer avec limites explicites
]


@dataclass
class SubQuestion:
    id: str                                  # SQ_1, SQ_2...
    title: str                               # Titre court
    question: str                            # Question explicite
    expected_evidence: list[str]             # Types de preuves attendues
    status: SubQuestionStatus = "NOT_STARTED"
    targeted_queries: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchPlan:
    main_topic: str
    sub_questions: list[SubQuestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "main_topic": self.main_topic,
            "sub_questions": [sq.to_dict() for sq in self.sub_questions],
        }

    def get_sub_question(self, sq_id: str) -> SubQuestion | None:
        for sq in self.sub_questions:
            if sq.id == sq_id:
                return sq
        return None

    def all_covered(self) -> bool:
        return bool(self.sub_questions) and all(sq.status == "COVERED" for sq in self.sub_questions)

    def coverage_summary(self) -> dict[str, str]:
        return {sq.id: sq.status for sq in self.sub_questions}

    def format_for_prompt(self) -> str:
        lines = [f"### PLAN DE RECHERCHE & PREUVES ATTENDUES : « {self.main_topic} »"]
        for sq in self.sub_questions:
            status_emoji = {
                "NOT_STARTED": "⏳",
                "SEARCHING": "🔍",
                "PARTIAL": "🟡",
                "COVERED": "🟢",
                "CONFLICTING": "⚡",
                "INSUFFICIENT": "⚠️",
                "BUDGET_EXHAUSTED": "🛑",
            }.get(sq.status, "⚪")
            lines.append(f"{status_emoji} **[{sq.id}] {sq.title}** ({sq.status}) : {sq.question}")
            if sq.expected_evidence:
                lines.append(f"   *Preuves requises* : {', '.join(sq.expected_evidence)}")
        return "\n".join(lines)


def audit_sub_question_coverage(
    plan: ResearchPlan,
    evidence_items: list[Any],
    budget_exhausted: bool = False,
) -> ResearchPlan:
    """Audit déterministe de la couverture de chaque sous-question en fonction des preuves collectées.

    Assigne les statuts normalisés de l'Evidence Auditor :
    - NOT_STARTED : 0 preuve
    - INSUFFICIENT : 0 preuve ou données inexploitables
    - PARTIAL : 1 preuve ou uniquement des sources tier C/D sans données chiffrées/normes
    - CONFLICTING : contradictions ou tensions documentaires identifiées
    - COVERED : au moins 2 preuves indépendantes, ou 1 preuve de Tier A/B avec donnée statistique/norme directe
    - BUDGET_EXHAUSTED : limite de requêtes atteinte, signalement explicite des limites
    """
    for sq in plan.sub_questions:
        expected = expected_evidence_types(sq.question + " " + " ".join(sq.expected_evidence))
        matching_evs = [
            ev for ev in evidence_items
            if evidence_answers_question(ev, sq.question, expected)
            and (not getattr(ev, "sub_question_id", "") or getattr(ev, "sub_question_id", "") == sq.id)
        ]

        sq.evidence_ids = [getattr(ev, "evidence_id", "") for ev in matching_evs if getattr(ev, "evidence_id", "")]

        if not matching_evs:
            sq.status = "BUDGET_EXHAUSTED" if budget_exhausted else ("NOT_STARTED" if sq.status == "NOT_STARTED" else "INSUFFICIENT")
        elif len(matching_evs) == 1:
            ev = matching_evs[0]
            tier = getattr(ev, "source_tier", "C")
            ctype = getattr(ev, "claim_type", "")
            if tier in ("A", "B") and ctype in ("statistic", "regulatory_norm", "scientific_finding"):
                sq.status = "COVERED"
            else:
                sq.status = "PARTIAL"
        else:
            # Plusieurs preuves : vérifier si proviennent d'au moins 2 familles de sources distinctes
            families = {getattr(ev, "source_family_id", "") for ev in matching_evs if getattr(ev, "source_family_id", "")}
            # Détection de divergence de chiffres pour CONFLICTING
            comparable = {}
            for ev in matching_evs:
                key = (getattr(ev, "normalized_metric", None), getattr(ev, "normalized_unit", None), getattr(ev, "period_or_year", None))
                if all(key) and getattr(ev, "normalized_value", None) is not None:
                    comparable.setdefault(key, []).append(ev.normalized_value)
            values = next((group for group in comparable.values() if len(group) >= 2), [])
            has_major_divergence = False
            if len(values) >= 2:
                min_v, max_v = min(values), max(values)
                if min_v > 0 and (max_v / min_v) > 1.4:
                    has_major_divergence = True

            if has_major_divergence:
                sq.status = "CONFLICTING"
            elif any(getattr(ev, "source_tier", "") in ("A", "B") for ev in matching_evs) or (not expected and len(families) >= 2):
                sq.status = "COVERED"
            else:
                sq.status = "PARTIAL"

    return plan


def verify_aspect_coverage(checklist: list[dict[str, Any]], sources: list[dict[str, Any]], assessments: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Require an explicit question/evidence mapping plus a matching proof type."""
    from .evidence_ledger import extract_deterministic_evidence_from_sources
    ledger = extract_deterministic_evidence_from_sources(sources)
    judgments = {str(item.get("id")): item for item in (assessments or []) if isinstance(item, dict)}
    output = []
    for original in checklist:
        item = dict(original)
        judgment = judgments.get(str(item.get("id")), item)
        question = str(item.get("question") or item.get("aspect") or "")
        expected = expected_evidence_types(question)
        candidates = []
        ids = judgment.get("evidence_ids") or []
        stored = judgment.get("coverage_evidence") or []
        for evidence in ledger.list_all():
            mapped = evidence.evidence_id in ids if assessments is not None else any(
                proof.get("source_url") == evidence.source_url and proof.get("exact_passage") == evidence.exact_passage
                for proof in stored if isinstance(proof, dict)
            )
            if mapped and evidence_answers_question(evidence, question, expected):
                candidates.append(evidence)
        sq = SubQuestion(str(item.get("id")), str(item.get("aspect")), question, [])
        audit_sub_question_coverage(ResearchPlan(question, [sq]), candidates)
        covered = judgment.get("status") == "covered" and sq.status == "COVERED"
        item["status"] = "covered" if covered else ("partial" if candidates else "missing")
        item["coverage_evidence"] = [{"source_url": ev.source_url, "exact_passage": ev.exact_passage} for ev in candidates]
        item["expected_evidence"] = sorted(expected)
        if not covered:
            item["note"] = "Preuves directes insuffisantes pour cette sous-question" + (" : " + ", ".join(sorted(expected)) if expected else "")
        output.append(item)
    return output


def coverage_query(item: dict[str, Any]) -> str:
    question = str(item.get("question") or item.get("aspect") or "").strip()
    expected = expected_evidence_types(question)
    suffix = "étude originale source primaire"
    if "employment_data" in expected:
        suffix += " statistiques emploi insertion recrutement"
    if "projection" in expected:
        suffix += " projections prospectives"
    if "regulatory_norm" in expected:
        suffix += " texte officiel réglementation"
    return f"{question[:220]} {suffix}".strip()


def format_coverage_limits(checklist: list[dict[str, Any]]) -> str:
    missing = [item for item in checklist if item.get("status") != "covered"]
    if not missing:
        return ""
    lines = ["## Limites de couverture documentaire", "", "Les sous-questions suivantes ne disposent pas de preuves directes suffisantes :", ""]
    for item in missing:
        label = str(item.get("question") or item.get("aspect") or "Sous-question").replace("\n", " ")
        lines.append(f"- **{label}** — conclusion non établie dans le corpus collecté.")
    return "\n".join(lines) + "\n"

