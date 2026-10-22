/* Adaptive tiles: the engine shared by the desktop (app/index.html) and the phone (mobile/index.html).
   items() turns Brain's state into scored items, templates() offers each a few shapes made of parts sized to their text,
   solve() packs them into the board with no holes, outline() draws one continuous rounded piece, renderPart() fills a part.
   Plain script: window.BrainTiles in the browser, module.exports for node tests. */
(function () {
const ROW = 28, GAP = 14, U = ROW + GAP, need = px => Math.max(1, Math.ceil(px / U));
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ICONS = { music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>', doc: '<path d="M6 3h9l4 4v14H6z"/>', cal: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>', bell: '<path d="M6 8a6 6 0 1112 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4"/>',
  bot: '<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 3v4M9 12h.01M15 12h.01"/>', ppl: '<circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6 7-6s7 2 7 6"/>', case: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5h6v2"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', fold: '<path d="M3 7h6l2 2h10v10H3z"/>', bulb: '<path d="M9 18h6M10 22h4M12 2a7 7 0 00-4 12.7V17h8v-2.3A7 7 0 0012 2z"/>',
  fire: '<path d="M12 3s5 5 5 10a5 5 0 01-10 0c0-3 2-4 2-4s0 3 3 3c0-4 0-9 0-9z"/>', inbox: '<path d="M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5"/>',
  aim: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>', map: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="8" r="2.5"/><circle cx="10" cy="18" r="2.5"/><path d="M8 7l8 1M7.5 8l2 8"/>', spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>' };
const LEGEND = ["--accent", "--good", "--info", "--bad", "--muted", "--extra"];

// ---------- items: one per section, scored 0-100 from live state (spec "Scores") ----------
const ORDER = ["cover", "next", "people", "intern", "nudges", "agents", "routines", "projects", "ideas", "streak", "habits", "knows", "map", "inbox"];
const ISO = /^\d{4}-\d{2}-\d{2}/;
function items(S, o) {
  S = S || {}; o = o || {};
  const today = o.today || S.today || new Date().toISOString().slice(0, 10), T = Date.parse(today + "T12:00:00Z");
  const dd = s => ISO.test(s || "") ? Math.round((Date.parse(s.slice(0, 10) + "T12:00:00Z") - T) / 864e5) : null;
  const day = s => new Date(s.slice(0, 10) + "T12:00:00Z").toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" });
  const rel = s => { const d = dd(s); return d === null ? "" : d === 0 ? "today" : d === 1 ? "tmrw" : d < 0 ? `${-d}d ago` : day(s); };
  const all = {}, mk = (key, title, icon, score, x) => all[key] = Object.assign({ key, title, icon, score, count: 0, summary: "", spot: null, rows: [], events: null, hero: null, cleared: false, days: null, legend: null, why: "" }, x);

  // Up next
  const up = (S.now && S.now.upcoming || []).filter(u => { const d = dd(u.date); return d === null || d >= 0; })
    .sort((a, b) => String(a.date).localeCompare(String(b.date)));
  const events = up.map(u => [rel(u.date) + (u.time ? " " + u.time : ""), u.title || "", u.detail || ""]);
  const d0 = up.length ? dd(up[0].date) : null, nToday = up.filter(u => dd(u.date) === 0).length;
  const exam = up.some(u => dd(u.date) === 0 && /exam|quiz|midterm|test|interview/i.test(u.title || ""));
  mk("next", "Up next", "cal", (d0 === 0 ? 75 : d0 === 1 ? 60 : d0 !== null && d0 <= 3 ? 45 : 25) + (exam ? 20 : 0), {
    count: up.length, events: events.slice(0, 8), cleared: !up.length, why: `${up.length} coming up`,
    summary: up.length ? `${nToday} today · next: ${up[0].title}` : "Nothing coming up.", spot: up.length ? [up[0].title, events[0][0]] : null });

  // People waiting: VIP right now is whoever's follow-up names today, else whoever has waited longest
  const md = new Date(T).toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" });
  const ppl = (S.people || []).filter(p => p.meta && p.meta.follow_up).sort((a, b) => String(a.title).localeCompare(String(b.title)));
  const vip = ppl.find(p => p.meta.follow_up.includes(today) || p.meta.follow_up.includes(md))
    || ppl.slice().sort((a, b) => String(a.meta.last_contact || "").localeCompare(String(b.meta.last_contact || "")))[0];
  mk("people", "People waiting", "ppl", Math.min(78, 10 * ppl.length), { count: ppl.length, cleared: !ppl.length, why: `${ppl.length} follow-up${ppl.length === 1 ? "" : "s"}`,
    summary: `${ppl.length} ${ppl.length === 1 ? "person" : "people"} with something open.`, rows: ppl.map(p => [p.title, p.meta.follow_up]), spot: vip ? [vip.title, vip.meta.follow_up] : null });

  // Internships
  const ins = S.internships || [], g = k => ins.filter(r => r.group === k);
  const live = ins.filter(r => r.group === "apply" || r.group === "check");
  const soon = live.filter(r => { const d = dd(r.deadline); return d !== null && d >= 0 && d <= 7; });
  const nextDl = live.filter(r => dd(r.deadline) >= 0).sort((a, b) => a.deadline.localeCompare(b.deadline))[0];
  const iso = r => ISO.test(r.deadline || "") ? r.deadline : "9999";
  mk("intern", "Internships", "case", Math.min(70, 10 + 15 * soon.length), { count: live.length, cleared: !ins.length, why: `${soon.length} due this week`,
    summary: `${g("applied").length} applied, ${g("apply").length} to apply, ${g("check").length} to check.`,
    rows: [...g("apply"), ...g("check")].sort((a, b) => (a.group === b.group ? 0 : a.group === "apply" ? -1 : 1) || iso(a).localeCompare(iso(b))).map(r => [r.company, `${r.group} · ${r.deadline || "—"}`]),
    spot: nextDl ? [[nextDl.company, nextDl.role].filter(Boolean).join(" · "), `deadline ${nextDl.deadline}`] : null });

  // Notes to self
  const open = (S.nudges || []).filter(n => n.status === "open"), due = n => n.due ? dd(n.due) : null;
  const late = open.filter(n => due(n) !== null && due(n) < 0).sort((a, b) => due(a) - due(b));
  const dueTxt = n => { const d = due(n); return d === null ? "" : d < 0 ? `${-d}d overdue` : d === 0 ? "today" : `in ${d}d`; };
  mk("nudges", "Notes to self", "bell", Math.min(90, 15 * late.length + 5 * open.length), { count: open.length, cleared: !open.length, why: late.length ? `${late.length} overdue` : `${open.length} open`,
    summary: `${open.length} thing${open.length === 1 ? "" : "s"} you told yourself to do${late.length ? `, ${late.length} overdue` : ""}.`,
    rows: open.map(n => [n.title, dueTxt(n)]), spot: (n => n ? [n.title, dueTxt(n) || "open"] : null)(late[0] || open.filter(n => due(n) !== null).sort((a, b) => due(a) - due(b))[0] || open[0]) });

  // Claude's agents
  const runs = (S.agents || []).slice().sort((a, b) => String(b.queued || "").localeCompare(String(a.queued || "")));
  const busy = runs.filter(r => /queued|running|failed/.test(r.status || "")).length;
  mk("agents", "Claude's agents", "bot", busy ? Math.min(70, 20 * busy) : 5, { count: runs.length, cleared: !runs.length, why: busy ? `${busy} active` : "all done",
    summary: "What your captures turned into.", rows: runs.map(r => [r.text || r.file || "", `${r.status} · ${String(r.finished || r.queued || "").slice(11, 16)}`]),
    spot: runs[0] ? [runs[0].text || "", String(runs[0].report || runs[0].status || "").slice(0, 160)] : null });

  // Routines
  const rts = (S.routines && S.routines.routines || []).filter(r => r.enabled !== false), bad = rts.filter(r => r.ok === false);
  mk("routines", "Routines", "clock", bad.length ? 70 : 15, { count: rts.length, cleared: !rts.length, why: bad.length ? `${bad.length} failed` : "all OK",
    summary: `${rts.length} running${bad.length ? `, ${bad.length} failed` : ""}.`, rows: rts.map(r => [r.name, `${r.ok === false ? "✗" : "✓"} ${String(r.last_run || "").slice(5)}`]),
    spot: bad[0] ? [bad[0].name, "last run failed"] : null });

  // Projects: most active = most recently touched
  const prj = (S.projects || []).filter(p => !p.archived && (!p.meta || !p.meta.status || p.meta.status === "active"));
  const hot = prj.slice().sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))[0];
  mk("projects", "Projects", "fold", 30, { count: prj.length, cleared: !prj.length, why: `${prj.length} active`, summary: `${prj.length} active.`,
    rows: prj.map(p => [p.title, (p.meta && p.meta.summary) || p.tldr || ""]), spot: hot ? [hot.title, hot.tldr || (hot.meta && hot.meta.summary) || ""] : null });

  // Ideas: "2026-10-09 · [try] text"
  const ideas = (S.ideas || []).map(s => { const m = String(s).match(/^(\d{4}-\d{2}-\d{2})\s*·\s*(?:\[[^\]]*\]\s*)?(.*)$/); return m ? [m[2], m[1].slice(5)] : [String(s), ""]; });
  mk("ideas", "Ideas", "bulb", 10, { count: ideas.length, cleared: !ideas.length, why: `${ideas.length} open`, summary: `${ideas.length} open.`, rows: ideas });

  // Streak: a 14-day strip of days with a session
  const seen = new Set((S.sessions || []).map(s => String(s.date || (s.meta && s.meta.date) || "").slice(0, 10)));
  const days = Array.from({ length: 14 }, (_, i) => seen.has(new Date(T - (13 - i) * 864e5).toISOString().slice(0, 10)) ? 1 : 0);
  mk("streak", "Streak", "fire", 12, { count: `${S.streak || 0}d`, days, why: `${S.streak || 0} day${S.streak === 1 ? "" : "s"}`, summary: "last 14 days" });

  // Habits: only while Claude has some waiting for a yes/no
  const prop = (S.habits || []).filter(h => h.status === "proposed");
  if (prop.length) mk("habits", "Habits", "spark", 5 + 20 * prop.length, { count: prop.length, why: `${prop.length} to decide`, summary: `${prop.length} new habit${prop.length === 1 ? "" : "s"} to decide.`, rows: prop.map(h => [h.title, "to decide"]) });

  // How well Claude knows you: only once Claude has logged bets (claude/predictions.md)
  const pr = S.predictions;
  if (pr && pr.n) mk("knows", "How well Claude knows you", "aim", 6, { count: pr.score, why: `${pr.n} bets`, summary: `Says ${pr.avg_conf}% sure, right ${pr.hit_rate}%.` });

  // Map: only when the page has a graph summary {nodes, links, legend:[[name,count]]}
  const gs = o.graphSummary;
  if (gs) mk("map", "Map", "map", 8, { count: gs.nodes || 0, legend: (gs.legend || []).slice(0, 5), why: `${gs.nodes || 0} notes · ${gs.links || 0} links`, summary: `${gs.nodes || 0} notes` });

  // Inbox. ponytail: spec only scores the empty inbox (1); a full one gets 20 until it's tuned
  const inbox = (S.inbox || []).map(l => { const p = String(l).split(" · "); return p.length >= 3 ? [p.slice(2).join(" · "), p[1]] : [String(l), ""]; });
  mk("inbox", "Inbox", "inbox", inbox.length ? 20 : 1, { count: inbox.length, cleared: !inbox.length, why: inbox.length ? `${inbox.length} to file` : "empty", summary: `${inbox.length} to file.`, rows: inbox });

  // Custom tiles: one per tiles/*.md, opened as that note
  (S.tiles || []).forEach(t => mk("t:" + t.slug, t.title, ICONS[t.icon] ? t.icon : "doc", 20, { count: t.rows.length, path: t.path,
    why: `${t.rows.length} item${t.rows.length === 1 ? "" : "s"}`, summary: t.summary || (t.rows[0] ? t.rows[0][0] : "Nothing yet."), rows: t.rows, spot: t.rows[0] || null }));

  // Cover last: it scores 90 when nothing else is due
  const n = S.now || {}, proj = (S.projects || []).find(p => p.slug === n.project);
  const quiet = !up.some(u => dd(u.date) <= 0) && !open.some(n => due(n) !== null && due(n) <= 0) && !soon.length;
  const side = up.slice(0, 2).map((u, i) => `${rel(u.date)[0].toUpperCase() + rel(u.date).slice(1)}: ${events[i][1]}`);
  const acts = proj ? [...(proj.resume ? [{ label: "Resume last chat", act: "resume", arg: proj.slug }] : []), { label: "Project page", act: "open", arg: proj.path }] : [];
  const head = n.headline || "Nothing on the cover yet.";
  mk("cover", S.issue ? `Issue ${S.issue}` : "Cover", "doc", quiet ? 90 : 80, { count: S.issue || "", summary: head.replace(/\*/g, ""), why: "today's cover",
    hero: { headline: head, side, dek: n.dek || "", acts } });

  const rank = k => ORDER.includes(k) ? ORDER.indexOf(k) : ORDER.length;  // custom tiles sort after the built-ins on a tie
  return Object.keys(all).sort((a, b) => all[b].score - all[a].score || rank(a) - rank(b)).map(k => all[k]);
}

