import json
import logging
import re
from typing import Any
import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import TopicEvent, TopicMemory, TopicSpace, now

_logger = logging.getLogger("uvicorn.error")

TOPIC_STATUS_LABELS = {
    "validated": "Validé",
    "provisional_mastery": "Acquis provisoire",
    "in_progress": "En cours",
    "needs_review": "À renforcer / corriger",
    "discussed": "Abordé",
}


def build_topic_prompt_context(topic: TopicSpace, memories: list[TopicMemory]) -> str:
    """Builds a concise, highly relevant context block to inject into the assistant's context."""
    lines = [
        f"=== ESPACE THÉMATIQUE ACTIF : {topic.icon} {topic.title} (Type : {topic.topic_type}) ===",
    ]
    if topic.objective:
        lines.append(f"Objectif : {topic.objective}")
    if topic.current_resume_context:
        lines.append(f"Point de reprise : {topic.current_resume_context}")
    if topic.suggested_next_step:
        lines.append(f"Prochaine étape recommandée : {topic.suggested_next_step}")

    active_memories = [m for m in memories if not m.is_archived]
    if active_memories:
        lines.append("\nAcquis, statut et mémoire persistante de l'espace :")
        for mem in active_memories[:25]:
            status_label = TOPIC_STATUS_LABELS.get(mem.status, mem.status)
            lines.append(f"- [{status_label}] {mem.fact}")

    resources = getattr(topic, "resources", [])
    if resources:
        lines.append("\nRessources et documents clés du sujet :")
        for res in resources[:10]:
            target = f" ({res.url})" if res.url else ""
            desc = f" : {res.content[:120]}" if res.content else ""
            lines.append(f"- [{res.resource_type.upper()}] {res.title}{target}{desc}")

    lines.append(
        "\nDirective didactique et de continuité :\n"
        "Tu es l'accompagnateur de l'utilisateur sur cet espace durable. "
        "Appuie-toi fidèlement sur ses progrès, ses difficultés identifiées et ses acquis sans le faire repartir de zéro."
    )
    return "\n".join(lines)


TOPIC_ANALYZER_PROMPT = """Tu es un agent d'analyse et de suivi de continuité pour un espace thématique utilisateur (apprentissage, projet, centre d'intérêt, dossier personnel).
Ton rôle est d'analyser le tour de conversation récent et de produire une synthèse de suivi actualisée.

Données d'entrée (JSON) :
- topic_title : titre de l'espace
- topic_type : type ("learning", "project", "interest", "personal")
- objective : objectif durable de l'espace
- current_resume_context : résumé de l'état précédent
- existing_memories : liste des souvenirs/acquis existants [{"id": "...", "fact": "...", "status": "..."}]
- user_message : message de l'utilisateur
- assistant_message : réponse de l'assistant

Règles impératives :
1. "new_resume_context" : Rédige 1 à 3 phrases concrètes décrivant où en est l'utilisateur après ce tour (ce qui a été fait, difficultés ou décisions).
2. "suggested_next_step" : Rédige 1 phrase concise sur l'action suivante recommandée pour progresser dans l'espace.
3. "add_memories" : Extrais de nouveaux faits durables, compétences, décisions ou notions abordées sous forme atomique :
   - fact : phrase concise et autonome (ex. "Distingue ser et estar pour les descriptions physiques", "Choix d'architecture : SQLite pour la persistance locale").
   - category : "grammar", "vocabulary", "decision", "task", "concept", "preference" ou "general".
   - status :
     * "discussed" si la notion a simplement été abordée ou expliquée par l'assistant.
     * "in_progress" si l'utilisateur y travaille activement.
     * "provisional_mastery" si l'utilisateur a réussi un exercice ou montré une bonne compréhension.
     * "needs_review" si une erreur, hésitation ou confusion est apparue.
     * "validated" si la compétence est pleinement maîtrisée ou validée formellement.
4. "update_memories" : Si un souvenir existant change de statut suite aux échanges (ex. passe de "needs_review" à "provisional_mastery"), fournis son id et son nouveau status.
5. "events" : Si un événement notable a eu lieu (exercice noté, quiz, décision de projet majeure), crée un événement :
   - event_type : "exercise_result", "decision_taken", "milestone", "session_recap"
   - title : intitulé court (ex. "Exercice conjugaison présent", "Validation modèle de données")
   - details : dictionnaire avec les données clés (ex. {"score": "7/8", "theme": "SER/ESTAR"})

Format de sortie STRICT : JSON pur sans markdown :
{
  "new_resume_context": "...",
  "suggested_next_step": "...",
  "add_memories": [{"fact": "...", "category": "...", "status": "..."}],
  "update_memories": [{"id": "...", "status": "...", "fact": "..."}],
  "events": [{"event_type": "...", "title": "...", "details": {...}}]
}
"""


