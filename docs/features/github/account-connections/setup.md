# Prepare a local GitHub App

Status: setup design for [#251](https://github.com/amadou-6e/laomedo/issues/251),
not a working installation guide. The connection UI and secure entry are not
implemented yet. No existing app is assumed; the owner corrected that on
2026-11-07. Creating an app or changing its settings needs explicit owner action.

## Registration configuration to review

| GitHub setting | Required value for this local source-read increment |
| --- | --- |
| App name | An available name identifying this local Laomedo installation |
| Homepage | The supported local app URL or a maintainer documentation URL |
| Callback | Exact fixed loopback callback displayed by the configured local app, ending `/api/v1/laomedo/github-connections/callback` |
| Repository permissions | Contents: read-only; Metadata: GitHub-required read-only |
| Organization/account permissions | None additionally requested for this feature |
| Webhooks | Disabled for this local polling/revalidation increment |
| User access token expiration | Enabled; retain supported refresh semantics |
| Device flow | Disabled; not an implicit fallback |
| Installation scope | Only the repository or repositories selected for Skill reads |
| Client secret | Generated deliberately, entered once into the secure local setup UI and stored in Windows vault; never pasted into chat |

GitHub account authorization and app installation are different. Private repository
access requires both the user and app installation to have access. No Issues,
Pull requests, Workflows or Contents write permission is needed for discovery.
GitHub App private keys/installation-token signing are not required by the proposed
user-access-token flow; do not generate or collect unrelated credentials.

## Intended one-time path

1. Choose the supported local-owner/session setup. Do not disable a running
   preview's auto-login as part of registration.
2. Start the eventual configured local connection UI; it displays its exact
   registered callback. Do not use a guessed preview port or wildcard callback.
3. Review the configuration above, open GitHub registration and create the app.
4. Install it on only the intended repositories. Copy the non-secret client ID
   and enter the client secret through the local masked setup field.
5. Use Connect GitHub; verify the returned account, then explicitly consent to
   the repositories Laomedo may read. Sign-in alone does not select every repository.
6. Enter the private HTTPS repository URL on the Skill node, choose the connection,
   discover a Skill/revision and inspect its real files. This is future acceptance,
   not a result established by these instructions.

Do not use the host gh token, GCM, .env token or another application's client ID
as a shortcut. The explicit token alternative accepts a deliberately supplied
supported fine-grained personal token, entered only through secure local UI.
Never claim its complete upstream permissions are known from a successful read.

## Recovery and setup constraints

A callback mismatch must show setup guidance and preserve the current ready
connection; it must not retry with an unregistered address. Missing org/installation
access or ambiguous 404 says access could not be confirmed. Cancel invalidates
this attempt only. Disconnect stops new local access and hides private views but
cannot retract previously delivered files or prove GitHub consent was revoked.

No registration URL with live callback or command is presented as runnable yet.
The exact local app origin and owner-authentication decision are pending. The
implementation will derive the fixed callback from trusted configuration; the
browser cannot substitute an arbitrary callback or token endpoint.

See GitHub's [registration parameters](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters),
[user authorization](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
and [callback requirements](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-user-authorization-callback-url).
