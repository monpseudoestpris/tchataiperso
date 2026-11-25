import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");

test("SettingsApiKeysSection enforces Write-Only zero-browser-storage and password hygiene", () => {
  const componentSrc = fs.readFileSync(
    path.join(rootDir, "components", "settings-api-keys-section.tsx"),
    "utf8",
  );

  for (const forbiddenStorage of [
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
  ]) {
    assert.equal(
      componentSrc.includes(forbiddenStorage),
      false,
      `Forbidden browser storage reference found: ${forbiddenStorage}`,
    );
  }

  assert.match(componentSrc, /autoComplete="new-password"/);
  assert.match(componentSrc, /autoComplete="current-password"/);
  assert.match(componentSrc, /data-1p-ignore="true"/);
});

test("AdminApiKeyItem contract never exposes secret value, mask, prefix or suffix", () => {
  const apiSrc = fs.readFileSync(path.join(rootDir, "lib", "api.ts"), "utf8");
  const blockMatch = apiSrc.match(/export type AdminApiKeyItem = \{([\s\S]*?)\};/);
  assert.ok(blockMatch, "AdminApiKeyItem type definition must exist in lib/api.ts");

  const body = blockMatch[1];
  for (const forbiddenField of ["secret", "value", "masked", "prefix", "suffix", "plaintext", "ciphertext"]) {
    assert.equal(
      new RegExp(`\\b${forbiddenField}\\b`, "i").test(body),
      false,
      `AdminApiKeyItem must not expose field '${forbiddenField}'`,
    );
  }
});

test("settings-api-keys-section.module.css obeys motion and design-token rules", () => {
  const cssSrc = fs.readFileSync(
    path.join(rootDir, "components", "settings-api-keys-section.module.css"),
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
