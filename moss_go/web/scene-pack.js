import { t } from "./i18n.js";

export function cleanScenes(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => typeof item === "string")
    .slice(0, 4)
    .map((item) => item.slice(0, 3000));
}

export function scenePlan(scenes, variants, mode) {
  const descriptions = mode === "refine" ? [] : cleanScenes(scenes);
  return {
    scenes: descriptions,
    total: Math.max(1, descriptions.length) * Number(variants),
  };
}

export function openScenePack(scenes, onApply) {
  const dialog = document.getElementById("scene-dialog");
  const fields = document.getElementById("scene-fields");
  const add = document.getElementById("scene-add");
  let draft = cleanScenes(scenes);
  if (!draft.length) draft = [""];
  function render() {
    fields.replaceChildren();
    draft.forEach((value, index) => {
      const row = document.createElement("div");
      row.className = "scene-row";
      const label = document.createElement("label");
      label.textContent = `${t("scene")} ${index + 1}`;
      const input = document.createElement("textarea");
      input.rows = 3;
      input.maxLength = 3000;
      input.value = value;
      input.placeholder = t("scenePlaceholder");
      input.oninput = () => {
        draft[index] = input.value;
        input.setCustomValidity("");
      };
      label.append(input);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "quiet";
      remove.textContent = t("remove");
      remove.setAttribute(
        "aria-label",
        `${t("remove")} ${t("scene")} ${index + 1}`,
      );
      remove.onclick = () => {
        draft.splice(index, 1);
        render();
        (fields.querySelector("textarea") || add).focus();
      };
      row.append(label, remove);
      fields.append(row);
    });
    add.disabled = draft.length >= 4;
  }
  add.onclick = () => {
    draft.push("");
    render();
    fields.querySelector(".scene-row:last-child textarea").focus();
  };
  document.getElementById("scene-apply").onclick = () => {
    const empty = draft.findIndex((value) => !value.trim());
    if (empty >= 0) {
      const input = fields.querySelectorAll("textarea")[empty];
      input.setCustomValidity(t("describeScene"));
      input.reportValidity();
      return;
    }
    onApply(draft.map((value) => value.trim()));
    dialog.close();
  };
  document.getElementById("scene-clear").onclick = () => {
    onApply([]);
    dialog.close();
  };
  render();
  dialog.showModal();
}
