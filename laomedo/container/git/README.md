# Opt-in Git-capable agent image

The historical `laomedo-codex-boundary:0.159.2` image is unchanged and has no
Git executable. This derivative adds Git only for `--git-workspace`; it does
not include `gh`, a GitHub token, or a credential helper.

Build from the pinned local base image, then check the result against
`GIT_IMAGE_ID` in `laomedo/local_runner.py`:

```sh
docker build --provenance=false --tag laomedo-codex-git:0.159.2 laomedo/container/git
docker image inspect laomedo-codex-git:0.159.2 --format '{{.Id}}'
```

The reviewed local build ID is
`sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78`.
An image built later against changed Debian package indexes can have a
different ID and must be reviewed and repinned; the runner refuses it by
default. A network-disabled, read-only inspection showed Git 2.39.5 and
Codex CLI 0.159.2 in this image. No model turn was run.
