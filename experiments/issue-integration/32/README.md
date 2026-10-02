# EXP-02: selected issue context and related PR classification

Status: observed read-only probe, 2026-10-02. Governing draft:
`amadou-6e/specs@6ff899522af54db3f8526c563f73500056ad8c5e`,
`projects/laomedo/subsystems/issue-integration/contract/interfaces.md` and
`design/decision-readiness.md`. Implementation baseline:
`laomedo/origin/develop@12adee2`; the candidate is branch `exp/32`.

## Protocol and observations

The candidate `laomedo.issue_context` fetches the selected issue twice around
its timeline read, reports a changed issue rather than a coherent snapshot,
and treats a failed or truncated timeline as incomplete. Timeline
cross-references to open PRs are *discovered candidates*, never a supplied
target. Mocked cases cover current text, a distinct supplied target, closed and
cross-repository PRs, pagination, inaccessible/moved/changed issue identities,
and a timeline failure. The transport test checks sanitized HTTP error classes.

After the mocks passed, read-only live calls used the existing `gh` login:

| Source | Observed non-secret result |
| --- | --- |
| `amadou-6e/laomedo#32` | Current issue identity and update marker returned; 0 open timeline-cross-referenced PRs; timeline complete; no supplied target. |
| `amadou-6e/specs#129` | Current issue identity and update marker returned; open timeline-cross-referenced PR #150; timeline complete; no supplied target. |

No issue body, private timeline payload, credential, or raw API response is
retained here. The second result proves separation for this observed pair, not
an exhaustive related-PR search across GitHub. A timeline can omit PRs that
never cross-referenced the issue; `related_prs_scope` says so explicitly.

`python -m unittest discover -s tests -p 'test_*.py'`: 109 tests passed.
`git diff --check`: clean. No model turn or GitHub write occurred.

## Limits and next handoff

The issue-context interface is not yet connected to Langflow launch setup.
This experiment does not choose a dispatch-time freshness policy, grant owner,
or PR continuation default. EXP-14 may use the same explicit distinction
between a reviewed publication intent and an observed remote effect, but its
fault injection is separate from this read-only probe.