// ---------- templates: shapes true to what an item holds, each part sized to its text ----------
const P = (x, y, c, r, role) => ({ x, y, c, r, role });
const heroOf = it => it.hero || { headline: it.summary || it.title, side: (it.events ? it.events.map(e => `${e[0]} · ${e[1]}`) : it.rows.map(r => r.filter(Boolean).join(" · "))).slice(0, 4), dek: "", acts: [{ label: "Open", act: "open", arg: it.key }] };
function heroPx(it, w, phone, cover) {
  const h = heroOf(it), fs = Math.min(52, Math.max(28, w * .06)), inner = w - 52, side = cover === "short" ? [] : h.side, two = !phone && inner > 560 && side.length;
  const hw = two ? inner * .6 - 14 : inner, sw = two ? inner * .4 - 14 : inner;
  const left = 30 + Math.ceil(h.headline.replace(/\*/g, "").length * fs * .5 / hw) * fs + (cover === "long" && h.dek ? Math.ceil(h.dek.length * 7.4 / hw) * 21 + 8 : 0);
  const sideH = side.reduce((s, t) => s + Math.ceil(t.length * 7.2 / sw) * 20 + 12, 0);
  return 62 + (two ? Math.max(left, sideH + 24) : left + sideH) + (h.acts.length ? 54 : 10);
}
function headPx(it, w) {
  const wide = w > 520, tw = Math.max(80, w - 110 - (it.spot && wide ? Math.min(w * .48, 300) + 14 : 0));
  return 46 + Math.max(44, Math.ceil(it.summary.length * 7.4 / tw) * 19, it.spot && wide ? 80 : 0) + (it.spot && !wide ? 88 : 0);
}
function templates(it, rank, cols, colW, o) {
  const cover = (o && o.cover) || "medium", pw = c => c * (colW + GAP) - GAP, n = it.rows.length, s = it.score;
  if (cols <= 6) {  // phone: pieces stack at full width, header above its list; number tiles pair up two to a row
    const F = cols, half = Math.max(1, Math.floor(F / 2)), hh = need(headPx(it, pw(F)));
    if (it.cleared) return [[P(0, 0, half, need(80), "big")]];
    if (rank === 0) return [[P(0, 0, F, need(heroPx(it, pw(F), true, cover)), "hero")]];
    if (it.events) return [[P(0, 0, F, hh, "head"), P(0, hh, F, need(Math.min(it.events.length, 5) * 58 + 12), "list")]];
    if (it.legend) return [[P(0, 0, F, need(200), "map")]];
    if (n && s >= 18) { const lr = need(Math.min(n, 5) * 32 + (n > 5 ? 44 : 8));  /* room for "All N →" only when rows are left out */ return [[P(0, 0, F, hh, "head"), P(0, hh, F, lr, "list")]]; }
    return [[P(0, 0, half, need(it.days ? 140 : 118), "big")]];
  }
  // desktop: designed at 12 columns, widths scaled to 10/8
  const W = c => cols === 12 ? c : Math.min(cols, Math.max(2, Math.round(c * cols / 12))), B = need(118);
  if (it.cleared) return [[P(0, 0, W(2), need(80), "big")], [P(0, 0, W(3), need(80), "big")]];
  if (rank === 0) return [7, 8].map(c => [P(0, 0, W(c), need(heroPx(it, pw(W(c)), false, cover)), "hero")]);
  const hh = c => need(headPx(it, pw(W(c))));
  if (it.events) {
    const lr = need(Math.min(it.events.length, 8) * 50 + 12 + (it.events.length > 8 ? 40 : 0));
    return s >= 40 ? [[P(0, 0, W(5), hh(5), "head"), P(1, hh(5), W(3), lr, "list")], [P(0, 0, W(4), hh(4), "head"), P(0, hh(4), W(3), lr, "list")]] : [[P(0, 0, W(3), hh(3), "head"), P(0, hh(3), W(3), lr, "list")]];
  }
  if (it.legend) return [[P(0, 0, W(5), need(210), "map")], [P(0, 0, W(6), need(210), "map")]];
  if (n && s >= 18) {
    const lr = Math.min(need(n * 31 + 16), s >= 35 ? 7 : 5);
    const T = [[P(0, 0, W(5), hh(5), "head"), P(0, hh(5), W(3), lr, "list")], [P(0, 0, W(3), hh(3), "head"), P(0, hh(3), W(4), lr, "list")], [P(0, 0, W(4), hh(4), "head"), P(0, hh(4), W(4), lr, "list")], [P(0, 0, W(4), hh(4), "head"), P(1, hh(4), W(3), lr, "list")]];
    return s >= 35 ? T : T.slice(1);
  }
  return it.days ? [[P(0, 0, W(3), need(140), "big")]] : n ? [[P(0, 0, W(3), need(230), "big")], [P(0, 0, W(4), need(190), "big")]] : [[P(0, 0, W(2), B, "big")], [P(0, 0, W(3), B, "big")]];
}

