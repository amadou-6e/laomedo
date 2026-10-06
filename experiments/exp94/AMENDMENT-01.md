# EXP-94 amendment 01 — late-click negative control

The initial CONTROL case completed its synthetic effect, but the browser probe
deliberately did not click the still-visible Playground Stop. It establishes
only the no-click baseline, not the issue's stronger late-click requirement.
Cases A and B are complete and will not be retried.

Add one new `CONTROL_LATE` case with a fresh flow and request identity. Wait
until the fake runner has recorded `synthetic_effect`, then click the visible
`button-stop` if it remains enabled. Observe for nine seconds. Pass only if
the exact completed runner run receives zero cancel requests and no second
start. If the control is no longer clickable, report that case as unsupported;
do not substitute a direct API cancel. All other timing, image, token and
zero-model rules in the frozen protocol remain unchanged.
