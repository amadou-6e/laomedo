# EXP-139 live imported-graph acceptance, 2026-10-12

**Passed at the bounded single-user local, fixed-report scope.** The imported
Langflow graph produced a real draft PR through the trusted controller publisher:
[disposable repository PR #8](https://github.com/ga84jog/laomedo-exp104-disposable-20261007/pull/8).
See [AMEND08-OBSERVATION.json](AMEND08-OBSERVATION.json). Neither this report nor
that test PR authorizes merging the disposable report or closing #139.

## Frozen execution and owner authorization

Executed source `598cf7e0f99e98c45accde6cf78e5f3f986b3799`, source parent
`112b5b550994d1fc011bf35852d6844ea2d9ffd1`, manifest
`a99a8d852d37c34784502b2acd16865deb7a29aaa175436ac5be75ea62d9fb8f`.
AMENDMENT-08 was drafted and committed before its live call. The owner approved
the fresh campaign, one additional push and later standing routine amendments.
Claude approved exact source and configuration; all four final-head CI checks
passed, source/input/Git-blob hashes matched and the fresh branch was absent.

Preparation reused the frozen issue, original baseline and deterministic skill
pin without refetching the issue or copying login files. It preserved the old
campaign and seeded seven consumed turns in the fresh ledger. Old state is
permanently retired and neither root may be deleted/reprepared to reset counts.
The calling command-approval check first timed out before process creation,
with no turn or write consumed. Its explicitly permitted single retry launched
the graph; this was not a retry of an agent or provider operation.

## Actual acceptance evidence

| Requirement | Actual result |
| --- | --- |
| Issue ingestion and frozen context | Same frozen issue snapshot `sha256:6ac43222d0b8ba7b17468b0247fff3dbca715ccc2b5068320152a45e6d4ee9df`; exact URL, body digest and snapshot ID present in the published report |
| Skill and agent node | Pinned `live-report` supplied through the Skill node into a real Codex invocation in the imported Langflow graph; this does not prove automatic skill discovery |
| Agent-side correction | Three bound native precheck calls: missing-report rejection followed by two accepted submissions, all within one submitted turn |
| Contract and routing | Accepted success followed the imported graph's success route through Accepted Validation to Draft PR Publisher; no direct publisher bypass |
| Actual external effects | One new confirmed mediated push and one confirmed draft PR creation; prior confirmed push remains preserved on its separate branch |
| Publication readback | PR #8 is draft, head `exp139-20261012-b`, commit `973b826fc5a25f1789578b2841c8e9cbfc5e3e67`; actual PR file-list GET returns only the added report |
| Exact published bytes | Report SHA-256 `3de179af048ab7823ab1a088459309e802b5a0253263718a8ce33f911eb3a49b` matches the frozen expected bytes and retained output |
| Execution evidence | Native closure covers twelve items and one turn; `evidence_complete=true`, `completion_basis=native_trace_closure`; all four recorded shell commands exited zero |
| Cleanup | Publication completed, zero active grants, controller/executor cleanup confirmed, exact owned host trees stopped and port 8779 released |

Run `4f05d15f-6880-4266-ac7d-b7707fc9d6c6`, native thread
`01a12f4e-76e2-71e2-8030-77f209a55872`. Ledger **8/10 cumulative turns**.
Across both preserved roots, **two push attempts and one draft-PR attempt** are
consumed. No further experimental write is authorized by the remaining turns.
The original 600-second handoff bound and credential/permission boundary stayed
unchanged; the new run received a fresh grant, not a renewed expired one.

## Failure routes, retained limits and reproducibility

The actual task-failure and downstream pin-rejection cases passed earlier under
AMENDMENT-04 and remain in [RECOVERY-RESULTS.md](RECOVERY-RESULTS.md). Neither
published. They were not resubmitted to fill this success campaign. AM05/06/07
failed or partial outcomes remain unchanged. AM07's immediate rejection cause
is still unproven; success with GET recovery does not establish its root cause.

The credential-free controls cover the same imported graph's failure, rejection
and incomplete-evidence routes, GET-only recovery without redispatch, and bounded
diagnostics. New budget controls verify the prior root is read-only and changed
prior write state refuses. These controls are distinct from live acceptance.

[readback.py](readback.py) performs only bounded host GETs and a readonly,
network-disabled credential-volume read for the in-memory current-token scan.
[observe_amend08.py](observe_amend08.py) exports closed evidence from retained
records and readback. Neither recreates a model turn or publication. A fresh
run must never reset either activated root's ledger or write budget.

No current GitHub token, runner token or stored Codex login value matched the
published metadata, actual PR file list or report bytes. Current source/evidence
must also pass the separate scan before publication. Historical rotated values
and private raw transcripts are outside that scan. Credentials stay host-side
for GitHub; Codex login custody uses the explicitly accepted container profile
and sandbox auth-file deny. Same-UID relay/process attachment isolation remains
unverified. This is not arbitrary issue implementation, hosted/multi-user
acceptance, or a production credential-isolation claim.
