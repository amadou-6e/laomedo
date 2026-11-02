# EXP-89 amendment 02 — open the playground before typing

The first Case B browser attempt on 2026-10-05 stopped before dispatch. The
Playground textarea existed in the page DOM but was hidden, so Playwright's
visible-element wait timed out. The fake runner journal has zero POSTs after
the attempt's baseline, and the attempt is retained as
`case-b-setup-failure.json`. It is not counted as a Case B run.

Before any retry, change the probe to click Langflow's visible `Playground`
button before locating the textarea. No test case, time threshold, runner
behavior, or interpretation is changed. A retry is allowed only because the
saved first attempt and runner journal prove no dispatch occurred. Freeze
this amendment and corrected probe before running Case B.
