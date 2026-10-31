"""Tests unitaires pour la génération de présentations PowerPoint (slides 16:9)."""
from html.parser import HTMLParser
import pytest
from fastapi.testclient import TestClient

from app.presentation_html import (
    generate_chat_presentation_html,
    generate_presentation_html,
    generate_report_presentation_html,
    markdown_to_slides,
    _detect_kpis,
)


SOURCES_SAMPLE = [
    {"title": "Étude INSEE Emploi", "url": "https://www.insee.fr/fr/statistiques/123", "snippet": "Taux d'emploi en hausse de +4,2 %."},
    {"title": "Rapport DARES 2026", "url": "https://dares.travail-emploi.gouv.fr/rapport", "snippet": "Les créations nettes d'emplois atteignent 150 000 postes."},
]

SAMPLE_MD = """# L'Avenir du Travail à l'Horizon 2030

## 1. Contexte Macroéconomique
La transition écologique et l'intelligence artificielle redéfinissent les compétences requises.
Selon les prévisions, +35% des métiers vont intégrer des outils génératifs.

### Les défis de la formation
- Modernisation des cursus d'ingénieurs et techniciens.
- Accélération de l'apprentissage continu dans 90 % des entreprises.

## 2. Analyse des Métiers Émergents
De nouveaux métiers voient le jour dans la cybersécurité et l'énergie bas carbone.
L'insertion professionnelle atteint 94 % à 6 mois.

| Domaine | Croissance prévue | Recrutements annuels |
|---|---|---|
| IA & Data | +28 % | 45 000 |
| Énergies renouvelables | +32 % | 60 000 |

> "L'anticipation des compétences constitue le levier stratégique majeur de la décennie."

## 3. Synthèse et Recommandations
1. Investir massivement dans la requalification professionnelle.
2. Développer des partenariats université-entreprise.
3. Sécuriser les parcours professionnels des travailleurs exposés.
"""


def test_detect_kpis():
    text = "La croissance atteint +35% cette année avec un budget de 1,4 Md€ et une satisfaction de 94 %."
    kpis = _detect_kpis(text)
    assert len(kpis) >= 2
    values = [k["value"] for k in kpis]
    assert any("+35%" in v for v in values)
    assert any("1,4 Md€" in v for v in values) or any("94 %" in v for v in values)


def test_markdown_to_slides_structure():
    slides = markdown_to_slides(
        markdown_text=SAMPLE_MD,
        default_title="L'Avenir du Travail",
        topic="Analyse Prospective 2030",
        model="gpt-5-turbo",
        created_at_str="31/10/2026",
        sources=SOURCES_SAMPLE,
    )

    # 1. Plus de slides avec moins de texte par slide (règle d'or)
    assert len(slides) >= 8

    # 2. Couverture
    assert slides[0]["slide_type"] == "cover"
    assert slides[0]["title"] == "L'Avenir du Travail à l'Horizon 2030"
    assert slides[0]["model"] == "gpt-5-turbo"

    # 3. Sommaire / Ordre du jour
    assert slides[1]["slide_type"] == "agenda"
    assert "Ordre du jour" in slides[1]["title"] or "Sommaire" in slides[1]["title"]

    # 4. Formats variés : KPIs, puces courtes, cartes ou citations
    slide_types = [s["slide_type"] for s in slides]
    assert "kpi" in slide_types
    assert "bullets" in slide_types
    assert "conclusion" in slide_types

    # 5. Sources vérifiées
    sources_slides = [s for s in slides if s["slide_type"] == "sources"]
    assert len(sources_slides) == 1
    assert len(sources_slides[0]["sources"]) == 2


def test_generate_presentation_html_output():
    slides = markdown_to_slides(
        markdown_text=SAMPLE_MD,
        default_title="Test Titre",
        sources=SOURCES_SAMPLE,
    )
    html_output = generate_presentation_html(
        title="Présentation Stratégique",
        slides=slides,
        topic="Horizon 2030",
        model="Claude 3.7",
        created_at_str="31/10/2026",
    )

    assert "<!DOCTYPE html>" in html_output
    assert "data-theme=\"dark\"" in html_output
    assert "PresentationApp" in html_output
    assert "presentation-stage" in html_output
    assert "presentation-toolbar" in html_output
    assert "sorter-overlay" in html_output
    assert "@media print" in html_output
    assert "size: landscape" in html_output
    assert "Présentation Stratégique" in html_output


