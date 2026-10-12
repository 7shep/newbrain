"""Bounded, read-only snapshots of recent local CLI transcript activity."""
import json
import os
import time


def collect(home, now=None):
    now = time.time() if now is None else now
    candidates = []
    for root, dirs, files in os.walk(os.path.join(home, "sessions"), followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in files:
            path = os.path.join(root, name)
            if not name.endswith(".jsonl") or os.path.islink(path):
                continue
            try:
                modified = os.path.getmtime(path)
                if 0 <= now - modified <= 86400:
                    candidates.append((modified, path))
            except OSError:
                continue
    result = []
    for modified, path in sorted(candidates, reverse=True)[:8]:
        try:
            with open(path, "rb") as stream:
                first = stream.readline(65536)
                stream.seek(0, os.SEEK_END)
                size = stream.tell()
                stream.seek(max(0, size - 65536))
                tail = stream.read(65536).splitlines()
            meta = json.loads(first).get("payload", {})
            if not isinstance(meta, dict) or not isinstance(meta.get("cwd"), str):
                continue
            event = "Transcript updated"
            for line in reversed(tail):
                try:
                    record = json.loads(line)
                    payload = record.get("payload", {})
                    if not isinstance(payload, dict):
                        continue
                    kind = payload.get("type")
                    if kind in ("function_call", "custom_tool_call"):
                        event = "Tool: " + str(payload.get("name") or "unknown")[:80]
                        break
                    if kind == "message" and payload.get("role") == "assistant":
                        event = "Assistant response recorded"
                        break
                    if kind == "message" and payload.get("role") == "user":
                        event = "Prompt recorded"
                        break
                    if kind in ("task_complete", "turn_aborted"):
                        event = "Turn completed" if kind == "task_complete" else "Turn interrupted"
                        break
                except (ValueError, AttributeError):
                    continue
            cwd = meta["cwd"]
            result.append({"cwd": cwd, "project": os.path.basename(cwd.rstrip("/\\")) or cwd,
                           "updated": modified, "event": event})
        except (OSError, ValueError, AttributeError):
            continue
    return result
