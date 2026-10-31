import asyncio

from app import providers
from app.source_filter import curate_sources, filter_findings_by_sources, is_junk_source, prefilter_sources

JUNK = [
    {"title": "Définition de délimitation", "url": "https://www.linternaute.fr/dictionnaire/fr/definition/delimitation/", "snippet": "n.f."},
    {"title": "Jeu pour adultes", "url": "https://f95zone.to/threads/12", "snippet": "game"},
    {"title": "Pornography video", "url": "https://xvideos.com/video123", "snippet": "adult xxx"},
    {"title": "Cracked software warez", "url": "https://thepiratebay.org/torrent/123", "snippet": "crack"},
]
GOOD = {"title": "Insertion des diplômés", "url": "https://www.cereq.fr/insertion", "snippet": "Enquête Génération"}


def test_junk_sources_detected_and_images_untouched():
    assert all(is_junk_source(s) for s in JUNK)
    assert not is_junk_source(GOOD)
    image = {"title": "img", "url": "https://x.org", "img_src": "https://example.com/i.jpg", "media_type": "image"}
    assert prefilter_sources(JUNK + [GOOD, image]) == [GOOD, image]


def test_curate_applies_llm_scores_and_caps(monkeypatch):
    sources = [dict(GOOD, url=f"https://site{i}.org/a", title=f"S{i}") for i in range(12)] + JUNK

    async def fake_judge(settings, question, candidates, batch_size=30):
        return {i: (0 if i in (1, 2) else 3) for i in range(len(candidates))}

    monkeypatch.setattr(providers, "judge_source_relevance", fake_judge)
    kept, stats = asyncio.run(curate_sources(None, "orientation", sources))
    assert stats["junk"] == 4
    assert stats["irrelevant"] == 2
    assert len(kept) == 10
    assert all(s["relevance_score"] == 3 for s in kept)