@pytest.mark.asyncio
async def test_generate_chat_presentation_html_turn_and_conversation():
    messages = [
        {"role": "user", "content": "Quelles sont les opportunités de l'IA en santé ?"},
        {"role": "assistant", "content": "## Diagnostic Médical\nL'IA permet d'améliorer la détection de pathologies de +40%.\n\n## Traitements personnalisés\nOptimisation des protocoles cliniques.", "sources": SOURCES_SAMPLE},
    ]

    # Turn scope
    html_turn = await generate_chat_presentation_html(
        title="IA en Santé",
        messages=messages,
        scope="turn",
        topic="Opportunités médicales",
        model="Gemini 2.5",
    )
    assert "<!DOCTYPE html>" in html_turn
    assert "PresentationApp" in html_turn
    assert "IA en Santé" in html_turn

    # Conversation scope
    html_conv = await generate_chat_presentation_html(
        title="Discussion Santé",
        messages=messages,
        scope="conversation",
        topic="Synthèse",
        model="Gemini 2.5",
        summary="Synthèse générale des échanges.",
    )
    assert "<!DOCTYPE html>" in html_conv
    assert "PresentationApp" in html_conv
    assert "Discussion Santé" in html_conv


@pytest.mark.asyncio
async def test_generate_report_presentation_html():
    html_report = await generate_report_presentation_html(
        title="Grand Rapport DeepSearch",
        markdown_content=SAMPLE_MD,
        topic="Travail 2030",
        model="Sonar Deep Research",
        sources=SOURCES_SAMPLE,
    )
    assert "<!DOCTYPE html>" in html_report
    assert "PresentationApp" in html_report
    assert "Grand Rapport DeepSearch" in html_report


def test_api_slides_endpoints(tmp_path):
    from app.config import Settings
    from app.main import create_app
    from app.models import Base, Conversation, Message, User
    from app.auth import hash_password
    from sqlalchemy import select

    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)
    app = create_app(settings)
    origin = settings.origins[0]
    Base.metadata.create_all(app.state.engine)

    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username == "slidestester"))
        if not user:
            user = User(username="slidestester", password_hash=hash_password("secretpass123"), is_admin=True)
            db.add(user)
            db.commit()
            db.refresh(user)

        conv = Conversation(user_id=user.id, title="Test Conversation Diaporama", model="demo-model")
        db.add(conv)
        db.commit()
        db.refresh(conv)

        m_user = Message(conversation_id=conv.id, role="user", content="Comment innover en 2026 ?")
        m_asst = Message(
            conversation_id=conv.id,
            role="assistant",
            content="## Axe 1 : Intelligence Artificielle\nL'IA progresse de +45%.\n\n## Axe 2 : Transition Écologique\nRéduction d'empreinte carbone.",
            sources=SOURCES_SAMPLE,
        )
        db.add_all([m_user, m_asst])
        db.commit()
        db.refresh(m_asst)
        msg_id = m_asst.id
        conv_id = conv.id

    with TestClient(app, base_url=origin, headers={"Origin": origin}) as client:
        # Connexion
        res_login = client.post("/api/auth/login", json={"username": "slidestester", "password": "secretpass123"})
        assert res_login.status_code == 200

        # 1. Slides de la conversation
        res_conv_slides = client.get(f"/api/conversations/{conv_id}/slides")
        assert res_conv_slides.status_code == 200
        assert "text/html" in res_conv_slides.headers.get("content-type", "")
        assert "PresentationApp" in res_conv_slides.text
        assert "Test Conversation Diaporama" in res_conv_slides.text

        # 2. Slides du message (Ce tour)
        res_msg_turn = client.get(f"/api/messages/{msg_id}/slides?scope=turn")
        assert res_msg_turn.status_code == 200
        assert "text/html" in res_msg_turn.headers.get("content-type", "")
        assert "Axe 1 : Intelligence Artificielle" in res_msg_turn.text

        # 3. Slides du message (Scope conversation)
        res_msg_conv = client.get(f"/api/messages/{msg_id}/slides?scope=conversation")
        assert res_msg_conv.status_code == 200
        assert "PresentationApp" in res_msg_conv.text

        # 4. Téléchargement avec header Attachment
        res_download = client.get(f"/api/messages/{msg_id}/slides?download=1")
        assert res_download.status_code == 200
        assert "attachment;" in res_download.headers.get("content-disposition", "")
        assert ".html" in res_download.headers.get("content-disposition", "")

