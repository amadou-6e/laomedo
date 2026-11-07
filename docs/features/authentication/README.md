# Local profiles

The first local Windows setup uses named profiles with a PIN. No email,
administrator bootstrap or approval step is exposed. Profiles distinguish setups
within one Windows user's installation; they are not isolated operating-system
accounts. Private GitHub connections remain separate work under #259-#262.

The profile implementation is in progress in PR #263. The canonical
[design and editable screens](https://github.com/amadou-6e/specs/blob/feat/410/projects/laomedo/subsystems/agent-execution/design/local-profiles.md)
passed design review. That does not establish that the implemented browser
workflow works. Keep this PR draft until the live stories, code review and owner
inspection pass. Do not point users at the older administrator bootstrap.

`tools/start_local_profiles.ps1` prepares an isolated, explicitly owned runtime
outside Git, checks an unused loopback port, and starts the matching frontend and
backend. Its modes are Prepare, Check and Serve. Check validates configuration;
it is not a server or login test. The existing preview and other runtime folders
are left unchanged. PIN entry belongs in the browser, never a command argument.

The backend admits fresh owned state or its recognized current schema before
migrations. Partial, corrupt or unexpected identity state is refused without
repair. One internal startup identity satisfies upstream's initialization contract
and delegates profile creation, but cannot enter the browser as a profile. Its
startup secret is generated only in process; it is not a human credential.
Ordinary profile identities, hashing and sessions remain upstream-owned.

Forgotten-PIN recovery is deferred by explicit owner choice: the profile cannot
be entered, while its data remains preserved. No delete/recreate recovery is
provided. [Implementation status](local-profiles.md) records remaining work.
