"""Opt-in, deterministic daily checklist planning from editable notes and deadlines."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import daily

CONFIG = "claude/day-planner.md"
COURSE = re.compile(r"\b([A-Z]{3,4})\s*(\d{3})\b", re.I)
ASSESSMENT = re.compile(r"\b(quiz|test|midterm|exam)\b", re.I)
ASSIGNMENT = re.compile(r"\b(assignment|homework|due)\b", re.I)


def settings(notes):
    path = Path(notes) / CONFIG
    if not path.exists():
        return None
    match = re.search(r"```json\s*\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S)
    config = json.loads(match.group(1)) if match else {}
    if not isinstance(config, dict):
        raise ValueError("Planner configuration must be an object")
    if not config.get("enabled"):
        return None
    for key, low, high in [("study_days", 1, 14), ("study_minutes", 15, 480),
                           ("assignment_minutes", 15, 480), ("gym_days", 0, 7),
                           ("gym_minutes", 15, 180), ("laundry_weekday", 0, 6)]:
        value = config.get(key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid planner setting: " + key)
    if not isinstance(config.get("courses", {}), dict):
        raise ValueError("courses must be an object")
    for course, overrides in config.get("courses", {}).items():
        if not isinstance(overrides, dict):
            raise ValueError("Course overrides must be objects")
        for key in ("study_days", "study_minutes", "quiz_material_weekday"):
            if key in overrides:
                limit = 6 if key == "quiz_material_weekday" else 14 if key == "study_days" else 480
                low = 0 if key == "quiz_material_weekday" else 1
                if type(overrides[key]) is not int or not low <= overrides[key] <= limit:
                    raise ValueError("Invalid planner override: " + course + "." + key)
    return config


def events(text):
    section = re.search(r"(?ms)^## Upcoming\s*\n(.*?)(?=^## |\Z)", text)
    result = []
    for date, title in re.findall(r"^- (\d{4}-\d{2}-\d{2})(?: \d{2}:\d{2})? · ([^\n]+)", section.group(1) if section else "", re.M):
        try:
            result.append((dt.date.fromisoformat(date), title.split(" · ")[0]))
        except ValueError:
            continue
    return sorted(set(result))


def schoolwork(day, upcoming, config):
    studies, assignments = {}, []
    for due, title in upcoming:
        days = (due - day).days
        course = COURSE.search(title)
        course = (course[1] + course[2]).upper() if course else title
        rule = dict(config, **config.get("courses", {}).get(course, {}))
        if ASSESSMENT.search(title) and 1 <= days <= rule["study_days"]:
            release = rule.get("quiz_material_weekday")
            if release is not None and re.search(r"\bquiz\b", title, re.I) and due.weekday() == 4:
                available = due - dt.timedelta(days=(due.weekday() - release) % 7)
                if day < available:
                    continue
            # One study block per course per day, even with overlapping tests.
            studies[course] = max(studies.get(course, 0), rule["study_minutes"])
        elif not ASSESSMENT.search(title) and ASSIGNMENT.search(title) and 0 <= days <= 1:
            if "exact date TBD" not in title:
                assignments.append(("Do " + re.sub(r"\s+due\b.*$", "", title, flags=re.I), config["assignment_minutes"]))
    return [("Study for " + course, minutes) for course, minutes in studies.items()] + assignments


def generate(notes, date):
    """Return tasks and a short context note. Never mutate files or existing completions."""
    notes = Path(notes)
    config = settings(notes)
    if config is None:
        return [], ""
    day = dt.date.fromisoformat(date)
    now_path = notes / "now.md"
    now = now_path.read_text(encoding="utf-8") if now_path.exists() else ""
    upcoming = events(now)
    work = schoolwork(day, upcoming, config)
    yesterday = notes / "daily" / ((day - dt.timedelta(days=1)).isoformat() + ".md")
    finished = {t["text"] for t in daily.parse(yesterday.read_text(encoding="utf-8")) if t["done"]} if yesterday.exists() else set()
    tasks = [title for title, _ in work if title.startswith("Study for ") or title not in finished]
    if day.weekday() == config["laundry_weekday"]:
        tasks.append("Do laundry")
    monday = day - dt.timedelta(days=day.weekday())
    completed = 0
    for offset in range(day.weekday()):
        path = notes / "daily" / ((monday + dt.timedelta(days=offset)).isoformat() + ".md")
        if path.exists() and any(t["done"] and re.search(r"\bgym\b", t["text"], re.I)
                                 for t in daily.parse(path.read_text(encoding="utf-8"))):
            completed += 1
    # Pick the lightest remaining days; ties are spread through the week.
    preference = [0, 2, 4, 6, 1, 3, 5]
    candidates = [monday + dt.timedelta(days=i) for i in range(day.weekday(), 7)]
    candidates.sort(key=lambda d: (sum(m for _, m in schoolwork(d, upcoming, config)), preference.index(d.weekday())))
    if day in candidates[:max(0, config["gym_days"] - completed)]:
        tasks.append("Go to the gym")
    note = "Plan: schoolwork first; gym %d min, assignments about %d min, study %d min per course (unless overridden)." % (config["gym_minutes"], config["assignment_minutes"], config["study_minutes"])
    synced = re.search(r"Calendar synced (\d{4}-\d{2}-\d{2})", now)
    if not synced or synced[1] != date:
        note += " Calendar has not refreshed today; check for changed or missing deadlines."
    return [{"id": hashlib.sha256((date + ":" + title).encode()).hexdigest()[:16],
             "text": title[:300], "done": False} for title in tasks][:100], note


def initial_text(notes, date):
    tasks, note = generate(notes, date)
    return daily.render(date, tasks) + "\n" + note + "\n"
