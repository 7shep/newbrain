#!/usr/bin/env python3
"""Persist a Claude Code session from Stop or SessionEnd without model cooperation."""
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTES = Path(os.environ.get("BRAIN_NOTES") or ROOT / "personal-notes").resolve()


# User records that are Claude Code's own wrappers, not something typed.
NOT_PROMPTS = ("<local-command", "<command-", "<task-notification", "<system-reminder", "Caveat: The messages below",
               "[SYSTEM NOTIFICATION", "[Request interrupted")


def _texts(content):
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list) or any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return []
    return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]


def extract(path, session_id):
    """Typed prompts, and for each the last text Claude wrote before the next prompt (its final response)."""
    prompts, replies = [], []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict) or record.get("isSidechain") or record.get("isMeta"):
                continue
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            text = "\n".join(_texts(message.get("content"))).strip()
            if not text:
                continue
            if record.get("type") == "user" and not text.startswith(NOT_PROMPTS):
                prompts.append(text)
                replies.append("")
            elif record.get("type") == "assistant" and prompts:
                replies[-1] = text
    return prompts, replies


def project_for(cwd):
    here = Path(cwd).resolve()
    for page in (NOTES / "projects").glob("*.md"):
        try:
            body = page.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^paths:\s*\[(.*)\]", body, re.M)
        if not match:
            continue
        for value in match.group(1).split(","):
            root = Path(os.path.expanduser(value.strip().strip("'\""))).resolve()
            if here == root or root in here.parents:
                return page.stem
    return "misc"


def save(event):
    session_id = event.get("session_id", "")
    transcript = event.get("transcript_path")
    cwd = event.get("cwd", "")
    if not re.fullmatch(r"[\w-]{8,100}", session_id) or not transcript or not cwd:
        return False
    path = Path(transcript)
    if not path.is_file() or path.suffix != ".jsonl":
        return False
    prompts, replies = extract(path, session_id)
    if not prompts:
        return False
    date = dt.datetime.fromtimestamp(path.stat().st_ctime).date().isoformat()
    title = " ".join(prompts[0].split())[:70].rstrip(" .,:;") or "Claude session"
    title = title.replace("\n", " ")
    project = project_for(cwd)
    note = NOTES / "sessions" / f"{date}-claude-{session_id[:8]}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    if note.exists() and "generated-by: brain_save_session.py" not in note.read_text(encoding="utf-8"):
        return False
    synopsis = " ".join((replies[-1] or prompts[-1]).split())[:400]
    sections = ["---", f"date: {date}", f"title: {title}", f"projects: [{project}]",
                "status: info", f"session: {session_id}", f"cwd: {cwd}",
                "generated-by: brain_save_session.py", "---", "", f"# {title}", "",
                f"**TL;DR:** {synopsis}", "", "## Requests and final responses", ""]
    for index, prompt in enumerate(prompts):
        sections.extend([f"### Request {index + 1}", "", prompt[:2000], ""])
        if replies[index]:
            sections.extend(["**Response:**", "", replies[index][:3000], ""])
    sections.extend(["## Where things live", "", f"- Claude Code session ID: `{session_id}`", ""])
    temp = note.with_suffix(".tmp")
    temp.write_text("\n".join(sections), encoding="utf-8")
    os.replace(temp, note)
    env = {**os.environ, "BRAIN_NOTES": str(NOTES)}
    subprocess.run([sys.executable, str(ROOT / "build.py")], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    return True


def main():
    event = {}
    try:
        event = json.load(sys.stdin)
        if NOTES.is_dir():
            save(event)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass  # A note hook must never interrupt Claude Code.
    if event.get("hook_event_name") == "Stop":
        print("{}")


if __name__ == "__main__":
    main()
