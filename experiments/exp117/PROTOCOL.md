# Develop-based #117 integration verification

The user selected finishing #117 and merging after independent approval. Its
former parent #105 is an independently maintained, unapproved mediation draft.
This slice starts from `develop` and carries only the native cancellation fix,
Langflow component/bridge, durable request store and related tests. The former
integrated branch is retained as `archive/117-integrated-fd3118d`; historical
evidence remains pinned to that implementation, not re-labelled as this slice.

Freeze and independently review this protocol and exact source before live
checks. Use unchanged Docker permissions, selected subscription login and pinned
Codex 0.159.2 and Langflow 1.12.3 images. No GitHub grant or mediation service is
provided. Private stores, tokens, native traces and browser state stay outside
Git. Langflow receives only the bridge token, not the runner token or login.

Run the no-model preflight first. Then run two fresh disposable cases, each in
a new empty directory, using the shared 12-entry ledger, initially 8/12:

1. **Pre-thread:** reserve one conservative entry immediately before visible
   Send. Hold the real runner's async acknowledgement so its native worker gate
   stays closed. When one prepared record exists, click visible Stop. Require
   exact bridge and native cancel routes, confirmed terminal cancellation before
   browser closure, and no native thread, event, container or turn-ledger file.
   Release the acknowledgement only after confirmed cancellation, including
   cleanup on failure. Reopen both host binding and Langflow trace after restart.
2. **Active command:** reserve one entry before visible Send. Use `gpt-6-luna`
   at low effort and the unchanged Phase E task. Its content-free auth-file read
   must be denied; a readable result stops the run. Click visible Stop only
   after the long command starts. Require exact bridge/native cancellation,
   native `interrupted`, confirmed runner cancellation, known container absence,
   absent delayed sentinel and preserved partial events. Reopen the exact host
   binding and one linked Langflow trace after restarting disposable Langflow.

Exactly one Send and one native runner start per case; no automatic redispatch.
The pre-thread case is designed to submit zero native model calls, but still
reserves an entry conservatively. At most one actual model turn in this protocol;
timeouts and uncertain submissions count. Do not retry an inconclusive case.

The trace join uses saved-flow UUID and component-reported graph-run ID in a
span. It is corroboration, not editor-graph attestation. Native cancellation and
container absence prove this bounded local stop, not semantic task success,
hosted isolation, timeout safety, production login lifecycle or #93's outage/
real push-credential revocation. Publish sanitized results, hashes and teardown,
preserving all earlier outcomes. No issue state changes are authorized here.
