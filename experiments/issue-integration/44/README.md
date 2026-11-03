# EXP-14: issue-publication acknowledgement loss

Status: synthetic fault-injection observation, 2026-10-02. Governing draft:
`amadou-6e/specs@6ff899522af54db3f8526c563f73500056ad8c5e`,
`projects/laomedo/subsystems/issue-integration/design/decision-readiness.md`
E01 and IF-12. Implementation baseline: `laomedo/origin/develop@12adee2`;
candidate branch: `exp/44`. EXP-02's read-only evidence is in PR #51; this
probe has no dependency on its unmerged code.

## Protocol

`probe.py` persists a reviewed synthetic proposal, target repository, bytes
hash, reviewer, decision and attempt ID before a POST. It marks the attempt
`sending` durably before contacting a localhost-only fake GitHub endpoint.
The fake server fsyncs its accepted request ledger before returning 201.
Each test runs the publisher in a child process and terminates it with
`os._exit(17)` at one selected point, then inspects the persisted intent and
fake-server ledger after that process is gone. No automatic retry is coded.

| Kill point | Fake server accepts | Restart inspection | Interpretation |
| --- | --- | --- | --- |
| After `sending` is saved, before POST | 0 requests | `unknown`, no issue ref | Conservative uncertainty; no claim of remote failure. |
| After server acceptance, before response is saved | 1 request | `unknown`, no issue ref | Remote issue may exist; blind retry would duplicate it. |
| After response is saved | 1 request | `published`, issue #123 | Acknowledged result survives publisher death. |

An unreviewed proposal, changed reviewed bytes, and a non-loopback endpoint
are rejected before any POST. A second send from an unresolved `sending`
record is rejected. Synthetic fixture text and the fake ledger exist only in
test temporary directories; no GitHub issue was created or changed.

`python -m unittest tests.test_issue_publication_probe -v`: 4 passed.
`python -m unittest discover -s tests -p 'test_*.py'`: 106 passed.
`git diff --check`: clean. Zero model turns and zero external writes.

## Limits and handoff

This is a probe, not a production publication service or GitHub exactly-once
guarantee. The child process is killed, not the full fate-shared
Langflow/Laomedo backend; the test does not verify UI state projection,
host-power-loss durability, real GitHub indexing delay, or grant enforcement.
The `unknown` result deliberately requires reconciliation or user resolution
before any retry. EXP-15 must first inspect GitHub's current API semantics and
obtain explicit disposable-repository write authorization before a live test.
