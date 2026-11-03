# GitHub pull requests

PR nodes own PR selection, inspection and existing-PR operations.

- [Inspect a PR and apply an Agent proposal](walkthrough.md): a read-only starting
  path followed by the explicitly authorized feedback workflow.
- [User stories and visuals](user-stories.md): selection, inspection, Agent feedback
  and a labelled proposal for creation before a PR reference exists.
- [PR node guide](../../../../examples/github-pr/README.md): feedback wiring and limitations.
- [Original-Agent PR example](../../../../examples/github-pr/original-agent/README.md):
  recorded real execution and its evidence boundaries.
- [PR component](../../../../components/laomedo/github_pr.py): graph boundary.
- [Shared GitHub architecture](../architecture.md): host authority and transport ownership.

Implementation belongs to `src/laomedo/github/pull_requests/`. The current node
supports existing-target operations; new-PR creation remains a proposed workflow.
Historical evidence is not acceptance of the current checkout.
