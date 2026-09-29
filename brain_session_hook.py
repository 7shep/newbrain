#!/usr/bin/env python3
"""Global Codex SessionStart hook for Alex's local Brain."""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTES = Path(os.environ.get("BRAIN_NOTES") or ROOT / "personal-notes").resolve()
os.environ["BRAIN_NOTES"] = str(NOTES)
sys.path.insert(0, str(ROOT))


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        event = {}
    if not NOTES.is_dir():
        return
    status = ""
    if event.get("source", "startup") in ("startup", "resume"):
        try:
            import calendar_sync
            status = calendar_sync.sync(NOTES)
        except Exception as exc:
            status = "Calendar refresh failed (%s); existing dates were kept." % type(exc).__name__
        try:
            import build
            with contextlib.redirect_stdout(io.StringIO()):
                build.main()
        except Exception:
            pass
    import session_start
    context = session_start.context()
    if status:
        context += "\n" + status
    context += "\nBrain app: http://127.0.0.1:4747/"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))


if __name__ == "__main__":
    main()
