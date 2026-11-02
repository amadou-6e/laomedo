# EXP-104/S12: grant-bound verified bundle resolution (local only)

Issue: https://github.com/amadou-6e/laomedo/issues/104. Related #100 staged
export is merged in `develop` at `a0ea0d8252841cde21647bdefc0a04d068b6b2fb`.
The governing design candidate is `amadou-6e/specs@b5b27170523334cc886cb0ea27ec616bef44fd4e`,
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
This protocol precedes the S12 binding implementation and any recorded S12
experiment. S11's live effects and S8's synthetic Docker result are not
replayed.

## Question and boundary

Can a trusted host resolve `{branch, commit, stage_attempt_id}` using only
the mediator grant's run ID and configured private roots, and return one
immutable in-memory snapshot of the exact S8-verified bundle? The agent may
name an attempt ID but never a host path or run ID. The resolver must not
use an agent-writable checkout as a Git object source or fetch any network
data. It must not issue a provider credential, grant or push.

## Fixed local cases

Use disposable synthetic runner/private roots, a real local Git bundle, a
synthetic completed Git run record, and a trusted verification record. No
Docker, model, `.env`, host `gh` state or GitHub provider. Validate:

1. One matching grant/run/repository/branch/commit/baseline and a `verified`
   record with confirmed cleanup resolves to exact immutable bytes, bundle
   SHA-256 and commit.
2. Reject another run's attempt, a wrong repository or branch, wrong commit,
   changed run record, failed/unknown verification, unconfirmed cleanup,
   changed frozen source hash, and changed/linked/oversized verified bytes.
   Each refusal happens before any transport or credential call.
3. Mutating the original verified file **after** resolution must not change
   the returned snapshot. A caller must never be handed the private path.
4. A distinct attempt ID must yield a distinct stage identity/digest so an
   effect key cannot silently switch staged input.

Keep observation/evidence separate from unit tests: unit tests establish code
behavior but do not claim a recorded campaign experiment. Before any S12
recorded run, freeze its exact identity, probe, evidence file and negative
controls in an amendment and obtain independent pre-run review. A later
mediated push needs its own frozen protocol and authorization; this page does
not authorize a live write or spend a model turn.
