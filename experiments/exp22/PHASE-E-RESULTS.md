# Phase E: visible Playground Stop interrupted one real Codex turn

The [frozen Phase E protocol](PHASE-E-UI-PROTOCOL.md) and browser/host probes
were reviewed before dispatch. The first review found that browser disconnect
could be mistaken for Stop; commit `84c1b29` added click-to-cancel-to-terminal
timing evidence and browser-process teardown. A focused independent recheck
cleared that blocker. A later substantive review of the fake-runner gate gave a
go for one turn with two waste-prevention findings. Commit `19e726a` cleared
the fake-task environment switch and verifies that the saved flow's embedded
Codex Agent and Skill code match their pinned source byte for byte. The
[credential-free preflight](PHASE-E-PREFLIGHT.md) passed before submission.

Tested implementation: `35a7d3c`. The user extended the shared ledger by
eight turns from 4 to 12. This result used **one**, leaving it at **5/12**.
The pinned Langflow image was
`sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
The Codex image, graph, component, skill, source and task hashes are in the
private `pins.json`; no login or runner token is published.

| Check | Observed |
| --- | --- |
| Browser and native start | The headless browser submitted once through the saved Playground flow. The visible `button-stop` was clicked after native `sleep 30` command start. |
| Exact routing and attribution | The authenticated runner audit recorded one async start, one lookup for the acknowledged request ID, and one cancel for the exact run ID. Cancel arrived after the click began, and the runner was terminal before browser-context closure. No host fallback cancel was counted. |
| Native and runner result | Native `turn/completed` was `interrupted`; runner status was `cancelled` with `cancel_confirmed=true`. Run `448e4385-fca4-41cb-8f2f-d5e4815357e7`, request `062358bd-3e02-48d9-8f82-37d780e5152f`. |
| Retained evidence and boundary | 61 partial raw events, SHA-256 `483362dee4e51c398f195c942bbf7a115f058838afbaa64504b6e78ec32ef6f1`. A content-free attempt to read `auth.json` was denied at native event index 52. The exact Codex container and delayed sentinel were absent. |
| Teardown and token check | The disposable Langflow UI container was absent, exact runner cleanup was verified, and the runner API token did not occur in the private browser log/result or sanitized result/teardown. |

Private state: `%LOCALAPPDATA%/Laomedo/exp22-phase-e-live-35a7d3c/`.

| Private sanitized artifact | SHA-256 |
| --- | --- |
| `sanitized.json` | `67ba03cbf71baf41f67c7324954e1a161f770339af93f7eb7e2f9b5a7493f837` |
| `teardown.json` | `897931ae5e8daef0e39519890410fefe0ba412a58da93a9ea8bf24d665af4c65` |
| `runner-routes.jsonl` | `8c9f6a2896e57691ee81015bf79dfde90a9579d42f43b8b4b8eb35ff3ab5160f` |
| `pins.json` | `131bc8da4a2b198d3c1d87f708dbe1cecdffde2190e59cec725e135fd213564e` |

This is a positive **visible Playground Stop to real native cancellation** at
the bounded local scope. The browser request observer saw only the build
monitor endpoint, not an exact frontend Stop request path. The runner route
and click timing establish the resulting component cancellation, but the test
does not establish a durable Langflow invocation-to-runner cross-store trace
join. The private Codex login remained mounted in the agent stage; the denied
command read does not prove controller-only credential custody or hosted
isolation. No real GitHub credential, grant or write was exercised. The
separate #93 postrevocation and joint-outage limits remain. No issue state is
changed by this result alone.
