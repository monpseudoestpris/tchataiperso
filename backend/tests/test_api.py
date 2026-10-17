import io
import json

import pytest
from fastapi.testclient import TestClient
from docx import Document
from PIL import Image
from pydantic import SecretStr
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app import providers
from app.config import Settings
from app.main import create_app
from app.models import Conversation, Message


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=True)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as value:
        yield value


def events(response):
    result = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        result.append((name, data))
    return result


def conversation(client, **body):
    response = client.post("/api/conversations", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def test_config_and_disabled_credentials(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["demo_mode"] is True
    assert config["features"] == {"chat": True, "web_search": False, "ocr": False, "image_generation": False}
    assert "api_key" not in json.dumps(config).lower()


def test_demo_stream_history_and_crud(client):
    item = conversation(client)
    sent = client.post(f"/api/conversations/{item}/messages", json={"content": "Bonjour"})
    stream = events(sent)
    assert stream[0][0] == "meta"
    assert stream[-1][0] == "done"
    assert "Mode démonstration" in "".join(data["text"] for name, data in stream if name == "delta")
    detail = client.get(f"/api/conversations/{item}").json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["title"] == "Bonjour"
    assert client.patch(f"/api/conversations/{item}", json={"title": "Test"}).json()["title"] == "Test"
    assert client.delete(f"/api/conversations/{item}").status_code == 204
    assert client.get(f"/api/conversations/{item}").status_code == 404


def test_model_and_feature_validation(client):
    assert client.post("/api/conversations", json={"model": "unknown"}).status_code == 422
    item = conversation(client)
    route = f"/api/conversations/{item}/messages"
    assert client.post(route, json={"content": "test", "model": "unknown"}).status_code == 422
    assert client.post(route, json={"content": ""}).status_code == 422
    assert client.post(route, json={"content": "test", "web_search": True}).status_code == 503
    assert client.post(f"/api/conversations/{item}/images", json={"prompt": "a cat"}).status_code == 503


def test_upload_attachment_extraction_history_and_deletion(client, settings):
    upload = client.post("/api/attachments", files={"file": ("../notes.md", b"# Document\nUne information", "text/plain")})
    assert upload.status_code == 201
    attachment = upload.json()
    assert attachment["filename"] == "notes.md"
    assert attachment["extracted_chars"] > 0
    assert client.get(attachment["url"]).content.startswith(b"# Document")
    item = conversation(client)
    response = client.post(f"/api/conversations/{item}/messages", json={"content": "Lis", "attachment_ids": [attachment["id"]]})
    assert events(response)[-1][0] == "done"
    detail = client.get(f"/api/conversations/{item}").json()
    assert detail["messages"][0]["attachments"][0]["id"] == attachment["id"]
    assert client.post(f"/api/conversations/{item}/messages", json={"content": "Bis", "attachment_ids": [attachment["id"]]}).status_code == 422
    assert client.delete(f"/api/conversations/{item}").status_code == 204
    assert client.get(attachment["url"]).status_code == 404
    assert list((settings.app_data_dir / "uploads").iterdir()) == []


def test_scanned_pdf_requires_ocr_and_unsafe_upload_rejected(client):
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)
    content = io.BytesIO()
    pdf.write(content)
    response = client.post("/api/attachments", files={"file": ("scan.pdf", content.getvalue(), "application/pdf")})
    assert response.status_code == 422
    assert "MISTRAL_API_KEY" in response.json()["detail"]
    assert client.post("/api/attachments", files={"file": ("code.html", b"<script>alert(1)</script>", "text/html")}).status_code == 415
    assert client.post("/api/attachments", files={"file": ("fake.png", b"bad image", "image/png")}).status_code == 422


def test_upload_limits(client, settings):
    settings.max_upload_mb = 1
    response = client.post("/api/attachments", files={"file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")})
    assert response.status_code == 413


def test_explicit_memory_is_persisted_and_deleted(client):
    item = client.post("/api/memories", json={"content": "Je préfère le français"}).json()
    assert client.get("/api/memories").json() == [item]
    assert client.delete(f"/api/memories/{item['id']}").status_code == 204
    assert client.get("/api/memories").json() == []
    assert client.post("/api/memories", json={"content": "  "}).status_code == 422


def test_no_key_never_silently_uses_demo(tmp_path):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/config").json()["features"]["chat"] is False
        item = conversation(client)
        response = client.post(f"/api/conversations/{item}/messages", json={"content": "hello"})
        assert response.status_code == 503
        assert client.get(f"/api/conversations/{item}").json()["messages"] == []


