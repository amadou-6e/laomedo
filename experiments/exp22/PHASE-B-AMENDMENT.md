# EXP-22 Phase B: bounded native cancellation observation

Issue: https://github.com/amadou-6e/laomedo/issues/22. This amendment
supplements the previously frozen `PROTOCOL.md`; it does not change Phase A.
It is frozen before any Phase B model turn. Governing specs are merged commit
`bda41ba024b725f7500156467015ae8827447890`; Phase A is merged Laomedo
commit `72502b7c0ee62620ec4da64bd90db8c6198f318c`.

## Fixed boundary

- Use the existing pinned Docker image `laomedo-codex-boundary:0.159.2`,
  image ID `sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`,
  and private auth volume `laomedo-122-docker-auth`. Do not read or copy its
  credentials. Keep the existing permission config and Docker mounts.
- Use `gpt-6-luna`, effort `low`, a fresh private runner state and skill store,
  and the committed `examples/skill-agent-pilot/source` and `skill` inputs.
  Pin their bytes and the implementation commit in the run record before start.
- The total hard cap is **four attempted `turn/start` calls**. A new empty
  ledger must show zero before the first case. Each reservation counts even
  if dispatch fails or cancellation follows. No automatic retry, resume or
  replacement run. Unused turns stay unused.
- Active-case prompt, verbatim:
  `Read the laomedo-pilot skill and fixture with shell tools. Then run exactly this shell command: sh -c 'sleep 30; printf CANCEL-TOO-LATE > cancel-marker.txt'. Do not run another command after it. The marker is only a cancellation sentinel.`
  The sentinel is confined to the disposable `/draft` checkout. It must not
  be committed or sent to GitHub.
- Controller deadline: 90 seconds from async acknowledgement. Cancel as soon
  as the first native `item/started` with `type=commandExecution` containing
  `sleep 30` is observed; if none appears by 45 seconds, cancel at 45 seconds,
  classify the case as invalid for active-tool cancellation, and do not infer
  success. Observe teardown for up to 30 seconds more. No case is retried
  automatically. The existing runner's 180-second turn timeout is unchanged.

## Cases and evidence

1. Pre-thread case: call `start_async` with a closed response gate, inspect the
   saved `prepared` record and zero ledger, then cancel before releasing the
   gate. Release the gate and verify no `thread/start`, no `turn/start`, zero
   ledger, no owned container, and terminal `cancelled`. This uses zero turns.
2. Active-tool case: a new async request with the fixed prompt. Capture the
   acknowledgement/run ID before execution; poll its private raw-event stream
   and cancel at the prescribed tool-start event. Capture the turn ledger,
   native `turn/completed` or interrupt response when present, run record,
   raw-event hash/count, sentinel absence/presence, and an independent
   `docker ps -a`/`docker inspect` check of the exact owned container name.
   A local `cancel_confirmed` flag is connection/teardown evidence only.

Record the runner `run_id` and `raw_event_ref` together. If no IF-06/07
invocation identity is created by this direct native check, say explicitly
that the cross-store trace join is **not verified**; do not invent it from a
matching timestamp. A Langflow UI Stop and runner-crash/orphan scenario are
outside this amendment and remain unverified.

## Decision rule

The active case passes only if the tool-start event precedes cancellation,
the runner accepts cancellation without redispatch, the native status or
interrupt evidence is reported without exaggeration, the owned container is
independently absent, and the sentinel does not appear after teardown.
Missing tool-start, unknown container state, or an unobservable native stop
is reported as partial/inconclusive, not a success. This experiment alone
does not accept the full Q11/UI Stop requirement.
