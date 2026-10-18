import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import session_start  # noqa: E402

NUDGES = """## N-001 · Later thing
- status: open
- due: 2026-10-25

## N-002 · Very late
- status: open
- due: 2026-10-10

## N-003 · Done already
- status: done
- due: 2026-10-01

## N-004 · Snooze ran out
- status: snoozed
- due: 2026-10-15
- snooze_until: 2026-10-17

## N-005 · Still snoozed
- status: snoozed
- due: 2026-10-12
- snooze_until: 2026-10-30

## N-006 · No date
- status: open
- due:
"""


class RankedNudges(unittest.TestCase):
    def test_most_overdue_first_skips_closed_and_live_snoozes(self):
        self.assertEqual(session_start.ranked_nudges(NUDGES, "2026-10-18"), [
            "N-002 Very late (8d overdue)",
            "N-004 Snooze ran out (3d overdue)",
            "N-001 Later thing (due 2026-10-25)",
            "N-006 No date",
        ])


if __name__ == "__main__":
    unittest.main()
