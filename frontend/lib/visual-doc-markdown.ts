/**
 * Utilitaires purs pour le rendu Markdown en streaming des documents illustrés :
 * 1. Placeholder anti-clignotement tant qu'une image Markdown `/api/docs/.../*.webp` est incomplète.
 * 2. Transformation des citations `[p. 6]` en liens interactifs ouvrant `page_6.webp`.
 */

const CODE_SEGMENT_RE =
  /((?:^|\n)(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n(?:`{3,}|~{3,})(?=\n|$)|$)|`+[^`]*?`+)/g;

const MARKDOWN_LINK_OR_IMG_RE = /(!?\[[^\]]*\]\([^)]*\))/g;

const PAGE_CITATION_RE = /\[(?:p\.?|page)\s*(\d{1,4})(?:\s*[-–—]\s*(\d{1,4}))?\]/gi;

export const STREAMING_WEBP_SENTINEL = "__streaming_webp__";

export type VisualDocRef = {
  slug: string;
  title?: string;
  page_count: number;
};

/**
 * Remplace une balise image Markdown encore incomplète en fin de flux SSE par un marqueur
 * de chargement propre (`__streaming_webp__`) afin d'éviter tout clignotement d'icône cassée
 * ou texte brut `![...` pendant le streaming token par token.
 */
export function prepareStreamingVisualMarkdown(content: string, isStreaming: boolean): string {
  if (!content || !isStreaming) return content;

  // Cas 1 : `![alt](url_incomplète` (parenthèse fermante pas encore reçue)
  if (/!\[[^\]]*\]\([^)]*$/.test(content)) {
    return content.replace(/!\[[^\]]*\]\([^)]*$/, `\n\n![Chargement du schéma…](${STREAMING_WEBP_SENTINEL})`);
  }

  // Cas 2 : `![alt_en_cours` en fin de ligne ou de bloc (crochet fermant pas encore reçu)
  if (/(?:^|\n)[ \t]*!\[[^\]]*$/.test(content)) {
    return content.replace(/(^|\n)[ \t]*!\[[^\]]*$/, `$1![Chargement du schéma…](${STREAMING_WEBP_SENTINEL})`);
  }

  return content;
}

/**
 * Indique si une URL d'image locale compilée est encore en cours de streaming (incomplète).
 * Ne bloque jamais les images web externes SearXNG (`.jpg`, `.png`, etc.).
 */
export function isIncompleteLocalDocImage(src?: string): boolean {
  if (!src) return true;
  const trimmed = src.trim();
  if (!trimmed || trimmed === STREAMING_WEBP_SENTINEL) return true;
  if (trimmed.startsWith("/api/docs/") || trimmed.startsWith("/static/")) {
    return !trimmed.toLowerCase().endsWith(".webp");
  }
  return false;
}

/**
 * Indique si l'image provient de la bibliothèque locale de documents illustrés.
 */
export function isLocalVisualDocImage(src?: string): boolean {
  if (!src) return false;
  const trimmed = src.trim();
  return trimmed.startsWith("/api/docs/") || trimmed.startsWith("/static/");
}

/**
 * Extrait le slug et le numéro de page depuis `/api/docs/<slug>/p6_fig1.webp` ou `page_6.webp`.
 */
export function extractDocMetaFromImageSrc(
  src?: string,
): { slug: string; page: number; isFullPage: boolean } | null {
  if (!src) return null;
  const fullPageMatch = src.trim().match(/^\/api\/docs\/([a-z0-9-]+)\/page_(\d{1,4})\.webp$/i);
  if (fullPageMatch) {
    return { slug: fullPageMatch[1], page: Number(fullPageMatch[2]), isFullPage: true };
  }
  const figMatch = src.trim().match(/^\/api\/docs\/([a-z0-9-]+)\/p(\d{1,4})_fig\d{1,4}\.webp$/i);
  if (figMatch) {
    return { slug: figMatch[1], page: Number(figMatch[2]), isFullPage: false };
  }
  return null;
}

/**
 * Analyse un `href` généré pour une citation de page cliquable (`#vdoc-page:<slug>:<page>`
 * ou `/api/docs/<slug>/page_<page>.webp`).
 */
export function parsePageCitationHref(href?: string): { slug: string; page: number } | null {
  if (!href) return null;
  const hashMatch = href.trim().match(/^#vdoc-page:([a-z0-9-]+):(\d{1,4})$/i);
  if (hashMatch) {
    return { slug: hashMatch[1], page: Number(hashMatch[2]) };
  }
  const directMatch = href.trim().match(/^\/api\/docs\/([a-z0-9-]+)\/page_(\d{1,4})\.webp$/i);
  if (directMatch) {
    return { slug: directMatch[1], page: Number(directMatch[2]) };
  }
  return null;
}

/**
 * Transforme les citations `[p. 6]`, `[p.6]`, `[Page 6]` ou `[p. 6-7]` (hors blocs de code
 * et liens existants) en liens internes `#vdoc-page:<slug>:<page>` ouvrant `page_<N>.webp`
 * dans la modale de zoom plein écran.
 */
export function linkifyPageCitations(content: string, docs: VisualDocRef[]): string {
  if (!content || !docs.length) return content;

  // Déterminer le document prioritaire mentionné dans le message, sinon le premier document lié
  const mentionedSlugMatch = content.match(/\/api\/docs\/([a-z0-9-]+)\//i);
  const primaryDoc =
    (mentionedSlugMatch && docs.find((d) => d.slug === mentionedSlugMatch[1])) || docs[0];
  if (!primaryDoc?.slug) return content;

  return content
    .split(CODE_SEGMENT_RE)
    .map((codePart, codeIdx) => {
      if (codeIdx % 2 === 1) return codePart;
      return codePart
        .split(MARKDOWN_LINK_OR_IMG_RE)
        .map((seg, segIdx) => {
          if (segIdx % 2 === 1) return seg;
          return seg.replace(PAGE_CITATION_RE, (fullMatch, startStr: string, endStr?: string) => {
            const startPage = Number(startStr);
            if (!Number.isFinite(startPage) || startPage < 1) return fullMatch;
            if (primaryDoc.page_count > 0 && startPage > primaryDoc.page_count) return fullMatch;
            if (endStr) {
              const endPage = Number(endStr);
              if (
                Number.isFinite(endPage) &&
                endPage >= startPage &&
                (primaryDoc.page_count === 0 || endPage <= primaryDoc.page_count)
              ) {
                return `[p. ${startPage}–${endPage}](#vdoc-page:${primaryDoc.slug}:${startPage})`;
              }
            }
            return `[p. ${startPage}](#vdoc-page:${primaryDoc.slug}:${startPage})`;
          });
        })
        .join("");
    })
    .join("");
}
