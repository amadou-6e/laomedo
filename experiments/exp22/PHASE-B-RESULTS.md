# EXP-22 Phase B native cancellation result

Issue: https://github.com/amadou-6e/laomedo/issues/22. Governing specs:
`amadou-6e/specs@bda41ba024b725f7500156467015ae8827447890`.
Phase A merged at `72502b7c0ee62620ec4da64bd90db8c6198f318c`.
The [Phase B amendment](PHASE-B-AMENDMENT.md) was committed at `2b83f88`
before execution. The probe was committed at
`34199042a715f772f3729f091571f927a959ad4e` before execution, and the
private `pins.json` records those exact bytes and all fixed inputs.

## One-shot observation

Private evidence remains at
`%LOCALAPPDATA%/Laomedo/exp22-phase-b-20261005-3419904/`. It contains the
raw trace and runner workspace; do not commit or publish it. The sanitized
observations were copied byte-for-byte, without editing, to
[prethread.json](prethread.json) (SHA-256
`348ac81af68234dd521565ea380b99a034b2b2fe3671692e4a7c0da553a12c14`)
and [active.json](active.json) (SHA-256
`b2384ed73147130414177323af659197401f9700474ad7d98b50e263a21aa40c`).
Their Git attributes disable line-ending conversion so the committed blobs
retain those exact hashes. No retry or resume was performed, and no active
process remains.

| Check | Observed |
| --- | --- |
| Pre-thread cancellation | Saved run `81d50308-bc07-44f8-8bf1-57f37b91edc8` was cancelled before its response gate opened; no thread, turn, container or ledger entry. |
| Active cancellation | Saved run `2ec7a732-a397-4545-9781-ae939169b4d4` acknowledged as `prepared`. A native `commandExecution` containing `sleep 30` started 10.828 seconds after acknowledgement (raw event index 78); cancellation was then accepted as `running`, not confirmed. |
| Native and local terminal evidence | The native `turn/completed` event at index 83 reported `interrupted`. `turn/interrupt` was acknowledged. The local record then reported `cancelled`, `cancelled_by_user`, and `cancel_confirmed=true` after teardown. These are distinct observations; the local flag alone would not prove native stop. |
| Independent process/effect check | Exact container `laomedo-codex-afd7c21ccf0341a5adafdb40b208b3f2` was absent from `docker inspect` and `docker ps -a`, including a later repeat query. The probe's immediate `sentinel_present=false` was too early to establish a late-effect result by itself. A separate read-only check at `2026-10-05T16:02:49Z` still found no `cancel-marker.txt`; `active.json` had been written at `15:31:00Z`, after the command-start event, so the recheck was more than 31 minutes after command start and far beyond the 30-second sleep. Container absence is the primary stop evidence. |
| Budget | One attempted `turn/start` in the fresh ledger; maximum four. Three authorized turns unused. |
| Trace | 84 private raw events, SHA-256 `187d8374c4f797db2fc8d754cfbe7394c21de1b89c382d114f6cce0084901aa4`; runner reference `laomedo:run:2ec7a732-a397-4545-9781-ae939169b4d4:events`. |

The read-only preflight passed with zero turns. Pins: image ID
`sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`,
model `gpt-6-luna`, effort `low`, prompt SHA-256
`34d90ca22c0515a8cf5fb0134106da346fa68e59619d9e2afc0469f7fc0126d8`,
skill revision
`sha256:a12c212a57a9bc8fa3f0ecd834c09f9576a37ee89e21c62a096b1213fcc2bef8`.

## Assessment and limits

This is positive evidence for the **native runner's** pre-thread and
active-tool cancellation path: no re-dispatch, an observed interrupted native
turn, independent container absence and a delayed read-only sentinel check.
The active case used only one model turn, so the reserve was not spent.

It is **not** full #22/Q11 acceptance. This direct runner check did not create
an IF-06/07 invocation or prove a cross-store trace join. It did not exercise
Langflow's UI Stop propagation. It did not simulate a runner crash, which is
explicitly outside this amendment. The existing `cancel_confirmed` field
means Docker connection/container teardown, not by itself native turn status;
the native `interrupted` event is separately evidenced here.

Verification after the run: `python -m unittest discover -s tests -p
test_*.py -q` passed 154 tests; the probe script passed `py_compile` and
`git diff --check`. The copied JSON files were inspected for private material
and their source/target SHA-256 values matched before staging. No weights,
credentials, raw events or private workspace are committed.
