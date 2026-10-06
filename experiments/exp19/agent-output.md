# EXP-19 bounded issue report

**Selected issue:** https://github.com/amadou-6e/laomedo/issues/49  
**Issue body digest:** `sha256:24fd4e512649b6c7436ab796d6f04f1c059a4761290cf5e2637fa932ea2cb23b`  
**Graph snapshot ID:** `sha256:089d4c23050a6e0304d147fa90b360d9334a2b66485e47896a0b4f76ba66f9d8`

## Testable requirement

For one bounded local run, the host-published PR must contain the agent-authored changes from the selected run artifact, and the linked Work Graph run binding must include the selected work key and source marker, graph and input digests, run and trace IDs, native thread reference, artifact and commit hashes, and published PR URL. Published commit contents must be compared with the selected run artifact; a local branch alone is not evidence of publication.

## Remaining limitation

This local host-published path does not establish that an agent-originated push-capable stage passed the deferred EXP-18 safety gate. It is not proof for direct push by an agent, a hosted service, or multiple users.
