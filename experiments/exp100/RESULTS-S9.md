# S9 synthetic literal-command controls

One approved capture at `0c72ed2c83bca10805d9f532dfb369f82920ee2d` under
Protocol09 (`ae1670a`) and Amendment06 (`acf3322`). The matrix is the frozen
test source, not an independently captured per-case provider comparison.
Eleven synthetic controls passed, zero failed/skipped, exit 0. No real provider,
container or model call. No production installation or native gh parity.

- [Machine observation](CLI-S9-OBSERVATION.json), SHA-256
  `4e9262344fed6db233989cb6f943f953e9be35f12c8e3345b8db722a117a0d92`.
- [Raw Node TAP output](CLI-S9-TESTS.tap), SHA-256
  `c751cb413c8de677394fd6899f86bb419e3774780c755d2f054ff20b0c92da2a`.
- Adapter SHA-256 `dde338ad04049c9dbe4922d2df5ec4518fb6e9423ec2f804bd7524f6f2fe48f7`;
  test SHA-256 `83ab1d69f954dc399f19b32900cfd8bbb680faea82886b7dc6872275457221a5`.

Original files are preserved byte-for-byte; matching committed hashes checked
by the coordinator. A separate coordinator `node --version` immediately after
capture returned v20.11.1; version is not a field in the machine observation.

The frozen assertions compare requests for bound PR view, create and edit,
Actions listing and same-repository GET API syntax; preserve CRLF/Unicode/BOM
body content, reject oversized input, empty `--repo`/duplicate/unsupported flags and
wrong targets, keep explicit effect IDs across unknown results, and distinguish
denied from unknown exits. Tests inject mediator replies; repeated-unknown edit
conflict is simulated, not an integrated SQLite/GitHub execution. The ambient
GH_TOKEN test shows parsing is insensitive to a canary, not an independent
filesystem/process credential audit.

## Explicit gaps

Adapter is experimental and not mounted on production agents. Native gh output,
title-only/body-only edits, interactive forms, presentation flags and paging,
aliases/extensions/token export, GraphQL, arbitrary REST writes and unreviewed
issue creation are visibly unsupported. No fetch or push CLI syntax is added;
existing exact-commit JSON push is separate evidence. Body/stdin bounds are
source-reviewed; the capture tests actual files, not oversized stdin. Repeated
invocation is never an automatic retry; earlier unknown effects stay unknown.
Production provider-error fidelity, durable replay reconciliation, full CLI
capability parity and the composed authority/lease/task path remain open.

No launch/timeout failure occurred. Such a capture failure would consume its
claim without a JSON observation in this version; retain failure evidence and
use a new frozen identity, never run this identity again. #100/#104/#105 remain
open; this capture does not accept their broader requirements.
