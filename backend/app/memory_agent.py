import json
import logging
import re
from typing import Any
import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .models import Memory, now
from .serializers import stamp

_logger = logging.getLogger("uvicorn.error")

_EXPLICIT_ADD_PATTERNS = [
    r"(?:peux-tu\s+|pourrais-tu\s+|veuillez\s+|merci\s+de\s+|tu\s+peux\s+)?(?:noter?|garder?|retiens?|retenir|mets?|mettre|ajouter?|enregistrer?|inscrire?|mémoriser?)\s+(?:dans\s+(?:ma\s+|la\s+)?mémoire|en\s+mémoire|à\s+(?:ma\s+|la\s+)?mémoire)\s*(?:que|qu'|:|d'|de)?\s*(.+)",
    r"(?:peux-tu\s+|pourrais-tu\s+|veuillez\s+|merci\s+de\s+|tu\s+peux\s+)?(?:noter?|garder?|retiens?|retenir|mets?|mettre|enregistrer?|mémoriser?)\s+(?:en\s+mémoire\s+)?(?:que|qu'|:)\s*(.+)",
    r"(?:souviens[- ]toi|rappelle[- ]toi)\s*(?:que|qu'|de|d'|:)?\s*(.+)",
]

_EXPLICIT_DELETE_PATTERNS = [
    r"(?:peux-tu\s+|pourrais-tu\s+|veuillez\s+|merci\s+de\s+|tu\s+peux\s+)?(?:oublie|oublier|efface|effacer|supprime|supprimer|retire|retirer)\s+(?:de\s+(?:ma\s+|la\s+)?mémoire\s+)?(?:que|qu'|:|d'|de)?\s*(.+)",
]

MEMORY_AGENT_PROMPT = """Tu es un agent expert en gestion de la mémoire à long terme pour un assistant personnel IA.
Ton rôle est d'analyser le tour de conversation récent et de décider quels souvenirs enregistrer ou supprimer dans la mémoire durable de l'utilisateur.

Données d'entrée (JSON) :
- user_message : le message récent de l'utilisateur.
- assistant_message : la réponse de l'assistant.
- existing_memories : liste des souvenirs déjà enregistrés pour cet utilisateur ([{"id": "...", "content": "..."}]).
- auto_memory_enabled : booléen indiquant si la capture autonome de souvenirs est active.

Règles impératives de décision :

1. DEMANDES EXPLICITES DE L'UTILISATEUR (Priorité absolue) :
   - Si l'utilisateur demande explicitement d'enregistrer, noter, retenir ou mémoriser (« note en mémoire que... », « retiens que... », « souviens-toi que... », « garde en mémoire : ... », « ajoute à ma mémoire », etc.) :
     -> Tu DOIS formuler ce fait atomique et l'ajouter à "add".
   - Si l'utilisateur demande d'oublier ou supprimer un souvenir (« oublie que... », « supprime de ma mémoire... », « efface ce souvenir ») :
     -> Identifie l'identifiant (id) du souvenir correspondant dans existing_memories et ajoute-le à "delete_ids".

2. DÉTECTION AUTONOME DE SOUVENIRS (si auto_memory_enabled = true) :
   L'agent décide intelligemment de son propre chef quoi retenir pour personnaliser et enrichir les échanges futurs :
   ✅ À RETENIR :
   - Identité & profil : prénom, âge, profession, lieu de résidence / ville, animaux de compagnie, situation familiale.
   - Préférences durables : langages ou frameworks préférés (ex. Python, Rust, React), style de réponse souhaité (ex. concis, sans bavardage), centres d'intérêt majeurs.
   - Contraintes fortes & santé : allergies, intolérances, régimes spécifiques (végétarien, sans gluten), restrictions physiques ou horaires récurrentes.
   - Projets de long terme : préparation d'un concours, marathon, création d'une entreprise.
   ❌ À NE JAMAIS RETENIR (bruit & éphémère) :
   - Tâches ponctuelles (« traduis ce texte », « résume ce PDF », « écris un script bash »).
   - États émotionnels ou météos passagers (« il fait beau », « j'ai faim », « je suis fatigué ce soir »).
   - Questions encyclopédiques générales (« qui est Victor Hugo ? », « comment marche un transformateur ? »).
   - Politesse courante (« merci beaucoup », « bonjour », « super explication »).

3. DÉDOUBLONNAGE ET FORMULATION STRICTE :
   - NE JAMAIS ajouter un fait déjà présent ou redondant avec existing_memories.
   - Si une nouvelle information met à jour un souvenir existant (ex. : déménagement, changement de langage favori) :
     -> Mets l'ancien id dans "delete_ids" et le nouveau fait dans "add".
   - Rédige chaque fait dans "add" à la 3e personne en français, sous forme d'une phrase atomique, concise et autonome (5 à 20 mots).
     Exemples :
     - « Vit à Lyon »
     - « Développe principalement en TypeScript et Python »
     - « Régime végétarien strict »
     - « Prépare le marathon de Paris 2027 »
     - « Préfère des réponses directes et synthétiques sans fioritures »

Format de sortie :
Retourne STRICTEMENT un objet JSON valide sans Markdown ni texte d'accompagnement :
{
  "add": ["fait 1", ...],
  "delete_ids": ["id_du_souvenir_a_supprimer", ...]
}
Si rien ne doit être ajouté ni supprimé, retourne : {"add": [], "delete_ids": []}
"""


