# S10: native command wiring, no-model/local-provider fixtures

Issue #100 / #104. User selected normal git/gh commands; governing recorded
choice is specs `18d4078` (draft branch), canonical design at `308f8f7`.
Freeze before implementation and any acceptance execution. No real GitHub
credential/provider call or model turn is authorized by this protocol.

Install reviewed partial gh adapter on the mediated agent PATH, not host PATH.
Git remains native; origin uses a `laomedo::OWNER/REPO` remote helper. The
helper advertises only implemented push/fetch/option commands. It never uses
native HTTPS or an ambient gh/GCM login as a fallback. A denied grant means
denial, not a new identity or different transport.

Push batches support one run-branch, non-forced ref. Source is HEAD or the
matching local branch. Bundle freeze/verification precedes the same exact
commit push. Record a deterministic commit-bound stage/effect identity in
agent Git metadata before requesting an effect; uncertainty never causes a
new identity. Concurrent local handoff is refused. Existing host first-push
absent-ref CAS remains; second-push support is a visible gap until a trusted
confirmed predecessor/fast-forward check is added. Do not report parity here.

Fetch uses a separately granted read lane, scoped to main/run branch, host
selected repository/credential. Advertised ref/SHA must match returned objects.
Host performs isolated, time-bounded Git reads, verifies ref/hash and fsck,
returns at most a 256 KiB bundle (larger snapshots fail explicitly), and checks
grant again before delivery. This bounds returned bundle bytes, not total
downloaded object disk usage; no such claim is allowed. Remote metadata and
object acquisition never run inside the agent with a reusable credential.

Local controls: command parsing/unknown replay/unsupported flags; readonly
mounts and selected repo/branch; exact helper protocol; real native Git push
and fetch against injected local provider fixtures; no credential in helper
environment; different repo/ref/force/multi-ref rejected; exact read and
revocation codes; package resource availability and shell LF materialization.
Implementation/tests may run while developing. Separately freeze exact
one-shot capture and obtain independent pre-run review before campaign evidence.
No service installation, live provider mutation or model follows automatically.
