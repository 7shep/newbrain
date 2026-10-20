import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const T = createRequire(import.meta.url)("../app/tiles.js");

const today = "2026-10-20";
const state = {
  today, issue: 7, streak: 2,
  now: { headline: "Deck *sent*. Next the site", dek: "A dek.", project: "club", upcoming: [
    { date: today, time: "10:30", title: "Quiz 2", detail: "Room 101" }, { date: "2026-10-21", title: "Club meeting" }, { date: "2026-10-25", title: "Dinner" }] },
  nudges: [{ id: "N-1", title: "Send times", status: "open", due: "2026-10-18" }, { id: "N-2", title: "Book room", status: "open", due: "2026-10-30" }, { id: "N-3", title: "x", status: "done" }],
  people: [1, 2, 3, 4, 5, 6, 7, 8].map(i => ({ title: `Person ${i}`, meta: { follow_up: i === 3 ? "Call Tue Oct 20 18:30" : "Reply", last_contact: "2026-10-0" + i } })).concat([{ title: "Quiet", meta: {} }]),
  internships: [{ company: "A", role: "Dev", deadline: "2026-10-22", group: "apply" }, { company: "B", role: "SWE", deadline: "rolling", group: "check" }, { company: "C", deadline: "2026-09-01", group: "applied" }],
  agents: [{ status: "done", text: "Fix thing", queued: "2026-10-19 12:00", finished: "2026-10-19 12:05", report: "Fixed." }],
  routines: { routines: [{ name: "Scout", enabled: true, ok: true, last_run: "2026-10-19 09:04" }] },
  projects: [{ title: "Club", slug: "club", path: "projects/club.md", resume: "abc", date: "2026-10-19", tldr: "Runs the club", meta: { status: "active" } }],
  ideas: ["2026-10-09 · [try] A poster generator", "2026-10-01 · Plain idea"],
  sessions: [{ date: today }, { date: "2026-10-19" }],
  habits: [{ status: "on", title: "h" }], inbox: [],
};
const its = T.items(state, { today });
const by = Object.fromEntries(its.map(i => [i.key, i]));

test("colsFor thresholds", () => {
  for (const [w, c] of [[1600, 12], [1500, 12], [1499, 10], [1100, 10], [1099, 8], [800, 8], [799, 6], [560, 6], [559, 4], [390, 4]]) assert.equal(T.colsFor(w), c, `width ${w}`);
});

test("scores follow the spec", () => {
  assert.equal(by.cover.score, 80); assert.ok(by.cover.hero && by.cover.hero.headline.includes("*sent*"));
  assert.equal(by.next.score, 95);  // today + quiz
  assert.equal(by.people.score, 78); assert.equal(by.people.spot[0], "Person 3");  // VIP: today's call
  assert.equal(by.intern.score, 25);
  assert.equal(by.nudges.score, 25); assert.equal(by.nudges.spot[1], "2d overdue");
  assert.equal(by.agents.score, 5); assert.equal(by.routines.score, 15); assert.equal(by.projects.score, 30);
  assert.equal(by.ideas.score, 10); assert.deepEqual(by.ideas.rows[0], ["A poster generator", "10-09"]);
  assert.equal(by.streak.score, 12); assert.deepEqual(by.streak.days.slice(-2), [1, 1]); assert.equal(by.streak.days.length, 14);
  assert.equal(by.inbox.score, 1); assert.ok(by.inbox.cleared);
  assert.ok(!by.habits && !by.map);
  assert.ok(its.findIndex(i => i.key === "people") < its.findIndex(i => i.key === "intern"));
  assert.deepEqual(its.slice(0, 3).map(i => i.key), ["next", "cover", "people"]);  // a quiz today outranks the cover
  for (let i = 1; i < its.length; i++) assert.ok(its[i - 1].score >= its[i].score);
});

test("cover is the hero when nothing outranks it; 90 when nothing is due", () => {
  const calm = T.items({ ...state, now: { headline: "Hi", upcoming: [] }, nudges: [], internships: [] }, { today });
  assert.equal(calm[0].key, "cover"); assert.equal(calm[0].score, 90);
  const S2 = T.items({ ...state, now: { ...state.now, upcoming: [{ date: today, title: "Lunch" }] } }, { today });
  assert.equal(S2[0].key, "cover"); assert.equal(S2[1].key, "people");
});

