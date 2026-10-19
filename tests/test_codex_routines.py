"""Offline checks for the read-only Codex automations connector."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
from codex_routines import Routines, automation_fields


class CodexRoutinesTest(unittest.TestCase):
    def test_reads_automations_and_never_changes_source(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root) / "home"
            path = home / "automations" / "daily" / "automation.toml"
            path.parent.mkdir(parents=True)
            original = 'name = "Daily review"\nstatus = "ACTIVE"\nrrule = "FREQ=DAILY"\n'
            path.write_text(original)
            r = Routines(str(Path(root) / "notes"), home=home)
            with patch("subprocess.run", side_effect=AssertionError("No CLI needed")):
                snap = r.refresh()
            self.assertEqual(snap["routines"][0]["name"], "Daily review")
            self.assertTrue(snap["routines"][0]["enabled"])
            self.assertTrue(snap["routines"][0]["read_only"])
            for action in ("pause", "run", "resume"):
                with self.assertRaisesRegex(ValueError, "Codex app"):
                    r.act("daily", action)
            self.assertEqual(path.read_text(), original)
            self.assertEqual(r.load(), snap)

    def test_empty_install_and_malformed_file(self):
        with tempfile.TemporaryDirectory() as root:
            r = Routines(root, home=Path(root) / "home")
            self.assertEqual(r.refresh()["routines"], [])
            path = r.home / "automations" / "bad" / "automation.toml"
            path.parent.mkdir(parents=True)
            path.write_text('name = "unfinished')
            self.assertIn("bad", r.refresh()["error"])

    def test_suggestions_use_codex_and_validate_items(self):
        with tempfile.TemporaryDirectory() as root:
            r = Routines(root, home=Path(root) / "home")
            r.refresh()
            with patch.object(r, "_ask", return_value=({"suggestions": [None, {"text": "Weekly review"}]}, "")) as ask:
                result = r.suggest()
            self.assertEqual(len(result["suggestions"]), 1)
            self.assertNotIn("claude", " ".join(ask.call_args[0][0]).lower())
            self.assertIn("codex/routines.json", ask.call_args[0][1])

    def test_python39_field_reader(self):
        with patch.dict(sys.modules, {"tomllib": None}):
            self.assertEqual(automation_fields('name = "Daily"\nstatus = \'PAUSED\'\n')["status"], "PAUSED")

    def test_disabled_agents_preserve_routine_in_inbox(self):
        import server
        with patch.object(server.AGENTS, "enabled", return_value=False), \
             patch.object(server.AGENTS, "submit"), \
             patch.object(server, "read", return_value="# Inbox\n"), \
             patch.object(server, "write") as write:
            server.act_capture({"kind": "routine", "text": "Every Sunday review my week"})
        self.assertEqual(write.call_args[0][0], "inbox.md")
        self.assertIn("routine · Every Sunday review my week", write.call_args[0][1])

    def test_habit_suggestion_uses_restricted_codex(self):
        import server
        from types import SimpleNamespace
        with patch.object(server, "read", return_value=""), \
             patch.object(server.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="Keep replies brief")) as run:
            self.assertEqual(server.habit_idea()["idea"], "Keep replies brief")
        command = run.call_args[0][0]
        self.assertIn("--ignore-user-config", command)
        self.assertIn("read-only", command)
        self.assertIn("shell_tool", command)
