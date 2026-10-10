# S12 B: managed native delivery and runner-loss check

Machine result: passed. Identity exp104-native-managed-s12-20261010-b is
consumed; never execute it again. Original S12 A remains separate/incomplete.
Amendment54fe106 preceded executableb2042452aab17b1e5a040633053e404a4b194c54.
Exact-source independent pre-run review approved one bounded execution;
CI38036116523 passed both3.10/3.13 before execution. Governing specs:
ea2558e910d640b802b7b197d2a90b8d14e3249c. Post-run review remains pending.

## Original machine evidence

Sanitized original files copied byte-for-byte, not transcribed:

| File | SHA-256 |
| --- | --- |
| native-managed-s12-b-observation.json | e80b5afa08d6077d154807a23ed7f57ab0d7994e47c7700f84faaf26c594bff4 |
| native-managed-s12-b-provider-attempts.jsonl | cee7d437a24955f0d13b5d33a6fd270771b3e4415690dbbd0731a3478d6ae7df |

Journal has original Windows CRLF bytes, preserved by an explicit -text
attribute. Observation uses LF. Private original capture retained; no bearer,
provider token, user path or email is published. Grant IDs are non-secret IDs,
not capabilities. Original files are not rewritten by verification tests.

## Result and limits

Two separate scripted runner fixtures registered through real RunGrantAuthority
and LeaseClient. Production credential-owning host services and bundle verifier
ran as limited interactive per-user Windows scheduled tasks, with exact action
ownership checked. Before/after PID sets matched: host12828/15364,
verifier3112/31160; heartbeat advanced. This is one machine/setup, not recovery
from service failure, Windows logout/job stop, power loss or Linux systemd.

While each container was owned/alive, supported native Git fetch/commit/push
and partial gh create/view ran. Four provider mutations were journaled:
A push, A PR create, B push, B PR create. Four other mediator entries are
fetch/read operations; direct host preflight/readback reads are outside that
journal. This is not four total network requests or complete git/gh parity.

A PR3 head a82bdd8dad29a3c2676a6729a7b8f84b0b52e936;
B PR4 head ed2eeceaee74b6f9702b464b5e58ebbee2cea314, in
ga84jog/laomedo-exp104-disposable-20261007. Exact branches/base/markers/head
readbacks matched. PRs/branches remain for audit; no deletion or merge.

A exact runner tree kill completed at monotonic90866.390; saved revocation
at90871.375 (4.985 seconds). Retained A capability got403/grant_unavailable
at90872.062; provider-attempt count stayed6 before/after the denial and A's
PR title/body stayed unchanged. This denial was controller-side after A loss,
not a surviving agent command. B's grant was live and its PR-create intent
at90872.859 followed the denial. No write was retried automatically.

All six recorded local cleanup checks passed (A/B exact containers, grants,
worker processes, tasks and stages); two stage reports verified absence after
stage cleanup. Persisted runner/stage exact-secret scan inspected103 files,
zero exact token/capability matches. It is not a memory/network exposure scan.

Zero model turns. Trusted lifecycle records and containers were scripted
fixtures, not actual LocalRunner/model execution. No Langflow UI Stop/real-agent
Q11 acceptance, full operation parity, multi-user custody, browser sign-in,
double-service failure or full draft#105/#97 promotion is established.
