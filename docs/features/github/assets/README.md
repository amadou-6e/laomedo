# GitHub visual provenance

| Image | Source | Capture | Evidence boundary |
| --- | --- | --- | --- |
| issue-node.png | Current `components/laomedo/github_issue.py` compiled into a documentation graph | 2026-10-28 | Actual unconfigured form; no GitHub mutation |
| pr-node.png | Current `components/laomedo/github_pr.py` compiled into a documentation graph | 2026-10-28 | Actual unconfigured form; no GitHub mutation |
| issue-viewer-empty.png / pr-viewer-empty.png | Actual installed viewer with no picker selection | 2026-10-28 | Empty states only; no fabricated provider response |
| create-pr-mock.png | Companion HTML mockup | This documentation increment | Proposed new-PR UI; illustrative content, no PR created |

The current app's read-only PR inspection returned HTTP 400, so these captures
do not show a populated viewer or claim a successful provider read. No mock
response was substituted. Screenshots were captured in headless Edge; the mockup
is separately labelled. No graph was executed or external write requested.
