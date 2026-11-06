# Publication handoff values

`PullRequestPublicationRequest` in `models.py` groups the already admitted head,
base, title, body, correlation marker and draft flag. `to_payload()` preserves the
existing private journal and host-mediator contract. It is a creation request,
so it deliberately has no PR number or reference yet.

`HandoffStore` retains transactions, effect reservation, authorization and
publication phase transitions. Constructing a request neither sends it nor
authorizes a write. The marker remains host-generated and travels with the
request for later reconciliation; ambiguous writes are not automatically repeated.
