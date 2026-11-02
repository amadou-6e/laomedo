# Skill source interface

This package owns the application's authenticated loopback source boundary.
The domain SkillSources service owns admission, discovery and registry imports.

| Module | Defining responsibility |
| --- | --- |
| client.py | source_request: validate endpoint/token and project requests |
| server.py | SkillSourceServer: own one loopback listener and service/token bindings |
| handler.py | SkillSourceRequestHandler: authenticate, admit routes/fields, call the service and return safe categories |
| settings.py | Settings: externally supplied endpoint and token-file configuration |
| cli.py | main: trusted explicit construction and service startup |

Server denotes listener lifetime; RequestHandler denotes one request's protocol.
Clients do not grant source admission or execute content. POST actions discover,
revisions and resolve retain their exact field sets and payload shapes. Limits,
authentication failures and descriptive client fallbacks retain their contracts.
No HTTP option enables the repository_provider test capability. Core source and
registry modules do not import this transport or an optional graph framework.
