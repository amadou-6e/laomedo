# Select, inspect and revise a Skill

Use this when instructions need to be reused or improved without losing which
files changed and why. You will import real instruction files into a private
registry, inspect their exact revision, then request a two-file candidate edit.
The original source and canonical latest remain unchanged by that proposal.

## Before you start

Use the app, Python environment and private `$runtimeRoot` from
[getting started](../../getting-started.md). Start its runner once so its private
API token exists. File inspection itself does not require a model turn; the
optional edit step uses the configured real Agent and subscription.

This concrete example uses two existing skills from this repository:

- **pr-feedback-title** is the instruction bundle you will inspect and revise.
- **skill-operation-editor** supplies the editing instructions for the Agent.

They are real recorded example skills, not fake providers. The new edit below
is a proposed task for you to run, not a claim that it was executed for this guide.

## 1. Import the bundles and authorize a narrow edit

In a terminal at the repository root, set the three variables from the quickstart
and run the following. It imports existing bytes, prints their actual reference
IDs, and writes a private edit policy. It does not invoke an Agent.

```powershell
$env:LAOMEDO_GUIDE_REPO = $repoPath
$env:LAOMEDO_GUIDE_STATE = $runtimeRoot
@'
import json
import os
from pathlib import Path
from laomedo.skills.registry.store import SkillStore

repo = Path(os.environ["LAOMEDO_GUIDE_REPO"])
state = Path(os.environ["LAOMEDO_GUIDE_STATE"])
store = SkillStore(state / "registry")
for skill_id, source in [
    ("pr-feedback-title", repo / "examples/github-pr/original-agent/title-skill"),
    ("skill-operation-editor", repo / "examples/skill-operations/editor-skill"),
]:
    revision = store.import_skill(skill_id, source)
    print(skill_id, revision["revision_id"])
policy = {
    "policy_id": "quickstart-skill-edit", "revision_id": "1",
    "allowed_paths": ["SKILL.md", "references/usage.md"],
    "allowed_suffixes": [".md"], "allow_new_files": True,
    "allow_deletions": False, "allow_scripts": False,
    "allow_dependencies": False, "allow_assets": False,
    "required_frontmatter": ["name", "description"],
    "permitted_validation_commands": ["structural-v1"],
    "max_files": 2, "max_file_bytes": 8192,
}
(state / "skill-edit-policies.json").write_text(
    json.dumps({"pr-feedback-title": policy}), encoding="utf-8")
'@ | & $pythonExe -
```

Keep the printed hashes for exact selection. This policy permits only those two
Markdown paths; it does not authorize scripts, Git publication or promotion.
For another edit, select the candidate revision and Base Commit from its existing
history. For a fresh installation, use a separate private runtime root for all
registry, journal and service paths together; an empty Base Commit is valid only
at the initial imported revision.

## 2. Start discovery and history services

Start each command in its own terminal, with the same quickstart variables.
They reuse the existing host transport-token file; it never enters the graph.
A process holding that shared token can call the other services configured to
use it. Separate per-service token files are supported for stronger isolation,
provided each backend token-file setting matches its owning service.

**Source service:**

```powershell
& $pythonExe -m laomedo.skills.interface.sources.cli `
  --registry "$runtimeRoot/registry" --state "$runtimeRoot/skill-sources" `
  --api-token-file "$runtimeRoot/runner/api-token" --port 8782
```

**Operation/history service:**

```powershell
& $pythonExe -m laomedo.skills.interface.operations.cli `
  --registry "$runtimeRoot/registry" --database "$runtimeRoot/skill-operations.sqlite" `
  --policies "$runtimeRoot/skill-edit-policies.json" `
  --api-token-file "$runtimeRoot/runner/api-token" --port 8787
