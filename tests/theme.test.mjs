import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// theme.js is a browser script; run it with just enough of a window to reach BrainTheme.
const win = {
  matchMedia: () => ({ matches: true, addEventListener() {} }),
  localStorage: { getItem: () => null },
  location: { search: "" },
  document: { documentElement: { dataset: {} }, querySelector: () => null, dispatchEvent() {} },
  getComputedStyle: () => ({ getPropertyValue: () => "" }),
  CustomEvent: class {},
  URLSearchParams,
};
win.window = win;
vm.runInNewContext(readFileSync(new URL("../app/theme.js", import.meta.url), "utf8"), win);
const { resolve, FAMILIES } = win.BrainTheme;

test("the lock turns any pick into its family, keeping a mode it has", () => {
  assert.deepEqual(Object.keys(FAMILIES), ["glass"]);
  assert.deepEqual({ ...resolve("phosphor/auto") }, { family: "glass", mode: "auto", id: "glass-light", tone: "light" });
  assert.equal(resolve("swiss/dark").id, "glass-dark");
  assert.equal(resolve("riso/paper").mode, "auto");
});

test("every family resolves under every mode the picker can pass it", () => {
  for (const f of Object.keys(FAMILIES)) for (const m of ["auto", "light", "softdark", "ink", "green", "nope"])
    assert.ok(resolve(`${f}/${m}`).id.startsWith(f + "-"));
});
