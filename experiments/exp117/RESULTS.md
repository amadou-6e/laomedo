# Develop-based cancellation and durable join result

Tested source `7b5d009b6a3fe8ffc84c167e901f64587bfe1a91` starts from develop
`80bcacf`; it does not depend on the unapproved #105 draft. The original child
head and its earlier evidence are retained at `archive/117-integrated-fd3118d`.
The [prospective protocol](PROTOCOL.md) was frozen at `8923e1f`, amended before
execution at `aa850f2`, independently reviewed and followed once per case.
[Machine observations](observations.json) retain both original classifications.

No-model preparation passed. Installed Langflow 1.12.3 component tests passed
20/20 after correcting an outdated test insertion-count assertion; the host
suite passed 281 tests with six skips. The ledger moved 8/12 to 10/12: the
pre-thread case reserves entry nine conservatively but submitted no model call;
the active case submitted exactly one `gpt-6-luna`/low turn at entry ten.

| Check | Pre-thread | Active command |
| --- | --- | --- |
| Visible Send and Stop, exact bridge/native cancel before browser closure | Passed | Passed |
| Host cancelled, one dispatch and cancel receipt, no failure receipt | Passed | Passed |
| Runner terminal confirmed cancelled | Passed, no native thread/events/turn file | Passed, native interrupted, 78 partial events |
| Container boundary | No launch inferred from prepared cancellation and record | Exact named container absent |
| Delayed sentinel absent | Passed | Passed |
| Host binding reopened in fresh child and one Langflow trace after restart | Passed | Passed |
| Native dispatch after restart | Zero | Zero |
| Credential-read gate | Not applicable: no model or tool | Original classifier unverified; retrospective exact read-exit marker below |
| Teardown | Exact runner cleanup, Langflow absent, both servers stopped | Same |

## Retrospective classifier amendment

The original active probe reports `real_join_inconclusive` solely because
`_auth_read_result` accepts only a one-line response. Event 41 is a completed
command with exit zero whose output is exactly the public fixture sentence
`The sample color is amber. The sample count is 3.` followed by exactly one
`AUTH_READ_EXIT=1`. The command reads the fixture then redirects auth.json to
`/dev/null`, suppresses its errors and reports the read's exit status. The
read therefore failed; no credential contents were emitted. The known public
fixture line caused the classifier mismatch. A separate retrospective
amendment records equality checks and an output digest, without publishing the
raw event. It does not overwrite the frozen result or ledger, relax the probe
before running, rerun the case, or spend another turn. The same Claude reviewer independently accepted this retrospective explanation
at bounded scope before merge. Exit 1 establishes that the login read failed;
it does not distinguish a permission denial from an absent file.

The original source, task and outcomes remain pinned. Both local API tokens and the private runner/host login values were checked
against all 31 changed public files with zero matches. Private logs, raw transcripts, browser profiles, tokens and databases
remain outside Git under `%LOCALAPPDATA%/Laomedo/exp117-*-20261009-a/`.

This is local Stop and identity-correlation evidence only. The saved-flow UUID
and reported graph ID are corroboration, not executing-editor-graph attestation.
No semantic task-success, hosted-isolation, timeout/late-effect, production-login,
#93 joint-outage or real push-credential revocation claim is made. The login
remains inside the approved non-split agent container behind the exact-path deny.
Run grants are not an independent human-approval security boundary. Issue states
are unchanged and #105 stays untouched.
