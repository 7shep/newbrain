"""The phone app's two moving parts: the queue applier (runs on GitHub) and the Mac's git sync.
Run: python3 -m unittest discover -s tests   (from the brain folder). Uses the example notes and temp git repos."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BRAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BRAIN, "app"))
from sync import Sync  # noqa: E402


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True).stdout


def notes_copy():
    d = tempfile.mkdtemp()
    notes = os.path.join(d, "notes")
    shutil.copytree(os.path.join(BRAIN, "example"), notes)
    os.makedirs(os.path.join(notes, "phone", "queue"))
    os.makedirs(os.path.join(notes, "agents"))
    return notes


def queue(notes, name, action, body):
    with open(os.path.join(notes, "phone", "queue", name + ".json"), "w") as f:
        json.dump({"action": action, "body": body}, f)


def read(notes, rel):
    with open(os.path.join(notes, rel), encoding="utf-8") as f:
        return f.read()


# Stands in for the Anthropic SDK so the ask test runs offline: replies with a capture and an answer.
FAKE_ANTHROPIC = """
class _B:
    type = "text"
    text = "INBOX: buy milk\\nNoted, milk is on your list."
class _R:
    stop_reason = "end_turn"
    content = [_B()]
class _M:
    def create(self, **kw):
        assert kw["model"] == "claude-opus-5-5" and "now.md" in kw["system"][0]["text"]
        return _R()
class _Beta:
    messages = _M()
class Anthropic:
    beta = _Beta()
