# EXP-22 Phase D: one-turn pinned Langflow graph cancellation

This protocol uses the fourth and final submission in the user's approved Phase C four-turn ledger. It must be committed and independently reviewed with its probe before the turn. The earlier three entries remain unchanged; a timeout still spends the last turn. The approved private Codex subscription-login copy stays in the runner's non-split profile. No new login copy, real GitHub credential, mediated write, or GitHub write is used.

## Boundary and inputs

- Run the pinned Langflow 1.12.3 image `langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0` with the repository read-only, a new private state directory, and only the runner API token mounted read-only. The real Codex runner uses its existing pinned image and `gpt-6-luna` at low effort, the disposable pilot source and one pinned pilot skill.
- Use the saved five-node `examples/native-codex-node/flow.json` through `Graph.from_payload` in the installed Langflow runtime. The probe may replace only the skill revision, runner port, timeout and Chat Input task. Freeze the resulting graph, prompt, source and skill hashes before dispatch. The flow's agent `fresh` operation sends one async start and waits for terminal status.
- The task attempts a content-free `auth.json` read, stops if readable, then enters an observable 30-second shell command writing a disposable sentinel only after its delay. Do not print credential contents.

## Credential-free gate

Use the same graph with the authenticated fake runner and no provider login. Cancel the Langflow graph after its synthetic wait begins. Require one start, one request-identity lookup, one cancel to that exact run, and no second start or synthetic late effect. Verify the pinned image reaches the intended test runner address and that the sanitized graph output does not contain the runner API token. This gate does not establish general container network isolation. A failed gate forbids the model turn.

## One submitted turn

Start a fresh real local runner with a one-turn internal cap, record its token only in the private state, and pin the source/skill/model/image. Reserve the shared Phase C ledger entry immediately before starting the graph; never reserve a second. Observe the native `commandExecution` start for the 30-second command. Then signal graph cancellation. If the command does not start within 45 seconds, cancel anyway and classify the active-tool check inconclusive. Do not use a direct runner cancel as a substitute for graph cancellation.

Record the graph cancellation signal, runner request ID and early run ID, the component's request lookup and cancel traffic, native `turn/interrupt` or `turn/completed: interrupted`, terminal runner status and `cancel_confirmed`, partial raw-event count/hash, exact Docker container absence and sentinel absence after the original delay. Distinguish a cancel request from confirmed remote cancellation. If any identity is unknown, retain the run as unknown; do not redispatch or reuse another request ID.

The in-process graph cancellation is a test of Langflow component cancellation propagation, not a visible Playground Stop. The separate EXP-94 synthetic browser test covers visible Stop routing but not a real agent. Full UI-to-real-agent composition and a complete cross-store trace join remain separate unless this probe observes them directly.

Private raw events, runner token and login state stay outside Git. Publish only sanitized categories, hashes, timings and a count of the shared ledger, including failure or inconclusive results. No issue closure follows automatically.
