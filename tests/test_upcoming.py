import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import server  # noqa: E402

NOW = """## Today · 2026-10-06
- 19:00 · quiz

## Done
- 2026-10-06 · shipped the site fix
- 2026-10-05 · applied to EA

## Upcoming
- 2026-10-06 19:00 · LING Practice Quiz 2 · optional
- 2026-10-05 · already past
- 2026-10-09 · LING Quiz 2
- Waiting: an undated line
"""


class Upcoming(unittest.TestCase):
    def test_only_the_upcoming_section_counts_and_past_dates_drop(self):
        items = server.upcoming_items(NOW, "2026-10-06")
        self.assertEqual([(u["date"], u["title"]) for u in items], [("2026-10-06", "LING Practice Quiz 2"), ("2026-10-09", "LING Quiz 2")])
        self.assertEqual(items[0]["time"], "19:00")

    def test_soonest_first_whatever_order_the_file_has(self):
        body = "## Upcoming\n- 2026-10-09 · later\n- 2026-10-06 · today all day\n- 2026-10-06 14:00 · today at 2\n"
        self.assertEqual([u["title"] for u in server.upcoming_items(body, "2026-10-06")], ["today at 2", "today all day", "later"])

    def test_no_upcoming_section_means_nothing_up_next(self):
        self.assertEqual(server.upcoming_items("## Done\n- 2026-10-06 · x\n", "2026-10-06"), [])


if __name__ == "__main__":
    unittest.main()
