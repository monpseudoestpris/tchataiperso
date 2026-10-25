"""
chat_export_html — Générateur de document HTML & PDF pour les échanges et conversations du tchat.

Permet d'exporter en Beau site HTML interactif ou en Beau document PDF d'édition (A4) :
1. "Question & Réponse" (scope='turn') : La question posée et la réponse complète de l'assistant.
2. "Synthèse des messages" (scope='conversation') : L'ensemble des échanges chronologiques
   de la discussion avec sommaire, rôles distincts, citations et sources consolidées.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

from .deep_search_html import (
    estimate_reading_time_minutes,
    extract_domain,
    markdown_to_html,
    slugify,
)


def generate_chat_export_html(
    title: str,
    messages: list[dict[str, Any]],
    scope: str = "turn",
    topic: str = "",
    model: str = "",
    created_at_str: str = "",
    summary: str = "",
) -> str:
    """
    Génère un document HTML complet, autonome et prêt pour l'impression PDF (A4)
    pour un échange ponctuel (question & réponse) ou l'ensemble de la discussion.
    """
    clean_title = (title or "").strip() or "Échange cLAIr"
    escaped_title = html.escape(clean_title)
    is_turn_scope = scope == "turn"

    # Calcul des statistiques globales
    total_words = sum(len(re.findall(r"\w+", m.get("content", ""))) for m in messages)
    reading_time = max(1, round(total_words / 200))
    date_display = html.escape(created_at_str or "Date récente")
    model_display = html.escape(model or "Assistant cLAIr")

    # Consolidation des sources
    all_sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for m in messages:
        for s in m.get("sources") or []:
            url = s.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_sources.append(s)

    # Construction du corps principal selon le scope
    if is_turn_scope:
        scope_badge = "Échange · Question & Réponse"
        scope_desc = "Sortie d'un échange ciblé entre l'utilisateur et l'assistant cLAIr."
        
        # Identifier la question utilisateur et la réponse assistant
        user_msg = next((m for m in messages if m.get("role") == "user"), None)
        asst_msg = next((m for m in messages if m.get("role") == "assistant"), None)
        if not asst_msg and messages:
            asst_msg = messages[-1]

        user_content = user_msg.get("content", "").strip() if user_msg else (topic or "Question non spécifiée")
        asst_content = asst_msg.get("content", "").strip() if asst_msg else ""
        asst_sources = asst_msg.get("sources", []) if asst_msg else []
        
        user_date = html.escape(user_msg.get("created_at_str", "") if user_msg else "")
        asst_date = html.escape(asst_msg.get("created_at_str", "") if asst_msg else date_display)

        # Rendu Markdown vers HTML
        user_body_html, _ = markdown_to_html(user_content)
        asst_body_html, asst_toc = markdown_to_html(asst_content, asst_sources)

        # Sommaire interne de la réponse si riche
        toc_html = ""
        if asst_toc:
            toc_html = (
                '<div class="chat-toc-box">'
                '<div class="chat-toc-header">'
                '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>'
                '<span>Plan de la réponse</span>'
                '</div>'
                '<nav class="chat-toc-nav">'
                + "".join(
                    f'<a href="#{item["anchor"]}" class="chat-toc-link toc-level-{item["level"]}">{html.escape(item["text"])}</a>'
                    for item in asst_toc
                )
                + '</nav></div>'
            )

        content_html = f"""
        <section class="chat-turn-exchange">
          <!-- Question Utilisateur -->
          <article class="chat-message-card chat-user-card" id="question">
            <header class="message-card-header">
              <div class="message-role-badge user-badge">
                <span class="role-icon">👤</span>
                <strong>Question de l'utilisateur</strong>
              </div>
              {f'<span class="message-time">{user_date}</span>' if user_date else ''}
            </header>
            <div class="message-card-body">
              {user_body_html}
            </div>
          </article>

          <!-- Réponse Assistant -->
          <article class="chat-message-card chat-asst-card" id="reponse">
            <header class="message-card-header">
              <div class="message-role-badge asst-badge">
                <span class="role-icon">🤖</span>
                <strong>Réponse de l'assistant cLAIr</strong>
              </div>
              <span class="message-time">{asst_date}</span>
            </header>
            {toc_html}
            <div class="message-card-body">
              {asst_body_html}
            </div>
          </article>
        </section>
        """
        active_sources = asst_sources or all_sources
    else:
        # Scope Conversation / Synthèse de tous les messages
        scope_badge = "Transcription & Synthèse de la discussion"
        scope_desc = f"Transcription chronologique intégrale ({len(messages)} messages) avec synthèse et sources."
        active_sources = all_sources

        # Sommaire des tours d'échanges
        turns_summary: list[str] = []
        conversation_cards: list[str] = []
        turn_counter = 0

        for idx, m in enumerate(messages, start=1):
            role = m.get("role", "assistant")
            m_content = m.get("content", "").strip()
            m_date = html.escape(m.get("created_at_str", ""))
            m_sources = m.get("sources") or []

            m_html, _ = markdown_to_html(m_content, m_sources)

            if role == "user":
                turn_counter += 1
                short_q = html.escape(m_content[:70] + ("…" if len(m_content) > 70 else ""))
                turns_summary.append(
                    f'<a href="#echange-{turn_counter}" class="chat-toc-link toc-level-2">'
                    f'<span class="toc-num">#{turn_counter}</span> '
                    f'<span>👤 {short_q}</span>'
                    f'</a>'
                )

                card = f"""
                <article class="chat-message-card chat-user-card" id="echange-{turn_counter}">
                  <header class="message-card-header">
                    <div class="message-role-badge user-badge">
                      <span class="role-icon">👤</span>
                      <strong>Échange #{turn_counter} · Utilisateur</strong>
                    </div>
                    {f'<span class="message-time">{m_date}</span>' if m_date else ''}
                  </header>
                  <div class="message-card-body">
                    {m_html}
                  </div>
                </article>
                """
            else:
                card = f"""
                <article class="chat-message-card chat-asst-card">
                  <header class="message-card-header">
                    <div class="message-role-badge asst-badge">
                      <span class="role-icon">🤖</span>
                      <strong>Assistant cLAIr</strong>
                    </div>
                    {f'<span class="message-time">{m_date}</span>' if m_date else ''}
                  </header>
                  <div class="message-card-body">
                    {m_html}
                  </div>
                </article>
                """
            conversation_cards.append(card)

        # Encart Synthèse de la conversation si disponible
        summary_html = ""
        if summary.strip():
            escaped_sum = html.escape(summary.strip())
            summary_html = f"""
            <aside class="chat-conversation-summary-box">
              <div class="summary-box-title">
                <span class="summary-icon">📋</span>
                <strong>Synthèse de la discussion</strong>
              </div>
              <p class="summary-box-text">{escaped_sum}</p>
            </aside>
            """

        # Sommaire global des échanges
        toc_html = ""
        if turns_summary:
            toc_html = f"""
            <div class="chat-toc-box">
              <div class="chat-toc-header">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
                <span>Sommaire chronologique des échanges ({turn_counter} questions)</span>
              </div>
              <nav class="chat-toc-nav">
                {"".join(turns_summary)}
              </nav>
            </div>
            """

        content_html = f"""
        {summary_html}
        {toc_html}
        <section class="chat-conversation-thread">
          {"".join(conversation_cards)}
        </section>
        """

    # Section Sources bibliographiques
    sources_html = ""
    if active_sources:
        sources_cards = []
        for idx, src in enumerate(active_sources, start=1):
            s_title = html.escape(src.get("title") or f"Source {idx}")
            s_url = html.escape(src.get("url") or "#")
            s_domain = html.escape(extract_domain(src.get("url") or ""))
            s_snippet = html.escape(src.get("snippet") or "")
            s_provider = html.escape(src.get("provider") or "web")

            sources_cards.append(
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
                + (f'<p class="source-snippet">« {s_snippet} »</p>' if s_snippet else '')
                + f'<div class="source-card-bottom">'
                f'<a href="{s_url}" target="_blank" rel="noopener noreferrer" class="source-direct-link">Consulter la ressource &rarr;</a>'
                f'</div>'
                f'</article>'
            )

        sources_html = f"""
        <section id="bibliography-sources" class="report-sources-section">
          <div class="report-sources-header">
            <h2>
              <span class="sources-icon">🌐</span> Sources et références bibliographiques ({len(active_sources)})
            </h2>
            <p>Données et sources externes consultées et croisées lors de cet échange.</p>
          </div>
          <div class="report-sources-grid">
            {"".join(sources_cards)}
          </div>
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escaped_title} — Sortie {scope_badge}</title>
  <meta name="description" content="{escaped_title} : {html.escape(scope_desc)}" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&family=Lora:ital,wght@0,400;0,600;1,400&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-body: #0b0f17;
      --bg-surface: #121824;
      --bg-surface-elevated: #1a2332;
      --bg-card: #151d2c;
      --bg-card-user: #181d33;
      --border-color: #243044;
      --border-user: #4338ca;
      --border-asst: #38bdf8;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent-primary: #6366f1;
      --accent-hover: #4f46e5;
      --accent-glow: rgba(99, 102, 241, 0.25);
      --code-bg: #090d16;
      --quote-border: #6366f1;
      --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      --font-serif: 'Lora', Georgia, Cambria, 'Times New Roman', serif;
      --font-mono: 'Fira Code', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}

    [data-theme="light"] {{
      --bg-body: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #f1f5f9;
      --bg-card: #ffffff;
      --bg-card-user: #f5f3ff;
      --border-color: #e2e8f0;
      --border-user: #c7d2fe;
      --border-asst: #bae6fd;
      --text-main: #0f172a;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      --accent-primary: #4f46e5;
      --accent-hover: #4338ca;
      --accent-glow: rgba(79, 70, 229, 0.15);
      --code-bg: #0f172a;
      --quote-border: #4f46e5;
    }}

    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    html {{
      scroll-behavior: smooth;
      font-size: 16px;
    }}

    body {{
      background-color: var(--bg-body);
      color: var(--text-main);
      font-family: var(--font-sans);
      line-height: 1.68;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      padding-bottom: 80px;
    }}

    /* Topbar de navigation & impression */
    .chat-export-topbar {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(18, 24, 36, 0.88);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-color);
      padding: 10px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    [data-theme="light"] .chat-export-topbar {{
      background: rgba(255, 255, 255, 0.92);
    }}

    .topbar-brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 0.95rem;
      color: var(--text-main);
      text-decoration: none;
    }}
    .topbar-badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 10px;
      border-radius: 9999px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: var(--accent-glow);
      color: var(--accent-primary);
      border: 1px solid var(--accent-primary);
    }}

    .topbar-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .topbar-btn {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 0.82rem;
      font-weight: 600;
      font-family: var(--font-sans);
      cursor: pointer;
      border: 1px solid var(--border-color);
      background: var(--bg-surface-elevated);
      color: var(--text-main);
      transition: all 0.15s ease;
      text-decoration: none;
    }}
    .topbar-btn:hover {{
      background: var(--border-color);
      transform: translateY(-1px);
    }}
    .topbar-btn.primary {{
      background: var(--accent-primary);
      color: #ffffff;
      border-color: var(--accent-primary);
      box-shadow: 0 2px 8px var(--accent-glow);
    }}
    .topbar-btn.primary:hover {{
      background: var(--accent-hover);
    }}

    /* Bandeau d'aperçu PDF sticky */
    .pdf-preview-banner {{
      display: none;
      background: linear-gradient(90deg, #4f46e5, #7c3aed);
      color: #ffffff;
      padding: 10px 24px;
      font-size: 0.88rem;
      font-weight: 600;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      box-shadow: 0 4px 14px rgba(79, 70, 229, 0.4);
    }}
    .pdf-preview-banner.is-active {{
      display: flex;
    }}
    .pdf-banner-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .pdf-banner-btn {{
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.78rem;
      font-weight: 700;
      border: 1px solid rgba(255, 255, 255, 0.4);
      background: rgba(255, 255, 255, 0.15);
      color: #ffffff;
      cursor: pointer;
      text-decoration: none;
    }}
    .pdf-banner-btn:hover {{
      background: rgba(255, 255, 255, 0.28);
    }}

    /* Conteneur principal */
    .chat-export-container {{
      max-width: 900px;
      margin: 0 auto;
      padding: 32px 24px 0;
    }}

    /* En-tête / Hero */
    .chat-export-hero {{
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 16px;
      padding: 30px 32px;
      margin-bottom: 28px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
    }}
    .hero-badges-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .hero-badge {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
      border: 1px solid var(--border-color);
    }}
    .hero-badge.highlight {{
      background: var(--accent-glow);
      color: var(--accent-primary);
      border-color: var(--accent-primary);
    }}
    .chat-export-title {{
      font-size: 2.1rem;
      font-weight: 800;
      line-height: 1.25;
      color: var(--text-main);
      margin-bottom: 16px;
      letter-spacing: -0.02em;
    }}
    .hero-meta-bar {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 18px;
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

    /* Encart Synthèse de la conversation */
    .chat-conversation-summary-box {{
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-left: 4px solid var(--accent-primary);
      border-radius: 10px;
      padding: 18px 22px;
      margin-bottom: 24px;
    }}
    .summary-box-title {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.88rem;
      color: var(--accent-primary);
      margin-bottom: 6px;
    }}
    .summary-box-text {{
      font-size: 0.95rem;
      color: var(--text-main);
      line-height: 1.6;
    }}

    /* Sommaire / TOC */
    .chat-toc-box {{
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 18px 22px;
      margin-bottom: 28px;
    }}
    .chat-toc-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-weight: 700;
      font-size: 0.86rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 12px;
    }}
    .chat-toc-nav {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .chat-toc-link {{
      color: var(--text-muted);
      text-decoration: none;
      font-size: 0.88rem;
      padding: 5px 10px;
      border-radius: 6px;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .chat-toc-link:hover {{
      color: var(--text-main);
      background: var(--bg-surface-elevated);
      padding-left: 14px;
    }}
    .chat-toc-link .toc-num {{
      font-family: var(--font-mono);
      font-size: 0.75rem;
      color: var(--accent-primary);
      font-weight: 700;
    }}
    .chat-toc-link.toc-level-3 {{
      padding-left: 20px;
      font-size: 0.84rem;
    }}

    /* Cartes de messages */
    .chat-turn-exchange, .chat-conversation-thread {{
      display: flex;
      flex-direction: column;
      gap: 22px;
      margin-bottom: 36px;
    }}
    .chat-message-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 24px 28px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
      position: relative;
    }}
    .chat-user-card {{
      background: var(--bg-card-user);
      border-color: var(--border-user);
      border-left: 5px solid #6366f1;
    }}
    .chat-asst-card {{
      border-left: 5px solid #38bdf8;
    }}

    .message-card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border-color);
    }}
    .message-role-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-size: 0.88rem;
      font-weight: 700;
    }}
    .user-badge {{
      color: #818cf8;
    }}
    [data-theme="light"] .user-badge {{
      color: #4338ca;
    }}
    .asst-badge {{
      color: #38bdf8;
    }}
    [data-theme="light"] .asst-badge {{
      color: #0284c7;
    }}
    .message-time {{
      font-size: 0.78rem;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }}

    /* Typographie de contenu */
    .message-card-body {{
      font-size: 1.02rem;
      line-height: 1.72;
      color: var(--text-main);
    }}
    .message-card-body p {{
      margin-bottom: 14px;
    }}
    .message-card-body p:last-child {{
      margin-bottom: 0;
    }}
    .message-card-body h1, .message-card-body h2, .message-card-body h3, .message-card-body h4 {{
      color: var(--text-main);
      font-weight: 700;
      margin-top: 24px;
      margin-bottom: 12px;
      line-height: 1.35;
    }}
    .message-card-body h2 {{
      font-size: 1.35rem;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 6px;
    }}
    .message-card-body h3 {{
      font-size: 1.15rem;
    }}
    .message-card-body ul, .message-card-body ol {{
      margin: 12px 0 16px 24px;
    }}
    .message-card-body li {{
      margin-bottom: 6px;
    }}

    /* Blocs de code & syntaxe */
    .code-block-container {{
      background: var(--code-bg);
      border: 1px solid #1e293b;
      border-radius: 10px;
      margin: 16px 0;
      overflow: hidden;
    }}
    .code-block-header {{
      background: #0f172a;
      padding: 6px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid #1e293b;
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: #94a3b8;
      text-transform: uppercase;
    }}
    .code-copy-btn {{
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #cbd5e1;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.7rem;
      cursor: pointer;
      font-family: var(--font-sans);
    }}
    .code-copy-btn:hover {{
      background: rgba(255, 255, 255, 0.2);
    }}
    pre {{
      padding: 14px 18px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 0.88rem;
      line-height: 1.55;
      color: #f1f5f9;
      background: var(--code-bg);
    }}
    code.inline-code {{
      font-family: var(--font-mono);
      font-size: 0.88em;
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--bg-surface-elevated);
      color: #38bdf8;
      border: 1px solid var(--border-color);
    }}

    /* Tableaux */
    .report-table-wrapper {{
      overflow-x: auto;
      margin: 18px 0;
      border: 1px solid var(--border-color);
      border-radius: 8px;
    }}
    .report-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      text-align: left;
    }}
    .report-table th, .report-table td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-color);
    }}
    .report-table th {{
      background: var(--bg-surface-elevated);
      font-weight: 700;
      color: var(--text-main);
    }}
    .report-table tr:last-child td {{
      border-bottom: none;
    }}

    /* Blockquote */
    .report-blockquote {{
      border-left: 4px solid var(--quote-border);
      background: var(--bg-surface-elevated);
      padding: 12px 18px;
      border-radius: 0 8px 8px 0;
      margin: 14px 0;
      font-style: italic;
      color: var(--text-muted);
    }}

    /* Puces de citations [1] */
    .report-cite-chip {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 5px;
      font-size: 0.74rem;
      font-family: var(--font-mono);
      font-weight: 700;
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.35);
      border-radius: 4px;
      text-decoration: none;
      vertical-align: super;
      margin: 0 2px;
      line-height: 1.3;
    }}

    /* Section Sources bibliographiques */
    .report-sources-section {{
      margin-top: 40px;
      padding-top: 28px;
      border-top: 2px solid var(--border-color);
    }}
    .report-sources-header h2 {{
      font-size: 1.35rem;
      font-weight: 800;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 6px;
    }}
    .report-sources-header p {{
      color: var(--text-muted);
      font-size: 0.88rem;
      margin-bottom: 18px;
    }}
    .report-sources-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 14px;
    }}
    .source-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: all 0.15s ease;
    }}
    .source-card:hover {{
      border-color: var(--accent-primary);
      transform: translateY(-2px);
    }}
    .source-card-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 0.75rem;
      font-family: var(--font-mono);
    }}
    .source-index {{
      font-weight: 700;
      color: var(--accent-primary);
    }}
    .source-domain {{
      color: var(--text-dim);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .source-provider-badge {{
      font-size: 0.65rem;
      text-transform: uppercase;
      padding: 2px 6px;
      border-radius: 4px;
      background: var(--bg-surface-elevated);
      color: var(--text-muted);
    }}
    .source-title {{
      font-size: 0.88rem;
      font-weight: 600;
      line-height: 1.35;
    }}
    .source-title a {{
      color: var(--text-main);
      text-decoration: none;
    }}
    .source-title a:hover {{
      color: var(--accent-primary);
    }}
    .source-snippet {{
      font-size: 0.78rem;
      color: var(--text-muted);
      line-height: 1.4;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .source-direct-link {{
      font-size: 0.75rem;
      color: var(--accent-primary);
      text-decoration: none;
      font-weight: 600;
      margin-top: auto;
    }}

    /* Footer */
    .chat-export-footer {{
      margin-top: 48px;
      padding-top: 20px;
      border-top: 1px solid var(--border-color);
      text-align: center;
      font-size: 0.82rem;
      color: var(--text-dim);
    }}

    /* Impression & PDF Styles */
    @page {{
      size: A4 portrait;
      margin: 16mm 14mm 16mm 14mm;
    }}

    @media print {{
      *, *::before, *::after {{
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }}
      .chat-export-topbar, .pdf-preview-banner, .code-copy-btn, .heading-anchor-link, .source-direct-link {{
        display: none !important;
      }}
      body {{
        background: #ffffff !important;
        color: #0f172a !important;
        padding: 0 !important;
        font-size: 10pt !important;
        line-height: 1.55 !important;
      }}
      .chat-export-container {{
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
      }}
      .chat-export-hero {{
        background: #f8fafc !important;
        color: #0f172a !important;
        border: 1.5px solid #cbd5e1 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
        padding: 16px 20px !important;
        margin-bottom: 18px !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .chat-export-title {{
        color: #0f172a !important;
        font-size: 18pt !important;
        margin-bottom: 10px !important;
      }}
      .hero-badge {{
        background: #e2e8f0 !important;
        color: #1e293b !important;
        border-color: #cbd5e1 !important;
      }}
      .hero-badge.highlight {{
        background: #e0e7ff !important;
        color: #3730a3 !important;
        border-color: #a5b4fc !important;
      }}
      .chat-message-card {{
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        box-shadow: none !important;
        break-inside: avoid;
        page-break-inside: avoid;
        margin-bottom: 14px !important;
        padding: 16px 20px !important;
      }}
      .chat-user-card {{
        background: #f8fafc !important;
        border-left: 4.5px solid #4f46e5 !important;
      }}
      .chat-asst-card {{
        border-left: 4.5px solid #0284c7 !important;
      }}
      .message-card-header {{
        border-bottom: 1px solid #e2e8f0 !important;
      }}
      .user-badge {{
        color: #3730a3 !important;
      }}
      .asst-badge {{
        color: #0369a1 !important;
      }}
      .message-card-body {{
        color: #0f172a !important;
        font-size: 10pt !important;
      }}
      h1, h2, h3, h4 {{
        color: #0f172a !important;
        break-after: avoid;
        page-break-after: avoid;
      }}
      .code-block-container {{
        background: #0f172a !important;
        border: 1px solid #1e293b !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      pre {{
        background: #0f172a !important;
        color: #f8fafc !important;
        font-size: 8.5pt !important;
      }}
      .report-table-wrapper {{
        break-inside: avoid;
        page-break-inside: avoid;
        border: 1px solid #cbd5e1 !important;
      }}
      .report-table th {{
        background: #f1f5f9 !important;
        color: #0f172a !important;
      }}
      .source-card {{
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }}
      .source-title a {{
        color: #0f172a !important;
      }}
    }}
  </style>
</head>
<body>
  <!-- Navigation Topbar -->
  <header class="chat-export-topbar">
    <div class="topbar-brand">
      <span class="topbar-badge">cLAIr Tchat IA</span>
      <span>{escaped_title}</span>
    </div>
    <div class="topbar-actions">
      <button type="button" class="topbar-btn" onclick="toggleTheme()" title="Basculer thème sombre / clair">
        <span id="theme-icon">☀️</span>
        <span>Thème</span>
      </button>
      <button type="button" class="topbar-btn" onclick="copyDocument()" title="Copier le contenu du document">
        <span>📋</span>
        <span>Copier</span>
      </button>
      <button type="button" class="topbar-btn primary" onclick="printPdf()" title="Imprimer ou enregistrer au format Beau PDF d'édition (A4)">
        <span>📕</span>
        <span>Beau PDF</span>
      </button>
    </div>
  </header>

  <!-- Bandeau d'aperçu PDF sticky (déclenché via ?pdf=1) -->
  <aside class="pdf-preview-banner" id="pdf-banner">
    <div>
      <strong>📕 Mode Aperçu & Impression PDF active</strong>
      <span style="opacity: 0.9; margin-left: 8px;">Mise en page d'édition A4 haute fidélité prête.</span>
    </div>
    <div class="pdf-banner-actions">
      <button type="button" class="pdf-banner-btn" onclick="printPdf()">
        🖨️ Réouvrir boîte d'impression
      </button>
      <a href="?" class="pdf-banner-btn">
        🌐 Revenir au site HTML
      </a>
    </div>
  </aside>

  <main class="chat-export-container">
    <!-- Hero / En-tête -->
    <header class="chat-export-hero">
      <div class="hero-badges-row">
        <span class="hero-badge highlight">{scope_badge}</span>
        {f'<span class="hero-badge">✓ {len(active_sources)} sources</span>' if active_sources else ''}
        <span class="hero-badge">Édition cLAIr</span>
      </div>

      <h1 class="chat-export-title">{escaped_title}</h1>

      <div class="hero-meta-bar">
        <div class="meta-item">
          <span>📅 {date_display}</span>
        </div>
        <div class="meta-item">
          <span>⏱️ Lecture estimée : {reading_time} min</span>
        </div>
        <div class="meta-item">
          <span>🤖 {model_display}</span>
        </div>
        <div class="meta-item">
          <span>💬 {len(messages)} message{'s' if len(messages) > 1 else ''}</span>
        </div>
      </div>
    </header>

    <!-- Contenu Principal -->
    <div id="export-main-content">
      {content_html}
    </div>

    <!-- Sources & Références Bibliographiques -->
    {sources_html}

    <footer class="chat-export-footer">
      <p>Document exporté automatiquement par <strong>cLAIr Tchat IA</strong> · {scope_badge} · {date_display}</p>
    </footer>
  </main>

  <script>
    function printPdf() {{
      window.print();
    }}

    function toggleTheme() {{
      const root = document.documentElement;
      const current = root.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      const icon = document.getElementById('theme-icon');
      if (icon) icon.textContent = next === 'dark' ? '☀️' : '🌙';
    }}

    function copyDocument() {{
      const content = document.getElementById('export-main-content');
      if (!content) return;
      navigator.clipboard.writeText(content.innerText).then(() => {{
        alert('Texte copié dans le presse-papier !');
      }});
    }}

    function copyCode(btn) {{
      const container = btn.closest('.code-block-container');
      const code = container ? container.querySelector('code') : null;
      if (!code) return;
      navigator.clipboard.writeText(code.innerText).then(() => {{
        const prev = btn.innerText;
        btn.innerText = 'Copié !';
        setTimeout(() => {{ btn.innerText = prev; }}, 2000);
      }});
    }}

    // Déclenchement automatique de l'impression si paramètre ?pdf=1 ou ?print=1
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
