# Skill source discovery

This feature discovers admitted local or HTTPS repository sources, preserves cached
choices and imports exact immutable skill bytes. It never executes skill content,
advances an existing canonical latest pointer or grants edit authorization.
The D2 README contract precedes its implementation; graph and live acceptance
remain separate gates.

## Concerns and defining objects

| Concern | Owner | Object or function vocabulary |
| --- | --- | --- |
| Public discovery, cached choices and registry imports | `service.py` | `SkillSources`: `discover`, `revisions`, `resolve`; no native process launcher |
| Git source cache and blob reads | `repository.py` | `GitSkillSource`: `repository`, `entries`, `read_blob`; compose the shared `GitCommandRunner` |
| Uncertain clone staging lifetime | `staging.py` | `SkillSourceStagingDirectory`: `preserve`, `cleanup`; retain owned staging when process termination is unconfirmed |
| Local-root admission and file reads | `local.py` | `LocalSkillSource`: `admit`, `discover`, `read`; no Git subprocess or registry writes |
| Byte/path admission before import | `bundle.py` | `validate_bundle`, `validate_bundle_path`; function-only |
| Source-specific naming/exclusions | `utils.py` | `skill_name`, `excluded_parts`; function-only |
| Admitted values that travel together | `models.py` | `AdmittedSkillSource`, `SkillSourceChoice`, `SkillRepositoryRef`, `SkillRepositoryState`, `PendingSkillImport` |
| Fixed source exclusions and limits | `settings.py` | Existing fixed policies, with no environment or HTTP flag to weaken them |
| Stable failure category | `errors.py` | `SourceError`; no credential, local path, parser text or Git stderr in public errors |
| App boundary | `skills/interface/sources/` | Existing client, handler, server and trusted startup CLI; URL/token settings stay here |

Source denotes an admitted read/discovery capability, not a generic transport.
Sources coordinates choices from those capabilities. Ref identifies a named Git
revision and its commit; State groups a cached directory and that reference list;
Choice supplies the existing display/name/path fields; Import groups already
collected bytes and provenance pending validation. No empty Base class, source
plugin framework, duplicate registry model or public forwarding facade is needed.

## Method nomenclature

| Object | Methods | Responsibility |
| --- | --- | --- |
| `SkillSources` | `discover(source)` | Admit a source, merge bounded discovered choices and atomically replace the existing index |
| `SkillSources` | `revisions(source, choice)` | Collect candidate exact bytes, enforce option limits before registry effects and cache immutable choices |
| `SkillSources` | `resolve(source, choice, revision)` | Resolve only a previously offered immutable reference; verify registry bytes |
| `SkillSources` | `_source`, `_register`, `_save` | Admit the source kind, publish verified bytes/provenance and replace the index; existing transaction order retained |
| `GitSkillSource` | `repository(source, deadline, refresh=False)` | Clone/fetch the owned cache and capture bounded refs through the shared Git runner |
| `GitSkillSource` | `entries(repository, commit, deadline)` | Decode tree metadata and apply existing source path/entry exclusions |
| `GitSkillSource` | `read_blob(repository, entry, deadline)` | Enforce supported blob mode and existing byte limits before reading |
| `GitSkillSource` | `_run`, `_check_cache_budget` | Translate shared process observations and enforce source-owned cache accounting |
| `LocalSkillSource` | `admit(path, require_exists=True)` | Keep allowed-root, symlink/reparse and post-admission resolution policy together |
| `LocalSkillSource` | `discover(root, deadline)` | Find bounded skill roots and display choices without reading/executing unrelated files |
| `LocalSkillSource` | `read(folder, deadline)` | Return the existing verified byte inventory, or the existing missing-SKILL.md outcome |
| `SkillSourceChoice` | `for_folder`, `for_registry`, `to_record` | Construct fresh choices and preserve existing wire keys/order |
| `SkillSourceStagingDirectory` | `preserve`, `cleanup` | Preserve owned clone staging only on cleanup uncertainty; otherwise retain standard-library TemporaryDirectory cleanup behavior |
| Other source models | Pydantic construction only | Carry admitted internal values; historical cached dictionaries retain their existing readers |

Core source methods import defining symbols directly. The registry remains the
single immutable content owner. Shared Git owns generic native process, environment,
protocol and cleanup mechanics; source cache paths, admission, index/provenance
writes and labels remain here. The operation deadline is passed explicitly across
source reads; it is never reset by each Git command.

## Exact execution and persistence contract

