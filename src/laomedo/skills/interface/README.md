# Skills application interface

This is the discoverable boundary used by components, the viewer and local
service startup. C3's proposed move places the existing HTTP clients, handlers,
servers and startup CLIs here; it introduces no forwarding facade or parallel
protocol. Domain values and service behavior stay in their canonical packages.

| Responsibility | Defining module | Naming and dependency rule |
| --- | --- | --- |
| Stateless request transport | `<feature>/client.py` | `*_request` reads its settings at call time, performs the existing local request and preserves safe error projection |
| HTTP request lifecycle | `<feature>/handler.py` | `*Handler` / `*RequestHandler` authenticates, parses, routes and replies through its server's bindings |
| Listener lifetime and private bindings | `<feature>/server.py` | `*Server` validates loopback/token and owns its domain service and private bearer token |
| Explicit trusted composition | `<feature>/cli.py` | `main` parses the current flags and composes canonical services; it is not an application-import shortcut |
| External service configuration | `<feature>/settings.py` | feature-local Pydantic `Settings`, constructed at use; credentials remain files, never serialized settings values |

Use Base only for an actual abstract contract. There is no common abstract HTTP
handler: each protocol's field sets, caps and uncertainty classifications differ.
No Async/Sync/Bounded variant is introduced. Compose the existing service rather
than inheriting its domain behavior into the transport. This placement lets callers
find the supported API without learning registry, gateway or provider internals.

Clients and protocol handlers retain their existing narrow dependencies and do
not import graph frameworks or execute provider commands. Trusted CLI composition
is the explicit exception that may load host credential/mediation and native
transport owners. Existing exception identities required by the handler boundary
stay direct imports; they do not authorize broader host access. The neutral shared
redirect policy remains `laomedo.http.redirect.NoRedirect`.

CLI commands and maintained component imports migrate through explicit flat
module/symbol/CLI maps. No old-package runtime facade or import hook is planned.
Historical graphs and retained probe sources remain byte-preserved; external
saved services/graphs require an explicitly selected migration before using this
installed version. Node identities, ports, routes, fields, environment names,
missing/empty semantics, error codes and remote-effect uncertainty are unchanged.

This README precedes implementation. Registry/source Git/workspace changes and
real graph acceptance are separate checkpoints; it is not a completion claim.