test("missing keys and phone state are tolerated", () => {
  const e = T.items({}, { today });
  assert.ok(e.length >= 10); assert.ok(e.every(i => typeof i.score === "number"));
  const m = T.items(state, { today, graphSummary: { nodes: 10, links: 4, legend: [["A", 5]] } });
  assert.equal(m.find(i => i.key === "map").score, 8);
  const h = T.items({ ...state, habits: [{ status: "proposed", title: "p" }] }, { today });
  assert.equal(h.find(i => i.key === "habits").score, 25);
});

const strip = b => JSON.stringify(b);
for (const [cols, colW] of [[12, 110], [10, 96], [8, 90], [6, 80], [4, 80]]) test(`solve at ${cols} cols: deterministic, no holes, parts inside cells`, () => {
  const a = T.solve(its, cols, colW), b = T.solve(T.items(state, { today }), cols, colW);
  assert.equal(strip(a), strip(b));
  assert.equal(a.length, its.length);
  const seen = new Map(); let bottom = 0;
  for (const bl of a) for (const [x, y] of bl.cells) {
    assert.ok(x >= 0 && x < cols, `x ${x} in board`); assert.ok(!seen.has(x + "," + y), `cell ${x},${y} used once`);
    seen.set(x + "," + y, bl.key); bottom = Math.max(bottom, y + 1);
  }
  for (let y = 0; y < bottom; y++) for (let x = 0; x < cols; x++) assert.ok(seen.has(x + "," + y), `hole at ${x},${y}`);
  for (const bl of a) {
    const own = new Set(bl.cells.map(c => c + ""));
    for (const q of bl.parts) for (let y = q.y; y < q.y + q.r; y++) for (let x = q.x; x < q.x + q.c; x++) assert.ok(own.has(x + "," + y), `${bl.key} part outside its cells`);
  }
  assert.ok(a.find(bl => bl.rank === 0).parts.some(q => q.role === "hero"));
});

test("outline is one closed path with rounded corners", () => {
  const o = T.outline([[0, 0], [1, 0], [2, 0], [1, 1], [1, 2]], 100, 28, 14, 20);  // a T
  assert.match(o.d, /^M[\d. -]+Q/); assert.ok(o.d.endsWith("Z")); assert.equal((o.d.match(/M/g) || []).length, 1);
  assert.equal((o.d.match(/Q/g) || []).length, 8);  // 8 corners on a T, convex and concave
  assert.deepEqual([o.x0, o.y0, o.w, o.h], [0, 0, 328, 112]);
  const sq = T.outline([[3, 2]], 50, 28, 14);
  assert.equal((sq.d.match(/Q/g) || []).length, 4); assert.deepEqual([sq.x0, sq.y0, sq.w, sq.h], [3, 2, 50, 28]);
});

test("renderPart escapes text and shows lists, buttons, clear", () => {
  const evil = { ...by.ideas, title: "<b>x</b>", rows: Array.from({ length: 9 }, (_, i) => [`<img src=x onerror=alert(${i})>`, "\"q\""]), count: 9, summary: "<script>" };
  for (const role of ["head", "list", "big", "hero"]) {
    const h = T.renderPart(evil, role, { w: 300, h: 300 });
    assert.ok(!/<img|<script|<b>x/.test(h), `${role} escaped`);
  }
  const list = T.renderPart(evil, "list", { w: 300, h: 120 });
  assert.match(list, /All 9 →/); assert.ok(!/more/.test(list.replace(/bt-more/g, "")));
  assert.ok(!/<div class="bt-more" hidden>/.test(list) && /<div class="bt-row" hidden>/.test(list), "rows past the estimate wait hidden for fit()");
  assert.ok(!/bt-more" hidden/.test(T.renderPart(evil, "list", { w: 300, h: 120 })));
  assert.match(T.strip(by.people), /bt-big.*bt-spot/s); assert.equal(T.strip(by.cover), ""); assert.match(T.strip(by.inbox), /All clear/);
  assert.match(T.renderPart(by.inbox, "big", { w: 200, h: 100 }), /✓ All clear/);
  assert.match(T.renderPart(by.cover, "hero", { w: 800, h: 400 }, { cover: "long" }), /<i>sent<\/i>.*bt-dek/s);
  assert.ok(!/bt-side/.test(T.renderPart(by.cover, "hero", { w: 800, h: 400 }, { cover: "short" })));
  assert.match(T.renderPart(by.streak, "big", { w: 200, h: 120 }), /bt-dots/);
  const blk = T.solve(its, 12, 110).find(b => b.key === "people");
  const rb = T.renderBlock(by.people, blk, { cw: 110, rh: 28, gap: 14 });
  assert.match(rb.html, /<svg class="bt-outline"/); assert.ok(rb.c >= 1 && rb.r >= 1);
});
