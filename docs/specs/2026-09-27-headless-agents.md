# Headless agents for Brain captures

Approved in chat with Zac on 2026-09-27.

## Goal
Anything added through Brain gets acted on right away by a headless Claude Code agent, which exits when it's done. Brain's existing buttons and flows don't change. The one visible addition is an **Agents** list.

## Trigger
After the existing save succeeds, these queue one job each, with the saved text and its type:
- `/api/capture`: every type (note, idea, todo, person). "+ Idea" goes through this too.
- `/api/habit-new`: habit proposals, as type `habit`.

Status changes (done, dismiss, snooze, habit on/off, archive) never queue anything.

**Opt-in:** agents run only when the `agents/` folder exists in the notes root. `brain` is a public tool, and nobody else should start spending on agents by surprise.

## Runner
- One job at a time: a single worker thread plus a FIFO queue, in `app/agents.py`.
- Command: `claude -p <prompt> --allowedTools <list>`, run from the notes folder, with a 20-minute timeout. On timeout the process is killed and the run is marked failed.
- Prompt: "Zac just added this in Brain ([type]): [text]. Read ~/Notes/INDEX.md and the relevant project page first. If it's only a thought to keep, file it where it belongs in ~/Notes and stop. If it's a task, do it. Anything that would leave this machine (email, texts, git push, a live site) becomes a draft (a Gmail draft, or text in your report), never an action. Don't git commit. End with a report of at most 3 lines: what you did, and any files changed or drafts made."
- A job is **queued** when accepted, **running** while `claude` runs, then **done** (exit 0) or **failed** (nonzero exit, timeout, or `claude` missing).

## Permissions (allowlist)
Runs with `--setting-sources project --permission-mode dontAsk` from the notes folder (plus `--add-dir ~/Projects`), so allow rules in the user's own settings don't apply and anything outside this list is refused. Verified 2026-09-27: `curl` and `python3` were both refused.
- `Read`, `Glob`, `Grep`, `Edit`, `Write`, `WebSearch`, `WebFetch`
- `Bash(ls:*)`, `Bash(cat:*)`, `Bash(grep:*)`, `Bash(git status:*)`, `Bash(git log:*)`, `Bash(git diff:*)`
- Gmail: search, get thread and message, **create draft**
- Google Calendar: list and search events, **create event**

Not allowed: sending email or texts, git commit or push, publishing, deleting, and any other shell command.

## Results
- Each job writes `agents/YYYY-MM-DD-HHMM-<slug>.md` with frontmatter (`status`, `type`, `started`, `finished`), then the input, then the report (the agent's final output, truncated to 2,000 characters).
- The file is created at queue time as `queued` and rewritten on each status change, so it shows the right state even if Brain restarts. On startup, anything left `running` or `queued` is marked `failed (Brain restarted)`.
- `/api/state` gains `agents`: the 10 newest runs (status, time, type, input, report).
- **Agents tile** in `index.html`, placed with the other tiles: one row per run with a status dot (queued, running, done, failed), the input text and the time. Clicking a row expands the report. While any run is queued or running, the page refreshes state every 5 seconds.

## Git
Agents never commit. The next interactive session commits notes, as now. `agents/` is committed like any other note.

## Testing
- Unit tests with `claude` swapped for a fake command: queue order, one at a time, status file transitions, timeout marks failed, restart recovery, opt-in off queues nothing.
- One live run: capture a trivial note, watch it go queued → running → done, and read the report.

## Out of scope
Approving drafts from inside Brain, parallel agents, per-type permissions, cancelling a running job.
