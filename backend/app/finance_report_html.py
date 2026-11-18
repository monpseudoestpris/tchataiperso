"""Formateur HTML institutionnel coloré (sans XSS) pour les analyses IA et avis d'experts."""

from __future__ import annotations

import datetime
import html
import re
from typing import Any

_VERDICT_RE = re.compile(
    r"(?:D[eé]cision(?:\s+analytique)?|Verdict(?:\s+global)?|Positionnement(?:\s+final)?|Recommandation)"
    r"\s*\*?\*?\s*:\s*\*?\*?\s*([^\n|*]+)",
    re.IGNORECASE,
)
_CONVICTION_RE = re.compile(
    r"Conviction\s*\*?\*?\s*:\s*\*?\*?\s*`?(\d+(?:[.,]\d+)?\s*/\s*10)`?",
    re.IGNORECASE,
)
_HORIZON_RE = re.compile(
    r"Horizon(?:\s+d['’]?investissement)?\s*\*?\*?\s*:\s*\*?\*?\s*([^\n|*·]+)",
    re.IGNORECASE,
)
_SAFE_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_UNSAFE_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!https?://)[^)]+\)")
_INLINE_TOKEN_RE = re.compile(
    r"(`[^`]+`|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*|\[[^\]]+\]\([^)]+\))"
)
_PCT_TOKEN_RE = re.compile(r"(?<![\w/])([+-]\d+(?:[.,]\d+)?\s*%)(?![\w/])")
_SCORE_TOKEN_RE = re.compile(r"\b(\d+(?:[.,]\d+)?\s*/\s*(?:10|100|9))\b")

_BULL_WORDS = (
    "achat fort",
    "achat",
    "accumuler",
    "renforcer",
    "sous-évalué",
    "solide",
    "haussier",
    "haussière",
    "irrésistible",
    "large (wide)",
    "wide",
    "favorable",
    "excellent",
)
_BEAR_WORDS = (
    "vente",
    "vendre",
    "éviter",
    "surévalué",
    "critique",
    "danger",
    "red flag",
    "baissier",
    "baissière",
    "fragile",
    "négatif",
    "aucun (none)",
)
_HOLD_WORDS = (
    "conserver",
    "attendre",
    "neutre",
    "modéré",
    "vigilance",
    "prudence",
    "étroit (narrow)",
    "narrow",
)


def _safe_accent(accent: str | None) -> str:
    clean = (accent or "").strip()
    return clean if _SAFE_HEX_RE.match(clean) else "#10b981"


def _strip_md_noise(raw: str) -> str:
    txt = raw.strip().strip("*`_ ")
    txt = re.sub(r"\s+", " ", txt)
    return txt[:80]


def extract_report_highlights(markdown: str) -> dict[str, str]:
    """Extrait verdict, conviction (sur 10) et horizon depuis une réponse Markdown."""
    text = markdown or ""
    verdict = ""
    conviction = ""
    horizon = ""

    m_v = _VERDICT_RE.search(text)
    if m_v:
        verdict = _strip_md_noise(m_v.group(1)).split("·")[0].strip(" .:-")
        verdict = re.sub(r"\s*\([^)]{30,}\)$", "", verdict).strip()

    m_c = _CONVICTION_RE.search(text)
    if m_c:
        conviction = re.sub(r"\s+", "", m_c.group(1)).replace(",", ".")

    m_h = _HORIZON_RE.search(text)
    if m_h:
        horizon = _strip_md_noise(m_h.group(1)).strip(" .:-")

    return {
        "verdict": verdict[:72],
        "conviction": conviction[:16],
        "horizon": horizon[:48],
    }


def classify_verdict_tone(verdict: str) -> str:
    """Retourne le ton sémantique ('bull' | 'hold' | 'bear' | 'neutral') du verdict."""
    low = (verdict or "").lower()
    if any(w in low for w in _BEAR_WORDS):
        return "bear"
    if any(w in low for w in _BULL_WORDS):
        return "bull"
    if any(w in low for w in _HOLD_WORDS):
        return "hold"
    return "neutral"


def _conviction_pct(conviction: str) -> int | None:
    m = re.search(r"(\d+(?:\.\d+)?)/10", conviction or "")
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    return max(0, min(100, round(val * 10)))


