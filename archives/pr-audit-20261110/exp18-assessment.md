# EXP-18 / PR 58 disposition assessment

Date: 2026-11-10. This is a source/specification investigation, not a new security
test, exploitation attempt or provider/model execution.

## Decision

Archive the old implementation. Do not continue or merge PR 58 unchanged.
Retiring that production-targeted PR is recommended; its existing issue
[48](https://github.com/amadou-6e/laomedo/issues/48) should remain open for the
unresolved protection requirement. This investigation leaves PR 58 open for the
owner's disposition decision and does not edit or close issue 48.

The useful continuation is a fresh, reviewed protocol against current supported
provider command boundaries, under the existing issue. It is not a resurrection
of the October Docker harness or permission to spend a historical model budget.

## What the old checkpoint established

At `571dac87d11f6b822129b9b2787f8f6bb990e4bc`, the committed observations describe
a direct, deterministic process test on Docker Desktop 27.3.1: writable disposable
checkout, scoped HTTP canary, immutable effective skill, protected markers absent,
symlink rejection, revocation and cleanup. The record says `model_turns: 0`.

That is historical direct-process evidence. The deferred agent-originated
forbidden-access step was not performed. The open issue explicitly requires
designing/reviewing the safety protocol before bounded execution; it grants no
new model calls or personal-credential access by itself. Authentication deferral
and the historical 0/4 ledger must not be interpreted as a runtime service cap.

## Why the harness is obsolete

- `experiments/exp18/probe_create_only.py:16,86` pins and enforces engine 27.3.1
  and literal image IDs. `preflight.py` compares an entire historical HostConfig
  projection. Those observations cannot establish a newer engine's behavior.
- `probe_stage.py` imports retired `laomedo.local_runner` names, binds an old
  sidecar on port 8767, and constructs its own stage topology. It does not exercise
  today's ACP/provider command path or the shared `py-docker` runtime.
- Current provider boundaries are not identical. At inspected Agent PR 250 head
  `0e23b3b9bcfc949d5254fa6f0c5499dd45ae18f6`:
  - Codex's `agents/agents/codex/split/executor.py:44-67` uses an exec-server on
    bridge networking with a writable `/draft` and no credential mount in that
    recipe.
  - Claude's `agents/agents/claude/policy.py:145-183` separates the controller
    profile from workers and selects worker networking independently.
  - OpenCode's `agents/agents/opencode/executor.py:173-201` uses a network-disabled
    worker with a writable draft and read-only canonical/store mounts.
  These are source-level recipe observations, not proof of effective denial or
  of a vulnerability. The old canary layout cannot be assumed to represent them.

## Why the requirement is still relevant

Canonical specs revision `125137a819b56a6347e3fdf12eb90132d147aebd`,
`agent-execution/design/decision-readiness.md` Q18 still identifies E05
as necessary to establish effective protected-root, symlink and shared-home
containment. Its S04 says unavailable requested protection must block dispatch.
The OpenCode contract expressly distinguishes direct command separation evidence
from agent-originated denial, network isolation and child termination.

Current Codex preflight regressions check a credential-free, network-disabled,
read-only version job. Such a job has neither the writable workspace nor the
agent-issued command path required by E05. Provider recipe/unit tests are useful
regressions, not live agent-originated confinement evidence.

Closed issues 100 and 104 concern mediated GitHub capability, grant revocation and
independent lease cleanup. Those questions overlap authority/lifetime but do not,
by themselves, prove protected-filesystem denial for a native agent command.
The agent need not receive a reusable GitHub credential to test this property.

## A useful future continuation

Under issue 48, first review a protocol that:

1. Pins current provider/runtime images, Docker endpoint and actual command route.
2. Defines allowed workspace and skill access separately from forbidden host,
   credential and store access; does not assume every provider has the same
   network mode or mount semantics.
3. Uses disposable marker files and stand-in secrets, with no personal profile
   or real credential deliberately exposed to a probe.
4. Exercises actual agent-originated commands, symlink/alias attempts, applicable
   network restrictions, refusal-before-dispatch and exact owned cleanup.
5. Separates direct setup controls, actual native-agent evidence and uncertainty;
   records an explicitly authorized fresh time/spend allowance outside services.

This is a proposed protocol outline, not authorization to implement or execute it.
No new protocol, live model run, security acceptance or issue-state change is
claimed by this assessment.
