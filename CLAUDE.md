# Working on Brain

## Project context

Brain is Alex's personal digital brain: plain Markdown notes plus a local app for browsing, capturing thoughts, managing projects, and working with AI. Alex studies Computer Science at Queen's, class of '28, and is interested in AI, ML, learning, and creative projects he can shape and understand.

Read `README.md` for the architecture and setup, `FORMATS.md` before changing note formats, and relevant `docs/specs/` documents before changing the corresponding behaviour. Treat upstream biography and fictional `example/` notes as examples, not facts about Alex. The project skills live in `.claude/skills/` (`/wild` for wild brainstorming).

## Implementation

- Keep the Python backend compatible with Python 3.9+ and standard-library-only unless the task explicitly calls for a dependency change.
- The desktop UI lives in `app/index.html` and `app/theme.css`; the phone UI lives in `mobile/`. Preserve the vanilla frontend and absence of a build step.
- Note parsing and index generation live in `build.py`; desktop actions live in `app/server.py`; phone actions reuse that logic through `app/phone.py`. Keep phone and desktop behaviour consistent when changing shared features.
- Preserve local-only binding, API token checks, Host validation, note path restrictions, and protection against overwriting concurrent edits.
- Background agent permissions are separate from this interactive development workflow. Preserve their configured boundaries; this file does not authorize background agents to commit, push, or publish.
- Keep changes focused on the task and update documentation when user-visible behaviour or setup changes.

## Notes and private data

`personal-notes/` is ignored by the application repository and may be a separate private Git repository. Never stage it, credentials, private calendar URLs, tokens, or runtime files in this repository. Use `example/` or temporary fixtures for development checks rather than modifying Alex's live notes. Follow the configured notes root when personal context is needed.

## Validation

Run checks appropriate to the change before committing:

- Python behaviour: `python3 -m unittest discover -s tests` (or `py -m unittest discover -s tests` on Windows).
- Math rendering: `node tests/test_math.cjs`.
- App or UI changes: start `python3 app/server.py --notes example --no-open` and verify the affected flow; check the phone UI when relevant.
- Documentation-only changes: review the content and run `git diff --check`; an application test run is unnecessary.

Report any failed or unavailable checks honestly. Do not claim a check passed unless it ran successfully.

## Completing a task: commit and push to main

When an implementation or file-editing task is done, commit its changes and push to `main`. This is Alex's standing authorization for the normal Git completion workflow; do not ask for confirmation again unless a tool or permission boundary requires it. Questions and brainstorming without file changes need no commit.

1. Check the working tree, current branch, and remote before making changes. Preserve unrelated user work and stage only files belonging to the completed task.
2. Finish the work, run the relevant validation, and inspect the diff for unintended changes or private data.
3. Integrate the completed task into local `main` without discarding unrelated work. If working on another branch, preserve that work and merge the task into `main` before pushing.
4. Make a descriptive commit and push local `main` to `origin/main` using `git push origin main`.
5. If the push is rejected because the remote advanced, fetch and reconcile the changes without losing work, rerun affected checks, and retry. Never force-push or use a destructive reset to complete this workflow.
6. Verify the result and report the commit hash, validation performed, and whether the push succeeded. If permissions, authentication, or a conflict prevent completion, state the blocker; do not describe an unpushed commit as pushed.
