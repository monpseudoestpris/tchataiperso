import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import vm from "node:vm";

function loadTsModule(path, deps = {}) {
  const source = ts.transpileModule(readFileSync(path, "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const exportsObj = {};
  const moduleObj = { exports: exportsObj };
  const localRequire = id => {
    if (Object.prototype.hasOwnProperty.call(deps, id)) return deps[id];
    throw new Error(`Unexpected import: ${id}`);
  };
  vm.runInThisContext(`(function(exports, require, module) { ${source}\n})`)(
    exportsObj,
    localRequire,
    moduleObj,
  );
  return moduleObj.exports;
}

const barAggregation = loadTsModule("lib/bar-aggregation.ts");
const chartDividends = loadTsModule("lib/chart-dividends.ts", {
  "./bar-aggregation": barAggregation,
});

const dailyBars = [
  { date: "2025-05-15", open: 180, high: 182, low: 179, close: 181, volume: 1000 },
  { date: "2025-05-16", open: 181, high: 183, low: 180, close: 182, volume: 1100 },
  { date: "2025-05-19", open: 179, high: 180, low: 178, close: 179, volume: 1500 },
  { date: "2025-05-20", open: 179, high: 181, low: 178, close: 180, volume: 1200 },
];

test("projects exact daily dividend and snaps weekend date to next trading day", () => {
  const projected = chartDividends.projectDividendsToBars(
    dailyBars,
    [
      { date: "2025-05-17", value: 1.5, currency: "EUR" }, // Saturday -> snaps to 2025-05-19
      { date: "2025-05-20", value: 2.0, currency: "EUR" }, // Exact
      { date: "2024-05-19", value: 1.0, currency: "EUR" }, // Out of range
    ],
    "day",
    "EUR",
  );
  assert.equal(projected.length, 2);
  assert.equal(projected[0].barDate, "2025-05-19");
  assert.equal(projected[0].barIndex, 2);
  assert.equal(projected[0].totalAmount, 1.5);
  assert.equal(projected[1].barDate, "2025-05-20");
  assert.equal(projected[1].totalAmount, 2.0);
});

test("aggregates multiple dividends inside the same quarter bucket", () => {
  const rawBars = [
    { date: "2025-01-15", open: 100, high: 102, low: 99, close: 101, volume: 500 },
    { date: "2025-02-15", open: 101, high: 104, low: 100, close: 103, volume: 500 },
    { date: "2025-03-20", open: 103, high: 105, low: 102, close: 104, volume: 500 },
    { date: "2025-04-18", open: 104, high: 106, low: 103, close: 105, volume: 500 },
  ];
  const quarterBars = barAggregation.aggregateBars(rawBars, "quarter");
  assert.equal(quarterBars.length, 2);

  const projected = chartDividends.projectDividendsToBars(
    quarterBars,
    [
      { date: "2025-01-25", value: 0.5, currency: "USD" },
      { date: "2025-02-25", value: 0.5, currency: "USD" },
      { date: "2025-04-25", value: 0.6, currency: "USD" },
    ],
    "quarter",
    "USD",
  );
  assert.equal(projected.length, 2);
  assert.equal(projected[0].barDate, "2025-03-20");
  assert.equal(projected[0].totalAmount, 1.0);
  assert.equal(projected[0].events.length, 2);
  assert.equal(projected[1].barDate, "2025-04-18");
  assert.equal(projected[1].totalAmount, 0.6);
});

test("switches marker text to compact D when more than 16 dividends are visible", () => {
  const many = Array.from({ length: 18 }, (_, i) => ({
    barDate: `2025-01-${String(i + 1).padStart(2, "0")}`,
    barIndex: i,
    totalAmount: 1.25,
    currency: "EUR",
    yieldPct: 1.2,
    events: [{ date: `2025-01-${String(i + 1).padStart(2, "0")}`, value: 1.25, currency: "EUR" }],
  }));
  const compactMarkers = chartDividends.buildDividendChartMarkers(many, false);
  assert.equal(compactMarkers.length, 18);
  assert.equal(compactMarkers[0].text, "D");

  const detailedMarkers = chartDividends.buildDividendChartMarkers(many.slice(0, 3), true);
  assert.equal(detailedMarkers.length, 3);
  assert.match(detailedMarkers[0].text, /^D 1[.,]25$/);
});
