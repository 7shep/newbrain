#!/usr/bin/env python3
"""SessionStart hook: a few lines of brain context for Claude. No model calls; one quick git pull when the phone app is set up.

Prints Claude's active habits, habits the user hasn't decided on, and anything waiting in the inbox.
Notes folder = parent of this folder, or $BRAIN_NOTES. Silent if it isn't there, so it never blocks a session.
"""
import os
import re
import subprocess
import sys

NOTES = os.path.expanduser(os.environ.get("BRAIN_NOTES") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(rel):
    try:
        with open(os.path.join(NOTES, rel), encoding="utf-8", errors="replace") as f:  # one bad byte mustn't silence the hook
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
    sys.stdout.reconfigure(encoding="utf-8")  # Windows pipes default to cp1252, which can't print every note
    print(context())


def context():
    """The brain summary every session starts with. Also written into Codex's AGENTS.md by brain_codex.py."""
    habits = blocks(read("claude/habits.md"))
    on = [t for _, t, s, _src in habits if s == "on"]
    proposed = [t for _, t, s, src in habits if s == "proposed" and not src.startswith("brainstorm")]
    brainstorm = [t for _, t, s, src in habits if s == "proposed" and src.startswith("brainstorm")]
    inbox = [l[2:] for l in read("inbox.md").splitlines() if l.startswith("- ")]
    name = (re.search(r"^name:\s*(\S+)", read("me.md"), re.M) or [None, "the user"])[1]
    home = NOTES.replace(os.path.expanduser("~"), "~", 1).replace("\\", "/")
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
    cal = calibration()
    if cal:
        lines.append(cal)
    return "\n".join(lines)


def calibration():
    """One line from claude/predictions.md: the score, what the misses say about how to answer, the latest misses.
    Advice only appears once a kind has 3+ bets, so one bad call can't steer a whole session."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))
    try:
        import predictions
    except ImportError:
        return ""
    entries = predictions.parse(read("claude/predictions.md"))
    if len(entries) < 5:
        return ""
    st = predictions.stats(entries)
    tips = []
    rate = lambda k: st["kinds"][k]["hits"] / st["kinds"][k]["n"] if st["kinds"].get(k, {}).get("n", 0) >= 3 else None
    r = rate("draft")
    if r is not None and r < .5:
        tips.append("drafts mostly get rewritten, so offer 2 short versions before one polished one")
    r = rate("habit")
    if r is not None and r < .5:
        tips.append("habit-driven pushback is often overruled, so once the user has clearly decided, build it")
    r = rate("guess")
    if r is not None and r < .5:
        tips.append("guesses about what the user means are often wrong, so ask before acting on one")
    r = rate("recommend")
    if r is not None and r >= .75:
        tips.append("recommendations usually land, so lead with one clear pick")
    if st["overconfidence"] > 8:
        tips.append("you claim more confidence than you earn, so hedge less and check more")
    elif st["overconfidence"] < -8:
        tips.append("you're right more often than you claim, so trust your reads")
    misses = [e for e in reversed(entries) if not e["hit"]][:3]
    line = "Calibration (claude/predictions.md, H-017): %s/100, right %s%% at %s%% claimed confidence." % (st["score"], st["hit_rate"], st["avg_conf"])
    if tips:
        line += " Adjust: " + "; ".join(tips) + "."
    if misses:
        line += " Latest misses: " + " | ".join('bet "%s", got "%s"' % (e["bet"], e["got"]) for e in misses)
    return line


if __name__ == "__main__":
    main()
