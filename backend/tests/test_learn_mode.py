import asyncio
import pytest

from app.learn_mode import (
    EvaluationOutput,
    LearnState,
    should_continue,
    execute_learn_mode,
)
from app.learn_html import (
    generate_learn_course_html,
    markdown_to_html,
    estimate_reading_time_minutes,
)


def test_learn_state_and_evaluation_output_schemas():
    output = EvaluationOutput(
        is_sufficient=False,
        critique="Manque d'exemples de code concrets",
        extracted_findings=["La descente de gradient calcule la dérivée partielle"],
        next_queries=["gradient descent python step by step"],
    )
    assert output.is_sufficient is False
    assert len(output.extracted_findings) == 1
    assert len(output.next_queries) == 1
    dump = output.model_dump()
    assert dump["critique"] == "Manque d'exemples de code concrets"

    state: LearnState = {
        "question": "Comprendre les réseaux de neurones",
        "iteration": 1,
        "max_iterations": 3,
        "findings": ["Faits initiaux"],
        "queries": ["deep learning intro"],
        "executed_queries": [],
        "sources": [],
        "is_sufficient": False,
        "critique": "",
        "final_answer": "",
    }
    assert state["question"] == "Comprendre les réseaux de neurones"


def test_should_continue_routing():
    assert should_continue({"is_sufficient": True, "iteration": 1, "max_iterations": 3, "queries": ["test"]}) == "synthesize"
    assert should_continue({"is_sufficient": False, "iteration": 4, "max_iterations": 3, "queries": ["test"]}) == "synthesize"
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "max_sources": 100, "sources": [{}] * 100, "queries": ["test"]}) == "synthesize"
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "queries": []}) == "synthesize"
    assert should_continue({"is_sufficient": False, "iteration": 1, "max_iterations": 3, "queries": ["module A"]}) == "search"


def test_execute_learn_mode_pipeline(monkeypatch):
    async def _run():
        class DummySettings:
            llm_api_key = "dummy"
            llm_base_url = "https://mock.ai"
            default_model = "mock-model"
            demo_mode = True

        settings = DummySettings()

        async def mock_search(query: str, limit: int = 10):
            return [
                {
                    "title": f"Cours didactique pour {query}",
                    "url": f"https://univ.edu/courses/{query.replace(' ', '-')}",
                    "snippet": f"Explication pédagogique détaillée et exemples pratiques sur {query}.",
                    "provider": "SearXNG",
                }
            ]

        events = []
        async for ev in execute_learn_mode(
            settings=settings,
            query="Apprendre les Transformers en IA",
            summary="",
            recent_turns=[],
            search_fn=mock_search,
            initial_queries=['"transformers" architecture attention cours', '"self-attention" step by step tutorial'],
            max_iterations=1,
        ):
            events.append(ev)

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        done = done_events[0]
        assert len(done["sources"]) >= 1
        assert any("univ.edu" in s["url"] for s in done["sources"])

    asyncio.run(_run())


def test_generate_learn_course_html():
    md = """# Cours Complet : Les Transformers
Bienvenue dans ce cours magistral interactif [1].

## 1. Intuition et Fondations
Le mécanisme d'attention permet de relier les mots distants sans récurrence [2].

### Exemple de Code
```python
def self_attention(Q, K, V):
    return "attention_weights"
```

| Modèle | Paramètres | Usage |
| --- | --- | --- |
| BERT | 110M | Encodage |
| GPT | 175B | Génération |
"""
    sources = [
        {"title": "Attention Is All You Need", "url": "https://arxiv.org/abs/1706.03762", "snippet": "The dominant sequence transduction models...", "provider": "arXiv"},
        {"title": "The Illustrated Transformer", "url": "https://jalammar.github.io/illustrated-transformer/", "snippet": "A visual explanation of Transformers.", "provider": "GitHub"},
    ]

    html_content, toc = markdown_to_html(md, sources)
    assert '<h1 id="cours-complet-les-transformers"' in html_content
    assert 'href="#source-1"' in html_content
    assert 'href="#source-2"' in html_content
    assert '<code class="language-python">' in html_content
    assert len(toc) >= 2

    page = generate_learn_course_html(
        title="Cours Complet : Les Transformers",
        topic="Transformers et Mécanisme d'Attention",
        markdown_content=md,
        sources=sources,
        created_at_str="24/10/2026 à 14:00",
    )
    assert "<!DOCTYPE html>" in page
    assert "Cours Complet : Les Transformers" in page
    assert "Mode Apprendre" in page
    assert "arxiv.org" in page
    assert "jalammar.github.io" in page
    assert estimate_reading_time_minutes(md) >= 1
    assert "flashcards-section" in page
    assert "quiz-section" in page
    assert "20 Flashcards" in page
    assert "20 Questions" in page


