"""Headless Claude Code agents for things added in Brain (spec: docs/specs/2026-09-27-headless-agents.md).

Captures start agents only when the notes folder has an agents/ folder (without the SPAWN_ONLY marker).
An agent started on purpose from the Agents tile (spawn) always runs; the first one creates agents/ with
that marker, so it doesn't also opt every capture in. One job at a time. Each job is a markdown file in
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
import time

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
    "Alex just added this in Brain ({kind}): {text}\n\n"
    "Read INDEX.md in this notes folder and the relevant project page first. If it's only a thought to keep, "
    "file it where it belongs in this notes folder and stop. If it's a task, do it. Anything that would leave this machine "
    "(email, texts, git push, a live site) becomes a draft (a Gmail draft, or text in your report), never "
    "an action. Don't git commit. End with a report of at most 3 lines: what you did, and any files "
    "changed or drafts made."
)
# An agent Alex started on purpose: the text is the task itself.
TASK_PROMPT = (
    "Alex started you from Brain's Agents tile with this task: {text}\n\n"
    "You're in Alex's notes folder; read INDEX.md first if the notes are relevant. Do the task. Anything that would "
    "leave this machine (email, texts, git push, a live site) becomes a draft (a Gmail draft, or text in your "
    "report), never an action. Don't git commit. End with a short report: what you did or found, and any files "
    "changed or drafts made."
)
SPAWN_ONLY = ".spawn-only"  # in agents/: runs started from the tile only; captures don't start agents

# The weekly internship run, only ever started from the tile's button: the apply-internships skill, headless,
# in Alex's Chrome. Its own boundary: Chrome,
# reading the notes, and writing only under internships/. No shell, web, mail or calendar.
INTERNSHIPS = "internships"
INTERNSHIPS_TIMEOUT = 60 * 60
INTERNSHIPS_MODEL = "claude-sonnet-5-5"
INTERNSHIPS_ALLOWED = ["Read", "Glob", "Grep", "Edit(internships/**)", "Write(internships/**)", "mcp__claude-in-chrome"]
INTERNSHIPS_TEXT = "Weekly internship run (/apply-internships)"
INTERNSHIPS_SKILL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 ".claude", "skills", "apply-internships", "SKILL.md")
INTERNSHIPS_PROMPT = (
    "Brain started you headless for Alex's weekly internship run. Nobody is watching this session, so you can't "
    "ask questions: when something needs Alex, skip it and put it in the report. You're in Alex's notes folder, "
    "so the skill's `personal-notes/` paths are relative to here (personal-notes/internships/ is ./internships/). "
    "The skill's rules hold without exception: never click Submit, never type a signature, never create accounts "
    "or enter passwords. Don't git commit. Your final message is Alex's hand-off (step 6), kept short.\n\n"
    "The skill:\n\n{skill}"
)


def internships_command():
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--model", INTERNSHIPS_MODEL, "--chrome", "--allowedTools", *INTERNSHIPS_ALLOWED, "-p"]


def internships_prompt():
    with open(INTERNSHIPS_SKILL, encoding="utf-8") as f:
        skill = f.read()
    return INTERNSHIPS_PROMPT.format(skill=re.sub(r"\A---\n.*?\n---\n+", "", skill, flags=re.S))


def _projects():
    """["--add-dir", ~/Projects] when that folder exists; claude rejects a missing one."""
    path = os.path.expanduser("~/Projects")
    return ["--add-dir", path] if os.path.isdir(path) else []


# The prompt goes on stdin (see Agents.run), never as an argument: on Windows an npm install is a
# .cmd shim, and cmd.exe cuts a command-line argument off at its first newline. which() finds those shims.
def claude_command(notes):
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            *_projects(), "--allowedTools", *ALLOWED, "-p"]


def default_command(notes):
    return claude_command(notes)


def _write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    for attempt in range(20):  # Windows refuses the replace while a reader has the file open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


class Agents:
    def __init__(self, notes, command=None, timeout=TIMEOUT, routine_command=None, internships_command=None,
                 internships_timeout=INTERNSHIPS_TIMEOUT):
        self.notes = notes
        self.routine_command = routine_command  # None: routines.create_command(), built when a routine job runs
        self.internships_command = internships_command  # None: internships_command() when that job runs
        self.internships_timeout = internships_timeout
        self.dir = os.path.join(notes, "agents")
        self.command = command or default_command(notes)
        self.timeout = timeout
        self.jobs = queue.Queue()
        self.lock = threading.Lock()
        self.worker = None

    def enabled(self):
        """Whether captures start agents (spawn() always works)."""
        return os.path.isdir(self.dir) and not os.path.exists(os.path.join(self.dir, SPAWN_ONLY))

    # ------------------------------------------------------------ files
    def _write(self, path, meta, text, report=""):
        head = "".join("%s: %s\n" % (k, v) for k, v in meta.items())
        body = "---\n%s---\n\n## Input\n%s\n" % (head, text)
        if report:
            body += "\n## Report\n%s\n" % report
        _write_atomic(path, body)

    def _read(self, path):
        for attempt in range(20):  # Windows refuses the open while _write_atomic replaces the file
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    raw = f.read()
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)
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
        if not os.path.isdir(self.dir):
            return
        for path in self._files():
            meta, text, report = self._read(path)
            if meta.get("status") in ("queued", "running"):
                meta.update(status="failed", finished=now())
                self._write(path, meta, text, report or "Brain restarted before this finished.")

    def submit(self, kind, text):
        if not self.enabled() or not text.strip():
            return None
        return self._queue(kind, text)

    def spawn(self, text, kind="task"):
        """Start an agent on a task typed in Brain, whether or not captures start agents."""
        if not text.strip():
            return None
        if not os.path.isdir(self.dir):
            os.makedirs(self.dir)
            with open(os.path.join(self.dir, SPAWN_ONLY), "w", encoding="utf-8") as f:
                f.write("Agents here were started from Brain's Agents tile. Delete this file to have every capture start one too.\n")
        return self._queue(kind, text)

    # ------------------------------------------------------------ the internship run (button only)
    def internships(self):
        """Queue the internship run unless one is already queued or running. Never parked for later."""
        if os.environ.get("BRAIN_AGENTS") == "pending":
            return None
        if os.path.isdir(self.dir) and any(r["type"] == INTERNSHIPS and r["status"] in ("queued", "running")
                                           for r in self.recent(50)):
            return None
        return self.spawn(INTERNSHIPS_TEXT, INTERNSHIPS)

    def _queue(self, kind, text):
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
        if not os.path.isdir(pending):
            return 0
        n = 0
        for name in sorted(os.listdir(pending)):
            path = os.path.join(pending, name)
            if not name.endswith(".json"):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    job = json.load(f)
            except (OSError, ValueError):
                continue
            kind, text = job.get("kind", "note"), str(job.get("text", ""))
            if kind != "task" and not self.enabled():
                continue  # a capture parked before captures were switched off waits for them
            try:
                os.remove(path)
            except OSError:
                continue
            if kind == INTERNSHIPS:
                continue  # only the Mac's button starts it, with Alex there; never a parked job
            if self.spawn(text) if kind == "task" else self.submit(kind, text):
                n += 1
        return n

    def recent(self, n=10):
        if not os.path.isdir(self.dir):
            return []
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
        command, prompt = self.command, (TASK_PROMPT if kind == "task" else PROMPT).format(kind=kind, text=text)
        if kind == "routine":  # its own prompt, and RemoteTrigger is the only tool; other kinds never get it
            import routines  # here, not at the top: routines imports this module
            command = self.routine_command or routines.create_command()
            prompt = routines.CREATE_PROMPT.format(text=text)
        timeout = self.timeout
        if kind == INTERNSHIPS:  # its own model, Chrome, a narrower allowlist and an hour
            command, timeout = self.internships_command or internships_command(), self.internships_timeout
        try:
            if kind == INTERNSHIPS:
                prompt = internships_prompt()
        except OSError as e:
            meta.update(status="failed", finished=now())
            return self._write(path, meta, text, "Couldn't read the apply-internships skill: %s" % e)
        try:
            p = subprocess.run(command, input=prompt, cwd=self.notes,
                               capture_output=True, encoding="utf-8", errors="replace", timeout=timeout)
            status = "done" if p.returncode == 0 else "failed"
            report = (p.stdout.strip() or p.stderr.strip() or "(no output)")
        except subprocess.TimeoutExpired:
            status, report = "failed", "Stopped after %d minutes." % (timeout // 60)
        except FileNotFoundError:
            status, report = "failed", "The %s command wasn't found." % os.path.basename(command[0])
        meta.update(status=status, finished=now())
        self._write(path, meta, text, report[:2000])
