"""Filtrage de pertinence des sources web (DeepSearch & Mode Apprendre).

Deux niveaux :
1. `is_junk_source` : filtre déterministe (hébergeurs de documents, contenu adulte/piratage, pages de définition).
2. `curate_sources` : jugement sémantique par un LLM rapide (score 0-3 par source), puis plafonnement
   sur les sources les plus pertinentes. Si le juge est indisponible, seul le filtre déterministe s'applique.

Le jugement sémantique ne repose volontairement pas sur un recouvrement lexical : les recherches sont
multilingues, une source anglaise pertinente ne partage pas les mots de la question française.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    yaml = None

from . import providers

_logger = logging.getLogger(__name__)

# ==============================================================================
# CLASSIFICATION UNIVERSELLE DES PLATEFORMES ET DOMAINES WEB (A à F)
# ==============================================================================

# Tier F : Pollution documentaire avérée (Critères objectivables : spam SEO, faux miroirs,
# contenu adulte/malware/piratage sans rapport, pages de définition sans apport, e-commerce pur, usurpation).
_POLLUTION_JUNK_DOMAINS = (
    "f95zone.to", "xvideos.", "pornhub.", "xnxx.", "xhamster.", "onlyfans.com",
    "1337x.", "thepiratebay.", "nulled.", "torrent", "crack", "warez",
    "freepik.com", "shutterstock.", "istockphoto.",
    # E-commerce / shopping pur sans apport analytique
    "galerieslafayette.com", "cdiscount.com", "aliexpress.com", "zalando.",
    "shein.com", "temu.com", "boulanger.com", "darty.com", "laredoute.",
    "showroomprive.com", "veepee.com", "etsy.com", "vinted.",
    # Dictionnaires et traducteurs purs sans contenu de preuve
    "youdao.com", "wordreference.com", "linguee.", "reverso.net",
    "pons.com", "bab.la", "dict.cc", "collinsdictionary.com", "le-dictionnaire.com",
)

# Tier E (par défaut) : Plateformes d'hébergement de documents déposés par les utilisateurs (UGC)
# Non vérifiés par défaut, mais JAMAIS exclus d'office en Tier F :
# Un document original de chercheur sur Scribd/Studocu peut être promu après vérification de l'auteur et des preuves.
_DOC_SHARING_DOMAINS = (
    "scribd.com", "fr.scribd.com", "studocu.com", "coursehero.com",
    "docsity.com", "pdfcoffee.com", "slideshare.net", "academia.edu", "yumpu.com",
)

# Tier E (par défaut) : Réseaux sociaux, forums, communautés et questions-réponses
# Utiles pour retours d'expérience terrain, signaux faibles, dépannage ou déclarations directes.
_UGC_COMMUNITY_DOMAINS = (
    "reddit.com", "quora.com", "stackoverflow.com", "stackexchange.com",
    "superuser.com", "serverfault.com", "forum.", "boards.",
    "pinterest.", "pin.it", "tumblr.com",
    "facebook.com", "twitter.com", "x.com", "tiktok.com", "instagram.com", "threads.net",
)

# Tier D (par défaut) : Blogs, plateformes de publication individuelle et comparateurs
_UGC_BLOG_DOMAINS = (
    "medium.com", "substack.com", "wordpress.com", "blogspot.com", "blogger.com",
    "hashnode.dev", "dev.to",
)

# Tier D (par défaut) : Encyclopédies collaboratives (point de départ pour remonter aux sources primaires)
_COLLABORATIVE_DOMAINS = (
    "wikipedia.org", "wikimedia.org", "wikiversity.org",
)

# Tier C (par défaut) : Presse de référence reconnue et journalisme d'investigation
_NEWS_PRESS_DOMAINS = (
    "afp.com", "reuters.com", "apnews.com", "lemonde.fr", "lesechos.fr", "lefigaro.fr",
    "usinenouvelle.com", "ft.com", "wsj.com", "economist.com", "bloomberg.com",
    "arstechnica.com", "wired.com", "nature.com/news",
)

# Rétrocompatibilité : _JUNK_DOMAINS pointe sur la pollution documentaire avérée
_JUNK_DOMAINS = _POLLUTION_JUNK_DOMAINS

# Registres YAML par mode (DeepSearch et Mode Apprendre)
_YAML_PATH_DEEPSEARCH = Path(__file__).parent / "trusted_sources_deepsearch.yaml"
_YAML_PATH_LEARN = Path(__file__).parent / "trusted_sources_learn.yaml"
_YAML_PATH_DEFAULT = Path(__file__).parent / "trusted_sources.yaml"


def _load_trusted_registry_file(yaml_file: Path) -> tuple[dict[str, tuple[str, ...]], set[str], dict[str, str]]:
    specs: dict[str, list[str]] = {}
    primaries: set[str] = set()
    tiers: dict[str, str] = {}
    target_path = yaml_file if yaml_file.exists() else _YAML_PATH_DEFAULT
    if yaml and target_path.exists():
        try:
            raw = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
            specialties = raw.get("specialties") or {}
            for s_id, s_data in specialties.items():
                d_list = []
                for entry in s_data.get("domains") or []:
                    dom = str(entry.get("domain") or "").strip().lower()
                    if not dom:
                        continue
                    d_list.append(dom)
                    prio = str(entry.get("priority") or "B").strip().upper()
                    tiers[dom] = prio
                    if entry.get("is_primary"):
                        primaries.add(dom)
                if d_list:
                    specs[s_id] = d_list
        except Exception as e:
            _logger.warning("Erreur lors de la lecture de %s: %s", target_path.name, e)
    return {k: tuple(v) for k, v in specs.items()}, primaries, tiers


# Registres chargés au démarrage
_DEEPSEARCH_SPECS, _DEEPSEARCH_PRIMARIES, DOMAIN_TIERS_DEEPSEARCH = _load_trusted_registry_file(_YAML_PATH_DEEPSEARCH)
_LEARN_SPECS, _LEARN_PRIMARIES, DOMAIN_TIERS_LEARN = _load_trusted_registry_file(_YAML_PATH_LEARN)

# Rétrocompatibilité : DOMAIN_TIERS pointe par défaut sur le registre DeepSearch
DOMAIN_TIERS = DOMAIN_TIERS_DEEPSEARCH
_REG_PRIMARIES = _DEEPSEARCH_PRIMARIES
_REG_SPECS = _DEEPSEARCH_SPECS

# Domaines primaires et de référence institutionnelle (statistiques officielles, recherche, ministères)
PRIMARY_DOMAINS = tuple(
    sorted(
        set(
            (
                ".gouv.fr", "insee.fr", "france-strategie.fr", "strategie-plan.gouv.fr", "dares.travail-emploi.gouv.fr",
                "cereq.fr", "francetravail.fr", "francetravail.org", "depp.education.gouv.fr", "enseignementsup-recherche.gouv.fr",
                "onisep.fr", "education.gouv.fr", "legifrance.gouv.fr", "ccomptes.fr", "vie-publique.fr", "senat.fr", "assemblee-nationale.fr",
                "service-public.fr", "cnil.fr", "curia.europa.eu", "eur-lex.europa.eu",
                "oecd.org", "eurostat.ec.europa.eu", "europa.eu", "banque-france.fr", "ecb.europa.eu", "imf.org", "worldbank.org", "bis.org",
                "who.int", "unesco.org", ".gov", ".edu", "pubmed.ncbi.nlm.nih.gov", "cochranelibrary.com", "hal.science",
                "arxiv.org", "github.com", "nature.com", "science.org", "docs.python.org", "developer.mozilla.org", "nvd.nist.gov", "owasp.org", "docs.kernel.org",
            )
        )
        | _REG_PRIMARIES
    )
)

# Registre de domaines prioritaires par spécialité (fusionné avec YAML)
_DEFAULT_SPECIALTY_DOMAINS: dict[str, tuple[str, ...]] = {
    "emploi_education": (
        "dares.travail-emploi.gouv.fr", "strategie-plan.gouv.fr", "france-strategie.fr",
        "francetravail.org", "francetravail.fr", "cereq.fr", "onisep.fr",
        "education.gouv.fr", "enseignementsup-recherche.gouv.fr", "bls.gov", "cedefop.europa.eu", "ilo.org", "nces.ed.gov", "oecd.org",
    ),
    "science_recherche": (
        "pubmed.ncbi.nlm.nih.gov", "arxiv.org", "nature.com", "science.org",
        "hal.science", "cochranelibrary.com", "biorxiv.org", "medrxiv.org", "cell.com", "thelancet.com", "nejm.org", "jamanetwork.com", "pnas.org",
    ),
    "economie_finances": (
        "insee.fr", "banque-france.fr", "ecb.europa.eu", "federalreserve.gov", "bankofengland.co.uk", "oecd.org",
        "imf.org", "worldbank.org", "bis.org", "eurostat.ec.europa.eu", "nber.org", "bea.gov",
    ),
    "droit_reglementation": (
        "legifrance.gouv.fr", "eur-lex.europa.eu", "service-public.fr",
        "cnil.fr", "curia.europa.eu", "supremecourt.gov", "congress.gov", "echr.coe.int", "icj-cij.org",
    ),
    "informatique_ia": (
        "docs.python.org", "developer.mozilla.org", "github.com",
        "arxiv.org", "nvd.nist.gov", "owasp.org", "docs.kernel.org", "huggingface.co", "paperswithcode.com", "pytorch.org",
    ),
}

SPECIALTY_DOMAINS: dict[str, tuple[str, ...]] = {
    **_DEFAULT_SPECIALTY_DOMAINS,
    **_REG_SPECS,
}
# Pages de définition / dictionnaire : hors sujet pour une investigation.
_DEFINITION_PATH_RE = re.compile(
    r"/(?:dictionnaire|definition|définition|synonymes?|conjugaison|dictionary|thesaurus)(?:/|$|\?)", re.IGNORECASE,
)
_SHOPPING_PATH_RE = re.compile(
    r"/(?:produits?|products?|boutique|panier|cart|checkout|catalogue/achat|shop|store|rayon|promotions?)(?:/|$|\?)",
    re.IGNORECASE,
)
_ADULT_OR_SPAM_RE = re.compile(
    r"\b(?:porn\w*|xxx|nsfw|hentai|adult game|jeu pour adultes|jeux? adulte|sex\s*toy|dildo|vibrat(?:or|eur)|"
    r"lingerie [eé]rotique|accessoires? sexuels?|masturbat\w*|escort\w*|casino|poker|paris sportifs?|gambling|slot machine)\b",
    re.IGNORECASE,
)

JUDGE_BATCH_SIZE = 30
KEEP_MIN_SCORE = 2
DEFAULT_MAX_KEEP = 60


def _domain(source: dict[str, Any]) -> str:
    try:
        return (urlparse(str(source.get("url") or source.get("img_src") or "")).hostname or "").lower()
    except ValueError:
        return ""


def is_junk_source(source: dict[str, Any]) -> bool:
    """Vrai uniquement si la source présente des critères objectivables de pollution documentaire (Tier F) :
    1. Domaines de spam avérés, piratage de malware, faux miroirs, contenu adulte ou shopping pur.
    2. Titre ou URL contenant des termes adultes, érotiques, jeux d'argent ou piratage.
    3. Pages de dictionnaire lexical pur ou paniers d'achat e-commerce sans apport analytique.

    Attention : Scribd, Studocu, Reddit, Medium, Wikipédia ne sont JAMAIS considérés comme du junk (Tier F).
    Ils reçoivent un niveau initial par défaut (E ou D) et sont jugés sur la valeur de leur document.
    """
    url = str(source.get("url") or source.get("img_src") or "").lower()
    domain = _domain(source)
    if any(bad in domain for bad in _POLLUTION_JUNK_DOMAINS):
        return True
    if domain.startswith("dict.") or domain.startswith("dictionary."):
        return True
    if _DEFINITION_PATH_RE.search(url):
        return True
    if _SHOPPING_PATH_RE.search(url):
        return True
    return bool(_ADULT_OR_SPAM_RE.search(f"{source.get('title', '')} {url} {source.get('snippet', '')}"))


def is_promoted_ugc_document(source: dict[str, Any]) -> bool:
    """Détecte si un document hébergé sur une plateforme UGC (Scribd, Studocu, Academia.edu, etc.)
    ou un article de blog (Medium, Substack) présente les attributs d'un travail d'auteur sérieux
    (auteur identifiable, thèse/mémoire, méthodologie, échantillon, DOI, données chiffrées).
    Dans ce cas, il est promu du niveau E/D vers un niveau supérieur (C ou B).
    """
    title = str(source.get("title") or "")
    snippet = str(source.get("snippet") or "")
    combined = f"{title} {snippet}"

    # 1. Présence d'un identifiant scientifique permanent (DOI)
    if re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", combined):
        return True

    # 2. Type de publication académique ou rapport d'étude identifié
    has_academic = bool(
        re.search(
            r"\b(?:thèse|dissertation|mémoire\s+de\s+(?:recherche|master)|working\s+paper|rapport\s+d'étude|research\s+paper|technical\s+report)\b",
            combined,
            re.IGNORECASE,
        )
    )

    # 3. Présence de méthodologie et de données probantes
    has_methodology = bool(_EVIDENCE_MARKERS_RE.search(combined))
    has_figures = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|€|\$|k€|millions?)\b", snippet, re.IGNORECASE))

    return has_academic or (has_methodology and has_figures)


# Chemins d'URL caractéristiques de la communication institutionnelle, actualité ou événement (non primaires)
_SECONDARY_PR_PATH_RE = re.compile(
    r"/(?:actualites?|news|communiques?(?:-de-presse)?|press-releases?|blog|evenements?|events?|agenda|discours|editorial|tribune|interviews?|point-presse|media|contact|a-propos|about)(?:/|$|\?|\.)",
    re.IGNORECASE,
)

# Termes de communication / actualité dans le titre ou l'extrait
_SECONDARY_PR_TEXT_RE = re.compile(
    r"\b(?:communiqu[ée](?:\s+de\s+presse)?|dossier\s+de\s+presse|agenda\s+(?:du|de\s+la)\s+ministre|discours\s+de|interview\s+de|conf[ée]rence\s+de\s+presse|point\s+presse|inauguration|flash\s+info)\b",
    re.IGNORECASE,
)

# Chemins d'URL pointant vers des documents primaires (études, données, lois, publications scientifiques)
_PRIMARY_DOC_PATH_RE = re.compile(
    r"/(?:articles?|papers?|doi|pdf|publications?|etudes?(?:-et-statistiques)?|donnees|statistiques|rapports?|reports?|datasets?|tableaux|enquetes?|data|rfc|std|lois?|decrets?|arretes?|codes?|decisions?)(?:/|$|\?|\.)|\.pdf$",
    re.IGNORECASE,
)

# Marqueurs méthodologiques et de preuves scientifiques/statistiques
_EVIDENCE_MARKERS_RE = re.compile(
    r"\b(?:m[ée]thodologie|donn[ée]es\s+brutes|s[ée]rie\s+chronologique|cohorte|[ée]chantillon|m[ée]ta-analyse|revue\s+syst[ée]matique|tableaux\s+statistiques|intervalle\s+de\s+confiance|p\s*[<=]\s*0\.\d+|n\s*=\s*\d+|r[ée]sultats\s+détaillés|abstract|doi:10\.\d{4,9}/)\b",
    re.IGNORECASE,
)


def is_primary_domain(source: dict[str, Any]) -> bool:
    """Indique si le domaine hébergeur est habituellement un producteur ou diffuseur de référence (Tier A/B)."""
    domain = _domain(source)
    url = str(source.get("url") or "").lower()
    if any(p in domain or p in url for p in PRIMARY_DOMAINS):
        return True
    return DOMAIN_TIERS.get(domain) in ("A", "B")


# Alias pour rétrocompatibilité
is_primary_source = is_primary_domain


def is_primary_document(source: dict[str, Any]) -> bool:
    """Distingue la nature du document effectivement consulté :
    - Faux si c'est un communiqué de presse, une actualité institutionnelle, un agenda ou un discours,
      même hébergé sur un site gouvernemental ou académique (Tier A habituel).
    - Vrai si le document présente des données primaires, une étude méthodologique, un jeu de données,
      un texte juridique officiel ou une publication scientifique originale.
    """
    url = str(source.get("url") or "").lower()
    title = str(source.get("title") or "")
    snippet = str(source.get("snippet") or "")
    combined_text = f"{title} {snippet}"

    # 1. Élimination formelle si le chemin d'URL ou le texte est purement communicationnel/événementiel
    if _SECONDARY_PR_PATH_RE.search(url) or _SECONDARY_PR_TEXT_RE.search(combined_text):
        return False

    domain_primary = is_primary_domain(source)
    has_primary_path = bool(_PRIMARY_DOC_PATH_RE.search(url))
    has_evidence_markers = bool(_EVIDENCE_MARKERS_RE.search(combined_text))

    if domain_primary:
        # Sur un domaine institutionnel : c'est un document primaire s'il ne s'agit pas de RP/agenda,
        # et qu'il cible une publication/données ou qu'on trouve des preuves statistiques/méthodes
        return has_primary_path or has_evidence_markers or (not _SECONDARY_PR_PATH_RE.search(url))

    # Sur un domaine généraliste ou indépendant, le document peut tout de même être primaire
    # (ex: PDF d'un laboratoire, dépôt de données brutes, article scientifique avec DOI)
    return has_primary_path and has_evidence_markers


def classify_source_tier(source: dict[str, Any], learn_mode: bool = False) -> str:
    """Classe la source selon la hiérarchie universelle A à F en séparant 3 décisions :
    1. Niveau du domaine : a priori initial (registre YAML selon le mode, plateformes UGC, presse).
    2. Qualité du document : détection de preuves, auteur, méthodologie (promotion E/D -> C/B ou rétrogradation A -> B).
    3. Pertinence exacte : évaluée indépendamment dans calculate_source_quality_score et curate_sources.
    """
    # 1. Élimination exclusive des pollutions documentaires avérées (Tier F objectivable)
    if is_junk_source(source):
        return "F"

    domain = _domain(source)
    url = str(source.get("url") or "").lower()
    doc_is_primary = is_primary_document(source)
    dom_is_primary = is_primary_domain(source)
    ugc_promoted = is_promoted_ugc_document(source)

    # 2. Plateformes d'hébergement de documents UGC (Scribd, Studocu, CourseHero, Academia.edu, etc.)
    # Par défaut Tier E, avec promotion en Tier C si étude d'auteur / méthodologie / DOI vérifié
    if any(plat in domain for plat in _DOC_SHARING_DOMAINS):
        if ugc_promoted or doc_is_primary:
            return "C"  # Document sérieux identifié sur plateforme hébergée
        return "E"      # Niveau E par défaut (non exclu)

    # 3. Forums, réseaux sociaux et communautés (Reddit, Quora, Stack Overflow, etc.)
    # Par défaut Tier E, avec promotion en Tier D si contribution technique détaillée
    if any(plat in domain for plat in _UGC_COMMUNITY_DOMAINS):
        if ugc_promoted:
            return "D"
        return "E"

    # 4. Blogs et plateformes de publication individuelle (Medium, Substack, etc.)
    # Par défaut Tier D, avec promotion en Tier C si analyse d'expert avec méthodologie
    if any(plat in domain for plat in _UGC_BLOG_DOMAINS):
        if ugc_promoted:
            return "C"
        return "D"

    # 5. Encyclopédies collaboratives (Wikipedia, etc.)
    # Tier D : point de départ pour remonter aux sources primaires
    if any(plat in domain for plat in _COLLABORATIVE_DOMAINS):
        return "D"

    # 6. Registre de priorités YAML adapté au mode (DeepSearch vs Mode Apprendre)
    active_tiers = DOMAIN_TIERS_LEARN if learn_mode else DOMAIN_TIERS_DEEPSEARCH
    for reg_dom, tier in active_tiers.items():
        if domain == reg_dom or domain.endswith("." + reg_dom):
            if tier == "A" and not doc_is_primary:
                # Rétrogradation d'une actualité/RP d'un domaine A en communication institutionnelle B
                return "B"
            return tier

    # 7. Document primaire avéré hors registre YAML (ex: laboratoire indépendant, preprint, loi)
    if doc_is_primary:
        if dom_is_primary:
            return "A"
        return "B"

    # 8. Domaine primaire habituel mais document d'actualité / communication
    if dom_is_primary:
        return "B"

    # 9. Presse spécialisée reconnue et journalisme d'investigation
    if any(k in domain for k in _NEWS_PRESS_DOMAINS):
        return "C"

    # 10. Presse généraliste et web ouvert par défaut (évalué au mérite)
    return "D"


_CATALOG_OR_NAV_RE = re.compile(
    r"\b(?:index\.php\?lvl=|lvl=publisher_see|catalogue|documentation\.|portail|annuaire|recherche\?|"
    r"liste\s+des\s+publications|toutes\s+les\s+publications|notice\s+générale|a-propos|about-us|"
    r"/taxonomy/|/category/|/tag/|/rubrique/)\b",
    re.IGNORECASE,
)


def is_catalog_or_nav_page(source: dict[str, Any]) -> bool:
    """Détecte les pages de catalogues documentaires, annuaires, index ou pages de métadonnées d'éditeurs
    qui ne constituent pas le rapport statistique original lui-même."""
    url = str(source.get("url") or "").lower()
    title = str(source.get("title") or "").lower()
    snippet = str(source.get("snippet") or "").lower()

    if _CATALOG_OR_NAV_RE.search(url):
        return True
    if any(k in title for k in ("catalogue documentaire", "liste des publications", "annuaire des", "portail documentaire", "notice bibliographique")):
        return True
    return False


def calculate_source_quality_score(
    source: dict[str, Any],
    question: str = "",
    semantic_score: int | None = None,
    learn_mode: bool = False,
) -> float:
    """Calcule un score global sur 100 basé sur les 6 piliers :
    1. Pertinence exacte pour la question (35 %)
    2. Proximité avec la source primaire / Hiérarchie A-F (20 %)
    3. Qualité des preuves et méthodologie (données chiffrées/techniques) (20 %)
    4. Fraîcheur temporelle adaptée (10 %)
    5. Indépendance et autorité du domaine (10 %)
    6. Accessibilité du contenu (5 %)
    """
    # 1. Pertinence exacte (35 pts max)
    relevance_pt = 25.0
    if semantic_score is not None:
        # semantic_score va de 0 à 3
        relevance_pt = (semantic_score / 3.0) * 35.0
    elif question:
        q_words = {w.lower() for w in re.findall(r"\w{4,}", question)}
        content = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
        matches = sum(1 for w in q_words if w in content)
        ratio = min(1.0, matches / max(1, len(q_words)))
        relevance_pt = 15.0 + ratio * 20.0

    # 2. Proximité source primaire / Nature du document (20 pts max)
    tier = classify_source_tier(source, learn_mode=learn_mode)
    tier_scores = {"A": 20.0, "B": 16.0, "C": 13.0, "D": 10.0, "E": 5.0, "F": 0.0}
    primary_pt = tier_scores.get(tier, 10.0)
    if is_primary_document(source) and primary_pt < 20.0:
        primary_pt = min(20.0, primary_pt + 3.0)

    # Pénalité stricte au niveau du document : un domaine de confiance (Tier A) pointant vers
    # un simple catalogue documentaire, une page d'accueil ou un index perd sa prime de source primaire
    if is_catalog_or_nav_page(source):
        primary_pt = max(6.0, primary_pt - 10.0)

    # 3. Qualité des preuves (chiffres, méthodologie, métriques) (20 pts max)
    snippet = str(source.get("snippet") or "")
    evidence_pt = 8.0
    if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:%|€|\$|k€|millions?|milliards?|points?|pts)\b", snippet, re.IGNORECASE):
        evidence_pt += 7.0
    if re.search(r"\b(méthodologie|échantillon|cohorte|enquête|statistique|taux|rapport|étude)\b", snippet, re.IGNORECASE):
        evidence_pt += 5.0
    evidence_pt = min(20.0, evidence_pt)

    # 4. Fraîcheur (10 pts max)
    freshness_pt = 7.0
    combined = f"{source.get('title', '')} {snippet}"
    if re.search(r"\b(?:202[3-6])\b", combined):
        freshness_pt = 10.0
    elif re.search(r"\b(?:202[0-2])\b", combined):
        freshness_pt = 6.0

    # 5. Indépendance et provenance (10 pts max)
    domain_pt = 8.0 if is_primary_domain(source) else 5.0
    if is_catalog_or_nav_page(source):
        domain_pt = max(2.0, domain_pt - 4.0)

    # 6. Accessibilité (5 pts max)
    access_pt = 5.0 if snippet and len(snippet) > 40 else 2.0

    total = relevance_pt + primary_pt + evidence_pt + freshness_pt + domain_pt + access_pt
    return round(min(100.0, max(0.0, total)), 1)


_PRIMARY_CITE_RE = re.compile(
    r"\b(?:selon|d'après|publié\s+par|source\s*:|rapport\s+(?:annuel\s+)?(?:de|du|d'|des)|données|chiffres|"
    r"according\s+to|reported\s+by|published\s+by|data\s+from)\s*"
    r"(?:une\s+étude|un\s+rapport|l'étude|le\s+rapport|les\s+données|les\s+chiffres|a\s+report|the\s+report|data)?\s*"
    r"(?:de\s+la|de\s+l'|du|de|d'|des|le|la|les|by|from)?\s*"
    r"(dares|france\s+stratégie|insee|céreq|cereq|depp|onisep|ocde|oecd|banque\s+de\s+france|eurostat|cnrs|inserm|who|fmi|imf|world\s+bank|bls|cdc|nih|cour\s+des\s+comptes)\b",
    re.IGNORECASE,
)


def extract_primary_source_citations(texts: list[str] | str) -> list[str]:
    """Primary Source Resolution : détecte les mentions d'études ou d'organismes officiels
    cités par des articles secondaires pour remonter vers la publication primaire."""
    if isinstance(texts, str):
        texts = [texts]
    detected: set[str] = set()
    for text in texts:
        for match in _PRIMARY_CITE_RE.finditer(text):
            org = match.group(1).strip()
            if org:
                detected.add(org.title())
    return sorted(detected)


def _is_image(source: dict[str, Any]) -> bool:
    return source.get("media_type") == "image" or bool(source.get("img_src"))


def prefilter_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retire les sources évidemment hors sujet (y compris images provenant de domaines indésirables)."""
    return [s for s in sources if not is_junk_source(s)]


