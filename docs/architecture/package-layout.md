# Package layout and migration

Install with `python -m pip install -e .`, or install the wheel. Python 3.10
remains the minimum. Import and launch canonical domain modules directly.
Normal Codex host runners additionally require `python -m pip install -e '.[runner]'`
(or `uv sync --extra runner`) in their launcher environment. This host-only extra
is optional for Langflow/core and stage-worker installations. The pre-PyPI Git
dependency and retained-receipt recovery are described in
[Docker runtime adoption](docker-runtime-adoption.md#local-installation-and-recovery).
The package root contains only `__init__.py` and `_paths.py`; there are no
forwarding modules, import hooks or checkout bridge.

```text
src/laomedo/
|-- activity/
|   |-- agent_activity/
|   |-- claude/
|   |-- opencode/
|   `-- runner/
|-- agents/
|   |-- artifacts/
|   |-- contracts/
|   |-- feedback/
|   |-- handoffs/
|   |-- runtime/
|   |-- workflow/
|   |-- workspace/
|   |-- providers/
|   |   |-- codex/
|   |   |   `-- resources/
|   |   |-- claude/
|   |   `-- opencode/
|   `-- resources/
|-- skills/
|   |-- authoring/
|   |-- ingestion/
|   |-- inspection/
|   |-- operations/
|   |-- registry/
|   |-- sources/
|   |-- workspace/
|   `-- resources/
|-- github/
|   |-- issues/
|   |-- pull_requests/
|   `-- transport/
|       |-- git/
|       `-- rest/
|-- host/
|   |-- credentials/
|   |   |-- codex/
|   |   |   `-- resources/
|   |   |-- claude/
|   |   |-- opencode/
|   |   |-- siwc/
|   |   `-- token/
|   |-- leases/
|   |-- mediation/
|   |-- runner/
|   `-- publication/
|       |-- bundle/
|       |-- handoff/
|       |-- verified/
|       `-- resources/
|-- integrations/
|   `-- langflow/
|       |-- agent/
|       `-- join/
`-- work_graph/
```

Each implementation has one owner. The neutral lifecycle is
`laomedo.agents.agents.base.agent.BaseAgent`; Codex execution is
`laomedo.agents.agents.codex.agent.CodexAgent`. Use
`laomedo.skills.registry.store` and `laomedo.agents.activity.capture`.
The activity package exports `ActivityStore`, `capture_for` and `now`;
module patch targets live in their defining modules. Docker build definitions
live in `docker/`; registry documentation is in [the Skills registry guide](../features/skills/registry.md).

Launchers use canonical names:

```text
python -m laomedo.agents.agents.codex.cli ...
python -m laomedo.agents.agents.claude.cli ...
python -m laomedo.host.leases.service_cli serve ...
python -m laomedo.host.managed_service ...
```

The app factory is `laomedo.integrations.langflow.viewer:create_app`.
Credentials and persisted runner/activity state stay outside the package.
Resource bytes, image pins, schemas, request acknowledgement and cleanup
behavior stay unchanged. Resource paths follow their owning package.

## One-time migration

Recognized Langflow component source hashes are refreshed with migrated code so
the graph does not retain an obsolete component cache key. IDs, connections,
settings, pinned skills and existing run references remain unchanged. Unknown
hash formats require manual component-revision migration. This operation does
not run or retry the graph; retain its exclusive backups.

Old flat imports are removed. Migrate older saved graph component code and
external launcher commands before running them with this version:

```text
python tools/migrations/migrate_module_paths.py saved-flow.json service-launcher.ps1
python tools/migrations/migrate_module_paths.py saved-flow.json service-launcher.ps1 --apply
python tools/migrations/migrate_module_paths.py saved-flow.json --check
```

The default reports which explicitly selected files need changes. Applying
creates a sibling `.before-module-migration` backup; existing backups are never
overwritten. Module references in graph JSON are rewritten without changing
graph/run identities or unrelated payloads. The map in `tools/migrations/` is
one-time migration data, not runtime compatibility code.

File migration splices changed JSON strings, preserving unrelated bytes,
formatting, duplicate keys, Unicode, number spelling, BOM and line endings.
Graph migration selects template code. It preserves `metadata.code_hash` and
stored dependency metadata; it does not regenerate component-cache metadata.
Generate current component templates/exports through Langflow or the graph's
builder when refreshed metadata is required. Import migration alone does not
certify those fields. Launcher fields are selected only at
the root or in an explicit root `launcher` object. Unparseable retired imports
require manual migration. `--check` exits 1 when changes are needed.
Backup conflicts are checked before writing; replacement is atomic per file.
An unexpected later I/O failure can leave a batch partly applied, with earlier
originals retained in backups. Registered tasks are not files: re-run
`scripts/Install-LaomedoUserTask.ps1` with the existing configuration to replace
an old registered command before enabling the task again.

Do not rewrite historical execution evidence. Preserve originals and migrate
a copy when needed for a new graph. Validation covers installed discovery,
resources, canonical CLIs, migration idempotence and migrated graph loading.
Real Agent and managed-service acceptance are recorded separately; internal
tests do not establish a live workflow.

## Cohesion and typed internal data

Package boundaries follow a feature's responsibilities and dependencies, with no
fixed nesting depth. Repeated filename prefixes trigger an ownership review.
Implementation files introduce classes or standalone functions, never both.
Request-handler classes may be nested in their owning server constructor.
Exceptions live in class-only `errors.py`. Helpers that belong to an object become
methods; independent helpers stay in that feature's function-only `utils.py` or a
focused module such as `serialization.py`. `settings.py` owns genuinely shared
constants and mutable locks exactly once. Initializers expose only deliberate
package APIs. Feature imports use explicit module owners; distinct dependencies
must never rebind the same module alias.

Use `settings.py`, not `constants.py`. Externally supplied feature configuration
lives in a feature-owned Pydantic `Settings` object in that file, constructed at
the point of use. Preserve existing environment names, empty/missing semantics
and exact `"1"` flags. Do not read dotenv files or secret directories implicitly.
Token file paths may be settings; credential values must not become settings
fields, logs or serialized configuration. Child-process environment allowlists,
dynamic credential lookups and the standard-library-only Git helper retain their
explicit boundary handling.

Fixed protocol values, image and integrity pins, safety bounds and shared locks
remain module-owned values, never environment fields. General domain payloads
remain in `models.py`; configuration is the explicit `settings.py` exception.
Domain exceptions document their meaning and outcome guarantees, expose the
stable `code`, and retain `str(error) == code` and existing inheritance. A
specialized exception may inherit its constructor, but must state its distinct
contract. Recovery and user-facing explanations remain in the shared error
catalogue; an internal code is not a human-readable error message.

Recurring values travel as canonical Pydantic models in the feature's `models.py`:

| Owner | Models and purpose |
| --- | --- |
| agents/agents/base | RuntimeBinding groups provider-owned public record metadata |
| agents/interface | RunnerRequest groups endpoint, payload and method; its projection preserves saved component HTTP interfaces |
| work_graph | WorkItem, Dependency and GraphSnapshot retain immutable source identity, ordering and snapshot hashes |
| skills/operations | FileEdit, SkillProposal and EditorProvenance carry a multi-file edit and authenticated editor context |
| host/publication/verified | VerifiedStage carries the immutable verified bundle and its provenance |
| host/leases | ContainerIdentity carries exact name, run ID and a secret launch token |
| agents/activity | CaptureIdentity carries graph provenance; ActivityInvocation replaces the anonymous store/invocation tuple |

Models own validation, constructors and explicit projections. HTTP/provider JSON
and persisted records retain their existing fields and identities. Strict models
do not coerce invalid values. Secret-bearing models hide values in representations
and validation text; only the named private registration projection extracts a
lease capability. Model construction never replaces host authorization checks.
The standalone Git credential helper remains stdlib-only.

Migration maps distinguish module names, moved symbols and CLI entrypoints. Every
published generation resolves directly to final owners in one pass. Ambiguous
symbols, dynamic access to retired modules and changed typed call signatures
require manual migration before any selected file is written. Detection is
conservative and best-effort; manually review changed call signatures and dynamic
references even after a successful migration preview. In particular,
container cleanup takes `ContainerIdentity` (including injected `LeaseService`
cleanup callbacks, whose signatures the tool cannot always infer); `ActivityStore.start` takes
`CaptureIdentity`; `capture_for` returns `ActivityInvocation` with `.store` and
`.invocation_id`, rather than a tuple. Historical execution records are retained.

Structural checks reject mixed class/function files, module/package shadowing and
conflicting module aliases. Regression checks preserve model serialization,
existing snapshot bytes/hashes, operation error codes and secret redaction. Error
catalogue checks follow feature error producers after extraction. Installed-wheel,
pinned-stage-image and real graph evidence remain separate from internal tests.

## Provider-neutral Agent boundary

The shared `BaseAgent` owns the current lifecycle and is not a default Codex provider.
It owns private state, durable request identity and acknowledgement, workspace
preparation, immutable skill/artifact inputs and host authorization orchestration.
Codex, Claude and OpenCode extend it directly. They own their constructors,
request policy, model discovery/cache, native execution, resume binding,
pre-dispatch authentication, cancellation and exact restart cleanup.
`RuntimeBinding` in `agents/agents/base/models.py` groups the public record fields;
it never carries an access token. Credential identity metadata is distinct from
login material. The record key set remains stable, including explicit nulls.
OpenCode prepared records now report its own CLI and `opencode_acp` mode, with
null image/profile/config fields, rather than inherited Codex metadata. Historical
records remain readable; the migration does not rewrite execution history.

The shared HTTP server delegates editor refresh and resume extensions to provider
hooks. Shared runtime code imports neither concrete providers nor credential
implementations. Closed external provider IDs for handoff/artifact validation
belong to the contracts vocabulary, not a default-provider switch.

Mediated GitHub eligibility is explicit: Codex enables it only with its supervised,
non-split execution path. Claude remains ineligible through the shared preparation
path. OpenCode now refuses this path before binding a grant: its former inherited
supervision flag did not implement mediated execution. Existing
`mediated_lease_required` behavior identifies the refusal. This does not enable a
new remote-write capability for either provider.

Graph components keep their public names and ports. Their shared implementation
lives in `agents/interface/langflow/component.py`, with the established
`integrations/langflow/agent/component.py` public entrypoint delegating to it,
so no additional base node is exposed by the component category loader.
Concrete adapters declare capabilities instead of the common component choosing
behavior by node name. Embedded Claude/OpenCode sources inheriting the old Codex
component must be migrated with the one-time tool; custom methods and graph
identities are retained. Regenerate templates when current dependency metadata is
needed. Current source templates are distinct from historical execution evidence.

Issue #205 covers this boundary. General helper decomposition, cross-feature HTTP/
Git command execution now belongs to `git/`; `AgentWorkspace` composes its objects
for Agent admission, while GitHub workflow rules and host publication policy keep
their own owners. Mediation server extraction and frontend feature directories
remain separate follow-ups (#206 through #210).

Concrete Codex components reject stale subclass inheritance before model discovery,
bridge selection or dispatch with `agent_component_migration_required`. The shared
error catalogue explains updating the node or explicitly migrating saved source;
unmigrated Claude/OpenCode code cannot silently route through Codex configuration.
OpenCode owns its worker image pin independently in its settings. It initially uses
the same reviewed sandbox bytes as Codex, without importing Codex configuration.

The migration tool refuses retired procedural Git symbols even when they appear
in comments or docstrings. Review those references manually; the tool never
guesses a new object call signature. Unchanged component code leaves its revision
key untouched. Changed code uses the pinned LFX hash, checked against the actual
`lfx.custom.utils._generate_code_hash` implementation in the Langflow suite.

Direct-symbol imports also change private monkeypatch bindings. Patch the name
where a consumer uses it, for example `agents.activity.capture.capture_for`, not
the original utility module's `capture_for`. Public component/error import paths
remain explicit delegates; they do not proxy private test bindings.
