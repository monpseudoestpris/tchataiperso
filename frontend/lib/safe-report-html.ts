/** Assainissement HTML strict par liste blanche + rendu éditorial coloré des rapports Finance. */

export type ReportHtmlMeta = {
  title: string;
  subtitle?: string;
  symbol?: string;
  model?: string | null;
  createdAt?: string | null;
  accent?: string;
  badgeLabel?: string;
  question?: string | null;
  monogram?: string;
};

const ALLOWED_TAGS = new Set([
  "article",
  "header",
  "footer",
  "section",
  "div",
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "ul",
  "ol",
  "li",
  "blockquote",
  "pre",
  "code",
  "strong",
  "em",
  "span",
  "a",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "hr",
  "br",
]);

const SAFE_CLASS_RE = /^[a-zA-Z0-9 _-]+$/;
const SAFE_HEX_RE = /^#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$/;

function escapeHtml(raw: string): string {
  return raw
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sanitizeSafeStyle(rawStyle: string): string {
  const cleanDecls: string[] = [];
  for (const part of rawStyle.split(";")) {
    const idx = part.indexOf(":");
    if (idx <= 0) continue;
    const prop = part.slice(0, idx).trim().toLowerCase();
    const val = part.slice(idx + 1).trim();
    if (prop === "--rep-accent" && SAFE_HEX_RE.test(val)) {
      cleanDecls.push(`--rep-accent:${val}`);
    } else if (prop === "background" && SAFE_HEX_RE.test(val)) {
      cleanDecls.push(`background:${val}`);
    } else if (prop === "width" && /^\d{1,3}%$/.test(val)) {
      const pct = Math.max(0, Math.min(100, parseInt(val, 10)));
      cleanDecls.push(`width:${pct}%`);
    }
  }
  return cleanDecls.join(";");
}

/** Filtre strict DOM-based contre tout script, événement inline ou URL non-HTTP(S). */
export function sanitizeReportHtml(rawHtml: string): string {
  if (!rawHtml || typeof window === "undefined" || typeof DOMParser === "undefined") {
    return "";
  }
  const parser = new DOMParser();
  const doc = parser.parseFromString(rawHtml, "text/html");

  const sanitizeNode = (node: Node): Node | null => {
    if (node.nodeType === Node.TEXT_NODE) {
      return document.createTextNode(node.textContent ?? "");
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    const el = node as Element;
    const tag = el.tagName.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) {
      return null;
    }
    const cleanEl = document.createElement(tag);

    const cls = el.getAttribute("class");
    if (cls && SAFE_CLASS_RE.test(cls)) {
      cleanEl.setAttribute("class", cls);
    }
    const style = el.getAttribute("style");
    if (style) {
      const safeStyle = sanitizeSafeStyle(style);
      if (safeStyle) cleanEl.setAttribute("style", safeStyle);
    }
    if (tag === "pre") {
      const lang = el.getAttribute("data-lang");
      if (lang && /^[a-zA-Z0-9_-]{1,24}$/.test(lang)) {
        cleanEl.setAttribute("data-lang", lang);
      }
    }
    if (tag === "a") {
      const href = (el.getAttribute("href") || "").trim();
      if (/^https?:\/\//i.test(href)) {
        cleanEl.setAttribute("href", href);
        cleanEl.setAttribute("target", "_blank");
        cleanEl.setAttribute("rel", "noopener noreferrer");
      }
    }

    for (const child of Array.from(el.childNodes)) {
      const cleanChild = sanitizeNode(child);
      if (cleanChild) cleanEl.appendChild(cleanChild);
    }
    return cleanEl;
  };

  const container = document.createElement("div");
  for (const child of Array.from(doc.body.childNodes)) {
    const cleanChild = sanitizeNode(child);
    if (cleanChild) container.appendChild(cleanChild);
  }
  return container.innerHTML;
}

const BULL_WORDS = [
  "achat fort",
  "achat",
  "accumuler",
  "renforcer",
  "sous-évalué",
  "solide",
  "haussier",
  "haussière",
  "irrésistible",
  "wide",
  "favorable",
  "excellent",
];
const BEAR_WORDS = [
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
  "none",
];
const HOLD_WORDS = ["conserver", "attendre", "neutre", "modéré", "vigilance", "prudence", "narrow"];

function classifyVerdictTone(verdict: string): "bull" | "hold" | "bear" | "neutral" {
  const low = verdict.toLowerCase();
  if (BEAR_WORDS.some(w => low.includes(w))) return "bear";
  if (BULL_WORDS.some(w => low.includes(w))) return "bull";
  if (HOLD_WORDS.some(w => low.includes(w))) return "hold";
  return "neutral";
}

function classifySectionTone(title: string): { tone: string; icon: string } {
  const low = title.toLowerCase();
  if (/(séduit|haussi|force|avantage|moat|atout|positif)/.test(low)) return { tone: "bull", icon: "▲" };
  if (/(hésit|risque|red flag|faiblesse|menace|refus|vigilance|baissi|alerte)/.test(low)) return { tone: "bear", icon: "⚠" };
  if (/(tableau|métrique|crible|chiffre|valoris|ratio|bilan|cash|rentab|marge)/.test(low)) return { tone: "metrics", icon: "▤" };
  if (/(seuil|plan|action|catalys|scénario|conclusion|allocation|synthèse)/.test(low)) return { tone: "action", icon: "◎" };
  if (/(verdict|décision|conviction|identité|résumé)/.test(low)) return { tone: "verdict", icon: "★" };
  return { tone: "info", icon: "◆" };
}

function formatDateFr(iso?: string | null): string {
  if (!iso) return "";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso.slice(0, 16);
  return dt.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

function renderInline(raw: string, highlightNumbers = true): string {
  const tokenRe = /(`[^`]+`|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*|\[[^\]]+\]\([^)]+\))/g;
  const out: string[] = [];
  let pos = 0;
  const decoratePlain = (plain: string) => {
    let escaped = escapeHtml(plain);
    if (!highlightNumbers) return escaped;
    escaped = escaped.replace(
      /(^|[\s(>])([+-]\d+(?:[.,]\d+)?\s*%)/g,
      (_m, p1: string, pct: string) =>
        `${p1}<span class="${pct.startsWith("+") ? "clair-rep-pos" : "clair-rep-neg"}">${pct}</span>`,
    );
    escaped = escaped.replace(
      /\b(\d+(?:[.,]\d+)?\s*\/\s*(?:10|100|9))\b/g,
      '<span class="clair-rep-score-inline">$1</span>',
    );
    return escaped;
  };

  let m: RegExpExecArray | null;
  while ((m = tokenRe.exec(raw)) !== null) {
    if (m.index > pos) out.push(decoratePlain(raw.slice(pos, m.index)));
    const tok = m[0];
    if (tok.startsWith("`") && tok.endsWith("`")) {
      out.push(`<code class="clair-rep-chip">${escapeHtml(tok.slice(1, -1))}</code>`);
    } else if (tok.startsWith("**") && tok.endsWith("**")) {
      out.push(`<strong class="clair-rep-strong">${escapeHtml(tok.slice(2, -2))}</strong>`);
    } else if (tok.startsWith("*") && tok.endsWith("*")) {
      out.push(`<em>${escapeHtml(tok.slice(1, -1))}</em>`);
    } else {
      const lm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok);
      if (lm && /^https?:\/\//i.test(lm[2])) {
        out.push(
          `<a class="clair-rep-link" href="${escapeHtml(lm[2])}" target="_blank" rel="noopener noreferrer">${escapeHtml(lm[1])}</a>`,
        );
      } else if (lm) {
        out.push(escapeHtml(lm[1]));
      } else {
        out.push(escapeHtml(tok));
      }
    }
    pos = tokenRe.lastIndex;
  }
  if (pos < raw.length) out.push(decoratePlain(raw.slice(pos)));
  return out.join("");
}

function splitTableRow(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map(c => c.trim());
}

function isTableSep(line: string): boolean {
  if (!line.includes("|")) return false;
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every(c => /^:?-{2,}:?$/.test(c.replace(/\s+/g, "")));
}

function renderBlocks(lines: string[]): string {
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (!trimmed) {
      i++;
      continue;
    }
    if (trimmed.startsWith("```")) {
      const lang = escapeHtml(trimmed.slice(3).trim());
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        code.push(escapeHtml(lines[i]));
        i++;
      }
      i++;
      out.push(`<pre class="clair-rep-pre"${lang ? ` data-lang="${lang}"` : ""}><code>${code.join("\n")}</code></pre>`);
      continue;
    }
    if (/^[-*_]{3,}$/.test(trimmed)) {
      out.push('<hr class="clair-rep-hr" />');
      i++;
      continue;
    }
    const subM = /^#{4,6}\s+(.+)$/.exec(trimmed);
    if (subM) {
      out.push(`<h4 class="clair-rep-h4">${renderInline(subM[1])}</h4>`);
      i++;
      continue;
    }
    if (trimmed.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const headers = splitTableRow(trimmed);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      const ths = headers.map(h => `<th>${renderInline(h, false)}</th>`).join("");
      const trs = rows
        .map(row => {
          const tds = headers
            .map((_h, idx) => `<td>${renderInline((row[idx] ?? "").trim(), true)}</td>`)
            .join("");
          return `<tr>${tds}</tr>`;
        })
        .join("");
      out.push(
        `<div class="clair-rep-table-wrap"><table class="clair-rep-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`,
      );
      continue;
    }
    if (trimmed.startsWith(">")) {
      const qs: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        qs.push(renderInline(lines[i].trim().replace(/^>+/, "").trim()));
        i++;
      }
      out.push(`<blockquote class="clair-rep-quote">${qs.join("<br/>")}</blockquote>`);
      continue;
    }
    const ulM = /^[-*+•]\s+(.+)$/.exec(trimmed);
    const olM = /^\d+[.)]\s+(.+)$/.exec(trimmed);
    if (ulM || olM) {
      const ordered = Boolean(olM);
      const tag = ordered ? "ol" : "ul";
      const items: string[] = [];
      while (i < lines.length) {
        const cur = lines[i].trim();
        const mItem = ordered ? /^\d+[.)]\s+(.+)$/.exec(cur) : /^[-*+•]\s+(.+)$/.exec(cur);
        if (!mItem) break;
        items.push(`<li>${renderInline(mItem[1])}</li>`);
        i++;
      }
      out.push(`<${tag} class="clair-rep-list${ordered ? " is-ordered" : ""}">${items.join("")}</${tag}>`);
      continue;
    }
    const paras: string[] = [];
    while (i < lines.length) {
      const cur = lines[i].trim();
      if (
        !cur ||
        cur.startsWith("#") ||
        cur.startsWith(">") ||
        cur.startsWith("```") ||
        /^[-*_]{3,}$/.test(cur) ||
        /^[-*+•]\s+/.test(cur) ||
        /^\d+[.)]\s+/.test(cur) ||
        (cur.includes("|") && i + 1 < lines.length && isTableSep(lines[i + 1]))
      ) {
        break;
      }
      paras.push(renderInline(cur));
      i++;
    }
    if (paras.length) out.push(`<p class="clair-rep-p">${paras.join(" ")}</p>`);
  }
  return out.join("");
}

