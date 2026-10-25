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

