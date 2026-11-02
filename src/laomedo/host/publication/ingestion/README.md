# Run-bound bundle ingestion

This package freezes a run-bound Git bundle from trusted runner/private roots.
utils.py owns freeze_run_bundle and focused path, record and reconciliation helpers;
settings.py owns fixed handoff names and caps; errors.py defines BundleIngestError.

Ingestion denotes credential-free admission of exact transferred bytes. It does
not verify Git object contents, stage commits, publish, grant provider authority or
inspect Skill content. Its caller owns the trusted roots and publication policy.
The immutable receipt and existing error categories retain their external shapes.
