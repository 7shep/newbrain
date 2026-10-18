---
name: are-you-done
description: Use when Zac asks "are you done", "anything left", "what's left", "did we miss anything", "backcheck", or types /are-you-done, and before claiming a multi-part session is finished. Backchecks the whole session for anything still undone, unverified or waiting on Zac, then does what Claude can do now and lists only what's actually left for him.
---

# Are you done?

A backcheck, not a summary. Go through the session and find everything that isn't actually finished, so nothing slips through the cracks. Do what you can fix now. Only list what really needs Zac.

## 1. Rebuild the list of asks

Scroll the whole conversation, including mid-turn messages ("The user sent a new message while you were working") and answers to questions. Write one line per thing Zac asked for. Asks that got overtaken by a later message count too, so mark them "replaced" rather than dropping them silently. Then mark each line:

- **done + verified:** you saw proof (a test passing, a screenshot, `git log` on the remote, the file on disk).
- **done, unverified:** you changed it but never looked at the result.
- **partial / skipped / blocked:** say why.

## 2. Check the evidence, don't trust memory

Run checks for every claim of "done":

- **Git:** `git status -sb` in each repo you touched. Look for uncommitted changes, unpushed commits, leftover branches, rejected pushes you never retried. Run `git -C ~/Notes status -sb` and `git -C ~/Notes/.brain status -sb` every time.
- **Builds and tests:** a build that failed and then "worked" might mean the old binary ran. Check that the timestamp or output changed.
- **Live things:** was the deployed page, phone state (`~/Notes/phone/state.json` `built`), GitHub Action or running app actually updated?
- **Leftovers:** background tasks still running, test data you wrote (for example `runtime/status.json`), temp servers on ports, Accessibility or other permissions that a rebuild reset.
- **Menu bar status:** if you wrote `~/Projects/screen-intelligence/runtime/status.json`, make sure it ends in `done` or idle, not stuck on `running`.

## 3. Brain write-back (H-005)

- Is there a session note for today in `~/Notes/sessions/`, and does it cover everything, including later changes and reversals?
- Were the touched project pages, `now.md` and the inbox captures filed? Was `python3 ~/Notes/.brain/build.py` run, then the notes committed and pushed (H-014)?
- Do the memories still match what Zac decided? Fix any memory a later message contradicted (for example a colour he changed his mind on).

## 4. Fix what you can, now

Commit, push, re-test, clean up and update notes yourself. Don't list something for Zac that you could have done in ten seconds. Outward actions (messages, posts, public repos) still need his OK.

## 5. Report

Keep it short (H-001):

- **Fixed just now:** one line each, if any.
- **Your turn:** only the things that really need Zac, and where (phone, System Settings, a reply). Give exact steps.
- **Unverified:** anything you couldn't check, and how he can.
- If nothing is left, say "Done. Nothing left for you" and stop.

## Common mistakes

| Mistake | Instead |
|---|---|
| Summarising what was built | List only what's not finished |
| "Pushed" from memory | `git status -sb` shows `[ahead N]` or not |
| Missing a mid-turn message | Re-read every "sent a new message while you were working" |
| Listing Zac todos you could do | Do them, then report them as fixed |
| Treating an ask that got replaced as done | Mark it "replaced by …" so he can see it |
