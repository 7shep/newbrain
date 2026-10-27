"""Run: python3 -m unittest discover -s tests   (from the brain folder). No real claude calls."""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from routines import Routines, _local, parse_json  # noqa: E402


def fake(reply, seconds=0):
    """Stands in for claude: ignores the prompt on stdin and prints `reply`."""
    return [sys.executable, "-c", "import sys,time; sys.stdout.reconfigure(encoding='utf-8'); sys.stdin.read(); time.sleep(%r); print(%r)" % (seconds, reply)]


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
        Routines(self.notes, command=fake(ONE)).refresh()
        snap = Routines(self.notes, command=["/no/such/claude"]).refresh()
        self.assertIn("wasn't found", snap["error"])

    def test_reply_without_a_routines_list_is_an_error(self):
        Routines(self.notes, command=fake(ONE)).refresh()
        snap = Routines(self.notes, command=fake('Error from tool: {"type": "auth_error"}')).refresh()
        self.assertTrue(snap["error"])
        self.assertEqual(snap["routines"][0]["id"], "t1")

    def test_malformed_items_are_skipped_not_fatal(self):
        r = Routines(self.notes, command=fake('{"routines": ["t1", {"id": "t2", "name": "B"}]}'),
                     suggest_command=fake('{"suggestions": {"title": "x"}, "pause": "nope"}'))
        self.assertEqual([x["id"] for x in r.refresh()["routines"]], ["t2"])
        self.assertEqual(r.suggest()["suggestions"], [])

    def test_failed_first_refresh_writes_nothing_and_backs_off(self):
        r = Routines(self.notes, command=["/no/such/claude"])
        self.assertIn("wasn't found", r.refresh()["error"])
        self.assertIsNone(r.load())   # new users without claude don't get a broken tile
        self.assertFalse(r.stale())   # and the next page load doesn't spawn claude again straight away

    def test_refresh_if_stale_skips_claude_while_backing_off(self):
        r = Routines(self.notes, command=["/no/such/claude"])
        r.refresh()
        r.command = fake(ONE)
        self.assertIsNone(r.refresh(force=False))       # backing off: no call, still no snapshot
        self.assertEqual(r.refresh()["routines"][0]["id"], "t1")  # the Refresh button forces it

    def test_pause_during_a_slow_suggest_is_not_lost(self):
        Routines(self.notes, command=fake(ONE)).refresh()
        slow = Routines(self.notes, suggest_command=fake('{"suggestions":[{"title":"W","schedule":"S","text":"t"}],"pause":[]}', seconds=1))
        t = threading.Thread(target=slow.suggest)
        t.start()
        time.sleep(0.3)
        Routines(self.notes, command=fake('{"ok": true}')).act("t1", "pause")
        t.join()
        snap = slow.load()
        self.assertFalse(snap["routines"][0]["enabled"])
        self.assertEqual(snap["suggestions"][0]["title"], "W")

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

    def test_history_reads_only_new_runs_and_writes_the_tile(self):
        Routines(self.notes, command=fake(ONE)).refresh()
        run = '{"runs":[{"run_id":"cse_1","created_at":"2026-10-19T11:00:05.12Z","ok":true,"did":"Sent the brief · 3 items"}]}'
        r = Routines(self.notes, command=fake(run))
        self.assertEqual([x["id"] for x in r.due_history()], ["t1"])
        r.history()
        self.assertEqual(r.due_history(), [])  # last_run is now known: no second log read
        r.history()
        self.assertEqual(len(r.load()["runs"]), 1)
        tile = open(os.path.join(self.notes, "tiles", "routine-runs.md"), encoding="utf-8").read()
        self.assertIn("summary: 1 recent runs, all OK", tile)
        self.assertEqual(r.load()["runs"][0]["at"], _local("2026-10-19T11:00:05.12Z"))  # UTC in, this computer's time out
        self.assertRegex(tile, r"\n- Daily, Mon 19 Oct \d+:00 · Sent the brief, 3 items\n")

    def test_no_snapshot_means_none(self):
        self.assertIsNone(Routines(self.notes).load())
        self.assertTrue(Routines(self.notes).stale())


if __name__ == "__main__":
    unittest.main()
