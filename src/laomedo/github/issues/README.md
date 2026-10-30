# Issue records

## HTTP object and method vocabulary (C1)

`IssueServer` in `server.py` owns loopback lifetime, the gateway and its private
bearer token. `IssueRequestHandler` in `handler.py` is a module-level collaborator:
`do_POST` authenticates/parses/routes, `reply` writes the existing JSON response,
and `log_message` suppresses private request logging. Bindings come from
`self.server`, never a nested class closure or mutable global.

`GitHubIssueGateway.discover` lists matching choices; `execute` admits a selected
resource and any authorized operation; `_finish` preserves durable outcome
precedence. The handler retains the existing routes, exact field checks, 1-MiB
body cap, status codes and pre-dispatch/unknown-write distinction. A transport
failure during a write does not authorize another write. Client/server/CLI paths
stay in this package until the separately reviewed interface relocation.

## Canonical values

`GitHubIssue` in `models.py` is the canonical normalized issue value. Identity is
descriptive and grants no authority. `contract.issue_value()` preserves the
existing response admission and error categories, constructs this object, then
calls `to_payload()` at the public dictionary boundary. Labels are normalized
by the existing validator before construction. Null provider bodies become empty
strings; all nine normalized fields remain present. `issue_digest()` hashes the
unchanged canonical JSON payload.

The gateway owns filtering, authorization and effect reconciliation. A model
does not make HTTP calls, validate grants or retry unknown writes. Historical
journal readers are unchanged; these strict models describe new normalized values.

`GitHubOperationIntent` and `GitHubGrantBinding` in `github/models.py` own the
shared issue/PR idempotency preimage. Construct them only after the gateway's
existing admission and grant authentication; `to_payload()` preserves the old
hash inputs and does not validate or authorize a grant.
