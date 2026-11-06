# Current conservation checkpoint: 6 November 2026

Four draft PRs remain separate and target develop. The visible implementation
checkout remains clean on develop at 37dc9aa9. No old PR has been retired or merged.

| Concern | PR | Pushed head | Worktree |
| --- | --- | --- | --- |
| Shared | #255 | 1db2a234408345e3751fe63f6a02d5b5fc5e197c | shared-reconciliation-237 |
| Skills | #254 | 972688347cd2c774e2f8096800987c9fe515cb33 | skills-followup-206 |
| GitHub | #249 | 4d59e9d90555982a5f8930c3d5fd1e7f90137fac | github-restored-245 |
| Agents | #250 | e61f5ae3282f3f2bae37ba879ac748ecf6b99362 | agent-refactor-205 |

The detached integration candidate is 42a16c392f8b7ee2d1ad8d31f1f23f98f7b64de5,
tree 37f7efaa8a626e5eb5c0b3c137999529374a0045. Its complete binary patch from
develop is preserved here. Applying the patch to a separate index initialized
from 37dc9aa9 produced exactly that tree. This preserves local merge resolutions
without a fifth production PR or wholesale experiment merge. The local candidate
commit is not a published GitHub commit; use the patch and manifest to reconstruct.

## Changes and supporting verification

Frontend assets now belong to errors, recovery, skills, agents or github, with
cohesive subpackages, models, functions, components, declarative READMEs and
installer paths. Skill Monaco lifetime moved into its source-editor component;
Agent activity renderers and projections were separated; GitHub viewers now have
separate Issue/PR owners. A real browser check exposed a queued rename-focus
race. The new regression fails on the old code and passes with the correction.

The approved CI change runs the complete Agent test concern in the existing
runner job. Test and documentation conservation gaps were repaired, including
manual migration refusals, described model fields, error catalogues, literal
wire/preimage contracts, retained dependency admission and historical wording.

- Combined source: 1014 tests, no failures/errors, 17 initial skips. Six Node,
  four formatting-policy and two no-model Docker cases subsequently passed.
  Three installed-artifact tests cover the installed-package skip as well as
  resources/import ownership. Four Windows symlink cases remain locally untested.
- Wheel: all 353 declared production files match source exactly; imports were
  validated under isolated Python against that wheel. The 67 architecture README
  files are source documentation, outside the declared wheel data inventory.
- Frontend: all 811 cases in 32 affected suites pass, including Shared error and
  recovery. The production build passes after the rename correction. Actual
  served index and Skill viewer bundle bytes match that build.
- Actual headless Edge: real local Skill import/history, search/collapse,
  full-page/restore, discard cancel/confirm, genuine edit/promotion, settled
  selected-file diff, PNG/JSON upload, inline rename, actual drag/drop, empty
  folder retention, immediate deletion/undo/redo, exact path copy and byte-exact
  multi-file publication passed. The private registry has three actual commits.
- Natural service outage: copyable descriptive popup stayed inside 1024x720,
  dismissed without closing the viewer, and real service restoration plus
  Reload history recovered. Natural missing local source, failure placement,
  successful discovery and selecting the published revision also passed.
- All 8 configured hosted checks passed on each pushed head listed above.

These are supporting controls and scoped real Skill paths, not fresh provider,
authenticated GitHub, independent reviewer or requesting-owner acceptance.
The two Docker controls use internal development fixtures and spend no model turn.

## Required next steps

1. Resume the existing Claude reviewer after its reported 16:30 Europe/Berlin
   reset. Codex session 01a14a4b-331a-72b2-947e-ef8192b3342d reuses Claude session
   266a9306-48e9-4131-b8f5-06dbe0d41e71. Do not start a new reviewer session or
   retry repeatedly before the reset. The last non-Python test-data packet is
   incomplete; its actual native quota failure is recorded locally. Earlier
   completed reports retain their exact coverage and exclusions.
2. Finish that packet and obtain focused rechecks of confirmed corrections,
   frontend modularity/installer resolution, the rename fix and actual screenshots.
   Preserve full substantive diff coverage against the intended base; previous
   approval is scoped to its reviewed revision, not these final heads.
3. Resolve remaining Agent/GitHub acceptance and spec gates, including draft
   specs #403 and #391 where applicable. No fresh provider or authenticated GitHub
   acceptance is claimed here; no new model run or external GitHub edit occurred.
4. Obtain requesting-owner inspection and explicit validation of final relevant
   workflows. All four PRs stay draft and unmerged until their gates are met.
5. Intended order is #255, #254, #249, #250. After each accepted merge, incorporate
   actual develop into the next owner and recheck exact resolved source and CI.
   Use the resolution ledgers and exact candidate tree as conservation references;
   do not put this complete combined patch onto a single owning production PR.
6. All 23 checkpoints #213,#214,#216-#234,#236,#238 remain OPEN/HOLD. Close only
   after their full preservation/replacement has actually been independently
   verified; never merge the old stack separately or merge exp wholesale.

## Private preview

The real loopback app remains intentionally available at
http://127.0.0.1:17860/flow/c6a92f33-32e8-486e-8d2a-a611df6b6fe1 .
Open Skill files to inspect the private copy and its three retained commits.
The Source discovery graph is
http://127.0.0.1:17860/flow/71f83a82-6f9d-4ea1-92a2-b54077c412de .

App/source/operation services use only task-owned temporary state and loopback
ports 17860, 18782, 18787. Browser automation closed its own contexts; disposable
Docker controls passed and no labeled native-development container remained.
Private API tokens, browser storage state, runtime databases and service logs are
not archived. The local runtime-path record identifies task-owned cleanup targets;
preserve the preview while the owner is inspecting it. Do not stop unrelated
services, browsers, profiles or containers.

## Final type and link checks

All 811 affected frontend tests pass; the final 39-case focused recheck also passes.
The nullable Activity target is guarded and has a no-dispatch regression. Full
TypeScript still reports 253 diagnostics, identical to clean pinned upstream with
the same dependencies after explicitly documented path/union-order normalization.
No additional diagnostic is suppressed or excluded. All 298 checked relative file
links resolve. All 344 production Python files have no class inside a function or
method. The actual unstarted Activity failure and same-read Refresh were observed;
normal captured Activity/provider rendering remains unverified. Auto-login browser
access does not establish cookie identity continuity or profile/expiry recovery.

Private service PID files are hints only. Before cleanup, verify the executable,
command/runtime path and current port ownership; never stop a reused stale PID.
