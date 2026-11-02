# Prospective safety amendment, 2026-10-11

Original protocol0b4af95 and executablef93d399 remain unchanged historical pins.
Independent pre-run review disapproved before any model turn or live acceptance
attempt. This amendment is committed before implementing the corrections.

- Both real-stage A and zero-turn control B grants permit only actions_read.
  No live write is authorized in this new case. The post-revocation PR-create
  request must return grant_unavailable before operation dispatch; a live grant
  would refuse that operation by scope. Earlier S13 actual write-grant revocation
  evidence remains the separate proof of that boundary. This fresh check does
  not claim an agent-held live write grant.
- Wait for the exact lease result.json no later than kill_completed+60seconds.
  Require cleanup_verified and bounded cleanup_finished_at_monotonic, then obtain
  an independent exact-Docker absence observation within the same60second bound.
  Revocation and container removal have separate recorded times.
- Follow frozen cleanup order: revoke grants, remove exact containers/stages,
  release B and wait workers, remove exact task actions. Missing state after the
  dispatch gate means unverified cleanup, not vacuous success.
- Check the overall600second controller deadline at phase boundaries and in
  timed waits. Each existing operation keeps its smaller individual deadline.
- Add mocked control-path checks for lease waiting/absence and cleanup ordering.
  Review record also pins the protocol hash. Budget, identity, model, task,
  sentinel window and no-retry rule do not change. Zero turns have been spent.
