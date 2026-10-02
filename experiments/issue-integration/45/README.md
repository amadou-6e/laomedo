# EXP-15: live GitHub issue-create reconciliation

Status: observed in a private disposable repository on 2026-10-02. Governing
draft: `amadou-6e/specs@6ff899522af54db3f8526c563f73500056ad8c5e`,
`projects/laomedo/subsystems/issue-integration/design/decision-readiness.md`
E01 and IF-12. Implementation baseline: `laomedo/origin/develop@12adee280a313b3dd5e7ea2b0e60e06aba0ff785`;
candidate branch: `exp/45`. Prerequisite synthetic evidence: EXP-14 PR #52.

## Authorization, API, and protocol

The user explicitly authorized a disposable repository and issue writes on
2026-10-02. We created the private, initially empty
[`amadou-6e/laomedo-exp15-disposable`](https://github.com/amadou-6e/laomedo-exp15-disposable)
repository and left it intact. Authentication used the existing `gh` login,
`gh` 2.98.0, and GitHub REST API version `2022-11-28`; no token is stored in
the evidence. The [create/list issue endpoint](https://docs.github.com/en/rest/issues/issues)
has no documented idempotency-key parameter; GitHub
[search](https://docs.github.com/en/rest/search/search) is a separate indexed
query. A missing result from either endpoint is therefore not proof that a
POST failed. These API observations are interpretations of the documented
contract, not an exactly-once guarantee.

`live_probe.py` saved a fresh marker and local attempt state before a single
POST, discarded that POST's status and body, then made 11 *pairs* of read-only
repository-list and search queries. It did not resend. It subsequently created
one acknowledged control and one near-marker control. Each lookup filters
returned issue bodies by an exact `EXP15-MARKER:` line, excluding PRs. The
first page is sufficient only because this new repository has fewer than 100
issues; the probe fails closed at that page size.

Run command, executed once:

```text
python experiments/issue-integration/45/live_probe.py --execute --evidence experiments/issue-integration/45/evidence.json
```

The durable, sanitized [evidence.json](evidence.json) contains the full UTC
timestamps, elapsed times, IDs, search completeness flags, and observations.
Its run ID is `3338168cb0d748b29d1de1227117e69d`; the tested exact marker
is `exp15-3338168cb0d748b29d1de1227117e69d`.

| Observation after suppressed POST process returned | Repository list | Search | Interpretation |
| --- | ---: | ---: | --- |
| 1.297 s | 0 | 0 | Negative lookups were not evidence of failed publication. |
| 2.719 s | 0 | 0 | Still absent from both queries. |
| 4.047 s | issue #1 | issue #1 | Both found one exact marker. |
| 5.641–61.328 s (8 more samples) | issue #1 | issue #1 | Exact match remained stable in this observation window. |

The suppressed POST produced [issue #1](https://github.com/amadou-6e/laomedo-exp15-disposable/issues/1),
GitHub ID `5682567402`. Acknowledged control [#2](https://github.com/amadou-6e/laomedo-exp15-disposable/issues/2)
has ID `5682578548`; near-marker control [#3](https://github.com/amadou-6e/laomedo-exp15-disposable/issues/3)
has ID `5682578820`. A subsequent raw search for the target marker returned
both #1 and #2 (`total_count=2`, `incomplete_results=false`), illustrating
why text-search hits require exact body-marker verification. There were zero
duplicate POST attempts and no cleanup writes.

## Assessment and limits

The conservative candidate policy is: persist the reviewed bytes and marker
before posting; after an acknowledgement is lost, keep the attempt `unknown`,
query/list by marker, require exactly one exact-body match before binding its
issue ID, and do not automatically POST again after a negative or ambiguous
lookup. More than one exact match is a failure requiring manual resolution.

This run measures a *visibility interval* of >2.719 s and <=4.047 s from the
POST process returning to a successful pair of queries. It does **not** prove
a safe wait after which absence licenses a retry: only one suppressed attempt,
one repository, one auth route, and one time period were sampled. The list and
search calls ran sequentially, so individual endpoint visibility times are
not isolated. Discarding the CLI response simulates acknowledgement loss to
the caller, not a true network partition or backend crash. The `unknown`
publication state still needs an approved IF-12 contract update before this
can become product behavior. The three disposable issues remain open because
their closure was not authorized.

`python -m unittest tests.test_issue_publication_live_probe -v`: 3 passed.
Full suite and CI results are recorded on the PR. Zero model turns; three
issue-create writes; 22 scheduled read queries plus verification reads.
