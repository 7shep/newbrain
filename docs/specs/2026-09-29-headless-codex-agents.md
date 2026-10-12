# Codex agents for Brain captures

Status: Codex-only read-only runner, updated 2026-10-12.

## Behavior

Creating `agents/` in the configured notes root opts in. Successful captures and habit proposals queue
one job; status buttons do not. A FIFO worker runs jobs one at a time with a 20-minute timeout. Markdown
reports preserve queued, running, done, and failed states; restart recovery marks unfinished jobs failed.
Phone captures park in `agents/pending/` until the local server pulls them.

Codex is now the default and only built-in runner. `BRAIN_AGENT=codex` remains compatible.
An installed, authenticated Codex CLI is required. `BRAIN_CODEX_MODEL` optionally selects a model.
The prompt asks for an exact proposed note change or short task plan, never autonomous execution.

## Boundary

The command uses `codex --ask-for-approval never exec --sandbox read-only`, skips user config and
user/project execution rules, and disables hooks, apps, plugins, multi-agent tools, browser/computer tools,
and web search. MCP configuration is cleared and automatic AGENTS.md context is disabled, so interactive
commit/push instructions do not get imported into these runs. Sessions are ephemeral. The prompt goes
through stdin, preserving multiline text on Windows. All paths derive from the configured notes root.

The Python host writes only the bounded Agents report. The runner cannot file captures, edit project
files, create external drafts/calendar events, commit, push, or publish. Read-only does not imply that
filesystem reads are restricted to the notes folder; do not describe it as a private-data isolation layer.
The old Claude tool allowlist is not reproduced by granting Codex workspace-write permission.
Interactive CLI development keeps its separate authorization.

## Validation

Offline tests cover queue order, statuses, timeouts, missing CLI, restart recovery, UTF-8 stdin, and
command flags. CLI flags and a live schema-validated voice answer passed with Codex CLI 0.162.1.
Desktop and phone fixture interactions passed in headless Chrome. The hosted workflow still requires
the private notes repo and secret setup; it was validated against the released Action v1 interface.
Tests use temporary/example notes, never personal notes.

## Phone voice

Voice questions use the same read-only command with shell tools disabled and supplied note context.
A JSON schema requests `answer` and nullable `capture`; the host validates types and lengths before
saving an explicitly requested capture. No Anthropic SDK is needed. The hosted workflow batches questions
through the Codex GitHub Action, which receives the OpenAI secret and outputs structured answers for the
host. Missing, duplicate, or invalid answers fail their question without blocking unrelated queue actions.
