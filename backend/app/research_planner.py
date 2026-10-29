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
        matching_evs = [
            ev for ev in evidence_items
            if getattr(ev, "sub_question_id", "") == sq.id
            or (hasattr(ev, "exact_passage") and any(
                w.lower() in ev.exact_passage.lower()
                for w in re.findall(r"\w{5,}", sq.question)
            ))
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
            values = [getattr(ev, "normalized_value", None) for ev in matching_evs if getattr(ev, "normalized_value", None) is not None]
            has_major_divergence = False
            if len(values) >= 2:
                min_v, max_v = min(values), max(values)
                if min_v > 0 and (max_v / min_v) > 1.4:
                    has_major_divergence = True

            if has_major_divergence:
                sq.status = "CONFLICTING"
            elif len(families) >= 2 or any(getattr(ev, "source_tier", "") in ("A", "B") for ev in matching_evs):
                sq.status = "COVERED"
            else:
                sq.status = "PARTIAL"

    return plan

