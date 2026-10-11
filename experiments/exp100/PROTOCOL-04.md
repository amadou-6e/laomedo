# EXP-100/S4: disposable Git-stage resource boundary

Issues: [#100](https://github.com/amadou-6e/laomedo/issues/100) and
[#104](https://github.com/amadou-6e/laomedo/issues/104). Governing design:
`amadou-6e/specs` `b5b27170523334cc886cb0ea27ec616bef44fd4e`,
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
This protocol is frozen before any recorded S4 run. S3's observation is not
modified or rerun. S4 is a credential-free resource experiment, not a product
transport, remote write, model turn or #104 acceptance check.

## Question and fixed setup

Can an untrusted bundle be verified using Git inside a disposable container
without allowing its pack/object expansion to consume unbounded host memory
or writable stage space? Use only the already checked local image ID
`sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.
No image pull/build or network access is allowed during the recorded run.
The container runs as UID 10001, with no capabilities, no-new-privileges,
`--network none`, a read-only root filesystem, at most 128 MiB memory and
32 PIDs. Its only writable location is a 32 MiB tmpfs at `/stage`; the
generated trusted source and bundle are mounted read-only. No host GitHub
credential, `gh` login, Codex profile, `.env`, or agent workspace is mounted.

Use only disposable generated repositories/files under a fresh local temp
directory. The positive case imports and `fsck --strict`-checks a small valid
single-ref bundle in `/stage`. The disk-limit control writes beyond `/stage`'s
32 MiB quota and must fail inside the container without changing the host
source or writing outside the temp directory. A no-network check must fail to
reach a reserved local test listener; it must not contact GitHub. Read back
the container image ID, memory/PID/network/read-only/tmpfs settings from the
Docker API or an equivalent inspectable invocation, not just from intended
arguments. Record host/container Git versions, wall times, exit classes,
source/bundle hashes and the absence of provider/model calls.

## Acceptance and limits

One `EXP-100-S4-01` recorded attempt only. Reserve the evidence identity
before any Docker launch, keep failed/unknown output, and never retry an
ambiguous container effect under the same identity. A positive import plus
observed disk/network denial permits a narrower product design proposal.
It does **not** establish memory-OOM behavior, resistance to all compressed
object bombs, a durable staged commit after the tmpfs vanishes, host-side
push safety, production service-manager survival, literal CLI parity, or a
live #104 result. Those remain explicit subsequent checks.
