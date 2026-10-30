export function filterHistory(jobs, scope, selected) {
  if (scope === "saved") return jobs.filter((job) => job.output_id);
  if (scope === "batch")
    return selected
      ? jobs.filter((job) => job.batch_id === selected.batch_id)
      : [];
  if (scope !== "versions" || !selected) return jobs;
  const byId = new Map(jobs.map((job) => [job.id, job]));
  let root = selected.id;
  const visited = new Set();
  while (byId.get(root)?.settings.parent_id && !visited.has(root)) {
    visited.add(root);
    root = byId.get(root).settings.parent_id;
  }
  const related = new Set([root]);
  for (let pass = 0; pass < jobs.length; pass++) {
    let changed = false;
    for (const job of jobs) {
      if (!related.has(job.id) && related.has(job.settings.parent_id)) {
        related.add(job.id);
        changed = true;
      }
    }
    if (!changed) break;
  }
  return jobs.filter((job) => related.has(job.id));
}

export function cancellationBatch(jobs, preferred) {
  const active = jobs.filter((job) =>
    ["pending", "submitting", "queued", "running"].includes(job.status),
  );
  return (
    (
      active.find((job) => job.batch_id === preferred) ||
      active.find((job) => job.status === "running") ||
      active[0]
    )?.batch_id ?? null
  );
}

export function nextFailure(jobs, previous, revealedBatch, notified) {
  return jobs.find(
    (job) =>
      job.status === "error" &&
      job.error &&
      !notified.has(job.id) &&
      (["pending", "submitting", "queued", "running"].includes(
        previous.get(job.id),
      ) ||
        job.batch_id === revealedBatch),
  );
}

export function launchParent(mode, refinementParent, recoveryParent) {
  return (
    recoveryParent || (mode === "refine" ? refinementParent : null) || null
  );
}
