import logging
from typing import Any

from .config import Settings
from .documents import extraction_text
from .token_counter import count_message_tokens, count_tokens

logger = logging.getLogger("clair.chat_memory")


def get_model_context_limit(settings: Settings, model_info: dict | None = None) -> int:
    """Détermine la limite maximale de contexte en tokens pour la conversation.

    Utilise CONTEXT_WINDOW_TOKENS comme plafond pour la conversation, borné par
    la capacité maximale du modèle si celle-ci est plus restreinte.
    """
    app_limit = max(2000, settings.context_window_tokens)
    if model_info:
        raw_ctx = model_info.get("context_length")
        if isinstance(raw_ctx, (int, float)) and raw_ctx > 0:
            return min(int(raw_ctx), app_limit)
    return app_limit


def evaluate_context_compression(
    history: list[Any],
    summary_through: int,
    current_summary: str,
    limit_tokens: int,
    settings: Settings,
    other_tokens: int = 0,
) -> tuple[bool, int, str]:
    """Évalue si la fenêtre de contexte dépasse le seuil haut (ex. 80 % de la limite max).

    Règles :
    1. Déclenchement par taille de contexte en tokens (jamais les messages).
       Tant que total_tokens < 80 % de la limite max, on ne touche à rien pour préserver le KV Cache.
    2. Fenêtre glissante intacte :
       On conserve toujours intacts les derniers milliers de tokens récents (mot pour mot).
    3. Compression par bloc :
       Dès que le seuil de 80 % est atteint, on prend la première moitié des messages les plus anciens
       compressibles et on les extrait dans un bloc à résumer pour redescendre vers ~40 % d'occupation.

    Retourne : (should_summarize, new_summary_cutoff, transcript)
    """
    total_messages = len(history)
    if summary_through >= total_messages:
        return False, summary_through, ""

    unsummarized = history[summary_through:]
    if not unsummarized:
        return False, summary_through, ""

    # Calcul des tokens de chaque message non résumé
    message_costs: list[int] = []
    for item in unsummarized:
        role = getattr(item, "role", "user") if hasattr(item, "role") else item.get("role", "user")
        content = getattr(item, "content", "") if hasattr(item, "content") else item.get("content", "")
        attachments = getattr(item, "attachments", []) if hasattr(item, "attachments") else item.get("attachments", [])
        cost = count_message_tokens(role, content, attachments)
        message_costs.append(cost)

    summary_tokens = count_tokens(current_summary) if current_summary else 0
    history_tokens = sum(message_costs)
    total_tokens = other_tokens + summary_tokens + history_tokens

    high_watermark = int(limit_tokens * settings.summary_trigger_ratio)

    # 1. Sous le seuil haut : préservation totale du KV Cache
    if total_tokens < high_watermark:
        return False, summary_through, ""

    # 2. Fenêtre glissante intacte : préserver les derniers milliers de tokens récents
    # On parcourt les messages depuis la fin vers l'arrière
    recent_tokens = 0
    preserved_count = 0
    min_recent_tokens = settings.summary_min_recent_tokens
    min_recent_turns = 2  # Conserver au minimum les 2 derniers messages bruts si possible

    for cost in reversed(message_costs):
        if recent_tokens >= min_recent_tokens and preserved_count >= min_recent_turns:
            break
        recent_tokens += cost
        preserved_count += 1

    # Indice maximum compressible dans l'historique non résumé
    # On ne doit jamais toucher aux 'preserved_count' messages les plus récents
    compressible_count = len(unsummarized) - preserved_count

    # Si tous les messages sont couverts par la fenêtre glissante mais qu'on dépasse le seuil,
    # on préserve au moins le dernier message actif (tour actuel)
    if compressible_count <= 0:
        if len(unsummarized) > 1:
            compressible_count = len(unsummarized) - 1
        else:
            # Un seul message énorme dépasse à lui seul le seuil : pas de messages antérieurs à résumer
            return False, summary_through, ""

    # 3. Compression par bloc : Dès que le seuil de 80 % est atteint, on prend la première
    # moitié des messages les plus anciens compressibles pour redescendre à ~40 % d'occupation
    block_count = max(1, compressible_count // 2)
    summary_cutoff = summary_through + block_count

    # Construction de la transcription du bloc à résumer
    transcript_parts: list[str] = []
    for item in history[summary_through:summary_cutoff]:
        role = getattr(item, "role", "user") if hasattr(item, "role") else item.get("role", "user")
        content = getattr(item, "content", "") if hasattr(item, "content") else item.get("content", "")
        item_text = f"{role}: {content[:4000]}"
        attachments = getattr(item, "attachments", []) if hasattr(item, "attachments") else item.get("attachments", [])
        for attachment in attachments:
            fname = getattr(attachment, "filename", "fichier") if hasattr(attachment, "filename") else attachment.get("filename", "fichier")
            extraction = getattr(attachment, "extraction", None) if hasattr(attachment, "extraction") else attachment.get("extraction")
            extracted_text = getattr(attachment, "extracted_text", "") if hasattr(attachment, "extracted_text") else attachment.get("extracted_text", "")
            attachment_text = (
                extraction_text(extraction, 4000)
                if extraction
                else (extracted_text or "")[:4000]
            )
            item_text += f"\n[Pièce jointe : {fname}]\n{attachment_text}"
        transcript_parts.append(item_text[:12000])

    transcript = "\n".join(transcript_parts)
    logger.info(
        "Déclenchement résumé par seuil de tokens : total=%d, limite=%d (seuil_haut=%d), bloc=%d messages (summary_through %d -> %d)",
        total_tokens,
        limit_tokens,
        high_watermark,
        block_count,
        summary_through,
        summary_cutoff,
    )
    return True, summary_cutoff, transcript
