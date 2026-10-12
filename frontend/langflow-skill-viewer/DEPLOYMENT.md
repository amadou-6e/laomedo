# Skill files activation draft

This draft requires owner approval under AGENTS.md after independent review and
passing relevant checks. Implementation approval has not activated it.

Target: existing `laomedo-langflow-view139`, loopback `127.0.0.1:7864`, pinned
image `langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.

Proposed changes only:

1. Mount the reviewed clean Laomedo #154 source read-only at `/workspace`.
2. Mount the pinned overlay build read-only at `/skill-frontend` and record hashes
   of every built asset plus upstream/source revisions before replacement.
3. Add a read-only `/skills` mount from the standing demo's `skill-store` outside
   Git. No personal skill directory, draft workspace or auth profile is mounted.
4. Set `LANGFLOW_FRONTEND_PATH=/skill-frontend`,
   `LAOMEDO_SKILL_STORE=/skills`, `PYTHONPATH=/workspace`.
5. Launch `/app/.venv/bin/python -m uvicorn
   laomedo.langflow_skill_viewer:create_app --factory --host 0.0.0.0 --port 7860`.

Preserve the existing SQLite volume, every saved graph, custom-component catalog,
runner-token mount, automatic loopback login, all other environment settings,
container protections and port binding. Do not restart or modify runner 8780,
its credential connection, permission profile or ledgers. Provider/GitHub secrets
remain where they already reside; the new route uses only Langflow login.

Prepare and inspect a candidate container first, comparing protection settings
and mounts to the current one with exactly the changes above. Refuse unexpected
changes. Avoid replacing the viewer during an active graph request. Rename the
old viewer as rollback rather than removing its volume. Then start the candidate
on the same port and verify saved graph identity plus authenticated skill reads
without executing a graph or spending a turn. Confirm the same database file
`/app/langflow/langflow.db`, existing auto-login superuser, complete Laomedo custom
component catalog, worker/time-limit settings and identical saved-flow exports.
Any unconfirmed setting refuses activation. On failure, restore the old viewer
and its unchanged volume. This does not authorize screenshot regeneration,
model calls, GitHub publication writes or issue-state changes.
