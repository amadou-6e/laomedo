# Phase G: opt-in host join in the installed Playground

On 2026-10-09, a disposable pinned Langflow container imported an in-memory
copy of the sample flow with the current Codex component source and optional
join URL. The checked-in flow was not changed or deployed. One visible
Playground Send reached the real Laomedo host join service, which reserved a
host run and sent one request to a **fake** native runner. One visible Stop
reached the same host binding and cancelled that fake run. This test used no
provider credential and **zero model turns**; the shared ledger stayed 6/12.

The final [probe](phase_g_join_installed.py) SHA-256 was
`afb71aa99e472667fbe12097ecb95dd8d176f7fba72911e07e44c8adbfa924c5`.
The tested Codex component SHA-256 was
`896ca1274f453dfe5d6410ded9cf6ada760c32115e5055400933cad30a4f411c`.
The host controller SHA-256 was
`d93ac98243a0820a1cd725987b97d3a30d0e7114aa70e3943fccb32729cf30ff`.
The pinned image remained
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

| Check | Observed |
| --- | --- |
| Visible Send and Stop | Both browser actions completed; Stop control was visible and enabled |
| Host/native identity | One host binding; the saved flow ID and exact frozen request digest matched; host invocation ID equalled the fake runner request ID |
| Fake native effect | One start, one exact cancel; host run projected `cancelled` |
| Attribution and teardown | Stop click preceded exact fake cancel, which preceded browser close; host trace reopened; Langflow container and both local servers stopped |
| Graph attestation | `executing_graph_verified=false`; only the saved-flow export was independently read |

Private browser logs, token files and the SQLite store remained at
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-realjoin-20261009-b/`, outside Git. The
sanitized `summary.json` SHA-256 was
`191487a14f6ee2c038d11b84f364e6b0dcc6fc099b935dd6f915801f186f12f9`;
`teardown.json` SHA-256 was
`5855910ab09f1de0d3b5671986c14a4f4f732161042b02b1e2d561e850ac2e7b`.
Neither token nor raw browser profile is committed.

This proves the installed first-call routing and fake-runner cancellation for
one local run. It does not prove that an actual Codex turn uses this bridge,
that a Langflow database trace joins after process restart, that the executing
editor graph matches the saved flow, or that a runner credential remains
unreadable to arbitrary component code. #22 remains open. A real-agent turn
must wait for the persistent Langflow restart gate and retain its approved
turn cap; an uncertain attempt consumes a slot.
