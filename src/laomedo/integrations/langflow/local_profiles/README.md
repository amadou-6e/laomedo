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

The planned startup adapter admits owned state before migrations and verifies the
internal actor before serving. Profile creation delegates to upstream user
creation; login, hashing and token validation stay upstream-owned. The authentication adapter refuses the internal actor without replacing ordinary
profile authentication. Routes and UI are not implemented at this checkpoint.

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
