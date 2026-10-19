# Brain file formats

The app (`app/server.py`) parses these. Codex writes them. Keep to the shapes exactly;
free markdown is fine inside bodies. Dates are absolute `YYYY-MM-DD`.
All names below are fictional examples.

## `me.md`
```
---
name: Sam Rivera
tagline: One line, in your own voice
updated: 2026-09-14
---
# About Sam
## Snapshot        — who you are right now (bullets)
## Goals           — this year / this term. Mark guesses "(draft — confirm)"
## How I work      — preferences, routines, tools, how to reach you
## Interests       — topics, things you want to learn/build
## Skills & tools
## Background      — dated bullets, newest first
```

## `people/<slug>.md`
```
---
name: Priya Shah
relation: Northside Coffee — club sponsorship contact   # one line
circle: work                                            # any word; family | friends | work | school | other …
last_contact: 2026-09-04                                # blank if unknown
follow_up: Waiting on her to pick a meeting time        # one line, blank if none
links: [mailto:priya@example.com]
---
# Priya Shah
**TL;DR:** One sentence.
## Who they are
## History          — dated bullets, newest first
## Open loops       — "- [ ] ..." items
```

## `nudges.md` — reminders for you
Codex adds one only when it clearly helps. Status `no` is permanent: never re-add that nudge.
```
# Nudges

## N-001 · Reply to Priya about the sponsorship
- status: open            # open | done | snoozed | no
- due: 2026-09-14         # optional
- snooze_until:           # set by the app
- done_on:                # set by the app
- why: You said you'd send her two meeting times by Friday.
- project: design-club
- source: sessions/2026-09-04-sponsor-outreach.md
- created: 2026-09-14
```

## `codex/habits.md` — how Codex adapts to you
`on` habits are followed every session. `off` ones show under "Past habits". `proposed` ones wait for you to decide.
A habit typed into the app's brainstorm box is saved as `proposed` with a `source:` starting `brainstorm` —
the SessionStart hook asks Codex to talk it through with you and refine it.
```
# Codex's habits

## H-001 · Lead with the answer, keep it short
- status: on              # on | off | proposed
- why: You asked for shorter responses.
- since: 2026-09-04
- source: conversation, 2026-09-04
```

## `codex/predictions.md` — how well Codex knows you
Codex logs a line whenever it bets on what you'll want, and marks it once you answer. Kinds: `recommend` (an option
it marked Recommended), `guess` (a stated guess about what you meant), `draft` (something it wrote that you kept or
rewrote), `habit` (a habit made it act and you went along or pushed back). Confidence is 50–100%. Brain turns this into
a score and a calibration chart (the score chip in the top bar).
```
# Predictions

- 2026-09-27 · 70% · recommend · bet: Status, then recent · got: Status, then recent · hit
- 2026-09-27 · 60% · recommend · bet: Todos only · got: Everything · miss
```

## `codex/routines.json` — your routines (written by Brain, don't edit)
Brain reads local Codex automation metadata when its cached copy is over 10 minutes old.
The phone reads this snapshot after notes sync. Suggestions come from a once-a-day read-only
Codex pass over the notes. Schedule controls and run history remain in the Codex app.
```json
{"provider": "codex", "read_only": true, "checked": "2026-10-19T13:54:50", "error": "", "suggested": "2026-10-19",
 "routines": [{"id": "daily-review", "name": "Morning update", "schedule": "FREQ=DAILY;BYHOUR=7",
               "enabled": true, "last_run": "", "ok": null, "next_run": "", "why_pause": "", "read_only": true}],
 "suggestions": [{"title": "Sunday week plan", "schedule": "Sundays 6pm", "text": "Every Sunday at 6pm, plan my week"}]}
```

## `now.md` — the cover story
Codex rewrites after real work. Headline is punchy, magazine-style, true. `*word*` renders italic.
```
---
headline: The site is live. *Now* the club has to show up.
dek: One or two sentences of real detail.
project: design-club        # slug the cover's buttons reopen
updated: 2026-09-14
---
## Upcoming
- 2026-09-17 18:00 · Design club workshop 1 · Room 101
- 2026-09-21 · Sponsorship deck due · Send to Priya
```

## Habit freshness
Session notes list the habits Codex applied (`habits: [H-001, H-014]` in the frontmatter). The app sorts habits by
days since last use (or a manual `- used: YYYY-MM-DD` on the habit), counting from 2026-10-01 at the earliest, stalest
first, and fades ones idle 21+ days so they can be switched off.

## `ideas.md`
Open ideas are the bullets before any section. The app moves an idea to `## Done` or `## Dismissed`
(appending `(done YYYY-MM-DD)`), and can restore it. An optional verdict after the date, `[try]`, `[maybe]` or
`[skip]`, sorts the open list: try, maybe, untagged, skip. Codex adds it when saving an idea.
```
# Ideas
- 2026-09-14 · Idea text — optional note (project: slug)

## Done
- 2026-09-01 · Shipped idea (done 2026-09-14)

## Dismissed
- 2026-08-20 · Idea you passed on (dismissed 2026-09-14)
```

## `inbox.md` — quick captures from the app
The app appends; Codex files each line into the right note at the start of the next session and deletes it.
```
# Inbox
- 2026-09-14 19:02 · idea · text
```
Kinds: `note`, `idea`, `todo`, `person`, `routine`. Routine captures produce an Agents proposal when enabled; otherwise they stay in the inbox for the next interactive session.

## `projects/<slug>.md` and `sessions/YYYY-MM-DD-<slug>.md`
Project pages: frontmatter `name, status (active|paused|done|abandoned), updated, paths: [...], links: [...], summary`,
optional `archived: YYYY-MM-DD` (set by the app's hide button; hidden projects appear under "Show hidden"),
then `**TL;DR:**` and sections. Session notes: see `session-template.md`. A session's `session:` id (first 8 chars
of the Codex session id) powers the app's "resume chat" button.

## `internships/tracker.md`

The desktop app reads Markdown tables with a `Company` column. Optional columns are `Role`, `Term`
(or `Where`), `Deadline`, `Link`, and `Status`. Column names are case-insensitive; use absolute
`YYYY-MM-DD` deadlines for date labels. Plain HTTP(S) links open the posting. Statuses beginning with
`Applied`, `To apply`/`Prep`, or `Out`/`Dropped` form those groups; other statuses are `To check`.

## `now.md` daily plan

An optional `## Today · YYYY-MM-DD` section records today's plan. Only dated bullets under
`## Upcoming` feed Up next; dated lines in `## Done` or other sections are excluded.
