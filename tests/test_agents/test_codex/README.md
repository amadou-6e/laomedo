# Codex launch policy

`test_sandbox.py` protects split-controller credential isolation, credential-free
cleanup, trusted daemon/image identity and bounded launch policy. It contains
the eleven existing sandbox-policy cases. Each case owns its temporary state.
Shared repository discovery uses `support.paths.repository_root`; support-only
modules retain descriptive names. The moved suite has no import-forwarding facade.

Run `python -m unittest test_agents.test_codex.test_sandbox -v` with `tests` on
PYTHONPATH, or use discovery from the parent README. These internal regressions
do not establish live Docker/credential acceptance.
