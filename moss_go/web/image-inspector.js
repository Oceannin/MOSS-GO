import { imageURL } from "./api.js";
import { t } from "./i18n.js";

export function inspectImage(id) {
  if (!id) return;
  const dialog = document.createElement("dialog");
  dialog.className = "dialog image-inspector";
  dialog.setAttribute("aria-label", t("inspectImage"));
  const heading = document.createElement("div");
  heading.className = "dialog-heading";
  const title = document.createElement("h2");
  title.textContent = t("inspectImage");
  const label = document.createElement("label");
  label.className = "inspection-scale";
  const text = document.createElement("span");
  text.textContent = t("zoom");
  const scale = document.createElement("select");
  for (const [value, caption] of [
    ["fit", t("fitImage")],
    ["1", "100%"],
    ["2", "200%"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = caption;
    scale.append(option);
  }
  label.append(text, scale);
  const close = document.createElement("button");
  close.type = "button";
  close.className = "quiet";
  close.textContent = t("close");
  close.onclick = () => dialog.close();
  heading.append(title, label, close);
  const viewport = document.createElement("div");
  viewport.className = "inspection-viewport";
  viewport.tabIndex = 0;
  viewport.setAttribute("role", "region");
  viewport.setAttribute("aria-label", t("scrollImage"));
  const image = document.createElement("img");
  image.alt = t("inspectImage");
  image.src = imageURL(id);
  const resize = () => {
    const fit = scale.value === "fit";
    image.style.width = fit
      ? "100%"
      : `${image.naturalWidth * Number(scale.value)}px`;
    image.style.height = fit ? "100%" : "auto";
    viewport.scrollTop = viewport.scrollLeft = 0;
  };
  image.onload = resize;
  scale.onchange = resize;
  viewport.append(image);
  dialog.append(heading, viewport);
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove(), { once: true });
  dialog.showModal();
}
