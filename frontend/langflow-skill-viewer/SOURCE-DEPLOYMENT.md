# Linked-source selector activation draft

Not activated. Apply only after independent review and explicit configuration approval.

Target: the existing single-user Langflow viewer on 7864, with its saved flow,
auto-login, database and runner on 8780 preserved. No model turns or publication
requests are part of activation. Existing run budgets and permissions stay unchanged.

Start one independent hidden host process for `laomedo.skill_source_server` from
this reviewed implementation, listening on loopback 8782. Use the existing runner
API transport-token file; do not print it or create another human login. Store
cache/index in the existing private standing demo state under a new `skill-sources`
folder. Registry is the existing standing demo skill-store. Allowed local roots:
the visible `specs/shared/skills`, `my-skills` and Laomedo's skill viewer example
folder. No whole-home or whole-workspace root is granted.

Create a candidate viewer using the pinned Langflow image and this reviewed app
source. Add only the source URL http://host.docker.internal:8782 and backend token
file setting. Preserve all existing mounts, network/protections, database volume,
auto-login and other environment settings. Mount a separately built frontend
read-only; do not rebuild the assets mounted by the active viewer in place.
Retain the stopped old viewer for rollback and compare owned saved flows exactly,
built-in template JSON semantically, user identity and database settings.

Set the existing demo Skill Source to the host registry path, select live-report
and the exact current sha256:3f6d9c52b1d4ad5777651fc600e1e9a86f8fae7b842438a045bc730c37f46349
revision. This preserves the runner's existing frozen accepted skill pin. Source
and discovery choices are nonsecret; no provider/GitHub credential is added to the
viewer or node. Preserve the original saved node for rollback.

Verify browser source discovery, typed filtering, revision selection and nested
file inspection without pressing Run. Stop and restore the old viewer on a failed
preservation check. Leave services and exact activation observations in ignored
local records. Changes to allowed roots or private repository connections require
a separate concrete configuration draft.
