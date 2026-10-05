# EXP-89 amendment 01 — keep the active-wait graph alive

Committed before any EXP-89 case was run. The frozen protocol's Case B used
the component's nonblocking `start` operation with an immediate acknowledgement.
That operation returns to Langflow immediately; the graph may already be
terminal before the synthetic tool wait begins, so a later Stop click cannot
test propagation to an active component.

Replace Case B only with the component's blocking `fresh` operation. The fake
runner accepts one POST and holds its response for 6 seconds while recording
`synthetic_wait_started`; click the visible UI Stop control after that event.
Observe the runner journal for 8 seconds after the click. The fake runner
retains its own run ID and returns it at terminal time, so the test can still
link UI/job and runner observations. Case A remains nonblocking `start` with a
3-second delayed acknowledgement; the negative control remains a completed
run followed by Stop. No model turns, no retry, and no other threshold changes.

This distinguishes current blocking-component behavior from the future early
identity path. It cannot by itself prove a future `start`+poll graph propagates
Stop; that remains a separate integration requirement if current Stop fails.
