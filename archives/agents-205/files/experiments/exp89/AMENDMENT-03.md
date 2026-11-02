# EXP-89 amendment 03 — choose the visible playground Stop

Case B dispatched exactly once on 2026-10-05, but the probe selected
`stop_building_button`, which belongs to the graph canvas behind the open
Playground. Playwright timed out before completing a click. The fake runner
later recorded a synthetic effect and terminal response, with no cancel
request. This is inconclusive about Langflow's visible Playground Stop and
Case B will not be retried under the frozen one-dispatch rule.

Before the independent Case A and completed-run control, select the visible
Playground button with `data-testid="button-stop"` explicitly. Record the
click timestamp only after Playwright confirms the click completed. A missing
or disabled Playground Stop is reported as such, not replaced with a backend
API cancellation call. No timing, fake-runner, model-turn or interpretation
rule changes. Freeze this amendment and probe revision before Case A.
