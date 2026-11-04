# Activity controls

`test_store.py` protects installed ActivityStore receipt retention, replay and
conflicting source IDs, pagination, partial/closed captures, usage uncertainty,
owner isolation and read-only access. Store checks run in normal core discovery;
HTTP route checks require FastAPI and skip only when that package is absent.
An import failure inside an installed integration is a failure.
`test_trace_join.py` protects graph/runner identity binding, conflict refusal,
late acknowledgements and recovery without redispatch.

These production APIs own the useful identity, replay and uncertainty controls
formerly illustrated by EXP-05 and EXP-09. Those prototypes have a different
EvidenceStore schema and their process-kill oracle remains historical, not an
assertion that the current ActivityStore passes those exact crash boundaries.
Their exact source is preserved on `exp` in `archives/agents-205/files/experiments`.
Production CI uses installed-package discovery and does not execute either
prototype. No experiment checkout is required for this suite.

Run `python -m unittest discover -s tests/test_agents/test_activity -t tests -v`.
Internal controls do not establish real provider or browser acceptance.

`test_records.py` preserves native attempt fields and the distinction between omitted and explicit provider freshness.

`test_envelope.py` runs both actual projectors against eight independent event
and JSON output cases in `data/projector-records.json`. These preserve field
order, omissions, Unicode escaping and nested values from the existing writers.
The cases contain no source-body digests and require no historical checkout.
