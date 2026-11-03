import { request, uploadImage, imageURL } from "./api.js";
import { t, applyTranslations, currentLanguage, setLanguage } from "./i18n.js";
import { editMask } from "./mask-editor.js";
import { openPromptAssistant } from "./prompt-assistant.js";
import { openScenePack, cleanScenes, scenePlan } from "./scene-pack.js";
import { openExport, reviewRecipeFile } from "./portable-recipes.js";
import {
  filterHistory,
  cancellationBatch,
  launchParent,
  nextFailure,
} from "./history.js";
import { inspectImage } from "./image-inspector.js";
import { scenePresets } from "./scene-presets.js";
import { openCharacterEditor } from "./character-editor.js";
import { LaunchController } from "./launch-controller.js";
import { chooseExample } from "./examples.js";
import { openExecutionDetails } from "./execution-details.js";
import { workspaceStatus } from "./workspace-status.js";
import {
  effectiveProfile,
  modeReadiness,
  renderDevice as renderDeviceInfo,
  renderEquipment,
} from "./equipment.js";

const launches = new LaunchController(request);

const $ = (id) => document.getElementById(id);
const icon = (paths) =>
  `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
$("theme").innerHTML = icon(
  '<circle cx="12" cy="12" r="8"/><path d="M12 4v16M12 4a8 8 0 0 1 0 16Z"/>',
);
$("upload-icon").innerHTML = icon(
  '<path d="M12 16V4m-4 4 4-4 4 4M4 16v4h16v-4"/>',
);
const state = {
  mode: "reference",
  input: null,
  mask: null,
  parent: null,
  recoveryParent: null,
  selected: null,
  selectedId: null,
  jobs: [],
  system: null,
  character: {},
  characterLocks: [],
  requesting: false,
  uploading: false,
  lastRender: "",
  activeBatch: null,
  revealBatch: null,
  scenes: [],
  recipeExtras: {},
  maskRequired: false,
  engines: {
    create: "flux3-klein",
    reference: "flux3-klein",
    refine: "flux3-klein",
  },
  failedJob: null,
  notifiedFailures: new Set(),
};
const activeStatuses = new Set(["pending", "submitting", "queued", "running"]);
let toastTimer,
  pollTimer,
  restoredEngine,
  systemRevision = 0,
  modeInitialized = false,
  refreshing = false;
function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("toast").hidden = true), 4000);
}
function error(message, job = null) {
  $("form-error").textContent = message;
  $("form-error").hidden = !message;
  state.failedJob = message ? job : null;
  $("recover-take").hidden = !state.failedJob;
  $("recover-take").textContent = t(
    ["out_of_memory", "batch_memory_hold"].includes(job?.error_code)
      ? "recoverInEconomy"
      : "recoverTake",
  );
  updateControls();
}
function jobError(job) {
  if (
    ["system_memory_exhausted", "batch_system_memory_hold"].includes(
      job.error_code,
    )
  )
    return t("systemMemoryExhausted");
  if (job.error_code === "out_of_memory") return t("outOfMemory");
  if (job.error_code === "batch_memory_hold") return t("batchMemoryHold");
  return job.error;
}
function takeStatus(job) {
  return t(
    ["batch_memory_hold", "batch_system_memory_hold"].includes(job.error_code)
      ? "held"
      : job.status,
  );
}
function selectedEngine() {
  return $("engine").value;
}
function isBusy() {
  return (
    state.requesting ||
    state.uploading ||
    state.jobs.some((job) => activeStatuses.has(job.status))
  );
}
function persist() {
  try {
    localStorage.setItem(
      "moss-go.workspace.v1",
      JSON.stringify({
        mode: state.mode,
        engine: $("engine").value,
        engines: state.engines,
        prompt: $("prompt").value,
        negative: $("negative").value,
        format: $("format").value,
        quality: $("quality").value,
        flux3_steps: Number($("flux3-steps").value),
        prompt_upsampler: $("flux3-upsampler").checked,
        variants: $("variants").value,
        profile: $("profile").value,
        seed: $("seed").value,
        character: state.character,
        characterLocks: state.characterLocks,
        input: state.input,
        mask: state.mask,
        parent: state.parent,
        recoveryParent: state.recoveryParent,
        maskRequired: state.maskRequired,
        selectedId: state.selectedId,
        historyScope: $("history-scope").value,
        activeBatch: state.activeBatch,
        revealBatch: state.revealBatch,
        scenes: state.scenes,
        recipeExtras: state.recipeExtras,
      }),
    );
  } catch {}
}
function mode(next, { keepInput = true } = {}) {
  if (!["create", "reference", "refine"].includes(next)) return;
  if (modeInitialized) state.engines[state.mode] = $("engine").value;
  if (state.mode !== next) {
    state.mask = null;
    state.maskRequired = false;
    state.recoveryParent = null;
  }
  state.mode = next;
  error("");
  for (const button of document.querySelectorAll("[data-mode]"))
    button.setAttribute("aria-pressed", String(button.dataset.mode === next));
  $("input-section").hidden = next === "create";
  $("refine-settings").hidden = next !== "refine";
  $("starters").hidden = next === "refine";
  $("scenes-open").hidden = next === "refine";
  const previous = state.engines[next];
  $("engine").replaceChildren();
  const choices =
    next === "reference"
      ? [
          ["flux-klein", "FLUX.2 Klein · 4B"],
          ["moss-charref", `MOSS · CharRef · ${t("experimental")}`],
        ]
      : next === "create"
        ? [
            ["moss", "MOSS · SFT"],
            ["flux-klein", "FLUX.2 Klein · 4B"],
          ]
        : [
            ["flux-klein", "FLUX.2 Klein · 4B"],
            ["moss", "MOSS · SFT"],
          ];
  choices.unshift(["flux3-klein", t("flux3Recommended")]);
  for (const [value, label] of choices) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    $("engine").append(option);
  }
  if (choices.some(([value]) => value === previous))
    $("engine").value = previous;
  modeInitialized = true;
  $("prompt-label").textContent = t(
    next === "create"
      ? "imageDescription"
      : next === "refine"
        ? "correction"
        : "sceneDescription",
  );
  $("prompt").placeholder = t(
    next === "create"
      ? "createPlaceholder"
      : next === "refine"
        ? "refinePlaceholder"
        : "referencePlaceholder",
  );
  $("empty-title").textContent = t(
    next === "create"
      ? "createTitle"
      : next === "refine"
        ? "refineTitle"
        : "emptyTitle",
  );
  $("empty-copy").textContent = t(
    next === "create"
      ? "createCopy"
      : next === "refine"
        ? "refineCopy"
        : "emptyCopy",
  );
  if (!keepInput) setInput(null);
  updateControls();
  persist();
}
function setInput(input) {
  state.input = input;
  state.recoveryParent = null;
  state.mask = null;
  state.parent = null;
  $("input-clear").hidden = !input;
  $("input-preview").hidden = !input;
  $("input-pick").classList.toggle("has-image", Boolean(input));
  if (input) $("input-preview").src = input.url || imageURL(input.id);
  else $("input-preview").removeAttribute("src");
  persist();
  updateControls();
  if (input && !input.width)
    request(`/images/${input.id}/metadata`)
      .then((metadata) => {
        if (state.input?.id !== input.id) return;
        state.input = { ...metadata, url: imageURL(input.id) };
        persist();
        updateControls();
      })
      .catch((exc) => error(exc.message));
}
async function acceptFile(file) {
  if (!file || launches.pending || state.uploading) return;
  error("");
  try {
    state.uploading = true;
    updateControls();
    $("input-pick").disabled = true;
    toast(t("uploading"));
    setInput(await uploadImage(file));
    toast(t("uploaded"));
  } catch (exc) {
    error(exc.message || t("uploadFailed"));
  } finally {
    state.uploading = false;
    $("input-pick").disabled = false;
    updateControls();
  }
}
function memoryProfile() {
  return effectiveProfile(state.system, $("profile").value);
}
function updateControls() {
  const pending = Boolean(launches.pending);
  $("settings-fields").disabled = pending || state.requesting;
  $("use-result").disabled = pending || state.requesting;
  $("recover-take").disabled = pending || isBusy();
  $("import-recipe").disabled = pending || state.requesting;
  $("examples-open").disabled = pending || state.requesting || state.uploading;
  for (const button of document.querySelectorAll("[data-mode]"))
    button.disabled = pending || state.requesting;
  $("pending-launch").hidden = !pending;
  $("pending-launch").textContent = pending
    ? t(launches.persisted ? "pendingLaunch" : "pendingLaunchMemory")
    : "";
  const plan = scenePlan(state.scenes, $("variants").value, state.mode);
  $("scenes-open").textContent = state.scenes.length
    ? `${t("scenePack")} · ${state.scenes.length}`
    : t("addScenes");
  $("scene-summary").hidden = !plan.scenes.length;
  $("scene-summary").textContent =
    `${t("scenePack")}: ${plan.scenes.length} × ${$("variants").value} = ${plan.total}`;
  $("generate").textContent = pending
    ? t("recoverLaunch")
    : plan.scenes.length
      ? `${t("generatePack")} · ${plan.total}`
      : t("generate");
  const engine = selectedEngine(),
    connected = state.system?.connected,
    ready = modeReadiness(
      state.system,
      engine,
      memoryProfile(),
      state.mode,
      $("flux3-upsampler").checked,
    ).ready;
  $("format").closest("label").hidden = state.mode === "refine";
  const flux = ["flux-klein", "flux3-klein"].includes(engine);
  $("quality").closest("label").hidden = flux;
  $("strength").closest("label").hidden = flux;
  $("negative").closest("label").hidden = flux;
  $("flux3-controls").hidden = engine !== "flux3-klein";
  $("mask-hint").textContent = t(flux ? "focusedMaskHint" : "maskHint");
  $("generate").disabled =
    !connected ||
    state.requesting ||
    (!pending &&
      (isBusy() ||
        !ready ||
        state.maskRequired ||
        (state.mode === "refine" && !state.mask)));
  $("cancel").hidden = !state.jobs.some((job) =>
    activeStatuses.has(job.status),
  );
  const steps =
    engine === "flux3-klein"
      ? Number($("flux3-steps").value)
      : engine === "flux-klein"
        ? 4
        : { draft: 20, standard: 30, detailed: 50 }[$("quality").value];
  let [width, height] = state.recipeExtras.size
    ? [state.recipeExtras.size.width, state.recipeExtras.size.height]
    : {
        portrait: [768, 1024],
        square: [1024, 1024],
        landscape: [1024, 768],
      }[$("format").value];
  const max =
    memoryProfile() === "economy"
      ? 589824
      : memoryProfile() === "quality"
        ? 2097152
        : 1048576;
  const scale = Math.min(1, Math.sqrt(max / (width * height)));
  width = Math.floor((width * scale) / 16) * 16;
  height = Math.floor((height * scale) / 16) * 16;
  $("effective-size").textContent = !connected
    ? t("startComfy")
    : !ready
      ? t("modelUnavailable")
      : `${t(memoryProfile() === "quality" ? "highPrecision" : memoryProfile())} · ${state.mode === "refine" ? (state.input?.width ? `${state.input.width} × ${state.input.height} · ${t("originalSize")}` : t("originalSize")) : `${width} × ${height}`} · ${steps} ${t("steps")} · ${t("sequential")}`;
  $("paint-open").disabled = !state.input || state.uploading;
  $("full-mask").disabled = !state.input || state.uploading;
  $("full-mask").setAttribute(
    "aria-pressed",
    String(Boolean(state.mask?.whole)),
  );
  $("paint-open").textContent = t(state.mask ? "maskReady" : "paintArea");
  const active =
    state.jobs.find((job) => job.status === "running") ||
    state.jobs.find((job) => activeStatuses.has(job.status));
  $("running-indicator").hidden = !active;
  if (active) {
    $("running-text").textContent = t(active.status);
    const progress = active.progress || {};
    if (progress.max > 0) {
      $("progress").max = progress.max;
      $("progress").value = progress.value || 0;
    } else $("progress").removeAttribute("value");
  }
  const status = t(
    workspaceStatus({
      pending,
      activeStatus: active?.status,
      uploading: state.uploading,
      requesting: state.requesting,
      system: state.system,
      ready,
      error: !$("form-error").hidden,
      mode: state.mode,
      hasInput: Boolean(state.input),
      hasMask: Boolean(state.mask) && !state.maskRequired,
      prompt: $("prompt").value,
    }),
  );
  if ($("footer-status").textContent !== status)
    $("footer-status").textContent = status;
  const setupNeeded = Boolean(state.system) && (!connected || !ready);
  $("setup-open").hidden = !setupNeeded;
}
function showJob(job) {
  state.selected = job;
  state.selectedId = job.id;
  $("result-image").hidden = !job.output_id;
  $("empty-state").hidden = Boolean(job.output_id);
  if (job.output_id) {
    $("result-image").src = imageURL(job.output_id);
    renderSelectionLabel();
    $("download").href = imageURL(job.output_id);
    $("download").download = `moss-go-${job.id.slice(0, 8)}.png`;
  }
  $("download").hidden = !job.output_id;
  $("recipe").hidden = !job.output_id;
  $("execution-details").hidden = !job.output_id;
  $("use-result").hidden = !job.output_id;
  $("zoom-open").hidden = !job.output_id;
  $("compare").hidden = !job.output_id || !job.settings.input_id;
  $("compare-layer").hidden = true;
  $("compare-slider").hidden = true;
  $("compare").setAttribute("aria-pressed", "false");
  if (job.error) error(jobError(job), job);
  else error("");
  persist();
  renderJobs(true);
}
function renderSelectionLabel() {
  const job = state.selected;
  $("image-label").textContent = job?.output_id
    ? `${t("nextTake")} ${job.variant + 1} · ${job.settings.source_width || job.settings.width} × ${job.settings.source_height || job.settings.height}`
    : t("noSelection");
  $("image-label").title = job?.output_id
    ? `${t(job.settings.mode)} · ${job.settings.engine} · ${job.settings.steps} ${t("steps")} · Seed ${job.settings.seed}`
    : "";
}
function renderJobs(force = false) {
  const signature = JSON.stringify(
    state.jobs.map((job) => [job.id, job.status, job.output_id]),
  );
  if (!force && signature === state.lastRender) {
    updateControls();
    return;
  }
  state.lastRender = signature;
  $("result-count").textContent = String(
    state.jobs.filter((job) => job.output_id).length,
  );
  $("results").replaceChildren();
  const visibleJobs = filterHistory(
    state.jobs,
    $("history-scope").value,
    state.selected,
  );
  if (!visibleJobs.length) {
    const hint = document.createElement("p");
    hint.className = "hint results-empty";
    hint.textContent = t(state.jobs.length ? "noMatchingTakes" : "historyHint");
    $("results").append(hint);
  }
  for (const job of visibleJobs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "take";
    button.setAttribute("aria-pressed", String(state.selected?.id === job.id));
    button.setAttribute(
      "aria-label",
      `${t("scene")} ${job.scene + 1}, ${t("nextTake")} ${job.variant + 1}: ${takeStatus(job)} · ${job.settings.engine} · Seed ${job.settings.seed}`,
    );
    button.title = `${t("scene")} ${job.scene + 1} · ${t("nextTake")} ${job.variant + 1} · ${takeStatus(job)} · ${job.settings.engine} · Seed ${job.settings.seed}`;
    if (job.output_id) {
      const image = document.createElement("img");
      image.src = imageURL(job.output_id);
      image.alt = "";
      image.loading = "lazy";
      button.append(image);
    } else {
      const label = document.createElement("span");
      label.className =
        "take-status" + (job.status === "error" ? " error" : "");
      label.textContent = takeStatus(job);
      button.append(label);
    }
    button.onclick = () => {
      if (job.output_id) {
        state.revealBatch = null;
        showJob(job);
      } else if (job.error) error(jobError(job), job);
      updateControls();
    };
    const item = document.createElement("div");
    item.className = "take-item";
    item.setAttribute("role", "listitem");
    item.append(button);
    $("results").append(item);
  }
  const fresh = state.jobs.find(
    (job) => job.output_id && job.batch_id === state.revealBatch,
  );
  if (
    fresh &&
    (!state.selected || state.selected.batch_id !== state.revealBatch)
  ) {
    state.revealBatch = null;
    showJob(fresh);
    return;
  }
  if (!state.selected) {
    const latest =
      state.jobs.find((job) => job.id === state.selectedId && job.output_id) ||
      state.jobs.find((job) => job.output_id);
    if (latest) {
      showJob(latest);
      return;
    }
  }
  updateControls();
}
async function refreshJobs() {
  if (refreshing) return;
  refreshing = true;
  try {
    if (launches.pending && !state.requesting) {
      const accepted = await launches.reconcile();
      if (accepted) {
        state.activeBatch = accepted.id;
        state.revealBatch = accepted.id;
        error("");
        persist();
        toast(t("batchAccepted"));
      }
    }
    const result = await request("/jobs");
    const previous = new Map(state.jobs.map((job) => [job.id, job.status]));
    state.jobs = result.items;
    const failed = nextFailure(
      state.jobs,
      previous,
      state.revealBatch,
      state.notifiedFailures,
    );
    renderJobs();
    if (failed) {
      state.notifiedFailures.add(failed.id);
      error(jobError(failed), failed);
      updateControls();
    }
  } catch (exc) {
    $("footer-status").textContent = exc.message;
  } finally {
    refreshing = false;
  }
}
async function refreshSystem(force = false) {
  const ticket = ++systemRevision;
  try {
    const system = await request(force ? "/system?refresh=1" : "/system");
    if (ticket !== systemRevision) return;
    state.system = system;
  } catch (exc) {
    if (ticket !== systemRevision) return;
    state.system = { connected: false, devices: [], engines: {} };
    error(exc.message);
  }
  $("connection-dot").classList.toggle("connected", state.system.connected);
  $("connection-label").textContent = t(
    state.system.connected ? "connected" : "disconnected",
  );
  renderDevice();
  renderModels();
  updateControls();
}
function renderDevice() {
  renderDeviceInfo(state.system);
}
function renderModels() {
  renderEquipment(
    state.system,
    memoryProfile(),
    state.mode,
    $("flux3-upsampler").checked,
  );
}
async function submit(event) {
  event.preventDefault();
  error("");
  if (launches.pending) {
    await sendLaunch();
    return;
  }
  if (!Number.isSafeInteger(Number($("seed").value))) {
    error(t("wholeSeed"));
    return;
  }
  if (!$("prompt").value.trim()) {
    error(t("describe"));
    $("prompt").focus();
    return;
  }
  if (state.mode !== "create" && !state.input) {
    error(t("selectImage"));
    $("input-pick").focus();
    return;
  }
  if (state.mode === "refine" && !state.mask) {
    error(t("selectMask"));
    $("paint-open").focus();
    return;
  }
  const settings = {
    request_id: crypto.randomUUID().replaceAll("-", ""),
    mode: state.mode,
    engine: selectedEngine(),
    profile: $("profile").value,
    quality: $("quality").value,
    format: $("format").value,
    prompt: $("prompt").value,
    negative: $("negative").value,
    seed: Number($("seed").value),
    variants: Number($("variants").value),
    character: state.character,
    strength: Number($("strength").value),
    feather: 8,
    ...state.recipeExtras,
    scenes: scenePlan(state.scenes, $("variants").value, state.mode).scenes,
  };
  if (settings.engine === "flux3-klein") {
    settings.flux3_steps = Number($("flux3-steps").value);
    settings.prompt_upsampler = $("flux3-upsampler").checked;
  }
  if (state.mode !== "create") settings.input_id = state.input.id;
  if (state.mode === "refine" && state.mask) settings.mask_id = state.mask.id;
  const parent = launchParent(state.mode, state.parent, state.recoveryParent);
  if (parent) settings.parent_id = parent;
  launches.prepare(settings);
  await sendLaunch();
}
async function sendLaunch() {
  $("toast").hidden = true;
  clearTimeout(toastTimer);
  state.requesting = true;
  updateControls();
  persist();
  try {
    const result = await launches.send();
    state.activeBatch = result.id;
    state.revealBatch = result.id;
    persist();
    await refreshJobs();
    const current = state.jobs.filter((job) => job.batch_id === result.id);
    if (window.matchMedia("(max-width: 760px)").matches) {
      $("workspace-title").focus({ preventScroll: true });
      $("output-panel").scrollIntoView({ block: "start" });
    }
    if (current.some((job) => activeStatuses.has(job.status)))
      toast(t("batchAccepted"));
    else if (current.some((job) => job.output_id)) toast(t("imageReady"));
  } catch (exc) {
    error(
      launches.pending
        ? t(
            launches.persisted
              ? "launchUnconfirmed"
              : "launchUnconfirmedMemory",
          )
        : exc.message,
    );
  } finally {
    state.requesting = false;
    updateControls();
  }
}
function setCharacter(character, locks = []) {
  state.character = character;
  state.characterLocks = locks;
  $("trait-summary").textContent = Object.values(state.character).join(", ");
  $("trait-summary").hidden = !Object.keys(state.character).length;
}
for (const button of document.querySelectorAll("[data-mode]"))
  button.onclick = () => mode(button.dataset.mode);
for (const button of document.querySelectorAll("[data-close]"))
  button.onclick = () => $(button.dataset.close).close();
for (const button of document.querySelectorAll("[data-starter]"))
  button.onclick = () => {
    $("prompt").value = scenePresets[button.dataset.starter];
    persist();
  };
$("input-pick").onclick = () => $("input-file").click();
$("examples-open").onclick = () => {
  if (launches.pending || state.requesting || state.uploading) return;
  chooseExample((artifact) => {
    setInput(artifact);
    setCharacter({});
    if (!$("prompt").value.trim() && state.mode === "reference")
      $("prompt").value = scenePresets.station;
    persist();
    updateControls();
    toast(t("exampleApplied"));
  }).catch((exc) => error(exc.message));
};
$("input-file").onchange = () => acceptFile($("input-file").files[0]);
$("input-clear").onclick = () => setInput(null);
$("input-pick").ondragover = (event) => {
  event.preventDefault();
  $("input-pick").classList.add("drag-over");
};
$("input-pick").ondragleave = () =>
  $("input-pick").classList.remove("drag-over");
$("input-pick").ondrop = (event) => {
  event.preventDefault();
  $("input-pick").classList.remove("drag-over");
  acceptFile(event.dataTransfer.files[0]);
};
$("settings-form").onsubmit = submit;
$("history-scope").onchange = () => {
  renderJobs(true);
  persist();
};
$("settings-form").oninput = () => {
  updateControls();
  persist();
};
$("format").onchange = () => {
  delete state.recipeExtras.size;
  updateControls();
  persist();
};
$("scenes-open").onclick = () =>
  openScenePack(state.scenes, (scenes) => {
    state.scenes = scenes;
    updateControls();
    persist();
  });
$("import-recipe").onclick = () => $("recipe-file").click();
$("recipe-file").onchange = async () => {
  try {
    await reviewRecipeFile($("recipe-file").files[0], applyRecipe);
  } catch (exc) {
    error(exc.message);
  } finally {
    $("recipe-file").value = "";
  }
};
function applyRecipe(item) {
  const settings = item.settings;
  state.recipeExtras = {};
  for (const key of ["size", "loras", "feather"]) {
    if (settings[key] != null) state.recipeExtras[key] = settings[key];
  }
  mode(settings.mode);
  $("flux3-steps").value = String(settings.flux3_steps ?? 16);
  $("flux3-upsampler").checked = settings.prompt_upsampler !== false;
  for (const key of [
    "prompt",
    "negative",
    "quality",
    "format",
    "variants",
    "profile",
    "seed",
    "engine",
    "strength",
  ]) {
    if (settings[key] != null) $(key).value = settings[key];
  }
  setCharacter(settings.character || {});
  state.engines[state.mode] = $("engine").value;
  state.scenes = cleanScenes(settings.scenes);
  setInput(
    settings.input_id && !item.missing_inputs.includes("input_id")
      ? { id: settings.input_id }
      : null,
  );
  if (settings.mask_id && !item.missing_inputs.includes("mask_id"))
    state.mask = { id: settings.mask_id };
  state.maskRequired = item.missing_inputs.includes("mask_id");
  state.parent = null;
  updateControls();
  persist();
  if (item.missing_inputs.length) error(t("recipeMissingInputs"));
  else toast(t("settingsLoaded"));
}
$("engine").onchange = () => {
  state.engines[state.mode] = $("engine").value;
  updateControls();
  persist();
};
$("profile").onchange = () => {
  updateControls();
  renderModels();
};
for (const id of ["flux3-steps", "flux3-upsampler"])
  $(id).onchange = () => {
    updateControls();
    renderModels();
    persist();
  };
$("recover-take").onclick = async () => {
  const job = state.failedJob;
  if (!job || launches.pending || isBusy()) return;
  let prepared = false;
  try {
    state.requesting = true;
    updateControls();
    const recipe = await request(`/jobs/${job.id}/recipe`);
    if (["out_of_memory", "batch_memory_hold"].includes(job.error_code))
      recipe.settings.profile = "economy";
    const preview = await request("/recipes/preview", recipe);
    applyRecipe(preview);
    state.recoveryParent = job.id;
    error("");
    persist();
    toast(t("recoveryPrepared"));
    prepared = true;
  } catch (exc) {
    error(exc.message, job);
  } finally {
    state.requesting = false;
    updateControls();
    if (prepared) $("prompt").focus();
  }
};
$("cancel").onclick = async () => {
  error("");
  const batchId = cancellationBatch(state.jobs, state.activeBatch);
  for (const job of state.jobs.filter(
    (item) => activeStatuses.has(item.status) && item.batch_id === batchId,
  )) {
    try {
      await request(`/jobs/${job.id}/cancel`, {});
    } catch (exc) {
      error(exc.message || t("cancelError"));
    }
  }
  await refreshJobs();
};
const openModels = () => {
  $("models-dialog").showModal();
  refreshSystem();
};
$("models-open").onclick = openModels;
$("setup-open").onclick = openModels;
$("refresh-system").onclick = async () => {
  await refreshSystem(true);
};
$("theme").onclick = () => {
  const theme =
    document.documentElement.dataset.theme === "comfy" ? "mineral" : "comfy";
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("moss-go.theme.v1", theme);
  } catch {}
};
$("language").onclick = () => {
  const failedJob = state.failedJob;
  setLanguage(currentLanguage() === "en" ? "ru" : "en");
  mode(state.mode);
  renderJobs(true);
  renderSelectionLabel();
  if (state.system) {
    $("connection-label").textContent = t(
      state.system.connected ? "connected" : "disconnected",
    );
    renderModels();
    renderDevice();
  }
  if (failedJob) error(jobError(failedJob), failedJob);
};
$("character-open").onclick = () =>
  openCharacterEditor(
    state.character,
    state.characterLocks,
    (character, locks) => {
      setCharacter(character, locks);
      persist();
      toast(t("traitsApplied"));
    },
  ).catch((exc) => error(exc.message));
$("assistant-open").onclick = () => {
  openPromptAssistant({
    prompt: $("prompt"),
    character: state.character,
    busy: isBusy(),
  }).catch((exc) => error(exc.message));
};
$("use-result").onclick = async () => {
  if (!state.selected?.output_id || state.uploading || launches.pending) return;
  const selected = state.selected;
  try {
    state.uploading = true;
    updateControls();
    const result = await fetch(imageURL(selected.output_id));
    const blob = await result.blob();
    const input = await uploadImage(
      new File([blob], "selected-take.png", { type: "image/png" }),
    );
    setInput(input);
    state.parent = selected.id;
    mode("refine");
    $("prompt").focus();
  } catch (exc) {
    error(exc.message);
  } finally {
    state.uploading = false;
    updateControls();
  }
};
$("paint-open").onclick = async () => {
  if (!state.input || state.uploading || launches.pending) return;
  const inputId = state.input.id;
  try {
    const blob = await editMask(
      imageURL(inputId),
      state.mask ? imageURL(state.mask.id) : null,
    );
    if (state.input?.id !== inputId) return;
    if (blob) {
      state.uploading = true;
      updateControls();
      const uploaded = await uploadImage(
        new File([blob], "mask.png", { type: "image/png" }),
        "mask",
      );
      if (state.input?.id !== inputId) return;
      state.mask = uploaded;
      state.maskRequired = false;
      persist();
      updateControls();
      toast(t("maskReady"));
    }
  } catch (exc) {
    error(exc.message);
  } finally {
    state.uploading = false;
    updateControls();
  }
};
$("full-mask").onclick = async () => {
  if (!state.input || state.uploading || launches.pending) return;
  const inputId = state.input.id;
  $("full-mask").disabled = true;
  try {
    state.uploading = true;
    updateControls();
    const image = new Image();
    image.src = imageURL(inputId);
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d");
    context.fillStyle = "white";
    context.fillRect(0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, "image/png"),
    );
    if (!blob) throw new Error(t("uploadFailed"));
    const uploaded = await uploadImage(
      new File([blob], "whole-image-mask.png", { type: "image/png" }),
      "mask",
    );
    if (state.input?.id !== inputId) return;
    state.mask = { ...uploaded, whole: true };
    state.maskRequired = false;
    persist();
    toast(t("wholeImageSelected"));
  } catch (exc) {
    error(exc.message);
  } finally {
    state.uploading = false;
    updateControls();
  }
};
$("compare").onclick = () => {
  const active = $("compare").getAttribute("aria-pressed") !== "true";
  $("compare").setAttribute("aria-pressed", String(active));
  $("compare-layer").hidden = $("compare-slider").hidden = !active;
  if (active)
    $("compare-image").src = imageURL(state.selected.settings.input_id);
};
$("zoom-open").onclick = () => inspectImage(state.selected?.output_id);
$("compare-slider").oninput = () =>
  ($("compare-layer").style.clipPath =
    `inset(0 ${100 - Number($("compare-slider").value)}% 0 0)`);
$("recipe").onclick = () => {
  openExport(state.selected, state.jobs);
};
$("execution-details").onclick = () => openExecutionDetails(state.selected);
try {
  const saved = JSON.parse(
    localStorage.getItem("moss-go.workspace.v1") || "null",
  );
  if (saved) {
    $("flux3-steps").value = String(saved.flux3_steps ?? 16);
    $("flux3-upsampler").checked = saved.prompt_upsampler !== false;
    for (const key of [
      "prompt",
      "negative",
      "format",
      "quality",
      "variants",
      "profile",
      "seed",
    ])
      if (saved[key] != null) $(key).value = saved[key];
    state.mode = ["create", "reference", "refine"].includes(saved.mode)
      ? saved.mode
      : "reference";
    setCharacter(saved.character || {}, saved.characterLocks || []);
    restoredEngine = saved.engine;
    state.engines = { ...state.engines, ...saved.engines };
    state.scenes = cleanScenes(saved.scenes);
    state.recipeExtras = saved.recipeExtras || {};
    if (saved.input) setInput(saved.input);
    state.mask = saved.mask || null;
    state.parent = saved.parent || null;
    state.recoveryParent = saved.recoveryParent || null;
    state.maskRequired = Boolean(saved.maskRequired);
    state.selectedId = saved.selectedId || null;
    state.activeBatch = saved.activeBatch || null;
    state.revealBatch = saved.revealBatch || null;
    if (
      [...$("history-scope").options].some(
        (option) => option.value === saved.historyScope,
      )
    )
      $("history-scope").value = saved.historyScope;
  }
  document.documentElement.dataset.theme =
    localStorage.getItem("moss-go.theme.v1") === "mineral"
      ? "mineral"
      : "comfy";
} catch {}
applyTranslations();
mode(state.mode);
if (
  [...$("engine").options].some((option) => option.value === restoredEngine)
) {
  $("engine").value = restoredEngine;
  state.engines[state.mode] = restoredEngine;
  persist();
}
await refreshSystem();
await refreshJobs();
pollTimer = setInterval(refreshJobs, 2000);
const systemTimer = setInterval(refreshSystem, 15000);
window.addEventListener("pagehide", () => clearInterval(systemTimer), {
  once: true,
});
window.addEventListener("pagehide", () => clearInterval(pollTimer), {
  once: true,
});
