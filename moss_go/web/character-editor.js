import { request, downloadJSON } from "./api.js";
import { t, currentLanguage } from "./i18n.js";

export function cleanCharacter(fields, source) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return {};
  return Object.fromEntries(
    Object.entries(fields)
      .filter(
        ([key, field]) =>
          typeof source[key] === "string" && field.values.includes(source[key]),
      )
      .map(([key]) => [key, source[key]]),
  );
}

export function cleanPins(fields, character, pins) {
  const pinned = new Set(Array.isArray(pins) ? pins : []);
  return Object.keys(fields).filter(
    (key) => pinned.has(key) && Object.hasOwn(character, key),
  );
}

export function characterPrompt(fields, character) {
  return Object.values(cleanCharacter(fields, character)).join(", ");
}

export function portableCharacter(fields, character, pins) {
  const clean = cleanCharacter(fields, character);
  return {
    format: "moss-go-character",
    version: 1,
    character: clean,
    locks: cleanPins(fields, clean, pins),
  };
}

export async function openCharacterEditor(character, pins, onApply) {
  const $ = (id) => document.getElementById(id);
  const dialog = $("character-dialog");
  if (dialog.open) return;
  const controller = new AbortController();
  let schema,
    draft = {},
    locked = [],
    pending = true;
  const fields = $("character-fields");
  const preset = $("character-preset");
  const localized = (item) =>
    currentLanguage() === "ru" ? item.label_ru || item.label : item.label;
  function message(text, isError = false) {
    const output = $("character-notice");
    output.textContent = text;
    output.hidden = !text;
    output.classList.toggle("review-warning", isError);
    output.setAttribute("role", isError ? "alert" : "status");
  }
  function controls(value) {
    pending = value;
    dialog.setAttribute("aria-busy", String(value));
    for (const control of dialog.querySelectorAll(
      ".character-control, #character-fields select, #character-fields button",
    ))
      control.disabled = value || !schema;
    $("export-character").disabled =
      value || !schema || !Object.keys(draft).length;
    if (!value && schema)
      for (const pin of fields.querySelectorAll("[data-pin]"))
        pin.disabled = !draft[pin.dataset.pin];
  }
  function preview() {
    $("character-prompt-text").textContent =
      characterPrompt(schema.fields, draft) || t("noTraitsChosen");
    $("export-character").disabled = pending || !Object.keys(draft).length;
  }
  function changed() {
    preset.value = "";
    message("");
    preview();
  }
  function render() {
    fields.replaceChildren();
    for (const group of ["identity", "wardrobe", "direction"]) {
      const section = document.createElement("fieldset");
      section.className = "character-group";
      const legend = document.createElement("legend");
      legend.textContent = t("characterGroup_" + group);
      const grid = document.createElement("div");
      grid.className = "character-group-fields";
      for (const [key, field] of Object.entries(schema.fields).filter(
        ([, field]) => (field.group || "identity") === group,
      )) {
        const row = document.createElement("div");
        row.className = "character-trait";
        const label = document.createElement("label");
        const name = localized(field);
        const caption = document.createElement("span");
        caption.textContent = name;
        const select = document.createElement("select");
        select.setAttribute("aria-label", name);
        select.dataset.trait = key;
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = t("noTrait");
        select.append(empty);
        for (const value of field.values) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent =
            currentLanguage() === "ru"
              ? field.labels_ru?.[value] || value
              : value;
          select.append(option);
        }
        select.value = draft[key] || "";
        const pin = document.createElement("button");
        pin.type = "button";
        pin.className = "trait-pin quiet";
        pin.dataset.pin = key;
        function updatePin() {
          const active = locked.includes(key);
          pin.setAttribute("aria-pressed", String(active));
          pin.setAttribute(
            "aria-label",
            `${t(active ? "unpinTrait" : "pinTrait")}: ${name}`,
          );
          pin.textContent = t(active ? "pinned" : "pin");
          pin.disabled = !draft[key];
        }
        pin.onclick = () => {
          locked = locked.includes(key)
            ? locked.filter((item) => item !== key)
            : [...locked, key];
          updatePin();
          changed();
        };
        select.onchange = () => {
          if (select.value) draft[key] = select.value;
          else {
            delete draft[key];
            locked = locked.filter((item) => item !== key);
          }
          updatePin();
          changed();
        };
        updatePin();
        label.append(caption, select);
        row.append(label, pin);
        grid.append(row);
      }
      if (grid.childElementCount) {
        section.append(legend, grid);
        fields.append(section);
      }
    }
    preview();
    controls(pending);
  }
  dialog.addEventListener("close", () => controller.abort(), { once: true });
  $("character-retry").hidden = true;
  fields.textContent = t("loadingTraits");
  $("character-prompt-text").textContent = "";
  message("");
  controls(true);
  dialog.showModal();
  async function load() {
    $("character-retry").hidden = true;
    message("");
    fields.textContent = t("loadingTraits");
    controls(true);
    try {
      schema = await request("/characters", undefined, {
        signal: controller.signal,
      });
      if (!dialog.open) return;
      draft = cleanCharacter(schema.fields, character);
      locked = cleanPins(schema.fields, draft, pins);
      preset.replaceChildren();
      const custom = document.createElement("option");
      custom.value = "";
      custom.textContent = t("customCharacter");
      preset.append(custom);
      for (const item of schema.presets || []) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = localized(item);
        preset.append(option);
      }
      if (
        character &&
        Object.keys(character).length !== Object.keys(draft).length
      )
        message(t("unavailableTraitsRemoved"), true);
      pending = false;
      render();
    } catch (exc) {
      if (!dialog.open || controller.signal.aborted) return;
      fields.textContent = "";
      message(t("traitsLoadFailed"), true);
      $("character-retry").hidden = false;
      controls(false);
    }
  }
  $("character-retry").onclick = load;
  preset.onchange = () => {
    const item = schema.presets?.find((item) => item.id === preset.value);
    if (!item) return;
    draft = cleanCharacter(schema.fields, item.character);
    locked = cleanPins(schema.fields, draft, item.locks);
    render();
    message(t("characterDraftReady"));
  };
  $("clear-character").onclick = () => {
    draft = {};
    locked = [];
    preset.value = "";
    render();
    message("");
  };
  $("random-character").onclick = async () => {
    if (pending || !schema) return;
    controls(true);
    message(t("mixingTraits"));
    try {
      const fixed = Object.fromEntries(locked.map((key) => [key, draft[key]]));
      const seed = crypto.getRandomValues(new Uint32Array(1))[0];
      const result = await request(
        "/characters/preview",
        { randomize: true, seed, character: fixed },
        { signal: controller.signal },
      );
      if (!dialog.open) return;
      draft = cleanCharacter(schema.fields, result.character);
      preset.value = "";
      render();
      message(t("characterDraftReady"));
    } catch (exc) {
      if (!controller.signal.aborted) message(exc.message, true);
    } finally {
      if (dialog.open) controls(false);
    }
  };
  $("import-character").onclick = () => $("character-file").click();
  $("character-file").onchange = async () => {
    const file = $("character-file").files[0];
    if (!file || pending || !dialog.open) return;
    controls(true);
    try {
      if (file.size > 120_000) throw new Error(t("characterFileTooLarge"));
      let data;
      try {
        data = JSON.parse(await file.text());
      } catch {
        throw new Error(t("invalidCharacterFile"));
      }
      const result = await request("/characters/import", data, {
        signal: controller.signal,
      });
      if (!dialog.open) return;
      draft = cleanCharacter(schema.fields, result.character);
      locked = cleanPins(schema.fields, draft, result.locks);
      preset.value = "";
      render();
      const removed = result.removed_fields || [];
      message(
        removed.length
          ? `${t("removedSettings")}: ${removed
              .slice(0, 8)
              .map((key) => key.slice(0, 48))
              .join(
                ", ",
              )}${removed.length > 8 ? "…" : ""}. ${t("characterDraftReady")}`
          : t("characterDraftReady"),
        Boolean(removed.length),
      );
    } catch (exc) {
      if (!controller.signal.aborted) message(exc.message, true);
    } finally {
      $("character-file").value = "";
      if (dialog.open) controls(false);
    }
  };
  $("export-character").onclick = () =>
    downloadJSON(
      portableCharacter(schema.fields, draft, locked),
      "moss-go-character.json",
    );
  $("apply-character").onclick = () => {
    if (pending || !schema) return;
    onApply(
      cleanCharacter(schema.fields, draft),
      cleanPins(schema.fields, draft, locked),
    );
    dialog.close();
  };
  await load();
}
