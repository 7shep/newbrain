"""Usage stats for Brain's Stats panel: Claude Code transcripts (~/.claude/projects) plus the notes' own size.

Per transcript: prompts you typed, tool calls, subagents started, and tokens (each reply counted once, even when
the transcript splits it across several lines). Parsed results are cached by file size + mtime in
app/.stats-cache.json, so only new or growing sessions get re-read.
"""
import collections
import datetime
import json
import os

AGENT_TOOLS = {"Agent", "Task"}
NOT_PROMPTS = ("<local-command", "<task-notification", "Caveat: The messages below", "[SYSTEM NOTIFICATION")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".stats-cache.json")


def _day(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date().isoformat()
    except (AttributeError, ValueError):
        return None


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return None


def scan_file(path):
    """One transcript -> counts. Unreadable lines are skipped."""
    out = {"prompts": 0, "subagents": 0, "tools": collections.Counter(), "tokens": collections.Counter(),
           "days": collections.defaultdict(lambda: {"prompts": 0, "tokens": 0}), "first": None, "last": None}
    seen = set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            day = _day(d.get("timestamp"))
            if day:
                out["first"] = min(out["first"] or day, day)
                out["last"] = max(out["last"] or day, day)
            msg = d.get("message") if isinstance(d.get("message"), dict) else {}
            if d.get("type") == "user" and not d.get("isMeta") and not d.get("isSidechain"):
                text = _text(msg.get("content"))
                if text and text.strip() and not text.lstrip().startswith(NOT_PROMPTS):
                    out["prompts"] += 1
                    if day:
                        out["days"][day]["prompts"] += 1
            elif d.get("type") == "assistant":
                for b in msg.get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        out["tools"][b.get("name", "?")] += 1
                        if b.get("name") in AGENT_TOOLS:
                            out["subagents"] += 1
                mid, u = msg.get("id"), msg.get("usage")
                if isinstance(u, dict) and mid not in seen:  # a reply split over several lines repeats its usage
                    seen.add(mid)
                    parts = {"input": u.get("input_tokens", 0), "cache_write": u.get("cache_creation_input_tokens", 0),
                             "cache_read": u.get("cache_read_input_tokens", 0), "output": u.get("output_tokens", 0)}
                    out["tokens"].update({k: v or 0 for k, v in parts.items()})
                    if day:
                        out["days"][day]["tokens"] += sum(v or 0 for v in parts.values())
    out["tools"], out["tokens"], out["days"] = dict(out["tools"]), dict(out["tokens"]), dict(out["days"])
    return out


def notes_storage(notes):
    files = size = words = 0
    for root, dirs, names in os.walk(notes):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "graphify-out"]
        for n in names:
            if n.endswith(".md"):
                p = os.path.join(root, n)
                files += 1
                size += os.path.getsize(p)
                with open(p, encoding="utf-8", errors="replace") as f:
                    words += len(f.read().split())
    return {"files": files, "bytes": size, "words": words}


def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def collect(projects_dir, notes, cache=None):
    persist = cache is None  # tests pass their own cache and never touch the real file
    cache = _load_cache() if cache is None else cache
    fresh, sessions, sub_files, transcript_bytes = {}, 0, 0, 0
    totals = {"prompts": 0, "subagents": 0}
    tools, tokens, sub_tokens = collections.Counter(), collections.Counter(), collections.Counter()
    days = collections.defaultdict(lambda: {"prompts": 0, "tokens": 0})
    first = last = None
    for root, _, names in os.walk(projects_dir):
        for n in names:
            if not n.endswith(".jsonl"):
                continue
            p = os.path.join(root, n)
            st = os.stat(p)
            transcript_bytes += st.st_size
            key = "%d:%d" % (st.st_size, int(st.st_mtime))
            hit = cache.get(p)
            r = hit["r"] if hit and hit["k"] == key else scan_file(p)
            fresh[p] = {"k": key, "r": r}
            if os.sep + "subagents" + os.sep in p:  # a subagent's own transcript: count its tokens separately
                sub_files += 1
                sub_tokens.update(r["tokens"])
                continue
            sessions += 1
            totals["prompts"] += r["prompts"]
            totals["subagents"] += r["subagents"]
            tools.update(r["tools"])
            tokens.update(r["tokens"])
            for d, v in r["days"].items():
                days[d]["prompts"] += v["prompts"]
                days[d]["tokens"] += v["tokens"]
            if r["first"]:
                first = min(first or r["first"], r["first"])
                last = max(last or r["last"], r["last"])
    if persist:
        try:
            with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(fresh, f)
            os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        except OSError:
            pass
    today = datetime.date.today()
    last30 = [(today - datetime.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    week = [d for d in last30[-7:]]
    return {
        "sessions": sessions, "subagent_sessions": sub_files, "since": first, "last": last,
        "prompts": totals["prompts"], "subagents": totals["subagents"], "tool_calls": sum(tools.values()),
        "tokens": dict(tokens), "subagent_tokens": dict(sub_tokens),
        "week": {"prompts": sum(days[d]["prompts"] for d in week), "tokens": sum(days[d]["tokens"] for d in week)},
        "days": [{"date": d, **days[d]} for d in last30],
        "top_tools": collections.Counter(tools).most_common(8),
        "storage": {"notes": notes_storage(notes), "transcripts_bytes": transcript_bytes},
    }
