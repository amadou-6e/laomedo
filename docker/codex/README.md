# Codex boundary image

This maintained recipe is extracted unchanged from the recorded #122 recipe;
historical sources and evidence remain unchanged. It pins the same base image
and Codex CLI version. It does not contain or copy login material.

Build the local image explicitly:

```powershell
docker build -t laomedo-codex-boundary:0.159.2 docker/codex
docker image inspect laomedo-codex-boundary:0.159.2 --format '{{.Id}}'
```

A rebuild can produce a different immutable image identity. Review the recipe
and record that exact local ID as `image_id` in the trusted runner-service JSON;
do not change the historical default digest or accept an arbitrary browser pin.
The existing preflight still checks the tag against that ID and runs the exact
CLI version in a credential-free restricted container before opening the API.

The normal runner uses the existing dedicated `laomedo-122-docker-auth` volume.
Provision its login through the supported native Codex login flow if needed;
this build and app startup do not create credentials or copy a host profile.
The [managed app launch guide](../../docs/features/agents/runner/local-app.md)
covers recovery, token binding and the independent supervisor.
