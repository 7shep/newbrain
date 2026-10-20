# Adaptive tiles (desktop + phone Brain)

## Why
Brain's page is a fixed stack of tiles, so what matters right now sits next to what doesn't. Zac wants the page to arrange itself: the most important thing gets the most room, quiet things shrink, every tile is shaped by what it holds (Tetris pieces, not just rectangles), the pieces interlock with no holes, and opening any tile gives its full UI without leaving the page.

The approved prototype is `~/Notes/.brain/.superpowers/brainstorm/6019-1792460956/content/demo-real.html` (real data, desktop + phone width). It is the reference for look, layout and behaviour. Its markup feedback from Zac is folded into this doc.

## What Zac decided
- **Board**: tiles sit in a centred board, 75% of the window wide on big screens, growing to the full width on smaller ones. Top bar spans the window and never moves.
- **Columns follow the board width**: 12 at ≥1500px, 10 at ≥1100, 8 at ≥800, 6 at ≥560, else 4 (phone). Row unit 28px, gap 14px. Re-solve on resize.
- **Score decides room**: each item gets a score 0–100 from live state; higher scores are placed first, top-left, and get bigger shapes.
- **Shapes come from content**: a tile is made of *parts* (rectangles): `hero`, `head` (title + big count + one-line summary + spotlight), `list` (rows or events), `big` (number block, may show rows if roomy), `map`. Parts together form the piece: Today/Up next is a T (header bar, events down the stem), lists are Γ or step shapes, numbers are blocks. Each part is sized to its text (lines estimated from the column width).
- **Solver**: try ~700 combinations of each tile's template, mirror and small order swaps; cost = holes×40 + height×7 + Σ score×row×0.06 + template-index×1.5. Seeded RNG so the same data gives the same layout (no jitter). Then close gaps by growing a real part into free cells (right, down, left, up); any cell still empty becomes an arm of the most important neighbour. No holes, ever.
- **One continuous outline per piece**: SVG path around the union of the piece's cells with 20px rounded convex and concave corners; gaps inside a piece are filled.
- **Hero** (cover, unless something outranks it): one block. Headline + side notes (right column on desktop, below on phone), buttons bottom-left. Sized to its text. No empty arm.
- **Head parts are never half empty**: big count + summary, and a **spotlight** card with the one thing that matters now (People: the VIP right now, e.g. today's call; Notes: most overdue; Up next: next event; Internships: next deadline; Agents: most recent run; Projects: most active). Spotlight sits right of the summary when wide, below it when narrow.
- **Lists fill their space**: as many whole rows as fit, then an **"All N →"** button (never "+N more"). Lists always sit under their own title.
- **Small tiles use their room**: Routines and Ideas show rows; Streak shows a 14-day dot strip; Map shows the mini graph plus its top clusters with counts. Empty items become a solid tile reading "✓ All clear" (readable contrast, not dashed/faded).
- **Ranking**: People waiting ranks just under the cover and above Internships ("VIP right now").
- **Header**: "Brain · Tuesday, October 20 · 2 overdue · 4 today".
- **Opening a tile**: the tile's real box grows (left/top/width/height animate, no scaling, no squash) from where it sits to 75% of the window (phone: full screen, rounded corners). The grid does not move or tilt; it only dims. Content fades in after, out before it shrinks back into its spot on Done/Esc/click outside. The overlay holds the existing full UI for that section (today's tile content moves into it and back, so every action keeps working).
- **Acting re-flows**: when Zac does something (marks a note done, etc.), scores recompute and pieces glide to their new spots/shapes (View Transitions; snapshots cross-fade with `object-fit:none`, never stretched). Background refreshes never reshuffle while he's looking; only load, returning after 10+ min, or his own actions.
- **Top bar**: greeting + date line on the left; centred **Dynamic Island** agent pill (grows while an agent works, "Done ✓", shrinks back; click drops down a list of runs; it replaces the agents chip); Capture (⌘K) and a Settings button on the right. Phone: no + in the top bar (floating orange + bottom-right instead), island sits right of the title, title truncates with "…".
- **Settings** opens like a tile (grows from the button): theme picker (existing families/modes), cover length (short/medium/long), layout (Tiles / Scroll = today's page). Scroll is a fallback that shows the old full tiles.
- **Every theme**: only theme tokens, no hard-coded colours. Fonts stay Bodoni Moda + Schibsted Grotesk for everyday themes.
- **60fps** on open/close/re-flow in `tools/frames`.

## Scores (first version, tune later)
Cover 80 (90 if nothing else is due) · Up next: today 75, tomorrow 60, ≤3 days 45, else 25, +20 if exam/quiz/midterm/test/interview today · People waiting: min(78, 10×follow-ups) · Internships: min(70, 10 + 15×deadlines in 7 days) · Notes to self: min(90, 15×overdue + 5×open) · Agents: min(70, 20×queued/running/failed) else 5 · Routines: 70 if a run failed else 15 · Projects 30 · Ideas 10 · Streak 12 · Habits 5 + 20×proposed · Map 8 · Inbox: 1 and "All clear" when empty. Ties keep this order.

## Not doing
Learning scores from what Zac opens; drag-to-rearrange; changing the server's data model beyond what the tiles need.

## Done when
Desktop (all 11 themes) and phone show the adaptive board with real data, every existing tile action works from inside the opened tile, Scroll layout still works, tests pass, and `tools/frames` holds ~60fps on open/close/re-flow.

## Added after the build started (lead applies these)
- **Opened tiles**: start with a summary strip (count · summary · spotlight), then the full section; size to content (max 75% of the window), long ones scroll. Not every tile opens: only ones with more behind them (People, Notes, Internships, Up next, Projects, Ideas, Agents); Streak, Inbox/"All clear" and other glance tiles aren't clickable; Map jumps to the full-screen map.
- **Freelance tiles**: anything urgent gets its own tile. Claude writes them to `claude/tiles.md` (title, 1–2 lines, urgency, expires, optional action); Brain scores them high by urgency, shows them like any tile, and drops them when they expire or Zac marks them done.
- **Everything fits its box**: after each layout, measure every part (scrollHeight/scrollWidth vs its box). If text overflows, re-size that piece (more rows) and re-solve, or trim lists to whole rows + "All N →". Never clip text mid-line or overflow a piece. A test/screenshot check enforces it in every theme, desktop and phone.
