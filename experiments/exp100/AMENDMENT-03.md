# EXP-100/S2 amendment 03: classify a truncated pack at import

Committed before S2 implementation or execution after the review of
amendment 02 at `b2eaae1`. That review found an ambiguity between V1's
`bundle_invalid` reason and the complete-pack object-integrity rule.

The pre-import shape check validates only bundle signature, version,
capabilities and ref header syntax. It does **not** parse the pack body or
compute its trailing checksum. Accordingly, V1 (A1 with a parseable header
but truncated pack) expects `object_invalid`, not `bundle_invalid`: its
first failure must be the import/integrity stage. `bundle_invalid` is
reserved for malformed signature/header or a pack whose header cannot be
parsed at all. A complete pack with invalid object connectivity also reports
`object_invalid`. The observation must record the failing stage as well as
the exact reason code. This explicitly overrides V1's expected reason in
amendment 01; all other frozen cases and controls are unchanged.

Both host-global-config and inherited-environment sentinel paths from
amendment 02 must be absolute paths. No S2 case has yet run.
