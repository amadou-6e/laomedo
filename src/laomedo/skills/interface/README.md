# Skills application interface

Components, the viewer and trusted service startup enter Skills through these
defining adapters. Registry, sources and operations own domain behavior and values.

| Responsibility | Defining module | Vocabulary and dependency rule |
| --- | --- | --- |
| Stateless HTTP transport | `<feature>/client.py` | `*_request` reads call-time settings, performs a local request and projects safe failures |
| Request lifecycle | `<feature>/handler.py` | RequestHandler authenticates, parses, dispatches through its server and replies |
| Listener lifetime/private bindings | `<feature>/server.py` | Server validates loopback/token and owns its domain service and private bearer token |
| Trusted composition | `<feature>/cli.py` | main parses supported flags and explicitly starts feature services |
| External service configuration | `<feature>/settings.py` | Pydantic Settings loads explicit/environment values at use; credentials stay in files |

Client is stateless request transport, Server owns endpoint lifetime, and
RequestHandler owns protocol handling. Each protocol has its own field sets,
caps and uncertainty classification. Transport composes the domain service.
This boundary is discoverable without learning registry or Git internals.

Clients and handlers have narrow feature dependencies. They do not import graph
frameworks or execute provider commands. CLI modules compose SkillStore,
SkillSources or SkillOperations explicitly. Credentials, listener binding and
editing policy come from trusted startup configuration, never graph content.
Redirect refusal uses `laomedo.http.redirect.NoRedirect`.

Selected external saved consumers use the explicit offline module/symbol/CLI maps.
Dynamic or ambiguous access requires manual migration; no runtime import hook or
forwarding facade is installed. Historical graphs and probe sources remain
byte-preserved. Public routes, fields, environment aliases, missing/empty semantics,
safe codes and effect-uncertainty classifications are adapter contracts.

Core domain services depend on registry/source owners rather than HTTP adapters.
Protocol controls and real graph workflows provide distinct evidence; requesting
user validation is a separate acceptance requirement.
