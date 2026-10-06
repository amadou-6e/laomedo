# EXP-96 host-owned stage control

Run the credential-free probe from the repository root with Docker Desktop
running and the pinned Langflow image already available:

```sh
python -m experiments.exp96.probe
python -m experiments.exp82.docker_timeout_probe
```

The first probe uses the real `DockerLangflowStage`, pinned image and temporary
SQLite run store. It checks a normal no-model stage, a component that writes a
forged `ready`, `complete`, and `failed` lines during construction and then
raises, and a component that writes the same forged lines during execution and
then raises. The fixtures try
ordinary `print`, raw file descriptor 1 and writable inherited FIFO descriptors
found under `/proc/self/fd`. The probe checks durable run counts and status,
host-computed graph and component identities, one dispatch attempt on failure,
and cleanup of the exact validation and execution containers. It prints only a
sanitized boolean summary. No model turn or credential is used.

The timeout probe checks that a deadline produces `unknown`, one attempt, and
an absent container. The host controls reservation and run status; executor
stdout is result data, never an attestation or status channel. A component can
still choose arbitrary result text or force its own process to exit zero. A
successful Docker exit establishes process termination, not truthful execution
of arbitrary component code. The validation container's exit status is a
compatibility check, not proof of runtime behavior.
