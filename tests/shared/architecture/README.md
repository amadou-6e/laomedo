# Architecture contracts

These controls protect package ownership, installed resources, migration targets,
module cohesion, settings/exception contracts and model wire/persistence formats.
They inspect declared application boundaries across concerns. Execution-specific
scenarios belong to the owning Agent/GitHub suites.

`test_packages.py` compares the actual installed artifact with this checkout and
checks executable entrypoints. `test_cohesion.py` checks module structure and
declared migration targets. `test_settings.py` checks configuration and exception
contracts. `test_models.py` checks existing model validation and serialized bytes.
Asset lookup uses the shared `repository_root()` helper, independently of
nesting or working directory.

```powershell
python -m unittest discover -s tests/shared/architecture -t tests -v
```
