"""Run: python3 -m unittest discover -s tests   (from the brain folder). No real claude calls."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from agents import Agents  # noqa: E402

# Stands in for claude: prints a report built from the prompt (last arg); "sleep" in the prompt stalls it.
FAKE = [sys.executable, "-c",
        "import sys,time; p=sys.argv[-1]; time.sleep(3 if 'sleep' in p else 0.05); "
        "sys.exit(2) if 'boom' in p else print('did: ' + p.split(': ',1)[1].splitlines()[0])"]


def wait(agents, n, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        runs = agents.recent()
        if len(runs) >= n and all(r["status"] in ("done", "failed") for r in runs):
            return runs
        time.sleep(0.05)
    raise AssertionError("jobs didn't finish: %r" % agents.recent())


class AgentsTest(unittest.TestCase):
    def setUp(self):
        self.notes = tempfile.mkdtemp()
        os.mkdir(os.path.join(self.notes, "agents"))

    def test_off_without_agents_folder(self):
        notes = tempfile.mkdtemp()
        a = Agents(notes, command=FAKE)
        self.assertIsNone(a.submit("note", "hello"))
        self.assertIsNone(a.recent())

    def test_runs_in_order_one_at_a_time_and_reports(self):
        a = Agents(self.notes, command=FAKE)
        a.submit("todo", "first thing")
        time.sleep(1.1)  # distinct timestamps, so files sort newest first
        a.submit("idea", "second thing")
        runs = wait(a, 2)
        self.assertEqual([r["text"] for r in runs], ["second thing", "first thing"])
        self.assertEqual([r["status"] for r in runs], ["done", "done"])
        self.assertIn("did: first thing", runs[1]["report"])
        self.assertEqual(runs[0]["type"], "idea")

    def test_second_job_waits_while_first_runs(self):
        a = Agents(self.notes, command=FAKE)
        a.submit("todo", "sleep please")
        time.sleep(1.1)
        a.submit("todo", "after")
        time.sleep(0.5)
        statuses = {r["text"]: r["status"] for r in a.recent()}
        self.assertEqual(statuses, {"sleep please": "running", "after": "queued"})
        wait(a, 2)

    def test_nonzero_exit_and_timeout_fail(self):
        a = Agents(self.notes, command=FAKE, timeout=1)
        a.submit("todo", "boom")
        time.sleep(1.1)
        a.submit("todo", "sleep forever")
        runs = {r["text"]: r for r in wait(a, 2, timeout=8)}
        self.assertEqual(runs["boom"]["status"], "failed")
        self.assertEqual(runs["sleep forever"]["status"], "failed")
        self.assertIn("Stopped after", runs["sleep forever"]["report"])

    def test_missing_claude_fails_cleanly(self):
        a = Agents(self.notes, command=["/no/such/claude"])
        a.submit("note", "x")
        run = wait(a, 1)[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("wasn't found", run["report"])

    def test_recover_marks_leftovers_failed(self):
        a = Agents(self.notes, command=FAKE)
        path = os.path.join(self.notes, "agents", "2026-01-01-000000-left.md")
        a._write(path, {"status": "running", "type": "todo", "queued": "2026-01-01 00:00"}, "left over")
        a.recover()
        run = a.recent()[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("restarted", run["report"])


if __name__ == "__main__":
    unittest.main()
