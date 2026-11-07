# PR250 focused packet at head `a5378a99`

The two fixes from last packet (A-L-D1 and A-D-D1) are done correctly. The three real provider screens look right for what they show. The resume builder bug has the cause you diagnosed. I'd change one part of the proposed fix, though: it depends on a saved field flag that an upstream template refresh could reset (A-R-Q1). This is not approval of the whole PR.

## 1. Recheck of A-L-D1 and A-D-D1: both resolved

**A-L-D1 (lease cleanup labelling): resolved.**
- `cleanup_after_loss` now always keeps the SDK's `verified` flag.
- When the SDK can't confirm cleanup and its detail starts with `removed`, the host reports `late_unknown` (with a watch window) or `unknown` (without one).
- A container that first appears at the deadline is still reported as `late_owned`.
- A host can no longer store "removed" for a cleanup that wasn't confirmed, and no extra removal is attempted.
- The new test `test_unconfirmed_final_inspection_never_reports_removed` runs the real SDK `ContainerWatch` (Docker calls mocked). It covers a final inspection that finds the container still there, a Docker failure, and a conflict, with and without a watch window. Each case expects `(False, unknown/late_unknown)` and exactly one removal.
- It matches the SDK branches I read last packet (`watch.py:88-98`).
- One difference from the old code: a final `conflict` is now reported as `late_unknown`, not `late_conflict`. That is less specific but still truthful, and nothing is lost for safety.
- The leases README describes this.
- I did not open `review-fix-tests-final.log`; the 15 passes are your report.

**A-D-D1 (Claude image tag in setup guides): resolved.** All five lines now use `laomedo-claude-controller:2.1.310-acp0.98.0`:
- `docker/claude/README.md:17` and `:19`;
- `docs/getting-started.md:77`, `:79` and `:109`.

**A-T-S1 (GitHub toolbar guard): resolved.** The guard now checks for the exact `prSelection`/`issueSelection` imports and both lazy viewer imports in `upstream.patch`, and that the Agent patch doesn't reference the GitHub modals.

**A-I-Q1 (installer whitespace warning): closed** on your explanation (CRLF line endings in the working copy). I did not open `installer-recheck.log`.

The fix also updates one recovery-copy assertion in `nodeErrors.test.ts`. It now expects "open Model and use Refresh", plus warnings that timed-out discovery may still be active and to avoid repeated Refresh. That is safer than before.

## 2. Integration resolution records: partly covered

- `integration-resolutions.json` lists 27 files, with hashes for each merge stage and a stated resolution type. `saved-skill-code-resolution.json` lists 5 saved flow JSONs whose Skill code hash moved from `bdef007d4b03` to `92f2ccc8ba61`, sourced from `components/laomedo/skill.py`.
- These hashes are for the `53c3bf5c` merge checkpoint. Having a recorded hash doesn't show the resolution was right.

Resolutions whose actual content I've reviewed, through last packet's full `integration-review.diff`:
- `viewer.py`, the installer, `tests/support/retained.py`;
- `test_feedback.py`, `test_settings.py` and `test_presenters.py`.

**A-I-G1 · integration coverage gap · not a defect.** Resolved content I have not reviewed:
- `.gitattributes`, `AGENTS.md`, `CONTRIBUTING.md`;
- `examples/README.md`, `frontend/langflow-skill-viewer/README.md`, `tests/README.md`;
- `integration/agents.patch`;
- `test_github/test_interface/test_reviewed_cli.py`;
- `node-error-catalog.json`, `module-paths.json`, `symbol-paths.json`. These are described as a three-way merge with no competing values; that claim is unverified.
- The 5 flow JSONs merged node by node. I haven't checked that nodes other than the Skill node match their inputs.
- The retirements:
  - `examples/{agent-activity, github-pr, opencode-node}`;
  - `tests/test_container_lease.py`, `test_exp19_live_e2e.py`, `test_runner_sandbox_policy.py`.

  These are recorded as "archived at `ca6d59e4`, lease assertions moved where applicable". I mapped the old lease deadline cases into `test_cleanup.py`. I have not checked the sandbox-policy and exp19 assertions against their archived copies.

## 3. Real provider screens (all four images opened)

**Activity pages, Codex, Claude and OpenCode:** each shows one graph run with one Agent row, "1 turn", completed, and one turn bar.

| Provider | Model | Captured stream | Input | Cached | Output | Reasoning | Cost estimate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Codex | gpt-6-luna | complete | 37,565 | 34,048 | 178 | 0 | $0.000781 |
| Claude | claude-haiku-5-5 | complete | 7,327 | 1,261 | 276 | 49 | Unknown |
| OpenCode | opencode-go/gpt-6-luna | complete | 4,024 | 0 | 83 | 0 | $0.000520 |