def _normalize_fact(text: str) -> str:
    cleaned = re.sub(r'^(?:je\s+suis|j\x27ai|j\x27habite\s+à|je\s+vis\s+à|mon\s+nom\s+est|je\s+m\x27appelle)\s+', '', text.strip(), flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .:,;!?\"'«»")
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _is_similar_fact(fact: str, existing_contents: list[str]) -> bool:
    norm_fact = re.sub(r'[^a-z0-9]', '', fact.lower())
    for existing in existing_contents:
        norm_ex = re.sub(r'[^a-z0-9]', '', existing.lower())
        if norm_fact == norm_ex:
            return True
        if len(norm_fact) > 8 and (norm_fact in norm_ex or norm_ex in norm_fact):
            return True
    return False


def fallback_memory_analysis(
    user_text: str,
    existing_memories: list[dict[str, str]],
    auto_memory_enabled: bool = True,
) -> dict[str, list[str]]:
    """Rule-based fallback for explicit memory requests and basic profile detection."""
    add_list: list[str] = []
    delete_ids: list[str] = []
    text = (user_text or "").strip()
    if not text:
        return {"add": [], "delete_ids": []}

    existing_contents = [m["content"] for m in existing_memories if "content" in m]

    # Check explicit deletion
    for pat in _EXPLICIT_DELETE_PATTERNS:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            target = match.group(1).strip().lower()
            target_norm = re.sub(r'[^a-z0-9]', '', target)
            for m in existing_memories:
                m_content_norm = re.sub(r'[^a-z0-9]', '', m.get("content", "").lower())
                if target_norm and (target_norm in m_content_norm or m_content_norm in target_norm):
                    delete_ids.append(m["id"])
            if delete_ids:
                return {"add": [], "delete_ids": delete_ids}

    # Check explicit addition
    for pat in _EXPLICIT_ADD_PATTERNS:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw_fact = match.group(1).strip()
            # Clean up trailing instructions or periods
            raw_fact = re.split(r'(?:\.\s|\n)', raw_fact)[0].strip(" .:,;!?\"'«»")
            if len(raw_fact) >= 3:
                # Basic 1st person to 3rd person conversions
                fact = re.sub(r"^(?:j'adore|j'aime)\s+", "Aime ", raw_fact, flags=re.IGNORECASE)
                fact = re.sub(r"^je\s+vis\s+à\s+", "Vit à ", fact, flags=re.IGNORECASE)
                fact = re.sub(r"^j'habite\s+à\s+", "Habite à ", fact, flags=re.IGNORECASE)
                fact = re.sub(r"^je\s+suis\s+", "", fact, flags=re.IGNORECASE)
                fact = re.sub(r"^je\s+travaille\s+chez\s+", "Travaille chez ", fact, flags=re.IGNORECASE)
                fact = re.sub(r"^je\s+code\s+en\s+", "Développe en ", fact, flags=re.IGNORECASE)
                fact = re.sub(r"^je\s+m'appelle\s+", "S'appelle ", fact, flags=re.IGNORECASE)
                fact = re.sub(r"^mon\s+anniversaire\s+est\s+(?:le\s+)?", "Anniversaire le ", fact, flags=re.IGNORECASE)
                fact = fact.strip(" .:,;!?\"'«»")
                if fact:
                    formatted = fact[0].upper() + fact[1:]
                    if not _is_similar_fact(formatted, existing_contents):
                        add_list.append(formatted)
            return {"add": add_list, "delete_ids": delete_ids}

    # If autonomous memory is enabled, check common high-confidence facts
    if auto_memory_enabled:
        auto_patterns = [
            (r"\bje\s+m'appelle\s+([A-ZÀ-Ÿ][a-zà-ÿ]+(?:\s+[A-ZÀ-Ÿ][a-zà-ÿ]+)?)\b", "S'appelle {0}"),
            (r"\bj'habite\s+à\s+([A-ZÀ-Ÿ][a-zà-ÿ\-]+)\b", "Habite à {0}"),
            (r"\bje\s+vis\s+à\s+([A-ZÀ-Ÿ][a-zà-ÿ\-]+)\b", "Vit à {0}"),
            (r"\bje\s+suis\s+végétar(?:ien|ienne)\b", "Régime végétarien"),
            (r"\bje\s+suis\s+végan(?:e)?\b", "Régime végan"),
            (r"\bje\s+suis\s+allergique\s+(?:à|au|aux)\s+([a-zA-ZÀ-ÿ\s]+?)(?:\.|$|,|\s+et\s+)", "Allergique à {0}"),
        ]
        for pat, template in auto_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                if "{0}" in template:
                    captured = m.group(1).strip()
                    cand = template.format(captured)
                else:
                    cand = template
                cand = cand[0].upper() + cand[1:]
                if not _is_similar_fact(cand, existing_contents) and cand not in add_list:
                    add_list.append(cand)

    return {"add": add_list, "delete_ids": delete_ids}


