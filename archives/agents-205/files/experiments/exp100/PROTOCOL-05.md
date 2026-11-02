# EXP-100/S4-02: fresh positive-import failure diagnosis

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100). Governing
design: `amadou-6e/specs` commit
`b5b27170523334cc886cb0ea27ec616bef44fd4e`,
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
This protocol is frozen before its probe is written or run. It is a new,
single-use diagnostic identity, **not** a retry of `EXP-100-S4-01`. The failed
S4 observation and its SHA remain unchanged.

## Question and fixed setup

Which stage of the credential-free positive Git import exits 128 under the
S4 resource boundary? Generate a new disposable trusted repo and agent
bundle. Use the same pinned local image ID and the same Docker flags,
read-only bind targets, 128 MiB memory, 32 PIDs, 32 MiB tmpfs, UID 10001,
`--network none`, dropped capabilities, no-new-privileges and read-only root
as S4. Run only the positive-import case, with a trusted verifier that emits
stage labels before checking mount readability, initializing the bare repo,
fetching the baseline, unbundling the candidate, and checking the commit.
Suppress raw Git stderr; record only stage labels, exit code, inspected
limits, bounded wall time, source/bundle hashes, cleanup status and the
verifier's Git version if reached. No credentials, host `gh` login, agent
profile, `.env`, live repository, provider call or model turn may enter the
container. No image pull or build.

## Outcome and limits

Reserve `EXP-100-S4-02` on disk before Docker creation. One recorded attempt
only. A nonzero exit is a diagnostic result, not a pass. Preserve failed or
unknown evidence and never rerun this identity; if a later corrected import
is needed, freeze a distinct identity and independent review first.
Inspect the exact container before starting; remove only that labelled
container and verify removal. Check the source and bundle remain unchanged.
This stage diagnosis cannot establish bounded successful import, memory-OOM
behavior, durable commit staging, CLI parity, a live #104 outcome, or readiness
to merge #105.
