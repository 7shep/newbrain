"""Codex transcript stats. Run: python3 -m unittest discover -s tests"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import stats  # noqa: E402

TS = "2026-09-28T15:00:00Z"


def item(kind, payload, timestamp=TS):
    return {"type": kind, "timestamp": timestamp, "payload": payload}


def write_lines(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(line) for line in lines) + "\nnot json\n")


class StatsTest(unittest.TestCase):
    def test_counts_codex_sessions_tools_tokens_and_archived_subagents(self):
        with tempfile.TemporaryDirectory() as root:
            home = os.path.join(root, "codex")
            write_lines(os.path.join(home, "sessions", "2026", "rollout-main.jsonl"), [
                item("session_meta", {"source": "cli"}),
                item("response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build it"}]}),
                item("response_item", {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "Rules"}]}),
                item("response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c1"}),
                item("response_item", {"type": "function_call", "name": "apply_patch", "call_id": "c2"}),
                item("token_usage_record", {"response_id": "r1", "usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 20}}),
                item("token_usage_record", {"response_id": "r1", "usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 20}}),
                item("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "output_tokens": 20}}}),
            ])
            write_lines(os.path.join(home, "archived_sessions", "rollout-agent.jsonl"), [
                item("session_meta", {"source": {"subagent": {"thread_spawn": {"depth": 1}}}}),
                item("response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c3"}),
                item("token_usage_record", {"response_id": "r2", "usage": {"input_tokens": 7, "output_tokens": 3}}),
            ])
            notes = os.path.join(root, "notes")
            os.makedirs(os.path.join(notes, ".brain"))
            with open(os.path.join(notes, "now.md"), "w") as f:
                f.write("three words here")
            with open(os.path.join(notes, ".brain", "README.md"), "w") as f:
                f.write("not counted")
            result = stats.collect(home, notes, cache={})
            self.assertEqual((result["sessions"], result["prompts"], result["subagents"], result["tool_calls"]), (1, 1, 1, 3))
            self.assertEqual(result["tokens"], {"input": 100, "cache_write": 0, "cache_read": 60, "output": 20})
            self.assertEqual(result["subagent_tokens"]["output"], 3)
            self.assertEqual(result["storage"]["notes"], {"files": 1, "bytes": 16, "words": 3})

    def test_older_cumulative_usage_counts_deltas_once(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "rollout.jsonl")
            write_lines(path, [
                item("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "output_tokens": 2}}}),
                item("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 16, "output_tokens": 5}}}),
                item("event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 20, "output_tokens": 7}}}),
            ])
            result = stats.scan_file(path)
            self.assertEqual(result["tokens"]["input"], 20)
            self.assertEqual(result["tokens"]["output"], 7)
            self.assertEqual(result["days"][stats._day(TS)]["tokens"], 27)


if __name__ == "__main__":
    unittest.main()
