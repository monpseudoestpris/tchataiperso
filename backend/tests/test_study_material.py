import asyncio
import pytest
from app.config import Settings
from app.auth import hash_password
from app.main import create_app
from app.models import Base, Conversation, Message, User
from app.providers import fallback_study_material, generate_study_material
from fastapi.testclient import TestClient


def test_fallback_study_material_flashcards():
    transcript = (
        "Utilisateur : Parle-moi de Docker et des conteneurs.\n"
        "Assistant : Docker est une plateforme de conteneurisation.\n"
        "- **Conteneur :** Environnement d'exécution isolé et léger partageant le noyau de l'OS hôte.\n"
        "- **Image Docker :** Modèle en lecture seule contenant le code, les dépendances et la configuration.\n"
        "- **Dockerfile :** Fichier de recette décrivant les étapes pour assembler une image.\n"
    )
    result = fallback_study_material(
        transcript=transcript,
        kind="flashcards",
        count=5,
        difficulty="easy",
        topic="Docker & Conteneurs",
    )
    assert result["kind"] == "flashcards"
    assert result["count"] == 5
    assert result["difficulty"] == "easy"
    assert result["topic"] == "Docker & Conteneurs"
    assert len(result["flashcards"]) == 5
    assert len(result["questions"]) == 0
    # First card should be extracted from definitions
    first_card = result["flashcards"][0]
    assert "Conteneur" in first_card["recto"]
    assert "isolé" in first_card["verso"]
    assert first_card["id"] == 1


def test_fallback_study_material_quiz():
    transcript = (
        "Utilisateur : Comment fonctionne Git ?\n"
        "Assistant : Git est un gestionnaire de versions décentralisé.\n"
        "- **Commit :** Enregistrement instantané d'un ensemble de modifications dans le dépôt.\n"
        "- **Branche :** Pointeur mobile vers un commit permettant de travailler en isolation.\n"
    )
    result = fallback_study_material(
        transcript=transcript,
        kind="quiz",
        count=4,
        difficulty="hard",
        topic="Git & Versioning",
    )
    assert result["kind"] == "quiz"
    assert result["count"] == 4
    assert result["difficulty"] == "hard"
    assert len(result["questions"]) == 4
    assert len(result["flashcards"]) == 0

    first_q = result["questions"][0]
    assert "Commit" in first_q["question"]
    assert len(first_q["options"]) == 4
    assert 0 <= first_q["answer"] < 4
    assert len(first_q["explanation"]) > 10


@pytest.mark.asyncio
async def test_generate_study_material_demo_mode():
    settings = Settings(_env_file=None, demo_mode=True)
    res = await generate_study_material(
        settings=settings,
        transcript="Discussion sur la relativité restreinte",
        kind="flashcards",
        count=6,
        difficulty="medium",
        topic="Physique",
    )
    assert res["kind"] == "flashcards"
    assert len(res["flashcards"]) == 6
    assert res["count"] == 6


def test_study_material_api_endpoint(tmp_path):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/data.db",
        demo_mode=True,
    )
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)

    with app.state.sessions() as db:
        user = User(username="quiz_user", password_hash=hash_password("correct horse battery"), is_admin=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        conv = Conversation(user_id=user.id, title="Apprentissage Python", model="mistral-small-latest")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        # Empty conversation -> 422
        client = TestClient(app, base_url=origin, headers={"Origin": origin})
        # Authenticate
        login_res = client.post("/api/auth/login", json={"username": "quiz_user", "password": "correct horse battery"})
        assert login_res.status_code == 200

        res_empty = client.post(f"/api/conversations/{conv.id}/study", json={"kind": "flashcards", "count": 5})
        assert res_empty.status_code == 422

        # Add messages
        msg1 = Message(conversation_id=conv.id, role="user", content="Comment fonctionnent les list comprehensions en Python ?")
        msg2 = Message(
            conversation_id=conv.id,
            role="assistant",
            content=(
                "Les list comprehensions permettent de construire une liste de manière concise.\n"
                "- **List comprehension :** Syntaxe concise `[expr for item in iterable if condition]`.\n"
                "- **Générateur :** Évaluation paresseuse économe en mémoire utilisant des parenthèses."
            ),
        )
        db.add_all([msg1, msg2])
        db.commit()

        # Test flashcards generation
        res_flash = client.post(
            f"/api/conversations/{conv.id}/study",
            json={"kind": "flashcards", "count": 5, "difficulty": "easy", "topic": "Python Comprehensions"},
        )
        assert res_flash.status_code == 200
        flash_data = res_flash.json()
        assert flash_data["kind"] == "flashcards"
        assert flash_data["count"] == 5
        assert flash_data["difficulty"] == "easy"
        assert len(flash_data["flashcards"]) == 5
        assert len(flash_data["questions"]) == 0

        # Test quiz generation
        res_quiz = client.post(
            f"/api/conversations/{conv.id}/study",
            json={"kind": "quiz", "count": 6, "difficulty": "medium"},
        )
        assert res_quiz.status_code == 200
        quiz_data = res_quiz.json()
        assert quiz_data["kind"] == "quiz"
        assert quiz_data["count"] == 6
        assert len(quiz_data["questions"]) == 6
        assert len(quiz_data["questions"][0]["options"]) == 4
