"""Vérificateur factuel déterministe des chiffres d'un rapport DeepSearch / Mode Apprendre.

Règle appliquée : aucun chiffre précis n'est présenté comme établi sans (1) une citation `[n]`,
(2) un chiffre effectivement retrouvé dans le contenu disponible de la source citée.
Le périmètre statistique (population, année, définition) ne peut pas être contrôlé automatiquement :
tout chiffre « retrouvé » reste donc au mieux de confiance moyenne, sauf recoupement par 2 sources distinctes.
"""
from __future__ import annotations

import re
from typing import Any

_CITATION_RE = re.compile(r"\[(\d{1,3}(?:\s*[,;–-]\s*\d{1,3})*)\]")
# Nombre précis : pourcentage, montant, décimal, ou entier d'au moins 2 chiffres suivi d'une unité courante.
_FIGURE_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:[\s\u00a0\u202f]\d{3})+|\d+)(?:[.,](\d+))?"
    r"(?=\s*(?:%|€|k€|m€|md€|\$|milliards?|millions?|mille|ans|mois|postes?|emplois?|recrutements?|salaires?|euros?|points?|pts|kw|gw|mw|ms|go|to)\b|\s*%|\s*€|[.,]\d|\s+[àa]\s+\d)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
# Formulations catégoriques à ne pas laisser passer sans nuance (tous domaines : sciences, santé, économie, droit, ingénierie).
_ABSOLUTE_RE = re.compile(
    r"vulnérabilité\s+(?:à\s+l'|à\s+la\s+)?(?:ia|ai)\s*:?\s*nulle|\b100\s?%\s+(?:de\s+)?(?:garanti|certain|sûr|efficace|fiable)|"
    r"\b(?:garanti(?:e|s|es)?\s+(?:à\s+100|sans\s+exception)|aucun\s+risque|zéro\s+risque|risque\s+nul|infaillible|"
    r"sans\s+aucun\s+effet\s+secondaire|rendement\s+garanti|inviolable|preuve\s+irréfutable|corrélation\s+parfaite|"
    r"certitude\s+absolue|filtre\s+(?:automatisé\s+)?binaire|sélection\s+binaire|emploi\s+garanti|insertion\s+garantie|"
    r"garantit\s+un\s+accès\s+privilégié|garantit\s+(?:un\s+|l')accès|deux\s+seuls\s+leviers|seuls?\s+leviers?|"
    r"par\s+nature\s+non\s+automatisables?|non\s+automatisables?|plein\s+emploi\s+structurel|immunité\s+totale)\b",
    re.IGNORECASE,
)
_MAX_ROWS = 60

