import pytest
from app.config import Settings
from app.chat_memory import evaluate_context_compression, get_model_context_limit
from app.token_counter import count_tokens, count_message_tokens


def test_token_counter_accuracy():
    assert count_tokens("") == 0
    assert count_tokens("Bonjour le monde") > 0
    # Code snippet
    code = "def add(a: int, b: int) -> int:\n    return a + b"
    tokens = count_tokens(code)
    assert 10 <= tokens <= 25


def test_short_messages_never_trigger_summary():
    """Vérifie que 12 messages courts ne déclenchent aucun résumé :

    tout est conservé brut pour préserver le KV Cache.
    """
    settings = Settings(_env_file=None, context_window_tokens=16000, summary_trigger_ratio=0.8)

    # 12 messages courts (environ 10 tokens chacun = 120 tokens << 12800 tokens seuil)
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message court numéro {i}"}
        for i in range(12)
    ]

    should_summarize, cutoff, transcript = evaluate_context_compression(
        history=history,
        summary_through=0,
        current_summary="",
        limit_tokens=16000,
        settings=settings,
    )

    assert not should_summarize
    assert cutoff == 0
    assert transcript == ""


def test_huge_messages_trigger_block_compression_down_to_40_percent():
    """Vérifie que 5 messages énormes dépassant 80 % déclenchent immédiatement

    la compression de la première moitié des anciens messages pour redescendre à ~40 %,
    tout en préservant intacts les messages les plus récents (fenêtre glissante).
    """
    settings = Settings(
        _env_file=None,
        context_window_tokens=10000,
        summary_trigger_ratio=0.8,
        summary_target_ratio=0.4,
        summary_min_recent_tokens=1500,
    )

    # 5 messages énormes : chacun environ 2000 tokens (total ~10 000 tokens >= 8000 seuil 80%)
    huge_content = "Grand bloc de données et de code verbeux. " * 300
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"MARKER_{i}: {huge_content}"}
        for i in range(5)
    ]

    should_summarize, cutoff, transcript = evaluate_context_compression(
        history=history,
        summary_through=0,
        current_summary="",
        limit_tokens=10000,
        settings=settings,
    )

    assert should_summarize is True
    # La compression prend la première moitié des messages compressibles
    # et préserve les messages récents (MARKER_3, MARKER_4) intacts
    assert cutoff >= 1
    assert "MARKER_0" in transcript
    # Les messages les plus récents ne doivent pas être dans le bloc compressé
    assert f"MARKER_{len(history) - 1}" not in transcript


def test_sliding_window_always_preserves_recent_tokens_verbatim():
    """Garantit que la fenêtre glissante garde toujours mot pour mot les derniers milliers

    de tokens récents sans jamais les compresser.
    """
    settings = Settings(
        _env_file=None,
        context_window_tokens=5000,
        summary_trigger_ratio=0.8,
        summary_min_recent_tokens=1000,
    )

    # 6 messages
    history = [
        {"role": "user", "content": "Ancien message 1 " * 200},
        {"role": "assistant", "content": "Ancienne réponse 1 " * 200},
        {"role": "user", "content": "Ancien message 2 " * 200},
        {"role": "assistant", "content": "Ancienne réponse 2 " * 200},
        {"role": "user", "content": "Dernière question contenant du CODE_PRECIS " * 50},
        {"role": "assistant", "content": "Dernière réponse avec DETAIL_CRITIQUE " * 50},
    ]

    should_summarize, cutoff, transcript = evaluate_context_compression(
        history=history,
        summary_through=0,
        current_summary="",
        limit_tokens=5000,
        settings=settings,
    )

    assert should_summarize is True
    # Vérifie que les deux derniers tours intacts sont épargnés par le résumé
    assert "CODE_PRECIS" not in transcript
    assert "DETAIL_CRITIQUE" not in transcript
    # Mais le premier message ancien est bien dans le transcript
    assert "Ancien message 1" in transcript


def test_model_context_limit_resolution():
    settings = Settings(_env_file=None, context_window_tokens=32000)

    # Modèle avec context_length explicite supérieur au plafond -> borné par settings.context_window_tokens
    model_gemini = {"id": "google/gemini-flash", "context_length": 128000}
    assert get_model_context_limit(settings, model_gemini) == 32000

    # Modèle avec context_length explicite inférieur -> respecte la limite du petit modèle
    model_small = {"id": "local/small", "context_length": 8192}
    assert get_model_context_limit(settings, model_small) == 8192

    # Modèle sans context_length explicite -> fallback sur settings.context_window_tokens
    model_custom = {"id": "custom/model"}
    assert get_model_context_limit(settings, model_custom) == 32000
