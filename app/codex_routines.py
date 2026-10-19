"""Read Codex app automations without changing their permissions or schedules.

Python 3.9 compatibility: only the string fields needed for display are decoded;
unknown TOML fields are ignored. Full TOML parsing is used when available.
"""
import datetime
import json
import os
from pathlib import Path
import re

from agents import _write_atomic, codex_command
from routines import Routines as ClaudeRoutines


def automation_fields(text):
    try:
        import tomllib
    except ImportError:
        fields = {}
        for key in ("id", "name", "status", "rrule"):
            match = re.search(r'^' + key + r'\s*=\s*("(?:[^"\\\n]|\\.)*"|\'[^\'\n]*\')\s*(?:#.*)?$', text, re.M)
            if match:
                value = match.group(1)
                fields[key] = json.loads(value) if value.startswith('"') else value[1:-1]
        if not fields.get("name") or not fields.get("status"):
            raise ValueError("Missing automation name or status")
        return fields
    return tomllib.loads(text)


class Routines(ClaudeRoutines):
    def __init__(self, notes, home=None):
        super().__init__(notes)
        self.path = os.path.join(notes, "codex", "routines.json")
        self.home = Path(home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        self.suggest_cmd = codex_command(notes)

    def refresh(self, force=True):
        if not force and not self.stale():
            return self.load()
        if not self.busy.acquire(blocking=False):
            return self.load()
        try:
            items, errors = [], []
            for path in sorted((self.home / "automations").glob("*/automation.toml")):
                try:
                    data = automation_fields(path.read_text(encoding="utf-8"))
                    items.append({"id": path.parent.name, "name": str(data.get("name") or path.parent.name),
                                  "schedule": str(data.get("rrule") or "Schedule in Codex"),
                                  "enabled": data.get("status") == "ACTIVE", "last_run": "", "next_run": "",
                                  "ok": None, "why_pause": "", "read_only": True})
                except (OSError, ValueError):
                    errors.append("Couldn't read automation " + path.parent.name)
            with self.saving:
                snap = self.load() or {"suggestions": [], "suggested": ""}
                snap.update(routines=items, provider="codex", read_only=True,
                            checked=datetime.datetime.now().isoformat(timespec="seconds"), error="; ".join(errors))
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                _write_atomic(self.path, json.dumps(snap, ensure_ascii=False, indent=1))
                return snap
        finally:
            self.busy.release()

    def _ask(self, command, prompt):
        reply, error = super()._ask(command, prompt)
        return reply, error.replace("Claude", "Codex")

    def act(self, rid, action):
        raise ValueError("Manage this automation in the Codex app. Brain's connector is read-only.")

    def suggest(self, force=False):
        # The existing suggestion pipeline uses the same restricted read-only Codex runner.
        from routines import SUGGEST_PROMPT
        # Use our own prompt without changing the Claude provider's module constants.
        snap = self.load()
        today = datetime.date.today().isoformat()
        if not snap or (snap.get("suggested") == today and not force):
            return snap
        prompt = SUGGEST_PROMPT.replace("claude/routines.json", "codex/routines.json").replace("Claude Code", "Codex")
        prompt += " Propose only; creation and schedule changes are reviewed in the Codex app."
        reply, error = self._ask(self.suggest_cmd, prompt)
        if reply is None:
            return self._merge(lambda s: s.update(error=error))
        values = reply.get("suggestions")
        values = values if isinstance(values, list) else []
        suggestions = [{k: str(x.get(k, ""))[:200] for k in ("title", "schedule", "text")}
                       for x in values[:3] if isinstance(x, dict) and x.get("text")]
        return self._merge(lambda s: s.update(suggestions=suggestions, suggested=today, error=""))
