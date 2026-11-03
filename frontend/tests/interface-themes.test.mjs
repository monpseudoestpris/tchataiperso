import { after, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import vm from "node:vm";

const source = ts.transpileModule(readFileSync("lib/interface-themes.ts", "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;
const themes = {};
vm.runInThisContext(`(function(exports) { ${source}\n})`)(themes);
const originals = { window: global.window, document: global.document };
after(() => {
  for (const [key, value] of Object.entries(originals)) {
    if (value === undefined) delete global[key]; else global[key] = value;
  }
});

beforeEach(() => {
  const values = new Map();
  global.window = new EventTarget();
  window.localStorage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  global.document = { documentElement: { dataset: {} } };
});

function storageEvent(key, newValue, storageArea = window.localStorage) {
  const event = new Event("storage");
  Object.assign(event, { key, newValue, storageArea });
  window.dispatchEvent(event);
}

test("all twelve themes persist and bootstrap before hydration", () => {
  assert.equal(themes.INTERFACE_THEMES.length, 12);
  assert.equal(new Set(themes.INTERFACE_THEMES.map(theme => theme.id)).size, 12);
  for (const theme of themes.INTERFACE_THEMES) {
    assert.equal(themes.saveInterfaceTheme(theme), true);
    assert.equal(window.localStorage.getItem(themes.INTERFACE_THEME_KEY), theme.id);
    document.documentElement.dataset = {};
    vm.runInNewContext(themes.interfaceThemeBootstrap, { document, localStorage: window.localStorage });
    assert.deepEqual(document.documentElement.dataset, { theme: theme.mode, palette: theme.id });
    assert.equal(themes.readInterfaceTheme(), theme);
  }
});

test("unknown and removed preferences fall back to light", () => {
  for (const id of [null, "unknown", "<script>", "__proto__"]) {
    assert.equal(themes.getInterfaceTheme(id).id, "light");
    window.localStorage.setItem(themes.INTERFACE_THEME_KEY, id);
    vm.runInNewContext(themes.interfaceThemeBootstrap, { document, localStorage: window.localStorage });
    assert.equal(document.documentElement.dataset.palette, "light");
  }
});

test("storage denied or full keeps the chosen theme active until reload", () => {
  window.localStorage.setItem(themes.INTERFACE_THEME_KEY, "ocean");
  window.localStorage.setItem = () => { throw new Error("quota exceeded"); };
  const theme = themes.getInterfaceTheme("cocoa");
  assert.equal(themes.saveInterfaceTheme(theme), false);
  assert.equal(themes.readInterfaceTheme(), theme);
  Object.defineProperty(window, "localStorage", { get() { throw new Error("denied"); } });
  assert.equal(themes.saveInterfaceTheme(theme), false);
  assert.equal(themes.readInterfaceTheme(), theme);
  document.documentElement.dataset = {};
  assert.doesNotThrow(() => vm.runInNewContext(themes.interfaceThemeBootstrap, {
    document, get localStorage() { throw new Error("denied"); },
  }));
  assert.equal(document.documentElement.dataset.palette, "light");
});

test("subscriptions update same-page pickers, other tabs and storage clearing; cleanup works", () => {
  let changes = 0;
  const unsubscribe = themes.subscribeInterfaceTheme(() => { changes++; });
  themes.saveInterfaceTheme(themes.getInterfaceTheme("forest"));
  assert.equal(changes, 1);
  storageEvent(themes.INTERFACE_THEME_KEY, "midnight");
  assert.equal(themes.readInterfaceTheme().id, "midnight");
  assert.equal(changes, 2);
  storageEvent("unrelated", "rose");
  storageEvent(themes.INTERFACE_THEME_KEY, "rose", {}); // sessionStorage must not change the theme.
  assert.equal(changes, 2);
  storageEvent(themes.INTERFACE_THEME_KEY, null);
  assert.equal(themes.readInterfaceTheme().id, "light");
  storageEvent(themes.INTERFACE_THEME_KEY, "emerald");
  storageEvent(null, null);
  assert.equal(themes.readInterfaceTheme().id, "light");
  unsubscribe();
  const previous = changes;
  themes.saveInterfaceTheme(themes.getInterfaceTheme("sand"));
  storageEvent(themes.INTERFACE_THEME_KEY, "rose");
  assert.equal(changes, previous);
  assert.equal(themes.readInterfaceTheme().id, "sand");
});

test("server snapshot reads safely without browser globals", () => {
  delete global.window;
  delete global.document;
  assert.equal(themes.readInterfaceTheme().id, "light");
});
