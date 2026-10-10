# S11 implementation notes before acceptance

The paired harness is unexecuted. Development checks are not campaign evidence.
The original protocol and prospective Amendment 01 remain unchanged.

The direct baseline uses literal installed `gh api` with full loopback URLs,
not native `gh pr`/`issue` internals, and compares selected fields/effects.
REST list and GraphQL connection ordering are compared to their corresponding
direct endpoints, never substituted for each other. Both provider states are
independent and initialized identically. Native output/table parity, general
GraphQL/API support, default runner issue publication, real GitHub authentication
and unrestricted repository size remain out of scope.

The reviewed issue request, including its marker and proposal ID, is constructed
in `paired_cases.py` before dispatch. The pre-run reviewer must inspect its exact
bytes and the manifest hash. An agent-provided proposal label is not approval.
The grants are explicit trusted fixture grants, not widened production defaults.

The synthetic server refuses requests beyond 100 REST attempts or five writes
per side. GraphQL POST is a read and excluded from the write count. Each side
also performs two Git pushes, for seven provider writes in the positive matrix.
Setup seeds are distinct from tested writes. Negative commands must not write;
the concurrent PR snapshot-change case may read before it refuses, and preserves
those read attempts in the journal. Confirmed and unknown effect replays may not
contact the provider again. The lost response is deliberately suppressed only
after the fixture applied one PATCH; it is never retried.

Fixed identity consumption uses one machine-temp campaign slot, regardless of
caller-selected output folders. The coordinator cannot start without an exact
pre-run approval record matching the final source and manifest. Per-command
30-second and overall 600-second bounds include the Docker calls. Cleanup has
separate bounded checks; failure or uncertainty consumes the identity and is
preserved. No new model turn or real GitHub acceptance mutation is authorized
by this harness.

Development findings resolved before capture: the provider's HTTP reader needed
bounded chunked stdin support for actual `gh api` POST; PR creation needed the
already intended grant-base check. Regression controls cover the latter with
zero provider attempts. The full paired capture has not yet been run.

Transport limits: input bodies are capped at 65,536 UTF-8 bytes, responses at
1 MiB, and fixed GraphQL lists at 30 nodes. Larger valid GitHub responses can be
refused. Git bundles remain bounded by existing transport limits, not an
assertion about large repository disk usage. Synthetic providers do not prove
all GitHub validation rules, rate limiting, paging or live provider behaviour.
