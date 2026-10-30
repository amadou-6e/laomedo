# Work graph value ownership

`GraphSnapshot`, `WorkItem` and dependency values remain the canonical source
graph. `WorkSnapshot` and `WorkLaunchBinding` in `models.py` group the selected
work identity/content digest and its frozen/current authorization evidence.
`to_payload()` preserves the existing launch/hash preimages. Preflight still
refreshes source, checks prerequisites and validates override admission before
constructing those values; a binding is evidence, never a grant.

Dynamic graph indexes and serialized graph-schema projections remain mappings.
`WorkflowRunStore` retains transactions and historical lifecycle records; this
increment does not reject old journals through a new strict reader.

`WorkGrantLimits` groups the existing timeout and turn limits. `WorkLaunchGrant`
constructs the safe response of a successfully redeemed local grant; it grants no
new authority and does not replace the caller's admission checks. Its
`to_payload()` keeps the callback contract. `WorkGrantReference.to_payload()`
keeps the CLI's flat nonsecret receipt, while `WorkLaunchResult.to_payload()`
keeps the existing eight-field local launch summary.
