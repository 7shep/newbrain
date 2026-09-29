#!/usr/bin/env python3
"""Refresh Brain's Upcoming section from private iCalendar feeds.

Configure personal-notes/calendar_sources.json with {"urls": ["https://.../basic.ics"]}.
The notes directory is intentionally outside Git. No credentials are logged or printed.
"""
import datetime as dt
import json
import os
import re
import urllib.request
from pathlib import Path

UPCOMING = re.compile(r"(?ms)^## Upcoming\n.*?(?=^## |\Z)")
WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def unfold(raw):
    lines = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def parse_date(value):
    value = value.strip()
    if not value:
        return None
    try:
        if len(value) == 8:
            return dt.datetime.strptime(value, "%Y%m%d")
        if value.endswith("Z"):
            return dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).astimezone().replace(tzinfo=None)
        return dt.datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        return None


def parse_events(raw):
    events, current = [], None
    for line in unfold(raw):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current and current.get("DTSTART") and current.get("SUMMARY") and current.get("STATUS") != "CANCELLED":
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.split(";", 1)[0]
            if key in ("DTSTART", "DTEND", "SUMMARY", "LOCATION", "RRULE", "STATUS", "EXDATE"):
                if key == "EXDATE":
                    current.setdefault(key, []).extend(value.split(","))
                else:
                    current[key] = value.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";")
                if key == "DTSTART" and "VALUE=DATE" in line.split(":", 1)[0]:
                    current["ALLDAY"] = True
    return events


def occurrences(event, start, end):
    first = parse_date(event["DTSTART"])
    if first is None:
        return []
    excluded = {x.date() for value in event.get("EXDATE", []) if (x := parse_date(value))}
    rule = dict(item.split("=", 1) for item in event.get("RRULE", "").split(";") if "=" in item)
    if not rule:
        return [first] if start <= first.date() <= end and first.date() not in excluded else []
    freq = rule.get("FREQ")
    if freq not in ("DAILY", "WEEKLY"):
        return []
    interval = max(1, int(rule.get("INTERVAL", "1")))
    until = parse_date(rule.get("UNTIL", ""))
    count = int(rule.get("COUNT", "0"))
    days = {WEEKDAYS[d] for d in rule.get("BYDAY", "").split(",") if d in WEEKDAYS} or {first.weekday()}
    out = []
    day = first.date()
    index = 0
    while day <= end:
        distance = (day - first.date()).days
        matching = (freq == "DAILY" and distance % interval == 0) or (freq == "WEEKLY" and distance // 7 % interval == 0 and day.weekday() in days)
        if matching:
            index += 1
            if count and index > count:
                break
            when = dt.datetime.combine(day, first.time())
            if until and when > until:
                break
            if day >= start and day not in excluded:
                out.append(when)
        day += dt.timedelta(days=1)
    return out


def sync(notes, today=None):
    notes = Path(notes)
    config = notes / "calendar_sources.json"
    if not config.exists():
        return "Calendar sync awaits a private iCal URL."
    urls = json.loads(config.read_text(encoding="utf-8")).get("urls", [])
    if not urls:
        return "Calendar sync awaits a private iCal URL."
    start = today or dt.date.today()
    end = start + dt.timedelta(days=31)
    events = []
    for url in urls:
        if not url.startswith("https://calendar.google.com/calendar/ical/"):
            raise ValueError("Calendar source must be a Google Calendar HTTPS iCal URL")
        with urllib.request.urlopen(url, timeout=12) as response:
            raw = response.read(5_000_001)
        if len(raw) > 5_000_000:
            raise ValueError("Calendar feed is too large")
        for event in parse_events(raw.decode("utf-8-sig", errors="replace")):
            for when in occurrences(event, start, end):
                events.append((when, event))
    events.sort(key=lambda item: item[0])
    lines = []
    seen = set()
    for when, event in events:
        title = re.sub(r"\s+", " ", event["SUMMARY"]).strip()
        key = (when, title)
        if key in seen:
            continue
        seen.add(key)
        date_text = when.strftime("%Y-%m-%d")
        end_at = parse_date(event.get("DTEND", ""))
        spans_days = end_at and end_at - when >= dt.timedelta(days=1) and when.time() == dt.time()
        if not event.get("ALLDAY") and not spans_days and "T" in event["DTSTART"]:
            display_when = when
            if "due" in title.lower() and end_at and dt.timedelta(0) < end_at - when <= dt.timedelta(hours=1):
                display_when = end_at
            date_text += display_when.strftime(" %H:%M")
        location = re.sub(r"\s+", " ", event.get("LOCATION", "")).strip()
        lines.append("- %s · %s%s" % (date_text, title, " · " + location if location else ""))
        if len(lines) == 8:
            break
    now = notes / "now.md"
    original = now.read_text(encoding="utf-8")
    section = "## Upcoming\n" + ("\n".join(lines) if lines else "No events in the next 31 days.") + "\n\n"
    section += "Calendar synced %s. Google Calendar remains the source of truth.\n" % start.isoformat()
    updated = UPCOMING.sub(lambda _: section, original) if UPCOMING.search(original) else original.rstrip() + "\n\n" + section
    if updated != original:
        now.write_text(updated, encoding="utf-8")
    return "Calendar synced: %d upcoming event(s)." % len(lines)


if __name__ == "__main__":
    import sys
    print(sync(sys.argv[1] if len(sys.argv) > 1 else os.environ["BRAIN_NOTES"]))
