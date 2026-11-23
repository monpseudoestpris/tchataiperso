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


_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class ResponseTooLargeError(ValueError):
    """Raised when an external HTTP response exceeds the allowed byte ceiling."""


class RedirectLimitError(ValueError):
    """Raised when an external HTTP fetch exceeds the maximum redirect hops."""


def is_private_or_local_host(hostname: str, *, resolve_dns: bool = True) -> bool:
    """Check if a hostname or IP points to a private, loopback, or reserved network."""
    host_lower = hostname.strip().rstrip(".").lower()
    if not host_lower:
        return True
    if host_lower in {"localhost", "localhost.localdomain", "broadcasthost"} or host_lower.endswith(
        (".local", ".internal", ".localhost")
    ):
        return True
    try:
        ip = ipaddress.ip_address(host_lower)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        pass

    if not resolve_dns:
        return False

    try:
        addrinfo = socket.getaddrinfo(host_lower, None)
        for _, _, _, _, sockaddr in addrinfo:
            ip = ipaddress.ip_address(sockaddr[0])
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_reserved
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return True
    except socket.gaierror:
        # Host resolution failed or offline; will fail connection if invalid
        pass
    except OSError:
        return True
    return False


def validate_web_url(
    url: str,
    allow_private: bool = False,
    *,
    resolve_dns: bool = True,
    allowed_schemes: tuple[str, ...] = ("http", "https"),
) -> urllib.parse.ParseResult:
    """Validate that the URL is a safe, publicly reachable HTTP/HTTPS address."""
    clean_url = (url or "").strip()
    if not clean_url:
        raise HTTPException(422, "L'adresse URL ne peut pas être vide.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in clean_url):
        raise HTTPException(422, "Adresse URL invalide.")
    try:
        parsed = urllib.parse.urlparse(clean_url)
    except ValueError as exc:
        raise HTTPException(422, "Adresse URL invalide.") from exc

    if parsed.scheme.lower() not in allowed_schemes:
        raise HTTPException(422, "Seuls les protocoles http:// et https:// sont autorisés.")

    if not parsed.netloc or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "L'adresse URL doit comporter un nom de domaine valide.")

    if not allow_private and is_private_or_local_host(parsed.hostname, resolve_dns=resolve_dns):
        raise HTTPException(422, "Les adresses du réseau local ou privé ne sont pas autorisées pour des raisons de sécurité.")

    return parsed


async def safe_stream_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    max_redirects: int = 5,
    allow_private: bool = False,
    resolve_dns: bool = True,
    allowed_schemes: tuple[str, ...] = ("http", "https"),
) -> tuple[str, int, httpx.Headers, bytes, str | None]:
    """Fetch an external URL with hop-by-hop SSRF validation before connecting and a strict byte cap."""
    current_url = validate_web_url(
        url,
        allow_private=allow_private,
        resolve_dns=resolve_dns,
        allowed_schemes=allowed_schemes,
    ).geturl()

    for hop in range(max_redirects + 1):
        async with client.stream("GET", current_url, follow_redirects=False) as response:
            location = response.headers.get("location")
            if response.status_code in _REDIRECT_STATUS_CODES and location:
                if hop >= max_redirects:
                    raise RedirectLimitError("Trop de redirections HTTP.")
                next_url = urllib.parse.urljoin(current_url, location.strip())
                current_url = validate_web_url(
                    next_url,
                    allow_private=allow_private,
                    resolve_dns=resolve_dns,
                    allowed_schemes=allowed_schemes,
                ).geturl()
                continue

            size_header = response.headers.get("content-length", "").strip()
            if size_header.isdigit() and int(size_header) > max_bytes:
                raise ResponseTooLargeError(f"La réponse dépasse la limite autorisée de {max_bytes} octets.")

            buf = bytearray()
            async for chunk in response.aiter_bytes():
                if len(buf) + len(chunk) > max_bytes:
                    raise ResponseTooLargeError(f"La réponse dépasse la limite autorisée de {max_bytes} octets.")
                buf.extend(chunk)

            final_url = str(response.url or current_url)
            return final_url, response.status_code, response.headers, bytes(buf), response.encoding

    raise RedirectLimitError("Trop de redirections HTTP.")


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
    from .finance import is_yahoo_finance_url, is_eodhd_url, fetch_and_parse_yahoo_finance

    video_id = extract_youtube_video_id(clean_url)
    if video_id:
        return await fetch_and_parse_youtube_video(settings, clean_url, video_id)

    if is_yahoo_finance_url(clean_url) or is_eodhd_url(clean_url):
        return await fetch_and_parse_yahoo_finance(settings, clean_url)

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,text/plain;q=0.8,*/*;q=0.5",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    max_upload_mb = max(1, min(int(getattr(settings, "max_upload_mb", 40) or 40), 100))
    max_bytes = max_upload_mb * 1024 * 1024

    try:
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=False,
            headers=headers,
        ) as client:
            final_url, status_code, resp_headers, content, resp_encoding = await safe_stream_get(
                client,
                clean_url,
                max_bytes=max_bytes,
                max_redirects=5,
                allow_private=allow_private,
            )
            if status_code >= 400:
                raise HTTPException(
                    422, f"Le site {domain} a renvoyé une erreur HTTP {status_code}."
                )
            content_type = resp_headers.get("content-type", "").lower()
    except HTTPException:
        raise
    except ResponseTooLargeError as exc:
        raise HTTPException(413, f"La ressource web dépasse la limite autorisée de {max_upload_mb} Mo.") from exc
    except RedirectLimitError as exc:
        raise HTTPException(422, "Le site effectue trop de redirections.") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(504, f"Le site {domain} a mis trop de temps à répondre (délai dépassé).") from exc
    except httpx.HTTPError as exc:
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
    charset = resp_encoding or "utf-8"
    try:
        html_text = content.decode(charset, errors="replace")
    except LookupError:
        html_text = content.decode("utf-8", errors="replace")

    extractor = WebPageContentExtractor(base_url=final_url)
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
