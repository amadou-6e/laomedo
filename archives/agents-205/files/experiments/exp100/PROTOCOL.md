# EXP-100: credential-free GitHub mediation

Issue: https://github.com/amadou-6e/laomedo/issues/100. Source base:
`9a59199945694dba5aa13d33fe6aa20f69bace1c`. Governing proposed
contract: specs merge `11c7abea3b8eb009150b19c950f6edbb3d1356f0`.
This protocol is frozen before implementation or observation.

## Question

Can an agent use a run-scoped, revocable Laomedo boundary for representative
authorized `git` and `gh` work, without receiving the reusable host credential?
Compare (A) a Laomedo-owned operation broker plus agent-side CLI adapter and
(B) a Git transport/API proxy. Choose a first implementation direction, not a
claim of complete `git`/`gh` compatibility or production security.

## Fixed probe

Use temporary local repositories and a synthetic GitHub provider. Do not use
real GitHub writes, a personal token, a model turn, or an ambient host `gh`
session. A locally generated fake upstream secret lives only in the broker
process and must not appear in the agent environment, command output or audit.
Create two independent run grants with a repository allowlist, allowed
operation classes and expiry. The agent receives only its revocable grant ID.

The parity matrix is: local Git status/commit (ordinary Git, no grant), remote
Git fetch/push (mediated); PR list/create; issue list/create; Actions read;
`gh api` REST GET/POST and GraphQL read/mutation (mediated). CLI-adapter
unsupported commands, `gh auth token`, extensions and credential export must
fail visibly without falling back to host credentials. Compare stdin/body-file,
working-directory, hooks, signing, exit/status and audit handling for both
candidates even where the first prototype does not implement them.

Positive control: grant A performs each representative operation and sees the
expected output/effect; grant B can perform a distinct allowed operation.
Negative controls: wrong repository, denied operation, expired/revoked A,
unknown grant, altered request under the same effect ID, repeated uncertain
write, and direct secret-export command. Revocation must deny A within 60 s
while B remains usable. An orphan simulation revokes A independently of agent
container teardown. Inspect upstream effect counts, not only broker responses.

## Q16 duplicate-write rule under test

Persist `effect_id`, run/repository/operation and a canonical request hash
*before* sending any remote mutation. An exact repeated request returns its
saved confirmed result, or `unknown` if the earlier outcome is uncertain; it
never sends again automatically. Reuse of an effect ID with a different hash
is a conflict. A lost response, timeout or crash after sending is `unknown`
even if a later read does not find an effect. Reconcile by a read-only exact
marker/branch identity when the operation supports one. A 4xx that is known
not to have created an effect can be `failed`; arbitrary `gh api` mutations
have no generic safe retry. A fresh attempt after `unknown` needs explicit
human authorization. This is a proposed policy for Q16, not yet a reviewed
product decision.

## Interpretation limits

Synthetic provider success proves the local boundary and representative
semantics only. It does not prove real GitHub permission parity, real `gh`
extensions, TLS transport safety, secret isolation from a hostile local
process, whole-tree-kill survival on Windows/systemd, or revocation of a real
GitHub grant. Those require separate integration checks before #100 closes.
