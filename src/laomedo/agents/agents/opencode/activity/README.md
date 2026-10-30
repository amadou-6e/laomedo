# OpenCode native activity

Native OpenCode message/session projection and native-history evidence belong
to this provider. `project` converts explicitly bound native history;
`estimate_native` distinguishes native usage/cost from API-equivalent estimates;
`export_attempt` retains the bound attempt after execution closes. Do not infer
parentage from timestamps or fill absent usage with zero. Shared storage consumes
canonical records; it must not reproduce these native parsers.
# Native token conversion

`OpenCodeTokenUsage` in `models.py` groups the five already validated native
counters. `to_activity_usage()` derives the shared `TokenUsage` object; its
`to_payload()` preserves the six existing normalized fields and arithmetic.
The projection retains native admission and incomplete-usage handling. These
objects introduce no new model, price, version or provider capability assumptions.
