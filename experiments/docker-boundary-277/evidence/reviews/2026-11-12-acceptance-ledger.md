# Corrected acceptance ledger (current head 341c68f3, substantive code 6cff259a)

My previous verdict stands: the implementation, tests and visuals are approved within their recorded scopes, and the code gaps are closed. Two corrections to it: the claim that a live split-executor run was missing was wrong, and CI on 341c68f3 is no longer pending (all five checks pass, per your report).

## Corrections

**Codex split execution has been run live.** I withdraw "a live split-executor run" as a missing item. The evidence:
- `2026-11-11-codex-agent-restart.md`:
  - a real model shell command ran;
  - the controller and the credential-free executor were both observed running, with two durable receipts;
  - after the owner process exited, both containers were still running;
  - a new `CodexAgent` constructor reconciled both: status interrupted with `runner_restarted`, zero pending receipts, resume refused, and the foreign sentinel left alive.
- `2026-11-11-native-runtime-retirement.md`: real Codex fresh, resume and resumed-turn cancellation, with Activity closed and complete and cancellation requested and confirmed.

**What those runs don't establish, by their own disclosure:**
- the executor isolation gate is exercised, but there is no independent certification of native isolation;
- supervised lease loss;
- process-tree kill;
- physical host or daemon loss;
- recovery of a terminal Activity stream (the interrupted feed stayed `closed=false`).

**CI:** all five checks pass on 341c68f3, per the run and job IDs you gave. I haven't seen the logs myself.

## Selected acceptance gates

These come from the completion checks in `provider-boundaries.md` and the acceptance scope in `activity-interface.md`.

| Gate | Status |
|---|---|
| Real-image fresh, resume and cancel for each supported provider | Evidence recorded for Codex, Claude and the explicitly composed OpenCode route (`provider-boundaries.md:291`, approved earlier). Whether that ticks the box is the owner's call. |
| All agent and worker dispatch paths use the shared mechanisms; whole-boundary acceptance | The document itself says this is still open (`:267-270`). This is a genuine selected gate, not something I invented. |
| Partial startup, cancellation, uncertain cleanup and recovery covered | Unit and control coverage exists, plus real Codex owner loss and constructor restart, and generic real Docker owner-loss controls. The box doesn't require a real run for every provider and every kind of loss. |
| Canonical spec (PR 403) | Draft; separate gate. |
| Owner's final real-graph validation | Absent; separate gate. |

## Declared exclusions and separately gated features

These are disclosed as unverified. They aren't selected blockers for the interface as implemented, unless the owner or the spec selects them:
- Claude and OpenCode restart and recovery;
- loss of the lease supervisor;
- physical host or daemon loss;
- a second real daemon;
- recovery of a terminal Activity stream;
- the default OpenCode Console composition (no default production composition is added);
- native GitHub mediation;
- independent certification of native isolation;
- the legacy workgraph demo's obsolete Output Requirements edge, which is disclosed and excluded from current native acceptance.

## One stale status note (informational)

`provider-boundaries.md:334-346` still says the edited tests, docs, settings and migration entries are "fully unreviewed — reviewer pending", and that the AB-01 recheck is pending. Both have since been reviewed and approved. This needs no reviewer recheck; it's just a status line that has gone out of date and should be updated before the PR handoff, so the reported status stays accurate.

## Status

| Area | Status |
|---|---|
| Implementation, tests, visuals | **APPROVE**, within the recorded scopes |
| Integration | **INCOMPLETE**: whole-boundary acceptance, spec PR 403 and the owner's final graph validation are open |

No merge or issue closure is authorized.