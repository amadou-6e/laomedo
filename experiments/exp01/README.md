# EXP-01: Work Graph source integrity

This experiment tests the installed Work Graph package against synthetic GitHub
GraphQL pages and an independently written oracle. It uses no GitHub reads or
writes, credentials, model calls, or existing Work Graph development fixtures.

The [protocol](https://github.com/amadou-6e/specs/blob/bf9dc494b20d8a9d683791b9e07630fe1a06d21f/projects/laomedo/experiments/work-graph-source-integrity/protocol.md)
was committed before the fixture corpus. `fixtures.py` specifies the response
shapes, `corpus.json` freezes the serialized response bytes, and `oracle.json`
records the hand-checked expected identities, edges, completeness, warnings,
readiness, and filtered projections. The probe reads the frozen JSON, not the
fixture generator. The corpus was written by the implementation author without
reusing its development fixtures; it was not produced by a second party.

The [original eight-case result](result.json) remains unchanged and is pinned
to input revision `7597c89`. Review then found that the filtered projection did
not compare readiness and hid only a closed blocker. The [amendment](result-amendment.json)
uses input revision `de32cc8`: a hidden **open** blocker must leave the visible
dependent `blocked`, and the probe compares projected readiness explicitly.
The original and amended result hashes refer to their respective input commits.
The wheel hash identifies a local build artifact, while source revision is the
reproducible package pin.

To reproduce, build an installed wheel in a disposable directory outside Git,
install it into a fresh virtual environment, and run `probe.py` with that
environment's Python in isolated mode. Pass an outside-Git output directory
for snapshot artifacts and the result JSON. Never update `oracle.json` from
observed package output.
