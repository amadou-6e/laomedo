# Work graph tests

`test_import.py` protects repository-page import, dependency projection and immutable
snapshot integrity. `test_runs/` protects run reservation, identity and persistence.
These are graph concerns rather than provider lifecycle behavior.

Run `python -m unittest discover -s tests/test_work_graph -t tests -v`.
The package uses the shared repository-root helper for checkout-owned input data;
it does not load historical campaigns or require the experiment branch.
