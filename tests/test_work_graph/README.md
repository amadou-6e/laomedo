# Work graph tests

`test_import.py` protects repository-page import, dependency projection and immutable
snapshot integrity. `test_runs/` protects run reservation, identity and persistence.
These are graph concerns rather than provider lifecycle behavior.

Run `python -m unittest discover -s tests/test_work_graph -t tests -v`.
The package uses the shared repository-root helper for checkout-owned input data;
it does not load historical campaigns or require the experiment branch.

`fixtures/corpus.json` and `frozen-flow.json` preserve the accepted EXP-16 and
EXP-03 inputs byte for byte. `timeout-observation.json` preserves the accepted
EXP-65 result used by the timeout-projection controls. They are historical
characterization inputs, not current graph templates or new execution evidence.
The related launch/timeout tests read these concern-owned copies, not experiments.