// ---------- solve: seeded multi-trial packing, then gap closing and arms (no holes, ever) ----------
const rng = a => () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const cellsOf = parts => parts.flatMap(q => { const o = []; for (let y = q.y; y < q.y + q.r; y++) for (let x = q.x; x < q.x + q.c; x++) o.push([x, y]); return o; });
function place(order, pick, cols) {  // drop pieces in order, each at the highest-then-leftmost spot it fits
  const g = [], at = (x, y) => g[y] && g[y][x], out = [];
  for (const p of order) {
    const parts = pick[p.key], wd = Math.max(...parts.map(q => q.x + q.c)), cells = cellsOf(parts);
    search: for (let y = 0; ; y++) for (let x = 0; x + wd <= cols; x++) {
      if (cells.some(([a, b]) => at(x + a, y + b))) continue;
      const b = { key: p.key, rank: p.rank, parts: parts.map(q => ({ ...q, x: q.x + x, y: q.y + y })), cells: cells.map(([a, c]) => [a + x, c + y]), py: y };
      for (const [a, c] of b.cells) (g[c] = g[c] || [])[a] = b;
      out.push(b); break search;
    }
  }
  const bottom = Math.max(...out.flatMap(b => b.cells.map(c => c[1]))) + 1; let holes = 0;
  for (let y = 0; y < bottom; y++) for (let x = 0; x < cols; x++) if (!at(x, y)) holes++;
  return { out, g, bottom, holes };
}
function solve(list, cols, colW, o) {
  if (!list.length) return [];
  let seed = cols * 7919; for (const it of list) for (const ch of it.key + it.score) seed = Math.imul(seed ^ ch.charCodeAt(0), 16777619);
  const rand = rng(seed), byKey = Object.fromEntries(list.map(it => [it.key, it]));
  const variants = Object.fromEntries(list.map((it, i) => [it.key, templates(it, i, cols, colW, o).flatMap((tp, ti) => {
    tp = tp.map(q => ({ ...q, c: Math.min(q.c, cols), x: Math.min(q.x, cols - Math.min(q.c, cols)) }));
    const wd = Math.max(...tp.map(q => q.x + q.c));
    return [{ tp, ti }, { tp: tp.map(q => ({ ...q, x: wd - q.x - q.c })), ti }];
  })]));
  let best = null;
  for (let trial = 0; trial < 700; trial++) {
    const order = list.map((it, i) => ({ key: it.key, rank: i }));
    for (let i = 1; i < order.length - 1; i++) if (rand() < .25) [order[i], order[i + 1]] = [order[i + 1], order[i]];
    const pick = {}, vi = {};
    for (const it of list) { const v = variants[it.key], c = trial === 0 ? v[0] : v[Math.floor(rand() * v.length)]; pick[it.key] = c.tp; vi[it.key] = c.ti; }
    const res = place(order, pick, cols);
    res.cost = res.holes * 40 + res.bottom * 7 + res.out.reduce((s, b) => s + byKey[b.key].score * b.py * .06 + vi[b.key] * 1.5, 0);
    if (!best || res.cost < best.cost) best = res;
  }
  // close the gaps: grow a real part (its content gets more room) before falling back to a plain arm
  const { out, g, bottom } = best, at = (x, y) => g[y] && g[y][x], free = (x, y) => x >= 0 && x < cols && y >= 0 && y < bottom && !at(x, y), claim = (b, x, y) => (g[y] = g[y] || [])[x] = b;
  const run = (n, f) => [...Array(n)].every((_, i) => f(i));
  for (let moved = true; moved;) {
    moved = false;
    for (const b of out) for (const q of b.parts) {
      if (run(q.r, i => free(q.x + q.c, q.y + i))) { for (let i = 0; i < q.r; i++) claim(b, q.x + q.c, q.y + i); q.c++; moved = true; }
      if (run(q.c, i => free(q.x + i, q.y + q.r))) { for (let i = 0; i < q.c; i++) claim(b, q.x + i, q.y + q.r); q.r++; moved = true; }
      if (run(q.r, i => free(q.x - 1, q.y + i))) { q.x--; q.c++; for (let i = 0; i < q.r; i++) claim(b, q.x, q.y + i); moved = true; }
      if (run(q.c, i => free(q.x + i, q.y - 1))) { q.y--; q.r++; for (let i = 0; i < q.c; i++) claim(b, q.x + i, q.y); moved = true; }
    }
  }
  for (const b of out) b.cells = cellsOf(b.parts);
  // any cell still empty becomes an arm of its most important neighbour (the hero only if nothing else touches it)
  for (let left = true; left;) {
    left = false;
    for (let y = 0; y < bottom; y++) for (let x = 0; x < cols; x++) if (!at(x, y)) {
      const nb = [[x - 1, y], [x, y - 1], [x + 1, y], [x, y + 1]].map(([a, c]) => at(a, c)).filter(Boolean)
        .sort((p, q) => (p.parts.some(z => z.role === "hero") - q.parts.some(z => z.role === "hero")) || p.rank - q.rank)[0];
      if (nb) { claim(nb, x, y); nb.cells.push([x, y]); } else left = true;
    }
  }
  return out.map(({ key, rank, parts, cells }) => ({ key, rank, parts, cells }));
}

