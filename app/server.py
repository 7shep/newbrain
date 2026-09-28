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
import re
import secrets
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
from sync import Sync  # noqa: E402  (git pull/commit/push for the phone app, when phone/ exists)
import codex  # noqa: E402  (Codex adapter: brain block in ~/.codex/AGENTS.md)
import predictions  # noqa: E402  (how well Claude knows you: claude/predictions.md)
import stats  # noqa: E402  (usage stats from Claude Code transcripts)

TOKEN = secrets.token_urlsafe(24)
CLAUDE_PROJECTS = os.path.expanduser("~/.claude/projects")
LOCK = threading.Lock()
AGENTS = Agents(NOTES)
SYNC = Sync(NOTES, on_pulled=AGENTS.drain_pending)
TOUCHED = set()  # notes files written since the last sync commit


# ---------------------------------------------------------------- helpers
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
    habits = parse_blocks(read("claude/habits.md"))

    now_meta, now_body = build.parse_frontmatter(read("now.md"))
    upcoming = []
    for line in now_body.splitlines():
        m = re.match(r"^- (\d{4}-\d{2}-\d{2})(?: (\d{1,2}:\d{2}))? · ([^·]+?)(?: · (.+))?$", line.strip())
        if m:
            upcoming.append({"date": m.group(1), "time": m.group(2), "title": m.group(3).strip(), "detail": m.group(4)})
    upcoming = [u for u in upcoming if u["date"] >= t]

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
        "sessions": session_out[:60], "inbox": inbox, "ideas": ideas["open"][::-1], "ideas_closed": {"done": len(ideas["done"]), "dismissed": len(ideas["dismissed"])},
        "notes": [slim(d) for d in docs if d["kind"] == "note" and not d["path"].startswith("people/")
                  and d["path"] not in ("me.md", "now.md", "nudges.md", "ideas.md", "inbox.md", "claude/habits.md")],
        "agents": AGENTS.recent(),
        "predictions": predictions.stats(predictions.parse(read("claude/predictions.md"))),
        "has": {k: k in by_path for k in ("me.md", "now.md")},
    }


# ---------------------------------------------------------------- ideas: open list, then "## Done" / "## Dismissed"
IDEA_SECTIONS = {"done": "## Done", "dismissed": "## Dismissed"}


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
def act_theme(body):
    """The desktop's light/dark choice, so the phone can follow it (phone.py puts it in state.json)."""
    if body.get("theme") not in ("light", "dark"):
        raise ValueError("theme must be light or dark")
    write("phone/theme", body["theme"])


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
    kind = body.get("kind") if body.get("kind") in ("note", "idea", "todo", "person") else "note"
    text = " ".join(str(body.get("text") or "").split())[:2000]
    if not text:
        raise ValueError("empty")
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
        TOUCHED.clear()
        SYNC.commit(files, message)

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
        if url.path == "/theme.css":  # shared with the phone app
            with open(os.path.join(HERE, "theme.css"), "rb") as f:
                return self.send(200, f.read(), "text/css; charset=utf-8")
        if not self.authed():
            return self.send(403, {"error": "forbidden"})
        try:
            if url.path == "/api/state":
                SYNC.pull()  # pick up phone changes; at most once a minute
                return self.send(200, {**state(), "sync": {"on": SYNC.enabled(), "error": SYNC.error}})
            if url.path == "/api/file":
                return self.send(200, file_get(urllib.parse.parse_qs(url.query)))
            if url.path == "/api/stats":
                return self.send(200, stats.collect(CLAUDE_PROJECTS, NOTES))
            if url.path == "/api/graph":
                g = graph_get()
                return self.send(200, g) if g else self.send(404, {"error": "No graph yet. Run graphify on your notes."})
        except PermissionError:
            return self.send(403, {"error": "That path isn't a note."})
        except Exception as e:
            return self.send(500, {"error": str(e)})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.authed():
            return self.send(403, {"error": "forbidden"})
        routes = {"/api/nudge": act_nudge, "/api/habit": act_habit, "/api/capture": act_capture,
                  "/api/idea": act_idea, "/api/project": act_project, "/api/habit-new": act_habit_new,
                  "/api/theme": act_theme}
        path = urllib.parse.urlparse(self.path).path
        try:
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


def graph_get():
    """The graphify knowledge graph of the notes (graphify-out/graph.json), trimmed for drawing.
    Returns None when there isn't one, so the app just hides the Map tile."""
    path = os.path.join(NOTES, "graphify-out", "graph.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    nodes = [{"id": n["id"], "label": n.get("label") or n["id"], "group": n.get("community"),
              "groupName": n.get("community_name") or "", "file": n.get("source_file") or ""}
             for n in g.get("nodes", [])]
    ids = {n["id"] for n in nodes}
    links = [[l["source"], l["target"]] for l in g.get("links", []) if l["source"] in ids and l["target"] in ids]
    return {"nodes": nodes, "links": links, "built": datetime.datetime.fromtimestamp(os.path.getmtime(path)).date().isoformat()}


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
    publish_graph()
    AGENTS.recover()
    if "--no-open" not in sys.argv:
        threading.Timer(0.4, lambda: subprocess.run(["open", url]) if sys.platform == "darwin" else webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBrain stopped.")


if __name__ == "__main__":
    main()
