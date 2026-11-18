# Activity presentation acceptance

Initial production changes: Laomedo issue295 / PR298, base fc0cfa3ad, tested
head8bd1279db. Specification: specs PR433, head06db633. Additional concurrent
activity refinements later landed on fix/295; those are outside this evidence.
Independent review is pending; the reviewer returned only a quota refusal.

The production build passed. GraphAgents38 tests and the separate current
per-node activity3 tests passed. A local setup initially placed the latter suite
in the wrong folder; correcting placement resolved that import failure. Combined
with the assistant suites,73 tests passed at activity8bd1279/sidebar4ea6234eb.

`ActivityPreview.tsx` renders the real GraphAgents component against an existing
real retained Codex run. `build.mjs` builds a focused read-only entrypoint using
the existing pinned upstream frontend configuration. `preview.py` serves it on
loopback and forwards GET requests to the existing app, preserving ordinary
authentication/origin checks. It rejects mutations and does not export or log
credentials, copy sessions or disable authentication. Opening sends no inference.

CoBrowse verified the retained answer, expanded search, real filtering from two
messages to one, close clearing back to two, both search controls, and centered
empty telemetry. Screenshots stay ignored. The optional fake ghost cards were
not selected. The original full-app proxy prototype had auto-login/bootstrap
errors and is not claimed as full-app acceptance; the focused entrypoint avoids
that unrelated bootstrap entirely. Fresh headless contexts without a login are
not evidence of a successful authenticated check (`check.mjs` is an earlier
unsuccessful full-app probe). No fixture is represented as real retained data.


## Current-head acceptance, 2026-11-18

The owner reserved port17920 for another agent. All subsequent checks use our
own app55753; the read-only proxy now forwards only to that app. No later checks
or restarts touch17920. Its profile login failure is not an acceptance result.

At implementation2b7624754 and spec0bb53b5,39 activity tests pass; spec validation
reports1845 files, zero errors and the existing large-file warning. Node22 full
production build passes. The initial review covered ff6a3e195/06db633 and found
count wording and specification drift. Both corrections are pushed; focused
implementation/specification/visual recheck is pending.

`own-graph.py` creates a separate saved native Codex graph in our app. Its first
HTTP execution failed before inference because the app had no runner auth-file
setting. `native-graph.py` executes that saved graph through actual Graph.arun
and an isolated authenticated RunnerServer, preserving the saved flow's actual
owner identity and writing normal activity to our own app store. It borrows only
the previously authorized access token through the existing scoped helper.
One real prompt ran pwd and returned Activity preview verified. Native resource
cleanup is provider-owned; the temporary HTTP server is closed in finally.
No DB remapping, synthetic receipts, copied browser session or auth bypass.

`current-app.mjs` inspects the full app and actual current production component:
three items (user + command + answer), search focus, Escape clearing, narrow
layout and selected turn. Screenshots remain private/ignored. Browser checks
submit no inference; the separate native harness does submit the one authorized
prompt. The integrated Laomedo tab is Activity review - isolated preview on55753.
The standalone graph's configured runner is offline after its isolated harness
ends; these checks do not claim the app runner-start configuration is validated.

Do not print raw browser errors near password inputs. The normal-login helper
reads the configured PIN only when necessary and emits a generic failure.

Final focused Claude recheck: APPROVE implementation2b7624754, spec0bb53b5 and current real images. L1-L3 closed; L4 optional. Notice and filtered-count image states not claimed. No merge.
