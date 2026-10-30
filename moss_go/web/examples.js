import { request } from "./api.js";
import { t, currentLanguage } from "./i18n.js";

export async function chooseExample(onApply) {
  const $ = (id) => document.getElementById(id);
  const dialog = $("example-dialog");
  if (dialog.open) return;
  const controller = new AbortController();
  const { signal } = controller;
  let items = [],
    revision = 0;
  const status = (message, failed = false) => {
    $("example-status").textContent = message;
    $("example-status").setAttribute("role", failed ? "alert" : "status");
  };
  const preview = async () => {
    const ticket = ++revision;
    $("example-apply").disabled = true;
    const selected = items.find(
      (item) => item.id === $("example-choice").value,
    );
    $("example-preview").hidden = true;
    status(t("loadingExample"));
    try {
      $("example-preview").src = selected.image_url;
      $("example-preview").alt =
        currentLanguage() === "ru" ? selected.label_ru : selected.label;
      await $("example-preview").decode();
      if (signal.aborted || ticket !== revision) return;
      $("example-preview").hidden = false;
      $("example-apply").disabled = false;
      status(t("exampleReady"));
    } catch {
      if (!signal.aborted && ticket === revision) {
        status(t("exampleLoadFailed"), true);
        $("example-retry").hidden = false;
      }
    }
  };
  const load = async () => {
    $("example-apply").disabled = true;
    $("example-choice").disabled = true;
    $("example-retry").hidden = true;
    status(t("loadingExample"));
    try {
      items = (await request("/examples", undefined, { signal })).items;
      if (signal.aborted) return;
      if (!items.length) throw new Error(t("exampleLoadFailed"));
      $("example-choice").replaceChildren(
        ...items.map((item) => {
          const option = document.createElement("option");
          option.value = item.id;
          option.textContent =
            currentLanguage() === "ru" ? item.label_ru : item.label;
          return option;
        }),
      );
      $("example-choice").disabled = false;
      await preview();
    } catch {
      if (!signal.aborted) {
        status(t("exampleLoadFailed"), true);
        $("example-retry").hidden = false;
      }
    }
  };
  $("example-choice").addEventListener("change", preview, { signal });
  $("example-retry").addEventListener("click", load, { signal });
  $("example-apply").addEventListener(
    "click",
    async () => {
      $("example-apply").disabled = true;
      $("example-choice").disabled = true;
      status(t("loadingExample"));
      try {
        const artifact = await request(
          `/examples/${encodeURIComponent($("example-choice").value)}/use`,
          {},
          { signal },
        );
        if (signal.aborted) return;
        onApply(artifact);
        dialog.close();
      } catch {
        if (!signal.aborted) {
          status(t("exampleLoadFailed"), true);
          $("example-choice").disabled = false;
          $("example-apply").disabled = false;
        }
      }
    },
    { signal },
  );
  dialog.addEventListener(
    "close",
    () => {
      controller.abort();
      $("example-preview").removeAttribute("src");
    },
    { once: true },
  );
  dialog.showModal();
  await load();
}
