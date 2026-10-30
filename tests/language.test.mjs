import test from "node:test";
import assert from "node:assert/strict";
import { initialLanguage, LANGUAGE_KEY } from "../moss_go/web/i18n.js";

test("a new workspace starts in English even on a Russian system", () => {
  assert.equal(initialLanguage({ getItem: () => null }), "en");
});
test("an explicit Russian choice is retained", () => {
  assert.equal(
    initialLanguage({ getItem: (key) => (key === LANGUAGE_KEY ? "ru" : null) }),
    "ru",
  );
});
test("broken or unavailable storage falls back to English", () => {
  assert.equal(
    initialLanguage({
      getItem: () => {
        throw new Error("blocked");
      },
    }),
    "en",
  );
  assert.equal(initialLanguage({ getItem: () => "{broken" }), "en");
});

test("a browser that blocks the storage getter still opens in English", () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  try {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      get() {
        throw new Error("storage denied");
      },
    });
    assert.equal(initialLanguage(), "en");
  } finally {
    if (previous) Object.defineProperty(globalThis, "localStorage", previous);
    else delete globalThis.localStorage;
  }
});