def _classify_section_tone(title: str) -> tuple[str, str]:
    low = title.lower()
    if any(k in low for k in ("séduit", "haussi", "force", "avantage", "moat", "atout", "positif")):
        return "bull", "▲"
    if any(k in low for k in ("hésit", "risque", "red flag", "faiblesse", "menace", "refus", "vigilance", "baissi", "alerte")):
        return "bear", "⚠"
    if any(k in low for k in ("tableau", "métrique", "crible", "chiffre", "valoris", "ratio", "bilan", "cash", "rentab", "marge")):
        return "metrics", "▤"
    if any(k in low for k in ("seuil", "plan", "action", "catalys", "scénario", "conclusion", "allocation")):
        return "action", "◎"
    if any(k in low for k in ("verdict", "décision", "conviction", "synthèse", "identité", "résumé")):
        return "verdict", "★"
    return "info", "◆"


def _format_date_fr(iso_str: str | None) -> str:
    if not iso_str:
        return ""
    try:
        clean = iso_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(clean)
        months = [
            "janv.", "févr.", "mars", "avr.", "mai", "juin",
            "juil.", "août", "sept.", "oct.", "nov.", "déc.",
        ]
        m = months[dt.month - 1]
        return f"{dt.day:02d} {m} {dt.year} · {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return html.escape(iso_str[:16])


def _render_plain_with_highlights(escaped: str, *, highlight_numbers: bool = True) -> str:
    if not highlight_numbers:
        return escaped
    out = _PCT_TOKEN_RE.sub(
        lambda m: (
            f'<span class="clair-rep-pos">{m.group(1)}</span>'
            if m.group(1).startswith("+")
            else f'<span class="clair-rep-neg">{m.group(1)}</span>'
        ),
        escaped,
    )
    out = _SCORE_TOKEN_RE.sub(r'<span class="clair-rep-score-inline">\1</span>', out)
    return out


def _render_inline(raw: str, *, highlight_numbers: bool = True) -> str:
    parts: list[str] = []
    pos = 0
    for match in _INLINE_TOKEN_RE.finditer(raw):
        if match.start() > pos:
            chunk = html.escape(raw[pos:match.start()], quote=True)
            parts.append(_render_plain_with_highlights(chunk, highlight_numbers=highlight_numbers))
        tok = match.group(0)
        if tok.startswith("`") and tok.endswith("`"):
            inner = html.escape(tok[1:-1], quote=True)
            parts.append(f'<code class="clair-rep-chip">{inner}</code>')
        elif tok.startswith("**") and tok.endswith("**"):
            inner = html.escape(tok[2:-2], quote=True)
            parts.append(f'<strong class="clair-rep-strong">{inner}</strong>')
        elif tok.startswith("*") and tok.endswith("*"):
            inner = html.escape(tok[1:-1], quote=True)
            parts.append(f"<em>{inner}</em>")
        else:
            m_link = _MD_LINK_RE.fullmatch(tok)
            if m_link:
                label = html.escape(m_link.group(1), quote=True)
                href = html.escape(m_link.group(2), quote=True)
                parts.append(
                    f'<a class="clair-rep-link" href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>'
                )
            else:
                m_unsafe = _UNSAFE_MD_LINK_RE.fullmatch(tok)
                if m_unsafe:
                    parts.append(html.escape(m_unsafe.group(1), quote=True))
                else:
                    parts.append(html.escape(tok, quote=True))
        pos = match.end()
    if pos < len(raw):
        chunk = html.escape(raw[pos:], quote=True)
        parts.append(_render_plain_with_highlights(chunk, highlight_numbers=highlight_numbers))
    return "".join(parts)


def _decorate_table_cell(raw_cell: str) -> str:
    rendered = _render_inline(raw_cell.strip(), highlight_numbers=True)
    plain = _strip_md_noise(raw_cell).lower()
    if len(plain) <= 36:
        if any(w in plain for w in _BEAR_WORDS):
            return f'<span class="clair-rep-cell-pill is-bear">{rendered}</span>'
        if any(w in plain for w in _BULL_WORDS):
            return f'<span class="clair-rep-cell-pill is-bull">{rendered}</span>'
        if any(w in plain for w in _HOLD_WORDS):
            return f'<span class="clair-rep-cell-pill is-hold">{rendered}</span>'
    return rendered


def _split_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [c.strip() for c in trimmed.split("|")]


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if "|" not in s:
        return False
    cells = _split_table_row(s)
    return bool(cells) and all(bool(re.fullmatch(r":?-{2,}:?", c.replace(" ", ""))) for c in cells)


