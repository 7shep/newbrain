"""Codex adapter: the AGENTS.md block and the codex exec agent command. Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest

BRAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["BRAIN_NOTES"] = os.path.join(BRAIN, "example")
sys.path.insert(0, BRAIN)
sys.path.insert(0, os.path.join(BRAIN, "app"))
import codex  # noqa: E402
from agents import Agents  # noqa: E402


class CodexTest(unittest.TestCase):
    def test_block_is_added_refreshed_and_leaves_the_rest_alone(self):
        path = os.path.join(tempfile.mkdtemp(), "AGENTS.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# My own rules\nAlways use tabs.\n")
        codex.sync(path)
        codex.sync(path)  # second run replaces, doesn't duplicate
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("# My own rules\nAlways use tabs.\n"))
        self.assertEqual(text.count(codex.START), 1)
        self.assertIn("INDEX.md", text)
        self.assertIn("Habits", text)  # the example notes have habits switched on

    def test_brain_agent_codex_uses_codex_exec(self):
        os.environ["BRAIN_AGENT"] = "codex"
        try:
            cmd = Agents(tempfile.mkdtemp()).command
        finally:
            del os.environ["BRAIN_AGENT"]
        self.assertEqual(cmd[1:5], ["--ask-for-approval", "never", "exec", "--cd"])  # exec itself rejects the flag
        self.assertIn("workspace-write", cmd)
        self.assertEqual(Agents(tempfile.mkdtemp()).command[1], "--setting-sources")  # default stays Claude


if __name__ == "__main__":
    unittest.main()
