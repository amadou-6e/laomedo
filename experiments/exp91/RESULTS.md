# EXP-91 result: restart status does not clean up the container

The one-shot synthetic probe at frozen revision `bdf6bc4` killed only its
runner child after the runner had saved a `running` run and launched one
labelled, non-model Docker sleeper. A new `LocalRunner` over the same state
marked the run `interrupted` with `runner_restarted`, but Docker still showed
the exact same container ID running. The saved record did not include its
container name. No turn ledger was created, and the probe used zero model
turns. See committed [`observation.json`](observation.json).

| Boundary | Saved run | Docker container |
| --- | --- | --- |
| Before hard kill | `running` | Running, exact name/ID captured |
| After runner restart sweep | `interrupted`, `runner_restarted` | **Still running**, same ID |
| After exact experiment cleanup | Unchanged | Absent |

This falsifies any claim that the current restart sweep also terminates
owned containers. `AppServer.close()` is a normal-path cleanup, not a
process-crash cleanup. The current `_docker_prefix` generates the name but
the durable run record stores no ownership identity; a later process cannot
safely infer the exact container by a broad name prefix. A fix must persist
an exact owner reference before spawn, reconcile it after restart, and
verify exact-target termination before reporting confirmed cleanup.

The test transport used the name from the actual `_docker_prefix` call, but
replaced the real Codex image and commands with a cached, labelled
`python:3.9-slim` sleeper. It blocked before initialization. This proves
the process/Docker boundary and the missing durable identity, not how a
real native turn behaves after a crash. No real credentials, shared auth
volume, model call, GitHub write, or production workspace was used. The
temporary runner state was removed after capture; the exact labelled test
container was removed and independently confirmed absent. Q11 remains open.