// ---------- outline: one continuous path around a piece, rounded convex and concave corners ----------
function outline(cells, cw, rh, gap, radius) {
  radius = radius ?? 20;
  const S = new Set(cells.map(c => c + "")), has = (x, y) => S.has(x + "," + y);
  const x0 = Math.min(...cells.map(c => c[0])), y0 = Math.min(...cells.map(c => c[1])), x1 = Math.max(...cells.map(c => c[0])), y1 = Math.max(...cells.map(c => c[1]));
  const X = x => x * (cw + gap), Y = y => y * (rh + gap), E = new Map(), add = (a, b, d) => { const k = a + ""; (E.get(k) || E.set(k, []).get(k)).push({ a, b, d }); };
  for (const [x, y] of cells) {
    if (!has(x, y - 1)) add([x, y], [x + 1, y], "R"); if (!has(x + 1, y)) add([x + 1, y], [x + 1, y + 1], "D");
    if (!has(x, y + 1)) add([x + 1, y + 1], [x, y + 1], "L"); if (!has(x - 1, y)) add([x, y + 1], [x, y], "U");
  }
  // walk clockwise from the top-left cell's top edge (always on the outside); at a pinch, turn right first
  const DIRS = "RDLU", top = cells.filter(c => c[1] === y0).sort((a, b) => a[0] - b[0])[0], path = [];
  let e = E.get(top + "").find(z => z.d === "R");
  const start = e;
  do {
    path.push(e);
    const nx = E.get(e.b + "") || [], di = DIRS.indexOf(e.d);
    e = [1, 0, 3].map(t => nx.find(z => z.d === DIRS[(di + t) % 4])).find(Boolean);
  } while (e && e !== start && path.length <= cells.length * 4);
  const pts = [];
  for (let i = 0; i < path.length; i++) {
    const p = path[i], n = path[(i + 1) % path.length];
    if (p.d === n.d) continue;
    const v = p.b, hor = p.d === "R" || p.d === "L" ? p : n, ver = p.d === "U" || p.d === "D" ? p : n;
    pts.push([X(v[0] - x0) - (ver.d === "D" ? gap : 0), Y(v[1] - y0) - (hor.d === "L" ? gap : 0)]);
  }
  let d = "";
  pts.forEach((Q, i) => {
    const A = pts[(i + pts.length - 1) % pts.length], B = pts[(i + 1) % pts.length];
    const u = Z => { const dx = Z[0] - Q[0], dy = Z[1] - Q[1], l = Math.hypot(dx, dy) || 1, r = Math.min(radius, l / 2); return [+(Q[0] + dx / l * r).toFixed(1), +(Q[1] + dy / l * r).toFixed(1)]; };
    d += (i ? "L" : "M") + u(A).join(" ") + "Q" + Q.join(" ") + " " + u(B).join(" ");
  });
  return { d: d + "Z", x0, y0, w: X(x1 - x0 + 1) - gap, h: Y(y1 - y0 + 1) - gap };
}