- Claude's cost card shows "Unknown — no priced observations captured"; it isn't faked as $0.
- OpenTelemetry records: Codex has 0 ("No OpenTelemetry records captured"), Claude has 30, and OpenCode has 0.
- Layout is consistent across the three: clear hierarchy, aligned stat cards, charts that fit, nothing overflowing at 1600px.

**Codex graph:** one Codex Agent with the README task, fresh, gpt-6-luna, low. The zoom controls overlap the "Submission / Outcome" output label ("ome"). That is the same upstream overlay issue as the optional G-V-S2.

**`live-runs.json`, `activity-browser-results.json` and `*-native-facts.json`** (records, not my own observation):
- Each provider ran once (`new_native_runs: 1`), completed, with no `error_category`, no page errors and no visible failure.
- Each answer correctly reports `# laomedo` and gives a sensible summary.
- Cleanup:
  - Codex: controller cleanup confirmed, native turn completed, `evidence_complete: true`.
  - OpenCode: controller cleanup confirmed, `evidence_complete: "complete"`, native turn status null.
  - Claude: descendant cleanup verified, controller cleanup null, native turn status null, `evidence_complete: "unknown"`.
- Claude's `evidence_complete: "unknown"` stays separate from its "Captured stream: complete". That is the stream-capture state, not proof the task succeeded, and I'm not treating it as such.

## 4. Resume builder failure

The cause you diagnosed is supported by the code:
- The builder adds an edge from the first Agent's `run` output to the second Agent's `run_reference` input (`examples/agents/build_flow.py:63-64`).
- The component declares `DataInput(name="run_reference", show=False)` (`agents/interface/langflow/component.py:324-329`).
- On import, upstream's `filterHiddenFieldsEdges` (`reactflowUtils.ts:380-403`) removes any edge whose target field has `show === false` in the node's template.
- `AgentAdvancedControls.tsx:9-12` also hides `run_reference` for all three Agent types.
- The component then refuses with `prior_run_required` (`component.py:716-717`), which is what `resume-diagnosis.txt` shows: two Agent nodes, Operation `resume`, "No previous run is available", and no native run.

**A-R-Q1 · question · medium · real failure in the maintained example.** The proposed fix makes sense and adds no disconnected setting or selector. One part looks fragile:
- **The renderer change is fine.** Showing the port only when that exact field has an incoming edge is a narrow compatibility rule. Keep the existing test that disconnected `run_reference` stays hidden, and add the connected case.
- **The builder change may not hold.** The filter reads `show` from the template saved with the node. If Langflow refreshes the node's template from the server component, for example when the component code hash changes, the server's `show=False` comes back and the edge would be dropped again on the next load or update.
- **A sturdier alternative:**
  - remove `show=False` on `run_reference` in the component, so the field is accepted as an edge target;
  - keep the renderer hiding it unless it has an incoming edge.

  This removes the dependence on a saved flag, and the user still sees no disconnected Prior Run control. It needs a check that server-side admission still refuses `run_reference` input that is shown but not connected, which it already does (`prior_run_required`).
- **Required evidence either way:**
  - a browser import of the resume flow that keeps the edge and runs one native resume;
  - a test that disconnected `run_reference` stays hidden;
  - a test that refreshing the template doesn't drop the edge.

I can't approve the fix until it is implemented.

## Verdicts

- **Implementation: APPROVE** for the review fixes (A-L-D1, A-T-S1) and the integration content already reviewed. The resume path is **REVISE**, pending the A-R-Q1 fix.
- **Spec:** no spec change in this packet. The draft spec 403 dependency is still open.
- **Docs: APPROVE.** A-D-D1 is resolved.
- **Visual: APPROVE for the four screens inspected:** the three Activity pages and the Codex graph. Still to see: error states, expanded controls, resume (currently broken), cancel, and graphs for multiple providers. This is not full UI approval.

## Not read or not checked

- **Not read this round:**
  - `AGENTS.md` and `CONTRIBUTING.md`. They were requested and I didn't read them, so I can't confirm compliance with them;
  - `review-fix-tests-final.log`, `installer-recheck.log`, `integration-inputs.json`;
  - `resume-diagnosis.png` (I read the `.txt` only);
  - the full native-facts files (I grepped key fields only);
  - `examples/graph.py` beyond the builder's edge call;
  - `prior-reviews/`, which I have not read in this or the previous packet.
- **Integration content gap:** see A-I-G1.
- **Separate closure still needed:** the conservation coverage from older packets and test data.
- **Not established:**
  - a green full TypeScript check (it still fails on inherited diagnostics: 259 candidate vs 265 accepted, no new ones);
  - real resume, cancel and error paths;
  - your browser validation.