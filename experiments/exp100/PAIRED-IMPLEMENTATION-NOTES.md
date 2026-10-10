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

Independent pre-run review disapproved the first harness before any capture.
Corrections: altered-effect now uses a valid PR title change and must yield
`effect_conflict`, not the reviewed-issue hash refusal; exact safe refusal codes
and exit classes are frozen; durable SQLite effect run/grant/state/operation and
per-case write counts are checked. Direct Git counts come from a post-receive
provider journal, not an assumed two writes. Local Git keeps each side's actual
output hashes. The production authority now carries an approved PR base even
when Git fetch is not granted, with an approval/bind/lease regression.

Unknown replay is explicitly a host-side saved-request state with no CLI exit.
A literal `gh pr edit` retry would re-read the already changed PR, construct a
different expected snapshot and conflict safely; it is not called equivalent.
The direct lost-PATCH baseline depends on installed gh not repeating it. Any
additional write fails the measured per-case and total limits rather than being
hidden. Partial provider journals are retained on an incomplete capture.

Transport limits: input bodies are capped at 65,536 UTF-8 bytes, responses at
1 MiB, and fixed GraphQL lists at 30 nodes. Larger valid GitHub responses can be
refused. Git bundles remain bounded by existing transport limits, not an
assertion about large repository disk usage. Synthetic providers do not prove
all GitHub validation rules, rate limiting, paging or live provider behaviour.

Post-capture integration: S11 was executed once at `2b93124` and its original
observation is retained at `c7dbed4`; see PAIRED-RESULTS.md. The pre-capture
"not yet run" statements above describe that historical development stage.
Independent post-run review approves this scoped implementation, not #100
closure. Evidence specs merged as
`04fade6d88cc4c6d5c494c7e566c5cacbad93b09` (specs PR #342), in
`projects/laomedo/subsystems/agent-execution/validation.md`, section
"EXP-100 paired S11 command comparison, 2026-10-10".
The clean develop merge preserves the reviewed mediation/authority/test diff;
output-contract additions in the parent remain separately owned. The original
manifest/source hashes and machine observation are unchanged and not rerun.
