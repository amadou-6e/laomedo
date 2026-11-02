# Host concerns

`test_publication/` owns frozen-bundle ingestion, bounded verification, worker
ownership and verified Git snapshots used by the Shared preparation boundary.
Tests follow the production concern, rather than a `test_bundle_*` filename
family at the discovery root. Agent execution and GitHub mediation suites retain
their separately scoped organization.

Run this package from the normal test discovery root:

```powershell
python -m unittest discover -s tests/test_host -t tests -v
```
