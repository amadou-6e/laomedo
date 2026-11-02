# EXP-94: visible Playground Stop to the bound native run

Frozen before implementation-specific browser capture. Issue: Laomedo #94.
Source base: Laomedo `develop` `d69c9a26d5bd591d2e99fb7f4a76b825fc66c343`.
Governing specs: `amadou-6e/specs` `d3c888498e3e9be2f5a1248ae4d949624bc6ba97`,
agent-execution `contract/early-run-cancellation.md` and Langflow integration
Q11. Runtime: cached Langflow 1.12.3 image
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

Use one disposable local Langflow container/volume, a loopback-only synthetic
runner and a headless browser. No model, real agent container, real credential,
GitHub write or production data. Freeze the code, fake runner, browser probe,
image digest and case parameters before running. Each dispatched case is
executed once; no retry of an uncertain start.

Case A: choose nonblocking `start`, hold the runner's early acknowledgement for
three seconds, and click the **visible Playground** Stop after the runner has
received exactly one POST but before the acknowledgement. Case B: choose
blocking `fresh`, return an early identity, enter a six-second synthetic wait,
then click the same visible Stop. Control: let a run finish, then verify no
cancel targets it after completion. The browser must record the exact Stop
control and Langflow job request; the fake runner must journal exact request
ID, run ID, status, GET and cancel traffic, including any synthetic effect.

Pass requires exactly one start per active case, the Stop-associated cancellation
to reach that same run, no cancellation of another or completed run, and no
synthetic effect after a confirmed pre-effect cancel. A 202 cancel response
means requested, not terminal confirmation. If binding cannot be recovered,
retain an uncertain result and do not start another agent. UI state or Langflow
job status alone never proves native cancellation. A missing browser click or
unobserved backend-to-component signal is inconclusive, not a pass.

Record machine-written sanitized case files, journal and committed-byte hashes.
Keep token, browser profile, screenshots and raw server logs private. Model-turn
budget: zero. This probe does not accept Q11's real-agent/container gate or
the separate crash-cleanup gate #93.
