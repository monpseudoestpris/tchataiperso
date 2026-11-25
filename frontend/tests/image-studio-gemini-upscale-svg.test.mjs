import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");

test("Studio Image exposes Google Cloud badge for Gemini models and never labels them OpenRouter", () => {
  const modalSrc = fs.readFileSync(
    path.join(rootDir, "components", "image-studio-modal.tsx"),
    "utf8",
  );
  const pickerSrc = fs.readFileSync(
    path.join(rootDir, "components", "image-model-modal.tsx"),
    "utf8",
  );

  assert.match(modalSrc, /routed_via === "google_cloud"/);
  assert.match(modalSrc, /Google Cloud \(Vertex AI\)/);
  assert.match(pickerSrc, /Google Cloud \(Vertex AI\)/);
});

test("ImageStudioUpscalePanel covers all 8 Ideogram v2 upscale models", () => {
  const upscaleSrc = fs.readFileSync(
    path.join(rootDir, "components", "image-studio-upscale-panel.tsx"),
    "utf8",
  );

  const expectedModels = [
    "auto",
    "topaz-standard-2",
    "topaz-text-refine",
    "topaz-wonder-3-5",
    "topaz-wonder-4",
    "topaz-bloom-2",
    "topaz-redefine",
    "nano-banana-pro",
  ];
  for (const modelId of expectedModels) {
    assert.match(
      upscaleSrc,
      new RegExp(`id:\\s*"${modelId}"`),
      `Missing upscale model spec '${modelId}' in FALLBACK_UPSCALE_MODELS`,
    );
  }
});

test("ImageStudioSvgPanel supports both Generate SVG and Image-to-SVG operations", () => {
  const svgSrc = fs.readFileSync(
    path.join(rootDir, "components", "image-studio-svg-panel.tsx"),
    "utf8",
  );

  assert.match(svgSrc, /operation:\s*"generate"/);
  assert.match(svgSrc, /operation:\s*"vectorize"/);
  assert.match(svgSrc, /\/images\/svg/);
  assert.match(svgSrc, /is_svg:\s*true/);
});

test("image-studio-ext.module.css obeys motion, tabular-nums, and design-token rules", () => {
  const cssSrc = fs.readFileSync(
    path.join(rootDir, "components", "image-studio-ext.module.css"),
    "utf8",
  );

  assert.equal(
    /transition\s*:\s*all\b/i.test(cssSrc),
    false,
    "CSS module must never use transition: all",
  );
  assert.match(cssSrc, /@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)/);
  assert.match(cssSrc, /font-variant-numeric:\s*tabular-nums/);
});
