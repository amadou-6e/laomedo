# EXP-01: Work Graph source integrity

This experiment tests the installed Work Graph package against synthetic GitHub
GraphQL pages and an independently written oracle. It uses no GitHub reads or
writes, credentials, model calls, or existing Work Graph development fixtures.

The [protocol](https://github.com/amadou-6e/specs/blob/docs/50/projects/laomedo/experiments/work-graph-source-integrity/protocol.md)
was committed before the fixture corpus. `fixtures.py` specifies the response
shapes, `corpus.json` freezes the serialized response bytes, and `oracle.json`
records the hand-checked expected identities, edges, completeness, warnings,
readiness, and one filtered projection. The probe reads the frozen JSON, not
the fixture generator. See the specs attempt for revision pins and results.

To reproduce, build an installed wheel in a disposable directory outside Git,
install it into a fresh virtual environment, and run `probe.py` with that
environment's Python in isolated mode. Pass an outside-Git output directory
for snapshot artifacts and the result JSON. Never update `oracle.json` from
observed package output.
