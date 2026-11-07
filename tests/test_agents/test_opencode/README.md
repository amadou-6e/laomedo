# Opencode controls

Existing Agent regressions for this concern. Run `python -m unittest discover -s tests/test_agents -t tests -v`. Internal controls do not establish real provider acceptance.

`test_records.py` preserves cache/reasoning accounting and the native runtime identity payload.

`test_recovery.py` retains the private command failure, cancellation and receipt
recovery controls from the earlier provider implementation. It uses internal
collaborators and does not establish live provider acceptance.
