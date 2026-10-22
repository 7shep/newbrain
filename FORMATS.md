# Brain file formats

The app (`app/server.py`) parses these. Claude writes them. Keep to the shapes exactly;
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
Claude adds one only when it clearly helps. Status `no` is permanent: never re-add that nudge.
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

## `claude/habits.md` — how Claude adapts to you
`on` habits are followed every session. `off` ones show under "Past habits". `proposed` ones wait for you to decide.
A habit typed into the app's brainstorm box is saved as `proposed` with a `source:` starting `brainstorm` —
the SessionStart hook asks Claude to talk it through with you and refine it.
```
# Claude's habits

## H-001 · Lead with the answer, keep it short
- status: on              # on | off | proposed
- why: You asked for shorter responses.
- since: 2026-09-04
- source: conversation, 2026-09-04
```

## `claude/predictions.md` — how well Claude knows you
Claude logs a line whenever it bets on what you'll want, and marks it once you answer. Kinds: `recommend` (an option
it marked Recommended), `guess` (a stated guess about what you meant), `draft` (something it wrote that you kept or
rewrote), `habit` (a habit made it act and you went along or pushed back). Confidence is 50–100%. Brain turns this into
a score and a calibration chart (the score chip in the top bar).
```
# Predictions

- 2026-09-27 · 70% · recommend · bet: Status, then recent · got: Status, then recent · hit
- 2026-09-27 · 60% · recommend · bet: Todos only · got: Everything · miss
```

## `claude/routines.json` — your routines (written by Brain, don't edit)
Brain asks Claude Code for your routines (when the app opens and the copy is over 10 minutes old) and keeps the
answer here so the phone can show it. `why_pause` and `suggestions` come from a once-a-day pass over your notes.
```json
{"checked": "2026-10-19T13:54:50", "error": "", "suggested": "2026-10-19",
 "routines": [{"id": "trig_…", "name": "Morning update", "schedule": "Daily 7am", "enabled": true,
               "last_run": "2026-10-19 07:02", "ok": true, "next_run": "2026-10-20 07:00", "why_pause": ""}],
 "suggestions": [{"title": "Sunday week plan", "schedule": "Sundays 6pm", "text": "Every Sunday at 6pm, plan my week"}]}
```

## `now.md` — the cover story
Claude rewrites after real work. Headline is punchy, magazine-style, true. `*word*` renders italic.
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
Session notes list the habits Claude applied (`habits: [H-001, H-014]` in the frontmatter). The app sorts habits by
days since last use (or a manual `- used: YYYY-MM-DD` on the habit), counting from 2026-10-01 at the earliest, stalest
first, and fades ones idle 21+ days so they can be switched off.

## `ideas.md`
Open ideas are the bullets before any section. The app moves an idea to `## Done` or `## Dismissed`
(appending `(done YYYY-MM-DD)`), and can restore it. An optional verdict after the date, `[try]`, `[maybe]` or
`[skip]`, sorts the open list: try, maybe, untagged, skip. Claude adds it when saving an idea.
```
# Ideas
- 2026-09-14 · Idea text — optional note (project: slug)

## Done
- 2026-09-01 · Shipped idea (done 2026-09-14)

## Dismissed
- 2026-08-20 · Idea you passed on (dismissed 2026-09-14)
```

## `inbox.md` — quick captures from the app
The app appends; Claude files each line into the right note at the start of the next session and deletes it.
```
# Inbox
- 2026-09-14 19:02 · idea · text
```
Kinds: `note`, `idea`, `todo`, `person`, `routine`. Routine captures produce an Agents proposal when enabled; otherwise they stay in the inbox for the next interactive session.

## `projects/<slug>.md` and `sessions/YYYY-MM-DD-<slug>.md`
Project pages: frontmatter `name, status (active|paused|done|abandoned), updated, paths: [...], links: [...], summary`,
optional `archived: YYYY-MM-DD` (set by the app's hide button; hidden projects appear under "Show hidden"),
then `**TL;DR:**` and sections. Session notes: see `session-template.md`. A session's `session:` id (first 8 chars
of the Claude Code session id) powers the app's "resume chat" button.

## `internships/tracker.md`

The desktop app reads Markdown tables with a `Company` column. Optional columns are `Role`, `Term`
(or `Where`), `Deadline`, `Link`, and `Status`. Column names are case-insensitive; use absolute
`YYYY-MM-DD` deadlines for date labels. Plain HTTP(S) links open the posting. Statuses beginning with
`Applied`, `To apply`/`Prep`, or `Out`/`Dropped` form those groups; other statuses are `To check`.

## `now.md` daily plan

An optional `## Today · YYYY-MM-DD` section records today's plan. Only dated bullets under
`## Upcoming` feed Up next; dated lines in `## Done` or other sections are excluded.

## `daily/YYYY-MM-DD.md`

A separate checklist for each local calendar day. The app shows only today's file; older lists are retained without carrying unfinished tasks forward. The server's local date guards writes, so delayed phone actions for a past day are rejected rather than applied to today's list. Phone and server should use the same local date. IDs make retries idempotent and updates target one item.

```markdown
# Daily tasks — 2026-10-21

- [ ] Pick up groceries <!-- task:0123456789abcdef -->
- [x] Water plants <!-- task:fedcba9876543210 -->
```

Task text is one line (1–300 characters), up to 100 tasks per day. The 16-character lowercase hexadecimal ID is stable.

## Study sessions and Tutor Genome

`study/state.json` is versioned storage written by the authenticated study API. It contains `revision`, `sessions`, `observations`, and `changes`. Sessions have an immutable ID, course/topic, UTC start/end, last check-in, and Discord adapter result. Evidence links to a session and records topic, outcome (`independent`, `hinted`, `struggled`), actual reasoning, source, creation time, and optional retraction time. `study/log.md` is generated from it. Use the panel or the `/study` skill to change data; see [study sessions](docs/study.md).

## `claude/day-planner.md` (optional)

An editable Markdown note containing a fenced `json` object enables automatic daily checklists.
Required fields are `enabled`, `study_days` (1–14), `study_minutes` (15–480),
`assignment_minutes` (15–480), `gym_days` (0–7), `gym_minutes` (15–180),
and `laundry_weekday` (Monday = 0, Sunday = 6). Optional `courses` maps normalized
course codes such as `STAT252` to `study_days`, `study_minutes`, or
`quiz_material_weekday` overrides. The latter limits Friday quiz study to the
material release day onward; other test types retain the normal study window.

The planner reads assessment and assignment dates from `now.md` → `## Upcoming`.
It creates today's checklist only if that file does not exist, on desktop or during
phone state generation. It preserves checked tasks, removals and manual additions.
One study item per course represents the configured daily study duration. Assignments
appear the day before and, if unfinished, on their due date. Gym days are selected
from the lighter remaining days of the Monday–Sunday week, counting completed gym
tasks in earlier daily files. Missing days are not treated as completed workouts.
A `Plan: ...` paragraph in the daily file explains estimates and stale calendar data;
the daily API returns it as optional `plan_note`. Checklist operations preserve it.
