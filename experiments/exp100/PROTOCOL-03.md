# EXP-100/S3: trusted run-bound bundle handoff (local, no provider)

Issues: [#100](https://github.com/amadou-6e/laomedo/issues/100) and
[#104](https://github.com/amadou-6e/laomedo/issues/104). Governing design:
`amadou-6e/specs` commit
`b5b27170523334cc886cb0ea27ec616bef44fd4e`;
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
This protocol must be committed before implementing or recording S3. S2's
recorded result remains unchanged. This exercise selects a local integration
candidate only; it does not authorize GitHub writes, model turns, or promotion.

## Question and fixed boundary

Can a trusted host controller consume one agent-written Git bundle from the
workspace belonging to an already saved run, verify it against that run's
trusted baseline and approved branch, and make the verified commit available
in a private host-owned Git object store without trusting agent Git config,
hooks, paths, refs or remote URLs?

The run record, not the agent request, selects the workspace, repository,
baseline and branch. The agent may select only the bytes placed at a fixed
handoff filename inside that workspace. The host never invokes Git in the
agent repository. It reads at most 4 MiB from a regular, single-link file,
rejects links/reparse points, and copies exact bytes to private staging.
Concurrent replacement must yield either a verified frozen byte sequence or
a known rejection, never a different payload sent to Git than the one hashed.

All host Git commands run without provider credentials, inherited Git/GCM/GH
environment, global/system config, hooks, signing or prompts. They are bounded
by process-tree timeouts. The private stage is seeded from the pinned trusted
host source; the bundle must advertise exactly the run's approved ref, SHA-1
objects, no filters and no other refs, and pass `fsck --strict` rooted at its
commit. It must descend from the pinned baseline. Workflow-file changes are
rejected absent separate trusted approval. A later thin bundle may depend
only on a previously host-confirmed commit for that run and branch.

No provider token, mediator write request, remote push, PR creation, model
turn, or host checkout mutation occurs in this protocol. All paths and Git
identities are disposable test fixtures; no `.env` or host `gh` login is read.

## Frozen local cases

1. One clean agent commit exports the approved ref. The host accepts the
   exact bytes, records their SHA-256 and commit/tree IDs, and imports only
   into a private stage. The agent workspace can be deleted afterwards;
   classification remains reproducible from the staged objects.
2. A second fast-forward commit is accepted only when the first commit is in
   the trusted per-run confirmed journal. Without that journal entry, the
   thin prerequisite is `missing_prerequisite`.
3. Wrong run, wrong branch, extra ref, wrong baseline, workflow-file edit,
   symlink/reparse point, hard link, oversize file, swapped file, truncated
   bundle, missing object, alternate object source and malicious agent hook
   are rejected before any provider effect. The hook and hostile remote are
   positive controls: the test fails if they are invoked or contacted.
4. A malformed or timeout case preserves a failure record and never triggers
   another transfer automatically. A duplicate transfer with identical bytes
   and same run identity may be read-only idempotent; conflicting bytes under
   that identity are refused.
5. Confirm that the host-owned stage is outside every agent mount and that
   `git status/add/commit` still work inside the isolated agent repository.

The test must have controls capable of failing if wrong-run bytes are accepted,
an extra ref is accepted, or an unverified commit is made available for push.
Record Git version, accepted/rejected class, artifact hashes, exact local
provider-call count (must be zero), model-turn count (must be zero), and any
limitations. A first failed attempt is evidence, not permission to rerun an
ambiguous effect. Amend this protocol in a new committed file before changing
the frozen cases or running a new evidence identity.

Passing S3 permits wiring a staged commit to a separately reviewed mediator
request. It does not prove safe remote pushes, literal `gh` coverage, `git
fetch`, production service management, or #104 acceptance.
