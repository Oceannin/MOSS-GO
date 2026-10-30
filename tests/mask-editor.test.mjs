import test from "node:test";
import assert from "node:assert/strict";
import { maskRectangle } from "../moss_go/web/mask-editor.js";

test("keyboard selection maps percentages to the source, including edge pixels", () => {
  assert.deepEqual(maskRectangle(768, 1024, 40, 40, 20, 20), {
    x: 307,
    y: 410,
    width: 154,
    height: 205,
  });
  assert.deepEqual(maskRectangle(768, 1024, 0, 0, 100, 100), {
    x: 0,
    y: 0,
    width: 768,
    height: 1024,
  });
});
test("invalid rectangles cannot silently select a different region", () => {
  for (const rectangle of [
    [-1, 0, 10, 10],
    [90, 0, 20, 10],
    [0, 0, 0, 10],
    [0, 0, 10, Infinity],
    [0, 99, 10, 2],
  ]) {
    assert.throws(() => maskRectangle(768, 1024, ...rectangle), RangeError);
  }
});
