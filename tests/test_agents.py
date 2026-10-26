"""Run: python3 -m unittest discover -s tests   (from the brain folder). No real claude calls."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from agents import Agents  # noqa: E402

# Stands in for claude: prints a report built from the prompt (on stdin); "sleep" in the prompt stalls it.
FAKE = [sys.executable, "-c",
        "import sys,time; sys.stdin.reconfigure(encoding='utf-8'); p=sys.stdin.read(); time.sleep(3 if 'sleep' in p else 0.05); "
        "sys.exit(2) if 'boom' in p else print('did: ' + p.split(': ',1)[1].splitlines()[0])"]

# Stands in for the routine command: proves which command and prompt a job got.
FAKE_ROUTINE = [sys.executable, "-c",
                "import sys; sys.stdin.reconfigure(encoding='utf-8'); p=sys.stdin.read(); print('routine: ' + p.splitlines()[0])"]


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
        self.assertEqual(a.recent(), [])
        self.assertFalse(os.path.exists(os.path.join(notes, "agents")))

    def test_spawn_works_without_opting_captures_in(self):
        notes = tempfile.mkdtemp()
        a = Agents(notes, command=FAKE)
        a.spawn("look into this")
        run = wait(a, 1)[0]
        self.assertEqual((run["type"], run["status"]), ("task", "done"))
        self.assertIn("did: look into this", run["report"])
        self.assertFalse(a.enabled())  # the first spawn doesn't make every capture start an agent
        self.assertIsNone(a.submit("note", "just a thought"))
        self.assertEqual(len(a.recent()), 1)

    def test_spawn_gets_the_task_prompt(self):
        echo = [sys.executable, "-c", "import sys; sys.stdin.reconfigure(encoding='utf-8'); print(sys.stdin.read().splitlines()[0])"]
        a = Agents(self.notes, command=echo)
        a.spawn("summarize my week")
        self.assertIn("Agents tile with this task: summarize my week", wait(a, 1)[0]["report"])

    def test_parked_tasks_run_even_when_captures_are_off(self):
        notes = tempfile.mkdtemp()
        a = Agents(notes, command=FAKE)
        os.environ["BRAIN_AGENTS"] = "pending"
        try:
            a.spawn("from the phone")
        finally:
            del os.environ["BRAIN_AGENTS"]
        self.assertEqual(a.drain_pending(), 1)
        self.assertEqual(wait(a, 1)[0]["text"], "from the phone")

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

    def test_prompt_goes_in_whole_on_stdin(self):
        # A multi-line, non-ASCII prompt must arrive intact (on Windows, a .cmd shim would cut an argument at its
        # first newline, and the default code page can't encode every character).
        echo = [sys.executable, "-c", "import sys; sys.stdin.reconfigure(encoding='utf-8'); "
                "sys.stdout.reconfigure(encoding='utf-8'); "
                "print('\\n'.join(l for l in sys.stdin.read().splitlines() if 'caf' in l or 'line two' in l))"]
        a = Agents(self.notes, command=echo)
        a.submit("note", "caf\u00e9 \u00b7 line one\nline two")
        report = wait(a, 1)[0]["report"]
        self.assertIn("caf\u00e9 \u00b7 line one", report)
        self.assertIn("line two", report)

    def test_recover_marks_leftovers_failed(self):
        a = Agents(self.notes, command=FAKE)
        path = os.path.join(self.notes, "agents", "2026-01-01-000000-left.md")
        a._write(path, {"status": "running", "type": "todo", "queued": "2026-01-01 00:00"}, "left over")
        a.recover()
        run = a.recent()[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("restarted", run["report"])

    def test_routine_kind_uses_its_own_command_and_prompt(self):
        a = Agents(self.notes, command=FAKE, routine_command=FAKE_ROUTINE)
        a.submit("routine", "every sunday plan my week")
        report = wait(a, 1)[0]["report"]
        self.assertIn("routine: Set up a Claude Code routine for this request: every sunday plan my week", report)

    def test_other_kinds_never_get_the_routine_command(self):
        a = Agents(self.notes, command=FAKE, routine_command=FAKE_ROUTINE)
        a.submit("todo", "buy milk")
        self.assertNotIn("routine:", wait(a, 1)[0]["report"])

    def test_internships_get_their_own_command_prompt_and_timeout(self):
        echo = [sys.executable, "-c", "import sys; sys.stdin.reconfigure(encoding='utf-8'); print('intern: ' + sys.stdin.read()[:60])"]
        a = Agents(self.notes, command=FAKE, internships_command=echo)
        a.internships()
        run = wait(a, 1)[0]
        self.assertEqual((run["type"], run["status"]), ("internships", "done"))
        self.assertIn("intern: Brain started you headless", run["report"])

    def test_internships_command_is_sonnet_with_chrome_and_a_narrow_allowlist(self):
        import agents
        cmd = agents.internships_command()
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-sonnet-5-5")
        self.assertIn("--chrome", cmd)
        self.assertIn("Write(internships/**)", cmd)
        for tool in ("Write", "Edit", "WebFetch", "Bash(ls:*)", "mcp__claude_ai_Gmail__create_draft"):
            self.assertNotIn(tool, cmd)
        self.assertIn("never click Submit", agents.internships_prompt())

    def test_one_internship_run_at_a_time(self):
        slow = [sys.executable, "-c", "import time; time.sleep(2)"]
        a = Agents(self.notes, command=FAKE, internships_command=slow, internships_timeout=5)
        self.assertTrue(a.internships())
        self.assertIsNone(a.internships())
        wait(a, 1)

    def test_internship_run_is_never_parked_or_drained(self):
        notes = tempfile.mkdtemp()
        a = Agents(notes, command=FAKE)
        os.environ["BRAIN_AGENTS"] = "pending"
        try:
            self.assertIsNone(a.internships())
        finally:
            del os.environ["BRAIN_AGENTS"]
        a._park("internships", "x")
        self.assertEqual(a.drain_pending(), 0)
        self.assertEqual(a.recent(), [])

    def test_reply_check_reads_gmail_only_and_writes_only_the_tracker_folder(self):
        import agents
        cmd = agents.replies_command()
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-sonnet-5-5")
        self.assertIn("mcp__claude_ai_Gmail__search_threads", cmd)
        self.assertIn("Write(internships/**)", cmd)
        for tool in ("Write", "Edit", "--chrome", "WebFetch", "mcp__claude_ai_Gmail__create_draft"):
            self.assertNotIn(tool, cmd)
        self.assertIn("never send", agents.REPLIES_PROMPT)

    def test_reply_check_gets_its_own_command_prompt_and_runs_one_at_a_time(self):
        echo = [sys.executable, "-c", "import sys, time; sys.stdin.reconfigure(encoding='utf-8'); time.sleep(.5); print('replies: ' + sys.stdin.read()[:40])"]
        a = Agents(self.notes, command=FAKE, replies_command=echo)
        self.assertTrue(a.replies())
        self.assertIsNone(a.replies())
        run = wait(a, 1)[0]
        self.assertEqual((run["type"], run["status"]), ("replies", "done"))
        self.assertIn("replies: Brain started you headless to check", run["report"])

    def test_linkedin_prep_can_read_chrome_but_never_click_type_or_script(self):
        import agents
        cmd = agents.linkedin_command()
        self.assertIn("--chrome", cmd)
        self.assertIn("mcp__claude-in-chrome__get_page_text", cmd)
        self.assertIn("Write(linkedin/**)", cmd)
        for tool in ("mcp__claude-in-chrome", "mcp__claude-in-chrome__computer", "mcp__claude-in-chrome__javascript_tool",
                     "mcp__claude-in-chrome__form_input", "mcp__claude-in-chrome__browser_batch", "Write", "Edit", "Bash(ls:*)"):
            self.assertNotIn(tool, cmd)
        self.assertIn("never like, react, comment, post", agents.LINKEDIN_PROMPT)
        prompt = agents.LINKEDIN_PROMPT.format(date="2026-10-26", context="")  # links: permalink, else a checked search
        self.assertIn("/feed/update/urn:li:activity:", prompt)
        self.assertIn("search/results/content/?keywords=%22", prompt)

    def test_linkedin_prep_gets_the_weeks_commits_and_runs_one_at_a_time(self):
        echo = [sys.executable, "-c", "import sys, time; sys.stdin.reconfigure(encoding='utf-8'); time.sleep(.5); print(sys.stdin.read()[-40:])"]
        a = Agents(self.notes, command=FAKE, linkedin_command=echo, linkedin_context=lambda: "Brain:\n- 2026-10-25 feat: glass")
        self.assertTrue(a.linkedin())
        self.assertIsNone(a.linkedin())
        run = wait(a, 1)[0]
        self.assertEqual((run["type"], run["status"]), ("linkedin", "done"))
        self.assertIn("2026-10-25 feat: glass", run["report"])
        a._park("linkedin", "x")
        self.assertEqual(a.drain_pending(), 0)

    def test_reply_check_is_never_drained(self):
        a = Agents(self.notes, command=FAKE)
        a._park("replies", "x")
        self.assertEqual(a.drain_pending(), 0)
        self.assertEqual(a.recent(), [])


if __name__ == "__main__":
    unittest.main()
