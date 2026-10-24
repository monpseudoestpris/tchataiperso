import json
import pytest

from app.config import Settings
from app.context import build_context
from app.documents import extraction_text


def test_context_budget_reserves_latest_turn_with_all_optional_data():
    settings = Settings(_env_file=None, max_context_chars=10000)
    context = build_context(settings, "résumé " * 1000, ["souvenir " * 2000],
                            [{"role": "user", "content": "LATEST_QUESTION " * 1400}],
                            [{"title": "Source" * 100, "url": "https://example.org", "snippet": "web " * 3000}], False)
    assert sum(len(message["content"]) for message in context) <= 10000
    assert context[-1]["role"] == "user"
    assert context[-1]["content"].startswith("LATEST_QUESTION")
    assert len(context[-1]["content"]) > 4000


def test_skill_prompts_are_separate_system_instructions_and_budgeted():
    settings = Settings(_env_file=None, max_context_chars=10000)
    context = build_context(settings, "Résumé", ["Souvenir"], [
        {"role": "user", "content": "QUESTION" * 1000},
    ], [], False, [{"name": "Rédaction", "prompt": "SKILL_INSTRUCTION" * 300}])
    assert context[0]["role"] == "system"
    assert context[1]["role"] == "system"
    assert "SKILL_INSTRUCTION" in context[1]["content"]
    assert sum(len(message["content"]) for message in context) <= 10000
    assert context[-1]["content"].startswith("QUESTION")


def test_generated_assistant_image_never_becomes_unsupported_vision_part():
    settings = Settings(_env_file=None)
    context = build_context(settings, "", [], [
        {"role": "assistant", "content": "Image générée : un chat", "attachments": [
            {"filename": "ideogram.png", "mime_type": "image/png", "extracted_text": "", "path": "/must/not/be/read"}]},
        {"role": "user", "content": "Continue"}], [], True)
    assert isinstance(context[-2]["content"], str)
    assert "Image générée : un chat" in context[-2]["content"]
    assert "image_url" not in json.dumps(context)


def test_user_image_is_encoded_only_for_vision(tmp_path):
    settings = Settings(_env_file=None)
    image = tmp_path / "picture.png"
    image.write_bytes(b"fake png")
    messages = [{"role": "user", "content": "Décris", "attachments": [
        {"filename": "photo.png", "mime_type": "image/png", "extracted_text": "", "path": str(image)}]}]
    vision = build_context(settings, "", [], messages, [], True)
    assert vision[-1]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert isinstance(build_context(settings, "", [], messages, [], False)[-1]["content"], str)


@pytest.mark.parametrize("hosts", ["*", "*.ideogram.ai", "localhost", "localhost.local", "127.0.0.1", "8.8.8.8", "https://ideogram.ai", "ideogram.ai:443", "example..org", "evil.internal", ""])
def test_ideogram_image_host_configuration_rejects_unsafe_destinations(hosts):
    with pytest.raises(ValueError, match="IDEOGRAM_IMAGE_HOSTS"):
        Settings(_env_file=None, ideogram_image_hosts=hosts)


def test_ideogram_image_host_configuration_normalizes_exact_names():
    settings = Settings(_env_file=None, ideogram_image_hosts=" ideogram.ai, CDN.Example.Org,ideogram.ai ")
    assert settings.ideogram_image_hosts == "ideogram.ai,cdn.example.org"


def test_paged_extraction_includes_late_figures_within_context_budget():
    settings = Settings(_env_file=None)
    extraction = {"model": "mistral-ocr-4-1", "pages": [
        {"index": index, "markdown": "OCR " * 2000, "vision_description": f"VISUAL_PAGE_{index}"}
        for index in range(10)
    ]}
    context = build_context(settings, "", [], [{"role": "user", "content": "Analyse", "attachments": [
        {"filename": "report.pdf", "mime_type": "application/pdf", "extracted_text": "full text",
         "extraction": extraction}
    ]}], [], False)
    text = context[-1]["content"]
    assert "VISUAL_PAGE_9" in text
    assert "Page 10" in text
    assert "contenu integral" in text
    assert 17000 < len(text) <= settings.max_context_chars


