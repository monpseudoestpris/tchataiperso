/**
 * Utilitaires purs pour le rendu Markdown en streaming des documents illustrés :
 * 1. Placeholder anti-clignotement tant qu'une image Markdown `/api/docs/.../*.webp` est incomplète.
 * 2. Transformation des citations `[p. 6]` en liens interactifs ouvrant `page_6.webp`.
 */

const CODE_SEGMENT_RE =
  /((?:^|\n)(?:`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n(?:`{3,}|~{3,})(?=\n|$)|$)|`+[^`]*?`+)/g;

const MARKDOWN_LINK_OR_IMG_RE = /(!?\[[^\]]*\]\([^)]*\))/g;

const PAGE_OR_ASSET_CITATION_RE =
  /\[(?:((?:supp_[a-f0-9]{8}_)?(?:p(\d{1,4})_fig(\d{1,4})|page_(\d{1,4}))(?:\.webp)?)|(?:pp?\.?|pages?)\s*(\d{1,4}(?:\s*(?:[-–—]|[,;])\s*(?:(?:pp?\.?|pages?)\s*)?\d{1,4})*)|([^\]\n,]{2,60}?)\s*[,·—–-]\s*(?:pp?\.?|pages?)\s*(\d{1,4}))\](?!\()/gi;

export const STREAMING_WEBP_SENTINEL = "__streaming_webp__";

export type VisualDocSuppRef = {
  id?: string;
  title?: string;
  asset_prefix?: string;
  page_count?: number;
};

export type VisualDocRef = {
  slug: string;
  title?: string;
  page_count: number;
  supplementary_docs?: VisualDocSuppRef[];
};

function normalizeMatchTokens(text: string): string[] {
  return (text || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((tok) => tok.length >= 3);
}

function resolveNamedDocCitation(
  docLabel: string,
  pageNum: number,
  docs: VisualDocRef[],
  primaryDoc: VisualDocRef,
): string | null {
  const labelTokens = normalizeMatchTokens(docLabel);
  if (!labelTokens.length || !Number.isFinite(pageNum) || pageNum < 1) return null;

  // 1. Chercher d'abord parmi les documents complémentaires compilés (`supp_<8hex>_`)
  let bestSupp: { slug: string; prefix: string; score: number } | null = null;
  for (const doc of docs) {
    for (const supp of doc.supplementary_docs || []) {
      if (!supp.asset_prefix) continue;
      if (supp.page_count && supp.page_count > 0 && pageNum > supp.page_count) continue;
      const suppTokens = new Set(normalizeMatchTokens(supp.title || ""));
      if (!suppTokens.size) continue;
      const hits = labelTokens.filter((t) => suppTokens.has(t)).length;
      if (hits > 0 && (!bestSupp || hits > bestSupp.score)) {
        bestSupp = { slug: doc.slug, prefix: supp.asset_prefix, score: hits };
      }
    }
  }
  if (bestSupp) {
    return `[${docLabel.trim()}, p. ${pageNum}](#vdoc-asset:${bestSupp.slug}:${bestSupp.prefix}page_${pageNum}.webp)`;
  }

  // 2. Sinon vérifier si cela correspond à l'un des documents principaux attachés
  let bestMain: { slug: string; score: number } | null = null;
  for (const doc of docs) {
    if (doc.page_count > 0 && pageNum > doc.page_count) continue;
    const docTokens = new Set(normalizeMatchTokens(doc.title || doc.slug));
    const hits = labelTokens.filter((t) => docTokens.has(t)).length;
    if (hits > 0 && (!bestMain || hits > bestMain.score)) {
      bestMain = { slug: doc.slug, score: hits };
    }
  }
  if (bestMain) {
    return `[${docLabel.trim()}, p. ${pageNum}](#vdoc-page:${bestMain.slug}:${pageNum})`;
  }

  // 3. Repli si aucun titre exact trouvé mais page valide dans le document principal
  if (primaryDoc.page_count === 0 || pageNum <= primaryDoc.page_count) {
    return `[${docLabel.trim()}, p. ${pageNum}](#vdoc-page:${primaryDoc.slug}:${pageNum})`;
  }
  return null;
}

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
 * Extrait le slug, le préfixe complémentaire éventuel (`supp_<8hex>_`) et le numéro de page
 * depuis `/api/docs/<slug>/p6_fig1.webp`, `page_6.webp`, `supp_<8hex>_p2_fig5.webp`, etc.
 */
