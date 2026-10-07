# #107 Codex subscription connection boundary probe

Observed on 2026-10-07 against Laomedo `c93be20`, Docker Desktop Engine
27.3.1, and the pinned `laomedo-codex-boundary:0.159.2` image. This is a
credential-free check of the existing controller and command layout, not a
Sign in with ChatGPT connection or a model-backed run.

## Question and method

The proposed [authentication contract](https://github.com/amadou-6e/specs/blob/1da03b5/projects/laomedo/subsystems/agent-execution/contract/authentication.md)
would give Codex app-server an OAuth access token in `ACCESS_TOKEN`, as in the
[OpenAI app-server recipe](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server).
Can a command invoked through this runner's `command/exec` read that token?

Run the probe from the Laomedo checkout in PowerShell:

```powershell
$env:PYTHONPATH = (Get-Location).Path
python experiments/feasibility/107/probe_controller_env.py
```

The probe constructs the reviewed Docker command, replaces the
real Codex login volume with disposable tmpfs, and gives app-server a random
synthetic canary in `ACCESS_TOKEN`. It initializes app-server, then makes three
`command/exec` calls that test for the variable without printing its value.
The temporary event log is removed when the probe exits. No browser, real
credential, model turn, or persistent Docker volume is used.

| Access route from `command/exec` | Exit code | Observation |
| --- | ---: | --- |
| Command environment: `ACCESS_TOKEN` is set | 0 | Readable |
| Controller `/proc/1/environ` contains `ACCESS_TOKEN` | 0 | Readable |
| Command's own `/proc/self/environ` contains `ACCESS_TOKEN` | 1 | Not observed there |

The probe returned `controller_env_credential_route_safe: false` and
`model_turns: 0`. A follow-up `docker ps -a` check found no named probe
container left behind. The command-environment result alone is a positive
secret-access path. The `/proc/1/environ` result supplies an independent path.
The `/proc/self/environ` negative result does not make the boundary safe.

## Decision and limits

**No-go for passing a reusable subscription access token through the current
single-container controller environment when untrusted commands are enabled.**
Do not wire Sign in with ChatGPT tokens into this runner or call its present
`command/exec` boundary credential-safe. A clean environment assertion, a
prompt rule, or output redaction cannot undo an observed read path.

This says nothing about whether the selected account will grant ChatGPT plan
usage. OpenAI's [local-app guide](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt)
lists personal projects that run locally as eligible in principle; Laomedo has
not performed app-owned sign-in or checked this account's granted scopes.
Refresh, restart, sign-out, account switching, and an agent-originated attempt
are also untested. No production credential broker was added here.

The next implementation needs a controller/tool separation that denies both
environment and controller-process reads, followed by canary probes through
every command and bundled-script path. Only after those denials should #107
connect an account, implement its persistent refresh lifecycle, and request a
separately capped live test. The existing copied-login prototype remains
unchanged; this experiment does not upgrade its security claim.
