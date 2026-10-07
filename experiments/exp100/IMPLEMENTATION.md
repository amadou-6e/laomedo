# EXP-100 implementation follow-up (separate from the recorded probe)

The frozen [protocol](PROTOCOL.md) and [machine observation](observation.json)
belong to the earlier synthetic experiment. The later
`laomedo.github_mediation.MediationStore` is new product code covered by
`tests/test_github_mediation.py`; it was **not** exercised by that recorded
observation. Its governing Q16 proposal is [specs PR #250](https://github.com/amadou-6e/specs/pull/250),
which must merge before this behavior is accepted as a contract. The still-open
[authentication contract #150](https://github.com/amadou-6e/specs/pull/150)
defines the first-slice grant scope; neither document asserts a live credential.

## What this code actually does

- The trusted controller issues a random run/invocation/repository grant,
  storing only its SHA-256 digest and a maximum 60-second lease. The lease
  owner can renew a live grant or revoke every grant for one run. A revoked or
  expired grant cannot be renewed. No host GitHub token is handled here.
- Before a remote mutation, SQLite commits run-scoped effect identity and
  `unknown` intent. Repeated identical calls return the saved result or
  `unknown`; changed content conflicts. A known non-creating rejection is
  separate from ambiguous failure. Reopening the store never re-dispatches.
- Cross-run PR-create and issue-create target identities prevent a new effect
  ID from silently hiding a previous unknown/confirmed create. A trusted
  controller can record a one-use explicit approval for a new attempt after
  an unknown result; the stage capability has no method to create that
  approval. This acknowledges duplicate risk rather than promising exactly
  once.
- A Git push is restricted to its granted branch. Issue creation requires a
  trusted issuer to bind the exact reviewed payload hash. PR updates require
  a grant-bound PR number and base plus the granted head branch; a confirmed
  create can bind its returned PR number. A Git push requires a trusted diff
  classifier: absent or uncertain classification refuses dispatch, and a
  detected `.github/workflows/` change requires separate approval. The
  agent's `workflow_file_change` flag cannot grant that approval.
- The generic REST read lane accepts only an explicit same-repository GET
  path. GraphQL reads are disabled until a reviewed query classifier exists;
  an agent-labelled GraphQL `mutation` cannot bypass the write journal.
  Generic REST/GraphQL mutations fail visibly in this slice.

## Boundaries not yet crossed

This is an in-process ledger with an injected transport, **not** a networked
credential-owning service. It has no literal `git`/`gh` adapter, real GitHub
token or App identity, Git pack transport, authenticated operator approval
endpoint, production database access control, hostile same-user isolation,
audit retention, or linked lease-service process. An agent must never receive
the `MediationStore` object, SQLite path or trusted retry-approval method.
The caller must place the store outside the checkout and mount, and keep its
transport and credential in the independently owned service. The current
tests use synthetic transport only and do not accept #100, #93 or Q11.
Grant expiry is checked on every invocation even if the lease owner dies;
the maximum TTL is 60 seconds. Expiry uses the wall clock, so a backwards
clock step is an open hardening issue. Revocation prevents *new* dispatches,
not an already in-flight provider call. Read-only reconciliation of unknown
effects and deliberate reopening after a confirmed create are also open.

The next integration must bind this store to #97's separately owned lease
service, then supply an actual credential-owning transport and a stage-facing
adapter. A whole-tree-kill probe must use a disposable scoped GitHub identity,
show a real post-kill write denied within 60 seconds, and show another run
still works. Until a reviewed transport classifier exists, arbitrary
`gh api` writes must remain unsupported rather than bypass approval through
an unclassified endpoint or GraphQL mutation.
