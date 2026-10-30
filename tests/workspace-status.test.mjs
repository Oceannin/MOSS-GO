import test from "node:test";
import assert from "node:assert/strict";
import { workspaceStatus } from "../moss_go/web/workspace-status.js";

const prepared = {
  system: { connected: true },
  ready: true,
  mode: "reference",
  hasInput: true,
  hasMask: false,
  prompt: "An original courier at a station.",
};

test("idle status never promises readiness without a connection or required setup", () => {
  assert.equal(workspaceStatus({ ...prepared, system: null }), "connecting");
  assert.equal(
    workspaceStatus({ ...prepared, system: { connected: false } }),
    "disconnected",
  );
  assert.equal(workspaceStatus({ ...prepared, ready: false }), "configure");
  assert.equal(workspaceStatus(prepared), "ready");
});

test("the next idle action follows the mode and actual draft", () => {
  assert.equal(
    workspaceStatus({ ...prepared, hasInput: false }),
    "chooseInput",
  );
  assert.equal(
    workspaceStatus({ ...prepared, mode: "create", hasInput: false }),
    "ready",
  );
  assert.equal(workspaceStatus({ ...prepared, mode: "refine" }), "chooseArea");
  assert.equal(
    workspaceStatus({ ...prepared, mode: "refine", hasMask: true }),
    "ready",
  );
  assert.equal(
    workspaceStatus({ ...prepared, prompt: "  " }),
    "enterDescription",
  );
  assert.equal(workspaceStatus({ ...prepared, error: true }), "reviewError");
});

test("an accepted job or unresolved launch stays visible over idle draft instructions", () => {
  const offline = {
    ...prepared,
    system: { connected: false },
    hasInput: false,
  };
  assert.equal(
    workspaceStatus({ ...offline, pending: true }),
    "recoveringLaunch",
  );
  assert.equal(
    workspaceStatus({ ...offline, activeStatus: "queued" }),
    "queued",
  );
  assert.equal(
    workspaceStatus({ ...offline, activeStatus: "running" }),
    "running",
  );
  assert.equal(workspaceStatus({ ...offline, uploading: true }), "uploading");
  assert.equal(workspaceStatus({ ...offline, requesting: true }), "submitting");
});
