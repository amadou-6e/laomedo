# Saved-flow API adapter probe for #77

This credential-free probe uses a disposable Langflow 1.12.3 server with
`LANGFLOW_AUTO_LOGIN=true` on a loopback-published port. It imports the
synthetic EXP-03 flow, fetches its saved export through
`GET /api/v1/flows/{id}`, and runs that export through the installed
`FrozenLangflowStage` adapter in the same container. The first stage pauses;
the probe edits the saved flow's marker and code through `PATCH`, resumes the
first stage, then fetches and runs the changed export. It checks old/new
outputs, graph and component revisions, and durable dispatch count.

The probe requires the Laomedo checkout mounted read-only at `/repo`, with
`PYTHONPATH=/repo`. Run `python /repo/experiments/exp77/api_probe.py` inside the
disposable server container after `/health` responds. The script prints only a
sanitized JSON summary. The auto-login token stays in process memory and is
never written or printed. Remove the container after the run; no personal
provider login, model call, GitHub write or production repository is used.

This checks the local in-process execution path from a real saved-flow API
export. It does not attest a remote Langflow `/run/{flow_id}` response or the
Work Graph/grant boundary in #82.
