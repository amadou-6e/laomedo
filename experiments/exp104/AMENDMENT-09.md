# EXP-104 amendment 09: freeze the D2 live runner-loss probe

Date: 2026-10-07. Status: frozen before the first mediated Git push.
Applies only to diagnostic `EXP-104-D2`; the original scoped-identity
acceptance protocol and its open gates remain unchanged.

Setup produced baseline `1f1a505f2fbd31993a7946924a9bec5a27bb15c1` by
the one-shot README request permitted by amendment 08. Its response confirmed
the new file and commit. No probe branch has yet been pushed.

The probe implementation is `live_probe.py` at the commit containing this
amendment. The invocation must pass that exact commit SHA as `--code-sha`;
the script refuses another head. It must use a new private state directory
outside all checkouts and a new observation path. The script freezes a plan
with the exact local commit and all identities before contacting the mediator.

Fixed identities and scope:

| Item | Value |
| --- | --- |
| Repository | `ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`) |
| Connection | `exp104-d2-selected-gh`, generation `1` |
| Run prefix | `exp104-d2-20261007-01` |
| A branch | `exp104-d2-20261007-01-a` |
| B branch | `exp104-d2-20261007-01-b` (read-only run; not pushed) |
| C branch | `exp104-d2-20261007-01-c` (post-restart read and workflow control; not pushed) |
| Container image | local `sha256:bb8009c87ab69e751a1dd2c6c7f8abaae3d9fce8e072802d4a23c95594d16d84` |

The ordered live cases are: independent mediator and lease-service startup;
trusted A/B approvals and exact labelled containers; one confirmed A branch
push and B same-repository read; one exact A runner-tree kill; lease-detected
revocation and exact A container cleanup; one fresh A effect on the **same**
approved branch, refused as `grant_unavailable` before provider transport;
remote SHA read-back and B continuity; lease-service restart that rejects old
B and accepts a freshly approved C read. The service restart does not restart
the mediator. No model turn or issue/PR write is permitted.

Before the only live push, the same grant must reject a wrong-branch request
without a provider attempt. After restart, the C grant must reject an
unpushed workflow-file commit and a mismatched repository without a provider
attempt; an unrecorded lease must not be authorized. Expiry and ambiguous
lost-response controls use an isolated synthetic ledger and fake transport,
never GitHub. A provider-attempt journal and remote ref read-back are the
revocation controls. A response of `unknown` or any failed preflight ends the
run; it is not retried. The probe leaves its Git branch for inspection.

Passing these cases would be **bounded diagnostic evidence** only. It would
not establish a repository-scoped credential, production browser/token
custody, a real agent turn, UI Stop behavior, or first-slice Q11 acceptance.
