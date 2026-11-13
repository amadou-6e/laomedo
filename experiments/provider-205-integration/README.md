# Provider interactive validation experiments

`validation_server.py` launches explicitly selected Codex, Claude or OpenCode
fresh/resume graph previews with private temporary state and the maintained graph
builder. Startup discovers real models but submits no prompt. `--resume` preserves
the selected graph, runner address and private profile. Servers remain available
for owner inspection; profile disposal belongs to ending that validation session.

`opencode_profile.py` is experiment-only credential preparation. It adapts the
previously archived Console account reader to the current shared redirect policy,
reads only the active account from the host database in read-only mode, checks
expiry and trusted HTTPS routing, and writes the selected credential/validity and
supported SDK routing to an ACL-restricted temporary profile. It never copies a
refresh token or prints account/credential values. The production OpenCode runner
continues to accept only an explicitly prepared private profile; no retired helper
is restored to production and production tests do not import this experiment.
