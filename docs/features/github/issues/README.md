# GitHub issues

Issue nodes own issue selection, inspection and existing-issue operations.

- [User stories and visuals](user-stories.md): select an issue, inspect it and apply an operation.
- [Issue node guide](../../../../examples/github-issue/README.md): controls, outputs,
  host setup, operation payloads and deployment limitations.
- [Issue component](../../../../components/laomedo/github_issue.py): graph boundary.
- [Shared GitHub architecture](../architecture.md): host authority and transport ownership.

Implementation belongs to `src/laomedo/github/issues/`. Governing requirements
live in the [canonical issue-integration specifications](https://github.com/amadou-6e/specs/tree/main/projects/laomedo/subsystems/issue-integration).
The screenshots illustrate implemented controls; they do not establish a new live GitHub test.