def fallback_topic_analysis(
    topic: TopicSpace,
    user_text: str,
    assistant_text: str,
) -> dict[str, Any]:
    """Lightweight rule-based fallback when model is unavailable."""
    clean_user = user_text.strip()
    clean_asst = assistant_text.strip()
    preview = clean_user[:80] + ("..." if len(clean_user) > 80 else "")

    new_resume = f"Dernière discussion sur : « {preview} »."
    suggested_step = "Poursuivre l'approfondissement sur ce point ou aborder une notion complémentaire."

    events = []
    # Check for exercise score pattern like 7/8 or 18/20
    score_match = re.search(r"(\d+)\s*/\s*(\d+)", clean_user + " " + clean_asst)
    if score_match:
        events.append({
            "event_type": "exercise_result",
            "title": f"Exercice ({score_match.group(1)}/{score_match.group(2)})",
            "details": {"score": f"{score_match.group(1)}/{score_match.group(2)}"},
        })

    return {
        "new_resume_context": new_resume,
        "suggested_next_step": suggested_step,
        "add_memories": [],
        "update_memories": [],
        "events": events,
    }


async def process_topic_turn(
    sessions: sessionmaker,
    topic_space_id: str,
    user_message: str,
    assistant_message: str,
    settings: Settings,
) -> dict[str, Any]:
    """Analyzes a message turn inside a topic space to update memory, resume context, and events."""
    with sessions() as db:
        topic = db.scalar(
            select(TopicSpace).where(TopicSpace.id == topic_space_id)
        )
        if not topic:
            return {}

        memories = list(
            db.scalars(
                select(TopicMemory)
                .where(TopicMemory.topic_space_id == topic.id, TopicMemory.is_archived.is_(False))
            )
        )
        existing_memories_data = [
            {"id": m.id, "fact": m.fact, "status": m.status, "category": m.category}
            for m in memories
        ]
        topic_title = topic.title
        topic_type = topic.topic_type
        objective = topic.objective
        current_resume = topic.current_resume_context

    analysis: dict[str, Any] = {}
    api_key = settings.openrouter_api_key or ""

    if api_key:
        model = settings.default_model
        payload_data = {
            "topic_title": topic_title,
            "topic_type": topic_type,
            "objective": objective,
            "current_resume_context": current_resume,
            "existing_memories": existing_memories_data,
            "user_message": user_message[:2000],
            "assistant_message": assistant_message[:3000],
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://clair.local",
                        "X-Title": "cLAIr Topic Memory Agent",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": TOPIC_ANALYZER_PROMPT},
                            {"role": "user", "content": json.dumps(payload_data, ensure_ascii=False)},
                        ],
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                    },
                )
                if res.status_code == 200:
                    raw_text = res.json()["choices"][0]["message"]["content"]
                    analysis = json.loads(raw_text)
        except Exception as exc:
            _logger.warning("Topic agent LLM analysis failed: %s; using fallback.", exc)

    if not analysis or not isinstance(analysis, dict):
        with sessions() as db:
            topic = db.scalar(select(TopicSpace).where(TopicSpace.id == topic_space_id))
            if topic:
                analysis = fallback_topic_analysis(topic, user_message, assistant_message)
            else:
                return {}

    # Apply analysis to database
    with sessions() as db:
        topic = db.scalar(select(TopicSpace).where(TopicSpace.id == topic_space_id))
        if not topic:
            return {}

        new_resume = analysis.get("new_resume_context")
        if new_resume and isinstance(new_resume, str):
            topic.current_resume_context = new_resume.strip()

        next_step = analysis.get("suggested_next_step")
        if next_step and isinstance(next_step, str):
            topic.suggested_next_step = next_step.strip()

        # Add new memories
        added_memories = []
        for item in analysis.get("add_memories", []):
            if not isinstance(item, dict) or not item.get("fact"):
                continue
            fact_text = item["fact"].strip()
            # Simple deduplication against existing
            already_exists = any(
                m.fact.strip().lower() == fact_text.lower() for m in topic.memories
            )
            if not already_exists:
                new_mem = TopicMemory(
                    topic_space_id=topic.id,
                    fact=fact_text,
                    category=item.get("category", "general")[:50],
                    status=item.get("status", "discussed")[:30],
                    confidence=float(item.get("confidence", 1.0)),
                    user_verified=False,
                )
                db.add(new_mem)
                added_memories.append({"fact": fact_text, "status": new_mem.status, "category": new_mem.category})

        analysis["added_memories"] = added_memories
        analysis["topic_title"] = topic.title
        analysis["topic_icon"] = topic.icon or "📌"

        # Update existing memories status
        for item in analysis.get("update_memories", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            mem_to_update = db.scalar(
                select(TopicMemory).where(
                    TopicMemory.id == item["id"], TopicMemory.topic_space_id == topic.id
                )
            )
            if mem_to_update:
                if item.get("status"):
                    mem_to_update.status = item["status"][:30]
                if item.get("fact"):
                    mem_to_update.fact = item["fact"].strip()
                mem_to_update.updated_at = now()

        # Add events
        for ev in analysis.get("events", []):
            if not isinstance(ev, dict) or not ev.get("title"):
                continue
            new_event = TopicEvent(
                topic_space_id=topic.id,
                event_type=ev.get("event_type", "session_recap")[:40],
                title=ev["title"].strip()[:200],
                details=ev.get("details", {}) if isinstance(ev.get("details"), dict) else {},
            )
            db.add(new_event)

        topic.updated_at = now()
        db.commit()

    return analysis

