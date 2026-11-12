# Owner-graph acceptance harness review (production a046a07e)

**Bottom line:** the fourth attempt's evidence does establish, for Codex only, a real maintained graph doing a fresh run and a resume on the same run, with both Activity captures completed and retained, and a cancelled graph task reaching a confirmed native cancel. It is sufficient for this bounded owner-delegated gate even though the PowerShell exit status was unreliable. It is not browser acceptance and says nothing about other providers. I found no production defects; the gaps below are harness and evidence limits.

## What the checks prove

**Fresh then resume on the same run: established.**
- The graph comes from the maintained `examples/agents/build_flow.py` with `workflow="resume"` (two nodes, one `run_reference` edge) and runs through the real `Graph.arun` against a real `RunnerServer` and `CodexAgent`.
- The runner state lives in a fresh temporary root, so `len(records) == 1` cannot be satisfied by leftover runs (line 59).
- `status == "completed"` and the marker check are asserted (lines 61-62).
- The two completed Activity invocations (`agent` and `follow-up`) show that two turns actually ran, so the resume did not silently skip.

**Retained common Activity: established, with one gap.**
- After waiting up to 30 seconds for the observer, the harness asserts two runs with both nodes `completed`/`complete` and at least one receipt (10 were recorded) (lines 75-77).
- **Gap (harness):** it selects `runner_run_id` but never asserts that it equals `record["run_id"]`. Captures are therefore not explicitly tied to the accepted run. In this isolated database it can only be that run, so this weakens the evidence rather than the result.

**Graph-task cancellation reaching a confirmed native outcome: established.**
- The only stop trigger is `task.cancel()` on the `arun` task (line 96); the harness never calls `agent.cancel` directly.
- The native status `cancelled` with `cancel_confirmed: true` therefore had to come through the component's own cancellation path to the runner.
- The run was confirmed `running` before the stop, plus 3 seconds.

**Scope is not overclaimed.** The acceptance note explicitly excludes browser and visual Activity, Claude and OpenCode at this revision, host or daemon loss, private access, GitHub mediation and default OpenCode.

## Is `graph_complete` + `graph_stop` enough despite the exit-code issue?

Yes, for this bounded gate:
- `graph_complete` (line 78) prints only after every run and capture assertion has passed.
- `graph_stop` prints just before its own assertion (lines 108-109), but the printed values (`cancelled`, `true`) satisfy that assertion.
- Every exception path prints a `failed` record. None follows `graph_stop`, including after the `finally` cleanup.

The note correctly refuses to treat the PowerShell exit 1 as a passing process check, and the direct native exit code was not captured.

## Evidence limitations (not production defects)

1. **The observations are transcribed.** `owner-graph-observations.json` is a curated record, not the raw console log, so I relied on its fidelity. The harness SHA-256 is recorded, but I can't recompute it read-only.
2. **The source revision comes from `git rev-parse HEAD` only.** A dirty working tree would not be detected; no `git status` was recorded.
3. **Container cleanup after the cancel run is not checked.** "No surviving containers" was observed only after attempt 3. Cleanup is not part of the stated gate, so this is optional.
4. **The Activity of the cancelled run is not checked.** No claim is made about it, so this is consistent.
5. **The earlier attempts were disclosed honestly:**
   - attempt 1: assertion with no message;
   - attempt 2: Activity checked before the asynchronous observer finished (a harness timing issue, fixed by the 30-second wait);
   - attempt 3: `docker_control_failed` before inference, an environmental failure with no production change since.

## Verdicts

- **Implementation:** unchanged. The coverage APPROVE through 3ebc4a34 still applies; production a046a07e differs only by status docs.
- **Acceptance evidence:** ACCEPT for the owner-delegated real-graph gate, Codex only, bounded by the limitations above. Recording the native exit code and asserting the `runner_run_id` link would strengthen it but are not required.
- **Visual:** unchanged. No browser or Activity UI was inspected here, and the earlier visual APPROVE scope is not extended.
- **Not authorized:** merge or issue closure.