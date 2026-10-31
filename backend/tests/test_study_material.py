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

        # Test cloze generation
        res_cloze = client.post(
            f"/api/conversations/{conv.id}/study",
            json={"kind": "cloze", "count": 5, "difficulty": "medium"},
        )
        assert res_cloze.status_code == 200
        cloze_data = res_cloze.json()
        assert cloze_data["kind"] == "cloze"
        assert len(cloze_data["cloze_items"]) == 5
        assert len(cloze_data["cloze_items"][0]["missing_words"]) >= 1

        # Test direct course_text study endpoint
        course_sample = (
            "# Cours d'Architecture Réseau\n\n"
            "- **Routeur :** Équipement réseau qui achemine les paquets IP entre plusieurs réseaux distincts.\n"
            "- **Switch :** Commutateur réseau qui relie des équipements au sein d'un même réseau local (LAN).\n"
            "- **DNS :** Système de noms de domaine traduisant les adresses IP en noms lisibles."
        )
        res_direct = client.post(
            "/api/study/generate",
            json={"kind": "all", "count": 3, "course_text": course_sample},
        )
        assert res_direct.status_code == 200
        direct_data = res_direct.json()
        assert direct_data["kind"] == "all"
        assert len(direct_data["flashcards"]) == 3
        assert len(direct_data["questions"]) == 3
        assert len(direct_data["cloze_items"]) == 3
        assert "Routeur" in direct_data["topic"] or "Réseau" in direct_data["topic"]


def test_study_material_no_generic_methodology_on_vectors_course():
    vectors_transcript = (
        "Un vecteur, pour faire simple, c'est un outil mathématique qui possède trois caractéristiques :\n"
        "1. **Une direction** (la droite selon laquelle il s'exerce, et ses parallèles).\n"
        "2. **Un sens** (de A vers B, ou de B vers A).\n"
        "3. **Une norme** (sa longueur, ou la distance entre son origine et son extrémité).\n\n"
        "### 1. Notation et égalité\n"
        "Deux vecteurs $\\vec{u}$ et $\\vec{v}$ sont **égaux** s'ils ont la même direction, le même sens et la même norme. "
        "Si $\\vec{AB} = \\vec{CD}$, alors le quadrilatère $ABDC$ est un parallélogramme.\n\n"
        "### 2. Addition de vecteurs et relation de Chasles\n"
        "La star absolue de ce chapitre, c'est la **relation de Chasles**. Pour n'importe quels points $A$, $B$ et $C$ du plan :\n"
        "$$\\vec{AB} + \\vec{BC} = \\vec{AC}$$\n\n"
        "### 3. Multiplication par un réel\n"
        "* Sa direction reste la même (les vecteurs $\\vec{u}$ et $k\\vec{u}$ sont **colinéaires**).\n"
        "* Sa longueur est multipliée par $|k|$ (la valeur absolue de $k$).\n"
        "* Son sens est conservé si $k > 0$, et inversé si $k < 0$.\n"
        "Deux droites $(AB)$ et $(CD)$ sont parallèles si et seulement si les vecteurs $\\vec{AB}$ et $\\vec{CD}$ sont colinéaires.\n\n"
        "### 4. Coordonnées dans un repère\n"
        "* Les coordonnées du vecteur $\\vec{AB}$ se calculent ainsi : $\\vec{AB} (x_B - x_A ; y_B - y_A)$\n"
        "* Pour additionner deux vecteurs en coordonnées, on additionne leurs abscisses entre elles et leurs ordonnées entre elles.\n"
        "* Pour multiplier par un réel $k$, on multiplie chaque coordonnée par $k$.\n"
    )

    res = fallback_study_material(
        transcript=vectors_transcript,
        kind="all",
        count=10,
        difficulty="medium",
        topic="Révision des vecteurs mathématiques niveau seconde",
    )

    assert len(res["flashcards"]) == 10
    assert len(res["questions"]) == 10
    assert len(res["cloze_items"]) == 10

    # Ensure NO card contains generic meta-methodology questions
    for card in res["flashcards"]:
        recto = card["recto"].lower()
        verso = card["verso"].lower()
        assert "piège ou l'erreur courante" not in recto
        assert "première démarche recommandée" not in recto
        assert "règle cardinale à respecter" not in recto
        assert "quel est l'objectif premier" not in recto
        assert "comment s'organiser" not in recto
        assert "se précipiter sur une solution superficielle" not in verso

    # Check that real vector concepts are present across the cards
    all_rectos = " ".join([c["recto"] for c in res["flashcards"]])
    assert "direction" in all_rectos.lower() or "sens" in all_rectos.lower() or "norme" in all_rectos.lower()
    assert "Chasles" in all_rectos or "égaux" in all_rectos or "colinéaires" in all_rectos or "Notation" in all_rectos

    # Ensure NO quiz question contains generic meta-methodology
    for q in res["questions"]:
        q_text = q["question"].lower()
        assert "finalité principale" not in q_text
        assert "piège fréquent" not in q_text
        assert "face à une difficulté" not in q_text

