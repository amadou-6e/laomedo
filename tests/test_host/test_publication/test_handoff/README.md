# Host publication handoff

`test_store.py` protects output validation, artifact binding, publisher handoff,
uncertain writes, expiry, cancellation and readback. `issue()` creates a scoped
grant; `begin()` starts its handoff; `pushed()` supplies an internal stage receipt;
`freeze()` validates output; `publish()` exercises the host publisher boundary.
These helpers belong to their case and do not borrow another TestCase.

A rejected handoff must not block another run on the same branch. Publishing
before readiness refuses without transport. Separately authorized PR operations
retain their existing mediation contract; this suite adds no blanket ban.
Fake transport/verified bytes are internal controls, not real GitHub, Docker
verification or graph acceptance.

Run `python -m unittest discover -s tests/test_host/test_publication/test_handoff -t tests -v`.
