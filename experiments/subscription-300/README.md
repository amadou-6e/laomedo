# Subscription allowance investigation (#300)

Production draft: `feat/300`, head `9fe91730`, PR #304, based on provider-connections
`42ab3c53b0aee1fd395085b9379eff1717c40ad2`. Specification draft: specs PR #438,
head `36b04e9a1979ef83ed2e042d73d32cb25d6c67ce`.

These are investigation/operator tools, not production dependencies. No
credentials, account identifiers, private profiles or raw runtime logs are saved.
`serve.py` reuses the existing runtime and stable preview port 17884; do not run it
alongside a different process owning the port. It initiates no model work.

`build_adapter.py` materializes the immutable registered Docker context, builds
with its real recipe label and checks ordinary image admission. It does not
change or bypass private build-cache ACLs. Native TypeScript check, 11 adapter
tests and build passed. Image:
`laomedo-codex-acp:0.159.2-2.1.1-quota1`,
`sha256:78a7adbd306c25d660777f52665c2e2a5aed7782cd2c01a04bddd116a251027e`.

`check_auth_mode.py` runs the pinned client with the exact custom Responses
provider configuration, an empty temporary home, no network, credentials or mounts.
It initializes, then sends only `account/rateLimits/read`. Observed 2026-11-18:
JSON-RPC error -32600, `codex account authentication required to read rate limits`.
Zero model turns. This proves the configuration lacks native authentication;
it does not establish upstream behavior for an authenticated account or authorize
token reuse across APIs.

Saved accounts use Sign in with ChatGPT token sharing. Official sources:

- https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/ui-ux-guidelines
- https://learn.chatgpt.com/docs/app-server

The first documents the custom provider, the second restricts inference to the
public Responses route, and the UI guidance links to ChatGPT usage settings.
Native quota APIs use a different authentication surface. No host-login import or
undocumented backend fallback was attempted. Owner decision on explicit native
sign-in is pending. Live saved-account quota acceptance has not passed.

Other checks: 76 Python tests/25 subtests, 20 frontend tests, frontend build and
pinned project-wide Black check pass. Fixture tests are not real subscription
acceptance. Preview responds on 17884; the shared integrated tab reports navigation
failure, so rendered UI remains unverified.

Review: implementation fully unreviewed — reviewer pending. Initial specification
review REVISE; corrections have recheck pending. Existing reviewer hit its usage
limit, reported reset 20:00 Europe/Berlin. No merge readiness claim.
