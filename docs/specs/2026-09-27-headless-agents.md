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
- **Agents** stay out of the way: a small dim "agents" chip in the top bar (amber and pulsing while working, "N agents working"). Clicking it opens the Agents tile: one row per run with a status dot (queued, running, done, failed), the input text and the time. Clicking a row expands the report. While any run is queued or running, the page refreshes state every 5 seconds.

## Git
Agents never commit. The next interactive session commits notes, as now. `agents/` is committed like any other note.

## Testing
- Unit tests with `claude` swapped for a fake command: queue order, one at a time, status file transitions, timeout marks failed, restart recovery, opt-in off queues nothing.
- One live run: capture a trivial note, watch it go queued → running → done, and read the report.

## Starting an agent directly (added 2026-10-22)
The Agents tile has a task box (and the ⌘K palette an **Agent** kind; the phone's Capture an **Agent task** type). `/api/agent` queues a job of type `task` with its own prompt: the text is the task. This works without the opt-in folder: the first one creates `agents/` with an `agents/.spawn-only` marker, and while that marker exists captures still don't start agents. Same runner, queue and allowlist as above. The phone parks tasks in `agents/pending/` like captures. With no runs, the tile offers to start one instead of saying "All clear".

## Internship run (added 2026-10-22)
A **Run internships** button in the Agents tile (shown when `internships/tracker.md` exists) posts `/api/agent {"preset": "internships"}` and queues a job of type `internships`: the `.claude/skills/apply-internships/SKILL.md` instructions as the prompt, `--model claude-sonnet-5-5 --chrome`, a 60-minute timeout, and its own allowlist (`Read`, `Glob`, `Grep`, `Edit(internships/**)`, `Write(internships/**)`, `mcp__claude-in-chrome`). One at a time: a second click while one is queued or running is refused. Button only, by design: no schedule, and it is never parked from the phone or drained from `agents/pending/`, so Alex is at the computer while it drives his browser. It never submits an application (the skill's rule, restated in the prompt).

## Internship reply check (added 2026-10-25)
A **Check replies** button beside it (shown once the tracker has an applied row) posts `/api/agent {"preset": "replies"}` and queues a job of type `replies`: `REPLIES_PROMPT`, `--model claude-sonnet-5-5`, a 20-minute timeout, and its own allowlist (`Read`, `Glob`, `Grep`, `Edit(internships/**)`, `Write(internships/**)`, `mcp__claude_ai_Gmail__search_threads`, `get_thread`, `get_message`). No browser and no draft or send tools. It reads the inbox on the `Email:` line of `internships/profile.md` (kept in the notes, not this repo) and sets each applied row's `Heard back?` cell to `Rejected · YYYY-MM-DD`, `Replied w/ <what> · YYYY-MM-DD` or `Pending`, then appends to `## Reply checks`. The server turns that cell into `reply`, `reply_kind` (`replied`, `rejected`, `pending`) and `reply_date` on each internship row; applied rows with no cell or "Not recorded" read as Pending. Same rules as the internship run: one at a time, button only, never parked or drained.

## LinkedIn prep (added 2026-10-25)
A **Prep LinkedIn** button posts `/api/agent {"preset": "linkedin"}` and queues a job of type `linkedin`: `LINKEDIN_PROMPT`, `--model claude-sonnet-5-5 --chrome`, 30 minutes, and an allowlist of `Read`, `Glob`, `Grep`, `Edit(linkedin/**)`, `Write(linkedin/**)` and only the reading Chrome tools (`tabs_context_mcp`, `tabs_create_mcp`, `tabs_close_mcp`, `navigate`, `get_page_text`, `read_page`, `find`). `computer`, `javascript_tool`, `form_input` and `browser_batch` are left out, so the agent can't click, type or script a page: liking, commenting, posting, connecting and messaging are impossible, not just forbidden. The server passes `week_commits()` (every active project folder's commits from the last 7 days, with authors) as the factual basis for post drafts. Output: `linkedin/<date>.md` with Posts to publish, Posts to comment on and Profile sections, written from `linkedin/voice.md`. One at a time, button only, never parked or drained (it needs Alex's Chrome).

## Dev log (added 2026-10-26)
A morning post about recent work on the GitHub profile README, in `app/devlog.py`. On only when the notes have `devlog/profile.md` with a `Repo: <user>/<user>` line. A server thread checks every five minutes; after 07:00, with no `devlog/<today>.md` and no `devlog` run queued today (a quiet or failed run counts), it queues a job of type `devlog`. The **Write dev log** button (shown when the profile exists) posts `/api/agent {"preset": "devlog"}`. One at a time, never parked or drained.

The facts are the user's own non-merge commits in their **public**, unarchived repos since the last post (at most 7 days), read from the GitHub API, never local repos, so private work can't reach a public page. No commits: the run ends `done` with that reason and `claude` isn't called. Otherwise `claude --model claude-sonnet-5-5 -p` with no `--allowedTools` (under `dontAsk`, no tools) gets `devlog.PROMPT`: 2 to 4 plain sentences, nothing the commits don't show, or exactly `SKIP`. Brain, not the agent, saves the answer as `devlog/<date>.md` and replaces the text between `<!-- devlog-posts:start -->` and `<!-- devlog-posts:end -->` in the profile README with the three newest posts, through the contents API with `$GITHUB_TOKEN` or `gh auth token`. No token: the post is saved but not published. Missing markers or an API error mark the run failed.

## Committing agent work (added 2026-10-25)
Agents still never run git. When the notes are synced (`app/sync.py` on), `Agents.run` takes `Sync.snapshot()` (every changed or untracked file with its blob hash) before the run and `Sync.changed_since()` after it, and commits those paths plus the run's `agents/` record as `agent: <first 60 characters of the task>`, then pushes in the background. Files already dirty before the run are left alone unless the run changed them again. Deleted files aren't committed. A file Alex edits during a run is indistinguishable from the agent's and is committed with it.

## Out of scope
Approving drafts from inside Brain, parallel agents, per-type permissions, cancelling a running job.
