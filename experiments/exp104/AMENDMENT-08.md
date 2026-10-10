# EXP-104 amendment 08: initialize the user-created empty repository

Date: 2026-10-07. Status: frozen before the first write to the new repository.
This amendment applies only to diagnostic `EXP-104-D2`; it does not revise the
original repository-scoped acceptance protocol.

The user created `ga84jog/laomedo-exp104-disposable-20261007` after the
one-shot creation request was rejected. Read-only preflight identified GitHub
repository ID `1408647759`, a public empty repository with no refs or issues,
and selected-token push permission. The selected token's response header gave
an expiry of `2026-11-06 11:08:23 UTC`. The user did not request a private
repository, and public visibility is therefore recorded, not treated as
evidence of any confidentiality property.

The exact-commit Git transport requires an existing baseline. Before any
mediated grant or diagnostic effect, the credential-owning setup process may
make **one** GitHub Contents API request creating only `README.md` on `main`,
with the text `Disposable repository for Laomedo EXP-104-D2.\n`. It must use
the selected `GH` token, never the ambient `gh` login, and must not expose the
token in arguments, output, evidence, or an agent mount. Save a non-secret
request marker and the observed response separately from mediated effects.
Read back `main` and the README to establish the baseline SHA. If the request
is rejected, times out, or has an ambiguous result, do not resend it
automatically; stop and inspect the remote state. No other setup write is
authorized by this amendment.

Before the live case, freeze the tested code SHA, baseline SHA, unique branch
names, exact run IDs, and the full negative-control plan. Keep the original
no-retry, no-cleanup, 60-second revocation and B-run continuity rules. A
successful run remains diagnostic only because the token is broadly scoped
and credential custody is test-only.
