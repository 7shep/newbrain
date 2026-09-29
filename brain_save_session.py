#!/usr/bin/env python3
"""Persist a Codex session from Stop or SessionEnd without model cooperation."""
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTES = Path(os.environ.get("BRAIN_NOTES") or ROOT / "personal-notes").resolve()


def extract(path, session_id):
    prompts, replies = [], []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or {}
            if record.get("type") == "session_meta":
                actual_id = payload.get("id") or payload.get("session_id")
                if actual_id != session_id:
                    return [], []
            if record.get("type") != "response_item" or payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            if role == "assistant" and payload.get("phase") != "final_answer":
                continue
            parts = [item.get("text", "") for item in payload.get("content", [])
                     if item.get("type") in ("input_text", "output_text")]
            message = "\n".join(parts).strip()
            if role == "user":
                # Codex may prepend its environment and AGENTS.md as a separate content part.
                message = "\n".join(part for part in parts if not part.startswith("# AGENTS.md instructions")).strip()
                if message:
                    prompts.append(message)
            elif message:
                replies.append(message)
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
    title = " ".join(prompts[0].split())[:70].rstrip(" .,:;") or "Codex session"
    title = title.replace("\n", " ")
    project = project_for(cwd)
    note = NOTES / "sessions" / f"{date}-codex-{session_id[:8]}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    if note.exists() and "generated-by: brain_save_session.py" not in note.read_text(encoding="utf-8"):
        return False
    synopsis = " ".join((replies[-1] if replies else prompts[-1]).split())[:400]
    sections = ["---", f"date: {date}", f"title: {title}", f"projects: [{project}]",
                "status: info", f"session: {session_id}", f"cwd: {cwd}",
                "generated-by: brain_save_session.py", "---", "", f"# {title}", "",
                f"**TL;DR:** {synopsis}", "", "## Requests and final responses", ""]
    for index, prompt in enumerate(prompts):
        sections.extend([f"### Request {index + 1}", "", prompt[:2000], ""])
        if index < len(replies):
            sections.extend(["**Response:**", "", replies[index][:3000], ""])
    sections.extend(["## Where things live", "", f"- Codex session ID: `{session_id}`", ""])
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
        pass  # A note hook must never interrupt Codex.
    if event.get("hook_event_name") == "Stop":
        print("{}")


if __name__ == "__main__":
    main()
