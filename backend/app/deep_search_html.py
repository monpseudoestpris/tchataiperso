"""
deep_search_html — Générateur de page HTML autonome et stylisée pour les rapports DeepSearch.

Produit un document HTML complet, élégant, responsive, typographiquement soigné
(façon blog/publication d'actualité et d'analyse technique type Substack/Medium/The Verge),
avec navigation, sommaire dynamique, citations interactives, encarts de sources et styles d'impression.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any
from urllib.parse import urlsplit


def slugify(text: str) -> str:
    """Produit un slug ASCII propre pour les ancres HTML."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[\s_]+", "-", cleaned)


def estimate_reading_time_minutes(text: str) -> int:
    """Estime le temps de lecture en minutes (environ 200 mots/min)."""
    words = len(re.findall(r"\w+", text))
    return max(1, round(words / 200))


def extract_domain(url: str) -> str:
    """Extrait le nom d'hôte propre d'une URL."""
    try:
        host = urlsplit(url).netloc
        return host.replace("www.", "") if host else url
    except Exception:
        return url


def markdown_to_html(md_text: str, sources: list[dict[str, Any]] | None = None) -> tuple[str, list[dict[str, str]]]:
    """
    Convertit un texte Markdown en HTML riche et sécurisé,
    en extrayant la table des matières (TOC) et en liant les citations [1], [2] aux sources.
    """
    sources = sources or []
    lines = md_text.split("\n")
    toc: list[dict[str, str]] = []
    html_lines: list[str] = []
    
    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []
    
    in_list: str | None = None  # "ul" ou "ol"
    in_table = False
    table_headers: list[str] = []
    table_rows: list[list[str]] = []

    def close_list():
        nonlocal in_list
        if in_list:
            html_lines.append(f"</{in_list}>")
            in_list = None

    def close_table():
        nonlocal in_table, table_headers, table_rows
        if in_table:
            t_html = ['<div class="report-table-wrapper"><table class="report-table">']
            if table_headers:
                t_html.append("<thead><tr>")
                for th in table_headers:
                    t_html.append(f"<th>{inline_formatting(th)}</th>")
                t_html.append("</tr></thead>")
            if table_rows:
                t_html.append("<tbody>")
                for row in table_rows:
                    t_html.append("<tr>")
                    for td in row:
                        t_html.append(f"<td>{inline_formatting(td)}</td>")
                    t_html.append("</tr>")
                t_html.append("</tbody>")
            t_html.append("</table></div>")
            html_lines.append("".join(t_html))
            in_table = False
            table_headers = []
            table_rows = []

    def inline_formatting(text: str) -> str:
        # Échappement HTML sécurisé
        escaped = html.escape(text)

        # Code en ligne `code`
        escaped = re.sub(r"`([^`]+)`", r'<code class="inline-code">\1</code>', escaped)

        # Gras **texte** ou __texte__
        escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)

        # Italique *texte* ou _texte_
        escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
        escaped = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", escaped)

        # Liens [texte](url)
        escaped = re.sub(
            r'\[([^\]]+)\]\((https?://[^)]+)\)',
            r'<a href="\2" target="_blank" rel="noopener noreferrer" class="report-link">\1 <svg class="external-icon" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>',
            escaped,
        )

        # Citations de sources [1], [2], [1, 2], [1-3]
        def replace_citations(match: re.Match) -> str:
            raw_nums = match.group(1)
            # Découper par virgule ou espace
            parts = re.split(r"[,;\s]+", raw_nums.strip())
            badges = []
            for p in parts:
                if "-" in p:
                    subparts = p.split("-")
                    if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                        badges.append(
                            f'<a href="#source-{subparts[0]}" class="report-cite-chip" title="Sources {p}">{p}</a>'
                        )
                        continue
                if p.isdigit():
                    num = int(p)
                    source_title = ""
                    if sources and 1 <= num <= len(sources):
                        source_title = html.escape(sources[num - 1].get("title") or "")
                    tip = f' title="Source {num} : {source_title}"' if source_title else f' title="Voir source {num}"'
                    badges.append(f'<a href="#source-{num}" class="report-cite-chip"{tip}>[{num}]</a>')
                else:
                    return match.group(0)
            return " ".join(badges)

        escaped = re.sub(r"\[(\d+(?:[,\s-]+\d+)*)\]", replace_citations, escaped)

        return escaped

    i = 0
    slug_counts: dict[str, int] = {}
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Bloc de code ```
        if stripped.startswith("```"):
            if in_code_block:
                close_list()
                close_table()
                code_content = html.escape("\n".join(code_lines))
                lang_label = html.escape(code_lang or "code")
                html_lines.append(
                    f'<div class="code-block-container">'
                    f'<div class="code-block-header"><span>{lang_label}</span>'
                    f'<button type="button" class="code-copy-btn" onclick="copyCode(this)" title="Copier ce bloc">'
                    f'Copier</button></div>'
                    f'<pre><code class="language-{lang_label}">{code_content}</code></pre></div>'
                )
                in_code_block = False
                code_lang = ""
                code_lines = []
            else:
                close_list()
                close_table()
                in_code_block = True
                code_lang = stripped[3:].strip().split()[0] if len(stripped) > 3 else ""
                code_lines = []
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Ligne vide
        if not stripped:
            close_list()
            close_table()
            i += 1
            continue

        # Séparateur horizontal ---
        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", stripped):
            close_list()
            close_table()
            html_lines.append('<hr class="report-divider" />')
            i += 1
            continue

        # Titres #, ##, ###, ####
        header_match = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if header_match:
            close_list()
            close_table()
            level = len(header_match.group(1))
            title_text = header_match.group(2).strip()
            # Nettoyer pour l'ancre
            clean_anchor = slugify(title_text) or f"section-{len(toc) + 1}"
            slug_counts[clean_anchor] = slug_counts.get(clean_anchor, 0) + 1
            if slug_counts[clean_anchor] > 1:
                clean_anchor = f"{clean_anchor}-{slug_counts[clean_anchor]}"

            toc.append({"level": str(level), "text": title_text, "anchor": clean_anchor})
            formatted_title = inline_formatting(title_text)
            html_lines.append(
                f'<h{level} id="{clean_anchor}" class="report-heading report-heading-{level}">'
                f'<a href="#{clean_anchor}" class="heading-anchor-link" aria-hidden="true">#</a> '
                f'{formatted_title}'
                f'</h{level}>'
            )
            i += 1
            continue

        # Table Markdown (| col | col |)
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            close_list()
            # Vérifier si la ligne suivante est un séparateur |---|---|
            if not in_table and i + 1 < len(lines):
                next_stripped = lines[i + 1].strip()
                if re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", next_stripped):
                    in_table = True
                    table_headers = [cell.strip() for cell in stripped.strip("|").split("|")]
                    i += 2  # Sauter l'en-tête et le séparateur
                    continue
            if in_table:
                row_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                table_rows.append(row_cells)
                i += 1
                continue

        # Si on sort d'une table
        if in_table:
            close_table()

        # Citations blockquote >
        if stripped.startswith(">"):
            close_list()
            close_table()
            quote_text = stripped.lstrip("> ").strip()
            html_lines.append(f'<blockquote class="report-blockquote"><p>{inline_formatting(quote_text)}</p></blockquote>')
            i += 1
            continue

        # Listes à puces * ou -
        ul_match = re.match(r"^[\*\-]\s+(.+)$", stripped)
        if ul_match:
            close_table()
            if in_list != "ul":
                close_list()
                html_lines.append('<ul class="report-list">')
                in_list = "ul"
            html_lines.append(f"<li>{inline_formatting(ul_match.group(1))}</li>")
            i += 1
            continue

        # Listes ordonnées 1. ou 2.
        ol_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ol_match:
            close_table()
            if in_list != "ol":
                close_list()
                html_lines.append('<ol class="report-ordered-list">')
                in_list = "ol"
            html_lines.append(f"<li>{inline_formatting(ol_match.group(1))}</li>")
            i += 1
            continue

        # Fin de liste si la ligne courante n'est pas un élément de liste
        close_list()

        # Paragraphe standard
        html_lines.append(f'<p class="report-paragraph">{inline_formatting(stripped)}</p>')
        i += 1

    close_list()
    close_table()

    # Si le bloc de code n'a pas été fermé
    if in_code_block:
        code_content = html.escape("\n".join(code_lines))
        lang_label = html.escape(code_lang or "code")
        html_lines.append(
            f'<div class="code-block-container">'
            f'<div class="code-block-header"><span>{lang_label}</span>'
            f'<button type="button" class="code-copy-btn" onclick="copyCode(this)">Copier</button></div>'
            f'<pre><code class="language-{lang_label}">{code_content}</code></pre></div>'
        )

    return "\n".join(html_lines), toc


