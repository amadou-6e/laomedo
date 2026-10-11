# EXP-104 S10 pre-run pin (unexecuted)

Status: frozen review candidate, 2026-10-08. S7 and S8 were retired
unexecuted; S9 stopped before any provider attempt. No S10 provider write or
model turn has occurred. Identity: `exp104-s10-20261008-01`. Only target:
`ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`) at baseline
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.

## Exact sources

- Candidate implementation commit before this pin: `5d0b229d24a41ec86fa6983fd9fc785df5eb83a9`.
- Probe `experiments/exp104/s10_probe.py`: Git blob `6aad72caee1d955625e3c12e4102a592b4c9a3a0`.
- Tests `tests/test_exp104_s10_probe.py`: Git blob `110b64ed448a12053cd9ace3fc5e69075a55604e`.
- S10 amendment `experiments/exp104/AMENDMENT-26.md`: Git blob `92f193048660d5be3d47d50a5a11058d6b11fed5`.
- Shared helper `experiments/exp104/live_probe.py`: Git blob `9b775fc4c5fe077838864b629a30727de4d9b2b6`.
- Host service `laomedo/host_services.py`: Git blob `e107890ac2ee9fcf6fd835a6a7f8bc308c676feb`.
- Amendments 21–25 remain governing with amendment 26's replacement of the
  S9 identity and directly owned process rule.
- Governing Laomedo specs revision: `amadou-6e/specs@5e77d864f4b5f2064adf07e86cdd5fb90a883122`.

The invocation must name the **final** PR head after this pin is committed.
An independent read-only reviewer must inspect that exact head and give an
explicit positive S10 pre-run verdict. Save a private review record with the
S10 identity, final source SHA and verdict before invocation. A later source,
test or protocol change requires another fresh identity and review.

## Fixed procedure and evidence

Amendments 21–26 govern the two new branches, four intended provider writes,
A revocation within 60 seconds, B continuity, exposure scan, no-model limit
and no ambiguous retry. The S10 executable retains the clean-tree, exact SHA,
module-origin, exact grant, container and denial gates. It starts the host
service and both runners through the direct base interpreter, with the source
checkout and active venv site-packages explicitly on their import path. The
host service publishes its module root and actual PID; the probe checks both
and records them before any provider write. Runner imports are checked too.

Keep raw output private until scanned, then commit sanitized observation,
journal and hashes without provider token or run capabilities. Leave remote
branches and PRs for review. User approval and selected-repository-only token
scope confirmation carry forward from amendment 26. Do not rerun S9.

Local validation at candidate `5d0b229`: synthetic Windows Docker route,
12 passed with 3 subtests, including direct parent/child PID equality and
exact grant/cleanup checks; non-Langflow host tests, 330 passed with 8 skipped
and 45 subtests. Langflow tests could not collect locally because `lfx` is
not installed in the test venv. Published CI at the final head must pass.
These checks are not live acceptance evidence. No S10 provider write or
model call is authorized until positive review of the final head.
