import html
import ipaddress
import re
import socket
import urllib.parse
from html.parser import HTMLParser
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException

from .config import Settings
from .documents import MAX_EXTRACTED_CHARS, extract_document
from .schemas import DocumentAnnotation, DocumentExtraction, ExtractedPage

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Tags to ignore completely along with their inner content
SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "template",
    "iframe",
    "form",
    "button",
    "dialog",
    "nav",
    "footer",
    "aside",
}

# Structural block elements that should trigger paragraph breaks
BLOCK_TAGS = {
    "article",
    "section",
    "nav",
    "aside",
    "header",
    "footer",
    "div",
    "main",
    "p",
    "blockquote",
    "figure",
    "figcaption",
    "pre",
    "table",
    "tr",
}


def is_private_or_local_host(hostname: str) -> bool:
    """Check if a hostname or IP points to a private, loopback, or reserved network."""
    host_lower = hostname.strip().lower()
    if host_lower in {"localhost", "localhost.localdomain", "broadcasthost"} or host_lower.endswith((".local", ".internal", ".localhost")):
        return True
    try:
        ip = ipaddress.ip_address(host_lower)
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(host_lower, None)
        for _, _, _, _, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast:
                return True
    except socket.gaierror:
        # Host resolution failed or offline; will fail connection if invalid
        pass
    except Exception:
        return True
    return False


def validate_web_url(url: str, allow_private: bool = False) -> urllib.parse.ParseResult:
    """Validate that the URL is a safe, publicly reachable HTTP/HTTPS address."""
    clean_url = url.strip()
    if not clean_url:
        raise HTTPException(422, "L'adresse URL ne peut pas être vide.")
    try:
        parsed = urllib.parse.urlparse(clean_url)
    except Exception as exc:
        raise HTTPException(422, "Adresse URL invalide.") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise HTTPException(422, "Seuls les protocoles http:// et https:// sont autorisés.")

    if not parsed.netloc or not parsed.hostname:
        raise HTTPException(422, "L'adresse URL doit comporter un nom de domaine valide.")

    if not allow_private and is_private_or_local_host(parsed.hostname):
        raise HTTPException(422, "Les adresses du réseau local ou privé ne sont pas autorisées pour des raisons de sécurité.")

    return parsed


class WebPageContentExtractor(HTMLParser):
    """Clean HTML-to-Markdown parser preserving article headings, text, lists, and links."""

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.base_url = base_url
        self.title: str = ""
        self.meta_description: str = ""
        self.site_name: str = ""
        self.author: str = ""
        self._in_title = False
        self._skip_depth = 0
        self._link_href: str | None = None
        self._pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag_lower in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        if tag_lower == "title":
            self._in_title = True
        elif tag_lower == "meta":
            prop = (attr_dict.get("property") or attr_dict.get("name") or "").lower()
            content = attr_dict.get("content", "").strip()
            if content:
                if prop in {"og:title", "twitter:title"} and not self.title:
                    self.title = content
                elif prop in {"description", "og:description", "twitter:description"} and not self.meta_description:
                    self.meta_description = content
                elif prop in {"og:site_name", "application-name"} and not self.site_name:
                    self.site_name = content
                elif prop in {"author", "article:author"} and not self.author:
                    self.author = content
        elif tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag_lower[1])
            self._pieces.append(f"\n\n{'#' * level} ")
        elif tag_lower in BLOCK_TAGS:
            self._pieces.append("\n\n")
        elif tag_lower == "br":
            self._pieces.append("\n")
        elif tag_lower == "li":
            self._pieces.append("\n- ")
        elif tag_lower == "th" or tag_lower == "td":
            self._pieces.append(" | ")
        elif tag_lower == "hr":
            self._pieces.append("\n\n---\n\n")
        elif tag_lower == "a":
            href = attr_dict.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self._link_href = urllib.parse.urljoin(self.base_url, href) if self.base_url else href
            else:
                self._link_href = None

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return

        if tag_lower == "title":
            self._in_title = False
        elif tag_lower in BLOCK_TAGS or tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._pieces.append("\n")
        elif tag_lower == "a":
            self._link_href = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title += data
            return

        text = data.strip()
        if not text:
            return

        leading = " " if data[0].isspace() else ""
        trailing = " " if data[-1].isspace() else ""
        if self._link_href:
            piece = f"{leading}[{text}]({self._link_href}){trailing}"
        else:
            piece = f"{leading}{text}{trailing}"
        self._pieces.append(piece)

    def extract(self) -> dict[str, str]:
        raw_text = "".join(self._pieces)
        cleaned_text = re.sub(r"[ \t]+", " ", raw_text)
        cleaned_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_text).strip()
        cleaned_title = html.unescape(" ".join(self.title.split())).strip()
        cleaned_desc = html.unescape(" ".join(self.meta_description.split())).strip()
        return {
            "title": cleaned_title,
            "description": cleaned_desc,
            "site_name": self.site_name,
            "author": self.author,
            "markdown": cleaned_text,
        }


