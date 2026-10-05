# EXP-10 amendment 01: direct compact-capture replication

Issue: https://github.com/amadou-6e/laomedo/issues/40
Date: 2026-10-05
Status: prospective amendment, committed before the replication

The first valid four-call run produced a verbose Langflow response. Its
committed `observation.json` at Laomedo `dee05c2` was manually condensed
afterward, while `probe.py` was changed to write that compact shape for future
runs. That makes the first observation inspectable but does not establish
that the final capture path reproduces its own committed artifact.

Run **one new** disposable four-call replication using the same pinned image,
timeouts, delays, route choices, one-attempt-per-case rule and zero-model
scope from `PROTOCOL.md`. The capture code must write the compact observation
directly, without manual editing. Check that all four calls reach the mock
runner once, the runner's effect ordering and response categories remain
observable, and mutation tests pass on the generated file. Preserve the first
run's source revision and hash as historical evidence; identify the new run
with a distinct revision and timestamps. If a result differs, report the
deviation rather than replacing the original claim silently.

This amendment authorizes four additional synthetic calls only; it does not
add model turns, external writes, changed thresholds or a product timeout
guarantee. The v2 post-408 job-status/IF-06/07 gap remains open.
