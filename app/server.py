#!/usr/bin/env python3
"""Brain: a local app over a folder of markdown notes.

Run: python3 app/server.py [--port 4747] [--notes DIR] [--no-open]
The notes folder defaults to the parent of the brain folder (e.g. ~/Notes/.brain -> ~/Notes);
--notes or $BRAIN_NOTES overrides it.
Stdlib only (Python 3.9+). Binds to 127.0.0.1. Every API call needs the per-run token that is
injected into the page, and the Host header must be local, so other websites can't read or write
the notes.
"""
import datetime
import glob
import http.server
import json
import os
import random
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.dirname(HERE)
if "--notes" in sys.argv:
    os.environ["BRAIN_NOTES"] = sys.argv[sys.argv.index("--notes") + 1]
NOTES = os.path.abspath(os.path.expanduser(os.environ.get("BRAIN_NOTES") or os.path.dirname(BRAIN)))
os.environ["BRAIN_NOTES"] = NOTES
sys.path.insert(0, BRAIN)
import build  # noqa: E402  (INDEX.md generator + frontmatter parser)
from agents import Agents  # noqa: E402  (headless agent per capture, when agents/ exists)
from routines import Routines  # noqa: E402  (Claude Code routines, cached in claude/routines.json)
from sync import Sync  # noqa: E402  (git pull/commit/push for the phone app, when phone/ exists)
import codex  # noqa: E402  (Codex adapter: brain block in ~/.codex/AGENTS.md)
import predictions  # noqa: E402  (how well Claude knows you: claude/predictions.md)
import stats  # noqa: E402  (usage stats from Claude Code transcripts)

TOKEN = secrets.token_urlsafe(24)
CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
LOCK = threading.Lock()
AGENTS = Agents(NOTES)
ROUTINES = Routines(NOTES)
HISTORY = threading.Lock()  # one past-runs read at a time


def routine_history():
    try:
        ROUTINES.history()
        if SYNC.enabled():
            with LOCK:
                SYNC.commit(["claude/routines.json", "tiles/routine-runs.md"], "brain: routine runs")
    finally:
        HISTORY.release()
SYNC = Sync(NOTES, on_pulled=AGENTS.drain_pending)
TOUCHED = set()  # notes files written since the last sync commit


# ---------------------------------------------------------------- helpers

def upcoming_items(now_body, t):
    """Dated lines under `## Upcoming` in now.md, from today on. Only that section: Done is dated too,
    and today's finished work isn't up next."""
    section = re.search(r"^## Upcoming\s*\n(.*?)(?=^## |\Z)", now_body, re.M | re.S)
    out = []
    for line in (section.group(1) if section else "").splitlines():
        m = re.match(r"^- (\d{4}-\d{2}-\d{2})(?: (\d{1,2}:\d{2}))? · ([^·]+?)(?: · (.+))?$", line.strip())
        if m and m.group(1) >= t:
            out.append({"date": m.group(1), "time": m.group(2), "title": m.group(3).strip(), "detail": m.group(4)})
    return sorted(out, key=lambda u: (u["date"], u["time"] or "99"))  # soonest first; timed items before all-day ones

def today():
    return datetime.date.today().isoformat()


