# Connect your local app to GitHub

This shared setup lets the Issue and PR nodes discover and inspect real repository
work. It configures **read access** first. An account's GitHub token permissions
alone do not authorize a node mutation: writes also require the existing trusted
mediation grant and binding described below.

Use the local app/Python environment and private `$runtimeRoot` from
[getting started](../../getting-started.md). The runner's API token must already
exist. You do not need a model turn to select or inspect an issue or PR.

## 1. Choose the repository and existing connection

In each service terminal, set the quickstart variables and these values:

```powershell
$githubRepository = 'YOUR-OWNER/YOUR-REPOSITORY'
$githubConnectionFile = 'C:/Private/your-existing-github-connection.env'
```

Replace both values. The connection file must already hold the `GH_LAOMEDO` key
readable by your host process. Keep that existing credential outside Git and
Agent mounts. Neither logging into the app nor having a working `gh` session
automatically configures this connection. No token is pasted into a node.

## 2. Start the owning service

For **Issues**, use a dedicated terminal:

```powershell
& $pythonExe -m laomedo.github.interface.issues.cli `
  --repository $githubRepository `
  --github-token-file $githubConnectionFile --github-token-key GH_LAOMEDO `
  --connection-id github-issue-local --connection-generation 1 `
  --api-token-file "$runtimeRoot/runner/api-token" `
  --mediation-store "$runtimeRoot/github-issues.sqlite" --port 8783
```

For **PRs**, use another terminal if you want both modules:

```powershell
& $pythonExe -m laomedo.github.interface.pull_requests.cli `
  --repository $githubRepository `
  --github-token-file $githubConnectionFile --github-token-key GH_LAOMEDO `
  --connection-id github-pr-local --connection-generation 1 `
  --api-token-file "$runtimeRoot/runner/api-token" `
  --mediation-store "$runtimeRoot/github-prs.sqlite" --port 8784
```

Each process serves its configured repository only. These commands deliberately
omit grant bindings: discovery and inspection can work, while updates remain
unauthorized. Keep connection generation aligned with your actual host connection;
if replacing an existing credential, increment its generation and retire old
bindings rather than reusing the example's `1` blindly.

## 3. Configure the app's backend

Set the variables for the services you started in the app's Terminal C, retaining
its other settings. Restart only the app after active graph requests finish.

```powershell
$env:LAOMEDO_GITHUB_ISSUE_URL = 'http://127.0.0.1:8783'
$env:LAOMEDO_GITHUB_ISSUE_TOKEN_FILE = "$runtimeRoot/runner/api-token"
$env:LAOMEDO_GITHUB_PR_URL = 'http://127.0.0.1:8784'
$env:LAOMEDO_GITHUB_PR_TOKEN_FILE = "$runtimeRoot/runner/api-token"
```

Then run the same app bootstrap from the quickstart. These are backend transport
credentials and URLs, distinct from the GitHub provider connection. No graph
export needs either credential. Do not change the existing runner or supervisor.

This local recipe reuses one transport token across the configured services:
holding it permits calls to each of them. For separate service credentials,
configure a distinct API token file on each service and the matching backend
token-file setting. The provider connection remains separate in either case.

Continue with [the Issue walkthrough](issues/walkthrough.md) or
[the PR walkthrough](pull-requests/walkthrough.md). Successful discovery should
show real choices for your exact configured repository, rather than an invented
default item. A service failure is different from an empty result list.

## Before you enable any write

The read-only path above is complete without a mutation grant. To go further,
you must already have a host-authorized, unexpired grant for the exact target,
registered with the matching connection identity/generation and mediation store.
The service's private grant-binding map resolves its opaque reference to that
grant. PR Agent feedback additionally needs a private `repository#PR` mapping
passed with `--feedback-bindings`.

There is currently no general-purpose UI in these nodes to mint those bindings.
Do not fill this gap with a made-up grant, provider token in Operation, or an
Agent-authored authority field. If you do not have the trusted host configuration,
stop after inspection. The module walkthroughs explain what to wire once it exists;
[host services](../agents/mediation/host-services.md) documents the advanced
mediation boundary and its deployment limitations.

## Finish

After any in-flight requests and uncertain writes have been reconciled, stop only
the Issue/PR service consoles you started. Keep their private intent databases.
If writes were separately enabled, revoke their grants during host shutdown.
Disconnecting the app is not proof of remote cancellation or revocation.