def _render_blocks_to_html(lines: list[str]) -> str:
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            lang = html.escape(stripped[3:].strip(), quote=True)
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(html.escape(lines[i], quote=True))
                i += 1
            i += 1
            lang_attr = f' data-lang="{lang}"' if lang else ""
            out.append(f'<pre class="clair-rep-pre"{lang_attr}><code>' + "\n".join(code_lines) + "</code></pre>")
            continue

        if re.fullmatch(r"[-*_]{3,}", stripped):
            out.append('<hr class="clair-rep-hr" />')
            i += 1
            continue

        m_sub = re.match(r"^(#{4,6})\s+(.+)$", stripped)
        if m_sub:
            out.append(f'<h4 class="clair-rep-h4">{_render_inline(m_sub.group(2))}</h4>')
            i += 1
            continue

        # Tableaux Markdown
        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            headers = _split_table_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i].strip() and lines[i].strip():
                rows.append(_split_table_row(lines[i]))
                i += 1
            th_html = "".join(f"<th>{_render_inline(h, highlight_numbers=False)}</th>" for h in headers)
            body_rows: list[str] = []
            for row in rows:
                padded = row + [""] * max(0, len(headers) - len(row))
                tds = "".join(f"<td>{_decorate_table_cell(c)}</td>" for c in padded[: len(headers)])
                body_rows.append(f"<tr>{tds}</tr>")
            out.append(
                '<div class="clair-rep-table-wrap"><table class="clair-rep-table">'
                f"<thead><tr>{th_html}</tr></thead>"
                f"<tbody>{''.join(body_rows)}</tbody>"
                "</table></div>"
            )
            continue

        # Citations > ...
        if stripped.startswith(">"):
            q_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                q_lines.append(_render_inline(lines[i].strip().lstrip(">").strip()))
                i += 1
            out.append(f'<blockquote class="clair-rep-quote">{"<br/>".join(q_lines)}</blockquote>')
            continue

        # Listes à puces ou numérotées
        m_ul = re.match(r"^[-*+•]\s+(.+)$", stripped)
        m_ol = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if m_ul or m_ol:
            is_ordered = bool(m_ol)
            tag = "ol" if is_ordered else "ul"
            cls = "clair-rep-list is-ordered" if is_ordered else "clair-rep-list"
            items: list[str] = []
            while i < n:
                cur = lines[i].strip()
                m_item = re.match(r"^\d+[.)]\s+(.+)$", cur) if is_ordered else re.match(r"^[-*+•]\s+(.+)$", cur)
                if not m_item:
                    break
                item_text = m_item.group(1)
                i += 1
                while i < n and lines[i].startswith(("  ", "\t")) and lines[i].strip() and not re.match(r"^[-*+•\d]", lines[i].strip()):
                    item_text += " " + lines[i].strip()
                    i += 1
                items.append(f"<li>{_render_inline(item_text)}</li>")
            out.append(f'<{tag} class="{cls}">{"".join(items)}</{tag}>')
            continue

        # Paragraphe normal
        para_lines: list[str] = []
        while i < n:
            cur = lines[i].strip()
            if (
                not cur
                or cur.startswith("#")
                or cur.startswith(">")
                or cur.startswith("```")
                or re.fullmatch(r"[-*_]{3,}", cur)
                or re.match(r"^[-*+•]\s+", cur)
                or re.match(r"^\d+[.)]\s+", cur)
                or ("|" in cur and i + 1 < n and _is_table_sep(lines[i + 1]))
            ):
                break
            para_lines.append(_render_inline(cur))
            i += 1
        if para_lines:
            out.append(f'<p class="clair-rep-p">{" ".join(para_lines)}</p>')

    return "".join(out)


