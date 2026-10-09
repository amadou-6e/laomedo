# Phase G real-route preflight, zero model turns

The [real-turn protocol](PHASE-G-LIVE-PROTOCOL.md) is prepared but no real
Playground Send has occurred. The shared EXP-22 ledger remains **6/12**.

On 2026-10-09, a disposable pinned Langflow 1.12.3 server with the approved
private SQLite mount imported the checked-in five-node flow. The existing
private Codex login volume was present, the one-turn local runner preflight
reported `gpt-6-luna` at low effort, the host bridge started, and the browser
opened Playground without clicking Send. No native runner record was created.
The state is private at
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-live-preflight-20261009-b/`.
Its sanitized result SHA-256 is
`745a1353081cd3dcc89276f07fe5175f11f1f52d6a0465bd465b71bb7ade4fb5`;
the teardown SHA-256 is
`5f6fcf4de57b5a79a231de89f866d43e549d1da01f617f7020e8bf3f0769813b`.
Langflow, the bridge and the runner server stopped, with no runner runs to
clean up.

Separately, the credential-free installed browser Send/Stop check was rerun
after the checked-in flow acquired its optional bridge field. It still showed
one fake native start and cancel, a fresh-process host-store reopen, one
Langflow trace after container recreation, and zero extra starts. Its private
state is at
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-fake-browserfix-20261009-a/`;
the sanitized result SHA-256 is
`001b0930901a968caf76ff3828025ca3f05a6601178959baee8f2a818cb7c772`.

These checks establish readiness for an independently reviewed one-turn
submission. They do not show that a real Codex turn traverses the bridge.

A subsequent zero-turn fake-runner check added authenticated route-only audit
at the host bridge. Its single visible Stop led to one exact client cancel at
the bridge before the fake native cancel, with clean teardown and the same
persisted join after restart. The sanitized result at
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-bridge-audit-20261009-a/summary.json`
has SHA-256
`b535d6b06ff04ce7c0dcb0d3c9c324308a17053beadd598d43ecb7acdd38137b`.
The shared ledger remained 6/12.
