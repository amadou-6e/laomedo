# Docker runtime adoption

This is the migration record for Laomedo issues #196–202. The first local trial replaces normal, non-split Codex image/version preflight
with the merged `py-docker` runtime. It is stacked on provider-neutral PR #211
head 8ff5a27; fetched develop remains 6069ac9. The visible checkout is kept
unchanged. The optional `runner` extra pins the local-trial jobs feature from
py-docker PR #11 before PyPI; that package PR remains unmerged.
this trial is not ready to merge into develop until the published dependency is
hash-pinned and the owner reviews the working graph.

## Ownership

The general `py-docker` distribution imports as `py_docker` and uses the official
Docker SDK. Laomedo retains provider authorization, image and CLI-version pins,
mount policy, configuration hashes, credential selection/mirroring, independent
lease supervision, publication verification and descriptive error presentation.
The runtime must not acquire application credentials or decide whether a graph
operation is authorized. Database drivers are a separate package dependency.

Pin the adopted version and artifact hashes in the lockfile. Review runtime
upgrades as changes to Laomedo's container security boundary. Stage-worker imports
and the standard-library Git credential helper must remain independent of the
runtime package. Verify the installed wheel, supported Python versions, Pydantic
ranges and pinned Langflow stage before adoption.

## Migration slices

| Issue | Existing owners | Runtime surface and remaining requirement |
| --- | --- | --- |
| #196 connection/readiness | host/runner/prerequisites.py, provider environment helpers | Client and ResolvedConnection; retain installation-vs-stopped-vs-unknown distinctions and resolve one endpoint for SDK and remaining CLI calls. |
| #197 image/CLI checks | agents/providers/codex/runner.py, provider containers | Images.resolve plus restricted credential-free verification container; exact expected image ID and native CLI version remain Laomedo policy. |
| #198 volumes/login copy | agents/runtime/utils.py, host/credentials/claude/utils.py | Volumes inspection/creation receipts; preserve existing named-volume labels and local-only login restrictions. Unique-volume helper alone does not migrate existing fixed auth volumes. |
| #199 launch | provider/runtime launch helpers, work_graph/docker_stage.py, publication bundle stage | ContainerSpec, reserve/create/reconcile and launch readback; compare every existing launch option before switching. No implicit pulls/builds or force replacement. |
| #200 interactive protocol | agents/providers/codex/servers.py, provider consumers | Execution.attach binary frames and stdin; prove real agent JSON-RPC, activity, cancellation and shutdown parity. SDK socket closure is not container termination; stdin half-close is not guaranteed. |
| #201 exec/export | command workers, publication bundle/stage.py and verified/git.py | Execution.run supports bounded binary output; archive streaming and a total end-to-end deadline are not supplied by the first prerelease. Keep the current verified export until those contracts are implemented and reviewed. |
| #202 cleanup/supervision | host/leases and publication/bundle/ownership.py | Exact immutable-ID removal and receipts; preserve absent/owned/conflict/unknown results, name replacement checks, ownership locks and independent supervisor lifetime. Never prune by prefix or port. |

The first prerelease has per-request API timeouts and a separate stream deadline.
It is not a substitute for an existing total execution deadline. Closing a stream
on timeout leaves the remote outcome uncertain until inspected and reconciled.
Generic Docker volume deletion is not exposed because volumes lack immutable IDs;
Laomedo must retain its own serialized named-volume lifecycle where required.

## Evidence and adoption gates

The library has credential-free local Windows named-pipe and Unix-socket checks.
These establish library behavior only. Internal fault-injection checks establish
recovery logic, not a real daemon failure or a working agent graph. The local trial records the merged Git revision and built-wheel hash. Runtime CI,
reviewed release artifacts and PyPI name/publisher acceptance precede production
dependency locking; each migration then needs its own affected checks and real agent path.

All existing public error codes and actual UI recovery controls stay intact.
Explicitly cover new producer paths in the shared error catalogue guard. A Docker
SDK failure cannot turn an unknown remote outcome into absence or justify a blind
graph retry. Docker stopped, missing and runner-offline states must keep their
distinct recovery actions from the local runner recovery contract.

The SDK owns Docker HTTP transport. The separate implementation-wide HTTPX issue
#203 concerns first-party HTTP clients; it must not monkeypatch Docker SDK internals.

Do not merge Laomedo into develop until the owner reviews the real working graph
and approves. Library CI or a package reviewer verdict does not satisfy that gate.


## First local slice: normal Codex preflight

