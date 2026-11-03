# GitHub pull requests

PR nodes own PR selection, inspection and existing-PR operations.

- [Inspect a PR and apply an Agent proposal](walkthrough.md): a read-only starting
  path followed by the explicitly authorized feedback workflow.
- [User stories and visuals](user-stories.md): selection, inspection, Agent feedback
  and a labelled proposal for creation before a PR reference exists.
- [PR node guide](../../../../examples/github/README.md): feedback wiring and limitations.
- [Original-Agent PR example](https://github.com/amadou-6e/laomedo/blob/714db418243bc17fff1c2a5bed5181006e21fdee/archives/github-244/files/examples/github-pr/original-agent/README.md):
  recorded real execution and its evidence boundaries.
- [PR component](../../../../components/laomedo/github_pr.py): graph boundary.
- [Shared GitHub architecture](../architecture.md): host authority and transport ownership.

Implementation belongs to `src/laomedo/github/pull_requests/`. The current node
supports existing-target operations; new-PR creation remains a proposed workflow.
Historical evidence is not acceptance of the current checkout.