The production Git profile is `ISOLATED_HTTPS_READ_ONLY`. It preserves the old
source environment allowlist (PATH/SYSTEMROOT/WINDIR/SYSTEMDRIVE/COMSPEC/PATHEXT/
TEMP/TMP, preserving actual key spelling), disables system/global Git config,
interactive prompts and askpass, clears credential helpers, disables redirects
and permits only HTTPS protocol. It does not inherit host HOME, credential,
proxy or provider environment values. The existing ordered native configuration
and subprocess cwd are preserved; no token appears in argv or configuration.
The trusted constructor-only `repository_provider` test adapter uses a distinct
explicit file-read profile. Production profile validation refuses credentials,
extra environment/configuration and protocol/hook override attempts; the HTTP
schema cannot enable that test seam.

Git stdout stays spooled to a temporary file. Running output/time/cache breaches
retain `repository_limit_exceeded`; nonzero exit or oversized final output retains
`repository_access_unavailable`. The per-command timeout remains 45 seconds within
the same 60-second discovery/revisions deadline. Polling remains 50ms. Source cache
accounting stays source-owned at 128 MiB; command-specific output caps and local
file/depth/count limits retain their existing values and boundary behavior.
The old source Popen/taskkill/killpg launcher is removed in the same checkpoint.

One explicit failure contract is strengthened: shared process-tree cleanup is
bounded by one five-second deadline shared across job/process-group termination,
pipe draining and final wait. Budgeted Windows reads are launched suspended and
assigned to an owned Job Object before resuming; job accounting must confirm zero
active processes, including after a successful root exit. Legacy profiles retain
their old launch and taskkill behavior. Native process creation, killing and
polling have operating-system overhead; this is not a hard real-time guarantee.
Legacy Git profiles keep their existing per-substep waits. If termination cannot be confirmed,
retain the owned clone staging and return `repository_cleanup_unverified`; do not claim the process stopped or advise
an immediate repeat. Confirmed cleanup preserves the prior categories. This new
uncertainty path needs its own catalogue/producer guard and remains live-unverified
unless safely observed; internal child-process controls are supporting evidence.

Retaining an uncertain clone staging directory is explicit: it must not be removed
while its process may still use it. The staging owner uses TemporaryDirectory
cleanup for the ordinary path and detaches its finalizer only when preserving
that directory. This is one feature-owned lifetime object, not another Git runner.
Retained `clone-*` directories remain under source state and count toward the
same 128 MiB cache budget, including partial files. They are not automatically
evicted: later source reads can refuse with `repository_limit_exceeded`. Do not
remove retained staging until its owned process tree is confirmed stopped; no
staging-reconciliation or removal button is provided by the current UI.
`KeyboardInterrupt` and `SystemExit` retain their identity and arguments after a
cleanup attempt. When that observation is uncertain, interrupted clone staging
is retained too; preserving an interrupt does not authorize deleting its files.

Index/origin JSON shapes, replacement order, retained choices, labels, sort order,
LF/CRLF byte identities and canonical latest behavior remain unchanged. Pydantic
models construct admitted new values; they do not impose a new schema on historical
index records. Public constructor and discover/revisions/resolve signatures stay
stable. Private coordinator Git/local methods move to their actual collaborators;
external custom code using them requires explicit manual migration. The offline
symbol map migrates independent utility imports, not arbitrary instance methods.

Before replacing the launcher, capture its actual argv/environment and process
limits at the exact base. Compare the new implementation against that independent
baseline using credential-free repositories and real controlled child processes.
Preserve historical source/evidence and distinguish these controls from real HTTPS
source/pin browsing. D3 Agent workspace moves and D4 GitHub domain ownership remain
separate checkpoints.

The HTTP source client forwards only the exact `repository_cleanup_unverified`
category from an error response of at most 16 KiB. Every other category, malformed
body, oversize response or read failure keeps the existing
`source_discovery_failed` mapping. It always closes HTTPError responses. No remote
message or payload is presented. This is the sole intentional client/error contract
change in D2; successful source payloads remain unchanged.

## Discovery failures at the node boundary

`LaomedoSkill.update_build_config` owns discovery-dependent form selections;
`source_request` remains the stateless application transport. A confirmed
`repository_cleanup_unverified` category must leave the component as that exact
safe code and reach the existing shared error catalogue. It must not become a
successful configuration response with generic refresh advice. The existing
catalogue explains that the user must not repeat discovery or remove retained
clone staging while earlier Git processes may remain. There is no staging cleanup
button. Other discovery failure behavior remains unchanged by this focused repair.

The component's local clearing is not a returned frontend template after an HTTP
failure. Do not claim that previous browser choices were replaced by that clearing.
Component and config-to-alert regressions are supporting controls. The exact real
cleanup-uncertainty discovery story remains unverified until safely observed;
ordinary service outage or a synthetic cleanup code cannot establish its acceptance.
This gap remains a merge/acceptance blocker under the workspace rules.
