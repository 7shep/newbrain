# Codex background agents for Brain captures

Status: read-only triage implemented, 2026-09-29. Codex execution remains opt-in and needs a local CLI live test.

## What exists today

Brain saves a capture, then `app/agents.py` queues one job if the notes root has an `agents/` directory. A worker runs the job and records queued, running, done, or failed in `agents/*.md`. The UI displays recent runs. The default runner is Claude Code with an explicit tool allowlist. `BRAIN_AGENT=codex` already selects a `codex exec` command, but its workspace sandbox cannot enforce the same shell and connector allowlist; it is not equivalent to the original permissions in `2026-09-27-headless-agents.md`.

## Goal

Let Alex use Codex to process Brain captures without making a background job capable of sending messages, publishing, pushing, committing, or changing unrelated projects. Keep the current queue, run files, and Agents UI.

## Shared behavior

- Queue only after `/api/capture` or `/api/habit-new` saves successfully, and only when `agents/` exists.
- Run one job at a time with the existing 20-minute timeout and restart recovery.
- Include capture type, text, Brain index, and relevant project page in the task.
- Report what was done, where output lives, and what needs Alex's decision. No automatic external action.
- Use Alex's notes paths and name; the older spec's `~/Notes`, `~/Projects`, and Zac are examples, not this machine's configuration.

## Codex boundary

`codex exec --sandbox workspace-write --ask-for-approval never` can run arbitrary commands inside its writable workspace. A prompt saying “don't commit” is guidance, not an enforceable command restriction. A writable checkout, executable files, hooks, or connectors may create effects outside the intended note edit. Do not treat this command as a drop-in replacement for Claude's `--allowedTools` runner.

Two implementable modes:

1. **Read-only triage (implemented).** Run Codex with `--sandbox read-only --ask-for-approval never`, ignore interactive user config, and disable hooks, apps, and web search. It classifies the capture, reads context, and returns a proposed note change or task plan. Brain writes only the bounded report to `agents/*.md`. No autonomous project edits. Select with `BRAIN_AGENT=codex` when the CLI is installed.
2. **Isolated editing.** Run Codex in a disposable worktree or copy with only explicitly selected writable roots, no ambient credentials or write-capable connectors, and network disabled. After the run, Brain checks the diff and exposes it for Alex to review before applying changes to the real notes or project. The host process, not Codex, enforces which files may be applied. Never auto-apply a diff to a project or run generated code on the host.

Alex chose analysis and proposals first. The second mode can do file edits but requires a review and apply workflow.

## Implementation checks

- Keep Codex opt-in rather than silently replacing the default Claude runner.
- Pass the prompt over stdin, as the current runner does on Windows.
- Make the command and its effective sandbox policy visible in the run report; fail clearly if Codex CLI or authentication is missing.
- Test queue order, restart recovery, timeout, no network, blocked writes outside the selected root, and absence of commit or push capability.
- Run one live benign capture and inspect its report before enabling unattended capture handling.

## Current limitation

The `codex` CLI is not on the PATH in the current development shell, so a live Codex run and sandbox test cannot be completed here yet. The command construction and queue behavior are covered by local tests; a real capture must be tested after the CLI is available. This mode only proposes changes, while the default Claude runner retains its separate allowlist and editing workflow.
