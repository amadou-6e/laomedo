# No-model attached-client diagnostic, 2026-10-11

Identity: exp93-attached-client-d1-20261011. Single-use; no automatic retry.
Purpose: test a narrower possible explanation of S2, not retrospectively prove
its cause or accept Q11. Source S2 at 5c5d28 used LocalRunner's `docker run --rm -i`
with piped stdin. A harmless stdin-dependent shell fixture substitutes for the
native app-server; it does not establish Codex's EOF behavior.

Before execution pin and review the executable. Use only the already local image
sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78,
--pull=never, --network=none, non-root UID10001, dropped capabilities,
no-new-privileges, memory/pid limits, and NO mounts or credentials. Start one
attached --rm -i container with exact diagnostic name and run/launch labels.
The shell prints READY then reads stdin until EOF. Keep stdin open.

Persist single-use claim before launch. Require READY and independent exact
label-verified ID, or abort and preserve failure. Kill only that subprocess PID
with Windows taskkill /T /F after checking it remains live. Record monotonic
command-ready, kill-start and kill-complete times immediately. Inspect the exact
name/labels at fixed offsets 0,1,5,10 seconds after kill. Unknown/conflict is not
absence. This tests whether CLI loss can accompany auto-removal of this fixture.

Always clean only the exact owned container and original subprocess handle;
record cleanup outcome and commit sanitized machine output. No model turns,
GitHub operations, auth volume, service configuration, runner recovery or
production behavior changes. Whole diagnostic bound120 seconds. No service is
running; absence does not prove service-attributed removal.
