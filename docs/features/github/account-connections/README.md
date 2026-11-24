# GitHub account connections for private Skill sources

The GitHub Settings pilot in [PR #257](https://github.com/amadou-6e/laomedo/pull/257) supports profile-scoped connections, explicit repository read consent and a read-only private Skill viewer. The pilot is opt-in for the local Windows deployment. Private Skill execution and repository writes are not supported. See [issue #251](https://github.com/amadou-6e/laomedo/issues/251), [specification PR #411](https://github.com/amadou-6e/specs/pull/411), [setup](setup.md) and the [implementation plan](implementation-plan.md).

Each account uses an account-owned private GitHub App created through the one-time setup screen, or a deliberately supplied fine-grained token. Secrets remain in Windows credential custody. Repository access is revalidated for private reads, and a successfully rotated credential remains fenced while GitHub is unavailable. Duplicate registration returns to the existing connection without silently changing its App or method; GitHub may already have created an extra App, which the user can remove there.

A real GitHub App registration, callback and repository selection succeeded in an isolated preview. Duplicate registration and outage recovery have synthetic test coverage; live token rotation, token entry, private Skill reads and the broader lifecycle remain unverified. These are not claims of end-to-end acceptance.

Reviewer status: Claude reviewed the connection core, authentication, frontend, private Skill integration and their tests in bounded packets against PR base `bf5165b2d7658899adaaa335f977b777d507f76b` and heads through `2c5ef244843fffca61e542c26bd7d3b4a9479c21`. Corrections after that head require a focused recheck; whole-PR review and live acceptance remain incomplete. See the PR for the current reviewed revisions and verdict.

## Code ownership

- `src/laomedo/github/connections/`: connection records, OAuth, repository access, provisioning, journal and service.
- `src/laomedo/github/connections/skills/`: owner-bound private Skill reads and storage.
- `src/laomedo/host/credentials/github/`: Windows credential custody.
- `src/laomedo/integrations/langflow/authentication/`: local browser admission, callbacks and response fences.
- `frontend/langflow-skill-viewer/githubConnections/` and `skills/private/`: Settings and private viewing controls.

The journal, vault, private session and response-release fences must remain bound to the authenticated profile and exact connection generation. The broker never silently falls back to ambient Git credentials or the public registry for a private source.
