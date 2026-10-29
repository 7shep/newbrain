---
name: brain-tile
description: Use when Zac says "I want a ___ tile", "add a tile for ___", "make a Brain tile", or types /brain-tile. Adds a custom tile (and its page) to Brain by writing one markdown file, plus a refresh script if the data is live.
---

# Brain tile

A custom tile is one file: `~/Notes/tiles/<slug>.md`. Brain draws a tile for every file in that folder and opens the
file itself as the tile's page. Nothing in `.brain/app` changes, so each person's tiles are their own.

## The file

```markdown
---
title: Recently played       # tile title
icon: music                  # one of the keys of ICONS in .brain/app/tiles.js (doc if unknown)
summary: optional one-liner  # else the first row is the summary
refresh: python3 tiles/<slug>.py   # optional: shell command run from ~/Notes, at most every 5 min
---
- First row · right-hand detail
- Second row · detail
```

- Every `- ` line is a row. ` · ` splits the row text from its right-hand detail. The first row is the tile's highlight.
- Anything after the list is free markdown: it shows on the page, not the tile.
- `refresh` must **rewrite the whole file** (frontmatter included), finish in under 15 s, and never print secrets.

## Steps

1. **Work out where the data lives** before writing anything. Prefer, in order: something already in `~/Notes`
   (a tracker, a section of now.md), a local app via `osascript` or a CLI, a public API with no key, an API that
   needs a key (keep the key in the macOS Keychain, read it with `security find-generic-password -w`, never in the file).
   If the data needs a login or a key Zac hasn't given, build the tile with a static list and ask for the key.
2. **Static data** (a list he gives, or something Claude keeps up to date): write `tiles/<slug>.md`, no `refresh`.
3. **Live data**: write `tiles/<slug>.py` (stdlib only) that builds the rows and rewrites `tiles/<slug>.md`,
   run it once, and show Zac the rows it produced. Then append the tile's exact `refresh:` command as a line in
   `~/.config/brain/refresh-allow` (create it if missing). Brain only runs refresh commands listed there, because
   tiles arrive by git pull; without the line the tile shows "Not refreshing".
4. If no icon fits, add one 24×24 stroke SVG path to `ICONS` in `.brain/app/tiles.js` (same style as the others).
5. `brain restart` only if `.brain/app` changed; otherwise the tile appears on Brain's next refresh.
6. Commit and push `~/Notes` (habit H-014).

Example already built: `tiles/music.md` + `tiles/music.py` (what Spotify is playing, added each refresh, keeps 20).
