"""Evidence Ledger pour cLAIr DeepSearch V2 — Architecture Evidence-First.

Base de preuves structurées immuables : chaque élément probant (statistique, norme,
constat empirique, réserve méthodologique) est extrait de son document source,
qualifié et indexé sous un identifiant unique (EV_xxxx) avant toute phase d'analyse ou de rédaction.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

EvidenceType = Literal[
    "statistic",             # Donnée chiffrée, taux, effectif, proportion
    "regulatory_norm",       # Texte de loi, arrêté, norme homologuée, référentiel
    "scientific_finding",    # Résultat expérimental, conclusion d'étude à comité
    "methodological_caveat", # Biais, limite de cohorte, réserve d'interprétation
    "factual_statement",     # Fait historique, description technique, architecture
]


@dataclass
class EvidenceItem:
    evidence_id: str
    source_id: str
    source_url: str
    source_title: str
    exact_passage: str
    claim_type: EvidenceType = "factual_statement"
    source_tier: str = "C"
    source_family_id: str = ""
    sub_question_id: str = ""
    topic: str = ""
    confidence: str = "moyenne"
    normalized_metric: str | None = None
    normalized_value: float | None = None
    normalized_unit: str | None = None
    period_or_year: str | None = None
    nature: str = "constat"  # constat | projection | simulation | estimation
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_family_id(url: str, title: str) -> str:
    """Regroupe les sources appartenant à la même organisation ou étude."""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        clean_host = re.sub(r"[^a-z0-9]", "_", host)
    except Exception:
        clean_host = "unknown"
    return clean_host or "generic"


class EvidenceLedger:
    """Registre centralisé et immuable des preuves extraites."""

    def __init__(self) -> None:
        self._items: list[EvidenceItem] = []
        self._by_id: dict[str, EvidenceItem] = {}
        self._counter: int = 1

    def add_evidence(
        self,
        source_id: str,
        source_url: str,
        source_title: str,
        exact_passage: str,
        claim_type: EvidenceType = "factual_statement",
        source_tier: str = "C",
        source_family_id: str | None = None,
        sub_question_id: str = "",
        topic: str = "",
        confidence: str = "moyenne",
        normalized_metric: str | None = None,
        normalized_value: float | None = None,
        normalized_unit: str | None = None,
        period_or_year: str | None = None,
        nature: str = "constat",
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceItem:
        passage_clean = re.sub(r"\s+", " ", exact_passage or "").strip()
        if not passage_clean:
            raise ValueError("Le passage exact ne peut être vide.")

        # Dédoublonnage : si un passage identique ou quasi-identique existe déjà pour la même source
        for existing in self._items:
            if existing.source_url == source_url and (
                passage_clean in existing.exact_passage
                or existing.exact_passage in passage_clean
            ):
                return existing

        ev_id = f"EV_{self._counter:04d}"
        self._counter += 1

        family = source_family_id or _compute_family_id(source_url, source_title)
        item = EvidenceItem(
            evidence_id=ev_id,
            source_id=source_id,
            source_url=source_url,
            source_title=source_title,
            exact_passage=passage_clean,
            claim_type=claim_type,
            source_tier=source_tier,
            source_family_id=family,
            sub_question_id=sub_question_id,
            topic=topic,
            confidence=confidence,
            normalized_metric=normalized_metric,
            normalized_value=normalized_value,
            normalized_unit=normalized_unit,
            period_or_year=period_or_year,
            nature=nature,
            metadata=metadata or {},
        )
        self._items.append(item)
        self._by_id[ev_id] = item
        return item

    def get(self, evidence_id: str) -> EvidenceItem | None:
        return self._by_id.get(evidence_id)

    def list_all(self) -> list[EvidenceItem]:
        return list(self._items)

    def by_sub_question(self, sub_question_id: str) -> list[EvidenceItem]:
        return [it for it in self._items if it.sub_question_id == sub_question_id]

    def count(self) -> int:
        return len(self._items)

    def format_for_analysts(self, max_items: int = 60) -> str:
        """Formate le grand livre des preuves pour transmission aux 3 analystes spécialisés."""
        if not self._items:
            return "Aucune preuve extraite dans le grand livre."

        lines = ["### GRAND LIVRE DES PREUVES VÉRIFIABLES (EVIDENCE LEDGER) :"]
        for it in self._items[:max_items]:
            norm_desc = ""
            if it.normalized_value is not None:
                norm_desc = f" | [Valeur: {it.normalized_value} {it.normalized_unit or ''} ({it.nature})]"
            lines.append(
                f"- **[{it.evidence_id}]** (Source {it.source_id} - Tier {it.source_tier}) : "
                f"« {it.exact_passage} »{norm_desc} — *Réf: {it.source_title}* — {it.source_url}"
            )
        return "\n".join(lines)

    def to_dict_list(self) -> list[dict[str, Any]]:
        return [it.to_dict() for it in self._items]

    @classmethod
    def from_dict_list(cls, data: list[dict[str, Any]]) -> EvidenceLedger:
        ledger = cls()
        for d in data:
            item = EvidenceItem(**{key: value for key, value in d.items() if key in EvidenceItem.__dataclass_fields__})
            if item.evidence_id in ledger._by_id:
                raise ValueError("Identifiant de preuve dupliqué.")
            ledger._items.append(item)
            ledger._by_id[item.evidence_id] = item
        numeric_ids = [int(it.evidence_id[3:]) for it in ledger._items if re.fullmatch(r"EV_\d+", it.evidence_id)]
        ledger._counter = max(numeric_ids, default=0) + 1
        return ledger


def extract_deterministic_evidence_from_sources(
    sources: list[dict[str, Any]],
    ledger: EvidenceLedger | None = None,
    sub_question_id: str = "",
) -> EvidenceLedger:
    """Extraction déterministe de premier niveau à partir des extraits de sources enrichies.

    Détecte les phrases clés contenant des chiffres, pourcentages, dispositions réglementaires
    ou réserves méthodologiques pour peupler l'Evidence Ledger de manière reproductible.
    """
    led = ledger or EvidenceLedger()
    figure_re = re.compile(
        r"(?<![\w.])(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d+)(?:[.,](\d+))?"
        r"(?=\s*(?:%|€|k€|m€|md€|\$|milliards?|millions?|postes?|emplois?|recrutements?|salaires?|ans|mois)\b|\s*%|\s*€|[.,]\d)",
        re.IGNORECASE,
    )
    norm_re = re.compile(r"\b(arrêté|décret|article\s+[ldr]\.?\s*\d+|norme\s+iso|loi\s+n°|directive)\b", re.IGNORECASE)

    for idx, s in enumerate(sources, start=1):
        if s.get("media_type") == "image" or s.get("img_src") or s.get("provider") == "searxng_images":
            continue
        src_id = str(s.get("source_id") or idx)
        url = str(s.get("url") or "")
        title = str(s.get("title") or "")
        tier = str(s.get("tier") or "C")

        # Analyse des textes disponibles (snippet et extract/content)
        text_blobs = [str(s.get("original_snippet", s.get("snippet")) or "")]
        content = str(s.get("content") or s.get("extract") or "")
        if content:
            text_blobs.append(content)

        full_text = " ".join(text_blobs)
        sentences = re.split(r"(?<=[.!?])\s+", full_text)

        for sent in sentences:
            sent_clean = sent.strip()
            if len(sent_clean) < 30 or len(sent_clean) > 400:
                continue

            # Cas 1 : donnée chiffrée
            fig_match = figure_re.search(sent_clean)
            if fig_match:
                raw_num = fig_match.group(1).replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
                if fig_match.group(2):
                    raw_num += f".{fig_match.group(2)}"
                val = None
                try:
                    val = float(raw_num)
                except Exception:
                    pass

                nature = "projection" if any(w in sent_clean.lower() for w in ("2030", "2035", "horizon", "projet", "estim", "scénario")) else "constat"
                led.add_evidence(
                    source_id=src_id,
                    source_url=url,
                    source_title=title,
                    exact_passage=sent_clean,
                    claim_type="statistic",
                    source_tier=tier,
                    sub_question_id=sub_question_id,
                    confidence="moyenne" if tier in ("A", "B") else "faible",
                    normalized_value=val,
                    nature=nature,
                )
                continue

            # Cas 2 : norme ou texte juridique/institutionnel
            if norm_re.search(sent_clean) and tier in ("A", "B"):
                led.add_evidence(
                    source_id=src_id,
                    source_url=url,
                    source_title=title,
                    exact_passage=sent_clean,
                    claim_type="regulatory_norm",
                    source_tier=tier,
                    sub_question_id=sub_question_id,
                    confidence="élevée",
                    nature="constat",
                )
                continue

            # Cas 3 : réserve méthodologique explicite
            if any(w in sent_clean.lower() for w in ("biais", "poursuite d'études", "hors champ", "échantillon", "intervalle de confiance", "limite")):
                led.add_evidence(
                    source_id=src_id,
                    source_url=url,
                    source_title=title,
                    exact_passage=sent_clean,
                    claim_type="methodological_caveat",
                    source_tier=tier,
                    sub_question_id=sub_question_id,
                    confidence="moyenne",
                    nature="constat",
                )

    return led

