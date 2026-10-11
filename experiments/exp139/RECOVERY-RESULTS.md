# EXP-139 recovery result, 2026-10-11

**No-go for live draft-PR acceptance.** Failure and rejection routes passed
through actual imported Langflow graphs with real Codex turns. Success publication
remains blocked. This does not complete #139 or permit an extra model turn.

The owner approved AMENDMENT-03 and then the concrete AMENDMENT-04 startup
correction. Claude approved each activation before execution. Final executed
source was `fc44d7edfb77519b4f4c0d8ef589606d424a232f`, manifest
`3554dad38921b21a1c695faa80897baf200adcf5bf4790e959f8cd2813a068d0`.
This is distinct from the later observation-writing source. See the preserved
[first result](RESULTS.md), [first observation](OBSERVATION.json), dated
[amendment 03](AMENDMENT-03.md), [amendment 04](AMENDMENT-04.md), and the
machine-written [recovery observation](RECOVERY-OBSERVATION.json).

## Actual cases

| Case | Native execution | Downstream graph | Publication |
| --- | --- | --- | --- |
| Fresh success task | One turn, 13 closed items, exact report bytes, precheck rejected missing report then accepted correction in the same request; final form reports task failure | Contract accepts the failure form; conditional route selects failure | No push or PR provider attempt |
| Deliberate task failure | One turn, four closed items, accepted failure form, ordinary non-mediated supervisor | Contract accepted; failure route | No GitHub grant or publication |
| Contract pin mismatch | One turn, four closed items, successful agent form and accepted agent-side precheck against its original requirements | Downstream contract rejects its mismatched pin; rejection route | No GitHub grant or publication |

All three fresh runs closed native execution evidence, snapshots and controller
cleanup. Both supervisors report verified container cleanup. Evidence closure
establishes retained execution evidence, not task success. The third precheck in
the fresh success task accepted its final failure form; it is not another model
turn. No continuation retry was submitted. No PR reference or published report
readback exists.

AMENDMENT-03 also produced a setup refusal before any model turn, run
`7391913c-318f-4317-8c68-fda10b84769d`. The nested CLI override did not form a
valid permission configuration. AMENDMENT-04 replaced its encoding with a full
inline table preserving root read, workspace write, exact auth-file deny,
network disabled, approval policy never and only the approved `.git` write
addition. Credential-free exact-invocation startup and dummy-auth sandbox
controls passed before activation. Three consumed identities and the original
failed records/configuration/exports were retained; nothing was reset.

## Remaining publication blockers

The fresh success task reached Git commit but its push command exited 128 with
`git: 'remote-laomedo' is not a git command`. A Python command had separately
exited 127 because Python was not installed in the agent image; the agent used
another shell command to create the report and continued. This recovered file
creation problem is not the publication blocker.

The live observation proves helper discovery failed; the exported command
metadata does not establish whether that invocation used a login shell. Login-shell
PATH loss below is a reproduced mechanism and likely cause, not an observed
live-shell identity. The observation's helper-path blocker label names that control.

The credential-free [helper control](helper_control.py) and its machine-written
[results](HELPER-CONTROL.json) distinguish two barriers:

1. A plain shell discovers the mounted helper. A login shell drops it from PATH.
   An explicit Git exec path discovers the dummy helper. This establishes helper
   discovery only, not a successful mediated Git push or a deployed fix.
2. The temporary host 404 fixture is reachable outside Codex's command sandbox.
   The exact network-off sandbox instead reports `EAI_AGAIN` for the same
   `host.docker.internal` route. This tests the selected hostname/DNS route; it
   does not prove every numeric-address path is denied. The live push did not
   reach this second barrier, since helper discovery failed first.

These blockers remain with [#139](https://github.com/amadou-6e/laomedo/issues/139).
Do not silently enable network access, replace the scoped mediator with direct
GitHub credentials, execute agent-controlled Git configuration on the host, or
retry an unknown write. A reviewed helper-discovery and mediator-reachability
solution, its required configuration approval and a new numeric model cap are
needed before another success campaign.

## Limits and cleanup

The campaign ledger is **4/4**, including the original turn, with zero push and
zero draft-PR provider attempts. All issued GitHub grants are revoked. Only the
two owned recovery process trees were stopped; port 8779 was released and no
campaign-labelled graph containers remained. Workspaces, raw traces, consumed
digests, write budget and configuration history remain private outside Git.

The GitHub token stayed on the host. Codex login custody is the explicitly
accepted local container profile with its sandbox auth-file denial. Dummy-auth
controls are not an audit of every real credential access route. No hosted,
multi-user or private-client subscription-eligibility claim is made.

Verification: 643 host tests with 11 skips passed before AMENDMENT-04 activation;
12 focused recovery controls and all three actual prepared request-digest checks
passed. Final executed-head CI passed after one rerun of the pre-existing Git
maintenance-lock race; both initial failed jobs remain visible. No additional
model-backed verifier was used. The result-writing helpers do not re-execute an
agent and never export raw answers or traces.

The exporter has a credential-free regression proving that private answer,
precheck payload and extra metadata contents are omitted. All 13 focused
recovery/export controls passed. An in-memory scan of proposed EXP-139 source,
evidence and all campaign report files found no matches for the selected GitHub
token, runner API token or current stored Codex login values. No credential
values or credential hashes were printed or committed. Historical rotated
values and private raw transcripts were not covered; no published PR exists
to scan. Existing servers and saved flows were not changed.