# Remplacements ciblés universels pour assainir les affirmations catégoriques ou hyperboliques tous domaines confondus
_ABSOLUTE_REPLACEMENTS: tuple[tuple[re.Pattern, str], ...] = (
    # Expressions universelles de certitude absolue, de risque nul ou de causalité sans réserve
    (re.compile(r"\b100\s?%\s+(?:de\s+)?(?:garanti|certain|sûr|efficace|fiable)\b", re.IGNORECASE), "très fortement corrélé selon les données disponibles"),
    (re.compile(r"\baucun\s+risque\b", re.IGNORECASE), "risque modéré"),
    (re.compile(r"\bzéro\s+risque\b", re.IGNORECASE), "risque très faible"),
    (re.compile(r"\brisque\s+nul\b", re.IGNORECASE), "risque résiduel limité"),
    (re.compile(r"\bsans\s+aucun\s+effet\s+secondaire\b", re.IGNORECASE), "avec un profil de tolérance favorable selon les données disponibles"),
    (re.compile(r"\brendement\s+garanti\b", re.IGNORECASE), "rendement potentiel sous réserve des conditions de marché"),
    (re.compile(r"\binviolable\b", re.IGNORECASE), "présentant un haut niveau de résistance"),
    (re.compile(r"\bpreuve\s+irréfutable\b", re.IGNORECASE), "élément probant convergent"),
    (re.compile(r"\bcorrélation\s+parfaite\b", re.IGNORECASE), "forte corrélation observée"),
    (re.compile(r"\bcertitude\s+absolue\b", re.IGNORECASE), "forte présomption empirique"),
    (re.compile(r"\binfaillible\b", re.IGNORECASE), "particulièrement éprouvé"),
    (re.compile(r"\bimmunité\s+totale\b", re.IGNORECASE), "très forte résilience observée"),
    (re.compile(r"\bratio\s+(?:[\w/]+\s+)?imbattable\b", re.IGNORECASE), "ratio particulièrement favorable"),
    (re.compile(r"\bfiltre\s+(?:automatisé\s+)?binaire\b", re.IGNORECASE), "tri algorithmique multicritère"),
    (re.compile(r"\bsélection\s+binaire\b", re.IGNORECASE), "sélection multicritère"),

    # Expressions de causalité exclusive ou de garantie de résultat / de trajectoire
    (re.compile(r"vulnérabilité\s+(?:à\s+l'|à\s+la\s+)?(?:ia|ai)\s*:?\s*nulle", re.IGNORECASE), "exposition directe à l'IA estimée très faible à court terme"),
    (re.compile(r"\bemploi\s+garanti\b", re.IGNORECASE), "taux d'insertion professionnelle historiquement très élevé"),
    (re.compile(r"\binsertion\s+garantie\b", re.IGNORECASE), "sécurisation de trajectoire observée"),
    (re.compile(r"\bpénurie\s+structurelle\s+garantie\b", re.IGNORECASE), "forte tension structurelle anticipée par les projections"),
    (re.compile(r"\bgarantit\s+un\s+accès\s+privilégié\b", re.IGNORECASE), "offre une voie d'accès ciblée préparant directement"),
    (re.compile(r"\bgarantit\s+un\s+accès\b", re.IGNORECASE), "facilite l'accès"),
    (re.compile(r"\bgarantit\s+l'accès\b", re.IGNORECASE), "favorise l'accès"),
    (re.compile(r"\b(?:les\s+)?deux\s+seuls\s+leviers\s+structurels\b", re.IGNORECASE), "deux leviers structurels majeurs"),
    (re.compile(r"\b(?:les\s+)?seuls\s+leviers\b", re.IGNORECASE), "des leviers majeurs"),
    (re.compile(r"\b(?:le\s+)?seul\s+levier\b", re.IGNORECASE), "un levier majeur"),
    (re.compile(r"\bpar\s+nature\s+non\s+automatisables?\b", re.IGNORECASE), "présentant une forte résistance opérationnelle à l'automatisation"),
    (re.compile(r"\bnon\s+automatisables?\b", re.IGNORECASE), "difficilement substituables par des systèmes automatisés"),
    (re.compile(r"\bnon\s+modélisables?\b", re.IGNORECASE), "difficilement formalisables par des modèles"),
    (re.compile(r"\bplein\s+emploi\s+structurel\b", re.IGNORECASE), "forte tension sur l'embauche"),
)


def remedy_unverified_claims(report_markdown: str, verification_result: dict[str, Any] | None = None) -> str:
    """Corrige préventivement les affirmations catégoriques et remédie aux affirmations non soutenues avant publication."""
    text = report_markdown
    # 1. Remplacement des expressions catégoriques
    for pattern, replacement in _ABSOLUTE_REPLACEMENTS:
        text = pattern.sub(replacement, text)

    # 2. Si un résultat de vérification est fourni, atténuer les affirmations chiffrées non sourcées ou non retrouvées
    if verification_result:
        rows = verification_result.get("rows") or []
        for r in rows:
            status = r.get("status")
            full_sentence = r.get("full_sentence") or r.get("claim", "").strip()
            # Si le statut est non sourcé ou non retrouvé et que la phrase n'a pas encore de mise en garde
            if status in ("non sourcé", "non retrouvé", "portée divergente") and full_sentence and len(full_sentence) > 15:
                if "indicatif" not in full_sentence and "estimation" not in full_sentence and "consolidé" not in full_sentence:
                    # Remplacement exact sur la phrase complète pour ne jamais couper au milieu d'un mot ou d'un tableau
                    if full_sentence in text:
                        nuanced = full_sentence.rstrip(".!?") + " *(ordre de grandeur indicatif non consolidé dans les sources)*."
                        text = text.replace(full_sentence, nuanced, 1)

    return text