def test_parse_flashcards_and_quiz_count():
    from app.learn_html import parse_flashcards, parse_quiz
    md = """# Cours Test
## 1. Concepts
- **Attention :** Mécanisme de pondération des tokens.
- **Encodeur :** Module transformant l'entrée en vecteurs denses.
- **Décodeur :** Module générant la séquence de sortie.
### Flashcard 1
- **Recto :** Qu'est-ce que l'attention ?
- **Verso :** Un calcul matriciel reliant Q, K et V.
### Question 1
**Énoncé :** Quel est le composant central du Transformer ?
- A) Le Self-Attention
- B) Le LSTM
- C) La convolution 2D
- D) Le Pooling
- **Bonne réponse :** A
- **Explication :** Le Self-Attention remplace la récurrence.
"""
    fcs = parse_flashcards(md, "Transformers")
    assert len(fcs) == 20
    assert fcs[0]["recto"] == "Qu'est-ce que l'attention ?"

    quizzes = parse_quiz(md, "Transformers")
    assert len(quizzes) == 20
    assert "composant central" in quizzes[0]["question"]
    assert quizzes[0]["answer"] == 0


def test_learn_mode_uncapped_argon_planning_and_validation(monkeypatch):
    from app import providers

    async def _run():
        class DummySettings:
            llm_api_key = "dummy"
            llm_base_url = "https://mock.ai"
            default_model = "mock-model"
            deep_search_plan_model = "google/gemini-4-argon"
            deep_search_synthesis_model = "google/gemini-3.8-flash"
            demo_mode = False

            def enabled(self, val):
                return bool(val)

        settings = DummySettings()

        # 1. Vérifier que default_learn_themes n'est pas limité à 8 par défaut
        themes = providers.default_learn_themes("Les études d'ingénieur et l'IA")
        assert len(themes) >= 10
        assert any("360°" in t or "tension" in t or "obsolètes" in t for t in themes)

        # 2. Vérifier la validation intermédiaire et les questions intermédiaires dans execute_learn_mode
        call_count = 0

        async def mock_validate_learn(**kwargs):
            nonlocal call_count
            call_count += 1
            checklist = kwargs["aspect_checklist"]
            if call_count == 1:
                for idx, item in enumerate(checklist):
                    item["status"] = "covered" if idx < 3 else "partial"
                return {
                    "is_sufficient": False,
                    "aspect_checklist": checklist,
                    "intermediate_questions": [
                        "Quelles spécialités de bac offrent le meilleur taux de réussite en école d'ingénieurs ?",
                        "Quelles filières informatiques sont aujourd'hui saturées pour les profils juniors ?",
                    ],
                    "unanswered_aspects": ["Vision Panoramique 360°"],
                    "validation_summary": "3 points couverts, relance sur la vision 360° et l'international",
                    "followup_queries": [
                        '"études ingénieur" insertion professionnelle statistiques',
                        '"computer science" junior job market saturation',
                    ],
                    "searched_languages": ["fr", "en", "de"],
                }
            for item in checklist:
                item["status"] = "covered"
            return {
                "is_sufficient": True,
                "aspect_checklist": checklist,
                "intermediate_questions": [],
                "unanswered_aspects": [],
                "validation_summary": "Tous les points pédagogiques sont validés.",
                "followup_queries": [],
                "searched_languages": ["fr", "en", "de"],
            }

        monkeypatch.setattr(providers, "validate_and_followup_learn", mock_validate_learn)
        monkeypatch.setattr(
            providers,
            "decompose_learn_objective",
            lambda *a, **kw: asyncio.sleep(0, result=providers.default_learn_aspect_checklist("Orientation post-bac")),
        )
        monkeypatch.setattr(
            providers,
            "translate_deep_search_sources",
            lambda s, srcs, q: asyncio.sleep(0, result=srcs),
        )

        async def mock_search(query: str, limit: int = 10):
            return [
                {
                    "title": f"Support officiel pour {query}",
                    "url": f"https://education.gov/guide/{abs(hash(query))}",
                    "snippet": f"Analyse approfondie avec chiffres officiels et exercices corrigés sur {query}.",
                    "provider": "SearXNG",
                }
            ]

        events = []
        async for ev in execute_learn_mode(
            settings=settings,
            query="Dans quelles études se lancer actuellement ?",
            summary="",
            recent_turns=[],
            search_fn=mock_search,
            initial_queries=["Module 1 : Choix des spécialités au lycée"],
            max_iterations=4,
        ):
            events.append(ev)

        done = [e for e in events if e.get("type") == "done"][0]
        assert call_count == 2
        assert len(done["aspect_checklist"]) >= 7
        assert all(c["status"] == "covered" for c in done["aspect_checklist"])
        assert len(done["intermediate_questions"]) == 2
        assert any("QUESTIONS INTERMÉDIAIRES PÉDAGOGIQUES" in f for f in done["findings"])

    asyncio.run(_run())


