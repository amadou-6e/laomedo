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
The Claude and OpenCode provider migration is in progress in this draft. Their
controllers use owned output-only sessions; command workers and Claude control
requests use bounded jobs. Provider policy stays in Laomedo. Old CLI builders,
name-based OpenCode removal and telemetry environment files have been removed.
Claude uses private read-only input files because Windows named pipes cannot
half-close stdin while retaining output. OpenCode launches both resolved immutable
images and accepts a published endpoint only on IPv4 loopback. Startup receipts
are recovered before another launch. Oversized command output is a failure after
confirmed cleanup, with a warning that workspace changes may already exist.
Recovery checks central receipts and older run/catalogue receipt directories
before another OpenCode dispatch. Catalogue cleanup retains unresolved intent.
Receipts include the resolved Docker endpoint; missing or mismatched provenance
blocks automatic recovery. The controller has an in-container deadline, and
capture failures stop it rather than silently leaving an unread stream. Fatal
worker output and transport failures reach the run record and shared node error
presenter, with cleanup uncertainty taking precedence.

Real zero-turn startup passed for both providers. A real OpenCode task completed
through its worker, and Claude completed after the already-authorized access-only
login mirror refreshed an expired copy. These are provider integration evidence,
not graph acceptance. The host credential mirror still uses its existing CLI
transport; its credential policy and transport are outside this increment.
Graph, publication and LOC acceptance remain outstanding.

OpenCode abort and shutdown signal the active py-docker job, which stops only its
observed owned container and confirms cleanup through the shared Session lifecycle.
A real active-worker cancellation originally waited 45.27 seconds; after this
correction it completed in 1.59 seconds with confirmed cleanup. This is provider
evidence, not a graph acceptance or a universal timing guarantee. In-container
deadlines still bound host-loss cases where no caller can signal cancellation.

Claude workers now use the same cancellable job path. The application no longer
races a separate foreground remover against the SDK journal owner. A real
active-worker cancellation completed in 2.00 seconds with verified removal and
zero receipts. Pending SDK cleanup cannot be promoted by a secondary absence
check; the independent lease remains responsible for host-loss supervision.

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

### Reconciling a receipt from an older draft

Older drafts did not save the endpoint in the receipt. Stop the affected local
runner process and keep its private state. Establish the original local endpoint
from its persisted run ownership or independent lease registration, rather than
the current default Docker context. If that original endpoint is unknown, retain
the receipt and do not launch replacement work under the same ownership name.

For an observed immutable ID, explicit host reconciliation can use the existing
owned-cleanup API below. This is a maintenance step after verifying the endpoint,
not an automatic migration or a graph input. It checks the recorded private
ownership labels and clears the receipt only after confirmed removal. Never print
the private record or its labels, and never add an endpoint just to bypass refusal.

```python
import json
from pathlib import Path
from py_docker import Client
from py_docker.containers.models import ContainerReceipt
from py_docker.containers.receipts import ReceiptStore

receipt_path = Path("<existing private receipt path>")
original_endpoint = "<verified original local endpoint>"
with Client(environment={"DOCKER_HOST": original_endpoint}) as docker:
    with ReceiptStore(receipt_path) as store:
        saved = ContainerReceipt.from_private_record(
            json.loads(receipt_path.read_text(encoding="utf-8")))
        if saved.identity is None:
            raise RuntimeError("Resolve the original uncertain create first")
        store.cleanup(docker.containers, saved.reservation, saved.identity)
```

An intent-only receipt cannot establish that a delayed create will never arrive.
Resolve that original request before cleaning or replacing it. Do not delete its
file merely because the name is currently absent. Current receipts with matching
endpoint provenance use normal `sessions.recover` or `jobs.recover` instead.

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
cancellation and abrupt-loss recovery, exact cleanup, descriptive failure
presentation, final-head CI and full substantive Claude review. Live graph review
and owner merge approval remain separate. Local checks with image73ad do not
validate checked-in image7b79 or establish the local image's build provenance.
Credentials are never committed or returned in graph payloads. Live Claude checks
used the existing access-only mirror under the owner's dedicated-local-volume
authorization; the host retains rotating refresh credentials and refresh ownership.

Real stream/EOF checks currently cover the runtime transport; a Codex-level EOF failure is not claimed as accepted. A split model turn remains unverified: only split initialize, registration and catalogue have real evidence.
