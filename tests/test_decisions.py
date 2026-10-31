"""Decision freshness: build.decisions_due finds Key-decisions lines whose check-by date has arrived."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build  # noqa: E402


class DecisionsDueTest(unittest.TestCase):
    def test_only_due_lines_in_key_decisions(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        os.makedirs(os.path.join(d, "projects"))
        with open(os.path.join(d, "projects", "brain.md"), "w") as f:
            f.write("# Brain\n## Key decisions\n"
                    "- 2026-10-02: **One-page dashboard.** check-by: 2026-10-20\n"
                    "- 2026-10-22: Tiles live in notes. check-by: 2026-11-22\n"
                    "- No date at all\n"
                    "## Superseded decisions\n- ~~Sidebar~~ check-by: 2026-01-01 (superseded by 2026-10-02)\n")
        due = build.decisions_due(d, "2026-10-22")
        self.assertEqual([(x["what"], x["check_by"], x["path"]) for x in due],
                         [("2026-10-02: One-page dashboard.", "2026-10-20", os.path.join("projects", "brain.md"))])
        self.assertEqual(len(build.decisions_due(d, "2026-11-22")), 2)


if __name__ == "__main__":
    unittest.main()
