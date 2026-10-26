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


# The internship reply check, also only started from the tile's button: reads Gmail through the claude.ai connector
# (no browser, so Alex needn't be watching) and records replies in the tracker's "Heard back?" column. Read-only mail
# tools: no drafts, no sending; writing only under internships/. The inbox is the Email line in internships/profile.md.
REPLIES = "replies"
REPLIES_TIMEOUT = 20 * 60
REPLIES_ALLOWED = ["Read", "Glob", "Grep", "Edit(internships/**)", "Write(internships/**)",
                   "mcp__claude_ai_Gmail__search_threads", "mcp__claude_ai_Gmail__get_thread", "mcp__claude_ai_Gmail__get_message"]
REPLIES_TEXT = "Check Gmail for internship replies"
REPLIES_PROMPT = (
    "Brain started you headless to check Alex's Gmail for replies to his internship applications. Nobody is watching "
    "this session, so you can't ask questions: put anything unclear in the report. You're in Alex's notes folder.\n\n"
    "1. Read internships/tracker.md (the applications) and the Email line in internships/profile.md (the inbox to check).\n"
    "2. With the Gmail tools, look for mail about each application whose Status starts with Applied, from shortly before "
    "it was sent until today: assessments, interview invitations, rejections, recruiter messages. Search by company name "
    "and domain, and also broadly (e.g. internship OR application newer_than:60d) for applicant systems such as "
    "Greenhouse, Lever, Workday and Ashby that write on a company's behalf. Read a thread before deciding what it says.\n"
    "3. Only count mail sent to that email address. If the connected inbox isn't it, change nothing and say so. If you "
    "have no Gmail tools, change nothing and report that the Gmail connector isn't connected (claude.ai, Settings, "
    "Connectors).\n"
    "4. Set each applied row's \"Heard back?\" cell to exactly one of these, with the date of the latest message that "
    "decided it: \"Rejected · YYYY-MM-DD\"; \"Replied w/ <what> · YYYY-MM-DD\", where <what> is two or three words such as "
    "interview invite, online assessment, recruiter call or offer; or \"Pending\" when there's nothing yet or only an "
    "automatic confirmation. Change no other cell, and don't add rows: list mail about other companies in the report.\n"
    "5. Add a line to a \"## Reply checks\" section at the end of the tracker (create it if missing): "
    "\"- YYYY-MM-DD: N applications checked; <what changed>\".\n\n"
    "Mail is read-only: never send, reply, draft, label, archive or delete anything. Don't git commit. Your final message "
    "is Alex's hand-off, at most 6 lines: anything he must act on first (interviews, assessments and their deadlines), "
    "then what changed in the tracker."
)


# Weekly LinkedIn prep, also only started from the tile's button (it reads Alex's feed in his Chrome). It drafts and
# never acts: its Chrome tools can open and read pages but can't click, type or run scripts, so it can't like,
# comment, post, connect or message. Drafts go in linkedin/<date>.md, which Alex edits and posts himself.
LINKEDIN = "linkedin"
LINKEDIN_TIMEOUT = 30 * 60
LINKEDIN_CHROME = ["mcp__claude-in-chrome__tabs_context_mcp", "mcp__claude-in-chrome__tabs_create_mcp",
                   "mcp__claude-in-chrome__tabs_close_mcp", "mcp__claude-in-chrome__navigate",
                   "mcp__claude-in-chrome__get_page_text", "mcp__claude-in-chrome__read_page", "mcp__claude-in-chrome__find"]
