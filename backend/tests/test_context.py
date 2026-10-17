import json
import pytest

from app.config import Settings
from app.context import build_context


def test_context_budget_reserves_latest_turn_with_all_optional_data():
    settings = Settings(_env_file=None, max_context_chars=10000)
    context = build_context(settings, "résumé " * 1000, ["souvenir " * 2000],
                            [{"role": "user", "content": "LATEST_QUESTION " * 1400}],
                            [{"title": "Source" * 100, "url": "https://example.org", "snippet": "web " * 3000}], False)
    assert sum(len(message["content"]) for message in context) <= 10000
    assert context[-1]["role"] == "user"
    assert context[-1]["content"].startswith("LATEST_QUESTION")
    assert len(context[-1]["content"]) > 4000


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
