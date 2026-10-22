#!/usr/bin/env python3
"""SessionStart hook: a few lines of brain context for Claude. No model calls; one quick git pull when the phone app is set up.

Prints Claude's active habits, habits the user hasn't decided on, and anything waiting in the inbox.
Notes folder = parent of this folder, or $BRAIN_NOTES. Silent if it isn't there, so it never blocks a session.
"""
import datetime
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
    """The brain summary every session starts with. Also written into Codex's AGENTS.md by codex.py."""
    habits = blocks(read("claude/habits.md"))
    on = ["%s %s" % (i, t) for i, t, s, _src in habits if s == "on"]
    proposed = [t for _, t, s, src in habits if s == "proposed" and not src.startswith("brainstorm")]
    brainstorm = [t for _, t, s, src in habits if s == "proposed" and src.startswith("brainstorm")]
    inbox = [l[2:] for l in read("inbox.md").splitlines() if l.startswith("- ")]
    name = (re.search(r"^name:\s*(\S+)", read("me.md"), re.M) or [None, "the user"])[1]
    home = NOTES.replace(os.path.expanduser("~"), "~", 1)
    lines = ["[Brain] %s is %s's brain: read %s/INDEX.md + the relevant project page before project work." % (home, name, home)]
    today = datetime.date.today().isoformat()
    now = read("now.md")
    if "## Today · " in now and "## Today · " + today not in now:  # only for people who use the morning routine
        lines.append(
            "MORNING UPDATE NOT DONE YET TODAY — do it FIRST, before anything else the user asks: "
            "(1) file every inbox.md capture into its note and empty the inbox; "
            "(2) re-check the open items in now.md 'Upcoming' and the active projects' open threads, verify each "
            "(deploy live? reply arrived? due date passed?), tick off what's done with evidence; "
            "(3) read all of %s's calendars for today plus deadlines in the next 3 days, then replace any old "
            "'## Today · …' section at the top of now.md's body with '## Today · %s' (a time-ordered plan: classes, "
            "deadlines, suggested work blocks), whose first bullet is '- To do today: a · b · c' listing only tasks to do today (the Claude Code today-band shows that line; delete an item from it when it's done); (4) rebuild with .brain/build.py, commit and push ~/Notes; "
            "(5) show %s the Today plan in a few lines, then handle their message." % (name, today, name))
    if on:
        lines.append("Habits %s has on (follow them): " % name + " | ".join(on))
        lines.append("In the session note's frontmatter, list the habits you actually applied as `habits: [H-001, H-014]`"
                     " — the app sorts unused ones down so %s can clean them up." % name)
    if proposed:
        lines.append("Proposed habits awaiting %s in the app (don't follow yet): " % name + " | ".join(proposed))
    if brainstorm:
        lines.append("%s brainstormed these habits in the app — early in this session, talk each through with them, "
                     "sharpen the wording/why, then set status on or off as they decide: " % name + " | ".join(brainstorm))
    if inbox:
        lines.append("Inbox has %d capture(s) from the app — file each into the right note, then delete it from inbox.md:" % len(inbox))
        lines += ["  - " + i for i in inbox[:15]]
    ranked = ranked_nudges(read("nudges.md"), today)
    if ranked:
        lines.append("Open nudges, most overdue first (the top one is the biggest gap; raise it with %s early): " % name
                     + " | ".join(ranked[:5]))
    import build  # same folder; for decisions_due
    due = build.decisions_due(NOTES, today)
    if due:
        lines.append("Decisions past their check-by date: re-verify each with %s, then bump check-by or move it to "
                     "'## Superseded decisions' (superseded by <date>): " % name
                     + " | ".join("%s (%s)" % (d["what"][:90], d["path"]) for d in due[:5]))
    cal = calibration()
    if cal:
        lines.append(cal)
    return "\n".join(lines)


def ranked_nudges(text, today):
    """Open nudges (and snoozes that have run out) ranked like drives: the further past due, the higher.
    Undated ones go last."""
    out = []
    for m in re.finditer(r"^## (N-\d+) · (.+)\n((?:- [a-z_]+:.*\n?)*)", text, re.M):
        f = dict(re.findall(r"^- ([a-z_]+):[ \t]*(.*)$", m.group(3), re.M))
        snooze_over = f.get("status") == "snoozed" and f.get("snooze_until", "") and f["snooze_until"] <= today
        if f.get("status") != "open" and not snooze_over:
            continue
        due = f.get("due", "")
        try:
            over = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(due)).days
        except ValueError:
            over, due = None, ""
        label = "%s %s" % (m.group(1), m.group(2).strip())
        if over is not None:
            label += " (%s)" % ("%dd overdue" % over if over > 0 else "due today" if over == 0 else "due " + due)
        out.append((over is None, -(over or 0), label))
    return [label for *_, label in sorted(out)]


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
