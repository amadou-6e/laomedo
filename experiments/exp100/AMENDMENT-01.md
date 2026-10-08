# EXP-100/S2 amendment 01: isolate checks before implementation

Committed after the read-only pre-run review of `PROTOCOL-02.md` at `67989d4`
and before any S2 implementation or recorded run. The reviewer disapproved
the original protocol because multiple unrelated failures could satisfy its
generic “rejected” outcomes. This amendment is part of the frozen protocol;
it does not erase that review. No S2 probe has run.

## Fixed evaluation order and reason codes

The host verifier first checks the bundle file shape/version/object format,
then the advertised ref count/name/type, then imports into its private seeded
bare repository with object verification enabled, then checks commit type,
baseline ancestry and staged workflow diff. It reports the first applicable
reason from `bundle_invalid`, `bundle_version`, `object_format`, `ref_count`,
`ref_name`, `ref_type`, `missing_prerequisite`, `object_invalid`,
`baseline_ancestry`, `workflow_change` or `accepted`. A case passes only when
its observed reason **exactly** matches the table, not merely when it rejects.
Any unexpected exception, Git timeout or process-cleanup uncertainty fails
the case. Every Git subprocess has a 10-second deadline and killed-process
verification; the probe's total local execution budget is 120 seconds.

| ID | Isolated fixture, otherwise valid | Exact expected reason |
| --- | --- | --- |
| A1 | Agent commit C1 on trusted baseline B, one expected branch ref, self-contained bundle | `accepted` |
| A2 | Agent commit C2 fast-forwards C1; host seed is B plus C1 read from its **own confirmed private stage** and host-written journal | `accepted` |
| M1 | C2 exported thin against C1, host seed has only B, no host C1 confirmation | `missing_prerequisite` |
| R1 | Bundle advertises two valid commit refs, expected branch plus an extra branch | `ref_count` |
| R2 | Bundle advertises one valid commit ref, but its name differs from the bound run branch | `ref_name` |
| R3 | Bundle advertises the expected ref as an annotated tag object rather than a commit | `ref_type` |
| H1 | Self-contained unrelated root commit U, one expected branch ref, B available in host stage | `baseline_ancestry` |
| V1 | Truncated otherwise valid A1 bundle, with header still parseable | `bundle_invalid` |
| W1 | Valid descendant commit changing `.github/workflows/check.yml`, one expected branch ref | `workflow_change` |
| F1 | Version-3 bundle with `@filter` capability, otherwise A1 data | `bundle_version` |
| O1 | Bundle whose object-format declaration differs from B's SHA-1 format | `object_format` |
| I1 | A1 fixture with deliberately invalid tree entry produced by `git mktree --missing` or equivalent; fetch may refuse, but report `object_invalid` only after ref metadata is valid | `object_invalid` |

If Git cannot construct a fixture exactly as specified, record `fixture_unavailable`
for that ID and mark the S2 result incomplete; do not substitute a different
fixture or silently drop it. For R1/R2/R3/H1/W1, the bundle must pass object
import and integrity checks in a control import so no earlier failure can
mask the targeted reason. For V1/F1/O1/I1, a control must prove the same
fixture with only its targeted mutation removed reaches `accepted`. A2 uses
a synthetic host-written `confirmed` journal entry after A1 local staging;
it is not represented as a GitHub push. M1 uses no such entry. Both are
separate observations.

## Observable isolation cases

The hostile agent repo has a hook that writes an agent-local sentinel and a
remote URL aimed at a local listener that counts connections. The host's
global Git config has a distinct `GIT_TRACE` sentinel path and a rewrite to
the same listener. The host verifier must leave the hook sentinel and trace
sentinel absent and listener count zero; it must derive its decision solely
from the private staged objects, not the agent repository after bundle bytes
are copied. For each sentinel, a local positive control intentionally invokes
the corresponding hostile path and must make the detector fire. Alternate
object paths and replace refs are planted only on the agent side; the host
must not reference them. If any detector cannot fire in its control, the
isolation claim is `incomplete`, not a pass. No host checkout is performed;
tree checks use `ls-tree` and `cat-file`.

## Reproduction and reporting

Fix author/committer names, emails, dates and timezone so commit and tree IDs
are reproducible. A fresh temporary run must reproduce every reason, commit
ID, tree ID, sentinel value and provider-call count. Record bundle SHA-256,
Git version and environment, but compare bundle bytes only within the same
Git version. `--record` remains single-use per evidence path; a plain test
must not rewrite the recorded observation. The operation-coverage table is
analysis, not executable evidence. Unsupported and untested entries stay
explicit. No live write or model turn is authorized by this amendment.
