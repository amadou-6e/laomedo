# Repository storage pilot acceptance

Owning implementation issue: amadou-6e/laomedo#309; draft PR310.
The harness is experiment-only and is not imported by production tests.

`restart_preview.py` restarts only the verified idle saved-account preview on55753,
preserving its login state. It refuses a different listener or active conversation.
`acceptance_shell.py` uses normal profile login with the root environment PIN kept
in memory. It uses the explicitly named validation clone, freezes graph and agent
locations, and submits at most a fresh and resumed prompt per saved provider.
It verifies written files in that clone. It does not export provider credentials,
commit/push repositories, edit the app graph or publish workflows.

2026-11-23: implementation0aba51d38; specs ebebcbb. Public GitHub cloning succeeded
in the real integrated preview. Codex fresh and resumed native-shell writes passed.
OpenCode fresh and resumed native-shell writes passed. Claude reached its native
session usage limit (reset00:10Berlin) before executing the requested shell action;
its retained normalized events confirm the quota response. Send unlocked; history
retained. Claude live acceptance remains incomplete. Independent review is also
quota-blocked and no merge is authorized by these results.

This evidence is specific to these revisions and the saved preview setup. It does
not establish private-remote acceptance, cancellation write-back or arbitrary host
filesystem isolation. No private runtime records or screenshots are tracked here.

2026-11-24 reset follow-up: Claude fresh and resumed native-shell writes passed
at implementation `070445cc0aed027580cd14970b3178c81785121b`, using the existing
saved connection and normal profile login. The harness verified exact repository
file contents after both turns. This completes the previously quota-blocked
Claude acceptance case; independent review remains pending. OpenCode had also
passed a later fresh/resume check through the browser-session export fence at
`a9c2e03f4`. These are bounded selected-file checks, not blanket provider approval.

`recovery_shell.py` adds a bounded four-turn OpenCode check: initial write, external
conflict, exact repository-text restoration via MCP plus shell, then a normal edit.
2026-11-24: all four stages passed with the corrected runtime from `2f731a965`.
The external version survived the conflict, Send unlocked, and later edits saved
in the same conversation. `ui_state.py` creates reversible whitespace-only graph
conflicts and briefly hides the validation clone's Git metadata for actual UI
captures. All such graph bytes and Git metadata were restored. These probes are
limited to the explicitly named app-owned validation checkout; no user repo is
modified and no model-based probe is part of normal production verification.
