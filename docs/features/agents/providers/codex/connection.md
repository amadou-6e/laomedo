# Connect Laomedo to your ChatGPT account

Laomedo creates its own private OAuth store during sign-in. You do not need an
existing store path, a manually registered client ID, or a copied Codex profile.
This is a separate connection from the desktop app or Codex CLI login.

Use the Python environment from [getting started](../../../../getting-started.md),
with Laomedo's `runner` extra installed. In PowerShell, choose a persistent folder
outside every Git checkout and agent mount:

```powershell
$chatgptStore = Join-Path $env:LOCALAPPDATA 'Laomedo/chatgpt'
& $pythonExe -m laomedo.host.credentials.siwc.cli --store $chatgptStore connect
& $pythonExe -m laomedo.host.credentials.siwc.cli --store $chatgptStore status
```

Complete the browser sign-in and consent while the command is waiting. The CLI
currently allows three minutes for its loopback callback. If it reports
`auth_callback_timeout`, a later browser confirmation does not establish a saved
connection: check Status and start a fresh Connect attempt if no account is saved.
Successful Status reports `auth_outcome: active` with safe identity references.
Never paste OAuth tokens into a graph, console command or support message.

The store holds the issued client ID and rotating login material. The host owns
refresh; only the access credential is passed to the split controller. Tool
execution takes place in a separate credential-free container. Keep the store
separate from runner state and the skill registry. Do not copy a standard Codex
login into this app-owned store or run two refresh owners against it.

Start the matching Codex runner with `--split-executor --auth-store $chatgptStore`
in addition to its normal `--state`, `--skill-store` and `--source-workspace`
arguments. Both flags are trusted host startup configuration. There is currently
no Connect button or credential-path input on the Agent node. App-owned OAuth
requires split execution; normal single-container execution refuses this store.

## Verification scope

On 2026-10-29, installed revision `4eb5d95` completed the actual browser OAuth
callback and one real read-only split ACP run using this store. Codex read
`local-service.md` and returned the documented recovery behavior. Controller and
executor cleanup were confirmed, no Docker receipts remained, and the dedicated
empty test profile was removed. No desktop/CLI login was copied for this run.

An earlier attempt failed during Docker setup with `docker_control_failed` before
any model request. Its cause remains unconfirmed; subsequent credential-free
profile initialization and the observed run succeeded. These observations do not
establish automatic refresh, revocation, account switching, restart/resume behavior,
or a node-owned browser sign-in experience.

See the [official registration and sign-in flow](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
for the provider protocol. GitHub uses its own
[host connection and mediation setup](../../../github/connection.md).
