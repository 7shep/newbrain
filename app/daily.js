/* Shared daily checklist UI for desktop and phone. */
(function (host) {
  "use strict";
  const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const day = (now = new Date()) => `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const forDay = (data, date) => data?.date === date ? data : { date, tasks: [] };
  function apply(data, body) {
    const next = JSON.parse(JSON.stringify(forDay(data, body.date)));
    const task = next.tasks.find(t => t.id === body.id);
    if (body.action === "add" && !task) next.tasks.push({ id: body.id, text: body.text, done: false });
    if (body.action === "set" && task) task.done = body.done;
    if (body.action === "remove") next.tasks = next.tasks.filter(t => t.id !== body.id);
    return next;
  }
  const views = new WeakMap();
  let draft = "", draftDay = day();
  function mount(root, data, send) {
    if (!root) return;
    const date = day();
    if (draftDay !== date) { draft = ""; draftDay = date; }
    let view = views.get(root);
    if (!view) {
      root.innerHTML = `<div class="daily-brief" hidden></div><p class="daily-summary" aria-live="polite"></p><ul class="daily-list"></ul>
        <form class="daily-form"><label class="daily-label">Add a task for today<input name="task" maxlength="300" autocomplete="off" placeholder="What needs doing today?" required></label><button type="submit">Add task</button></form>
        <p class="daily-error" role="alert" hidden></p><p class="daily-reset">Starts fresh every day. Unfinished tasks stay with that day.</p>`;
      view = { busy: false, date, data, send, signature: "", root };
      views.set(root, view);
      const input = root.querySelector("input[name=task]");
      input.value = draft;
      input.addEventListener("input", () => { draft = input.value; });
      async function act(body) {
        if (view.busy) return;
        if (view.date !== day()) { mount(root, { date: day(), tasks: [] }, view.send); return; }
        view.busy = true;
        root.querySelector(".daily-error").hidden = true;
        root.setAttribute("aria-busy", "true");
        root.querySelectorAll("input, button").forEach(el => { el.disabled = true; });
        try {
          await view.send({ ...body, date: view.date });
          if (body.action === "add") { input.value = draft = ""; view.addId = null; }
        } catch (e) {
          const error = root.querySelector(".daily-error");
          error.textContent = `Couldn't save your task. ${e.message || "Try again."}`;
          error.hidden = false;
        } finally {
          view.busy = false;
          view.signature = "";
          root.setAttribute("aria-busy", "false");
          root.querySelectorAll("input, button").forEach(el => { el.disabled = false; });
          mount(root, view.data, view.send);
          if (body.action === "set") root.querySelector(`[data-daily-check="${body.id}"]`)?.focus();
          else input.focus();
        }
      }
      root.querySelector("form").addEventListener("submit", e => {
        e.preventDefault();
        const text = input.value.trim();
        if (text) {
          if (!view.addId || view.addText !== text) { view.addId = crypto.randomUUID().replace(/-/g, "").slice(0, 16); view.addText = text; }
          act({ action: "add", id: view.addId, text });
        }
      });
      root.addEventListener("change", e => {
        if (e.target.matches("[data-daily-check]")) act({ action: "set", id: e.target.dataset.dailyCheck, done: e.target.checked });
      });
      root.addEventListener("click", e => {
        const b = e.target.closest("[data-daily-remove]");
        if (b) act({ action: "remove", id: b.dataset.dailyRemove });
      });
    }
    if (view.date !== date) { root.querySelector("input[name=task]").value = ""; view.signature = ""; }
    view.date = date; view.data = forDay(data, date); view.send = send;
    const brief = view.data.brief, briefEl = root.querySelector(".daily-brief");
    briefEl.hidden = !brief;  // the morning routine's daily/YYYY-MM-DD-briefing.md; the page's [data-open] handler opens it
    briefEl.innerHTML = brief ? `<b>Morning brief</b>${brief.line ? `<span>${esc(brief.line)}</span>` : ""}<button type="button" data-open="${esc(brief.path)}">Read the brief</button>` : "";
    root.querySelector(".daily-reset").textContent = view.data.plan_note || "Starts fresh every day. Unfinished tasks stay with that day.";
    const tasks = view.data.tasks, done = tasks.filter(t => t.done).length;
    root.querySelector(".daily-summary").textContent = tasks.length ? `${done} of ${tasks.length} done today` : "A fresh page for today. Add your first task.";
    const signature = JSON.stringify(tasks);
    if (!view.busy && view.signature !== signature) {
      const focused = root.contains(document.activeElement) ? document.activeElement : null;
      const focusId = focused?.dataset.dailyCheck || focused?.dataset.dailyRemove;
      const focusAttr = focused?.hasAttribute("data-daily-check") ? "data-daily-check" : "data-daily-remove";
      root.querySelector("ul").innerHTML = tasks.map(t => `<li class="daily-row${t.done ? " is-done" : ""}"><label><input type="checkbox" data-daily-check="${esc(t.id)}"${t.done ? " checked" : ""}><span>${esc(t.text)}</span></label><button type="button" data-daily-remove="${esc(t.id)}" aria-label="Remove ${esc(t.text)}" title="Remove task"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button></li>`).join("");
      view.signature = signature;
      if (focusId) root.querySelector(`[${focusAttr}="${CSS.escape(focusId)}"]`)?.focus();
    }
  }
  function onDayChange(callback) {
    let last = day();
    const check = () => { const date = day(); if (date !== last) { last = date; callback(); } };
    setInterval(check, 1000);
    document.addEventListener("visibilitychange", check);
    host.addEventListener("focus", check);
  }
  const api = { day, forDay, apply, mount, onDayChange };
  if (typeof module !== "undefined") module.exports = api;
  else host.BrainDaily = api;
})(typeof window === "undefined" ? globalThis : window);
