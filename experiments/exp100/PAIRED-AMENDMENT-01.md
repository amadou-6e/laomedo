# Prospective amendment 01: fixed GraphQL read, before implementation/capture

The independent review of S11's prospective protocol identified that the original
EXP-100 matrix includes a GraphQL-read positive. Recording that as unsupported
cannot establish complete matrix acceptance. The user selected full #100
completion, not weakening that criterion. No S11 capture has run; preserve the
original protocol and amend prospectively before code or evidence execution.

Implement exactly one fixed query mapped to existing explicitly granted issue_list:

`query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issues(first:30,states:OPEN){nodes{number title body}}}}`

Native syntax: gh api graphql --method POST --input FILE (or stdin). JSON must
contain only query and variables; query must match exactly, variables only owner
and name matching the selected repository. No fragments, alternate selections,
aliases, pagination, mutation, additional variables or cross-repository values.
Reject nonmatching inputs before mediation. Project typed issue_list results to
that fixed GraphQL shape; validate requested scalar fields. This is a fixed
semantic read adapter, not arbitrary GraphQL parsing or a provider GraphQL proxy.
No new operation/grant/default-authority permission. Native formatting/syntax
differences remain explicit. Prior tests/records are not re-labelled.

Add positive/query-shape tests and zero-dispatch controls for mutation, fragments,
cross-repo variables, additional variable/input keys and malformed readback.
Update/review canonical specs and exact source before S11 pre-run. The final
manifest must pin the merged native issue/GraphQL classifier revision in addition
to the earlier b319630 baseline, both sides' exact vectors/input/attempt caps,
reviewed issue snapshot (including marker), and container credential inventory.
Perform a zero-write loopback gh-api feasibility check before the capture manifest;
retain any failure as development/setup, not quietly altering frozen acceptance.
