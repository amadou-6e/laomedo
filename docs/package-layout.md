# Package layout and migration

Install with `python -m pip install -e .`, or install the wheel. Python 3.10
remains the minimum. Import and launch canonical domain modules directly.
The package root contains only `__init__.py` and `_paths.py`; there are no
forwarding modules, import hooks or checkout bridge.

```text
src/laomedo/
  activity/{agent_activity,claude,opencode,runner}/
  agents/
    {artifacts,contracts,feedback,handoffs,runtime,workflow,workspace}/
    providers/{claude,opencode}/
    resources/
  skills/{authoring,ingestion,inspection,operations,registry,sources,workspace}/
  skills/resources/
  github/{issues,pull_requests,transport/{git,rest}}/
  host/
    credentials/{claude,opencode,siwc,token}/
    {leases,mediation,runner}/
    publication/{bundle,handoff,verified}/
    publication/resources/
  integrations/langflow/join/
  work_graph/
```

Each implementation has one owner. Use `laomedo.agents.runtime.runner`,
`laomedo.skills.registry.store` and `laomedo.activity.agent_activity.capture`.
The activity package exports `ActivityStore`, `capture_for` and `now`;
module patch targets live in their defining modules. Docker build definitions
live in `containers/`; registry documentation is in `docs/skill-registry.md`.

Launchers use canonical names:

```text
python -m laomedo.agents.runtime.cli ...
python -m laomedo.agents.providers.claude.cli ...
python -m laomedo.host.leases.service_cli serve ...
python -m laomedo.host.managed_service ...
```

The app factory is `laomedo.integrations.langflow.viewer:create_app`.
Credentials and persisted runner/activity state stay outside the package.
Resource bytes, image pins, schemas, request acknowledgement and cleanup
behavior stay unchanged. Resource paths follow their owning package.

## One-time migration

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
Graph migration selects template code. Launcher fields are selected only at
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
focused module such as `serialization.py`. `constants.py` owns genuinely shared
constants and mutable locks exactly once. Initializers expose only deliberate
package APIs. Feature imports use explicit module owners; distinct dependencies
must never rebind the same module alias.

Recurring values travel as canonical Pydantic models in the feature's `models.py`:

| Owner | Models and purpose |
| --- | --- |
| agents/contracts | RunnerRequest groups endpoint, payload and method; its projection preserves saved component HTTP interfaces |
| work_graph | WorkItem, Dependency and GraphSnapshot retain immutable source identity, ordering and snapshot hashes |
| skills/operations | FileEdit, SkillProposal and EditorProvenance carry a multi-file edit and authenticated editor context |
| host/publication/verified | VerifiedStage carries the immutable verified bundle and its provenance |
| host/leases | ContainerIdentity carries exact name, run ID and a secret launch token |
| activity/agent_activity | CaptureIdentity carries graph provenance; ActivityInvocation replaces the anonymous store/invocation tuple |

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
