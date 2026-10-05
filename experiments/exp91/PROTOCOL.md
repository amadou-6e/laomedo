# EXP-91: runner-crash orphan and exact-container identity

Issue: https://github.com/amadou-6e/laomedo/issues/91; parent Q11:
https://github.com/amadou-6e/laomedo/issues/22. Laomedo source base
`f7a83f085d38caadc1e19838da09eb44c2d7a1df` on `develop`.
Governing specs: `amadou-6e/specs` `2d4ba40682faedb10a505984f4146ca8c0f10b6f` (agent execution crash and
Langflow integration Q11). The exact full spec SHA is resolved before run.

## Question and falsifiers

Does a hard host-runner process kill leave an owned Docker container alive
while the restart sweep merely marks the saved run `interrupted`? A claim of
safe orphan cleanup fails if the container remains after restart, if its
identity is absent from the durable record, or if cleanup relies on a broad
prefix that could target another run.

## Frozen method

One local synthetic run, zero model turns. A child process constructs the
real `LocalRunner` on disposable state with `max_model_turns=0`, imports a
synthetic skill and starts one async request. Its test transport consumes
the actual `_docker_prefix` name chosen by the runner but launches a
cached `python:3.9-slim` container that only sleeps, with a unique
experiment label. The locally cached image ID at preflight is
`sha256:bb8009c87ab69e751a1dd2c6c7f8abaae3d9fce8e072802d4a23c95594d16d84`;
the probe records and verifies it again. It blocks before
initialization/any native thread.

The parent waits for a durable run record, exact container name and Docker
inspect confirmation. It then kills only that known child process (not the
container), constructs a new `LocalRunner` over the same state, and records
the saved run status and Docker inspect result. It does not rerun the request.
The parent finally removes **only the exact labelled test container** and
verifies its absence. No prefix-wide cleanup, real Codex image, credentials,
shared Docker auth volume, GitHub write, or model call.

The probe, protocol and source revision must be committed before execution.
Run exactly once unless no child/container was ever started; a crash or
uncertain result is evidence, not permission to rerun. Capture sanitized
status/identity/label/count/timing, keeping synthetic token and disposable
state private. The test must fail if the container unexpectedly vanished,
if the saved record includes a different name, or if cleanup cannot verify
the exact target.

## Interpretation

`interrupted` describes runner state only. It is **not** proof that the
container or native turn stopped. If an orphan survives, Q11 remains open
and a separate fix must persist exact ownership before spawn, reconcile it
after restart, and verify termination without touching unrelated containers.
This experiment cannot prove real-agent cancellation or Langflow UI Stop.
