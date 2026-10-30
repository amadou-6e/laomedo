# Issue records

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
