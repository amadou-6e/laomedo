# Phase G continuation: real visible Stop and durable host join

The user authorized repairing the rejected private runner login and continuing.
The [diagnostic](PHASE-G-LOGIN-DIAGNOSTIC.md) and
[protocol amendment](PHASE-G-LIVE-PROTOCOL.md#authorized-continuation-after-login-repair-2026-10-09)
were committed before dispatch at `26e37ad`; the tested documentation-only
clarification head was `85ddbf9`. The same Claude reviewer cleared exactly one
new turn. The credential-free Playground preflight passed first. One subsequent
visible Send used `gpt-6-luna` at low effort and moved the shared ledger from
**7/12 to 8/12**. No additional submission occurred.

The fresh attempt passed `real_join_visible_stop_passed`. This composes a real
active-command visible Stop with the durable Langflow/host/native identity join
in the same bounded local run. The earlier failed attempt remains unchanged in
[PHASE-G-LIVE-RESULTS.md](PHASE-G-LIVE-RESULTS.md).

| Criterion | Observed |
| --- | --- |
| Exact dispatch | One browser Send, one authenticated host-bridge start and one native runner start; host/native request digest and run identity matched. |
| Credential read boundary | The agent-originated content-free `auth.json` read was denied at native event index 45. The tested non-split profile still mounts the login inside the stage; this is a read-denial observation, not controller-only custody. |
| Active Stop | The long native command started. One visible Stop reached the exact host client-cancel route before one exact runner cancel, with terminal observation before browser closure. |
| Native and filesystem outcome | Native completion `interrupted`; runner terminal `cancelled`, cancellation confirmed; exact owned container absent and delayed sentinel absent. |
| Durable identity | After stopping the bridge and recreating disposable Langflow on the same private SQLite mount, a fresh child reopened the exact host binding and one linked Langflow trace. Saved-flow UUID and reported graph-run ID in a span were the trace join basis. |
| No redispatch | One native start total, zero new starts after restart. |
| Partial evidence | 87 native events retained privately, including the interrupted turn. No raw transcript published. |
| Cleanup | Langflow container absent, exact runner cleanup verified, bridge and runner servers stopped. |
| Token-publication check | Neither local bridge nor runner API token occurs in the sanitized result, pins, teardown or route audits. |

The pinned runtime was Codex CLI 0.159.2, image
`sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`,
and Langflow 1.12.3, image
`sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
The private state is
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-live-20261009-b/`.

| Artifact | SHA-256 |
| --- | --- |
| `sanitized.json` | `c0354838ad5857f1e014256af929a1a662d8a7eaa42dc19564cf3ca2e5c21416` |
| `teardown.json` | `c1c6fee74f805ca1f4f3e166f550faefc1f48bb803391dff3a8cad6b5d53a57c` |
| `pins.json` | `b05f7060cc85fecab947651839005161b9231b7cfc25a5efb74881f4e245e948` |
| `bridge-routes.jsonl` | `14a49192e19e1bf6ae356415c1372a74d30d3019f1f0d39c4079bb636615507b` |
| `runner-routes.jsonl` | `54660716460bed59466cca67518007574a735b37317b9f7cd58f3adc77247078` |
| Private native events | `e428fb5551b30db636fa22d9196fb2795ac36fe23606eb8425ab12d5d2c3ba23` |

This is one bounded single-user cancellation-and-join pass. The graph ID is
component-reported corroboration, not executing-editor-graph attestation. The
result does not establish semantic task success, hosted isolation, timeout
effects, runner/lease joint-outage behavior or real GitHub push-credential
revocation under #93. The copied-login lifecycle remains unresolved under
specs #129. No issue state changed.

The earlier pre-thread Stop result is separate: pre-thread Stop was not composed
with the durable join in this active-command continuation.
