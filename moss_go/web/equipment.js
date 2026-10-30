import { t } from "./i18n.js";

export function effectiveProfile(system, requested) {
  if (requested !== "auto") return requested;
  const recommended = system?.hardware?.recommended_profile;
  if (["economy", "balanced"].includes(recommended)) return recommended;
  const capacity = system?.devices?.find(
    (item) => item.type === "cuda",
  )?.vram_total;
  return typeof capacity === "number" &&
    Number.isFinite(capacity) &&
    capacity >= 14 * 1024 ** 3
    ? "balanced"
    : "economy";
}

export function modeReadiness(system, engine, profile, mode) {
  const setup = system?.engines?.[engine];
  const configured = setup?.profiles?.[profile] ?? setup;
  return { ...configured, ...configured?.modes?.[mode] };
}

function memory(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? `${(value / 1024 ** 3).toFixed(1)} GiB`
    : "—";
}

export function renderDevice(system) {
  const device =
    system?.devices?.find((item) => item.type === "cuda") ||
    system?.devices?.[0];
  document.getElementById("device-label").textContent = device
    ? `${device.name.replace(/^cuda:\d+\s*/, "").replace(/\s*:\s*cudaMallocAsync.*$/, "")} · ${device.type === "cuda" ? memory(device.vram_total) : device.type.toUpperCase()}`
    : t("deviceUnknown");
}

export function renderEquipment(system, profile, mode) {
  const content = document.getElementById("models-content");
  content.replaceChildren();
  const note = (text) => {
    const paragraph = document.createElement("p");
    paragraph.className = "hint";
    paragraph.textContent = text;
    content.append(paragraph);
  };
  note(t(system?.connected ? "filesLocal" : "startComfy"));
  const hardware = system?.hardware;
  if (hardware) {
    note(
      `${t("systemMemory")}: ${memory(hardware.ram_total)} · ${t("currentlyFree")}: ${memory(hardware.ram_free)}`,
    );
    if (hardware.accelerator === "cuda")
      note(
        `VRAM: ${memory(hardware.vram_total)} · ${t("currentlyFree")}: ${memory(hardware.vram_free)}`,
      );
    else note(t("acceleratorUnverified"));
    note(
      `${t("memory")}: ${t(profile === "quality" ? "highPrecision" : profile)}. ${t("capacityRecommendation")}`,
    );
    if (profile === "economy") note(t("cpuEncoderMemory"));
  }
  for (const [id, label] of [
    ["moss", "MOSS · SFT"],
    ["moss-charref", "MOSS · CharRef"],
    ["flux-klein", "FLUX.2 Klein · 4B"],
  ]) {
    const engine = system?.engines?.[id];
    if (!engine) continue;
    const configured = modeReadiness(system, id, profile, mode);
    const section = document.createElement("section");
    section.className = "model-engine";
    const title = document.createElement("h3");
    title.textContent = label;
    section.append(title);
    const status = document.createElement("p");
    status.textContent =
      configured.supported === false
        ? `${t("supportedModes")}: ${Object.entries(engine.modes)
            .filter(([, item]) => item.supported)
            .map(([name]) => t(name))
            .join(", ")}`
        : configured.ready
          ? `${t("setupFound")} · ${t("hashesNotChecked")}`
          : t("configure");
    section.append(status);
    if (configured.supported !== false) {
      for (const missing of configured.missing || []) {
        const text = document.createElement("p");
        text.className = "missing";
        text.textContent = `${missing.category}/${missing.filename}`;
        section.append(text);
      }
      if (configured.missing_nodes?.length) {
        const text = document.createElement("p");
        text.className = "missing";
        text.textContent = `${t("missingNodes")}: ${configured.missing_nodes.join(", ")}`;
        section.append(text);
      }
    }
    content.append(section);
  }
}
