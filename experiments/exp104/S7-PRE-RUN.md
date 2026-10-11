# EXP-104 S7 pre-run pin (unexecuted)

Status: frozen review candidate, 2026-10-08. No S7 provider write or model
turn has occurred. The executable probe is single-use and refuses a prior
state directory, mismatched source SHA, missing positive review record, or an
approval ID other than `exp104-s7-20261007-01`.

## Exact sources

- Candidate implementation commit: `ddb3a273597fb0aa6b7447f379eaf8409db1d3ac`.
- Probe `experiments/exp104/s7_probe.py`: Git blob
  `cc75b795bcc470bfaad635983d3bf2526df12382`.
- Tests `tests/test_exp104_s7_probe.py`: Git blob
  `c65d72844178f4cc0ccd2df5f75dda70dbc8f3a2`.
- Amendments 21, 22 and 23: Git blobs `00bc262ea22014ddecb802f434cb152b9baf700b`,
  `a4d366c34daf1fb13bcacb73e05c31ae831abb43`, and
  `faaac533f5a07498069767a022614557f2e4ddfa`.
- Governing Laomedo specs revision:
  `amadou-6e/specs@5e77d864f4b5f2064adf07e86cdd5fb90a883122`; see the
  agent-execution validation and decision-readiness pages at that revision.

The eventual invocation must pin the **final** PR head after this record is
committed, not only the candidate commit above. The read-only reviewer must
inspect that exact final head and issue an explicit positive S7 pre-run
verdict. Save a private review record containing its identity, final source
SHA and verdict before invocation. Any code, protocol, or test change after
review requires a new pin and review; no uncertain effect may be retried.

## Fixed procedure and evidence

Amendments 21–23 govern the identity, repository, baseline, branch names,
four intended provider writes, denial, timing and user-authoritative token
scope. The executable probe saves an observation before dispatch, durably
records planned effect IDs, refuses any write whose response is not confirmed,
and leaves remote refs/PRs in place. It records provider-attempt counts,
monotonic runner-loss/revocation times, exact PR read-backs and local cleanup.
Its output remains private until scanned and reviewed; then commit sanitized
raw observation, journal and hashes without the provider token or run
capabilities. The post-loss denial must add zero provider attempts; A must be
revoked within 60 seconds and B must still create its PR.

Synthetic validation at candidate commit: the host suite passed 323 tests
with 7 skips and 45 subtests; opt-in Windows Docker checks passed 10 tests,
including the S7 runner/container/client route. These do not prove the live
GitHub result or production service-manager survival. #100 literal `git`/`gh`
parity, #93 service deployment and #22 real-agent cancellation remain open.
