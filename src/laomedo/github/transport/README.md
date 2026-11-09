# GitHub operation delivery

`GitHubMediatedTransport` lives in `mediated.py`. Keep GitHub
Git policy in `git/`, REST delivery in `rest.py` and its fixed protocol values in `settings.py`, and generic Git mechanics in
`laomedo.git`. This is composition, not a common base or new transport pipeline.

`GitHubMediatedTransport` means the concrete dispatcher for an already-admitted
operation; `GitHubGitTransport` and `GitHubRestTransport` identify the actual
delivery mechanism. No adjective is added merely because every operation is
bounded. Public HTTP adapters remain at the wider `github/interface/` boundary.

| Method | Contract and effects |
| --- | --- |
| `__init__(git_transport, rest_transport)` | Require the same selected repository; retain `ValueError("repository_mismatch")`. Store the two existing collaborators; perform no delivery. |
| `__call__(repository, operation, payload, **binding)` | Route `git_push`/`git_fetch` to Git and every other operation to REST, forwarding the exact arguments and result/errors. No retry, new validation or identity selection. |

GitHub-specific workflows, branch/reference scope, verified stage, credentials
and unknown remote outcomes remain with their current transport/host owners.
Migrate maintained imports directly to the defining module. Preserve retained
probe bytes and use explicitly selected import-only copies in internal controls;
there is no duplicate dispatcher or legacy production alias.

## REST delivery

`rest.py` owns GitHubRestTransport. Its __call__ selects the narrow admitted
operation for the configured repository. Reads normalize Issue/PR data; writes
preserve confirmed, rejected and uncertain outcomes without silently retrying
unknown writes. Host-owned credential suppliers are evaluated for the current
connection generation. A resource identity never authorizes a write.
Pagination, payload and deadline limits bound reads. Feature utils.py modules
own response admission; transport/settings.py owns fixed query/pattern values.
Redirect refusal uses the existing shared HTTP policy.