def test_mock_real_chat_injects_memory_docs_and_sources(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False, llm_api_key="secret", brave_api_key="brave")
    captured = {}

    async def search(_settings, query):
        assert query == "Compare les infos"
        return [{"title": "Référence", "url": "https://example.org", "snippet": "Texte web"}]

    async def stream(_settings, messages, model):
        captured["messages"] = messages
        yield "Réponse "
        yield "réelle simulée"

    monkeypatch.setattr(providers, "search_web", search)
    monkeypatch.setattr(providers, "stream_chat", stream)
    with TestClient(create_app(settings)) as client:
        client.post("/api/memories", json={"content": "Répondre en français"})
        attachment = client.post("/api/attachments", files={"file": ("facts.txt", b"Information document", "text/plain")}).json()
        item = conversation(client)
        response = client.post(f"/api/conversations/{item}/messages", json={"content": "Compare les infos", "web_search": True, "attachment_ids": [attachment["id"]]})
        assert events(response)[-1][0] == "done"
        payload = json.dumps(captured["messages"], ensure_ascii=False)
        assert "Répondre en français" in payload
        assert "Information document" in payload
        assert "https://example.org" in payload
        assert client.get(f"/api/conversations/{item}").json()["messages"][-1]["sources"][0]["title"] == "Référence"


def test_stream_failure_is_explicit_unlocks_and_preserves_user(client, settings, monkeypatch):
    settings.demo_mode = False
    settings.llm_api_key = SecretStr("secret")

    async def failing(*args):
        yield "Début"
        raise providers.ProviderError("Quota épuisé")

    monkeypatch.setattr(providers, "stream_chat", failing)
    item = conversation(client)
    response = client.post(f"/api/conversations/{item}/messages", json={"content": "hello"})
    assert events(response)[-1] == ("error", {"message": "Quota épuisé"})
    assert [value["role"] for value in client.get(f"/api/conversations/{item}").json()["messages"]] == ["user"]
    assert client.patch(f"/api/conversations/{item}", json={"title": "unlocked"}).status_code == 200


def test_summary_retains_complete_history_and_excludes_global_memory(client, settings):
    settings.summary_every_messages = 8
    client.post("/api/memories", json={"content": "GLOBAL_PRIVATE_MEMORY"})
    item = conversation(client)
    for index in range(5):
        response = client.post(f"/api/conversations/{item}/messages", json={"content": f"Échange numéro {index}"})
        assert events(response)[-1][0] == "done"
    detail = client.get(f"/api/conversations/{item}").json()
    assert len(detail["messages"]) == 10
    assert detail["summary"]
    assert "GLOBAL_PRIVATE_MEMORY" not in detail["summary"]


def test_image_model_and_ocr_fallback(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, demo_mode=False, llm_api_key="secret",
                        mistral_api_key="ocr", llm_models='[{"id":"text","name":"Text","vision":false}]', default_model="text")
    content = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(content, format="PNG")
    captured = {}

    async def ocr(_settings, data, mime):
        assert mime == "image/png"
        return "TEXTE OCR"

    async def stream(_settings, messages, model):
        captured["messages"] = messages
        yield "Texte lu"

    monkeypatch.setattr(providers, "extract_ocr", ocr)
    monkeypatch.setattr(providers, "stream_chat", stream)
    with TestClient(create_app(settings)) as client:
        upload = client.post("/api/attachments", files={"file": ("image.png", content.getvalue(), "image/png")}).json()
        item = conversation(client)
        response = client.post(f"/api/conversations/{item}/messages", json={"content": "lis", "attachment_ids": [upload["id"]]})
        assert events(response)[-1][0] == "done"
        assert "TEXTE OCR" in json.dumps(captured)


def test_mock_image_generation_saved_in_history(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, ideogram_api_key="image", demo_mode=False)

    async def generate(_settings, prompt, ratio):
        assert prompt == "Un chat" and ratio == "1:1"
        return b"image-data", "image/png"

    monkeypatch.setattr(providers, "generate_image", generate)
    with TestClient(create_app(settings)) as client:
        item = conversation(client)
        response = client.post(f"/api/conversations/{item}/images", json={"prompt": "Un chat"})
        assert response.status_code == 201
        image = response.json()
        assert image["attachments"][0]["mime_type"] == "image/png"
        assert client.get(image["attachments"][0]["url"]).content == b"image-data"
        assert len(client.get(f"/api/conversations/{item}").json()["messages"]) == 2


