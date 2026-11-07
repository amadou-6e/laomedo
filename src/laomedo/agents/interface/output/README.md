# Agent output contract

This public boundary owns declarative response requirements and their validation.
The function-only API in `utils.py` validates the same requirements for native
prechecks and graph callers. It is the single owner of the serialized contract
and its validation rules.

| Existing method vocabulary | Contract |
| --- | --- |
| `requirements(specification)` | Validate/copy the closed specification and calculate its immutable revision. |
| `verify_requirements(reference)` | Check the reference shape and revision against the canonical specification. |
| `evaluate(reference, submission)` | Evaluate a response against the same requirements. |
| `evaluate_envelope(...)` | Validate the submission envelope and return routing evidence. |

These are pure data checks: no model request, graph traversal, GitHub operation or
publication effect is authorized here. Stable errors and serialized forms must
survive object extraction. Graph discovery/routing belongs to
`integrations/langflow/output`; downstream callers use this same contract.
