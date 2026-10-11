# EXP-104 amendment 11: wait for the restart sweep before admitting C

Date: 2026-10-07. Status: frozen before any `-02` run or mediated effect.
The first run (`-01`) remains incomplete and is not retried. The fresh
identity `exp104-d2-20261007-02` from amendment 10 has not yet been used.

The local-only Docker control at the pinned image passed: the exact labelled
container launched, was inspected as owned, and was removed. It used no
GitHub credential or model turn. Inspection of `-01`'s saved lease records
shows B's restart cleanup finished about five seconds after the new service
started. C's lease was accepted near the end of that sweep, then its initial
heartbeat immediately expired; no C container was observed. This timing is
consistent with C waiting for acceptance while the single-threaded sweep
cleaned B. Because the runner's stderr was not captured, this is a diagnosis,
not a proven exception message.

For `-02`, the probe must wait for B's durable `service_restart` result and
verified exact-container cleanup **before** approving or starting C. A failed
or absent sweep result ends the run without a C launch. The script also keeps
sanitized progress at each phase and records a safe runner-start error code.
No earlier A effect or branch is reused. The repository-scoped acceptance
criteria remain unchanged and unmet.
