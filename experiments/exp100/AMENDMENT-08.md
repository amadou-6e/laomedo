# Prospective S10 native end-to-end capture

Before executable probe implementation or capture. Original PROTOCOL-10 and
AMENDMENT-07 remain unchanged. Candidate implementation: `22837c4`.
Native surface selected in specs `d4dd27a`; scoped fetch choice is explicitly
user-approved and recorded in draft specs #315 (`192fa6d`). Spec merge and
independent pre-run review remain prerequisites to capture.

Identity: `exp100-native-s10-20261010-a`. Claim it exclusively in private state
before setup; no second invocation of that identity. Require a clean source
checkout and exact independently reviewed source SHA supplied by the controller.
No real GitHub call, reusable credential in the agent, or model turn. Use the
pinned Git-capable container, real mediation HTTP/client/store, production Git
remote helper/gh adapter, exact-container stage ownership and production bundle
verifier. The provider connectors are explicitly fake REST and local bare Git.
Host-only credential supplier returns a synthetic credential. No lease/service
manager lifetime or user-facing agent judgment is exercised.

Seed a local provider base `develop`, with absent run branch. Trusted approval
permits git_fetch, git_push, pr_create, pr_update and pr_read for that run and
configured base. Mount only the run capability, trusted wrappers/scripts and
checkout; no .env, host gh login or account-store credential. Capture:

1. Literal `git fetch origin` reads `develop` through host transport; exact
   advertised/ref/object agreement and local remote-tracking base are checked.
2. Literal first `git push origin HEAD:refs/heads/run-branch` freezes/verifies
   before an exact absent-ref CAS push. Repeating the same confirmed command
   must not cause another provider push or new stage.
3. A second committed change pushes fast-forward using the trusted journal
   predecessor. Provider ref equals the second commit; exactly two pushes.
4. Literal supported gh creates one PR, reads it, corrects its body and reads
   it again while the container is alive. Bound branch/base/head/body agree.
5. Force/other-ref/multiple-ref pushes and unsupported gh commands are refused;
   unbound PR read is refused. The provider journal must show no such targets.
6. While the scripted container remains alive, host controls mark the run
   complete, then replace its connection and revoke its grant. Stage/push/read
   or new PR update must be refused appropriately with no further provider
   call. This is not a runner-loss or GitHub-side token-revocation test.

Machine-produced observation records exact source, image, identities, commit
hashes, command outcomes, sanitized provider method/path/refspec journal,
confirmed store effects and negative-control codes. No token, request header,
absolute personal path, credential file or raw private agent transcript.
Preserve failed/unknown outcome and do not retry effects. Bound fixture wait
to 180 seconds; on timeout record incomplete/unknown, stop exact agent
container, wait for verifier, reconcile only recorded owned stage containers,
and report cleanup uncertainty. Preserve the claim and result on failure.

Acceptance requires every positive readback and negative refusal, exactly one
PR create and two Git pushes, no changed provider count after post-completion
controls, and verified cleanup. This only establishes the stated local
scripted integration, not native git/gh parity, real providers, managed
startup, cancellation, crash/recovery, budgets or first-slice acceptance.
Capture once only after executable code is committed and independently
pre-reviewed; results are then reviewed separately before recording evidence.
