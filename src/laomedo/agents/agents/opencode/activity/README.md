# OpenCode native activity

Native OpenCode message/session projection and native-history evidence belong
to this provider. `project` converts explicitly bound native history;
`estimate_native` distinguishes native usage/cost from API-equivalent estimates;
`export_attempt` retains the bound attempt after execution closes. Do not infer
parentage from timestamps or fill absent usage with zero. Shared storage consumes
canonical records; it must not reproduce these native parsers.

## Native token conversion

`OpenCodeTokenUsage` in `models.py` groups the five already validated native
counters. `to_activity_usage()` derives the shared `TokenUsage` object; its
`to_payload()` preserves the six existing normalized fields and arithmetic.
`from_native()` validates the closed set of required counters; `plus()` adds
disjoint message counters; `to_native_payload()` preserves the runner's native
wire shape. Root run usage sums every completed assistant step in the current
attempt, excluding the Resume baseline. Child and inclusive totals remain in
Activity. Any missing or invalid step makes the root attempt total unknown.
The projection retains native admission and incomplete-usage handling. These
objects introduce no new model, price, version or provider capability assumptions.

## Shared response envelope

Native parsing remains here; the final response composes the shared
`ActivityProjection` in `agents/activity/models.py`. Its explicit
`to_usage_first_payload()` method names this provider's existing field ordering
and retains absent diagnostics. No provider-specific envelope model or new native
validation is introduced. See the shared Activity README for method vocabulary,
reference preservation and the internal-only byte compatibility controls.