def test_two_step_outline_planner_and_section_writer():
    from app import providers

    # Test Step 1 domain experts selection (ex. dette souveraine vs études)
    debt_experts = providers.default_domain_experts("Quelles sont les causes de la dette publique ?")
    assert len(debt_experts) == 1
    assert "Macroéconomie" in debt_experts[0]["title"]

    # Test Step 1 fallback & formatting (DeepSearch + Learn Mode) avec Expert Référent Global
    ds_outline = providers.default_report_outline("Quelles études faire et quels bacs privilégier ?", learn_mode=False)
    assert len(ds_outline["parts"]) >= 5
    assert len(ds_outline["experts"]) == 1
    # Les sous-parties restent ancrées dans la demande.
    assert "études faire" in ds_outline["parts"][0]["subparts"][0]

    ds_md = providers.format_report_outline_markdown(ds_outline, learn_mode=False)
    assert "Expert Référent Global du Domaine" in ds_md
    assert "Architecture & Plan Détaillé du Dossier (Généré par l'Agent Planificateur)" in ds_md
    assert "études faire et quels bacs privilégier" in ds_md
    assert "Cadre Général" not in ds_md

    learn_outline = providers.default_report_outline("Apprendre l'architecture Rust", learn_mode=True)
    assert len(learn_outline["parts"]) >= 7
    assert len(learn_outline["experts"]) == 1
    assert "Flashcard" in learn_outline["parts"][-1]["heading"]

    # Test Step 2 section writer message builder with the single reference expert
    base_ctx = [
        {"role": "system", "content": "Système Mode DeepSearch"},
        {"role": "user", "content": "Question initiale"},
    ]
    msg_part_0 = providers.build_section_writer_messages(
        base_context=base_ctx,
        query="Quelles études faire ?",
        outline=ds_outline,
        part_index=0,
        written_headings=[],
        previous_tail="",
        learn_mode=False,
    )
    assert "PARTIE 1/" in msg_part_0[-1]["content"]
    assert "EXPERT RÉFÉRENT DU DOMAINE" in msg_part_0[-1]["content"]
    assert "SYNTHÈSE EXÉCUTIVE D'OUVERTURE" in msg_part_0[-1]["content"]
    assert "STRUCTURE DE RÉDACTION UNIFIÉE" in msg_part_0[-1]["content"]
    assert ds_outline["parts"][0]["heading"] in msg_part_0[-1]["content"]

    msg_part_1 = providers.build_section_writer_messages(
        base_context=base_ctx,
        query="Quelles études faire ?",
        outline=ds_outline,
        part_index=1,
        written_headings=[ds_outline["parts"][0]["heading"]],
        previous_tail="Fin de la première partie rédigée avec chiffres [1].",
        learn_mode=False,
    )
    assert "PARTIE 2/" in msg_part_1[-1]["content"]
    assert "PARTIES DÉJÀ RÉDIGÉES PRÉCÉDEMMENT" in msg_part_1[-1]["content"]
    assert "Fin de la première partie rédigée" in msg_part_1[-1]["content"]
    assert ds_outline["parts"][1]["heading"] in msg_part_1[-1]["content"]


def test_learn_mode_source_intelligence_and_enrichment(monkeypatch):
    """Vérifie la parité du Mode Apprendre avec DeepSearch :
    - Classification universelle Tier A-E et scores de qualité
    - Résolution des sources primaires citées
    - Enrichissement textuel complet (enrich_top_sources_content)
    """
    from app import providers, source_filter, web
    from app.source_filter import extract_primary_source_citations, enrich_top_sources_content

    # 1. Test extraction des sources primaires citées dans un cours ou article secondaire
    sample_text = (
        "D'après les données de l'INSEE et selon un rapport de la DARES, "
        "l'insertion des diplômés a progressé selon le Céreq."
    )
    extracted = extract_primary_source_citations(sample_text)
    assert any("insee" in s.lower() for s in extracted)
    assert any("dares" in s.lower() for s in extracted)
    assert any("céreq" in s.lower() or "cereq" in s.lower() for s in extracted)

    # 2. Test enrichissement du contenu des top sources
    async def _run():
        class MockSettings:
            llm_api_key = "dummy"
            demo_mode = False

        sources = [
            {
                "title": "Rapport DARES 2026",
                "url": "https://dares.travail-emploi.gouv.fr/etude/metiers-2030",
                "snippet": "Chiffres d'insertion 2030...",
                "tier": "A",
                "quality_score": 95,
            },
            {
                "title": "Article Wikipedia",
                "url": "https://fr.wikipedia.org/wiki/Ing%C3%A9nierie",
                "snippet": "Définition de l'ingénierie...",
                "tier": "D",
                "quality_score": 60,
            },
        ]

        sample_content = (
            "Texte extrait du document officiel avec 4000 caractères de données vérifiables et détaillées sur l'insertion professionnelle, "
            "les salaires médians, les taux d'emploi à 12 et 24 mois pour les différentes filières et spécialités."
        )

        async def mock_fetch(url, timeout=4.0):
            return {
                "url": url,
                "title": "Page extraite",
                "text": sample_content,
            }

        monkeypatch.setattr(web, "fetch_and_parse_web_url", mock_fetch)

        await enrich_top_sources_content(MockSettings(), sources, limit=2)
        assert sources[0].get("content") == sample_content
        assert sources[1].get("content") == sample_content

    asyncio.run(_run())



