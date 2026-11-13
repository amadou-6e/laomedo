# Prepare a local GitHub App

Status: local deployment provisioning for [#251](https://github.com/amadou-6e/laomedo/issues/251).
Open `/settings/github?deployment=1` deliberately as the deployment owner.
Continue on GitHub sends a prefilled App manifest; confirm creation and choose
repositories on GitHub. The bound return exchanges the one-use registration code
and stores only the client secret in Windows vault. Ordinary Add Connection never
enters registration or asks for App identifiers or secrets.

Registration is profile-scoped in this local increment. It is not a distributed
shared-App deployment or multi-user administrator capability. App installation
does not create a saved connection: return to connections, Add Connection, authorize
the App and confirm repository choices. No live success is implied by this guide.

If registration cannot be confirmed, inspect your GitHub Apps before retrying:
GitHub may have created an App even when conversion or local custody failed.
Automatic registration retries are intentionally absent. Restart, logout, expiry
or another profile/lease cannot resume a pending registration. Remove an unused
remote App deliberately in GitHub; local cancellation does not delete it.

The opt-in native implementation targets Python 3.11 or newer (the inspected
local runtime is 3.12). Its `private-sources` extra pins Authlib and its supported
HTTPX2 client together, plus the explicit Windows keyring backend. Installing
these dependencies does not configure an app or connect an account. Core Python
3.10 installations retain public behavior and do not support this private path.

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
| App slug | Non-secret name from the registered app URL; validate before deriving its GitHub installation link |
| Client secret | Returned directly to the host by manifest conversion and stored in Windows vault; never copied into chat or the browser UI |

GitHub account authorization and app installation are different. Private repository
access requires both the user and app installation to have access. No Issues,
Pull requests, Workflows or Contents write permission is needed for discovery.
GitHub manifest conversion also returns signing material and a webhook secret.
Neither is used by this user-token flow; they are discarded, never persisted or
returned to the browser. The webhook is disabled. Expiring user tokens are required;
the manifest uses GitHub's default expiration and does not disable it.

## Intended one-time path

1. Configure normal Laomedo sign-in for private access, as selected by the owner.
   Do not disable a running
   preview's auto-login as part of registration.
2. Start the configured local connection UI. Open the deliberate deployment
   entry described above; callbacks derive from the trusted fixed app origin.
3. Continue on GitHub and confirm the prefilled private App registration.
4. Install it on only the intended repositories through its Install App page
   (`https://github.com/apps/APP-NAME/installations/new`, derived from its trusted
   slug). A private app installs only on its owning account; GitHub controls
   account/repository permission checks. The host receives and stores the App
   credentials directly; nothing needs to be copied.
5. Use Add Connection; verify the returned account, then explicitly consent to
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

The implementation derives the fixed callback from trusted configuration; the
browser cannot substitute an arbitrary callback or token endpoint.

See GitHub's [manifest registration](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest),
[user authorization](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
and [callback requirements](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-user-authorization-callback-url).
