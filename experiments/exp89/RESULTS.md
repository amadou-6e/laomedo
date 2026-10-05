# EXP-89 results: Langflow Playground Stop

This is a zero-model-turn, local-only probe of pinned Langflow 1.12.3 and
the committed Laomedo Codex component. The protocol and three amendments
were committed before their respective runs. The checked-in
[`observation.json`](observation.json) is a **derived, hand-written summary**.
The machine-written case outputs and complete 11-line fake-runner journal
are committed unchanged under [`evidence/`](evidence/). The probe and fake
runner are committed so the capture can be repeated in a fresh disposable
setup. The synthetic `api-token`, browser profile and Langflow volume are
not published. We inspected every committed evidence file for credentials,
personal paths and non-synthetic task text before adding it.

| Machine-written file | SHA-256 of committed bytes |
| --- | --- |
| [`case-a.json`](evidence/case-a.json) | `24baf9d36276f01b7068e5832ed57f14f73dcae8b916d69d6b36a69cad597abe` |
| [`case-b.json`](evidence/case-b.json) | `4757f687a65192ad873609c7cfd6edf175a698a998543a2f8f53c246b92c5d1c` |
| [`case-control.json`](evidence/case-control.json) | `093f29e3427417970c38fe9c3aa8df2a10d4b7d6e49e2a9f2ec8bc2222df7b9e` |
| [`case-b-setup-failure.json`](evidence/case-b-setup-failure.json) | `a242cd27ce7d75869feec0fafae2a5e54a85c92d1ff1daa1c792abf27f2a5182` |
| [`journal.jsonl`](evidence/journal.jsonl) | `9902f3058cfaac0e3cc8cd146795001fdc554a130724d7dc2934c3288eecf31c` |

The test checks these hashes and reconstructs the summary's key counts and
ordering from the machine files. Screenshots remain local-only optional
context; neither the finding nor the test depends on them.

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

**Why the cancel did not arrive is unknown.** The probe did not observe a
backend-to-component cancellation hook, and its browser request filter
captured no matching endpoint path. Langflow may not have signalled the
component, or may have aborted it before the delayed `start` acknowledgement
returned a native run ID to forward. The current component shields its
blocking HTTP task, but this evidence does not distinguish those two paths.
Langflow's own job status is not a substitute for a native cancel
acknowledgement. Q11 remains open. The next implementation must correlate
UI Stop to the bound runner run (including a still-pending acknowledgement),
issue native cancel, and verify runner/container and native turn status;
never label the agent cancelled on a UI-only stop.

No run was retried after a possible dispatch. The synthetic Case A run was
left `running` in the disposable fake runner until teardown; no real agent
or external side effect existed. The browser request capture filter produced
no matching request entries, so this report makes no claim about the exact
Langflow frontend endpoint used by Stop. The observed boundary is the
confirmed visible click followed by zero cancels in the same runner journal;
it does not establish the missing link's location inside Langflow or the
component.
