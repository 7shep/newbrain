"""The private calendar importer keeps dates and recurring events accurate."""
import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import calendar_sync as calendar  # noqa: E402


FEED = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260929
SUMMARY:QWeb reminder
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/Toronto:20261001T180000
RRULE:FREQ=WEEKLY;COUNT=3;BYDAY=TH
EXDATE;TZID=America/Toronto:20261008T180000
SUMMARY:QWeb Tutorial
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/Toronto:20261007T232900
DTEND;TZID=America/Toronto:20261007T235900
SUMMARY:CISC 235 Assignment Due
END:VEVENT
END:VCALENDAR
"""


class CalendarSyncTest(unittest.TestCase):
    def test_weekly_recurrence_and_exception(self):
        events = calendar.parse_events(FEED)
        dates = calendar.occurrences(events[1], dt.date(2026, 9, 28), dt.date(2026, 10, 20))
        self.assertEqual([day.date().isoformat() for day in dates], ["2026-10-01", "2026-10-15"])

    def test_sync_updates_upcoming_and_keeps_other_sections(self):
        with tempfile.TemporaryDirectory() as folder:
            notes = Path(folder)
            (notes / "calendar_sources.json").write_text('{"urls":["https://calendar.google.com/calendar/ical/test/private/basic.ics"]}', encoding="utf-8")
            (notes / "now.md").write_text("---\nheadline: Alex's week\n---\n\n## Upcoming\nOld date\n\n## Notes\nKeep this.\n", encoding="utf-8")
            class Response:
                def __enter__(self): return self
                def __exit__(self, *_): pass
                def read(self, _): return FEED.encode()
            with patch.object(calendar.urllib.request, "urlopen", return_value=Response()):
                result = calendar.sync(notes, today=dt.date(2026, 9, 28))
            output = (notes / "now.md").read_text(encoding="utf-8")
            self.assertIn("2026-09-29 · QWeb reminder", output)
            self.assertIn("2026-10-07 23:59 · CISC 235 Assignment Due", output)
            self.assertNotIn("2026-10-08", output)
            self.assertIn("## Notes\nKeep this.", output)
            self.assertIn("4 upcoming", result)


if __name__ == "__main__":
    unittest.main()