// ---------- renderPart: one part's share of the content (all text escaped) ----------
const ico = k => `<svg class="bt-i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[k] || ""}</svg>`;
const rowHtml = (r, off) => `<div class="bt-row"${off ? " hidden" : ""}><b>${esc(r[0])}</b><span>${esc(r[1])}</span></div>`;
const allBtn = (it, on) => `<div class="bt-more"${on ? "" : " hidden"}><button class="bt-all" data-all="${esc(it.key)}"${typeof it.count === "number" && it.count > (it.events || it.rows).length ? ' data-extra="1"' : ""}>All ${esc(it.count && typeof it.count === "number" ? Math.max(it.count, (it.events || it.rows).length) : (it.events || it.rows).length)} →</button></div>`;
function renderPart(it, role, box, o) {
  box = box || { w: 400, h: 200 }; o = o || {};
  const head = `<h2 class="bt-h">${ico(it.icon)}<span class="bt-t">${esc(it.title)}</span><span class="bt-sc">${it.cleared ? "" : esc(it.score)}</span></h2>`;
  if (role === "hero") {
    const h = heroOf(it), cover = o.cover || "medium";
    return `<div class="bt-hmain">${head}<h3 class="bt-hl">${esc(h.headline).replace(/\*(.+?)\*/g, "<i>$1</i>")}</h3>`
      + (cover !== "short" && h.side.length ? `<div class="bt-side">${h.side.map(s => `<div>${esc(s)}</div>`).join("")}</div>` : "")
      + (cover === "long" && h.dek ? `<p class="bt-dek">${esc(h.dek)}</p>` : "") + `</div>`
      + (h.acts.length ? `<div class="bt-acts">${h.acts.map((a, i) => `<button class="bt-btn${i ? " ghost" : ""}" data-act="${esc(a.act)}" data-arg="${esc(a.arg ?? "")}">${esc(a.label)}</button>`).join("")}</div>` : "");
  }
  if (it.cleared) return `${head}<div class="bt-clear">✓ All clear</div>`;
  if (role === "head") {
    const sp = it.spot ? `<div class="bt-spot"><b>${esc(it.spot[0])}</b><span>${esc(it.spot[1])}</span></div>` : "";
    return `${head}<div class="bt-hrow"><span class="bt-big">${esc(it.count)}</span><p class="bt-desc">${esc(it.summary)}</p>${box.w > 520 ? sp : ""}</div>${box.w <= 520 ? sp : ""}`;
  }
  if (role === "list" && it.events) {
    const fit = Math.max(1, Math.floor((box.h - 8) / 50)), show = it.events.length > fit ? fit - 1 : fit;
    return `<div class="bt-tl">${it.events.map((e, i) => `<div class="bt-ev${i ? "" : " now"}"${i < show ? "" : " hidden"}><span>${esc(e[0])}</span><div><b>${esc(e[1])}</b>${e[2] ? `<small>${esc(e[2])}</small>` : ""}</div></div>`).join("")}</div>`
      + allBtn(it, it.events.length > show || it.count > it.events.length);
  }
  if (role === "list") {
    const fit = Math.max(1, Math.floor((box.h - 14) / 31)), show = it.rows.length > fit ? fit - 1 : fit;
    return it.rows.slice(0, 30).map((r, i) => rowHtml(r, i >= show)).join("") + allBtn(it, it.rows.length > show);
  }
  if (role === "map") return `${head}<div class="bt-map"><canvas class="bt-mini" data-mini></canvas>${it.legend ? `<div class="bt-legend">${it.legend.map((l, i) => `<div><i style="background:var(${LEGEND[i % LEGEND.length]})"></i><em>${esc(l[0])}</em><span>${esc(l[1])}</span></div>`).join("")}<small>${esc(it.why)}</small></div>` : ""}</div>`;
  if (it.days) return `${head}<div class="bt-big">${esc(it.count)}</div><div class="bt-dots">${it.days.map(d => `<i class="${d ? "on" : ""}"></i>`).join("")}</div><div class="bt-one">${esc(it.summary)}</div>`;
  if (box.h > 150 && it.rows.length) {
    const fit = Math.max(1, Math.floor((box.h - 110) / 27));
    return `${head}<div class="bt-brow"><span class="bt-big">${esc(it.count)}</span><span class="bt-one">${esc(it.summary || it.why)}</span></div>${it.rows.slice(0, fit).map(rowHtml).join("")}`;
  }
  return `${head}<div class="bt-big">${esc(it.count)}</div><div class="bt-one">${esc(it.summary || it.why)}</div>`;
}
// A whole block's inner HTML: the outline SVG plus each part placed in pixels. g = {cw, rh, gap, radius, cover}.
function renderBlock(it, b, g) {
  const gap = g.gap ?? GAP, rh = g.rh ?? ROW, o = outline(b.cells, g.cw, rh, gap, g.radius), X = x => x * (g.cw + gap), Y = y => y * (rh + gap);
  const html = `<svg class="bt-outline" width="${o.w}" height="${o.h}"><path d="${o.d}"/></svg>` + b.parts.map(q => {
    const w = X(q.c) - gap, h = Y(q.r) - gap;
    return `<div class="bt-part r-${q.role}" style="left:${X(q.x - o.x0)}px;top:${Y(q.y - o.y0)}px;width:${w}px;height:${h}px">${renderPart(it, q.role, { w, h }, g)}</div>`;
  }).join("");
  const xs = b.cells.map(c => c[0]), ys = b.cells.map(c => c[1]);
  return { html, x0: o.x0, y0: o.y0, c: Math.max(...xs) - o.x0 + 1, r: Math.max(...ys) - o.y0 + 1 };
}

