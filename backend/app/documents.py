import asyncio
import io
import re
import warnings
import zipfile
from contextlib import closing
from pathlib import Path
from threading import Lock

from docx import Document
from fastapi import HTTPException
from PIL import Image
from pypdf import PdfReader, PdfWriter
import pypdfium2 as pdfium

from . import providers
from .config import Settings
from .schemas import DocumentExtraction, ExtractedPage

MAX_EXTRACTED_CHARS = 40000
_PDF_RENDER_LOCK = Lock()


def normalize_unlocked_pdf(content: bytes, max_pages: int = 300) -> tuple[bytes, int, list[str]]:
    """Valide et normalise un PDF :
    - Tolère les octets d'en-tête avant `%PDF-` (norme ISO 32000 : dans les 1024 premiers octets).
    - Déverrouille automatiquement les PDF protégés uniquement par permissions éditeur (mot de passe ouverture vide `""`,
      très fréquent sur les livrets de règles, FAQ officielles et rapports financiers exportés depuis InDesign/Acrobat)
      et réécrit un flux PDF propre non chiffré pour Mistral OCR.
    - Isole les erreurs de polices/CMap page par page lors de `extract_text()`.
    - Utilise `pypdfium2` en filet de sécurité si la table xref `pypdf` est atypique.
    """
    header_idx = content.find(b"%PDF-", 0, 1024) if content else -1
    if header_idx < 0:
        raise HTTPException(422, "Le fichier fourni n'est pas un PDF valide.")
    if header_idx > 0:
        content = content[header_idx:]

    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        was_owner_encrypted = False
        if reader.is_encrypted:
            try:
                dec_status = reader.decrypt("")
            except Exception as exc:
                raise HTTPException(
                    422,
                    "Ce PDF est protégé par un chiffrement non supporté ou un mot de passe d'ouverture.",
                ) from exc
            if not dec_status:
                raise HTTPException(
                    422,
                    "Ce PDF exige un mot de passe d'ouverture. Déverrouillez-le avant de l'importer.",
                )
            was_owner_encrypted = True

        page_count = len(reader.pages)
        if page_count < 1:
            raise HTTPException(422, "Le PDF ne contient aucune page.")
        if page_count > max_pages:
            raise HTTPException(422, f"Le PDF dépasse la limite de {max_pages} pages ({page_count} pages détectées).")

        page_texts: list[str] = []
        total_chars = 0
        for page in reader.pages:
            if total_chars < MAX_EXTRACTED_CHARS * 2:
                try:
                    txt = (page.extract_text() or "").strip()
                except Exception:
                    txt = ""
            else:
                txt = ""
            page_texts.append(txt)
            total_chars += len(txt)

        if was_owner_encrypted:
            try:
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                out = io.BytesIO()
                writer.write(out)
                unlocked_bytes = out.getvalue()
                if unlocked_bytes.startswith(b"%PDF-"):
                    content = unlocked_bytes
            except Exception:
                pass

        return content, page_count, page_texts
    except HTTPException:
        raise
    except Exception:
        # Filet de sécurité via le moteur C++ PDFium (Chrome) si pypdf échoue sur une table xref atypique
        try:
            with _PDF_RENDER_LOCK:
                doc = pdfium.PdfDocument(content)
                try:
                    page_count = len(doc)
                    if page_count < 1:
                        raise HTTPException(422, "Le PDF ne contient aucune page.")
                    if page_count > max_pages:
                        raise HTTPException(422, f"Le PDF dépasse la limite de {max_pages} pages.")
                    page_texts = []
                    for idx in range(page_count):
                        page = doc[idx]
                        try:
                            textpage = page.get_textpage()
                            try:
                                page_texts.append((textpage.get_text_range() or "").strip())
                            finally:
                                if hasattr(textpage, "close"):
                                    textpage.close()
                        except Exception:
                            page_texts.append("")
                        finally:
                            if hasattr(page, "close"):
                                page.close()
                    return content, page_count, page_texts
                finally:
                    if hasattr(doc, "close"):
                        doc.close()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, "PDF illisible ou protégé par un mot de passe d'ouverture.") from exc


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
        _norm_bytes, _page_count, page_texts = normalize_unlocked_pdf(content, max_pages=300)
        return "application/pdf", "\n".join(t for t in page_texts if t)[:MAX_EXTRACTED_CHARS]
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


