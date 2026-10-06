# EXP-94 result: Playground Stop reached the bound fake runner

The protocol was frozen at `e28a6ae` before the component, saved flow, fake
runner and browser probe were committed at `0aeb9de`. The late-click control
amendment was committed at `47a7834` before its case. Every dispatched case
ran once with a fresh flow and request ID; none was retried. All four cases
used the cached pinned Langflow 1.12.3 image and a synthetic loopback-only
runner. Model turns: **zero**.

The primary evidence is the byte-identical machine output in [`evidence/`](evidence/).
The probe made these files in ignored private state; they were screened for
credential markers, email addresses and user paths, then copied unchanged.

| File | SHA-256 of source and copied bytes |
| --- | --- |
| `case-a.json` | `7a12bd36b7a64da5530f8ba88e8ed64588d91b2643d54b5e1acf58b950622533` |
| `case-b.json` | `62dd9ea8722a0a67b23c2e2a385cc0603ad060e3581e63518a65c809318fd909` |
| `case-control.json` | `8601db3000bfebcd941b9c31fdff8ad014075d4040fc7d43c3b728e473f6a12e` |
| `case-control_late.json` | `82aa5ea95f7fe966df9a5ed06e5ec24772583b3f3b5b94c9acf80124b6b6d02e` |
| `journal.jsonl` | `0a24849c5badb341fc92c570f9728454f702dceda0c872bbf8560c2ff9ea27f2` |

| Case | Browser action | Exact fake-runner evidence | Result |
| --- | --- | --- | --- |
| A: held `start` acknowledgement | Visible `button-stop` clicked between `ack_held` and `ack_sent` | One POST, one matching read-only request lookup, one cancel for that run before acknowledgement, no synthetic effect | Stop propagated through the pending-acknowledgement path. |
| B: blocking `fresh` | Visible `button-stop` clicked during synthetic wait | One POST, one matching lookup, one cancel for that run, no synthetic effect | Stop propagated through blocking fresh. |
| CONTROL | No click after completion | One POST and effect, no cancel | Baseline only; it did not exercise a late click. |
| CONTROL_LATE | Amendment 01: visible `button-stop` clicked after effect | One POST and effect, zero cancels | A late click did not cancel the completed run. |

The new component uses one durable request ID for both operations, read-only
lookup with the canonical request hash, and only then sends cancel to the
matching run. It does not issue a second start. The test in
`tests/test_exp94_observation.py` re-hashes the machine files and checks
the exact identities, counts and timestamp order. Pinned-Langflow unit tests
also check binding conflict and completed-run refusal.

This is a **synthetic propagation result**, not native-agent cancellation.
The fake runner's cancel handler marks the run cancelled, but the browser
evidence did not separately capture a terminal status payload or real
container teardown. The browser request logger saw only its monitor request,
not Langflow's exact Stop endpoint, so the upstream frontend request path is
still unknown. A 202 from a real runner remains merely `cancel_requested`
until native/container evidence confirms terminal cancellation. Q11 and #22
stay open for a bounded real-agent check and #93 crash/grant safety.
