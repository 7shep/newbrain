# Codex connector for upstream routines

The fork includes upstream through `9437de2`. It retains the upstream Claude routines
module and uses `app/codex_routines.py` for the desktop application.

The Codex connector reads local automation metadata under
`$CODEX_HOME/automations/*/automation.toml`, defaulting to `~/.codex`. It caches names,
active status and recurrence rules in the configured notes root's
`codex/routines.json`. The phone receives that snapshot through its normal sync.
No automation prompts, credentials, project paths or run transcripts enter the snapshot.
Python 3.9 and 3.10 use a restricted string-field reader; newer Python uses tomllib.
Malformed automations produce a visible error without dropping readable entries.

Schedule creation, run, pause and resume remain in the Codex app. The connector
never changes automation files or uses an undocumented automation control endpoint.
Run history is labeled as available in Codex, rather than inferred from metadata.
See [Codex scheduled tasks](https://learn.chatgpt.com/docs/automations?surface=app).

Routine captures use the existing read-only background runner to propose a schedule
and prompt for review. When agents are disabled, the request stays in the inbox.
Suggested routines use the same restricted runner. Background permissions and
interactive Git authorization remain separate. Random habit suggestions also use
Codex, with shell tools disabled and note context supplied through stdin.

Offline tests cover snapshot extraction, unchanged source files, rejected controls,
malformed input, Python 3.9 field parsing and validated suggestion items. Upstream
Claude tests continue to use fake commands. Live scheduled execution belongs to
Codex and is not exercised by Brain's checks.
