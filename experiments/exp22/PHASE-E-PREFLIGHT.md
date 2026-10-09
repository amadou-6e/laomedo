# Phase E: disposable UI and fake-runner gates

The first disposable UI check opened Playground and imported the five-node
flow with the real runner ready, submitting **zero** model turns. Its result is
private at `%LOCALAPPDATA%/Laomedo/exp22-phase-e-preflight-02/` and recorded
`no_model_preflight_passed`. A later attempt to require the installed custom
component catalog timed out, then reported `component_absent`. That additional
catalog condition was withdrawn. The saved flow embeds the component source,
so catalog presence would be an unreliable gate for this route. Those failed
preflights did not click Send or change the turn ledger.

The stronger no-model gate ran the exact saved flow through the disposable
Langflow UI with a fake runner and a browser click on visible Playground Stop.
It observed exactly one start, one lookup and one cancel for the same fake run,
with zero late effects. The browser result did not contain the fake runner
token. Both the UI container and fake-runner process were absent at teardown.
Private state: `%LOCALAPPDATA%/Laomedo/exp22-phase-e-fake-01/`.

| Private sanitized artifact | SHA-256 |
| --- | --- |
| `sanitized.json` | `daccc09f0a46a94887d811c50c0d46101288303518cf186f522afe61a836a093` |
| `teardown.json` | `e9dfbaed41efca2752c3df2f551899796c1b08377ea34f3c61e782990d6b8f61` |

These gates prove disposable-server readiness and visible Stop propagation to a
fake runner. They do not show native Codex interruption or a durable trace
join. The shared ledger remains **4/12** before a Phase E live submission.
