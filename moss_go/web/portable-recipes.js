import { API, request, imageURL } from "./api.js";
import { t } from "./i18n.js";

export async function reviewRecipeFile(file, onApply) {
  if (!file) return;
  if (file.size > 100 * 1024 ** 2) throw new Error(t("packTooLarge"));
  const dialog = document.getElementById("recipe-dialog");
  const content = document.getElementById("recipe-content");
  content.removeAttribute("role");
  content.textContent = t("readingPack");
  dialog.showModal();
  try {
    let items;
    if (file.name.toLowerCase().endsWith(".zip")) {
      const body = new FormData();
      body.append("bundle", file);
      items = (
        await request("/recipes/import", undefined, { method: "POST", body })
      ).items;
    } else {
      if (file.size > 1024 ** 2) throw new Error(t("recipeTooLarge"));
      let data;
      try {
        data = JSON.parse(await file.text());
      } catch {
        throw new Error(t("invalidRecipe"));
      }
      items = [await request("/recipes/preview", data)];
    }
    content.replaceChildren();
    const intro = document.createElement("p");
    intro.className = "hint";
    intro.textContent = t("reviewRecipeHint");
    content.append(intro);
    for (const [index, item] of items.entries()) {
      const section = document.createElement("section");
      section.className = "recipe-review";
      const title = document.createElement("h3");
      title.textContent = `${t("nextTake")} ${index + 1}`;
      section.append(title);
      if (item.imported_output_id) {
        const image = document.createElement("img");
        image.src = imageURL(item.imported_output_id);
        image.alt = t("importedImage");
        section.append(image);
      }
      const summary = document.createElement("p");
      const settings = item.settings;
      const size =
        settings.mode === "refine"
          ? t("originalSize")
          : settings.size
            ? `${settings.size.width} × ${settings.size.height}`
            : "";
      summary.textContent = [
        settings.engine,
        t(settings.mode),
        `Seed ${settings.seed}`,
        size,
      ]
        .filter(Boolean)
        .join(" · ");
      section.append(summary);
      const prompt = document.createElement("p");
      prompt.className = "recipe-prompt";
      prompt.textContent = settings.prompt;
      section.append(prompt);
      const details = document.createElement("details");
      const caption = document.createElement("summary");
      caption.textContent = t("allSettings");
      const code = document.createElement("pre");
      code.textContent = JSON.stringify(settings, null, 2);
      details.append(caption, code);
      section.append(details);
      const removed = [
        ...item.removed_fields,
        ...item.removed_character_fields,
      ];
      if (removed.length || item.missing_inputs.length) {
        const warning = document.createElement("p");
        warning.className = "review-warning";
        warning.textContent = [
          item.missing_inputs.length ? t("recipeMissingInputs") : "",
          removed.length
            ? `${t("removedSettings")}: ${removed.join(", ")}`
            : "",
        ]
          .filter(Boolean)
          .join(" ");
        section.append(warning);
      }
      const apply = document.createElement("button");
      apply.type = "button";
      apply.className = "secondary";
      apply.textContent = t("loadSettings");
      apply.onclick = () => {
        onApply(item);
        dialog.close();
      };
      section.append(apply);
      content.append(section);
    }
  } catch (exc) {
    content.textContent = exc.message;
    content.setAttribute("role", "alert");
  }
}

export function openExport(job, jobs) {
  if (!job?.output_id) return;
  const dialog = document.getElementById("export-dialog");
  document.getElementById("export-json").href = `${API}/jobs/${job.id}/recipe`;
  document.getElementById("export-take").href = `${API}/jobs/${job.id}/bundle`;
  const siblings = jobs.filter((item) => item.batch_id === job.batch_id);
  const pack = document.getElementById("export-pack");
  const ready =
    siblings.length > 0 &&
    siblings.every((item) => item.output_id && item.status === "done");
  pack.hidden = !ready;
  if (ready) pack.href = `${API}/batches/${job.batch_id}/bundle`;
  document.getElementById("export-wait").hidden = ready;
  dialog.showModal();
}
