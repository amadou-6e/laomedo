# Local profile integration

This package adapts the pinned Langflow user and session implementation to local
setup profiles. It does not provide hosted accounts or a second identity store.
The canonical draft is [local profiles](https://github.com/amadou-6e/specs/blob/feat/410/projects/laomedo/subsystems/agent-execution/design/local-profiles.md).

`models.py` owns the boundary vocabulary: `ProfileCreateRequest` validates a
profile name and masked PIN pair; `ProfileSummary` exposes only an ordinary
profile identity and display name; `ProfileIndex` describes picker contents.
PINs are excluded from serialization and representations. A boundary must catch
validation errors and return catalogue codes, never Pydantic input payloads.
`settings.py` owns fixed local-profile policy, including the reserved system name.
`auth.py` owns `LocalProfileAuthService`, the narrow authentication adapter.

The startup adapter admits owned state before migrations and verifies the
internal actor before serving. Profile creation delegates to upstream user
creation; login, hashing and token validation stay upstream-owned. The authentication adapter refuses the internal actor without replacing ordinary
profile authentication. `runtime.py` composes these adaptations around the upstream
lifespan only for the opt-in local profile app. The React entry UI is unfinished.

## Object interfaces

- `ProfileCreateRequest.validate_name`: trim and reject empty/reserved names;
  display case is retained. Registry creation must additionally enforce
  case-insensitive uniqueness transactionally.
- `ProfileCreateRequest.validate_pin`: accept exactly the initial six ASCII
  digits; retain leading zeroes. `confirm_pin` checks equality without echoing it.
- `ProfileSummary`: safe projection, never an upstream user serialization.
- `ProfileIndex`: picker response; an empty list represents first run.
- `LocalProfileAuthService.authenticate_user`: delegates ordinary credentials and
  refuses the reserved actor without verifying its startup secret.
- `create_user_tokens`: checks ordinary active identity before upstream minting;
  inherited refresh uses this method too.
- `_authenticate_with_token` / `_authenticate_with_api_key`: validate through
  upstream, then refuse a non-profile principal. Direct upstream API-key callers
  still require startup admission; this adapter alone is not a complete boundary.

These boundary models and internal tests alone do not implement or validate the
registration, switching, restoration or recovery user stories.

- `ProfileRuntimeAdmission.verify_settings` verifies the effective database/auth
  policy; `verify_database` classifies state read-only; `prepare` sets the
  ephemeral in-process startup value after admission.
- `LocalProfileRuntime.configure` installs routes before the SPA fallback;
  `lifespan` verifies the initialized database and effective auth adapter before
  the application accepts requests.
- `LocalProfileRegistry.list_profiles` projects safe identities; `create_profile`
  serializes local registration and delegates the upstream committed transaction.
- `LocalProfileBoundary` validates exact browser entry origin/host and refuses
  unsupported direct identity mutations. `routes.py` is function-only composition.

Forgotten-PIN recovery is intentionally deferred by the owner: entry is blocked,
but profile data remains preserved. No reset/deletion recovery is offered.

The credential invariant is that the app never mints an access/refresh JWT for
the internal actor. Fresh provisioning occurs before requests are accepted;
password login, refresh and token creation refuse that actor, and existing owned
state cannot contain internal API keys. The inspected upstream auth utilities
delegate WebSocket/SSE/MCP identity to the configured service; service-method
checks do not establish real transport acceptance. A local OS user directly
editing the database or signing credentials is outside this convenience-lock
trust boundary.
