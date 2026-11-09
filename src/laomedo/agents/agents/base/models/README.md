# Shared Agent values

Data contracts are organized by concern within the same Agent capability. Import
directly from defining modules; the initializer contains no model re-exports.

| Module | Values |
| --- | --- |
| [attempt.py](attempt.py) | Attempt context/request/outcome and detached settlement view/updates/result |
| [journal.py](journal.py) | Typed ownership, native binding, dispatch, turn, lease, identity, correction, evidence and cleanup writes |
| [runtime.py](runtime.py) | Runtime binding/observations, resource plans and per-resource cleanup reports |
| [credentials.py](credentials.py) | Public bindings, admission constraints and excluded host material |
| [commands.py](commands.py) | Bounded command request and native result |
| [catalog.py](catalog.py) | Native model choices and snapshots |
| [preparation.py](preparation.py) | Existing preparation, workspace, skill, exclusion and GitHub scope records |
| [failures.py](failures.py) | Existing private allowlisted failure observations and finalization records |

The move preserves class bodies, validation, field descriptions and serialization.
Target values remain inspection-stage contracts; they do not replace current
public payloads or persisted schemas. Host callables, credentials and settlement
handles retain their exclusions and validation-error privacy. Dependencies flow
from value concerns to lower resource/settlement ports without importing concrete
providers or optional Docker implementations at module load.
