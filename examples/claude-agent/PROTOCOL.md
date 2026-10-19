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