/** Convertit un Markdown financier en HTML éditorial coloré `.clair-rep-*` (fallback client pour MOAT/Actus/Rapports). */
export function markdownToClassyReportHtml(markdown: string, meta: ReportHtmlMeta): string {
  const safeAccent = SAFE_HEX_RE.test((meta.accent || "").trim()) ? meta.accent!.trim() : "#10b981";
  const lines = (markdown || "").split(/\r?\n/);

  const verdictMatch = /(?:Décision(?:\s+analytique)?|Verdict(?:\s+global)?|Recommandation)\s*\*?\*?\s*:\s*\*?\*?\s*([^\n|*]+)/i.exec(
    markdown || "",
  );
  const verdict = verdictMatch ? verdictMatch[1].replace(/[*`_]/g, "").trim().slice(0, 64) : "";
  const vTone = classifyVerdictTone(verdict);

  const sections: { title: string | null; lines: string[] }[] = [];
  let curTitle: string | null = null;
  let curLines: string[] = [];
  for (const line of lines) {
    const hm = /^#{1,3}\s+(.+)$/.exec(line.trim());
    if (hm) {
      if (curTitle !== null || curLines.some(l => l.trim())) {
        sections.push({ title: curTitle, lines: curLines });
      }
      curTitle = hm[1].trim();
      curLines = [];
    } else {
      curLines.push(line);
    }
  }
  if (curTitle !== null || curLines.some(l => l.trim())) {
    sections.push({ title: curTitle, lines: curLines });
  }

  const chips: string[] = [];
  if (meta.badgeLabel) chips.push(`<span class="clair-rep-badge">${escapeHtml(meta.badgeLabel)}</span>`);
  if (meta.symbol) chips.push(`<span class="clair-rep-ticker">${escapeHtml(meta.symbol)}</span>`);
  if (meta.model) chips.push(`<span class="clair-rep-model">${escapeHtml(meta.model)}</span>`);
  const dTxt = formatDateFr(meta.createdAt);
  if (dTxt) chips.push(`<span class="clair-rep-date">🕒 ${escapeHtml(dTxt)}</span>`);

  const avatar = meta.monogram
    ? `<div class="clair-rep-avatar" style="background:${safeAccent}">${escapeHtml(meta.monogram.slice(0, 3))}</div>`
    : "";
  const verdictRight = verdict
    ? `<div class="clair-rep-hero-right"><span class="clair-rep-verdict-pill is-${vTone}">${escapeHtml(verdict)}</span></div>`
    : "";
  const qBanner = meta.question?.trim()
    ? `<div class="clair-rep-question-banner"><span>Question posée :</span> <strong>« ${escapeHtml(meta.question.trim())} »</strong></div>`
    : "";

  const hero = `<header class="clair-rep-hero"><div class="clair-rep-hero-main">${avatar}<div class="clair-rep-hero-titles"><div class="clair-rep-hero-chips">${chips.join("")}</div><h2 class="clair-rep-hero-title">${escapeHtml(meta.title)}</h2>${
    meta.subtitle ? `<p class="clair-rep-hero-sub">${escapeHtml(meta.subtitle)}</p>` : ""
  }</div></div>${verdictRight}${qBanner}</header>`;

  const cards = sections
    .map((sec, idx) => {
      const body = renderBlocks(sec.lines);
      if (!body && !sec.title) return "";
      if (sec.title) {
        const { tone, icon } = classifySectionTone(sec.title);
        return `<section class="clair-rep-card is-${tone}"><div class="clair-rep-card-head"><span class="clair-rep-card-icon">${icon}</span><h3 class="clair-rep-card-title">${escapeHtml(
          sec.title.replace(/[*]/g, "").trim(),
        )}</h3></div><div class="clair-rep-card-body">${body}</div></section>`;
      }
      return `<section class="clair-rep-card ${idx === 0 ? "is-intro" : "is-info"}"><div class="clair-rep-card-body">${body}</div></section>`;
    })
    .join("");

  return `<article class="clair-rep-root" style="--rep-accent:${safeAccent}">${hero}<div class="clair-rep-sections">${cards}</div></article>`;
}

const STANDALONE_REPORT_CSS = `
:root{color-scheme:light dark}
body{margin:0;padding:32px 20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;background:#f1f5f9;color:#0f172a;line-height:1.6}
@media (prefers-color-scheme:dark){body{background:#0b1120;color:#e2e8f0}}
.wrap{max-width:980px;margin:0 auto}
.clair-rep-root{--rep-accent:#10b981;display:flex;flex-direction:column;gap:16px}
.clair-rep-hero{background:linear-gradient(135deg,rgba(16,185,129,.12),rgba(99,102,241,.08));border:1px solid rgba(148,163,184,.35);border-left:5px solid var(--rep-accent);border-radius:16px;padding:18px 20px;display:flex;flex-wrap:wrap;justify-content:space-between;gap:14px}
.clair-rep-hero-main{display:flex;gap:14px;align-items:flex-start}
.clair-rep-avatar{width:44px;height:44px;border-radius:12px;color:#fff;font-weight:800;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.clair-rep-hero-chips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px;font-size:12px}
.clair-rep-badge,.clair-rep-ticker,.clair-rep-model,.clair-rep-date{padding:2px 9px;border-radius:999px;font-weight:700;background:rgba(148,163,184,.18)}
.clair-rep-badge{background:var(--rep-accent);color:#fff}
.clair-rep-hero-title{margin:0;font-size:20px}
.clair-rep-hero-sub{margin:4px 0 0;opacity:.8;font-size:13px}
.clair-rep-verdict-pill{padding:6px 14px;border-radius:999px;font-weight:800;font-size:13px;display:inline-block}
.clair-rep-verdict-pill.is-bull{background:#10b981;color:#fff}
.clair-rep-verdict-pill.is-hold{background:#f59e0b;color:#fff}
.clair-rep-verdict-pill.is-bear{background:#f43f5e;color:#fff}
.clair-rep-verdict-pill.is-neutral{background:#6366f1;color:#fff}
.clair-rep-conv-box{margin-top:8px;font-size:12px}
.clair-rep-conv-track{display:block;width:140px;height:7px;border-radius:999px;background:rgba(148,163,184,.25);overflow:hidden;margin-top:4px}
.clair-rep-conv-fill{display:block;height:100%;background:#10b981;border-radius:999px}
.clair-rep-sections{display:flex;flex-direction:column;gap:14px}
.clair-rep-card{border-radius:14px;border:1px solid rgba(148,163,184,.3);padding:16px 18px;background:rgba(255,255,255,.75)}
@media (prefers-color-scheme:dark){.clair-rep-card{background:rgba(15,23,42,.8)}}
.clair-rep-card.is-bull{border-left:4px solid #10b981;background:linear-gradient(90deg,rgba(16,185,129,.1),transparent 35%)}
.clair-rep-card.is-bear{border-left:4px solid #f43f5e;background:linear-gradient(90deg,rgba(244,63,94,.1),transparent 35%)}
.clair-rep-card.is-metrics{border-left:4px solid #0ea5e9}
.clair-rep-card.is-action{border-left:4px solid #f59e0b}
.clair-rep-card.is-verdict{border-left:4px solid #6366f1}
.clair-rep-card-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.clair-rep-card-title{margin:0;font-size:15.5px}
.clair-rep-table-wrap{overflow-x:auto}
.clair-rep-table{width:100%;border-collapse:collapse;font-size:13px}
.clair-rep-table th{text-align:left;padding:8px 10px;background:rgba(148,163,184,.16)}
.clair-rep-table td{padding:8px 10px;border-top:1px solid rgba(148,163,184,.2)}
.clair-rep-pos{color:#10b981;font-weight:700}
.clair-rep-neg{color:#f43f5e;font-weight:700}
.clair-rep-cell-pill{padding:2px 8px;border-radius:999px;font-weight:700;font-size:12px}
.clair-rep-cell-pill.is-bull{background:rgba(16,185,129,.18);color:#059669}
.clair-rep-cell-pill.is-bear{background:rgba(244,63,94,.18);color:#e11d48}
.clair-rep-cell-pill.is-hold{background:rgba(245,158,11,.18);color:#d97706}
.clair-rep-quote{margin:8px 0;padding:10px 14px;border-left:3px solid var(--rep-accent);background:rgba(148,163,184,.12);border-radius:8px;font-style:italic}
.clair-rep-chip{padding:1px 6px;border-radius:6px;background:rgba(99,102,241,.14);font-size:12px}
`;

export function buildStandaloneReportDocument(sanitizedInnerHtml: string, title: string): string {
  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>${escapeHtml(title)}</title>
<style>${STANDALONE_REPORT_CSS}</style>
</head>
<body>
<div class="wrap">${sanitizedInnerHtml}</div>
</body>
</html>`;
}
