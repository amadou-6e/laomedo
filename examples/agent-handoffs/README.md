# Explicit two-agent handoff

`flow.json` is generated using pinned Langflow 1.12.3. It connects Chat Input,
pinned Skill, Codex A, explicit Handoff, Codex B and Chat Output. Both agents start
fresh independent workspaces. Handoff rejects failed A and passes only the selected
answer or explicit task override. Provenance is exposed separately, not durably
attached to B yet. Runtime loop support is not inferred from cyclic visual edges.

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
dispatch. Text output supplies the next task; artifacts fail closed. This is not a
native Langflow loop node and has no durable restart/reconnect state.

Observed: 48 host tests and two pinned-runtime synthetic graph tests pass. No live
model calls were made for #28. Installed UI, real chain/loop, selected file import,
shared workspaces and cross-provider live acceptance remain outstanding. Fresh
POST cannot expose remote run ID early, so cancellation/timeout is not proof the
remote agent stopped (Laomedo #22). Existing permissions and ledgers stay unchanged.
