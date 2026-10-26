"""Run: python3 -m unittest discover -s tests   (from the brain folder). No real claude or GitHub calls."""
import datetime
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import devlog  # noqa: E402
from agents import Agents  # noqa: E402

ECHO = [sys.executable, "-c", "import sys; sys.stdin.reconfigure(encoding='utf-8'); sys.stdin.read(); print('Shipped a glass theme.')"]


def notes_with_profile():
    notes = tempfile.mkdtemp()
    os.makedirs(os.path.join(notes, "devlog"))
    os.mkdir(os.path.join(notes, "agents"))
    with open(os.path.join(notes, "devlog", "profile.md"), "w", encoding="utf-8") as f:
        f.write("# Dev log\n\nRepo: 7shep/7shep\n")
    return notes


def wait(agents, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        runs = agents.recent()
        if runs and all(r["status"] in ("done", "failed") for r in runs):
            return runs[0]
        time.sleep(0.05)
    raise AssertionError("job didn't finish: %r" % agents.recent())


class DevlogTest(unittest.TestCase):
    def test_off_without_a_profile(self):
        notes = tempfile.mkdtemp()
        self.assertIsNone(devlog.repo(notes))
        self.assertFalse(devlog.due(notes, [], datetime.datetime(2026, 10, 26, 9)))

    def test_due_once_each_morning(self):
        notes = notes_with_profile()
        self.assertEqual(devlog.repo(notes), "7shep/7shep")
        self.assertFalse(devlog.due(notes, [], datetime.datetime(2026, 10, 26, 6, 59)))
        self.assertTrue(devlog.due(notes, [], datetime.datetime(2026, 10, 26, 7, 0)))
        ran = [{"type": "devlog", "queued": "2026-10-26 07:00"}]
        self.assertFalse(devlog.due(notes, ran, datetime.datetime(2026, 10, 26, 12)))  # even a failed or quiet run
        self.assertTrue(devlog.due(notes, ran, datetime.datetime(2026, 10, 27, 8)))

    def test_commits_are_public_own_and_unmerged(self):
        def fake(path, auth=None):
            if path.startswith("/users/"):
                return [{"name": "brain-notes", "private": True, "archived": False, "pushed_at": "2026-10-26T00:00:00Z"},
                        {"name": "7shep", "private": False, "archived": False, "pushed_at": "2026-10-26T00:00:00Z"},
                        {"name": "old", "private": False, "archived": False, "pushed_at": "2026-01-01T00:00:00Z"},
                        {"name": "clubkit", "private": False, "archived": False, "pushed_at": "2026-10-26T00:00:00Z"}]
            self.assertIn("/repos/7shep/clubkit/commits?author=7shep", path)
            return [{"parents": [1], "commit": {"author": {"date": "2026-10-25T03:00:00Z"}, "message": "feat: outbox\n\nbody"}},
                    {"parents": [1, 2], "commit": {"author": {"date": "2026-10-25T04:00:00Z"}, "message": "Merge PR #2"}}]
        real, devlog.api = devlog.api, fake
        try:
            self.assertEqual(devlog.commits("7shep", datetime.date(2026, 10, 20)), "2026-10-25 clubkit: feat: outbox")
        finally:
            devlog.api = real

    def test_splice_and_render(self):
        readme = "Hi\n%s\nold\n%s\nbye\n" % (devlog.START, devlog.END)
        body = devlog.render([("2026-10-26", "Newest."), ("2026-10-05", "Older."), ("2026-10-01", "a"), ("2026-09-01", "b")])
        self.assertEqual(body, "**Oct 26** · Newest.\n\n**Oct 5** · Older.\n\n**Oct 1** · a")
        self.assertEqual(devlog.splice(readme, body), "Hi\n%s\n%s\n%s\nbye\n" % (devlog.START, body, devlog.END))
        with self.assertRaises(ValueError):
            devlog.splice("no markers", body)

    def test_skip_publishes_nothing(self):
        notes = notes_with_profile()
        self.assertIn("nothing was published", devlog.publish(notes, "SKIP\n", "2026-10-26"))
        self.assertEqual(devlog.posts(notes), [])

    def test_saves_the_post_when_it_cannot_publish(self):
        notes = notes_with_profile()
        real, devlog.token = devlog.token, lambda: None
        try:
            self.assertIn("couldn't publish", devlog.publish(notes, "Shipped it.\n", "2026-10-26"))
        finally:
            devlog.token = real
        self.assertEqual(devlog.posts(notes), [("2026-10-26", "Shipped it.")])

    def test_the_agent_has_no_tools(self):
        self.assertNotIn("--allowedTools", devlog.command())
        self.assertNotIn("--chrome", devlog.command())


class DevlogAgentTest(unittest.TestCase):
    def test_runs_publishes_and_is_one_at_a_time(self):
        notes = notes_with_profile()
        published = []
        a = Agents(notes, devlog_command=ECHO, devlog_context=lambda n: ("commits: x", None),
                   devlog_publish=lambda n, post: published.append(post.strip()) or "Published.")
        self.assertTrue(a.devlog())
        self.assertIsNone(a.devlog())
        run = wait(a)
        self.assertEqual((run["type"], run["status"]), ("devlog", "done"))
        self.assertEqual(published, ["Shipped a glass theme."])
        self.assertIn("Published.", run["report"])

    def test_a_quiet_day_skips_claude(self):
        notes = notes_with_profile()
        a = Agents(notes, devlog_command=["no-such-claude"], devlog_context=lambda n: (None, "No public commits."))
        a.devlog()
        run = wait(a)
        self.assertEqual((run["status"], run["report"]), ("done", "No public commits."))

    def test_publish_errors_fail_the_run(self):
        notes = notes_with_profile()
        def boom(n, post):
            raise ValueError("no markers")
        a = Agents(notes, devlog_command=ECHO, devlog_context=lambda n: ("x", None), devlog_publish=boom)
        a.devlog()
        run = wait(a)
        self.assertEqual(run["status"], "failed")
        self.assertIn("Couldn't publish: no markers", run["report"])

    def test_never_parked_or_drained(self):
        notes = notes_with_profile()
        a = Agents(notes)
        a._park("devlog", "x")
        self.assertEqual(a.drain_pending(), 0)
        self.assertEqual(a.recent(), [])


if __name__ == "__main__":
    unittest.main()
