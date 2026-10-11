# EXP-100/S3: run-bound local bundle handoff result

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100), as a
dependency of [#104](https://github.com/amadou-6e/laomedo/issues/104).
Governing spec: `amadou-6e/specs` commit
`b5b27170523334cc886cb0ea27ec616bef44fd4e`,
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.

The [protocol](PROTOCOL-03.md) was committed at `3564292` before code. Its
[identity clarification](AMENDMENT-04.md) was committed at `f0d8a42` before
the amended code. The independently reviewed source was
`09166ad60f36140d0b1dc3d7754cf89415e02675`. After a clean-tree check,
the single `EXP-100-S3-01` `--record` run exited zero and wrote
[observation-s3.json](observation-s3.json), SHA-256
`e88135f7e2cde7156a15ddf31738f03bbe322f5a28fa5b3c99e0053d14514222`.
The same file identifies its exact source commit and SHA-256 of the protocol,
amendment, S2 verifier, S3 code and tests. The identity was consumed once;
there was no retry or second recorded run.

## Observed

- All 14 non-link S3 controls passed. The actual Windows junction and
  synthetic reparse-attribute controls passed. The separate file-symlink
  control skipped because this Windows environment cannot create that link;
  the result keeps the skip visible rather than calling it a pass.
- Ten unchanged S2 verifier controls were rerun in the same probe and passed.
  The record names reused S2 controls separately from new S3 controls.
- A valid run-bound bundle was frozen, hashed, checked against the trusted
  baseline and branch, and imported into a host-private Git stage. The test
  moved the agent workspace away and still read the commit from the stage.
  A later thin/fast-forward bundle required the host-confirmed earlier stage.
- Wrong-run bytes, wrong branch/baseline, divergent later history, extra ref,
  workflow-file change, malformed/truncated data, hardlink/oversize input,
  a simulated replacement after open, an incomplete prior attempt, and stage
  placement under another run's mount were refused in local controls. The
  host-Git guard would fail if the verifier invoked Git in the agent checkout.
- Instrumented Git/REST transport entrypoints and `LocalRunner.start` saw
  zero calls. This is narrow instrumentation, **not** a packet capture or an
  independent proof that arbitrary code could make no network call. No token,
  Docker container, model turn or live GitHub write was used.

## What this does not establish

This is experimental code under `experiments/`, not a product handoff API.
No agent adapter produced a bundle in a real run, no mediator consumed this
stage, and no remote push or PR update was attempted. A 4 MiB bundle-input
limit and bounded Git subprocesses do not independently bound decompressed
Git object growth or host disk use. The private stage is protected by a
same-user path boundary, not a multi-user isolation boundary. A stale per-run
lock is deliberately fail-closed and requires an operator to inspect the
attempt record before manual reconciliation; there is no automatic cleanup.

Therefore S3 supports continued product integration work, not #100 `git`/`gh`
parity, #104 live runner-loss acceptance, draft #105 promotion, or spending a
model turn. The next safe step is to design and test a resource-contained
product handoff and bind its verified staged commit to the mediator's run
grant before any new live write.
