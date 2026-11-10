# Historical PR checkpoints: 10 November 2026

This archive preserves existing repository history, not a runnable example or
fresh acceptance result. It belongs to `exp` and must not be merged wholesale
into production. No model, Docker probe, credential copy or external repository
operation was executed to produce this archive.

| PR | Disposition | Reason |
| --- | --- | --- |
| [168](https://github.com/amadou-6e/laomedo/pull/168) | Retire the superseded checkpoint; retain its source branch | Current operations/Activity supersede the old implementation. Preserve its unique demo, inspection and deployment history rather than merging the retired layout. Successors include merged PRs 172, 175, 178 and 249. |
| [71](https://github.com/amadou-6e/laomedo/pull/71) | Archive the completed report and retire the production-targeted PR | Issue 49 is closed. The only change is the historical EXP-19 agent output, preserved byte-for-byte here. It is experiment evidence, not a production feature. |
| [58](https://github.com/amadou-6e/laomedo/pull/58) | Historical snapshot; assessment recommends retiring this implementation, not its unresolved requirement | Its old E05 harness is not current-provider acceptance. Issue 48 remains open; see [the assessment](exp18-assessment.md). PR 58 is left open for the owner's disposition decision. |

`manifest.json` records exact PR heads, trees, patch digests, bundle identity and
the EXP-19 artifact digest. `exp19-agent-output.md` is exactly the 1,024-byte
report from PR 71, SHA-256
`b05e98c3bb4b42cf20c9a3e743bc4e1ec646c63b4a6501ab28b20b02f5dd6f15`.
Its historical claims and limits are not new verification of a current runner.

The three `pr-*.patch` files preserve each head's binary-capable delta from its
recorded merge base with the pre-archive `exp` baseline. They are historical
patches for that base, not patches to apply blindly to current `develop` or `exp`.
`checkpoints.bundle` preserves the exact commits and trees; its prerequisites
are reachable from the recorded `exp` baseline. Original PR branches are retained.

## Recover a checkpoint

In a repository containing the recorded `exp` history:

```sh
git bundle verify checkpoints.bundle
git bundle list-heads checkpoints.bundle
git fetch checkpoints.bundle refs/audits/pr-age-20261110/pr-71:refs/archives/pr-audit-20261110/pr-71
git show refs/archives/pr-audit-20261110/pr-71:experiments/exp19/agent-output.md
```

Use the corresponding advertised ref for PR 168 or 58. Restoring history does
not authorize launching its scripts or reviving historical model allowances.

Verification reconstructs all three heads/trees in a fresh bare repository using
only the `exp` baseline and this bundle, checks the exact report bytes and runs
Git object verification. A credential-shape scan of the archived own patches
found no matches; it is not a guarantee that every historical ancestor is free
of sensitive content. No private runtime/profile state was collected.
