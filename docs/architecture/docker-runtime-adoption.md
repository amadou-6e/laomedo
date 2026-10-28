# Docker runtime adoption

Laomedo uses the optional `runner` extra to consume `py-docker` (`py_docker`),
which builds on the official Docker SDK. The dependency is currently pinned to
an unpublished Git revision for local verification. PyPI publication, an accepted
image build and owner graph approval are separate requirements before release.
The preflight migration merged in PR212; the normal/split migration remains draft.

## Boundary

The runtime owns endpoint/context resolution, immutable resource identity,
launch readback, creation/attachment/start/removal, bounded binary transport,
line framing, EOF/state confirmation and durable ownership receipts. It never
pulls, builds, recreates or retries an uncertain create implicitly.

Laomedo owns approved image/CLI/config/seccomp pins, mount and sandbox policy,
credential selection, native protocol, decoding, redaction, evidence, telemetry,
turn budgets, grants and the independent supervisor process. Database drivers
remain in the separate database package. No Codex, GitHub or graph authorization
policy belongs in py-docker.

One `Client` selects a daemon from the explicit host environment snapshot.
Subsequent launches and supervision use that endpoint; graph inputs cannot
select it. Ambiguous, remote and TLS configurations fail closed in this local
integration. Core imports and stage workers remain SDK-independent. Actual
Claude container startup also requires the runner extra for endpoint binding;
missing dependencies and unsupported configuration map to Claude error codes.
The remaining Claude/OpenCode lifecycle is not yet migrated.

## Canonical paths

Credential-free version checks use `client.jobs.run`. Normal and split Codex
controllers use `client.sessions.open`. A typed `CodexLaunch` projects app policy
into `ContainerSpec`; `SplitLaunch` supplies controller-specific deferred-tool
configuration. There is no Docker CLI transport fallback, command-list parser,
`SplitTransport`, `_docker_prefix` or `_docker_checked` in the Codex path.

The normal controller retains its reviewed seccomp checksum, UID10001,
capability dropping, no-new-privileges, resource limits and scoped mounts.
The split controller joins the observed executor ID's network. Its launch-only
OAuth credential never enters the Docker control environment or executor. The
executor mounts only its writable workspace and a temporary credential-free home.
Both output channels are drained under validated stream budgets. SDK exec probes
preserve listener isolation, CLI-version and executor-selection checks.

Profile preparation recovers its previous job receipt before dispatch. Newly
created volumes receive bounded root+CHOWN initialization; reused profiles get
an unprivileged read-only UID check. Failure never removes a mutable volume name
or silently accepts an unprepared profile. Known existing profile names are
explicit host selections, not implicit library ownership adoption.

## Recovery and shutdown

Active controller and executor receipts live in private `state/receipts/`,
outside disposable metadata. Both central receipt kinds and legacy controller/
executor receipt names are recovered. Legacy evidence directories are retained.
Catalogue evidence is retained while either lifecycle remains unresolved.

A receipt records intent before creation, then the observed immutable ID.
Recovery can confirm that ID's absence after independent removal. Intent-only
absence cannot prove that a delayed daemon request will not create the container.
Keep unresolved receipts on the original endpoint; never delete one merely to
permit a retry. Resolve the original outstanding create before reusing its name.
Receipt locks prevent recovery from stealing an active lifecycle.

Session close removes the exact owned ID before detaching and unblocking readers.
EOF alone is not execution success. A still-running process after EOF is a
transport failure; a nonterminal created state waits for the bounded deadline.
Reader resources close only after their actual users finish.

Lease registrations and persisted run ownership record the selected endpoint.
Legacy records without it stay unknown. `Containers.watch` implements exact
inspection/removal and delayed-create observation; the Laomedo supervisor owns
heartbeat loss, grant revocation and authority. A loss watch that never observes
creation remains unverified. Zero-window cleanup is only for an already resolved
operation, not evidence that an unknown create cannot arrive later.

Confirmed SDK close replaces redundant normal cleanup. Independent lease
completion remains required; its failure cannot be promoted to success by
another container-absence check. Split shutdown reports unresolved executor
cleanup separately and preserves its receipt.

## Configuration and errors

Existing native-turn allowances and correction retries determine stream lifetime.
Host settings `LAOMEDO_CODEX_STREAM_MAX_BYTES` (64MiB default) and
`LAOMEDO_CODEX_STREAM_STARTUP_MARGIN` (120s default) are validated at use. They
introduce no model-turn cap. API, stream and wait deadlines remain distinct;
there is no claimed total wall-clock deadline across all Docker calls.

Stable user-visible codes and the shared error catalogue remain authoritative.
Cleanup uncertainty outranks ordinary failure. Errors expose safe codes and
identifiers, never daemon text, raw output, credentials or private receipt labels.

## Acceptance and LOC

The pre-offloading baseline is develop
`975d13cf2d8a62c50acef2b1eb4835c6040d9bee`, before PR212. Compare production
`src` physical lines separately from tests, documentation and experiments; also
report the full diff. The owner expects parity. If it is not met, reinvestigate
and report the gap. Historical script retirement is not production savings.

The obsolete CLI-specific EXP107 entrypoints are retired with their reports and
Git history retained. Maintained diagnostics use the SDK. Tests with internal
controls do not establish integration acceptance.

Required acceptance includes installed-wheel/source provenance, real completion,
cancellation, EOF and abrupt-loss recovery, exact cleanup, descriptive failure
presentation, final-head CI and full substantive Claude review. Live graph review
and owner merge approval remain separate. Local checks with image73ad do not
validate checked-in image7b79 or establish the local image's build provenance.
No credentials are copied by this migration. Actual login-only mirroring remains
subject to the owner's existing dedicated-local-volume authorization.
