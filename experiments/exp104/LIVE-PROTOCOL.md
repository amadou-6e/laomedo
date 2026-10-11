# EXP-104 live mediated-grant revocation protocol

Status: frozen protocol; **no live run has occurred**. Issue: Laomedo #104.
This protocol is independent of the existing EXP-93 synthetic records. Any
change to its cases or acceptance rules needs a committed, dated amendment
*before* the affected run. Developmental unit tests are not campaign evidence.

## Preconditions (all mandatory)

1. Use only `amadou-6e/laomedo-exp15-disposable` or a newly named disposable
   repository authorized by the user. Record repository ID, baseline refs and
   issue count. Do not delete or overwrite pre-existing refs/issues.
2. Use a newly provisioned, repository-scoped GitHub App installation token
   or fine-grained token with only the permissions this probe needs. Its
   reusable source stays in the credential-owning service; neither agent
   container nor trace receives it. The ambient `gh` login is forbidden.
   Record issuer, repository scope, permissions and expiry **without token
   bytes or token hash**. Refuse if the identity cannot be independently
   verified or revoked.
3. Review and merge or explicitly authorize running against specs #150 and
   #250 and implementation drafts #97, #103 and #105. Pin all governing
   commits and the tested implementation commit before the first call.
4. The independent lease service must be launched outside the runner's
   process tree and have its own failure boundary. Verify its PID/identity,
   private state path, and startup sweep. The credential-owning mediator
   must refuse unknown grants and fail closed if the lease binding is absent.
5. No model turn. Use deterministic synthetic requests. Stop on any failed
   preflight; do not substitute a personal token or an unreviewed API path.

## Cases, in order

1. **Control:** Create two distinct run grants A and B for the same disposable
   repository, each bound to a different lease and branch. With A, push a
   uniquely named new branch containing a harmless marker commit; with B,
   perform a scoped read. Capture provider responses, exact refs, mediator
   effect journal and lease identities. Do not reuse an existing branch.
2. **Runner loss:** Kill the exact runner process tree once, while its lease A
   and service remain alive. Do not kill the independent service. Capture the
   service's observed loss, grant revocation time, and exact-container state.
   Do not retry an ambiguous write. After revocation, attempt one *new*
   unique-branch push using A's same capability; it must be denied by the
   mediator before a provider call. Independently read the remote ref to
   confirm no new A branch appeared. Grant B must still permit its approved
   operation. Capture both results and their timestamps.
3. **Service restart:** If the first two cases pass, stop and restart only
   the independent service. A previously accepted grant must remain denied;
   no old lease is adopted or renewed. A new run C can be admitted only after
   a new durable authorization. Capture the startup sweep and exact identity.
4. **Negative controls:** A missing run record, mismatched repository/branch,
   expired grant, revoked grant, and workflow-file write without separate
   approval each fail *before* any provider call. A lost response remains
   `unknown` and is never automatically resent. These may use fake transport
   where real GitHub would create undesirable duplicate effects; label each
   transport used.

## Acceptance and measurement

- Every writable grant and lease binding is durable before dispatch. The
  provider credential is absent from container mounts, environment, raw
  events, HTTP responses and committed evidence; a synthetic canary scan is
  required. No token value or token hash is committed.
- A's post-loss write is refused within 60 seconds of runner loss and before
  any provider transport call. B remains usable. Exact container cleanup is
  separately verified; stopping a container alone does not count as grant
  revocation. Any service-detection window where writes remain possible is
  measured and reported, not hidden.
- Records include monotonic host timestamps for request, runner loss,
  service detection, revocation, provider call (if any), denial and remote
  read-back. Record wall-clock offset if comparing another host/container.
- Each mutating call has a durable effect ID and request digest *before* the
  call. Unknown outcomes never trigger automatic resend. No write is attempted
  twice after a timeout or lost response.
- Retain sanitized raw observations and a derived result with SHA-256 hashes
  of the **committed bytes**. Include a negative-control assertion that would
  fail if a revoked grant reached the provider. Count actual provider calls.
- Leave probe-created refs in the disposable repo for review unless cleanup
  is separately authorized; report their names and whether they can be
  removed. A failure or missing observation is a failed/inconclusive gate,
  not a pass. No real-agent turns are spent under this protocol.
