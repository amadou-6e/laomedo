# Run and inspect an Agent task

Use this when you have a project question and want an answer you can inspect
alongside its execution. You will create one Agent node, submit one task and
review the retained result. Skills and GitHub are optional for this task.

## Before you start

Complete [getting started](../../getting-started.md) if you do not yet have the
app, frontend overlay, supervisor and Claude runner. That page includes the
installation commands, private state paths, login, readiness check and shutdown
order in one place. This walkthrough uses that same setup and its source folder,
`docs/vision-and-goals`, where the Agent sees `README.md`.

If you configure another source, choose the project directory on the trusted host
before starting the runner. The browser Task does not choose an arbitrary host
folder. The normal source mode expects a directory within a Git tree, without
the repository's own `.git` directory at its root. The quickstart's document
subdirectory meets that condition; Git-workspace mode is a separate setup.

## Configure the question

1. Create a blank flow named **Improve the project introduction**.
2. Add **Laomedo Claude Agent**. Under Advanced controls, use the host runner URL
   from your installation, `http://127.0.0.1:8769` in the quickstart.
3. Refresh Model, choose an available model, then choose a supported effort.
   Reuse your chosen values when reopening the flow; model discovery is read-only.
4. Select **fresh** and enter:

   ```text
   Read README.md. Identify two places where a first-time user might not know
   what to do next. Suggest a concrete wording improvement for each. Return
   your suggestions in the answer; do not change files or external systems.
   ```

![Actual Agent node controls](assets/agent-node.png)

*Existing app capture, with Status selected. Choose Fresh for this new task.
See [visual provenance](assets/README.md) for its exact evidence scope.*

## Run once and inspect the answer

Run the node once and wait for its terminal result. Open **Activity** from the
selected node, then read the conversation for that invocation. Confirm the
answer refers to the document you provided and includes the two requested
suggestions. Neither the source file nor a GitHub item should be changed by
this task.

A successful graph build by itself is insufficient: inspect the Agent's actual
outcome and conversation. If a trace reports an error or an uncertain outcome,
retain its run identity and inspect the failure before another submission.

![Actual retained Agent conversation](assets/agent-activity.png)

*Historical conversation displayed in the running app, not a model response to
the new wording-improvement task above. Opening Activity does not submit work.*

## Choose the next operation deliberately

| Your goal | What to do |
| --- | --- |
| Ask a separate question | Use Fresh; this creates new work |
| Read retained messages and execution evidence | Open Activity; no dispatch |
| Check a known earlier execution through the runner | Use Status only with that execution's valid prior-run binding |
| Continue a completed native session | Use Resume with the compatible prior-run binding and snapshot |
| Interrupt known running work | Use Cancel through its valid binding and wait for confirmed cleanup |

There is no node-local run selector today. A newly created node cannot infer a
prior execution for Status, Resume or Cancel. Existing serialized flows or API
requests can supply the binding; the fresh tutorial does not establish one for
you to select. Do not substitute Fresh for an unavailable Status or Cancel action.

## When the runner is unavailable

Check Docker Desktop first. If Docker is healthy but the runner is offline,
restart the exact runner command from the quickstart. **Start local runner** is
available only when your app host has configured the managed runner service;
the manual quickstart does not enable that control automatically. Starting the
service does not rerun the graph or resolve an uncertain task outcome.

If the API responds but subscription/model discovery fails, check the dedicated
runner login. The host's interactive Claude login and a separately authenticated
Docker volume are distinct. [Runner recovery](runner/local-service.md) and
[the Docker controller guide](../../../docker/claude/README.md) explain the host
configuration and supported login mirroring.

## Finish

Retain the flow and Activity record. Once the task is terminal and cleanup is
confirmed, use [the quickstart shutdown order](../../getting-started.md#8-finish-and-clean-up).
You can next [add a Skill](../skills/walkthrough.md) or
[work with a PR](../github/pull-requests/walkthrough.md).
