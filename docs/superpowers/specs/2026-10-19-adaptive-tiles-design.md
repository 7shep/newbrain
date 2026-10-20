# Adaptive tiles (desktop Brain)

## Why
Brain's desktop page is a fixed stack of tiles, most of them full-width, so what matters right now sits next to what doesn't. Zac wants the page to arrange itself: the most important thing gets the biggest tile, quiet things shrink, and opening any tile gives its full UI without leaving the page. Mockup he approved: `.superpowers/brainstorm/6019-1792460956/content/bento-14.html` (Soft dark, orange hero, black tiles).

## What he decided
- One screen of tiles that fills the window (more margin top and bottom, a little at the sides), laid out like his sketch: hero top-left, four squares top-right, a tall column on the right, wide tiles and small squares below.
- Which item goes in which slot is decided by a score ("math for what shows"), recomputed whenever the data changes. The highest score takes the hero; the squares are for low scorers. None of the slots are fixed launchers.
- Big tiles show real text: a one-line summary plus as many rows as fit (fade at the bottom, no cut-off lines).
- Clicking a tile grows that tile itself (its real box, no scaling or squashing) out to 75% of the screen, centred under the top bar. Its contents are the tile's full UI. Done / Esc / click outside shrinks it back into its spot. The grid does not move, tilt or shift; it only dims.
- The top bar stays put above everything: greeting on the left; Capture and a Settings button on the right. Settings opens the same way (a tile growing from the button) and holds the theme picker.
- Works in every theme (only theme tokens, no hard-coded colours).

## Design (builder's calls, marked)
- **Reuse, don't rewrite** (call): every existing tile section (`#cover`, Up next, Notes to self, Projects, Internships, Agents, Routines, Ideas, Habits, Map, Timeline) keeps its current render function and markup. They move into a hidden holder; the grid shows new *summary* tiles. Opening a summary moves the real section into the overlay (listeners and state come with it) and moves it back on close. So every action that works today still works.
- **Items and summaries** (call): one entry per section: title, score, big number, one-line summary, rows. "People waiting" is a new item from `S.people` follow-ups (opens the existing People & me panel content).
- **Scores, 0–100** (call; tune later):
  - Cover: 80 if there's a headline, else 0.
  - Up next: soonest item today 75, tomorrow 60, within 3 days 45, else 25; +20 if it's an exam/quiz/midterm/test/interview due today.
  - Notes to self: 15 per overdue + 5 per open, max 90; 0 if none open.
  - People waiting: 8 per follow-up, max 60.
  - Internships: 10 + 15 per deadline in the next 7 days, max 80.
  - Agents: 20 per queued/running/failed run, max 70; 5 otherwise.
  - Routines: 70 if any failed last run, else 15.
  - Projects: 30. Ideas: 10. Habits: 5 + 20 per proposed. Timeline: 12. Map: 8.
  - Ties keep this order. Items scoring 0 are hidden.
- **Hero** (call): when the cover wins, the hero *is* the cover (today's headline, dek and buttons). When another item wins (an exam today in Up next), the hero shows that item big: its top row as the headline, the next rows beside it, an Open button; the cover drops to a normal slot.
- **Top bar** (call): the theme chip becomes the Settings button. The stats and "how well Claude knows you" chips stay. The agents chip opens the Agents item. "People & me" stays and opens its panel as today; the People waiting tile opens the same panel.
- **Slots** (from the mockup): hero 7×6, tall 3×8, wide 7×3, mid 2×5, four squares 2×2 (top-right), bottom wide 5×3, two bottom squares 2×3. Up next prefers the tall slot when it ranks top-3. Items past the 11 slots go in an extra row of squares below (the page scrolls).
- **Overlay**: a fixed box whose left/top/width/height animate from the tile's rect to 75% of the window (0.5s, Brain's ease); content fades in after it grows and out before it shrinks. z-index under the note drawer and palette so opening a note from inside the overlay works.
- **Small screens** (call): under 1000px wide the grid falls back to one column in score order; overlay goes full width.

## Not doing
- Phone app: unchanged in this pass.
- Learning the scores from what Zac opens (later, once the fixed scores have been lived with).
- Drag-to-rearrange.

## Done when
- The desktop page shows the adaptive grid with real data in all 11 themes, and every action from today's tiles works from inside the overlay.
- Open/close animations hold ~60fps in `tools/frames`.
