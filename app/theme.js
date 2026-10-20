/* Brain's theme picker logic, shared by the desktop and phone apps. Load it in <head> (not deferred) so the
   theme is set before first paint. A choice is "family/mode"; mode "auto" follows the system light/dark. */
(function () {
  const FAMILIES = {
    classic: { label: "Classic", modes: { light: "Light", softlight: "Soft light", dark: "Dark", softdark: "Soft dark" }, auto: ["light", "dark"] },
    brain: { label: "Brain", modes: { light: "Light", softlight: "Soft light", dark: "Dark", softdark: "Soft dark" }, auto: ["light", "dark"] },
    phosphor: { label: "Phosphor", wild: true, modes: { green: "Green", amber: "Amber" } },
    riso: { label: "Riso", wild: true, modes: { paper: "Paper", ink: "Ink" }, auto: ["paper", "ink"] },
    swiss: { label: "Swiss", wild: true, modes: { light: "Light", dark: "Dark" }, auto: ["light", "dark"] },
  };
  const DARK = new Set(["dark", "softdark", "green", "amber", "ink"]);
  const LEGACY = { dark: "classic/dark", light: "classic/light", soft: "classic/softlight" };
  const sysLight = matchMedia("(prefers-color-scheme: light)");

  // "riso/auto" -> { family: "riso", mode: "auto", id: "riso-paper", tone: "light" }. Anything unknown -> classic/auto.
  function resolve(choice) {
    let [family, mode] = String(LEGACY[choice] || choice || "").split("/");
    const f = FAMILIES[family] || FAMILIES[(family = "classic")];
    if (mode === "auto" ? !f.auto : !f.modes[mode]) mode = f.auto ? "auto" : Object.keys(f.modes)[0];
    const m = mode === "auto" ? f.auto[sysLight.matches ? 0 : 1] : mode;
    return { family, mode, id: family + "-" + m, tone: DARK.has(m) ? "dark" : "light" };
  }

  // Put a theme on any element (the page, or a preview tile in a picker).
  function paint(el, choice) {
    const r = resolve(choice);
    Object.assign(el.dataset, { theme: r.id, family: r.family, tone: r.tone });
    return r;
  }

  let current = null;
  function apply(choice) {
    current = choice;
    paint(document.documentElement, choice);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    document.dispatchEvent(new CustomEvent("brain-theme", { detail: resolve(choice) }));
  }
  sysLight.addEventListener("change", () => { if (current && resolve(current).mode === "auto") apply(current); });

  let saved = null; try { saved = localStorage.getItem("brain.theme"); } catch (e) {}
  saved = new URLSearchParams(location.search).get("theme") || saved;  // ?theme=riso/paper to preview one
  window.BrainTheme = { FAMILIES, resolve, paint, apply, get: () => current, saved };
  apply(saved);
})();