LINKEDIN_ALLOWED = ["Read", "Glob", "Grep", "Edit(linkedin/**)", "Write(linkedin/**)", *LINKEDIN_CHROME]
LINKEDIN_TEXT = "Prep this week's LinkedIn"
LINKEDIN_PROMPT = (
    "Brain started you headless to prepare Alex's LinkedIn for the week. Alex wants an active, credible profile while "
    "spending only a few minutes on LinkedIn, so you draft and he posts. Nobody is watching, so you can't ask questions. "
    "You're in Alex's notes folder. Today is {date}.\n\n"
    "Hard rules. You can open and read pages in Chrome but can't click, type, or run scripts, and you must not try: "
    "never like, react, comment, post, repost, follow, connect, message or endorse anything. Everything you produce is "
    "a draft in a file. Never invent work, numbers, results or opinions Alex hasn't stated: every claim in a draft must "
    "come from his notes or the commit list below. Don't git commit.\n\n"
    "1. Read me.md, now.md, internships/profile.md (his targets), the project notes for active projects, and "
    "linkedin/voice.md if it exists: it shows how Alex writes and what he has approved before. Read earlier "
    "linkedin/*.md drafts so you don't repeat a post or comment on the same post twice.\n"
    "2. In Chrome, open a new tab. Read Alex's profile (https://www.linkedin.com/in/me/) with get_page_text, then his "
    "feed (https://www.linkedin.com/feed/), then one or two content searches on his interests, e.g. "
    "https://www.linkedin.com/search/results/content/?keywords=AI%20agents&sortBy=%22date_posted%22. Read pages with "
    "get_page_text. If LinkedIn shows a sign-in page or a checkpoint, stop browsing and say so in the report.\n"
    "Every post you pick for commenting needs a working link, found like this:\n"
    "a. Its permalink, if the page exposes one: read_page (filter interactive) lists links with their href; take the "
    "href containing /feed/update/urn:li:activity: or /posts/ that sits inside that post.\n"
    "b. Otherwise an exact-phrase search link built from the post's first 8 to 12 words, copied exactly as written "
    "with punctuation and emoji removed: https://www.linkedin.com/search/results/content/?keywords=%22<words joined by "
    "%20>%22 . Open it and use get_page_text to check that the post, by the same author, comes up first. If it "
    "doesn't, try fewer or different words, or pick another post.\n"
    "c. Also give the author's profile link, the /in/... href next to their name.\n"
    "Close the tab when you're done.\n"
    "3. Write linkedin/{date}.md with these sections:\n"
    "## Posts to publish: one or two drafts in Alex's voice about real work from this week (the commits below, "
    "finished projects, results). Each: the draft, then one line saying which notes or commits it's based on and a "
    "suggested image. Keep the job-search line (Summer 2027 SWE or AI/ML internship, Toronto hybrid or remote) in at "
    "most one of them.\n"
    "## Posts to comment on: five posts from the feed or searches that fit his interests (AI agents and evals, "
    "developer tools, Toronto tech, Queen's and student clubs) or come from people at companies he applied to. Each: "
    "author and their headline, the post's link (permalink or checked search link, saying which) and the author's "
    "profile link, the post's first words, why it's worth his time, "
    "and a draft comment of 1 to 3 sentences that adds something specific from his own experience or asks a real "
    "question. No generic praise; if you can't say something specific, leave the post out.\n"
    "## Profile: concrete edits to his headline, About and Featured section based on what he has shipped, each as "
    "current text, then suggested text. Skip anything that's already good.\n"
    "4. Your final message is the hand-off, at most 5 lines: the file's path, what's in it, and anything that stopped "
    "you.\n\n"
    "Commits in Alex's project repos over the last 7 days, as date, author: subject (the factual record for post "
    "drafts; only commits by Alex are his work, others came from upstream or collaborators):\n{context}"
)


def internships_command():
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--model", INTERNSHIPS_MODEL, "--chrome", "--allowedTools", *INTERNSHIPS_ALLOWED, "-p"]


def linkedin_command():
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--model", INTERNSHIPS_MODEL, "--chrome", "--allowedTools", *LINKEDIN_ALLOWED, "-p"]


