"""Run: python3 -m unittest discover -s tests   (from the brain folder). A fake clubkit repo; no node or claude."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import clubkit  # noqa: E402
from agents import Agents, REPLIES  # noqa: E402


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if isinstance(text, str) else json.dumps(text))


def run_file(agent, clubkit_passed, baseline_passed, date):
    return {"runId": date + "-" + agent, "agent": agent, "model": "sonnet" if agent == "claude" else None, "commit": "abc1234",
            "date": date, "summary": {"clubkit": {"passed": clubkit_passed, "total": 2, "costUsd": 0.5},
                                      "baseline": {"passed": baseline_passed, "total": 2, "costUsd": 0.25}},
            "attempts": [{"task": "a"}, {"task": "b"}, {"task": "a"}]}


class ClubkitTest(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        write(self.repo, "package.json", {"name": "clubkit"})
        write(self.repo, "catalog.json", {"modules": [{"name": "events", "status": "experimental", "summary": "Club events."},
                                                      {"name": "roster", "status": "planned", "summary": "Members."}]})
        write(self.repo, "TODOS.md", "# TODOS\n\n- [x] done already\n- [ ] Grow the eval set,\n      then run **Sonnet** on `evals/results/*.json`\n- [ ] Add CI\n")
        write(self.repo, "evals/results/2026-10-22T01-00-00-000Z-claude.json", run_file("claude", 1, 1, "2026-10-22T01:00:00Z"))
        write(self.repo, "evals/results/2026-10-23T01-00-00-000Z-claude.json", run_file("claude", 2, 1, "2026-10-23T01:00:00Z"))
        write(self.repo, "evals/results/2026-10-23T02-00-00-000Z-noop.json", run_file("noop", 0, 0, "2026-10-23T02:00:00Z"))
        write(self.repo, "evals/results/broken.json", "{not json")
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed clubkit"]):
            subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True)
        self.projects = [{"path": "projects/other.md", "title": "Other", "folders": [tempfile.mkdtemp()]},
                         {"path": "projects/clubkit.md", "title": "clubkit", "folders": [self.repo]}]

    def test_found_through_a_project_folder_and_absent_otherwise(self):
        self.assertEqual(clubkit.find(self.projects)[0], self.repo)
        self.assertIsNone(clubkit.state(self.projects[:1]))

    def test_state_summarises_git_catalog_todos_and_evals(self):
        s = clubkit.state(self.projects)
        self.assertEqual((s["project"], s["branch"], s["dirty"]), ("projects/clubkit.md", "main", 0))
        self.assertEqual(s["commit"]["subject"], "seed clubkit")
        self.assertEqual([m["name"] for m in s["modules"]], ["events", "roster"])
        self.assertEqual(s["todos"], ["Grow the eval set, then run Sonnet on evals/results/*.json", "Add CI"])
        self.assertEqual([r["date"][:10] for r in s["evals"]], ["2026-10-23", "2026-10-22"])  # newest first, sanity runs apart
        self.assertEqual((s["evals"][0]["clubkit"]["passed"], s["evals"][0]["baseline"]["passed"], s["evals"][0]["tasks"]), (2, 1, 2))
        self.assertEqual(s["sanity"]["noop"]["clubkit"]["passed"], 0)
        self.assertIsNone(s["sanity"]["reference"])
        self.assertFalse(s["mcp"])  # no node_modules/tsx in the fake repo

    def test_mcp_config_starts_the_server_from_any_folder(self):
        write(self.repo, "packages/mcp/src/server.ts", "")
        write(self.repo, "node_modules/tsx/dist/loader.mjs", "")
        cfg = json.loads(clubkit.mcp_config(self.repo))["mcpServers"]["clubkit"]
        self.assertEqual(cfg["command"], "node")
        self.assertTrue(cfg["args"][1].startswith("file:"))  # --import needs a URL for an absolute path on Windows
        self.assertTrue(os.path.isabs(cfg["args"][2]))


class ExtraToolsTest(unittest.TestCase):
    # Stands in for claude: prints its arguments and the end of the prompt.
    ECHO = [sys.executable, "-c", "import sys; sys.stdin.reconfigure(encoding='utf-8'); print(sys.argv[1:], sys.stdin.read()[-12:])", "-p"]

    def wait(self, a):
        for _ in range(200):
            runs = a.recent()
            if runs and all(r["status"] in ("done", "failed") for r in runs):
                return runs[0]["report"]
            time.sleep(0.05)
        raise AssertionError("agent didn't finish")

    def test_task_agents_get_the_extra_tools_and_note_but_presets_dont(self):
        notes = tempfile.mkdtemp()
        os.mkdir(os.path.join(notes, "agents"))
        extra = lambda: (["--mcp-config", "{}"], ["mcp__clubkit__list_modules"], "\nCLUBKIT NOTE")
        a = Agents(notes, command=self.ECHO, extra_tools=extra, replies_command=self.ECHO)
        a.spawn("what modules exist?")
        report = self.wait(a)
        self.assertIn("'mcp__clubkit__list_modules', '--mcp-config', '{}', '-p'", report)
        self.assertIn("CLUBKIT NOTE", report)
        os.remove(os.path.join(notes, "agents", os.listdir(os.path.join(notes, "agents"))[0]))
        a.replies()
        self.assertNotIn("clubkit", self.wait(a))
        self.assertEqual(a.recent()[0]["type"], REPLIES)


if __name__ == "__main__":
    unittest.main()
