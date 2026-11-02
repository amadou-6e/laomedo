# EXP-22 Phase A: synthetic early identity and cancellation

Protocol: [PROTOCOL.md](PROTOCOL.md), frozen in `7975ffaa1555d7baf39880a578128724e5a08f50`
before implementation or these checks. This is a zero-model result, not a
real-runner cancellation pass.

The credential-free fake transport and authenticated loopback HTTP tests
observed an HTTP 202 with a queryable run ID before the blocked fake turn
finished. An exact duplicate request ID/body returned that ID without a
second turn; a changed body returned 409. Cancel before the worker gate
prevented a turn. Cancel during a blocked fake turn first returned
`cancel_requested=true, cancel_confirmed=false`; after the fake transport
closed, the saved record said `cancelled` and retained its partial raw event.
The turn ledger held one attempt. A saved pending or active record appeared
as `interrupted` after synthetic runner re-instantiation and was not replayed.
The bounded controller persisted the early ID while dispatch still waited;
a Stop arriving before acknowledgement was forwarded after the ID appeared.
A polling deadline left the early ID available and did not assert cancellation.
A subsequent cancel races with the fake turn's own timeout; either terminal
outcome is accepted only when its `cancel_confirmed` value matches the outcome.
A separate controlled race pauses a cancel writer after it reads `running`,
lets the worker reach finalization, then releases the writer. The final
persisted record remains terminal rather than being overwritten as `running`.

Verification commands and observations:

- `python -m unittest discover -s tests -p test_*.py`: 154 passed.
- Pinned Langflow image `langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`, offline, with `PYTHONPATH=/workspace`: the Codex component, bounded controller and handoff graph suites passed together (19 tests); the OpenCode component passed in its separate component-package process (3 tests).
- The combined Langflow discovery command is not a supported single process:
  both the product and UI component trees use the `laomedo` package name.
  These suites must be run in the separate processes above. No model or
  GitHub write was used in either test run.

Limits: the restart test reconstructs a runner from a saved record rather
than killing a real container; the cancellation evidence is from a fake
transport; UI Stop propagation, native `turn/interrupt`, container teardown
and post-timeout trace completeness are not proven. Phase B and first-slice
Q11 remain open. A model-turn cap and a reviewed Phase B amendment are
required before any real agent turn.
