# EXP-104 S9 pre-run pin (unexecuted)

Status: frozen review candidate, 2026-10-08. S7 and S8 were retired without
live calls. No S9 provider write or model turn has occurred. The single-use
identity is `exp104-s9-20261008-01`; the only target is
`ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`) at baseline
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.

## Exact sources

- Candidate implementation commit before this pin: `d58ba4448e02beeb7859384ebf1f3627a210ff48`.
- Probe `experiments/exp104/s9_probe.py`: Git blob `fae101c4e7dd140f899c6d640a5e0773db5ca719`.
- Tests `tests/test_exp104_s9_probe.py`: Git blob `b941726f39b6d0fddaf681fc185010c0a40968a9`.
- S9 amendment `experiments/exp104/AMENDMENT-25.md`: Git blob `f7c1a64c83c199c2ea3ea361d00a9fe5f83ef4cb`.
- Shared live probe `experiments/exp104/live_probe.py`: Git blob `662942efde8bf2994ed16b07c3ddc9628661a7e0`.
- Amendments 21–24 remain governing, with amendment 25 replacing the S8
  identity and clarifying the import-origin gate.
- Governing Laomedo specs revision: `amadou-6e/specs@5e77d864f4b5f2064adf07e86cdd5fb90a883122`.

The invocation must pin the **final** PR head after this record is committed.
The independent read-only reviewer must inspect that exact head and give an
explicit positive S9 pre-run verdict. Save a private review record with S9
identity, final source SHA and verdict before invocation. A later change to
code, protocol or tests requires another fresh identity and review. No
uncertain provider effect may be retried.

## Fixed procedure and evidence

Amendments 21–25 govern the branches and markers, four intended provider
mutations, A revocation within 60 seconds, B continuity, confidentiality scan
and no-model limit. Before reading the token, the executable refuses a dirty
source tree, a mismatched head, or any imported `laomedo` module outside the
reviewed checkout. The host service and runners start in that checkout. The
resolved module root is recorded. The other S8 denial and cleanup gates carry
forward unchanged.

Keep raw output private until scanned; then commit sanitized observation,
journal and hashes without provider token or run capabilities. Leave remote
branches and PRs for review. An ambiguous acknowledgement ends the run without
a retry. The user has authorized this bounded run and confirmed the token's
selected-repository-only scope; no separate API proof is required.

Local validation at candidate `d58ba44`: synthetic Windows Docker route,
11 passed with 3 subtests; non-Langflow host tests, 329 passed with 8 skipped
and 45 subtests. The full `tests/` command could not collect the Langflow
suite because `lfx` is not installed in the local test environment. Published
CI at the final head must also pass. These checks are not live acceptance
evidence. No S9 provider write or model call is authorized until the positive
pre-run review of the final head.
