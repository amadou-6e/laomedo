# Laomedo implementation documentation

Laomedo lets you run agent tasks, reuse versioned instructions and connect work
to GitHub issues and pull requests in a graph you can inspect.

New here? Read [who Laomedo is for](vision-and-goals/README.md#who-this-is-for),
then follow [getting started](getting-started.md) from installation through your
first Agent answer and cleanup. The current walkthrough uses a local, single-user
Windows/Docker Desktop setup and a real Claude subscription.

## Features

- [Agents](features/agents/README.md): [run and inspect a task](features/agents/walkthrough.md).
- [Skills](features/skills/README.md): [select, inspect and revise instructions](features/skills/walkthrough.md).
- [GitHub](features/github/README.md): [work from an issue](features/github/issues/walkthrough.md)
  or [inspect and update a PR](features/github/pull-requests/walkthrough.md).

For each feature, start with its walkthrough for concrete steps and expected
results. User stories explain the goal and show the UI; architecture and reference
guides explain the implementation. Existing limitations are stated at the step
where they matter.

## For contributors

Read [shared architecture](architecture/README.md) for feature ownership, node
boundaries and package layout before changing the implementation.

Each feature owns its architecture, setup and validation documentation. Provider
details live beneath their feature. Shared architecture describes composition
and boundaries across features, rather than duplicating their internal guides.

The [canonical specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo)
own requirements and decisions. These guides describe this implementation;
historical validation reports establish only their stated revision and scope.
