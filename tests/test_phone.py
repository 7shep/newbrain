"""The phone app's two moving parts: the queue applier (runs on GitHub) and the Mac's git sync.
Run: python3 -m unittest discover -s tests   (from the brain folder). Uses the example notes and temp git repos."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


class AskTest(unittest.TestCase):
    def run_ask(self, notes, response=None, fail=False):
        # Substitute only the CLI process: test the real queue, prompt, flags, response validation and capture.
        code = r"""
import json, os, sys
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
sys.argv = ["phone.py", sys.argv[2]]
import phone

def fake(command, **kw):
    assert command[-1] == "-" and "read-only" in command
    assert "--ignore-user-config" in command and "--ignore-rules" in command
    disabled = [command[i+1] for i, value in enumerate(command[:-1]) if value == "--disable"]
    assert all(f in disabled for f in ["hooks", "apps", "plugins", "multi_agent", "shell_tool"])
    assert "--output-schema" in command and "--ephemeral" in command
    assert "now.md" in kw["input"] and "question" in kw["input"]
    assert kw["cwd"] != phone.NOTES
    if os.environ.get("TEST_CODEX_FAIL") == "1":
        return SimpleNamespace(returncode=1)
    path = command[command.index("--output-last-message") + 1]
    with open(path, "w", encoding="utf-8") as f:
        f.write(os.environ["TEST_CODEX_RESPONSE"])
    return SimpleNamespace(returncode=0)
with patch.object(phone.subprocess, "run", side_effect=fake):
    phone.main()
"""
        env = {**os.environ, "TEST_CODEX_RESPONSE": json.dumps(response), "TEST_CODEX_FAIL": str(int(fail))}
        result = subprocess.run([sys.executable, "-c", code, os.path.join(BRAIN, "app"), notes],
                                capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(read(notes, "phone/state.json"))

    def test_ask_answers_and_captures(self):
        notes = notes_copy()
        queue(notes, "q1", "ask", {"id": "a1", "text": "remember to buy milk"})
        state = self.run_ask(notes, {"answer": "Noted, milk is on your list.", "capture": "buy milk"})
        self.assertEqual(state["failed"], [])
        self.assertEqual([(a["id"], a["a"]) for a in state["answers"]], [("a1", "Noted, milk is on your list.")])
        self.assertIn("buy milk", read(notes, "inbox.md"))
        self.assertEqual(len(os.listdir(os.path.join(notes, "agents", "pending"))), 1)

    def test_question_without_capture_or_projects_folder(self):
        notes = notes_copy()
        shutil.rmtree(os.path.join(notes, "projects"))
        before = read(notes, "inbox.md")
        queue(notes, "q1", "ask", {"id": "a1", "text": "what is on today?"})
        state = self.run_ask(notes, {"answer": "The notes do not say.", "capture": None})
        self.assertEqual(state["failed"], [])
        self.assertEqual(read(notes, "inbox.md"), before)

    def test_invalid_answer_or_cli_failure_does_not_block_capture(self):
        for reply, fail in [({"answer": "", "capture": "unexpected"}, False), (None, True)]:
            with self.subTest(reply=reply, fail=fail):
                notes = notes_copy()
                queue(notes, "1-ask", "ask", {"id": "a1", "text": "what is next?"})
                queue(notes, "2-capture", "capture", {"kind": "note", "text": "keep this"})
                state = self.run_ask(notes, reply, fail)
                self.assertEqual([f["id"] for f in state["failed"]], ["1-ask"])
                self.assertEqual(state["applied"], ["2-capture"])
                self.assertNotIn("unexpected", read(notes, "inbox.md"))
                self.assertIn("keep this", read(notes, "inbox.md"))

    def test_hosted_answers_match_question_ids_and_reject_duplicates(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                notes = notes_copy()
                queue(notes, "q1", "ask", {"id": "a1", "text": "remember milk"})
                response = {"id": "a1", "answer": "Noted.", "capture": "milk"}
                path = os.path.join(tempfile.mkdtemp(), "answers.json")
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"answers": [response] * (2 if duplicate else 1)}, f)
                result = subprocess.run([sys.executable, os.path.join(BRAIN, "app", "phone.py"), notes,
                                         "--answers-file", path], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = json.loads(read(notes, "phone/state.json"))
                if duplicate:
                    self.assertEqual(len(state["failed"]), 1)
                    self.assertEqual(state["answers"], [])
                else:
                    self.assertEqual(state["failed"], [])
                    self.assertEqual(state["answers"][0]["a"], "Noted.")

    def test_prepare_writes_only_fixture_context_for_the_action(self):
        notes = notes_copy()
        queue(notes, "q1", "ask", {"id": "a1", "text": "what is next?"})
        work = tempfile.mkdtemp()
        output = os.path.join(work, "github-output")
        code = """
import sys
sys.path.insert(0, sys.argv[1])
work = sys.argv[3]
sys.argv = ["phone.py", sys.argv[2]]
import phone
phone.__file__ = work + "/app/phone.py"
phone.prepare_asks()
"""
        result = subprocess.run([sys.executable, "-c", code, os.path.join(BRAIN, "app"), notes, work],
                                capture_output=True, text=True, env={**os.environ, "GITHUB_OUTPUT": output})
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(os.path.join(work, "phone-ask-prompt.txt"), encoding="utf-8") as f:
            prompt = f.read()
        self.assertIn('"id": "a1"', prompt)
        self.assertIn('"now.md"', prompt)
        self.assertIn("has_questions=true", Path(output).read_text())
        self.assertTrue(os.path.exists(os.path.join(notes, "phone", "queue", "q1.json")))


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
        self.assertIn("Ask before long builds", read(notes, "codex/habits.md"))
        self.assertNotIn("sessions", state)  # the phone only gets what it shows

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
