# Docker boundary acceptance

Runs the selected implementation checkout through its production Agent and an
independently launched lease service. Runtime state stays outside Git; only safe
status codes and assertions belong in committed evidence. Never print login files,
API tokens or raw provider responses. No normal runner limits are changed.

`acceptance.py` owns zero-turn admission/catalog discovery and optional bounded
fresh/resume/cancel checks. Pass the implementation checkout explicitly. This
harness lives only on the permanent remote exp history, not the production PR.
## Session-token continuation

The human explicitly authorized borrowing this Codex session's credential.
`--session-login` reads only the needed access credential and account reference
for the existing split-controller constructor. It does not print token values,
copy refresh credentials, create an app-owned OAuth connection, or give the
executor an access credential. Keep normal host refresh ownership unchanged.

A session-only check creates/configures a native session without inference.
`--execute --max-prompts 1` performs only a fresh task. The optional
`--resume-cancel --max-prompts 2` flow performs a new fresh task, resumes that
same native thread and cancels its active second prompt. It does not establish a
successfully completed resumed answer. Check `prompt_started`, cancellation
acknowledgement and terminal status before claiming this combined flow passes.
All prompt allowances apply across invocations, including uncertain submissions;
flags are harness bounds, not renewed authorization.

`--native-model-metadata` observes allowlisted Codex model metadata and the typed
catalog without submitting an inference prompt.
