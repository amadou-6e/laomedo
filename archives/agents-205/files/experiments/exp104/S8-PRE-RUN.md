# EXP-104 S8 pre-run pin (unexecuted)

Status: frozen review candidate, 2026-10-08. S7 was retired without a live
call. No S8 provider write or model turn has occurred. The single-use identity
is `exp104-s8-20261008-01`; the only target is
`ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`) at baseline
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.

## Exact sources

- Candidate implementation commit before this pin: `ba8e7e315d5d274b5d728c54bf2da19c559d9231`.
- Probe `experiments/exp104/s8_probe.py`: Git blob `9a94702f3b239963a7ee5ad3d3633aceb4ff7079`.
- Tests `tests/test_exp104_s8_probe.py`: Git blob `64a6b66d6e59377387b94fb04e9ef1ff8d2f366d`.
- S8 amendment `experiments/exp104/AMENDMENT-24.md`: Git blob `c7f5470e3a42aa41bf92ee10700270212278d855`.
- Shared live probe `experiments/exp104/live_probe.py`: Git blob `164aa368ffb2758f1646911fc6d7365afcb17368`.
- Amendments 21, 22 and 23 remain governing, with amendment 24's explicit
  replacement of the S7 identity and token-scope gate.
- Governing Laomedo specs revision: `amadou-6e/specs@5e77d864f4b5f2064adf07e86cdd5fb90a883122`.

The invocation must pin the **final** PR head after this record is committed.
The independent read-only reviewer must inspect that exact head and give an
explicit positive S8 pre-run verdict. Save a private review record containing
the S8 identity, final source SHA and verdict before invocation. A change to
code, protocol or tests after that review requires a fresh pin and review.
No uncertain provider effect may be retried.

## Fixed procedure and evidence

Amendments 21–24 govern the exact branches and markers, four intended provider
mutations, A revocation within 60 seconds, B continuity, confidentiality scan
and no-model limit. The S8 executable refuses a dirty source tree, an existing
state directory, an unexpected source SHA, a missing positive review record,
or a reused identity. It verifies exact A-grant revocation before one negative
PR-update attempt and requires `grant_unavailable` with no additional provider
attempt. It records A/B grant and container IDs, labels and cleanup evidence.

Keep raw output private until scanned; then commit sanitized observation,
journal and hashes without provider token or run capabilities. Leave remote
branches and PRs for review. A lost or ambiguous acknowledgement ends the run
without a retry. The user has authorized this bounded S8 run and confirmed the
token's selected-repository-only scope; no separate API proof is required.

Published CI on `ba8e7e3` passed Python 3.10 and 3.13 package-and-test jobs.
Local targeted test rerun was unavailable in this environment: the root venv
lacks `PyJWT`, and the worktree's test venv lacks `pytest`. This is not treated
as a live acceptance check. No S8 provider write or model call is authorized
until the positive pre-run review of the final head.
