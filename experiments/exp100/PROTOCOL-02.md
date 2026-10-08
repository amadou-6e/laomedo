# EXP-100/S2: local Git commit-transfer boundary

Issue: https://github.com/amadou-6e/laomedo/issues/100. Governing design
candidate: specs merge `af571c8ba460d8e7042d244ecfad87575ff07fa8`,
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
This protocol is frozen before implementing or running S2. It does not select
the candidate as the product transport or replace the original EXP-100 result.

## Question and limits

Can a disposable agent-side Git repository produce a new commit, export a
single-ref bundle, and have a host-side verifier import that commit into a
separate bare repository seeded only from a trusted pinned baseline? Compare
that with a Git remote-helper sketch on operation coverage and isolation cost.
This is a local, credential-free feasibility check, not a GitHub write, CLI
parity pass, or approval to change the product runner.

Run entirely in temporary local repositories with generated test files. Do
not load `.env`, a GitHub token, a host `gh` profile, a model, Docker, or the
user's checkout. Disable system/global Git configuration, credential helpers,
hooks, signing, replace objects and prompts in every child Git process. Do
not invoke a shell with agent-controlled arguments. The host receives bundle
bytes and trusted run/repository/baseline/branch bindings, not a source path,
remote URL or Git command selected by the agent.

## Frozen cases and expected classes

1. Build a baseline in a disposable source repository. Clone it into an
   isolated agent repository, make one regular-file commit, export exactly
   `refs/heads/run-a` as a bundle, seed a private bare repository from the
   baseline, import the bundle, and verify type `commit`, baseline ancestry,
   expected ref and exact tree contents. The staged commit must equal the
   agent's commit. No provider call occurs.
2. Repeat with a second fast-forward commit. It may depend on the first only
   if the host's trusted per-run journal has confirmed and seeded that first
   commit. Without that trusted seed, classify the thin/missing-object bundle
   as rejected, not as a reason to consult the agent's repository or remote.
3. Reject a bundle advertising an extra ref, an unexpected ref, a ref whose
   object is not a commit, or a commit not descended from the pinned baseline.
   A malformed/truncated bundle is rejected. A workflow-file change is
   classified from staged objects and rejected absent separate approval.
4. Plant an agent-side Git hook, alternate object path, replace ref, hostile
   remote URL and global Git configuration. The host verifier must not run the
   hook, contact that URL, consume the alternate or replacement object, or
   change its trusted repository/ref decision. A local negative control must
   demonstrate the check would fail if an extra ref or workflow change were
   accepted.
5. Record a comparison table for normal `git status/add/commit`, initial and
   later push, fetch, tags, force, and `gh` forms. Mark unsupported and
   untested forms explicitly. The remote-helper alternative is analyzed from
   the documented protocol only, not simulated as though it worked.

Freeze the local fixture names and expected statuses in the probe before the
first recorded run. The probe must be single-use per evidence path, emit a
machine-readable observation without secrets or user paths, and keep its
input commits/bundle hashes, Git version and provider-call count. A test
rebuilds the observation from a fresh temporary directory; `--record` is the
only mode allowed to replace committed evidence. If the implementation needs
a changed case, commit a numbered amendment before another run and keep the
earlier outcome.

## Acceptance boundary

Passing S2 allows a reviewed, bounded transport implementation proposal. It
does not establish safe concurrent bundle replacement, bounded pack resource
use, repeated remote pushes, read-only reconciliation, literal `gh` support,
provider duplicate-write safety, runner integration or production readiness.
Those require separate tests and their own frozen identities. No live GitHub
write follows automatically from S2.
