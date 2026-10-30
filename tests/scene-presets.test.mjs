import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { scenePresets } from "../moss_go/web/scene-presets.js";

test("visible starter wording stays aligned with the real action benchmark", () => {
  const cases = JSON.parse(
    readFileSync(
      new URL("../moss_go/assets/benchmark_action_v2.json", import.meta.url),
      "utf8",
    ),
  );
  assert.deepEqual(
    scenePresets,
    Object.fromEntries(
      cases.scenes.map((scene) => [scene.id, scene.description]),
    ),
  );
});
