# Normal-login startup admission

`NormalLoginStartup` adapts the pinned upstream startup requirement after an
administrator was created through its CLI. It never implements authentication.
`confirm_bootstrap` verifies the explicit administrator and records non-secret
identity/database metadata. `prepare` rechecks effective database, account role,
activity and absence of the legacy default password before setting an ephemeral
in-memory startup value. Upstream sees an existing administrator and preserves
its password. No value is stored, exported as an environment credential or usable
as the user's login password. Missing/changed state fails before app creation.

`RuntimeMarker` in models.py is non-secret runtime metadata. Settings in
settings.py reads only the explicit runtime location. `cli.main` owns command-line
composition. Login, password verification, JWTs and database migrations remain
upstream-owned. This adapter is specific to the pinned Langflow setup behavior;
compatibility and real startup/restart must be verified, not assumed.