def test_extracted_text_does_not_suppress_original_image_for_vision(tmp_path):
    image = tmp_path / "photo.png"
    image.write_bytes(b"fake png")
    context = build_context(Settings(_env_file=None), "", [], [{"role": "user", "content": "Detaille", "attachments": [
        {"filename": "photo.png", "mime_type": "image/png", "extracted_text": "A red rectangle", "path": str(image)}
    ]}], [], True)
    assert "A red rectangle" in context[-1]["content"][0]["text"]
    assert context[-1]["content"][1]["type"] == "image_url"


def test_extraction_text_preserves_verbatim_ocr_instead_of_document_summary():
    original = "Original title\n\n  00123 ; 12,50 EUR\nFootnote: EXCEPTION applies.\n"
    extraction = {"model": "mistral-ocr-4-1", "pages": [{"index": 0, "markdown": original}],
                  "annotations": [{"title": "Title", "summary": "LOSSY_SUMMARY" * 1000}]}
    assert extraction_text(extraction) == "[Page 1]\n" + original
    assert extraction_text(extraction, len(original) + 10) == "[Page 1]\n" + original


def test_chat_keeps_details_after_old_16000_character_cutoff():
    settings = Settings(_env_file=None, max_context_chars=60000)
    original = "Texte exact " * 2000 + "\nLATE_FOOTNOTE_12345"
    extraction = {"model": "mistral-ocr-4-1", "pages": [{"index": 0, "markdown": original}],
                  "annotations": [{"title": "Title", "summary": "LOSSY_SUMMARY"}]}
    context = build_context(settings, "", [], [{"role": "user", "content": "Lis", "attachments": [
        {"filename": "details.pdf", "mime_type": "application/pdf", "extracted_text": original, "extraction": extraction}
    ]}], [], False)
    assert original in context[-1]["content"]
    assert "LOSSY_SUMMARY" not in context[-1]["content"]
    assert sum(len(message["content"]) for message in context) <= settings.max_context_chars


def test_multiple_documents_share_context_without_losing_last_details():
    settings = Settings(_env_file=None, max_context_chars=10000)
    attachments = [{"filename": f"file-{index}.pdf", "mime_type": "application/pdf", "extracted_text": "available",
                    "extraction": {"model": "ocr", "pages": [{"index": 0, "markdown": f"DOC_{index}\n" + "text " * 3000}]}}
                   for index in range(2)]
    context = build_context(settings, "", [], [{"role": "user", "content": "Lis les deux", "attachments": attachments}], [], False)
    assert "DOC_0" in context[-1]["content"] and "DOC_1" in context[-1]["content"]
    assert "contenu integral" in context[-1]["content"]
    assert sum(len(message["content"]) for message in context) <= settings.max_context_chars


def test_deep_search_context_expands_sources_and_injects_synthesis_instructions():
    settings = Settings(_env_file=None, max_context_chars=120000)
    sources = [
        {"title": f"Source {index}", "url": f"https://example.org/{index}", "query": f"piste {index}", "snippet": f"EXTRAIT_{index} " * 40}
        for index in range(1, 101)
    ]
    context = build_context(
        settings, "Résumé", ["Souvenir"],
        [{"role": "user", "content": "Synthèse complète"}],
        sources, False, deep_search=True,
    )
    assert "Mode DeepSearch" in context[0]["content"]
    assert "Traduis systématiquement" in context[0]["content"]
    reference_block = context[1]["content"]
    assert "Requête : piste 1" in reference_block
    assert "EXTRAIT_100" in reference_block
    assert sum(len(message["content"]) for message in context) <= settings.max_context_chars


def test_code_mode_context_injects_canvas_multi_file_instructions():
    settings = Settings(_env_file=None, max_context_chars=30000)
    context = build_context(
        settings, "", [],
        [{"role": "user", "content": "Crée une application Pomodoro en HTML/CSS/JS"}],
        [], False, code_mode=True,
    )
    assert "Mode Code Canvas" in context[0]["content"]
    assert 'path="chemin/relatif/fichier.ext"' in context[0]["content"]
    assert context[-1]["content"] == "Crée une application Pomodoro en HTML/CSS/JS"

