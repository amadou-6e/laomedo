# EXP-104 amendment 21: fresh S7 no-model agent mediation run

Date: 2026-10-07. Status: frozen **before implementation of the S7 probe and
before any S7 live call**. This amendment does not reinterpret S3's unknown
outcome or reuse consumed S6 identity. It adds a new bounded run to test the
agent-container path introduced after S6. No model turn is authorized by this
amendment.

## Frozen identity and gates

- Identity: `exp104-s7-20261007-01`. Run A/B and leases A/B, PR markers,
  effect IDs and branch names derive only from this identity. Branches are
  `exp104-s7-20261007-01-a` and `exp104-s7-20261007-01-b`. Neither may exist
  before the run. Never rerun the identity after an uncertain effect.
- Repository: only `ga84jog/laomedo-exp104-disposable-20261007` (ID
  `1408647759`), baseline main commit
  `1f1a505f2fbd31993a7946924a9bec5a27bb15c1`. Abort if the ID, default
  branch, baseline, or existing A/B refs differ. Do not delete or overwrite
  pre-existing refs, PRs, issues, or evidence.
- Implementation, governing specs and probe hashes must be pinned in a
  separate pre-run record after the probe is committed. A code change after
  that record requires a new amendment/identity. The previous S6 SHA is not
  accepted as proof for this code.
- The user must explicitly approve this bounded live run and provide
  independent **non-secret** evidence that the selected token is scoped only
  to this disposable repository. User attestation alone and the GitHub API's
  positive access result do not establish exclusivity. Never print, hash or
  commit token bytes. No ambient `gh` or Git Credential Manager fallback.
- Obtain an independent reviewer verdict on the committed S7 protocol,
  executable probe, preflight and exact proposed source SHA before the first
  provider write. A self-review is not a substitute. Any disapproval blocks
  execution until a fresh amendment and re-review.

## Fixed sequence and write budget

1. Read-only preflight: check repository identity/baseline, absent new refs,
   absent S7 PR markers, token connection generation, exact host-service
   process identity, Windows Docker route, pinned image, private mounts, and
   four unused run authorizations (two one-shot setup push grants and the
   two agent-container grants). Abort on any mismatch. The host lease and
   mediator process is already running outside the runner tree.
2. In a disposable trusted host checkout, construct two deterministic marker
   commits on the pinned baseline. Through the credential-owning host
   mediator with two separately leased, one-shot setup grants, make **one**
   unique-branch push for A and **one** for B. Each
   request gets a durable effect ID before dispatch. Do not retry either
   push if its response is lost or uncertain. Read back both exact refs.
3. Start two no-model pinned agent containers with distinct run capabilities,
   using the same Docker mount/security profile as `LocalRunner._docker_prefix`.
   No
   provider credential enters either container. A uses the same mounted
   Node client path as `LocalRunner._docker_prefix` to create one marked PR
   from branch A to main. Capture the response, provider-attempt journal,
   exact PR number/head/base and run/lease/container identity. Do not proceed
   unless that write is confirmed and the marker resolves to exactly one PR.
4. Kill the exact runner A **whole process tree once**, leaving the host
   service and B alive. Record host-monotonic kill, detection, revocation and
   container-removal times. After revocation, submit **one new** PR-update
   effect through A's same capability. It must return denial before any
   provider attempt; independently read back that the PR title/body were not
   changed. Do not retry or replace the denied call.
5. With B's still-live capability, create one marked PR from branch B to
   main. Confirm its distinct number/head/base and provider attempt. This is
   the positive write control for an unaffected run. Stop B normally and
   verify the exact B grant is revoked. Leave the two branches/PRs for review.

Maximum intended provider mutations: two setup pushes and two PR creates.
The post-loss PR update must not reach the provider. Any timeout, 5xx,
missing acknowledgement, unknown effect, unexpected extra attempt, or
container/service identity mismatch makes the run inconclusive/failed and
stops further writes. There is no automatic retry, no cleanup mutation and
zero model turns.

## Evidence and acceptance

- Persist a sanitized raw observation, mediator provider-attempt journal,
  exact read-backs and derived assessment. Hash the committed bytes. Record
  the source SHA, protocol/probe hashes, identity, token scope evidence
  reference (not the token), each effect ID, host-monotonic timestamps,
  provider attempt counts, and the exact container labels/IDs.
- A's post-loss denial must occur no later than 60 seconds after runner loss,
  with zero additional provider attempt and unchanged remote PR. B's write
  must succeed after A's revocation. Report the exposure window before
  revocation; do not call container removal credential revocation.
- Scan agent mounts, environment, raw events, stderr, committed evidence
  and HTTP responses for the provider token and exact run capabilities.
  Any hit invalidates the confidentiality claim. The run-capability redactor
  handles only exact bytes; encoded disclosures remain a known limitation.
- This test can support a Windows no-model runner-loss claim for the new
  mediated path only. It does **not** accept full literal `git`/`gh` parity,
  Linux systemd ownership, real-agent timeout/cancellation, host-service
  double failure, or production service-manager installation. Keep #100,
  #93 and Q11 open for those separate gates.
