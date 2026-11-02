# S11: bounded paired Git/gh comparison

Single-use identity `exp100-paired-s11-20261010-a`, executed 2026-10-10 on
Windows after independent pre-run approval of exact source
`2b931242fc34c65746cfb3a98deb118ed821b2a1`. Governing merged specs
`193fdfb2c31e71745943039c05e14d5d72e8309e`; original prospective protocol
`8e219b7` and Amendment 01 `d4a2f14` precede implementation and capture.
The earlier pre-run disapproval was resolved before any capture. This identity
is consumed; it was run once, with no repeat after an uncertain provider effect.

## Original evidence

The probe-generated [observation](PAIRED-OBSERVATION.json) is byte-identical to
its original private capture. SHA-256:
`4165c588ccf3e5251322a4baaa3e8e0d8bb2d30d8753850f8d782acaa715b1af`.
It is not a hand transcription or relabelled earlier run. The reviewed
[manifest](PAIRED-MANIFEST.json) SHA-256 is
`c15b68968444cfe8ec1cfd60aa61f0ef5c16c8f7f10bb40abe900bb78d82126c`.
It freezes local checkout bytes; all 53 entries matched before dispatch.
Source commit and manifest must both be cited: different-platform line endings
can differ from those explicitly frozen local source bytes.

The pinned agent image is
`sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.
Two separate owned run containers and checkouts use read-only capabilities.
The direct side uses installed Git/gh, isolated configuration and an explicit
synthetic credential only to loopback. No real GitHub credential, real provider
acceptance call, model turn or persistent service setting was used.

## Recorded result

The original checker returned `passed` for all 44 required cases:

| Classification | Cases | Meaning |
| --- | ---: | --- |
| equivalent | 18 | Actual direct/mediated exits succeed and selected normalized results match |
| denied | 11 | Exact frozen denial code/exit, no prohibited provider dispatch/write |
| unsupported | 11 | Exact unsupported code/exit, no fallback/provider dispatch |
| different-but-authorized | 2 | Confirmed replay and actual credential inventory; not native output equivalence |
| unknown | 2 | CLI lost response and host-side saved-request replay remain uncertain |

Each side has seven measured writes: two Git receiver updates and five REST
mutations. The direct receiver journal records zero -> first and first -> second
for the run branch. First commit `9547b4ba88d3946a036dcbe7182e7fd0dd5ccdb8`;
second `c13d5d93dceda90ae9e13d4d4b90a0445b1048c4`. Local Git uses separately
recorded output hashes. PR creation/read/correction/list and REST create alias,
issue read/list/exact-reviewed creation, fixed GraphQL issue read, Actions reads
and selected REST reads match the stated semantic baseline.

Eight actual durable effect rows have the expected run/grant/operation/state:
six confirmed, the changed-snapshot correction rejected, and the lost-PATCH
effect unknown. The snapshot-change case permits reads but no PATCH. Altered
valid PR content reaches `effect_conflict`, rather than the issue review gate.
Edited or unreviewed issues refuse before dispatch. Confirmed and saved-unknown
replays issue no new provider request. Revoked A refuses; B still reads afterward.

The lost PATCH was applied once by the synthetic provider before its response
was deliberately suppressed. The journal does not infer confirmation from that
fixture knowledge. Unknown replay is a host-side replay of the identical saved
request, with no invented CLI exit. A literal `gh pr edit` retry would re-read
the changed expected snapshot and conflict safely, not return an equivalent
unknown result. Direct gh did not duplicate the lost PATCH; an additional write
would have failed the frozen per-case and total checks.

Cleanup verified both exact containers, both private verification stages and
both grant revocations. Elapsed `1.9060000000026776` seconds, below the 30-second
acceptance bound. The exclusive identity claim remains consumed.

## Limits and assessment boundary

This is the frozen representative first-slice matrix, not unrestricted git/gh
feature or formatting parity. Direct HTTP commands use `gh api` loopback URLs,
not the high-level native PR/issue internals; the comparison covers authorized
effects and selected fields. The provider does not implement every GitHub
validation, paging, rate limit or authentication behaviour. Both fresh Git
objects and branches are tiny fixtures. In this S11 run fetches exercised ref
listing and selected FETCH_HEAD results only: the objects were already local
and the journal records no acquisition call. Forced missing-object acquisition
remains separately evidenced by accepted S10 B, not re-proven by S11.

Grants are explicit trusted fixture scopes, not widened LocalRunner or authority
defaults. The synthetic token stays host-side. Actual inspected container env
keys and mount destinations qualify the selected boundary; this is not hostile
code/network confinement. General GraphQL/mutations/API writes, paging,
credential export, aliases/extensions and unsupported targets refuse explicitly.
65,536-byte inputs, 1 MiB responses, 30-node queries and existing Git bundle
limits may refuse larger valid requests; large-repository acceptance is absent.

Windows/systemd whole-tree loss and independent grant revocation remain the
separate accepted #104 evidence, not re-proven by the fixture renewal thread.
Pre-upgrade scopes lacking a PR base fail closed; restart recovery remains out
of scope. Cross-run existing-branch adoption, stage cleanup campaign #93/#97,
Langflow integration, real-agent cancellation and Q11 remain separate.

#100 closure requires independent post-run assessment and a merged specs result.
This report alone is not an independent verdict or permission to promote those
other capabilities.