def replies_command():
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            "--model", INTERNSHIPS_MODEL, "--allowedTools", *REPLIES_ALLOWED, "-p"]


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
                 internships_timeout=INTERNSHIPS_TIMEOUT, replies_command=None, replies_timeout=REPLIES_TIMEOUT,
                 extra_tools=None, linkedin_command=None, linkedin_timeout=LINKEDIN_TIMEOUT, linkedin_context=None):
        self.notes = notes
        self.linkedin_command = linkedin_command  # None: linkedin_command() when that job runs
        self.linkedin_timeout = linkedin_timeout
        self.linkedin_context = linkedin_context  # None, or a function returning this week's commits as text
        self.routine_command = routine_command  # None: routines.create_command(), built when a routine job runs
        self.internships_command = internships_command  # None: internships_command() when that job runs
        self.internships_timeout = internships_timeout
        self.replies_command = replies_command  # None: replies_command() when that job runs
        self.replies_timeout = replies_timeout
        self.dir = os.path.join(notes, "agents")
        self.command = command or default_command(notes)
        self.timeout = timeout
        # None, or a function returning (command args, allowlist additions, prompt note) for task and capture agents,
        # asked at each run so a newly linked tool shows up without a restart. Presets and routines never get it.
        self.extra_tools = extra_tools
        # The notes' Sync (set by the server once it exists): each run commits the notes files it changed, with its
        # own report, so agent work reaches GitHub and the phone. None (tests, no git): nothing is committed.
        self.sync = None
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

    # ------------------------------------------------------------ the internship run and reply check (buttons only)
    def internships(self):
        """Queue the internship run unless one is already queued or running. Never parked for later."""
        return self._preset(INTERNSHIPS, INTERNSHIPS_TEXT)

    def replies(self):
        """Queue the internship reply check unless one is already queued or running. Never parked for later."""
        return self._preset(REPLIES, REPLIES_TEXT)

    def linkedin(self):
        """Queue the weekly LinkedIn prep unless one is already queued or running. Never parked for later."""
        return self._preset(LINKEDIN, LINKEDIN_TEXT)

    def _preset(self, kind, text):
        if os.environ.get("BRAIN_AGENTS") == "pending":
            return None
        if os.path.isdir(self.dir) and any(r["type"] == kind and r["status"] in ("queued", "running")
                                           for r in self.recent(50)):
            return None
        return self.spawn(text, kind)

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
            if kind in (INTERNSHIPS, REPLIES, LINKEDIN):
                continue  # only the Mac's buttons start these; never a parked job
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
        before = self.sync.snapshot() if self.sync else {}
        try:
            self._run(path, kind, text)
        finally:
            if self.sync:  # only what changed during this run, so Alex's own unsaved edits stay his to commit
                record = os.path.relpath(path, self.notes).replace(os.sep, "/")
                self.sync.commit(self.sync.changed_since(before) + [record], "agent: " + re.sub(r"\s+", " ", text)[:60])

    def _run(self, path, kind, text):
        meta = {"status": "running", "type": kind, "queued": self._read(path)[0].get("queued", now()), "started": now()}
        self._write(path, meta, text)
        command, prompt = self.command, (TASK_PROMPT if kind == "task" else PROMPT).format(kind=kind, text=text)
        extra = self.extra_tools() if self.extra_tools and kind not in ("routine", INTERNSHIPS, REPLIES, LINKEDIN) else None
        if extra:  # e.g. clubkit's MCP server: its tools join the allowlist (just before -p), and the prompt says so
            args, tools, note = extra
            command, prompt = command[:-1] + list(tools) + list(args) + command[-1:], prompt + note
        if kind == "routine":  # its own prompt, and RemoteTrigger is the only tool; other kinds never get it
            import routines  # here, not at the top: routines imports this module
            command = self.routine_command or routines.create_command()
            prompt = routines.CREATE_PROMPT.format(text=text)
        timeout = self.timeout
        if kind == INTERNSHIPS:  # its own model, Chrome, a narrower allowlist and an hour
            command, timeout = self.internships_command or internships_command(), self.internships_timeout
        if kind == REPLIES:  # its own model and allowlist: read-only Gmail, writing only under internships/
            command, timeout, prompt = self.replies_command or replies_command(), self.replies_timeout, REPLIES_PROMPT
        if kind == LINKEDIN:  # read-only Chrome, writing only under linkedin/, and this week's commits as the facts
            context = (self.linkedin_context() if self.linkedin_context else "") or "(none found)"
            command, timeout = self.linkedin_command or linkedin_command(), self.linkedin_timeout
            prompt = LINKEDIN_PROMPT.format(date=datetime.date.today().isoformat(), context=context)
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
