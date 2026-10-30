import { request } from "./api.js";
import { t } from "./i18n.js";
import { renderPromptDiff } from "./prompt-diff.js";

function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text) item.textContent = text;
  if (className) item.className = className;
  return item;
}
let session = 0;

export async function openPromptAssistant({ prompt, character, busy }) {
  const ticket = ++session;
  const dialog = document.getElementById("assistant-dialog");
  const content = document.getElementById("assistant-content");
  const actions = document.getElementById("assistant-actions");
  const apply = document.getElementById("assistant-apply");
  actions.hidden = true;
  apply.disabled = true;
  const original = prompt.value;
  content.replaceChildren();
  if (!dialog.open) dialog.showModal();
  const current = () => dialog.open && ticket === session;
  const status = element("p", "", "hint");
  status.setAttribute("role", "status");
  content.append(status);
  if (busy) {
    status.textContent = t("assistantWait");
    return;
  }
  if (!original.trim()) {
    status.textContent = t("describe");
    return;
  }
  try {
    status.textContent = t("checkingAssistant");
    const connection = await request("/assistant");
    if (!current()) return;
    if (!connection.ready) {
      status.textContent = t(
        connection.installed
          ? "assistantRevisionMismatch"
          : "assistantUnavailable",
      );
      const code = element("code", `ollama pull ${connection.model}`);
      code.className = "setup-command";
      const link = element("a", t("ollamaSetup"), "text-button");
      link.href = "https://ollama.com/download";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      content.append(code, link);
      return;
    }
    if (connection.busy) {
      status.textContent = t("assistantBusy");
      const retry = element("button", t("checkAgain"), "secondary");
      retry.type = "button";
      retry.onclick = () => openPromptAssistant({ prompt, character, busy });
      content.append(retry);
      return;
    }
    status.textContent = "Qwen3 Instruct · 4B · CPU";
    const originalTitle = element("summary", t("originalPrompt"));
    originalTitle.className = "assistant-label";
    const before = element("p", original, "prompt-original");
    const originalDetails = element("details");
    originalDetails.open = true;
    originalDetails.append(originalTitle, before);
    const button = element("button", t("suggestPrompt"), "secondary");
    button.type = "button";
    content.append(originalDetails, button);
    const traits = Object.values(character || {}).filter(
      (value) => typeof value === "string",
    );
    if (traits.length) {
      const protectedDetails = element("details");
      protectedDetails.append(
        element("summary", t("protectedTraits")),
        element("p", t("protectedTraitsHint"), "hint"),
        element("p", traits.join(", "), "prompt-original"),
      );
      content.insertBefore(protectedDetails, button);
    }
    button.onclick = async () => {
      button.disabled = true;
      status.textContent = t("assistantWorking");
      try {
        const result = await request("/prompts/enhance", {
          prompt: original,
          character,
        });
        if (!current()) return;
        const label = element("label");
        label.append(element("span", t("suggestedPrompt")));
        const suggestion = element("textarea");
        suggestion.value = result.suggestion;
        suggestion.rows = 6;
        suggestion.maxLength = 12000;
        suggestion.setAttribute("aria-label", t("suggestedPrompt"));
        label.append(suggestion);
        const changesTitle = element(
          "h3",
          t("promptChanges"),
          "assistant-label",
        );
        const legend = element("p", t("diffLegend"), "hint");
        const changes = element("div", "", "prompt-diff");
        changes.tabIndex = 0;
        changes.setAttribute("role", "region");
        changes.setAttribute("aria-label", t("promptChanges"));
        const redraw = () => {
          renderPromptDiff(changes, original, suggestion.value, {
            insert: t("added"),
            delete: t("removed"),
          });
          const unchanged = suggestion.value === original;
          apply.disabled = !suggestion.value.trim() || unchanged;
          changesTitle.hidden = unchanged;
          changes.hidden = unchanged;
          legend.hidden = unchanged;
          status.textContent = t(
            !suggestion.value.trim()
              ? "emptySuggestion"
              : unchanged
                ? "noPromptChanges"
                : "suggestionReady",
          );
        };
        suggestion.oninput = redraw;
        redraw();
        apply.onclick = () => {
          if (!suggestion.value.trim()) return;
          prompt.value = suggestion.value;
          prompt.dispatchEvent(new Event("input", { bubbles: true }));
          dialog.close();
        };
        originalDetails.open = false;
        content.append(changesTitle, legend, changes, label);
        actions.hidden = false;
        button.hidden = true;
      } catch (error) {
        if (current()) status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    };
  } catch (error) {
    if (current()) status.textContent = error.message;
  }
}
