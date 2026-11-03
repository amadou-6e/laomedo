# Issue user stories

Acceptance criteria describe intended behavior and were not re-verified for this
documentation increment. Consult the linked guides and revision-specific evidence.
Actual screenshots are labelled separately from proposed mockups.
See [visual provenance](assets/README.md) and [shared architecture](../architecture.md).

## ISSUE-01 — Select an issue

As a workflow author, I want to choose a repository, filter by labels and select an
issue, so the workflow operates on an explicit piece of work.

**Status: Implemented.** Repository URL, Labels and Issue belong to the Issue node.

Acceptance criteria:

- Repository changes clear dependent selections; all selected labels must match.
- Refresh does not silently select the first result or replace an exact identity.
- A missing selection is distinct from a connection error or an empty result list.

![Actual GitHub Issue node before configuring a repository](assets/issue-node.png)

*Actual component form, 2026-10-28. The documentation node is unconfigured;
no repository data or operation outcome is fabricated.*

Guide: [Issue node](../../../../examples/github-issue/README.md).

## ISSUE-02 — Inspect the selected issue without running it

As a workflow author, I want to view the selected issue in the app and open its
exact GitHub page, so I can check the context before running an operation.

**Status: Implemented; populated viewer not captured here.** Issue viewer and
Open in GitHub use the valid picker selection. A runtime-only reference is not
guessed into a saved selection.

Acceptance criteria:

- Opening the viewer fetches scoped content without executing an operation or model call.
- Open in GitHub targets the exact selected repository and issue number.
- Loading, unavailable content and no selection remain distinguishable.

![Actual Issue viewer with no issue selected](assets/issue-viewer-empty.png)

*Actual empty state, 2026-10-28. This illustrates the selection requirement;
it does not demonstrate a populated live issue or a successful provider read.*
Guide: [Issue inspection controls](../../../../examples/github-issue/README.md#issue-inspection-controls).

## ISSUE-03 — Apply an operation to the selected issue

As a workflow author, I want to send a scoped operation to the Issue node,
so the host can validate and apply it to the intended issue.

**Status: Implemented for existing targets.** Issue operations accept ordinary
incoming operation data. This does not claim the PR node's Agent feedback cycle
is supported for Issues in the same way.

Acceptance criteria:

- An operation requires a selected or otherwise valid bound issue target.
- The host validates identity and authorization; a proposal cannot supply its own authority.
- Confirmed, failed and unknown outcomes remain distinct; uncertain writes are not blindly resent.

Visual: [the actual Issue Operation input and Operation Result output](assets/issue-node.png).
See the [Issue operation guide](../../../../examples/github-issue/README.md).
No new issue mutation was performed for this documentation.
