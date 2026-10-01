"""Codex adapter: the AGENTS.md block and the codex exec agent command. Run: python3 -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
import subprocess

BRAIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["BRAIN_NOTES"] = os.path.join(BRAIN, "example")
sys.path.insert(0, BRAIN)
sys.path.insert(0, os.path.join(BRAIN, "app"))
import brain_codex as codex  # noqa: E402
from agents import Agents  # noqa: E402


class CodexTest(unittest.TestCase):
    def test_rebuilding_other_notes_does_not_replace_global_instructions(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as notes:
            path = os.path.join(home, "AGENTS.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Personal Brain\n")
            app = os.path.join(BRAIN, "app")
            code = "import sys; sys.path.insert(0, %r); import server; server.rebuild_index()" % app
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                    env={**os.environ, "BRAIN_NOTES": notes, "CODEX_HOME": home}, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "# Personal Brain\n")

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

    def test_old_marker_is_replaced_without_a_second_block(self):
        path = os.path.join(tempfile.mkdtemp(), "AGENTS.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# My rules\n" + codex.OLD_START + "\nold\n" + codex.END + "\n")
        codex.sync(path)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count(codex.START), 1)
        self.assertNotIn(codex.OLD_START, text)

    def test_brain_agent_codex_uses_codex_exec(self):
        os.environ["BRAIN_AGENT"] = "codex"
        try:
            agent = Agents(tempfile.mkdtemp())
            cmd = agent.command
        finally:
            del os.environ["BRAIN_AGENT"]
        self.assertIn("--ignore-user-config", cmd)
        self.assertEqual(cmd[cmd.index("--ask-for-approval"):cmd.index("--ask-for-approval") + 4],
                         ["--ask-for-approval", "never", "exec", "--cd"])
        self.assertIn("read-only", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertEqual(cmd[-1], "-")  # read the entire capture prompt from stdin
        self.assertIn("Analyze this capture only", agent.prompt)
        self.assertEqual(Agents(tempfile.mkdtemp()).command[1], "--setting-sources")  # default stays Claude


if __name__ == "__main__":
    unittest.main()