// fit: in the page, show as many whole rows as each part really holds (text wraps differently from the estimate),
// then "All N →" only when some are left out. Nothing ever spills out of its box.
function fit(root) {
  // a head keeps only the height its text uses; the list right under it moves up and takes the rest (no empty band)
  for (const h of root.querySelectorAll(".bt-part.r-head")) {
    const l = h.parentNode.querySelector(".bt-part.r-list"), px = k => parseFloat(h.style[k]) || 0, lx = k => parseFloat(l?.style[k]) || 0;
    if (!l || lx("left") < px("left") || lx("left") + lx("width") > px("left") + px("width") + 1) continue;
    const used = Math.max(...[...h.children].map(c => c.offsetTop + c.offsetHeight)) + 16, d = Math.floor(px("height") - used);
    if (d > 4) { h.style.height = px("height") - d + "px"; l.style.top = lx("top") - d + "px"; l.style.height = lx("height") + d + "px"; }
  }
  // the cover's headline steps down a size until it fits (display fonts differ a lot in width between themes)
  for (const p of root.querySelectorAll(".bt-part.r-hero")) {
    const hl = p.querySelector(".bt-hl"); if (!hl) continue;
    hl.style.fontSize = "";
    for (let fs = parseFloat(getComputedStyle(hl).fontSize); fs > 20 && p.scrollHeight > p.clientHeight + 1; fs -= 2) hl.style.fontSize = fs - 2 + "px";
  }
  for (const p of root.querySelectorAll(".bt-part")) {
    const rows = [...p.querySelectorAll(".bt-row, .bt-ev")], more = p.querySelector(".bt-more");
    if (!rows.length) continue;
    const over = () => p.scrollHeight > p.clientHeight + 1;
    rows.forEach(r => r.hidden = false); if (more) more.hidden = true;
    let n = rows.length;
    if (more && !over() && !p.querySelector(".bt-all").dataset.extra) continue;
    if (more) more.hidden = false;
    while (n > 1 && over()) rows[--n].hidden = true;
    if (more && n === rows.length && !p.querySelector(".bt-all").dataset.extra) more.hidden = true;
  }
}
// strip: the top of an opened tile — count, summary and the one thing that matters, then the full section below it
const strip = it => !it || it.hero ? "" : `<span class="bt-big">${esc(it.cleared ? "✓" : it.count)}</span><p class="bt-desc">${esc(it.cleared ? "All clear." : it.summary)}</p>`
  + (it.spot ? `<div class="bt-spot"><b>${esc(it.spot[0])}</b><span>${esc(it.spot[1])}</span></div>` : "");
