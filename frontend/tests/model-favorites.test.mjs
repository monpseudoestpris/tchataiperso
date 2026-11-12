import { after, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import vm from "node:vm";

const source = ts.transpileModule(readFileSync("lib/model-favorites.ts", "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;

const mod = {};
vm.runInThisContext(`(function(exports, require) { ${source}\n})`)(mod, () => ({
  useEffect: () => {},
  useMemo: (fn) => fn(),
  useState: (init) => [typeof init === "function" ? init() : init, () => {}],
}));

const originals = { window: global.window, CustomEvent: global.CustomEvent, Event: global.Event };
after(() => {
  for (const [key, value] of Object.entries(originals)) {
    if (value === undefined) delete global[key]; else global[key] = value;
  }
});

let storageValues;
beforeEach(() => {
  storageValues = new Map();
  global.window = new EventTarget();
  window.localStorage = {
    getItem: (key) => storageValues.get(key) ?? null,
    setItem: (key, value) => storageValues.set(key, String(value)),
    removeItem: (key) => storageValues.delete(key),
  };
  global.Event = class Event {
    constructor(type) {
      this.type = type;
    }
  };
  global.CustomEvent = class CustomEvent extends global.Event {
    constructor(type, params = {}) {
      super(type);
      this.detail = params.detail;
    }
  };
});

test("reads empty list when storage is empty", () => {
  assert.deepEqual(mod.readFavoriteModels("llm"), []);
  assert.deepEqual(mod.readFavoriteModels("image"), []);
});

test("saves and reads favorites correctly", () => {
  const models = ["openai/gpt-6-astra", "google/gemini-3.8-flash"];
  assert.equal(mod.saveFavoriteModels(models, "llm"), true);
  assert.deepEqual(mod.readFavoriteModels("llm"), models);
  // Image category remains separate
  assert.deepEqual(mod.readFavoriteModels("image"), []);
});

test("toggles favorite model on and off", () => {
  const modelId = "anthropic/claude-3-7-sonnet";
  assert.equal(mod.isModelFavorite(modelId, mod.readFavoriteModels("llm")), false);

  const added = mod.toggleFavoriteModel(modelId, "llm");
  assert.equal(added, true);
  assert.equal(mod.isModelFavorite(modelId, mod.readFavoriteModels("llm")), true);

  const removed = mod.toggleFavoriteModel(modelId, "llm");
  assert.equal(removed, false);
  assert.equal(mod.isModelFavorite(modelId, mod.readFavoriteModels("llm")), false);
});

test("sortModelsWithFavorites places favorite models at the head", () => {
  const models = [
    { id: "model-a", name: "Model A" },
    { id: "model-b", name: "Model B" },
    { id: "model-c", name: "Model C" },
    { id: "model-d", name: "Model D" },
  ];
  const favorites = ["model-c", "model-a"];

  const sorted = mod.sortModelsWithFavorites(models, favorites);
  assert.equal(sorted[0].id, "model-a");
  assert.equal(sorted[1].id, "model-c");
  assert.equal(sorted[2].id, "model-b");
  assert.equal(sorted[3].id, "model-d");
});

test("sortModelsWithFavorites handles active model positioning within favorites", () => {
  const models = [
    { id: "model-a", name: "Model A" },
    { id: "model-b", name: "Model B" },
    { id: "model-c", name: "Model C" },
  ];
  const favorites = ["model-b", "model-c"];

  // model-c is active and also favorite -> should be at the very top
  const sorted = mod.sortModelsWithFavorites(models, favorites, "model-c");
  assert.equal(sorted[0].id, "model-c");
  assert.equal(sorted[1].id, "model-b");
  assert.equal(sorted[2].id, "model-a");
});

test("handles corrupted storage gracefully", () => {
  storageValues.set(mod.FAVORITE_LLM_MODELS_KEY, "{not-json");
  assert.deepEqual(mod.readFavoriteModels("llm"), []);
  storageValues.set(mod.FAVORITE_LLM_MODELS_KEY, "12345");
  assert.deepEqual(mod.readFavoriteModels("llm"), []);
});
