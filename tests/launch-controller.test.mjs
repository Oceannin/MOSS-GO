import test from "node:test";
import assert from "node:assert/strict";
import { LaunchController } from "../moss_go/web/launch-controller.js";

const settings = {
  request_id: "a".repeat(32),
  mode: "create",
  prompt: "An original clockmaker.",
  character: { hair: "short silver hair" },
};
const memory = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
};

test("a lost response and reload retry the identical launch snapshot", async () => {
  const storage = memory();
  const first = new LaunchController(async () => {
    throw new TypeError("Connection lost");
  }, storage);
  const draft = structuredClone(settings);
  first.prepare(draft);
  draft.prompt = "A different draft";
  draft.character.hair = "changed";
  await assert.rejects(first.send());
  let posted;
  const reloaded = new LaunchController(async (path, body) => {
    posted = structuredClone(body);
    assert.equal(path, "/jobs");
    return { id: "batch-a" };
  }, storage);
  assert.deepEqual(reloaded.pending, settings);
  assert.equal(reloaded.persisted, true);
  assert.deepEqual(await reloaded.send(), { id: "batch-a" });
  assert.deepEqual(posted, settings);
  assert.equal(new LaunchController(() => {}, storage).pending, null);
});

test("finding an accepted request recovers it without another POST", async () => {
  const paths = [];
  const controller = new LaunchController(async (path, body) => {
    assert.equal(body, undefined);
    paths.push(path);
    return { batch: { id: "accepted" } };
  }, memory());
  controller.prepare(settings);
  assert.deepEqual(await controller.reconcile(), { id: "accepted" });
  assert.deepEqual(paths, [`/requests/${settings.request_id}`]);
  assert.equal(controller.pending, null);
});

test("explicit validation errors unlock editing; server failures keep recovery", async () => {
  for (const [status, code, keep] of [
    [400, "invalid_request", false],
    [409, "models_missing", false],
    [409, "request_conflict", true],
    [503, "internal_error", true],
  ]) {
    const controller = new LaunchController(async () => {
      throw Object.assign(new Error("rejected"), { status, code });
    }, memory());
    controller.prepare(settings);
    await assert.rejects(controller.send());
    assert.equal(Boolean(controller.pending), keep);
  }
});

test("a delayed lookup for an older launch cannot discard a newer intent", async () => {
  let resolve;
  const controller = new LaunchController(
    () => new Promise((done) => (resolve = done)),
    memory(),
  );
  controller.prepare(settings);
  const lookup = controller.reconcile();
  controller.clear();
  controller.prepare({ ...settings, request_id: "b".repeat(32) });
  resolve({ batch: { id: "old-batch" } });
  assert.equal(await lookup, null);
  assert.equal(controller.pending.request_id, "b".repeat(32));
});

test("unavailable browser storage still permits an in-memory launch", async () => {
  const controller = new LaunchController(async () => ({ id: "batch" }), {
    getItem() {
      throw new Error("blocked");
    },
    setItem() {
      throw new Error("blocked");
    },
    removeItem() {
      throw new Error("blocked");
    },
  });
  controller.prepare(settings);
  assert.equal(controller.persisted, false);
  assert.equal((await controller.send()).id, "batch");
  assert.equal(controller.pending, null);
});
