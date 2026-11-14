# Codex native evidence

`rollout_export.py` retains explicitly selected native Codex evidence. Its
command-line entrypoint is an existing external interface, independent of normal
Activity ingestion. `export_rollout(state, run_id)` validates the recorded thread,
profile, immutable image and `container_ownership.docker_endpoint` before access.
Missing bindings are refused; no default daemon, volume or image is substituted.

The exporter runs bounded find/stat/cat jobs through `DockerRuntime` on that
recorded daemon. Each job mounts only the recorded profile read-only, disables
networking, runs as the existing non-root user and retains its own recovery
receipt until cleanup is confirmed. Images and volumes must already exist;
export never builds, pulls or creates a profile. Previous export receipts are
reconciled before dispatch. Cleanup uncertainty retains the receipt and refuses
publication. Valid JSONL is published atomically only after exact thread/path
and size checks. No raw Docker output is included in error messages.

Provider `projection.py` interprets native evidence behind `read_activity`.
Shared application projection consumes only the retained common display; old
native-only Activity databases are unsupported. This leaf defines no additional
interface, projector or cost engine. Unknown or partial usage remains unknown
or partial.
