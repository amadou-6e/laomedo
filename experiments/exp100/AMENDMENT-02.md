# EXP-100/S2 amendment 02: make the config detector executable

Committed before S2 implementation or execution, after the read-only review
of amendment 01 at `7a08798`. That review found its `GIT_TRACE` global-config
detector impossible: `GIT_TRACE` is an environment variable, not a config key.

Replace that detector with two independent, positively controlled sentinels:

- Plant `trace2.normalTarget=<host-global-sentinel>` in the **host's global
  Git config**. A control Git command with that config enabled must create
  the sentinel. The verifier's Git command must leave it absent.
- Plant `GIT_TRACE=<host-environment-sentinel>` in the **host process
  environment**. A control Git command inheriting it must create the
  sentinel. The verifier's Git command must leave it absent.

The other amendment-01 controls remain. If either positive control fails,
report `incomplete`, not a pass or a substituted detector. The post-import
type check reports `ref_type`; the pre-import ref check covers only count and
name. `missing_prerequisite` is reserved for an absent prerequisite declared
in the bundle header; a bundle with no declared prerequisite that fails
object-integrity checking reports `object_invalid`. If an annotated-tag
branch-ref fixture cannot be constructed exactly, R3 is
`fixture_unavailable` and S2 is incomplete.