def extraction_text(extraction: dict | DocumentExtraction, limit: int | None = None) -> str:
    result = DocumentExtraction.model_validate(extraction)
    sections = []
    page_contents = []
    for page in result.pages:
        descriptions = [f"Figure {image.id} : {image.annotation.description}\n{image.annotation.visible_text}"
                        for image in page.images if image.annotation]
        if page.vision_description:
            descriptions.append(f"Description visuelle : {page.vision_description}")
        header = f"[Page {page.index + 1}]\n"
        description = "\n\n".join(descriptions)
        page_contents.append((header, page.markdown, description))
        sections.append(header + "\n\n".join(value for value in (page.markdown, description) if value))
    full = "\n\n".join(sections)
    if limit is None or len(full) <= limit:
        return full
    notice = "[Extraits limites par page ; contenu integral disponible dans la piece jointe.]\n"
    allowance = max(0, (limit - len(notice)) // len(sections) - 2)
    marker = " [...]"

    def excerpt(value: str, size: int) -> str:
        if len(value) <= size:
            return value
        return (value[:max(0, size - len(marker))] + marker)[:size]

    excerpts = []
    for header, markdown, description in page_contents:
        content_budget = max(0, allowance - len(header) - 2)
        description_budget = min(len(description), content_budget // 3) if markdown else content_budget
        text_budget = max(0, content_budget - description_budget)
        excerpts.append(header + excerpt(markdown, text_budget) + "\n\n" + excerpt(description, description_budget))
    return (notice + "\n\n".join(excerpts))[:limit]


def render_pdf_page(content: bytes, index: int) -> bytes:
    try:
        with _PDF_RENDER_LOCK:
            document = pdfium.PdfDocument(content)
            try:
                page = document[index]
                try:
                    width, height = page.get_size()
                    if min(width, height) <= 0 or max(width, height) / min(width, height) > 100:
                        raise ValueError
                    bitmap = page.render(scale=min(2, 2048 / max(width, height)))
                    try:
                        image = bitmap.to_pil()
                        try:
                            output = io.BytesIO()
                            image.save(output, format="PNG")
                            return output.getvalue()
                        finally:
                            if hasattr(image, "close"):
                                image.close()
                    finally:
                        if hasattr(bitmap, "close"):
                            bitmap.close()
                finally:
                    if hasattr(page, "close"):
                        page.close()
            finally:
                if hasattr(document, "close"):
                    document.close()
    except Exception:
        raise HTTPException(422, "Impossible de rendre cette page PDF pour la vision.") from None


def normalize_vision_image(content: bytes) -> bytes:
    with Image.open(io.BytesIO(content)) as image:
        image.thumbnail((2048, 2048))
        with image.convert("RGB") as picture:
            output = io.BytesIO()
            picture.save(output, format="JPEG", quality=90)
            return output.getvalue()


async def extract_document(settings: Settings, content: bytes, filename: str, mode: str = "auto") -> tuple[str, str, dict | None]:
    pdf_page_count = 1
    if Path(filename).suffix.lower() == ".pdf":
        content, pdf_page_count, page_texts = await asyncio.to_thread(normalize_unlocked_pdf, content, 300)
        mime = "application/pdf"
        text = "\n".join(t for t in page_texts if t)[:MAX_EXTRACTED_CHARS]
    else:
        mime, text = await asyncio.to_thread(inspect_document, content, filename)
    visual = mime == "application/pdf" or mime.startswith("image/")
    if mime.startswith("image/") and len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Les images sont limitées à 8 Mo pour la vision")

    # Mode Vision explicite : analyse visuelle détaillée par le modèle de vision
    if mode in ("vision", "image"):
        if not visual:
            raise HTTPException(422, "L'analyse visuelle détaillée s'applique uniquement aux images (PNG, JPEG, WebP) et aux PDF.")
        if settings.demo_mode:
            description = f"Description visuelle détaillée simulée pour {filename}."
            extraction = DocumentExtraction(
                model="demo-vision",
                pages=[ExtractedPage(index=0, markdown=description, vision_description=description, method="vision")],
                warnings=[],
            )
            return mime, description, extraction.model_dump()
        if not settings.vision_model:
            raise HTTPException(422, "Configurez VISION_MODEL pour analyser les images avec le modèle de vision.")
        try:
            if mime == "application/pdf":
                image = await asyncio.to_thread(render_pdf_page, content, 0)
                image_mime = "image/png"
            else:
                image = await asyncio.to_thread(normalize_vision_image, content)
                image_mime = "image/jpeg"
            description = await asyncio.wait_for(
                providers.describe_image(settings, image, image_mime),
                timeout=300,
            )
            extraction = DocumentExtraction(
                model=settings.vision_model,
                pages=[ExtractedPage(index=0, markdown="", vision_description=description, method="vision")],
                warnings=[],
            )
            return mime, description, extraction.model_dump()
        except TimeoutError:
            raise providers.ProviderError("L'analyse visuelle a dépassé le délai autorisé de 5 minutes.") from None

    if not visual or settings.demo_mode:
        if mime == "application/pdf" and not text.strip():
            raise HTTPException(422, "Configurez MISTRAL_API_KEY et désactivez DEMO_MODE pour analyser ce PDF sans texte.")
        extraction = (DocumentExtraction(model="local", pages=[ExtractedPage(index=0, markdown=text, method="local")],
                     warnings=["Extraction locale limitée, sans analyse des illustrations."])
                      if text else None)
        return mime, text, extraction.model_dump() if extraction else None
    try:
        if not settings.enabled(settings.mistral_api_key):
            raise HTTPException(422, "Configurez MISTRAL_API_KEY pour analyser les PDF et images avec OCR 4.1.")
        page_count = pdf_page_count if mime == "application/pdf" else 1
        async def _do_ocr():
            ext = await providers.extract_ocr(settings, content, mime, page_count=page_count)
            for page in ext.pages:
                readable = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", page.markdown)
                if not any(character.isalnum() for character in readable):
                    if mime == "application/pdf":
                        if not settings.vision_model:
                            continue
                        try:
                            image = await asyncio.to_thread(render_pdf_page, content, page.index)
                            page.vision_description = await providers.describe_image(settings, image, "image/png")
                            page.method = "vision"
                        except (providers.ProviderError, HTTPException):
                            pass
                    else:
                        image = await asyncio.to_thread(normalize_vision_image, content)
                        page.vision_description = await providers.describe_image(settings, image, "image/jpeg")
                        page.method = "vision"
            return ext

        extraction = await asyncio.wait_for(_do_ocr(), timeout=600)
        if len(extraction.model_dump_json().encode("utf-8")) > 4 * 1024 * 1024:
            raise providers.ProviderError("L'extraction dépasse la limite de stockage de 4 Mo.")
        return mime, extraction_text(extraction), extraction.model_dump()
    except TimeoutError:
        raise providers.ProviderError("L'analyse du document dépasse le délai global de 10 minutes.") from None
