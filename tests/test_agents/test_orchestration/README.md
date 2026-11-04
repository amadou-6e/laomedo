# Orchestration controls

Existing Agent regressions for this concern. Run `python -m unittest discover -s tests/test_agents -t tests -v`. Internal controls do not establish real provider acceptance.

Handoff/fresh-request identity checks use data/request-records.json with independent canonical preimages and digests. These are internal compatibility fixtures, not real provider acceptance.