```

Before restarting Terminal C's app, set these additional variables in that same
terminal. Keep its other quickstart settings, then run its app bootstrap again.
Wait until any active graph work has finished before restarting the app.

```powershell
$env:LAOMEDO_SKILL_SOURCE_URL = 'http://127.0.0.1:8782'
$env:LAOMEDO_SKILL_SOURCE_TOKEN_FILE = "$runtimeRoot/runner/api-token"
$env:LAOMEDO_SKILL_OPERATION_URL = 'http://127.0.0.1:8787'
$env:LAOMEDO_SKILL_OPERATION_TOKEN_FILE = "$runtimeRoot/runner/api-token"
```

## 3. Select and read the skill

1. Create a flow and add a **Laomedo Skill** node, named **Skill to edit**.
2. Set Source to the full path of `$runtimeRoot/registry` and refresh discovery.
3. Choose `pr-feedback-title`, then choose the exact imported revision printed
   in step 1. Do not assume a revision labelled latest is the one you reviewed.
4. Open **Skill files** and read `SKILL.md`. File browsing is read-only.

![Actual Skill file viewer](assets/skill-files.png)

*This existing capture shows another real registered skill and unavailable
history in that captured runtime. Your configured history service should remove
that connection limitation; the picture is not a fresh test of these steps.*

The selected skill instructs a proposal-only PR title change. Merely selecting
or inspecting it neither starts an Agent nor changes GitHub.

## 4. Request a two-file improvement

Add a **Laomedo Claude Agent**, configure its host Runner URL/model/effort as in
the Agent walkthrough, and leave Operation on Fresh. Add another Skill node named
**Editor instructions**, selecting the imported `skill-operation-editor` revision.
Leave that editor Skill's Edit Request and Operation empty.

Wire the named ports:

```text
Skill to edit.Task ----------> Claude Agent.Task
Claude Agent.Answer ---------> Skill to edit.Operation
Editor instructions.Skill Reference --> Claude Agent.Skill References
```

The editor Skill is an independent, read-only instruction dependency. Do not wire
the editing controller's own Skill Reference to the Agent in this feedback graph;
the controller supplies its target snapshot through the task already.

On **Skill to edit**, enter this Edit Request:

```text
Preserve the existing title instruction and frontmatter. Append a reference to
references/usage.md in SKILL.md. Add references/usage.md explaining that the
Agent proposes only a title update, the host applies it after authorization,
and selecting this skill alone does not update GitHub. Change only those two files.
```

Base Commit is in the Skill node's advanced settings. For the first imported
revision leave it empty. Run the **Skill to edit**
controller once. It reserves the edit, invokes the existing Agent, validates the
returned files and records a candidate. Do not separately run the Agent and then
run the controller again: that would be another operation.

## 5. Review the candidate and its diff

Expected Operation Result: `status: proposed`, `promotion_performed: false`, a
new Skill Reference, and a commit with parent, changed paths and editor provenance.
Verify both `SKILL.md` and `references/usage.md` appear in its changed paths.

Select that exact candidate revision on the Skill node and open Skill files.
Choose the earlier commit beneath the file tree, then switch between the two
files. Each view compares that file with the pinned current candidate. Use
**Current source** to leave comparison; drag the divider to resize navigation.

![Historical actual per-file comparison and commit tree](assets/skill-history.png)

*Historical real comparison from another task. It illustrates the viewer, not
the result of this proposed two-file edit. [Provenance](assets/README.md).*

For another edit, use the candidate's exact revision and its commit ID as
**Base Commit**. If a reply is uncertain, inspect history before a fresh run;
do not generate another edit merely to find out whether the first was recorded.

## Finish

Keep the candidate and private journal for review. This workflow does not move
canonical latest or create a source Git commit. Promotion is a separate checked
host operation; Git publishing remains [proposed](user-stories.md#sk-05--publish-a-reviewed-registry-revision-to-git).

After pending edits finish, stop only the source and operation-service terminals
you started. Preserve the registry, policies and journal. If stopping the rest
of the app, follow the quickstart's runner/supervisor shutdown order.
See [registry reference](registry.md) for the promotion boundary and payloads.
