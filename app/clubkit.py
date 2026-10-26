"""clubkit (Alex's agent-first club monorepo) seen from Brain: the clubkit tile and clubkit's MCP tools for agents.

The repo is found through a project note's `paths:` (the first folder whose package.json is named "clubkit"), so
nothing here names a machine path. Read-only: Brain reads the repo's git state, catalog.json, TODOS.md and the
eval runner's evals/results/*.json, and never writes to it. Agents reach clubkit only through its MCP server.
"""
import json
import os
import pathlib
import re
import subprocess

RUNS = 12  # eval runs kept for the tile, newest first
# clubkit's MCP tools a Brain agent may call: discovery, contracts, playbooks, and a module's own verify command.
AGENT_TOOLS = ["mcp__clubkit__list_modules", "mcp__clubkit__get_module", "mcp__clubkit__verify_module",
               "mcp__clubkit__list_skills", "mcp__clubkit__read_skill"]
AGENT_NOTE = (
    "\n\nYou also have clubkit's MCP tools (mcp__clubkit__*): Alex's agent-first monorepo for running a student club. "
    "For anything about clubkit, start with list_modules, then get_module or read_skill, and use verify_module to "
    "check a module rather than guessing. You can't edit the clubkit repo; put proposed changes in your report."
)

_runs = {}  # results file path -> (mtime, summary): the result files are large and never change once written


def is_repo(folder):
    try:
        with open(os.path.join(folder, "package.json"), encoding="utf-8") as f:
            return json.load(f).get("name") == "clubkit"
    except (OSError, ValueError, AttributeError):
        return False


def find(projects):
    """(folder, project) for the first project folder that is a clubkit repo, else (None, None)."""
    for p in projects:
        for folder in p.get("folders") or []:
            if is_repo(folder):
                return folder, p
    return None, None


def _git(folder, *args):
    try:
        p = subprocess.run(["git", "--no-optional-locks", "-C", folder, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def _modules(folder):
    try:
        with open(os.path.join(folder, "catalog.json"), encoding="utf-8") as f:
            mods = json.load(f).get("modules") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [{"name": m.get("name", ""), "status": m.get("status", ""), "summary": m.get("summary", "")}
            for m in mods if isinstance(m, dict)]


def _todos(folder):
    """Open checklist items in TODOS.md, in order, as plain text."""
    try:
        with open(os.path.join(folder, "TODOS.md"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    out = []
    for m in re.finditer(r"^\s*- \[ \] (.+(?:\n {4,}\S.*)*)", text, re.M):
        item = re.sub(r"\s+", " ", m.group(1)).strip()
        out.append(re.sub(r"`|\*\*", "", item))  # drop code ticks and bold, keep globs like results/*.json
    return out


def _run(path):
    """One eval run's summary, or None for a file that isn't one."""
    mtime = os.path.getmtime(path)
    hit = _runs.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        side = lambda v: {k: (r["summary"].get(v) or {}).get(k, 0) for k in ("passed", "total", "costUsd")}
        out = {"id": r["runId"], "agent": r.get("agent", ""), "model": r.get("model") or "", "commit": r.get("commit", ""),
               "date": r.get("date", ""), "tasks": len({a.get("task") for a in r.get("attempts", [])}),
               "clubkit": side("clubkit"), "baseline": side("baseline")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        out = None
    _runs[path] = (mtime, out)
    return out


def _evals(folder):
    d = os.path.join(folder, "evals", "results")
    try:
        names = sorted((n for n in os.listdir(d) if n.endswith(".json")), reverse=True)
    except OSError:
        return []
    runs = [r for r in (_run(os.path.join(d, n)) for n in names) if r]
    return runs  # newest first; noop/reference are the runner's sanity checks, kept so the tile can show them


def state(projects):
    """The clubkit tile's data, or None when no project points at a clubkit repo."""
    folder, project = find(projects)
    if not folder:
        return None
    head = _git(folder, "log", "-1", "--format=%h%x00%s%x00%cI").split("\x00")
    runs = _evals(folder)
    todos = _todos(folder)
    return {
        "path": folder, "project": project.get("path", ""), "title": project.get("title", "clubkit"),
        "branch": _git(folder, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": len([l for l in _git(folder, "status", "--porcelain").splitlines() if l.strip()]),
        "commit": {"hash": head[0], "subject": head[1], "date": head[2]} if len(head) == 3 else None,
        "modules": _modules(folder),
        "evals": [r for r in runs if r["agent"] not in ("noop", "reference")][:RUNS],
        "sanity": {k: next((r for r in runs if r["agent"] == k), None) for k in ("noop", "reference")},
        "todos": todos[:8], "todo_count": len(todos),
        "mcp": bool(mcp_config(folder)),
    }


def mcp_config(folder):
    """--mcp-config JSON that starts clubkit's MCP server from any working directory, or None if it can't run.
    The server finds its repo from its own file path; tsx is given as an absolute file URL for the same reason."""
    server = os.path.join(folder, "packages", "mcp", "src", "server.ts")
    loader = os.path.join(folder, "node_modules", "tsx", "dist", "loader.mjs")
    if not (os.path.exists(server) and os.path.exists(loader)):
        return None
    return json.dumps({"mcpServers": {"clubkit": {"command": "node", "args": [
        "--import", pathlib.Path(loader).as_uri(), server]}}})
