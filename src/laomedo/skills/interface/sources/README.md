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

The handler admits at most 16 KiB of request-body bytes. The client retains its
bounded response read and safe source-error projection. An uncertain response
after possible dispatch does not establish that resending is safe. This boundary
never executes a Skill or Agent.

Settings use explicit construction arguments or the declared environment fields;
there is no dotenv or secret-store lookup. Credential values remain in token files,
not serialized settings. Start the service with
`python -m laomedo.skills.interface.sources.cli --help`; callers import
`source_request` from `laomedo.skills.interface.sources.client`.

The checkout-owned offline migrator handles explicitly selected source paths.
Immutable historical exports remain byte-preserved on `exp`, independently of
current module migration and without any historical execution acceptance claim.
