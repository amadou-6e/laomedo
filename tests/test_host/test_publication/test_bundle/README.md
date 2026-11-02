# Frozen bundles

`test_stage.py` checks verification and binary export. `test_ownership.py` checks
exclusive reservation and exact-container reconciliation. `test_verifier.py`
checks worker claims, active run bindings and status replacement. These are
separate behavior owners sharing the frozen-bundle boundary; a successful stage
does not substitute for ownership or worker recovery checks.

Each TestCase owns its own inputs and cleanup. Existing test method names state
the expected outcome; setup and private scenario helpers remain with their case.
