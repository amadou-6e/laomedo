# Configuration approval draft: AMENDMENT-05

This draft is not activation. The owner has approved increasing the turn ledger
to ten total; the four used turns are preserved. Six remain. The new startup
below needs explicit approval after exact-source Claude review.

Changes from the last stopped configuration:

- Replace only this campaign's read-only mediation client mount with the
  file-mailbox client, and mount the trusted relay source read-only.
- Start the relay inside the owned Codex container before the app-server, with
  an exclusive readiness file. The relay forwards only to the existing fixed
  host mediator endpoint using the run capability, never a GitHub credential.
- Set `GIT_EXEC_PATH=/run/laomedo/bin` for this invocation so a login shell can
  find the read-only helper. No user or machine environment is changed.
- Apply the separately prepared AMENDMENT-05 config/exports, with one fresh
  success-request and grant identity. Archive AMENDMENT-04 configuration, exports,
  activation and results before replacing any of those files.

Unchanged: filesystem root read, workspace write, `/draft/.git` write, exact
Codex auth-file deny, command network disabled, approval policy never, pinned
images, existing subscription profile, disposable repository and branch, host
GitHub token, 600-second handoff, port 8779, independent host services and runner,
one experimental push and one draft PR attempt. Existing servers and saved flows
are untouched. Preserve every consumed request, revoked grant, write-budget row,
raw trace and workspace. No ambiguous write is retried.

After approval and exact final-head CI, start only these owned hidden services
and run the fresh success graph. A failure consumes its submitted turn and is
preserved. Stop on an unknown provider outcome, expired/revoked grant, missing
native closure or exhausted cap. The already-passed live failure/rejection cases
need not be resubmitted. Cleanup leaves evidence and any test PR/branch for review.

Credential-free Docker network-none controls establish the candidate relay,
helper discovery, direct TCP denial and dummy auth-file denial. They do not prove
the actual Windows host route or draft-PR publication. Those remain live gates.