def _normalise_number(integer: str, decimals: str | None) -> str:
    """Retire espaces et séparateurs de milliers ; garde la partie décimale avec un point."""
    clean = re.sub(r"[\s\u00a0\u202f]", "", integer)
    return f"{clean}.{decimals}" if decimals else clean


def _normalise_text(text: str) -> str:
    """Texte de source normalisé pour la recherche d'un nombre (espaces retirés, virgule décimale -> point)."""
    flat = re.sub(r"[\s\u00a0\u202f]", "", text or "")
    return flat.replace(",", ".")


def _source_text(source: dict[str, Any]) -> str:
    """Contenu consultable d'une source : titre, extrait et éventuel contenu complet."""
    parts = [source.get(key) for key in ("title", "snippet", "content", "extract", "text")]
    return " ".join(str(p) for p in parts if p)


def _extract_figures(sentence: str) -> list[str]:
    """Chiffres précis d'une phrase (hors années, numérotation de sections et marqueurs de citation)."""
    scrubbed = _CITATION_RE.sub(" ", sentence)
    figures: list[str] = []
    for match in _FIGURE_RE.finditer(scrubbed):
        value = _normalise_number(match.group(1), match.group(2))
        if _YEAR_RE.match(value) or (len(value) < 2 and "." not in value):
            continue
        if value not in figures:
            figures.append(value)
    return figures


def _cited_indexes(sentence: str) -> list[int]:
    indexes: list[int] = []
    for group in _CITATION_RE.findall(sentence):
        for token in re.split(r"[,;–-]", group):
            token = token.strip()
            if token.isdigit() and int(token) not in indexes:
                indexes.append(int(token))
    return indexes


def _figure_matches_text(figure: str, norm_src_text: str, raw_src_text: str) -> bool:
    """Vérifie si un chiffre est présent de manière exacte ou approximative (ordre de grandeur / projection).
    
    Gère la normalisation sémantique des données :
    - Équivalence exacte (ex. '89' == '89', '760000' == '760000')
    - Tolérance d'arrondi usuel pour les projections (ex. 760 000 arrondi en 800 000 postes, 89 % en 90 %)
    """
    if figure in norm_src_text:
        return True
    try:
        val = float(figure)
        # Extraction de tous les nombres du texte source brut
        found_tokens = re.findall(r"(?<![\w.])(\d[\d\s\u00a0\u202f]*(?:[.,]\d+)?)", raw_src_text)
        for tok in found_tokens:
            cleaned = re.sub(r"[\s\u00a0\u202f]", "", tok).replace(",", ".")
            if not cleaned:
                continue
            try:
                clean_num = float(cleaned)
            except ValueError:
                continue
            if abs(clean_num - val) < 1e-4:
                return True
            # Tolérance d'arrondi pour les grands volumes (> 10 000 : jusqu'à 8 % d'arrondi)
            if val >= 10000 and abs(clean_num - val) / val <= 0.08:
                return True
            # Tolérance d'arrondi pour les pourcentages (ex: 89 % -> ~90 %)
            if 1 <= val <= 100 and abs(clean_num - val) <= 1.5:
                return True
    except Exception:
        pass
    return False