async def fetch_and_parse_web_url(
    settings: Settings,
    raw_url: str,
    allow_private: bool = False,
) -> tuple[str, bytes, str, str, dict[str, Any]]:
    """
    Fetches a web page or file at raw_url, parses its content, and returns:
    (filename, content_bytes, mime_type, extracted_text, extraction_dict)
    """
    parsed = validate_web_url(raw_url, allow_private=allow_private)
    clean_url = parsed.geturl()
    domain = parsed.hostname or ""

    from .youtube import extract_youtube_video_id, fetch_and_parse_youtube_video

    video_id = extract_youtube_video_id(clean_url)
    if video_id:
        return await fetch_and_parse_youtube_video(settings, clean_url, video_id)

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,text/plain;q=0.8,*/*;q=0.5",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            max_redirects=5,
            headers=headers,
        ) as client:
            response = await client.get(clean_url)
            final_parsed = urllib.parse.urlparse(str(response.url))
            if not allow_private and is_private_or_local_host(final_parsed.hostname or ""):
                raise HTTPException(422, "Redirection vers un hôte local ou privé interdite.")
            response.raise_for_status()
            content = response.content
            content_type = response.headers.get("content-type", "").lower()
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(504, f"Le site {domain} a mis trop de temps à répondre (délai dépassé).") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            422, f"Le site {domain} a renvoyé une erreur HTTP {exc.response.status_code}."
        ) from exc
    except Exception as exc:
        raise HTTPException(
            422, f"Impossible d'accéder au lien web ({type(exc).__name__}). Vérifiez l'adresse ou la connexion."
        ) from exc

    if not content:
        raise HTTPException(422, "La page web ou le document cible est vide.")

    # Check for direct PDF or image downloads
    if "application/pdf" in content_type or clean_url.lower().endswith(".pdf"):
        filename = f"{clean_url.split('/')[-1] or 'document.pdf'}"
        mime, extracted, extraction = await extract_document(settings, content, filename)
        return filename, content, mime, extracted, extraction or {}

    if any(img_mime in content_type for img_mime in ("image/png", "image/jpeg", "image/webp")):
        filename = f"{clean_url.split('/')[-1] or 'image.jpg'}"
        mime, extracted, extraction = await extract_document(settings, content, filename)
        return filename, content, mime, extracted, extraction or {}

    # Handle HTML or text content
    charset = response.encoding or "utf-8"
    try:
        html_text = content.decode(charset, errors="replace")
    except Exception:
        html_text = content.decode("utf-8", errors="replace")

    extractor = WebPageContentExtractor(base_url=str(response.url))
    extractor.feed(html_text)
    extracted_data = extractor.extract()

    title = extracted_data["title"] or domain
    # Clean title to keep reasonable length
    short_title = title[:80].strip()
    markdown = extracted_data["markdown"]

    if not markdown.strip():
        # Fallback if page had very little standard HTML text
        text_content = re.sub(r"<[^>]+>", " ", html_text)
        text_content = re.sub(r"\s+", " ", text_content).strip()
        markdown = text_content[:MAX_EXTRACTED_CHARS]

    # Prepend title and source metadata to the extracted markdown
    header_parts = [f"# {title}", f"\n**Source :** [{domain}]({clean_url})"]
    if extracted_data.get("description"):
        header_parts.append(f"\n> {extracted_data['description']}")
    if extracted_data.get("author"):
        header_parts.append(f"\n*Auteur : {extracted_data['author']}*")

    full_markdown = "\n".join(header_parts) + "\n\n" + markdown
    if len(full_markdown) > MAX_EXTRACTED_CHARS:
        full_markdown = full_markdown[:MAX_EXTRACTED_CHARS] + "\n\n[... contenu tronqué à 40 000 caractères ...]"

    filename = f"🌐 {short_title} ({domain})"[:255]
    mime_type = "text/html"

    extraction = DocumentExtraction(
        model="web-parser",
        pages=[
            ExtractedPage(
                index=0,
                markdown=full_markdown,
                method="local",
                images=[],
            )
        ],
        annotations=[
            DocumentAnnotation(
                title=title,
                summary=extracted_data.get("description") or f"Contenu web extrait depuis {clean_url}",
            )
        ],
        warnings=[],
    ).model_dump()
    extraction["url"] = clean_url
    extraction["domain"] = domain

    # Store markdown as content bytes
    content_bytes = full_markdown.encode("utf-8")

    return filename, content_bytes, mime_type, full_markdown, extraction
