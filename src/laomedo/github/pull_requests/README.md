# Pull request records

`GitHubPullRequest` is the canonical normalized PR value; `PullRequestHead` groups
its nullable source repository, branch and immutable commit identity. `models.py`
owns these values; `contract.pr_value()` keeps existing manual admission and safe
error categories, then calls `to_payload()` for the public dictionary contract.
All thirteen normalized PR fields remain present. A deleted head repository is
explicitly null, a null body is empty, and labels retain existing normalization.

`to_payload()` means serialization, not authorization. The gateway retains grants,
feedback tickets, selected-PR checks and unknown-write reconciliation. The shared
canonical JSON digest and historical journal readers remain unchanged.

Shared `GitHubOperationIntent` groups the existing authenticated intent hash
inputs. `PullRequestFeedbackContext` in `models.py` groups a newly reserved PR
snapshot and its two monotonic expiry markers. `to_payload()` preserves the
existing ticket context; historical ticket readers and authorization stay in
the gateway. These values neither create tickets nor perform an operation.