def build_classy_report_html(
    markdown: str,
    *,
    title: str,
    subtitle: str = "",
    symbol: str = "",
    model: str = "",
    created_at: str = "",
    accent: str = "#10b981",
    badge_label: str = "",
    question: str | None = None,
    monogram: str = "",
) -> str:
    """Transforme un rapport financier Markdown en HTML éditorial coloré, structuré et sans XSS."""
    raw_lines = (markdown or "").splitlines()
    highlights = extract_report_highlights(markdown)
    verdict = highlights["verdict"]
    conviction = highlights["conviction"]
    horizon = highlights["horizon"]
    verdict_tone = classify_verdict_tone(verdict)
    conv_pct = _conviction_pct(conviction)
    safe_accent = _safe_accent(accent)

    # Découpe en sections sur les titres # / ## / ###
    sections: list[tuple[str | None, list[str]]] = []
    cur_title: str | None = None
    cur_lines: list[str] = []
    for line in raw_lines:
        m_head = re.match(r"^#{1,3}\s+(.+)$", line.strip())
        if m_head:
            heading_txt = m_head.group(1).strip()
            if cur_title is not None or any(l.strip() for l in cur_lines):
                sections.append((cur_title, cur_lines))
            cur_title = heading_txt
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_title is not None or any(l.strip() for l in cur_lines):
        sections.append((cur_title, cur_lines))

    # Hero Header
    meta_chips: list[str] = []
    if badge_label:
        meta_chips.append(f'<span class="clair-rep-badge">{html.escape(badge_label)}</span>')
    if symbol:
        meta_chips.append(f'<span class="clair-rep-ticker">{html.escape(symbol)}</span>')
    if model:
        meta_chips.append(f'<span class="clair-rep-model">{html.escape(model)}</span>')
    date_txt = _format_date_fr(created_at)
    if date_txt:
        meta_chips.append(f'<span class="clair-rep-date">🕒 {html.escape(date_txt)}</span>')

    avatar_html = (
        f'<div class="clair-rep-avatar" style="background:{safe_accent}">{html.escape(monogram[:3])}</div>'
        if monogram
        else ""
    )

    verdict_block_parts: list[str] = []
    if verdict:
        verdict_block_parts.append(
            f'<span class="clair-rep-verdict-pill is-{verdict_tone}">{html.escape(verdict)}</span>'
        )
    if conviction:
        bar_html = (
            f'<span class="clair-rep-conv-track"><span class="clair-rep-conv-fill is-{verdict_tone}" style="width:{conv_pct}%"></span></span>'
            if conv_pct is not None
            else ""
        )
        verdict_block_parts.append(
            f'<div class="clair-rep-conv-box"><span class="clair-rep-conv-label">Conviction <strong>{html.escape(conviction)}</strong></span>{bar_html}</div>'
        )
    if horizon:
        verdict_block_parts.append(
            f'<span class="clair-rep-horizon-pill">Horizon : {html.escape(horizon)}</span>'
        )
    right_hero = (
        f'<div class="clair-rep-hero-right">{"".join(verdict_block_parts)}</div>'
        if verdict_block_parts
        else ""
    )

    subtitle_html = (
        f'<p class="clair-rep-hero-sub">{html.escape(subtitle)}</p>'
        if subtitle
        else ""
    )
    question_html = (
        f'<div class="clair-rep-question-banner"><span>Question posée :</span> <strong>« {html.escape(question.strip())} »</strong></div>'
        if question and question.strip()
        else ""
    )

    hero_html = (
        f'<header class="clair-rep-hero">'
        f'<div class="clair-rep-hero-main">{avatar_html}'
        f'<div class="clair-rep-hero-titles">'
        f'<div class="clair-rep-hero-chips">{"".join(meta_chips)}</div>'
        f'<h2 class="clair-rep-hero-title">{html.escape(title)}</h2>'
        f"{subtitle_html}"
        f"</div></div>"
        f"{right_hero}"
        f"{question_html}"
        f"</header>"
    )

    cards_html: list[str] = []
    for idx, (sec_title, sec_lines) in enumerate(sections):
        body = _render_blocks_to_html(sec_lines)
        if not body and not sec_title:
            continue
        if sec_title:
            tone, icon = _classify_section_tone(sec_title)
            title_clean = html.escape(sec_title.strip("* "))
            cards_html.append(
                f'<section class="clair-rep-card is-{tone}">'
                f'<div class="clair-rep-card-head">'
                f'<span class="clair-rep-card-icon">{icon}</span>'
                f'<h3 class="clair-rep-card-title">{title_clean}</h3>'
                f"</div>"
                f'<div class="clair-rep-card-body">{body}</div>'
                f"</section>"
            )
        else:
            cls = "clair-rep-card is-intro" if idx == 0 else "clair-rep-card is-info"
            cards_html.append(f'<section class="{cls}"><div class="clair-rep-card-body">{body}</div></section>')

    return (
        f'<article class="clair-rep-root" style="--rep-accent:{safe_accent}">'
        f"{hero_html}"
        f'<div class="clair-rep-sections">{"".join(cards_html)}</div>'
        f"</article>"
    )
