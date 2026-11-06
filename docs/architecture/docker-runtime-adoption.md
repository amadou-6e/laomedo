# Docker runtime boundary

Laomedo consumes `py-docker` (`py_docker`) through its optional `runner` extra,
pinned to an exact Git revision in `pyproject.toml`. The runtime uses the official
Docker SDK; database integrations have a separate package. Core imports and stage
workers do not require this extra.

## Ownership

The runtime owns endpoint resolution, immutable resource identity, launch
readback, create/start/attach/remove, bounded binary transport, framing, EOF/state
confirmation and durable ownership receipts. It never implicitly pulls, builds,
recreates or retries an uncertain create.

Laomedo owns approved image/CLI/config/seccomp pins, mount and sandbox policy,
credentials, native protocol, ACP extensions, redaction, telemetry, output
validation, run budgets, grants and independent supervision/publication authority.
The daemon comes from an explicit host environment snapshot; graph input cannot
select it. Ambiguous, remote and TLS configurations fail closed locally.

## Provider lifecycle

Providers share ACP conversation lifecycle through `laomedo.agents.agents.base.acp`.
Concrete entry points are `laomedo.agents.agents.{codex,claude,opencode}.cli`.
Adapters retain their native permission, authentication, terminal-outcome and
raw-event contracts. Shared ACP does not make those policies interchangeable.

Codex uses `client.sessions.open`; `CodexLaunch.to_container_spec` projects
host-owned policy and `SplitLaunch` adds its deferred executor binding. Bounded
command/version work uses jobs, without a Docker CLI transport fallback. The
controller retains its checksum-verified seccomp policy, UID, capability dropping,
no-new-privileges, resource limits and scoped mounts. A split controller binds the
observed executor ID; its launch OAuth credential never enters the executor or
Docker control environment.

Public preflight operations keep their actual side effects: Codex performs its
permission/model probe; Claude checks authentication and can perform the explicitly
authorized login-only mirror; OpenCode configuration does not attest authenticated
readiness. Startup, catalogue and turn checks report their observed scope.

## Local installation and recovery

Install `python -m pip install -e '.[runner]'` in the launcher environment. Start
Codex with `python -m laomedo.agents.agents.codex.cli`; the launcher must resolve
the same installed package and dependency revision.

Reconcile central receipts and older run/catalogue receipt directories before a
new launch. Exact resource identity, ownership and Docker endpoint provenance must
match. Missing provenance blocks automatic adoption; unresolved cleanup retains
intent. Never delete pending receipts or remove containers by name prefix. A name
replacement is not the previously owned container. Zero-window cleanup cannot
establish that a pending create will never arrive later.

Profile preparation first reconciles its prior job. New profiles get bounded
initialization; existing profiles get read-only ownership checks. Incomplete
copies retain receipts. Do not change permissions while a copy may be active,
delete a pending receipt or infer ownership of a mutable volume name. Rotating
credential refresh ownership stays on the host.

Normal shutdown uses exact-ID runtime cleanup. Required independent lease
completion cannot be replaced by a secondary absence check. Host-loss supervision
has its own lifetime. Transport completion or socket closure does not establish
native completion or container termination.

## Budgets, errors and evidence

`LAOMEDO_CODEX_STREAM_MAX_BYTES` defaults to 64 MiB and
`LAOMEDO_CODEX_STREAM_STARTUP_MARGIN` to 120 seconds; controller settings validate
them at use. They introduce no model-turn cap. API, stream and wait deadlines
remain distinct, without a claimed total deadline across all Docker operations.
Cleanup uncertainty outranks ordinary failure. Stable codes and safe identifiers
reach the shared error presenter; daemon text, native payloads, credentials and
private receipt labels do not. Disconnection does not authorize resending work.

Installed-package checks, real completion/cancellation/host-loss paths, exact
cleanup, descriptive graph failures, configured CI and independent review require
separate evidence. Browser stories require requesting-user validation. Historical
probes remain on `exp` and do not establish current image or graph acceptance.
The production-LOC parity baseline is pre-offloading develop
`975d13cf2d8a62c50acef2b1eb4835c6040d9bee`; report tests, docs and experiments
separately, and investigate or report a remaining increase.