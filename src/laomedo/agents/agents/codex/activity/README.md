# Codex native evidence

`rollout_export.py` retains explicitly selected native Codex evidence. Its
command-line entrypoint is an existing external interface. Shared
`agents/activity/projection.py` consumes the retained thread/turn/item vocabulary,
including original Codex notifications and explicitly normalized ACP records.
This leaf does not define a separate projector or cost engine. Unknown or partial
usage remains unknown or partial.
