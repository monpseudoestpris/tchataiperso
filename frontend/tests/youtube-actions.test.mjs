import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcPath = path.resolve(__dirname, "../lib/youtube-actions.ts");
const src = fs.readFileSync(srcPath, "utf8");

test("youtube-actions exposes canonical 5 actions and URL helpers", () => {
  for (const action of ["summarize", "analyze", "key_points", "study", "translate_fr"]) {
    assert.ok(src.includes(`id: "${action}"`), `missing canonical action ${action}`);
  }
  assert.ok(src.includes("export function isYoutubeUrl("));
  assert.ok(src.includes("export function buildYoutubeActionPrompt("));
  assert.ok(src.includes("export function getUrlSubmitLabel("));
  assert.ok(src.includes("du début à la toute fin"));
});
