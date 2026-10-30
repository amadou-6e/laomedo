# Issues HTTP boundary

C3 location for the existing API; README committed before moving code.
This leaf adapts local HTTP to `GitHubIssueGateway` in `github/issues`. It owns no duplicate
domain records or authority. `GitHubIssue` remain canonical under the domain owner.

| Symbol | Supported interface vocabulary | Effects and failures |
| --- | --- | --- |
| `issue_request` in `client.py` | `(action, **payload) -> dict`; actions: discover, execute | Reads call-time Settings/token file, performs the existing local HTTP request; preserves response admission, code and uncertain-write mapping |
| `IssueServer` in `server.py` | Constructor accepts existing service/token/port arguments; inherited serve_forever, shutdown, server_close | Owns listener lifetime and instance-local service/private token; exact loopback and credential admission remains |
| `IssueRequestHandler` in `handler.py` | do_POST, reply, log_message | Authenticates before parsing, admits exact field sets, dispatches through self.server and writes current JSON/no-store response; suppresses private request logging |
| `Settings` in `settings.py` | Existing Pydantic constructor and settings_customise_sources | Only explicit arguments and environment, at point of use; same aliases/defaults/missing and empty values; no credential content, dotenv or secret-store discovery |
| `main` in `cli.py` | Existing flags; explicit trusted startup composition | Starts the listener with host-supplied services/credentials; `--help` must work at the new module command |

Request body cap stays 1 MiB; endpoints, response encoding/status, redirect
refusal and error catalogue/client projection stay exact. A response failure after
possible dispatch never means a write is safe to resend. Domain manual admission
and canonical Pydantic projections remain authoritative; no transport schema is
added merely to move a file. Constructors and full signatures remain in code.

Usage: configure the existing service URL/token-file environment, start
`python -m laomedo.github.interface.issues.cli` using its current flags, then
call `laomedo.github.interface.issues.client.issue_request`. Stop through the
existing server lifecycle; no graph-selected credential or listener binding.
Maintained imports/launchers use the new owner. Explicit offline migration handles
old selected copies, while retained historical bytes stay unchanged.
