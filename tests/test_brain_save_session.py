"""Automatic Codex transcript note capture."""
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
            transcript = base / "rollout.jsonl"
            session_id = "01a0eed0-852b-7460-bc98-07ff18758ae8"
            entries = [
                {"type": "session_meta", "payload": {"id": session_id}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Fix the sample"}]}},
                {"type": "response_item", "payload": {"type": "message", "role": "assistant", "phase": "final_answer", "content": [{"type": "output_text", "text": "Fixed the sample."}]}},
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
            self.assertIn("Fixed the sample.", saved[0].read_text(encoding="utf-8"))
            self.assertIn("Fix the sample", (notes / "INDEX.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
