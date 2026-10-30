import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  cleanCharacter,
  cleanPins,
  characterPrompt,
  portableCharacter,
} from "../moss_go/web/character-editor.js";

const catalog = JSON.parse(
  readFileSync(
    new URL("../moss_go/assets/character_catalog.json", import.meta.url),
    "utf8",
  ),
);
const fields = Object.fromEntries(
  Object.entries(catalog.fields).map(([key, field]) => [
    key,
    { values: field.options.map(([value]) => value) },
  ]),
);

test("draft cleaning keeps only catalog values and selected pins", () => {
  const clean = cleanCharacter(fields, {
    hair: "short silver hair",
    eyes: { nested: true },
    role: "unrecognized",
    unsupported: true,
  });
  assert.deepEqual(clean, { hair: "short silver hair" });
  assert.deepEqual(
    cleanPins(fields, clean, ["hair", "hair", "eyes", "unsupported"]),
    ["hair"],
  );
  assert.deepEqual(cleanCharacter(fields, null), {});
});

test("portable presets carry values and pins independently of interface language", () => {
  const preset = catalog.presets[2];
  const portable = portableCharacter(fields, preset.character, preset.locks);
  assert.equal(portable.format, "moss-go-character");
  assert.equal(portable.version, 1);
  assert.equal(portable.character.hair, "two long purple braids");
  assert.deepEqual(new Set(portable.locks), new Set(preset.locks));
  assert.equal(
    characterPrompt(fields, {
      eyes: "green eyes",
      role: "a courier",
      hair: "short silver hair",
    }),
    "a courier, short silver hair, green eyes",
  );
});
