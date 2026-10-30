# Run-bound bundle ingestion

This package admits exact bytes from the fixed handoff file in a trusted runner
state root into a separate private publication stage. It owns no Git checkout,
credential, registry entry or repository authorization. No object is introduced:
the existing functions are stateless admission operations and callers may need
them before a stage object exists.

| Defining module | Symbol | Responsibility and outcome |
| --- | --- | --- |
| `utils.py` | `freeze_run_bundle` | Reserve one run/attempt, bind its record, copy bounded bytes, durably record frozen or refused outcome |
| `utils.py` | `validate_ingestion_roots` | Validate nonredirected, disjoint, nonrepository runner/private roots; return resolved roots |
| `utils.py` | `read_run_binding` | Admit the existing run record and workspace; return run directory and exact binding projection |
| `utils.py` | `is_redirected_path` | Detect symlinks, Windows reparse points and failed metadata reads |
| `utils.py` | `read_bundle_bytes` | Read one bounded regular file with link, identity and concurrent-change checks |
| `utils.py` | `write_durable_json` | Write the existing sorted JSON record through an exclusive pending file and atomic replace |
| `settings.py` | `RUN_IDENTITY`, size limits, filename and patterns | Fixed protocol policy, not externally configurable settings |
| `errors.py` | `BundleIngestError` | Existing RuntimeError category with stable code and arguments; failure does not establish verified Git data |

Read, validate, freeze and write describe distinct operations. Preserve function
signatures and exact serialized records/hash preimages. The active binding and
completed-record binding intentionally differ. Filesystem admission, locks,
one-shot attempts, prior-attempt reconciliation and unknown outcomes must remain
fail-closed; the move does not add automatic retry or cleanup authority.

Public shared helper names replace accidental cross-module private imports.
Historical module/symbol migration maps point directly here, with no Skills
facade and no chain. Private same-module helpers stay private. Ingestion has no
graph node or browser endpoint: raw refusal codes are host publication boundary
diagnostics, and callers preserve their current projections. The C2 error guard
records each boundary explicitly rather than assuming every diagnostic is a
node-visible error.
