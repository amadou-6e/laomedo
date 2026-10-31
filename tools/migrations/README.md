# Saved-code migration

These offline tools update explicitly selected saved code and graph templates to
the installed package interfaces. They do not install runtime aliases, import
hooks or parallel implementations.

| Owner | Responsibility |
| --- | --- |
| `migrate_module_paths.py` | Rewrite admitted Python imports, CLI commands and recognized graph code/hash tokens; preserve unrelated JSON bytes and values |
| `module-paths.json` | Map supported module references to defining owners |
| `symbol-paths.json` | Map symbols whose defining module or name differs |
| `cli-paths.json` | Map executable module commands independently from server-class imports |
| `manual-symbols.json` | Identify access requiring explicit manual migration |
| `migration_errors.py` | ManualMigrationRequired reports unsupported or ambiguous conversion |

Run `python tools/migrations/migrate_module_paths.py --help` for supported flags.
Migration must be selected explicitly. Dynamic lookup, star imports and ambiguous
private access are refused where the tool cannot preserve meaning. Known graph
components have their source hashes checked before replacement. Persisted run
identities, selections, topology and historical execution evidence remain intact.

The `retained-*-callers.json` inventories identify archived probe sources and their
exact bytes. Named internal controls adapt only imports in a temporary copy or
in memory, verify non-import code equality and never invoke live probe entrypoints.
These inventories preserve provenance; they are not compatibility exports or
evidence that the current real integration has passed. Application code imports
defining owners directly.
