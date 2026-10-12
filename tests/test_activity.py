import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import activity


class ActivityTest(unittest.TestCase):
    def test_recent_activity_survives_partial_write_and_hides_prompt(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkdir(os.path.join(root, "sessions"))
            path = os.path.join(root, "sessions", "session.jsonl")
            records = [
                {"payload": {"cwd": "/projects/brain", "source": "cli"}},
                {"payload": {"type": "message", "role": "user", "content": "SECRET"}},
                {"payload": {"type": "function_call", "name": "exec_command"}},
            ]
            with open(path, "w") as stream:
                stream.write("\n".join(json.dumps(r) for r in records) + '\n{"partial":')
            os.utime(path, (100000, 100000))
            result = activity.collect(root, now=100010)
            self.assertEqual(result[0]["project"], "brain")
            self.assertEqual(result[0]["event"], "Tool: exec_command")
            self.assertNotIn("SECRET", json.dumps(result))
            self.assertEqual(activity.collect(root, now=200000), [])

    def test_missing_home(self):
        self.assertEqual(activity.collect("/missing/brain-test-home"), [])
