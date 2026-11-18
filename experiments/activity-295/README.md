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

## Real longer-conversation inspection, 2026-11-18

At owner request, `native-long-chat.py` ran the existing saved graph through the
real Codex runner using a separate read-only task-board workspace. It creates
three harmless exercise source files before execution; the agent is asked not
to edit them, access credentials, use the network, or delegate. Normal graph
activity capture belongs to the isolated app on 55753; the current production
UI is served through the stable 17921 preview without synthetic middleware.

Execution `a4155c56-cf64-45de-ba52-25da08d3447d` completed in 35.5 seconds.
CoBrowse verified 10 retained conversation/tool items, 46,213 input tokens,
27,008 cached input, 942 output, zero reported reasoning and the displayed
$0.002662 API-equivalent estimate (not an actual invoice). Five usage
observations are charted. The real final answer includes a table and TypeScript
code. One requested jq pipeline found jq unavailable; the model disclosed this
and used the already-read source to report counts. The task still completed.

This real run captured zero OpenTelemetry records. This does not establish
live native tracing acceptance. The earlier synthetic chat and spans remain
separate visual samples on exp and are no longer served in the preview.
The activity implementation at 2fcce7cda remains fully unreviewed for the newer
hierarchy and table changes; reviewer pending. No raw private runtime data or
credentials are archived here.

## Native telemetry follow-up

The initial longer-run harness did not set `LAOMEDO_RUNNER_OTEL=1`; native
collector startup is opt-in. The harness now enables that existing setting
before launching the task, without changing production defaults or past runs.
A second real run, execution `b563a7e2-203a-4fd4-9e34-bb79b182ebed`, completed
with native OTLP collection: 6,687 receipt lines and 6,687 normalized telemetry
records in the saved activity projection. Coverage reports observed records
with exporter flush completeness unverified. No synthetic spans were injected.

Metadata-only inspection confirmed the attempt's otel range 0..6687 and terminal
status complete. The activity store retains a projection snapshot, so counting
only top-level otel/record methods in its receipt table would incorrectly report
zero; the telemetry list belongs to that normalized projection.
