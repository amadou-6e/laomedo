# Vision and goals

Laomedo supports designing, inspecting and running agent workflows as a graph
of focused nodes. Agents perform work, Skills supply versioned instructions,
and GitHub nodes connect work to issues and pull requests.

## Who this is for

Laomedo is for people who want to compose and inspect agent work rather than
repeat prompts and manually move results between tools. The current setup is
a trusted, single-user local application; the getting-started path uses Windows,
Docker Desktop and an existing Claude subscription.

| User | Problem to solve | A concrete starting scenario |
| --- | --- | --- |
| Workflow author | A useful prompt becomes difficult to repeat, configure and inspect | Give an Agent a project document, choose its model and effort, then inspect its answer in the same graph |
| Skill author or maintainer | Instructions change across several files, and the reason for each change gets lost | Pin a skill, request a two-file improvement, and review its parent-linked revision and per-file diff |
| Developer working with GitHub | Moving issue or PR context into an agent and applying its answer by hand loses target identity | Select an issue or PR, inspect it, and route an authorized operation through the owning node |

The first useful result is a small, inspectable task on your own project. You do
not need to configure Skills or GitHub to run that first Agent. Add those features
when you need reusable instructions or repository operations.

## Choose your first task

- **Understand a project:** [install, run one Agent and inspect the answer](../getting-started.md).
- **Improve reusable instructions:** [select, inspect and revise a Skill](../features/skills/walkthrough.md).
- **Work from an issue:** [select and inspect an issue](../features/github/issues/walkthrough.md).
- **Review a PR in context:** [select a PR and prepare an Agent operation](../features/github/pull-requests/walkthrough.md).

Application maintainers can start with [architecture](../architecture/README.md).
The user walkthroughs explain the task first; architecture explains the ownership
and boundaries behind it.

## Goals guiding the implementation

- Keep each node responsible for its own domain and controls, with explicit
  contracts for data and operations exchanged with other nodes.
- Make skill changes reviewable through immutable revisions and file diffs.
- Make agent execution inspectable through retained activity and run identity.
- Keep host credentials and authorization outside the agent's command surface.
- Distinguish completed work, uncertain remote outcomes and historical evidence.

These goals summarize the existing [implementation overview](../../README.md)
and feature guides; they do not certify that every target behavior is delivered.
The [canonical project specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo)
retain the governing requirements, decisions and capability limitations.

Continue with [architecture](../architecture/README.md) or the
[feature guides](../README.md#features).
