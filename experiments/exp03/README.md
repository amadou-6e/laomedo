# EXP-03: pinned Langflow graph mutation probe

This is a zero-model, single-user synthetic test of Langflow 1.12.3 at image
`sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
`build_flow.py` uses the installed `lfx` custom-component template API. `probe.py`
imports the resulting flow, starts a run, pauses its first component, edits the
saved second component's source and field, releases the first component, and
runs the edited flow again. The disposable server must have auto-login enabled
and listen only on `127.0.0.1:17863`.

The retained [observation](observation.json) shows the paused run returned
`TASK|BEFORE`, while the next run returned `TASK|EDITED-AFTER`. Its graph and
component hashes differ after the edit. The pinned `simple_run_flow` source
builds a detached graph before job execution. The run response does not include
the component-code hash or an authenticated link to the exported graph revision.
This test supports behavioral non-uptake of a mid-run saved-flow edit, but not a
native, independently attested per-run component revision. Laomedo must record
and bind that revision before dispatch.

The API token was created by the disposable server's auto-login route and held
only in process memory. No model, personal credential, or agent was used. The
generated `flow.json` and synthetic response contain no personal data.