// nextUp: the soonest thing still ahead, from Up next (now.upcoming) and dated Notes to self. Its time comes from u.time or a
// leading "18:30 " in the title; an untimed one stays ahead until its day ends. to = what the countdown counts to (null = today).
function nextUp(S, now) {
  S = S || {}; now = +(now || new Date());
  const pad = n => String(n).padStart(2, "0"), at = (d, t) => +new Date(`${d}T${t}`);  // no offset: local time
  const all = [...(S.now && S.now.upcoming || []).map(u => ({ ...u, key: "next" })),
    ...(S.nudges || []).filter(n => n.status === "open" && n.due).map(n => ({ date: n.due, title: n.title, key: "nudges" }))];
  return all.filter(u => ISO.test(u.date || "")).map(u => {
    const d = u.date.slice(0, 10), m = String(u.time || u.title || "").match(/^(\d{1,2}):(\d{2})\b\s*/), t = m && `${pad(m[1])}:${m[2]}`;
    const title = m && !u.time ? u.title.slice(m[0].length) : u.title || "";
    return { key: u.key, title, date: d, time: t || "", detail: u.detail || "", at: at(d, t || "23:59:59"), to: t ? at(d, t) : at(d, "00:00") > now ? at(d, "00:00") : null };
  }).filter(u => u.at > now).sort((a, b) => a.at - b.at)[0] || null;
}
// countdown(ms) -> "22h 41m 58s" (days only when there are some; minutes and seconds keep two digits after a bigger unit)
function countdown(ms) {
  const s = Math.max(0, Math.floor(ms / 1000)), d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60), p = n => String(n).padStart(2, "0");
  return d ? `${d}d ${h}h ${p(m)}m ${p(s % 60)}s` : h ? `${h}h ${p(m)}m ${p(s % 60)}s` : `${m}m ${p(s % 60)}s`;
}
const colsFor = w => w >= 1500 ? 12 : w >= 1100 ? 10 : w >= 800 ? 8 : w >= 560 ? 6 : 4;
const API = { colsFor, nextUp, countdown, fit, strip, items, templates, solve, outline, renderPart, renderBlock, esc, ICONS, ROW, GAP };
if (typeof window !== "undefined") window.BrainTiles = API;
if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
