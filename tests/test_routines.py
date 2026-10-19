"""Run: python3 -m unittest discover -s tests   (from the brain folder). No real claude calls."""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from routines import Routines, parse_json  # noqa: E402


def fake(reply, seconds=0):
    """Stands in for claude: ignores the prompt on stdin and prints `reply`."""
    return [sys.executable, "-c", "import sys,time; sys.stdin.read(); time.sleep(%r); print(%r)" % (seconds, reply)]


ONE = '{"routines":[{"id":"t1","name":"Daily","schedule":"Daily 7am","enabled":true,"last_run":"2026-10-19 07:00","ok":true,"next_run":"2026-10-20 07:00"}]}'


class RoutinesTest(unittest.TestCase):
    def setUp(self):
        self.notes = tempfile.mkdtemp()

    def test_parse_json_ignores_prose_and_fences(self):
        self.assertEqual(parse_json('Sure!\n```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            parse_json("no json here")

    def test_refresh_writes_snapshot(self):
        r = Routines(self.notes, command=fake(ONE))
        snap = r.refresh()
        self.assertEqual(snap["routines"][0]["id"], "t1")
        self.assertEqual(snap["error"], "")
        self.assertEqual(r.load()["routines"][0]["why_pause"], "")
        self.assertFalse(r.stale())

    def test_bad_reply_keeps_old_list(self):
        Routines(self.notes, command=fake('{"routines":[{"id":"t1","name":"A"}]}')).refresh()
        snap = Routines(self.notes, command=fake("I couldn't do that")).refresh()
        self.assertEqual([x["id"] for x in snap["routines"]], ["t1"])
        self.assertTrue(snap["error"])

    def test_missing_claude_sets_error(self):
        snap = Routines(self.notes, command=["/no/such/claude"]).refresh()
        self.assertIn("wasn't found", snap["error"])

    def test_act_validates(self):
        r = Routines(self.notes, command=fake('{"routines":[{"id":"t1","name":"A"}]}'))
        r.refresh()
        with self.assertRaises(ValueError):
            r.act("t1", "delete")
        with self.assertRaises(KeyError):
            r.act("gone", "run")

    def test_pause_and_resume_update_the_snapshot_without_a_second_call(self):
        Routines(self.notes, command=fake(ONE)).refresh()
        r = Routines(self.notes, command=fake('{"ok": true}'))  # a refresh with this reply would fail
        self.assertFalse(r.act("t1", "pause")["routines"][0]["enabled"])
        snap = r.act("t1", "resume")
        self.assertTrue(snap["routines"][0]["enabled"])
        self.assertEqual(snap["error"], "")

    def test_failed_action_reports_and_keeps_state(self):
        Routines(self.notes, command=fake(ONE)).refresh()
        snap = Routines(self.notes, command=fake('{"ok": false, "error": "nope"}')).act("t1", "pause")
        self.assertTrue(snap["routines"][0]["enabled"])
        self.assertEqual(snap["error"], "nope")

    def test_suggest_once_a_day_and_flags(self):
        r = Routines(self.notes, command=fake('{"routines":[{"id":"t1","name":"A"}]}'),
                     suggest_command=fake('{"suggestions":[{"title":"Week plan","schedule":"Sun 6pm","text":"Every Sunday 6pm, plan my week"}],"pause":[{"id":"t1","reason":"replaced"}]}'))
        r.refresh()
        snap = r.suggest()
        self.assertEqual(snap["suggestions"][0]["title"], "Week plan")
        self.assertEqual(snap["routines"][0]["why_pause"], "replaced")
        self.assertEqual(r.suggest(), snap)  # same day: no second call

    def test_concurrent_refresh_runs_once(self):
        r = Routines(self.notes, command=fake('{"routines":[]}', seconds=1))
        t = threading.Thread(target=r.refresh)
        t.start()
        time.sleep(0.3)
        self.assertIsNone(r.refresh())  # second caller gets load(), and there's no snapshot yet
        t.join()

    def test_no_snapshot_means_none(self):
        self.assertIsNone(Routines(self.notes).load())
        self.assertTrue(Routines(self.notes).stale())


if __name__ == "__main__":
    unittest.main()
