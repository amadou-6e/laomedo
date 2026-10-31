# Skill source discovery

This feature discovers admitted local or HTTPS repository sources, caches choices
and imports exact immutable skill bytes. Source reads do not execute skill content,
advance canonical latest or grant editing authority.

## Concerns and object nomenclature

| Concern | Owner | Interface vocabulary |
| --- | --- | --- |
| Discovery, cached choices and registry imports | `service.py` | `SkillSources`: discover, revisions, resolve |
| Git cache, refs and blobs | `repository.py` | `GitSkillSource`: repository, entries, read_blob |
| Uncertain clone staging lifetime | `staging.py` | `SkillSourceStagingDirectory`: preserve, cleanup |
| Allowed local roots and file reads | `local.py` | `LocalSkillSource`: admit, discover, read |
| Bundle byte/path admission | `bundle.py` | validate_bundle, validate_bundle_path |
| Naming and excluded paths | `utils.py` | skill_name, excluded_parts |
| Canonical admitted values | `models.py` | AdmittedSkillSource, SkillSourceChoice, SkillRepositoryRef, SkillRepositoryState, PendingSkillImport |
| Fixed exclusions and limits | `settings.py` | Source policy; no environment or HTTP flag weakens it |
| Stable failure category | `errors.py` | SourceError; public codes exclude credentials, paths, parser text and Git stderr |
| Application transport | [../interface/sources/](../interface/sources/README.md) | Client, handler, server, settings and explicit startup |

Source denotes an admitted read capability. Sources coordinates choices from
those capabilities. Ref identifies a named Git revision and its commit; State
groups a cache directory and refs; Choice carries display/name/path fields;
Import groups collected bytes and provenance awaiting validation. Services compose
the registry and shared Git runner. Independent helpers use function-only modules.

## Method vocabulary

| Object / method | Responsibility |
| --- | --- |
| `SkillSources.discover(source)` | Admit a source, merge bounded discovered choices and atomically replace the index |
| `SkillSources.revisions(source, choice)` | Collect exact bytes, enforce option limits before registry effects and cache immutable choices |
| `SkillSources.resolve(source, choice, revision)` | Resolve a previously offered immutable reference and verify registry bytes |
| `SkillSources._source`, `_register`, `_save` | Admit source kind, publish verified bytes/provenance and replace index state |
| `GitSkillSource.repository(source, refresh=False, *, deadline)` | Clone/fetch owned cache and capture bounded refs through GitCommandRunner |
| `GitSkillSource.entries(repository, commit, deadline)` | Decode tree metadata and apply path/entry exclusions |
| `GitSkillSource.read_blob(repository, entry, deadline)` | Admit blob mode and enforce byte limits before reading |
| `GitSkillSource._run`, `_check_cache_budget` | Translate process observations and enforce cache accounting |
| `LocalSkillSource.admit(path, require_exists=True)` | Enforce allowed roots, link/reparse policy and post-admission path resolution |
| `LocalSkillSource.discover(root, deadline)` | Find bounded skill roots without executing content or reading unrelated files |
| `LocalSkillSource.read(folder, deadline)` | Return a verified byte inventory, or the missing-SKILL.md outcome |
| `SkillSourceChoice.for_folder`, `for_registry`, `to_record` | Construct and project the choice's wire fields |
| `SkillSourceStagingDirectory.preserve`, `cleanup` | Retain staging on cleanup uncertainty; otherwise use TemporaryDirectory cleanup |

Other models carry admitted values through Pydantic construction. Persisted cache
dictionaries have independent readers; they are not coerced into a new-write schema.
Registry owns immutable content. Shared Git owns native execution, environment,
protocol and process cleanup. Source paths, admission, labels, cache accounting and
index/provenance writes belong here. Callers import defining symbols directly.

## Execution and persistence

Production uses ISOLATED_HTTPS_READ_ONLY. Its environment allowlist is PATH,
SYSTEMROOT, WINDIR, SYSTEMDRIVE, COMSPEC, PATHEXT, TEMP and TMP, preserving key
spelling. It disables system/global Git config, interactive prompts and askpass,
clears credential helpers, refuses redirects and permits only HTTPS. Host HOME,
credential, proxy and provider variables are excluded. Tokens never enter argv
or configuration. Native cwd is distinct from the `-C` repository argument.

The trusted constructor-only `repository_provider` test capability selects an
isolated file-read profile. HTTP cannot enable it. Production rejects credentials,
extra environment/configuration and protocol/hook overrides.

Git stdout is spooled. Active output/time/cache breaches produce
`repository_limit_exceeded`; a nonzero exit or oversized final output produces
`repository_access_unavailable`. Commands have a 45-second timeout within one
60-second discovery/revisions deadline, polled every 50ms. That operation deadline
is passed across reads rather than reset per command. Cache budget is 128 MiB;
ref, entry, file, bundle, depth and option caps are enforced before publication.

Source cleanup shares one five-second deadline across tree termination, pipe
draining and final wait. Budgeted Windows reads launch suspended into an owned
Job Object before resuming; job accounting must confirm zero active processes,
including after root success. WORKSPACE/HOST_TRANSPORT use separate launch and
per-substep cleanup policies. OS overhead means these are not hard real-time bounds.

Unconfirmed termination retains owned clone staging and produces
`repository_cleanup_unverified`. Do not infer the process stopped or advise an
immediate repeat. Retained `clone-*` directories count toward the cache budget and
are not automatically evicted. Removal requires confirming the owned process tree
stopped; the UI provides no staging reconciliation/removal button. Interrupts keep
their identity and arguments plus the cleanup observation, and retain uncertain
staging too. Internal process controls do not establish real browser acceptance.

Index/origin records carry retained choices, labels, sort order and source
provenance. LF/CRLF file bytes have distinct immutable identities. Importing a
source revision does not advance an established canonical latest pointer.

## Application failures

The HTTP client forwards only the exact `repository_cleanup_unverified` category
from an error body of at most 16 KiB. Other categories, malformed/oversized bodies
and read failures map to `source_discovery_failed`. HTTPError responses are always
closed; remote messages and raw payloads are not presented.

`LaomedoSkill.update_build_config` owns discovery-dependent form selections.
Confirmed cleanup uncertainty propagates as its exact safe code to the shared
error catalogue, without generic refresh advice or a successful form response.
A failed form update supplies no replacement template: earlier browser choices
may remain visible. Local clearing alone does not prove a browser transition.
The real cleanup-uncertainty story requires separate acceptance evidence; an
ordinary outage or synthetic error code cannot establish it.
