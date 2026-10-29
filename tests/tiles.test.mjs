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

test("nextUp picks the soonest thing still ahead; countdown formats it", () => {
  const S = { now: { upcoming: [{ date: "2026-10-20", title: "Post due" }, { date: "2026-10-20", title: "18:30 Call Sam", time: null },
    { date: "2026-10-21", title: "10:30 Quiz 2", detail: "Ellis" }, { date: "2026-10-19", title: "Gone" }] },
    nudges: [{ status: "open", due: "2026-10-18", title: "Late" }, { status: "open", due: "2026-10-22", title: "Book room" }] };
  const at = s => new Date(s);
  let n = T.nextUp(S, at("2026-10-20T09:00"));
  assert.equal(n.title, "Call Sam"); assert.equal(n.time, "18:30"); assert.equal(n.to, +at("2026-10-20T18:30"));
  n = T.nextUp(S, at("2026-10-20T19:00"));
  assert.equal(n.title, "Post due"); assert.equal(n.to, null);  // untimed, today: no countdown
  n = T.nextUp(S, at("2026-10-21T00:30"));
  assert.equal(n.title, "Quiz 2"); assert.equal(n.detail, "Ellis");
  n = T.nextUp(S, at("2026-10-21T12:00"));
  assert.equal(n.title, "Book room"); assert.equal(n.key, "nudges"); assert.equal(n.to, +at("2026-10-22T00:00"));
  assert.equal(T.nextUp({}, at("2026-10-20T09:00")), null);
  assert.equal(T.countdown((22 * 3600 + 41 * 60 + 58) * 1000), "22h 41m 58s");
  assert.equal(T.countdown((2 * 86400 + 3600 + 5) * 1000), "2d 1h 00m 05s");
  assert.equal(T.countdown(65e3), "1m 05s"); assert.equal(T.countdown(-5), "0m 00s");
});

test("knows tile only once Claude has logged bets", () => {
  assert.ok(!by.knows);
  const k = T.items({ ...state, predictions: { n: 12, score: 64, avg_conf: 80, hit_rate: 70 } }, { today }).find(i => i.key === "knows");
  assert.equal(k.count, 64); assert.equal(k.score, 6);
});

test("a saved order (tiles he moved) wins over the scores, and moveTo drops a tile into another's spot", () => {
  const auto = T.items(state, { today }).map(i => i.key);
  const mine = T.items({ ...state, layout: ["inbox", "gone", "next"] }, { today }).map(i => i.key);
  assert.deepEqual(mine.slice(0, 2), ["inbox", "next"]);  // a saved key that no longer exists is skipped
  assert.deepEqual(mine.slice(2), auto.filter(k => k !== "inbox" && k !== "next"));  // the rest keep score order
  assert.deepEqual(T.moveTo(["a", "b", "c", "d"], "a", "c"), ["b", "c", "a", "d"]);
  assert.deepEqual(T.moveTo(["a", "b", "c", "d"], "d", "b"), ["a", "d", "b", "c"]);
  const its = T.items({ ...state, layout: mine }, { today });
  assert.deepEqual(T.solve(its, 12, 110, { fixed: true }).map(b => b.key).slice(0, 2), ["inbox", "next"]);
});

test("hidden tiles leave the board; o.all still lists them for Settings", () => {
  const keys = T.items({ ...state, hidden: ["inbox", "cover"] }, { today }).map(i => i.key);
  assert.ok(!keys.includes("inbox") && !keys.includes("cover") && keys.includes("next"));
  assert.ok(T.items({ ...state, hidden: ["inbox"] }, { today, all: true }).some(i => i.key === "inbox"));
});

test("today's timed events drop off Up next once their time has passed", () => {
  const d = new Date(), t = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const nx = T.items({ today: t, now: { upcoming: [{ date: t, time: "0:00", title: "Gone" }, { date: t, time: "23:59", title: "Still on" }, { date: t, title: "All day" }] } }).find(i => i.key === "next");
  assert.deepEqual(nx.events.map(e => e[1]), d.getHours() || d.getMinutes() ? ["Still on", "All day"] : ["Gone", "Still on", "All day"]);
});

test("people: dated follow-ups are due or parked, undated wait since last contact", () => {
  const S = { people: [
    { title: "Later", meta: { follow_up: "Follow up 2026-11-17", last_contact: "2026-10-13" } },
    { title: "Late", meta: { follow_up: "Email Oct 27 to pick a day", last_contact: "2026-10-13" } },
    { title: "Old", meta: { follow_up: "Waiting on his verdict", last_contact: "2026-09-14" } },
    { title: "New", meta: { follow_up: "Waiting on a reply", last_contact: "2026-10-26" } },
    { title: "Options", meta: { follow_up: "His pick: Mon Oct 26, Sun Nov 1", last_contact: "2026-10-18" } }] };
  const p = T.items(S, { today: "2026-10-29" }).find(i => i.key === "people");
  assert.deepEqual(p.rows.map(r => r[0]), ["Options", "Late", "Old", "New", "Later"]);
  assert.deepEqual(p.rows.map(r => r[1].split(" · ")[0]), ["3d late", "2d late", "waiting 45d", "waiting 3d", "on Nov 17"]);
  assert.equal(p.count, 4); assert.equal(p.spot[0], "Options"); assert.match(p.summary, /2 due · 2 waiting on a reply · 1 later/);
  const jan = T.items({ people: [{ title: "J", meta: { follow_up: "Coffee Jan 5" } }] }, { today: "2026-12-20" }).find(i => i.key === "people");
  assert.equal(jan.rows[0][1].split(" · ")[0], "on Jan 5");  // next year, not 349 days late
});

test("how well Claude knows you only gets the small shape", () => {
  const k = T.items({ predictions: { n: 40, score: -6, avg_conf: 63, hit_rate: 39 } }, { today }).find(i => i.key === "knows");
  for (const cols of [12, 10, 8]) assert.deepEqual(T.templates(k, 5, cols, 100).map(t => t[0].c), [2]);
});