The generic one-shot lifecycle is now delegated to `client.jobs.run` and
`client.jobs.recover`. Laomedo no longer implements private receipt writing,
reconciliation, frame collection, exit waiting or cleanup for this probe.
It retains only the image/version authorization, hardened probe policy, state
path, endpoint snapshot and mapping to the existing descriptive error codes.
Generic fault controls live in py-docker; Laomedo's controls guard delegation and
policy. A native receipt lock prevents another caller from recovering a live job.
The empty sibling `.lock` file is normal and must not be deleted during use.

The host-only `runner` extra loads py-docker lazily. Core Laomedo, Langflow
components and stage-worker imports do not require the Docker SDK. Split Codex,
Claude, OpenCode, host readiness classification, login mirroring, volumes,
publication/export and independent lease supervision retain their existing paths.

One scoped Client receives the exact host environment snapshot and explicit
15-second request settings. PY_DOCKER_* endpoint overrides are deliberately not
adopted. Ambiguous DOCKER_HOST/DOCKER_CONTEXT, remote and TLS configurations now
fail closed for this local trial. Image inspection checks the host pin; creation
uses that immutable ID, never the mutable tag. The real codex --version probe
has no volumes or login, runs as 10001:10001 with no networking, no capabilities
and no-new-privileges. Read-only rootfs, 128 processes and 1g memory intentionally
tighten the previous probe and require real-image verification.

Attach happens before start; combined binary output is limited to 64 KiB and a
20-second stream lifetime. Exit-status wait is bounded separately to 20 seconds.
These are per-operation limits, not the former single 20-second process deadline.
The private runner state retains a canonical ownership receipt before create;
unknown create outcomes retain it and block another probe until exact cleanup
can be confirmed. Cleanup failure takes precedence over version/pin errors.

The remaining normal-mode CLI volume check, launch and fallback cleanup receive
the same snapshot pinned with DOCKER_HOST and without DOCKER_CONTEXT. Independent
lease cleanup remains on its existing host CLI configuration. Therefore changing
Docker host/context configuration while a runner or lease service is alive is
unsupported; restart/reconcile services first. This pre-existing lease risk is
not claimed fixed by the trial and blocks general endpoint migration (#196/#202).

Error mapping uses existing catalogue entries: image pin mismatch becomes
docker_image_digest_changed; nonzero/invalid UTF-8/version mismatch becomes
unsupported_codex_cli_version; SDK, connection, import and stream failures become
runner_docker_check_unconfirmed; cleanup uncertainty becomes
container_termination_unverified. Missing image is not inferred from a generic
SDK failure. No external exception text, output or receipt labels cross the boundary.

## Local installation and recovery

For a normal Codex host runner, install `python -m pip install -e '.[runner]'`
or `uv sync --extra runner` in the same environment used by
`python -m laomedo.agents.providers.codex.cli`. A managed launcher must point to
that environment; installing into the app's different Python does not update it.
The constructor checks the optional runtime before starting Docker work, for
both manual and managed launchers. Its host startup log distinguishes a missing
runner extra from rejected ambiguous/TLS/remote endpoint settings using fixed
diagnostics, without logging environment values or raw external exceptions.
The shared public code remains runner_docker_check_unconfirmed.

If startup reports container_termination_unverified, stop that runner and retain
`<runner-state>/docker-preflight-receipt.json`. This is private ownership data;
do not copy its labels into a graph, issue, transcript or shared log. A later
startup automatically reconciles an observed matching container and removes
only its immutable ID. A corrupt receipt, conflicting resource, unknown daemon
response or absent never-observed create leaves the receipt in place and blocks
another probe. Even failure to delete the receipt after container removal is
reported conservatively as cleanup-unverified.

For a never-observed reservation, immediate absence is insufficient: an old
daemon request might still complete. Do not simply delete the receipt to retry.
Keep the original host/context unchanged, stop the original runner/client, and
resolve the original daemon's outstanding create request first. If that cannot
be established, restart the local Docker engine at a suitable time, after
reconciling other active local work. Once the old request cannot execute, inspect
the saved name and ownership label privately on that same endpoint. Remove only
a matching owned immutable ID if present; a conflict requires investigation.
Only after confirmed absence and no outstanding create may you remove the saved
receipt and start the runner again. There is no automatic timed-absence shortcut
and no new graph retry or model request is needed for this recovery.

## Local trial evidence limits

The installed local image is sha256:73ad6bbdfa6a8c14ecb50cf4276c013184b0befa75bb7facdab38977e37bd738,
not the checked-in sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239.
The trial confirms the default pin is refused, then uses the existing trusted-host
image_id override. This is local integration evidence for that explicitly selected
image, whose build provenance is not established here; it does not validate the
checked-in image or approve changing its pin. The local wheel hash, merged source
revision, installed module origin and module-byte comparison are retained in the
ignored trial evidence. PyPI publication, hash-pinned production adoption and
owner graph review remain separate pending steps.
