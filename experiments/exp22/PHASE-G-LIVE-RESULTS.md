# Phase G: real Codex bridge turn, incomplete visible Stop

The [frozen protocol](PHASE-G-LIVE-PROTOCOL.md) and
[credential-free preflight](PHASE-G-LIVE-PREFLIGHT.md) were reviewed before one
model submission at Laomedo commit `aa12af6`. Claude's same-session reviewer
gave a go for one bounded local turn after a focused bridge-cancel attribution
recheck. The shared EXP-22 ledger moved from **6/12 to 7/12**. No retry was
made.

One visible Playground Send reached the opt-in host bridge. The host persisted
one reservation and posted one exact request to the **real Codex runner**. The
native turn started but failed before running the task's first shell command.
The runner's redacted diagnostic reports nine
`responseStreamDisconnected` retry events followed by one `other` event, with
no HTTP status code. This does not establish whether the cause was network,
provider service, login state or another transport fault. The agent-originated
content-free `auth.json` read never ran, so credential unreadability was not
retested in this turn.

Because the runner failed early, the Playground Stop button was not visible
when the browser received the stop signal. No Stop click or cancel request
occurred. This result **does not pass** the visible Stop or native interruption
criteria. The 30-second sentinel file remained absent, but no long shell
command started, so sentinel absence is not cancellation evidence.

| Check | Observed |
| --- | --- |
| Bounded dispatch | One browser Send, one host bridge start, one real native runner start; one submitted turn, no second POST |
| Native outcome | `failed`; 25 raw events; redacted error categories: 9 stream disconnect retries and 1 `other`; no task shell call |
| Visible Stop | No click; bridge and runner cancel-route counts both 0; attribution and cancellation inconclusive |
| Durable join | After bridge shutdown and disposable Langflow recreation, a fresh process reopened the exact host binding; one Langflow trace matched the saved-flow UUID and reported graph-run ID in a linked span; no extra native start |
| Teardown | Exact owned runner container absent, Langflow container absent, bridge and runner servers stopped; no leftover test container |
| Credential handling | Langflow mounted only the bridge token; neither bridge nor runner token appeared in the sanitized result, pins, teardown or route logs; no credential value is published |

The private state is at
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-live-20261009-a/`, outside Git. Its
sanitized files have these SHA-256 hashes:

| File | SHA-256 |
| --- | --- |
| `sanitized.json` | `ce50e8ecfb91d1755ff3bcf0dbf13ff1d3156bb2eac0685a22ae7fed6a646761` |
| `teardown.json` | `6bcf12ea19459955330e912d91b1b101a429725eeb975c22c94983609e83f256` |
| `pins.json` | `35b5cca3d1f296bc468f8d8e80ae4db37b158783df8042200cfa9e6897b4043d` |
| `bridge-routes.jsonl` | `1415cf0cba9896ea04f49624c1da03c5bfd95d6fc6f357a0b82180f4b90a5c27` |
| `runner-routes.jsonl` | `b480f442ceb46d20f8e161076859c030a0a5904d336bad6ce9756dcd41ff92e5` |

The native raw-event file SHA-256 is
`63396d5b94d116adbaeaa031b549bddb707c7b0bc4a5c8de9ca006e64804b8f7`;
the file itself is not committed. This result establishes one real
Playground-to-host-to-Codex dispatch and a durable identity join at the failed
turn's scope. It does not attest the executing editor graph, prove an active
Stop, or close #22 or #93. A later real-turn attempt needs a new reviewed
protocol and a separate decision; this run will not be retried as the same
experiment.
