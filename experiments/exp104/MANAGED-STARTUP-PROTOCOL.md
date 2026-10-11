# Independent Windows task startup: no-provider diagnostic

Frozen prospectively on 2026-10-09 before implementation of its executable
probe or installation/start of any task. Identity: `exp104-task-s1-20261009`.
This is separate from the consumed live provider identities. Zero model turns,
zero GitHub requests or writes, synthetic token only, no grants and no agent
container. User selected Windows per-user scheduled tasks on this machine.

## Procedure and bounds

After independent review, the single-use probe creates a new private temporary
directory outside Git for synthetic service state, agent mount, token file and
JSON configuration. It registers only the two exact per-user task names
returned by the reviewed installer, refusing any pre-existing task. The host
service uses repository `example/disposable` and synthetic credentials, and
the verifier has no staged attempts to dispatch. No Docker action is needed.

Start both tasks once. Wait at most 20 seconds for host service heartbeat and
both exact managed-service processes. Capture task principal/settings,
service module root and process IDs. Start one disposable stand-in runner
process; kill only that exact process tree. Recheck the same task-owned service
processes and advancing host heartbeat after five seconds. This establishes
independence from a runner tree, not grant revocation or container cleanup.

Pass only if both processes start under the limited interactive user's tasks,
the same service processes survive the runner kill, and the host heartbeat
advances. Any permission or readiness failure is a failed/blocked diagnostic,
not permission to elevate, overwrite tasks, or reuse the identity. Record
sanitized machine-generated observations and hash committed bytes.

Finally stop and unregister only the exact tasks created by this attempt,
verify their absence and no matching service process remains. Never delete
unrelated tasks or private state. Keep the bounded private state for inspection;
do not commit credentials, full command lines, user identity or private paths.

## Limits

No automatic acceptance of #97/#105, no service/logout/power-loss survival,
Task Scheduler failure recovery, verifier in-flight Docker cleanup, real grant
or provider behavior. The verifier's persistent claims already prevent a
restart from redispatching a consumed attempt, but safe verifier-crash cleanup
needs its own test. The active freeze/verify/push/PR/readback test is a separate
no-model protocol. Review this executable probe before any task installation.
