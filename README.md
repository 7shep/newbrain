# brain

[![tests](https://github.com/zacfink/brain/actions/workflows/tests.yml/badge.svg)](https://github.com/zacfink/brain/actions/workflows/tests.yml)

A personal "digital brain" for working with [Claude Code](https://claude.com/claude-code): a folder of plain
markdown notes that Claude reads instead of re-deriving context every session, plus a small local app to browse and
act on them.

![Brain app running on the example notes](docs/screenshot.png)

- **Cover story:** Claude writes a magazine-style headline about your week after real work.
- **Notes to self:** reminders Claude adds only when they help. You can mark them Done (with confetti), snooze them, or say "Not doing this", which retires them for good.
- **Projects:** hide the ones you're not working on; they wait under "Show hidden".
- **How Claude adapts to you:** habits Claude follows every session. Claude can *propose* a new one, and you switch each on or off. You can also brainstorm a habit in the app, and Claude talks it through with you next session. Past habits stay out of the way.
- **⌘K capture:** type a thought, idea, to-do or person. Claude files it into the right note next session.
- **Ideas board:** mark ideas done or dismiss them.
- **Edit in place:** every note, person and project page opens in a side panel with a live markdown preview. ⌘S saves the file.
- **Reopen anything:** copy the command to resume a past Claude Code chat, open a project in VS Code, or open its live site.
- **Map of everything:** if you've run graphify (the Claude Code skill) on your notes (`graphify-out/graph.json`), a Map tile draws the knowledge graph in the app's colours. Hover a dot to see its links, click to open its note, and use the legend to focus one cluster.
- **Everything we've done:** one self-contained note per session, in a full-width timeline.
- **People & me:** your profile and contacts, one click away but out of the main view.

Everything is plain markdown on your machine. The app is ~1 Python file plus ~1 HTML file, uses only the standard
library, and has no build step.

![A person page open in the side panel](docs/page.png)

## How I actually use it

I've run every Claude Code session through this since May 2026: 47 sessions across 12 projects, with 15 habits Claude
follows on every session. A few things it has shipped:

- **[qweb.dev](https://qweb.dev)**, the 2026 site for Queen's Web Development Club, which I co-chair: rebuilt in
  React + Supabase and shipped through PRs.
- **[zacfinkelstein.ca](https://zacfinkelstein.ca)**, my portfolio.
- The weekly admin of a full course load: syllabi into my calendar, lab prep, reminders.

The habits are the part I'd copy. Each one exists because something went wrong once. For example, I brought Claude a
popular "LLM council" skill (11 subagents per question). It argued me out of it: same model, fake independence, and
10–20× the tokens for an answer I can get by asking. That argument became a habit: **when I pitch a project, Claude
argues against it first.**

## Try it (30 seconds)

```bash
git clone https://github.com/zacfink/brain.git
cd brain
python3 app/server.py --notes example      # opens http://127.0.0.1:4747
```

`example/` is a fictional student's notes. Requires Python 3.9+.

## Use it for real

The brain folder lives *inside* your notes folder as `.brain/`, so the app finds your notes as its parent:

```bash
mkdir -p ~/Notes && git clone https://github.com/zacfink/brain.git ~/Notes/.brain
ln -s ~/Notes/.brain/bin/brain ~/.local/bin/brain    # any folder on your PATH
brain                                                # start + open;  brain stop / restart / log
```

Start your notes from the shapes in [`FORMATS.md`](FORMATS.md). You can also copy `example/` and edit it, or just ask
Claude Code to draft them from your projects, calendar and email. `BRAIN_NOTES=/some/folder brain` points the app
somewhere else.

### Connect Claude Code

1. **Session-start hook** tells Claude your active habits and any inbox captures. It adds a few hundred tokens and makes no model call.
   Add to `~/.claude/settings.json`:
   ```json
   "hooks": {
     "SessionStart": [{ "hooks": [{ "type": "command", "command": "python3 ~/Notes/.brain/session_start.py 2>/dev/null || true", "timeout": 5 }] }]
   }
   ```
2. **Instructions** in your `CLAUDE.md` or Claude's memory, for example:
   > `~/Notes` is my brain. Before project work, read `~/Notes/INDEX.md` and the project page. File any inbox
   > captures into the right note. Follow `on` habits in `claude/habits.md`, and propose (never enable) new ones.
   > Add nudges to `nudges.md` only when they clearly help me, and never re-add one marked `no`. After real work,
   > write a session note (`.brain/session-template.md`), update the project page and `now.md`, then run
   > `python3 ~/Notes/.brain/build.py`.

## How it fits together

```
~/Notes/                      your notes (keep private)
├── INDEX.md                  generated table of contents — Claude reads this first
├── me.md  now.md  nudges.md  ideas.md  inbox.md
├── claude/habits.md
├── projects/<slug>.md        current truth per project
├── people/<slug>.md
├── sessions/YYYY-MM-DD-*.md  one note per Claude Code session (history)
├── agents/                   optional: turns on background agents; one log file per run
└── .brain/                   this repo
    ├── app/server.py         stdlib HTTP server: reads/writes the notes, serves the app
    ├── app/index.html        the whole UI (vanilla JS, no build)
    ├── app/agents.py         background agent runner (queue, one at a time, status files)
    ├── build.py              regenerates INDEX.md
    ├── session_start.py      Claude Code SessionStart hook
    ├── bin/brain             launcher
    ├── FORMATS.md            file shapes the app parses
    ├── example/              fictional notes to try it with
    └── tests/                unit tests, run on every push by GitHub Actions
```

**Why markdown files instead of a database?** Claude reads and edits them with the tools it already has. Opening
a file costs nothing until it's needed, and you stay in control of your own data.

## Background agents (optional)

Create an `agents/` folder in your notes and anything you capture in the app (a note, idea, todo, person or habit
proposal) also starts a headless Claude Code agent (`claude -p`). It files the thought where it belongs, or does the
task, writes a short report and exits. Runs go one at a time with a 20-minute limit, and a small "agents" chip in the
top bar turns amber while one is working. Click it for the reports.

The agent's permissions are an allowlist, not a denylist. It runs with `--setting-sources project --permission-mode
dontAsk`, so your own Claude settings can't widen it and anything off the list is refused. It can read, edit notes and
project files, search the web, create Gmail drafts and add calendar events. It can't send email or texts, commit,
push or run arbitrary shell commands. Outward actions come back as drafts for you to send.

Each run writes `agents/<time>-<slug>.md` (queued, running, then done or failed), so the state survives a restart. The
runner's tests use a fake `claude`, so they're free: `python3 -m unittest discover -s tests`.

## Security

The server binds to `127.0.0.1` only. Every API call needs a random per-run token embedded in the page, and requests
whose `Host` isn't local are rejected, which blocks DNS rebinding. Reads and writes are limited to `.md` files inside
the notes folder, never dot-folders. Saves detect edits made on disk since you opened a file, so you won't
overwrite Claude's changes.

Your notes folder will likely hold contacts and personal details. Keep it out of public repos.

## Notes

Tested on macOS with Chrome and Safari. Fonts load from Google Fonts, with system fallbacks when offline. Resume
buttons read session ids from `~/.claude/projects`.

## License

[MIT](LICENSE)
