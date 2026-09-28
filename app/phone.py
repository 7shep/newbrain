#!/usr/bin/env python3
"""Apply the phone's queued actions to the notes, then write phone/state.json for the phone to read.

Run by the notes repo's GitHub Action (see docs/specs/2026-09-27-phone-app.md):
    python3 .brain/app/phone.py <notes folder>

The phone never edits notes. It drops one JSON file per action into phone/queue/, and this applies each with
the same functions the Mac app uses, so both write notes identically. A bad action is moved to phone/failed/
with its error instead of blocking the rest. Captures don't run agents here: they're parked in
agents/pending/ for the Mac.
"""
import datetime
import glob
import json
import os
import sys

NOTES = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
os.environ["BRAIN_NOTES"] = NOTES
os.environ["BRAIN_AGENTS"] = "pending"
sys.argv = sys.argv[:1]  # server.py reads its own flags from argv
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402

ACTIONS = {
    "capture": server.act_capture,
    "nudge": server.act_nudge,
    "idea": server.act_idea,
    "habit": server.act_habit,
    "habit-new": server.act_habit_new,
}
# What the phone shows. Sessions, people and the note list stay on the Mac.
KEEP = ("today", "issue", "streak", "now", "me", "nudges", "habits", "projects", "ideas", "ideas_closed", "inbox", "agents", "predictions")


def apply_queue():
    applied, failed = [], []
    for path in sorted(glob.glob(os.path.join(NOTES, "phone", "queue", "*.json"))):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as f:
                job = json.load(f)
            ACTIONS[job["action"]](job.get("body") or {})
            applied.append(name[:-5])
        except Exception as e:  # noqa: BLE001  one bad action mustn't block the rest
            failed.append({"id": name[:-5], "error": "%s: %s" % (type(e).__name__, e)})
            os.makedirs(os.path.join(NOTES, "phone", "failed"), exist_ok=True)
            with open(os.path.join(NOTES, "phone", "failed", name), "w", encoding="utf-8") as f:
                json.dump({"error": failed[-1]["error"], "job": open(path, encoding="utf-8").read()}, f)
        os.remove(path)
    return applied, failed


def main():
    applied, failed = apply_queue()
    server.rebuild_index()
    full = server.state()
    state = {k: full[k] for k in KEEP if k in full}
    for p in state.get("projects", []):  # Mac-only details: resume commands and local folder paths
        p.pop("resume", None)
        p.pop("folders", None)
    state["theme"] = server.read("phone/theme").strip() or None  # the desktop chip's choice
    state["built"] = datetime.datetime.now().isoformat(timespec="seconds")
    state["applied"], state["failed"] = applied, failed
    with open(os.path.join(NOTES, "phone", "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    print("applied %d, failed %d" % (len(applied), len(failed)))


if __name__ == "__main__":
    main()
