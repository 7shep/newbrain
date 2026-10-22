"""Daily tasks: persistence, date boundaries, stale clients, and authenticated routes."""
import http.client
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import server
import daily

DATE = "2026-10-21"
KEY = "0123456789abcdef"


class DailyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = server.NOTES
        server.NOTES = self.tmp.name
        self.clock = patch.object(server, "today", return_value=DATE)
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        server.NOTES = self.old
        server.TOUCHED.clear()
        self.tmp.cleanup()

    def add(self, **changes):
        body = dict(date=DATE, id=KEY, action="add", text="Pick up groceries")
        body.update(changes)
        server.act_daily(body)

    def test_persists_and_updates_items_without_overwriting_other_tasks(self):
        self.add()
        self.add(id="fedcba9876543210", text="Water plants")
        self.add()  # repeated phone delivery must not duplicate a task
        server.act_daily(dict(date=DATE, id=KEY, action="set", done=True))
        tasks = server.daily_state()["tasks"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(tasks[0]["done"])
        self.assertEqual(tasks[1]["text"], "Water plants")
        self.assertIn("- [x] Pick up groceries", server.read("daily/" + DATE + ".md"))
        server.act_daily(dict(date=DATE, id=KEY, action="set", done=False))
        self.assertFalse(server.daily_state()["tasks"][0]["done"])
        server.act_daily(dict(date=DATE, id=KEY, action="remove"))
        self.assertEqual(len(server.daily_state()["tasks"]), 1)

    def test_midnight_starts_empty_without_erasing_yesterday_or_accepting_stale_actions(self):
        self.add()
        before = server.read("daily/" + DATE + ".md")
        with patch.object(server, "today", return_value="2026-10-22"):
            self.assertEqual(server.daily_state(), {"date": "2026-10-22", "tasks": []})
            for action in ["add", "set", "remove"]:
                with self.subTest(action=action), self.assertRaisesRegex(ValueError, "new day"):
                    server.act_daily(dict(date=DATE, id=KEY, action=action, text="Old task", done=True))
            self.add(date="2026-10-22", text="New task")
            self.assertEqual(server.daily_state()["tasks"][0]["text"], "New task")
        self.assertEqual(server.read("daily/" + DATE + ".md"), before)

    def test_todays_morning_brief_is_linked(self):
        os.makedirs(os.path.join(self.tmp.name, "daily"))
        server.write("daily/2026-10-20-briefing.md", "**Today in one line:** old news\n")
        self.assertNotIn("brief", server.daily_state())
        server.write("daily/" + DATE + "-briefing.md", "# Morning briefing\n\n**Today in one line:** Quiz at 16:30.\n")
        self.assertEqual(server.daily_state()["brief"], {"path": "daily/" + DATE + "-briefing.md", "line": "Quiz at 16:30."})
        self.assertEqual(server.daily_state()["tasks"], [])

    def test_invalid_payloads_cannot_write_files(self):
        for body in [dict(text=""), dict(text=" " * 10), dict(text="x" * 301), dict(text=12),
                     dict(id="../escape"), dict(date="../../escape"), dict(action="unknown")]:
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.add(**body)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])
        self.add()
        with self.assertRaises(ValueError):
            server.act_daily(dict(date=DATE, id=KEY, action="set", done="false"))
        with self.assertRaises(ValueError):
            self.add(text="A different task using an existing ID")

    def test_text_with_markdown_or_comment_content_round_trips(self):
        title = 'Buy <bread> & milk <!-- task:aaaaaaaaaaaaaaaa --> [ ]'
        self.add(text=title)
        self.assertEqual(server.daily_state()["tasks"][0]["text"], title)
        self.add(id="fedcba9876543210", text="One\nline\tonly")
        self.assertEqual(server.daily_state()["tasks"][1]["text"], "One line only")

    def test_http_requires_token_and_persists_task(self):
        srv = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1])
            body = json.dumps(dict(date=DATE, id=KEY, action="add", text="HTTP task"))
            conn.request("POST", "/api/daily", body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            with patch.object(server.SYNC, "commit"):
                conn.request("POST", "/api/daily", body, {"Content-Type": "application/json", "X-Brain-Token": server.TOKEN})
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
            self.assertEqual(server.daily_state()["tasks"][0]["text"], "HTTP task")
            for asset in ["daily.js", "daily.css"]:
                conn.request("GET", "/" + asset)
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
            conn.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
