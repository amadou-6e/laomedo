# Shared Agent activity

`ActivityStore` retains owner-scoped invocations, receipts and observations;
`ActivityCapture` observes one runner attempt (formerly `RunnerCapture`). `CaptureIdentity` and `ActivityInvocation` in `models.py`
carry correlated values. `routes.py` presents the authenticated read-only API.

Vocabulary: `start` reserves capture identity; `bind` binds the actual remote run;
`append`-family operations retain observations; `finish` seals an observed outcome;
read methods inspect retained evidence without running a model. Exact method names
are listed below; record schemas and provider IDs do not change during renaming.

Provider-native interpretation is being separated behind registered adapters.
Current `projection.py` and `cost.py` still contain Codex-specific interpretation;
that is remaining integration work, not completed common normalization. Partial
capture cannot be upgraded merely because execution ended successfully.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `ActivityCapture` | `capture.py` | `__init__`, `feed`, `bind`, `observe`, `dispatched` |
| `CaptureIdentity` | `models.py` | `from_values` |
| `ActivityInvocation` | `models.py` | Validated fields / inherited interface |
| `Settings` | `settings.py` | `settings_customise_sources` |
| `ActivityStore` | `store.py` | `__init__`, `db`, `start`, `append`, `bind`, `graph_runs`, `claim_attempt`, `finish`, `runs`, `read` |
