import test from "node:test";
import assert from "node:assert/strict";
import { cleanScenes, scenePlan } from "../moss_go/web/scene-pack.js";

test("scene packs count sequential jobs without enabling them in refine mode", () => {
  assert.deepEqual(scenePlan(["Station", "Workshop"], 4, "reference"), {
    scenes: ["Station", "Workshop"],
    total: 8,
  });
  assert.deepEqual(scenePlan(["Station"], 4, "refine"), {
    scenes: [],
    total: 4,
  });
  assert.equal(scenePlan([], 2, "create").total, 2);
});

test("restored scene drafts ignore corrupt data and stay within request limits", () => {
  assert.deepEqual(cleanScenes(null), []);
  assert.deepEqual(cleanScenes([12, "Station", null]), ["Station"]);
  assert.equal(cleanScenes(["1", "2", "3", "4", "5"]).length, 4);
  assert.equal(cleanScenes(["a".repeat(4000)])[0].length, 3000);
});
