# GitHub examples

Use one builder for two supported workflows: inspect an existing Issue/PR, or
propose and apply one bounded PR operation through the existing Codex Agent.
The builder uses production components. It does not start a service, contact
GitHub, dispatch an Agent or perform a write.

## Prerequisites

Install the implementation and the project's Langflow/LFX runtime. Configure
the private host GitHub service and application connection as described in
[connection setup](../../docs/features/github/connection.md). Supply a real
repository, existing resource number and current title. The host connection must
allow that repository; selecting a reference never grants write authority.

## Inspect an Issue or PR

From the implementation checkout:

```powershell
python examples/github/build_flow.py --repository OWNER/REPO --number NUMBER --title "Current title" --kind issue --output issue-flow.json
```

Replace the placeholders with the actual selected resource. Use `--kind pr` for
a PR. Import the generated flow into the application, refresh discovery, select
the existing resource and run its node. Open its viewer; the normalized content
must match the independently read GitHub resource. No operation is connected,
so Operation Result reports `not_requested`.

See [Issue controls](../../docs/features/github/issues/walkthrough.md) and
[PR controls](../../docs/features/github/pull-requests/walkthrough.md). Filters
must still match the selected resource. A missing or stale selection refuses;
it does not silently choose another Issue/PR.

## One PR operation with the real Agent

Register [title-skill](title-skill/SKILL.md) through the existing Skill service
and obtain its immutable revision. Configure the real Codex runner and a
host-owned PR feedback grant bound to this exact PR and the permitted operation.
Follow the [PR walkthrough](../../docs/features/github/pull-requests/walkthrough.md)
for service and grant setup. Credentials belong outside the graph and Git.

```powershell
python examples/github/build_flow.py --repository OWNER/REPO --number NUMBER --title "Current title" --feedback --runner-url http://host.docker.internal:PORT --skill-id pr-feedback-title --revision sha256:REVISION --output pr-flow.json
```

The two operation participants are `PR → Agent → same PR.Operation`; an
independent read-only Skill supplies the trusted instruction. Run the PR node
once. The Agent proposes content-only JSON; the host validates the selected
identity, scope and current content before applying it. The sample Skill asks for
the title **Original Codex Agent feedback verified**. Confirm `succeeded` and
read the remote PR independently. A proposal alone is not success.

Keep the existing intent/run record on `unknown`; inspect remote state before
starting a new operation. Do not blindly repeat Fresh. Finish by revoking the
temporary grant and stopping only the services you started. This workflow does
not create a PR or support arbitrary graph cycles.

## Ownership and history

`build_flow.py` owns the CLI and `build()` projection. Shared `../graph.py` owns
pure `node()` and `edge()` metadata construction, also used by Skills. The
`title-skill` folder contains only the real operation instruction.

Older Issue operation campaigns, fixture graphs and executed exports are
[preserved on exp](https://github.com/amadou-6e/laomedo/tree/714db418243bc17fff1c2a5bed5181006e21fdee/archives/github-244),
with original revision, paths and byte hashes. Their recorded results describe
historical runs, not current acceptance. Internal deterministic graph controls
live in the owning tests and are never offered as a real integration example.
