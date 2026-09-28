"""Headless Claude Code agents for things added in Brain (spec: docs/specs/2026-09-27-headless-agents.md).

Off unless the notes folder has an agents/ folder. One job at a time. Each job is a markdown file in
agents/ that is rewritten as it moves queued -> running -> done/failed, so its state survives restarts.
"""
import datetime
import json
import os
import queue
import re
import shutil
import subprocess
import threading

TIMEOUT = 20 * 60
# The whole permission boundary: --setting-sources project + dontAsk means nothing outside this list
# runs, including allow rules from the user's own settings. Outward actions are drafts only.
ALLOWED = [
    "Read", "Glob", "Grep", "Edit", "Write", "WebSearch", "WebFetch",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(grep:*)", "Bash(git status:*)", "Bash(git log:*)", "Bash(git diff:*)",
    "mcp__claude_ai_Gmail__search_threads", "mcp__claude_ai_Gmail__get_thread",
    "mcp__claude_ai_Gmail__get_message", "mcp__claude_ai_Gmail__create_draft",
    "mcp__claude_ai_Google_Calendar__list_events", "mcp__claude_ai_Google_Calendar__search_events",
    "mcp__claude_ai_Google_Calendar__create_event",
]
PROMPT = (
    "Zac just added this in Brain ({kind}): {text}\n\n"
    "Read ~/Notes/INDEX.md and the relevant project page first. If it's only a thought to keep, file it "
    "where it belongs in ~/Notes and stop. If it's a task, do it. Anything that would leave this machine "
    "(email, texts, git push, a live site) becomes a draft (a Gmail draft, or text in your report), never "
    "an action. Don't git commit. End with a report of at most 3 lines: what you did, and any files "
    "changed or drafts made."
)


def claude_command(notes):
    # which(): on Windows an npm install is claude.cmd, which a bare "claude" wouldn't find.
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--add-dir", os.path.expanduser("~/Projects"), "--allowedTools", *ALLOWED, "-p"]


def codex_command(notes):
    # Codex's sandbox is the boundary here: it can write the notes folder and ~/Projects, nothing else, and it has
    # no network by default, so outward actions can only come back as text in the report.
    return [shutil.which("codex") or "codex", "exec", "--cd", notes, "--sandbox", "workspace-write",
            "--add-dir", os.path.expanduser("~/Projects"), "--skip-git-repo-check", "--ask-for-approval", "never"]


def default_command(notes):
    """BRAIN_AGENT=codex runs agents through Codex; anything else (the default) uses Claude Code."""
    return codex_command(notes) if os.environ.get("BRAIN_AGENT", "").lower() == "codex" else claude_command(notes)


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


class Agents:
    def __init__(self, notes, command=None, timeout=TIMEOUT):
        self.notes = notes
        self.dir = os.path.join(notes, "agents")
        self.command = command or default_command(notes)
        self.timeout = timeout
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        self.worker = None

    def enabled(self):
        return os.path.isdir(self.dir)

    # ------------------------------------------------------------ files
    def _write(self, path, meta, text, report=""):
        head = "".join("%s: %s\n" % (k, v) for k, v in meta.items())
        body = "---\n%s---\n\n## Input\n%s\n" % (head, text)
        if report:
            body += "\n## Report\n%s\n" % report
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)

    def _read(self, path):
        with open(path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        m = re.match(r"---\n(.*?)\n---\n", raw, re.S)
        meta = dict(re.findall(r"^(\w+): (.*)$", m.group(1), re.M)) if m else {}
        text = re.search(r"## Input\n(.*?)(?:\n## Report\n|\Z)", raw, re.S)
        report = re.search(r"## Report\n(.*)\Z", raw, re.S)
        return meta, (text.group(1).strip() if text else ""), (report.group(1).strip() if report else "")

    def _files(self):
        return sorted((os.path.join(self.dir, f) for f in os.listdir(self.dir) if f.endswith(".md")), reverse=True)

    # ------------------------------------------------------------ api
    def recover(self):
        """Runs left queued/running by a previous Brain can never finish: mark them failed."""
        if not self.enabled():
            return
        for path in self._files():
            meta, text, report = self._read(path)
            if meta.get("status") in ("queued", "running"):
                meta.update(status="failed", finished=now())
                self._write(path, meta, text, report or "Brain restarted before this finished.")

    def submit(self, kind, text):
        if not self.enabled() or not text.strip():
            return None
        if os.environ.get("BRAIN_AGENTS") == "pending":
            return self._park(kind, text)
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "item"
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
        path = os.path.join(self.dir, "%s-%s.md" % (stamp, slug))
        self._write(path, {"status": "queued", "type": kind, "queued": now()}, text)
        self.jobs.put((path, kind, text))
        with self.lock:
            if not self.worker or not self.worker.is_alive():
                self.worker = threading.Thread(target=self._work, daemon=True)
                self.worker.start()
        return path

    # ------------------------------------------------------------ phone captures
    # Captures applied on GitHub (no claude there) are parked in agents/pending/; the Mac runs them
    # after its next pull.
    def _park(self, kind, text):
        pending = os.path.join(self.dir, "pending")
        os.makedirs(pending, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")
        path = os.path.join(pending, stamp + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"kind": kind, "text": text}, f)
        return path

    def drain_pending(self):
        """Start an agent for each parked capture. Returns how many it started."""
        pending = os.path.join(self.dir, "pending")
        if not self.enabled() or not os.path.isdir(pending):
            return 0
        n = 0
        for name in sorted(os.listdir(pending)):
            path = os.path.join(pending, name)
            if not name.endswith(".json"):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    job = json.load(f)
                os.remove(path)
            except (OSError, ValueError):
                continue
            if self.submit(job.get("kind", "note"), str(job.get("text", ""))):
                n += 1
        return n

    def recent(self, n=10):
        if not self.enabled():
            return None
        out = []
        for path in self._files()[:n]:
            meta, text, report = self._read(path)
            out.append({"file": "agents/" + os.path.basename(path), "status": meta.get("status", "failed"),
                        "type": meta.get("type", ""), "queued": meta.get("queued", ""),
                        "finished": meta.get("finished", ""), "text": text, "report": report})
        return out

    # ------------------------------------------------------------ worker
    def _work(self):
        while True:
            try:
                job = self.jobs.get(timeout=1)
            except queue.Empty:
                return  # idle: the next submit starts a fresh worker
            self.run(*job)

    def run(self, path, kind, text):
        meta = {"status": "running", "type": kind, "queued": self._read(path)[0].get("queued", now()), "started": now()}
        self._write(path, meta, text)
        try:
            p = subprocess.run([*self.command, PROMPT.format(kind=kind, text=text)], cwd=self.notes,
                               capture_output=True, text=True, timeout=self.timeout, stdin=subprocess.DEVNULL)
            status = "done" if p.returncode == 0 else "failed"
            report = (p.stdout.strip() or p.stderr.strip() or "(no output)")
        except subprocess.TimeoutExpired:
            status, report = "failed", "Stopped after %d minutes." % (self.timeout // 60)
        except FileNotFoundError:
            status, report = "failed", "The claude command wasn't found."
        meta.update(status=status, finished=now())
        self._write(path, meta, text, report[:2000])
