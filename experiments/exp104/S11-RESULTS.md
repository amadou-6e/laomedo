# EXP-104 S11: mediated runner-loss live result

Status: **passed the bounded Windows no-model S11 protocol**. The single-use
identity `exp104-s11-20261008-01` ran once at reviewed source
`d0d3b25a06835c701a5e294b27eeebfef1d0cdae`, against only the disposable
repository `ga84jog/laomedo-exp104-disposable-20261007` (ID `1408647759`).
No model turn was used and no ambiguous write was retried. The remote refs and
PRs remain in place for audit.

## Committed evidence

- [Raw observation](S11-OBSERVATION.json): SHA-256
  `ea7aa7c1b11f6f9a81b33e94ff264b4e632bcb8973d7f28871055adfc057c817`.
- [Provider-attempt journal](S11-PROVIDER-ATTEMPTS.jsonl): SHA-256
  `b53387625dccf213d0e53d490855fbb92b2e787566ffb3f6d62bd20c4299273f`.

Both files were copied byte-for-byte from the private run state after the
probe's exact-token/capability scans reported zero unexpected hits. They were
also screened for user-profile paths, email addresses and GitHub token
prefixes; none were found. The private state and token file are not committed.
The observation names the exact source SHA, review-record hash, host process,
container IDs/labels, events and cleanup results. The journal has exactly
four lines, one per confirmed provider mutation.

## Acceptance assessment

| Check | Observed result |
| --- | --- |
| Intended writes | One setup branch push each for A and B, then one PR create each: four confirmed provider attempts in that order. |
| A before runner loss | [PR #1](https://github.com/ga84jog/laomedo-exp104-disposable-20261007/pull/1) read back with the expected A branch, `main` base and marker. |
| A revocation | Exact A grant revoked for `heartbeat_lost` 4.906 seconds after the recorded runner-kill completion, within the 60-second bound. |
| Post-loss negative write | A's one PR-update request returned HTTP 403 `grant_unavailable`, added zero provider attempts, and left the remote PR title unchanged. |
| A container cleanup | Exact labelled A container removal was verified; the cleanup result reports `removed_after_loss`. |
| B continuity | [PR #2](https://github.com/ga84jog/laomedo-exp104-disposable-20261007/pull/2) was created **after** A revocation with the expected B branch, `main` base and marker. B's grant was then revoked on normal finish and its container absence verified. |
| Confidentiality | Agent and persisted-state scans each report zero unexpected exact token or capability hits. |
| Compute | Zero model turns. |

The approximately 4.9-second interval before A revocation remained an
exposure window; this run did not try to write during it. The probe's denial
check is after exact grant revocation. This result supports the Windows
no-model runner-loss property for this pinned mediated path, **not** production
service-manager installation, service double failure, literal `git`/`gh`
capability parity, or real-agent timeout/cancellation. Keep #93, #100 and
the Q11/#22 real-agent gate open for those separate claims. The three
remaining authorized model turns were not spent.
