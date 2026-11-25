# Connect a GitHub account

Status: per-account private App onboarding for [#251](https://github.com/amadou-6e/laomedo/issues/251).
Open GitHub connections and choose Add connection, then Continue on GitHub.
Laomedo prepares a private App registration for the account being connected; GitHub
asks for creation, repository installation and authorization approvals. Confirm
that GitHub shows the intended account before approving registration.

Each GitHub account owns its own private App. Existing connections retain their
original App and credentials. No App is made public, and users never copy an App
ID, client secret or signing key into Laomedo. Completing registration stores the
credential in native custody, begins the exact new App's authorization attempt,
and carries installation back to that attempt. Final repository access in Laomedo
still requires Save access. Live acceptance is recorded separately from this guide.

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

| GitHub setting | Required value for the connected App |
| --- | --- |
| App name | An available name identifying this local Laomedo installation |
| Homepage | The supported local app URL or a maintainer documentation URL |
| Callback | Exact fixed loopback callback displayed by the configured local app, ending `/api/v1/laomedo/github-connections/callback` |
| Repository permissions | Contents: read-only; Metadata: GitHub-required read-only; Pull requests: read and write |
| Organization/account permissions | None additionally requested for this feature |
| Webhooks | Disabled for this local polling/revalidation increment |
| User access token expiration | Enabled; retain supported refresh semantics |
| Device flow | Disabled; not an implicit fallback |
| Installation scope | Only the repositories selected for source and PR access |
| App slug | Non-secret name from the registered app URL; validate before deriving its GitHub installation link |
| Client secret | Returned directly to the host by manifest conversion and stored in Windows vault; never copied into chat or the browser UI |

GitHub account authorization and app installation are different. Private repository
access requires both the user and app installation to have access. The App requests Pull requests read and write access, including PR creation,
for selected repositories. Issues, Workflows and Contents write permission are
not requested. A connected account does not itself grant a graph permission to
perform a write; application operations still require their own authorization.
GitHub manifest conversion also returns signing material and a webhook secret.
Neither is used by this user-token flow; they are discarded, never persisted or
returned to the browser. The webhook is disabled. Expiring user tokens are required;
the manifest uses GitHub's default expiration and does not disable it.

## Connection path

1. Log into the local Laomedo profile and open GitHub connections.
2. Choose Add connection and Continue on GitHub.
3. On GitHub, use the account being connected and approve the prefilled private
   App registration. The App remains owned by that account.
4. Approve installation for the intended repositories. The bound return continues
   authorization for that same App; no other connection's App is selected.
5. Verify the returned account and Save access for the repositories Laomedo may read.
6. Existing accounts are managed through View connection: edit repository access or
   sign in again using that connection's saved App. Do not create another App merely
   to refresh an existing account.

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
