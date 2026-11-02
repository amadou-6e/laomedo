# EXP-100/S4-03: trusted-baseline bundle import

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100). Governing
design: `amadou-6e/specs` commit
`b5b27170523334cc886cb0ea27ec616bef44fd4e`,
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
Frozen before S4-03 implementation or Docker execution. S4-01's failed
positive import and S4-02's observed `baseline_fetch` failure remain immutable.
S4-03 has a distinct single-use identity and is **not** a retry of either.

## Question and fixed setup

Can a small agent bundle be imported under the same resource boundary when
the trusted baseline crosses into the container as a host-generated Git
bundle, rather than as a differently owned working repository? Generate a
fresh disposable trusted repository and agent commit. On the host, create a
baseline-only bundle from the trusted HEAD and a candidate bundle from the
agent branch. Preflight their compatibility using local Git and no Docker.
In the one recorded Docker case, mount only these two bundles and a fixed
verifier as read-only files. The verifier initializes a bare stage on the
32 MiB tmpfs, unbundles the trusted baseline, confirms its exact object ID,
unbundles the candidate, checks the exact candidate commit, performs strict
fsck and confirms the baseline is an ancestor. Emit bounded stage markers,
but suppress raw Git error text.

Use the same pinned image ID, 128 MiB memory, 32 PIDs, UID 10001,
`--network none`, read-only root, dropped capabilities, no-new-privileges
and exact read-only binds as S4-01. Inspect the actual image and limits
before starting. Do not mount a repository tree, credentials, host `gh`
login, agent profile, `.env`, or any live checkout. Do not pull/build an
image or contact GitHub. Only the disposable local temp directory and the
exact labelled container may be changed.

## Acceptance and limits

Reserve `EXP-100-S4-03` on disk before Docker creation. One recorded Docker
attempt only. Require exit 0, verifier marker, exact read-back settings,
unchanged bundle hashes, and confirmed removal of that labelled container.
Preserve failure or uncertainty; never rerun this identity. Record the
protocol/probe/script hashes, image ID, Git versions, object IDs, stages,
wall time, and scoped provider/model counts.

A pass would establish only that this small fixture can be imported under
the configured resource boundary. The separate S4-01 quota check supports
the bound's disk-control behavior but does not prove an adversarial pack
cannot cause OOM, a production handoff, durable staging, safe remote push,
literal CLI parity, a live #104 runner-loss result, or #105 merge readiness.
