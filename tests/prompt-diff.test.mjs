import test from "node:test";
import assert from "node:assert/strict";
import { diffWords } from "../moss_go/web/prompt-diff.js";

function roundtrip(before, after) {
  const changes = diffWords(before, after);
  assert.equal(
    changes
      .filter((op) => op.kind !== "insert")
      .map((op) => op.text)
      .join(""),
    before,
  );
  assert.equal(
    changes
      .filter((op) => op.kind !== "delete")
      .map((op) => op.text)
      .join(""),
    after,
  );
  return changes;
}

test("word review preserves exact quoted text, Unicode and whitespace", () => {
  const changes = roundtrip(
    'A sign: "Тихая мастерская"\n3 birds.',
    'A wooden sign: "Тихая мастерская"\n3 orange birds.',
  );
  assert.ok(
    changes.some((op) => op.kind === "insert" && op.text.includes("orange")),
  );
  assert.ok(
    changes
      .filter((op) => op.kind === "equal")
      .some((op) => op.text.includes("Тихая мастерская")),
  );
});
test("unchanged prompts and empty edits are represented truthfully", () => {
  assert.deepEqual(roundtrip("One cup.", "One cup."), [
    { kind: "equal", text: "One cup." },
  ]);
  roundtrip("One cup.", "");
  roundtrip("", "Two cups.");
  roundtrip("", "");
});
test("long replacements stay bounded and retain both complete texts", () => {
  const changes = roundtrip(
    "shared " + "old ".repeat(700) + "end",
    "shared " + "new ".repeat(700) + "end",
  );
  assert.ok(changes.length <= 4);
});
