import re
from typing import Any

_TIKTOKEN_ENCODER = None
_TIKTOKEN_FAILED = False


def _get_encoder():
    global _TIKTOKEN_ENCODER, _TIKTOKEN_FAILED
    if _TIKTOKEN_FAILED:
        return None
    if _TIKTOKEN_ENCODER is None:
        try:
            import tiktoken
            _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _TIKTOKEN_FAILED = True
            return None
    return _TIKTOKEN_ENCODER


def estimate_tokens_fallback(text: str) -> int:
    """Estimation rapide et précise du nombre de tokens sans dépendance externe.

    Approche combinée : découpage lexical (mots et symboles) et ratio volumique
    adapté au français, à l'anglais et aux structures de code.
    """
    if not text:
        return 0
    words_and_symbols = len(re.findall(r"\w+|[^\w\s]+", text))
    newlines = text.count("\n")
    char_estimate = int(len(text) / 3.7)
    return max(1, words_and_symbols + newlines, char_estimate)


def count_tokens(text: str) -> int:
    """Compte le nombre de tokens d'un texte en utilisant tiktoken si disponible,

    avec repli immédiat et sans erreur vers l'estimation heuristique standard.
    """
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    return estimate_tokens_fallback(text)


def count_message_tokens(role: str, content: str, attachments: list[dict] | list[Any] | None = None) -> int:
    """Calcule le coût total en tokens d'un message individuel incluant son rôle,

    son contenu textuel et le texte extrait des pièces jointes associées.
    """
    # Surcoût de structure par message (balises de rôle et séparateurs de messages style ChatML)
    overhead = 4
    total = count_tokens(role) + count_tokens(content) + overhead

    if attachments:
        for attachment in attachments:
            att_text = ""
            if isinstance(attachment, dict):
                att_text = attachment.get("extracted_text") or ""
                if not att_text and attachment.get("extraction"):
                    from .documents import extraction_text
                    att_text = extraction_text(attachment["extraction"])
            else:
                att_text = getattr(attachment, "extracted_text", "") or ""
                if not att_text and getattr(attachment, "extraction", None):
                    from .documents import extraction_text
                    att_text = extraction_text(attachment.extraction)
            if att_text:
                total += count_tokens(att_text)
    return total

