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
        self.busy = threading.Lock()   # one refresh at a time; a second caller gets the current snapshot
        self.saving = threading.Lock()  # load-merge-save, so a slow call can't overwrite a newer change
        self.failed_at = None           # in memory: back off after a failed refresh, even with no snapshot yet

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def stale(self, minutes=10):
        limit = datetime.timedelta(minutes=minutes)
        if self.failed_at and datetime.datetime.now() - self.failed_at < limit:
            return False
        snap = self.load()
        if not snap or not snap.get("checked"):
            return True
        return datetime.datetime.now() - datetime.datetime.fromisoformat(snap["checked"]) > limit

    def _merge(self, change):
        """Re-read the snapshot after the slow claude call and apply only this call's fields to it."""
        with self.saving:
            snap = self.load()
            if snap is None:
                return None
            change(snap)
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

    def refresh(self, force=True):
        """force=False (page loads) does nothing while the snapshot is fresh or a failure is being backed off."""
        if not force and not self.stale():
            return self.load()
        if not self.busy.acquire(blocking=False):
            return self.load()
        try:
            reply, error = self._ask(self.command, STATUS_PROMPT)
            items = reply.get("routines") if reply is not None else None
            now = datetime.datetime.now().isoformat(timespec="seconds")
            if not isinstance(items, list):
                error = error or "Unexpected reply: %s" % json.dumps(reply)[:200]
                self.failed_at = datetime.datetime.now()
                # A failed check still counts as a check, so page loads don't keep spawning claude.
                return self._merge(lambda snap: snap.update(error=error, checked=now)) or {"routines": [], "suggestions": [], "error": error}
            self.failed_at = None
            fresh = [_clean(x) for x in items if isinstance(x, dict)]

            def apply(snap):
                why = {r["id"]: r.get("why_pause", "") for r in snap.get("routines", [])}
                snap.update(routines=[dict(r, why_pause=why.get(r["id"], "")) for r in fresh], checked=now, error="")
            with self.saving:  # first snapshot: create it
                if self.load() is None:
                    os.makedirs(os.path.dirname(self.path), exist_ok=True)
                    _write_atomic(self.path, json.dumps({"routines": [], "suggestions": [], "suggested": ""}))
            return self._merge(apply)
        finally:
            self.busy.release()

    def act(self, rid, action):
        if action not in ("run", "pause", "resume"):
            raise ValueError("unknown action: %s" % action)
        if rid not in {r["id"] for r in (self.load() or {}).get("routines", [])}:
            raise KeyError(rid)
        body = "" if action == "run" else ", body {\"enabled\": %s}" % ("false" if action == "pause" else "true")
        reply, error = self._ask(self.command, ACT_PROMPT.format(action="run" if action == "run" else "update", rid=rid, body=body))
        if error or not (reply or {}).get("ok"):
            msg = error or (reply or {}).get("error") or "That didn't work."
            return self._merge(lambda snap: snap.update(error=msg))

        # It worked, so the snapshot already knows the result: no second claude call (that doubled the wait).
        # A run's last_run shows up on the next refresh.
        def apply(snap):
            snap["error"] = ""
            for r in snap.get("routines", []):
                if r["id"] == rid and action != "run":
                    r["enabled"] = action == "resume"
        return self._merge(apply)

    def suggest(self, force=False):
        snap = self.load()
        today = datetime.date.today().isoformat()
        if not snap or (snap.get("suggested") == today and not force):
            return snap
        reply, error = self._ask(self.suggest_cmd, SUGGEST_PROMPT)
        if reply is None:
            return self._merge(lambda s: s.update(error=error))
        sugs = reply.get("suggestions") if isinstance(reply.get("suggestions"), list) else []
        pause = reply.get("pause") if isinstance(reply.get("pause"), list) else []
        # The text goes into a RemoteTrigger-capable prompt when picked, so keep it short enough to read in full.
        sugs = [{k: str(g.get(k, ""))[:200] for k in ("title", "schedule", "text")} for g in sugs[:3] if isinstance(g, dict) and g.get("text")]
        why = {str(p.get("id")): str(p.get("reason", "")) for p in pause if isinstance(p, dict)}

        def apply(s):
            s.update(suggestions=sugs, suggested=today)
            for r in s.get("routines", []):
                r["why_pause"] = why.get(r["id"], "")
        return self._merge(apply)
