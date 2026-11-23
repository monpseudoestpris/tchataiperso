import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import vm from "node:vm";

const source = ts.transpileModule(readFileSync("lib/visual-doc-markdown.ts", "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const mod = {};
vm.runInThisContext(`(function(exports) { ${source}\n})`)(mod);

test("prepareStreamingVisualMarkdown remplace une image incomplète par le placeholder sans clignotement", () => {
  const partialUrl = "Le symbole indique 2 PV [p. 6] :\n\n![Anatomie d'une carte](/api/docs/catan-1a2b/p6_fi";
  const out = mod.prepareStreamingVisualMarkdown(partialUrl, true);
  assert.ok(out.endsWith(`![Chargement du schéma…](${mod.STREAMING_WEBP_SENTINEL})`));
  assert.ok(!out.includes("p6_fi"));

  const partialAlt = "Voici le schéma :\n![Anatomie en cours";
  assert.ok(mod.prepareStreamingVisualMarkdown(partialAlt, true).includes(mod.STREAMING_WEBP_SENTINEL));

  const complete = "Voici le schéma :\n\n![Anatomie](/api/docs/catan-1a2b/p6_fig1.webp)";
  assert.equal(mod.prepareStreamingVisualMarkdown(complete, true), complete);
  assert.equal(mod.prepareStreamingVisualMarkdown(partialUrl, false), partialUrl);
});

test("isIncompleteLocalDocImage bloque les URL locales tronquées sans casser les images web externes", () => {
  assert.equal(mod.isIncompleteLocalDocImage(mod.STREAMING_WEBP_SENTINEL), true);
  assert.equal(mod.isIncompleteLocalDocImage("/api/docs/catan-1a2b/p6_fig1.we"), true);
  assert.equal(mod.isIncompleteLocalDocImage("/api/docs/catan-1a2b/p6_fig1.webp"), false);
  assert.equal(mod.isIncompleteLocalDocImage("https://cdn.example.com/photo.jpg?w=800"), false);
});

test("linkifyPageCitations rend [p. 6] cliquable hors blocs de code et liens existants", () => {
  const docs = [{ slug: "catan-1a2b", title: "Catan", page_count: 12 }];
  const input = [
    "Le coût est en haut à gauche [p. 6] et voir aussi [Page 12] ainsi que [p. 4-5].",
    "Page hors bornes ignorée [p. 99].",
    "`code inline [p. 6]`",
    "```md\n[p. 6]\n```",
    "![Carte](/api/docs/catan-1a2b/p6_fig1.webp)",
  ].join("\n\n");

  const output = mod.linkifyPageCitations(input, docs);
  assert.ok(output.includes("[p. 6](#vdoc-page:catan-1a2b:6)"));
  assert.ok(output.includes("[p. 12](#vdoc-page:catan-1a2b:12)"));
  assert.ok(output.includes("[p. 4–5](#vdoc-page:catan-1a2b:4)"));
  assert.ok(output.includes("Page hors bornes ignorée [p. 99]."));
  assert.ok(output.includes("`code inline [p. 6]`"));
  assert.ok(output.includes("```md\n[p. 6]\n```"));
  assert.ok(output.includes("![Carte](/api/docs/catan-1a2b/p6_fig1.webp)"));
});

test("parsePageCitationHref et extractDocMetaFromImageSrc analysent les chemins WebP et ancres", () => {
  assert.deepEqual(mod.parsePageCitationHref("#vdoc-page:catan-1a2b:6"), { slug: "catan-1a2b", page: 6 });
  assert.deepEqual(mod.parsePageCitationHref("/api/docs/catan-1a2b/page_6.webp"), { slug: "catan-1a2b", page: 6 });
  assert.equal(mod.parsePageCitationHref("https://example.com"), null);

  assert.deepEqual(mod.extractDocMetaFromImageSrc("/api/docs/catan-1a2b/p6_fig2.webp"), {
    slug: "catan-1a2b",
    assetPrefix: "",
    page: 6,
    isFullPage: false,
  });
  assert.deepEqual(mod.extractDocMetaFromImageSrc("/api/docs/catan-1a2b/page_6.webp"), {
    slug: "catan-1a2b",
    assetPrefix: "",
    page: 6,
    isFullPage: true,
  });
  assert.deepEqual(mod.extractDocMetaFromImageSrc("/api/docs/catan-1a2b/supp_a1b2c3d4_p3_fig1.webp"), {
    slug: "catan-1a2b",
    assetPrefix: "supp_a1b2c3d4_",
    page: 3,
    isFullPage: false,
  });
});
