# EXP-100/S8: bounded stream from the live Git container

Issue: https://github.com/amadou-6e/laomedo/issues/100. Governing design
candidate: specs merge `af571c8ba460d8e7042d244ecfad87575ff07fa8`.
S7's failed identity and observation remain intact at `473fe82`; this is a
new protocol, frozen before the S8 product change and run. The reason for the
mechanism change is Docker's documented inability to `docker cp` tmpfs files,
not a reinterpretation or retry of S7.

## Question and controls

Can the fixed command `docker exec --user 10001:10001 <exact-container> cat
/stage/verified.bundle` stream only the completed verified bundle into a
bounded private host file while the container runs, with the same Git checks
and exact cleanup? The stream must use binary stdout; it must never decode or
re-encode bundle bytes as text. No agent-supplied command, path or container
name is accepted. Cap the output at 32 MiB (the tmpfs is also 32 MiB), enforce
a 30-second command deadline, record only a fixed-vocabulary error class and
never raw stderr or host paths. A stream failure or uncertain cleanup never
becomes `verified`.

Keep the exact S7 pinned image ID and all container restrictions: no network,
read-only root, no capabilities, no new privileges, UID/GID 10001, 128 MiB
memory, 32 PIDs, 32 MiB tmpfs and exactly three read-only binds. No `.env`,
host `gh` credentials, model, real checkout or provider endpoint may enter
the probe. Product output is integrity-verified only, not push-approved. Do
not run `docker cp` again: S7 already measured that path and the official
Docker documentation rules it out for tmpfs.

## Fixed cases and one-shot identity

The fresh identity is `exp100-s8-20261009-a`. One `--record` invocation may
dispatch the following two cases once each, using fresh synthetic fixture
and run IDs:

1. Positive: baseline plus one descendant commit, single-ref agent bundle.
   Expect exactly one container, limits verified, success marker while running,
   bounded binary stream, output hash/size, exported `refs/heads/validated`
   at the candidate commit, independent unbundle/fsck/ancestry pass, exact
   cleanup, and no container remaining. The result must retain
   `policy_approved: false`.
2. Wrong commit: a valid, distinct bundle whose advertised commit differs
   from the host-selected commit. Expect `candidate_commit_mismatch` before
   journal/dispatch, zero new Docker creates and no verified output.

Record source revision and hashes, exact image ID, sanitized result/stream
classes, output hash and size, timestamps, provider/model counts, and
post-cleanup container presence. The probe reserves its evidence identity
durably before dispatch, refuses a dirty tree and any existing pending or
final evidence, checkpoints partial observations, and commits the original
record whatever the outcome. A failed or unknown result is not retried.
Any material change after freezing this protocol needs a numbered amendment
before the first run; a change after dispatch needs a new identity and review.

## Acceptance boundary

Pass only if both fixed cases meet expectations and the original committed
observation hash verifies. Passing S8 supports this bounded Docker export
mechanism only. It does not approve a mediated GitHub push, workflow-file
change, literal `gh` parity, #100/#104 closure, or use of reserved real-agent
turns. Independent pre-run review is required before the one-shot dispatch.