def generate_report_html(
    title: str,
    topic: str,
    markdown_content: str,
    sources: list[dict[str, Any]],
    created_at_str: str = "",
) -> str:
    """Génère un document HTML complet, autonome et haut de gamme pour le rapport DeepSearch."""
    sources = sources or []
    reading_time = estimate_reading_time_minutes(markdown_content)
    body_html, toc = markdown_to_html(markdown_content, sources)
    clean_title = title.strip() or "Rapport d'analyse approfondie DeepSearch"
    clean_topic = topic.strip() or clean_title

    # Construction du Sommaire (TOC)
    toc_html_parts = []
    if toc:
        toc_html_parts.append('<div class="report-toc-card">')
        toc_html_parts.append('<div class="report-toc-header">')
        toc_html_parts.append('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>')
        toc_html_parts.append('<span>Sommaire du rapport</span>')
        toc_html_parts.append('</div>')
        toc_html_parts.append('<nav class="report-toc-list">')
        for item in toc:
            indent_class = f"toc-level-{item['level']}"
            toc_html_parts.append(
                f'<a href="#{item["anchor"]}" class="report-toc-link {indent_class}">'
                f'<span>{html.escape(item["text"])}</span>'
                f'</a>'
            )
        toc_html_parts.append('</nav></div>')
    toc_html = "".join(toc_html_parts)

    # Construction de la section des sources
    sources_html_parts = []
    if sources:
        sources_html_parts.append('<section id="bibliography-sources" class="report-sources-section">')
        sources_html_parts.append('<div class="report-sources-header">')
        sources_html_parts.append('<h2>')
        sources_html_parts.append(f'<span class="sources-icon">🌐</span> Sources et références bibliographiques ({len(sources)})')
        sources_html_parts.append('</h2>')
        sources_html_parts.append(f'<p>Toutes les affirmations factuelles du rapport ci-dessus sont adossées aux extraits et domaines recensés ci-dessous lors de l’exploration web.</p>')
        sources_html_parts.append('</div>')
        sources_html_parts.append('<div class="report-sources-grid">')

        for idx, src in enumerate(sources, start=1):
            s_title = html.escape(src.get("title") or f"Source {idx}")
            s_url = html.escape(src.get("url") or "#")
            s_domain = html.escape(extract_domain(src.get("url") or ""))
            s_snippet = html.escape(src.get("snippet") or "")
            s_provider = html.escape(src.get("provider") or "web")

            sources_html_parts.append(
                f'<article id="source-{idx}" class="source-card">'
                f'<div class="source-card-top">'
                f'<span class="source-index">#{idx}</span>'
                f'<span class="source-domain">{s_domain}</span>'
                f'<span class="source-provider-badge">{s_provider}</span>'
                f'</div>'
                f'<h3 class="source-title">'
                f'<a href="{s_url}" target="_blank" rel="noopener noreferrer">{s_title} '
                f'<svg class="external-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>'
                f'</a>'
                f'</h3>'
            )
            if s_snippet:
                sources_html_parts.append(f'<p class="source-snippet">« {s_snippet} »</p>')
            sources_html_parts.append(
                f'<div class="source-card-bottom">'
                f'<a href="{s_url}" target="_blank" rel="noopener noreferrer" class="source-direct-link">Consulter la page source originale &rarr;</a>'
                f'</div>'
                f'</article>'
            )

        sources_html_parts.append('</div></section>')
    sources_html = "".join(sources_html_parts)

    escaped_title = html.escape(clean_title)
    escaped_topic = html.escape(clean_topic)
    date_display = html.escape(created_at_str or "Date de génération récente")

    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escaped_title} — Rapport DeepSearch</title>
  <meta name="description" content="Rapport d'analyse approfondie DeepSearch : {escaped_topic}" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Lora:ital,wght@0,400;0,600;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-serif: 'Lora', Georgia, serif;
      --font-mono: 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      
      --bg-page: #0b0f19;
      --bg-card: #111827;
      --bg-card-subtle: #172236;
      --bg-hero: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
      --border-color: rgba(255, 255, 255, 0.1);
      --border-accent: rgba(56, 189, 248, 0.35);
      
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --text-heading: #ffffff;
      
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --primary-glow: rgba(56, 189, 248, 0.15);
      --accent: #818cf8;
      --accent-badge: rgba(99, 102, 241, 0.18);
      --accent-badge-border: rgba(129, 140, 248, 0.3);
      --success: #34d399;
      
      --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.35);
      --shadow-md: 0 8px 30px rgba(0, 0, 0, 0.5);
      --shadow-lg: 0 20px 50px rgba(0, 0, 0, 0.65);
    }}

    html[data-theme="light"] {{
      --bg-page: #f8fafc;
      --bg-card: #ffffff;
      --bg-card-subtle: #f1f5f9;
      --bg-hero: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
      --border-color: rgba(0, 0, 0, 0.08);
      --border-accent: rgba(2, 132, 199, 0.3);
      
      --text-main: #1e293b;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      --text-heading: #0f172a;
      
      --primary: #0284c7;
      --primary-hover: #0369a1;
      --primary-glow: rgba(2, 132, 199, 0.12);
      --accent: #4f46e5;
      --accent-badge: rgba(79, 70, 229, 0.08);
      --accent-badge-border: rgba(79, 70, 229, 0.2);
      
      --shadow-sm: 0 2px 6px rgba(0, 0, 0, 0.05);
      --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.08);
      --shadow-lg: 0 20px 40px rgba(0, 0, 0, 0.12);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: var(--font-sans);
      background-color: var(--bg-page);
      color: var(--text-main);
      line-height: 1.72;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      transition: background-color 0.25s ease, color 0.25s ease;
      padding-bottom: 80px;
    }}

    /* Top Sticky Navigation Bar */
    .report-topbar {{
      position: sticky;
      top: 0;
      z-index: 100;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 60px;
      padding: 0 24px;
      background: var(--bg-card);
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow-sm);
    }}

    .topbar-brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 0.95rem;
      letter-spacing: -0.01em;
      color: var(--text-heading);
    }}

    .brand-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: linear-gradient(135deg, #0284c7, #6366f1);
      color: #fff;
    }}

    .topbar-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .nav-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 13px;
      border-radius: 7px;
      font-size: 0.82rem;
      font-weight: 600;
      font-family: inherit;
      cursor: pointer;
      border: 1px solid var(--border-color);
      background: var(--bg-card-subtle);
      color: var(--text-main);
      transition: all 0.18s ease;
    }}

    .nav-btn:hover {{
      border-color: var(--primary);
      color: var(--primary);
      transform: translateY(-1px);
    }}

    .nav-btn.primary {{
      background: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
    }}

    .nav-btn.primary:hover {{
      background: var(--primary-hover);
    }}

    /* Article Container Layout */
    .report-container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 40px 24px 0;
    }}

    /* Article Hero */
    .report-hero {{
      margin-bottom: 36px;
      padding: 36px 36px 28px;
      border-radius: 20px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-md);
      position: relative;
      overflow: hidden;
    }}

    .report-hero::after {{
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 4px;
      background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
    }}

    .hero-badge-row {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 18px;
    }}

    .hero-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 11px;
      border-radius: 9999px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      background: var(--accent-badge);
      border: 1px solid var(--accent-badge-border);
      color: var(--accent);
    }}

    .hero-badge.verified {{
      background: rgba(16, 185, 129, 0.15);
      border-color: rgba(16, 185, 129, 0.3);
      color: #34d399;
    }}

    .report-title {{
      font-family: var(--font-sans);
      font-size: 2.25rem;
      font-weight: 800;
      line-height: 1.22;
      letter-spacing: -0.025em;
      color: var(--text-heading);
      margin-bottom: 16px;
    }}

    .hero-topic-box {{
      padding: 14px 18px;
      border-radius: 12px;
      background: var(--bg-card-subtle);
      border-left: 3px solid var(--primary);
      margin-bottom: 22px;
      font-size: 0.92rem;
      color: var(--text-muted);
    }}

    .hero-topic-box strong {{
      color: var(--text-main);
      display: block;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 3px;
    }}

    .hero-meta-bar {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 20px;
      padding-top: 14px;
      border-top: 1px solid var(--border-color);
      font-size: 0.82rem;
      color: var(--text-dim);
    }}

    .meta-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}

    /* Table of contents card */
    .report-toc-card {{
      margin-bottom: 40px;
      padding: 22px 26px;
      border-radius: 14px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
    }}

    .report-toc-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.85rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-dim);
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-color);
    }}

    .report-toc-list {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}

    .report-toc-link {{
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.88rem;
      transition: color 0.15s ease, transform 0.15s ease;
      display: inline-flex;
      align-items: center;
    }}

    .report-toc-link:hover {{
      color: var(--primary);
      transform: translateX(4px);
    }}

    .report-toc-link.toc-level-3 {{
      padding-left: 18px;
      font-size: 0.84rem;
      color: var(--text-dim);
    }}

    .report-toc-link.toc-level-4 {{
      padding-left: 32px;
      font-size: 0.8rem;
      color: var(--text-dim);
    }}

    /* Article Content Typography */
    .report-content {{
      font-size: 1.06rem;
      color: var(--text-main);
      line-height: 1.8;
    }}

    .report-paragraph {{
      margin-bottom: 22px;
    }}

    .report-heading {{
      font-family: var(--font-sans);
      color: var(--text-heading);
      letter-spacing: -0.02em;
      font-weight: 700;
      position: relative;
      scroll-margin-top: 80px;
    }}

    .report-heading-1 {{
      font-size: 1.75rem;
      margin: 44px 0 20px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border-color);
    }}

    .report-heading-2 {{
      font-size: 1.4rem;
      margin: 38px 0 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-color);
    }}

    .report-heading-3 {{
      font-size: 1.18rem;
      margin: 28px 0 12px;
      color: var(--accent);
    }}

    .report-heading-4 {{
      font-size: 1.02rem;
      margin: 20px 0 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-dim);
    }}

    .heading-anchor-link {{
      position: absolute;
      left: -22px;
      color: var(--text-dim);
      text-decoration: none;
      opacity: 0;
      transition: opacity 0.15s;
    }}

    .report-heading:hover .heading-anchor-link {{
      opacity: 0.65;
    }}

    .heading-anchor-link:hover {{
      opacity: 1 !important;
      color: var(--primary);
    }}

    .report-link {{
      color: var(--primary);
      text-decoration: none;
      border-bottom: 1px dotted var(--primary);
      transition: border-bottom-color 0.15s, color 0.15s;
    }}

    .report-link:hover {{
      color: var(--primary-hover);
      border-bottom-style: solid;
    }}

    .external-icon {{
      vertical-align: middle;
      margin-left: 2px;
      opacity: 0.7;
    }}

    /* Citation badge chips: [1], [2] */
    .report-cite-chip {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 1px 6px;
      font-size: 0.72rem;
      font-weight: 700;
      font-family: var(--font-mono);
      color: var(--primary);
      background: var(--primary-glow);
      border: 1px solid var(--border-accent);
      border-radius: 5px;
      text-decoration: none;
      margin: 0 2px;
      vertical-align: 0.25em;
      line-height: 1.2;
      transition: all 0.15s ease;
    }}

    .report-cite-chip:hover {{
      background: var(--primary);
      color: #ffffff;
      transform: translateY(-1px);
      box-shadow: 0 2px 8px var(--primary-glow);
    }}

    /* Blockquotes */
    .report-blockquote {{
      margin: 26px 0;
      padding: 16px 24px;
      border-left: 4px solid var(--accent);
      background: var(--bg-card-subtle);
      border-radius: 0 12px 12px 0;
      font-style: italic;
      color: var(--text-main);
    }}

    .report-blockquote p {{
      margin: 0;
    }}

    /* Lists */
    .report-list, .report-ordered-list {{
      margin: 16px 0 24px 28px;
    }}

    .report-list li, .report-ordered-list li {{
      margin-bottom: 8px;
      padding-left: 4px;
    }}

    /* Dividers */
    .report-divider {{
      border: none;
      border-top: 1px dashed var(--border-color);
      margin: 40px 0;
    }}

    /* Code Blocks */
    .code-block-container {{
      margin: 24px 0;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border-color);
      background: #090d16;
      box-shadow: var(--shadow-sm);
    }}

    .code-block-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 16px;
      background: rgba(255, 255, 255, 0.04);
      border-bottom: 1px solid var(--border-color);
      font-family: var(--font-mono);
      font-size: 0.76rem;
      text-transform: uppercase;
      color: var(--text-dim);
    }}

    .code-copy-btn {{
      background: transparent;
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      border-radius: 5px;
      padding: 2px 8px;
      font-size: 0.72rem;
      cursor: pointer;
      font-family: inherit;
      transition: all 0.15s;
    }}

    .code-copy-btn:hover {{
      color: var(--primary);
      border-color: var(--primary);
    }}

    pre {{
      padding: 16px 20px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 0.88rem;
      line-height: 1.6;
      background: #090d16;
      color: #f1f5f9;
      border-radius: 10px;
      border: 1px solid var(--border-color);
      margin: 24px 0;
      box-shadow: var(--shadow-sm);
    }}
    pre code {{
      background: transparent !important;
      color: inherit;
      padding: 0;
      font-family: inherit;
    }}
    .code-block-container pre {{
      margin: 0;
      border: none;
      border-radius: 0;
      background: transparent;
      color: #f1f5f9;
      box-shadow: none;
    }}

    .inline-code {{
      font-family: var(--font-mono);
      font-size: 0.86em;
      padding: 2px 6px;
      border-radius: 5px;
      background: var(--bg-card-subtle);
      border: 1px solid var(--border-color);
      color: var(--primary);
    }}

    /* Tables */
    .report-table-wrapper {{
      margin: 28px 0;
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
    }}

    .report-table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.92rem;
    }}

    .report-table th {{
      background: var(--bg-card-subtle);
      padding: 12px 16px;
      font-weight: 700;
      color: var(--text-heading);
      border-bottom: 1px solid var(--border-color);
    }}

    .report-table td {{
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-color);
      color: var(--text-main);
    }}

    .report-table tr:last-child td {{
      border-bottom: none;
    }}

    .report-table tr:hover td {{
      background: var(--primary-glow);
    }}

    /* Bibliography & Sources Section */
    .report-sources-section {{
      margin-top: 60px;
      padding-top: 40px;
      border-top: 2px solid var(--border-color);
    }}

    .report-sources-header {{
      margin-bottom: 24px;
    }}

    .report-sources-header h2 {{
      font-size: 1.5rem;
      font-weight: 800;
      color: var(--text-heading);
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }}

    .report-sources-header p {{
      font-size: 0.9rem;
      color: var(--text-dim);
    }}

    .report-sources-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
      gap: 16px;
    }}

    .source-card {{
      padding: 16px;
      border-radius: 12px;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: all 0.2s ease;
      scroll-margin-top: 80px;
    }}

    .source-card:target {{
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--primary-glow);
      background: var(--bg-card-subtle);
    }}

    .source-card:hover {{
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
      border-color: var(--border-accent);
    }}

    .source-card-top {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.72rem;
      font-weight: 700;
    }}

    .source-index {{
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--primary-glow);
      color: var(--primary);
      border: 1px solid var(--border-accent);
      font-family: var(--font-mono);
    }}

    .source-domain {{
      color: var(--text-dim);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      flex: 1;
    }}

    .source-provider-badge {{
      text-transform: uppercase;
      font-size: 0.65rem;
      letter-spacing: 0.05em;
      color: var(--accent);
      background: var(--accent-badge);
      padding: 1px 5px;
      border-radius: 4px;
    }}

    .source-title {{
      font-size: 0.92rem;
      font-weight: 600;
      line-height: 1.35;
    }}

    .source-title a {{
      color: var(--text-heading);
      text-decoration: none;
      display: inline;
    }}

    .source-title a:hover {{
      color: var(--primary);
    }}

    .source-snippet {{
      font-size: 0.8rem;
      color: var(--text-dim);
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      font-style: italic;
    }}

    .source-card-bottom {{
      margin-top: auto;
      padding-top: 8px;
    }}

    .source-direct-link {{
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--primary);
      text-decoration: none;
    }}

    .source-direct-link:hover {{
      text-decoration: underline;
    }}

    /* PDF preview notice banner */
    .pdf-preview-banner {{
      display: none;
      background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
      color: #ffffff;
      padding: 10px 20px;
      font-size: 13px;
      font-weight: 500;
      position: sticky;
      top: 57px;
      z-index: 99;
      box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .pdf-preview-banner.is-active {{
      display: flex;
    }}
    .pdf-preview-banner-text {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pdf-preview-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pdf-preview-btn {{
      background: rgba(255, 255, 255, 0.2);
      border: 1px solid rgba(255, 255, 255, 0.4);
      color: #ffffff;
      padding: 4px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: background 0.15s;
    }}
    .pdf-preview-btn:hover {{
      background: rgba(255, 255, 255, 0.35);
    }}
    .pdf-preview-btn.primary {{
      background: #ffffff;
      color: #4f46e5;
      border-color: #ffffff;
    }}
    .pdf-preview-btn.primary:hover {{
      background: #f1f5f9;
    }}

    /* Footer */
    .report-footer {{
      margin-top: 80px;
      text-align: center;
      font-size: 0.82rem;
      color: var(--text-dim);
      padding-top: 30px;
      border-top: 1px solid var(--border-color);
    }}

    /* Media queries */
    @media (max-width: 768px) {{
      .report-container {{
        padding: 20px 16px 0;
      }}
      .report-hero {{
        padding: 24px 20px;
      }}
      .report-title {{
        font-size: 1.7rem;
      }}
      .report-sources-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    /* Print & Beau PDF Styles */
    @page {{
      size: A4 portrait;
      margin: 16mm 14mm 16mm 14mm;
    }}
    @media print {{
      *, *::before, *::after {{
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }}
      .report-topbar, .pdf-preview-banner, .code-copy-btn, .heading-anchor-link, .source-direct-link {{
        display: none !important;
      }}
      body {{
        background: #ffffff !important;
        color: #0f172a !important;
        padding: 0 !important;
        font-size: 10.5pt !important;
        line-height: 1.6 !important;
      }}
      .report-container {{
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
      }}
      .report-hero {{
        background: #f8fafc !important;
        color: #0f172a !important;
        border: 1.5px solid #e2e8f0 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
        padding: 20px 24px !important;
        margin-bottom: 24px !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .hero-badge {{
        background: #eff6ff !important;
        color: #1e40af !important;
        border: 1px solid #bfdbfe !important;
        font-size: 8pt !important;
        padding: 3px 8px !important;
      }}
      .hero-badge.verified {{
        background: #f0fdf4 !important;
        color: #166534 !important;
        border: 1px solid #bbf7d0 !important;
      }}
      .report-title {{
        color: #0f172a !important;
        font-size: 19pt !important;
        line-height: 1.25 !important;
        margin: 12px 0 !important;
      }}
      .hero-topic-box {{
        background: #ffffff !important;
        color: #334155 !important;
        border: 1px solid #e2e8f0 !important;
        border-left: 4px solid #6366f1 !important;
        padding: 10px 14px !important;
        font-size: 9.5pt !important;
      }}
      .hero-meta-bar {{
        border-top: 1px solid #e2e8f0 !important;
        padding-top: 10px !important;
        font-size: 8.5pt !important;
        color: #64748b !important;
      }}
      h1, h2, h3, h4 {{
        color: #0f172a !important;
        break-after: avoid;
        page-break-after: avoid;
      }}
      h2 {{
        border-bottom: 1.5px solid #e2e8f0 !important;
        padding-bottom: 6px !important;
        margin-top: 26px !important;
      }}
      .report-toc-card {{
        background: #f8fafc !important;
        color: #0f172a !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: none !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .code-block-container {{
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        border-radius: 6px !important;
        box-shadow: none !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .code-block-container pre, .code-block-container code {{
        color: #f8fafc !important;
        background: transparent !important;
      }}
      .source-card {{
        background: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 6px !important;
        box-shadow: none !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .source-index {{
        background: #ede9fe !important;
        color: #4338ca !important;
      }}
      .source-provider-badge {{
        background: #f1f5f9 !important;
        color: #475569 !important;
        border: 1px solid #e2e8f0 !important;
      }}
      .report-cite-chip {{
        background: #ede9fe !important;
        color: #4338ca !important;
        border: 1px solid #c7d2fe !important;
        padding: 1px 6px !important;
        font-size: 8pt !important;
      }}
      .report-table-wrapper table {{
        border-collapse: collapse !important;
        width: 100% !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .report-table-wrapper th {{
        background: #f1f5f9 !important;
        color: #0f172a !important;
        border: 1px solid #cbd5e1 !important;
      }}
      .report-table-wrapper td {{
        border: 1px solid #e2e8f0 !important;
      }}
      .report-footer {{
        border-top: 1px solid #e2e8f0 !important;
        color: #64748b !important;
        font-size: 8pt !important;
        margin-top: 30px !important;
      }}
    }}
  </style>
</head>
<body>

  <!-- Top Sticky Navigation Bar -->
  <header class="report-topbar">
    <div class="topbar-brand">
      <span class="brand-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
        </svg>
      </span>
      <span>cLAIr &bull; Grand Rapport DeepSearch</span>
    </div>
    <div class="topbar-actions">
      <button type="button" class="nav-btn" onclick="toggleTheme()" title="Basculer entre thème sombre et clair">
        <span id="theme-icon">☀️</span> <span id="theme-label">Thème</span>
      </button>
      <button type="button" class="nav-btn" onclick="copyReport()" title="Copier tout le contenu du rapport">
        📋 Copier
      </button>
      <a href="?download=1" class="nav-btn" download title="Télécharger le fichier .html complet">
        📥 Télécharger .html
      </a>
      <button type="button" class="nav-btn primary" onclick="printPdf()" title="Imprimer ou enregistrer en Beau PDF">
        📕 Beau PDF
      </button>
    </div>
  </header>

  <!-- Notice bandeau mode aperçu PDF -->
  <aside id="pdf-banner" class="pdf-preview-banner" role="region" aria-label="Mode Aperçu & Impression PDF">
    <div class="pdf-preview-banner-text">
      <span>📕</span>
      <span><strong>Mode Beau PDF (A4) :</strong> La boîte d'impression s'ouvre pour enregistrer le rapport en PDF avec typographie haute fidélité.</span>
    </div>
    <div class="pdf-preview-actions">
      <button type="button" class="pdf-preview-btn primary" onclick="printPdf()">
        🖨️ Réouvrir impression PDF
      </button>
      <a href="?" class="pdf-preview-btn">
        🌐 Revenir au site HTML interactif
      </a>
    </div>
  </aside>

  <main class="report-container">
    <!-- Hero Article Card -->
    <header class="report-hero">
      <div class="hero-badge-row">
        <span class="hero-badge">Rapport d'Investigation Approfondie</span>
        <span class="hero-badge verified">✓ {len(sources)} sources analysées & croisées</span>
        <span class="hero-badge">Mode Publication Blog</span>
      </div>

      <h1 class="report-title">{escaped_title}</h1>

      <div class="hero-topic-box">
        <strong>Question cible de l'investigation</strong>
        « {escaped_topic} »
      </div>

      <div class="hero-meta-bar">
        <div class="meta-item">
          <span>📅 {date_display}</span>
        </div>
        <div class="meta-item">
          <span>⏱️ Lecture estimée : {reading_time} min</span>
        </div>
        <div class="meta-item">
          <span>🤖 Agent StateGraph 5 étapes (cLAIr DeepSearch)</span>
        </div>
      </div>
    </header>

    <!-- Table of Contents (Sommaire) -->
    {toc_html}

    <!-- Main Synthesized Content Body -->
    <article class="report-content" id="report-main-article">
      {body_html}
    </article>

    <!-- Sources & Bibliography -->
    {sources_html}

    <footer class="report-footer">
      <p>Rapport d'analyse généré automatiquement par <strong>cLAIr DeepSearch</strong> via exploration internationale SearXNG et synthèse multi-sources.</p>
    </footer>
  </main>

  <script>
    function printPdf() {{
      window.print();
    }}

    function toggleTheme() {{
      const html = document.documentElement;
      const current = html.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      const icon = document.getElementById('theme-icon');
      if (icon) icon.textContent = next === 'dark' ? '☀️' : '🌙';
    }}

    function copyCode(btn) {{
      const pre = btn.closest('.code-block-container').querySelector('code');
      if (!pre) return;
      navigator.clipboard.writeText(pre.innerText).then(() => {{
        const oldText = btn.innerText;
        btn.innerText = 'Copié !';
        setTimeout(() => {{ btn.innerText = oldText; }}, 2000);
      }});
    }}

    function copyReport() {{
      const article = document.getElementById('report-main-article');
      if (!article) return;
      navigator.clipboard.writeText(article.innerText).then(() => {{
        alert('Contenu du rapport copié dans le presse-papier !');
      }});
    }}

    // Détection automatique du paramètre ?pdf=1 ou ?print=1
    window.addEventListener('DOMContentLoaded', () => {{
      const params = new URLSearchParams(window.location.search);
      if (params.get('pdf') === '1' || params.get('print') === '1') {{
        const banner = document.getElementById('pdf-banner');
        if (banner) banner.classList.add('is-active');
        setTimeout(() => {{
          window.print();
        }}, 450);
      }}
    }});
  </script>
</body>
</html>"""
