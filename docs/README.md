# Laomedo implementation documentation

Laomedo composes agent workflows from nodes with distinct responsibilities.
Start with [vision and goals](vision-and-goals/README.md), then read the
[shared architecture](architecture/README.md) or the feature you are changing.

## Features

- [Agents](features/agents/README.md): execution, runners, provider activity and mediated commands.
- [Skills](features/skills/README.md): revisioned files, drafts and controlled promotion.
- [GitHub](features/github/README.md): issue and pull-request selection and operations.

Each feature owns its architecture, setup and validation documentation. Provider
details live beneath their feature. Shared architecture describes composition
and boundaries across features, rather than duplicating their internal guides.

The [canonical specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo)
own requirements and decisions. These guides describe this implementation;
historical validation reports establish only their stated revision and scope.
