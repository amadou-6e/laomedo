# Pull request records

## HTTP object and method vocabulary (C1)

`PullRequestServer` in `server.py` owns loopback lifetime, the gateway and private
bearer token. Module-level `PullRequestHandler` in `handler.py` implements
`do_POST`, `reply` and a private-log-suppressing `log_message`, using only its
server instance bindings. No nested class, captured credential or global binding
is needed.

`GitHubPRGateway` owns `discover`, `execute`, `prepare_feedback` and
`apply_feedback`. Selection and feedback remain PR concerns. The handler keeps
all four current routes, accepted field sets, 1-MiB request cap, JSON encoding,
status codes and unknown-write classification. Failure after possible dispatch
never becomes advice to blindly retry. HTTP adapter relocation is a later C3
checkpoint; current module/CLI entrypoints and canonical models stay unchanged.

## Canonical values

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
