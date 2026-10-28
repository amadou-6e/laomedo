# Getting started: your first Agent task

By the end, you will have a local graph whose Claude Agent reads Laomedo's real
vision document, returns a short explanation and retains its conversation in
Activity. You will also know how to stop the processes you started.

This is a source-setup walkthrough for **Windows, local Docker Desktop, Python
3.12, Git, Node.js 20.19+ and an existing Claude subscription**. It uses the pinned
Langflow 1.12.3 frontend and the matching Laomedo overlay. These commands describe
the supported components; a fresh clean-machine installation was not re-run for
this documentation change. No fixture provider or simulated answer is used.

If your local app and Claude runner are already configured, go straight to
[create and run the graph](#6-create-and-run-the-graph).

## 1. Install the Python application

Use a checkout of the same Laomedo revision as this guide; the current review
branch and an older default-branch checkout may have different layouts. Open
PowerShell at the implementation repository root: the folder containing
`pyproject.toml`, `components/` and `docker/`. In this workspace that is
`implementation/`; a standalone clone uses its repository root.

```powershell
$repoPath = (Get-Location).Path
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'Laomedo/quickstart'
$pythonExe = Join-Path $repoPath '.venv/Scripts/python.exe'
py -3.12 -m venv .venv
& $pythonExe -m pip install --upgrade pip
& $pythonExe -m pip install '.[observability]' 'langflow==1.12.3'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
```

The application environment belongs in `.venv`. Registry bundles, API state,
activity and login material belong outside Git, under the private runtime folder
or the dedicated Docker volume. Keep this same `$runtimeRoot` in later sessions
to retain saved graphs and run references.

In each additional terminal below, open the same repository root and set:

```powershell
$repoPath = (Get-Location).Path
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'Laomedo/quickstart'
$pythonExe = Join-Path $repoPath '.venv/Scripts/python.exe'
```

## 2. Build the matching frontend

Use a new upstream checkout for this setup; the overlay requires a clean checkout
at the exact pinned revision. Leave the checkout used by an existing app alone.

```powershell
$upstreamPath = Join-Path $runtimeRoot 'upstream-langflow'
git clone https://github.com/langflow-ai/langflow.git $upstreamPath
git -C $upstreamPath checkout fec71dca901949c09ed4d63315804337cd2eb13d
& $pythonExe tools/apply_langflow_skill_viewer.py $upstreamPath
& $pythonExe tools/apply_pr_operation_feedback.py $upstreamPath
Push-Location (Join-Path $upstreamPath 'src/frontend')
npm ci
npm run build
Pop-Location
```

Expected result: `src/frontend/build/index.html` exists in that upstream checkout.
The overlay supplies the Skill viewer, Agent controls/activity, GitHub viewers and
shared errors. The separate feedback patch supports returning PR or Skill
operations to their owning node. Apply each script once to this new checkout.

## 3. Prepare the Claude controller

Start Docker Desktop and wait for its engine to be ready. Check `docker info`
before building. This dedicated volume is for the tutorial's Claude login and
native sessions; do not substitute a full personal profile mount.

```powershell
docker info
docker build -t laomedo-claude-controller:2.1.310 docker/claude
docker volume create --label laomedo.provider=claude laomedo-claude-quickstart-profile
docker run --rm -it --mount type=volume,source=laomedo-claude-quickstart-profile,target=/profile laomedo-claude-controller:2.1.310 auth login
```

Complete the native subscription sign-in. The controller image's CLI is pinned;
the runner resolves and checks its immutable image identity on startup. Existing
single-user installations can instead opt into access-login mirroring through
their host configuration; see [the controller guide](../docker/claude/README.md).
This walkthrough uses the dedicated-volume login above.

## 4. Start the supervisor and runner

Use two terminals with the variables from step 1. The supervisor must outlive the
runner so it can reconcile owned containers after runner loss.

**Terminal A — independent supervisor:**

```powershell
& $pythonExe -m laomedo.host.leases.service_cli serve --state "$runtimeRoot/lease"
```

Leave it running. In **Terminal B**, start the API. Its source is the actual
Laomedo vision document directory within this Git checkout, not a synthetic
project. It exposes `README.md` at the root of the Agent's private draft.

```powershell
& $pythonExe -m laomedo.agents.providers.claude.cli `
  --state "$runtimeRoot/runner" `
  --skill-store "$runtimeRoot/registry" `
  --source "$repoPath/docs/vision-and-goals" `
  --lease-service "$runtimeRoot/lease" `
  --image laomedo-claude-controller:2.1.310 `
  --profile-volume laomedo-claude-quickstart-profile `
  --port 8769
```

Leave it running. If these ports are already owned by another installation, use
unused ports and change both the corresponding host configuration and node URL.
Do not replace another listener.

## 5. Start the app and check the connection

In **Terminal C**, set the step-1 variables, then configure the app. The bootstrap
extends the custom-component category's import path, as required for the current
Agent components; it does not add a compatibility facade to the core package.

```powershell
$env:LANGFLOW_CONFIG_DIR = "$runtimeRoot/langflow"
$env:LFX_CONFIG_DIR = "$runtimeRoot/langflow"
$env:LANGFLOW_DATABASE_URL = 'sqlite:///' + ("$runtimeRoot/langflow/flow.db").Replace('\', '/')
$env:LANGFLOW_FRONTEND_PATH = "$runtimeRoot/upstream-langflow/src/frontend/build"
$env:LANGFLOW_COMPONENTS_PATH = "$repoPath/components"
$env:LAOMEDO_COMPONENT_DIR = "$repoPath/components/laomedo"
$env:LANGFLOW_AUTO_LOGIN = 'true'
$env:LANGFLOW_DO_NOT_TRACK = 'true'
$env:LAOMEDO_SKILL_STORE = "$runtimeRoot/registry"
$env:LAOMEDO_AGENT_ACTIVITY_DB = "$runtimeRoot/activity.db"
$env:LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE = "$runtimeRoot/runner/api-token"
New-Item -ItemType Directory -Force -Path "$runtimeRoot/langflow" | Out-Null

# Readiness only: this does not submit a task or print the API token.
$headers = @{ Authorization = 'Bearer ' + ([IO.File]::ReadAllText($env:LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE)).Trim() }
Invoke-RestMethod 'http://127.0.0.1:8769/v1/health' -Headers $headers |
  Select-Object status, provider
Remove-Variable headers

@'
import os
import laomedo
import uvicorn
laomedo.__path__.append(os.environ["LAOMEDO_COMPONENT_DIR"])
uvicorn.run("laomedo.integrations.langflow.viewer:create_app", factory=True,
            host="127.0.0.1", port=7860)
'@ | & $pythonExe -
```

Expected health response: `status` is `ready` and `provider` is `claude`. That
confirms the API identity; it is not proof of model entitlement or a completed
task. Open **http://127.0.0.1:7860**. Auto-login is used only for this loopback,
single-user app. Keep this terminal running.

## 6. Create and run the graph

1. Create a blank flow and name it **Understand Laomedo**.
2. Add **Laomedo Claude Agent** from the Laomedo component category. Keep it as
   the only node for this first task; Skills are optional.
3. Expand **Advanced controls** and set **Runner URL** to
   `http://127.0.0.1:8769`. The app and runner in this guide are both host processes;
   the component's Docker-host default is not the URL for this setup.
4. Refresh **Model**, select an available model from your configured runner and
   choose a supported **Reasoning Effort**. Discovery does not submit a model task.
5. Set **Operation** to `fresh` and enter this **Task**:

   ```text
   Read README.md in the provided project. In three short bullets, explain who
   Laomedo is for, what problem it addresses, and what a new user should try first.
   Do not edit files or perform external actions.
   ```

6. Run the Agent once. This submits a real task through your Claude subscription.
   Do not repeatedly click Run while its outcome is uncertain.
7. Open **Activity** on the selected Agent to read its retained conversation.

![Actual Agent controls, with an existing node on Status](features/agents/assets/agent-node.png)

*Existing real app capture; this walkthrough selects Fresh instead of the Status
value pictured. The image does not show an execution of the new tutorial task.*

## 7. Check the result

You should see a terminal successful invocation and an answer about the document
you supplied. Check the conversation against your prompt rather than accepting a
green build duration alone. A trace error or unknown outcome is not a successful
Agent result. Your wording can vary because this is a real model response.

Activity is read-only: opening it does not rerun the task. Do not change Operation
to Status, Resume or Cancel unless that node/request has a valid prior-run binding.
There is currently no node-local run selector; a missing binding produces a
descriptive error. The [Agent walkthrough](features/agents/walkthrough.md) explains
the distinction and the next task.

The first result to check is the conversation and terminal outcome. Usage or
OpenTelemetry sections can be absent or incomplete depending on capture settings;
the existing Activity illustration includes telemetry from its recorded run.

| Where you are blocked | What to do |
| --- | --- |
| Docker command is missing | [Install Docker Desktop](https://docs.docker.com/get-started/get-docker/), then reopen the terminal |
| Docker is installed but its engine is stopped | Start Docker Desktop and wait for `docker info` to succeed |
| Runner is offline | Restart Terminal B's exact runner command; managed installations may offer Start local runner in the recovery panel |
| Model list or subscription is unavailable | Check the configured runner and its dedicated login; a working host Claude session alone does not prove this separate volume is signed in |
| Existing work may still be running | Inspect the recorded run/activity before another submission; restarting a service does not reconcile or rerun the graph |

## 8. Finish and clean up

After the invocation is terminal and its owned containers have been reconciled,
stop Terminal C's app with Ctrl+C, then Terminal B's runner, then Terminal A's
supervisor. Keep the supervisor running if cleanup is still unconfirmed.

Keep `$runtimeRoot` and the dedicated login volume for your next session: they
retain graph data, API identity, native sessions and results. Removing the profile
invalidates sessions needed for Resume. If you later choose to discard this
installation, remove only its reviewed private runtime directory and the exact
`laomedo-claude-quickstart-profile` volume after all its work has finished.
Do not prune unrelated Docker containers, volumes or personal profiles.

Continue with [Agent tasks](features/agents/walkthrough.md),
[Skills](features/skills/walkthrough.md), [Issues](features/github/issues/walkthrough.md)
or [pull requests](features/github/pull-requests/walkthrough.md).
