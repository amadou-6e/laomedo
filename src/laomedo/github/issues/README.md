# Issue records

HTTP clients, handlers, servers, Settings and trusted startup live in
`github/interface/issues/`; see that leaf README for supported protocol and
object/method vocabulary. This package retains domain behavior and values.

## Canonical values

`GitHubIssue` in `models.py` is the canonical normalized issue value. Identity is
descriptive and grants no authority. `contract.issue_value()` preserves the
existing response admission and error categories, constructs this object, then
calls `to_payload()` at the public dictionary boundary. Labels are normalized
by the existing validator before construction. Null provider bodies become empty
strings; all nine normalized fields remain present. `github.contract.issue_digest()` hashes the unchanged canonical JSON payload.

The gateway owns filtering, authorization and effect reconciliation. A model
does not make HTTP calls, validate grants or retry unknown writes. Historical
journal readers are unchanged; these strict models describe new normalized values.

`GitHubOperationIntent` and `GitHubGrantBinding` in `github/models.py` own the
shared issue/PR idempotency preimage. Construct them only after the gateway's
existing admission and grant authentication; `to_payload()` preserves the old
hash inputs and does not validate or authorize a grant.

## Read-only context reader and CLI

`context_reader.py` owns the existing read-only `gh` functions, and `context.py`
owns the actual CLI parser and `main() -> int`, retaining its existing `-m`
entrypoint. Shared repository/label/digest primitives live in `github/contract.py`; normalized
Issue response admission and patch validation stay in `issues/contract.py`.

| Function | Interface and effects |
| --- | --- |
| `fetch_context(repository, number, *, supplied_target_pr, request, fetched_at, max_timeline_pages)` | Read issue/timeline pages and confirm the issue again; return the existing context dictionary, never edit GitHub. Injected `request` retains its current signature/default. |
| `_gh_json(path)` | Run the existing bounded `gh api` read; retain safe `IssueContextError.code` categories without exposing stderr. |
| `_issue`, `_pr_candidates` | Admit the existing weaker context schema and distinguish discovered PR candidates from an explicitly supplied target. No authorization is granted. |
| `main()` | Parse existing arguments, call the reader, print the existing JSON success/error result and return its existing exit status. |

Timeline failure remains incomplete evidence, never a confirmed empty search;
changed issue text remains an explicit error. Context dictionaries intentionally
do not become node `GitHubIssue` records. Caller migrations preserve all function
arguments and default bindings. There is no compatibility `utils.py` runtime.
