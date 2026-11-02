# EXP-139 bounded live checkpoint, 2026-10-11

This first result remains unchanged below. The later owner-approved recovery,
its three additional live turns, exhausted 4/4 ledger and remaining publication
barriers are recorded in [RECOVERY-RESULTS.md](RECOVERY-RESULTS.md).

**Blocked, not a successful draft-PR demonstration.** The durable ledger is
**1/4 submitted turns**, with zero push attempts and zero PR attempts. No unknown
provider operation was retried. See [OBSERVATION.json](OBSERVATION.json).

Execution source: [1477034](https://github.com/amadou-6e/laomedo/commit/1477034cdbce24b277334e9754c1899fcd03e52d),
manifest SHA-256 `c4d9be2b80d3cc1f3c9b75a05b870acbef12db684db299ecfbdb5c67cd6b9253`.
The owner approved the concrete two-process deployment, original permissions,
existing Codex subscription profile, four submitted turns, and at most one push
plus one draft PR in the named disposable repository. Claude approved the own
diff at `91528e9` and the substantive transport correction at `1477034` before
activation. It read source/diffs but did not independently run the tests or
compute the prepared-input hashes.

## Preparation and controls

Host-held scoped reads obtained an existing issue and baseline; no issue was
created or edited. The first network-disabled run of the real prepared graph
found altered JSON escapes in a multiline issue body. AMENDMENT-02 records the
prospective correction: base64 UTF-8 transport, strict decoding and unchanged
canonical context verification. Only the three exports were rebuilt, without
re-fetching the issue or baseline. All three actual agent requests then matched
their host-approved digests in a credential-free pinned Langflow run.

The preceding host head passed 638 tests with 11 skips. The corrected imported
graph passed three pinned-runtime tests, including all four negative outcome
variants and exact multiline/non-ASCII round-trip. Seven focused host binding and
durable-write-budget controls passed. The service initially refused startup
because its private boundary directories did not exist; creating those approved
directories resolved this before any model submission.

## Actual live outcomes

| Case | Observation | Route and external effects |
| --- | --- | --- |
| Intended success | One completed native turn; two bound precheck calls, first missing-report rejection then correction/acceptance; exact report bytes created; Git config/index-lock writes denied by the original sandbox | Agent honestly returned task failure; downstream contract accepted the failure form and routed to failure; controller handoff rejected; zero push/PR attempts |
| Deliberate failure launch | Refused before model submission: a mediated supervisor requires a GitHub scope, but this case deliberately has none; lease result says `mediated_lease_request_invalid` | Runner reports `lease_service_unavailable`; graph routes to rejection; no assertion that the intended real-agent failure case passed |
| Downstream pin rejection | Not run live | Credential-free control only |

The first run closed nine native item identities and one turn, retained its
snapshot, and verified controller/container cleanup. `evidence_complete=true`
means retained native execution evidence closed; it does not mean task success.
The report SHA-256 equals the frozen expected digest
`3de179af048ab7823ab1a088459309e802b5a0253263718a8ce33f911eb3a49b`.
No commit or push was made. The expected draft PR therefore does not exist.

## Recovery proposal and cleanup

[RECOVERY-DRAFT.md](RECOVERY-DRAFT.md) presents the two configuration corrections
for approval. A credential-free sandbox control reproduced original Git-metadata
write denial and showed that an explicit `/draft/.git` write rule permits config
and index-lock writes while still denying the dummy auth-file canary. It used no
real login and no network. This draft was not activated.

The first run's GitHub grant is revoked. Its lease reports cleanup verified;
the refused second launch's lease reports cleanup unverified, while the runner
record reports cleanup verified and no native items or model turn. Do not treat
those as equivalent evidence. Both exact new host process trees were stopped,
port 8779 was released, and no campaign-labelled graph containers remain. All
workspaces, partial evidence and the original ledger are preserved outside Git.

Live success publication, intended deliberate agent failure and downstream pin
rejection remain unverified. Raw traces and login state are not committed.
The infrastructure refusal selected rejection because the missing submission
failed the form check before execution recovery was considered. The intended
non-completed-execution recovery priority remains a design gap under #139.
An in-memory scan of the proposed EXP-139 evidence/source and exact report file
found no match for the selected GitHub token, runner API token or current stored
Codex login values. This scan did not export credentials, inspect historical
rotated token values or scan private raw transcripts. There is no published PR
to scan.
The GitHub credential stayed on the host; Codex login custody remains the
explicitly accepted local container profile, protected by its sandbox auth-file
deny. No hosted or multi-user isolation claim is made. Blockers remain owned by
[Laomedo #139](https://github.com/amadou-6e/laomedo/issues/139); it is not complete.