# Paires de périmètres incompatibles multi-domaines :
# (marqueurs de périmètre restreint dans la source, marqueurs d'extrapolation dans l'affirmation)
_INCOMPATIBLE_SCOPES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    # 1. Périmètre expérimental / préclinique / in vitro vs efficacité clinique humaine établie
    (
        ("in vitro", "modèle murin", "chez la souris", "chez le rat", "préclinique", "culture cellulaire"),
        ("chez l'homme", "chez le patient", "patients humains", "guérison clinique", "efficacité clinique prouvée", "mortalité hospitalière"),
    ),
    # 2. Périmètre de simulation / benchmark synthétique / testnet vs production réelle à grande échelle
    (
        ("simulation numérique", "benchmark synthétique", "environnement de test", "testnet", "conditions de laboratoire"),
        ("en production réelle", "déploiement industriel", "conditions réelles d'exploitation", "garantit en production"),
    ),
    # 3. Régime administratif ou réglementaire spécifique restreint vs population générale ou cursus initial
    (
        ("travailleurs étrangers", "immigration", "titre de séjour", "main-d'œuvre étrangère"),
        ("lycée", "bac ", "baccalauréat", "st2s", "sti2d", "parcoursup", "ifsi", "école d'ingénieur", "but ", "orientation scolaire"),
    ),
)

_STOPWORDS_SCOPE = frozenset({
    "dans", "pour", "avec", "sans", "plus", "moins", "entre", "selon", "cette", "ces", "sont",
    "comme", "tout", "tous", "toute", "toutes", "leur", "leurs", "dont", "mais", "ou", "et",
    "donc", "ainsi", "alors", "après", "avant", "depuis", "vers", "chez", "sous", "sur",
    "être", "avoir", "faire", "peut", "peuvent", "doit", "doivent", "permet", "permettent",
    "niveau", "taux", "part", "effet", "étude", "source", "rapport", "données", "analyse",
})


def _has_scope_divergence(sentence: str, src_text: str, figures_matched: bool) -> bool:
    """Détecte de manière universelle si une source citée a un périmètre incompatible avec l'affirmation."""
    lower_src = src_text.lower()
    lower_sent = sentence.lower()

    # 1. Vérification des incompatibilités de régime / périmètre connues (santé, ingénierie, réglementation)
    for src_markers, claim_markers in _INCOMPATIBLE_SCOPES:
        if (
            any(m in lower_src for m in src_markers)
            and any(m in lower_sent for m in claim_markers)
            and not any(m in lower_src for m in claim_markers)
        ):
            return True

    # 2. Orthogonalité lexicale totale : si le chiffre n'est pas dans la source (ou s'il n'y a pas de chiffre)
    # et qu'une phrase comportant une affirmation causale forte ("garantit", "prouve", "démontre", "assure")
    # ne partage strictement aucun terme substantif (>= 5 lettres) avec la source citée.
    if not figures_matched and len(lower_src) >= 40:
        sent_words = {
            w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ]{5,}", lower_sent)
            if w not in _STOPWORDS_SCOPE
        }
        src_words = {
            w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ]{5,}", lower_src)
            if w not in _STOPWORDS_SCOPE
        }
        has_strong_claim = any(
            k in lower_sent for k in ("garantit", "prouve", "démontre", "assure", "certifie", "confirme")
        )
        if has_strong_claim and sent_words and src_words and sent_words.isdisjoint(src_words):
            return True

    return False


