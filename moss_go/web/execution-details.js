import { request } from "./api.js";
import { t } from "./i18n.js";
let revision = 0;

export async function openExecutionDetails(job) {
  if (!job) return;
  const ticket = ++revision;
  const dialog = document.getElementById("execution-dialog");
  const content = document.getElementById("execution-content");
  content.replaceChildren();
  content.textContent = "…";
  dialog.showModal();
  try {
    const recorded = await request(`/jobs/${job.id}`);
    const execution = recorded.execution;
    if (!dialog.open || ticket !== revision) return;
    content.replaceChildren();
    const paragraph = (text) => {
      const p = document.createElement("p");
      p.textContent = text;
      content.append(p);
    };
    const model = execution?.models?.model || job.settings.engine;
    const precision = model.includes("int8")
      ? "INT8"
      : model.includes("fp8")
        ? "FP8"
        : model.includes("bf16")
          ? "BF16"
          : "—";
    paragraph(
      `${job.settings.engine} · ${t("precision")}: ${precision} · ${job.settings.steps} ${t("steps")} · Seed ${job.settings.seed}`,
    );
    if (!execution) {
      paragraph(t("noExecutionMetadata"));
      return;
    }
    const section = (label, value, open = false) => {
      if (value == null) return;
      const details = document.createElement("details");
      details.open = open;
      const summary = document.createElement("summary");
      summary.textContent = label;
      const pre = document.createElement("p");
      pre.className = "execution-value";
      pre.textContent =
        typeof value === "string" ? value : JSON.stringify(value, null, 2);
      details.append(summary, pre);
      content.append(details);
    };
    section(t("originalPrompt"), job.settings.prompt);
    section(t("expandedPrompt"), execution.runtime?.expanded_prompt, true);
    section(t("modelComponents"), execution.models);
    section(t("runtimeVersions"), execution.settings?.runtime_versions);
  } catch (error) {
    if (dialog.open && ticket === revision) content.textContent = error.message;
  }
}
