// Brain home-screen widget for iOS, run by the free Scriptable app.
// Shows the next few Up next items and the open nudges from phone/state.json,
// the same file the phone app reads. Tapping it opens the phone app.
//
// Setup: paste this into a new Scriptable script named "Brain", run it once in the app
// (it asks for the notes repo and the same GitHub key the phone app uses, kept in the
// iOS Keychain), then add a Scriptable widget to the home screen and pick "Brain".
// Small shows the top item, medium/large show more.

const APP_URL = "https://zacfink.github.io/brain/mobile/";
const K_REPO = "brain.repo", K_TOKEN = "brain.token";

async function ask(title, placeholder, secure) {
  const a = new Alert();
  a.title = title;
  secure ? a.addSecureTextField(placeholder) : a.addTextField(placeholder);
  a.addAction("Save"); a.addCancelAction("Cancel");
  if (await a.present() === -1) return null;
  return a.textFieldValue(0).trim();
}

if (config.runsInApp && (!Keychain.contains(K_TOKEN) || args.queryParameters.reset)) {
  const repo = await ask("Notes repo", "zacfink/notes", false);
  const token = repo && await ask("GitHub key", "the phone app's key", true);
  if (repo && token) { Keychain.set(K_REPO, repo); Keychain.set(K_TOKEN, token); }
}

const fm = FileManager.local();
const cache = fm.joinPath(fm.cacheDirectory(), "brain-state.json");

async function loadState() {
  if (!Keychain.contains(K_TOKEN)) throw new Error("Open Scriptable and run Brain once to set it up.");
  const r = new Request(`https://api.github.com/repos/${Keychain.get(K_REPO)}/contents/phone/state.json`);
  r.headers = { Authorization: `Bearer ${Keychain.get(K_TOKEN)}`, Accept: "application/vnd.github.raw+json",
    "X-GitHub-Api-Version": "2022-11-28" };
  try {
    const S = await r.loadJSON();
    if (r.response.statusCode !== 200) throw new Error(`GitHub said ${r.response.statusCode}.`);
    fm.writeString(cache, JSON.stringify(S));
    return S;
  } catch (e) {
    if (fm.fileExists(cache)) return JSON.parse(fm.readString(cache)); // offline: last good copy
    throw e;
  }
}

const today = () => new Date().toLocaleDateString("en-CA");
const daysFrom = d => Math.round((new Date(d + "T00:00") - new Date(today() + "T00:00")) / 864e5);
const when = d => { const n = daysFrom(d); return n === 0 ? "Today" : n === 1 ? "Tmrw" : n < 7 ? `${n}d` : d.slice(5); };

const ink = Color.dynamic(new Color("#1c1c1e"), new Color("#f2f2f7"));
const dim = Color.dynamic(new Color("#6e6e73"), new Color("#98989d"));
const accent = Color.dynamic(new Color("#e8590c"), new Color("#ff922b"));

function line(w, text, font, color, lines = 1) {
  const t = w.addText(text); t.font = font; t.textColor = color; t.lineLimit = lines;
  return t;
}

async function build() {
  const w = new ListWidget();
  w.url = APP_URL;
  w.backgroundColor = Color.dynamic(new Color("#ffffff"), new Color("#1c1c1e"));
  w.setPadding(12, 14, 12, 14);
  w.refreshAfterDate = new Date(Date.now() + 30 * 60e3);

  let S;
  try { S = await loadState(); }
  catch (e) { line(w, "Brain", Font.boldSystemFont(14), ink); line(w, e.message, Font.systemFont(12), dim, 4); return w; }

  const t = today(), fam = config.widgetFamily || "medium";
  const up = (S.upcoming || []).filter(u => u.date && u.date >= t).sort((a, b) => a.date.localeCompare(b.date));
  const nudges = (S.nudges || []).filter(x => x.status === "open" || (x.status === "snoozed" && x.snooze_until && x.snooze_until <= t));
  const max = fam === "small" ? 2 : fam === "large" ? 8 : 3;

  const head = w.addStack(); head.centerAlignContent();
  const h = head.addText("Brain"); h.font = Font.boldSystemFont(14); h.textColor = ink;
  head.addSpacer();
  if (nudges.length) { const n = head.addText(`${nudges.length} nudge${nudges.length > 1 ? "s" : ""}`); n.font = Font.mediumSystemFont(11); n.textColor = accent; }
  w.addSpacer(6);

  if (!up.length) line(w, "Nothing coming up.", Font.systemFont(12), dim);
  for (const u of up.slice(0, max)) {
    const row = w.addStack(); row.spacing = 6;
    const d = row.addText(when(u.date)); d.font = Font.semiboldMonospacedSystemFont(11); d.textColor = daysFrom(u.date) === 0 ? accent : dim;
    d.minimumScaleFactor = 0.8;
    const ti = row.addText(u.title); ti.font = Font.systemFont(12); ti.textColor = ink; ti.lineLimit = fam === "small" ? 2 : 1;
    w.addSpacer(3);
  }

  if (fam === "large" && nudges.length) {
    w.addSpacer(6);
    line(w, "NUDGES", Font.semiboldSystemFont(10), dim);
    for (const n of nudges.slice(0, 4)) { w.addSpacer(2); line(w, "• " + n.title, Font.systemFont(12), ink); }
  }
  w.addSpacer();
  return w;
}

const widget = await build();
if (config.runsInWidget) Script.setWidget(widget);
else await widget.presentMedium();
Script.complete();
