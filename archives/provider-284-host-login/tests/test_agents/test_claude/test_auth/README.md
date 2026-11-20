# Claude authentication controls

These internal regressions belong to the provider's authentication concern.
They do not establish real login, provider or graph acceptance.

| File | Boundary |
| --- | --- |
| `test_mirror.py` | Opt-in host admission, access-only payload, expiry and native copy failures. |
| `test_session.py` | Exact-length writer protocol, SDK session ownership and cleanup/deadline guarantees. |
| `test_admission.py` | Concurrent copy serialization, queue deadline and release after failure. |

Run `python -m unittest discover -s tests/test_agents/test_claude/test_auth -t tests -v`.
The parent Claude concern discovers these cases normally; no forwarding suites or
campaign imports are needed.
