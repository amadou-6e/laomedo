# Package layout and migration

Install with `python -m pip install -e .`, or install the wheel. Python 3.10
remains the minimum. Import and launch canonical domain modules directly.
The package root contains only `__init__.py` and `_paths.py`; there are no
forwarding modules, import hooks or checkout bridge.

```text
src/laomedo/
  agents/
    providers/
    resources/               # Config, seccomp and agent-side MJS adapters
  skills/resources/          # Bundled skill instructions
  github/{issues,pull_requests,transport}/
  host/
    credentials/             # Standalone Git credential helper
    mediation/
    leases/
    publication/resources/   # Pinned staging script
  activity/agent_activity/   # store, capture, cost, projection, routes
  integrations/langflow/
  work_graph/
```

Each implementation has one owner. Use `laomedo.agents.local_runner`,
`laomedo.skills.skill_store` and `laomedo.activity.agent_activity.capture`.
The activity package exports `ActivityStore`, `capture_for` and `now`;
module patch targets live in their defining modules. Docker build definitions
live in `containers/`; registry documentation is in `docs/skill-registry.md`.

Launchers use canonical names:

```text
python -m laomedo.agents.local_runner ...
python -m laomedo.agents.providers.claude_runner ...
python -m laomedo.host.leases.lease_service serve ...
python -m laomedo.host.managed_service ...
```

The app factory is `laomedo.integrations.langflow.langflow_skill_viewer:create_app`.
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
