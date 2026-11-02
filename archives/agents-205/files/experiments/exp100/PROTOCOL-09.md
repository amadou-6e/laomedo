# EXP-100/S9: bounded literal command adapter, synthetic only

Issue #100; governing design at specs `c0af42d`:
`projects/laomedo/subsystems/agent-execution/design/mediated-cli-transport.md`.
Record this before implementation. No GitHub/provider/model call authorized
by this protocol. No deployment or production parity acceptance is implied.

Compare literal supported CLI command forms with their exact typed mediator
requests using an injected local fake. `gh pr view NUMBER`, `gh pr create`
with explicit title/body/head/base, `gh pr edit NUMBER` with explicit title
and body, `gh run list`, and same-repository `gh api PATH --method GET` form
the initial matrix. `--repo OWNER/REPO` is optional when the run repository
is configured. Body literals and `--body-file` (including stdin `-`) preserve
UTF-8 content. Mutation needs a caller-supplied durable effect identity and
marker; repeated invocation never automatically invents a replacement.
Edit performs a bound read, uses its expected title/body/head SHA and target
base/branch, then issues one update. It never retries unknown results.

Local Git operations continue natively; this experiment does not intercept
native Git or implement remote push/fetch syntax. Existing exact-commit JSON
push is separate evidence. Presentation is result JSON, not native gh output:
this is explicitly a partial semantic adapter, not full CLI equivalence.
Paging, jq/template/json selectors, interactive forms, aliases/extensions,
auth/token export, generic REST mutations, GraphQL and unreviewed issue-create
remain explicitly unsupported before any mediator request. No ambient gh,
Git credential helper or real token is consulted; no shell command execution.

Tests freeze expected requests/counts/errors: supported reads, create/update
body bytes and exact target/expected snapshots, missing effect identity,
unknown response with exactly one attempted mutation, duplicate/unknown flags,
hostile API paths/repositories, and ambient credential canary environment.
The adapter accepts no caller URL. Wrong repository is refused locally before
contact, while host grant authorization remains authoritative. Unsupported,
denied and unknown outcomes have distinct exit categories. Persist a sanitized
matrix observation only after independent pre-run review of exact source;
prototype tests are not live production evidence.
