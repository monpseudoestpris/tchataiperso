import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import vm from "node:vm";

const source = ts.transpileModule(readFileSync("lib/finance-game-helpers.ts", "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS },
}).outputText;

const helpers = {};
vm.runInThisContext(`(function(exports, require) { ${source}\n})`)(helpers, () => ({}));

test("formatRelativeSessionLabel formats T0, past and future bars", () => {
  assert.equal(helpers.formatRelativeSessionLabel(10, 10, "day"), "T0");
  assert.equal(helpers.formatRelativeSessionLabel(4, 10, "day"), "J-6");
  assert.equal(helpers.formatRelativeSessionLabel(15, 10, "day"), "J+5");
  assert.equal(helpers.formatRelativeSessionLabel(8, 10, "week"), "S-2");
  assert.equal(helpers.formatRelativeSessionLabel(13, 10, "month"), "M+3");
});

test("computeQuickSlTp calculates symmetric Long and Short targets", () => {
  const longTargets = helpers.computeQuickSlTp(100, "long", 5, 10);
  assert.equal(longTargets.sl, 95);
  assert.equal(longTargets.tp, 110);

  const shortTargets = helpers.computeQuickSlTp(100, "short", 5, 10);
  assert.equal(shortTargets.sl, 105);
  assert.equal(shortTargets.tp, 90);
});

test("buildRoundChartOverlays orders markers chronologically and emits SL/TP lines", () => {
  const overlays = helpers.buildRoundChartOverlays({
    id: "r1",
    status: "finished",
    blind_mode: false,
    is_revealed: true,
    universe_type: "all",
    universe_value: "",
    timeframe: "day",
    horizon_code: "1m",
    symbol: "AI.PA",
    company_name: "Air Liquide",
    exchange: "PA",
    sector: "Materials",
    currency: "EUR",
    cutoff_index: 1,
    horizon_bars: 2,
    current_step: 2,
    remaining_bars: 0,
    cutoff_date: "2024-01-03",
    end_date: "2024-01-05",
    cutoff_price: 100,
    current_price: 110,
    change_from_cutoff_pct: 10,
    position_side: "long",
    position_status: "closed",
    position_size_pct: 100,
    stake_amount: 10000,
    entry_step: 0,
    entry_date: "2024-01-03",
    entry_price: 100,
    stop_loss: 95,
    take_profit: 110,
    exit_step: 2,
    exit_date: "2024-01-05",
    exit_price: 110,
    exit_reason: "take_profit",
    return_pct: 10,
    pnl_amount: 1000,
    unrealized_return_pct: null,
    unrealized_pnl: null,
    buy_hold_return_pct: 10,
    triggered_event: null,
    bars: [
      { date: "2024-01-02", open: 99, high: 101, low: 98, close: 99.5, volume: 1000 },
      { date: "2024-01-03", open: 99.5, high: 101, low: 99, close: 100, volume: 1200 },
      { date: "2024-01-04", open: 100, high: 106, low: 100, close: 105, volume: 1300 },
      { date: "2024-01-05", open: 105, high: 111, low: 104, close: 110, volume: 1500 },
    ],
    created_at: "2024-01-05T00:00:00Z",
    finished_at: "2024-01-05T00:00:00Z",
  });

  assert.equal(overlays.priceLines.length, 3);
  assert.equal(overlays.markers.length, 3);
  assert.deepEqual(
    overlays.markers.map((m) => m.text),
    ["T0", "ACHAT", "TP"],
  );
  assert.ok(overlays.markers[0].time <= overlays.markers[1].time);
  assert.ok(overlays.markers[1].time <= overlays.markers[2].time);
});

test("resolveHorizonForTimeframe adapts horizon to selected timeframe up to 5y", () => {
  assert.equal(helpers.resolveHorizonForTimeframe("day", "3m"), "3m");
  assert.equal(helpers.resolveHorizonForTimeframe("day", "5y"), "3m");
  assert.equal(helpers.resolveHorizonForTimeframe("week", "5y"), "5y");
  assert.equal(helpers.resolveHorizonForTimeframe("week", "1w"), "1y");
  assert.equal(helpers.resolveHorizonForTimeframe("month", "5y"), "5y");
  assert.equal(helpers.resolveHorizonForTimeframe("month", "1m"), "2y");
});
