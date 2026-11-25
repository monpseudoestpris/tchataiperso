"""Validation et nettoyage XML strict des fichiers SVG entrants (anti-XSS, anti-XXE, anti-SSRF)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from .google_cloud import ProviderError

_MAX_SVG_BYTES = 10 * 1024 * 1024
_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"

ET.register_namespace("", _SVG_NS)
ET.register_namespace("xlink", _XLINK_NS)

_ALLOWED_SVG_TAGS: frozenset[str] = frozenset({
    "svg",
    "g",
    "defs",
    "symbol",
    "use",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "tspan",
    "textpath",
    "lineargradient",
    "radialgradient",
    "stop",
    "clippath",
    "mask",
    "pattern",
    "marker",
    "switch",
    "style",
    "title",
    "desc",
    "metadata",
    "filter",
    "feblend",
    "fecolormatrix",
    "fecomponenttransfer",
    "fecomposite",
    "feconvolvematrix",
    "fediffuselighting",
    "fedisplacementmap",
    "fedropshadow",
    "feflood",
    "fegaussianblur",
    "fefuncr",
    "fefuncg",
    "fefuncb",
    "fefunca",
    "femerge",
    "femergenode",
    "femorphology",
    "feoffset",
    "fespecularlighting",
    "fetile",
    "feturbulence",
    "fedistantlight",
    "fepointlight",
    "fespotlight",
})

_FORBIDDEN_HEADER_RE = re.compile(r"<!\s*(?:DOCTYPE|ENTITY)\b|<\?\s*xml-stylesheet\b", re.IGNORECASE)
_INTERNAL_FRAGMENT_RE = re.compile(r"^#[A-Za-z0-9_.:-]+$")
_DANGEROUS_CSS_RE = re.compile(
    r"@import\b|expression\s*\(|javascript\s*:|vbscript\s*:|-moz-binding\s*:|behavior\s*:",
    re.IGNORECASE,
)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)


def _local_name(tag_or_attr: str) -> str:
    if "}" in tag_or_attr:
        return tag_or_attr.split("}", 1)[1]
    if ":" in tag_or_attr:
        return tag_or_attr.split(":", 1)[1]
    return tag_or_attr


def _sanitize_css_value(raw_css: str) -> str:
    cleaned = _DANGEROUS_CSS_RE.sub("", raw_css)

    def _replace_url(match: re.Match[str]) -> str:
        target = match.group(2).strip()
        if _INTERNAL_FRAGMENT_RE.fullmatch(target):
            return f"url({target})"
        return "none"

    return _CSS_URL_RE.sub(_replace_url, cleaned)


def _sanitize_element_tree(elem: ET.Element) -> None:
    children_to_remove: list[ET.Element] = []
    for child in list(elem):
        if not isinstance(child.tag, str):
            children_to_remove.append(child)
            continue
        local_tag = _local_name(child.tag).lower()
        if local_tag not in _ALLOWED_SVG_TAGS:
            children_to_remove.append(child)
            continue
        _sanitize_element_tree(child)

    for dead in children_to_remove:
        elem.remove(dead)

    local_self = _local_name(elem.tag).lower() if isinstance(elem.tag, str) else ""
    if local_self == "style":
        if elem.text:
            elem.text = _sanitize_css_value(elem.text)

    sanitized_attrs: dict[str, str] = {}
    for attr_key, attr_val in elem.attrib.items():
        local_attr = _local_name(attr_key).lower()
        if local_attr.startswith("on"):
            continue
        val = (attr_val or "").strip()
        if local_attr == "href":
            if not _INTERNAL_FRAGMENT_RE.fullmatch(val):
                continue
            sanitized_attrs[attr_key] = val
            continue
        if local_attr == "style":
            safe_style = _sanitize_css_value(val).strip()
            if safe_style:
                sanitized_attrs[attr_key] = safe_style
            continue
        if "url(" in val.lower():
            val = _sanitize_css_value(val)
        if re.search(r"(?:javascript|vbscript|data)\s*:", val, re.IGNORECASE):
            continue
        sanitized_attrs[attr_key] = val

    elem.attrib.clear()
    elem.attrib.update(sanitized_attrs)


def sanitize_svg_bytes(content: bytes) -> bytes:
    """Validate and sanitize untrusted SVG bytes, stripping scripts, XXE, foreignObject and external URLs."""
    if not content:
        raise ProviderError("Le fichier SVG reçu est vide.")
    if len(content) > _MAX_SVG_BYTES:
        raise ProviderError("Le fichier SVG dépasse la limite de 10 Mio.")
    if b"\x00" in content:
        raise ProviderError("Le fichier SVG contient des octets invalides.")

    try:
        text = content.decode("utf-8-sig").strip()
    except UnicodeDecodeError:
        raise ProviderError("Le fichier SVG n'est pas encodé en UTF-8 valide.") from None

    if _FORBIDDEN_HEADER_RE.search(text):
        raise ProviderError("Le fichier SVG contient des déclarations DTD ou entités XML interdites.")

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise ProviderError("Le fichier renvoyé n'est pas un document SVG/XML valide.") from None

    if not isinstance(root.tag, str) or _local_name(root.tag).lower() != "svg":
        raise ProviderError("Le document XML reçu n'a pas de racine <svg>.")

    if not root.tag.startswith("{"):
        root.tag = f"{{{_SVG_NS}}}svg"
    _sanitize_element_tree(root)

    serialized = ET.tostring(root, encoding="unicode", method="xml")
    return ('<?xml version="1.0" encoding="utf-8"?>\n' + serialized).encode("utf-8")