def filter_findings_by_sources(findings: list[str], kept_sources: list[dict[str, Any]]) -> list[str]:
    """Retire les notes extraites d'une source écartée (les notes contiennent `URL: <url>`)."""
    kept_urls = {str(s.get("url") or "").strip() for s in kept_sources}
    result: list[str] = []
    for note in findings:
        match = re.search(r"URL:\s*(\S+)", note)
        if not match or match.group(1).rstrip("|]") in kept_urls or match.group(1) in kept_urls:
            result.append(note)
    return result


def _lexical_relevance_fallback(source: dict[str, Any], question: str) -> int:
    """Calcule une note de pertinence lexicale et thématique (0 à 3) si le juge LLM est indisponible ou incomplet."""
    if not question:
        return 2
    tokens = {w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", question) if len(w) >= 4}
    text = f"{source.get('title', '')} {source.get('snippet', '')}".lower()
    matches = sum(1 for tok in tokens if tok in text)
    if is_primary_document(source) and matches >= 1:
        return 3
    if matches >= 3:
        return 3
    if matches >= 2:
        return 2
    if matches >= 1:
        return 1
    return 0


async def curate_sources(
    settings: Any,
    question: str,
    sources: list[dict[str, Any]],
    max_keep: int = DEFAULT_MAX_KEEP,
    use_llm_judge: bool = True,
    learn_mode: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Filtre déterministe puis jugement sémantique ; retourne (sources conservées triées, statistiques)."""
    images = [s for s in sources if _is_image(s)]
    texts = [s for s in sources if not _is_image(s)]
    stats = {"initial": len(texts), "junk": 0, "irrelevant": 0, "kept": 0, "judged": 0}

    candidates = [s for s in texts if not is_junk_source(s)]
    stats["junk"] = len(texts) - len(candidates)

    scores: dict[int, int] = {}
    if use_llm_judge and candidates:
        try:
            scores = await providers.judge_source_relevance(settings, question, candidates, batch_size=JUDGE_BATCH_SIZE)
        except Exception as exc:  # le filtrage sémantique ne doit jamais bloquer la recherche
            _logger.warning("Juge de pertinence indisponible, repli lexical actif : %s", exc)
            scores = {}
    stats["judged"] = len(scores)

    if scores:
        scored = [(scores.get(i, 0), i, s) for i, s in enumerate(candidates)]
        kept = [t for t in scored if t[0] >= KEEP_MIN_SCORE]
        if len(kept) < 8:  # repli : compléter avec les sources tangentielles (score 1) pour ne pas vider le rapport
            kept += sorted((t for t in scored if t[0] == 1), key=lambda t: t[1])[: 8 - len(kept)]
        kept.sort(key=lambda t: (-t[0], t[1]))
        stats["irrelevant"] = len(candidates) - len(kept)
        result = [
            dict(
                s,
                relevance_score=score,
                tier=classify_source_tier(s, learn_mode=learn_mode),
                quality_score=calculate_source_quality_score(s, question, semantic_score=score, learn_mode=learn_mode),
            )
            for score, _, s in kept[:max_keep]
        ]
        result.sort(key=lambda x: (x.get("quality_score", 0), x.get("relevance_score", 0)), reverse=True)
        stats["irrelevant"] += max(0, len(kept) - max_keep)
    else:
        tokens = {w.lower() for w in re.findall(r"[a-zA-ZÀ-ÿ]{3,}", question) if len(w) >= 3}
        if tokens:
            scored = [(_lexical_relevance_fallback(s, question), i, s) for i, s in enumerate(candidates)]
            kept = [t[2] for t in scored if t[0] >= 1 or is_primary_document(t[2])]
            if not kept and candidates:
                kept = candidates
            stats["irrelevant"] = len(candidates) - len(kept)
            result = kept[:max_keep]
        else:
            result = candidates[:max_keep]
    stats["kept"] = len(result)
    return result + images, stats


async def enrich_top_sources_content(settings: Any, sources: list[dict[str, Any]], limit: int = 10) -> None:
    """Récupère le contenu textuel complet des meilleures sources candidates (top A/B/C)
    pour que le rédacteur et le vérificateur factuel disposent des données réelles et non de simples snippets.
    Applicable à DeepSearch ET au Mode Apprendre.
    """
    if not settings or getattr(settings, "demo_mode", False) or not sources:
        return
    try:
        from . import web
    except ImportError:
        return

    candidates = [
        s for s in sources
        if not s.get("content") and s.get("media_type") != "image" and not s.get("img_src")
    ][:limit]
    if not candidates:
        return

    sem = asyncio.Semaphore(4)

    async def _fetch(src: dict[str, Any]) -> None:
        url = str(src.get("url") or "").strip()
        if not url.startswith("http"):
            return
        async with sem:
            try:
                res = await asyncio.wait_for(
                    web.fetch_and_parse_web_url(settings, url), timeout=5.0
                )
                extracted_text = ""
                if isinstance(res, tuple) and len(res) >= 4:
                    extracted_text = str(res[3] or "")
                elif isinstance(res, dict):
                    extracted_text = str(res.get("text") or res.get("content") or "")

                if extracted_text and len(extracted_text.strip()) > 100:
                    src["content"] = extracted_text.strip()[:8000]
            except Exception:
                pass

    await asyncio.gather(*[_fetch(s) for s in candidates], return_exceptions=True)


