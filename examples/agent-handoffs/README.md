# Explicit two-agent handoff

`flow.json` is generated using pinned Langflow 1.12.3. It connects Chat Input,
pinned Skill, Codex A, explicit Handoff, Codex B and Chat Output. Both agents start
fresh independent workspaces. Handoff rejects failed A and passes only the selected
answer or explicit task override. Its provenance output connects to B and persists
in B's runner record. Runtime loop support is not inferred from cyclic visual edges.

Run credential-free tests:

```powershell
python -m unittest discover -s tests
```

Inside the existing pinned Langflow environment:

```text
python examples/agent-handoffs/build_flow.py
python tests/langflow/test_handoff_graph.py
```

`laomedo.handoffs.BoundedController` schedules finite chains or bounded loops via
`laomedo.handoff_http.RunnerAdapter`. Supply target provider/model/effort, pinned
skills, positive iteration and turn budgets, deadline and explicit success predicate.
It conservatively reserves each possible submitted turn and never retries uncertain
dispatch. Text output supplies the next task. Explicit artifact manifests import
only selected files from completed, hash-bound snapshots into `handoff/` in the
new independent workspace. Traversal, protected profile/credential paths, links,
hash mismatches, existing destinations and case-insensitive conflicts fail before
model dispatch. Maximum 32 files, 1 MiB per file, 8 MiB total. Cross-provider files
require a common audited store and currently fail closed.

The native `LaomedoBoundedController` node schedules the same controller with exact
success-answer comparison, explicit iteration/turn/deadline limits and private
execution records. Both outputs share one execution per build. Langflow request
cancellation sends cancellation to the adapter and retains the partial record;
acknowledgment is reported separately. Restart inspection uses
`BoundedController.inspect(state_directory, execution_id)` and never replays an
uncertain dispatch. Fresh controllers always create a new execution ID.

The component requires the Laomedo runtime package in the Langflow Python path.
`compose.yaml` is a deployment draft with separate UI/state volumes and a read-only
runtime package mount. It was not applied to the user's shared services. It does
not mount credentials or change runner permissions.

Host tests and pinned-runtime synthetic graph tests cover independent stopping
conditions, cancellation evidence, safe selected import and restart provenance.
`live_chain.py --approved-two-turns` is an explicitly bounded two-node acceptance
harness, with no retries or automatic auth handoff. Check the published evidence
record for actual submitted turns and results. Shared sequential workspaces remain
unsupported; the default independent policy is enforced. Fresh
POST cannot expose remote run ID early, so cancellation/timeout is not proof the
remote agent stopped (Laomedo #22). Existing permissions and ledgers stay unchanged.
