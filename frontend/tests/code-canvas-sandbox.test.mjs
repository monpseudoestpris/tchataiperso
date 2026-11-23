import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import vm from "node:vm";

function loadCodeCanvasModule() {
  const source = ts.transpileModule(readFileSync("lib/code-canvas.ts", "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const mod = { exports: {} };
  const fakeRequire = () => ({});
  vm.runInThisContext(`(function(exports, require, module) { ${source}\n})`)(mod.exports, fakeRequire, mod);
  return mod.exports;
}

test("injectSandboxStorageShim injecte le shim avant les scripts applicatifs et reste idempotent", () => {
  const { injectSandboxStorageShim } = loadCodeCanvasModule();
  const input = "<!doctype html><html><head><title>App</title><script>localStorage.setItem('k','v')</script></head><body></body></html>";
  const output = injectSandboxStorageShim(input);
  assert.ok(output.includes("__clair_storage_shim__"));
  assert.ok(output.indexOf("__clair_storage_shim__") < output.indexOf("localStorage.setItem"));
  assert.equal(injectSandboxStorageShim(output), output);
});

test("le shim mémoire localStorage/sessionStorage fonctionne sans SecurityError sur origine opaque", () => {
  const { injectSandboxStorageShim } = loadCodeCanvasModule();
  const html = injectSandboxStorageShim("<html><head></head><body></body></html>");
  const match = html.match(/<script data-clair-storage-shim>([\s\S]*?)<\/script>/);
  assert.ok(match, "Le bloc script du shim doit être présent");

  const fakeWindow = {};
  for (const name of ["localStorage", "sessionStorage"]) {
    Object.defineProperty(fakeWindow, name, {
      configurable: true,
      get() {
        throw new Error("SecurityError: The operation is insecure.");
      },
    });
  }
  const sandbox = { window: fakeWindow, Object };
  vm.runInNewContext(match[1], sandbox);

  fakeWindow.localStorage.setItem("kanban", "ok");
  assert.equal(fakeWindow.localStorage.getItem("kanban"), "ok");
  assert.equal(fakeWindow.localStorage.length, 1);
  assert.equal(fakeWindow.localStorage.key(0), "kanban");
  fakeWindow.localStorage.removeItem("kanban");
  assert.equal(fakeWindow.localStorage.getItem("kanban"), null);

  fakeWindow.sessionStorage.setItem("draft", "123");
  fakeWindow.sessionStorage.clear();
  assert.equal(fakeWindow.sessionStorage.length, 0);
});

test("CodeCanvas et WebPageModal n'associent jamais allow-scripts et allow-same-origin", () => {
  for (const file of ["components/code-canvas.tsx", "components/web-page-modal.tsx"]) {
    const content = readFileSync(file, "utf8");
    const sandboxAttrs = [...content.matchAll(/sandbox="([^"]+)"/g)].map(m => m[1]);
    assert.ok(sandboxAttrs.length >= 1, `${file} doit déclarer un attribut sandbox`);
    for (const attr of sandboxAttrs) {
      assert.ok(
        !(attr.includes("allow-scripts") && attr.includes("allow-same-origin")),
        `${file} ne doit pas combiner allow-scripts et allow-same-origin (${attr})`,
      );
    }
  }
});
