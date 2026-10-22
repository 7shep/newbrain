"""How well Claude knows you: predictions Claude logged in claude/predictions.md, scored for calibration.

One line per prediction (see FORMATS.md):
    - 2026-09-27 · 70% · recommend · bet: Status, then recent · got: Status, then recent · hit

Kinds: recommend (a "(Recommended)" option), guess (a stated guess about what you meant or want), draft (something
Claude wrote that you kept or rewrote), habit (a habit made Claude act and you went along or pushed back).
The score is a Brier skill score: 100 = perfectly confident and right, 0 = no better than always saying 50%.
Being 90% sure and wrong costs far more than being 55% sure and wrong.
"""
import datetime
import re

LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · (\d{1,3})% · (recommend|guess|draft|habit) · bet: (.+?) · got: (.+?) · (hit|miss)\s*$")
BUCKETS = [(50, 60), (60, 70), (70, 80), (80, 90), (90, 101)]


def parse(text):
    out = []
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if m:
            conf = min(max(int(m.group(2)), 50), 100)  # a bet below 50% is a bet on the other answer
            out.append({"date": m.group(1), "conf": conf, "kind": m.group(3), "bet": m.group(4).strip(),
                        "got": m.group(5).strip(), "hit": m.group(6) == "hit"})
    return out


def score(entries):
    """Brier skill score vs always saying 50%, as 0-100 (can go negative when overconfident and wrong)."""
    if not entries:
        return None
    brier = sum((e["conf"] / 100 - (1 if e["hit"] else 0)) ** 2 for e in entries) / len(entries)
    return round(100 * (1 - brier / 0.25))


def stats(entries, today=None):
    today = today or datetime.date.today().isoformat()
    if not entries:
        return {"n": 0, "score": None, "entries": []}
    week_ago = (datetime.date.fromisoformat(today) - datetime.timedelta(days=7)).isoformat()
    older = [e for e in entries if e["date"] < week_ago]
    hit_rate = round(100 * sum(e["hit"] for e in entries) / len(entries))
    avg_conf = round(sum(e["conf"] for e in entries) / len(entries))
    buckets = []
    for lo, hi in BUCKETS:
        b = [e for e in entries if lo <= e["conf"] < hi]
        if b:
            buckets.append({"conf": round(sum(e["conf"] for e in b) / len(b)), "hit": round(100 * sum(e["hit"] for e in b) / len(b)), "n": len(b)})
    kinds = {}
    for e in entries:
        k = kinds.setdefault(e["kind"], {"n": 0, "hits": 0})
        k["n"] += 1
        k["hits"] += e["hit"]
    now, before = score(entries), score(older)
    return {
        "n": len(entries), "score": now, "hit_rate": hit_rate, "avg_conf": avg_conf,
        # positive: claims more confidence than it earns (cocky); negative: humble
        "overconfidence": avg_conf - hit_rate,
        "week_change": None if before is None else now - before,
        "buckets": buckets, "kinds": kinds,
        "entries": entries[::-1][:12],  # newest first
    }
