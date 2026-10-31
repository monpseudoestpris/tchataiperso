const test = require("node:test");
const assert = require("node:assert");

function extractThoughtAndContent(text) {
  if (!text) return { thought: "", cleanContent: "" };
  const thinkMatch = text.match(/^<think>([\s\S]*?)<\/think>\s*/);
  if (thinkMatch) {
    return {
      thought: thinkMatch[1].trim(),
      cleanContent: text.slice(thinkMatch[0].length),
    };
  }
  return { thought: "", cleanContent: text };
}

test("extractThoughtAndContent correctly splits <think> block from final answer", () => {
  const raw = `<think>
Voici le raisonnement détaillé :
1. Analyser les données
2. Vérifier les chiffres
</think>

Voici la réponse finale complète.`;

  const parsed = extractThoughtAndContent(raw);
  assert.strictEqual(parsed.thought, "Voici le raisonnement détaillé :\n1. Analyser les données\n2. Vérifier les chiffres");
  assert.strictEqual(parsed.cleanContent, "Voici la réponse finale complète.");
});

test("extractThoughtAndContent leaves text untouched if no <think> block", () => {
  const raw = "Réponse directe sans balise.";
  const parsed = extractThoughtAndContent(raw);
  assert.strictEqual(parsed.thought, "");
  assert.strictEqual(parsed.cleanContent, raw);
});

