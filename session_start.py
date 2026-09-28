#!/usr/bin/env python3
"""SessionStart hook: a few lines of brain context for Claude. No model calls; one quick git pull when the phone app is set up.

Prints Claude's active habits, habits the user hasn't decided on, and anything waiting in the inbox.
Notes folder = parent of this folder, or $BRAIN_NOTES. Silent if it isn't there, so it never blocks a session.
"""
import os
import re
import subprocess

NOTES = os.path.expanduser(os.environ.get("BRAIN_NOTES") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    try:
        with open(os.path.join(NOTES, rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def blocks(text):
    out = []
    for m in re.finditer(r"^## ([A-Z]+-\d+) · (.+)\n((?:- [a-z_]+:.*\n?)*)", text, re.M):
        status = re.search(r"^- status:\s*(\w+)", m.group(3), re.M)
        source = re.search(r"^- source:\s*(.*)$", m.group(3), re.M)
        out.append((m.group(1), m.group(2).strip(), status.group(1) if status else "", source.group(1).strip() if source else ""))
    return out


def main():
    if not os.path.isdir(NOTES):
        return
    if os.path.isdir(os.path.join(NOTES, "phone")) and os.path.isdir(os.path.join(NOTES, ".git")):
        try:  # pick up what the phone app did while this Mac was off; never block the session over it
            subprocess.run(["git", "-C", NOTES, "pull", "--rebase", "--autostash", "--quiet"],
                           capture_output=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            pass
    print(context())


def context():
    """The brain summary every session starts with. Also written into Codex's AGENTS.md by codex.py."""
    habits = blocks(read("claude/habits.md"))
    on = [t for _, t, s, _src in habits if s == "on"]
    proposed = [t for _, t, s, src in habits if s == "proposed" and not src.startswith("brainstorm")]
    brainstorm = [t for _, t, s, src in habits if s == "proposed" and src.startswith("brainstorm")]
    inbox = [l[2:] for l in read("inbox.md").splitlines() if l.startswith("- ")]
    name = (re.search(r"^name:\s*(\S+)", read("me.md"), re.M) or [None, "the user"])[1]
    home = NOTES.replace(os.path.expanduser("~"), "~", 1)
    lines = ["[Brain] %s is %s's brain: read %s/INDEX.md + the relevant project page before project work." % (home, name, home)]
    if on:
        lines.append("Habits %s has on (follow them): " % name + " | ".join(on))
    if proposed:
        lines.append("Proposed habits awaiting %s in the app (don't follow yet): " % name + " | ".join(proposed))
    if brainstorm:
        lines.append("%s brainstormed these habits in the app — early in this session, talk each through with them, "
                     "sharpen the wording/why, then set status on or off as they decide: " % name + " | ".join(brainstorm))
    if inbox:
        lines.append("Inbox has %d capture(s) from the app — file each into the right note, then delete it from inbox.md:" % len(inbox))
        lines += ["  - " + i for i in inbox[:15]]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
