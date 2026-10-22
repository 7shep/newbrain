"""Usage stats from Claude Code transcripts. Run: python3 -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import stats  # noqa: E402

TS = "2026-09-27T15:00:00Z"
LINES = [
    {"type": "user", "timestamp": TS, "message": {"content": "build the phone app"}},
    {"type": "user", "timestamp": TS, "message": {"content": [{"type": "text", "text": "and add tests"}]}},
    {"type": "user", "timestamp": TS, "isMeta": True, "message": {"content": "meta, not a prompt"}},
    {"type": "user", "timestamp": TS, "message": {"content": "<local-command-stdout>copied</local-command-stdout>"}},
    {"type": "user", "timestamp": TS, "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
    # one reply split over two lines: its usage must count once
    {"type": "assistant", "timestamp": TS, "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100},
     "content": [{"type": "tool_use", "name": "Agent"}]}},
    {"type": "assistant", "timestamp": TS, "message": {"id": "m1", "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100},
     "content": [{"type": "tool_use", "name": "Bash"}]}},
]


class StatsTest(unittest.TestCase):
    def test_counts_prompts_tools_subagents_and_tokens_once(self):
        root = tempfile.mkdtemp()
        proj = os.path.join(root, "projects", "-Users-x")
        os.makedirs(os.path.join(proj, "s1", "subagents"))
        with open(os.path.join(proj, "s1.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(l) for l in LINES) + "\nnot json\n")
        with open(os.path.join(proj, "s1", "subagents", "agent-a.jsonl"), "w") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": TS, "message": {"id": "s", "usage": {"output_tokens": 7}}}))
        notes = os.path.join(root, "notes")
        os.makedirs(os.path.join(notes, ".brain"))
        with open(os.path.join(notes, "now.md"), "w") as f:
            f.write("three words here")
        with open(os.path.join(notes, ".brain", "README.md"), "w") as f:
            f.write("not counted")
        s = stats.collect(os.path.join(root, "projects"), notes, cache={})
        self.assertEqual((s["sessions"], s["prompts"], s["subagents"], s["tool_calls"]), (1, 2, 1, 2))
        self.assertEqual(s["tokens"], {"input": 10, "cache_write": 0, "cache_read": 100, "output": 5})
        self.assertEqual(s["subagent_tokens"]["output"], 7)
        self.assertEqual(s["storage"]["notes"], {"files": 1, "bytes": 16, "words": 3})


if __name__ == "__main__":
    unittest.main()
