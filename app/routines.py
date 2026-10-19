"""Claude Code routines (scheduled cloud agents) in Brain.

Brain can't call the routines API itself: it needs the Claude login that only Claude Code holds. So each call
runs headless claude with nothing allowed but the RemoteTrigger tool, asks for compact JSON, and caches the
answer in claude/routines.json. The desktop app, phone.py and the phone all read that one snapshot.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import threading

from agents import _write_atomic

TIMEOUT = 5 * 60
SNAPSHOT = os.path.join("claude", "routines.json")

ITEM = ('{"id", "name", "schedule", "enabled": true|false, "last_run": "YYYY-MM-DD HH:MM" or "", '
        '"ok": true|false|null, "next_run": "YYYY-MM-DD HH:MM" or ""}')
STATUS_PROMPT = (
    "Call the RemoteTrigger tool with action \"list\". Reply with only JSON, no prose: {\"routines\": [...]}, one "
    "item per routine shaped " + ITEM + ". Times are in this computer's local time zone. \"schedule\" is the "
    "schedule in a few plain words (\"Daily 7am\", \"Mon + Thu 9am\"); if a routine's prompt says to run only "
    "when the local hour is N, the schedule is that hour. \"ok\" is false when the last run failed for a real "
    "reason, null when it never ran."
)
ACT_PROMPT = (
    "Call the RemoteTrigger tool with action \"{action}\", trigger_id \"{rid}\"{body}. "
    "Reply with only JSON: {{\"ok\": true}}, or {{\"ok\": false, \"error\": \"...\"}} if it failed."
)
SUGGEST_PROMPT = (
    "Read INDEX.md, now.md and claude/routines.json in this folder: the person's notes and their Claude Code "
    "routines (cloud agents on a schedule, with Gmail, Google Calendar and GitHub). Reply with only JSON: "
    "{\"suggestions\": [at most 3 of {\"title\", \"schedule\", \"text\"}], \"pause\": [{\"id\", \"reason\"}]}. "
    "Suggest only routines that would clearly help with what's in the notes right now and that such an agent "
    "can really do; \"text\" is the request in one sentence, e.g. \"Every Sunday at 6pm, plan my week from my "
    "calendar\". In \"pause\", list running routines that duplicate another or whose subject is finished, with "
    "a reason of a few words. Empty lists are fine."
)
CREATE_PROMPT = (
    "Set up a Claude Code routine for this request: {text}\n\n"
    "Use the RemoteTrigger tool. Call action \"list\", then \"get\" on one existing routine to copy the shape of "
    "its request body, then \"create\" one with a short name, a prompt that does the request on its own (it "
    "has no other context), and a cron schedule in UTC matching the request in this computer's local time. "
    "Always create it with \"enabled\": false. End with at most 3 lines: the name, the schedule in plain words, "
    "and \"Created paused. Resume it in Brain's Routines tile.\""
)


def _claude(*flags):
    return [shutil.which("claude") or "claude", "--setting-sources", "project", "--permission-mode", "dontAsk",
            *flags, "-p"]


def routine_command():
    return _claude("--model", "haiku", "--allowedTools", "RemoteTrigger")


def create_command():
    return _claude("--allowedTools", "RemoteTrigger")


def suggest_command():
    return _claude("--allowedTools", "Read", "Glob", "Grep")


def parse_json(text):
    """The first {...} object in text; claude may wrap it in prose or a ```json fence."""
    start = text.find("{")
    while start >= 0:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text, start)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        start = text.find("{", start + 1)
    raise ValueError("no JSON in the reply")


def _clean(item):
    return {"id": str(item.get("id", "")), "name": str(item.get("name", "")), "schedule": str(item.get("schedule") or ""),
            "enabled": bool(item.get("enabled", True)), "last_run": str(item.get("last_run") or ""),
            "ok": item.get("ok") if item.get("ok") in (True, False) else None,
            "next_run": str(item.get("next_run") or ""), "why_pause": ""}


class Routines:
    def __init__(self, notes, command=None, suggest_command=None):
        self.notes = notes
        self.path = os.path.join(notes, SNAPSHOT)
        self.command = command or routine_command()
        self.suggest_cmd = suggest_command or globals()["suggest_command"]()
        self.lock = threading.Lock()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def stale(self, minutes=10):
        snap = self.load()
        if not snap or not snap.get("checked"):
            return True
        return datetime.datetime.now() - datetime.datetime.fromisoformat(snap["checked"]) > datetime.timedelta(minutes=minutes)

    def _save(self, snap):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        _write_atomic(self.path, json.dumps(snap, ensure_ascii=False, indent=1))
        return snap

    def _ask(self, command, prompt):
        """Run claude with the prompt on stdin; returns (reply dict, error text)."""
        try:
            p = subprocess.run(command, input=prompt, cwd=self.notes, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=TIMEOUT)
        except FileNotFoundError:
            return None, "The %s command wasn't found." % os.path.basename(command[0])
        except subprocess.TimeoutExpired:
            return None, "Claude didn't answer in %d minutes." % (TIMEOUT // 60)
        try:
            return parse_json(p.stdout), ""
        except ValueError:
            return None, (p.stdout.strip() or p.stderr.strip() or "No reply.")[:300]

    def refresh(self):
        if not self.lock.acquire(blocking=False):
            return self.load()
        try:
            snap = self.load() or {"routines": [], "suggestions": [], "suggested": ""}
            reply, error = self._ask(self.command, STATUS_PROMPT)
            if reply is not None and isinstance(reply.get("routines"), list):
                old = {r["id"]: r.get("why_pause", "") for r in snap.get("routines", [])}
                snap["routines"] = [dict(_clean(x), why_pause=old.get(str(x.get("id")), "")) for x in reply["routines"]]
                snap["checked"] = datetime.datetime.now().isoformat(timespec="seconds")
            snap["error"] = error or ("" if reply is not None else "No reply.")
            return self._save(snap)
        finally:
            self.lock.release()

    def act(self, rid, action):
        if action not in ("run", "pause", "resume"):
            raise ValueError("unknown action: %s" % action)
        snap = self.load() or {}
        if rid not in {r["id"] for r in snap.get("routines", [])}:
            raise KeyError(rid)
        body = "" if action == "run" else ", body {\"enabled\": %s}" % ("false" if action == "pause" else "true")
        reply, error = self._ask(self.command, ACT_PROMPT.format(action="run" if action == "run" else "update", rid=rid, body=body))
        snap = self.refresh() or snap
        if error or not (reply or {}).get("ok"):
            snap = self._save(dict(snap, error=error or (reply or {}).get("error") or "That didn't work."))
        return snap

    def suggest(self, force=False):
        snap = self.load()
        today = datetime.date.today().isoformat()
        if not snap or (snap.get("suggested") == today and not force):
            return snap
        reply, error = self._ask(self.suggest_cmd, SUGGEST_PROMPT)
        if reply is None:
            return self._save(dict(snap, error=error))
        snap["suggestions"] = [{k: str(s.get(k, "")) for k in ("title", "schedule", "text")}
                               for s in reply.get("suggestions", [])[:3] if isinstance(s, dict) and s.get("text")]
        why = {str(p.get("id")): str(p.get("reason", "")) for p in reply.get("pause", []) if isinstance(p, dict)}
        for r in snap.get("routines", []):
            r["why_pause"] = why.get(r["id"], "")
        snap["suggested"] = today
        return self._save(snap)