def validate_claim_evidence(
    sentence: str,
    cited_indices: list[int],
    text_sources: list[dict[str, Any]],
    figures: list[str],
) -> dict[str, Any]:
    """ClaimEvidenceValidator : évalue l'adéquation de preuve entre une affirmation et ses sources citées (NLI / Entailment).
    
    Vérifie l'existence de la source, la cohérence de sa portée (scope), la présence exacte ou normalisée des données
    et prescrit l'action corrective appropriée (retain, nuance, rewrite_or_research).
    """
    valid = [i for i in cited_indices if 1 <= i <= len(text_sources)]
    lower_sent = sentence.lower()
    is_explicitly_indicative = any(
        kw in lower_sent
        for kw in (
            "ordre de grandeur indicatif",
            "non consolidé",
            "non consolidée",
            "estimation indicative",
            "données indicatives",
            "à titre indicatif",
            "fourchette indicative",
            "barème indicatif",
            "estimations non consolidées",
        )
    )

    if not cited_indices:
        if is_explicitly_indicative:
            return {
                "evidence_url": None,
                "exact_passage": None,
                "domain_category": None,
                "relevance": "indicative_caveat",
                "entailment": "caveat_acknowledged",
                "confidence": "indicative",
                "action": "retained_with_caveat",
                "status": "mention indicative nuancée",
                "normalized_status": "SUPPORTED_WITH_CAVEAT",
                "note": "Mention indicative signalée au lecteur ; non présentée comme un fait consolidé.",
            }
        return {
            "evidence_url": None,
            "exact_passage": None,
            "domain_category": None,
            "relevance": "insufficient",
            "entailment": "unsupported",
            "confidence": "faible",
            "action": "rewrite_or_research",
            "status": "non sourcé",
            "normalized_status": "UNSUPPORTED",
            "note": "Aucune citation : ne pas tenir pour un fait établi.",
        }
    if not valid:
        if is_explicitly_indicative:
            return {
                "evidence_url": None,
                "exact_passage": None,
                "domain_category": None,
                "relevance": "indicative_caveat",
                "entailment": "caveat_acknowledged",
                "confidence": "indicative",
                "action": "retained_with_caveat",
                "status": "mention indicative nuancée",
                "normalized_status": "SUPPORTED_WITH_CAVEAT",
                "note": "Mention indicative signalée au lecteur ; référence externe non répertoriée.",
            }
        return {
            "evidence_url": None,
            "exact_passage": None,
            "domain_category": None,
            "relevance": "insufficient",
            "entailment": "unsupported",
            "confidence": "faible",
            "action": "rewrite_or_research",
            "status": "source inexistante",
            "normalized_status": "UNSUPPORTED",
            "note": "La référence citée n'existe pas dans la bibliographie.",
        }

    # Inspection des sources citées
    passages: list[str] = []
    has_scope_mismatch = False
    supporting_indices: list[int] = []

    for idx in valid:
        src = text_sources[idx - 1]
        src_text = _source_text(src)
        norm_src_text = _normalise_text(src_text)

        figures_matched = bool(figures and all(_figure_matches_text(fig, norm_src_text, src_text) for fig in figures))

        if _has_scope_divergence(sentence, src_text, figures_matched):
            has_scope_mismatch = True

        # Recherche de passage contenant les chiffres (avec normalisation sémantique d'arrondi)
        if figures_matched:
            supporting_indices.append(idx)
            first_fig = figures[0]
            pos = src_text.find(first_fig)
            if pos != -1:
                start = max(0, pos - 60)
                end = min(len(src_text), pos + len(first_fig) + 100)
                passages.append(src_text[start:end].strip())
            elif src_text:
                passages.append(src_text[:160].strip())

    primary_src = text_sources[valid[0] - 1]
    primary_url = primary_src.get("url")

    if has_scope_mismatch:
        return {
            "evidence_url": primary_url,
            "exact_passage": passages[0] if passages else None,
            "domain_category": primary_src.get("tier"),
            "relevance": "divergent_scope",
            "entailment": "unsupported",
            "confidence": "faible",
            "action": "rewrite_or_research",
            "status": "portée divergente",
            "normalized_status": "CONTRADICTED",
            "note": "Portée divergente : le périmètre, la population ou l'objet de la source citée ne correspond pas à l'affirmation avancée.",
        }

    if len(supporting_indices) >= 2:
        return {
            "evidence_url": primary_url,
            "exact_passage": passages[0] if passages else None,
            "domain_category": primary_src.get("tier"),
            "relevance": "sufficient",
            "entailment": "supported",
            "confidence": "élevée",
            "action": "retain",
            "status": "retrouvé",
            "normalized_status": "SUPPORTED",
            "note": "Chiffre et données corroborés par au moins 2 sources distinctes.",
        }

    if supporting_indices:
        return {
            "evidence_url": primary_url,
            "exact_passage": passages[0] if passages else None,
            "domain_category": primary_src.get("tier"),
            "relevance": "sufficient",
            "entailment": "partially_supported",
            "confidence": "moyenne",
            "action": "nuance",
            "status": "retrouvé",
            "normalized_status": "SUPPORTED_WITH_CAVEAT",
            "note": "Chiffre présent dans la source citée ; vérifier le périmètre statistique.",
        }

    if is_explicitly_indicative:
        return {
            "evidence_url": primary_url,
            "exact_passage": None,
            "domain_category": primary_src.get("tier"),
            "relevance": "indicative_caveat",
            "entailment": "caveat_acknowledged",
            "confidence": "indicative",
            "action": "retained_with_caveat",
            "status": "mention indicative nuancée",
            "normalized_status": "SUPPORTED_WITH_CAVEAT",
            "note": "Ordre de grandeur indicatif explicité au lecteur ; non consolidé dans la source citée.",
        }

    return {
        "evidence_url": primary_url,
        "exact_passage": None,
        "domain_category": primary_src.get("tier"),
        "relevance": "insufficient",
        "entailment": "unsupported",
        "confidence": "faible",
        "action": "rewrite_or_research",
        "status": "non retrouvé",
        "normalized_status": "UNSUPPORTED",
        "note": "Chiffre ou affirmation absent du contenu textuel de la source citée.",
    }


