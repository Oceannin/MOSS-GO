import test from "node:test";
import assert from "node:assert/strict";
import {
  filterHistory,
  cancellationBatch,
  launchParent,
  nextFailure,
} from "../moss_go/web/history.js";

test("an immediate failure is announced even before the first active-job poll, once", () => {
  const failed = {
    id: "failed",
    batch_id: "new-batch",
    status: "error",
    error: "Out of memory",
  };
  const notified = new Set();
  assert.equal(nextFailure([failed], new Map(), "new-batch", notified), failed);
  notified.add(failed.id);
  assert.equal(
    nextFailure([failed], new Map(), "new-batch", notified),
    undefined,
  );
  assert.equal(
    nextFailure([failed], new Map(), "other-batch", new Set()),
    undefined,
  );
  assert.equal(
    nextFailure(
      [failed],
      new Map([[failed.id, "running"]]),
      "other-batch",
      new Set(),
    ),
    failed,
  );
});

test("recovery retains its failed parent in every mode without linking unrelated creation", () => {
  for (const mode of ["create", "reference", "refine"])
    assert.equal(
      launchParent(mode, "source-take", "failed-take"),
      "failed-take",
    );
  assert.equal(launchParent("create", "source-take", null), null);
  assert.equal(launchParent("reference", "source-take", null), null);
  assert.equal(launchParent("refine", "source-take", null), "source-take");
});

const jobs = [
  {
    id: "child2",
    batch_id: "b2",
    settings: { parent_id: "child1" },
    output_id: "3",
  },
  {
    id: "sibling",
    batch_id: "b1",
    settings: { parent_id: "root" },
    output_id: "4",
  },
  { id: "unrelated", batch_id: "b3", settings: {}, output_id: null },
  {
    id: "child1",
    batch_id: "b1",
    settings: { parent_id: "root" },
    output_id: "2",
  },
  { id: "root", batch_id: "b0", settings: {}, output_id: "1" },
];
test("versions connect ancestors, descendants and sibling refinements", () => {
  assert.deepEqual(
    filterHistory(jobs, "versions", jobs[0]).map((job) => job.id),
    ["child2", "sibling", "child1", "root"],
  );
  assert.deepEqual(
    filterHistory(jobs, "batch", jobs[1]).map((job) => job.id),
    ["sibling", "child1"],
  );
});
test("missing old ancestors and malformed cycles do not hang history", () => {
  assert.equal(filterHistory(jobs.slice(0, -1), "versions", jobs[0]).length, 3);
  const cyclic = [
    { id: "a", settings: { parent_id: "b" } },
    { id: "b", settings: { parent_id: "a" } },
  ];
  assert.equal(filterHistory(cyclic, "versions", cyclic[0]).length, 2);
  assert.equal(filterHistory(jobs, "saved").length, 4);
});

test("cancelling a batch never broadens to every active batch after reload", () => {
  const active = [
    { batch_id: "mine", status: "pending" },
    { batch_id: "other", status: "running" },
  ];
  assert.equal(cancellationBatch(active, "mine"), "mine");
  assert.equal(cancellationBatch(active, null), "other");
  assert.equal(cancellationBatch(active, "finished"), "other");
  assert.equal(
    cancellationBatch([{ batch_id: "old", status: "done" }], null),
    null,
  );
});
