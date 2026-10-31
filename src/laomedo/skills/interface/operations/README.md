# Operations HTTP boundary

This leaf adapts local HTTP to `SkillOperations` in `skills/operations`. It owns no duplicate
domain records or authority. `SkillProposal, SkillCommit and SkillOperationResult` remain canonical under the domain owner.

| Symbol | Supported interface vocabulary | Effects and failures |
| --- | --- | --- |
| `skill_request` in `client.py` | `(action, **payload) -> dict`; actions: prepare, apply, history, diff, compare | Reads call-time Settings/token file, performs the local HTTP request; applies response admission, safe code and uncertainty mapping |
| `SkillOperationServer` in `server.py` | Constructor accepts service/token/port arguments; inherited serve_forever, shutdown, server_close | Owns listener lifetime and instance-local service/private token; enforces loopback and credential admission |
| `SkillOperationRequestHandler` in `handler.py` | do_POST, reply, log_message | Authenticates before parsing, admits exact field sets, dispatches through self.server and writes current JSON/no-store response; suppresses private request logging |
| `Settings` in `settings.py` | Supported Pydantic constructor and settings_customise_sources | Only explicit arguments and environment, at point of use; documented aliases, defaults and missing/empty behavior; no credential content, dotenv or secret-store discovery |
| `main` in `cli.py` | Supported flags; explicit trusted startup composition | Starts the listener with host-supplied services/credentials; `--help` describes the supported command |

Request body cap is 4 MiB; endpoints, response encoding/status, redirect
refusal and error catalogue/client projection are protocol contracts. A response failure after
possible dispatch never means a write is safe to resend. Domain manual admission
and canonical Pydantic projections remain authoritative; transport performs admission at the HTTP boundary. Constructors and full signatures remain in code.

Usage: configure the service URL/token-file environment, start
`python -m laomedo.skills.interface.operations.cli` using its current flags, then
call `laomedo.skills.interface.operations.client.skill_request`. Stop through the
server lifecycle; no graph-selected credential or listener binding.
Callers use the defining client module and CLI command above. Explicit offline
migration supports selected saved consumers; archived evidence stays byte-preserved.
