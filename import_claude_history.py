"""Archive local Claude Code transcripts in Brain and build a readable prompt index."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import zipfile

SOURCE = Path.home() / ".claude"
DEST = Path(__file__).parent / "personal-notes" / "claude-history"
SESSION_DIRS = (SOURCE / "projects",)
NOT_PROMPTS = ("<local-command", "<command-", "<task-notification", "<system-reminder", "Caveat: The messages below",
               "[SYSTEM NOTIFICATION", "[Request interrupted")
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def messages(path):
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("type") != "user" or item.get("isMeta") or item.get("isSidechain"):
                continue
            content = (item.get("message") or {}).get("content")
            if isinstance(content, str):
                parts = [content]
            elif isinstance(content, list) and not any(p.get("type") == "tool_result" for p in content):
                parts = [p.get("text", "") for p in content if p.get("type") == "text"]
            else:
                continue
            value = "\n".join(parts).strip()
            if value and not value.startswith(NOT_PROMPTS):
                yield value


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    files = sorted(p for root in SESSION_DIRS for p in root.rglob("*.jsonl"))
    archive = DEST / "claude-transcripts.zip"
    index = DEST / "prompts.jsonl"
    manifest = DEST / "README.md"
    prompt_count = 0
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zipped, index.open("w", encoding="utf-8") as out:
        for path in files:
            relative = path.relative_to(SOURCE).as_posix()
            zipped.write(path, relative)
            session_id = (GUID.search(path.name) or [path.stem])[0]
            for number, value in enumerate(messages(path), 1):
                out.write(json.dumps({"session": session_id, "file": relative, "number": number, "text": value}, ensure_ascii=False) + "\n")
                prompt_count += 1
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest.write_text(
        "# Claude Code session history\n\n"
        f"Imported {dt.date.today().isoformat()} from `{SOURCE}`.\n\n"
        f"- Raw archive: [{archive.name}]({archive.name}) ({len(files)} JSONL transcripts; SHA-256 `{digest}`)\n"
        f"- Searchable user messages: [{index.name}]({index.name}) ({prompt_count} entries)\n\n"
        "The ZIP preserves every byte of each available Claude Code session transcript (subagents included), "
        "including assistant messages, tools, and metadata. It may contain sensitive information. "
        "The JSONL is a convenience index; the ZIP is the complete source. "
        "Rerun `python3 import_claude_history.py` to refresh this snapshot.\n",
        encoding="utf-8",
    )
    print(f"Archived {len(files)} transcripts and indexed {prompt_count} user messages; {archive.stat().st_size:,} ZIP bytes")


if __name__ == "__main__":
    main()
