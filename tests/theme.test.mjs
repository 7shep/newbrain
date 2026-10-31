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

test("unlocked: every family is offered and a pick keeps its family", () => {
  assert.deepEqual(Object.keys(FAMILIES), ["classic", "brain", "glass", "phosphor", "riso", "swiss", "macglass"]);
  assert.equal(resolve("swiss/dark").id, "swiss-dark");
  assert.equal(resolve("macglass/dark").id, "macglass-dark");
});

test("auto on a family with no auto mode falls back instead of throwing (Settings picker previews)", () => {
  assert.deepEqual({ ...resolve("phosphor/auto") }, { family: "phosphor", mode: "green", id: "phosphor-green", tone: "dark" });
});

test("every family resolves under every mode the picker can pass it", () => {
  for (const f of Object.keys(FAMILIES)) for (const m of ["auto", "light", "softdark", "ink", "green", "nope"])
    assert.ok(resolve(`${f}/${m}`).id.startsWith(f + "-"));
});
