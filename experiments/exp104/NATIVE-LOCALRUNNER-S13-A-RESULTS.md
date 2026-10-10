# Production LocalRunner S13 A results

One independently pre-reviewed capture, identity
`exp104-localrunner-s13-20261010-a`, executed once at source
`2bde4340717140b53b96da012d26428e632a4cae`. Protocol was committed at
`a5b38c2` before executable source. Governing specs
`3f731a5a168cd6bb39da6fa273b53fe4469e94d9`. All four source CI jobs passed;
546 local tests passed, 11 skipped. Original machine evidence is preserved
without reconstruction:

| File | SHA-256 of original/committed bytes |
| --- | --- |
| `native-localrunner-s13-a-observation.json` | `9f2b0e04ad56eb52a6d84b9ca55fc4378552076a4f6bf939b2a992c64f09eeec` |
| `native-localrunner-s13-a-provider-attempts.jsonl` | `c21a24bc259a8fc08dd6dd6bc21c554b2087d4b08d47887092a1ec5cd8a166b6` |

The journal retains its original CRLF bytes through an explicit Git attribute.
It has eight entries, including reads, and exactly four mutations in order:
A push/create, B push/create. Direct host preflight and audit readbacks are
outside that journal. No ambiguous write or consumed identity was replayed.

## Observed boundary

Both real LocalRunner instances completed construction before preparation
began. Real `_prepare` consumed authority references and installed an actual
pinned fixture skill; real `_execute` persisted the running record, exact
container/lease/grant metadata and launched through `_open_server`/AppServer.
The fixture subclass held after the **real native initialize response**, and
refused every other request. Native Git received no controller trust override:
`/draft` trust came from the production Docker launch. Skill exclusion digests
stayed unchanged. Commands were controller-driven, not autonomous agent work.

A's tree kill completed at 93191.796 host-monotonic seconds. The independent
lease service recorded revocation at 93196.750, a delta of **4.954 seconds**.
At 93197.562, the retained A capability returned403/grant_unavailable;
provider entries stayed6→6 and A's PR title/body remained unchanged. B's
grant was still active and its create intent was recorded at93198.375,
after the denial, followed by an exact PR readback.

The managed host and verifier task PID sets stayed identical and heartbeats
advanced. Exact A/B container, grant, worker, task and verification-stage
cleanup all passed. The controller deliberately released B into a pre-turn
fixture failure during cleanup; that is not an agent completion or cancelled
model turn. Private roots and remote PRs/branches remain for audit.

Zero model turns: the local ledger stayed absent/zero, only initialize was
allowed, and the shared model ledger stayed byte-identical. The exhausted
12-entry shared budget was not enlarged or consumed by this capture.

## Limits

This supplies the bounded **production LocalRunner launch and mediated
runner-loss** evidence that S12's scripted workers could not supply. It does
not prove a model's delivery/PR assessment, Q11 timeout/cancellation, all Git/gh
capabilities, Linux/logout/double-manager survival, browser-login production
or any global absence of effects. No write was attempted during the detection
window before revocation; that window still permitted possible writes.

Persisted runner/stage scan:118 files, zero exact provider-token/capability
hits. Public original files also contain no exact token/capability or private
host path. This is not a memory/network/exfiltration audit. The production
container mounted the persistent Codex profile volume (possibly containing
the model login); the scan does **not** cover that volume. Public `token`
fields are container ownership nonces/labels, not GitHub tokens or mediator
bearer capabilities. Native event and running-record hashes refer to private
capture-time bytes; those full private records are not public evidence.
Read-only post-run inspection found that both native event hashes match the
first 412 bytes of their retained logs. Each final log is 523 bytes after later
`remoteControl/status/changed` and `account/updated` notifications; the hashes
are not whole-final-log hashes. No thread or turn request was sent.

Independent post-run evidence/promotion assessment is pending. Keep #105/#97
draft and #100/#104/#93/#22/Q11 open until their actual scope is accepted.
