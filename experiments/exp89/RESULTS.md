# EXP-89 results: Langflow Playground Stop

This is a zero-model-turn, local-only probe of pinned Langflow 1.12.3 and
the committed Laomedo Codex component. The protocol and three amendments
were committed before their respective runs. The checked-in
[`observation.json`](observation.json) is a sanitized transcription of the
ignored browser outputs and fake-runner journal. The probe and fake runner
are committed so the capture can be repeated in a fresh disposable setup;
the synthetic token, browser profile, Langflow volume and raw journal are
not published.

| Case | Visible Playground Stop | Native runner evidence | Conclusion |
| --- | --- | --- | --- |
| A: delayed `start` acknowledgement | Click completed 0.29 s after runner POST, before acknowledgement | One POST, zero cancels during eight-second observation; acknowledgement still sent | Stop did not reach the native runner in this path |
| B: blocking `fresh` wait | Wrong graph-canvas Stop was selected; click timed out | One POST, effect after six seconds, zero cancels | Inconclusive for UI Stop; not retried |
| Completed control | No Playground Stop after completion | One POST, one effect, zero cancels | No active cancellation inferred |

An earlier Case B browser setup attempt could not access the hidden textarea
and made zero runner POSTs. Amendment 02 permitted the real Case B attempt.
Case B then dispatched, so Amendment 03 deliberately did **not** permit a
retry. The only completed active Stop click is Case A. It proves a gap for
the current `start` path, not every possible Langflow graph or a real Codex
turn. The graph-canvas Stop and Playground Stop are distinct controls.

The current component shields its blocking HTTP task, and Langflow's own job
status is not a substitute for a native cancel acknowledgement. Q11 remains
open. The next implementation must explicitly correlate UI Stop to the
bound runner run, issue a native cancel, and verify both runner/container and
native turn status; never label the agent cancelled on a UI-only stop.

No run was retried after a possible dispatch. The synthetic Case A run was
left `running` in the disposable fake runner until teardown; no real agent
or external side effect existed. The browser request capture filter produced
no matching request entries, so this report makes no claim about the exact
Langflow frontend endpoint used by Stop. The causal evidence is the
confirmed visible click followed by the same runner journal's zero cancels.
