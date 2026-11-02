# EXP-104 amendment 05: bounded diagnostic with a broad test token

Date: 2026-10-07. Status: frozen **before any live EXP-104 request**.
This amendment does not revise or replace `LIVE-PROTOCOL.md` or amendments
01–04. It defines a separately labelled diagnostic, `EXP-104-D1`, in response
to the user's explicit instruction to use the token already placed under
`GH=` in the ignored local `.env` even though its GitHub repository selection
is **All repositories**. Specs #256 merged as `7fcc218c77bd483a7428dd8a3a0e370a1a44e34b`.

## Deliberate deviations and limits

- The credential is a fine-grained personal token with broader repository
  selection and permissions than the original disposable-repository-only
  precondition. The mediator remains hard-bound to
  `amadou-6e/laomedo-exp15-disposable`, but that software boundary is not a
  substitute for provider-enforced repository scoping. The token source is
  the host's ignored `.env`, read only by the credential-owning process.
- `HostTokenConnection` is an explicit, file-backed test source. It binds a
  non-secret connection ID and generation and refuses writes if the file is
  replaced or removed, but it is **not** production browser login, a durable
  connection registry, or an OS-backed secret vault. The test cannot satisfy
  amendment 04's production custody prerequisite.
- Therefore a successful diagnostic may support only the narrow claim that
  this implementation refused a post-loss mediated write while another run
  remained usable. It cannot close #104, #100, #93, or Q11, establish
  provider-enforced least privilege, or promote drafts #97/#105 on its own.

## Added safeguards and run identity

- Record a fresh diagnostic ID, tested code SHA, approved issue/PR/spec SHAs,
  exact disposable repository ID and baseline refs before the first call.
  Use new branch names that have never been used by another probe. Never
  overwrite or delete existing refs or issues.
- Prove the token file is not in the agent source tree, container mounts,
  environment, command arguments, trace, or committed evidence. Never print,
  hash into evidence, or transmit the token outside the host mediator and its
  short-lived Git credential helper. Do not use `gh`, Git Credential Manager,
  ambient `GH_TOKEN`, or the host's Git config as fallbacks.
- The transport accepts only an exact 40/64-character commit object present
  in its trusted checkout, checks the baseline-to-commit diff for workflow
  files, stages the object in a fresh bare repository, and pushes only a new
  `refs/heads/` branch under an absent-ref lease. Any ambiguous push result
  remains `unknown` and is never automatically retried.
- Preserve the original live protocol's ordered controls, one-shot writes,
  exact runner kill, independent service, 60-second denial bound, B-run
  continuity, remote read-back, sanitized raw observations and no automatic
  cleanup. Stop on any failed preflight or uncertain effect.

The user authorized the credential-scope deviation; no token value appears
in this amendment. Actual observations must explicitly state which of the
original gates remain unmet.
