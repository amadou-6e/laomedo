# Docker boundary acceptance

Runs the selected implementation checkout through its production Agent and an
independently launched lease service. Runtime state stays outside Git; only safe
status codes and assertions belong in committed evidence. Never print login files,
API tokens or raw provider responses. No normal runner limits are changed.

`acceptance.py` owns zero-turn admission/catalog discovery and optional bounded
fresh/resume/cancel checks. Pass the implementation checkout explicitly. This
harness lives only on the permanent remote exp history, not the production PR.
