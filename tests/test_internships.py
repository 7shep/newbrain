"""Run: python3 -m unittest discover -s tests   (from the brain folder)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import server  # noqa: E402

TRACKER = """# Internship tracker
| found | company | role | term | deadline | link | status |
|---|---|---|---|---|---|---|
| 2026-09-23 | RBC | Developer | Summer 2027 | 2026-10-04 | https://rbc.example/job | **applied 2026-09-29** (retry worked) |
| 2026-09-24 | Google | SWE Intern | Summer 2027 | ~2026-09-25 | https://g.example | prep emailed |

## Top 15
1. not a table row

| id | company | role | where | deadline | fit | status |
|---|---|---|---|---|---|---|
| 163920 | CC&L | Quant Dev | Vancouver | 2026-10-26 | strong | out (finance); to check |
| 163938 | Wayfair | Security Intern | Toronto | 2026-12-24 | weak | to check |
| 1 | Manulife | 12-mo | Waterloo | x | y | different req from the one already applied to |
"""


class InternshipsTest(unittest.TestCase):
    def test_parses_every_table_and_groups_by_status(self):
        rows = server.internships(TRACKER)
        self.assertEqual([r["company"] for r in rows], ["RBC", "Google", "CC&L", "Wayfair", "Manulife"])
        self.assertEqual([r["group"] for r in rows], ["applied", "apply", "out", "check", "check"])
        self.assertEqual(rows[0]["link"], "https://rbc.example/job")
        self.assertEqual(rows[0]["status"], "applied 2026-09-29 (retry worked)")
        self.assertEqual(rows[1]["deadline"], "2026-09-25")
        self.assertEqual(rows[2]["term"], "Vancouver")  # "where" stands in when there's no term column
        self.assertEqual(rows[2]["link"], "")  # a portal id, not a URL


if __name__ == "__main__":
    unittest.main()
