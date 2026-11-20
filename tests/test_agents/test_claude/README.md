# Claude controls

Existing Agent regressions for this concern. Run `python -m unittest discover -s tests/test_agents -t tests -v`. Internal controls do not establish real provider acceptance.

[Authentication controls](test_authentication.py) protect native authentication
and Docker control deadlines. Retired host-login copying controls are archived
on `exp` at `b594dab6`, outside production test discovery.

`test_records.py` fixes the full privacy-preserving telemetry environment and excludes the test access header from ordinary model rendering.

`test_recovery.py` retains the private command failure, cancellation and receipt
recovery controls from the earlier provider implementation. It uses internal
collaborators and does not establish live provider acceptance.
