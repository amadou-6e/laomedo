# Offline migration controls

`test_paths.py` protects final defining imports, local aliases, line endings,
Unicode offsets, typed-interface refusals, idempotence, explicit selection and
exclusive backups. `utils.load_migration()` loads the checkout-owned tool while
restoring temporary import paths. Other files protect component revision hashes,
immutable history and the inventoried retained callers under their own boundaries.

`agent-history.json` belongs to `tools/migrations`, where the offline CLI consumes
it. It identifies immutable historical paths, not runnable examples. Current
module imports must remain current, including GitHub utilities retained in this
independent Agent cut. Twenty-one automatically mapped constants modules plus the
explicitly manual retired OpenCode parser cover the twenty-two original inputs.

Run `python -m unittest discover -s tests/test_shared/test_migration -t tests -v`.
No check fetches `exp` or runs a provider. Historical source dependencies that have
not yet been migrated remain explicit failures, not new compatibility facades.
