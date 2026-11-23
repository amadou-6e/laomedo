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
