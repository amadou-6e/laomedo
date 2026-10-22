# Real Claude proposal verification

Authorized by the user's request for a Claude node and explicit selection of
Claude Code subscription on 2026-10-19. Use the normal official CLI login in
place, without copying or reading credential files. Keep the reviewer session
separate from the node's new native Claude session.

Create a real new workspace-guide skill with a missing description. Run the
actual native Langflow two-node Skill -> Claude -> Skill feedback graph. Use
Claude Code 2.1.301, sonnet, low effort, native tools disabled, pinned skill
snapshots and static output requirements. Permit one initial turn and at most
one same-session output correction. Preserve errors and uncertain dispatches;
do not silently restart, repair JSON or reset the ledger.

Read back the accepted candidate independently. Require only a description line
to differ, exact parent and backend provenance, unchanged canonical/source, and
same-ticket replay without another model or revision. Then permit one additional
native resume turn asking for the previous proposal, without applying it again.
Total campaign ceiling: three turns. A failed resume is not silently retried.
Record native session, pinned skill hashes, host IDs, terminal receipt, output
validation, process cleanup and actual usage fields. Unknown stays unknown.

Internal controls may simulate receipts but are not this acceptance. No fixture
provider or credential access is permitted. Stop the runner and writable host
service afterward. The review preview must use an empty edit-policy map and
clear the edit request. Do not merge before independent review, passing CI and
the user's review of the actual working graph.

## Verification-harness correction (2026-10-21)

The first real edit completed and was host-applied using one turn. Exact byte
readback confirmed a description-only insertion with CRLF preserved. The original
verifier compared normalized LF text with raw CRLF and used an overescaped regex;
its finally block stopped the runner before resume. Preserve that successful
run, its native receipt, commit and the harness error. Do not replay its task.

Use the remaining two turns for a new explicitly requested description revision
and one resume of that new session. Preserve the original completed run and
unchanged ledger (total ceiling still three). The old run is not reattached to a
new runner instance. If the new edit needs a correction, it consumes the last
turn and resume remains unverified; never dispatch a fourth turn. Compare exact
bytes, write exported accepted bytes without newline conversion, and disable
writable services after this case.
