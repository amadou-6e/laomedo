# EXP-22 Phase C: integrated lease and cancellation boundary

This protocol is a proposal for the remaining #22/#93 real-stage check. It
must be committed and independently reviewed before a model turn. The old
Phase B ledger has three unused turns, but its grant covered Phase B only. Do
not spend them here. No Phase C model turns are authorized by this file.

## Boundary and fixed inputs

- Use the merged, pinned Docker Codex image ID and record its CLI version,
  source commit, component revision, requested model and effort, and every
  task/skill byte hash before dispatch. Refuse a changed image or source.
- Use a new private run directory and synthetic pinned skill. The current
  mediated lease route is non-split: its Codex profile volume, including the
  provider login, is mounted in the agent container. Codex's `auth_read`
  sandbox control must deny agent commands access to `auth.json`; record the
  volume name, mount target and negative-control result without recording the
  login. Do not claim controller-only credential custody. The provider login
  remains exposed to the container process itself, so this is a bounded local
  test, not proof of an untrusted-container credential boundary. No personal
  skills, personal checkout, host `gh` login, Git Credential Manager, or GitHub
  token may enter the agent container. Record only nonsecret credential mode
  and outcome. Obtain an explicit decision for this exact custody mode before
  copying or using the subscription login. The preflight `command/exec`
  `auth_read` result alone does not prove an agent tool call uses the same
  policy. The first approved model turn must attempt an agent-originated read
  of `auth.json`, record a denial without printing its contents, and confirm
  tool-call network access to the scoped mediator. Stop on a readable login.
- Start the lease/mediator process independently of the runner's process tree.
  Use a fake, credential-free transport with an append-only receipt for one
  disposable operation. The container receives only its run-scoped mediator
  capability. This case is not evidence of a real GitHub write.
- Freeze the exact prompts, artifact names, timeouts, safe-stop commands and
  private evidence directory. Never replay an ambiguous effect with a new ID.
  Before dispatch, verify that service identity and grant ownership match the
  run, that the capability is absent from logs and argv, and that a second
  unrelated run has an independent grant.

## Execution sequence

1. With zero model turns, run the host tests and the opt-in Docker routing
   check. Confirm the service survives a runner-tree kill, the fake transport
   refuses A after revocation, B still works, the owned container is absent,
   and a same-prefix lookalike remains. Abort if any preflight fails.
2. Obtain a separate explicit model-turn cap and credential decision for this
   exact protocol. Count every submitted `turn/start`, including a timeout.
   The proposed cap is four turns, with two planned runs and up to two
   diagnostic retries. A retry needs a recorded cause, an unused turn and a
   check that no ambiguous mediated effect would be replayed. Record the
   ledger before and after each attempt. Do not run if the cap or nonsecret
   login reference is missing.
3. Start one Codex run through the real runner with the pinned skill and
   scoped fake-mediator grant. Capture the early run ID before turn completion.
   The task asks the agent to make one deterministic mediated fake write and then
   enter a long, observable command. A successful mediator receipt must bind
   the run, effect ID, invocation, repository and scope; raw output is not an
   authorization or completion signal.
4. After the native command-start event, request cancellation by the saved
   run ID. Record the HTTP acknowledgement separately from native interrupt,
   terminal run state, exact-container inspection, raw-event retention and
   fake-transport receipts. Require a saved native `turn/completed` event with
   status `interrupted` for the native-interrupt criterion. A bounded wait that
   expires without it records an unknown native outcome, even if exact Docker
   cleanup succeeds. Never infer confirmed cancellation from the HTTP request
   alone. Check after the command's original delay that its sentinel is absent.
5. In a separate run, kill the runner's entire Windows process tree while the
   agent's tool is active. Before launch, freeze an in-container loop that
   issues new, distinct effect IDs in the approved fake-write scope and logs a
   host-correlatable timestamp and response for each. A host-side call using
   A's capability is a separate boundary check, not agent-originated evidence.
   On one host monotonic clock, measure the kill,
   lease detection, grant revocation, post-revocation request and exact
   container removal. Record the source of each timestamp and distinguish
   lease-service `removed` from `already absent` after the Docker client exits.
   Only the former proves service-attributed cleanup. If the container is
   already absent or the agent loop stops before a post-revocation request,
   classify service-attributed cleanup or agent-originated denial as
   inconclusive, respectively; do not promote a host-side denial to either
   claim. The post-revocation
   request must be a new effect in the
   already approved scope, not a retry of an unknown effect. Verify no new
   fake-provider receipt, B remains usable, the lookalike survives, and the
   startup sweep records the old run as interrupted or unknown without
   redispatch. A failure to verify cleanup remains unknown, never cancelled.

## Pass, fail and evidence

For #22, pass requires a stable early ID, no duplicate dispatch, native
interrupted status for the active cancellation, a confirmed exact-container
stop, retained partial raw events, and honest remote-cancel reporting.
For #93, pass requires pre-launch exact ownership, independent service
survival, grant denial and exact cleanup within 60 seconds, B continuity,
lookalike survival, and startup reconciliation with no redispatch. A real
agent turn without a mediated request is inconclusive for agent-originated
grant routing. This Windows case says nothing about a Linux service manager.

Preserve raw traces and login state only in a private directory outside Git.
Commit sanitized machine observations, the protocol and source hashes, turn
ledger counts, negative controls and an explicit limits table. Scan committed
evidence, argv, environment and the container mount list for the provider
login, capability and any host GitHub credential without printing their
values. A credential leak, unverified container cleanup, service death, an
unexpected provider call, or an exceeded turn/time cap stops the experiment.
Do not relabel EXP-104 S6 or earlier synthetic EXP-93 evidence as this result.
