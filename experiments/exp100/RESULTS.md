# EXP-100: first credential-free mediator slice

Issue: https://github.com/amadou-6e/laomedo/issues/100. Protocol was
committed as `0991d04` before implementation. Probe code was committed as
`cac03fa` before the recorded run. The recorded [observation](observation.json)
has SHA-256 `1d1d1f7c34ad3e0cf80946d9427629487719de2440d3cfe4375d92bf91ef6322`.
Earlier development runs were not recorded as evidence. No model turn, real
GitHub write or personal credential was used.

## Candidate comparison and selection

| Concern | Laomedo operation broker (selected for next slice) | Git transport + API proxy (not selected yet) |
| --- | --- | --- |
| Credential custody | Credential stays in broker process; agent gets revocable run capability. | Credential stays at proxy, but unmodified `gh` needs a way to route every API request there without exposing a token. |
| Git fetch/push | Broker performs a fixed operation on the granted workspace/repository. Must isolate hooks, config, remote URL, signing and race with agent edits. | Git remote helper or HTTP transport proxy could preserve ordinary Git syntax, but pack protocol, endpoint routing and proxy authentication add substantial work. |
| `gh` commands/API | Adapter must deliberately support command flags, stdin/body files, response and exit-code fidelity. Arbitrary extensions/aliases cannot safely inherit broker credentials. | Closer to unmodified `gh` if routing works; HTTPS/TLS, redirects, arbitrary endpoint authorization and credential export remain hard boundaries. |
| Revocation/audit | Validate each call and persist intent before mutation; denial is visible. | Validate each HTTP/Git request and persist intent before mutation; multi-request commands complicate effect identity. |

The first implementation direction is a Laomedo-owned broker with a
credential-free stage adapter. This is a **direction**, not a parity pass:
the current adapter accepts normalized operation names, not literal `gh` or
general Git command syntax. A real `gh api` call can use GraphQL, arbitrary
methods, input files, field expansion, pagination and output transforms; the
synthetic probe does not implement those semantics. The official
[GitHub CLI API manual](https://cli.github.com/manual/gh_api) confirms that
surface. The [Git remote-helper protocol](https://git-scm.com/docs/gitremote-helpers)
is a plausible alternative to the broker's fixed Git commands; it has not
been prototyped. `GH_TOKEN` would be consumed directly by `gh` and override
stored credentials according to the [CLI environment manual](https://cli.github.com/manual/gh_help_environment),
so it is not an acceptable stage-side shortcut.

## Observed matrix

- Ordinary local Git produced a commit; the broker ran real `git push` and
  `git fetch` against a temporary bare repository. The pushed branch resolved
  to the local commit. This is local Git transport, not GitHub authentication.
- Synthetic PR and issue create/list, Actions read, REST read/write and
  GraphQL read/mutation returned the expected effects. No real `gh` process
  executed. Unsupported `auth_token` returned 403; wrong repo, unknown grant,
  denied operation and expired grant also returned 403.
- The deliberate lost-response mutation reached the synthetic upstream once,
  but both the first response and same-key repeat stayed `unknown`. A changed
  request with that key returned 409. A confirmed same-key repeat returned its
  saved result without resending. The same effect ID belonged independently to
  another run. The upstream effect counts verified these results.
- A direct synthetic orphan revocation denied the next run-A call in 0.125 s;
  run B still read successfully. This does **not** test a runner whole-tree
  kill, grant revocation on an actual supervisor event, or denial of a real
  GitHub write after such a kill. The 60-second production gate remains open.
- The child environment explicitly removed GitHub token variables; none were
  set in the host environment during this run. Container mounts and hostile
  same-user processes were not inspected. A random stand-in secret existed in
  broker memory only, but no external service checked that secret.

## Q16 proposed rule, not yet accepted

An effect ID is scoped to a run and names the full canonical mutation
request, not one network attempt. Persist identity and intent before sending.
An identical repeat returns the saved confirmed result or `unknown`, never
resends automatically; changed payload conflicts. A timeout/crash/lost
response is `unknown` even when a read fails to locate the effect. Reconcile
read-only by an exact marker or branch/ref identity where available. A known
non-creating rejection may be `failed`. Generic `gh api` mutations have no
automatic safe retry. After unresolved uncertainty, only an explicitly
authorized new attempt may write again. This deliberately does **not** claim
exactly-once GitHub effects. The rule must be reviewed in the specs decision
record before any implementation claims safe retries.

## Next integration gates

1. Define and test literal `git`/`gh` invocation compatibility, especially
   `gh api` input files/stdin, GraphQL mutations, output/exit codes, Git hooks,
   signing and agent-controlled Git config. Reject credential-export paths.
2. Choose a broker service parent independent of the runner on Windows and a
   systemd unit outside the runner control group on Linux. A Windows child
   process group did not survive a whole-tree kill in EXP-93. Persist grant
   ownership before dispatch; revoke on owner death/lease expiry independently
   of container teardown. Test real whole-tree kill and late container start.
3. Test with a scoped, disposable GitHub identity/grant and actual GitHub
   operations. Verify revocation and a denied post-kill write, without using a
   personal token in the stage. Keep #93 draft until that gate passes.
4. Review Q16 with the owner of the specs checkout; at the recorded run it
   had uncommitted work on another branch, so this probe does not alter it.
