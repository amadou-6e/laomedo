# MCP #280 editor and shutdown evidence, 2026-11-15

Implementation base `feadd5fbccdebbe7bf1d5614c5bad187b9ad975d`, head
`ead50c23865b3d2e19bfb2eab976f3bc5947d062`. No production code changed for these
checks. The existing isolated preview was restarted from this checkout.

## Actual integrated editor

The owner shared the Codex STDIO graph through CoBrowse View & Interact. The
updated CoBrowse extension supported background screenshots, page reads and
clicks; automatic recording was active without gaps. No other shared app was
modified.

The native Actions drawer visibly selected Read Marker and left Unselected Probe
unchecked. Closing it and clicking the Agent's Run control submitted the graph
through the actual editor, without re-entering server configuration. Async start
returned in about 0.7 seconds; the real run completed in about 8.5 seconds. The
returned private marker matched, the selected counter increased from one prior
call to two total, and the unselected counter remained zero. The run manifest had
one tool.

The Activity view showed all three conversation items: the user prompt, one
external MCP call and the correct final answer. Advanced controls expanded and
collapsed without changing values. An initial native output label showed Response
despite persisted Toolset metadata; building settled it to Toolset and execution
worked. No production workaround was added for that presentation.

Actual screenshots remain in ignored local review evidence, not this archive.
Claude opened the Actions and Activity images and returned bounded visual ACCEPT
and supported the editor evidence. It noted a Low usability issue: the Activity
row shows the opaque external identity rather than a human-readable tool name.
This mouse-driven check does not establish keyboard/accessibility or edge-drag
creation coverage.

## Graceful app shutdown

A separate isolated app on port 17883 left the owner's shared preview unchanged.
Only the experiment launcher accepted an explicit private stop-file control. It
set Uvicorn's normal exit flag and observed the actual app lifespan stopping.
No shutdown endpoint or test gate was added to production.

The real Codex run entered the harmless held STDIO tool once. The harness retained
its scoped capability only in memory, requested graceful app shutdown, observed
the app become unavailable, and verified the grant file was removed and the old
forwarding endpoint was unusable. No tool result completed before observation;
later upstream effects are unknown. This establishes app/grant teardown, not a
terminal agent outcome. The retained run still said running when its runner
process exited; cancellation was requested by launcher cleanup.

An earlier harness version incorrectly waited for that stopped runner to persist
a terminal result. Its polling process was stopped after confirming recovery,
and its result is excluded from the passing corrected shutdown audit. Restarting
the isolated runner recovered its first record as interrupted/runner_restarted.
Restarting again also recovered the second record as interrupted/runner_restarted.
The separate preview was then gracefully stopped without another model run.

## Immutable Codex image provenance

`image_provenance.py` used shared DockerRuntime job handling, the exact immutable
image ID and the daemon endpoint recorded by the accepted run. The read-only job
had no networking, credential environment or profile mounts.

Image ID: `sha256:f00c76d680b6399850570c98335701359776f29ec92cdaa9e29dfb1cca569e93`.
All comparisons passed: native-events.patch, LaomedoExtension.ts and
LaomedoLaunch.ts matched the image's build checksums; the installed index.mjs
matched the recorded built adapter digest. This is Codex image provenance, not a
claim about every provider image or historical loaded Python memory.

## Remaining limits

Claude independently reviewed the shutdown and checksum evidence and supports
those bounded claims. It did not inspect the Docker job's sandbox defaults;
those defaults were inspected separately by the implementer. The evidence does
not claim coverage of all images or loaded historical Python memory.

## Status and cancel with an unavailable upstream

`control_case.py` used the actual native graph/session API for all three
providers, reusing harmless HTTP server registrations whose processes had ended.
A counted HTTP listener on that same owned endpoint returned 503. Status and
cancel each returned the existing completed run reference with zero upstream
attempts. No new agent run was created.

As a comparison, running that same native MCP component's direct Response
operation against the unavailable endpoint failed with HTTP 500 and made three
upstream attempts for each provider. This comparison performs native MCP
discovery/direct-tool setup, not an agent inference. The earlier standalone
Toolset-only comparison opened no connection and is not used as a falsifier.
The harness also corrected PowerShell UTF-16 log decoding and requested explicit
component output before asserting the returned reference. Failed harness
iterations do not establish acceptance.

The local actual deployment uses loopback forwarding exposed to Docker controllers
through host.docker.internal, as exercised by the real tool calls. Other private
interface configurations are not claimed as tested.

New unavailable-upstream control evidence awaits independent review. Two-server
editor rendering, wider privacy/log scopes and specification PR #419 remain
separate acceptance constraints. No merge or issue closure is authorized.