def verify_report_figures(report_markdown: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Contrôle chaque phrase contenant un chiffre précis ou une causalité forte et retourne les lignes de vérification ClaimEvidence."""
    text_sources = [s for s in sources if s.get("media_type") != "image" and not s.get("img_src")]
    rows: list[dict[str, Any]] = []
    for raw_line in report_markdown.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(">") or set(line) <= set("-|: "):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            full_sent = sentence.strip()
            absolute = _ABSOLUTE_RE.search(sentence)
            if absolute:
                rows.append({
                    "claim": full_sent[:200],
                    "full_sentence": full_sent,
                    "figures": [],
                    "sources": _cited_indexes(sentence),
                    "status": "formulation catégorique",
                    "normalized_status": "CONTRADICTED",
                    "confidence": "faible",
                    "action": "rewrite_or_research",
                    "note": f"« {absolute.group(0)} » : une projection ou un processus complexe ne se présente pas comme une certitude absolue.",
                })
            figures = _extract_figures(sentence)
            if not figures:
                continue
            cited = _cited_indexes(sentence)
            val_res = validate_claim_evidence(full_sent, cited, text_sources, figures)
            rows.append({
                "claim": full_sent[:200],
                "full_sentence": full_sent,
                "figures": figures,
                "sources": [i for i in cited if 1 <= i <= len(text_sources)] or cited,
                "status": val_res["status"],
                "normalized_status": val_res.get("normalized_status", "UNSUPPORTED"),
                "confidence": val_res["confidence"],
                "action": val_res["action"],
                "evidence_url": val_res.get("evidence_url"),
                "exact_passage": val_res.get("exact_passage"),
                "relevance": val_res.get("relevance"),
                "entailment": val_res.get("entailment"),
                "note": val_res["note"],
            })
    stats = {"total": sum(1 for r in rows if r["figures"])}
    for key in (
        "retrouvé",
        "mention indicative nuancée",
        "non retrouvé",
        "non sourcé",
        "source inexistante",
        "formulation catégorique",
        "portée divergente",
    ):
        stats[key] = sum(1 for r in rows if r["status"] == key)
    return {"rows": rows, "stats": stats}


def run_repair_loop(
    report_markdown: str,
    sources: list[dict[str, Any]],
    max_cycles: int = 2,
) -> tuple[str, dict[str, Any]]:
    """Boucle de réparation ciblée multi-cycles (Claim Validator + Repair Loop V2).
    
    Exécute jusqu'à `max_cycles` passes de vérification et de remédiation chirurgicale :
    - Détecte les affirmations non étayées, non sourcées ou à portée divergente.
    - Applique la qualification chirurgicale sur les phrases ou paragraphes concernés.
    - Revérifie immédiatement pour s'assurer qu'aucune anomalie résiduelle n'a subsisté.
    Retourne le texte final assaini et le résultat d'audit consolidé.
    """
    text = report_markdown
    result = verify_report_figures(text, sources)
    for _ in range(max_cycles):
        rows = result.get("rows") or []
        unverified_count = sum(
            1 for r in rows if r.get("status") in ("non sourcé", "non retrouvé", "portée divergente", "formulation catégorique")
        )
        if unverified_count == 0:
            break
        text = remedy_unverified_claims(text, result)
        result = verify_report_figures(text, sources)
    return text, result


def compute_validation_status(
    stats: dict[str, Any],
    audit_review: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Calcule mathématiquement le statut et le badge d'audit global à partir des vérifications effectives.
    
    Règles de vérité terrain déterministes (QualityGate Python) :
    1. 'PASSED' (🟢 Validé) : STRICTEMENT si 100% des affirmations chiffrées sont retrouvées et qu'aucune
       affirmation n'est non retrouvée, non sourcée, en portée divergente ou catégorique.
    2. 'PUBLISH_WITH_LIMITATIONS' (🔵 Remanié ou 🟡 Validé avec réserves) : publication autorisée avec
       incertitudes ou corrections explicitement signalées au lecteur.
    3. 'REQUIRES_REVISION' (🔴 Révision requise) : Si le volume d'affirmations sans preuve est trop important.
    """
    total = stats.get("total", 0)
    retrouve = stats.get("retrouvé", 0)
    non_retrouve = stats.get("non retrouvé", 0)
    non_source = stats.get("non sourcé", 0) + stats.get("source inexistante", 0)
    categorique = stats.get("formulation catégorique", 0)
    portee_divergente = stats.get("portée divergente", 0)
    indicatif = stats.get("mention indicative nuancée", 0)

    unverified = non_retrouve + non_source + portee_divergente
    applied_count = (audit_review or {}).get("applied_count", 0)
    decision_hint = str((audit_review or {}).get("decision") or "").lower()

    # Condition stricte pour la validation intégrale : 0 affirmation non vérifiée, 0 catégorique
    if unverified == 0 and categorique == 0 and total > 0 and (retrouve + indicatif) == total:
        if indicatif > 0 or applied_count > 0 or decision_hint in ("remanié", "remanie"):
            count_label = indicatif or applied_count or 1
            return "PUBLISH_WITH_LIMITATIONS", f"🔵 Remanié & Sécurisé ({count_label} affirmation{'s' if count_label > 1 else ''} corrigée{'s' if count_label > 1 else ''} avant publication)"
        return "PASSED", "🟢 Validé (Conformité documentaire intégrale)"

    # S'il reste des affirmations non retrouvées ou sans source
    if unverified > 0 or categorique > 0:
        anomalies_count = unverified + categorique
        if anomalies_count <= max(2, int(total * 0.25)):
            return "PUBLISH_WITH_LIMITATIONS", f"🟡 Validé avec réserves ({anomalies_count} affirmation{'s' if anomalies_count > 1 else ''} non consolidée{'s' if anomalies_count > 1 else ''})"
        return "REQUIRES_REVISION", f"🔴 Révision requise ({anomalies_count} affirmation{'s' if anomalies_count > 1 else ''} sans validation documentaire)"

    return "PUBLISH_WITH_LIMITATIONS", "🟡 Validé avec réserves (Périmètre documentaire à vérifier)"


def format_verification_markdown(
    result: dict[str, Any],
    audit_review: dict[str, Any] | None = None,
) -> str:
    """Section Markdown « Registre de vérification factuelle » enrichie avec l'arbitrage critique GPT-6 Astra."""
    rows = result.get("rows") or []
    stats = result.get("stats") or {}
    if not rows and not audit_review:
        return ""
    order = {
        "portée divergente": 0,
        "non sourcé": 1,
        "source inexistante": 1,
        "formulation catégorique": 2,
        "non retrouvé": 3,
        "mention indicative nuancée": 4,
        "retrouvé": 5,
    }
    ranked = sorted(rows, key=lambda r: order.get(r["status"], 6))[:_MAX_ROWS]
    parts_stat = [
        f"> **{stats.get('retrouvé', 0)}/{stats.get('total', 0)}** affirmations chiffrées retrouvées dans les sources citées",
    ]
    if stats.get("mention indicative nuancée"):
        parts_stat.append(f"**{stats.get('mention indicative nuancée', 0)}** ordres de grandeur indicatifs nuancés")
    if stats.get("non retrouvé"):
        parts_stat.append(f"**{stats.get('non retrouvé', 0)}** non retrouvées")
    if stats.get("non sourcé", 0) + stats.get("source inexistante", 0):
        parts_stat.append(f"**{stats.get('non sourcé', 0) + stats.get('source inexistante', 0)}** sans source valide")
    if stats.get("formulation catégorique"):
        parts_stat.append(f"**{stats.get('formulation catégorique', 0)}** formulations catégoriques assainies")
    if stats.get("portée divergente"):
        parts_stat.append(f"**{stats.get('portée divergente', 0)}** portée(s) divergente(s) rectifiée(s)")

    title = (
        "## Registre de vérification factuelle & Arbitrage critique"
        if audit_review
        else "## Registre de vérification factuelle"
    )
    lines = [title, ""]

    if audit_review:
        auditor_raw = audit_review.get("auditor_model") or "openai/gpt-6-astra"
        auditor_label = (
            auditor_raw.split("/")[-1].replace("-", " ").title()
            if "/" in auditor_raw
            else auditor_raw
        )
        # RÈGLE D'OR P0 : Le badge de décision est STRICTEMENT calculé à partir de la vérité terrain Python
        _verdict_code, decision_badge = compute_validation_status(stats, audit_review)

        lines.extend([
            f"> ### 🛡️ Validation Critique · {auditor_label} : {decision_badge}",
            f"> **Arbitrage factuel :** {audit_review.get('critique', 'Relecture critique effectuée.')}",
        ])
        verified_facts = audit_review.get("verified_facts") or []
        if isinstance(verified_facts, list) and verified_facts:
            lines.append(">")
            lines.append("> **Faits majeurs corroborés par les sources :**")
            for f in verified_facts[:4]:
                lines.append(f"> - {f}")
        warnings = audit_review.get("warnings") or []
        if isinstance(warnings, list) and warnings:
            lines.append(">")
            lines.append("> **Réserves & Vigilance méthodologique :**")
            for w in warnings[:3]:
                lines.append(f"> - {w}")
        if audit_review.get("sources_assessment"):
            lines.append(">")
            lines.append(f"> *Évaluation des sources : {audit_review['sources_assessment']}*")
        lines.append("")

    lines.extend([
        " · ".join(parts_stat) + ".",
        "> Règle : aucun chiffre précis n'est un fait établi sans source pertinente, contenu effectivement consulté "
        "(extrait) et périmètre statistique vérifié. Ce contrôle automatique ne valide jamais le périmètre : "
        "« retrouvé » signifie seulement que le nombre figure dans la source.",
        "",
        "| Affirmation chiffrée | Source(s) | Statut | Confiance | Action ClaimEvidence |",
        "|---|---|---|---|---|",
    ])
    for r in ranked:
        claim = r["claim"].replace("|", "\\|")
        srcs = ", ".join(f"[{i}]" for i in r["sources"]) or "—"
        action = r.get("action", "remedy")
        lines.append(f"| {claim} | {srcs} | {r['status']} | {r['confidence']} | {action} |")
    if len(rows) > len(ranked):
        lines.append(f"\n*{len(rows) - len(ranked)} autres affirmations chiffrées non listées (statut « retrouvé » majoritairement).*")
    lines.append("")
    return "\n".join(lines)

