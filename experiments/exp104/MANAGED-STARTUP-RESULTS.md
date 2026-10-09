# Windows task startup S1 result

Executed once on 2026-10-09 after positive independent pre-run review posted
on draft #105. Protocol: `7545de9`; first probe implementation: `e983a13`;
review-directed fixes: `f6740ae`, then exact executed source
`065eea52d4d79cee2f81a24a6018c57b885522aa`. Earlier probe heads were never
executed. The source checkout was clean before the single-use claim.

Machine-generated `MANAGED-STARTUP-OBSERVATION.json` is copied unchanged from
the probe output, with SHA-256
`c2bf7b11bc5b6d0fdf695ca76e8529a372856794bb3578ec15c81d64419f1966`.
It contains no token, SID, username, private path or command line. Its process
IDs are ephemeral observations, not durable identity for future operations.

## Observed

- Both managed service tasks started under the limited interactive user with
  IgnoreNew. Each Python venv launch had two process IDs, unchanged across
  the disposable stand-in runner-tree kill.
- The host service published the expected module root; its heartbeat advanced
  after the kill. No provider attempt was recorded.
- Both tasks were stopped/unregistered and neither matching service process
  remained. A separate read-only post-check found none of the four saved PIDs
  and no Laomedo tasks. No permanent task was left installed.
- Zero model turns, grants, GitHub calls, real credentials and Docker actions.

## Assessment and limits

Pass for this narrow independent task startup and stand-in-tree survival
diagnostic. It is not production deployment acceptance, a real runner loss,
grant revocation, container teardown, logout/power-loss survival, Task Scheduler
failure recovery or verifier cleanup during an in-flight Docker stage.
Historical S11 provider evidence does not validate this newer source.
#97/#105 remain drafts pending their outstanding acceptance work. No unknown
provider effect was retried and no live acceptance identity was consumed.