def test_curate_falls_back_to_deterministic_when_judge_fails(monkeypatch):
    async def broken(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(providers, "judge_source_relevance", broken)
    kept, stats = asyncio.run(curate_sources(None, "q", JUNK + [GOOD]))
    assert kept == [GOOD]
    assert stats["kept"] == 1


def test_partial_judge_response_does_not_drop_unjudged_primary_documents(monkeypatch):
    async def partial(*args, **kwargs):
        return {0: 0}

    monkeypatch.setattr(providers, "judge_source_relevance", partial)
    documents = [dict(GOOD, url="https://example.org/rejected"), GOOD]
    kept, stats = asyncio.run(curate_sources(None, "insertion professionnelle", documents))
    assert [s["url"] for s in kept] == [GOOD["url"]]
    assert stats["kept"] == 1


def test_findings_of_removed_sources_are_dropped():
    findings = ["[T | URL: https://www.cereq.fr/insertion | Date: N/A | Contexte: x] ok", "[T | URL: https://scribd.com/z | Date: N/A | Contexte: x] bad"]
    assert filter_findings_by_sources(findings, [GOOD]) == [findings[0]]


def test_classify_source_tier_and_scoring():
    from app.source_filter import calculate_source_quality_score, classify_source_tier

    primary = {"url": "https://dares.travail-emploi.gouv.fr/etude", "title": "Insertion 2024", "snippet": "Taux d'insertion de 94 % et 38 000 €"}
    tier_a = classify_source_tier(primary)
    assert tier_a == "A"
    score_a = calculate_source_quality_score(primary, question="insertion professionnelle", semantic_score=3)
    assert score_a >= 80.0

    pinterest_src = {"url": "https://pinterest.com/pin/123", "title": "Pin"}
    assert classify_source_tier(pinterest_src) == "E"

    junk = {"url": "https://f95zone.to/threads/123", "title": "Adult game crack"}
    assert classify_source_tier(junk) == "F"


def test_primary_source_resolution_extracts_cited_orgs():
    from app.source_filter import extract_primary_source_citations

    texts = [
        "Selon une étude de la DARES publiée récemment...",
        "D'après les chiffres de France Stratégie et les données INSEE...",
    ]
    citations = extract_primary_source_citations(texts)
    assert "Dares" in citations
    assert "France Stratégie" in citations
    assert "Insee" in citations


def test_classify_international_english_domains():
    from app.source_filter import (
        SPECIALTY_DOMAINS,
        classify_source_tier,
        is_primary_document,
        is_primary_source,
    )

    # US BLS (Bureau of Labor Statistics) - Table de données statistiques
    bls = {
        "url": "https://www.bls.gov/emp/tables/occupational-projections-and-worker-characteristics.htm",
        "title": "Employment Projections: 2024-2034",
        "snippet": "National employment projections, statistical tables and methodology.",
    }
    assert is_primary_source(bls)
    assert is_primary_document(bls) is True
    assert classify_source_tier(bls) == "A"

    # Nature / Cell / Lancet (Scientific journals Tier A)
    nature = {"url": "https://www.nature.com/articles/s41586-024-00001", "title": "Quantum breakthrough"}
    cell = {"url": "https://www.cell.com/cell/fulltext/S0092-8674", "title": "Cell Biology"}
    assert classify_source_tier(nature) == "A"
    assert classify_source_tier(cell) == "A"

    # US Federal Reserve & NBER (Economics Tier A)
    fed = {"url": "https://www.federalreserve.gov/monetarypolicy/fomcminutes2024.htm", "title": "FOMC Minutes"}
    nber = {"url": "https://www.nber.org/papers/w31000", "title": "Macroeconomic Trends"}
    assert classify_source_tier(fed) == "A"
    assert classify_source_tier(nber) == "A"

    # Financial Times & Bloomberg (Press Tier C)
    ft = {"url": "https://www.ft.com/content/12345", "title": "Markets Overview"}
    assert classify_source_tier(ft) == "C"

    # IPCC & WHO (Global agencies Tier A pour publications, Tier B pour actualités)
    ipcc = {"url": "https://www.ipcc.ch/report/ar6/syr/", "title": "Synthesis Report"}
    assert classify_source_tier(ipcc) == "A"

    who_news = {"url": "https://www.who.int/news/item/12-05-2024", "title": "Global Health News"}
    assert classify_source_tier(who_news) == "B"  # Actualité institutionnelle -> B

    who_report = {
        "url": "https://www.who.int/publications/i/item/97892400000",
        "title": "Global Health Report",
        "snippet": "Systematic review, statistical cohort and epidemiological findings.",
    }
    assert classify_source_tier(who_report) == "A"  # Publication primaire -> A

    # Informatique / IA
    hf = {"url": "https://huggingface.co/papers/2401.12345", "title": "LLM Alignment"}
    assert classify_source_tier(hf) == "A"

    # Vérification présence des nouvelles spécialités
    assert "sante_biomedical" in SPECIALTY_DOMAINS
    assert "climat_energie_environnement" in SPECIALTY_DOMAINS


def test_distinction_primary_domain_vs_primary_document():
    from app.source_filter import (
        calculate_source_quality_score,
        classify_source_tier,
        is_primary_document,
        is_primary_domain,
    )

    # 1. Page d'actualité / communiqué de presse sur site ministériel (domaine primaire Tier A)
    ministerial_pr = {
        "url": "https://www.education.gouv.fr/actualites/communique-de-presse-rentree-2024",
        "title": "Communiqué de presse : déplacement du ministre",
        "snippet": "Le ministre inaugurera demain un nouvel établissement scolaire...",
    }
    assert is_primary_domain(ministerial_pr) is True
    # Ce n'est PAS un document primaire de données scientifiques ou statistiques
    assert is_primary_document(ministerial_pr) is False
    # Rétrogradé de A à B (communication institutionnelle, pas une preuve primaire)
    assert classify_source_tier(ministerial_pr) == "B"

    # 2. Publication / données statistiques réelles sur le même domaine
    ministerial_study = {
        "url": "https://www.education.gouv.fr/donnees/etudes-et-statistiques/depp-reperes-2024.pdf",
        "title": "Répères et références statistiques 2024",
        "snippet": "Méthodologie d'enquête et données brutes sur la cohorte 2018-2024 avec échantillon représentatif de 45 000 élèves.",
    }
    assert is_primary_domain(ministerial_study) is True
    assert is_primary_document(ministerial_study) is True
    assert classify_source_tier(ministerial_study) == "A"

    # 3. Étude scientifique hébergée sur un domaine indépendant / ouvert (non répertorié au YAML)
    independent_study = {
        "url": "https://independent-lab.org/papers/statistical-analysis-2024.pdf",
        "title": "Empirical study on LLM reasoning",
        "snippet": "Abstract: Comprehensive benchmark on 50 models, methodology, p < 0.001, n = 12000, doi:10.1234/test.2024",
    }
    assert is_primary_domain(independent_study) is False
    # Reconnu comme document primaire grâce aux marqueurs méthodologiques et au path
    assert is_primary_document(independent_study) is True
    assert classify_source_tier(independent_study) == "B"

    # 4. Vérification que le YAML n'est pas une liste blanche bloquante
    score_indep = calculate_source_quality_score(independent_study, question="reasoning benchmarks", semantic_score=3)
    # L'étude indépendante obtient un très bon score (> 75 pts) et sera conservée dans le rapport
    assert score_indep >= 75.0


def test_universal_platform_classification_and_promotions():
    from app.source_filter import classify_source_tier, is_junk_source, is_promoted_ugc_document

    # 1. Scribd / Studocu : JAMAIS de Tier F d'office, Tier E par défaut
    scribd_student_note = {
        "url": "https://fr.scribd.com/document/12345/cours-droit",
        "title": "Notes de cours de droit constitutionnel",
        "snippet": "Introduction générale au droit de 2e année.",
    }
    assert not is_junk_source(scribd_student_note)
    assert not is_promoted_ugc_document(scribd_student_note)
    assert classify_source_tier(scribd_student_note) == "E"

    # 2. Promotion d'un document scientifique ou d'une thèse hébergée sur Scribd/Studocu
    scribd_academic_thesis = {
        "url": "https://fr.scribd.com/document/99999/these-econometrie",
        "title": "Thèse de doctorat : Impact macroéconomique de l'automatisation",
        "snippet": "Mémoire de recherche universitaire, méthodologie économétrique, données de panel 1990-2022 et régression statistique.",
    }
    assert is_promoted_ugc_document(scribd_academic_thesis) is True
    # Promu de Tier E vers Tier C !
    assert classify_source_tier(scribd_academic_thesis) == "C"

    # 3. Réseaux sociaux & Forums : Tier E par défaut
    reddit_post = {
        "url": "https://www.reddit.com/r/learnprogramming/comments/xyz123/rust_async_lifetime/",
        "title": "How to handle lifetime in async Rust",
        "snippet": "I had this issue yesterday, here is how I fixed it...",
    }
    assert not is_junk_source(reddit_post)
    assert classify_source_tier(reddit_post) == "E"

    # 4. Wikipédia : Tier D par défaut (bon point de départ, pas une poubelle)
    wikipedia_page = {
        "url": "https://fr.wikipedia.org/wiki/Intelligence_artificielle",
        "title": "Intelligence artificielle",
        "snippet": "Ensemble des théories et des techniques mises en œuvre...",
    }
    assert not is_junk_source(wikipedia_page)
    assert classify_source_tier(wikipedia_page) == "D"

    # 5. Blogs (Medium, Substack) : Tier D par défaut, promu Tier C si expert avec méthode/stats
    medium_post = {
        "url": "https://medium.com/@author/tech-thoughts",
        "title": "Thoughts on new frameworks",
        "snippet": "Just a casual opinion about JavaScript in 2024.",
    }
    assert classify_source_tier(medium_post) == "D"

    medium_expert_study = {
        "url": "https://medium.com/@researcher/empirical-latency-study",
        "title": "Technical report on database latencies",
        "snippet": "Research paper: detailed methodology, benchmark on 100k requests with 99th percentile figures and 95% confidence intervals.",
    }
    assert is_promoted_ugc_document(medium_expert_study) is True
    assert classify_source_tier(medium_expert_study) == "C"

    # 6. Pollution documentaire réelle : Tier F (Exclusion documentée)
    malware_spam = {
        "url": "https://f95zone.to/threads/adult-pirated-game.123",
        "title": "Adult game free download crack",
        "snippet": "warez download torrent",
    }
    assert is_junk_source(malware_spam) is True
    assert classify_source_tier(malware_spam) == "F"

    # 7. Exclusion e-commerce pur, dictionnaires purs et sex toys (Signalés dans l'audit)
    ecommerce_shop = {
        "url": "https://www.galerieslafayette.com/p/mode-homme/123",
        "title": "Galeries Lafayette — Boutique en ligne",
        "snippet": "Achetez les dernières collections au meilleur prix.",
    }
    assert is_junk_source(ecommerce_shop) is True
    assert classify_source_tier(ecommerce_shop) == "F"

    dictionary_page = {
        "url": "https://dict.youdao.com/w/orientation",
        "title": "Dictionnaire Youdao — Formation professionnelle",
        "snippet": "Traduction et définition du mot.",
    }
    assert is_junk_source(dictionary_page) is True

    adult_accessory = {
        "url": "https://www.masterclass.com/articles/guide-accessoire-sexuel",
        "title": "Guide sur un accessoire sexuel et sex toys",
        "snippet": "Conseils d'utilisation pour adultes.",
    }
    assert is_junk_source(adult_accessory) is True
    assert classify_source_tier(adult_accessory) == "F"


