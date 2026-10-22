# Study sessions and Tutor Genome

Open the Study sessions tile in Brain. Enter a course and topic and choose Start session. The panel shows elapsed time and records start/end timestamps when Stop session is used. History includes exact local timestamps, duration, and a control to correct an end time. Only one session can run at a time, and retries do not duplicate it.

Brain checks in every 30 seconds while the desktop page is open. If the server restarts or no check-in arrives for 150 seconds, the timer is held at the last check-in. Choose “I kept studying” to confirm the gap or enter your actual finish time and stop. Closing a tab cannot silently count a long absence as study. A suspended tab or computer sleep can also trigger review. Phone shows the last synced snapshot read-only; it does not queue timer controls whose timing would be ambiguous.

## Tutor Genome

The panel's Tutor Genome lets you inspect or retract evidence and add your own observation. To correct an observation, retract it and add a corrected one. Retracted entries remain in the audit history but no longer affect the profile.

Topic status is derived from observations: “demonstrated” requires at least three independent attempts across two UTC dates and the latest three attempts independent. A latest struggle marks “needs practice”; other topics are “developing.” Confidence starts low, rises with more evidence across sessions, and returns to low when the latest evidence is over 21 days old. These are transparent practice heuristics, not a validated assessment or a permanent ability label.

## Discord

On Windows, Start attempts to set the Discord desktop app to Do Not Disturb through its accessibility controls. Stop attempts to restore the recorded prior status, including Invisible. If the user has changed status away from DND, Brain preserves that manual choice. No Discord account token is read or stored. The desktop app must be open, accessible to the current user, and expose English status labels; unavailable controls and verification failures are shown in the panel. Use Retry Discord DND or Retry restoring Discord after opening the app. Study logging continues independently of adapter failure. Stopping the Brain process itself cannot restore Discord until Brain is reopened and the session is stopped.

The adapter is bounded and uses named controls; it does not click guessed screen coordinates. Discord UI changes can require updating the adapter. Discord's native [Social SDK status method](https://discord.com/developers/docs/social-sdk/classdiscordpp_1_1Client.html) is a separate integration and is not included in this standard-library-only app. Automatic Discord control is unavailable on other operating systems.

## Storage and API

`study/state.json` in the configured private notes root contains sessions, observation evidence, revisions, and change history. Atomic replacement protects writes, and the server serializes actions. `study/log.md` is a generated readable log and Genome snapshot. Edit data through the panel or authenticated helper rather than the generated Markdown. Existing note/Git sync includes study files when enabled.

`GET /api/study` returns the profile and sessions. `POST /api/study` accepts start, stop, heartbeat, continue, correct_end, discord_retry, observe, and retract. Host and API token requirements match other Brain APIs. Observation/retraction actions require the current revision; stale changes are rejected. Session control uses an explicit ID so a stale client cannot stop a newer session. The skill's bundled `scripts/study.py` reads a local API token in memory and refuses remote addresses or redirects.
