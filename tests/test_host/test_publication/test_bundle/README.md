# Frozen bundles

`test_stage.py` checks verification and binary export. `test_ownership.py` checks
exclusive reservation and exact-container reconciliation. `test_verifier.py`
checks worker claims, active run bindings and status replacement. These are
separate behavior owners sharing the frozen-bundle boundary; a successful stage
does not substitute for ownership or worker recovery checks.

Each TestCase owns its own inputs and cleanup. Existing test method names state
the expected outcome; setup and private scenario helpers remain with their case.

The production suite calls the installed bundle boundary directly. The historical
EXP-139 `verify_attempt` composition check belongs to `exp` at `8b2f2395`, under
`archives/agents-205/test-callers/files/tests/test_host/test_publication/test_bundle/test_stage.py`.
It tested the campaign wrapper, not an installed API. Its exact original bytes are
archived; it is not counted as current production coverage. The eleven installed
stage controls remain: binary export/size/timeout, exact single ref, private verified
artifact, wrong baseline, changed frozen bytes, unsafe network, uncertain cleanup,
early container exit, failed binary stream, unreviewed image and wrong exported ref.
No production test loads the EXP-139 runtime to exercise these boundaries.
