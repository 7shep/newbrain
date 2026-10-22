"""SessionStart hook: on Thursdays, prompt the weekly internship run if it hasn't happened yet.

Prints nothing on other days, or when today's date is already in the tracker's
"Weekly run log" section. Otherwise prints hook JSON that asks Claude to run
/apply-internships.
"""

import datetime
import json
import os
import re
import sys

THURSDAY = 3


def main():
    today = datetime.date.today()
    if today.weekday() != THURSDAY:
        return

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    tracker = os.path.join(root, "personal-notes", "internships", "tracker.md")
    try:
        with open(tracker, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return  # No tracker on this machine: nothing to check.

    match = re.search(r"^## Weekly run log\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match and today.isoformat() in match.group(1):
        return

    message = (
        "It's Thursday ({}) and this week's internship run isn't in "
        "personal-notes/internships/tracker.md yet. Before anything else, tell Alex "
        "you're starting the weekly run, then follow the apply-internships skill "
        "(/apply-internships). If Alex's first message asks for something else, "
        "ask whether to do the run first or later today."
    ).format(today.isoformat())
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}},
        sys.stdout,
    )


if __name__ == "__main__":
    main()
