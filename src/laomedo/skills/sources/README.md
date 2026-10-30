# Skill source interface

`SkillSources` owns admitted source discovery, cached choices and immutable
resolution: `discover(source)`, `revisions(source, choice)` and
`resolve(source, choice, revision)`. It imports exact content without advancing
an existing canonical latest pointer. It never executes Skill code.

| Object/function | Defining file | Method vocabulary |
| --- | --- | --- |
| `SkillSources` | `service.py` | discover, revisions, resolve |
| `SkillSourceServer` | `server.py` | constructor validates loopback/token and binds its source service; inherited HTTP lifetime methods |
| `SkillSourceRequestHandler` | `handler.py` | do_POST authenticates/parses/routes, reply writes a bounded response, log_message suppresses private request logging |
| `source_request` | `client.py` | existing local HTTP client and safe public fallback mapping |

The server retains its source service and private bearer token on that instance;
the module-level handler reads those bindings through `self.server`. No closure,
mutable global, class factory, graph-selected service or credential input is used.
Existing /v1/skill-sources routes, 16-KiB request cap, response encoding, status
codes, SourceError pass-through and unknown-error redaction stay unchanged.
Identical redirect refusal comes from `laomedo.http.redirect.NoRedirect`.

This is C1 only. Interface relocation and bounded shared Git execution require
their own README-first checkpoints, migration controls and real workflow checks.
