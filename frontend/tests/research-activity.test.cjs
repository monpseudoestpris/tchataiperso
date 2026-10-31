const { after, test } = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { mkdtempSync, rmSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");

const output = mkdtempSync(path.join(tmpdir(), "clair-research-test-"));
after(() => rmSync(output, { recursive: true, force: true }));
execFileSync(process.execPath, ["node_modules/typescript/bin/tsc", "lib/research-activity.ts", "lib/api.ts",
  "--outDir", output, "--target", "ES2020", "--module", "commonjs", "--skipLibCheck"], { stdio: "pipe" });
const { collectResearchSites } = require(path.join(output, "research-activity.js"));
const { streamMessage } = require(path.join(output, "api.js"));

test("site states distinguish results from read pages and reject unsafe links", () => {
  const source = { title: "Document", url: "https://example.org/document" };
  const events = [
    { sources: [{ ...source, state: "found" }] },
    { sources: [{ ...source, state: "read" }] },
    { sources: [{ ...source, state: "selected" }] },
    { sources: [{ title: "Unsafe", url: "javascript:alert(1)", state: "found" }] },
    { sources: [{ title: "Credentials", url: "https://user:password@example.org", state: "found" }] },
  ];
  assert.deepEqual(collectResearchSites(events, [source]), [{ ...source, state: "read" }]);
  assert.equal(collectResearchSites([], [source])[0].state, "selected");
});

test("SSE parser delivers research activity independently of report text", async () => {
  const previousFetch = global.fetch;
  const activity = { kind: "query", query: "insertion", message: "Recherche lancée", timestamp: "2026-10-30T12:00:00Z" };
  const frames = `event: research_activity\ndata: ${JSON.stringify(activity)}\n\nevent: done\ndata: {}\n\n`;
  global.fetch = async () => new Response(new ReadableStream({ start(controller) {
    const encoded = new TextEncoder().encode(frames);
    controller.enqueue(encoded.slice(0, 40));
    controller.enqueue(encoded.slice(40));
    controller.close();
  } }));
  try {
    const events = [];
    await streamMessage("test-conversation", {}, new AbortController().signal, event => events.push(event));
    assert.deepEqual(events.map(event => event.type), ["research_activity", "done"]);
    assert.deepEqual(events[0].data, activity);
    assert.equal(events.some(event => event.type === "delta"), false);
  } finally { global.fetch = previousFetch; }
});
