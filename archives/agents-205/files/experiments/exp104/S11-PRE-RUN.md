# EXP-104 S11 pre-run pin (unexecuted)

Status: frozen review candidate, 2026-10-08. S7/S8 were retired unexecuted;
S9/S10 stopped before provider writes and are consumed. No S11 provider write
or model turn has occurred. Identity: `exp104-s11-20261008-01`. Only target:
`ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`) at baseline
`1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.

## Exact sources

- Candidate implementation commit before this pin: `382673a504e58f2c8630a88571a81eb53c32e0e2`.
- Probe `experiments/exp104/s11_probe.py`: Git blob `14dde2896dee915afdb5ae8e59d09bf5a9e1f96c`.
- Tests `tests/test_exp104_s11_probe.py`: Git blob `e1adcd755b458fbd1356cc923fd8b1c9288a0d2b`.
- S11 amendment `experiments/exp104/AMENDMENT-27.md`: Git blob `5689bc0e910ff403350a66ad4115e81fdd507cc7`.
- Shared helper `experiments/exp104/live_probe.py`: Git blob `9b775fc4c5fe077838864b629a30727de4d9b2b6`.
- Host service `laomedo/host_services.py`: Git blob `e107890ac2ee9fcf6fd835a6a7f8bc308c676feb`.
- Amendments 21–26 remain governing, with amendment 27 replacing S10's
  identity and requiring fresh service heartbeats before setup grants.
- Governing Laomedo specs revision: `amadou-6e/specs@5e77d864f4b5f2064adf07e86cdd5fb90a883122`.

The invocation must name the **final** PR head after this pin is committed.
An independent read-only reviewer must inspect that exact head and give an
explicit positive S11 pre-run verdict. Save a private review record with the
S11 identity, final source SHA and verdict before invocation. Any later
source, test or protocol change requires another fresh identity and review.

## Fixed procedure and evidence

Amendments 21–27 govern the two new branches, four intended provider writes,
A revocation within 60 seconds, B continuity, exposure scan, no-model limit
and no ambiguous retry. S11 retains strict reviewed-source, direct process,
module-origin, exact grant, container and denial gates. Before the first
setup grant, it waits for the exact live host service and both fresh wall and
monotonic heartbeat files under the lease service's own staleness limit. A
service exit or timeout fails closed without a provider write.

Keep raw output private until scanned, then commit sanitized observation,
journal and hashes without provider token or run capabilities. Leave remote
branches and PRs for review. User approval and selected-repository-only token
confirmation carry forward. Do not rerun earlier identities.

Local validation at candidate `382673a`: synthetic Windows Docker route,
13 passed with 3 subtests, including a delayed heartbeat control, direct PID
equality, exact grant and cleanup checks; non-Langflow host tests, 331 passed
with 8 skipped and 45 subtests. Langflow tests could not collect locally
because `lfx` is absent. Published CI at the final head must pass. These
checks are not live acceptance evidence. No S11 provider write or model call
is authorized until positive review of the final head.