async def analyze_memories_with_agent(
    settings: Settings,
    user_text: str,
    assistant_text: str,
    existing_memories: list[dict[str, str]],
    auto_memory_enabled: bool = True,
) -> dict[str, list[str]]:
    """Analyze the user turn with an auxiliary LLM to detect memories to store or delete."""
    key = settings.llm_api_key.get_secret_value() if hasattr(settings.llm_api_key, "get_secret_value") else str(settings.llm_api_key)
    if not key or settings.demo_mode:
        return fallback_memory_analysis(user_text, existing_memories, auto_memory_enabled=auto_memory_enabled)

    model = getattr(settings, "memory_agent_model", None) or getattr(settings, "web_search_decision_model", None) or getattr(settings, "search_query_model", "google/gemini-3.5-flash-lite")

    payload_data = {
        "user_message": (user_text or "")[:1500],
        "assistant_message": (assistant_text or "")[:1000],
        "existing_memories": [{"id": m.get("id"), "content": m.get("content")} for m in existing_memories[:100]],
        "auto_memory_enabled": bool(auto_memory_enabled),
    }

    messages = [
        {"role": "system", "content": MEMORY_AGENT_PROMPT},
        {"role": "user", "content": json.dumps(payload_data, ensure_ascii=False)},
    ]

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.1,
                    "max_tokens": 400,
                },
            )
            if resp.status_code in (400, 404, 422):
                alt_model = getattr(settings, "default_model", "mistralai/mistral-small-3.2-24b-instruct")
                if alt_model and alt_model != model:
                    resp = await client.post(
                        settings.llm_base_url.rstrip("/") + "/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={
                            "model": alt_model,
                            "messages": messages,
                            "stream": False,
                            "temperature": 0.1,
                            "max_tokens": 400,
                        },
                    )
            if resp.status_code >= 400:
                _logger.warning("Échec HTTP agent mémoire (%s): %s", resp.status_code, resp.text[:200])
                return fallback_memory_analysis(user_text, existing_memories, auto_memory_enabled=auto_memory_enabled)

            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content.strip(), flags=re.IGNORECASE | re.DOTALL).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                add_items = [str(item).strip() for item in parsed.get("add", []) if str(item).strip()]
                del_ids = [str(item).strip() for item in parsed.get("delete_ids", []) if str(item).strip()]
                return {"add": add_items, "delete_ids": del_ids}
    except Exception as exc:
        _logger.warning("Erreur lors de l'exécution de l'agent mémoire: %s ; bascule sur repli local", exc)

    return fallback_memory_analysis(user_text, existing_memories, auto_memory_enabled=auto_memory_enabled)


async def process_memory_turn(
    settings: Settings,
    sessions: sessionmaker,
    user_id: str,
    user_text: str,
    assistant_text: str,
    auto_memory_enabled: bool = True,
) -> dict[str, Any]:
    """Execute the memory agent, apply DB mutations, and return updated & newly added memories."""
    with sessions() as db:
        existing_items = list(db.scalars(
            select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at)
        ))
        existing_memories = [{"id": m.id, "content": m.content, "created_at": stamp(m.created_at)} for m in existing_items]
        existing_ids = {m["id"] for m in existing_memories}

    decision = await analyze_memories_with_agent(
        settings=settings,
        user_text=user_text,
        assistant_text=assistant_text,
        existing_memories=existing_memories,
        auto_memory_enabled=auto_memory_enabled,
    )

    to_delete = [item_id for item_id in decision.get("delete_ids", []) if item_id in existing_ids]
    to_add = [fact.strip() for fact in decision.get("add", []) if fact.strip()]

    newly_added: list[str] = []
    deleted_ids: list[str] = []

    if to_delete or to_add:
        with sessions() as db:
            if to_delete:
                db.execute(delete(Memory).where(Memory.id.in_(to_delete), Memory.user_id == user_id))
                deleted_ids = to_delete

            current_count = len(existing_memories) - len(deleted_ids)
            current_contents = [m["content"] for m in existing_memories if m["id"] not in deleted_ids]

            for raw_fact in to_add:
                fact = raw_fact[:500].strip()
                if len(fact) < 3:
                    continue
                if current_count >= 100:
                    break
                if _is_similar_fact(fact, current_contents):
                    continue

                item = Memory(user_id=user_id, content=fact)
                db.add(item)
                current_contents.append(fact)
                newly_added.append(fact)
                current_count += 1

            db.commit()

            # Refresh all memories from database
            fresh_items = list(db.scalars(
                select(Memory).where(Memory.user_id == user_id).order_by(Memory.created_at)
            ))
            all_memories = [{"id": m.id, "content": m.content, "created_at": stamp(m.created_at)} for m in fresh_items]
    else:
        all_memories = existing_memories

    return {
        "new_memories": newly_added,
        "deleted_memories": deleted_ids,
        "all_memories": all_memories,
    }

