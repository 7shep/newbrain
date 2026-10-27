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

ASK_SYSTEM = """You are Zac's notes, answering a question he spoke into his phone. The reply is read aloud.
Answer in 1-3 short plain sentences: no markdown, lists, links or file paths. Use only the notes below; if they
don't say, say so. If he asks you to remember or capture something, put it on a first line starting "INBOX: ",
then confirm in one sentence."""


def act_ask(body):
    """Answer a spoken question from the notes and keep it in phone/answers.json (the last 20)."""
    import anthropic  # only the Action needs it

    text = " ".join(str(body.get("text") or "").split())[:2000]
    if not text:
        raise ValueError("empty")
    notes = "\n\n".join("<file path=\"%s\">\n%s\n</file>" % (rel, server.read(rel) or "")
                         for rel in ["INDEX.md", "now.md"] + sorted("projects/" + f for f in os.listdir(os.path.join(NOTES, "projects")) if f.endswith(".md")))
    r = anthropic.Anthropic().beta.messages.create(
        model="claude-opus-5-5", max_tokens=2000, output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=[{"type": "text", "text": ASK_SYSTEM + "\n\n" + notes, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text}])
    reply = "".join(b.text for b in r.content if b.type == "text").strip() if r.stop_reason != "refusal" else "I can't answer that one."
    if reply.startswith("INBOX: "):
        line, _, reply = reply.partition("\n")
        server.act_capture({"kind": "note", "text": line[7:]})
    path = os.path.join(NOTES, "phone", "answers.json")
    answers = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    answers = (answers + [{"id": body.get("id"), "q": text, "a": reply.strip(), "at": datetime.datetime.now().isoformat(timespec="seconds")}])[-20:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False)


ACTIONS = {
    "ask": act_ask,
    "capture": server.act_capture,
    "nudge": server.act_nudge,
    "idea": server.act_idea,
    "habit": server.act_habit,
    "habit-new": server.act_habit_new,
    "layout": server.act_layout,  # tiles he moved on the phone; the Mac uses the same order
    "theme": server.act_theme,  # "Sync theme with Mac" on: the phone's pick becomes the shared one
}
# What the phone shows. Sessions and the note list stay on the Mac.
KEEP = ("today", "issue", "streak", "now", "me", "people", "nudges", "habits", "projects", "ideas", "ideas_closed", "inbox", "agents", "predictions", "internships", "routines", "theme", "graph", "tiles", "decisions", "layout")


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
    path = os.path.join(NOTES, "phone", "answers.json")
    state["sessions"] = [{"path": x["path"], "title": x["title"], "date": x["meta"].get("date", ""), "tldr": x.get("tldr", "")}
                         for x in full.get("sessions", [])[:30]]
    state["answers"] = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    state["built"] = datetime.datetime.now().isoformat(timespec="seconds")
    state["applied"], state["failed"] = applied, failed
    with open(os.path.join(NOTES, "phone", "state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    print("applied %d, failed %d" % (len(applied), len(failed)))


if __name__ == "__main__":
    main()
