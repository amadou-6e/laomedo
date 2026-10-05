# EXP-10: long-call timeout and late effects

This is a zero-model, four-call synthetic observation under the
[prospectively committed protocol](PROTOCOL.md) (`e4f4685`) and a separate
[compact-capture replication amendment](AMENDMENT-01.md) (`8ceb50d`). The source base
was Laomedo `a365238`; Langflow was pinned to version 1.12.3 and image
`sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
The disposable backend used a localhost-only published port, an in-container
loopback mock runner, a temporary auto-login account and a named volume. No
agent model or external integration was called. The container and volume were
removed after the observation.

| Boundary | Configured limit | Caller result | Synthetic effect |
| --- | ---: | --- | --- |
| Control | HTTP 8 s / caller 15 s | 200 after 1.063 s | Before response |
| Outer client | caller 1 s / HTTP 8 s | `TimeoutError` after 1.000 s | About 3.1 s **after** caller timeout |
| Component HTTP | HTTP 2 s / caller 15 s | 500 after 5.282 s; says remote execution may still be active | Before the 500 response; runner response was disconnected |
| Langflow v2 synchronous server | server 3 s / HTTP 8 s / caller 15 s | 408 `EXECUTION_TIMEOUT` after 3.031 s, with job ID | About 3.1 s **after** the 408 response |

The [sanitized observation](observation.json) includes exact UTC entry/effect
timestamps, caller start and elapsed time, response category and the v2 job ID.
One runner request and one effect were observed in each case. The native
component's asynchronous shield and Langflow graph scheduling are not proof
of remote cancellation. In particular, HTTP 408 and outer-client timeout
**did not stop** the synthetic side effect. The v1 component error was
effect-aware in wording, but returned only after the delayed effect; a
configured 2-second socket timeout was not a 2-second whole-graph response
bound in this setup.

The first two launch attempts failed **before any case was dispatched**:
the fresh Docker volume was root-owned while the image runs as UID 1000, then
the copied example flow's fixed ID collided in Langflow. The fixture now
initializes the volume for UID 1000 and removes the copied export ID before
creating flows. Neither correction changed the frozen cases or limits.
The first valid run at `dee05c2` produced a verbose response that was manually
condensed after capture. The amendment committed before the second run allowed
one new four-call replication; the current compact observation was written
directly by the probe. The first result remains in Git history, not silently
relabelled as the direct-capture replication.

Run `python -m unittest experiments.exp10.test_probe -v` to check the pinned
observation and falsifying mutations. `python -m experiments.exp10.probe
--record` is a **new live run**, not a deterministic replay: it starts one
disposable container, executes four new synthetic calls and overwrites the
observation. Do not run it merely to verify committed evidence.

Limits: the v1 and v2 routes have different timeout mechanisms; a v2 timeout
was not checked through a later job-status query, and no IF-06/07 trace or
Laomedo run-record integration was captured for failed calls. A real Codex
container, network partition, process kill, grant and production UI were not
tested. The first slice still needs an effect-aware run/trace outcome: an
HTTP timeout may mean an external action is continuing, not that it failed or
stopped. EXP-10 measures this hazard; it does not implement the missing policy.