export function extractDocMetaFromImageSrc(
  src?: string,
): { slug: string; page: number; isFullPage: boolean; assetPrefix: string } | null {
  if (!src) return null;
  const fullPageMatch = src
    .trim()
    .match(/^\/api\/docs\/([a-z0-9-]+)\/(supp_[a-f0-9]{8}_)?page_(\d{1,4})\.webp$/i);
  if (fullPageMatch) {
    return {
      slug: fullPageMatch[1],
      assetPrefix: fullPageMatch[2] || "",
      page: Number(fullPageMatch[3]),
      isFullPage: true,
    };
  }
  const figMatch = src
    .trim()
    .match(/^\/api\/docs\/([a-z0-9-]+)\/(supp_[a-f0-9]{8}_)?p(\d{1,4})_fig\d{1,4}\.webp$/i);
  if (figMatch) {
    return {
      slug: figMatch[1],
      assetPrefix: figMatch[2] || "",
      page: Number(figMatch[3]),
      isFullPage: false,
    };
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
 * Analyse un `href` généré pour un schéma/asset cité par erreur entre crochets
 * (`#vdoc-asset:<slug>:<filename.webp>`).
 */
export function parseAssetCitationHref(
  href?: string,
): { slug: string; filename: string; page?: number; isFullPage: boolean } | null {
  if (!href) return null;
  const match = href
    .trim()
    .match(/^#vdoc-asset:([a-z0-9-]+):((?:supp_[a-f0-9]{8}_)?(?:p(\d{1,4})_fig\d{1,4}|page_(\d{1,4}))\.webp)$/i);
  if (!match) return null;
  const figPage = match[3] ? Number(match[3]) : undefined;
  const fullPage = match[4] ? Number(match[4]) : undefined;
  return {
    slug: match[1],
    filename: match[2],
    page: figPage ?? fullPage,
    isFullPage: Boolean(fullPage),
  };
}

/**
 * Transforme les citations `[p. 6]`, `[p.6]`, `[Page 6]` ou `[p. 6-7]` (hors blocs de code
 * et liens existants) en liens internes `#vdoc-page:<slug>:<page>` ouvrant `page_<N>.webp`
 * dans la modale de zoom plein écran.
 *
 * Filet de sécurité : si le LLM cite par erreur un nom de fichier technique entre crochets
 * (ex. `[supp_3a0f61cb_p1_fig1.webp]` ou `[supp_3a0f61cb_p2_fig7]`), le transforme proprement
 * en pastille cliquable `[Schéma p. 1]` ouvrant l'image correspondante.
 */
export function linkifyPageCitations(content: string, docs: VisualDocRef[]): string {
  if (!content || !docs.length) return content;

  // Déterminer le document prioritaire mentionné dans le message, sinon le premier document lié
  const mentionedSlugMatch = content.match(/\/api\/docs\/([a-z0-9-]+)\//i);
  const primaryDoc =
    (mentionedSlugMatch && docs.find((d) => d.slug === mentionedSlugMatch[1])) || docs[0];
  if (!primaryDoc?.slug) return content;

  function linkifyPlainSegment(seg: string): string {
    return seg.replace(
      PAGE_OR_ASSET_CITATION_RE,
      (
        fullMatch,
        rawAsset?: string,
        figPage?: string,
        _figIdx?: string,
        fullAssetPage?: string,
        pagesSpec?: string,
        namedDocLabel?: string,
        namedDocPage?: string,
      ) => {
        // 1. Nom de fichier technique `.webp` cité par erreur entre crochets -> pastille cliquable
        if (rawAsset) {
          const filename = rawAsset.toLowerCase().endsWith(".webp") ? rawAsset : `${rawAsset}.webp`;
          const label = figPage
            ? `Schéma p. ${figPage}`
            : fullAssetPage
              ? `Page ${fullAssetPage}`
              : "Schéma";
          return `[${label}](#vdoc-asset:${primaryDoc.slug}:${filename})`;
        }

        // 2. Citation nommée d'un document complémentaire ou principal : `[Lux et Tenebrae, p. 2]`
        if (namedDocLabel && namedDocPage) {
          const resolved = resolveNamedDocCitation(namedDocLabel, Number(namedDocPage), docs, primaryDoc);
          return resolved || fullMatch;
        }

        // 3. Citation de page(s) : `[p. 6]`, `[p. 6-7]`, `[p. 1, p. 2]`, `[p. 5, 1, 2]`, `[pp. 1; 2]`
        if (!pagesSpec) return fullMatch;
        const rangeOnly = pagesSpec.match(/^(\d{1,4})\s*[-–—]\s*(\d{1,4})$/);
        if (rangeOnly) {
          const startPage = Number(rangeOnly[1]);
          const endPage = Number(rangeOnly[2]);
          if (
            Number.isFinite(startPage) &&
            startPage >= 1 &&
            (primaryDoc.page_count === 0 || startPage <= primaryDoc.page_count)
          ) {
            if (
              Number.isFinite(endPage) &&
              endPage >= startPage &&
              (primaryDoc.page_count === 0 || endPage <= primaryDoc.page_count)
            ) {
              return `[p. ${startPage}–${endPage}](#vdoc-page:${primaryDoc.slug}:${startPage})`;
            }
            return `[p. ${startPage}](#vdoc-page:${primaryDoc.slug}:${startPage})`;
          }
          return fullMatch;
        }

        const nums = Array.from(pagesSpec.matchAll(/\d{1,4}/g))
          .map((m) => Number(m[0]))
          .filter(
            (n) =>
              Number.isFinite(n) &&
              n >= 1 &&
              (primaryDoc.page_count === 0 || n <= primaryDoc.page_count),
          );
        if (!nums.length) return fullMatch;
        return nums.map((n) => `[p. ${n}](#vdoc-page:${primaryDoc.slug}:${n})`).join(" ");
      },
    );
  }

  return content
    .split(CODE_SEGMENT_RE)
    .map((codePart, codeIdx) => {
      if (codeIdx % 2 === 1) {
        // Ne jamais toucher aux blocs de code multi-lignes ```...```
        if (codePart.includes("\n") || codePart.startsWith("```") || codePart.startsWith("~~~")) {
          return codePart;
        }
        // Si le LLM a entouré une citation de backticks (ex. `[p. 9]` ou `[Lux et Tenebrae, p. 2]`),
        // retirer les backticks et la rendre cliquable !
        const inner = codePart.replace(/^`+/, "").replace(/`+$/, "").trim();
        if (inner.startsWith("[") && inner.endsWith("]")) {
          const converted = linkifyPlainSegment(inner);
          if (converted !== inner) {
            return converted;
          }
        }
        return codePart;
      }
      return codePart
        .split(MARKDOWN_LINK_OR_IMG_RE)
        .map((seg, segIdx) => {
          if (segIdx % 2 === 1) return seg;
          return linkifyPlainSegment(seg);
        })
        .join("");
    })
    .join("");
}