def test_summary_includes_old_document_text_and_preserves_unsummarized_turns(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_data_dir=tmp_path, llm_api_key="key", summary_every_messages=8)
    captured = {}

    async def summarize(_settings, model, previous, transcript):
        captured["transcript"] = transcript
        return "Résumé fiable"

    async def stream(_settings, messages, model):
        captured["context"] = json.dumps(messages, ensure_ascii=False)
        yield "Réponse"

    monkeypatch.setattr(providers, "summarize", summarize)
    monkeypatch.setattr(providers, "stream_chat", stream)
    app = create_app(settings)
    with TestClient(app) as client:
        item = conversation(client)
        document = client.post("/api/attachments", files={"file": ("facts.txt", b"OLD_DOCUMENT_FACT", "text/plain")}).json()
        client.post(f"/api/conversations/{item}/messages", json={"content": "Premier échange", "attachment_ids": [document["id"]]})
        with app.state.sessions() as db:
            # Long previous turns force a bounded partial summary batch.
            for index in range(14):
                db.add(Message(conversation_id=item, role="user" if index % 2 == 0 else "assistant",
                               content=f"MARKER_{index} " + "x" * 6000))
            db.commit()
        response = client.post(f"/api/conversations/{item}/messages", json={"content": "Nouvelle question"})
        assert events(response)[-1][0] == "done"
        assert "OLD_DOCUMENT_FACT" in captured["transcript"]
        with app.state.sessions() as db:
            stored = db.get(Conversation, item)
            assert stored.summary_through < len(stored.messages) - 7
            first_unsummarized = stored.messages[stored.summary_through].content.split(" ")[0]
        assert first_unsummarized not in captured["transcript"]
        assert first_unsummarized in captured["context"]


def test_real_pdf_and_docx_extraction(client):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 50 200 Td (PDF_DOCUMENT_FACT) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf = io.BytesIO()
    writer.write(pdf)
    pdf_response = client.post("/api/attachments", files={"file": ("facts.pdf", pdf.getvalue(), "application/pdf")})
    assert pdf_response.status_code == 201
    assert pdf_response.json()["extracted_chars"] >= len("PDF_DOCUMENT_FACT")

    document = Document()
    document.add_paragraph("DOCX_DOCUMENT_FACT")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "TABLE_DOCUMENT_FACT"
    docx = io.BytesIO()
    document.save(docx)
    docx_response = client.post("/api/attachments", files={"file": ("facts.docx", docx.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert docx_response.status_code == 201
    assert docx_response.json()["extracted_chars"] >= len("DOCX_DOCUMENT_FACT\nTABLE_DOCUMENT_FACT")

    item = conversation(client)
    client.post(f"/api/conversations/{item}/messages", json={"content": "Résume", "attachment_ids": [pdf_response.json()["id"], docx_response.json()["id"]]})
    with client.app.state.sessions() as db:
        stored = db.get(Conversation, item)
        texts = [attachment.extracted_text for attachment in stored.messages[0].attachments]
    assert any("PDF_DOCUMENT_FACT" in value for value in texts)
    assert any("DOCX_DOCUMENT_FACT" in value and "TABLE_DOCUMENT_FACT" in value for value in texts)


def test_orphan_upload_delete_and_linked_file_protected(client):
    item = client.post("/api/attachments", files={"file": ("unused.txt", b"Unused", "text/plain")}).json()
    assert client.delete(f"/api/attachments/{item['id']}").status_code == 204
    assert client.get(item["url"]).status_code == 404
    attached = client.post("/api/attachments", files={"file": ("used.txt", b"Used", "text/plain")}).json()
    conv = conversation(client)
    client.post(f"/api/conversations/{conv}/messages", json={"content": "Lis", "attachment_ids": [attached["id"]]})
    assert client.delete(f"/api/attachments/{attached['id']}").status_code == 409


def test_five_images_rejected_explicitly(client):
    image = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(image, format="PNG")
    attachments = [client.post("/api/attachments", files={"file": (f"{index}.png", image.getvalue(), "image/png")}).json()["id"] for index in range(5)]
    item = conversation(client)
    response = client.post(f"/api/conversations/{item}/messages", json={"content": "Compare", "attachment_ids": attachments})
    assert response.status_code == 422
    assert "4 images" in response.json()["detail"]
    assert client.get(f"/api/conversations/{item}").json()["messages"] == []
