import asyncio
import io
import warnings
import zipfile
from pathlib import Path

from docx import Document
from fastapi import HTTPException
from PIL import Image
from pypdf import PdfReader

from . import providers
from .config import Settings

MAX_EXTRACTED_CHARS = 40000


def inspect_document(content: bytes, filename: str) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as picture:
                    picture.verify()
                    if picture.format not in {"PNG", "JPEG", "WEBP"}:
                        raise ValueError()
                    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[picture.format]
                    return mime, ""
        except Exception as exc:
            raise HTTPException(422, "Image invalide ou dimensions excessives. Formats acceptés : PNG, JPEG, WebP.") from exc
    if suffix == ".pdf":
        try:
            if not content.startswith(b"%PDF-"):
                raise ValueError()
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise HTTPException(422, "Déverrouillez le PDF avant de le joindre.")
            if len(reader.pages) > 300:
                raise HTTPException(422, "Le PDF dépasse la limite de 300 pages.")
            chunks: list[str] = []
            length = 0
            for page in reader.pages:
                text = page.extract_text() or ""
                chunks.append(text)
                length += len(text)
                if length >= MAX_EXTRACTED_CHARS:
                    break
            return "application/pdf", "\n".join(chunks)[:MAX_EXTRACTED_CHARS]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, "PDF illisible ou non pris en charge.") from exc
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 40 * 1024 * 1024:
                    raise ValueError()
            document = Document(io.BytesIO(content))
            paragraphs = [paragraph.text for paragraph in document.paragraphs]
            paragraphs.extend(" | ".join(cell.text for cell in row.cells) for table in document.tables for row in table.rows)
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "\n".join(paragraphs)[:MAX_EXTRACTED_CHARS]
        except Exception as exc:
            raise HTTPException(422, "Document Word invalide ou trop volumineux après décompression.") from exc
    if suffix in {".txt", ".md", ".csv", ".json"}:
        try:
            text = content.decode("utf-8-sig")
            if "\x00" in text:
                raise ValueError()
            return "text/plain", text[:MAX_EXTRACTED_CHARS]
        except (UnicodeDecodeError, ValueError) as exc:
            raise HTTPException(422, "Le document texte doit être encodé en UTF-8.") from exc
    raise HTTPException(415, "Formats acceptés : PDF, DOCX, TXT, MD, CSV, JSON, PNG, JPEG et WebP.")


async def extract_document(settings: Settings, content: bytes, filename: str) -> tuple[str, str]:
    mime, text = await asyncio.to_thread(inspect_document, content, filename)
    if mime == "application/pdf" and not text.strip():
        if not settings.enabled(settings.mistral_api_key):
            raise HTTPException(422, "Ce PDF est scanné ou ne contient aucun texte. Configurez MISTRAL_API_KEY pour l'OCR, ou joignez un PDF texte.")
        text = await providers.extract_ocr(settings, content, mime)
        if not text.strip():
            raise HTTPException(422, "L'OCR n'a détecté aucun texte dans ce PDF.")
    return mime, text[:MAX_EXTRACTED_CHARS]