"""


class AskTest(unittest.TestCase):
    def test_ask_answers_and_captures(self):
        notes, fake = notes_copy(), tempfile.mkdtemp()
        with open(os.path.join(fake, "anthropic.py"), "w") as f:
            f.write(FAKE_ANTHROPIC)
        queue(notes, "q1", "ask", {"id": "a1", "text": "remember to buy milk"})
        p = subprocess.run([sys.executable, os.path.join(BRAIN, "app", "phone.py"), notes], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": fake})
        self.assertEqual(p.returncode, 0, p.stderr)
        state = json.loads(read(notes, "phone/state.json"))
        self.assertEqual(state["failed"], [])
        self.assertEqual([(a["id"], a["a"]) for a in state["answers"]], [("a1", "Noted, milk is on your list.")])
        self.assertIn("buy milk", read(notes, "inbox.md"))


class ApplyQueueTest(unittest.TestCase):
    def run_phone(self, notes):
        # A fresh process each time: server.py fixes its notes folder when imported.
        p = subprocess.run([sys.executable, os.path.join(BRAIN, "app", "phone.py"), notes], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(read(notes, "phone/state.json"))

    def test_applies_every_action_type_like_the_mac_app(self):
        notes = notes_copy()
        queue(notes, "1-capture", "capture", {"kind": "todo", "text": "Buy a sensor"})
        queue(notes, "2-nudge", "nudge", {"action": "done", "id": "N-001"})
        queue(notes, "3-idea", "idea", {"action": "done", "text": "2026-09-10 · Plant tracker sends a weekly photo collage of growth"})
        queue(notes, "4-habit", "habit", {"id": "H-002", "status": "off"})
        queue(notes, "5-habitnew", "habit-new", {"title": "Ask before long builds", "why": "phone test"})
        state = self.run_phone(notes)
        self.assertEqual(state["applied"], ["1-capture", "2-nudge", "3-idea", "4-habit", "5-habitnew"])
        self.assertEqual(state["failed"], [])
        self.assertEqual(os.listdir(os.path.join(notes, "phone", "queue")), [])
        self.assertIn("todo · Buy a sensor", read(notes, "inbox.md"))
        self.assertEqual(next(n for n in state["nudges"] if n["id"] == "N-001")["status"], "done")
        self.assertIn("Plant tracker sends a weekly photo collage of growth (done", read(notes, "ideas.md"))
        self.assertEqual(next(h for h in state["habits"] if h["id"] == "H-002")["status"], "off")
        self.assertIn("Ask before long builds", read(notes, "claude/habits.md"))
        self.assertEqual(set(state["sessions"][0]), {"path", "title", "date", "tldr"})  # the phone only gets what it shows
        self.assertNotIn("notes", state)

    def test_theme_pick_from_the_phone_becomes_the_shared_theme(self):
        notes = notes_copy()
        queue(notes, "1-theme", "theme", {"theme": "riso/paper"})
        queue(notes, "2-bad", "theme", {"theme": "../../etc"})
        state = self.run_phone(notes)
        self.assertEqual(state["applied"], ["1-theme"])
        self.assertEqual([f["id"] for f in state["failed"]], ["2-bad"])
        self.assertEqual(json.loads(read(notes, "claude/theme.json")), {"theme": "riso/paper"})  # what the Mac follows
        self.assertEqual(state["theme"], "riso/paper")

    def test_routines_snapshot_and_routine_captures_reach_the_phone(self):
        notes = notes_copy()
        with open(os.path.join(notes, "claude", "routines.json"), "w") as f:
            json.dump({"checked": "2026-10-19T10:00:00", "routines": [{"id": "t1", "name": "Daily"}], "suggestions": []}, f)
        queue(notes, "1", "capture", {"kind": "routine", "text": "Every Sunday, plan my week"})
        state = self.run_phone(notes)
        self.assertEqual(state["routines"]["routines"][0]["id"], "t1")
        self.assertEqual(state["failed"], [])
        pending = os.listdir(os.path.join(notes, "agents", "pending"))
        with open(os.path.join(notes, "agents", "pending", pending[0])) as f:
            self.assertEqual(json.load(f)["kind"], "routine")
        self.assertNotIn("plan my week", read(notes, "inbox.md"))  # not a thought to file: the morning routine would redo it

    def test_captures_are_parked_for_the_mac_not_run(self):
        notes = notes_copy()
        queue(notes, "1", "capture", {"kind": "idea", "text": "Parked idea"})
        self.run_phone(notes)
        pending = os.listdir(os.path.join(notes, "agents", "pending"))
        self.assertEqual(len(pending), 1)
        with open(os.path.join(notes, "agents", "pending", pending[0])) as f:
            self.assertEqual(json.load(f), {"kind": "idea", "text": "Parked idea"})
        self.assertEqual([f for f in os.listdir(os.path.join(notes, "agents")) if f.endswith(".md")], [])

    def test_a_bad_action_is_set_aside_and_the_rest_still_apply(self):
        notes = notes_copy()
        queue(notes, "1-bad", "nudge", {"action": "done", "id": "N-999"})
        queue(notes, "2-good", "capture", {"kind": "note", "text": "still applied"})
        state = self.run_phone(notes)
        self.assertEqual(state["applied"], ["2-good"])
        self.assertEqual([f["id"] for f in state["failed"]], ["1-bad"])
        self.assertTrue(os.path.exists(os.path.join(notes, "phone", "failed", "1-bad.json")))
        self.assertIn("still applied", read(notes, "inbox.md"))


class SyncTest(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.remote = os.path.join(root, "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.remote], check=True)
        seed = notes_copy()
        open(os.path.join(seed, "phone", "queue", ".gitkeep"), "w").close()
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed"],
                     ["remote", "add", "origin", self.remote], ["push", "-q", "-u", "origin", "main"]):
            git(seed, *args)
        self.mac = os.path.join(root, "mac")
        self.phone = os.path.join(root, "phone")  # stands in for GitHub's side
        for d in (self.mac, self.phone):
            subprocess.run(["git", "clone", "-q", self.remote, d], check=True)
            git(d, "config", "user.name", "t")
            git(d, "config", "user.email", "t@t")

    def remote_change(self, rel, text):
        with open(os.path.join(self.phone, rel), "a") as f:
            f.write(text)
        git(self.phone, "commit", "-qam", "phone change")
        git(self.phone, "push", "-q")

    def test_pull_brings_in_remote_changes_and_runs_the_hook(self):
        pulled = []
        s = Sync(self.mac, on_pulled=lambda: pulled.append(1))
        self.remote_change("inbox.md", "- from the phone\n")
        self.assertTrue(s.pull(gap=0))
        self.assertIn("from the phone", read(self.mac, "inbox.md"))
        self.assertEqual(pulled, [1])
        self.assertTrue(s.pull())  # within the minute: skipped, hook not re-run
        self.assertEqual(pulled, [1])

    def test_commit_only_takes_brains_files_and_pushes(self):
        s = Sync(self.mac)
        with open(os.path.join(self.mac, "inbox.md"), "a") as f:
            f.write("- brain wrote this\n")
        with open(os.path.join(self.mac, "me.md"), "a") as f:
            f.write("\nhalf-finished edit by someone else\n")
        s.commit(["inbox.md"], "brain: capture")
        self.assertTrue(s.push())
        git(self.phone, "pull", "-q")
        self.assertIn("brain wrote this", read(self.phone, "inbox.md"))
        self.assertNotIn("half-finished", read(self.phone, "me.md"))
        self.assertIn("me.md", git(self.mac, "status", "--porcelain"))  # left for its owner

    def test_commit_blocked_by_another_git_says_so_and_returns_false(self):
        s = Sync(self.mac)
        with open(os.path.join(self.mac, "inbox.md"), "a") as f:
            f.write("- capture while a terminal holds the index\n")
        open(os.path.join(self.mac, ".git", "index.lock"), "w").close()  # another git process is running
        self.assertFalse(s.commit(["inbox.md"], "brain: capture"))
        self.assertIn("couldn't save", s.error)
        os.remove(os.path.join(self.mac, ".git", "index.lock"))
        self.assertTrue(s.commit(["inbox.md"], "brain: capture"))  # next try goes through and clears it
        self.assertIsNone(s.error)

    def test_push_rejected_by_newer_remote_rebases_and_retries(self):
        s = Sync(self.mac)
        self.remote_change("ideas.md", "- phone idea\n")
        with open(os.path.join(self.mac, "inbox.md"), "a") as f:
            f.write("- mac capture\n")
        s.commit(["inbox.md"], "brain: capture")
        self.assertTrue(s.push())
        git(self.phone, "pull", "-q")
        self.assertIn("mac capture", read(self.phone, "inbox.md"))
        self.assertIn("phone idea", read(self.mac, "ideas.md"))

    def test_real_conflict_pauses_and_leaves_the_folder_untouched(self):
        s = Sync(self.mac)
        self.remote_change("now.md", "\nphone line\n")
        with open(os.path.join(self.mac, "now.md"), "a") as f:
            f.write("\nmac line\n")
        git(self.mac, "commit", "-qam", "mac edit")
        self.assertFalse(s.pull(gap=0))
        self.assertIn("Sync paused", s.error)
        self.assertIn("mac line", read(self.mac, "now.md"))
        self.assertFalse(os.path.isdir(os.path.join(self.mac, ".git", "rebase-merge")))  # rebase aborted

    def test_off_without_phone_folder(self):
        shutil.rmtree(os.path.join(self.mac, "phone"))
        self.assertFalse(Sync(self.mac).enabled())


@unittest.skipUnless(shutil.which("node"), "needs node")
class TranscriptTest(unittest.TestCase):
    """The mic's transcript() in mobile/index.html, fed Chrome-style and iOS-style result lists."""
    def test_joins_chrome_and_ios_results(self):
        js = r"""
const h = require("fs").readFileSync(process.argv[1], "utf8");
eval(h.match(/function transcript[\s\S]*?\n}\n/)[0]);
const R = (...ts) => ts.map(t => [{ transcript: t }]), eq = (a, b) => { if (a !== b) throw new Error(JSON.stringify(a)); };
eq(transcript(R("can you fix", " the talking on brain")), "can you fix the talking on brain");
eq(transcript(R("Can you fix the talking", "On brain")), "Can you fix the talking On brain");
eq(transcript(R("Can you", "can you fix the", "Can you fix the talking on brain")), "Can you fix the talking on brain");
eq(transcript(R("Can you fix the talking on brain", "on brain", "")), "Can you fix the talking on brain");
"""
        subprocess.run(["node", "-e", js, os.path.join(BRAIN, "mobile", "index.html")], check=True)


if __name__ == "__main__":
    unittest.main()
