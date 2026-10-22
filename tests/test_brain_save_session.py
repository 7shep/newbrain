"""Automatic Claude Code transcript note capture."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SaveSessionTest(unittest.TestCase):
    def test_stop_hook_saves_and_updates_one_note_from_other_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            notes = base / "notes"
            (notes / "projects").mkdir(parents=True)
            (notes / "projects" / "sample.md").write_text(
                f"---\nname: Sample\npaths: [{(base / 'other').as_posix()}]\n---\n# Sample\n",
                encoding="utf-8")
            other = base / "other"
            other.mkdir()
            transcript = base / "session.jsonl"
            session_id = "01a0eed0-852b-7460-bc98-07ff18758ae8"
            entries = [
                {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<local-command-caveat>x"}},
                {"type": "user", "message": {"role": "user", "content": "Fix the sample"}},
                {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Looking."}]}},
                {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Edit", "input": {}}]}},
                {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
                {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": [{"type": "text", "text": "Subagent chatter."}]}},
                {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Fixed the sample."}]}},
            ]
            transcript.write_text("\n".join(json.dumps(entry) for entry in entries), encoding="utf-8")
            event = {"hook_event_name": "Stop", "session_id": session_id,
                     "transcript_path": str(transcript), "cwd": str(other)}
            for _ in range(2):
                result = subprocess.run([sys.executable, str(ROOT / "brain_save_session.py")],
                                        input=json.dumps(event), text=True, capture_output=True,
                                        cwd=other, env={**os.environ, "BRAIN_NOTES": str(notes)})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "{}")
            saved = list((notes / "sessions").glob("*.md"))
            self.assertEqual(len(saved), 1)
            self.assertIn("projects: [sample]", saved[0].read_text(encoding="utf-8"))
            body = saved[0].read_text(encoding="utf-8")
            self.assertIn("Fixed the sample.", body)
            self.assertNotIn("Looking.", body)
            self.assertNotIn("Subagent chatter.", body)
            self.assertIn("-claude-01a0eed0.md", saved[0].name)
            self.assertIn("Fix the sample", (notes / "INDEX.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
