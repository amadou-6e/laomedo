# EXP-108: synthetic GitHub account-connection exercise

Status: frozen before probe implementation or execution. Governing specification:
[`github-account-connection.md` at specs merge `9c287ec`](https://github.com/amadou-6e/specs/blob/9c287ec/projects/laomedo/subsystems/agent-execution/contract/github-account-connection.md).
Issue: [Laomedo #108](https://github.com/amadou-6e/laomedo/issues/108).

## Question and scope

Can a credential-owning broker accept a browser callback or an explicitly
supplied token, bind it to the right Laomedo user and GitHub account, then
issue only a non-secret connection reference while refusing ambient host
credentials? This is a synthetic exercise, not production login, secure token
custody, or a live GitHub grant. There is no agent/model call or network call
to GitHub. No personal credentials may be read, copied, or printed.

## Fixed setup

- Python standard library only. Use a temporary broker store and a fake
  loopback GitHub-compatible identity endpoint with synthetic identities,
  repositories, browser codes, and tokens.
- Browser mode is the default. A one-use callback challenge must bind user,
  session, intended account/repository, and callback state. Replay and
  wrong-user/session/state/account/repository callbacks must be refused.
- Explicit token mode must verify identity, repository access, expiry, and
  operation scope before becoming ready. A broad classic token is refused;
  no refreshability is inferred for supplied tokens.
- A run selector sees only a connection ID and credential generation. A
  stage-facing payload sees only a run capability, never a token or code.
- Replacement/disconnect increments or revokes the old generation. The
  mediator must refuse a write using the old generation, even for an active
  run; an unrelated connection remains usable.
- After broker recreation from its store, a completed connection remains
  distinguishable from an incomplete browser challenge. No callback silently
  chooses a different identity. A missing broker credential fails closed.
- Set synthetic `GH_TOKEN`, `GITHUB_TOKEN`, `GH_HOST`, Git credential-helper
  config and a fake `gh` shim in the child probe environment. The broker must
  use only explicitly connected credentials. No real host `gh` state is read.

## Measurements and acceptance

Run the probe once per frozen revision and record a sanitized JSON observation
that includes each case's pass/fail, connection/generation identifiers,
requests seen by the fake provider, and any unexpected secret exposure. The
tests must fail if an expected refusal is accepted, if an old grant can write
after replacement, if an unrelated run is denied, or if ambient credentials
are used. Record source and observation hashes from committed LF bytes.

An accepted browser path, accepted explicit token path, every listed negative
control, and an absent-secret inspection are required for a synthetic pass.
Any failure is reported, not repaired by silently changing this protocol.
The probe may be amended in a separately committed amendment *before* a new
run, retaining the first result.

## Limits and stop conditions

Stop without a live call if the endpoint is not loopback, a real credential
would be used, or any output contains a secret. Do not retry an ambiguous
write. This exercise cannot establish GitHub OAuth/App behavior, callback
security in a deployed browser, OS-backed secret storage, real permission
semantics, live runner-loss revocation, or `git`/`gh` command parity. Those
remain separate work under #100 and #104 or later integration tests.
