# EXP-100/S7: product-stage Docker export check

Issue: https://github.com/amadou-6e/laomedo/issues/100. Code candidate:
draft PR #122 at `d0a8d7b`. The governing mediated-CLI design is specs
merge `af571c8ba460d8e7042d244ecfad87575ff07fa8`. This protocol is
frozen before writing or running the S7 probe. S7 is new evidence, not a
retry of EXP-104/S4 or of any earlier ambiguous dispatch.

## Question and boundaries

Does `verify_frozen_bundle` actually copy a complete bundle from a *running*
Git container's tmpfs on this Docker daemon, verify the expected commit, and
remove only its labelled container? Does a wrong candidate fail without
producing a verified output? The exact image ID is
`sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.

This is a local, credential-free synthetic check. Use a temporary repository
and synthetic run record; do not load `.env`, a model, host `gh` state, any
GitHub token, an existing checkout, or any provider endpoint. The container
must have no network, a read-only root, no capabilities, no new privileges,
UID/GID 10001, 128 MiB memory, 32 PIDs, a 32 MiB tmpfs, and only the three
read-only mounts specified by the product code. The product code must verify
these limits before start. Do not weaken limits merely to get a pass.

## Fixed cases and identity

The one-shot evidence identity is `exp100-s7-20261009-a`. A single `--record`
invocation may dispatch exactly two independent cases, each once:

1. `positive`: one new synthetic commit descended from a pinned baseline;
   agent-style bundle has exactly `refs/heads/run-branch`. Expect `verified`,
   `policy_approved: false`, output hash recorded, output ref
   `refs/heads/validated` at the candidate commit, verified cleanup, and no
   container remaining by exact name/label. Compare the output bytes against
   its recorded hash and independently unbundle/fsck in a disposable local
   repository.
2. `wrong-commit`: use a fresh attempt/run identity and valid bundle whose
   advertised commit is different from the host-selected expected commit.
   Expect a pre-dispatch `candidate_commit_mismatch`, zero new Docker create
   calls, and no verified output. This tests refusal without consuming a
   second container. Do not substitute a malformed bundle for the case.

The probe must record the source code SHA, image ID, input and output hashes,
sanitized Docker settings and state, timestamps, exact result classes, and
container presence after cleanup. It must not record credentials or absolute
user paths. Evidence file `observation-s7.json` must not be overwritten; the
probe refuses a second recorded attempt even if the first fails or crashes.
An unknown result is retained as unknown and never retried under the same
identity. Any correction requires a numbered amendment, new identity, and
another independent pre-run review.

## Acceptance and stop rule

Pass only if both fixed cases meet their expectations and the direct
observation is committed with a hash of committed bytes. A failed or unknown
case ends S7 without retry. Passing S7 supports the bounded Docker export
mechanism only. It does not approve a GitHub push, workflow-file change,
literal `gh` parity, #100 completion, #104 runner-loss acceptance, or use of
the three reserved real-agent turns.
