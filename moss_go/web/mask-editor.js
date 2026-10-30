import { t } from "./i18n.js";

const make = (tag, text) => {
  const item = document.createElement(tag);
  if (text) item.textContent = text;
  return item;
};

export function maskRectangle(width, height, x, y, w, h) {
  if (
    ![width, height, x, y, w, h].every(Number.isFinite) ||
    !Number.isInteger(width) ||
    !Number.isInteger(height) ||
    width < 1 ||
    height < 1 ||
    x < 0 ||
    y < 0 ||
    w <= 0 ||
    h <= 0 ||
    x + w > 100 ||
    y + h > 100
  )
    throw new RangeError("Rectangle lies outside the image");
  const left = Math.min(width - 1, Math.round((width * x) / 100)),
    top = Math.min(height - 1, Math.round((height * y) / 100));
  return {
    x: left,
    y: top,
    width: Math.min(width - left, Math.max(1, Math.round((width * w) / 100))),
    height: Math.min(height - top, Math.max(1, Math.round((height * h) / 100))),
  };
}

export async function editMask(imageURL, initialMaskURL = null) {
  const image = new Image();
  image.src = imageURL;
  await image.decode();
  const originalMask = new Image();
  if (initialMaskURL) {
    originalMask.src = initialMaskURL;
    await originalMask.decode();
    if (
      originalMask.naturalWidth !== image.naturalWidth ||
      originalMask.naturalHeight !== image.naturalHeight
    )
      throw new Error(t("maskSizeMismatch"));
  }
  const dialog = make("dialog");
  dialog.className = "dialog mask-dialog";
  dialog.setAttribute("aria-label", t("paintTitle"));
  const heading = make("div");
  heading.className = "dialog-heading";
  heading.append(make("h2", t("paintTitle")));
  const close = make("button", t("close"));
  close.type = "button";
  close.className = "quiet";
  heading.append(close);
  const body = make("div");
  body.className = "dialog-content mask-editor-body";
  const stage = make("div");
  stage.className = "mask-stage";
  const canvas = make("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  canvas.className = "mask-canvas";
  canvas.setAttribute("aria-label", t("maskCanvasHint"));
  stage.append(canvas);
  const mask = make("canvas");
  mask.width = canvas.width;
  mask.height = canvas.height;
  const context = canvas.getContext("2d"),
    maskContext = mask.getContext("2d");
  const baseMask = make("canvas"),
    overlay = make("canvas");
  baseMask.width = overlay.width = canvas.width;
  baseMask.height = overlay.height = canvas.height;
  if (initialMaskURL) {
    const base = baseMask.getContext("2d");
    base.drawImage(originalMask, 0, 0);
    const pixels = base.getImageData(0, 0, baseMask.width, baseMask.height);
    for (let i = 0; i < pixels.data.length; i += 4) {
      const alpha = pixels.data[i];
      pixels.data[i] = pixels.data[i + 1] = pixels.data[i + 2] = 255;
      pixels.data[i + 3] = alpha;
    }
    base.putImageData(pixels, 0, 0);
  }
  let strokes = [],
    current = null,
    undone = [],
    erasing = false;
  const radius = make("input");
  radius.type = "range";
  radius.min = "4";
  radius.max = "160";
  radius.value = "36";
  radius.setAttribute("aria-label", t("brush"));
  const tools = make("div");
  tools.className = "mask-tools";
  const eraser = make("button", t("erase"));
  eraser.type = "button";
  eraser.className = "secondary small";
  eraser.setAttribute("aria-pressed", "false");
  const undo = make("button", t("undo"));
  undo.type = "button";
  undo.className = "quiet";
  const redo = make("button", t("redo"));
  redo.type = "button";
  redo.className = "quiet";
  const clear = make("button", t("resetMask"));
  clear.type = "button";
  clear.className = "quiet";
  tools.append(make("span", t("brush")), radius, eraser, undo, redo, clear);
  const area = make("details");
  area.className = "mask-area";
  area.append(make("summary", t("selectRectangle")));
  const areaFields = make("div");
  areaFields.className = "mask-area-fields";
  const rectangleInputs = [];
  for (const [key, value] of [
    ["areaLeft", 40],
    ["areaTop", 40],
    ["areaWidth", 20],
    ["areaHeight", 20],
  ]) {
    const label = make("label");
    label.append(make("span", t(key)));
    const input = make("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.step = "1";
    input.value = String(value);
    input.setAttribute("aria-label", t(key));
    input.oninput = () =>
      rectangleInputs.forEach((field) => field.setCustomValidity(""));
    rectangleInputs.push(input);
    label.append(input);
    areaFields.append(label);
  }
  const addArea = make("button", t("addRegion"));
  addArea.type = "button";
  addArea.className = "secondary small";
  areaFields.append(addArea);
  area.append(areaFields);
  body.append(stage, tools, area);
  const foot = make("div");
  foot.className = "dialog-footer";
  const note = make("p", t("emptyMask"));
  note.className = "hint";
  note.style.marginRight = "auto";
  const apply = make("button", t("applyMask"));
  apply.type = "button";
  apply.className = "primary";
  foot.append(note, apply);
  dialog.append(heading, body, foot);
  document.body.append(dialog);
  function redraw() {
    maskContext.globalCompositeOperation = "source-over";
    maskContext.clearRect(0, 0, mask.width, mask.height);
    maskContext.drawImage(baseMask, 0, 0);
    for (const stroke of strokes) {
      if (stroke.clear) {
        maskContext.clearRect(0, 0, mask.width, mask.height);
        continue;
      }
      maskContext.globalCompositeOperation = stroke.erase
        ? "destination-out"
        : "source-over";
      maskContext.strokeStyle = "#fff";
      maskContext.fillStyle = maskContext.strokeStyle;
      if (stroke.rectangle) {
        const r = stroke.rectangle;
        maskContext.fillRect(r.x, r.y, r.width, r.height);
        continue;
      }
      maskContext.lineCap = "round";
      maskContext.lineJoin = "round";
      maskContext.lineWidth = stroke.radius * 2;
      const start = stroke.points[0];
      if (!start) continue;
      maskContext.beginPath();
      maskContext.arc(start.x, start.y, stroke.radius, 0, Math.PI * 2);
      maskContext.fill();
      maskContext.beginPath();
      maskContext.moveTo(start.x, start.y);
      for (const point of stroke.points.slice(1))
        maskContext.lineTo(point.x, point.y);
      maskContext.stroke();
    }
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0);
    const tint = overlay.getContext("2d");
    tint.globalCompositeOperation = "source-over";
    tint.clearRect(0, 0, overlay.width, overlay.height);
    tint.drawImage(mask, 0, 0);
    tint.globalCompositeOperation = "source-in";
    tint.fillStyle = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent")
      .trim();
    tint.fillRect(0, 0, overlay.width, overlay.height);
    context.save();
    context.globalAlpha = 0.42;
    context.drawImage(overlay, 0, 0);
    context.restore();
    undo.disabled = !strokes.length;
    redo.disabled = !undone.length;
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) * canvas.width) / rect.width,
      y: ((event.clientY - rect.top) * canvas.height) / rect.height,
    };
  }
  canvas.onpointerdown = (event) => {
    if (event.button !== 0) return;
    canvas.setPointerCapture(event.pointerId);
    current = {
      erase: erasing,
      radius:
        (Number(radius.value) * canvas.width * 0.5) /
        canvas.getBoundingClientRect().width,
      points: [point(event)],
    };
    strokes.push(current);
    undone = [];
    redraw();
  };
  canvas.onpointermove = (event) => {
    if (current) {
      current.points.push(point(event));
      redraw();
    }
  };
  canvas.onpointerup = canvas.onpointercancel = () => {
    current = null;
  };
  eraser.onclick = () => {
    erasing = !erasing;
    eraser.setAttribute("aria-pressed", String(erasing));
  };
  undo.onclick = () => {
    if (strokes.length) undone.push(strokes.pop());
    current = null;
    redraw();
  };
  redo.onclick = () => {
    if (undone.length) strokes.push(undone.pop());
    current = null;
    redraw();
  };
  clear.onclick = () => {
    strokes.push({ clear: true });
    current = null;
    undone = [];
    redraw();
  };
  addArea.onclick = () => {
    if (!rectangleInputs.every((input) => input.reportValidity())) return;
    try {
      const rectangle = maskRectangle(
        canvas.width,
        canvas.height,
        ...rectangleInputs.map((input) => Number(input.value)),
      );
      strokes.push({ rectangle, erase: erasing });
      undone = [];
      redraw();
    } catch {
      rectangleInputs[0].setCustomValidity(t("rectangleOutside"));
      rectangleInputs[0].reportValidity();
    }
  };
  redraw();
  dialog.showModal();
  return new Promise((resolve) => {
    let accepted = false;
    close.onclick = () => dialog.close();
    apply.onclick = () => {
      accepted = true;
      dialog.close();
    };
    dialog.addEventListener(
      "close",
      async () => {
        if (!accepted) {
          dialog.remove();
          resolve(null);
          return;
        }
        const exported = make("canvas");
        exported.width = mask.width;
        exported.height = mask.height;
        const output = exported.getContext("2d");
        output.fillStyle = "black";
        output.fillRect(0, 0, exported.width, exported.height);
        output.drawImage(mask, 0, 0);
        const blob = await new Promise((done) =>
          exported.toBlob(done, "image/png"),
        );
        dialog.remove();
        resolve(blob);
      },
      { once: true },
    );
  });
}
