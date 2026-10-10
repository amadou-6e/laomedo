# EXP-100 S12 real-provider result, 2026-10-10

One consumed identity: `exp100-live-s12-20261010-a`. Result **passed**.
Original machine capture: [LIVE-OBSERVATION.json](LIVE-OBSERVATION.json),
SHA-256 `54f45affa640cebfe995942152f9923300e8ecd16d3cfdf4fda70a01647a3b13`.
The committed copy was compared byte-for-byte with the original probe file;
tests never overwrite or rerun it. No discarded live attempt or POST retry.

## Provenance

Owner explicitly approved one reviewed issue-create in the disposable repo
and read-only public Laomedo Actions access. [Protocol](LIVE-PROTOCOL.md)
was committed `0aeacce` before implementation. Prospective
[visibility amendment](LIVE-AMENDMENT-01.md) was committed `c5f5997` before
its fixed five-second pause was implemented or any live attempt.

Initial pre-run source `93816f5` was independently disapproved: nonexistent
cleanup column and unnecessary old-run membership on page one. Both and
three advisories were fixed before capture, with seven synthetic helper tests.
Executed source: `76902618cb6e0319b3f9752672911786aa46d7e4`, independently
[pre-approved](https://github.com/amadou-6e/laomedo/pull/143#pullrequestreview-5479294097)
after [initial disapproval](https://github.com/amadou-6e/laomedo/pull/143#pullrequestreview-5479275992).
All four exact-head CI jobs passed; clean state and 14 local-byte hashes matched.
No production mediation/permission change in this continuation.

Manifest SHA-256: `ee22192232b88375724d5ef7559ed2fa7ca09c08979ec0594a16d2876a1cd1fd`.
Source hashes describe exact local checkout bytes at capture, not an assertion
about Git line-ending conversion on another platform. Governing specs:
`04fade6d88cc4c6d5c494c7e566c5cacbad93b09`. Pinned image:
`sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.

## Machine-recorded checks

| Check | Actual result |
| --- | --- |
| Real PR list | Six items at preflight; selected number/title/body/state matched independent host HTTP baseline |
| Issue/GraphQL preflight | Both empty before creation; GraphQL capacity available; not presented as positive item parsing |
| Repository REST read | Native mediated `gh api` branch read matched real HTTPS baseline |
| Public Actions | Nonempty overlapping current listings; exact job `114224703478`, run `38056050461`, completed/success matched baseline |
| Unsupported and credential-export commands | Exit2 `unsupported_command`, zero provider calls |
| Wrong repository | Adapter exit2 `repository_mismatch`; host binding `connection_unavailable`, zero calls |
| Altered reviewed request | Exit3 `mediator_denied:issue_review_denied`, zero calls |
| Exact issue create | One POST, HTTP201; issue7 has exact reviewed title/body/marker |
| Positive issue view/list/GraphQL | Exact created issue found after fixed pause; issue lists exclude PR objects; baseline readback matched |
| Confirmed saved-request replay | Same issue7, zero provider calls; host replay, not literal CLI retry |
| Revocation | Exit3 `mediator_denied:grant_unavailable`, zero calls |
| Credentials | Actual inspected environment KEYS and mount DESTINATIONS contain no GitHub token/config; selected token remained host-side |
| Cleanup | Both exact labelled containers removed, both grants durably revoked/renewal refused, verified in1.625s |

17 cases, 18 total real provider attempts: **17 reads and one issue POST**.
The GraphQL POSTs are fixed read-only queries counted as reads. No real
Git push, PR mutation, workflow edit, service install or model turn. Issue
[ga84jog/laomedo-exp104-disposable-20261007#7](https://github.com/ga84jog/laomedo-exp104-disposable-20261007/issues/7)
is left in place; no edit/delete/close was authorized or performed.

Durable effect: run `exp100-live-s12-20261010-a-disposable`, grant
`4763e88b71124c45d9e526e917092a7c`, operation `issue_create`, state
`confirmed`, request hash
`17feef05070877b26199ed687b48fa71203ad9e0cc80da81e34c7c5c9e9bab5b`.
Its hash identifies the full reviewed request, not a caller's proposal label.

## Limits and acceptance

Real production CLI/client/store/host transport over HTTPS, compared to a
host HTTP semantic baseline using the explicitly selected credential. This
is not a full upstream high-level gh command/output comparison, exhaustive
permission proof, paging or large-data acceptance. Fixture counts are not a
claim that arbitrary future repositories fit the 30-node GraphQL limit.
The host cross-repository refusal tests connection binding; repository-only
refusal is not independently isolated. It makes no egress/hostile-code claim.

Only selected normalized fields/IDs, output hashes, safe call paths/statuses,
known reviewed issue bytes, inventory and durable attribution are retained;
arbitrary provider bodies/headers and credentials are not published. The
runtime baseline comparisons fail closed on mismatches; not every baseline
payload is separately archived. Five-second visibility is not a guarantee;
a lag would consume an incomplete attempt without retrying the POST.

S10 acquisition, S11 paired synthetic controls and accepted #104 service-loss
evidence remain separate; this capture does not re-prove them. Independent
post-run assessment and merged specs evidence are still required before #100
closure. #22/Q11/#93/#97 remain separate open gates.

Post-capture integration note: the
[independent post-run review](https://github.com/amadou-6e/laomedo/pull/143#pullrequestreview-5479313106)
approved the evidence and original selected #100 closure after integration.
The canonical evidence specs merged in
[specs #344](https://github.com/amadou-6e/specs/pull/344) as
`56642addc7b634b41ea4cc9808124438f239e24b`, at
`projects/laomedo/subsystems/agent-execution/validation.md`, section
"EXP-100 S12 real-provider integration, 2026-10-10". The earlier assessment
paragraph describes the gates at initial report creation, not a new experiment.
This note changes no original observation, executed source, manifest or criteria.
