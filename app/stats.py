"""Usage stats from Codex session transcripts and Brain's markdown notes.

Codex stores active sessions in ~/.codex/sessions and archived sessions in
~/.codex/archived_sessions. Parsed counts are cached by file size and mtime.
"""
import collections
import datetime
import json
import os

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".stats-cache.json")
CACHE_VERSION = 3
TOKEN_FIELDS = {"input": "input_tokens", "cache_write": "cache_write_input_tokens",
                "cache_read": "cached_input_tokens", "output": "output_tokens"}


def _day(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date().isoformat()
    except (AttributeError, ValueError):
        return None


def _tokens(usage):
    if not isinstance(usage, dict):
        return {}
    return {name: int(usage.get(field) or 0) for name, field in TOKEN_FIELDS.items()}


def _add_usage(out, usage, day):
    parts = _tokens(usage)
    out["tokens"].update(parts)
    if day:
        out["days"][day]["tokens"] += parts.get("input", 0) + parts.get("output", 0)


def scan_file(path):
    """One Codex JSONL transcript -> counts; skip incomplete or unknown records."""
    out = {"prompts": 0, "subagent": False, "tools": collections.Counter(),
           "tokens": collections.Counter(),
           "days": collections.defaultdict(lambda: {"prompts": 0, "tokens": 0}),
           "first": None, "last": None}
    seen_responses, usage_records, fallback = set(), False, []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            kind = record.get("type")
            payload = record.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            day = _day(record.get("timestamp"))
            if day:
                out["first"] = min(out["first"] or day, day)
                out["last"] = max(out["last"] or day, day)
            if kind == "session_meta":
                out["subagent"] = isinstance(payload.get("source"), dict) and "subagent" in payload["source"]
            elif kind == "response_item":
                if payload.get("type") == "message" and payload.get("role") == "user" and payload.get("content"):
                    out["prompts"] += 1
                    if day:
                        out["days"][day]["prompts"] += 1
                elif payload.get("type") in ("function_call", "custom_tool_call"):
                    out["tools"][payload.get("name") or "unknown"] += 1
            elif kind == "token_usage_record":
                response_id = payload.get("response_id")
                if response_id and response_id in seen_responses:
                    continue
                if response_id:
                    seen_responses.add(response_id)
                if isinstance(payload.get("usage"), dict):
                    usage_records = True
                    _add_usage(out, payload["usage"], day)
            elif kind == "event_msg" and payload.get("type") == "token_count":
                usage = (payload.get("info") or {}).get("total_token_usage")
                if isinstance(usage, dict):
                    fallback.append((day, _tokens(usage)))
    if not usage_records:
        previous = collections.Counter()
        for day, cumulative in fallback:
            delta = {k: max(0, value - previous[k]) for k, value in cumulative.items()}
            _add_usage(out, {field: delta[name] for name, field in TOKEN_FIELDS.items()}, day)
            previous = collections.Counter(cumulative)
    out["tools"], out["tokens"], out["days"] = dict(out["tools"]), dict(out["tokens"]), dict(out["days"])
    return out


def notes_storage(notes):
    files = size = words = 0
    for root, dirs, names in os.walk(notes):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "graphify-out"]
        for name in names:
            if name.endswith(".md"):
                path = os.path.join(root, name)
                files += 1
                size += os.path.getsize(path)
                with open(path, encoding="utf-8", errors="replace") as f:
                    words += len(f.read().split())
    return {"files": files, "bytes": size, "words": words}


def _load_cache():
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("entries", {}) if data.get("version") == CACHE_VERSION else {}
    except (OSError, ValueError, AttributeError):
        return {}


def collect(codex_home, notes, cache=None):
    persist = cache is None
    cache = _load_cache() if persist else cache
    fresh, sessions, sub_files, transcript_bytes = {}, 0, 0, 0
    totals = {"prompts": 0}
    tools, tokens, sub_tokens = collections.Counter(), collections.Counter(), collections.Counter()
    days = collections.defaultdict(lambda: {"prompts": 0, "tokens": 0})
    first = last = None
    for folder in ("sessions", "archived_sessions"):
        for root, _, names in os.walk(os.path.join(codex_home, folder)):
            for name in names:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                    transcript_bytes += stat.st_size
                    key = "%d:%d" % (stat.st_size, stat.st_mtime_ns)
                    hit = cache.get(path)
                    result = hit["r"] if hit and hit.get("k") == key else scan_file(path)
                except OSError:
                    continue
                fresh[path] = {"k": key, "r": result}
                tools.update(result["tools"])
                if result["subagent"]:
                    sub_files += 1
                    sub_tokens.update(result["tokens"])
                    continue
                sessions += 1
                totals["prompts"] += result["prompts"]
                tokens.update(result["tokens"])
                for day, values in result["days"].items():
                    days[day]["prompts"] += values["prompts"]
                    days[day]["tokens"] += values["tokens"]
                if result["first"]:
                    first = min(first or result["first"], result["first"])
                    last = max(last or result["last"], result["last"])
    if persist:
        try:
            with open(CACHE_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"version": CACHE_VERSION, "entries": fresh}, f)
            os.replace(CACHE_FILE + ".tmp", CACHE_FILE)
        except OSError:
            pass
    today = datetime.date.today()
    last30 = [(today - datetime.timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    week = last30[-7:]
    return {
        "sessions": sessions, "subagent_sessions": sub_files, "since": first, "last": last,
        "prompts": totals["prompts"], "subagents": sub_files, "tool_calls": sum(tools.values()),
        "tokens": dict(tokens), "subagent_tokens": dict(sub_tokens),
        "week": {"prompts": sum(days[d]["prompts"] for d in week), "tokens": sum(days[d]["tokens"] for d in week)},
        "days": [{"date": day, **days[day]} for day in last30],
        "top_tools": tools.most_common(8),
        "storage": {"notes": notes_storage(notes), "transcripts_bytes": transcript_bytes},
    }