def read(rel):
    path = os.path.join(NOTES, rel)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(rel, text):
    path = os.path.join(NOTES, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    TOUCHED.add(rel)


def safe_rel(rel):
    """Only .md files inside ~/Notes, never inside dot-folders."""
    if not isinstance(rel, str) or not rel.endswith(".md"):
        return None
    full = os.path.realpath(os.path.join(NOTES, rel))
    if not full.startswith(os.path.realpath(NOTES) + os.sep):
        return None
    inner = os.path.relpath(full, os.path.realpath(NOTES))
    if any(part.startswith(".") for part in inner.split(os.sep)):
        return None
    return inner


def rebuild_index():
    try:
        docs = build.load_notes()
        known = [p for d in docs if d["kind"] == "project" for p in build.as_list(d["meta"].get("paths"))]
        with open(os.path.join(NOTES, "INDEX.md"), "w", encoding="utf-8") as f:
            f.write(build.build_index(docs, build.other_folders(known)))
        TOUCHED.add("INDEX.md")
        codex.sync()  # keep Codex's AGENTS.md brain block current (no-op without Codex)
    except Exception as e:  # the index is a convenience; never fail a save over it
        print("index rebuild failed:", e, file=sys.stderr)


# ------------------------------------------------ "## ID · title" + "- key: value" blocks
BLOCK = re.compile(r"^## ([A-Z]+-\d+) · (.+)$", re.M)


def parse_blocks(text):
    items = []
    heads = list(BLOCK.finditer(text))
    for i, m in enumerate(heads):
        body = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        fields = {}
        for line in body.splitlines():
            fm = re.match(r"^- ([a-z_]+):[ \t]*(.*?)(?:\s{2,}#.*)?\s*$", line)
            if fm:
                fields[fm.group(1)] = fm.group(2)
        items.append({"id": m.group(1), "title": m.group(2).strip(), **fields})
    return items


def set_fields(text, item_id, updates):
    heads = list(BLOCK.finditer(text))
    for i, m in enumerate(heads):
        if m.group(1) != item_id:
            continue
        start, end = m.end(), heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[start:end]
        for key, val in updates.items():
            pat = re.compile(r"^- %s:[^\n]*$" % re.escape(key), re.M)
            line = "- %s: %s" % (key, val)
            if pat.search(body):
                body = pat.sub(lambda _: line, body, count=1)
            else:  # add the field after the block's last "- key:" line
                last = list(re.finditer(r"^- [a-z_]+:[^\n]*$", body, re.M))
                cut = last[-1].end() if last else 0
                body = body[:cut] + "\n" + line + body[cut:]
        return text[:start] + body + text[end:]
    raise KeyError(item_id)


# ---------------------------------------------------------------- sessions → resume commands
def session_index():
    """short id → (full uuid, cwd recorded in the transcript)."""
    out = {}
    for f in glob.glob(os.path.join(CLAUDE_PROJECTS, "*", "*.jsonl")):
        sid = os.path.basename(f)[:-6]
        out[sid[:8]] = {"uuid": sid, "cwd": None, "file": f}
    return out


def transcript_cwd(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for _ in range(40):
                line = f.readline()
                if not line:
                    break
                m = re.search(r'"cwd":"([^"]+)"', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def resume_for(short_ids, fallback_cwd, idx):
    for short in reversed(short_ids):  # merged notes list the earliest first; resume the latest
        hit = idx.get(short)
        if hit:
            cwd = transcript_cwd(hit["file"]) or os.path.expanduser(fallback_cwd or "~")
            return {"uuid": hit["uuid"], "cwd": cwd,
                    "command": ('cd /d "%s" && claude --resume %s' if os.name == "nt" else 'cd "%s" && claude --resume %s') % (cwd, hit["uuid"])}
    return None


# ---------------------------------------------------------------- state
def streak(dates):
    days = set(dates)
    n, d = 0, datetime.date.today()
    if d.isoformat() not in days:
        d -= datetime.timedelta(days=1)
    while d.isoformat() in days:
        n += 1
        d -= datetime.timedelta(days=1)
    return n


REFRESHED = {}  # tile path -> last time its refresh command ran
# Tiles arrive by git pull, so anyone who can push to the notes repo (the phone's key can) could put a command in one.
# Only commands listed in this Mac-only file run, one per line, exactly as written in the tile; it is never synced.
REFRESH_ALLOW = os.path.expanduser("~/.config/brain/refresh-allow")


def refresh_allowed(cmd):
    try:
        with open(REFRESH_ALLOW, encoding="utf-8") as f:
            return cmd in {l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")}
    except OSError:
        return False


def custom_tiles():
    """tiles/*.md: one tile each. Frontmatter title/icon/refresh; each "- a · b" line is a row.
    refresh is a shell command (cwd = notes) that rewrites the file; it runs at most every 5 min, and only if it's
    in REFRESH_ALLOW."""
    out = []
    for path in sorted(glob.glob(os.path.join(NOTES, "tiles", "*.md"))):
        rel = "tiles/" + os.path.basename(path)  # "/" on Windows too: the page uses it as a note path
        meta, _ = build.parse_frontmatter(read(rel))
        cmd, note = meta.get("refresh"), ""
        if cmd and not refresh_allowed(cmd):
            note = "Not refreshing: add its command to ~/.config/brain/refresh-allow on this Mac."
        elif cmd and datetime.datetime.now().timestamp() - REFRESHED.get(rel, 0) > 300:
            REFRESHED[rel] = datetime.datetime.now().timestamp()
            try:
                subprocess.run(cmd, shell=True, cwd=NOTES, timeout=15, capture_output=True)
            except subprocess.TimeoutExpired:
                pass
        meta, body = build.parse_frontmatter(read(rel))
        rows = [[p.strip() for p in (l[2:].split(" · ", 1) + [""])[:2]] for l in body.splitlines() if l.startswith("- ")]
        out.append({"slug": os.path.basename(path)[:-3], "path": rel, "title": meta.get("title") or os.path.basename(path)[:-3],
                    "icon": meta.get("icon", "doc"), "summary": note or meta.get("summary", ""), "count": meta.get("count", ""), "rows": rows})
    return out


def state():
    docs = build.load_notes()
    idx = session_index()
    by_path = {d["path"]: d for d in docs}

    def slim(d):
        return {"path": d["path"], "title": d["title"], "meta": d["meta"], "tldr": d["tldr"],
                "date": d["date"], "open": d["open"][:8]}

    sessions = sorted((d for d in docs if d["kind"] == "session"), key=lambda d: d["path"], reverse=True)
    session_out = []
    latest_resume = {}
    for s in sessions:
        item = slim(s)
        item["resume"] = resume_for(build.as_list(s["meta"].get("session")), s["meta"].get("cwd"), idx)
        session_out.append(item)
        for p in build.as_list(s["meta"].get("projects")):
            if item["resume"] and p not in latest_resume:
                latest_resume[p] = item["resume"]

    projects = []
    for d in docs:
        if d["kind"] != "project":
            continue
        slug = os.path.basename(d["path"])[:-3]
        item = slim(d)
        item["slug"] = slug
        item["resume"] = latest_resume.get(slug)
        item["sessions"] = sum(slug in build.as_list(s["meta"].get("projects")) for s in sessions)
        item["folders"] = [os.path.expanduser(p) for p in build.as_list(d["meta"].get("paths"))]
        item["archived"] = bool(d["meta"].get("archived"))
        projects.append(item)
    projects = build.sort_projects(projects)

    people = [slim(d) for d in docs if d["path"].startswith("people/")]
    people.sort(key=lambda p: (not p["meta"].get("follow_up"), p["title"].lower()))

    nudges = parse_blocks(read("nudges.md"))
    t = today()
    for n in nudges:  # a snooze that has run out is open again
        if n.get("status") == "snoozed" and n.get("snooze_until") and n["snooze_until"] <= t:
            n["status"] = "open"
    habits = habit_freshness(parse_blocks(read("claude/habits.md")), sessions, t)

    now_meta, now_body = build.parse_frontmatter(read("now.md"))
    upcoming = upcoming_items(now_body, t)

    me_meta, me_body = build.parse_frontmatter(read("me.md"))
    inbox = [l[2:] for l in read("inbox.md").splitlines() if l.startswith("- ")]
    ideas = idea_sections(read("ideas.md"))

    activity = [s["meta"].get("date", "") for s in sessions] + [n.get("done_on", "") for n in nudges]
    activity += [i[:10] for i in inbox]
    iso = datetime.date.today().isocalendar()

    return {
        "today": t, "issue": iso[1], "streak": streak([a for a in activity if a]),
        "now": {**now_meta, "upcoming": upcoming[:8]},
        "me": {"meta": me_meta, "exists": bool(me_body.strip()), "path": "me.md",
               "snapshot": re.findall(r"^- (.+)$", me_body.split("## Goals")[0], re.M)[:5]},
        "nudges": nudges, "habits": habits, "projects": projects, "people": people,
        "sessions": session_out[:60], "inbox": inbox, "ideas": sorted(ideas["open"][::-1], key=idea_rank), "ideas_closed": {"done": len(ideas["done"]), "dismissed": len(ideas["dismissed"])},
        "notes": [slim(d) for d in docs if d["kind"] == "note" and not d["path"].startswith("people/")
                  and d["path"] not in ("me.md", "now.md", "nudges.md", "ideas.md", "inbox.md", "claude/habits.md")],
        "internships": internships(read("internships/tracker.md")),
        "tiles": custom_tiles(),
        "decisions": build.decisions_due(NOTES, t),
        "agents": AGENTS.recent(),
        "routines": ROUTINES.load(),
        "theme": saved_theme(),
        "layout": saved_layout(),
        "graph": graph_summary(),
        "predictions": predictions.stats(predictions.parse(read("claude/predictions.md"))),
        "has": {k: k in by_path for k in ("me.md", "now.md")},
    }


# ---------------------------------------------------------------- internships: every table row in internships/tracker.md
def internship_group(status):
    s = status.lower()
    if s.startswith(("applied", "emailed")):  # a cold email is an application waiting on a reply
        return "applied"
    if s.startswith(("out", "dropped", "skipped", "not a fit")):
        return "out"
    if s.startswith(("to apply", "prep")):
        return "apply"
    return "check"


def internships(text):
    """Rows from every markdown table that has a company column. Status decides the group by its first words."""
    rows, head = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            head = None
            continue
        cells = [c.strip().replace("**", "") for c in line.strip().strip("|").split("|")]
        if head is None:
            head = [c.lower() for c in cells]
            continue
        if not line.strip("|-: "):
            continue
        r = dict(zip(head, cells))
        if not r.get("company"):
            continue
        link = r.get("link", "")
        rows.append({"company": r["company"], "role": r.get("role", ""), "term": r.get("term") or r.get("where", ""),
                     "deadline": r.get("deadline", "").lstrip("~"), "link": link if link.startswith("http") else "",
                     "status": r.get("status", ""), "group": internship_group(r.get("status", ""))})
    return rows


# ---------------------------------------------------------------- ideas: open list, then "## Done" / "## Dismissed"
IDEA_SECTIONS = {"done": "## Done", "dismissed": "## Dismissed"}


VERDICTS = {"try": 0, "maybe": 1, "skip": 2}


HABIT_TRACKING_SINCE = "2026-10-01"  # session notes list the habits used (`habits:`) from here on (backfilled 2026-10-17)


def habit_freshness(habits, sessions, t):
    """Each habit's last use (newest session note whose `habits:` lists it, or a manual `- used:` date) and how many
    days it has sat idle since. Idle counts from tracking day at the earliest, so old habits don't all start stale.
    Stalest first, so the ones to clean up are on top."""
    last = {}
    for s in sessions:
        ids = s["meta"].get("habits") or []
        for hid in ids if isinstance(ids, list) else re.findall(r"H-\d+", str(ids)):
            last[hid] = max(last.get(hid, ""), str(s["meta"].get("date") or s["date"]))
    day = datetime.date.fromisoformat
    for h in habits:
        used = max(last.get(h["id"], ""), h.get("used", ""))
        h["last_used"] = used or None
        start = max(used, h.get("since", ""), HABIT_TRACKING_SINCE)
        try:
            h["idle"] = max(0, (day(t) - day(start[:10])).days)
        except ValueError:
            h["idle"] = 0
    return sorted(habits, key=lambda h: -h["idle"])


HABIT_AREAS = ["studying and exams", "internship applications", "networking and outreach", "running his club",
               "sleep, health and breaks", "money and spending", "how Claude writes code for him", "his notes and memory",
               "email and messages", "planning his week", "side projects", "how Claude talks to him",
               "catching mistakes before they ship", "saving him time on repetitive chores"]  # one at random per idea, for variety


def habit_idea():
    """A fresh habit suggestion from Claude (Haiku, no tools), grounded in who Zac is, what's going on, and the
    habits he already has, so it doesn't repeat one. ~5s."""
    titles = [h["title"] for h in parse_blocks(read("claude/habits.md"))]
    _, me = build.parse_frontmatter(read("me.md"))
    _, now = build.parse_frontmatter(read("now.md"))
    prompt = ("You suggest habits for Claude, an AI assistant that works with this person every day through Claude Code."
              " A habit is a standing rule for how Claude behaves.\n\nAbout them:\n" + me[:2500] +
              "\n\nWhat's going on now:\n" + now[:2500] +
              "\n\nHabits Claude already has (don't repeat or rephrase any):\n- " + "\n- ".join(titles) +
              "\n\nSuggest ONE new, specific, useful habit about " + random.choice(HABIT_AREAS) + ", written as the person"
              " would ask for it, imperative, under 14 words. Reply with only the habit, no quotes.")
    out = subprocess.run([shutil.which("claude") or "claude", "-p", "--model", "haiku", "--setting-sources", "",
                          "--tools", ""], input=prompt, capture_output=True, text=True, timeout=60)
    idea = (out.stdout.strip().splitlines() or [""])[-1].strip().strip('"')
    if out.returncode or not idea:
        raise RuntimeError("Claude didn't answer")
    return {"idea": idea[:160]}


def idea_rank(line):
    """Open ideas sort try, maybe, untagged, skip; newest first inside each."""
    m = re.match(r"\d{4}-\d{2}-\d{2} · \[(\w+)\]", line)
    return VERDICTS.get(m.group(1), 1.5) if m else 1.5


def idea_sections(text):
    out, current = {"open": [], "done": [], "dismissed": []}, "open"
    for line in text.splitlines():
        heading = line.strip().lower()
        if heading.startswith("## "):
            current = "done" if heading == "## done" else "dismissed" if heading == "## dismissed" else current
        elif line.startswith("- "):
            out[current].append(line[2:])
    return out


def render_ideas(sections):
    text = "# Ideas\n" + "".join("- %s\n" % i for i in sections["open"])
    for key, heading in IDEA_SECTIONS.items():
        if sections[key]:
            text += "\n%s\n" % heading + "".join("- %s\n" % i for i in sections[key])
    return text


# ---------------------------------------------------------------- actions
def act_idea(body):
    action, line = body.get("action"), str(body.get("text") or "")
    sections = idea_sections(read("ideas.md"))
    if action in ("done", "dismissed"):
        if line not in sections["open"]:
            raise KeyError(line)
        sections["open"].remove(line)
        sections[action].append("%s (%s %s)" % (line, action, today()))
    elif action == "restore":
        for key in ("done", "dismissed"):
            match = next((i for i in sections[key] if i == line or i.startswith(line + " (")), None)
            if match:
                sections[key].remove(match)
                sections["open"].append(re.sub(r" \((done|dismissed) \d{4}-\d{2}-\d{2}\)$", "", match))
                break
        else:
            raise KeyError(line)
    else:
        raise ValueError("unknown action")
    write("ideas.md", render_ideas(sections))


def saved_theme():
    """The desktop's theme pick ("family/mode", e.g. "riso/auto"); the phone follows it unless set itself."""
    try:
        return json.loads(read("claude/theme.json") or "{}").get("theme")
    except ValueError:
        return None


def saved_layout():
    """Tile order he set by moving tiles; [] = by urgency. The Mac and the phone's Action both write the file, so a
    merge-conflicted or half-written one falls back to [] instead of failing every state() (and the phone's build)."""
    try:
        order = json.loads(read("claude/layout.json") or "{}").get("order")
        return order if isinstance(order, list) else []
    except (ValueError, AttributeError):
        return []


def act_theme(body):
    theme = body.get("theme")
    if not isinstance(theme, str) or not re.fullmatch(r"[a-z]+/[a-z]+", theme):
        raise ValueError("theme must look like family/mode")
    write("claude/theme.json", json.dumps({"theme": theme}) + "\n")


def act_layout(body):
    """The tile order he set by moving tiles (keys like "next" or "t:music"); [] goes back to ordering by score."""
    order = body.get("order")
    if not isinstance(order, list) or len(order) > 100 or not all(isinstance(k, str) and 0 < len(k) <= 80 for k in order):
        raise ValueError("order must be a list of tile keys")
    write("claude/layout.json", json.dumps({"order": order}) + "\n")


def act_project(body):
    rel = safe_rel(body.get("path"))
    if not rel or not rel.startswith("projects/"):
        raise PermissionError("path")
    text = read(rel)
    if not text.startswith("---\n"):
        raise ValueError("project page has no frontmatter")
    end = text.find("\n---", 4)
    head, rest = text[4:end], text[end:]
    head = re.sub(r"^archived:.*\n?", "", head, flags=re.M).rstrip("\n")
    if body.get("archived"):
        head += "\narchived: %s" % today()
    write(rel, "---\n" + head + rest)
    rebuild_index()


def act_habit_new(body):
    title = " ".join(str(body.get("title") or "").split())[:160]
    why = " ".join(str(body.get("why") or "").split())[:600]
    if not title:
        raise ValueError("empty")
    text = read("claude/habits.md") or "# Claude's habits\n"
    ids = [int(m) for m in re.findall(r"^## H-(\d+) ·", text, re.M)]
    block = ("\n## H-%03d · %s\n- status: proposed\n- why: %s\n- since: %s\n"
             "- source: brainstorm — typed in the app; Claude: talk it through with the user next session and refine it\n"
             % ((max(ids) if ids else 0) + 1, title, why or "(to discuss)", today()))
    write("claude/habits.md", text.rstrip("\n") + "\n" + block)
    AGENTS.submit("habit", title + (": " + why if why else ""))



def act_nudge(body):
    action, nid = body.get("action"), body.get("id")
    updates = {
        "done": {"status": "done", "done_on": today()},
        "no": {"status": "no"},
        "reopen": {"status": "open", "snooze_until": ""},
        "snooze": {"status": "snoozed", "snooze_until": (datetime.date.today() + datetime.timedelta(
            days=max(1, min(60, int(body.get("days") or 3))))).isoformat()},
    }.get(action)
    if not updates:
        raise ValueError("unknown action")
    write("nudges.md", set_fields(read("nudges.md"), nid, updates))


def act_habit(body):
    status = body.get("status")
    if status not in ("on", "off", "proposed"):
        raise ValueError("bad status")
    write("claude/habits.md", set_fields(read("claude/habits.md"), body.get("id"), {"status": status}))


def act_capture(body):
    kind = body.get("kind") if body.get("kind") in ("note", "idea", "todo", "person", "routine") else "note"
    text = " ".join(str(body.get("text") or "").split())[:2000]
    if not text:
        raise ValueError("empty")
    if kind != "routine":  # a routine request isn't a thought to file: the agent sets it up, and its report is the record
        current = read("inbox.md") or "# Inbox\n"
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        write("inbox.md", current.rstrip("\n") + "\n- %s · %s · %s\n" % (stamp, kind, text))
    AGENTS.submit(kind, text)


def file_get(query):
    rel = safe_rel(query.get("path", [""])[0])
    if not rel:
        raise PermissionError("path")
    full = os.path.join(NOTES, rel)
    exists = os.path.exists(full)
    return {"path": rel, "text": read(rel), "mtime": os.path.getmtime(full) if exists else None, "exists": exists}


def file_put(body):
    rel = safe_rel(body.get("path"))
    if not rel:
        raise PermissionError("path")
    full = os.path.join(NOTES, rel)
    if os.path.exists(full) and body.get("mtime") is not None and abs(os.path.getmtime(full) - float(body["mtime"])) > 0.001:
        return 409, {"error": "This file changed on disk since you opened it (Claude may have edited it). Reload to see the new version."}
    write(rel, str(body.get("text", "")))
    rebuild_index()
    return 200, {"ok": True, "mtime": os.path.getmtime(full)}


# ---------------------------------------------------------------- http
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "Brain/1"

    def log_message(self, fmt, *args):
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    def local_host(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def send(self, code, payload, ctype="application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def commit_touched(self, message):
        files = sorted(TOUCHED)
        if SYNC.commit(files, message) is not False:  # a refused commit keeps them for the next one
            TOUCHED.difference_update(files)

    def authed(self):
        return self.local_host() and secrets.compare_digest(self.headers.get("X-Brain-Token", ""), TOKEN)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ValueError("too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self.local_host():
            return self.send(403, {"error": "forbidden"})
        url = urllib.parse.urlparse(self.path)
        if url.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
                html = f.read().replace("__BRAIN_TOKEN__", TOKEN).replace('"__NOTES_ROOT__"', json.dumps(NOTES))  # json: Windows backslashes stay intact
            return self.send(200, html.encode(), "text/html; charset=utf-8")
        if url.path in ("/theme.css", "/theme.js", "/tiles.css", "/tiles.js"):  # shared with the phone app
            with open(os.path.join(HERE, url.path[1:]), "rb") as f:
                return self.send(200, f.read(), "text/css; charset=utf-8" if url.path.endswith("css") else "text/javascript; charset=utf-8")
        if not self.authed():
            return self.send(403, {"error": "forbidden"})
        try:
            if url.path == "/api/state":
                SYNC.pull()  # pick up phone changes; at most once a minute
                publish_graph_if_rebuilt()  # one stat() per poll; publishes only after a graphify rebuild
                return self.send(200, {**state(), "sync": {"on": SYNC.enabled(), "error": SYNC.error}})
            if url.path == "/api/file":
                return self.send(200, file_get(urllib.parse.parse_qs(url.query)))
            if url.path == "/api/stats":
                return self.send(200, stats.collect(CLAUDE_PROJECTS, NOTES))
            if url.path == "/api/habit-idea":
                return self.send(200, habit_idea())
            if url.path == "/api/graph":
                g = graph_get()
                return self.send(200, g) if g else self.send(404, {"error": "No graph yet. Run graphify on your notes."})
        except PermissionError:
            return self.send(403, {"error": "That path isn't a note."})
        except Exception as e:
            return self.send(500, {"error": str(e)})
        self.send(404, {"error": "not found"})

    def routines(self, body):
        action, rid = body.get("action"), str(body.get("id") or "")
        try:
            if action == "refresh":
                snap = ROUTINES.refresh(force=not body.get("ifStale"))
            elif action == "suggest":
                snap = ROUTINES.suggest()
            else:
                snap = ROUTINES.act(rid, action)
        except KeyError:
            return self.send(404, {"error": "That routine isn't in the list any more. Refreshing."})
        except ValueError as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # always answer: the tile shows the message
            return self.send(500, {"error": str(e)})
        if SYNC.enabled() and snap:
            with LOCK:
                SYNC.commit(["claude/routines.json"], "brain: routines")
        if action == "refresh" and ROUTINES.due_history() and HISTORY.acquire(blocking=False):
            threading.Thread(target=routine_history, daemon=True).start()  # reads run logs: minutes, so not in the reply
        return self.send(200, {"routines": snap})

    def do_POST(self):
        if not self.authed():
            return self.send(403, {"error": "forbidden"})
        routes = {"/api/nudge": act_nudge, "/api/habit": act_habit, "/api/capture": act_capture,
                  "/api/idea": act_idea, "/api/project": act_project, "/api/habit-new": act_habit_new, "/api/theme": act_theme, "/api/layout": act_layout}
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/routines":  # slow (a claude call), so outside LOCK
                return self.routines(self.body())
            with LOCK:
                if path == "/api/file":
                    code, out = file_put(self.body())
                    self.commit_touched("brain: edit note")
                    return self.send(code, out)
                if path not in routes:
                    return self.send(404, {"error": "not found"})
                routes[path](self.body())
                self.commit_touched("brain: " + path.rsplit("/", 1)[-1])
            return self.send(200, {"ok": True})
        except KeyError:
            return self.send(404, {"error": "No such item — the file may have changed. Reload."})
        except PermissionError:
            return self.send(403, {"error": "That path isn't a note."})
        except (ValueError, TypeError) as e:
            return self.send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001  a disk or git error still owes the page an answer, not a hung request
            return self.send(500, {"error": "%s: %s" % (type(e).__name__, e)})


def graph_get():
    """The graphify knowledge graph of the notes (graphify-out/graph.json), trimmed for drawing.
    Returns None when there isn't one, so the app just hides the Map tile.
    Without graphify-out/ (gitignored, so the phone's GitHub Action never has it) the copy the Mac published
    to phone/graph.json stands in, already trimmed."""
    path = os.path.join(NOTES, "graphify-out", "graph.json")
    if not os.path.exists(path):
        pub = os.path.join(NOTES, "phone", "graph.json")
        if not os.path.exists(pub):
            return None
        with open(pub, encoding="utf-8") as f:
            return json.load(f)
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    nodes = [{"id": n["id"], "label": n.get("label") or n["id"], "group": n.get("community"),
              "groupName": n.get("community_name") or "", "file": n.get("source_file") or ""}
             for n in g.get("nodes", [])]
    ids = {n["id"] for n in nodes}
    links = [[l["source"], l["target"]] for l in g.get("links", []) if l["source"] in ids and l["target"] in ids]
    return {"nodes": nodes, "links": links, "built": datetime.datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat()}


def graph_summary():
    """Map tile: node/link counts and the six biggest clusters as [name, count]; None without a graph."""
    g = graph_get()
    if not g:
        return None
    sizes, names = {}, {}
    for n in g["nodes"]:
        sizes[n["group"]] = sizes.get(n["group"], 0) + 1
        names.setdefault(n["group"], n["groupName"].split(" / ")[0] or f"Cluster {n['group']}")
    top = sorted(sizes, key=sizes.get, reverse=True)[:6]
    return {"nodes": len(g["nodes"]), "links": len(g["links"]), "clusters": [[names[k], sizes[k]] for k in top]}


def publish_graph():
    """Phone app: copy the trimmed Map into phone/graph.json (committed, since graphify-out/ isn't) when it changed."""
    if not SYNC.enabled():
        return
    g = graph_get()
    if not g:
        return
    text = json.dumps(g, ensure_ascii=False, separators=(",", ":"))
    if read("phone/graph.json") != text:
        write("phone/graph.json", text)
        SYNC.commit(["phone/graph.json"], "brain: publish the Map for the phone")
    TOUCHED.discard("phone/graph.json")


GRAPH_SEEN = [None]  # mtime of graphify-out/graph.json when last published


def publish_graph_if_rebuilt():
    """graphify can rebuild the Map while Brain runs; republish the phone's copy then, not only at startup."""
    try:
        m = os.path.getmtime(os.path.join(NOTES, "graphify-out", "graph.json"))
    except OSError:
        return
    if m != GRAPH_SEEN[0]:
        GRAPH_SEEN[0] = m
        publish_graph()


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 4747
    try:
        httpd = Server(("127.0.0.1", port), Handler)
    except OSError:
        print("Brain is already running on http://127.0.0.1:%d (or the port is taken)." % port)
        if "--no-open" not in sys.argv:
            print("Restart it with: brain restart")
        sys.exit(1)
    url = "http://127.0.0.1:%d/" % port
    print("Brain running at %s  (Ctrl+C to stop)" % url)
    SYNC.pull(gap=0)  # start from GitHub's latest: whatever the phone did while the Mac was off
    rebuild_index()
    TOUCHED.clear()  # the startup index rebuild isn't worth a commit on its own
    publish_graph_if_rebuilt()
    AGENTS.recover()
    if "--no-open" not in sys.argv:
        threading.Timer(0.4, lambda: subprocess.run(["open", url]) if sys.platform == "darwin" else webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBrain stopped.")


if __name__ == "__main__":
    main()
